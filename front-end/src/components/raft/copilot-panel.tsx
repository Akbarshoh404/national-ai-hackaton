"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { useT } from "@/i18n";
import { Conversation } from "./conversation";

export function CopilotPanel({ open, onClose, context }: { open: boolean; onClose: () => void; context: { screen: string; selected_ids: string[] } }) {
  const t = useT();
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector("[role=dialog]")) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open, onClose]);

  return (
    <aside aria-label={t.shell.copilot} hidden={!open} className="pop slide-in fixed top-5 right-5 bottom-5 z-40 w-[400px] max-w-[calc(100vw-32px)] flex-col rounded-[36px] p-5 [&:not([hidden])]:flex">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <h2 className="t-title">{t.shell.copilot}</h2>
          <p className="text-[12px] text-text-2">{context.selected_ids.length ? `${context.selected_ids.length} ta qator tanlangan` : "Shu ekran haqida so‘rang"}</p>
        </div>
        <button type="button" className="icon-btn -mt-2 -mr-2" aria-label={t.shell.close} onClick={onClose}>
          <X size={18} strokeWidth={1.75} aria-hidden />
        </button>
      </div>
      {open ? <Conversation compact autoFocus context={context} hint="Raqamlarni Python hisoblaydi, yordamchi ularni tushuntiradi." /> : null}
    </aside>
  );
}
