import { Check, Play, RotateCcw, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Badge, Button, Panel, Segmented } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api } from "@/lib/api";
import type { LlmMode, LlmStatus, Snapshot } from "@/lib/types";

export const LLM_STATUS: Record<LlmStatus, { label: string; color: string }> = {
  APPLIED: { label: "Đã áp dụng", color: "#10B981" },
  APPROVED: { label: "Đã duyệt", color: "#10B981" },
  PENDING: { label: "Chờ duyệt", color: "#F59E0B" },
  REJECTED: { label: "Bị từ chối", color: "#94A3B8" },
  EXPIRED: { label: "Hết hạn", color: "#94A3B8" },
  INVALID: { label: "Sai schema – chặn", color: "#EF4444" },
  ERROR: { label: "Lỗi gọi LLM", color: "#EF4444" },
  SKIPPED: { label: "Bỏ qua", color: "#94A3B8" },
};

export const STRATEGY_LABEL: Record<string, string> = {
  BALANCED: "Cân bằng hai trục",
  PRIORITIZE_NS: "Ưu tiên trục Bắc–Nam",
  PRIORITIZE_EW: "Ưu tiên trục Đông–Tây",
  PEAK_HOUR: "Giờ cao điểm – ưu tiên trục chính",
  INCIDENT_MODE: "Bất thường – giữ cân bằng thận trọng",
};

const MODE_HINT: Record<LlmMode, string> = {
  OFF: "Chỉ dùng thuật toán Webster (tầng 2).",
  ADVISORY: "LLM đề xuất chiến lược, người vận hành duyệt trước khi áp dụng.",
  AUTONOMOUS: "LLM tự áp dụng chiến lược; Webster và bộ khoá an toàn vẫn kiểm soát mọi lệnh.",
};

function WeightBar({ label, w }: { label: string; w: number }) {
  // 0.5 → 2.0, 1.0 là trung lập (vạch giữa ở 1/3)
  const pct = ((w - 0.5) / 1.5) * 100;
  const neutral = (0.5 / 1.5) * 100;
  const color = w > 1.02 ? "#8B5CF6" : w < 0.98 ? "#94A3B8" : "#64748B";
  return (
    <div className="min-w-0">
      <div className="flex justify-between text-2xs font-semibold text-ink-mute">
        <span>{label}</span>
        <span className="num font-bold text-ink">×{w.toFixed(2)}</span>
      </div>
      <div className="relative mt-1 h-2 rounded-full bg-carbon ring-1 ring-line/50">
        <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
        <div className="absolute -top-0.5 h-3 w-px bg-ink-mute" style={{ left: `${neutral}%` }} title="Trung lập ×1.0" />
      </div>
    </div>
  );
}

/** Tầng 3 — LLM Supervisor (Groq): chế độ, chiến lược hiệu lực, đề xuất chờ duyệt và quyết định gần nhất. */
export function LlmSupervisorCard({ snap }: { snap: Snapshot }) {
  const llm = snap.llm;
  const { can } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmAuto, setConfirmAuto] = useState(false);
  const canAct = can("llm:supervise");
  const iid = snap.intersection_id;

  async function call(key: string, fn: () => Promise<unknown>, ok?: string) {
    setBusy(key);
    try {
      await fn();
      if (ok) toast("success", ok);
    } catch (e) {
      toast("error", "Thao tác LLM thất bại", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const setMode = (mode: LlmMode, confirm = false) =>
    call("mode", () => api.post(`/llm/${iid}/mode`, { mode, confirm }), `LLM Supervisor: ${mode === "OFF" ? "đã tắt" : mode === "ADVISORY" ? "chế độ Tư vấn" : "chế độ Tự động"}`);

  if (!llm) return null;
  const last = llm.last;
  const pending = llm.pending;
  const autoOk = snap.signal.mode === "AUTO";

  return (
    <Panel
      title="LLM Supervisor (tầng 3)"
      icon={<Sparkles className="h-4 w-4 text-[#8B5CF6]" />}
      actions={
        llm.enabled ? (
          <Badge color="#8B5CF6" title={llm.model}>Groq · {llm.model.split("-").slice(0, 2).join("-")}</Badge>
        ) : (
          <Badge color="#94A3B8" title="Đặt GROQ_API_KEY trong backend/.env">Chưa có khoá Groq</Badge>
        )
      }
    >
      <div className="space-y-3">
        {/* Chế độ */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Segmented<LlmMode>
            size="sm"
            value={llm.mode}
            onChange={(m) => (m === "AUTONOMOUS" ? setConfirmAuto(true) : setMode(m))}
            options={[
              { id: "OFF", label: "Tắt" },
              { id: "ADVISORY", label: "Tư vấn" },
              { id: "AUTONOMOUS", label: "Tự động" },
            ]}
            disabled={!canAct || busy === "mode"}
          />
          <div className="flex gap-1.5">
            {canAct && (
              <Button
                size="sm"
                variant="secondary"
                icon={<Play className="h-3.5 w-3.5" />}
                loading={busy === "run" || llm.running}
                disabled={!llm.enabled || !autoOk || !!pending || llm.mode === "OFF"}
                title={!autoOk ? "Chỉ chạy khi nút giao ở chế độ AUTO" : "Gọi LLM phân tích ngay"}
                onClick={() => call("run", () => api.post(`/llm/${iid}/run`))}
              >
                Phân tích ngay
              </Button>
            )}
            {canAct && llm.strategy !== "BALANCED" && (
              <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} loading={busy === "reset"}
                onClick={() => call("reset", () => api.post(`/llm/${iid}/reset`), "Đã đặt lại về cân bằng")}>
                Cân bằng
              </Button>
            )}
          </div>
        </div>
        <p className="text-2xs text-ink-mute">
          {!llm.enabled ? (
            <span className="text-warn-ink">LLM đang tắt: đặt <code className="num">GROQ_API_KEY</code> trong <code className="num">backend/.env</code> rồi khởi động lại backend. Webster vẫn điều khiển bình thường.</span>
          ) : (
            MODE_HINT[llm.mode]
          )}
          {llm.enabled && !autoOk && llm.mode !== "OFF" && <span className="font-semibold text-warn-ink"> Tạm dừng: nút giao đang {snap.signal.mode}.</span>}
          {llm.enabled && autoOk && llm.mode !== "OFF" && llm.next_run_in_s != null && !pending && (
            <span className="num"> Lần phân tích kế tiếp ≤ {llm.next_run_in_s}s (hoặc sớm hơn khi có sự kiện ùn tắc).</span>
          )}
        </p>

        {/* Đề xuất chờ duyệt */}
        {pending && (
          <div className="rounded-ctl border border-warn/50 bg-warn/10 p-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-bold text-ink">Đề xuất chờ duyệt #{pending.id}</div>
              <span className="num text-2xs text-ink-mute">hết hạn sau {pending.expires_in_s}s</span>
            </div>
            <div className="mt-1 text-xs text-ink-dim">
              <b className="text-ink">{STRATEGY_LABEL[pending.strategy] ?? pending.strategy}</b> · B–N ×{pending.weight_ns.toFixed(2)} / Đ–T ×{pending.weight_ew.toFixed(2)} · {pending.duration_min} phút
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-dim">{pending.reason}</p>
            {pending.guard_notes && <p className="mt-1 text-2xs text-warn-ink">Lớp kiểm tra: {pending.guard_notes}</p>}
            {canAct && (
              <div className="mt-2 flex gap-1.5">
                <Button size="sm" variant="success" icon={<Check className="h-3.5 w-3.5" />} loading={busy === "approve"} disabled={!autoOk}
                  onClick={() => call("approve", () => api.post(`/llm/${iid}/decisions/${pending.id}/approve`), "Đã duyệt chiến lược LLM")}>
                  Duyệt & áp dụng
                </Button>
                <Button size="sm" variant="ghost" icon={<X className="h-3.5 w-3.5" />} loading={busy === "reject"}
                  onClick={() => call("reject", () => api.post(`/llm/${iid}/decisions/${pending.id}/reject`), "Đã từ chối đề xuất")}>
                  Từ chối
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Chiến lược đang hiệu lực */}
        <div className="rounded-ctl border border-line/70 bg-panel/20 p-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="label">Chiến lược đang hiệu lực</div>
            <span className="num text-2xs text-ink-mute">
              {llm.expires_in_s != null ? `còn ${Math.floor(llm.expires_in_s / 60)}:${String(llm.expires_in_s % 60).padStart(2, "0")}` : "mặc định"}
            </span>
          </div>
          <div className="mt-1 text-[13px] font-bold text-ink">{llm.strategy_label}</div>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <WeightBar label="Trọng số Bắc–Nam" w={llm.weight_ns} />
            <WeightBar label="Trọng số Đông–Tây" w={llm.weight_ew} />
          </div>
          {llm.reason && <p className="mt-2 text-xs leading-relaxed text-ink-dim">{llm.reason}</p>}
          {llm.source && <p className="mt-1 text-2xs text-ink-mute">Nguồn: {llm.source}</p>}
        </div>

        {/* Quyết định gần nhất */}
        {last && (
          <div className="flex items-start gap-2 text-2xs text-ink-mute">
            <Badge color={LLM_STATUS[last.status].color}>{LLM_STATUS[last.status].label}</Badge>
            <span className="min-w-0 flex-1">
              Lần gọi gần nhất ({last.trigger === "EVENT" ? "do sự kiện" : last.trigger === "MANUAL" ? "thủ công" : "định kỳ"}
              {last.latency_ms != null && <span className="num">, {Math.round(last.latency_ms)} ms</span>})
              {last.guard_notes && <>: {last.guard_notes}</>}
            </span>
          </div>
        )}
        {llm.last_error && !last?.guard_notes && <p className="text-2xs text-stop-ink">{llm.last_error}</p>}
      </div>

      <Modal
        open={confirmAuto}
        onClose={() => setConfirmAuto(false)}
        title="Bật LLM Supervisor chế độ Tự động?"
        icon={<Sparkles className="h-4 w-4 text-[#8B5CF6]" />}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmAuto(false)}>Huỷ</Button>
            <Button variant="primary" loading={busy === "mode"} onClick={async () => { await setMode("AUTONOMOUS", true); setConfirmAuto(false); }}>
              Xác nhận bật
            </Button>
          </>
        }
      >
        <ul className="list-disc space-y-1.5 pl-5 text-[13px] text-ink-dim">
          <li>LLM sẽ tự đổi chiến lược và trọng số ưu tiên 2 trục mà không cần duyệt.</li>
          <li>LLM <b>không</b> đặt thời gian pha: Webster vẫn tính chu kỳ, trọng số bị kẹp 0.5–2.0, mỗi lần đổi tối đa ±0.5.</li>
          <li>Bộ khoá an toàn (vàng ≥ 3s, toàn đỏ ≥ 2s, xanh tối thiểu) và FAILSAFE luôn có quyền phủ quyết.</li>
          <li>LLM lỗi hoặc trả sai định dạng → giữ chiến lược hiện tại, mọi quyết định được ghi nhật ký.</li>
        </ul>
      </Modal>
    </Panel>
  );
}
