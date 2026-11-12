import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import type { Alert, FramesMessage, Incident, IntersectionSummary, Snapshot } from "@/lib/types";
import { useAuth } from "./AuthContext";
import { useToast } from "./ToastContext";

export type WsStatus = "connecting" | "open" | "closed";

export interface LogEvent {
  id: number;
  created_at: string;
  category: string;
  action: string;
  username: string;
  description: string;
  result: string;
  intersection_id: number | null;
}

interface LiveState {
  status: WsStatus;
  latencyMs: number | null;
  summary: IntersectionSummary[];
  selectedId: number | null;
  select: (id: number) => void;
  snapshot: Snapshot | null;
  subscribeFrames: (fn: (f: FramesMessage) => void) => () => void;
  activeAlerts: Alert[];
  openIncidents: Incident[];
  logs: LogEvent[];
  refreshAlerts: () => void;
  muted: boolean;
  setMuted: (m: boolean) => void;
}

const LiveCtx = createContext<LiveState | null>(null);
const SEL_KEY = "stcs.intersection";

function beep(critical: boolean) {
  try {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AC();
    const pattern = critical ? [880, 660, 880] : [740];
    pattern.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(0.06, ctx.currentTime + i * 0.18 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.18 + 0.15);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + i * 0.18);
      osc.stop(ctx.currentTime + i * 0.18 + 0.16);
    });
    window.setTimeout(() => ctx.close(), 1000);
  } catch {
    /* trình duyệt chặn âm thanh khi chưa có tương tác */
  }
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const { token, can } = useAuth();
  const toast = useToast();
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [latencyMs, setLatency] = useState<number | null>(null);
  const [summary, setSummary] = useState<IntersectionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const v = localStorage.getItem(SEL_KEY);
    return v ? Number(v) : null;
  });
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([]);
  const [openIncidents, setOpenIncidents] = useState<Incident[]>([]);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [muted, setMutedState] = useState(() => localStorage.getItem("stcs.muted") === "1");
  const wsRef = useRef<WebSocket | null>(null);
  const frameSubs = useRef(new Set<(f: FramesMessage) => void>());
  const selectedRef = useRef(selectedId);
  const mutedRef = useRef(muted);
  selectedRef.current = selectedId;
  mutedRef.current = muted;

  const setMuted = useCallback((m: boolean) => {
    localStorage.setItem("stcs.muted", m ? "1" : "0");
    setMutedState(m);
  }, []);

  const refreshAlerts = useCallback(() => {
    if (!can("alerts:view")) return;
    api.get<Alert[]>("/alerts/active").then(setActiveAlerts).catch(() => undefined);
    api
      .get<{ items: Incident[] }>("/incidents?status=OPEN&page_size=100")
      .then((r) => setOpenIncidents(r.items))
      .catch(() => undefined);
  }, [can]);

  const select = useCallback((id: number) => {
    localStorage.setItem(SEL_KEY, String(id));
    setSelectedId(id);
    setSnapshot((s) => (s && s.intersection_id === id ? s : null));
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "subscribe", intersection_id: id }));
  }, []);

  const subscribeFrames = useCallback((fn: (f: FramesMessage) => void) => {
    frameSubs.current.add(fn);
    return () => {
      frameSubs.current.delete(fn);
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    refreshAlerts();
    let stopped = false;
    let retry = 0;
    let pingTimer: number | undefined;
    let reconnectTimer: number | undefined;

    const connect = () => {
      if (stopped) return;
      setStatus("connecting");
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/live?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;
      ws.onopen = () => {
        retry = 0;
        setStatus("open");
        if (selectedRef.current) ws.send(JSON.stringify({ type: "subscribe", intersection_id: selectedRef.current }));
        pingTimer = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping", t: performance.now() }));
        }, 3000);
        refreshAlerts();
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        switch (msg.type) {
          case "frames":
            if (msg.intersection_id === selectedRef.current) frameSubs.current.forEach((fn) => fn(msg));
            break;
          case "snapshot":
            if (msg.intersection_id === selectedRef.current) setSnapshot(msg);
            break;
          case "hello":
          case "summary": {
            const list: IntersectionSummary[] = msg.type === "hello" ? msg.summary : msg.data;
            setSummary(list);
            if (list.length && (selectedRef.current == null || !list.some((x) => x.id === selectedRef.current))) {
              const id = list[0].id;
              selectedRef.current = id;
              localStorage.setItem(SEL_KEY, String(id));
              setSelectedId(id);
              ws.send(JSON.stringify({ type: "subscribe", intersection_id: id }));
            }
            break;
          }
          case "pong":
            if (typeof msg.t === "number") setLatency(Math.round(performance.now() - msg.t));
            break;
          case "alert": {
            const a: Alert = msg.data;
            setActiveAlerts((xs) => {
              const rest = xs.filter((x) => x.id !== a.id);
              return a.status === "RESOLVED" ? rest : [a, ...rest];
            });
            if (msg.event === "created" || (msg.event === "updated" && a.level === "CRITICAL" && a.status === "ACTIVE")) {
              const critical = a.level === "CRITICAL";
              toast(critical ? "error" : "warning", a.title, a.message);
              if (!mutedRef.current) beep(critical);
            }
            break;
          }
          case "incident": {
            const inc: Incident = msg.data;
            setOpenIncidents((xs) => {
              const rest = xs.filter((x) => x.id !== inc.id);
              return inc.status === "RESOLVED" ? rest : [inc, ...rest];
            });
            if (msg.event === "created") {
              toast(inc.severity === "CRITICAL" ? "error" : "warning", `Sự cố thiết bị ${inc.device_code}`, inc.message);
              if (!mutedRef.current) beep(inc.severity === "CRITICAL");
            } else if (msg.event === "recovered") {
              toast("success", `${inc.device_code} đã kết nối lại`, "Thiết bị hoạt động trở lại — chờ xác nhận khắc phục.");
            }
            break;
          }
          case "log":
            setLogs((xs) => [msg.data as LogEvent, ...xs].slice(0, 60));
            break;
          default:
            break;
        }
      };
      ws.onclose = (ev) => {
        window.clearInterval(pingTimer);
        setStatus("closed");
        if (stopped || ev.code === 4401) return;
        retry += 1;
        reconnectTimer = window.setTimeout(connect, Math.min(1000 * 2 ** Math.min(retry, 4), 15000));
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearInterval(pingTimer);
      window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [token, refreshAlerts, toast]);

  const value = useMemo(
    () => ({
      status,
      latencyMs,
      summary,
      selectedId,
      select,
      snapshot,
      subscribeFrames,
      activeAlerts,
      openIncidents,
      logs,
      refreshAlerts,
      muted,
      setMuted,
    }),
    [status, latencyMs, summary, selectedId, select, snapshot, subscribeFrames, activeAlerts, openIncidents, logs, refreshAlerts, muted, setMuted],
  );
  return <LiveCtx.Provider value={value}>{children}</LiveCtx.Provider>;
}

export function useLive() {
  const ctx = useContext(LiveCtx);
  if (!ctx) throw new Error("useLive phải dùng trong LiveProvider");
  return ctx;
}
