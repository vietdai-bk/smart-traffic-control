import { BarChart3, History, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CycleHistoryTab } from "@/components/analytics/CycleHistoryTab";
import { EvaluationTab } from "@/components/analytics/EvaluationTab";
import { StatsTab } from "@/components/analytics/StatsTab";
import { Tabs } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { Intersection } from "@/lib/types";

type Tab = "stats" | "evaluation" | "cycles";

export default function AnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "stats";
  const [intersections, setIntersections] = useState<Intersection[]>([]);
  useEffect(() => {
    api.get<Intersection[]>("/intersections").then(setIntersections).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-line/80 bg-surface p-4 shadow-panel">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-ink">Phân tích & Đánh giá Hiệu quả Vận hành</h1>
          <p className="mt-0.5 text-xs font-medium text-ink-mute">
            Thống kê lưu lượng 4 hướng tiếp cận, so sánh định lượng trước/sau AI Webster và nhật ký chu kỳ đèn.
          </p>
        </div>
      </div>
      <Tabs
        className="no-print"
        value={tab}
        onChange={(t) => setParams({ tab: t })}
        tabs={[
          { id: "stats", label: "Thống kê giao thông", icon: <BarChart3 className="h-4 w-4" /> },
          { id: "evaluation", label: "Đánh giá trước / sau AI", icon: <Scale className="h-4 w-4" /> },
          { id: "cycles", label: "Chu kỳ đèn & lệnh điều khiển", icon: <History className="h-4 w-4" /> },
        ]}
      />
      {tab === "stats" && <StatsTab intersections={intersections} />}
      {tab === "evaluation" && <EvaluationTab intersections={intersections} />}
      {tab === "cycles" && <CycleHistoryTab intersections={intersections} />}
    </div>
  );
}
