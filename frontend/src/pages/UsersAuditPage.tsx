import clsx from "clsx";
import { ChevronRight, KeyRound, Lock, Pencil, Plus, ScrollText, Search, ShieldCheck, Trash2, Unlock, UserCog, Users } from "lucide-react";
import { Fragment, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Field, Input, Select, Toggle } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { Badge, Button, Empty, Pager, Panel, Spinner, Tabs } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, qs } from "@/lib/api";
import { fmtDateTime, relTime, tone } from "@/lib/format";
import { ROLE_COLOR, ROLE_LABEL } from "@/lib/permissions";
import type { AuditLog, Page, Role, User } from "@/lib/types";

const PERM_LABEL: Record<string, string> = {
  "live:view": "Xem giám sát trực tiếp",
  "stats:view": "Xem thống kê & đánh giá",
  "stats:export": "Xuất báo cáo",
  "alerts:view": "Xem cảnh báo & sự cố",
  "alerts:ack": "Xác nhận cảnh báo, đóng sự cố",
  "signal:control": "Điều khiển đèn tín hiệu",
  "signal:mode": "Chuyển chế độ, khôi phục FAILSAFE",
  "sim:control": "Công cụ giả lập tình huống",
  "config:view": "Xem cấu hình",
  "config:manage": "Quản lý nút giao & camera",
  "users:manage": "Quản lý tài khoản",
  "audit:view": "Tra cứu nhật ký hệ thống",
  "llm:supervise": "Điều hành LLM Supervisor (bật/duyệt)",
  "assistant:use": "Dùng trợ lý vận hành AI",
  "report:ai": "Sinh báo cáo tự động bằng AI",
};

const CAT_COLOR: Record<string, string> = {
  AUTH: "#94A3B8",
  SIGNAL_CONTROL: "#A855F7",
  ALERT: "#F59E0B",
  DEVICE: "#EF4444",
  CONFIG: "#3B82F6",
  USER: "#0891B2",
  SYSTEM: "#64748B",
};
const CAT_LABEL: Record<string, string> = {
  AUTH: "Đăng nhập",
  SIGNAL_CONTROL: "Điều khiển đèn",
  ALERT: "Cảnh báo",
  DEVICE: "Thiết bị",
  CONFIG: "Cấu hình",
  USER: "Tài khoản",
  SYSTEM: "Hệ thống",
};

type UserForm = { id: number | null; username: string; full_name: string; email: string; phone: string; role: Role; password: string; is_active: boolean };
const EMPTY: UserForm = { id: null, username: "", full_name: "", email: "", phone: "", role: "OPERATOR", password: "", is_active: true };

function UsersTab() {
  const { user: me } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState<User[] | null>(null);
  const [roles, setRoles] = useState<{ role: Role; label: string; permissions: string[] }[]>([]);
  const [q, setQ] = useState("");
  const [form, setForm] = useState<UserForm | null>(null);
  const [del, setDel] = useState<User | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<User[]>(`/users${qs({ q: q || undefined })}`).then(setUsers).catch((e) => toast("error", "Không tải được tài khoản", (e as Error).message));
  }, [q, toast]);
  useEffect(load, [load]);
  useEffect(() => {
    api.get<typeof roles>("/users/roles").then(setRoles).catch(() => undefined);
  }, []);

  const save = async () => {
    if (!form) return;
    setBusy(true);
    try {
      if (form.id) {
        const body: Record<string, unknown> = { full_name: form.full_name, email: form.email || null, phone: form.phone || null, role: form.role, is_active: form.is_active };
        if (form.password) body.password = form.password;
        await api.patch(`/users/${form.id}`, body);
        toast("success", "Đã cập nhật tài khoản", form.username);
      } else {
        await api.post("/users", { ...form, email: form.email || null, phone: form.phone || null });
        toast("success", "Đã tạo tài khoản", form.username);
      }
      setForm(null);
      load();
    } catch (e) {
      toast("error", "Không lưu được", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleLock = async (u: User) => {
    try {
      await api.patch(`/users/${u.id}`, { is_active: !u.is_active });
      toast("success", u.is_active ? "Đã khoá tài khoản" : "Đã mở khoá tài khoản", u.username);
      load();
    } catch (e) {
      toast("error", "Thao tác thất bại", (e as Error).message);
    }
  };

  const remove = async () => {
    if (!del) return;
    try {
      await api.del(`/users/${del.id}`);
      toast("success", "Đã xoá tài khoản", del.username);
      setDel(null);
      load();
    } catch (e) {
      toast("error", "Không xoá được", (e as Error).message);
    }
  };

  return (
    <div className="grid gap-3 2xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel
        title="Tài khoản người dùng"
        icon={<Users className="h-4 w-4" />}
        bodyClassName="p-0"
        actions={
          <div className="flex items-center gap-1.5">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-mute" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm tên, email…" className="h-7 w-48 pl-7 text-xs" />
            </div>
            <Button size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setForm({ ...EMPTY })}>
              Tạo tài khoản
            </Button>
          </div>
        }
      >
        {!users ? (
          <Spinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-ink-mute">
                  {["Người dùng", "Vai trò", "Liên hệ", "Trạng thái", "Đăng nhập gần nhất", ""].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const tempLocked = u.locked_until && new Date(u.locked_until) > new Date();
                  return (
                    <tr key={u.id} className="border-b border-line/40 hover:bg-panel/40">
                      <td className="px-3 py-2">
                        <div className="font-medium">{u.full_name}{u.id === me?.id && <span className="ml-1.5 text-2xs text-ink-mute">(bạn)</span>}</div>
                        <div className="num text-2xs text-ink-mute">{u.username}</div>
                      </td>
                      <td className="px-3 py-2">
                        <Badge color={ROLE_COLOR[u.role]}>{ROLE_LABEL[u.role]}</Badge>
                      </td>
                      <td className="px-3 py-2 text-ink-dim">
                        <div className="truncate">{u.email ?? "—"}</div>
                        <div className="num text-2xs text-ink-mute">{u.phone ?? ""}</div>
                      </td>
                      <td className="px-3 py-2">
                        {!u.is_active ? (
                          <Badge color="#EF4444"><Lock className="h-3 w-3" /> Đã khoá</Badge>
                        ) : tempLocked ? (
                          <Badge color="#F59E0B">Khoá tạm đến {fmtDateTime(u.locked_until).slice(6)}</Badge>
                        ) : (
                          <Badge color="#10B981">Hoạt động</Badge>
                        )}
                        {u.failed_attempts > 0 && <div className="num mt-0.5 text-2xs text-warn-ink">sai mật khẩu {u.failed_attempts} lần</div>}
                      </td>
                      <td className="px-3 py-2 text-ink-dim">
                        {relTime(u.last_login_at)}
                        <div className="num text-2xs text-ink-mute">{fmtDateTime(u.last_login_at)}</div>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-right">
                        <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setForm({ id: u.id, username: u.username, full_name: u.full_name, email: u.email ?? "", phone: u.phone ?? "", role: u.role, password: "", is_active: u.is_active })}>
                          Sửa
                        </Button>
                        {u.id !== me?.id && (
                          <>
                            <Button size="sm" variant="ghost" icon={u.is_active ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />} onClick={() => toggleLock(u)}>
                              {u.is_active ? "Khoá" : "Mở khoá"}
                            </Button>
                            <Button size="sm" variant="ghost" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDel(u)} aria-label={`Xoá ${u.username}`} />
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {users.length === 0 && <Empty title="Không tìm thấy tài khoản" />}
          </div>
        )}
      </Panel>

      <Panel title="Ma trận phân quyền (RBAC)" icon={<ShieldCheck className="h-4 w-4" />} bodyClassName="p-0">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line text-2xs text-ink-mute">
              <th className="px-3 py-2 text-left font-medium">Quyền</th>
              {roles.map((r) => (
                <th key={r.role} className="px-2 py-2 font-medium" style={{ color: tone(ROLE_COLOR[r.role], 75) }}>
                  {r.role}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.keys(PERM_LABEL).map((p) => (
              <tr key={p} className="border-b border-line/40">
                <td className="px-3 py-1.5 text-ink-dim">{PERM_LABEL[p]}</td>
                {roles.map((r) => (
                  <td key={r.role} className="px-2 py-1.5 text-center">
                    {r.permissions.includes(p) ? <span className="text-go" aria-label="có">✓</span> : <span className="text-ink-mute" aria-label="không">–</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Modal
        open={form != null}
        onClose={() => setForm(null)}
        title={form?.id ? `Sửa tài khoản ${form.username}` : "Tạo tài khoản"}
        icon={<UserCog className="h-4 w-4 text-auto" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setForm(null)}>Huỷ</Button>
            <Button variant="primary" loading={busy} onClick={save} disabled={!form?.full_name || (!form?.id && (!form?.username || (form?.password.length ?? 0) < 6))}>
              {form?.id ? "Lưu thay đổi" : "Tạo tài khoản"}
            </Button>
          </>
        }
      >
        {form && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Tên đăng nhập" hint={form.id ? "Không thể đổi tên đăng nhập" : "Chữ, số, . _ -"}>
              <Input value={form.username} disabled={!!form.id} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </Field>
            <Field label="Họ và tên"><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
            <Field label="Email"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Số điện thoại"><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <Field label="Vai trò">
              <Select value={form.role} disabled={form.id === me?.id} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {(["ADMIN", "OPERATOR", "MANAGER", "VIEWER"] as Role[]).map((r) => (
                  <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                ))}
              </Select>
            </Field>
            <Field label={form.id ? "Đặt lại mật khẩu" : "Mật khẩu"} hint={form.id ? "Để trống nếu không đổi" : "Tối thiểu 6 ký tự"}>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-mute" />
                <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="pl-8" autoComplete="new-password" />
              </div>
            </Field>
            <div className="sm:col-span-2">
              <Toggle checked={form.is_active} disabled={form.id === me?.id} onChange={(v) => setForm({ ...form, is_active: v })} label="Tài khoản được phép đăng nhập" />
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={del != null}
        onClose={() => setDel(null)}
        tone="danger"
        title="Xoá tài khoản"
        icon={<Trash2 className="h-4 w-4 text-stop" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDel(null)}>Huỷ</Button>
            <Button variant="danger" onClick={remove}>Xoá tài khoản</Button>
          </>
        }
      >
        <p className="text-sm text-ink-dim">
          Xoá tài khoản <b className="text-ink">{del?.full_name}</b> (<span className="num">{del?.username}</span>)? Nhật ký hoạt động của tài khoản vẫn được giữ lại. Nếu chỉ tạm ngừng, hãy dùng chức năng Khoá.
        </p>
      </Modal>
    </div>
  );
}

function AuditTab() {
  const [q, setQ] = useState("");
  const [cats, setCats] = useState<string[]>([]);
  const [username, setUsername] = useState("");
  const [result, setResult] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AuditLog> | null>(null);
  const [meta, setMeta] = useState<{ categories: string[]; usernames: string[] }>({ categories: [], usernames: [] });
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    api.get<typeof meta>("/audit/meta").then(setMeta).catch(() => undefined);
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => {
      api
        .get<Page<AuditLog>>(
          `/audit${qs({
            q: q || undefined,
            category: cats.join(",") || undefined,
            username: username || undefined,
            result: result || undefined,
            start: start ? new Date(start).toISOString() : undefined,
            end: end ? new Date(end).toISOString() : undefined,
            page,
            page_size: 40,
          })}`,
        )
        .then(setData)
        .catch(() => undefined);
    }, 250);
    return () => window.clearTimeout(t);
  }, [q, cats, username, result, start, end, page]);

  const toggleCat = (c: string) => {
    setPage(1);
    setCats((xs) => (xs.includes(c) ? xs.filter((x) => x !== c) : [...xs, c]));
  };

  return (
    <div className="space-y-3">
      <div className="space-y-2.5 rounded-panel border border-line bg-surface p-3">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Từ khoá" className="min-w-[240px] flex-1">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-mute" />
              <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Mô tả, hành động, đối tượng, người dùng…" className="pl-8" />
            </div>
          </Field>
          <Field label="Người dùng" className="w-[160px]">
            <Select value={username} onChange={(e) => { setUsername(e.target.value); setPage(1); }}>
              <option value="">Tất cả</option>
              {meta.usernames.map((u) => <option key={u} value={u}>{u}</option>)}
            </Select>
          </Field>
          <Field label="Kết quả" className="w-[140px]">
            <Select value={result} onChange={(e) => { setResult(e.target.value); setPage(1); }}>
              <option value="">Tất cả</option>
              <option value="SUCCESS">Thành công</option>
              <option value="FAILURE">Thất bại / lỗi</option>
            </Select>
          </Field>
          <Field label="Từ" className="w-[190px]"><Input type="datetime-local" value={start} onChange={(e) => { setStart(e.target.value); setPage(1); }} /></Field>
          <Field label="Đến" className="w-[190px]"><Input type="datetime-local" value={end} onChange={(e) => { setEnd(e.target.value); setPage(1); }} /></Field>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs text-ink-dim">Loại sự kiện</span>
          {(meta.categories.length ? meta.categories : Object.keys(CAT_LABEL)).map((c) => {
            const on = cats.includes(c);
            return (
              <button
                key={c}
                onClick={() => toggleCat(c)}
                aria-pressed={on}
                className={clsx("rounded-tag border px-2 py-0.5 text-2xs font-medium transition-colors", on ? "text-carbon" : "text-ink-dim hover:text-ink")}
                style={on ? { background: CAT_COLOR[c], borderColor: CAT_COLOR[c] } : { borderColor: "#334155" }}
              >
                {CAT_LABEL[c] ?? c}
              </button>
            );
          })}
          {cats.length > 0 && (
            <button onClick={() => setCats([])} className="text-2xs text-ink-mute underline-offset-2 hover:underline">
              Bỏ lọc
            </button>
          )}
        </div>
      </div>

      <Panel title="Nhật ký hoạt động hệ thống (audit trail)" icon={<ScrollText className="h-4 w-4" />} bodyClassName="p-0">
        {!data ? (
          <Spinner />
        ) : data.items.length === 0 ? (
          <Empty title="Không có bản ghi phù hợp" hint="Thử bỏ bớt điều kiện lọc." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-ink-mute">
                  {["", "Thời gian", "Loại", "Hành động", "Người thực hiện", "Mô tả", "IP", "Kết quả"].map((h, i) => (
                    <th key={i} className="px-3 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((l) => (
                  <Fragment key={l.id}>
                    <tr className="cursor-pointer border-b border-line/40 hover:bg-panel/40" onClick={() => setOpen(open === l.id ? null : l.id)}>
                      <td className="w-6 px-2 py-1.5 text-ink-mute">
                        <ChevronRight className={clsx("h-3.5 w-3.5 transition-transform", open === l.id && "rotate-90")} />
                      </td>
                      <td className="num whitespace-nowrap px-3 py-1.5 text-ink-dim">{fmtDateTime(l.created_at)}</td>
                      <td className="px-3 py-1.5"><Badge color={CAT_COLOR[l.category] ?? "#64748B"}>{CAT_LABEL[l.category] ?? l.category}</Badge></td>
                      <td className="num px-3 py-1.5 text-2xs">{l.action}</td>
                      <td className="px-3 py-1.5">
                        {l.username}
                        {l.role && <span className="ml-1 text-2xs" style={{ color: tone(ROLE_COLOR[l.role], 75) }}>{l.role}</span>}
                      </td>
                      <td className="max-w-[420px] truncate px-3 py-1.5 text-ink-dim" title={l.description}>{l.description}</td>
                      <td className="num px-3 py-1.5 text-2xs text-ink-mute">{l.ip ?? "—"}</td>
                      <td className="px-3 py-1.5">
                        <Badge color={l.result === "SUCCESS" ? "#10B981" : "#EF4444"}>{l.result === "SUCCESS" ? "Thành công" : "Thất bại"}</Badge>
                      </td>
                    </tr>
                    {open === l.id && (
                      <tr className="border-b border-line/40 bg-carbon">
                        <td />
                        <td colSpan={7} className="px-3 py-2">
                          <div className="text-xs text-ink-dim">{l.description}</div>
                          {l.target && <div className="num mt-1 text-2xs text-ink-mute">Đối tượng: {l.target}</div>}
                          <pre className="num mt-1.5 max-h-48 overflow-auto rounded-ctl border border-line bg-surface p-2 text-2xs text-ink-dim">{JSON.stringify(l.details, null, 2)}</pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pager page={page} pageSize={40} total={data.total} onPage={setPage} />}
      </Panel>
    </div>
  );
}

export default function UsersAuditPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const canUsers = can("users:manage");
  const canAudit = can("audit:view");
  const tab = (params.get("tab") as "users" | "audit") || (canUsers ? "users" : "audit");
  const tabs = [
    ...(canUsers ? [{ id: "users" as const, label: "Tài khoản & phân quyền", icon: <Users className="h-4 w-4" /> }] : []),
    ...(canAudit ? [{ id: "audit" as const, label: "Nhật ký hoạt động", icon: <ScrollText className="h-4 w-4" /> }] : []),
  ];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-line/80 bg-surface p-4 shadow-panel">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-ink">Quản trị Tài khoản & Nhật ký Hoạt động</h1>
          <p className="mt-0.5 text-xs font-medium text-ink-mute">
            Phân quyền vai trò quản trị (Admin, Operator, Manager), bảo mật truy cập và đối soát nhật ký kiểm toán (Audit Trail).
          </p>
        </div>
      </div>
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={tabs} />
      {tab === "users" && canUsers ? <UsersTab /> : canAudit ? <AuditTab /> : <Empty title="Không có quyền truy cập" />}
    </div>
  );
}
