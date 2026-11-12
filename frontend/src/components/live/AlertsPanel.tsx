import clsx from "clsx";
import { CheckCheck, Cpu, ExternalLink, ShieldAlert, Siren } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLive } from "@/context/LiveContext";
import { useToast } from "@/context/ToastContext";
import { api } from "@/lib/api";
import { relTime } from "@/lib/format";
import { Badge, Button, Empty, Panel } from "../ui/primitives";

/** US11-T03 + US12-T03: cảnh báo nóng và sự cố thiết bị đang mở của nút giao. */
export function AlertsPanel({ intersectionId }: { intersectionId: number | null }) {
  const { activeAlerts, openIncidents } = useLive();
  const { can } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<number | null>(null);
  const alerts = activeAlerts.filter((a) => a.intersection_id === intersectionId);
  const incidents = openIncidents.filter((i) => i.intersection_id === intersectionId);

  const ack = async (id: number) => {
    setBusy(id);
    try {
      await api.post(`/alerts/${id}/ack`, { note: "Xác nhận từ Trung tâm giám sát" });
      toast("success", "Đã xác nhận cảnh báo");
    } catch (e) {
      toast("error", "Không xác nhận được", (e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Panel
      title="Cảnh báo & sự cố hiện trường"
      icon={<Siren className="h-4 w-4 text-stop" />}
      tone={alerts.some((a) => a.level === "CRITICAL" && a.status === "ACTIVE") ? "danger" : undefined}
      actions={
        <Link to="/alerts" className="flex items-center gap-1 text-2xs font-semibold text-auto hover:underline">
          Trung tâm cảnh báo <ExternalLink className="h-3 w-3" />
        </Link>
      }
      bodyClassName="max-h-[320px] overflow-y-auto p-0"
    >
      {alerts.length === 0 && incidents.length === 0 ? (
        <Empty title="Nút giao vận hành bình thường" hint="Cảnh báo ùn tắc, sự cố camera và thiết bị sẽ xuất hiện tại đây ngay khi phát hiện." />
      ) : (
        <ul className="divide-y divide-line/40">
          {alerts.map((a) => (
            <li
              key={`a${a.id}`}
              className={clsx(
                "flex items-start gap-2.5 px-3.5 py-2.5 transition-colors",
                a.status === "ACTIVE" && a.level === "CRITICAL" ? "bg-stop/10 hover:bg-stop/15" : "hover:bg-panel/40",
              )}
            >
              <ShieldAlert className={clsx("mt-0.5 h-4 w-4 shrink-0", a.level === "CRITICAL" ? "text-stop" : "text-warn", a.status === "ACTIVE" && "animate-blink")} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge color={a.level === "CRITICAL" ? "#EF4444" : "#F59E0B"}>
                    {a.alert_type === "CONGESTION" ? (a.level === "CRITICAL" ? "Ùn tắc nghiêm trọng" : "Đông đúc") : a.alert_type}
                  </Badge>
                  <span className="text-2xs text-ink-mute">{relTime(a.created_at)}</span>
                  {a.status === "ACKNOWLEDGED" && <span className="text-2xs font-medium text-go">✓ {a.acknowledged_by}</span>}
                </div>
                <p className="mt-1 text-xs font-medium leading-snug text-ink">{a.message}</p>
              </div>
              {a.status === "ACTIVE" && can("alerts:ack") && (
                <Button size="sm" variant="ghost" loading={busy === a.id} icon={<CheckCheck className="h-3.5 w-3.5" />} onClick={() => ack(a.id)}>
                  Xác nhận
                </Button>
              )}
            </li>
          ))}
          {incidents.map((i) => (
            <li key={`i${i.id}`} className="flex items-start gap-2.5 px-3.5 py-2.5 transition-colors hover:bg-panel/40">
              <Cpu className={clsx("mt-0.5 h-4 w-4 shrink-0", i.recovered_at ? "text-ink-mute" : "text-stop")} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge color={i.recovered_at ? "#10B981" : i.severity === "CRITICAL" ? "#EF4444" : "#F59E0B"}>
                    {i.recovered_at ? "Đã kết nối lại" : i.incident_type}
                  </Badge>
                  <span className="num text-2xs font-bold text-ink-dim">{i.device_code}</span>
                  <span className="text-2xs text-ink-mute">{relTime(i.started_at)}</span>
                </div>
                <p className="mt-1 text-xs leading-snug text-ink-dim">{i.message}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
