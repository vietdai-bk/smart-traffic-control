import clsx from "clsx";
import { Activity, Camera as CameraIcon, MapPin, Pencil, Plus, Radar, Save, Trash2, TrafficCone } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RoiEditor } from "@/components/config/RoiEditor";
import { Field, Input, Select, Textarea, Toggle } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { Badge, Button, Empty, Panel, Spinner, Tabs } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, qs } from "@/lib/api";
import { DIRECTIONS, DIR_LABEL, MODE_LABEL } from "@/lib/format";
import type { Camera, Direction, Intersection } from "@/lib/types";

type FieldDef = {
  key: keyof Intersection;
  label: string;
  type?: "number" | "text" | "select" | "textarea";
  options?: { v: string; l: string }[];
  hint?: string;
  span?: 2;
  step?: number;
};

const SECTIONS: { title: string; hint?: string; fields: FieldDef[] }[] = [
  {
    title: "Thông tin nút giao",
    fields: [
      { key: "code", label: "Mã nút giao" },
      { key: "name", label: "Tên nút giao" },
      { key: "district", label: "Quận / khu vực" },
      { key: "lanes_per_approach", label: "Số làn mỗi hướng", type: "number" },
      { key: "ns_road", label: "Tên trục Bắc–Nam" },
      { key: "ew_road", label: "Tên trục Đông–Tây" },
      { key: "latitude", label: "Vĩ độ", type: "number", step: 0.00001 },
      { key: "longitude", label: "Kinh độ", type: "number", step: 0.00001 },
      { key: "description", label: "Mô tả", type: "textarea", span: 2 },
    ],
  },
  {
    title: "Kế hoạch đèn chuẩn & ràng buộc an toàn",
    hint: "Giới hạn cứng của hệ thống: xanh ≥ 5s, vàng ≥ 3s, toàn đỏ ≥ 2s. Thay đổi áp dụng ngay cho bộ khoá an toàn, thời gian mới có hiệu lực từ pha xanh kế tiếp.",
    fields: [
      {
        key: "default_mode",
        label: "Chế độ mặc định khi khởi động",
        type: "select",
        options: (["AUTO", "FIXED_TIME", "MANUAL"] as const).map((m) => ({ v: m, l: MODE_LABEL[m] })),
      },
      {
        key: "failsafe_strategy",
        label: "Chiến lược FAILSAFE",
        type: "select",
        options: [
          { v: "FIXED_TIME", l: "Chạy chu kỳ cố định chuẩn" },
          { v: "FLASHING_YELLOW", l: "Chớp vàng tất cả hướng" },
        ],
      },
      { key: "fixed_green_ns", label: "Xanh cố định Bắc–Nam (s)", type: "number" },
      { key: "fixed_green_ew", label: "Xanh cố định Đông–Tây (s)", type: "number" },
      { key: "yellow_s", label: "Vàng chuyển tiếp (s)", type: "number" },
      { key: "all_red_s", label: "Toàn đỏ (s)", type: "number" },
      { key: "min_green_s", label: "Xanh tối thiểu (s)", type: "number" },
      { key: "max_green_s", label: "Xanh tối đa (s)", type: "number" },
      { key: "cycle_min_s", label: "Chu kỳ tối thiểu (s)", type: "number" },
      { key: "cycle_max_s", label: "Chu kỳ tối đa (s)", type: "number" },
      { key: "saturation_flow", label: "Lưu lượng bão hoà (PCU/h/làn)", type: "number", hint: "Tham số Webster" },
    ],
  },
  {
    title: "Ngưỡng cảnh báo mật độ",
    hint: "Áp dụng cho mọi camera của nút giao trừ khi camera có ngưỡng riêng.",
    fields: [
      { key: "density_medium", label: "Ngưỡng Đông đúc (%)", type: "number" },
      { key: "density_high", label: "Ngưỡng Ùn tắc (%)", type: "number" },
      { key: "alert_hold_s", label: "Thời gian duy trì trước khi báo (s)", type: "number", hint: "Chống báo nhầm khi mật độ dao động" },
    ],
  },
  {
    title: "Bộ điều khiển đèn & mô phỏng",
    fields: [
      { key: "controller_endpoint", label: "Địa chỉ bộ điều khiển" },
      { key: "controller_model", label: "Model bộ điều khiển" },
      { key: "base_demand_ns", label: "Lưu lượng mô phỏng Bắc–Nam (xe/h/hướng)", type: "number" },
      { key: "base_demand_ew", label: "Lưu lượng mô phỏng Đông–Tây (xe/h/hướng)", type: "number" },
    ],
  },
];

function IntersectionTab({ list, reload, selected, setSelected }: { list: Intersection[]; reload: () => void; selected: number | null; setSelected: (id: number) => void }) {
  const { can } = useAuth();
  const toast = useToast();
  const manage = can("config:manage");
  const cur = list.find((i) => i.id === selected) ?? null;
  const [form, setForm] = useState<Partial<Intersection>>({});
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newIt, setNewIt] = useState({ code: "", name: "", district: "", lanes_per_approach: 3 });
  const [delOpen, setDelOpen] = useState(false);
  const [delCode, setDelCode] = useState("");
  const [ping, setPing] = useState<string | null>(null);

  useEffect(() => {
    if (cur) setForm(cur);
  }, [cur]);

  const dirty = useMemo(() => cur && SECTIONS.some((s) => s.fields.some((f) => form[f.key] !== cur[f.key])) || (cur && form.is_active !== cur.is_active), [form, cur]);

  const save = async () => {
    if (!cur) return;
    const patch: Record<string, unknown> = {};
    SECTIONS.forEach((s) => s.fields.forEach((f) => {
      if (form[f.key] !== cur[f.key]) patch[f.key] = f.type === "number" ? Number(form[f.key]) : form[f.key];
    }));
    if (form.is_active !== cur.is_active) patch.is_active = form.is_active;
    setSaving(true);
    try {
      await api.patch(`/intersections/${cur.id}`, patch);
      toast("success", "Đã lưu cấu hình nút giao", `${Object.keys(patch).length} thay đổi đã được áp dụng cho runtime`);
      reload();
    } catch (e) {
      toast("error", "Cấu hình không hợp lệ", (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const create = async () => {
    try {
      const it = await api.post<Intersection>("/intersections", { ...newIt, lanes_per_approach: Number(newIt.lanes_per_approach), create_default_cameras: true });
      toast("success", "Đã tạo nút giao", `${it.name} kèm 4 camera mô phỏng`);
      setCreating(false);
      setNewIt({ code: "", name: "", district: "", lanes_per_approach: 3 });
      reload();
      setSelected(it.id);
    } catch (e) {
      toast("error", "Không tạo được nút giao", (e as Error).message);
    }
  };

  const remove = async () => {
    if (!cur) return;
    try {
      await api.del(`/intersections/${cur.id}`);
      toast("success", "Đã xoá nút giao", cur.name);
      setDelOpen(false);
      setDelCode("");
      reload();
    } catch (e) {
      toast("error", "Không xoá được", (e as Error).message);
    }
  };

  const pingController = async () => {
    if (!cur) return;
    setPing("…");
    try {
      const r = await api.post<{ ok: boolean; latency_ms: number; error: string | null; signal_state: string }>(`/intersections/${cur.id}/controller/ping`);
      setPing(r.ok ? `OK · ${r.latency_ms.toFixed(0)} ms · trạng thái ${r.signal_state}` : `Lỗi: ${r.error}`);
    } catch (e) {
      setPing(`Lỗi: ${(e as Error).message}`);
    }
  };

  return (
    <div className="grid gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
      <Panel
        title="Danh sách nút giao"
        icon={<TrafficCone className="h-4 w-4" />}
        className="self-start xl:sticky xl:top-[calc(var(--header-h,57px)+16px)] xl:max-h-[calc(100dvh-var(--header-h,57px)-32px)] [&>header]:shrink-0"
        bodyClassName="p-1.5 xl:overflow-y-auto xl:overscroll-contain"
        actions={manage && <Button size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setCreating(true)}>Thêm</Button>}
      >
        <ul className="space-y-1">
          {list.map((i) => (
            <li key={i.id}>
              <button
                onClick={() => setSelected(i.id)}
                className={clsx("w-full rounded-ctl border px-2.5 py-2 text-left", i.id === selected ? "border-auto bg-panel" : "border-transparent hover:bg-panel/60")}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[13px] font-medium">{i.name}</span>
                  {!i.is_active && <Badge color="#64748B">Tắt</Badge>}
                </div>
                <div className="num mt-0.5 flex items-center gap-1.5 text-2xs text-ink-mute">
                  <MapPin className="h-3 w-3" />
                  {i.code} · {i.cameras.length} camera · {i.lanes_per_approach} làn
                </div>
              </button>
            </li>
          ))}
        </ul>
      </Panel>

      {!cur ? (
        <Empty title="Chọn một nút giao để xem cấu hình" />
      ) : (
        <Panel
          title={cur.name}
          icon={<MapPin className="h-4 w-4" />}
          actions={
            <div className="flex items-center gap-1.5">
              <Button size="sm" variant="ghost" icon={<Radar className="h-3.5 w-3.5" />} onClick={pingController}>
                Kiểm tra bộ điều khiển
              </Button>
              {manage && (
                <>
                  <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDelOpen(true)}>
                    Xoá
                  </Button>
                  <Button size="sm" variant="primary" icon={<Save className="h-3.5 w-3.5" />} disabled={!dirty} loading={saving} onClick={save}>
                    Lưu thay đổi
                  </Button>
                </>
              )}
            </div>
          }
        >
          {ping && <div className="num mb-3 rounded-ctl border border-line bg-carbon px-2.5 py-1.5 text-xs text-ink-dim">Ping {cur.controller_endpoint}: {ping}</div>}
          {!manage && <div className="mb-3 rounded-ctl border border-line bg-carbon px-2.5 py-1.5 text-xs text-ink-mute">Bạn đang ở chế độ chỉ xem. Chỉ Quản trị viên được thay đổi cấu hình.</div>}
          <div className="space-y-5">
            {SECTIONS.map((s) => (
              <fieldset key={s.title} disabled={!manage}>
                <legend className="text-[13px] font-semibold">{s.title}</legend>
                {s.hint && <p className="mt-0.5 text-2xs text-ink-mute">{s.hint}</p>}
                <div className="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {s.fields.map((f) => (
                    <Field key={String(f.key)} label={f.label} hint={f.hint} className={f.span === 2 ? "sm:col-span-2 xl:col-span-4" : undefined}>
                      {f.type === "select" ? (
                        <Select value={String(form[f.key] ?? "")} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
                          {f.options!.map((o) => (
                            <option key={o.v} value={o.v}>{o.l}</option>
                          ))}
                        </Select>
                      ) : f.type === "textarea" ? (
                        <Textarea value={String(form[f.key] ?? "")} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                      ) : (
                        <Input
                          type={f.type === "number" ? "number" : "text"}
                          step={f.step}
                          value={String(form[f.key] ?? "")}
                          onChange={(e) => setForm({ ...form, [f.key]: f.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value })}
                        />
                      )}
                    </Field>
                  ))}
                </div>
              </fieldset>
            ))}
            <Toggle checked={!!form.is_active} disabled={!manage} onChange={(v) => setForm({ ...form, is_active: v })} label="Nút giao đang hoạt động (tắt sẽ dừng runtime giám sát & điều khiển)" />
            <p className="num text-2xs text-ink-mute">
              Chu kỳ cố định = {Number(form.fixed_green_ns) + Number(form.fixed_green_ew) + 2 * (Number(form.yellow_s) + Number(form.all_red_s))}s · thời gian tổn thất L = {2 * (Number(form.yellow_s) + Number(form.all_red_s))}s
            </p>
          </div>
        </Panel>
      )}

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="Thêm nút giao"
        icon={<Plus className="h-4 w-4 text-auto" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>Huỷ</Button>
            <Button variant="primary" disabled={!newIt.code || !newIt.name} onClick={create}>Tạo nút giao</Button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Mã nút giao"><Input value={newIt.code} onChange={(e) => setNewIt({ ...newIt, code: e.target.value.toUpperCase() })} placeholder="DN-NVL-HP" /></Field>
          <Field label="Số làn mỗi hướng"><Input type="number" min={1} max={5} value={newIt.lanes_per_approach} onChange={(e) => setNewIt({ ...newIt, lanes_per_approach: Number(e.target.value) })} /></Field>
          <Field label="Tên nút giao" className="sm:col-span-2"><Input value={newIt.name} onChange={(e) => setNewIt({ ...newIt, name: e.target.value })} placeholder="Nút giao Nguyễn Văn Linh – Hàm Nghi" /></Field>
          <Field label="Quận / khu vực" className="sm:col-span-2"><Input value={newIt.district} onChange={(e) => setNewIt({ ...newIt, district: e.target.value })} /></Field>
        </div>
        <p className="mt-3 text-2xs text-ink-mute">Hệ thống tự tạo 4 camera mô phỏng cho 4 hướng và cấu hình đèn mặc định an toàn. Có thể chỉnh chi tiết sau khi tạo.</p>
      </Modal>

      <Modal
        open={delOpen}
        onClose={() => setDelOpen(false)}
        tone="danger"
        title="Xoá nút giao"
        icon={<Trash2 className="h-4 w-4 text-stop" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDelOpen(false)}>Huỷ</Button>
            <Button variant="danger" disabled={delCode !== cur?.code} onClick={remove}>Xoá vĩnh viễn</Button>
          </>
        }
      >
        <p className="text-sm text-ink-dim">
          Xoá <b className="text-ink">{cur?.name}</b> sẽ dừng giám sát và xoá toàn bộ camera, thống kê, chu kỳ đèn, cảnh báo của nút giao này.
        </p>
        <Field label={<>Gõ <span className="num text-ink">{cur?.code}</span> để xác nhận</>} className="mt-3">
          <Input value={delCode} onChange={(e) => setDelCode(e.target.value)} className="num" />
        </Field>
      </Modal>
    </div>
  );
}

const EMPTY_CAM = {
  code: "",
  name: "",
  direction: "NORTH" as Direction,
  source_type: "SIMULATED" as Camera["source_type"],
  stream_url: "",
  resolution: "1280x720",
  target_fps: 15,
  roi_length_m: 60,
  density_medium: "" as number | "",
  density_high: "" as number | "",
  is_enabled: true,
  roi: [] as number[][],
  counting_line: [] as number[][],
};

function CameraTab({ list, reload, selected, setSelected }: { list: Intersection[]; reload: () => void; selected: number | null; setSelected: (id: number) => void }) {
  const { can } = useAuth();
  const toast = useToast();
  const manage = can("config:manage");
  const cur = list.find((i) => i.id === selected) ?? null;
  const [edit, setEdit] = useState<{ id: number | null; data: typeof EMPTY_CAM } | null>(null);
  const [pings, setPings] = useState<Record<number, string>>({});
  const [del, setDel] = useState<Camera | null>(null);

  const openEdit = (c: Camera | null, direction?: Direction) => {
    if (c) {
      setEdit({
        id: c.id,
        data: { ...EMPTY_CAM, ...c, density_medium: c.density_medium ?? "", density_high: c.density_high ?? "", roi: c.roi, counting_line: c.counting_line },
      });
    } else if (cur) {
      api.get<{ roi: number[][]; counting_line: number[][] }>(`/cameras/default-geometry${qs({ lanes: cur.lanes_per_approach, roi_length_m: 60 })}`).then((g) =>
        setEdit({
          id: null,
          data: { ...EMPTY_CAM, direction: direction ?? "NORTH", code: `CAM-${cur.code}-${(direction ?? "NORTH")[0]}`.slice(0, 32), name: `Camera hướng ${DIR_LABEL[direction ?? "NORTH"]}`, roi: g.roi, counting_line: g.counting_line },
        }),
      );
    }
  };

  const resetGeometry = async () => {
    if (!edit || !cur) return;
    const g = await api.get<{ roi: number[][]; counting_line: number[][] }>(`/cameras/default-geometry${qs({ lanes: cur.lanes_per_approach, roi_length_m: edit.data.roi_length_m })}`);
    setEdit({ ...edit, data: { ...edit.data, roi: g.roi, counting_line: g.counting_line } });
  };

  const save = async () => {
    if (!edit || !cur) return;
    const d = edit.data;
    const body = {
      ...d,
      target_fps: Number(d.target_fps),
      roi_length_m: Number(d.roi_length_m),
      density_medium: d.density_medium === "" ? null : Number(d.density_medium),
      density_high: d.density_high === "" ? null : Number(d.density_high),
    };
    try {
      if (edit.id) {
        await api.patch(`/cameras/${edit.id}`, { ...body, clear_thresholds: d.density_medium === "" && d.density_high === "" });
        toast("success", "Đã cập nhật camera", d.code);
      } else {
        await api.post("/cameras", { ...body, intersection_id: cur.id });
        toast("success", "Đã thêm camera", d.code);
      }
      setEdit(null);
      reload();
    } catch (e) {
      toast("error", "Không lưu được camera", (e as Error).message);
    }
  };

  const ping = async (c: Camera) => {
    setPings((p) => ({ ...p, [c.id]: "Đang kiểm tra…" }));
    try {
      const r = await api.post<{ ok: boolean; status: string; latency_ms: number | null; fps?: number; error: string | null }>(`/cameras/${c.id}/ping`);
      setPings((p) => ({ ...p, [c.id]: r.ok ? `${r.status} · ${r.latency_ms} ms · ${r.fps} fps` : `OFFLINE · ${r.error}` }));
    } catch (e) {
      setPings((p) => ({ ...p, [c.id]: (e as Error).message }));
    }
  };

  const remove = async () => {
    if (!del) return;
    try {
      await api.del(`/cameras/${del.id}`);
      toast("success", "Đã xoá camera", del.code);
      setDel(null);
      reload();
    } catch (e) {
      toast("error", "Không xoá được", (e as Error).message);
    }
  };

  if (!cur) return <Empty title="Chưa có nút giao" />;
  const missing = DIRECTIONS.filter((d) => !cur.cameras.some((c) => c.direction === d));

  return (
    <>
      <div className="flex flex-wrap items-end gap-2 rounded-panel border border-line bg-surface p-3">
        <Field label="Nút giao" className="w-[320px]">
          <Select value={cur.id} onChange={(e) => setSelected(Number(e.target.value))}>
            {list.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </Select>
        </Field>
        <span className="text-xs text-ink-mute">
          Ngưỡng chung: đông đúc {cur.density_medium}% · ùn tắc {cur.density_high}%
        </span>
        {manage && missing.length > 0 && (
          <div className="ml-auto flex gap-1.5">
            {missing.map((d) => (
              <Button key={d} size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => openEdit(null, d)}>
                Camera hướng {DIR_LABEL[d]}
              </Button>
            ))}
          </div>
        )}
      </div>

      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
        {DIRECTIONS.map((d) => {
          const c = cur.cameras.find((x) => x.direction === d);
          return (
            <Panel
              key={d}
              title={`Hướng ${DIR_LABEL[d]}`}
              icon={<CameraIcon className="h-4 w-4" />}
              actions={c && <Badge color={c.is_enabled ? "#10B981" : "#64748B"}>{c.is_enabled ? c.source_type : "Đã tắt"}</Badge>}
            >
              {!c ? (
                <Empty title="Chưa gắn camera" hint={manage ? "Dùng nút thêm camera phía trên." : undefined} />
              ) : (
                <div className="space-y-2.5">
                  <RoiEditor roi={c.roi} line={c.counting_line} onChange={() => undefined} readOnly />
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                    <dt className="text-ink-mute">Mã</dt>
                    <dd className="num truncate">{c.code}</dd>
                    <dt className="text-ink-mute">Tên</dt>
                    <dd className="truncate" title={c.name}>{c.name}</dd>
                    <dt className="text-ink-mute">Luồng</dt>
                    <dd className="num truncate" title={c.stream_url}>{c.stream_url || "—"}</dd>
                    <dt className="text-ink-mute">Độ phân giải</dt>
                    <dd className="num">{c.resolution} @ {c.target_fps} fps</dd>
                    <dt className="text-ink-mute">Chiều dài ROI</dt>
                    <dd className="num">{c.roi_length_m} m</dd>
                    <dt className="text-ink-mute">Ngưỡng riêng</dt>
                    <dd className="num">{c.density_medium != null ? `${c.density_medium}% / ${c.density_high}%` : "Theo nút giao"}</dd>
                  </dl>
                  {pings[c.id] && <div className="num rounded-ctl bg-carbon px-2 py-1 text-2xs text-ink-dim">{pings[c.id]}</div>}
                  <div className="flex flex-wrap gap-1.5">
                    <Button size="sm" variant="secondary" icon={<Activity className="h-3.5 w-3.5" />} onClick={() => ping(c)}>
                      Kiểm tra kết nối
                    </Button>
                    {manage && (
                      <>
                        <Button size="sm" variant="secondary" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => openEdit(c)}>
                          Sửa & ROI
                        </Button>
                        <Button size="sm" variant="ghost" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDel(c)}>
                          Xoá
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </Panel>
          );
        })}
      </div>

      <Modal
        open={edit != null}
        onClose={() => setEdit(null)}
        width={820}
        title={edit?.id ? `Sửa camera ${edit.data.code}` : "Thêm camera"}
        icon={<CameraIcon className="h-4 w-4 text-auto" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEdit(null)}>Huỷ</Button>
            <Button variant="primary" icon={<Save className="h-3.5 w-3.5" />} onClick={save}>Lưu camera</Button>
          </>
        }
      >
        {edit && (
          <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
            <div className="grid content-start gap-3 sm:grid-cols-2">
              <Field label="Mã camera"><Input value={edit.data.code} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, code: e.target.value } })} /></Field>
              <Field label="Hướng">
                <Select value={edit.data.direction} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, direction: e.target.value as Direction } })}>
                  {DIRECTIONS.map((d) => <option key={d} value={d}>{DIR_LABEL[d]}</option>)}
                </Select>
              </Field>
              <Field label="Tên" className="sm:col-span-2"><Input value={edit.data.name} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, name: e.target.value } })} /></Field>
              <Field label="Nguồn">
                <Select value={edit.data.source_type} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, source_type: e.target.value as Camera["source_type"] } })}>
                  <option value="SIMULATED">Mô phỏng (SIMULATED)</option>
                  <option value="RTSP">RTSP</option>
                  <option value="HTTP">HTTP / MJPEG</option>
                  <option value="FILE">Tệp video</option>
                </Select>
              </Field>
              <Field label="Độ phân giải"><Input value={edit.data.resolution} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, resolution: e.target.value } })} /></Field>
              <Field label="Stream URL" className="sm:col-span-2" hint="Camera thực cần cài OpenCV (requirements-vision.txt)">
                <Input value={edit.data.stream_url} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, stream_url: e.target.value } })} placeholder="rtsp://user:pass@10.0.0.10:554/stream1" />
              </Field>
              <Field label="FPS mục tiêu"><Input type="number" value={edit.data.target_fps} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, target_fps: Number(e.target.value) } })} /></Field>
              <Field label="Chiều dài ROI (m)"><Input type="number" value={edit.data.roi_length_m} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, roi_length_m: Number(e.target.value) } })} /></Field>
              <Field label="Ngưỡng đông đúc riêng (%)" hint="Để trống = theo nút giao">
                <Input type="number" value={edit.data.density_medium} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, density_medium: e.target.value === "" ? "" : Number(e.target.value) } })} />
              </Field>
              <Field label="Ngưỡng ùn tắc riêng (%)">
                <Input type="number" value={edit.data.density_high} onChange={(e) => setEdit({ ...edit, data: { ...edit.data, density_high: e.target.value === "" ? "" : Number(e.target.value) } })} />
              </Field>
              <div className="sm:col-span-2">
                <Toggle checked={edit.data.is_enabled} onChange={(v) => setEdit({ ...edit, data: { ...edit.data, is_enabled: v } })} label="Camera đang bật" />
              </div>
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-medium text-ink-dim">Vùng theo dõi (ROI) & vạch đếm</span>
                <Button size="sm" variant="ghost" onClick={resetGeometry}>Đặt lại theo hiệu chuẩn</Button>
              </div>
              <RoiEditor
                roi={edit.data.roi}
                line={edit.data.counting_line}
                onChange={(roi, line) => setEdit({ ...edit, data: { ...edit.data, roi, counting_line: line } })}
              />
              <p className="num mt-1.5 text-2xs leading-relaxed text-ink-mute">
                ROI: {edit.data.roi.map((p) => `(${p[0].toFixed(2)}, ${p[1].toFixed(2)})`).join(" ")}
                <br />
                Vạch đếm: {edit.data.counting_line.map((p) => `(${p[0].toFixed(2)}, ${p[1].toFixed(2)})`).join(" → ")}
              </p>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={del != null}
        onClose={() => setDel(null)}
        tone="danger"
        title="Xoá camera"
        icon={<Trash2 className="h-4 w-4 text-stop" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDel(null)}>Huỷ</Button>
            <Button variant="danger" onClick={remove}>Xoá camera</Button>
          </>
        }
      >
        <p className="text-sm text-ink-dim">
          Xoá camera <b className="num text-ink">{del?.code}</b>? Hướng {del && DIR_LABEL[del.direction]} sẽ không còn dữ liệu đếm xe; nếu nút giao đang AUTO, thuật toán sẽ thiếu dữ liệu hướng này.
        </p>
      </Modal>
    </>
  );
}

export default function ConfigPage() {
  const [tab, setTab] = useState<"intersections" | "cameras">("intersections");
  const [list, setList] = useState<Intersection[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const reload = useCallback(() => {
    api.get<Intersection[]>("/intersections").then((l) => {
      setList(l);
      setSelected((s) => (s && l.some((i) => i.id === s) ? s : (l[0]?.id ?? null)));
    });
  }, []);
  useEffect(reload, [reload]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-line/80 bg-surface p-4 shadow-panel">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-ink">Quản trị Nút giao, Camera & Tham số An toàn</h1>
        </div>
      </div>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "intersections", label: "Nút giao & an toàn đèn", icon: <TrafficCone className="h-4 w-4" />, count: list?.length },
          { id: "cameras", label: "Camera 4 hướng", icon: <CameraIcon className="h-4 w-4" /> },
        ]}
      />
      {!list ? (
        <Spinner />
      ) : tab === "intersections" ? (
        <IntersectionTab list={list} reload={reload} selected={selected} setSelected={setSelected} />
      ) : (
        <CameraTab list={list} reload={reload} selected={selected} setSelected={setSelected} />
      )}
    </div>
  );
}
