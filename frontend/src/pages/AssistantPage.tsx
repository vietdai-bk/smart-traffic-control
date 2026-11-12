import clsx from "clsx";
import {
  ArrowDown,
  Bot,
  Check,
  ChevronDown,
  Copy,
  Download,
  FileText,
  History,
  Loader2,
  Printer,
  Send,
  Sparkles,
  Square,
  SquarePen,
  User2,
  Wrench,
  X,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { LLM_STATUS } from "@/components/live/LlmSupervisorCard";
import { Select } from "@/components/ui/Form";
import { Markdown } from "@/components/ui/Markdown";
import { Badge, Button, Empty, Pager, Panel, Segmented, Spinner, Tabs } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";
import { useToast } from "@/context/ToastContext";
import { api, qs, streamPost } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { AssistantAction, ChatStreamEvent, LlmDecision, ReportStreamEvent } from "@/lib/types";
import { useDevice } from "@/lib/useMedia";

interface LlmInfo {
  provider: string;
  configured: boolean;
  model: string;
  interval_s: number;
}

const TOOL_LABEL: Record<string, string> = {
  list_intersections: "Danh sách nút giao",
  get_intersection_status: "Trạng thái thời gian thực",
  query_traffic_stats: "Thống kê lưu lượng",
  list_active_alerts: "Cảnh báo & sự cố",
  get_llm_decisions: "Quyết định LLM",
  get_signal_history: "Lịch sử lệnh đèn",
  propose_action: "Tạo đề xuất điều khiển",
};

/**
 * Hiệu ứng "đánh máy" như ChatGPT: văn bản về theo cụm (Groq rất nhanh) được nhả dần từng vài ký tự mỗi khung hình.
 * Tốc độ tự thích ứng với lượng chữ còn tồn để không bao giờ chậm hơn mạng quá nhiều.
 */
function useTypewriter() {
  const full = useRef("");
  const [shown, setShown] = useState(0);
  const raf = useRef<number | null>(null);
  const tick = useCallback(() => {
    setShown((n) => {
      const left = full.current.length - n;
      if (left <= 0) {
        raf.current = null;
        return n;
      }
      raf.current = requestAnimationFrame(tick);
      return n + Math.max(1, Math.ceil(left / 14));
    });
  }, []);
  const push = useCallback(
    (t: string) => {
      full.current += t;
      if (raf.current == null) raf.current = requestAnimationFrame(tick);
    },
    [tick],
  );
  const reset = useCallback(() => {
    full.current = "";
    if (raf.current != null) cancelAnimationFrame(raf.current);
    raf.current = null;
    setShown(0);
  }, []);
  useEffect(
    () => () => {
      if (raf.current != null) cancelAnimationFrame(raf.current);
    },
    [],
  );
  return { text: full.current.slice(0, shown), full, caughtUp: shown >= full.current.length, push, reset };
}

function Caret() {
  return <span className="ml-0.5 inline-block h-[1.05em] w-[7px] translate-y-[2px] animate-caret rounded-[1px] bg-[#8B5CF6] align-baseline" aria-hidden />;
}

function useAutoScroll(dep: unknown) {
  const box = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  useEffect(() => {
    const el = box.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [dep, atBottom]);
  const onScroll = () => {
    const el = box.current;
    if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };
  const toBottom = () => {
    const el = box.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    setAtBottom(true);
  };
  return { box, atBottom, onScroll, toBottom };
}

function IntersectionSelect({ value, onChange }: { value: number | null; onChange: (id: number) => void }) {
  const { summary } = useLive();
  return (
    <Select value={value ?? ""} onChange={(e) => onChange(Number(e.target.value))} className="h-9 w-full text-xs sm:max-w-[300px]" aria-label="Chọn nút giao">
      {summary.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </Select>
  );
}

// ------------------------------------------------------------------------------------------- Chat
type ToolStep = { tool: string; ok?: boolean };
interface Msg {
  role: "user" | "assistant";
  content: string;
  tools?: ToolStep[];
  actions?: (AssistantAction & { state?: "done" | "cancelled" | "failed"; result?: string })[];
  meta?: string;
  error?: boolean;
  stopped?: boolean;
}

const STORE = "stcs.assistant.chat";

function ToolChips({ tools, live }: { tools: ToolStep[]; live?: boolean }) {
  if (!tools.length) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {tools.map((t, j) => (
        <span
          key={j}
          className={clsx(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-2xs",
            t.ok === false ? "border-stop/40 text-stop-ink" : t.ok ? "border-line/70 text-ink-mute" : "border-[#8B5CF6]/50 text-[#8B5CF6]",
          )}
        >
          {t.ok === undefined && live ? <Loader2 className="h-3 w-3 animate-spin" /> : t.ok === false ? <X className="h-3 w-3" /> : <Check className="h-3 w-3" />}
          {TOOL_LABEL[t.tool] ?? t.tool}
        </span>
      ))}
    </div>
  );
}

function ActionCard({ a, onDone }: { a: NonNullable<Msg["actions"]>[number]; onDone: (state: "done" | "cancelled" | "failed", result: string) => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<"ok" | "cancel" | null>(null);
  const settled = a.state != null;
  async function confirm() {
    setBusy("ok");
    try {
      const r = await api.post<{ ok: boolean; message: string }>(`/llm/assistant/actions/${a.id}/confirm`);
      onDone(r.ok ? "done" : "failed", r.message);
      toast(r.ok ? "success" : "error", r.ok ? "Đã thực thi lệnh" : "Lệnh bị từ chối", r.message);
    } catch (e) {
      onDone("failed", (e as Error).message);
      toast("error", "Không thực thi được", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  async function cancel() {
    setBusy("cancel");
    await api.post(`/llm/assistant/actions/${a.id}/cancel`).catch(() => undefined);
    onDone("cancelled", "Đã huỷ");
    setBusy(null);
  }
  return (
    <div className={clsx("mt-3 rounded-ctl border p-3", settled ? "border-line/60 bg-panel/20" : "border-manual/50 bg-manual/10")}>
      <div className="flex items-center gap-2 text-xs font-bold text-ink">
        <Wrench className="h-3.5 w-3.5 shrink-0 text-manual" />
        <span className="min-w-0 truncate">Đề xuất điều khiển · {a.intersection}</span>
      </div>
      <div className="mt-1 text-[13px] font-semibold text-ink">{a.summary}</div>
      {a.reason && <div className="mt-0.5 text-xs text-ink-dim">Lý do: {a.reason}</div>}
      {settled ? (
        <div className={clsx("mt-1.5 text-xs font-semibold", a.state === "done" ? "text-go-ink" : a.state === "failed" ? "text-stop-ink" : "text-ink-mute")}>
          {a.state === "done" ? "✓ " : a.state === "failed" ? "✕ " : ""}
          {a.result}
        </div>
      ) : (
        <>
          <p className="mt-1.5 text-2xs text-ink-mute">Lệnh chưa được thực thi. Khi xác nhận, lệnh đi qua bộ khoá an toàn (vàng → toàn đỏ → pha mới) và được ghi nhật ký.</p>
          <div className="mt-2 flex flex-col gap-1.5 sm:flex-row">
            <Button variant="manual" icon={<Check className="h-3.5 w-3.5" />} loading={busy === "ok"} onClick={confirm} className="max-sm:h-11">
              Xác nhận thực thi
            </Button>
            <Button variant="ghost" icon={<X className="h-3.5 w-3.5" />} loading={busy === "cancel"} onClick={cancel} className="max-sm:h-11">
              Huỷ
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function CopyBtn({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(text).then(() => {
          setOk(true);
          window.setTimeout(() => setOk(false), 1500);
        });
      }}
      className="inline-flex h-7 items-center gap-1 rounded-ctl px-1.5 text-2xs text-ink-mute transition-colors hover:bg-panel hover:text-ink"
      aria-label="Sao chép câu trả lời"
    >
      {ok ? <Check className="h-3.5 w-3.5 text-go" /> : <Copy className="h-3.5 w-3.5" />}
      {ok ? "Đã chép" : "Chép"}
    </button>
  );
}

function ChatTab({ info }: { info: LlmInfo | null }) {
  const { selectedId } = useLive();
  const { can } = useAuth();
  const device = useDevice();
  const [msgs, setMsgs] = useState<Msg[]>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(STORE) ?? "[]") as Msg[];
    } catch {
      return [];
    }
  });
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [live, setLive] = useState<Msg | null>(null); // tin nhắn đang sinh
  const tw = useTypewriter();
  const abort = useRef<AbortController | null>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const scroll = useAutoScroll(`${msgs.length}-${tw.text.length}-${live?.tools?.length}`);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-40)));
    } catch {
      /* bỏ qua */
    }
  }, [msgs]);

  // Chốt tin nhắn khi luồng đã xong VÀ hiệu ứng đánh máy đã bắt kịp
  useEffect(() => {
    if (!streaming && live && tw.caughtUp) {
      const finalText = tw.full.current || live.content; // lấy trước khi reset — updater của setState chạy trễ
      setMsgs((cur) => [...cur, { ...live, content: finalText }]);
      setLive(null);
      tw.reset();
    }
  }, [streaming, live, tw]);

  // Ô nhập tự giãn theo nội dung
  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, device === "phone" ? 120 : 200)}px`;
  }, [text, device]);

  const suggestions = [
    "Tình hình nút giao đang chọn thế nào? Hướng nào đông nhất?",
    "Thống kê lưu lượng 24 giờ qua theo hướng",
    "Có cảnh báo hay sự cố thiết bị nào đang mở không?",
    "LLM Supervisor đã quyết định gì gần đây và vì sao?",
    ...(can("llm:supervise") ? ["Ưu tiên trục Đông–Tây trong 10 phút vì đang ùn ứ"] : []),
  ];

  async function send(content: string) {
    const q = content.trim();
    if (!q || streaming) return;
    const history = [...msgs, { role: "user" as const, content: q }];
    setMsgs(history);
    setText("");
    tw.reset();
    setLive({ role: "assistant", content: "", tools: [], actions: [] });
    setStreaming(true);
    scroll.toBottom();
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      await streamPost<ChatStreamEvent>(
        "/llm/assistant/chat/stream",
        { messages: history.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content })), intersection_id: selectedId },
        (e) => {
          if (e.type === "delta") tw.push(e.text);
          else if (e.type === "tool_start") setLive((m) => m && { ...m, tools: [...(m.tools ?? []), { tool: e.tool }] });
          else if (e.type === "tool")
            setLive((m) => {
              if (!m) return m;
              const tools = [...(m.tools ?? [])];
              const i = tools.map((t) => t.tool).lastIndexOf(e.tool);
              if (i >= 0) tools[i] = { tool: e.tool, ok: e.ok };
              else tools.push({ tool: e.tool, ok: e.ok });
              return { ...m, tools };
            });
          else if (e.type === "action") setLive((m) => m && { ...m, actions: [...(m.actions ?? []), e.action] });
          else if (e.type === "done") setLive((m) => m && { ...m, meta: `${e.model} · ${(e.latency_ms / 1000).toFixed(1)}s` });
          else if (e.type === "error") setLive((m) => m && { ...m, error: !tw.full.current, content: e.message, meta: `Lỗi: ${e.message}` });
        },
        ctrl.signal,
      );
    } catch (e) {
      if ((e as Error).name === "AbortError") setLive((m) => m && { ...m, stopped: true, meta: "Đã dừng" });
      else setLive((m) => m && { ...m, error: true, content: (e as Error).message });
    } finally {
      abort.current = null;
      setStreaming(false);
    }
  }

  const stop = () => abort.current?.abort();
  const settle = (mi: number, ai: number, state: "done" | "cancelled" | "failed", result: string) =>
    setMsgs((cur) => cur.map((m, i) => (i !== mi ? m : { ...m, actions: m.actions?.map((a, j) => (j === ai ? { ...a, state, result } : a)) })));

  const renderAssistant = (m: Msg, body: string, isLive: boolean, mi: number) => (
    <div className="flex gap-2.5 sm:gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#8B5CF6]/15 text-[#8B5CF6]">
        <Bot className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        <ToolChips tools={m.tools ?? []} live={isLive} />
        {m.error ? (
          <div className="rounded-ctl border border-stop/40 bg-stop/10 px-3 py-2 text-xs text-stop-ink">{m.content}</div>
        ) : body ? (
          <div className="relative">
            <Markdown text={body} />
            {isLive && (streaming || !tw.caughtUp) && <Caret />}
          </div>
        ) : isLive ? (
          <div className="flex items-center gap-2 py-1 text-xs text-ink-mute">
            {(m.tools?.length ?? 0) > 0 ? "Đang phân tích dữ liệu…" : "Đang suy nghĩ…"}
            <Caret />
          </div>
        ) : null}
        {m.actions?.map((a, j) => <ActionCard key={a.id} a={a} onDone={(s, r) => !isLive && settle(mi, j, s, r)} />)}
        {!isLive && (m.meta || body) && (
          <div className="mt-1 flex items-center gap-1">
            {body && !m.error && <CopyBtn text={body} />}
            {m.meta && <span className="num text-2xs text-ink-mute">{m.meta}</span>}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <Panel
      title="Trợ lý vận hành"
      icon={<Bot className="h-4 w-4 text-[#8B5CF6]" />}
      actions={
        (msgs.length > 0 || live) && (
          <Button size="sm" variant="ghost" icon={<SquarePen className="h-3.5 w-3.5" />} disabled={streaming} onClick={() => setMsgs([])}>
            <span className="hidden sm:inline">Cuộc trò chuyện mới</span>
            <span className="sm:hidden">Mới</span>
          </Button>
        )
      }
      bodyClassName="flex flex-col p-0"
    >
      <div className="relative flex h-[calc(100dvh-var(--header-h,57px)-190px)] min-h-[380px] flex-col md:h-[calc(100dvh-var(--header-h,57px)-150px)]">
        <div ref={scroll.box} onScroll={scroll.onScroll} className="flex-1 overflow-y-auto overscroll-contain">
          <div className="mx-auto w-full max-w-3xl space-y-5 px-3 py-4 sm:px-5">
            {msgs.length === 0 && !live && (
              <div className="py-4 text-center sm:py-8">
                <Sparkles className="mx-auto h-8 w-8 text-[#8B5CF6]" />
                <p className="mt-2 text-sm font-semibold text-ink">Hỏi về tình hình giao thông, thống kê, cảnh báo — hoặc yêu cầu thao tác điều khiển.</p>
                <p className="mx-auto mt-1 max-w-lg text-xs text-ink-mute">
                  Trợ lý tra cứu số liệu thật qua công cụ của hệ thống. Mọi thao tác điều khiển chỉ là <b>đề xuất</b> và cần bạn xác nhận.
                </p>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      disabled={!info?.configured}
                      className="rounded-ctl border border-line/80 bg-panel/30 px-3 py-2.5 text-left text-xs text-ink-dim transition-colors hover:border-[#8B5CF6]/60 hover:text-ink disabled:opacity-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end gap-2.5">
                  <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-[18px] rounded-br-md bg-auto/10 px-3.5 py-2 text-[13px] text-ink sm:max-w-[75%]">{m.content}</div>
                  <div className="mt-0.5 hidden h-7 w-7 shrink-0 items-center justify-center rounded-full bg-auto/15 text-auto sm:flex">
                    <User2 className="h-3.5 w-3.5" />
                  </div>
                </div>
              ) : (
                <Fragment key={i}>{renderAssistant(m, m.content, false, i)}</Fragment>
              ),
            )}
            {live && renderAssistant(live, tw.text, true, -1)}
          </div>
        </div>

        {!scroll.atBottom && (
          <button
            onClick={scroll.toBottom}
            className="absolute bottom-[88px] left-1/2 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-line bg-surface text-ink-dim shadow-pop hover:text-ink"
            aria-label="Cuộn xuống cuối"
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}

        <form
          className="border-t border-line/60 bg-surface p-2.5 sm:p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
        >
          <div className="mx-auto flex w-full max-w-3xl items-end gap-2 rounded-[14px] border border-line/80 bg-panel/30 p-1.5 pl-3 focus-within:border-[#8B5CF6]/60 focus-within:ring-2 focus-within:ring-[#8B5CF6]/15">
            <textarea
              ref={ta}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                // Điện thoại: Enter xuống dòng (bàn phím ảo), gửi bằng nút
                if (e.key === "Enter" && !e.shiftKey && device !== "phone" && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send(text);
                }
              }}
              rows={1}
              maxLength={4000}
              enterKeyHint="send"
              placeholder={info?.configured ? (device === "phone" ? "Hỏi trợ lý…" : "Nhập câu hỏi (Enter để gửi, Shift+Enter xuống dòng)…") : "Trợ lý đang tắt — cần GROQ_API_KEY ở backend"}
              disabled={!info?.configured}
              className="max-h-[200px] min-h-[36px] flex-1 resize-none bg-transparent py-2 text-[14px] text-ink outline-none placeholder:text-ink-mute md:text-[13px]"
              aria-label="Nội dung câu hỏi"
            />
            {streaming ? (
              <button type="button" onClick={stop} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-surface transition-transform active:scale-95" aria-label="Dừng sinh câu trả lời" title="Dừng">
                <Square className="h-3.5 w-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!text.trim() || !info?.configured}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#8B5CF6] text-white transition-all active:scale-95 disabled:bg-line disabled:text-ink-mute"
                aria-label="Gửi"
                title="Gửi"
              >
                <Send className="h-4 w-4" />
              </button>
            )}
          </div>
          <p className="mx-auto mt-1.5 hidden max-w-3xl text-center text-2xs text-ink-mute sm:block">
            Trợ lý AI có thể sai. Lệnh điều khiển luôn cần bạn xác nhận và đi qua bộ khoá an toàn.
          </p>
        </form>
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------------------------------------- Report
function ReportTab({ info }: { info: LlmInfo | null }) {
  const { selectedId } = useLive();
  const toast = useToast();
  const [iid, setIid] = useState<number | null>(selectedId);
  const [hours, setHours] = useState<"6" | "24" | "168" | "720">("24");
  const [streaming, setStreaming] = useState(false);
  const [meta, setMeta] = useState<{ model: string; latency_ms: number; generated_at: string } | null>(null);
  const tw = useTypewriter();
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (iid == null && selectedId != null) setIid(selectedId);
  }, [selectedId, iid]);

  async function generate() {
    if (iid == null) return;
    tw.reset();
    setMeta(null);
    setStreaming(true);
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      await streamPost<ReportStreamEvent>(
        "/llm/report/stream",
        { intersection_id: iid, hours: Number(hours) },
        (e) => {
          if (e.type === "delta") tw.push(e.text);
          else if (e.type === "done") setMeta({ model: e.model, latency_ms: e.latency_ms, generated_at: e.generated_at });
          else if (e.type === "error") toast("error", "Không sinh được báo cáo", e.message);
        },
        ctrl.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") toast("error", "Không sinh được báo cáo", (e as Error).message);
    } finally {
      abort.current = null;
      setStreaming(false);
    }
  }

  function download() {
    const blob = new Blob([tw.full.current], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bao-cao-giao-thong-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const hasText = tw.full.current.length > 0;
  return (
    <Panel
      title="Báo cáo tự động"
      icon={<FileText className="h-4 w-4 text-[#8B5CF6]" />}
      actions={
        hasText &&
        !streaming && (
          <>
            <Button size="sm" variant="ghost" icon={<Printer className="h-3.5 w-3.5" />} onClick={() => window.print()} className="max-sm:hidden">
              In
            </Button>
            <Button size="sm" variant="secondary" icon={<Download className="h-3.5 w-3.5" />} onClick={download}>
              .md
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-2.5 border-b border-line/60 pb-3 sm:flex-row sm:flex-wrap sm:items-center print:hidden">
        <IntersectionSelect value={iid} onChange={setIid} />
        <div className="overflow-x-auto">
          <Segmented
            size="sm"
            value={hours}
            onChange={setHours}
            options={[
              { id: "6", label: "6 giờ" },
              { id: "24", label: "24 giờ" },
              { id: "168", label: "7 ngày" },
              { id: "720", label: "30 ngày" },
            ]}
          />
        </div>
        {streaming ? (
          <Button variant="secondary" icon={<Square className="h-3.5 w-3.5 fill-current" />} onClick={() => abort.current?.abort()} className="max-sm:h-11">
            Dừng
          </Button>
        ) : (
          <Button variant="primary" icon={<Sparkles className="h-3.5 w-3.5" />} disabled={!info?.configured || iid == null} onClick={generate} className="max-sm:h-11">
            Sinh báo cáo
          </Button>
        )}
        <span className="text-2xs text-ink-mute">Tổng hợp từ lưu lượng, chu kỳ đèn, cảnh báo, sự cố và quyết định LLM đã lưu.</span>
      </div>
      {hasText || streaming ? (
        <div className="mx-auto max-w-4xl pt-3">
          {hasText ? (
            <div>
              <Markdown text={tw.text} />
              {(streaming || !tw.caughtUp) && <Caret />}
            </div>
          ) : (
            <div className="flex items-center gap-2 py-6 text-sm text-ink-mute">
              <Loader2 className="h-4 w-4 animate-spin text-[#8B5CF6]" /> Đang tổng hợp số liệu…
            </div>
          )}
          {meta && tw.caughtUp && (
            <div className="num mt-4 border-t border-line/60 pt-2 text-2xs text-ink-mute">
              Sinh lúc {fmtDateTime(meta.generated_at)} · {meta.model} · {(meta.latency_ms / 1000).toFixed(1)}s · Nội dung do AI tạo từ số liệu hệ thống — cần kiểm tra trước khi ban hành.
            </div>
          )}
        </div>
      ) : (
        <Empty title="Chưa có báo cáo" hint="Chọn nút giao, khoảng thời gian rồi bấm Sinh báo cáo." icon={<FileText className="h-6 w-6" />} />
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------------------------------- Decisions
function DecisionDetail({ d }: { d: LlmDecision }) {
  return (
    <div className="space-y-2">
      {d.reason && (
        <p className="text-[13px] text-ink">
          <b>Lý do của LLM:</b> {d.reason}
        </p>
      )}
      {d.guard_notes && (
        <p className="text-xs text-warn-ink">
          <b>Lớp kiểm tra:</b> {d.guard_notes}
        </p>
      )}
      {d.decided_by && <p className="text-xs text-ink-mute">Xử lý bởi: {d.decided_by}</p>}
      <details>
        <summary className="cursor-pointer text-xs font-semibold text-ink-dim">Dữ liệu đầu vào gửi cho LLM</summary>
        <pre className="num mt-1.5 max-h-72 overflow-auto rounded-ctl bg-carbon p-2.5 text-2xs text-ink-dim">{JSON.stringify(d.context, null, 2)}</pre>
      </details>
      {d.raw_output && (
        <details>
          <summary className="cursor-pointer text-xs font-semibold text-ink-dim">Đầu ra thô của LLM</summary>
          <pre className="num mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap rounded-ctl bg-carbon p-2.5 text-2xs text-ink-dim">{d.raw_output}</pre>
        </details>
      )}
    </div>
  );
}

const trigLabel = (d: LlmDecision) => (d.trigger === "EVENT" ? "Sự kiện" : d.trigger === "MANUAL" ? `Thủ công${d.decided_by ? ` (${d.decided_by})` : ""}` : "Định kỳ");

function DecisionsTab() {
  const { summary } = useLive();
  const device = useDevice();
  const [iid, setIid] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ items: LlmDecision[]; total: number } | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(() => {
    api
      .get<{ items: LlmDecision[]; total: number }>(`/llm/decisions${qs({ intersection_id: iid, status, page, page_size: 20 })}`)
      .then(setData)
      .catch(() => setData({ items: [], total: 0 }));
  }, [iid, status, page]);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [load]);

  const name = (id: number) => summary.find((s) => s.id === id)?.name ?? `#${id}`;
  const filters = (
    <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
      <Select value={iid} onChange={(e) => { setIid(e.target.value); setPage(1); }} className="h-8 text-xs" aria-label="Lọc nút giao">
        <option value="">Tất cả nút giao</option>
        {summary.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </Select>
      <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-8 text-xs" aria-label="Lọc trạng thái">
        <option value="">Mọi trạng thái</option>
        {Object.entries(LLM_STATUS).map(([k, v]) => (
          <option key={k} value={k}>
            {v.label}
          </option>
        ))}
      </Select>
    </div>
  );

  return (
    <Panel title="Nhật ký quyết định LLM" icon={<History className="h-4 w-4 text-[#8B5CF6]" />} actions={device !== "phone" ? filters : undefined} bodyClassName="p-0">
      {device === "phone" && <div className="border-b border-line/60 p-3">{filters}</div>}
      {!data ? (
        <Spinner />
      ) : data.items.length === 0 ? (
        <Empty title="Chưa có quyết định nào" hint="Bật LLM Supervisor ở màn hình Giám sát & Điều khiển (nút giao phải ở chế độ AUTO)." />
      ) : (
        <>
          {device === "phone" ? (
            /* Điện thoại: dạng thẻ, chạm để mở chi tiết */
            <ul className="divide-y divide-line/50">
              {data.items.map((d) => (
                <li key={d.id ?? 0}>
                  <button className="w-full p-3 text-left active:bg-panel/40" onClick={() => setOpen(open === d.id ? null : d.id)} aria-expanded={open === d.id}>
                    <div className="flex items-center justify-between gap-2">
                      <Badge color={LLM_STATUS[d.status].color}>{LLM_STATUS[d.status].label}</Badge>
                      <span className="num text-2xs text-ink-mute">{fmtDateTime(d.created_at)}</span>
                    </div>
                    <div className="mt-1.5 text-[13px] font-semibold text-ink">{d.strategy_label ?? "—"}</div>
                    <div className="mt-0.5 truncate text-xs text-ink-dim">{name(d.intersection_id)}</div>
                    <div className="num mt-0.5 text-2xs text-ink-mute">
                      {trigLabel(d)}
                      {d.weight_ns != null && ` · B–N ×${d.weight_ns.toFixed(2)} / Đ–T ×${d.weight_ew?.toFixed(2)}`}
                      {d.latency_ms != null && ` · ${Math.round(d.latency_ms)} ms`}
                    </div>
                  </button>
                  {open === d.id && (
                    <div className="bg-panel/20 px-3 pb-3">
                      <DecisionDetail d={d} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-2xs uppercase tracking-wider text-ink-mute">
                    <th className="px-3 py-2 font-semibold">Thời điểm</th>
                    <th className="px-3 py-2 font-semibold">Nút giao</th>
                    <th className="px-3 py-2 font-semibold max-lg:hidden">Kích hoạt</th>
                    <th className="px-3 py-2 font-semibold">Chiến lược</th>
                    <th className="px-3 py-2 font-semibold">B–N / Đ–T</th>
                    <th className="px-3 py-2 font-semibold">Trạng thái</th>
                    <th className="px-3 py-2 font-semibold max-lg:hidden">Độ trễ</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((d) => (
                    <Fragment key={d.id ?? 0}>
                      <tr className="cursor-pointer border-b border-line/40 hover:bg-panel/40" onClick={() => setOpen(open === d.id ? null : d.id)}>
                        <td className="num whitespace-nowrap px-3 py-2 text-ink-dim">{fmtDateTime(d.created_at)}</td>
                        <td className="max-w-[220px] truncate px-3 py-2 text-ink">{name(d.intersection_id)}</td>
                        <td className="px-3 py-2 text-ink-dim max-lg:hidden">{trigLabel(d)}</td>
                        <td className="px-3 py-2 text-ink">{d.strategy_label ?? "—"}</td>
                        <td className="num whitespace-nowrap px-3 py-2 text-ink-dim">{d.weight_ns != null ? `×${d.weight_ns.toFixed(2)} / ×${d.weight_ew?.toFixed(2)}` : "—"}</td>
                        <td className="px-3 py-2">
                          <Badge color={LLM_STATUS[d.status].color}>{LLM_STATUS[d.status].label}</Badge>
                        </td>
                        <td className="num px-3 py-2 text-ink-mute max-lg:hidden">{d.latency_ms != null ? `${Math.round(d.latency_ms)} ms` : "—"}</td>
                        <td className="px-2">
                          <ChevronDown className={clsx("h-4 w-4 text-ink-mute transition-transform", open === d.id && "rotate-180")} />
                        </td>
                      </tr>
                      {open === d.id && (
                        <tr className="border-b border-line/40 bg-panel/20">
                          <td colSpan={8} className="px-3 py-3">
                            <DecisionDetail d={d} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="p-3">
            <Pager page={page} pageSize={20} total={data.total} onPage={setPage} />
          </div>
        </>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------------------------------- Page
type Tab = "chat" | "report" | "decisions";

export default function AssistantPage() {
  const { can } = useAuth();
  const [info, setInfo] = useState<LlmInfo | null>(null);
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    api.get<LlmInfo>("/llm/info").then(setInfo).catch(() => undefined);
  }, []);

  const tabs: { id: Tab; label: string; icon: JSX.Element }[] = [
    { id: "chat", label: "Trợ lý", icon: <Bot className="h-3.5 w-3.5" /> },
    ...(can("report:ai") ? [{ id: "report" as Tab, label: "Báo cáo", icon: <FileText className="h-3.5 w-3.5" /> }] : []),
    ...(can("stats:view") ? [{ id: "decisions" as Tab, label: "Nhật ký LLM", icon: <History className="h-3.5 w-3.5" /> }] : []),
  ];

  return (
    <div className="space-y-2.5 md:space-y-3">
      <div className="flex items-center justify-between gap-3">
        <Tabs tabs={tabs} value={tab} onChange={setTab} className="min-w-0 flex-1" />
        {info && (
          <div className="hidden shrink-0 md:block">
            {info.configured ? <Badge color="#8B5CF6">{info.provider} · {info.model}</Badge> : <Badge color="#EF4444">LLM chưa cấu hình (GROQ_API_KEY)</Badge>}
          </div>
        )}
      </div>
      {tab === "chat" && <ChatTab info={info} />}
      {tab === "report" && <ReportTab info={info} />}
      {tab === "decisions" && <DecisionsTab />}
    </div>
  );
}
