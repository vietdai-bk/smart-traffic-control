import { BrainCircuit } from "lucide-react";
import { MODE_LABEL } from "@/lib/format";
import type { Snapshot } from "@/lib/types";
import { Badge, Panel } from "../ui/primitives";

/** US09-T03: đề xuất thời gian xanh của AI + lý do diễn giải. */
export function AdaptivePlanCard({ snap }: { snap: Snapshot | null }) {
  const plan = snap?.plan;
  const sig = snap?.signal;
  const applied = snap?.plan_applied && sig?.mode === "AUTO";
  const active = sig?.active_plan;
  const total = plan ? plan.green_ns + plan.green_ew : 1;

  return (
    <Panel
      title="Webster · thời gian xanh (tầng 2)"
      icon={<BrainCircuit className="h-4 w-4 text-auto" />}
      actions={
        sig &&
        (applied ? (
          <Badge color="#3B82F6">Đang áp dụng từ pha kế tiếp</Badge>
        ) : sig.mode === "FAILSAFE" ? (
          <Badge color="#EF4444">Khoá do FAILSAFE</Badge>
        ) : (
          <Badge color="#94A3B8">Tham khảo · {MODE_LABEL[sig.mode]}</Badge>
        ))
      }
    >
      {!plan || !sig ? (
        <p className="py-8 text-center text-sm text-ink-mute">Đang thu thập dữ liệu hàng đợi từ 4 camera…</p>
      ) : (
        <div className="space-y-3.5">
          {/* Thanh phân bổ thời gian xanh */}
          <div>
            <div className="mb-1.5 flex justify-between text-2xs font-semibold text-ink-mute">
              <span>Phân bổ thời gian xanh đề xuất (Webster)</span>
              <span className="num font-bold text-ink">
                Chu kỳ {plan.cycle_s.toFixed(0)}s · Lý thuyết {plan.webster_cycle_s.toFixed(0)}s
              </span>
            </div>
            <div className="flex h-8 overflow-hidden rounded-ctl border border-line/80 bg-panel/30 text-xs font-bold shadow-inner">
              <div
                className="num flex items-center justify-center bg-go/30 text-go-ink transition-[width] duration-700"
                style={{ width: `${(plan.green_ns / total) * 100}%` }}
                title={`Pha 1 (Bắc–Nam): ${plan.green_ns.toFixed(0)}s`}
              >
                Bắc–Nam {plan.green_ns.toFixed(0)}s ({((plan.green_ns / total) * 100).toFixed(0)}%)
              </div>
              <div
                className="num flex items-center justify-center border-l border-line bg-auto/30 text-auto-ink transition-[width] duration-700"
                style={{ width: `${(plan.green_ew / total) * 100}%` }}
                title={`Pha 2 (Đông–Tây): ${plan.green_ew.toFixed(0)}s`}
              >
                Đông–Tây {plan.green_ew.toFixed(0)}s ({((plan.green_ew / total) * 100).toFixed(0)}%)
              </div>
            </div>
            {active && (
              <div className="num mt-1.5 flex items-center justify-between text-2xs font-medium text-ink-mute">
                <span>Đang thực thi tại nút:</span>
                <span className="font-bold text-ink">
                  B–N {active.green_ns.toFixed(0)}s / Đ–T {active.green_ew.toFixed(0)}s ({active.source === "ADAPTIVE" ? "AI Webster" : "Kế hoạch cố định"})
                </span>
              </div>
            )}
          </div>

          {/* Lưới nhu cầu */}
          <div className="grid grid-cols-2 gap-2.5 rounded-ctl border border-line/70 bg-panel/20 p-2.5">
            {[
              ["Nhu cầu Bắc–Nam", `${plan.demand_ns_pcu_h.toLocaleString("vi-VN")} PCU/h`, `y = ${plan.flow_ratio_ns.toFixed(2)}`],
              ["Nhu cầu Đông–Tây", `${plan.demand_ew_pcu_h.toLocaleString("vi-VN")} PCU/h`, `y = ${plan.flow_ratio_ew.toFixed(2)}`],
              ["Hàng đợi tới hạn B–N", `${plan.queue_ns_m.toFixed(0)} m`, `hướng ${plan.critical_ns === "NORTH" ? "Bắc" : "Nam"}`],
              ["Hàng đợi tới hạn Đ–T", `${plan.queue_ew_m.toFixed(0)} m`, `hướng ${plan.critical_ew === "EAST" ? "Đông" : "Tây"}`],
            ].map(([k, v, s]) => (
              <div key={k} className="min-w-0">
                <div className="text-2xs font-semibold text-ink-mute uppercase tracking-wider">{k}</div>
                <div className="num mt-0.5 text-xs font-bold text-ink">
                  {v} <span className="font-normal text-ink-mute">({s})</span>
                </div>
              </div>
            ))}
          </div>

          {/* Tỷ số lưu lượng Y */}
          <div className="flex items-center gap-2.5 text-2xs">
            <span className="font-semibold text-ink-mute uppercase tracking-wider">Tổng tỷ số Y:</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-carbon ring-1 ring-line/50">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(100, plan.flow_ratio_total * 100)}%`,
                  background: plan.saturated ? "#EF4444" : plan.flow_ratio_total > 0.7 ? "#F59E0B" : "#10B981",
                }}
              />
            </div>
            <span className="num font-bold text-ink">{plan.flow_ratio_total.toFixed(2)}</span>
            <span className="text-ink-mute">{plan.saturated ? "(Quá bão hoà)" : plan.flow_ratio_total > 0.7 ? "(Tải cao)" : "(Tải vừa)"}</span>
          </div>

          {/* Diễn giải lý do của AI */}
          <div className="rounded-ctl border-l-3 border-auto bg-auto/10 p-2.5 text-xs leading-relaxed text-ink-dim">
            <span className="font-bold text-ink">Lý do thuật toán: </span>
            {plan.reason}
          </div>
        </div>
      )}
    </Panel>
  );
}
