"use client";

import { useEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/raft/states";
import { Button } from "@/components/ui/button";
import { useChat } from "@/lib/api/hooks";
import type { ChatAnswer, Chip } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";
import { BlockView } from "./blocks";

export type Message = { id: number; role: "user"; text: string } | { id: number; role: "assistant"; answer: ChatAnswer };

let nextId = 1;
export const userMessage = (text: string): Message => ({ id: nextId++, role: "user", text });
export const assistantMessage = (answer: ChatAnswer): Message => ({ id: nextId++, role: "assistant", answer });

export function Conversation({
  initial,
  context,
  compact,
  empty,
  autoFocus,
}: {
  initial: Message[];
  context: { screen: string; selected_ids: string[] };
  compact?: boolean;
  empty?: { text: string; chips: Chip[] };
  autoFocus?: boolean;
}) {
  const [messages, setMessages] = useState(initial);
  const [input, setInput] = useState("");
  const [failed, setFailed] = useState<(() => void) | null>(null);
  const chat = useChat();
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el && messages.length > initial.length) el.scrollTo({ top: el.scrollHeight });
  }, [messages, chat.isPending, initial.length]);

  const run = (label: string, endpoint: string, body: Record<string, unknown>) => {
    setFailed(null);
    setMessages((m) => [...m, userMessage(label)]);
    const attempt = () => {
      setFailed(null);
      chat.mutate(
        { endpoint, body: { ...body, context } },
        {
          onSuccess: (answer) => setMessages((m) => [...m, assistantMessage(answer)]),
          onError: () => setFailed(() => attempt),
        },
      );
    };
    attempt();
  };

  const runChip = (chip: Chip) => run(chip.label, chip.action.endpoint, chip.action.body ?? {});
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scroller} role="log" aria-label="Suhbat" tabIndex={0} className="-mx-1 flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-1 py-1">
        {messages.length === 0 && empty ? (
          <div>
            <p className="text-[14px] text-text-2">{empty.text}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {empty.chips.map((chip) => (
                <Button key={chip.label} onClick={() => runChip(chip)}>
                  {chip.label}
                </Button>
              ))}
            </div>
          </div>
        ) : null}
        {messages.map((m) =>
          m.role === "user" ? (
            <p key={m.id} className="fade-in max-w-[85%] self-end rounded-[16px] bg-[rgb(15_23_22/0.06)] px-4 py-3 text-[14px]">
              {m.text}
            </p>
          ) : (
            <div key={m.id} className="fade-in flex flex-col gap-3">
              <div className={cn("flex flex-col gap-4 rounded-[16px] bg-white/70", compact ? "p-3" : "p-4")}>
                {m.answer.blocks.map((block, i) => (
                  <BlockView key={i} block={block} compact={compact} />
                ))}
              </div>
              {m === lastAssistant && m.answer.chips.length ? (
                <div className="flex flex-wrap gap-2">
                  {m.answer.chips.map((chip) => (
                    <Button key={chip.label} disabled={chat.isPending} onClick={() => runChip(chip)}>
                      {chip.label}
                    </Button>
                  ))}
                </div>
              ) : null}
            </div>
          ),
        )}
        {chat.isPending ? (
          <div role="status" aria-label="Javob tayyorlanmoqda" className="flex flex-col gap-2">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-5 w-1/2" />
          </div>
        ) : null}
        {failed ? (
          <div role="alert" className="flex items-center gap-2 text-[14px] text-text-2">
            Javob olinmadi.
            <Button variant="plain" onClick={failed}>
              Qayta urinish
            </Button>
          </div>
        ) : null}
      </div>
      <form
        className="mt-3"
        onSubmit={(e) => {
          e.preventDefault();
          const text = input.trim();
          if (!text || chat.isPending) return;
          setInput("");
          run(text, "/advisor/chat", { message: text });
        }}
      >
        <label className="field-label mb-1 text-[12px]" htmlFor={compact ? "copilot-input" : "chat-input"}>
          Savolingiz
        </label>
        <div className="relative">
          <input
            id={compact ? "copilot-input" : "chat-input"}
            autoFocus={autoFocus}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={compact ? "Savol bering" : "Savol bering yoki ovozli xabar yuboring"}
            className="input h-[52px] pr-16"
          />
          <span aria-hidden className="t-mono-cap absolute top-1/2 right-4 -translate-y-1/2">
            Enter
          </span>
        </div>
      </form>
    </div>
  );
}
