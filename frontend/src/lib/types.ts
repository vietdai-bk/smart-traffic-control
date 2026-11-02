export type Role = "ADMIN" | "OPERATOR" | "MANAGER" | "VIEWER";
export type Direction = "NORTH" | "SOUTH" | "EAST" | "WEST";
export type Mode = "AUTO" | "MANUAL" | "FIXED_TIME" | "FAILSAFE";
export type Interval = "GREEN" | "YELLOW_CLEARANCE" | "ALL_RED_CLEARANCE" | "FLASHING_YELLOW";
export type HeadColor = "GREEN" | "YELLOW" | "RED" | "FLASHING_YELLOW" | "OFF";
export type CamStatus = "ONLINE" | "DEGRADED" | "OFFLINE" | "CONNECTING" | "NO_CAMERA";
export type Level = "LOW" | "MEDIUM" | "HIGH";
export type VehicleClass = "car" | "motorbike" | "bus" | "truck";

export interface User {
  id: number;
  username: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  role: Role;
  is_active: boolean;
  failed_attempts: number;
  locked_until: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface Camera {
  id: number;
  intersection_id: number;
  code: string;
  name: string;
  direction: Direction;
  source_type: "SIMULATED" | "RTSP" | "HTTP" | "FILE";
  stream_url: string;
  resolution: string;
  target_fps: number;
  roi: number[][];
  counting_line: number[][];
  roi_length_m: number;
  density_medium: number | null;
  density_high: number | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface Intersection {
  id: number;
  code: string;
  name: string;
  description: string | null;
  district: string | null;
  latitude: number;
  longitude: number;
  ns_road: string;
  ew_road: string;
  lanes_per_approach: number;
  default_mode: "AUTO" | "FIXED_TIME" | "MANUAL";
  fixed_green_ns: number;
  fixed_green_ew: number;
  yellow_s: number;
  all_red_s: number;
  min_green_s: number;
  max_green_s: number;
  cycle_min_s: number;
  cycle_max_s: number;
  saturation_flow: number;
  failsafe_strategy: "FIXED_TIME" | "FLASHING_YELLOW";
  density_medium: number;
  density_high: number;
  alert_hold_s: number;
  base_demand_ns: number;
  base_demand_ew: number;
  controller_endpoint: string;
  controller_model: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  cameras: Camera[];
}

export interface Plan {
  green_ns: number;
  green_ew: number;
  source: string;
  reason: string;
  cycle_s: number | null;
}

export interface SignalState {
  mode: Mode;
  mode_label: string;
  state: string;
  phase_id: number;
  phase_name: string;
  interval: Interval;
  elapsed: number;
  remaining: number | null;
  duration: number | null;
  green_target: number;
  next_phase_id: number;
  heads: Record<Direction, { color: HeadColor; remaining: number | null }>;
  hold: { phase_id: number; remaining: number | null; by: string | null } | null;
  scheduled: { phase_id: number; by: string | null; eta: number } | null;
  flash_requested: boolean;
  failsafe_reason: string | null;
  failsafe_strategy: string;
  auto_locked: boolean;
  min_green_ok: boolean;
  timing: { min_green: number; max_green: number; yellow: number; all_red: number; cycle_min: number; cycle_max: number };
  active_plan: Plan;
  pending_plan: Plan | null;
  fixed_plan: Plan;
  last_violation: string | null;
}

export interface CameraLive {
  id: number;
  code: string;
  name: string;
  direction: Direction;
  source_type: string;
  status: CamStatus;
  fps: number;
  target_fps: number;
  resolution: string;
  bitrate_kbps: number;
  latency_ms: number;
  frame_no: number;
  fault: string | null;
  error: string | null;
  reconnect_attempts: number;
  next_reconnect_in: number | null;
  uptime_s: number;
  mjpeg: boolean;
}

export interface DetectionSummary {
  inference_ms: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  avg_confidence: number | null;
  class_accuracy: number | null;
}

export interface Calibration {
  lanes: number;
  lane_width: number;
  y_horizon: number;
  stop_y: number;
  d0: number;
  cam_offset: number;
  fx: number;
  A: number;
  visible_far_m: number;
}

export interface DirectionMetrics {
  direction: Direction;
  label: string;
  camera: CameraLive | null;
  counts_total: Record<VehicleClass, number>;
  counts_15m: Record<VehicleClass, number>;
  flow_vph: number;
  arrival_pcu_h: number;
  in_roi: Record<VehicleClass, number>;
  roi_pcu: number;
  occupancy: number;
  queue_count: number;
  queue_m: number;
  density: number;
  density_smoothed: number;
  level: Level;
  level_label: string;
  avg_wait_s: number | null;
  thresholds: { medium: number; high: number };
  detection: DetectionSummary;
  geometry: { roi: number[][]; counting_line: number[][]; roi_length_m: number; calibration: Calibration };
}

export interface AdaptivePlan {
  green_ns: number;
  green_ew: number;
  cycle_s: number;
  webster_cycle_s: number;
  flow_ratio_ns: number;
  flow_ratio_ew: number;
  flow_ratio_total: number;
  demand_ns_pcu_h: number;
  demand_ew_pcu_h: number;
  queue_ns_m: number;
  queue_ew_m: number;
  critical_ns: Direction;
  critical_ew: Direction;
  saturated: boolean;
  reason: string;
}

export interface SignalEvent {
  ts: number;
  state: string;
  interval: Interval;
  phase_id: number;
  cause: string;
  ack: { ok: boolean; seq: number; latency_ms: number; error: string | null } | null;
}

export interface Snapshot {
  type: "snapshot";
  intersection_id: number;
  ts: number;
  name: string;
  code: string;
  signal: SignalState;
  controller: {
    endpoint: string;
    model: string;
    online: boolean;
    fault: string | null;
    last_ack: SignalEvent["ack"];
    heartbeat_age_s: number;
  };
  directions: Record<Direction, DirectionMetrics>;
  plan: AdaptivePlan | null;
  plan_applied: boolean;
  llm?: LlmState;
  kpi: {
    avg_wait_s: number | null;
    flow_vph: number;
    avg_density: number;
    worst_level: Level;
    vehicles_in_roi: number;
    today_total: number;
  };
  detection: DetectionSummary & { model: string; fps: number };
  sim: {
    scenario: string;
    scenario_label: string;
    tod_factor: number;
    surges: Partial<Record<Direction, { multiplier: number; remaining: number | null }>>;
    vehicles: Record<Direction, number>;
    pending: Record<Direction, number>;
    vision_fault: boolean;
    controller_fault: string | null;
  };
  health_issues: string[];
  recent_events: SignalEvent[];
  tick_ms: number;
}

/** [x1, y1, x2, y2, clsIdx, colorIdx, brake, objectId] */
export type FrameObject = [number, number, number, number, number, number, number, number];
/** [trackId, x1, y1, x2, y2, clsIdx, conf, stopped] */
export type FrameTrack = [number, number, number, number, number, number, number, number];

export interface FramesMessage {
  type: "frames";
  intersection_id: number;
  ts: number;
  cameras: Record<Direction, { status: CamStatus; frame_no: number; objects: FrameObject[]; tracks: FrameTrack[]; signal: HeadColor }>;
}

export interface IntersectionSummary {
  id: number;
  code: string;
  name: string;
  mode: Mode;
  interval: Interval;
  phase_id: number;
  worst_level: Level;
  cameras_online: number;
  cameras_degraded: number;
  cameras_total: number;
  controller_online: boolean;
  failsafe_reason: string | null;
}

export interface Alert {
  id: number;
  intersection_id: number;
  direction: Direction | null;
  alert_type: "CONGESTION" | "FAILSAFE" | "SAFETY";
  level: "WARNING" | "CRITICAL";
  title: string;
  message: string;
  density: number | null;
  queue_m: number | null;
  peak_density: number | null;
  status: "ACTIVE" | "ACKNOWLEDGED" | "RESOLVED";
  created_at: string;
  resolved_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  ack_note: string | null;
}

export interface Incident {
  id: number;
  intersection_id: number;
  device_type: "CAMERA" | "CONTROLLER" | "VISION";
  device_id: number | null;
  device_code: string;
  incident_type: string;
  severity: "WARNING" | "CRITICAL";
  message: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
  started_at: string;
  recovered_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
}

export interface AuditLog {
  id: number;
  created_at: string;
  category: string;
  action: string;
  username: string;
  role: string | null;
  target: string | null;
  description: string;
  details: Record<string, unknown>;
  ip: string | null;
  result: "SUCCESS" | "FAILURE";
  intersection_id: number | null;
}

export interface SignalCommandLog {
  id: number;
  intersection_id: number;
  created_at: string;
  command: string;
  params: Record<string, unknown>;
  source: "MANUAL" | "AUTO" | "SYSTEM";
  issued_by: string;
  mode: string;
  from_state: string;
  to_state: string;
  reason: string | null;
  status: string;
  ack: boolean;
  ack_latency_ms: number | null;
  message: string | null;
}

export interface SignalCycle {
  id: number;
  intersection_id: number;
  started_at: string;
  ended_at: string;
  mode: string;
  cycle_length_s: number;
  green_ns_s: number;
  green_ew_s: number;
  yellow_s: number;
  all_red_s: number;
  demand_ns_pcu: number;
  demand_ew_pcu: number;
  queue_ns_m: number;
  queue_ew_m: number;
  avg_wait_s: number;
  throughput: number;
  plan_reason: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface CommandResult {
  status: "ACCEPTED" | "SCHEDULED" | "EXECUTED" | "REJECTED";
  message: string;
  from_state: string;
  to_state: string;
  eta_s: number | null;
  ack: SignalEvent["ack"];
  signal: SignalState | null;
}

export interface StatRow {
  car: number;
  motorbike: number;
  bus: number;
  truck: number;
  total: number;
  pcu: number;
  avg_density: number;
  max_density: number;
  avg_queue_m: number;
  max_queue_m: number;
  avg_wait_s: number;
}

// ---------------------------------------------------------------- LLM Supervisor (tầng 3) & trợ lý
export type LlmMode = "OFF" | "ADVISORY" | "AUTONOMOUS";
export type LlmStatus = "APPLIED" | "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "INVALID" | "ERROR" | "SKIPPED";

export interface LlmDecision {
  id: number | null;
  intersection_id: number;
  created_at: string | null;
  trigger: "PERIODIC" | "EVENT" | "MANUAL";
  supervisor_mode: LlmMode;
  model: string;
  status: LlmStatus;
  strategy: string | null;
  strategy_label: string | null;
  weight_ns: number | null;
  weight_ew: number | null;
  duration_min: number | null;
  reason: string | null;
  guard_notes: string | null;
  latency_ms: number | null;
  decided_by: string | null;
  context?: Record<string, unknown>;
  raw_output?: string | null;
}

export interface LlmPending {
  id: number;
  strategy: string;
  weight_ns: number;
  weight_ew: number;
  duration_min: number;
  reason: string;
  guard_notes: string | null;
  expires_in_s: number;
}

export interface LlmState {
  enabled: boolean;
  model: string;
  mode: LlmMode;
  mode_label: string;
  strategy: string;
  strategy_label: string;
  weight_ns: number;
  weight_ew: number;
  reason: string;
  source: string;
  expires_in_s: number | null;
  decision_id: number | null;
  pending: LlmPending | null;
  last: LlmDecision | null;
  running: boolean;
  last_error: string | null;
  next_run_in_s: number | null;
}

export interface AssistantAction {
  id: string;
  intersection_id: number;
  intersection: string;
  action: string;
  params: Record<string, unknown>;
  reason: string;
  summary: string;
  expires_in_s: number;
}

export interface AssistantReply {
  reply: string;
  trace: { tool: string; args: Record<string, unknown>; ok: boolean }[];
  actions: AssistantAction[];
  model: string;
  latency_ms: number;
}

export interface AiReport {
  markdown: string;
  data: Record<string, unknown>;
  model: string;
  latency_ms: number;
  generated_at: string;
}
