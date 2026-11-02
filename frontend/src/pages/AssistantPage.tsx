import clsx from "clsx";
import { Bot, Check, ChevronDown, Download, FileText, History, Printer, Send, Sparkles, Trash2, User2, Wrench, X } from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { LLM_STATUS } from "@/components/live/LlmSupervisorCard";
import { Select, Textarea } from "@/components/ui/Form";
import { Markdown } from "@/components/ui/Markdown";
import { Badge, Button, Empty, Pager, Panel, Segmented, Spinner, Tabs } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";
import { useToast } from "@/context/ToastContext";
import { api, qs } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { AiReport, AssistantAction, AssistantReply, LlmDecision } from "@/lib/types";

interface LlmInfo {
  provider: string;
  configured: boolean;
  model: string;
  interval_s: number;
}

const TOOL_LABEL: Record<string, string> = {
  list_intersections: "Danh sách nút giao",
  get_intersection_status: "Trạng thái thời gian thực",
  query_traffic_stats: "Truy vấn thống kê",
  list_active_alerts: "Cảnh báo & sự cố",
  get_llm_decisions: "Quyết định LLM",
  get_signal_history: "Lịch sử lệnh đèn",
  propose_action: "Tạo đề xuất điều khiển",
};

function IntersectionSelect({ value, onChange }: { value: number | null; onChange: (id: number) => void }) {
  const { summary } = useLive();
  return (
    <Select value={value ?? ""} onChange={(e) => onChange(Number(e.target.value))} className="h-8 max-w-[300px] text-xs" aria-label="Chọn nút giao">
      {summary.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </Select>
  );
}

// ------------------------------------------------------------------------------------------- Chat
interface Msg {
  role: "user" | "assistant";
  content: string;
  trace?: AssistantReply["trace"];
  actions?: (AssistantAction & { state?: "done" | "cancelled" | "failed"; result?: string })[];
  meta?: string;
  error?: boolean;
}

const STORE = "stcs.assistant.chat";

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
    <div className={clsx("mt-2 rounded-ctl border p-2.5", settled ? "border-line/60 bg-panel/20" : "border-manual/50 bg-manual/10")}>
      <div className="flex items-center gap-2 text-xs font-bold text-ink">
        <Wrench className="h-3.5 w-3.5 text-manual" />
        Đề xuất điều khiển · {a.intersection}
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
          <div className="mt-2 flex gap-1.5">
            <Button size="sm" variant="manual" icon={<Check className="h-3.5 w-3.5" />} loading={busy === "ok"} onClick={confirm}>
              Xác nhận thực thi
            </Button>
            <Button size="sm" variant="ghost" icon={<X className="h-3.5 w-3.5" />} loading={busy === "cancel"} onClick={cancel}>
              Huỷ
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function ChatTab({ info }: { info: LlmInfo | null }) {
  const { selectedId } = useLive();
  const { can } = useAuth();
  const [msgs, setMsgs] = useState<Msg[]>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(STORE) ?? "[]") as Msg[];
    } catch {
      return [];
    }
  });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-40)));
    } catch {
      /* bỏ qua */
    }
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs]);

  const suggestions = [
    "Tình hình nút giao đang chọn thế nào? Hướng nào đông nhất?",
    "Thống kê lưu lượng 24 giờ qua theo hướng",
    "Có cảnh báo hay sự cố thiết bị nào đang mở không?",
    "LLM Supervisor đã quyết định gì gần đây và vì sao?",
    ...(can("llm:supervise") ? ["Ưu tiên trục Đông–Tây trong 10 phút vì đang ùn ứ"] : []),
  ];

  async function send(content: string) {
    const q = content.trim();
    if (!q || busy) return;
    const next = [...msgs, { role: "user" as const, content: q }];
    setMsgs(next);
    setText("");
    setBusy(true);
    try {
      const r = await api.post<AssistantReply>("/llm/assistant/chat", {
        messages: next.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content })),
        intersection_id: selectedId,
      });
      setMsgs((cur) => [...cur, { role: "assistant", content: r.reply || "(không có nội dung)", trace: r.trace, actions: r.actions, meta: `${r.model} · ${r.latency_ms} ms` }]);
    } catch (e) {
      setMsgs((cur) => [...cur, { role: "assistant", content: (e as Error).message, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  const settle = (mi: number, ai: number, state: "done" | "cancelled" | "failed", result: string) =>
    setMsgs((cur) => cur.map((m, i) => (i !== mi ? m : { ...m, actions: m.actions?.map((a, j) => (j === ai ? { ...a, state, result } : a)) })));

  return (
    <Panel
      title="Trợ lý vận hành"
      icon={<Bot className="h-4 w-4 text-[#8B5CF6]" />}
      actions={
        msgs.length > 0 && (
          <Button size="sm" variant="ghost" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setMsgs([])}>
            Cuộc trò chuyện mới
          </Button>
        )
      }
      bodyClassName="flex flex-col p-0"
    >
      <div className="flex h-[calc(100vh-300px)] min-h-[420px] flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {msgs.length === 0 && (
            <div className="mx-auto max-w-xl py-6 text-center">
              <Sparkles className="mx-auto h-8 w-8 text-[#8B5CF6]" />
              <p className="mt-2 text-sm font-semibold text-ink">Hỏi về tình hình giao thông, thống kê, cảnh báo — hoặc yêu cầu thao tác điều khiển.</p>
              <p className="mt-1 text-xs text-ink-mute">
                Trợ lý tra cứu số liệu thật qua công cụ của hệ thống. Mọi thao tác điều khiển chỉ là <b>đề xuất</b> và cần bạn xác nhận.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button key={s} onClick={() => send(s)} disabled={!info?.configured}
                    className="rounded-full border border-line/80 bg-panel/40 px-3 py-1.5 text-xs text-ink-dim transition-colors hover:border-[#8B5CF6]/60 hover:text-ink disabled:opacity-50">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={clsx("flex gap-2.5", m.role === "user" && "flex-row-reverse")}>
              <div className={clsx("flex h-7 w-7 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-auto/15 text-auto" : "bg-[#8B5CF6]/15 text-[#8B5CF6]")}>
                {m.role === "user" ? <User2 className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
              </div>
              <div className={clsx("min-w-0 max-w-[85%] rounded-panel px-3.5 py-2.5", m.role === "user" ? "bg-auto/10 text-[13px] text-ink" : m.error ? "border border-stop/40 bg-stop/10" : "border border-line/70 bg-surface")}>
                {m.trace && m.trace.length > 0 && (
                  <div className="mb-1.5 flex flex-wrap gap-1">
                    {m.trace.map((t, j) => (
                      <span key={j} className={clsx("inline-flex items-center gap-1 rounded-tag border px-1.5 py-0.5 text-2xs", t.ok ? "border-line/70 text-ink-mute" : "border-stop/40 text-stop-ink")}>
                        <Wrench className="h-3 w-3" />
                        {TOOL_LABEL[t.tool] ?? t.tool}
                      </span>
                    ))}
                  </div>
                )}
                {m.role === "user" ? <div className="whitespace-pre-wrap">{m.content}</div> : m.error ? <div className="text-xs text-stop-ink">{m.content}</div> : <Markdown text={m.content} />}
                {m.actions?.map((a, j) => <ActionCard key={a.id} a={a} onDone={(s, r) => settle(i, j, s, r)} />)}
                {m.meta && <div className="num mt-1.5 text-2xs text-ink-mute">{m.meta}</div>}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-xs text-ink-mute">
              <Bot className="h-4 w-4 animate-pulse text-[#8B5CF6]" /> Đang tra cứu dữ liệu và suy luận…
            </div>
          )}
          <div ref={endRef} />
        </div>
        <form
          className="flex items-end gap-2 border-t border-line/60 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
        >
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(text);
              }
            }}
            rows={2}
            maxLength={2000}
            placeholder={info?.configured ? "Nhập câu hỏi (Enter để gửi, Shift+Enter xuống dòng)…" : "Trợ lý đang tắt — cần cấu hình GROQ_API_KEY ở backend"}
            disabled={!info?.configured}
            className="min-h-[44px] flex-1 resize-none"
          />
          <Button type="submit" variant="primary" icon={<Send className="h-4 w-4" />} loading={busy} disabled={!text.trim() || !info?.configured}>
            Gửi
          </Button>
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
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<AiReport | null>(null);

  useEffect(() => {
    if (iid == null && selectedId != null) setIid(selectedId);
  }, [selectedId, iid]);

  async function generate() {
    if (iid == null) return;
    setBusy(true);
    try {
      setReport(await api.post<AiReport>("/llm/report", { intersection_id: iid, hours: Number(hours) }));
    } catch (e) {
      toast("error", "Không sinh được báo cáo", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function download() {
    if (!report) return;
    const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bao-cao-giao-thong-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Panel
      title="Báo cáo tình hình giao thông tự động"
      icon={<FileText className="h-4 w-4 text-[#8B5CF6]" />}
      actions={
        report && (
          <>
            <Button size="sm" variant="ghost" icon={<Printer className="h-3.5 w-3.5" />} onClick={() => window.print()}>In</Button>
            <Button size="sm" variant="secondary" icon={<Download className="h-3.5 w-3.5" />} onClick={download}>Tải .md</Button>
          </>
        )
      }
    >
      <div className="flex flex-wrap items-center gap-2.5 border-b border-line/60 pb-3 print:hidden">
        <IntersectionSelect value={iid} onChange={setIid} />
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
        <Button variant="primary" size="sm" icon={<Sparkles className="h-3.5 w-3.5" />} loading={busy} disabled={!info?.configured || iid == null} onClick={generate}>
          Sinh báo cáo
        </Button>
        <span className="text-2xs text-ink-mute">LLM tổng hợp từ lưu lượng, chu kỳ đèn, cảnh báo, sự cố và quyết định LLM đã lưu.</span>
      </div>
      {busy ? (
        <Spinner label="Đang tổng hợp số liệu và viết báo cáo…" />
      ) : report ? (
        <div className="mx-auto max-w-4xl pt-3">
          <Markdown text={report.markdown} />
          <div className="num mt-4 border-t border-line/60 pt-2 text-2xs text-ink-mute">
            Sinh lúc {fmtDateTime(report.generated_at)} · {report.model} · {report.latency_ms} ms · Nội dung do AI tạo từ số liệu hệ thống — cần kiểm tra trước khi ban hành.
          </div>
        </div>
      ) : (
        <Empty title="Chưa có báo cáo" hint="Chọn nút giao, khoảng thời gian rồi bấm Sinh báo cáo." icon={<FileText className="h-6 w-6" />} />
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------------------------------- Decisions
function DecisionsTab() {
  const { summary } = useLive();
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

  return (
    <Panel
      title="Nhật ký quyết định LLM Supervisor"
      icon={<History className="h-4 w-4 text-[#8B5CF6]" />}
      actions={
        <div className="flex gap-2">
          <Select value={iid} onChange={(e) => { setIid(e.target.value); setPage(1); }} className="h-7 text-xs" aria-label="Lọc nút giao">
            <option value="">Tất cả nút giao</option>
            {summary.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-7 text-xs" aria-label="Lọc trạng thái">
            <option value="">Mọi trạng thái</option>
            {Object.entries(LLM_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </Select>
        </div>
      }
      bodyClassName="p-0"
    >
      {!data ? (
        <Spinner />
      ) : data.items.length === 0 ? (
        <Empty title="Chưa có quyết định nào" hint="Bật LLM Supervisor ở màn hình Giám sát & Điều khiển (nút giao phải ở chế độ AUTO)." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wider text-ink-mute">
                  <th className="px-3 py-2 font-semibold">Thời điểm</th>
                  <th className="px-3 py-2 font-semibold">Nút giao</th>
                  <th className="px-3 py-2 font-semibold">Kích hoạt</th>
                  <th className="px-3 py-2 font-semibold">Chiến lược</th>
                  <th className="px-3 py-2 font-semibold">Trọng số B–N / Đ–T</th>
                  <th className="px-3 py-2 font-semibold">Trạng thái</th>
                  <th className="px-3 py-2 font-semibold">Độ trễ</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((d) => (
                  <Fragment key={d.id ?? 0}>
                    <tr className="cursor-pointer border-b border-line/40 hover:bg-panel/40" onClick={() => setOpen(open === d.id ? null : d.id)}>
                      <td className="num whitespace-nowrap px-3 py-2 text-ink-dim">{fmtDateTime(d.created_at)}</td>
                      <td className="px-3 py-2 text-ink">{name(d.intersection_id)}</td>
                      <td className="px-3 py-2 text-ink-dim">{d.trigger === "EVENT" ? "Sự kiện" : d.trigger === "MANUAL" ? `Thủ công${d.decided_by ? ` (${d.decided_by})` : ""}` : "Định kỳ"}</td>
                      <td className="px-3 py-2 text-ink">{d.strategy_label ?? "—"}</td>
                      <td className="num px-3 py-2 text-ink-dim">{d.weight_ns != null ? `×${d.weight_ns.toFixed(2)} / ×${d.weight_ew?.toFixed(2)}` : "—"}</td>
                      <td className="px-3 py-2"><Badge color={LLM_STATUS[d.status].color}>{LLM_STATUS[d.status].label}</Badge></td>
                      <td className="num px-3 py-2 text-ink-mute">{d.latency_ms != null ? `${Math.round(d.latency_ms)} ms` : "—"}</td>
                      <td className="px-2"><ChevronDown className={clsx("h-4 w-4 text-ink-mute transition-transform", open === d.id && "rotate-180")} /></td>
                    </tr>
                    {open === d.id && (
                      <tr className="border-b border-line/40 bg-panel/20">
                        <td colSpan={8} className="space-y-2 px-3 py-3">
                          {d.reason && <p className="text-[13px] text-ink"><b>Lý do của LLM:</b> {d.reason}</p>}
                          {d.guard_notes && <p className="text-xs text-warn-ink"><b>Lớp kiểm tra:</b> {d.guard_notes}</p>}
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
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
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
    { id: "chat", label: "Trợ lý vận hành", icon: <Bot className="h-3.5 w-3.5" /> },
    ...(can("report:ai") ? [{ id: "report" as Tab, label: "Báo cáo tự động", icon: <FileText className="h-3.5 w-3.5" /> }] : []),
    ...(can("stats:view") ? [{ id: "decisions" as Tab, label: "Nhật ký quyết định LLM", icon: <History className="h-3.5 w-3.5" /> }] : []),
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs tabs={tabs} value={tab} onChange={setTab} className="flex-1" />
        {info && (
          <div className="flex items-center gap-2 text-2xs text-ink-mute">
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
