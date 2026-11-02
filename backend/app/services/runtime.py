"""Intersection Runtime — điều phối thời gian thực một nút giao.

Mỗi tick (100 ms): mô phỏng → camera → nhận diện → tracking → đếm → mật độ → FSM tín hiệu → adapter.
Mỗi giây: heartbeat thiết bị, fail-safe, thuật toán adaptive, cảnh báo ùn tắc, thống kê.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.control_engine.adapter import SimulatedSignalController
from app.control_engine.adaptive import AdaptivePlanner, AdaptiveResult, ApproachDemand
from app.control_engine.fsm import CommandResult, CycleRecord, GreenPlan, SignalControllerFSM, TransitionEvent
from app.control_engine.phases import DIRECTION_LABELS, DIRECTIONS, PHASES, Interval, Mode
from app.control_engine.safety import TimingConstraints
from app.core.audit import audit
from app.core.config import settings
from app.core.events import bus
from app.db.session import session_scope
from app.llm.supervisor import SupervisorState
from app.models.signal import SignalCommand, SignalCycle
from app.services.alert_service import (
    CongestionMonitor,
    create_alert,
    create_incident,
    recover_incident,
    resolve_alert,
)
from app.services.stats import StatsAccumulator, load_today_totals
from app.vision_engine.counter import DirectionalCounter
from app.vision_engine.density import LEVEL_LABELS, DensityAnalyzer
from app.vision_engine.detector import CLASSES, SyntheticDetector, VisionAlgorithmError
from app.vision_engine.geometry import CameraCalibration, polygon_y_range
from app.vision_engine.simulator import TrafficSimulator
from app.vision_engine.stream_manager import DEGRADED, OFFLINE, ONLINE, CameraInfo, CameraStream
from app.vision_engine.tracker import CentroidTracker

log = logging.getLogger("stcs.runtime")
CLS_INDEX = {c: i for i, c in enumerate(CLASSES)}


@dataclass
class CameraConfig:
    id: int
    code: str
    name: str
    direction: str
    source_type: str
    stream_url: str
    resolution: str
    target_fps: int
    roi: list
    counting_line: list
    roi_length_m: float
    density_medium: float | None
    density_high: float | None
    is_enabled: bool


@dataclass
class IntersectionConfig:
    id: int
    code: str
    name: str
    lanes: int
    default_mode: str
    fixed_green_ns: int
    fixed_green_ew: int
    yellow_s: int
    all_red_s: int
    min_green_s: int
    max_green_s: int
    cycle_min_s: int
    cycle_max_s: int
    saturation_flow: int
    failsafe_strategy: str
    density_medium: float
    density_high: float
    alert_hold_s: int
    base_demand_ns: int
    base_demand_ew: int
    controller_endpoint: str
    controller_model: str
    cameras: list[CameraConfig] = field(default_factory=list)

    @classmethod
    def from_model(cls, m) -> "IntersectionConfig":
        return cls(
            id=m.id, code=m.code, name=m.name, lanes=m.lanes_per_approach, default_mode=m.default_mode,
            fixed_green_ns=m.fixed_green_ns, fixed_green_ew=m.fixed_green_ew, yellow_s=m.yellow_s,
            all_red_s=m.all_red_s, min_green_s=m.min_green_s, max_green_s=m.max_green_s,
            cycle_min_s=m.cycle_min_s, cycle_max_s=m.cycle_max_s, saturation_flow=m.saturation_flow,
            failsafe_strategy=m.failsafe_strategy, density_medium=m.density_medium, density_high=m.density_high,
            alert_hold_s=m.alert_hold_s, base_demand_ns=m.base_demand_ns, base_demand_ew=m.base_demand_ew,
            controller_endpoint=m.controller_endpoint, controller_model=m.controller_model,
            cameras=[
                CameraConfig(
                    id=c.id, code=c.code, name=c.name, direction=c.direction, source_type=c.source_type,
                    stream_url=c.stream_url, resolution=c.resolution, target_fps=c.target_fps,
                    roi=list(c.roi or []), counting_line=list(c.counting_line or []), roi_length_m=c.roi_length_m,
                    density_medium=c.density_medium, density_high=c.density_high, is_enabled=c.is_enabled,
                )
                for c in m.cameras
            ],
        )

    def timing(self) -> TimingConstraints:
        return TimingConstraints(
            min_green=self.min_green_s, max_green=self.max_green_s, yellow=self.yellow_s,
            all_red=self.all_red_s, cycle_min=self.cycle_min_s, cycle_max=self.cycle_max_s,
        )

    def fixed_plan(self) -> GreenPlan:
        cycle = self.fixed_green_ns + self.fixed_green_ew + 2 * (self.yellow_s + self.all_red_s)
        return GreenPlan(self.fixed_green_ns, self.fixed_green_ew, source="FIXED",
                         reason="Kế hoạch chu kỳ cố định chuẩn của nút giao", cycle_s=cycle)


class DirectionPipeline:
    """Pipeline thị giác cho 1 hướng: camera → detector → tracker → counter → density."""

    def __init__(self, direction: str, cam: CameraConfig | None, calib: CameraCalibration, lanes: int,
                 frame_hz: float, seed: int) -> None:
        self.direction = direction
        self.cfg = cam
        self.calib = calib
        self.camera: CameraStream | None = None
        self.roi = (cam.roi if cam and len(cam.roi) >= 3 else None) or calib.roi_polygon(cam.roi_length_m if cam else 60)
        self.line = (cam.counting_line if cam and len(cam.counting_line) == 2 else None) or calib.counting_line()
        roi_len = cam.roi_length_m if cam else 60.0
        if cam is not None:
            self.camera = CameraStream(
                CameraInfo(cam.id, cam.code, cam.name, direction, cam.source_type, cam.stream_url, cam.resolution,
                           cam.target_fps, cam.is_enabled),
                frame_hz,
            )
        self.detector = SyntheticDetector(seed)
        self.tracker = CentroidTracker(calib)
        roi_top, _ = polygon_y_range(self.roi)
        line_y = (self.line[0][1] + self.line[1][1]) / 2
        self.counter = DirectionalCounter(line_y, roi_top, roi_len)
        self.analyzer = DensityAnalyzer(roi_len, lanes)
        self.objects: list[dict] = []
        self.tracks = []
        self.last_frame_ts: float | None = None
        self.offline_since: float | None = None
        self.level = "LOW"

    def thresholds(self, cfg: IntersectionConfig) -> tuple[float, float]:
        med = self.cfg.density_medium if self.cfg and self.cfg.density_medium is not None else cfg.density_medium
        high = self.cfg.density_high if self.cfg and self.cfg.density_high is not None else cfg.density_high
        return float(med), float(high)

    def process(self, sim_objects_fn, now: float, degraded_vision: bool) -> list:
        cam = self.camera
        if cam is None:
            return []
        if cam.info.source_type == "SIMULATED":
            objs = cam.read_simulated(sim_objects_fn, now)
            if objs is None:
                return []
            self.objects = objs
            dets = self.detector.detect(objs, degraded=cam.fault == "DEGRADE" or degraded_vision)
        else:
            dets = cam.read_real(now)
            if dets is None:
                return []
            self.objects = []
        dt = (now - self.last_frame_ts) if self.last_frame_ts else 0.1
        dt = min(max(dt, 0.02), 1.0)
        self.last_frame_ts = now
        self.tracks = self.tracker.update(dets, dt)
        events = self.counter.update(self.tracks, dt, now)
        self.analyzer.update(self.tracks, dt)
        return events

    def mark_no_frame(self, now: float) -> None:
        """Mất khung hình kéo dài → xoá track để không đếm sai khi kết nối lại."""
        if self.last_frame_ts and now - self.last_frame_ts > 1.5:
            self.tracker.reset()
            self.tracks = []
            self.objects = []

    def frame_payload(self) -> dict:
        cam = self.camera
        return {
            "status": cam.status if cam else "NO_CAMERA",
            "frame_no": cam.frame_no if cam else 0,
            "objects": [
                [round(o["box"][0], 4), round(o["box"][1], 4), round(o["box"][2], 4), round(o["box"][3], 4),
                 CLS_INDEX[o["cls"]], o["color"], int(o["brake"]), o["id"]]
                for o in self.objects
            ] if cam and cam.connected else [],
            "tracks": [
                [t.id, round(t.box[0], 4), round(t.box[1], 4), round(t.box[2], 4), round(t.box[3], 4),
                 CLS_INDEX.get(t.cls, 0), round(t.conf, 2), int(t.stopped)]
                for t in self.tracks
            ] if cam and cam.connected else [],
        }

    def close(self) -> None:
        if self.camera:
            self.camera.close()


class IntersectionRuntime:
    def __init__(self, cfg: IntersectionConfig) -> None:
        self.cfg = cfg
        self.id = cfg.id
        self.started_at = time.time()
        self.sim = TrafficSimulator(cfg.lanes, cfg.base_demand_ns, cfg.base_demand_ew, seed=cfg.id * 7919)
        self.adapter = SimulatedSignalController(cfg.controller_endpoint, cfg.controller_model, seed=cfg.id)
        self.planner = AdaptivePlanner()
        self.latest_plan: AdaptiveResult | None = None
        self.plan_applied = False
        self.monitor = CongestionMonitor(cfg.id, cfg.name)
        self.stats = StatsAccumulator(cfg.id, settings.stats_bucket_minutes)
        self.pipelines: dict[str, DirectionPipeline] = {}
        self._build_pipelines()
        self._load_totals()
        mode = Mode(cfg.default_mode) if cfg.default_mode in ("AUTO", "FIXED_TIME", "MANUAL") else Mode.AUTO
        self.fsm = SignalControllerFSM(
            cfg.timing(), cfg.fixed_plan(), mode=mode, failsafe_strategy=cfg.failsafe_strategy,
            on_transition=self._on_transition, on_cycle=self._on_cycle, on_violation=self._on_violation,
        )
        self.controller_online = True
        self.controller_incident: int | None = None
        self.camera_incidents: dict[int, tuple[str, int]] = {}  # camera_id -> (status, incident_id)
        self.vision_fault = False
        self.vision_incident: int | None = None
        self.failsafe_alert: int | None = None
        self.last_ack: dict | None = None
        self._cycle_events = 0
        self._cycle_wait_sum = 0.0
        self._cycle_wait_n = 0
        self._t1 = 0.0
        self._t_snap = 0.0
        self._t_frame = 0.0
        self._day = datetime.now().date()
        self.tick_ms = 0.0
        self.recent_events: list[dict] = []
        mode = settings.llm_mode if settings.llm_mode in ("OFF", "ADVISORY", "AUTONOMOUS") else "ADVISORY"
        self.llm = SupervisorState(mode=mode)

    # ------------------------------------------------------------------ setup
    def _build_pipelines(self) -> None:
        for p in self.pipelines.values():
            p.close()
        by_dir = {c.direction: c for c in self.cfg.cameras}
        self.pipelines = {
            d: DirectionPipeline(d, by_dir.get(d), self.sim.calib, self.cfg.lanes, settings.frame_hz,
                                 seed=self.id * 100 + i)
            for i, d in enumerate(DIRECTIONS)
        }

    def _load_totals(self) -> None:
        try:
            totals = load_today_totals(self.id)
        except Exception:  # pragma: no cover
            log.exception("Không nạp được tổng lưu lượng hôm nay")
            return
        for d, p in self.pipelines.items():
            p.counter.totals = dict(totals.get(d, p.counter.totals))

    def apply_config(self, cfg: IntersectionConfig) -> None:
        old = self.cfg
        self.cfg = cfg
        self.fsm.update_config(cfg.timing(), cfg.fixed_plan(), cfg.failsafe_strategy)
        self.sim.set_demand(cfg.lanes, cfg.base_demand_ns, cfg.base_demand_ew)
        cams_changed = [(c.id, c.direction, c.source_type, c.stream_url, c.roi, c.counting_line, c.roi_length_m,
                         c.is_enabled, c.resolution, c.target_fps) for c in old.cameras] != \
                       [(c.id, c.direction, c.source_type, c.stream_url, c.roi, c.counting_line, c.roi_length_m,
                         c.is_enabled, c.resolution, c.target_fps) for c in cfg.cameras]
        if cams_changed or old.lanes != cfg.lanes:
            totals = {d: p.counter.totals for d, p in self.pipelines.items()}
            faults = {p.camera.info.id: p.camera.fault for p in self.pipelines.values() if p.camera}
            self._build_pipelines()
            for d, p in self.pipelines.items():
                p.counter.totals = totals.get(d, p.counter.totals)
                if p.camera and p.camera.info.id in faults:
                    p.camera.inject_fault(faults[p.camera.info.id])
        else:
            by_dir = {c.direction: c for c in cfg.cameras}
            for d, p in self.pipelines.items():
                if d in by_dir:
                    p.cfg = by_dir[d]
                    if p.camera:
                        p.camera.info.name = by_dir[d].name
                        p.camera.info.code = by_dir[d].code

    def close(self) -> None:
        for p in self.pipelines.values():
            p.close()
        self.stats.flush()

    # ------------------------------------------------------------------ FSM callbacks
    def _on_transition(self, ev: TransitionEvent) -> None:
        ack = self.adapter.apply_state(ev.heads, self.fsm.mode.value)
        self.last_ack = ack.to_dict()
        event = {
            "ts": time.time(), "state": ev.new_state, "interval": ev.new_interval.value,
            "phase_id": ev.phase_id, "cause": ev.cause, "ack": self.last_ack,
        }
        self.recent_events = (self.recent_events + [event])[-30:]
        bus.publish({"type": "signal_event", "data": event}, self.id, droppable=True)
        if ev.new_interval == Interval.GREEN:
            mode = self.fsm.mode
            if mode == Mode.AUTO:
                source, by = "AUTO", "AI_ADAPTIVE"
            elif mode == Mode.MANUAL:
                source, by = "MANUAL", self.fsm.scheduled_by or "operator"
            else:
                source, by = "SYSTEM", "FIXED_PLAN" if mode == Mode.FIXED_TIME else "FAILSAFE"
            plan = self.fsm.active_plan
            reason = ev.cause
            if mode == Mode.AUTO and plan.reason:
                reason = f"{ev.cause}. {plan.reason}"
            self._log_command(
                "PHASE_CHANGE", {"green_s": round(self.fsm.green_target, 1)}, source, by, ev.prev_state,
                ev.new_state, reason, "EXECUTED", ack.ok, ack.latency_ms,
                f"Bật xanh {PHASES[ev.phase_id].name} trong {self.fsm.green_target:.0f}s"
                if mode != Mode.MANUAL else f"Bật xanh {PHASES[ev.phase_id].name} (giữ thủ công)",
            )

    def _on_cycle(self, rec: CycleRecord) -> None:
        plan = self.latest_plan
        avg_wait = self._cycle_wait_sum / self._cycle_wait_n if self._cycle_wait_n else 0.0
        try:
            with session_scope() as db:
                db.add(
                    SignalCycle(
                        intersection_id=self.id,
                        started_at=datetime.fromtimestamp(rec.started_at, timezone.utc),
                        ended_at=datetime.fromtimestamp(rec.ended_at, timezone.utc),
                        mode=rec.mode, cycle_length_s=rec.cycle_length_s, green_ns_s=rec.green_ns_s,
                        green_ew_s=rec.green_ew_s, yellow_s=rec.yellow_s, all_red_s=rec.all_red_s,
                        demand_ns_pcu=plan.demand_ns_pcu_h if plan else 0.0,
                        demand_ew_pcu=plan.demand_ew_pcu_h if plan else 0.0,
                        queue_ns_m=plan.queue_ns_m if plan else 0.0,
                        queue_ew_m=plan.queue_ew_m if plan else 0.0,
                        avg_wait_s=round(avg_wait, 1), throughput=self._cycle_events,
                        plan_reason=rec.plan_reason[:1000] if rec.plan_reason else None,
                    )
                )
        except Exception:  # pragma: no cover
            log.exception("Không ghi được chu kỳ đèn")
        self._cycle_events = 0
        self._cycle_wait_sum = 0.0
        self._cycle_wait_n = 0

    def _on_violation(self, reason: str) -> None:
        create_alert(self.id, "SAFETY", "CRITICAL", f"VI PHẠM KHOÁ AN TOÀN — {self.cfg.name}",
                     f"Bộ khoá an toàn đã chặn trạng thái nguy hiểm và ép toàn đỏ: {reason}")

    def _log_command(self, command: str, params: dict, source: str, by: str, from_state: str, to_state: str,
                     reason: str | None, status: str, ack: bool, latency: float | None, message: str | None) -> None:
        try:
            with session_scope() as db:
                db.add(
                    SignalCommand(
                        intersection_id=self.id, command=command, params=params, source=source, issued_by=by,
                        mode=self.fsm.mode.value, from_state=from_state, to_state=to_state,
                        reason=(reason or "")[:1000], status=status, ack=ack, ack_latency_ms=latency, message=message,
                    )
                )
        except Exception:  # pragma: no cover
            log.exception("Không ghi được lệnh điều khiển")

    # ------------------------------------------------------------------ tick
    def tick(self, dt: float, now: float) -> None:
        t0 = time.perf_counter()
        heads = self.fsm.heads()
        self.sim.step(dt, heads)
        for d, p in self.pipelines.items():
            approach = self.sim.approaches[d]
            try:
                events = p.process(approach.visible_objects, now, degraded_vision=False)
            except VisionAlgorithmError as exc:
                self._vision_error(str(exc))
                events = []
            if p.camera and (not p.camera.connected):
                p.mark_no_frame(now)
            if events:
                self.stats.add_events(d, events)
                self._cycle_events += len(events)
                for e in events:
                    self._cycle_wait_sum += e.wait_s
                    self._cycle_wait_n += 1
        self.fsm.tick(dt)
        self.adapter.poll_heartbeat()

        self._t1 += dt
        if self._t1 >= 1.0:
            self._t1 = 0.0
            self._one_hz(now)

        self.tick_ms = 0.9 * self.tick_ms + 0.1 * (time.perf_counter() - t0) * 1000.0
        if bus.has_listeners(self.id):
            self._t_frame += dt
            self._t_snap += dt
            if self._t_frame >= 1.0 / settings.frame_hz - 1e-3:
                self._t_frame = 0.0
                bus.publish(self.frames_message(), self.id, droppable=True)
            if self._t_snap >= 1.0 / settings.snapshot_hz - 1e-3:
                self._t_snap = 0.0
                bus.publish(self.snapshot_message(), self.id, droppable=True)

    def _one_hz(self, now: float) -> None:
        today = datetime.now().date()
        if today != self._day:
            self._day = today
            for p in self.pipelines.values():
                p.counter.totals = {k: 0 for k in p.counter.totals}

        # 1) Heartbeat camera (US12-T01/T02)
        any_offline = []
        for d, p in self.pipelines.items():
            cam = p.camera
            if cam is None:
                continue
            status = cam.evaluate(now)
            self._camera_incident(cam, status)
            if status == OFFLINE and cam.info.is_enabled:
                any_offline.append(cam.info.code)

        # 2) Heartbeat bộ điều khiển
        hb_age = now - self.adapter.last_heartbeat_at
        if self.controller_online and hb_age > settings.controller_timeout_s:
            self.controller_online = False
            self.controller_incident = create_incident(
                self.id, "CONTROLLER", None, f"TSC-{self.cfg.code}", "CONNECTION_LOST", "CRITICAL",
                f"Mất heartbeat bộ điều khiển đèn {self.cfg.controller_endpoint} ({hb_age:.1f}s)",
            )
            self.enter_failsafe("Mất kết nối bộ điều khiển đèn — bộ điều khiển hiện trường chuyển chớp vàng",
                                emergency_flash=True)
        elif not self.controller_online and hb_age <= settings.controller_timeout_s:
            self.controller_online = True
            if self.controller_incident:
                recover_incident(self.controller_incident)
                self.controller_incident = None

        # 3) Fail-safe khi đang AUTO (NFR07, US10-T04)
        if self.fsm.mode == Mode.AUTO:
            if any_offline:
                self.enter_failsafe(f"Mất kết nối camera {', '.join(any_offline)} khi đang điều khiển tự động")
            elif self.vision_fault:
                self.enter_failsafe("Lỗi thuật toán phân tích hình ảnh khi đang điều khiển tự động")

        # 4) Thuật toán adaptive (US09)
        demands = {}
        uptime = now - self.started_at
        for d, p in self.pipelines.items():
            res = p.analyzer.last
            if p.camera is None or res is None:
                continue
            demands[d] = ApproachDemand(
                d, p.counter.arrival_pcu_h(180, now, uptime), res.queue_pcu, res.queue_m, res.density_smoothed
            )
        if demands:
            try:
                weights = self.llm.active_weights(now)
                self.latest_plan = self.planner.compute(
                    demands, self.fsm.timing, self.cfg.lanes, self.cfg.saturation_flow, self.fsm.active_plan,
                    weights=weights, weight_note=self.llm.note(),
                )
                self.llm.sample(now, self.latest_plan.demand_ns_pcu_h, self.latest_plan.demand_ew_pcu_h)
                sensing_ok = not any_offline and not self.vision_fault
                self.plan_applied = sensing_ok and self.fsm.propose_plan(self.latest_plan.plan)
            except Exception:  # pragma: no cover
                log.exception("Thuật toán adaptive lỗi")

        # 5) Cảnh báo ùn tắc + thống kê (US11, US13)
        for d, p in self.pipelines.items():
            res = p.analyzer.last
            if p.camera is None or res is None or (p.camera.status == OFFLINE):
                continue
            med, high = p.thresholds(self.cfg)
            p.level = self.monitor.update(d, res.density_smoothed, res.queue_m, med, high, self.cfg.alert_hold_s, now)
            self.stats.sample(d, res.density_smoothed, res.queue_m)
        self.stats.sample_mode(self.fsm.mode.value)
        try:
            self.stats.maybe_flush()
        except Exception:  # pragma: no cover
            log.exception("Không ghi được thống kê")

    # ------------------------------------------------------------------ device / failsafe
    def _camera_incident(self, cam: CameraStream, status: str) -> None:
        prev = self.camera_incidents.get(cam.info.id)
        prev_status = prev[0] if prev else ONLINE
        if status == prev_status:
            return
        if prev:
            recover_incident(prev[1])
            self.camera_incidents.pop(cam.info.id, None)
        label = DIRECTION_LABELS.get(cam.info.direction, cam.info.direction)
        if status == OFFLINE and cam.info.is_enabled:
            iid = create_incident(self.id, "CAMERA", cam.info.id, cam.info.code, "CONNECTION_LOST", "CRITICAL",
                                  f"Camera hướng {label} mất kết nối: {cam.error or 'không có khung hình'}")
            self.camera_incidents[cam.info.id] = (OFFLINE, iid)
        elif status == DEGRADED:
            iid = create_incident(self.id, "CAMERA", cam.info.id, cam.info.code, "DEGRADED", "WARNING",
                                  f"Camera hướng {label} suy giảm chất lượng (FPS {cam.fps:.1f}, mất gói tin)")
            self.camera_incidents[cam.info.id] = (DEGRADED, iid)

    def _vision_error(self, msg: str) -> None:
        if self.vision_incident is None:
            self.vision_incident = create_incident(self.id, "VISION", None, f"AI-{self.cfg.code}",
                                                   "ALGORITHM_ERROR", "CRITICAL", msg)
        self.vision_fault = True

    def set_vision_fault(self, on: bool) -> None:
        for p in self.pipelines.values():
            p.detector.fault = on
        if not on:
            self.vision_fault = False
            if self.vision_incident:
                recover_incident(self.vision_incident)
                self.vision_incident = None

    def enter_failsafe(self, reason: str, emergency_flash: bool = False) -> None:
        if self.fsm.mode == Mode.FAILSAFE:
            if emergency_flash and self.fsm.interval != Interval.FLASHING:
                self.fsm.enter_failsafe(reason, emergency_flash=True)
            return
        before = self.fsm.state
        # Tầng 3 bị vô hiệu khi FAILSAFE: bỏ chiến lược & đề xuất LLM đang chờ (NFR07)
        self.llm.reset("FAILSAFE — chiến lược LLM bị huỷ")
        self.llm.pending = None
        res = self.fsm.enter_failsafe(reason, emergency_flash=emergency_flash)
        self._log_command("ENTER_FAILSAFE", {"emergency_flash": emergency_flash}, "SYSTEM", "FAILSAFE_GUARD",
                          before, self.fsm.state, reason, "EXECUTED", True, None, res.message)
        how = "CHỚP VÀNG" if (emergency_flash or self.fsm.failsafe_strategy == "FLASHING_YELLOW") else "CHU KỲ CỐ ĐỊNH"
        self.failsafe_alert = create_alert(
            self.id, "FAILSAFE", "CRITICAL", f"FAILSAFE ({how}) — {self.cfg.name}",
            f"{reason}. Điều khiển tự động đã bị khoá; cần khắc phục sự cố và khôi phục thủ công.",
        )
        audit(None, "SIGNAL_CONTROL", "ENTER_FAILSAFE", f"{self.cfg.name}: {reason}", username="system",
              target=self.cfg.code, details={"strategy": how}, result="FAILURE", intersection_id=self.id)
        bus.publish({"type": "failsafe", "data": {"reason": reason, "strategy": how}}, self.id)

    def health_issues(self) -> list[str]:
        issues = []
        for p in self.pipelines.values():
            if p.camera and p.camera.info.is_enabled and p.camera.status == OFFLINE:
                issues.append(f"Camera {p.camera.info.code} đang OFFLINE")
        if not self.controller_online or self.adapter.fault:
            issues.append("Bộ điều khiển đèn mất kết nối")
        if self.vision_fault or any(p.detector.fault for p in self.pipelines.values()):
            issues.append("Thuật toán phân tích hình ảnh đang lỗi")
        return issues

    # ------------------------------------------------------------------ commands
    def execute(self, command: str, params: dict, username: str) -> tuple[CommandResult, dict | None]:
        if self.adapter.fault or not self.controller_online:
            before = self.fsm.state
            res = CommandResult("REJECTED", "Bộ điều khiển đèn mất kết nối — không thể gửi lệnh (đang chớp vàng tại hiện trường)",
                                before, before)
            self._log_command(command, params, "MANUAL", username, before, before, params.get("reason"),
                              res.status, False, None, res.message)
            return res, None
        seq_before = self.adapter.last_ack.seq if self.adapter.last_ack else 0
        fsm = self.fsm
        if command == "NEXT_PHASE":
            res = fsm.next_phase(username)
        elif command == "GOTO_PHASE":
            res = fsm.goto_phase(int(params.get("phase_id", 1)), username)
        elif command == "HOLD_PHASE":
            dur = params.get("duration_s")
            res = fsm.hold_phase_cmd(int(params.get("phase_id", fsm.phase_id)), float(dur) if dur else None, username)
        elif command == "RELEASE_HOLD":
            res = fsm.release_hold(username)
        elif command == "EXTEND_GREEN":
            res = fsm.extend_green(float(params.get("seconds", 10)), username)
        elif command == "SET_TIMING":
            res = fsm.set_fixed_timing(float(params.get("green_ns", 30)), float(params.get("green_ew", 30)), username)
        elif command == "FLASHING_YELLOW":
            res = fsm.set_flashing(bool(params.get("on", True)), username)
        else:
            before = fsm.state
            res = CommandResult("REJECTED", f"Lệnh không hỗ trợ: {command}", before, before)
        # ACK: nếu lệnh gây chuyển trạng thái → ACK của trạng thái mới; nếu không → ACK nhận lệnh
        ack = self.adapter.last_ack if (self.adapter.last_ack and self.adapter.last_ack.seq != seq_before) else None
        if ack is None and res.ok:
            ack = self.adapter.ping()
        ack_d = ack.to_dict() if ack else None
        self._log_command(command, params, "MANUAL", username, res.from_state, res.to_state, params.get("reason"),
                          res.status, bool(ack and ack.ok), ack.latency_ms if ack else None, res.message)
        return res, ack_d

    def set_mode(self, mode: str, username: str, reason: str | None) -> CommandResult:
        res = self.fsm.set_mode(Mode(mode), username)
        ack = self.adapter.ping() if res.ok else None
        self._log_command("SET_MODE", {"mode": mode}, "MANUAL", username, res.from_state, res.to_state, reason,
                          res.status, bool(ack and ack.ok), ack.latency_ms if ack else None, res.message)
        return res

    def recover(self, mode: str, username: str, reason: str | None) -> CommandResult:
        issues = self.health_issues()
        before = self.fsm.state
        if issues and self.fsm.mode == Mode.FAILSAFE:
            res = CommandResult("REJECTED", "Chưa thể khôi phục: " + "; ".join(issues), before, before)
        else:
            res = self.fsm.recover(Mode(mode), username)
            if res.ok and self.failsafe_alert:
                resolve_alert(self.failsafe_alert, f"Khôi phục bởi {username}")
                self.failsafe_alert = None
        self._log_command("RECOVER", {"mode": mode}, "MANUAL", username, res.from_state, res.to_state, reason,
                          res.status, res.ok, None, res.message)
        return res

    # ------------------------------------------------------------------ snapshots
    def direction_metrics(self, d: str, now: float) -> dict:
        p = self.pipelines[d]
        res = p.analyzer.last
        med, high = p.thresholds(self.cfg)
        cam = p.camera
        return {
            "direction": d,
            "label": DIRECTION_LABELS[d],
            "camera": cam.snapshot(now) if cam else None,
            "counts_total": dict(p.counter.totals),
            "counts_15m": p.counter.by_class(900, now),
            "flow_vph": round(p.counter.flow_vph(300, now, now - self.started_at)),
            "arrival_pcu_h": round(p.counter.arrival_pcu_h(180, now, now - self.started_at)),
            "in_roi": res.in_roi if res else {c: 0 for c in CLASSES},
            "roi_pcu": res.roi_pcu if res else 0,
            "occupancy": res.occupancy if res else 0,
            "queue_count": res.queue_count if res else 0,
            "queue_m": res.queue_m if res else 0,
            "density": res.density if res else 0,
            "density_smoothed": res.density_smoothed if res else 0,
            "level": p.level,
            "level_label": LEVEL_LABELS[p.level],
            "avg_wait_s": None if (w := p.counter.avg_wait(300, now)) is None else round(w, 1),
            "thresholds": {"medium": med, "high": high},
            "detection": p.detector.metrics.summary(),
            "geometry": {
                "roi": p.roi,
                "counting_line": p.line,
                "roi_length_m": p.counter.roi_length_m,
                "calibration": self.sim.calib.to_dict(),
            },
        }

    def snapshot_message(self) -> dict:
        now = time.time()
        dirs = {d: self.direction_metrics(d, now) for d in DIRECTIONS}
        det = [m["detection"] for m in dirs.values() if m["detection"]["inference_ms"] is not None]

        def avg(key):
            vals = [x[key] for x in det if x.get(key) is not None]
            return round(sum(vals) / len(vals), 4) if vals else None

        waits = [m["avg_wait_s"] for m in dirs.values() if m["avg_wait_s"] is not None]
        levels = [m["level"] for m in dirs.values()]
        worst = "HIGH" if "HIGH" in levels else ("MEDIUM" if "MEDIUM" in levels else "LOW")
        cams = [m["camera"] for m in dirs.values() if m["camera"]]
        return {
            "type": "snapshot",
            "intersection_id": self.id,
            "ts": now,
            "name": self.cfg.name,
            "code": self.cfg.code,
            "signal": self.fsm.snapshot(),
            "controller": {
                "endpoint": self.cfg.controller_endpoint,
                "model": self.cfg.controller_model,
                "online": self.controller_online and not self.adapter.fault,
                "fault": self.adapter.fault,
                "last_ack": self.last_ack,
                "heartbeat_age_s": round(now - self.adapter.last_heartbeat_at, 1),
            },
            "directions": dirs,
            "plan": self.latest_plan.to_dict() if self.latest_plan else None,
            "plan_applied": self.plan_applied,
            "llm": self.llm.to_dict(now),
            "kpi": {
                "avg_wait_s": round(sum(waits) / len(waits), 1) if waits else None,
                "flow_vph": sum(m["flow_vph"] for m in dirs.values()),
                "avg_density": round(sum(m["density_smoothed"] for m in dirs.values()) / 4, 1),
                "worst_level": worst,
                "vehicles_in_roi": sum(sum(m["in_roi"].values()) for m in dirs.values()),
                "today_total": sum(sum(m["counts_total"].values()) for m in dirs.values()),
            },
            "detection": {
                "model": self.pipelines["NORTH"].detector.name,
                "inference_ms": avg("inference_ms"),
                "precision": avg("precision"),
                "recall": avg("recall"),
                "f1": avg("f1"),
                "avg_confidence": avg("avg_confidence"),
                "class_accuracy": avg("class_accuracy"),
                "fps": round(sum(c["fps"] for c in cams) / len(cams), 1) if cams else 0,
            },
            "sim": {
                **self.sim.state(),
                "vision_fault": self.vision_fault or any(p.detector.fault for p in self.pipelines.values()),
                "controller_fault": self.adapter.fault,
            },
            "health_issues": self.health_issues(),
            "recent_events": self.recent_events[-12:],
            "tick_ms": round(self.tick_ms, 2),
        }

    def frames_message(self) -> dict:
        heads = self.fsm.heads()
        return {
            "type": "frames",
            "intersection_id": self.id,
            "ts": time.time(),
            "cameras": {
                d: {**p.frame_payload(), "signal": heads[d].value} for d, p in self.pipelines.items()
            },
        }

    def summary(self) -> dict:
        levels = [p.level for p in self.pipelines.values()]
        cams = [p.camera for p in self.pipelines.values() if p.camera]
        return {
            "id": self.id,
            "code": self.cfg.code,
            "name": self.cfg.name,
            "mode": self.fsm.mode.value,
            "interval": self.fsm.interval.value,
            "phase_id": self.fsm.phase_id,
            "worst_level": "HIGH" if "HIGH" in levels else ("MEDIUM" if "MEDIUM" in levels else "LOW"),
            "cameras_online": sum(1 for c in cams if c.status == ONLINE),
            "cameras_degraded": sum(1 for c in cams if c.status == DEGRADED),
            "cameras_total": len(cams),
            "controller_online": self.controller_online and not self.adapter.fault,
            "failsafe_reason": self.fsm.failsafe_reason,
        }
