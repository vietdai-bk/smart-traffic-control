"""Adaptive Traffic Signal Control — Webster-based Dynamic Allocation (US09-T02/T03).

    y_i = q_i / s            (q_i: nhu cầu PCU/h của hướng tới hạn trên trục i; s: lưu lượng bão hoà)
    C₀  = (1.5·L + 5)/(1 − Y) (L: thời gian tổn thất = Σ vàng + toàn đỏ)
    g_i = (C₀ − L)·y_i / Y    (kẹp trong [min_green, max_green], làm mượt ±max_step mỗi lần cập nhật)

Nhu cầu q_i lấy max(lưu lượng đến đo bằng tracker, hàng đợi hiện tại quy về PCU/h theo chu kỳ trước) để thuật toán
phản ứng nhanh khi có hàng đợi dồn ứ.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.control_engine.fsm import GreenPlan
from app.control_engine.safety import TimingConstraints

AXES = {"NS": ("NORTH", "SOUTH"), "EW": ("EAST", "WEST")}
AXIS_LABEL = {"NS": "Bắc–Nam", "EW": "Đông–Tây"}


@dataclass
class ApproachDemand:
    direction: str
    arrival_pcu_h: float
    queue_pcu: float
    queue_m: float
    density: float


@dataclass
class AdaptiveResult:
    plan: GreenPlan
    cycle_s: float
    webster_cycle_s: float
    flow_ratio_ns: float
    flow_ratio_ew: float
    flow_ratio_total: float
    demand_ns_pcu_h: float
    demand_ew_pcu_h: float
    queue_ns_m: float
    queue_ew_m: float
    critical_ns: str
    critical_ew: str
    saturated: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "green_ns": round(self.plan.green_ns, 1),
            "green_ew": round(self.plan.green_ew, 1),
            "cycle_s": round(self.cycle_s, 1),
            "webster_cycle_s": round(self.webster_cycle_s, 1),
            "flow_ratio_ns": round(self.flow_ratio_ns, 3),
            "flow_ratio_ew": round(self.flow_ratio_ew, 3),
            "flow_ratio_total": round(self.flow_ratio_total, 3),
            "demand_ns_pcu_h": round(self.demand_ns_pcu_h, 0),
            "demand_ew_pcu_h": round(self.demand_ew_pcu_h, 0),
            "queue_ns_m": round(self.queue_ns_m, 1),
            "queue_ew_m": round(self.queue_ew_m, 1),
            "critical_ns": self.critical_ns,
            "critical_ew": self.critical_ew,
            "saturated": self.saturated,
            "reason": self.reason,
        }


class AdaptivePlanner:
    def __init__(self, max_step_s: float = 10.0) -> None:
        self.max_step_s = max_step_s

    def compute(
        self,
        approaches: dict[str, ApproachDemand],
        timing: TimingConstraints,
        lanes: int,
        saturation_flow: float,
        prev: GreenPlan,
        weights: tuple[float, float] = (1.0, 1.0),
        weight_note: str = "",
    ) -> AdaptiveResult:
        """weights = (w_NS, w_EW) do LLM Supervisor đặt (tầng 3). Trọng số chỉ thay đổi CÁCH CHIA thời gian xanh;
        chu kỳ Webster, min/max xanh, biên độ thay đổi và bộ khoá an toàn vẫn được áp đầy đủ như bình thường."""
        w_ns = min(max(float(weights[0]), 0.5), 2.0)
        w_ew = min(max(float(weights[1]), 0.5), 2.0)
        t = timing.sanitized()
        lost = t.lost_time
        sat = max(1.0, saturation_flow * max(1, lanes))
        prev_cycle = prev.cycle_s or (prev.green_ns + prev.green_ew + lost)

        def effective(a: ApproachDemand) -> float:
            queue_flow = a.queue_pcu * 3600.0 / max(prev_cycle, 1.0)
            return max(a.arrival_pcu_h, queue_flow)

        crit: dict[str, ApproachDemand] = {}
        q: dict[str, float] = {}
        for axis, dirs in AXES.items():
            cands = [approaches[d] for d in dirs if d in approaches]
            if not cands:
                crit[axis] = ApproachDemand(dirs[0], 0, 0, 0, 0)
                q[axis] = 0.0
                continue
            best = max(cands, key=effective)
            crit[axis] = best
            q[axis] = effective(best)

        y_ns = min(q["NS"] / sat, 0.95)
        y_ew = min(q["EW"] / sat, 0.95)
        if y_ns + y_ew < 0.05:
            y_ns = y_ew = 0.025
        y_total = y_ns + y_ew
        saturated = y_total >= 0.85
        y_capped = min(y_total, 0.9)

        webster = (1.5 * lost + 5.0) / (1.0 - y_capped)
        cycle = min(max(webster, t.cycle_min), t.cycle_max)
        effective_green = cycle - lost

        wy_ns, wy_ew = y_ns * w_ns, y_ew * w_ew
        targets = {
            "NS": effective_green * wy_ns / (wy_ns + wy_ew),
            "EW": effective_green * wy_ew / (wy_ns + wy_ew),
        }
        prev_g = {"NS": prev.green_ns, "EW": prev.green_ew}
        greens: dict[str, float] = {}
        for axis in AXES:
            target = min(max(targets[axis], t.min_green), t.max_green)
            step = max(-self.max_step_s, min(self.max_step_s, target - prev_g[axis]))
            greens[axis] = round(min(max(prev_g[axis] + step, t.min_green), t.max_green))
        final_cycle = greens["NS"] + greens["EW"] + lost

        reason = self._explain(q, crit, greens, prev_g, webster, y_total, saturated)
        if abs(w_ns - 1.0) > 1e-3 or abs(w_ew - 1.0) > 1e-3:
            reason += f" Trọng số LLM Supervisor B–N ×{w_ns:.2f} / Đ–T ×{w_ew:.2f}{(' — ' + weight_note) if weight_note else ''}."
        plan = GreenPlan(
            green_ns=greens["NS"], green_ew=greens["EW"], source="ADAPTIVE", reason=reason, cycle_s=final_cycle
        )
        return AdaptiveResult(
            plan=plan,
            cycle_s=final_cycle,
            webster_cycle_s=webster,
            flow_ratio_ns=y_ns,
            flow_ratio_ew=y_ew,
            flow_ratio_total=y_total,
            demand_ns_pcu_h=q["NS"],
            demand_ew_pcu_h=q["EW"],
            queue_ns_m=max((approaches[d].queue_m for d in AXES["NS"] if d in approaches), default=0.0),
            queue_ew_m=max((approaches[d].queue_m for d in AXES["EW"] if d in approaches), default=0.0),
            critical_ns=crit["NS"].direction,
            critical_ew=crit["EW"].direction,
            saturated=saturated,
            reason=reason,
        )

    @staticmethod
    def _explain(q, crit, greens, prev_g, webster, y_total, saturated) -> str:
        ns, ew = q["NS"], q["EW"]
        head = (
            f"Nhu cầu Bắc–Nam {ns:,.0f} PCU/h (hàng đợi {crit['NS'].queue_m:.0f} m) · "
            f"Đông–Tây {ew:,.0f} PCU/h (hàng đợi {crit['EW'].queue_m:.0f} m)."
        )
        hi, lo = ("NS", "EW") if ns >= ew else ("EW", "NS")
        diff = (q[hi] - q[lo]) / max(q[lo], 1.0) * 100
        if diff < 10:
            body = "Hai trục cân bằng → chia thời gian xanh gần đều."
        else:
            body = f"Trục {AXIS_LABEL[hi]} cao hơn {min(diff, 999):.0f}% → ưu tiên xanh cho {AXIS_LABEL[hi]}."
        changes = []
        for axis in ("NS", "EW"):
            delta = greens[axis] - prev_g[axis]
            if abs(delta) >= 1:
                changes.append(f"Xanh {AXIS_LABEL[axis]} {prev_g[axis]:.0f}→{greens[axis]:.0f}s ({delta:+.0f}s)")
            else:
                changes.append(f"Xanh {AXIS_LABEL[axis]} giữ {greens[axis]:.0f}s")
        tail = f"{'; '.join(changes)}. Chu kỳ Webster {webster:.0f}s (Y={y_total:.2f})."
        if saturated:
            tail += " Cảnh báo: nút giao gần bão hoà (Y ≥ 0.85)."
        return f"{head} {body} {tail}"
