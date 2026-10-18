"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type Tone = "info" | "error";
type Toast = { id: number; msg: string; tone: Tone };
type ShowToast = (msg: string, tone?: Tone) => void;

const ToastContext = createContext<ShowToast>(() => {});

export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const seq = useRef(0);

  const show = useCallback<ShowToast>((msg, tone = "info") => {
    clearTimeout(timer.current);
    setToast({ id: ++seq.current, msg, tone });
    timer.current = setTimeout(() => setToast(null), tone === "error" ? 5000 : 2600);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 top-6 z-50">
        {toast && (
          <div
            key={toast.id}
            className={`animate-toast-in absolute left-1/2 max-w-[calc(100vw-32px)] -translate-x-1/2 rounded-2xl px-[18px] py-3 text-sm font-semibold shadow-lg ${
              toast.tone === "error" ? "bg-red-ink text-white" : "bg-ink text-white"
            }`}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}
