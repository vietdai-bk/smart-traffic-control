import clsx from "clsx";
import { CheckCheck, Cpu, Search, ShieldAlert, Siren, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { Badge, Button, Empty, Pager, Panel, Spinner, Tabs } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";
import { useToast } from "@/context/ToastContext";
import { api, qs } from "@/lib/api";
import { DIR_LABEL, STATUS_LABEL, fmtDateTime, since, tone } from "@/lib/format";
import type { Alert, Incident, Intersection, Page } from "@/lib/types";

type Tab = "alerts" | "incidents";

const LEVEL_C = { CRITICAL: "#EF4444", WARNING: "#F59E0B" } as const;
const STATUS_C: Record<string, string> = { ACTIVE: "#EF4444", OPEN: "#EF4444", ACKNOWLEDGED: "#F59E0B", RESOLVED: "#10B981" };
const TYPE_LABEL: Record<string, string> = { CONGESTION: "Ùn tắc / đông đúc", FAILSAFE: "Fail-safe", SAFETY: "Khoá an toàn" };
const DEVICE_LABEL: Record<string, string> = { CAMERA: "Camera", CONTROLLER: "Bộ điều khiển đèn", VISION: "Thuật toán AI" };
const INCIDENT_LABEL: Record<string, string> = {
  CONNECTION_LOST: "Mất kết nối",
  TIMEOUT: "Hết thời gian phản hồi",
  DEGRADED: "Suy giảm chất lượng",
  HARDWARE_FAULT: "Lỗi phần cứng",
  ALGORITHM_ERROR: "Lỗi thuật toán",
};

function useIntersections() {
  const [list, setList] = useState<Intersection[]>([]);
  useEffect(() => {
    api.get<Intersection[]>("/intersections").then(setList).catch(() => undefined);
  }, []);
  return list;
}

function AlertsTab({ names, intersections }: { names: Record<number, string>; intersections: Intersection[] }) {
  const { can } = useAuth();
  const toast = useToast();
  const { activeAlerts } = useLive();
  const [status, setStatus] = useState("OPEN");
  const [type, setType] = useState("");
  const [level, setLevel] = useState("");
  const [iid, setIid] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<Alert> | null>(null);
  const [ackTarget, setAckTarget] = useState<Alert | "ALL" | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<Page<Alert>>(`/alerts${qs({ status: status || undefined, alert_type: type || undefined, level: level || undefined, intersection_id: iid || undefined, q: q || undefined, page, page_size: 30 })}`)
      .then(setData)
      .catch(() => undefined);
  }, [status, type, level, iid, q, page]);

  useEffect(load, [load]);
  // làm mới khi có cảnh báo thời gian thực thay đổi
  const liveKey = useMemo(() => activeAlerts.map((a) => `${a.id}:${a.status}:${a.level}`).join(","), [activeAlerts]);
  useEffect(() => {
    const t = window.setTimeout(load, 300);
    return () => window.clearTimeout(t);
  }, [liveKey, load]);

  const submitAck = async () => {
    setBusy(true);
    try {
      if (ackTarget === "ALL") {
        const r = await api.post<{ acknowledged: number }>(`/alerts/ack-all${qs({ intersection_id: iid || undefined })}`, { note: note || null });
        toast("success", `Đã xác nhận ${r.acknowledged} cảnh báo`);
      } else if (ackTarget) {
        await api.post(`/alerts/${ackTarget.id}/ack`, { note: note || null });
        toast("success", "Đã xác nhận cảnh báo", ackTarget.title);
      }
      setAckTarget(null);
      setNote("");
      load();
    } catch (e) {
      toast("error", "Không xác nhận được", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-end gap-2 rounded-panel border border-line bg-surface p-3">
        <Field label="Trạng thái" className="w-[170px]">
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="OPEN">Đang mở (chưa đóng)</option>
            <option value="ACTIVE">Chưa xác nhận</option>
            <option value="ACKNOWLEDGED">Đã xác nhận</option>
            <option value="RESOLVED">Đã đóng</option>
            <option value="">Tất cả</option>
          </Select>
        </Field>
        <Field label="Loại" className="w-[160px]">
          <Select value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}>
            <option value="">Tất cả</option>
            {Object.entries(TYPE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </Select>
        </Field>
        <Field label="Mức độ" className="w-[130px]">
          <Select value={level} onChange={(e) => { setLevel(e.target.value); setPage(1); }}>
            <option value="">Tất cả</option>
            <option value="CRITICAL">Khẩn cấp</option>
            <option value="WARNING">Cảnh báo</option>
          </Select>
        </Field>
        <Field label="Nút giao" className="w-[240px]">
          <Select value={iid} onChange={(e) => { setIid(e.target.value); setPage(1); }}>
            <option value="">Tất cả</option>
            {intersections.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Tìm kiếm" className="min-w-[200px] flex-1">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-mute" />
            <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Tiêu đề, nội dung…" className="pl-8" />
          </div>
        </Field>
        {can("alerts:ack") && (
          <Button variant="secondary" icon={<CheckCheck className="h-3.5 w-3.5" />} onClick={() => setAckTarget("ALL")}>
            Xác nhận tất cả
          </Button>
        )}
      </div>

      <Panel title="Danh sách cảnh báo" icon={<Siren className="h-4 w-4" />} bodyClassName="p-0">
        {!data ? (
          <Spinner />
        ) : data.items.length === 0 ? (
          <Empty title="Không có cảnh báo phù hợp" hint="Đổi bộ lọc trạng thái sang “Tất cả” để xem lịch sử." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px] text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-ink-mute">
                  {["Thời điểm", "Mức", "Nút giao / hướng", "Nội dung", "Mật độ / hàng đợi", "Trạng thái", "Người xác nhận", ""].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id} className={clsx("border-b border-line/40 align-top", a.status === "ACTIVE" && a.level === "CRITICAL" && "bg-stop/5")}>
                    <td className="num whitespace-nowrap px-3 py-2 text-ink-dim">
                      {fmtDateTime(a.created_at)}
                      <div className="text-2xs text-ink-mute">kéo dài {since(a.created_at, a.resolved_at)}</div>
                    </td>
                    <td className="px-3 py-2">
                      <Badge color={LEVEL_C[a.level]} pulse={a.status === "ACTIVE" && a.level === "CRITICAL"}>
                        {a.level === "CRITICAL" ? "Khẩn cấp" : "Cảnh báo"}
                      </Badge>
                      <div className="mt-1 text-2xs text-ink-mute">{TYPE_LABEL[a.alert_type]}</div>
                    </td>
                    <td className="px-3 py-2">
                      <div className="max-w-[220px] truncate">{names[a.intersection_id] ?? `#${a.intersection_id}`}</div>
                      <div className="text-2xs text-ink-mute">{a.direction ? `Hướng ${DIR_LABEL[a.direction]}` : "Toàn nút giao"}</div>
                    </td>
                    <td className="max-w-[360px] px-3 py-2">
                      <div className="font-medium">{a.title}</div>
                      <div className="mt-0.5 text-2xs leading-relaxed text-ink-dim">{a.message}</div>
                    </td>
                    <td className="num whitespace-nowrap px-3 py-2">
                      {a.density != null ? `${a.density.toFixed(0)}% (đỉnh ${a.peak_density?.toFixed(0)}%)` : "—"}
                      <div className="text-2xs text-ink-mute">{a.queue_m != null ? `${a.queue_m.toFixed(0)} m` : ""}</div>
                    </td>
                    <td className="px-3 py-2">
                      <Badge color={STATUS_C[a.status]}>{STATUS_LABEL[a.status]}</Badge>
                    </td>
                    <td className="px-3 py-2 text-ink-dim">
                      {a.acknowledged_by ?? "—"}
                      {a.acknowledged_at && <div className="num text-2xs text-ink-mute">{fmtDateTime(a.acknowledged_at)}</div>}
                      {a.ack_note && <div className="max-w-[200px] text-2xs italic text-ink-mute">“{a.ack_note}”</div>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {a.status === "ACTIVE" && can("alerts:ack") && (
                        <Button size="sm" variant="secondary" onClick={() => setAckTarget(a)}>
                          Xác nhận
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pager page={page} pageSize={30} total={data.total} onPage={setPage} />}
      </Panel>

      <Modal
        open={ackTarget != null}
        onClose={() => setAckTarget(null)}
        title={ackTarget === "ALL" ? "Xác nhận tất cả cảnh báo chưa xử lý" : "Xác nhận cảnh báo"}
        icon={<CheckCheck className="h-4 w-4 text-go" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setAckTarget(null)}>Huỷ</Button>
            <Button variant="primary" loading={busy} onClick={submitAck}>Xác nhận</Button>
          </>
        }
      >
        {ackTarget && ackTarget !== "ALL" && (
          <div className="mb-3 rounded-ctl border border-line bg-carbon p-2.5 text-xs">
            <div className="font-semibold">{ackTarget.title}</div>
            <div className="mt-0.5 text-ink-dim">{ackTarget.message}</div>
          </div>
        )}
        <Field label="Ghi chú xử lý (lưu vào CSDL và nhật ký)">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="vd: Đã phối hợp CSGT phân luồng, AI đang tăng thời gian xanh…" />
        </Field>
      </Modal>
    </>
  );
}

function IncidentsTab({ names, intersections }: { names: Record<number, string>; intersections: Intersection[] }) {
  const { can } = useAuth();
  const toast = useToast();
  const { openIncidents } = useLive();
  const [status, setStatus] = useState("OPEN");
  const [device, setDevice] = useState("");
  const [iid, setIid] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<Incident> | null>(null);
  const [target, setTarget] = useState<{ inc: Incident; action: "ack" | "resolve" } | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<Page<Incident>>(`/incidents${qs({ status: status || undefined, device_type: device || undefined, intersection_id: iid || undefined, q: q || undefined, page, page_size: 30 })}`)
      .then(setData)
      .catch(() => undefined);
  }, [status, device, iid, q, page]);
  useEffect(load, [load]);
  const liveKey = useMemo(() => openIncidents.map((i) => `${i.id}:${i.status}:${i.recovered_at}`).join(","), [openIncidents]);
  useEffect(() => {
    const t = window.setTimeout(load, 300);
    return () => window.clearTimeout(t);
  }, [liveKey, load]);

  const submit = async () => {
    if (!target) return;
    setBusy(true);
    try {
      if (target.action === "ack") await api.post(`/incidents/${target.inc.id}/ack`, { note: note || null });
      else await api.post(`/incidents/${target.inc.id}/resolve`, { note });
      toast("success", target.action === "ack" ? "Đã xác nhận sự cố" : "Đã đóng sự cố", target.inc.device_code);
      setTarget(null);
      setNote("");
      load();
    } catch (e) {
      toast("error", "Thao tác thất bại", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-end gap-2 rounded-panel border border-line bg-surface p-3">
        <Field label="Trạng thái" className="w-[170px]">
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="OPEN">Chưa đóng</option>
            <option value="ACKNOWLEDGED">Đã xác nhận</option>
            <option value="RESOLVED">Đã khắc phục</option>
            <option value="">Tất cả</option>
          </Select>
        </Field>
        <Field label="Thiết bị" className="w-[180px]">
          <Select value={device} onChange={(e) => { setDevice(e.target.value); setPage(1); }}>
            <option value="">Tất cả</option>
            {Object.entries(DEVICE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </Select>
        </Field>
        <Field label="Nút giao" className="w-[240px]">
          <Select value={iid} onChange={(e) => { setIid(e.target.value); setPage(1); }}>
            <option value="">Tất cả</option>
            {intersections.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Tìm kiếm" className="min-w-[200px] flex-1">
          <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Mã thiết bị, nội dung…" />
        </Field>
      </div>

      <Panel title="Sự cố thiết bị & lịch sử bảo trì" icon={<Cpu className="h-4 w-4" />} bodyClassName="p-0">
        {!data ? (
          <Spinner />
        ) : data.items.length === 0 ? (
          <Empty title="Không có sự cố phù hợp" hint="Tất cả thiết bị đang hoạt động bình thường." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1060px] text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs text-ink-mute">
                  {["Phát sinh", "Thiết bị", "Sự cố", "Kết nối lại", "Gián đoạn", "Trạng thái", "Khắc phục", ""].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id} className={clsx("border-b border-line/40 align-top", !i.recovered_at && "bg-stop/5")}>
                    <td className="num whitespace-nowrap px-3 py-2 text-ink-dim">{fmtDateTime(i.started_at)}</td>
                    <td className="px-3 py-2">
                      <div className="num font-medium">{i.device_code}</div>
                      <div className="text-2xs text-ink-mute">
                        {DEVICE_LABEL[i.device_type]} · {names[i.intersection_id] ?? `#${i.intersection_id}`}
                      </div>
                    </td>
                    <td className="max-w-[320px] px-3 py-2">
                      <Badge color={i.severity === "CRITICAL" ? "#EF4444" : "#F59E0B"}>{INCIDENT_LABEL[i.incident_type] ?? i.incident_type}</Badge>
                      <div className="mt-1 text-2xs leading-relaxed text-ink-dim">{i.message}</div>
                    </td>
                    <td className="num whitespace-nowrap px-3 py-2">
                      {i.recovered_at ? fmtDateTime(i.recovered_at) : <span className="font-semibold text-stop">Đang mất kết nối</span>}
                    </td>
                    <td className="num whitespace-nowrap px-3 py-2">{since(i.started_at, i.recovered_at)}</td>
                    <td className="px-3 py-2">
                      <Badge color={STATUS_C[i.status]}>{STATUS_LABEL[i.status]}</Badge>
                      {i.acknowledged_by && <div className="mt-1 text-2xs text-ink-mute">xác nhận: {i.acknowledged_by}</div>}
                    </td>
                    <td className="max-w-[240px] px-3 py-2 text-2xs text-ink-dim">
                      {i.resolution_note ?? "—"}
                      {i.resolved_by && <div className="num text-ink-mute">{i.resolved_by} · {fmtDateTime(i.resolved_at)}</div>}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      {can("alerts:ack") && i.status === "OPEN" && (
                        <Button size="sm" variant="ghost" onClick={() => setTarget({ inc: i, action: "ack" })}>
                          Xác nhận
                        </Button>
                      )}
                      {can("alerts:ack") && i.status !== "RESOLVED" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={<Wrench className="h-3.5 w-3.5" />}
                          disabled={!i.recovered_at}
                          title={!i.recovered_at ? "Thiết bị chưa kết nối lại" : undefined}
                          onClick={() => setTarget({ inc: i, action: "resolve" })}
                        >
                          Đóng sự cố
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pager page={page} pageSize={30} total={data.total} onPage={setPage} />}
      </Panel>

      <Modal
        open={target != null}
        onClose={() => setTarget(null)}
        title={target?.action === "resolve" ? "Đóng sự cố — ghi nhận khắc phục" : "Xác nhận sự cố"}
        icon={<Wrench className="h-4 w-4 text-auto" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setTarget(null)}>Huỷ</Button>
            <Button variant="primary" loading={busy} disabled={target?.action === "resolve" && note.trim().length < 3} onClick={submit}>
              {target?.action === "resolve" ? "Đóng sự cố" : "Xác nhận"}
            </Button>
          </>
        }
      >
        {target && (
          <div className="mb-3 rounded-ctl border border-line bg-carbon p-2.5 text-xs">
            <div className="num font-semibold">{target.inc.device_code}</div>
            <div className="mt-0.5 text-ink-dim">{target.inc.message}</div>
          </div>
        )}
        <Field label={target?.action === "resolve" ? "Nội dung khắc phục / bảo trì (bắt buộc)" : "Ghi chú (tuỳ chọn)"}>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="vd: Thay cáp mạng PoE, khởi động lại bộ mã hoá…" />
        </Field>
      </Modal>
    </>
  );
}

export default function AlertsPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "alerts";
  const intersections = useIntersections();
  const names = useMemo(() => Object.fromEntries(intersections.map((i) => [i.id, i.name])), [intersections]);
  const { activeAlerts, openIncidents } = useLive();

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-line/80 bg-surface p-4 shadow-panel">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-ink">Trung tâm Cảnh báo & Xử lý Sự cố</h1>
          <p className="mt-0.5 text-xs font-medium text-ink-mute">
            Cảnh báo ùn tắc vượt ngưỡng, fail-safe và sự cố thiết bị tại hiện trường được phát hiện tự động và đồng bộ thời gian thực.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {[
          { label: "Cảnh báo chưa xác nhận", v: activeAlerts.filter((a) => a.status === "ACTIVE").length, c: "#EF4444", icon: <ShieldAlert className="h-5 w-5" /> },
          { label: "Cảnh báo khẩn cấp đang mở", v: activeAlerts.filter((a) => a.level === "CRITICAL").length, c: "#EF4444", icon: <Siren className="h-5 w-5" /> },
          { label: "Thiết bị đang mất kết nối", v: openIncidents.filter((i) => !i.recovered_at).length, c: "#F59E0B", icon: <Cpu className="h-5 w-5" /> },
          { label: "Sự cố chờ đóng (đã phục hồi)", v: openIncidents.filter((i) => i.recovered_at).length, c: "#94A3B8", icon: <Wrench className="h-5 w-5" /> },
        ].map((s) => (
          <div key={s.label} className="relative flex items-center gap-3.5 rounded-panel border border-line/80 bg-surface p-3.5 shadow-panel transition-all hover:border-auto/50">
            {s.v > 0 && <span className="absolute inset-x-0 top-0 h-[3px] rounded-t-panel" style={{ background: s.c }} />}
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-ctl bg-panel" style={{ color: s.v ? s.c : "rgb(var(--c-ink-mute))" }}>
              {s.icon}
            </div>
            <div className="min-w-0">
              <div className="num text-2xl font-bold tracking-tight" style={{ color: s.v ? tone(s.c, 85) : undefined }}>{s.v}</div>
              <div className="text-2xs font-medium text-ink-mute truncate">{s.label}</div>
            </div>
          </div>
        ))}
      </div>
      <Tabs
        value={tab}
        onChange={(t) => setParams({ tab: t })}
        tabs={[
          { id: "alerts", label: "Cảnh báo giao thông", icon: <Siren className="h-4 w-4" />, count: activeAlerts.length },
          { id: "incidents", label: "Sự cố thiết bị", icon: <Cpu className="h-4 w-4" />, count: openIncidents.length },
        ]}
      />
      {tab === "alerts" ? <AlertsTab names={names} intersections={intersections} /> : <IncidentsTab names={names} intersections={intersections} />}
    </div>
  );
}
