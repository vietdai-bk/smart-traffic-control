import { CircleCheck, CircleMinus, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, qs } from "@/lib/api";
import { AFTER_COLOR, BEFORE_COLOR, fmtInt, fmtNum } from "@/lib/format";
import type { Intersection } from "@/lib/types";
import { AXIS, ChartTooltip, GRID, Legend } from "../ui/chart";
import { Field, Select } from "../ui/Form";
import { Panel, Segmented, Spinner } from "../ui/primitives";

interface ModeStats {
  samples: number;
  hours: number;
  matched_hours: number;
  vehicles: number;
  avg_wait_s: number | null;
  avg_queue_m: number | null;
  avg_density: number | null;
  congestion_rate: number | null;
  throughput_vph: number | null;
  throughput_pcu_h: number | null;
  cycles: number;
  avg_cycle_s: number | null;
  avg_green_ns_s: number | null;
  avg_green_ew_s: number | null;
}
interface Summary {
  before: ModeStats;
  after: ModeStats;
  improvement: {
    wait_reduction_pct: number | null;
    queue_reduction_pct: number | null;
    congestion_reduction_pct: number | null;
    density_reduction_pct: number | null;
    throughput_increase_pct: number | null;
  };
}
type Hourly = Record<string, number | null> & { hour: number };

function Delta({ value, goodWhenPositive }: { value: number | null; goodWhenPositive: boolean }) {
  if (value == null) return <span className="text-ink-mute">—</span>;
  const good = goodWhenPositive ? value > 0 : value < 0;
  const flat = Math.abs(value) < 0.5;
  const Icon = flat ? CircleMinus : good ? CircleCheck : TriangleAlert;
  return (
    <span
      className={`num inline-flex items-center gap-1 rounded-tag px-1.5 py-0.2 font-bold ${
        flat ? "bg-panel text-ink-dim" : good ? "bg-go/15 text-go" : "bg-warn/15 text-warn"
      }`}
      title={flat ? "Không đổi" : good ? "Cải thiện tốt" : "Kém hơn"}
    >
      <Icon className="h-3.5 w-3.5" />
      {value > 0 ? "+" : value < 0 ? "−" : ""}
      {Math.abs(value).toFixed(1)}%
    </span>
  );
}

function CompareCard({
  label,
  unit,
  before,
  after,
  improvement,
  improvementLabel,
  digits = 1,
}: {
  label: string;
  unit: string;
  before: number | null;
  after: number | null;
  improvement: number | null;
  improvementLabel: string;
  digits?: number;
}) {
  const max = Math.max(before ?? 0, after ?? 0, 1e-6);
  return (
    <div className="rounded-card border border-line/80 bg-surface p-3.5 shadow-panel transition-all hover:border-auto/50">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-bold text-ink-dim">{label}</span>
        <div className="text-right">
          <Delta value={improvement} goodWhenPositive />
          <span className="mt-0.5 block text-2xs font-medium text-ink-mute">{improvementLabel}</span>
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {[
          { k: "Trước · Cố định", v: before, c: BEFORE_COLOR },
          { k: "Sau · AI Adaptive", v: after, c: AFTER_COLOR },
        ].map((r) => (
          <div key={r.k}>
            <div className="flex items-baseline justify-between text-2xs">
              <span className="font-medium text-ink-mute">{r.k}</span>
              <span className="num font-bold text-ink">
                {r.v == null ? "—" : fmtNum(r.v, digits)} <span className="font-normal text-ink-mute">{unit}</span>
              </span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-carbon ring-1 ring-line/40">
              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${((r.v ?? 0) / max) * 100}%`, background: r.c }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function HourlyChart({ data, keyBase, title, unit }: { data: Hourly[]; keyBase: string; title: string; unit: string }) {
  return (
    <Panel
      title={title}
      actions={<Legend items={[{ label: "Cố định (trước)", color: BEFORE_COLOR, dashed: true }, { label: "AI Adaptive (sau)", color: AFTER_COLOR }]} />}
    >
      <div className="h-[230px]">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="hour" {...AXIS} tickFormatter={(h) => `${h}h`} interval={2} />
            <YAxis {...AXIS} axisLine={false} width={48} tickFormatter={(v) => fmtInt(v)} />
            <Tooltip content={<ChartTooltip unit={unit} labelFormatter={(h) => `${String(h).padStart(2, "0")}:00 – ${String(Number(h) + 1).padStart(2, "0")}:00`} />} />
            <Line type="monotone" dataKey={`fixed_${keyBase}`} name="Cố định (trước)" stroke={BEFORE_COLOR} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey={`auto_${keyBase}`} name="AI Adaptive (sau)" stroke={AFTER_COLOR} strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function EvaluationTab({ intersections }: { intersections: Intersection[] }) {
  const [iid, setIid] = useState("");
  const [days, setDays] = useState<"7" | "14" | "30">("7");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [hourly, setHourly] = useState<Hourly[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const q = qs({ intersection_id: iid || undefined, days });
    const tz = -new Date().getTimezoneOffset();
    setErr(null);
    Promise.all([api.get<Summary>(`/evaluation/summary${q}&tz_offset_min=${tz}`), api.get<Hourly[]>(`/evaluation/hourly${q}&tz_offset_min=${tz}`)])
      .then(([s, h]) => {
        setSummary(s);
        setHourly(h);
      })
      .catch((e) => setErr((e as Error).message));
  }, [iid, days]);

  if (err) return <div className="rounded-ctl border border-stop/60 bg-stop/10 p-3 text-sm font-semibold text-stop-ink">{err}</div>;
  if (!summary) return <Spinner />;
  const b = summary.before;
  const a = summary.after;
  const imp = summary.improvement;

  return (
    <div className="space-y-3">
      {/* Bộ lọc thanh công cụ */}
      <div className="no-print flex flex-wrap items-end gap-3 rounded-card border border-line/80 bg-surface p-3.5 shadow-panel">
        <Field label="Nút giao đối sánh" className="w-[280px]">
          <Select value={iid} onChange={(e) => setIid(e.target.value)}>
            <option value="">Tất cả các nút giao</option>
            {intersections.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </Select>
        </Field>
        <div>
          <span className="mb-1 block text-xs font-semibold text-ink-dim">Cửa sổ thời gian phân tích</span>
          <Segmented value={days} onChange={setDays} options={[{ id: "7", label: "7 ngày gần nhất" }, { id: "14", label: "14 ngày" }, { id: "30", label: "30 ngày" }]} />
        </div>
        <p className="ml-auto max-w-xl text-2xs leading-relaxed text-ink-mute">
          Phương pháp so sánh: ghép cặp từng bucket 5 phút cùng giờ trong ngày giữa hai giai đoạn <b className="text-ink">FIXED_TIME (Cố định)</b> và <b className="text-ink">AUTO (AI Webster)</b> để khử hoàn toàn độ lệch do giờ cao điểm.
        </p>
      </div>

      {/* Thẻ chỉ số đối sánh KPI */}
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-5">
        <CompareCard label="Thời gian chờ trung bình" unit="s" before={b.avg_wait_s} after={a.avg_wait_s} improvement={imp.wait_reduction_pct} improvementLabel="giảm thời gian chờ" />
        <CompareCard label="Chiều dài hàng đợi TB" unit="m" before={b.avg_queue_m} after={a.avg_queue_m} improvement={imp.queue_reduction_pct} improvementLabel="giảm hàng đợi" />
        <CompareCard label="Mật độ diện tích TB" unit="%" before={b.avg_density} after={a.avg_density} improvement={imp.density_reduction_pct} improvementLabel="giảm mật độ" />
        <CompareCard label="Tỷ lệ thời gian đông đúc" unit="%" before={b.congestion_rate} after={a.congestion_rate} improvement={imp.congestion_reduction_pct} improvementLabel="giảm ùn tắc" />
        <CompareCard label="Lưu lượng thông qua" unit="xe/h" before={b.throughput_vph} after={a.throughput_vph} improvement={imp.throughput_increase_pct} improvementLabel="tăng lưu lượng" digits={0} />
      </div>

      {/* Biểu đồ diễn tiến 24 giờ */}
      <div className="grid gap-3 xl:grid-cols-3">
        <HourlyChart data={hourly} keyBase="wait" title="Thời gian chờ 24h (giây/xe)" unit="s" />
        <HourlyChart data={hourly} keyBase="queue" title="Độ dài hàng đợi 24h (mét)" unit="m" />
        <HourlyChart data={hourly} keyBase="flow" title="Lưu lượng thông qua 24h (xe/h)" unit="xe/h" />
      </div>

      {/* Bảng đối sánh chi tiết */}
      <Panel title="Bảng đối sánh số liệu chi tiết" bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-xs">
            <thead>
              <tr className="border-b border-line/80 bg-panel/30 text-left text-2xs font-bold uppercase tracking-wider text-ink-mute">
                <th className="px-3.5 py-2.5">Chỉ số đo lường</th>
                <th className="px-3.5 py-2.5 text-right">Trước · Cố định</th>
                <th className="px-3.5 py-2.5 text-right">Sau · AI Adaptive</th>
                <th className="px-3.5 py-2.5 text-right">Mức độ thay đổi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/40">
              {[
                ["Số giờ thu thập dữ liệu", b.hours, a.hours, null, "giờ", 1],
                ["Số khung giờ được ghép cặp", b.matched_hours, a.matched_hours, null, "/ 24h", 0],
                ["Tổng phương tiện thông qua", b.vehicles, a.vehicles, null, "xe", 0],
                ["Thời gian chờ TB", b.avg_wait_s, a.avg_wait_s, imp.wait_reduction_pct, "s", 1],
                ["Chiều dài hàng đợi TB", b.avg_queue_m, a.avg_queue_m, imp.queue_reduction_pct, "m", 1],
                ["Mật độ dòng xe TB", b.avg_density, a.avg_density, imp.density_reduction_pct, "%", 1],
                ["Tỷ lệ thời gian đông đúc / ùn tắc", b.congestion_rate, a.congestion_rate, imp.congestion_reduction_pct, "%", 1],
                ["Lưu lượng thông qua TB", b.throughput_vph, a.throughput_vph, imp.throughput_increase_pct, "xe/h", 0],
                ["Lưu lượng quy đổi xe con", b.throughput_pcu_h, a.throughput_pcu_h, null, "PCU/h", 0],
                ["Số chu kỳ đèn thực thi", b.cycles, a.cycles, null, "chu kỳ", 0],
                ["Thời lượng chu kỳ TB", b.avg_cycle_s, a.avg_cycle_s, null, "s", 1],
                ["Thời gian xanh TB Bắc–Nam", b.avg_green_ns_s, a.avg_green_ns_s, null, "s", 1],
                ["Thời gian xanh TB Đông–Tây", b.avg_green_ew_s, a.avg_green_ew_s, null, "s", 1],
              ].map(([label, bv, av, d, unit, digits]) => (
                <tr key={label as string} className="transition-colors hover:bg-panel/40">
                  <td className="px-3.5 py-2 font-medium text-ink">{label}</td>
                  <td className="num px-3.5 py-2 text-right font-medium">
                    {bv == null ? "—" : fmtNum(bv as number, digits as number)} <span className="text-ink-mute">{unit}</span>
                  </td>
                  <td className="num px-3.5 py-2 text-right font-bold text-ink">
                    {av == null ? "—" : fmtNum(av as number, digits as number)} <span className="text-ink-mute">{unit}</span>
                  </td>
                  <td className="px-3.5 py-2 text-right">
                    {d == null ? <span className="text-ink-mute">—</span> : <Delta value={d as number} goodWhenPositive />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t border-line/70 bg-panel/20 px-3.5 py-2 text-2xs text-ink-mute">
          Ghi chú: Dấu + kèm icon xanh thể hiện mức độ cải thiện hiệu quả tích cực của hệ thống AI so với chu kỳ cố định truyền thống.
        </p>
      </Panel>
    </div>
  );
}
