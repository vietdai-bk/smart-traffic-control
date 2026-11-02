import { Cctv, FlaskConical, Grid2x2, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { AdaptivePlanCard } from "@/components/live/AdaptivePlanCard";
import { AlertsPanel } from "@/components/live/AlertsPanel";
import { CameraFeed } from "@/components/live/CameraFeed";
import { DirectionMetrics } from "@/components/live/DirectionMetrics";
import { InsightPanel } from "@/components/live/InsightPanel";
import { IntersectionTwin } from "@/components/live/IntersectionTwin";
import { LlmSupervisorCard } from "@/components/live/LlmSupervisorCard";
import { SignalControlPanel } from "@/components/live/SignalControlPanel";
import { SimulationTools, activeSimCount } from "@/components/live/SimulationTools";
import { Drawer } from "@/components/ui/Drawer";
import { Toggle } from "@/components/ui/Form";
import { Button, Panel, Segmented, Spinner } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";
import { api } from "@/lib/api";
import { DIRECTIONS, DIR_LABEL, LEVEL_COLOR, LEVEL_LABEL, MODE_COLOR, MODE_LABEL, fmtInt, tone } from "@/lib/format";
import type { Direction, Intersection, Snapshot } from "@/lib/types";
import { useDevice } from "@/lib/useMedia";

function KpiStrip({ s }: { s: Snapshot }) {
  const items: { label: string; value: string; unit?: string; color?: string; sub?: string }[] = [
    { label: "Chế độ điều khiển", value: s.signal.mode, color: MODE_COLOR[s.signal.mode], sub: MODE_LABEL[s.signal.mode] },
    { label: "Tình trạng chung", value: LEVEL_LABEL[s.kpi.worst_level], color: LEVEL_COLOR[s.kpi.worst_level], sub: `Mật độ TB ${s.kpi.avg_density.toFixed(0)}%` },
    { label: "Thời gian chờ TB", value: s.kpi.avg_wait_s == null ? "—" : s.kpi.avg_wait_s.toFixed(1), unit: "s", sub: "5 phút gần nhất" },
    { label: "Lưu lượng thông qua", value: fmtInt(s.kpi.flow_vph), unit: "xe/h", sub: "Tổng 4 hướng" },
    { label: "Đã đếm hôm nay", value: fmtInt(s.kpi.today_total), unit: "xe", sub: "Tích lũy từ 00:00" },
    { label: "Chu kỳ AI đề xuất", value: s.plan ? s.plan.cycle_s.toFixed(0) : "—", unit: "s", sub: s.plan ? `Tỷ số Y = ${s.plan.flow_ratio_total.toFixed(2)}` : undefined },
  ];
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 min-[1600px]:grid-cols-6">
      {items.map((it) => (
        <div
          key={it.label}
          className="relative min-w-0 rounded-panel border border-line/80 bg-surface p-3 shadow-panel transition-all hover:border-auto/50"
        >
          {it.color && (
            <span
              className="absolute inset-x-0 top-0 h-[3px] rounded-t-panel"
              style={{ background: it.color }}
            />
          )}
          <div className="label truncate">{it.label}</div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span
              className="num truncate text-xl font-bold tracking-tight"
              style={it.color ? { color: tone(it.color, 85) } : undefined}
            >
              {it.value}
            </span>
            {it.unit && <span className="text-2xs font-semibold text-ink-mute">{it.unit}</span>}
          </div>
          {it.sub && <div className="mt-0.5 truncate text-2xs text-ink-mute">{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}

/**
 * Bố cục Trung tâm Giám sát & Điều khiển:
 *  - Cột chính: chỉ số KPI tổng quan → camera 4 hướng → lưu lượng theo hướng → đề xuất AI + hiệu suất/nhật ký.
 *  - Cột phải (dính khi cuộn): mô phỏng nút giao → điều khiển đèn → cảnh báo nóng.
 */
export default function CommandCenterPage() {
  const { snapshot, selectedId, status } = useLive();
  const { can } = useAuth();
  const [intersections, setIntersections] = useState<Intersection[]>([]);
  const device = useDevice();
  // Adaptive: điện thoại mặc định xem 1 camera (đỡ băng thông & dễ nhìn), máy lớn xem lưới 2×2
  const [layout, setLayout] = useState<"grid" | "single">(() => (window.matchMedia("(max-width: 767px)").matches ? "single" : "grid"));
  useEffect(() => {
    if (device === "phone") setLayout("single");
  }, [device]);
  const [focus, setFocus] = useState<Direction>("NORTH");
  const [showBoxes, setShowBoxes] = useState(true);
  const [showRoi, setShowRoi] = useState(true);
  const [simOpen, setSimOpen] = useState(false);

  useEffect(() => {
    api.get<Intersection[]>("/intersections").then(setIntersections).catch(() => undefined);
  }, [selectedId]);

  const info = intersections.find((i) => i.id === selectedId);
  const snap = snapshot && snapshot.intersection_id === selectedId ? snapshot : null;

  if (!snap) return <Spinner label={status === "open" ? "Đang nhận dữ liệu nút giao…" : "Đang kết nối luồng dữ liệu thời gian thực…"} />;

  const dirs = layout === "grid" ? DIRECTIONS : [focus];
  const sims = activeSimCount(snap);

  return (
    <div className="grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_440px]">
      {/* ---------------- Cột chính ---------------- */}
      <div className="min-w-0 space-y-3">
        <KpiStrip s={snap} />

        <Panel
          title={`Camera 4 hướng${info ? ` · ${info.name}` : ""}`}
          icon={<Cctv className="h-4 w-4 text-auto" />}
          actions={
            <div className="flex flex-wrap items-center gap-2.5">
              <Toggle checked={showBoxes} onChange={setShowBoxes} label="AI overlay" />
              <Toggle checked={showRoi} onChange={setShowRoi} label="ROI & vạch đếm" />
              {layout === "single" && (
                <Segmented size="sm" value={focus} onChange={setFocus} options={DIRECTIONS.map((d) => ({ id: d, label: device === "phone" ? DIR_LABEL[d].slice(0, 1) : DIR_LABEL[d] }))} />
              )}
              {device !== "phone" && <Segmented
                size="sm"
                value={layout}
                onChange={setLayout}
                options={[
                  { id: "grid", label: <Grid2x2 className="h-3.5 w-3.5" aria-label="Lưới 2×2" /> },
                  { id: "single", label: <Square className="h-3.5 w-3.5" aria-label="Một hướng" /> },
                ]}
              />}
              {can("sim:control") && (
                <Button size="sm" variant={sims ? "warn" : "secondary"} icon={<FlaskConical className="h-3.5 w-3.5" />} onClick={() => setSimOpen(true)}>
                  Giả lập{sims ? ` (${sims})` : ""}
                </Button>
              )}
            </div>
          }
          bodyClassName="p-2.5"
        >
          <div className={layout === "grid" ? "grid grid-cols-1 gap-2.5 md:grid-cols-2" : "mx-auto max-w-[1100px]"}>
            {dirs.map((d) => (
              <CameraFeed
                key={`${selectedId}-${d}`}
                direction={d}
                metrics={snap.directions[d]}
                signal={snap.signal.heads[d].color}
                showBoxes={showBoxes}
                showRoi={showRoi}
                expanded={layout === "single"}
                onToggleExpand={() => {
                  if (layout === "grid") {
                    setFocus(d);
                    setLayout("single");
                  } else setLayout("grid");
                }}
              />
            ))}
          </div>
        </Panel>

        <DirectionMetrics snap={snap} />

        {/* Điều khiển 3 tầng: LLM chọn chiến lược → Webster tính thời gian xanh → bộ khoá an toàn (cột phải) */}
        <div className="grid gap-3 lg:grid-cols-2">
          <LlmSupervisorCard snap={snap} />
          <AdaptivePlanCard snap={snap} />
        </div>
        <InsightPanel snap={snap} />
      </div>

      {/* ---------------- Cột phải: luôn trong tầm mắt ---------------- */}
      <aside className="space-y-3 xl:sticky xl:top-[calc(var(--header-h,57px)+12px)] xl:max-h-[calc(100vh-var(--header-h,57px)-24px)] xl:overflow-y-auto xl:pb-1 xl:pr-1">
        <Panel title="Mô phỏng nút giao" bodyClassName="grid-bg p-2 flex items-center justify-center">
          <div className="aspect-square w-full max-w-[360px]">
            <IntersectionTwin snap={snap} nsRoad={info?.ns_road ?? "Trục Bắc–Nam"} ewRoad={info?.ew_road ?? "Trục Đông–Tây"} />
          </div>
        </Panel>
        <SignalControlPanel snap={snap} />
        <AlertsPanel intersectionId={selectedId} />
      </aside>

      <Drawer
        open={simOpen}
        onClose={() => setSimOpen(false)}
        title="Giả lập tình huống giao thông"
        icon={<FlaskConical className="h-4 w-4 text-warn" />}
      >
        <SimulationTools snap={snap} />
      </Drawer>
    </div>
  );
}
