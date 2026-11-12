import clsx from "clsx";
import {
  Ambulance,
  ArrowRightLeft,
  Clock4,
  LifeBuoy,
  Lock,
  Plus,
  RadioTower,
  SlidersHorizontal,
  TriangleAlert,
  Unlock,
  Zap,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api } from "@/lib/api";
import { HEAD_COLOR, INTERVAL_LABEL, MODE_LABEL, PHASE_LABEL, STATUS_LABEL, tone } from "@/lib/format";
import type { CommandResult, Mode, Snapshot } from "@/lib/types";
import { Modal } from "../ui/Modal";
import { Field, Input, Select } from "../ui/Form";
import { Badge, Button, Dot, Panel } from "../ui/primitives";
import { previewFlash, previewGoto, SafetyConfirmModal, type SafetyStep } from "./SafetyConfirmModal";

type Pending =
  | { kind: "command"; command: string; params: Record<string, unknown>; title: string; description: string; steps: SafetyStep[]; tone: "auto" | "manual" | "danger"; requireReason?: boolean; requireCode?: boolean; confirmLabel: string; warning?: string | null }
  | { kind: "mode"; mode: Mode }
  | { kind: "recover"; mode: Mode };

export function SignalControlPanel({ snap }: { snap: Snapshot | null }) {
  const { can } = useAuth();
  const toast = useToast();
  const quickLock = useRef(false);
  const [quickBusy, setQuickBusy] = useState(false);
  const [quickChoice, setQuickChoice] = useState<{ command: "HOLD_PHASE" | "RELEASE_HOLD"; phase?: number; iid: number; duration: string } | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [holdDur, setHoldDur] = useState("60");
  const [timing, setTiming] = useState<{ ns: string; ew: string } | null>(null);

  useEffect(() => {
    setQuickChoice(null);
  }, [snap?.intersection_id, holdDur, snap?.signal.hold?.phase_id, snap?.controller.online, snap?.signal.mode]);

  if (!snap) {
    return (
      <Panel title="Điều khiển đèn tín hiệu" icon={<RadioTower className="h-4 w-4" />}>
        <div className="py-8 text-center text-sm text-ink-mute">Đang chờ dữ liệu bộ điều khiển…</div>
      </Panel>
    );
  }

  const sig = snap.signal;
  const iid = snap.intersection_id;
  const canControl = can("signal:control");
  const canMode = can("signal:mode");
  const ctlOnline = snap.controller.online;
  const failsafe = sig.mode === "FAILSAFE";
  const lockedFlash = failsafe && sig.interval === "FLASHING_YELLOW";
  const disabledReason = !canControl
    ? "Chỉ Người vận hành / Quản trị viên được điều khiển đèn"
    : !ctlOnline
      ? "Bộ điều khiển mất kết nối"
      : lockedFlash
        ? "Đang FAILSAFE chớp vàng — cần khôi phục"
        : null;
  const cmdDisabled = !!disabledReason || quickBusy;
  const t = sig.timing;
  const progress = sig.duration ? Math.min(100, (sig.elapsed / sig.duration) * 100) : 100;
  const intervalColor =
    sig.interval === "GREEN" ? HEAD_COLOR.GREEN : sig.interval === "ALL_RED_CLEARANCE" ? HEAD_COLOR.RED : HEAD_COLOR.YELLOW;

  const checks = [
    { label: "Ma trận xung đột Bắc–Nam ⟂ Đông–Tây", ok: true },
    { label: `Xanh tối thiểu ${t.min_green}s`, ok: sig.interval !== "GREEN" || sig.min_green_ok },
    { label: `Vàng ${t.yellow}s + Toàn đỏ ${t.all_red}s tự chèn`, ok: true },
    { label: `Bộ điều khiển ${ctlOnline ? "phản hồi ACK" : "mất kết nối"}`, ok: ctlOnline },
  ];

  const run = async (path: string, body: Record<string, unknown>, label: string) => {
    try {
      const r = await api.post<CommandResult>(path, { ...body, confirm: true });
      const ack = r.ack ? ` · ACK #${r.ack.seq} ${r.ack.latency_ms.toFixed(0)} ms` : "";
      toast(r.status === "REJECTED" ? "error" : r.status === "SCHEDULED" ? "warning" : "success", `${label}: ${STATUS_LABEL[r.status]}${ack}`, r.message);
    } catch (e) {
      toast("error", `${label} thất bại`, (e as Error).message);
      throw e;
    }
  };

  const quickCommand = async (command: "HOLD_PHASE" | "RELEASE_HOLD", phase?: number) => {
    if (cmdDisabled || quickLock.current) return;
    quickLock.current = true;
    setQuickBusy(true);
    try {
      await run(`/signals/${iid}/command`, {
        command,
        params: command === "HOLD_PHASE" ? { phase_id: phase, duration_s: holdDur ? Number(holdDur) : null } : {},
        reason: command === "HOLD_PHASE" ? `Ưu tiên xe khẩn cấp ${PHASE_LABEL[phase!]}; thao tác nhanh` : "Bỏ giữ pha; thao tác nhanh",
      }, command === "HOLD_PHASE" ? `Giữ xanh ${PHASE_LABEL[phase!]}` : "Bỏ giữ pha");
    } catch {
      // run() already displays the backend error; allow retry after completion.
    } finally {
      quickLock.current = false;
      setQuickBusy(false);
      setQuickChoice(null);
    }
  };

  const gotoPending = (target: number, command = "GOTO_PHASE"): Pending => ({
    kind: "command",
    command,
    params: command === "GOTO_PHASE" ? { phase_id: target } : {},
    title: command === "NEXT_PHASE" ? "Chuyển pha kế tiếp" : `Chuyển sang ${PHASE_LABEL[target]}`,
    description:
      sig.mode === "MANUAL"
        ? "Chế độ thủ công: pha mới sẽ được giữ xanh cho đến lệnh tiếp theo."
        : `Đang ở chế độ ${MODE_LABEL[sig.mode]}: sau khi chuyển, thời gian xanh tiếp tục theo kế hoạch hiện hành.`,
    steps: previewGoto(sig, target),
    tone: "manual",
    confirmLabel: "Thực hiện chuyển pha",
  });

  const upcoming = sig.interval === "GREEN" ? (sig.scheduled?.phase_id ?? (sig.phase_id === 1 ? 2 : 1)) : sig.next_phase_id;
  const nextTarget = sig.interval === "GREEN" || sig.interval === "FLASHING_YELLOW" ? (sig.phase_id === 1 ? 2 : 1) : sig.next_phase_id;

  return (
    <Panel
      title="Điều khiển đèn tín hiệu"
      icon={<RadioTower className="h-4 w-4 text-auto" />}
      tone={failsafe ? "danger" : undefined}
      actions={
        <span className="flex items-center gap-1.5 text-2xs text-ink-mute" title={snap.controller.endpoint}>
          <Dot color={ctlOnline ? "#10B981" : "#EF4444"} size={7} pulse={!ctlOnline} />
          <span className="num font-semibold">
            {ctlOnline
              ? `ACK ${snap.controller.last_ack ? snap.controller.last_ack.latency_ms.toFixed(0) : "–"} ms`
              : `mất heartbeat ${snap.controller.heartbeat_age_s.toFixed(0)}s`}
          </span>
        </span>
      }
    >
      {/* Khối cảnh báo FAILSAFE */}
      {failsafe ? (
        <div className="mb-3 rounded-panel border border-stop/60 bg-stop/15 p-3 shadow-inner">
          <div className="flex items-center gap-2 text-[13px] font-bold text-stop-ink">
            <Lock className="h-4 w-4 shrink-0" /> FAILSAFE — điều khiển tự động đã bị khoá
          </div>
          <p className="mt-1 text-xs leading-relaxed text-stop-ink/90">{sig.failsafe_reason}</p>
          {snap.health_issues.length > 0 && (
            <ul className="mt-1.5 space-y-0.5 text-2xs font-medium text-stop-ink">
              {snap.health_issues.map((h) => (
                <li key={h}>• {h}</li>
              ))}
            </ul>
          )}
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {(["AUTO", "FIXED_TIME", "MANUAL"] as Mode[]).map((m) => (
              <Button
                key={m}
                size="sm"
                variant={m === "AUTO" ? "primary" : "secondary"}
                icon={<LifeBuoy className="h-3.5 w-3.5" />}
                disabled={!canMode}
                title={!canMode ? "Không có quyền" : undefined}
                onClick={() => setPending({ kind: "recover", mode: m })}
              >
                Khôi phục → {MODE_LABEL[m]}
              </Button>
            ))}
          </div>
        </div>
      ) : (
        /* Bộ chọn chế độ điều khiển */
        <div className="mb-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="label">Chế độ vận hành</span>
            {!canMode && <span className="text-2xs text-ink-mute">Chỉ xem</span>}
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            {(["AUTO", "MANUAL", "FIXED_TIME"] as Mode[]).map((m) => {
              const active = sig.mode === m;
              return (
                <button
                  key={m}
                  disabled={!canMode || active}
                  onClick={() => setPending({ kind: "mode", mode: m })}
                  className={clsx(
                    "flex flex-col items-start rounded-ctl border px-2.5 py-1.5 text-left transition-all disabled:cursor-default",
                    active
                      ? "border-ink-dim bg-panel text-ink font-semibold"
                      : "border-line/70 bg-panel/30 text-ink-dim hover:bg-panel hover:text-ink disabled:opacity-50",
                  )}
                >
                  <span className="text-xs font-semibold">{MODE_LABEL[m]}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Đồng hồ hiển thị Pha & Đếm ngược */}
      <div className="relative overflow-hidden rounded-card border border-line/80 bg-panel/30 p-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-1.5">
              <Dot color={intervalColor} pulse={sig.interval === "GREEN" || sig.interval === "FLASHING_YELLOW"} size={10} />
              <span className="text-[13px] font-bold text-ink">{sig.phase_name}</span>
            </div>
            <div className="mt-0.5 text-xs font-semibold" style={{ color: tone(intervalColor, 82) }}>
              {INTERVAL_LABEL[sig.interval]}
              {sig.interval === "GREEN" && (
                <span className="num font-normal text-ink-mute"> · mục tiêu {sig.mode === "MANUAL" ? "giữ" : `${sig.green_target.toFixed(0)}s`}</span>
              )}
            </div>
          </div>
          <div className="text-right">
            <div
              className="num text-3xl font-extrabold leading-none tracking-tight sm:text-4xl"
              style={{
                color: tone(intervalColor, 88),
              }}
            >
              {sig.remaining == null ? (sig.interval === "FLASHING_YELLOW" ? "--" : "∞") : Math.ceil(sig.remaining).toString().padStart(2, "0")}
            </div>
            <div className="num mt-1 text-2xs font-semibold text-ink-mute">đã chạy {sig.elapsed.toFixed(0)}s</div>
          </div>
        </div>
        <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-line/60">
          <div className="h-full rounded-full transition-[width] duration-300" style={{ width: `${progress}%`, background: intervalColor }} />
        </div>

        {/* Trình tự pha tiếp theo */}
        <div className="mt-2.5 flex items-center gap-1 text-2xs">
          {[
            { k: "GREEN", label: `Xanh P${sig.phase_id}`, c: HEAD_COLOR.GREEN },
            { k: "YELLOW_CLEARANCE", label: `Vàng ${t.yellow}s`, c: HEAD_COLOR.YELLOW },
            { k: "ALL_RED_CLEARANCE", label: `Đỏ ${t.all_red}s`, c: HEAD_COLOR.RED },
            { k: "NEXT", label: `Xanh P${upcoming}`, c: HEAD_COLOR.GREEN },
          ].map((s, i) => {
            const on = sig.interval === s.k;
            return (
              <div key={i} className="flex flex-1 items-center gap-1">
                <span
                  className={clsx("num flex-1 truncate rounded-tag border px-1 py-0.5 text-center font-medium", on ? "font-bold shadow-sm" : "opacity-50")}
                  style={{
                    borderColor: on ? s.c : "rgb(var(--c-line))",
                    color: on ? tone(s.c, 85) : "rgb(var(--c-ink-mute))",
                    background: on ? `color-mix(in srgb, ${s.c} 14%, transparent)` : undefined,
                  }}
                >
                  {s.label}
                </span>
                {i < 3 && <span className="text-ink-mute font-bold">›</span>}
              </div>
            );
          })}
        </div>

        {/* Trạng thái khoá & xếp lịch */}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {!sig.min_green_ok && sig.interval === "GREEN" ? (
            <Badge color="#94A3B8">Khoá min green {Math.max(0, t.min_green - sig.elapsed).toFixed(0)}s</Badge>
          ) : null}
          {sig.hold && (
            <Badge color="#A855F7">
              Giữ P{sig.hold.phase_id} {sig.hold.remaining != null ? `${Math.ceil(sig.hold.remaining)}s` : "∞"} · {sig.hold.by}
            </Badge>
          )}
          {sig.scheduled && <Badge color="#F59E0B">Đã xếp lịch → P{sig.scheduled.phase_id} sau {sig.scheduled.eta.toFixed(0)}s</Badge>}
          {sig.flash_requested && sig.interval !== "FLASHING_YELLOW" && <Badge color="#F59E0B">Đang chuyển sang chớp vàng</Badge>}
        </div>
      </div>

        {/* Giữ xanh khẩn cấp */}
        <div className="mt-3 rounded-ctl border border-line bg-surface p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Ambulance className="h-4 w-4" />Ưu tiên xe khẩn cấp</div>
          <Field label="Thời gian giữ xanh" className="mb-2">
            <Select value={holdDur} onChange={(e) => setHoldDur(e.target.value)} disabled={cmdDisabled}>
              <option value="30">30 s</option>
              <option value="60">60 s</option>
              <option value="120">120 s</option>
              <option value="">Đến khi bỏ</option>
            </Select>
          </Field>
          {sig.hold ? (
            <Button variant="secondary" icon={<Unlock className="h-3.5 w-3.5" />}
              disabled={cmdDisabled} loading={quickBusy} onClick={() => setQuickChoice({ command: "RELEASE_HOLD", iid, duration: holdDur })}>
              Bỏ giữ
            </Button>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {[1, 2].map((phase) => (
                <Button key={phase} variant="secondary" icon={<Ambulance className="h-3.5 w-3.5" />}
                  disabled={cmdDisabled} loading={quickBusy} onClick={() => setQuickChoice({ command: "HOLD_PHASE", phase, iid, duration: holdDur })}>
                  {phase === 1 ? "Giữ Bắc–Nam" : "Giữ Đông–Tây"}
                </Button>
              ))}
            </div>
          )}
          {quickChoice && quickChoice.iid === iid && quickChoice.duration === holdDur && (
            <Modal
              open
              title="Xác nhận điều khiển khẩn cấp"
              width={420}
              onClose={() => { if (!quickLock.current) setQuickChoice(null); }}
              footer={
                <>
                  <Button variant="ghost" data-autofocus disabled={quickBusy} onClick={() => setQuickChoice(null)}>Huỷ</Button>
                  <Button variant="primary" disabled={cmdDisabled} loading={quickBusy}
                    onClick={() => void quickCommand(quickChoice.command, quickChoice.phase)}>
                    Xác nhận
                  </Button>
                </>
              }
            >
              <p className="mb-2 text-sm font-semibold text-ink">{snap.name}</p>
              <p className="text-sm text-ink-dim">
                {quickChoice.command === "HOLD_PHASE"
                  ? `Giữ ${PHASE_LABEL[quickChoice.phase!]} ${holdDur ? `${holdDur} giây` : "đến khi bỏ giữ"}?`
                  : "Bỏ giữ pha và trở lại kế hoạch hiện hành?"}
              </p>
            </Modal>
          )}
        </div>


      {/* Lệnh can thiệp */}
      <div className="mt-3">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="label">Điều khiển thường</span>
          {disabledReason && <span className="text-2xs text-warn-ink">{disabledReason}</span>}
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <Button variant="secondary" icon={<ArrowRightLeft className="h-3.5 w-3.5" />} disabled={cmdDisabled} onClick={() => setPending(gotoPending(nextTarget, "NEXT_PHASE"))}>
            Chuyển pha kế tiếp
          </Button>
          <Button
            variant="secondary"
            icon={<Plus className="h-3.5 w-3.5" />}
            disabled={cmdDisabled || sig.interval !== "GREEN" || sig.mode === "MANUAL"}
            title={sig.mode === "MANUAL" ? "Thủ công đã giữ xanh vô thời hạn" : undefined}
            onClick={() =>
              setPending({
                kind: "command",
                command: "EXTEND_GREEN",
                params: { seconds: 10 },
                title: "Kéo dài pha xanh +10s",
                description: `Kéo dài ${sig.phase_name} thêm 10 giây (không vượt Max Green ${t.max_green}s).`,
                steps: [
                  { label: `${sig.phase_name} xanh thêm 10s`, tone: "green" },
                  { label: `Vàng ${t.yellow}s → Toàn đỏ ${t.all_red}s`, tone: "yellow" },
                ],
                tone: "auto",
                confirmLabel: "Kéo dài xanh",
              })
            }
          >
            Kéo dài xanh +10s
          </Button>
          {[1, 2].map((p) => (
            <Button
              key={p}
              variant="secondary"
              disabled={cmdDisabled || (sig.interval === "GREEN" && sig.phase_id === p)}
              onClick={() => setPending(gotoPending(p))}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: HEAD_COLOR.GREEN }} />
              {PHASE_LABEL[p]}
            </Button>
          ))}
        </div>


        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <Button
            variant="secondary"
            icon={<SlidersHorizontal className="h-3.5 w-3.5" />}
            disabled={cmdDisabled}
            onClick={() => setTiming({ ns: String(sig.fixed_plan.green_ns), ew: String(sig.fixed_plan.green_ew) })}
          >
            Thời gian pha cố định
          </Button>
          {sig.interval === "FLASHING_YELLOW" || sig.flash_requested ? (
            <Button
              variant="warn"
              icon={<Zap className="h-3.5 w-3.5" />}
              disabled={cmdDisabled}
              onClick={() =>
                setPending({
                  kind: "command",
                  command: "FLASHING_YELLOW",
                  params: { on: false },
                  title: "Thoát chế độ chớp vàng",
                  description: "Đưa nút giao trở lại vận hành pha bình thường qua khoảng toàn đỏ an toàn.",
                  steps: previewFlash(sig, false),
                  tone: "manual",
                  confirmLabel: "Thoát chớp vàng",
                })
              }
            >
              Thoát chớp vàng
            </Button>
          ) : (
            <Button
              variant="warn"
              icon={<TriangleAlert className="h-3.5 w-3.5" />}
              disabled={cmdDisabled}
              onClick={() =>
                setPending({
                  kind: "command",
                  command: "FLASHING_YELLOW",
                  params: { on: true },
                  title: "Chuyển chớp vàng",
                  description: "Tất cả các hướng chuyển chớp vàng — chỉ dùng khi bảo trì hoặc sự cố tại hiện trường.",
                  steps: previewFlash(sig, true),
                  tone: "danger",
                  requireReason: true,
                  requireCode: true,
                  confirmLabel: "Chuyển chớp vàng",
                })
              }
            >
              Chớp vàng
            </Button>
          )}
        </div>
      </div>

      {/* Modal xác nhận an toàn */}
      {pending?.kind === "command" && (
        <SafetyConfirmModal
          open
          onClose={() => setPending(null)}
          title={pending.title}
          intersectionName={snap.name}
          intersectionCode={snap.code}
          description={pending.description}
          steps={pending.steps}
          checks={checks}
          warning={pending.warning}
          tone={pending.tone}
          requireReason={pending.requireReason}
          requireCode={pending.requireCode}
          confirmLabel={pending.confirmLabel}
          onConfirm={(reason) => run(`/signals/${iid}/command`, { command: pending.command, params: pending.params, reason: reason || undefined }, pending.title)}
        />
      )}
      {pending?.kind === "mode" && (
        <SafetyConfirmModal
          open
          onClose={() => setPending(null)}
          title={`Chuyển ${MODE_LABEL[sig.mode]} → ${MODE_LABEL[pending.mode]}`}
          intersectionName={snap.name}
          intersectionCode={snap.code}
          description={
            pending.mode === "MANUAL"
              ? "Pha hiện tại tiếp tục an toàn và sẽ được giữ xanh cho đến khi bạn ra lệnh chuyển pha. Thuật toán AI ngừng áp dụng kế hoạch."
              : pending.mode === "AUTO"
                ? "Thuật toán Webster thích ứng sẽ tính thời gian xanh từ hàng đợi camera; kế hoạch mới áp dụng từ pha xanh kế tiếp."
                : `Nút giao chạy kế hoạch cố định: Bắc–Nam ${sig.fixed_plan.green_ns}s / Đông–Tây ${sig.fixed_plan.green_ew}s từ pha xanh kế tiếp.`
          }
          steps={[
            { label: `${sig.phase_name} — ${INTERVAL_LABEL[sig.interval]} tiếp tục`, detail: "Không cắt ngang trạng thái đèn hiện tại", tone: "info" },
            pending.mode === "MANUAL"
              ? { label: "Giữ pha xanh đến khi có lệnh", tone: "green" }
              : { label: `Áp dụng thời gian ${pending.mode === "AUTO" ? "AI" : "cố định"} ở pha xanh kế tiếp`, tone: "green" },
          ]}
          checks={checks}
          tone={pending.mode === "MANUAL" ? "manual" : "auto"}
          requireReason={pending.mode === "MANUAL"}
          confirmLabel={`Chuyển sang ${MODE_LABEL[pending.mode]}`}
          onConfirm={(reason) => run(`/signals/${iid}/mode`, { mode: pending.mode, reason: reason || undefined }, "Chuyển chế độ")}
        />
      )}
      {pending?.kind === "recover" && (
        <SafetyConfirmModal
          open
          onClose={() => setPending(null)}
          title={`Khôi phục FAILSAFE → ${MODE_LABEL[pending.mode]}`}
          intersectionName={snap.name}
          intersectionCode={snap.code}
          description="Chỉ khôi phục khi toàn bộ camera, bộ điều khiển và thuật toán phân tích đã hoạt động bình thường. Hệ thống sẽ kiểm tra lại trước khi thực thi."
          steps={[
            ...(sig.interval === "FLASHING_YELLOW" ? previewFlash(sig, false) : [{ label: "Pha hiện tại tiếp tục", tone: "info" as const }]),
            { label: `Mở khoá chế độ ${MODE_LABEL[pending.mode]}`, tone: "green" },
          ]}
          checks={[
            { label: "Camera 4 hướng hoạt động", ok: !snap.health_issues.some((h) => h.startsWith("Camera")) },
            { label: "Bộ điều khiển đèn phản hồi", ok: ctlOnline },
            { label: "Thuật toán AI hoạt động", ok: !snap.sim.vision_fault },
          ]}
          warning={snap.health_issues.length ? `Còn sự cố: ${snap.health_issues.join("; ")} — lệnh khôi phục sẽ bị từ chối.` : null}
          tone="danger"
          requireReason
          requireCode
          confirmLabel="Khôi phục hệ thống"
          onConfirm={(reason) => run(`/signals/${iid}/recover`, { mode: pending.mode, reason }, "Khôi phục FAILSAFE")}
        />
      )}
      {timing && (
        <SafetyConfirmModal
          open
          onClose={() => setTiming(null)}
          title="Điều chỉnh thời gian pha (kế hoạch cố định)"
          intersectionName={snap.name}
          intersectionCode={snap.code}
          description={`Thiết lập thời gian xanh cho kế hoạch cố định / FAILSAFE của phiên vận hành hiện tại. Giá trị được kẹp trong [${t.min_green}–${t.max_green}]s; áp dụng từ pha xanh kế tiếp.`}
          extra={
            <div className="grid grid-cols-2 gap-2">
              <Field label="Xanh Bắc–Nam (s)">
                <Input type="number" min={t.min_green} max={t.max_green} value={timing.ns} onChange={(e) => setTiming({ ...timing, ns: e.target.value })} />
              </Field>
              <Field label="Xanh Đông–Tây (s)">
                <Input type="number" min={t.min_green} max={t.max_green} value={timing.ew} onChange={(e) => setTiming({ ...timing, ew: e.target.value })} />
              </Field>
              <p className="num col-span-2 text-2xs text-ink-mute">
                Chu kỳ = {Number(timing.ns) + Number(timing.ew) + 2 * (t.yellow + t.all_red)}s (gồm 2 × (vàng {t.yellow}s + đỏ {t.all_red}s))
              </p>
            </div>
          }
          steps={[{ label: "Pha hiện tại không bị ảnh hưởng", tone: "info" }, { label: "Áp dụng ở pha xanh kế tiếp", tone: "green" }]}
          checks={checks}
          tone="auto"
          confirmLabel="Áp dụng thời gian"
          onConfirm={(reason) =>
            run(`/signals/${iid}/command`, { command: "SET_TIMING", params: { green_ns: Number(timing.ns), green_ew: Number(timing.ew) }, reason: reason || undefined }, "Điều chỉnh thời gian pha")
          }
        />
      )}
      <div className="mt-3 flex items-center gap-1.5 text-2xs text-ink-mute">
        <Clock4 className="h-3 w-3 shrink-0" />
        <span>
          Ràng buộc: xanh {t.min_green}–{t.max_green}s · chu kỳ {t.cycle_min}–{t.cycle_max}s · FAILSAFE: {sig.failsafe_strategy === "FLASHING_YELLOW" ? "chớp vàng" : "chu kỳ cố định"}
        </span>
      </div>
    </Panel>
  );
}
