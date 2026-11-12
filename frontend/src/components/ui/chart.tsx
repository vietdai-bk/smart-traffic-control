import type { ReactNode } from "react";

/** Tham số biểu đồ dùng chung: đồng bộ với bảng màu giao diện light/dark. */
export const AXIS = {
  stroke: "rgb(var(--c-line) / 0.8)",
  tick: { fill: "rgb(var(--c-ink-mute))", fontSize: 11, fontFamily: "var(--font-mono, JetBrains Mono, monospace)" },
  tickLine: false,
} as const;

export const GRID = {
  stroke: "rgb(var(--c-line) / 0.5)",
  strokeDasharray: "3 3",
  vertical: false,
} as const;

export const SURFACE = "rgb(var(--c-surface))";
export const CURSOR = { fill: "rgb(var(--c-auto) / 0.08)" };

export function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
  unit,
}: {
  active?: boolean;
  payload?: { name: string; value: number | null; color: string; dataKey: string }[];
  label?: string | number;
  labelFormatter?: (l: string | number) => ReactNode;
  unit?: string | Record<string, string>;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-[170px] rounded-ctl border border-line/80 bg-surface/98 px-3.5 py-2.5 text-xs shadow-pop backdrop-blur-md">
      <div className="mb-1.5 font-bold tracking-tight text-ink">
        {labelFormatter && label != null ? labelFormatter(label) : label}
      </div>
      <ul className="space-y-1">
        {payload.map((p) => (
          <li key={p.dataKey} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 font-medium text-ink-dim">
              <span className="h-2 w-2 rounded-full ring-1 ring-white/20" style={{ background: p.color }} />
              {p.name}
            </span>
            <span className="num font-bold text-ink">
              {p.value == null ? "—" : p.value.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}
              {unit ? ` ${typeof unit === "string" ? unit : (unit[p.dataKey] ?? "")}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-2xs font-semibold text-ink-dim">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          {i.dashed ? (
            <span className="h-0 w-4 border-t-2 border-dashed" style={{ borderColor: i.color }} />
          ) : (
            <span className="h-2.5 w-2.5 rounded-sm shadow-sm" style={{ background: i.color }} />
          )}
          {i.label}
        </span>
      ))}
    </div>
  );
}
