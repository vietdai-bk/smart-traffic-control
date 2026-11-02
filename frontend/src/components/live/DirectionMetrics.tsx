import { Gauge } from "lucide-react";
import { CLASSES, CLASS_COLOR, CLASS_LABEL, DIRECTIONS, HEAD_COLOR, LEVEL_COLOR, fmtInt, tone } from "@/lib/format";
import type { Snapshot } from "@/lib/types";
import { Badge, Dot, Panel } from "../ui/primitives";

/** US06 + US07: đếm phương tiện theo hướng, mật độ, hàng đợi, mức độ. */
export function DirectionMetrics({ snap }: { snap: Snapshot | null }) {
  return (
    <Panel title="Lưu lượng & mật độ 4 hướng tiếp cận" icon={<Gauge className="h-4 w-4 text-auto" />} bodyClassName="p-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px] whitespace-nowrap text-xs">
          <thead>
            <tr className="border-b border-line/70 bg-panel/30 text-left text-2xs font-bold uppercase tracking-wider text-ink-mute">
              <th className="px-3.5 py-2.5">Hướng</th>
              <th className="px-3 py-2.5">Mật độ dòng xe</th>
              <th className="px-3 py-2.5 text-right">Chiều dài hàng đợi</th>
              <th className="px-3 py-2.5 text-right">Lưu lượng thông qua</th>
              <th className="px-3 py-2.5 text-right">Trong ROI</th>
              <th className="px-3.5 py-2.5 text-right">Đếm hôm nay</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/40">
            {DIRECTIONS.map((d) => {
              const m = snap?.directions[d];
              const head = snap?.signal.heads[d];
              if (!m) {
                return (
                  <tr key={d}>
                    <td className="px-3.5 py-3 text-ink-mute" colSpan={6}>
                      Đang chờ luồng dữ liệu…
                    </td>
                  </tr>
                );
              }
              const total = CLASSES.reduce((a, c) => a + m.counts_total[c], 0);
              const roiTotal = CLASSES.reduce((a, c) => a + m.in_roi[c], 0);
              const off = m.camera?.status === "OFFLINE";
              return (
                <tr key={d} className="transition-colors hover:bg-panel/40">
                  <td className="px-3.5 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <Dot color={head ? HEAD_COLOR[head.color] : "#334155"} size={9} pulse={head?.color === "FLASHING_YELLOW"} />
                      <span className="font-bold text-ink">{m.label}</span>
                      <Badge color={off ? "#EF4444" : LEVEL_COLOR[m.level]} pulse={m.level === "HIGH" && !off}>
                        {off ? "Mất camera" : m.level_label}
                      </Badge>
                    </div>
                  </td>
                  <td className="w-[190px] px-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-carbon ring-1 ring-line/50">
                        <div
                          className="h-full rounded-full transition-[width] duration-500"
                          style={{ width: `${Math.min(100, m.density_smoothed)}%`, background: LEVEL_COLOR[m.level] }}
                        />
                        <span
                          className="absolute top-0 bottom-0 w-0.5 bg-warn"
                          style={{ left: `${m.thresholds.medium}%` }}
                          title={`Ngưỡng đông đúc ${m.thresholds.medium}%`}
                        />
                        <span
                          className="absolute top-0 bottom-0 w-0.5 bg-stop"
                          style={{ left: `${m.thresholds.high}%` }}
                          title={`Ngưỡng ùn tắc ${m.thresholds.high}%`}
                        />
                      </div>
                      <span className="num w-10 text-right font-bold" style={{ color: tone(LEVEL_COLOR[m.level], 85) }}>
                        {m.density_smoothed.toFixed(0)}%
                      </span>
                    </div>
                    <div className="num mt-0.5 text-2xs font-medium text-ink-mute">
                      chiếm {(m.occupancy * 100).toFixed(0)}% diện tích · {m.roi_pcu.toFixed(1)} PCU
                    </div>
                  </td>
                  <td className="num px-3 py-2.5 text-right">
                    <div className="font-bold text-ink">{m.queue_m.toFixed(0)} m</div>
                    <div className="text-2xs text-ink-mute">
                      {m.queue_count} dừng · chờ {m.avg_wait_s == null ? "—" : `${m.avg_wait_s.toFixed(0)}s`}
                    </div>
                  </td>
                  <td className="num px-3 py-2.5 text-right">
                    <div className="font-bold text-ink">{fmtInt(m.flow_vph)}</div>
                    <div className="text-2xs text-ink-mute">xe/h · đến {fmtInt(m.arrival_pcu_h)} PCU</div>
                  </td>
                  <td className="num px-3 py-2.5 text-right font-bold text-ink" title="Số xe đang trong vùng ROI">
                    <span className="rounded-tag bg-panel px-1.5 py-0.5">{roiTotal}</span>
                  </td>
                  <td className="px-3.5 py-2.5 text-right">
                    <div className="num font-bold text-ink">{fmtInt(total)}</div>
                    <div className="num ml-auto grid w-max grid-cols-2 gap-x-2.5 text-2xs text-ink-mute">
                      {CLASSES.map((c) => (
                        <span key={c} title={CLASS_LABEL[c]} className="text-right font-medium">
                          <span style={{ color: CLASS_COLOR[c] }}>●</span> {fmtInt(m.counts_total[c])}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-line/70 bg-panel/20 px-3.5 py-2 text-2xs text-ink-mute">
        {CLASSES.map((c) => (
          <span key={c} className="flex items-center gap-1.5 font-medium">
            <span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLOR[c] }} />
            {CLASS_LABEL[c]}
          </span>
        ))}
        <span className="ml-auto font-medium">Vạch vàng/đỏ = Ngưỡng cảnh báo đông đúc/ùn tắc đã cấu hình</span>
      </div>
    </Panel>
  );
}
