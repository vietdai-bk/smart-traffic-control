import type { CamStatus, Direction, HeadColor, Level, Mode, VehicleClass } from "./types";

export const DIRECTIONS: Direction[] = ["NORTH", "SOUTH", "EAST", "WEST"];
export const DIR_LABEL: Record<Direction, string> = { NORTH: "Bắc", SOUTH: "Nam", EAST: "Đông", WEST: "Tây" };
export const DIR_SHORT: Record<Direction, string> = { NORTH: "B", SOUTH: "N", EAST: "Đ", WEST: "T" };

export const CLASSES: VehicleClass[] = ["car", "motorbike", "bus", "truck"];
export const CLASS_LABEL: Record<VehicleClass, string> = { car: "Ô tô", motorbike: "Xe máy", bus: "Xe buýt", truck: "Xe tải" };
// Bảng màu phân loại đã kiểm định (CVD ΔE ≥ 11, dải sáng nền tối) — tránh trùng màu trạng thái emerald/amber/red
export const CLASS_COLOR: Record<VehicleClass, string> = {
  car: "#0891B2",
  motorbike: "#65A30D",
  bus: "#DB2777",
  truck: "#EA580C",
};
export const BEFORE_COLOR = "#64748B";
export const AFTER_COLOR = "#3B82F6";

export const MODE_LABEL: Record<Mode, string> = {
  AUTO: "Tự động AI",
  MANUAL: "Thủ công",
  FIXED_TIME: "Chu kỳ cố định",
  FAILSAFE: "An toàn khi lỗi",
};
export const MODE_COLOR: Record<Mode, string> = {
  AUTO: "#3B82F6",
  MANUAL: "#A855F7",
  FIXED_TIME: "#94A3B8",
  FAILSAFE: "#EF4444",
};

export const LEVEL_LABEL: Record<Level, string> = { LOW: "Thông thoáng", MEDIUM: "Đông đúc", HIGH: "Ùn tắc" };
export const LEVEL_COLOR: Record<Level, string> = { LOW: "#10B981", MEDIUM: "#F59E0B", HIGH: "#EF4444" };

export const HEAD_COLOR: Record<HeadColor, string> = {
  GREEN: "#10B981",
  YELLOW: "#F59E0B",
  RED: "#EF4444",
  FLASHING_YELLOW: "#F59E0B",
  OFF: "#334155",
};

export const CAM_STATUS_COLOR: Record<CamStatus, string> = {
  ONLINE: "#10B981",
  DEGRADED: "#F59E0B",
  OFFLINE: "#EF4444",
  CONNECTING: "#94A3B8",
  NO_CAMERA: "#64748B",
};

export const INTERVAL_LABEL: Record<string, string> = {
  GREEN: "Xanh",
  YELLOW_CLEARANCE: "Vàng chuyển tiếp",
  ALL_RED_CLEARANCE: "Toàn đỏ",
  FLASHING_YELLOW: "Chớp vàng",
};

export const PHASE_LABEL: Record<number, string> = { 1: "Pha 1 · Bắc–Nam", 2: "Pha 2 · Đông–Tây" };

export const COMMAND_LABEL: Record<string, string> = {
  NEXT_PHASE: "Chuyển pha kế tiếp",
  GOTO_PHASE: "Chuyển đến pha",
  HOLD_PHASE: "Giữ xanh khẩn cấp",
  RELEASE_HOLD: "Giải phóng giữ pha",
  EXTEND_GREEN: "Kéo dài xanh",
  SET_TIMING: "Điều chỉnh thời gian pha",
  FLASHING_YELLOW: "Chớp vàng",
  SET_MODE: "Chuyển chế độ",
  RECOVER: "Khôi phục FAILSAFE",
  ENTER_FAILSAFE: "Kích hoạt FAILSAFE",
  PHASE_CHANGE: "Chuyển pha",
};

export const STATUS_LABEL: Record<string, string> = {
  ACCEPTED: "Đã nhận",
  SCHEDULED: "Đã xếp lịch",
  EXECUTED: "Đã thực thi",
  REJECTED: "Bị từ chối",
  ACTIVE: "Đang hoạt động",
  ACKNOWLEDGED: "Đã xác nhận",
  RESOLVED: "Đã đóng",
  OPEN: "Chưa xử lý",
};

/**
 * Tông chữ cho màu trạng thái: trộn màu với màu chữ chính (ink) để đủ tương phản trên nền sáng.
 */
export const tone = (color: string, amount = 68) => `color-mix(in oklab, ${color} ${amount}%, rgb(var(--c-ink)))`;

const nf = new Intl.NumberFormat("vi-VN");
export const fmtInt = (n: number | null | undefined) => (n == null || Number.isNaN(n) ? "—" : nf.format(Math.round(n)));
export const fmtNum = (n: number | null | undefined, digits = 1) =>
  n == null || Number.isNaN(n) ? "—" : n.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const fmtPct = (n: number | null | undefined, digits = 1) => (n == null ? "—" : `${fmtNum(n, digits)}%`);
export const fmtSec = (n: number | null | undefined) => (n == null ? "∞" : `${Math.max(0, Math.ceil(n))}`);

export function fmtTime(iso: string | null | undefined, withDate = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const time = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  if (!withDate) return time;
  return `${d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })} ${time}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  return fmtTime(iso, true);
}

export function fmtHour(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:00`;
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}ph ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}g ${m % 60}ph`;
  return `${Math.floor(h / 24)}n ${h % 24}g`;
}

export function since(iso: string | null | undefined, end?: string | null): string {
  if (!iso) return "—";
  const a = new Date(iso).getTime();
  const b = end ? new Date(end).getTime() : Date.now();
  return fmtDuration((b - a) / 1000);
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "vừa xong";
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  return `${Math.floor(diff / 86400)} ngày trước`;
}
