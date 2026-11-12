import { X } from "lucide-react";
import clsx from "clsx";
import { useEffect, useRef, type ReactNode } from "react";

export function Modal({
  open,
  onClose,
  title,
  icon,
  children,
  footer,
  width = 520,
  tone,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
  tone?: "danger" | "manual" | "auto";
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    window.setTimeout(() => ref.current?.querySelector<HTMLElement>("[data-autofocus], input, textarea, select")?.focus(), 30);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-start justify-center overflow-y-auto bg-slate-950/65 p-4 pt-[8vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
        style={{ maxWidth: width }}
        className={clsx(
          "w-full rounded-card border bg-surface shadow-pop transition-all",
          tone === "danger"
            ? "border-stop/70 ring-1 ring-stop/30"
            : tone === "manual"
              ? "border-manual/60 ring-1 ring-manual/30"
              : tone === "auto"
                ? "border-auto/60 ring-1 ring-auto/30"
                : "border-line/80",
        )}
      >
        <header className="flex items-center justify-between gap-3 border-b border-line/70 bg-panel/30 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-bold text-ink">
            {icon}
            {title}
          </div>
          <button onClick={onClose} className="rounded-ctl p-1 text-ink-mute transition-colors hover:bg-panel hover:text-ink" aria-label="Đóng">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="p-4">{children}</div>
        {footer && <footer className="flex items-center justify-end gap-2 border-t border-line/70 bg-panel/20 px-4 py-2.5">{footer}</footer>}
      </div>
    </div>
  );
}
