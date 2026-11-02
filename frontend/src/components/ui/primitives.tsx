import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { tone } from "@/lib/format";

export function Panel({
  title,
  icon,
  actions,
  children,
  className,
  bodyClassName,
  tone: panelTone,
}: {
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: "danger" | "manual" | "auto";
}) {
  return (
    <section
      className={clsx(
        "flex min-w-0 flex-col rounded-panel border bg-surface shadow-panel transition-all print-plain",
        panelTone === "danger"
          ? "border-stop/50 ring-1 ring-stop/20"
          : panelTone === "manual"
            ? "border-manual/50 ring-1 ring-manual/20"
            : panelTone === "auto"
              ? "border-auto/50 ring-1 ring-auto/20"
              : "border-line/80",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex min-h-[42px] flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line/60 bg-panel/30 px-3 py-2.5 sm:px-3.5">
          <div className="flex min-w-0 items-center gap-2.5 text-[13px] font-semibold tracking-tight text-ink">
            {icon && <span className="text-ink-dim">{icon}</span>}
            <span className="truncate">{title}</span>
          </div>
          {actions && <div className="flex max-w-full flex-wrap items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={clsx("min-h-0 flex-1", bodyClassName ?? "p-3 sm:p-3.5")}>{children}</div>
    </section>
  );
}

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "manual" | "success" | "warn";
const BTN: Record<BtnVariant, string> = {
  primary: "bg-auto text-white hover:brightness-110 active:brightness-95 border-auto/80 shadow-sm shadow-auto/20",
  secondary: "bg-panel text-ink hover:bg-line/70 active:bg-line border-line/80 shadow-sm",
  ghost: "bg-transparent text-ink-dim hover:text-ink hover:bg-panel border-transparent",
  danger: "bg-stop/15 text-stop-ink hover:bg-stop/25 active:bg-stop/30 border-stop/50",
  manual: "bg-manual/15 text-manual-ink hover:bg-manual/25 active:bg-manual/30 border-manual/50",
  success: "bg-go/15 text-go-ink hover:bg-go/25 active:bg-go/30 border-go/50",
  warn: "bg-warn/15 text-warn-ink hover:bg-warn/25 active:bg-warn/30 border-warn/50",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-ctl border font-medium transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-[13px]",
        BTN[variant],
        className,
      )}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Badge({
  color,
  children,
  solid,
  pulse,
  className,
  title,
}: {
  color: string;
  children: ReactNode;
  solid?: boolean;
  pulse?: boolean;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-tag border px-2 py-0.5 text-2xs font-semibold leading-4 tracking-wide",
        pulse && "animate-pulseRing",
        className,
      )}
      style={
        solid
          ? { background: color, borderColor: color, color: "#FFFFFF" }
          : {
              color: tone(color, 82),
              borderColor: `color-mix(in srgb, ${color} 38%, transparent)`,
              background: `color-mix(in srgb, ${color} 12%, transparent)`,
            }
      }
    >
      {children}
    </span>
  );
}

export function Dot({ color, pulse, size = 8 }: { color: string; pulse?: boolean; size?: number }) {
  return (
    <span
      aria-hidden
      className={clsx("inline-block shrink-0 rounded-full", pulse && "animate-pulseRing")}
      style={{
        width: size,
        height: size,
        background: color,
        boxShadow: `0 0 6px color-mix(in srgb, ${color} 60%, transparent)`,
      }}
    />
  );
}

export function Spinner({ label = "Đang tải…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-mute">
      <Loader2 className="h-4 w-4 animate-spin text-auto" />
      {label}
    </div>
  );
}

export function Empty({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-4 py-10 text-center">
      {icon && <div className="mb-1 text-ink-mute">{icon}</div>}
      <p className="text-sm font-semibold text-ink-dim">{title}</p>
      {hint && <p className="max-w-sm text-xs leading-relaxed text-ink-mute">{hint}</p>}
    </div>
  );
}

export function Stat({
  label,
  value,
  unit,
  sub,
  color,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  color?: string;
  className?: string;
}) {
  return (
    <div className={clsx("min-w-0", className)}>
      <div className="label truncate">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="num truncate text-xl font-bold leading-tight" style={color ? { color: tone(color, 85) } : undefined}>
          {value}
        </span>
        {unit && <span className="text-2xs font-medium text-ink-mute">{unit}</span>}
      </div>
      {sub && <div className="mt-0.5 truncate text-2xs text-ink-mute">{sub}</div>}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: { id: T; label: ReactNode; icon?: ReactNode; count?: number }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={clsx("flex gap-1.5 overflow-x-auto border-b border-line/80 pb-px", className)}>
      {tabs.map((t) => {
        const active = value === t.id;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={clsx(
              "-mb-px flex items-center gap-2 whitespace-nowrap rounded-t-ctl border-b-2 px-3.5 py-2.5 text-xs font-semibold transition-all",
              active
                ? "border-auto bg-surface text-auto shadow-sm"
                : "border-transparent text-ink-mute hover:bg-panel/40 hover:text-ink",
            )}
          >
            {t.icon}
            {t.label}
            {t.count != null && (
              <span className="num rounded-tag bg-panel px-1.5 py-0.2 text-2xs font-bold text-ink-dim">
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "md",
  disabled,
}: {
  options: { id: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-ctl border border-line/80 bg-carbon p-0.5 shadow-inner">
      {options.map((o) => {
        const active = value === o.id;
        return (
          <button
            key={o.id}
            onClick={() => !active && onChange(o.id)}
            aria-pressed={active}
            disabled={disabled}
            className={clsx(
              "rounded-[5px] font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50",
              size === "sm" ? "px-2 py-0.5 text-2xs" : "px-3 py-1 text-xs",
              active
                ? "bg-surface text-ink shadow-sm ring-1 ring-line/50"
                : "text-ink-mute hover:text-ink",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between gap-2 border-t border-line/70 px-3 py-2 text-xs text-ink-mute">
      <span className="num font-medium">
        {total === 0 ? 0 : (page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} / {total.toLocaleString("vi-VN")}
      </span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Trước
        </Button>
        <span className="num px-1.5 font-semibold text-ink">
          {page}/{pages}
        </span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Sau
        </Button>
      </div>
    </div>
  );
}

export function Meter({ value, max = 100, color, height = 6 }: { value: number; max?: number; color: string; height?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="w-full overflow-hidden rounded-full bg-carbon" style={{ height }}>
      <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}
