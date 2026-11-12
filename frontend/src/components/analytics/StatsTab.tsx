import { Download, FileJson, Printer } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, download, qs } from "@/lib/api";
import { CLASSES, CLASS_COLOR, CLASS_LABEL, DIR_LABEL, fmtDateTime, fmtHour, fmtInt, fmtNum } from "@/lib/format";
import type { Direction, Intersection, StatRow } from "@/lib/types";
import { AXIS, ChartTooltip, CURSOR, GRID, Legend, SURFACE } from "../ui/chart";
import { Field, Input, Select } from "../ui/Form";
import { Button, Empty, Pager, Panel, Segmented, Spinner, Stat } from "../ui/primitives";

type Preset = "today" | "24h" | "7d" | "custom";
type Gran = "5min" | "hour" | "day";

interface Overview extends StatRow {
  peak_hour: string | null;
  peak_hour_total: number;
  avg_flow_vph: number;
  samples: number;
}
interface TableRow extends StatRow {
  time: string;
  intersection: string;
  direction: Direction;
  direction_label: string;
}

function toLocalInput(d: Date) {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}

export function StatsTab({ intersections }: { intersections: Intersection[] }) {
  const { can } = useAuth();
  const toast = useToast();
  const [iid, setIid] = useState<string>("");
  const [dir, setDir] = useState<string>("");
  const [preset, setPreset] = useState<Preset>("24h");
  const [gran, setGran] = useState<Gran>("hour");
  const [start, setStart] = useState(toLocalInput(new Date(Date.now() - 3 * 86400000)));
  const [end, setEnd] = useState(toLocalInput(new Date()));
  const [overview, setOverview] = useState<Overview | null>(null);
  const [series, setSeries] = useState<(StatRow & { time: string })[]>([]);
  const [byDir, setByDir] = useState<(StatRow & { direction: Direction; label: string })[]>([]);
  const [comp, setComp] = useState<{ cls: string; label: string; count: number; pct: number }[]>([]);
  const [table, setTable] = useState<{ items: TableRow[]; total: number }>({ items: [], total: 0 });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const filterQs = useMemo(
    () =>
      qs({
        intersection_id: iid || undefined,
        direction: dir || undefined,
        preset,
        start: preset === "custom" ? new Date(start).toISOString() : undefined,
        end: preset === "custom" ? new Date(end).toISOString() : undefined,
      }),
    [iid, dir, preset, start, end],
  );

  useEffect(() => {
    if (preset === "7d" && gran === "5min") setGran("hour");
  }, [preset, gran]);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setErr(null);
    const sep = filterQs ? "&" : "?";
    Promise.all([
      api.get<Overview>(`/stats/overview${filterQs}`),
      api.get<(StatRow & { time: string })[]>(`/stats/timeseries${filterQs}${sep}granularity=${gran}`),
      api.get<(StatRow & { direction: Direction; label: string })[]>(`/stats/by-direction${filterQs}`),
      api.get<{ cls: string; label: string; count: number; pct: number }[]>(`/stats/composition${filterQs}`),
    ])
      .then(([o, s, b, c]) => {
        if (cancel) return;
        setOverview(o);
        setSeries(s);
        setByDir(b);
        setComp(c);
        setPage(1);
      })
      .catch((e) => !cancel && setErr((e as Error).message))
      .finally(() => !cancel && setLoading(false));
    return () => {
      cancel = true;
    };
  }, [filterQs, gran]);

  useEffect(() => {
    const sep = filterQs ? "&" : "?";
    api
      .get<{ items: TableRow[]; total: number }>(`/stats/table${filterQs}${sep}page=${page}&page_size=25`)
      .then(setTable)
      .catch(() => undefined);
  }, [filterQs, page]);

  const exportFile = async (format: "csv" | "json") => {
    try {
      const sep = filterQs ? "&" : "?";
      await download(`/stats/export${filterQs}${sep}format=${format}`, `stcs_thong_ke.${format}`);
      toast("success", `Đã xuất báo cáo ${format.toUpperCase()}`);
    } catch (e) {
      toast("error", "Xuất báo cáo thất bại", (e as Error).message);
    }
  };

  const tickTime = (iso: string) =>
    gran === "day"
      ? new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })
      : gran === "hour" && preset === "7d"
        ? `${new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })} ${fmtHour(iso)}`
        : new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });

  const iName = intersections.find((i) => String(i.id) === iid)?.name ?? "Tất cả nút giao";

  return (
    <div className="space-y-3">
      {/* Bộ lọc: một hàng phía trên biểu đồ */}
      <div className="no-print flex flex-wrap items-end gap-2 rounded-panel border border-line bg-surface p-3">
        <Field label="Nút giao" className="w-[280px]">
          <Select value={iid} onChange={(e) => setIid(e.target.value)}>
            <option value="">Tất cả nút giao</option>
            {intersections.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Hướng" className="w-[130px]">
          <Select value={dir} onChange={(e) => setDir(e.target.value)}>
            <option value="">Cả 4 hướng</option>
            {(Object.keys(DIR_LABEL) as Direction[]).map((d) => (
              <option key={d} value={d}>
                {DIR_LABEL[d]}
              </option>
            ))}
          </Select>
        </Field>
        <div>
          <span className="mb-1 block text-xs font-medium text-ink-dim">Khoảng thời gian</span>
          <Segmented
            value={preset}
            onChange={setPreset}
            options={[
              { id: "today", label: "Hôm nay" },
              { id: "24h", label: "24 giờ qua" },
              { id: "7d", label: "7 ngày" },
              { id: "custom", label: "Tuỳ chọn" },
            ]}
          />
        </div>
        {preset === "custom" && (
          <>
            <Field label="Từ" className="w-[190px]">
              <Input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label="Đến" className="w-[190px]">
              <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </>
        )}
        <div>
          <span className="mb-1 block text-xs font-medium text-ink-dim">Độ chi tiết</span>
          <Segmented
            value={gran}
            onChange={setGran}
            options={[
              ...(preset !== "7d" ? [{ id: "5min" as Gran, label: "5 phút" }] : []),
              { id: "hour" as Gran, label: "Giờ" },
              { id: "day" as Gran, label: "Ngày" },
            ]}
          />
        </div>
        <div className="ml-auto flex gap-1.5">
          {can("stats:export") && (
            <>
              <Button variant="secondary" icon={<Download className="h-3.5 w-3.5" />} onClick={() => exportFile("csv")}>
                Xuất CSV
              </Button>
              <Button variant="secondary" icon={<FileJson className="h-3.5 w-3.5" />} onClick={() => exportFile("json")}>
                Xuất JSON
              </Button>
            </>
          )}
          <Button variant="ghost" icon={<Printer className="h-3.5 w-3.5" />} onClick={() => window.print()}>
            In báo cáo
          </Button>
        </div>
      </div>

      <div className="hidden print:block">
        <h1 className="text-lg font-bold">STCS — Báo cáo thống kê lưu lượng giao thông</h1>
        <p className="text-sm">
          {iName} · {dir ? `hướng ${DIR_LABEL[dir as Direction]}` : "cả 4 hướng"} · in lúc {fmtDateTime(new Date().toISOString())}
        </p>
      </div>

      {err && <div className="rounded-ctl border border-stop/60 bg-stop/10 p-3 text-sm font-semibold text-stop-ink">{err}</div>}
      {loading && !overview ? (
        <Spinner />
      ) : overview ? (
        <>
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-6">
            {[
              { label: "Tổng phương tiện", value: fmtInt(overview.total), unit: "xe", sub: `${fmtInt(overview.pcu)} PCU`, color: "#3B82F6" },
              { label: "Lưu lượng trung bình", value: fmtInt(overview.avg_flow_vph), unit: "xe/h", color: "#10B981" },
              {
                label: "Giờ cao điểm",
                value: overview.peak_hour ? fmtHour(overview.peak_hour) : "—",
                sub: overview.peak_hour ? `${fmtInt(overview.peak_hour_total)} xe · ${new Date(overview.peak_hour).toLocaleDateString("vi-VN")}` : undefined,
                color: "#F59E0B",
              },
              { label: "Mật độ trung bình", value: fmtNum(overview.avg_density), unit: "%", sub: `cao nhất ${fmtNum(overview.max_density)}%` },
              { label: "Hàng đợi trung bình", value: fmtNum(overview.avg_queue_m), unit: "m", sub: `dài nhất ${fmtNum(overview.max_queue_m)} m` },
              { label: "Thời gian chờ TB", value: fmtNum(overview.avg_wait_s), unit: "s" },
            ].map((s) => (
              <div key={s.label} className="relative min-w-0 rounded-panel border border-line/80 bg-surface p-3 shadow-panel transition-all hover:border-auto/50">
                {s.color && <span className="absolute inset-x-0 top-0 h-[3px] rounded-t-panel" style={{ background: s.color }} />}
                <Stat label={s.label} value={s.value} unit={s.unit} sub={s.sub} />
              </div>
            ))}
          </div>

          <div className="grid gap-3 xl:grid-cols-3">
            <Panel
              className="xl:col-span-2"
              title="Lưu lượng theo thời gian, phân loại phương tiện"
              actions={<Legend items={CLASSES.map((c) => ({ label: CLASS_LABEL[c], color: CLASS_COLOR[c] }))} />}
            >
              {series.length === 0 ? (
                <Empty title="Không có dữ liệu trong khoảng đã chọn" hint="Thử mở rộng khoảng thời gian hoặc bỏ bớt bộ lọc." />
              ) : (
                <div className="h-[280px]">
                  <ResponsiveContainer>
                    <BarChart data={series} margin={{ top: 8, right: 8, left: 4, bottom: 0 }} barCategoryGap={series.length > 60 ? 0 : "18%"}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="time" tickFormatter={tickTime} {...AXIS} minTickGap={28} />
                      <YAxis {...AXIS} axisLine={false} width={52} tickFormatter={(v) => fmtInt(v)} />
                      <Tooltip cursor={CURSOR} content={<ChartTooltip unit="xe" labelFormatter={(l) => fmtDateTime(String(l))} />} />
                      {CLASSES.map((c, i) => (
                        <Bar
                          key={c}
                          dataKey={c}
                          name={CLASS_LABEL[c]}
                          stackId="v"
                          fill={CLASS_COLOR[c]}
                          stroke={SURFACE}
                          strokeWidth={series.length > 60 ? 0 : 1}
                          radius={i === CLASSES.length - 1 ? [3, 3, 0, 0] : 0}
                          isAnimationActive={false}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Panel>

            <Panel title="Cơ cấu phương tiện">
              <div className="flex h-[280px] flex-col">
                <div className="relative min-h-0 flex-1">
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={comp} dataKey="count" nameKey="label" innerRadius="58%" outerRadius="86%" stroke={SURFACE} strokeWidth={2} isAnimationActive={false}>
                        {comp.map((c) => (
                          <Cell key={c.cls} fill={CLASS_COLOR[c.cls as keyof typeof CLASS_COLOR]} />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip unit="xe" />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <span className="num text-xl font-semibold">{fmtInt(overview.total)}</span>
                    <span className="text-2xs text-ink-mute">phương tiện</span>
                  </div>
                </div>
                <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  {comp.map((c) => (
                    <li key={c.cls} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-ink-dim">
                        <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CLASS_COLOR[c.cls as keyof typeof CLASS_COLOR] }} />
                        {c.label}
                      </span>
                      <span className="num text-ink">{fmtNum(c.pct)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Panel>
          </div>

          <div className="grid gap-3 xl:grid-cols-3">
            <Panel title="Phân bố theo hướng" actions={<Legend items={CLASSES.map((c) => ({ label: CLASS_LABEL[c], color: CLASS_COLOR[c] }))} />}>
              <div className="h-[240px]">
                <ResponsiveContainer>
                  <BarChart data={byDir} layout="vertical" margin={{ top: 4, right: 12, left: 0, bottom: 0 }} barCategoryGap="28%">
                    <CartesianGrid {...GRID} horizontal={false} vertical />
                    <XAxis type="number" {...AXIS} tickFormatter={(v) => fmtInt(v)} />
                    <YAxis type="category" dataKey="label" {...AXIS} width={40} axisLine={false} />
                    <Tooltip cursor={CURSOR} content={<ChartTooltip unit="xe" />} />
                    {CLASSES.map((c, i) => (
                      <Bar key={c} dataKey={c} name={CLASS_LABEL[c]} stackId="d" fill={CLASS_COLOR[c]} stroke={SURFACE} strokeWidth={2} radius={i === CLASSES.length - 1 ? [0, 4, 4, 0] : 0} isAnimationActive={false} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Mật độ trung bình (%)">
              <div className="h-[240px]">
                <ResponsiveContainer>
                  <LineChart data={series} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="time" tickFormatter={tickTime} {...AXIS} minTickGap={36} />
                    <YAxis {...AXIS} axisLine={false} width={44} domain={[0, 100]} />
                    <Tooltip content={<ChartTooltip unit="%" labelFormatter={(l) => fmtDateTime(String(l))} />} />
                    <Line type="monotone" dataKey="avg_density" name="Mật độ TB" stroke="#0891B2" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Thời gian chờ trung bình (giây)">
              <div className="h-[240px]">
                <ResponsiveContainer>
                  <LineChart data={series} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="time" tickFormatter={tickTime} {...AXIS} minTickGap={36} />
                    <YAxis {...AXIS} axisLine={false} width={44} />
                    <Tooltip content={<ChartTooltip unit="s" labelFormatter={(l) => fmtDateTime(String(l))} />} />
                    <Line type="monotone" dataKey="avg_wait_s" name="Chờ TB" stroke="#DB2777" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          </div>

          <Panel title="Bảng dữ liệu chi tiết (theo giờ × hướng)" bodyClassName="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-2xs text-ink-mute">
                    {["Giờ", "Nút giao", "Hướng", "Ô tô", "Xe máy", "Xe buýt", "Xe tải", "Tổng", "PCU", "Mật độ TB", "Hàng đợi TB", "Chờ TB"].map((h, i) => (
                      <th key={h} className={`px-3 py-2 font-medium ${i >= 3 ? "text-right" : ""}`}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.items.map((r, i) => (
                    <tr key={`${r.time}-${r.intersection}-${r.direction}-${i}`} className="border-b border-line/40 hover:bg-panel/40">
                      <td className="num px-3 py-1.5 text-ink-dim">{fmtDateTime(r.time).slice(0, 11)}</td>
                      <td className="max-w-[260px] truncate px-3 py-1.5">{r.intersection}</td>
                      <td className="px-3 py-1.5">{r.direction_label}</td>
                      {[r.car, r.motorbike, r.bus, r.truck].map((v, j) => (
                        <td key={j} className="num px-3 py-1.5 text-right text-ink-dim">
                          {fmtInt(v)}
                        </td>
                      ))}
                      <td className="num px-3 py-1.5 text-right font-semibold">{fmtInt(r.total)}</td>
                      <td className="num px-3 py-1.5 text-right">{fmtNum(r.pcu)}</td>
                      <td className="num px-3 py-1.5 text-right">{fmtNum(r.avg_density)}%</td>
                      <td className="num px-3 py-1.5 text-right">{fmtNum(r.avg_queue_m)} m</td>
                      <td className="num px-3 py-1.5 text-right">{fmtNum(r.avg_wait_s)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {table.items.length === 0 && <Empty title="Không có dòng dữ liệu" />}
            </div>
            <Pager page={page} pageSize={25} total={table.total} onPage={setPage} />
          </Panel>
        </>
      ) : null}
    </div>
  );
}
