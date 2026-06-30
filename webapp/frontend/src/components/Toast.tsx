// Minimal toast system: provider + useToast hook + portal render.
// Success/error/info variants; auto-dismiss after ~3.6s.

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode
} from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";

export type ToastKind = "success" | "error" | "info";

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

const ToastCtx = createContext<(kind: ToastKind, message: string) => void>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

let counter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = ++counter;
    setItems((prev) => [...prev, { id, kind, message }]);
    window.setTimeout(
      () => setItems((prev) => prev.filter((t) => t.id !== id)),
      3600
    );
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      {createPortal(
        <div className="toast-stack" role="status" aria-live="polite">
          {items.map((t) => (
            <div key={t.id} className={`toast toast--${t.kind}`}>
              <span className="toast-icon">
                {t.kind === "success" ? (
                  <CheckCircle2 size={16} aria-hidden="true" />
                ) : t.kind === "error" ? (
                  <AlertCircle size={16} aria-hidden="true" />
                ) : (
                  <Info size={16} aria-hidden="true" />
                )}
              </span>
              <span className="toast-message">{t.message}</span>
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastCtx.Provider>
  );
}
