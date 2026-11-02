import clsx from "clsx";
import { CheckCircle2, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { SignalState } from "@/lib/types";
import { INTERVAL_LABEL, PHASE_LABEL } from "@/lib/format";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/primitives";
import { Input, Textarea } from "../ui/Form";

export interface SafetyStep {
  label: string;
  detail?: string;
  tone: "wait" | "yellow" | "red" | "green" | "flash" | "info";
}

const TONE: Record<SafetyStep["tone"], string> = {
  wait: "#94A3B8",
  yellow: "#F59E0B",
  red: "#EF4444",
  green: "#10B981",
  flash: "#F59E0B",
  info: "#3B82F6",
};

/** Dự báo trình tự chuyển pha an toàn phía client (backend vẫn là nơi kiểm tra cuối cùng). */
export function previewGoto(sig: SignalState, target: number): SafetyStep[] {
  const t = sig.timing;
  const steps: SafetyStep[] = [];
  if (sig.interval === "FLASHING_YELLOW") {
    steps.push({ label: "Thoát chớp vàng", tone: "flash" });
    steps.push({ label: `Toàn đỏ ${t.all_red}s`, detail: "Giải phóng nút giao", tone: "red" });
  } else if (sig.interval === "GREEN") {
    if (sig.phase_id === target) {
      return [{ label: `${PHASE_LABEL[target]} đang xanh`, detail: "Không cần chuyển pha", tone: "green" }];
    }
    const left = Math.max(0, t.min_green - sig.elapsed);
    if (left > 0.05) {
      steps.push({
        label: `Chờ đủ xanh tối thiểu: còn ${left.toFixed(1)}s`,
        detail: `Đã xanh ${sig.elapsed.toFixed(1)}s / tối thiểu ${t.min_green}s — lệnh được xếp lịch, không cắt ngắn`,
        tone: "wait",
      });
    }
    steps.push({ label: `Vàng chuyển tiếp ${t.yellow}s`, detail: PHASE_LABEL[sig.phase_id], tone: "yellow" });
    steps.push({ label: `Toàn đỏ ${t.all_red}s`, detail: "Tất cả hướng dừng", tone: "red" });
  } else {
    steps.push({ label: `Hoàn tất ${INTERVAL_LABEL[sig.interval].toLowerCase()} đang diễn ra`, detail: "Không thể huỷ khoảng chuyển tiếp", tone: sig.interval === "YELLOW_CLEARANCE" ? "yellow" : "red" });
    if (sig.interval === "YELLOW_CLEARANCE") steps.push({ label: `Toàn đỏ ${t.all_red}s`, tone: "red" });
  }
  steps.push({ label: `${PHASE_LABEL[target]} bật xanh`, tone: "green" });
  return steps;
}

export function previewFlash(sig: SignalState, on: boolean): SafetyStep[] {
  const t = sig.timing;
  if (!on) return [{ label: "Thoát chớp vàng", tone: "flash" }, { label: `Toàn đỏ ${t.all_red}s`, tone: "red" }, { label: `${PHASE_LABEL[sig.next_phase_id]} bật xanh`, tone: "green" }];
  const steps: SafetyStep[] = [];
  if (sig.interval === "GREEN") {
    const left = Math.max(0, t.min_green - sig.elapsed);
    if (left > 0.05) steps.push({ label: `Chờ đủ xanh tối thiểu: còn ${left.toFixed(1)}s`, tone: "wait" });
    steps.push({ label: `Vàng chuyển tiếp ${t.yellow}s`, tone: "yellow" });
  }
  if (sig.interval !== "ALL_RED_CLEARANCE") steps.push({ label: `Toàn đỏ ${t.all_red}s`, tone: "red" });
  steps.push({ label: "Chớp vàng tất cả hướng", detail: "Người tham gia giao thông tự quan sát, nhường đường", tone: "flash" });
  return steps;
}

export function SafetyConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  intersectionName,
  intersectionCode,
  description,
  steps,
  checks,
  warning,
  requireReason,
  requireCode,
  confirmLabel,
  tone = "auto",
  extra,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
  title: string;
  intersectionName: string;
  intersectionCode: string;
  description: ReactNode;
  steps: SafetyStep[];
  checks?: { label: string; ok: boolean }[];
  warning?: string | null;
  requireReason?: boolean;
  requireCode?: boolean;
  confirmLabel: string;
  tone?: "auto" | "manual" | "danger";
  extra?: ReactNode;
}) {
  const [reason, setReason] = useState("");
  const [ack, setAck] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) {
      setReason("");
      setAck(false);
      setCode("");
      setBusy(false);
    }
  }, [open]);

  const ready = ack && (!requireReason || reason.trim().length >= 3) && (!requireCode || code.trim().toUpperCase() === intersectionCode.toUpperCase());

  const submit = async () => {
    if (!ready) return;
    setBusy(true);
    try {
      await onConfirm(reason.trim());
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onClose}
      tone={tone}
      width={560}
      icon={<ShieldCheck className={clsx("h-4 w-4", tone === "danger" ? "text-stop" : tone === "manual" ? "text-manual" : "text-auto")} />}
      title={`Xác nhận an toàn · ${title}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Huỷ thao tác
          </Button>
          <Button variant={tone === "danger" ? "danger" : tone === "manual" ? "manual" : "primary"} disabled={!ready} loading={busy} onClick={submit}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <div className="text-xs text-ink-mute">{intersectionName}</div>
          <div className="mt-1 text-sm leading-relaxed text-ink-dim">{description}</div>
        </div>

        <div>
          <div className="mb-2 text-xs font-medium text-ink-dim">Trình tự sẽ thực hiện (do khoá an toàn chèn tự động)</div>
          <ol className="relative space-y-0">
            {steps.map((s, i) => (
              <li key={i} className="relative flex gap-3 pb-3 last:pb-0">
                {i < steps.length - 1 && <span className="absolute left-[7px] top-4 h-full w-px bg-line" />}
                <span
                  className={clsx("relative mt-0.5 h-[15px] w-[15px] shrink-0 rounded-full border-2", s.tone === "flash" && "animate-blink")}
                  style={{ borderColor: TONE[s.tone], background: `${TONE[s.tone]}33` }}
                />
                <div>
                  <div className="text-[13px] font-medium">{s.label}</div>
                  {s.detail && <div className="text-2xs text-ink-mute">{s.detail}</div>}
                </div>
              </li>
            ))}
          </ol>
        </div>

        {checks && checks.length > 0 && (
          <ul className="grid gap-1.5 rounded-ctl border border-line bg-carbon p-2.5 sm:grid-cols-2">
            {checks.map((c) => (
              <li key={c.label} className="flex items-center gap-2 text-xs">
                {c.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-go" /> : <TriangleAlert className="h-3.5 w-3.5 text-warn" />}
                <span className={c.ok ? "text-ink-dim" : "text-warn-ink"}>{c.label}</span>
              </li>
            ))}
          </ul>
        )}

        {warning && (
          <div className="flex gap-2 rounded-ctl border border-warn/50 bg-warn/10 p-2.5 text-xs text-warn-ink">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {warning}
          </div>
        )}

        {extra}

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-ink-dim">
            Lý do thao tác {requireReason ? <span className="text-stop">(bắt buộc)</span> : <span className="text-ink-mute">(ghi vào nhật ký)</span>}
          </span>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="vd: Xe cứu thương hướng Bắc, ùn tắc kéo dài trục Đông–Tây…" />
        </label>

        {requireCode && (
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-dim">
              Gõ mã nút giao <span className="num text-ink">{intersectionCode}</span> để xác nhận thao tác rủi ro cao
            </span>
            <Input value={code} onChange={(e) => setCode(e.target.value)} className="num" autoComplete="off" />
          </label>
        )}

        <label className="flex cursor-pointer items-start gap-2.5 rounded-ctl border border-line p-2.5 text-xs text-ink-dim hover:border-ink-mute">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[rgb(var(--c-auto))]" data-autofocus />
          Tôi đã quan sát camera hiện trường, hiểu trình tự chuyển pha ở trên và chịu trách nhiệm với thao tác này.
        </label>
      </div>
    </Modal>
  );
}
