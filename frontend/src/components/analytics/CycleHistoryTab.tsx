import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLive } from "@/context/LiveContext";
import { api, qs } from "@/lib/api";
import { COMMAND_LABEL, MODE_COLOR, MODE_LABEL, STATUS_LABEL, fmtDateTime, fmtNum, fmtTime } from "@/lib/format";
import type { Intersection, Mode, Page, SignalCommandLog, SignalCycle } from "@/lib/types";
import { AXIS, ChartTooltip, CURSOR, GRID, Legend } from "../ui/chart";
import { Field, Select } from "../ui/Form";
import { Badge, Empty, Pager, Panel, Segmented } from "../ui/primitives";

const NS_COLOR = "#0891B2";
const EW_COLOR = "#65A30D";
const CLEAR_COLOR = "#475569";

const STATUS_COLOR: Record<string, string> = { EXECUTED: "#10B981", ACCEPTED: "#3B82F6", SCHEDULED: "#F59E0B", REJECTED: "#EF4444" };

export function CycleHistoryTab({ intersections }: { intersections: Intersection[] }) {
  const { selectedId } = useLive();
  const [iid, setIid] = useState<number | null>(selectedId);
  const [hours, setHours] = useState<"2" | "24" | "168">("2");
  const [mode, setMode] = useState("");
  const [cycles, setCycles] = useState<Page<SignalCycle> | null>(null);
  const [cPage, setCPage] = useState(1);
  const [cmds, setCmds] = useState<Page<SignalCommandLog> | null>(null);
  const [source, setSource] = useState("MANUAL");
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (iid == null && intersections.length) setIid(intersections[0].id);
  }, [intersections, iid]);

  useEffect(() => {
    if (!iid) return;
    api.get<Page<SignalCycle>>(`/signals/${iid}/cycles${qs({ hours, mode: mode || undefined, page: cPage, page_size: 120 })}`).then(setCycles).catch(() => undefined);
  }, [iid, hours, mode, cPage]);

  useEffect(() => {
    if (!iid) return;
    api.get<Page<SignalCommandLog>>(`/signals/${iid}/commands${qs({ source: source || undefined, page, page_size: 20 })}`).then(setCmds).catch(() => undefined);
  }, [iid, source, page]);

  const chartData = useMemo(
    () =>
      (cycles?.items ?? [])
        .slice()
        .reverse()
        .map((c) => ({ t: c.started_at, ns: c.green_ns_s, ew: c.green_ew_s, clr: +(2 * (c.yellow_s + c.all_red_s)).toFixed(1), mode: c.mode })),
    [cycles],
  );

  return (
    <div className="space-y-3">
      <div className="no-print flex flex-wrap items-end gap-2 rounded-panel border border-line bg-surface p-3">
        <Field label="Nút giao" className="w-[280px]">
          <Select value={iid ?? ""} onChange={(e) => { setIid(Number(e.target.value)); setCPage(1); setPage(1); }}>
            {intersections.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </Select>
        </Field>
        <div>
          <span className="mb-1 block text-xs font-medium text-ink-dim">Khoảng thời gian</span>
          <Segmented value={hours} onChange={(v) => { setHours(v); setCPage(1); }} options={[{ id: "2", label: "2 giờ" }, { id: "24", label: "24 giờ" }, { id: "168", label: "7 ngày" }]} />
        </div>
        <Field label="Chế độ" className="w-[170px]">
          <Select value={mode} onChange={(e) => { setMode(e.target.value); setCPage(1); }}>
            <option value="">Tất cả</option>
            {(["AUTO", "FIXED_TIME", "MANUAL", "FAILSAFE"] as Mode[]).map((m) => (
              <option key={m} value={m}>
                {MODE_LABEL[m]}
              </option>
            ))}
          </Select>
        </Field>
        <span className="num ml-auto text-xs text-ink-mute">{cycles?.total.toLocaleString("vi-VN") ?? "—"} chu kỳ</span>
      </div>

      <Panel
        title="Cấu trúc chu kỳ đèn (mỗi cột là một chu kỳ)"
        actions={<Legend items={[{ label: "Xanh Bắc–Nam", color: NS_COLOR }, { label: "Xanh Đông–Tây", color: EW_COLOR }, { label: "Vàng + toàn đỏ", color: CLEAR_COLOR }]} />}
      >
        {chartData.length === 0 ? (
          <Empty title="Chưa có chu kỳ trong khoảng đã chọn" />
        ) : (
          <div className="h-[260px]">
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barCategoryGap={chartData.length > 80 ? 0 : 1}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="t" {...AXIS} tickFormatter={(t) => fmtTime(t).slice(0, 5)} minTickGap={40} />
                <YAxis {...AXIS} axisLine={false} width={44} unit="s" />
                <Tooltip cursor={CURSOR} content={<ChartTooltip unit="s" labelFormatter={(l) => fmtDateTime(String(l))} />} />
                <Bar dataKey="ns" name="Xanh Bắc–Nam" stackId="c" fill={NS_COLOR} isAnimationActive={false} />
                <Bar dataKey="ew" name="Xanh Đông–Tây" stackId="c" fill={EW_COLOR} isAnimationActive={false} />
                <Bar dataKey="clr" name="Vàng + toàn đỏ" stackId="c" fill={CLEAR_COLOR} radius={[3, 3, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      <div className="grid gap-3 2xl:grid-cols-2">
        <Panel title="Lịch sử chu kỳ đèn" bodyClassName="p-0">
          <div className="max-h-[520px] overflow-auto">
            <table className="w-full min-w-[760px] text-xs">
              <thead className="sticky top-0 bg-surface">
                <tr className="border-b border-line text-left text-2xs text-ink-mute">
                  {["Bắt đầu", "Chế độ", "Chu kỳ", "Xanh B–N", "Xanh Đ–T", "Vàng/Đỏ", "Nhu cầu B–N/Đ–T", "Chờ TB", "Thông qua"].map((h, i) => (
                    <th key={h} className={`px-3 py-2 font-medium ${i >= 2 ? "text-right" : ""}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(cycles?.items ?? []).map((c) => (
                  <tr key={c.id} className="border-b border-line/40 hover:bg-panel/40" title={c.plan_reason ?? undefined}>
                    <td className="num px-3 py-1.5 text-ink-dim">{fmtDateTime(c.started_at)}</td>
                    <td className="px-3 py-1.5">
                      <Badge color={MODE_COLOR[c.mode as Mode] ?? "#94A3B8"}>{c.mode}</Badge>
                    </td>
                    <td className="num px-3 py-1.5 text-right font-semibold">{fmtNum(c.cycle_length_s, 0)}s</td>
                    <td className="num px-3 py-1.5 text-right">{fmtNum(c.green_ns_s, 0)}s</td>
                    <td className="num px-3 py-1.5 text-right">{fmtNum(c.green_ew_s, 0)}s</td>
                    <td className="num px-3 py-1.5 text-right text-ink-mute">
                      {c.yellow_s}/{c.all_red_s}s
                    </td>
                    <td className="num px-3 py-1.5 text-right text-ink-dim">
                      {fmtNum(c.demand_ns_pcu, 0)} / {fmtNum(c.demand_ew_pcu, 0)}
                    </td>
                    <td className="num px-3 py-1.5 text-right">{fmtNum(c.avg_wait_s)}s</td>
                    <td className="num px-3 py-1.5 text-right">{c.throughput}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {cycles && <Pager page={cPage} pageSize={120} total={cycles.total} onPage={setCPage} />}
        </Panel>

        <Panel
          title="Lịch sử lệnh điều khiển đèn"
          bodyClassName="p-0"
          actions={
            <Segmented
              size="sm"
              value={source}
              onChange={(v) => { setSource(v); setPage(1); }}
              options={[{ id: "MANUAL", label: "Thủ công" }, { id: "AUTO", label: "Tự động" }, { id: "SYSTEM", label: "Hệ thống" }, { id: "", label: "Tất cả" }]}
            />
          }
        >
          <ul className="max-h-[520px] divide-y divide-line/40 overflow-auto">
            {(cmds?.items ?? []).map((c) => (
              <li key={c.id} className="px-3 py-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="num text-2xs text-ink-mute">{fmtDateTime(c.created_at)}</span>
                  <span className="font-semibold">{COMMAND_LABEL[c.command] ?? c.command}</span>
                  <Badge color={STATUS_COLOR[c.status] ?? "#94A3B8"}>{STATUS_LABEL[c.status] ?? c.status}</Badge>
                  <span className="text-ink-dim">{c.issued_by}</span>
                  <span className="num ml-auto text-2xs text-ink-mute">
                    {c.from_state} → {c.to_state}
                    {c.ack_latency_ms != null && ` · ACK ${c.ack_latency_ms.toFixed(0)}ms`}
                  </span>
                </div>
                {(c.message || c.reason) && (
                  <p className="mt-0.5 line-clamp-2 text-2xs leading-relaxed text-ink-mute">
                    {c.message}
                    {c.reason && c.source === "MANUAL" ? ` — Lý do: ${c.reason}` : ""}
                  </p>
                )}
              </li>
            ))}
            {cmds && cmds.items.length === 0 && <Empty title="Không có lệnh phù hợp bộ lọc" />}
          </ul>
          {cmds && <Pager page={page} pageSize={20} total={cmds.total} onPage={setPage} />}
        </Panel>
      </div>
    </div>
  );
}
