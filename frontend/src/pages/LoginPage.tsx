import { KeyRound, Loader2, LockKeyhole, Moon, OctagonAlert, Radio, Sun, User as UserIcon } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { ApiError } from "@/lib/api";
import { ROLE_COLOR } from "@/lib/permissions";

const DEMO = [
  { username: "admin", password: "admin123", role: "ADMIN", title: "Quản trị viên", can: "Toàn quyền: cấu hình nút giao, camera, tài khoản, nhật ký" },
  { username: "operator", password: "operator123", role: "OPERATOR", title: "Người vận hành", can: "Điều khiển đèn, chuyển chế độ, xác nhận cảnh báo, giả lập sự cố" },
  { username: "manager", password: "manager123", role: "MANAGER", title: "Người quản lý", can: "Xem giám sát, thống kê, đánh giá hiệu quả, nhật ký (chỉ đọc)" },
  { username: "viewer", password: "viewer123", role: "VIEWER", title: "Người xem dữ liệu", can: "Chỉ xem thống kê, cảnh báo và hỏi trợ lý AI (không xem video)" },
];

/** Cột đèn tín hiệu chạy chu kỳ thật: Xanh 6s → Vàng 3s → Đỏ 6s */
function SignalHead() {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setT((x) => (x + 1) % 15), 1000);
    return () => window.clearInterval(id);
  }, []);
  const phase = t < 6 ? "G" : t < 9 ? "Y" : "R";
  const left = phase === "G" ? 6 - t : phase === "Y" ? 9 - t : 15 - t;
  const lamp = (on: boolean, color: string) => (
    <div
      className="h-14 w-14 rounded-full border border-black/40 transition-all duration-300"
      style={{
        background: on ? color : "#0f1623",
        boxShadow: on ? `0 0 32px ${color}cc, inset 0 0 10px #ffffff66` : "inset 0 2px 6px #000",
      }}
    />
  );
  return (
    <div className="flex items-end gap-5">
      <div className="flex flex-col gap-3 rounded-[16px] border border-slate-700/80 bg-slate-950 p-3.5 shadow-2xl ring-1 ring-slate-800">
        {lamp(phase === "R", "#EF4444")}
        {lamp(phase === "Y", "#F59E0B")}
        {lamp(phase === "G", "#10B981")}
      </div>
      <div className="pb-1">
        <div
          className="num text-6xl font-extrabold leading-none tracking-tight sm:text-7xl"
          style={{
            color: phase === "G" ? "rgb(var(--c-go))" : phase === "Y" ? "rgb(var(--c-warn))" : "rgb(var(--c-stop))",
            textShadow: `0 0 20px ${phase === "G" ? "#10b98155" : phase === "Y" ? "#f59e0b55" : "#ef444455"}`,
          }}
        >
          {String(left).padStart(2, "0")}
        </div>
        <div className="mt-2 text-xs font-semibold uppercase tracking-wider text-ink-mute">
          {phase === "G" ? "Pha xanh tiếp tục" : phase === "Y" ? "Vàng chuyển tiếp" : "Toàn đỏ → Pha kế tiếp"}
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  const { login, user, ready } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const loc = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (ready && user) return <Navigate to={(loc.state as { from?: string } | null)?.from ?? "/"} replace />;

  const doLogin = async (u: string, p: string, key: string) => {
    setError(null);
    setBusy(key);
    try {
      await login(u, p);
      navigate((loc.state as { from?: string } | null)?.from ?? "/", { replace: true });
    } catch (e) {
      const err = e as ApiError;
      setError({ status: err.status ?? 0, message: err.message });
    } finally {
      setBusy(null);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError({ status: 400, message: "Vui lòng nhập tên đăng nhập và mật khẩu." });
      return;
    }
    doLogin(username.trim(), password, "form");
  };

  const errTitle =
    error?.status === 403 ? "Tài khoản bị khoá" : error?.status === 423 ? "Tạm khoá đăng nhập" : error?.status === 0 ? "Mất kết nối máy chủ" : "Đăng nhập không thành công";

  return (
    <div className="grid-bg relative grid min-h-screen bg-carbon lg:grid-cols-[1.1fr_1fr]">
      {/* Theme Switcher Top-Right */}
      <div className="absolute right-4 top-4 z-50">
        <button
          onClick={toggleTheme}
          className="flex h-9 w-9 items-center justify-center rounded-ctl border border-line/80 bg-surface/80 p-2 text-ink-mute shadow-sm backdrop-blur transition-all hover:bg-panel hover:text-ink active:scale-95"
          title={theme === "dark" ? "Chuyển sang giao diện Sáng" : "Chuyển sang giao diện Tối"}
        >
          {theme === "dark" ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-blue-600" />}
        </button>
      </div>

      {/* Hero Showcase bên trái */}
      <section className="hidden flex-col justify-between border-r border-line/80 bg-surface/40 p-12 backdrop-blur-sm lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-ctl bg-slate-900 shadow ring-1 ring-slate-700">
            <Radio className="h-4 w-4 text-blue-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-extrabold tracking-tight text-ink">STCS</span>
              <span className="rounded bg-auto/15 px-1.5 py-0.2 text-[10px] font-bold text-auto">ĐÀ NẴNG</span>
            </div>
            <div className="text-2xs font-medium text-ink-mute">Trung tâm Giám sát & Điều khiển Giao thông</div>
          </div>
        </div>

        <div className="max-w-xl">
          <SignalHead />
          <h1 className="mt-10 text-[2.8rem] font-extrabold leading-[1.15] tracking-tight text-ink">
            Mỗi giây đèn xanh
            <br />
            <span className="bg-gradient-to-r from-blue-500 to-emerald-500 bg-clip-text text-transparent">
              tính từ hàng đợi thật.
            </span>
          </h1>
          <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink-dim">
            Camera thị giác máy tính nhận diện và đếm phương tiện ở 4 hướng tiếp cận, thuật toán Webster thích ứng tự động tối ưu chu kỳ đèn,
            đồng bộ bộ khoá an toàn bảo đảm tuyệt đối không xung đột pha.
          </p>
        </div>

        <dl className="grid max-w-2xl grid-cols-3 gap-8 border-t border-line/60 pt-6 text-sm">
          <div>
            <dt className="text-2xs font-bold uppercase tracking-wider text-ink-mute">Trình tự chuyển pha</dt>
            <dd className="num mt-1 font-semibold text-ink">Xanh → Vàng 3s → Đỏ 2s</dd>
          </div>
          <div>
            <dt className="text-2xs font-bold uppercase tracking-wider text-ink-mute">An toàn tự động</dt>
            <dd className="mt-1 font-semibold text-ink">FAILSAFE tức thì khi lỗi</dd>
          </div>
          <div>
            <dt className="text-2xs font-bold uppercase tracking-wider text-ink-mute">Phân loại AI Edge</dt>
            <dd className="mt-1 font-semibold text-ink">Ô tô · Xe máy · Buýt · Tải</dd>
          </div>
        </dl>
      </section>

      {/* Form đăng nhập bên phải */}
      <section className="flex items-center justify-center p-6 md:p-10">
        <div className="w-full max-w-[420px] rounded-card border border-line/80 bg-surface/90 p-8 shadow-pop backdrop-blur-md">
          <div className="mb-6">
            <h2 className="text-2xl font-extrabold tracking-tight text-ink">Đăng nhập hệ thống</h2>
            <p className="mt-1 text-xs font-medium text-ink-mute">Truy cập trung tâm tác chiến điều hành giao thông STCS.</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold text-ink-dim">Tên đăng nhập</span>
              <div className="relative">
                <UserIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-mute" />
                <input
                  autoFocus
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="h-11 w-full rounded-ctl border border-line/80 bg-carbon pl-9 pr-3 text-sm font-medium text-ink shadow-sm transition-all placeholder:text-ink-mute focus:border-auto focus:bg-surface focus:outline-none focus:ring-2 focus:ring-auto/20"
                  placeholder="vd: operator"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold text-ink-dim">Mật khẩu</span>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-mute" />
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11 w-full rounded-ctl border border-line/80 bg-carbon pl-9 pr-3 text-sm font-medium text-ink shadow-sm transition-all placeholder:text-ink-mute focus:border-auto focus:bg-surface focus:outline-none focus:ring-2 focus:ring-auto/20"
                />
              </div>
            </label>

            {error && (
              <div role="alert" className="flex gap-2.5 rounded-ctl border border-stop/60 bg-stop/15 p-3 shadow-inner">
                {error.status === 403 || error.status === 423 ? (
                  <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-stop" />
                ) : (
                  <OctagonAlert className="mt-0.5 h-4 w-4 shrink-0 text-stop" />
                )}
                <div>
                  <p className="text-sm font-bold text-stop-ink">{errTitle}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-stop-ink/90">{error.message}</p>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={!!busy}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-ctl bg-auto text-sm font-bold text-white shadow-md shadow-auto/25 transition-all hover:brightness-110 active:scale-[0.99] disabled:opacity-60"
            >
              {busy === "form" && <Loader2 className="h-4 w-4 animate-spin" />}
              Đăng nhập phiên tác chiến
            </button>
          </form>

          {/* Tài khoản mẫu tiện dụng */}
          <div className="mt-8 border-t border-line/60 pt-6">
            <p className="text-2xs font-bold uppercase tracking-wider text-ink-mute">Đăng nhập nhanh tài khoản mẫu</p>
            <div className="mt-2.5 space-y-2">
              {DEMO.map((d) => (
                <button
                  key={d.username}
                  disabled={!!busy}
                  onClick={() => doLogin(d.username, d.password, d.username)}
                  className="group flex w-full items-center gap-3 rounded-ctl border border-line/70 bg-panel/30 p-2.5 text-left transition-all hover:border-auto/60 hover:bg-panel hover:shadow-sm disabled:opacity-60"
                >
                  <span className="h-8 w-1 shrink-0 rounded-full" style={{ background: ROLE_COLOR[d.role] }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-xs font-bold text-ink">
                      {d.title}
                      <span className="num font-normal text-ink-mute">
                        ({d.username} / {d.password})
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-2xs text-ink-mute">{d.can}</div>
                  </div>
                  {busy === d.username && <Loader2 className="h-4 w-4 animate-spin text-auto" />}
                </button>
              ))}
            </div>
            <p className="mt-3 text-2xs text-ink-mute">
              Bảo mật: Sai mật khẩu 5 lần liên tiếp sẽ tạm khóa tài khoản 5 phút để bảo vệ hệ thống.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
