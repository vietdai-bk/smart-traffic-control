import clsx from "clsx";
import {
  BarChart3,
  Bell,
  BellOff,
  ChevronDown,
  LogOut,
  MonitorDot,
  Moon,
  Radio,
  Settings2,
  ShieldAlert,
  Siren,
  Sparkles,
  Sun,
  TrafficCone,
  Users,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";
import { useTheme } from "@/context/ThemeContext";
import { LEVEL_COLOR, MODE_COLOR, MODE_LABEL, tone } from "@/lib/format";
import { ROLE_COLOR, ROLE_LABEL, type Perm } from "@/lib/permissions";
import { Badge, Dot } from "../ui/primitives";

interface NavItem {
  to: string;
  label: string;
  hint: string;
  icon: ReactNode;
  perms: Perm[];
}

const NAV: NavItem[] = [
  { to: "/live", label: "Giám sát & Điều khiển", hint: "Camera, digital twin, đèn tín hiệu", icon: <MonitorDot className="h-[18px] w-[18px]" />, perms: ["live:view"] },
  { to: "/analytics", label: "Phân tích & Đánh giá", hint: "Thống kê, trước/sau AI", icon: <BarChart3 className="h-[18px] w-[18px]" />, perms: ["stats:view"] },
  { to: "/assistant", label: "Trợ lý AI & Báo cáo", hint: "LLM Groq: hỏi đáp, báo cáo, nhật ký", icon: <Sparkles className="h-[18px] w-[18px]" />, perms: ["assistant:use"] },
  { to: "/alerts", label: "Cảnh báo & Sự cố", hint: "Ùn tắc, thiết bị, bảo trì", icon: <Siren className="h-[18px] w-[18px]" />, perms: ["alerts:view"] },
  { to: "/config", label: "Nút giao & Cấu hình", hint: "Camera, ngưỡng, an toàn", icon: <Settings2 className="h-[18px] w-[18px]" />, perms: ["config:view"] },
  { to: "/admin", label: "Tài khoản & Nhật ký", hint: "Người dùng, audit trail", icon: <Users className="h-[18px] w-[18px]" />, perms: ["users:manage", "audit:view"] },
];

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="hidden text-right leading-tight md:block">
      <div className="num text-[15px] font-bold tracking-tight text-ink">
        {now.toLocaleTimeString("vi-VN", { hour12: false })}
      </div>
      <div className="text-2xs font-medium text-ink-mute">
        {now.toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" })}
      </div>
    </div>
  );
}

function IntersectionPicker() {
  const { summary, selectedId, select } = useLive();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const cur = summary.find((s) => s.id === selectedId);
  return (
    <div ref={ref} className="relative min-w-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex h-10 min-w-0 max-w-[440px] items-center gap-2.5 rounded-ctl border border-line/80 bg-surface px-3 text-left shadow-sm transition-all hover:border-auto/60 hover:shadow"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-warn/15 text-warn">
          <TrafficCone className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-bold text-ink">{cur?.name ?? "Chọn nút giao"}</div>
          <div className="num truncate text-2xs text-ink-mute">{cur?.code ?? "—"}</div>
        </div>
        {cur && (
          <Badge color={MODE_COLOR[cur.mode]} pulse={cur.mode === "FAILSAFE"}>
            {cur.mode}
          </Badge>
        )}
        <ChevronDown className={clsx("h-4 w-4 shrink-0 text-ink-mute transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ul role="listbox" className="absolute left-0 top-12 z-50 w-[460px] max-w-[90vw] overflow-hidden rounded-panel border border-line bg-surface/98 p-1.5 shadow-pop backdrop-blur-md">
          <div className="px-2.5 py-1 text-2xs font-bold uppercase tracking-wider text-ink-mute">
            Danh sách nút giao trực tuyến
          </div>
          {summary.map((s) => {
            const isSel = s.id === selectedId;
            return (
              <li key={s.id}>
                <button
                  role="option"
                  aria-selected={isSel}
                  onClick={() => {
                    select(s.id);
                    setOpen(false);
                  }}
                  className={clsx(
                    "flex w-full items-center gap-3 rounded-ctl px-2.5 py-2.5 text-left transition-colors",
                    isSel ? "bg-panel text-ink ring-1 ring-line/70" : "hover:bg-panel/70 text-ink-dim hover:text-ink",
                  )}
                >
                  <Dot color={LEVEL_COLOR[s.worst_level]} pulse={s.worst_level === "HIGH"} size={9} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-semibold text-ink">{s.name}</div>
                    <div className="num text-2xs text-ink-mute">
                      {s.code} · camera {s.cameras_online}/{s.cameras_total} · controller {s.controller_online ? "online" : "mất kết nối"}
                    </div>
                  </div>
                  <Badge color={MODE_COLOR[s.mode]}>{MODE_LABEL[s.mode]}</Badge>
                </button>
              </li>
            );
          })}
          {summary.length === 0 && <li className="px-3 py-4 text-xs text-ink-mute">Chưa có nút giao đang hoạt động</li>}
        </ul>
      )}
    </div>
  );
}

function CriticalBanner() {
  const { activeAlerts, openIncidents, summary } = useLive();
  const navigate = useNavigate();
  const critical = activeAlerts.filter((a) => a.level === "CRITICAL" && a.status === "ACTIVE");
  const failsafe = summary.filter((s) => s.mode === "FAILSAFE");
  const criticalIncidents = openIncidents.filter((i) => i.severity === "CRITICAL" && !i.recovered_at);
  if (!critical.length && !failsafe.length && !criticalIncidents.length) return null;
  const head = failsafe[0]
    ? `FAILSAFE tại ${failsafe[0].name}: ${failsafe[0].failsafe_reason ?? ""}`
    : criticalIncidents[0]
      ? `Sự cố thiết bị ${criticalIncidents[0].device_code}: ${criticalIncidents[0].message}`
      : critical[0].title;
  const extra = critical.length + criticalIncidents.length + failsafe.length - 1;
  return (
    <div role="alert" className="no-print flex items-center gap-3 border-b border-stop/60 bg-stop/15 px-4 py-2 text-[13px] font-medium shadow-inner">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-stop/20 text-stop">
        <ShieldAlert className="h-4 w-4 animate-blink" />
      </div>
      <span className="min-w-0 flex-1 truncate font-semibold text-stop-ink">{head}</span>
      {extra > 0 && <span className="num shrink-0 rounded-full bg-stop/20 px-2 py-0.5 text-xs font-bold text-stop-ink">+{extra} cảnh báo khác</span>}
      <button
        onClick={() => navigate("/alerts")}
        className="shrink-0 rounded-ctl border border-stop/60 bg-stop/20 px-3 py-1 text-xs font-semibold text-stop-ink transition-colors hover:bg-stop/30"
      >
        Mở trung tâm cảnh báo
      </button>
    </div>
  );
}

export function AppShell() {
  const { user, logout, can } = useAuth();
  const { status, latencyMs, activeAlerts, openIncidents, muted, setMuted } = useLive();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const headerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty("--header-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const visibleNav = NAV.filter((n) => n.perms.some((p) => can(p)));
  const activeCount = activeAlerts.filter((a) => a.status === "ACTIVE").length;
  const incidentCount = openIncidents.filter((i) => i.status === "OPEN").length;
  const totalAlertBadge = activeCount + incidentCount;

  return (
    <div className="flex h-full min-h-screen bg-carbon">
      {/* ---------------- Sidebar cố định bên trái ---------------- */}
      <aside className="no-print sticky top-0 hidden h-screen w-[240px] shrink-0 flex-col border-r border-line/80 bg-surface shadow-sm lg:flex">
        {/* Brand Header */}
        <div className="flex items-center gap-3 border-b border-line/70 px-4 py-3.5">
          <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-card bg-slate-900 shadow-md ring-1 ring-slate-700">
            {/* 3 traffic light mini diodes */}
            <div className="flex flex-col gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-rose-500 shadow-[0_0_5px_#f43f5e]" />
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 opacity-60" />
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_#34d399]" />
            </div>
            <Radio className="absolute right-1 top-1 h-2.5 w-2.5 text-blue-400/80" />
          </div>
          <div className="min-w-0 leading-tight">
            <div className="flex items-center gap-1.5">
              <span className="text-[15px] font-extrabold tracking-tight text-ink">STCS</span>
              <span className="num rounded bg-auto/15 px-1 py-0.2 text-[10px] font-bold text-auto">AI-TOC</span>
            </div>
            <div className="truncate text-2xs font-medium text-ink-mute">Điều khiển giao thông</div>
          </div>
        </div>

        {/* Menu Navigation */}
        <nav className="flex-1 space-y-1 p-2.5" aria-label="Điều hướng chính">
          {visibleNav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                clsx(
                  "group relative flex items-start gap-3 rounded-ctl px-3 py-2.5 transition-all",
                  isActive
                    ? "bg-auto/10 text-auto font-semibold shadow-sm"
                    : "text-ink-dim hover:bg-panel hover:text-ink font-medium",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r-full bg-auto" />}
                  <span className={clsx("mt-0.5 transition-colors", isActive ? "text-auto" : "text-ink-mute group-hover:text-ink")}>
                    {n.icon}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-1.5 text-[13px]">
                      <span>{n.label}</span>
                      {n.to === "/alerts" && totalAlertBadge > 0 && (
                        <span className="num animate-pulse rounded-full bg-stop px-1.5 py-0.2 text-2xs font-bold text-white shadow-sm shadow-stop/30">
                          {totalAlertBadge}
                        </span>
                      )}
                    </span>
                    <span className="block truncate text-2xs text-ink-mute">{n.hint}</span>
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer Sidebar */}
        <div className="border-t border-line/70 p-3 text-2xs text-ink-mute">
          <div className="flex items-center justify-between font-medium">
            <span className="flex items-center gap-1.5">
              <Dot color={status === "open" ? "#10B981" : status === "connecting" ? "#F59E0B" : "#EF4444"} size={7} pulse={status === "connecting"} />
              <span>{status === "open" ? "Luồng thời gian thực" : status === "connecting" ? "Đang kết nối…" : "Mất luồng"}</span>
            </span>
            <span className="num font-bold text-ink">
              {status === "open" ? `${latencyMs ?? "–"} ms` : "—"}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between text-ink-mute/80">
            <span>STCS v1.0 · Đà Nẵng</span>
            <span className="num">TOC-Node-01</span>
          </div>
        </div>
      </aside>

      {/* ---------------- Main Content Workspace ---------------- */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Header Bar */}
        <header ref={headerRef} className="no-print sticky top-0 z-40 border-b border-line/80 bg-surface/90 backdrop-blur-md transition-colors">
          <div className="flex items-center gap-3 px-3 py-2 md:px-4">
            <IntersectionPicker />

            {/* Mobile navigation buttons */}
            <nav className="flex gap-1 lg:hidden" aria-label="Điều hướng di động">
              {visibleNav.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  title={n.label}
                  className={({ isActive }) => clsx("rounded-ctl p-2 transition-colors", isActive ? "bg-panel text-auto" : "text-ink-mute hover:text-ink")}
                >
                  {n.icon}
                </NavLink>
              ))}
            </nav>

            <div className="flex-1" />

            {/* WebSocket connection status indicator */}
            <div className="hidden items-center gap-1.5 rounded-ctl border border-line/60 bg-panel/40 px-2.5 py-1 text-2xs text-ink-mute xl:flex">
              {status === "open" ? (
                <>
                  <Wifi className="h-3.5 w-3.5 text-go" />
                  <span className="font-medium text-ink">WebSocket: Đã kết nối</span>
                  <span className="num text-ink-mute">({latencyMs ?? "–"}ms)</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3.5 w-3.5 text-stop" />
                  <span className="font-medium text-stop">Đang kết nối lại…</span>
                </>
              )}
            </div>

            {/* Audio Mute Button */}
            <button
              onClick={() => setMuted(!muted)}
              className={clsx(
                "rounded-ctl border border-line/60 p-2 transition-all hover:bg-panel",
                muted ? "text-ink-mute" : "text-warn bg-warn/10 border-warn/30",
              )}
              title={muted ? "Bật âm báo sự cố" : "Tắt âm báo"}
              aria-label={muted ? "Bật âm báo sự cố" : "Tắt âm báo"}
            >
              {muted ? <BellOff className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
            </button>

            {/* Hot Alerts Button */}
            {can("alerts:view") && (
              <button
                onClick={() => navigate("/alerts")}
                className={clsx(
                  "flex h-9 items-center gap-2 rounded-ctl border px-2.5 text-xs font-semibold transition-all shadow-sm",
                  activeCount > 0
                    ? "border-stop/60 bg-stop/15 text-stop-ink hover:bg-stop/20 ring-1 ring-stop/30"
                    : "border-line/70 bg-surface text-ink-dim hover:bg-panel",
                )}
                title="Cảnh báo chưa xác nhận"
              >
                <Siren className={clsx("h-4 w-4", activeCount > 0 && "animate-blink text-stop")} />
                <span className="num font-bold">{activeCount}</span>
                <span className="hidden sm:inline">cảnh báo</span>
              </button>
            )}

            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className="flex h-9 w-9 items-center justify-center rounded-ctl border border-line/70 bg-surface text-ink-dim shadow-sm transition-all hover:bg-panel hover:text-ink active:scale-95"
              title={theme === "dark" ? "Chuyển sang Giao diện Sáng (Ban ngày)" : "Chuyển sang Giao diện Tối (Tác chiến TOC)"}
              aria-label="Đổi giao diện sáng/tối"
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4 text-amber-400 transition-transform hover:rotate-45" />
              ) : (
                <Moon className="h-4 w-4 text-blue-600 transition-transform hover:-rotate-12" />
              )}
            </button>

            {/* Real-time Clock */}
            <Clock />

            {/* User Profile & Logout */}
            <div className="flex items-center gap-2.5 border-l border-line/70 pl-3">
              <div className="hidden text-right leading-tight sm:block">
                <div className="truncate text-[13px] font-bold text-ink">{user?.full_name}</div>
                <div className="text-2xs font-semibold" style={{ color: tone(ROLE_COLOR[user?.role ?? "MANAGER"], 85) }}>
                  {ROLE_LABEL[user?.role ?? "MANAGER"]}
                </div>
              </div>
              <button
                onClick={() => logout().then(() => navigate("/login"))}
                className="flex h-9 w-9 items-center justify-center rounded-ctl border border-line/70 bg-surface text-ink-mute shadow-sm transition-all hover:bg-stop/15 hover:border-stop/40 hover:text-stop active:scale-95"
                title="Đăng xuất"
                aria-label="Đăng xuất"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
          <CriticalBanner />
        </header>

        {/* Main Body */}
        <main className="min-w-0 flex-1 p-3 md:p-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
