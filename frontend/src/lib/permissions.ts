export type Perm =
  | "live:view"
  | "stats:view"
  | "stats:export"
  | "alerts:view"
  | "alerts:ack"
  | "signal:control"
  | "signal:mode"
  | "sim:control"
  | "config:view"
  | "config:manage"
  | "users:manage"
  | "audit:view"
  | "llm:supervise"
  | "assistant:use"
  | "report:ai";

export const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Quản trị viên",
  OPERATOR: "Người vận hành",
  MANAGER: "Người quản lý",
  VIEWER: "Người xem dữ liệu",
};

export const ROLE_COLOR: Record<string, string> = {
  ADMIN: "#F59E0B",
  OPERATOR: "#3B82F6",
  MANAGER: "#94A3B8",
  VIEWER: "#14B8A6",
};
