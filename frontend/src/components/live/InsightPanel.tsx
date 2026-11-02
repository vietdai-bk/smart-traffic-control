import { Activity } from "lucide-react";
import { useState } from "react";
import { useLive } from "@/context/LiveContext";
import { INTERVAL_LABEL, fmtTime } from "@/lib/format";
import type { Snapshot } from "@/lib/types";
import { Panel, Segmented, Stat } from "../ui/primitives";

const pct = (v: number | null | undefined) => (v == null ? "—" : (v * 100).toFixed(1));

/** US05-T04: hiệu suất nhận diện thực tế. */
function DetectionStats({ snap }: { snap: Snapshot | null }) {
  const d = snap?.detection;
  return (
    <div className="p-3.5">
      <div className="num mb-3 flex items-center justify-between text-2xs text-ink-mute">
        <span>Mô hình thị giác máy tính: <strong className="font-bold text-ink">{d?.model ?? "—"}</strong></span>
        <span className="rounded bg-panel px-1.5 py-0.5 font-bold text-auto">YOLOv8 Edge</span>
      </div>
      <div className="grid grid-cols-3 gap-2.5">
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="Suy luận" value={d?.inference_ms == null ? "—" : d.inference_ms.toFixed(2)} unit="ms" />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="FPS xử lý" value={d?.fps.toFixed(1) ?? "—"} unit="fps" />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="Pipeline tick" value={snap?.tick_ms.toFixed(2) ?? "—"} unit="ms" />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="Precision" value={pct(d?.precision)} unit="%" />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="Recall" value={pct(d?.recall)} unit="%" />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="F1-Score" value={pct(d?.f1)} unit="%" />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="Độ tin cậy TB" value={d?.avg_confidence == null ? "—" : d.avg_confidence.toFixed(2)} />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="Đúng phân loại" value={pct(d?.class_accuracy)} unit="%" />
        <Stat className="rounded-ctl border border-line/70 bg-panel/30 p-2" label="Xe trong ROI" value={snap?.kpi.vehicles_in_roi ?? "—"} unit="xe" />
      </div>
      <p className="mt-3 text-2xs leading-relaxed text-ink-mute">
        Precision/Recall đo trên cửa sổ ~10 s bằng cách so khớp IoU ≥ 0.5 giữa bounding box AI và ground truth của luồng mô phỏng; đối tượng nhỏ ở xa chân trời được tự động lọc theo chuẩn đánh giá.
      </p>
    </div>
  );
}

function EventLogList({ snap }: { snap: Snapshot | null }) {
  const { logs, selectedId } = useLive();
  const signalEvents = (snap?.recent_events ?? []).slice().reverse();
  const opLogs = logs.filter((l) => l.intersection_id === selectedId || l.intersection_id == null).slice(0, 15);
  return (
    <div className="max-h-[300px] overflow-y-auto">
      <ul className="divide-y divide-line/40 text-xs">
        {opLogs.map((l) => (
          <li key={`l${l.id}`} className="flex items-center gap-2 px-3.5 py-2 transition-colors hover:bg-panel/40">
            <span className="num shrink-0 text-2xs font-semibold text-ink-mute">{fmtTime(l.created_at)}</span>
            <span className={`num shrink-0 rounded-tag px-1.5 py-0.2 text-2xs font-bold ${l.result === "FAILURE" ? "bg-stop/20 text-stop" : "bg-auto/20 text-auto"}`}>
              {l.category}
            </span>
            <span className="min-w-0 truncate text-ink-dim" title={l.description}>
              <span className="font-semibold text-ink">{l.username}</span> · {l.description}
            </span>
          </li>
        ))}
        {signalEvents.map((e, i) => (
          <li key={`e${e.ts}${i}`} className="flex items-center gap-2 px-3.5 py-2 transition-colors hover:bg-panel/40">
            <span className="num shrink-0 text-2xs font-semibold text-ink-mute">{fmtTime(new Date(e.ts * 1000).toISOString())}</span>
            <span className="num shrink-0 rounded-tag bg-panel px-1.5 py-0.2 text-2xs font-bold text-ink">P{e.phase_id}</span>
            <span className="min-w-0 truncate text-ink-dim" title={e.cause}>
              {INTERVAL_LABEL[e.interval]} · {e.cause}
            </span>
            {e.ack && (
              <span className={`num ml-auto shrink-0 text-2xs font-bold ${e.ack.ok ? "text-go" : "text-stop"}`}>
                {e.ack.ok ? `ACK ${e.ack.latency_ms.toFixed(0)}ms` : "NO ACK"}
              </span>
            )}
          </li>
        ))}
        {opLogs.length === 0 && signalEvents.length === 0 && <li className="px-3.5 py-8 text-center text-ink-mute">Chưa có sự kiện ghi nhận</li>}
      </ul>
    </div>
  );
}

/** US05-T04 + nhật ký: gộp vào một panel có tab để tiết kiệm diện tích. */
export function InsightPanel({ snap }: { snap: Snapshot | null }) {
  const [tab, setTab] = useState<"ai" | "log">("ai");
  return (
    <Panel
      title={tab === "ai" ? "Hiệu suất mô hình AI" : "Nhật ký tác chiến thời gian thực"}
      icon={<Activity className="h-4 w-4 text-auto" />}
      bodyClassName="p-0"
      actions={
        <Segmented
          size="sm"
          value={tab}
          onChange={setTab}
          options={[
            { id: "ai", label: "Chỉ số AI" },
            { id: "log", label: "Nhật ký" },
          ]}
        />
      }
    >
      {tab === "ai" ? <DetectionStats snap={snap} /> : <EventLogList snap={snap} />}
    </Panel>
  );
}
