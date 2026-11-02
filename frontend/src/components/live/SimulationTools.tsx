import { CameraOff, Cpu, RotateCcw, TrendingUp, Unplug, Wifi } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api } from "@/lib/api";
import { DIRECTIONS, DIR_LABEL } from "@/lib/format";
import type { Direction, Snapshot } from "@/lib/types";
import { Select } from "../ui/Form";
import { Badge, Button } from "../ui/primitives";

const SCENARIOS = [
  { id: "NORMAL", label: "Bình thường (theo giờ thực)" },
  { id: "RUSH_HOUR", label: "Giờ cao điểm ×1.6" },
  { id: "EVENT", label: "Sự kiện / tan tầm ×2.1" },
  { id: "NIGHT", label: "Ban đêm ×0.25" },
];

/** Công cụ giả lập tình huống để kiểm thử NFR07, US11, US12 ngay trên giao diện (hiển thị trong ngăn kéo). */
export function SimulationTools({ snap }: { snap: Snapshot | null }) {
  const { can } = useAuth();
  const toast = useToast();
  const [dir, setDir] = useState<Direction>("NORTH");
  const [busy, setBusy] = useState<string | null>(null);
  const allowed = can("sim:control");
  const iid = snap?.intersection_id;

  const call = async (key: string, path: string, body: unknown) => {
    if (!iid) return;
    setBusy(key);
    try {
      const r = await api.post<{ message: string }>(`/simulation/${iid}/${path}`, body);
      toast("info", "Giả lập", r.message);
    } catch (e) {
      toast("error", "Giả lập thất bại", (e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const cam = snap?.directions[dir]?.camera;
  const surge = snap?.sim.surges[dir];

  return (
    <div>
      {!allowed ? (
        <p className="text-xs text-ink-mute">Chỉ Người vận hành và Quản trị viên được dùng công cụ giả lập.</p>
      ) : (
        <div className="space-y-3">
          <div>
            <div className="label mb-1">Kịch bản lưu lượng</div>
            <Select value={snap?.sim.scenario ?? "NORMAL"} onChange={(e) => call("scn", "scenario", { scenario: e.target.value })} disabled={!iid}>
              {SCENARIOS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </Select>
            <div className="num mt-1 text-2xs text-ink-mute">hệ số giờ hiện tại ×{snap?.sim.tod_factor.toFixed(2) ?? "—"}</div>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="label">Hướng tác động</span>
              {cam && <Badge color={cam.status === "ONLINE" ? "#10B981" : cam.status === "DEGRADED" ? "#F59E0B" : "#EF4444"}>{cam.code} · {cam.status}</Badge>}
            </div>
            <div className="grid grid-cols-4 gap-1">
              {DIRECTIONS.map((d) => (
                <button
                  key={d}
                  onClick={() => setDir(d)}
                  aria-pressed={dir === d}
                  className={`rounded-ctl border py-1 text-xs font-medium ${dir === d ? "border-auto bg-auto/15 text-ink" : "border-line text-ink-mute hover:text-ink"}`}
                >
                  {DIR_LABEL[d]}
                  {snap?.sim.surges[d] && <span className="ml-0.5 text-warn">↑</span>}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-1.5">
            <Button size="sm" variant="warn" icon={<TrendingUp className="h-3.5 w-3.5" />} loading={busy === "s3"} onClick={() => call("s3", "surge", { directions: [dir], multiplier: 3, duration_s: 180 })}>
              Đột biến ×3 (3 phút)
            </Button>
            <Button size="sm" variant="secondary" disabled={!surge} loading={busy === "s1"} onClick={() => call("s1", "surge", { directions: [dir], multiplier: 1, duration_s: null })}>
              {surge ? `Huỷ ×${surge.multiplier} ${surge.remaining ?? ""}s` : "Không có đột biến"}
            </Button>
            <Button size="sm" variant="danger" icon={<CameraOff className="h-3.5 w-3.5" />} loading={busy === "cd"} onClick={() => call("cd", "camera", { direction: dir, action: "DISCONNECT" })}>
              Ngắt camera
            </Button>
            <Button size="sm" variant="warn" icon={<Unplug className="h-3.5 w-3.5" />} loading={busy === "cg"} onClick={() => call("cg", "camera", { direction: dir, action: "DEGRADE" })}>
              Suy giảm tín hiệu
            </Button>
            <Button size="sm" variant="success" icon={<Wifi className="h-3.5 w-3.5" />} loading={busy === "cr"} className="col-span-2" disabled={!cam?.fault} onClick={() => call("cr", "camera", { direction: dir, action: "RESTORE" })}>
              Khôi phục camera hướng {DIR_LABEL[dir]}
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-1.5 border-t border-line/70 pt-3">
            {snap?.sim.controller_fault ? (
              <Button size="sm" variant="success" icon={<Cpu className="h-3.5 w-3.5" />} loading={busy === "ct"} onClick={() => call("ct", "controller", { action: "RESTORE" })}>
                Nối lại bộ điều khiển
              </Button>
            ) : (
              <Button size="sm" variant="danger" icon={<Cpu className="h-3.5 w-3.5" />} loading={busy === "ct"} onClick={() => call("ct", "controller", { action: "FAULT" })}>
                Mất bộ điều khiển
              </Button>
            )}
            {snap?.sim.vision_fault ? (
              <Button size="sm" variant="success" loading={busy === "vf"} onClick={() => call("vf", "vision", { action: "RESTORE" })}>
                Khôi phục thuật toán AI
              </Button>
            ) : (
              <Button size="sm" variant="danger" loading={busy === "vf"} onClick={() => call("vf", "vision", { action: "FAULT" })}>
                Lỗi thuật toán AI
              </Button>
            )}
          </div>
          <p className="text-2xs leading-relaxed text-ink-mute">
            Khi đang AUTO, mất camera hoặc lỗi AI sẽ chuyển FAILSAFE chu kỳ cố định; mất bộ điều khiển sẽ chuyển chớp vàng. Sau khi khôi phục thiết bị,
            dùng nút “Khôi phục” trong bảng điều khiển đèn.
          </p>
          <Button
            variant="secondary"
            className="w-full"
            icon={<RotateCcw className="h-3.5 w-3.5" />}
            disabled={!iid}
            loading={busy === "reset"}
            onClick={() => call("reset", "reset", {})}
          >
            Xoá toàn bộ giả lập
          </Button>
        </div>
      )}
    </div>
  );
}

/** Số giả lập đang tác động (để hiển thị trên nút mở ngăn kéo). */
export function activeSimCount(snap: Snapshot | null): number {
  if (!snap) return 0;
  const camFaults = Object.values(snap.directions).filter((d) => d.camera?.fault).length;
  return (
    Object.keys(snap.sim.surges).length +
    camFaults +
    (snap.sim.controller_fault ? 1 : 0) +
    (snap.sim.vision_fault ? 1 : 0) +
    (snap.sim.scenario !== "NORMAL" ? 1 : 0)
  );
}
