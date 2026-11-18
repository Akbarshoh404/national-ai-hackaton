"use client";

import { X } from "lucide-react";
import { useEffect } from "react";
import { useT } from "@/i18n";

export function CopilotPanel({ open, onClose }: { open: boolean; onClose: () => void; context: { screen: string; selected_ids: string[] } }) {
  const t = useT();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <aside aria-label={t.shell.copilot} className="pop slide-in fixed top-5 right-5 bottom-5 z-40 flex w-[400px] max-w-[calc(100vw-32px)] flex-col rounded-[36px] p-5">
      <div className="flex items-center justify-between">
        <h2 className="t-title">{t.shell.copilot}</h2>
        <button type="button" className="icon-btn -mr-2" aria-label={t.shell.close} onClick={onClose}>
          <X size={18} strokeWidth={1.75} />
        </button>
      </div>
    </aside>
  );
}
