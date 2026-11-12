import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

/** Ngăn kéo trượt từ phải — cho công cụ phụ trợ không cần hiển thị thường trực. */
export function Drawer({
  open,
  onClose,
  title,
  icon,
  actions,
  children,
  width = 400,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80]" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={onClose} />
      <aside
        className="absolute inset-y-0 right-0 flex max-w-full animate-slideIn flex-col border-l border-line/80 bg-surface shadow-pop"
        style={{ width }}
      >
        <header className="flex items-center justify-between gap-2 border-b border-line/70 bg-panel/30 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-bold text-ink">
            {icon}
            {title}
          </div>
          <div className="flex items-center gap-1">
            {actions}
            <button onClick={onClose} className="rounded-ctl p-1 text-ink-mute transition-colors hover:bg-panel hover:text-ink" aria-label="Đóng">
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  );
}
