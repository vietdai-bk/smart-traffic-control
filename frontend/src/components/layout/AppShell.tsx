import clsx from "clsx";
import {
  BarChart3,
  Bell,
  BellOff,
  ChevronDown,
  LogOut,
  Menu,
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
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";
import { useTheme } from "@/context/ThemeContext";
import { LEVEL_COLOR, MODE_COLOR, MODE_LABEL, tone } from "@/lib/format";
import { ROLE_COLOR, ROLE_LABEL, type Perm } from "@/lib/permissions";
import { Badge, Dot } from "../ui/primitives";

interface NavItem {
  to: string;
  label: string;
  short: string;
  hint: string;
  icon: ReactNode;
  perms: Perm[];
}

const NAV: NavItem[] = [
  { to: "/live", short: "Giám sát", label: "Giám sát & Điều khiển", hint: "Camera, digital twin, đèn tín hiệu", icon: <MonitorDot className="h-[18px] w-[18px]" />, perms: ["live:view"] },
  { to: "/analytics", short: "Phân tích", label: "Phân tích & Đánh giá", hint: "Thống kê, trước/sau AI", icon: <BarChart3 className="h-[18px] w-[18px]" />, perms: ["stats:view"] },
  { to: "/assistant", short: "Trợ lý AI", label: "Trợ lý AI & Báo cáo", hint: "LLM Groq: hỏi đáp, báo cáo, nhật ký", icon: <Sparkles className="h-[18px] w-[18px]" />, perms: ["assistant:use"] },
  { to: "/alerts", short: "Cảnh báo", label: "Cảnh báo & Sự cố", hint: "Ùn tắc, thiết bị, bảo trì", icon: <Siren className="h-[18px] w-[18px]" />, perms: ["alerts:view"] },
  { to: "/config", short: "Cấu hình", label: "Nút giao & Cấu hình", hint: "Camera, ngưỡng, an toàn", icon: <Settings2 className="h-[18px] w-[18px]" />, perms: ["config:view"] },
  { to: "/admin", short: "Tài khoản", label: "Tài khoản & Nhật ký", hint: "Người dùng, audit trail", icon: <Users className="h-[18px] w-[18px]" />, perms: ["users:manage", "audit:view"] },
];

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="hidden shrink-0 text-right leading-tight xl:block">
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
    <div ref={ref} className="relative min-w-0 flex-1 md:flex-none">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex h-10 w-full min-w-0 md:max-w-[440px] items-center gap-2.5 rounded-ctl border border-line/80 bg-surface px-3 text-left transition-colors hover:border-auto/60"
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
        <ul role="listbox" className="absolute left-0 top-12 z-50 w-[460px] max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-panel border border-line bg-surface p-1.5 shadow-pop">
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
    <div role="alert" className="no-print flex items-center gap-2 border-b border-stop/60 bg-stop/15 px-3 py-1.5 sm:gap-3 sm:px-4 sm:py-2 text-[13px] font-medium shadow-inner">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-stop/20 text-stop">
        <ShieldAlert className="h-4 w-4 animate-blink" />
      </div>
      <span className="min-w-0 flex-1 truncate font-semibold text-stop-ink">{head}</span>
      {extra > 0 && <span className="num hidden shrink-0 rounded-full bg-stop/20 px-2 py-0.5 text-xs font-bold text-stop-ink sm:inline">+{extra} cảnh báo khác</span>}
      <button
        onClick={() => navigate("/alerts")}
        className="shrink-0 rounded-ctl border border-stop/60 bg-stop/20 px-3 py-1 text-xs font-semibold text-stop-ink transition-colors hover:bg-stop/30"
      >
        <span className="hidden sm:inline">Mở trung tâm cảnh báo</span>
        <span className="sm:hidden">Xem{extra > 0 ? ` (+${extra})` : ""}</span>
      </button>
    </div>
  );
}

function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className={clsx("flex items-center gap-3", compact && "justify-center")}>
      <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-card bg-slate-900 shadow-md ring-1 ring-slate-700">
        <div className="flex flex-col gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-rose-500 shadow-[0_0_5px_#f43f5e]" />
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400 opacity-60" />
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_#34d399]" />
        </div>
        <Radio className="absolute right-1 top-1 h-2.5 w-2.5 text-blue-400/80" />
      </div>
      {!compact && (
        <div className="min-w-0 leading-tight">
          <div className="flex items-center gap-1.5">
            <span className="text-[15px] font-extrabold tracking-tight text-ink">STCS</span>
            <span className="num rounded bg-auto/15 px-1 py-0.2 text-[10px] font-bold text-auto">AI-TOC</span>
          </div>
          <div className="truncate text-2xs font-medium text-ink-mute">Điều khiển giao thông</div>
        </div>
      )}
    </div>
  );
}

function AlertCount({ n }: { n: number }) {
  if (n <= 0) return null;
  return (
    <span className="num animate-pulse rounded-full bg-stop px-1.5 py-0.2 text-2xs font-bold leading-4 text-white shadow-sm shadow-stop/30">
      {n > 99 ? "99+" : n}
    </span>
  );
}

/** Ngăn "Thêm" trên điện thoại: mục điều hướng còn lại + tiện ích tài khoản. */
function MoreSheet({ open, onClose, items, alertBadge }: { open: boolean; onClose: () => void; items: NavItem[]; alertBadge: number }) {
  const { user, logout } = useAuth();
  const { status, latencyMs, muted, setMuted } = useLive();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  const row = "flex min-h-[48px] w-full items-center gap-3 rounded-ctl px-3 text-left text-sm font-medium text-ink transition-colors hover:bg-panel active:bg-panel";
  return (
    <div className="fixed inset-0 z-[90] md:hidden" role="dialog" aria-modal="true" aria-label="Menu">
      <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={onClose} />
      <div className="absolute inset-x-0 bottom-0 max-h-[85vh] animate-slideUp overflow-y-auto rounded-t-[20px] border-t border-line/80 bg-surface p-3 pb-[calc(12px+env(safe-area-inset-bottom))] shadow-pop">
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />
        <div className="flex items-center gap-3 rounded-ctl bg-panel/40 p-3">
          <Brand compact />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-bold text-ink">{user?.full_name}</div>
            <div className="text-2xs font-semibold" style={{ color: tone(ROLE_COLOR[user?.role ?? "MANAGER"], 85) }}>
              {ROLE_LABEL[user?.role ?? "MANAGER"]}
            </div>
          </div>
          <span className="flex items-center gap-1.5 text-2xs text-ink-mute">
            <Dot color={status === "open" ? "#10B981" : "#EF4444"} size={7} />
            <span className="num">{status === "open" ? `${latencyMs ?? "–"} ms` : "mất luồng"}</span>
          </span>
        </div>
        {items.length > 0 && (
          <nav className="mt-2 space-y-0.5" aria-label="Mục khác">
            {items.map((n) => (
              <NavLink key={n.to} to={n.to} onClick={onClose}
                className={({ isActive }) => clsx(row, isActive && "bg-auto/10 text-auto")}>
                <span className="text-ink-mute">{n.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block">{n.label}</span>
                </span>
                {n.to === "/alerts" && <AlertCount n={alertBadge} />}
              </NavLink>
            ))}
          </nav>
        )}
        <div className="mt-2 space-y-0.5 border-t border-line/60 pt-2">
          <button className={row} onClick={toggleTheme}>
            {theme === "dark" ? <Sun className="h-[18px] w-[18px] text-amber-400" /> : <Moon className="h-[18px] w-[18px] text-blue-600" />}
            {theme === "dark" ? "Giao diện sáng" : "Giao diện tối"}
          </button>
          <button className={row} onClick={() => setMuted(!muted)}>
            {muted ? <BellOff className="h-[18px] w-[18px] text-ink-mute" /> : <Bell className="h-[18px] w-[18px] text-warn" />}
            {muted ? "Bật âm báo sự cố" : "Tắt âm báo sự cố"}
          </button>
          <button className={clsx(row, "text-stop-ink")} onClick={() => { onClose(); logout().then(() => navigate("/login")); }}>
            <LogOut className="h-[18px] w-[18px]" />
            Đăng xuất
          </button>
        </div>
      </div>
    </div>
  );
}

export function AppShell() {
  const { user, logout, can } = useAuth();
  const { status, latencyMs, activeAlerts, openIncidents, muted, setMuted } = useLive();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const headerRef = useRef<HTMLElement>(null);
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty("--header-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => setMoreOpen(false), [location.pathname]);

  const visibleNav = NAV.filter((n) => n.perms.some((p) => can(p)));
  const activeCount = activeAlerts.filter((a) => a.status === "ACTIVE").length;
  const incidentCount = openIncidents.filter((i) => i.status === "OPEN").length;
  const totalAlertBadge = activeCount + incidentCount;
  // Điện thoại: tối đa 4 mục ở thanh dưới, phần còn lại vào ngăn "Thêm"
  const tabNav = visibleNav.length <= 5 ? visibleNav.slice(0, visibleNav.length === 5 ? 4 : visibleNav.length) : visibleNav.slice(0, 4);
  const moreNav = visibleNav.filter((n) => !tabNav.includes(n));
  const moreActive = moreNav.some((n) => location.pathname.startsWith(n.to));

  return (
    <div className="min-h-screen bg-carbon">
      {/* ---------- Sidebar: icon rail trên máy tính bảng, đầy đủ trên desktop ---------- */}
      {/* Cố định theo cửa sổ (fixed) — luôn hiển thị khi cuộn nội dung */}
      <aside className="no-print fixed inset-y-0 left-0 z-40 hidden h-dvh w-[72px] flex-col border-r border-line/80 bg-surface shadow-sm md:flex lg:w-[240px]">
        <div className="border-b border-line/70 px-4 py-3.5 max-lg:px-0">
          <div className="lg:hidden"><Brand compact /></div>
          <div className="hidden lg:block"><Brand /></div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-2.5" aria-label="Điều hướng chính">
          {visibleNav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              title={n.label}
              className={({ isActive }) =>
                clsx(
                  "group relative flex items-center gap-3 rounded-ctl px-3 py-2.5 transition-all max-lg:flex-col max-lg:items-center max-lg:gap-1 max-lg:px-1",
                  isActive ? "bg-panel font-semibold text-auto-ink" : "font-medium text-ink-dim hover:bg-panel hover:text-ink",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute bottom-1.5 left-0 top-1.5 w-1 rounded-r-full bg-auto" />}
                  <span className={clsx("relative transition-colors", isActive ? "text-auto" : "text-ink-mute group-hover:text-ink")}>
                    {n.icon}
                    {n.to === "/alerts" && totalAlertBadge > 0 && (
                      <span className="absolute -right-2 -top-2 lg:hidden"><AlertCount n={totalAlertBadge} /></span>
                    )}
                  </span>
                  <span className="text-center text-[10px] leading-tight lg:hidden">{n.short}</span>
                  <span className="hidden min-w-0 flex-1 lg:block">
                    <span className="flex items-center justify-between gap-1.5 text-[13px]">
                      <span>{n.label}</span>
                      {n.to === "/alerts" && <AlertCount n={totalAlertBadge} />}
                    </span>
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line/70 p-3 text-2xs text-ink-mute max-lg:px-1 max-lg:text-center">
          <div className="flex items-center justify-between font-medium max-lg:flex-col max-lg:gap-1">
            <span className="flex items-center gap-1.5">
              <Dot color={status === "open" ? "#10B981" : status === "connecting" ? "#F59E0B" : "#EF4444"} size={7} pulse={status === "connecting"} />
              <span className="hidden lg:inline">{status === "open" ? "Luồng thời gian thực" : status === "connecting" ? "Đang kết nối…" : "Mất luồng"}</span>
            </span>
            <span className="num font-bold text-ink">{status === "open" ? `${latencyMs ?? "–"} ms` : "—"}</span>
          </div>
          <div className="mt-1 hidden items-center justify-between text-ink-mute/80 lg:flex">
            <span>STCS v1.0 · Đà Nẵng</span>
            <span className="num">TOC-Node-01</span>
          </div>
        </div>
      </aside>

      {/* ---------- Vùng làm việc ---------- */}
      <div className="flex min-h-screen min-w-0 flex-col md:pl-[72px] lg:pl-[240px]">
        <header ref={headerRef} className="no-print sticky top-0 z-40 border-b border-line/80 bg-surface pt-[env(safe-area-inset-top)] transition-colors">
          <div className="flex items-center gap-2 px-3 py-2 md:gap-3 md:px-4">
            <div className="md:hidden"><Brand compact /></div>
            <IntersectionPicker />

            <div className="hidden flex-1 md:block" />

            <div className="hidden shrink-0 items-center gap-1.5 whitespace-nowrap rounded-ctl border border-line/60 bg-panel/40 px-2.5 py-1 text-2xs text-ink-mute 2xl:flex">
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

            <button
              onClick={() => setMuted(!muted)}
              className={clsx("hidden rounded-ctl border border-line/60 p-2 transition-all hover:bg-panel md:block", muted ? "text-ink-mute" : "border-warn/30 bg-warn/10 text-warn")}
              title={muted ? "Bật âm báo sự cố" : "Tắt âm báo"}
              aria-label={muted ? "Bật âm báo sự cố" : "Tắt âm báo"}
            >
              {muted ? <BellOff className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
            </button>

            {can("alerts:view") && (
              <button
                onClick={() => navigate("/alerts")}
                className={clsx(
                  "flex h-10 shrink-0 items-center gap-1.5 rounded-ctl border px-2.5 text-xs font-semibold shadow-sm transition-all md:h-9 md:gap-2",
                  activeCount > 0 ? "border-stop/60 bg-stop/15 text-stop-ink ring-1 ring-stop/30 hover:bg-stop/20" : "border-line/70 bg-surface text-ink-dim hover:bg-panel",
                )}
                title="Cảnh báo chưa xác nhận"
                aria-label={`${activeCount} cảnh báo chưa xác nhận`}
              >
                <Siren className={clsx("h-4 w-4", activeCount > 0 && "animate-blink text-stop")} />
                <span className="num font-bold">{activeCount}</span>
                <span className="hidden sm:inline">cảnh báo</span>
              </button>
            )}

            <button
              onClick={toggleTheme}
              className="hidden h-9 w-9 items-center justify-center rounded-ctl border border-line/70 bg-surface text-ink-dim shadow-sm transition-all hover:bg-panel hover:text-ink active:scale-95 md:flex"
              title={theme === "dark" ? "Chuyển sang Giao diện Sáng (Ban ngày)" : "Chuyển sang Giao diện Tối (Tác chiến TOC)"}
              aria-label="Đổi giao diện sáng/tối"
            >
              {theme === "dark" ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-blue-600" />}
            </button>

            <Clock />

            <div className="hidden items-center gap-2.5 border-l border-line/70 pl-3 md:flex">
              <div className="hidden text-right leading-tight lg:block">
                <div className="max-w-[160px] truncate text-[13px] font-bold text-ink">{user?.full_name}</div>
                <div className="text-2xs font-semibold" style={{ color: tone(ROLE_COLOR[user?.role ?? "MANAGER"], 85) }}>
                  {ROLE_LABEL[user?.role ?? "MANAGER"]}
                </div>
              </div>
              <button
                onClick={() => logout().then(() => navigate("/login"))}
                className="flex h-9 w-9 items-center justify-center rounded-ctl border border-line/70 bg-surface text-ink-mute shadow-sm transition-all hover:border-stop/40 hover:bg-stop/15 hover:text-stop active:scale-95"
                title="Đăng xuất"
                aria-label="Đăng xuất"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
          <CriticalBanner />
        </header>

        <main className="min-w-0 flex-1 p-2.5 pb-[calc(76px+env(safe-area-inset-bottom))] sm:p-3 md:p-4 md:pb-4">
          <Outlet />
        </main>
      </div>

      {/* ---------- Thanh điều hướng dưới (điện thoại) ---------- */}
      <nav
        className="no-print fixed inset-x-0 bottom-0 z-50 grid border-t border-line/80 bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
        style={{ gridTemplateColumns: `repeat(${tabNav.length + 1}, minmax(0, 1fr))` }}
        aria-label="Điều hướng di động"
      >
        {tabNav.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              clsx("relative flex min-h-[58px] flex-col items-center justify-center gap-1 text-[10.5px] font-semibold transition-colors", isActive ? "text-auto" : "text-ink-mute active:text-ink")
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute inset-x-5 top-0 h-[3px] rounded-b-full bg-auto" />}
                <span className="relative">
                  {n.icon}
                  {n.to === "/alerts" && totalAlertBadge > 0 && <span className="absolute -right-3 -top-2"><AlertCount n={totalAlertBadge} /></span>}
                </span>
                <span className="max-w-full truncate px-1">{n.short}</span>
              </>
            )}
          </NavLink>
        ))}
        <button
          onClick={() => setMoreOpen(true)}
          className={clsx("relative flex min-h-[58px] flex-col items-center justify-center gap-1 text-[10.5px] font-semibold", moreActive ? "text-auto" : "text-ink-mute")}
          aria-label="Mở menu"
        >
          {moreActive && <span className="absolute inset-x-5 top-0 h-[3px] rounded-b-full bg-auto" />}
          <span className="relative">
            <Menu className="h-[18px] w-[18px]" />
            {moreNav.some((n) => n.to === "/alerts") && totalAlertBadge > 0 && <span className="absolute -right-2 -top-1.5 h-2 w-2 rounded-full bg-stop" />}
          </span>
          Thêm
        </button>
      </nav>
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} items={moreNav} alertBadge={totalAlertBadge} />
    </div>
  );
}
