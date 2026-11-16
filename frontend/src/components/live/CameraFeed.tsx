import clsx from "clsx";
import { Maximize2, Minimize2, RefreshCw, VideoOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLive } from "@/context/LiveContext";
import { getTicket } from "@/lib/api";
import { CAM_STATUS_COLOR, DIR_LABEL, HEAD_COLOR, LEVEL_COLOR } from "@/lib/format";
import type { Direction, DirectionMetrics, FrameObject, FrameTrack, FramesMessage, HeadColor } from "@/lib/types";
import { Badge, Dot } from "../ui/primitives";
import { drawBackground, drawNoise, drawOverlay, drawVehicle } from "./sceneRenderer";

interface FrameState {
  t: number;
  objects: Map<number, FrameObject>;
  tracks: Map<number, FrameTrack>;
  status: string;
  signal: HeadColor;
}

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

export function CameraFeed({
  direction,
  metrics,
  showBoxes,
  showRoi,
  expanded,
  onToggleExpand,
  signal,
}: {
  signal: HeadColor;
  direction: Direction;
  metrics: DirectionMetrics | undefined;
  showBoxes: boolean;
  showRoi: boolean;
  expanded?: boolean;
  onToggleExpand?: () => void;
}) {
  const { subscribeFrames } = useLive();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const bgRef = useRef<HTMLCanvasElement | null>(null);
  const prevRef = useRef<FrameState | null>(null);
  const curRef = useRef<FrameState | null>(null);
  const optsRef = useRef({ showBoxes, showRoi, metrics });
  optsRef.current = { showBoxes, showRoi, metrics };

  const cam = metrics?.camera;
  const geometry = metrics?.geometry;
  const isReal = cam?.mjpeg;

  useEffect(() => {
    return subscribeFrames((f: FramesMessage) => {
      const c = f.cameras[direction];
      if (!c) return;
      prevRef.current = curRef.current;
      curRef.current = {
        t: performance.now(),
        objects: new Map(c.objects.map((o) => [o[7], o])),
        tracks: new Map(c.tracks.map((t) => [t[0], t])),
        status: c.status,
        signal: c.signal,
      };
    });
  }, [subscribeFrames, direction]);

  // Render loop
  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap || isReal) return;
    let raf = 0;
    let size = { w: 0, h: 0, dpr: 1 };
    let bgKey = "";

    const resize = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      size = { w: Math.max(1, Math.floor(r.width)), h: Math.max(1, Math.floor(r.height)), dpr };
      canvas.width = size.w * dpr;
      canvas.height = size.h * dpr;
      canvas.style.width = `${size.w}px`;
      canvas.style.height = `${size.h}px`;
      bgKey = "";
    };
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    resize();

    const render = () => {
      raf = requestAnimationFrame(render);
      const ctx = canvas.getContext("2d");
      const { metrics: m, showBoxes: sb, showRoi: sr } = optsRef.current;
      if (!ctx || !m) return;
      const { w, h, dpr } = size;
      const calib = m.geometry.calibration;
      const key = `${w}x${h}:${calib.lanes}`;
      if (key !== bgKey) {
        const bg = document.createElement("canvas");
        bg.width = w * dpr;
        bg.height = h * dpr;
        const bctx = bg.getContext("2d")!;
        bctx.scale(dpr, dpr);
        drawBackground(bctx, w, h, calib);
        bgRef.current = bg;
        bgKey = key;
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const cur = curRef.current;
      const online = m.camera && m.camera.status !== "OFFLINE" && cur && cur.status !== "OFFLINE";
      if (!online) {
        const isDark = document.documentElement.classList.contains("dark") || document.documentElement.getAttribute("data-theme") === "dark";
        ctx.fillStyle = isDark ? "#0c1322" : "#e6ebf1";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.scale(dpr, dpr);
        drawNoise(ctx, w, h, 2.5);
        return;
      }
      ctx.drawImage(bgRef.current!, 0, 0);
      ctx.scale(dpr, dpr);
      const prev = prevRef.current;
      const k = prev ? Math.min(1, (performance.now() - cur.t) / 100) : 1;
      const objs: FrameObject[] = [];
      cur.objects.forEach((o, id) => {
        const p = prev?.objects.get(id);
        objs.push(p ? [lerp(p[0], o[0], k), lerp(p[1], o[1], k), lerp(p[2], o[2], k), lerp(p[3], o[3], k), o[4], o[5], o[6], o[7]] : o);
      });
      objs.sort((a, b) => a[3] - b[3]); // xa vẽ trước, gần vẽ sau
      for (const o of objs) drawVehicle(ctx, o, w, h);
      const trs: FrameTrack[] = [];
      cur.tracks.forEach((t, id) => {
        const p = prev?.tracks.get(id);
        trs.push(p ? [t[0], lerp(p[1], t[1], k), lerp(p[2], t[2], k), lerp(p[3], t[3], k), lerp(p[4], t[4], k), t[5], t[6], t[7]] : t);
      });
      drawOverlay(ctx, w, h, m.geometry.roi, m.geometry.counting_line, trs, sr, sb);
      const degraded = m.camera?.status === "DEGRADED";
      if (degraded) {
        drawNoise(ctx, w, h, 2.2);
        ctx.fillStyle = "rgba(226,232,240,0.25)";
        ctx.fillRect(0, 0, w, h);
      }
    };
    render();
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [isReal, geometry?.calibration.lanes]);

  const status = cam?.status ?? "NO_CAMERA";
  const sig = metrics ? signal : "OFF";
  const inRoi = metrics ? Object.values(metrics.in_roi).reduce((a, b) => a + b, 0) : 0;
  const off = status === "OFFLINE";
  const camId = cam?.id;
  const wantStream = Boolean(isReal && camId != null && !off);

  // Luồng MJPEG: xin vé dùng một lần rồi mới gắn src (không đặt JWT lên URL). Vé chỉ dùng được một lần,
  // nên khi <img> lỗi/rớt kết nối thì xin vé mới (streamReload) với độ trễ tăng dần (streamFails).
  const [streamSrc, setStreamSrc] = useState<string | null>(null);
  const [streamReload, setStreamReload] = useState(0);
  const streamFails = useRef(0);
  const retryStream = () => {
    streamFails.current += 1;
    setStreamReload((n) => n + 1);
  };
  useEffect(() => {
    setStreamSrc(null);
    if (!wantStream || camId == null) return;
    let cancelled = false;
    const fails = streamFails.current;
    const delay = fails === 0 ? 0 : Math.min(1000 * 2 ** Math.min(fails, 4), 15000);
    const timer = window.setTimeout(() => {
      getTicket("stream", camId)
        .then((t) => {
          if (!cancelled) setStreamSrc(`/api/cameras/${camId}/stream.mjpg?ticket=${encodeURIComponent(t)}`);
        })
        .catch(() => {
          if (!cancelled) retryStream();
        });
    }, delay);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantStream, camId, streamReload]);

  return (
    <div
      className={clsx(
        "group flex min-h-0 flex-col overflow-hidden rounded-card border bg-surface shadow-panel transition-all hover:border-auto/60 hover:shadow-md",
        off ? "border-stop/70 ring-1 ring-stop/30" : status === "DEGRADED" ? "border-warn/70 ring-1 ring-warn/30" : "border-line/80",
      )}
    >
      {/* Thanh thông tin trên */}
      <div className="flex items-center justify-between gap-2 border-b border-line/70 bg-panel/30 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex items-center gap-1.5 text-[13px] font-bold tracking-tight text-ink" title="Đèn tín hiệu hướng này">
            <Dot color={HEAD_COLOR[sig as HeadColor] ?? "#94A3B8"} size={10} pulse={sig === "FLASHING_YELLOW"} />
            {DIR_LABEL[direction]}
          </span>
          <span className="num truncate text-2xs font-medium text-ink-mute">
            {cam?.code ?? "Chưa gắn camera"} · {cam?.resolution ?? "—"} · #{cam?.frame_no ?? 0}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge color={CAM_STATUS_COLOR[status]} pulse={off}>
            {status}
          </Badge>
          {onToggleExpand && (
            <button
              onClick={onToggleExpand}
              className="rounded-ctl p-1 text-ink-mute transition-colors hover:bg-panel hover:text-ink"
              aria-label={expanded ? "Thu nhỏ" : "Phóng to camera"}
              title={expanded ? "Về lưới 2×2" : "Phóng to hướng này"}
            >
              {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
          )}
        </div>
      </div>

      {/* Khung hình Video / Canvas */}
      <div ref={wrapRef} className="relative aspect-video w-full bg-slate-950/20">
        {isReal && cam && !off ? (
          streamSrc && <img
            src={streamSrc}
            onLoad={() => (streamFails.current = 0)}
            onError={retryStream}
            alt={`Camera ${cam.code}`}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : (
          <canvas ref={canvasRef} className="absolute inset-0" aria-label={`Luồng camera hướng ${DIR_LABEL[direction]}`} />
        )}
        {off && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-stop/10 p-4 text-center backdrop-blur-sm">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-stop/20 text-stop">
              <VideoOff className="h-6 w-6" />
            </div>
            <div className="text-sm font-bold tracking-wider text-stop-ink">MẤT TÍN HIỆU CAMERA</div>
            <div className="max-w-[80%] text-xs text-ink-dim">{cam?.error ?? "Không nhận được khung hình từ thiết bị"}</div>
            {cam?.next_reconnect_in != null && (
              <div className="num mt-1 flex items-center gap-1.5 rounded-full bg-panel/80 px-2.5 py-1 text-2xs font-semibold text-ink-mute">
                <RefreshCw className="h-3 w-3 animate-spin text-auto" />
                Kết nối lại lần {cam.reconnect_attempts + 1} sau {Math.ceil(cam.next_reconnect_in)}s
              </div>
            )}
          </div>
        )}
      </div>

      {/* Thanh thông số dưới */}
      <div className="flex items-center justify-between gap-2 border-t border-line/70 bg-surface/50 px-3 py-1.5 text-2xs">
        {metrics && !off ? (
          <>
            <span className="num truncate font-medium text-ink-mute">
              <span className="font-bold text-ink">{cam?.fps.toFixed(1)}</span> fps · {((cam?.bitrate_kbps ?? 0) / 1000).toFixed(2)} Mbps · {cam?.latency_ms} ms
            </span>
            <span className="flex shrink-0 items-center gap-2.5">
              <span className="num font-medium text-ink-mute" title="Số xe trong ROI · độ dài hàng đợi">
                <span className="font-bold text-ink">{inRoi}</span> xe · <span className="font-bold text-ink">{metrics.queue_m.toFixed(0)}</span> m
              </span>
              <Badge color={LEVEL_COLOR[metrics.level]}>{metrics.density_smoothed.toFixed(0)}%</Badge>
            </span>
          </>
        ) : (
          <span className="text-ink-mute">{off ? "Không có dữ liệu" : "Đang chờ dữ liệu…"}</span>
        )}
      </div>
    </div>
  );
}
