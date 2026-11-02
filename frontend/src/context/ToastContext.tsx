import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { CheckCircle2, Info, OctagonAlert, TriangleAlert, X } from "lucide-react";
import clsx from "clsx";

type Tone = "success" | "info" | "warning" | "error";
interface Toast {
  id: number;
  tone: Tone;
  title: string;
  body?: string;
}

const ToastCtx = createContext<{ push: (tone: Tone, title: string, body?: string) => void } | null>(null);

const ICON = { success: CheckCircle2, info: Info, warning: TriangleAlert, error: OctagonAlert };
const TONE = {
  success: "border-go/60 text-go",
  info: "border-auto/60 text-auto",
  warning: "border-warn/60 text-warn",
  error: "border-stop/70 text-stop",
};

let seq = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (tone: Tone, title: string, body?: string) => {
      const id = seq++;
      setItems((xs) => [...xs.slice(-4), { id, tone, title, body }]);
      window.setTimeout(() => dismiss(id), tone === "error" ? 8000 : 5000);
    },
    [dismiss],
  );
  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[380px] max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
        {items.map((t) => {
          const Icon = ICON[t.tone];
          return (
            <div
              key={t.id}
              role="status"
              className={clsx(
                "pointer-events-auto flex gap-3 rounded-card border bg-surface/98 p-3.5 shadow-pop backdrop-blur-md transition-all ring-1 ring-black/5 dark:ring-white/10",
                TONE[t.tone],
              )}
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">{t.title}</p>
                {t.body && <p className="mt-0.5 text-xs leading-relaxed text-ink-dim">{t.body}</p>}
              </div>
              <button onClick={() => dismiss(t.id)} className="text-ink-mute hover:text-ink" aria-label="Đóng thông báo">
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast phải dùng trong ToastProvider");
  return ctx.push;
}
