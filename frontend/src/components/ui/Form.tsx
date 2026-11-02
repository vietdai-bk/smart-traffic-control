import clsx from "clsx";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

const base =
  "w-full rounded-ctl border border-line/80 bg-carbon px-3 text-[13px] text-ink placeholder:text-ink-mute shadow-sm transition-all focus:border-auto focus:bg-surface focus:outline-none focus:ring-2 focus:ring-auto/20 disabled:opacity-50";

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={clsx("block min-w-0", className)}>
      <span className="mb-1.5 block text-xs font-semibold text-ink-dim">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-2xs leading-relaxed text-ink-mute">{hint}</span>}
    </label>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={clsx(base, "h-9", rest.type === "number" && "num", className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={clsx(base, "h-9 pr-7", className)}>
      {children}
    </select>
  );
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={clsx(base, "min-h-[76px] py-2 leading-relaxed", className)} />;
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; disabled?: boolean }) {
  return (
    <label className={clsx("inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-ink-dim hover:text-ink transition-colors", disabled && "opacity-50 cursor-not-allowed")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative h-5 w-8 rounded-full border transition-all shadow-inner",
          checked ? "border-go bg-go/30 ring-1 ring-go/30" : "border-line bg-panel",
        )}
      >
        <span
          className={clsx(
            "absolute top-[2px] h-3.5 w-3.5 rounded-full transition-all shadow-sm",
            checked ? "left-[14px] bg-go shadow-[0_0_6px_#10b981]" : "left-[2px] bg-ink-mute",
          )}
        />
      </button>
      {label}
    </label>
  );
}
