"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/raft/states";
import { Button } from "@/components/ui/button";
import type { Answer, Chip } from "@/lib/api/backend/advisor";
import { ApiError } from "@/lib/api/client";
import { chipKind, useChat, useChatSuggestions, useChipAction, type ChatTurn } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { BlockView } from "./blocks";

export type Message = { id: number; role: "user"; text: string } | { id: number; role: "assistant"; answer: Answer };

let nextId = 1;
export const userMessage = (text: string): Message => ({ id: nextId++, role: "user", text });
export const assistantMessage = (answer: Answer): Message => ({ id: nextId++, role: "assistant", answer });

/** Turns the conversation so far into the backend's `history` (text only; blocks stay on screen). */
function history(messages: Message[]): ChatTurn[] {
  return messages.flatMap((m): ChatTurn[] => {
    if (m.role === "user") return [{ role: "user", content: m.text }];
    return m.answer.text ? [{ role: "assistant", content: m.answer.text }] : [];
  });
}

export function Conversation({
  context,
  compact,
  hint,
  autoFocus,
}: {
  context: { screen: string; selected_ids: string[] };
  compact?: boolean;
  /** Shown while the conversation is empty, above the backend's starter questions for this screen. */
  hint?: string;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [failed, setFailed] = useState<{ retry: () => void; message: string } | null>(null);
  const chat = useChat();
  const chipAction = useChipAction();
  const suggestions = useChatSuggestions(context.screen);
  const pending = chat.isPending || chipAction.isPending;
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el && messages.length) el.scrollTo({ top: el.scrollHeight });
  }, [messages, pending]);

  const onError = (retry: () => void) => (error: unknown) =>
    setFailed({ retry, message: error instanceof ApiError && error.status !== 0 && error.code !== "bad_shape" ? error.message : "Javob olinmadi." });

  const ask = (question: string) => {
    const before = messages;
    setFailed(null);
    setMessages((m) => [...m, userMessage(question)]);
    const attempt = () => {
      setFailed(null);
      chat.mutate(
        { question, history: history(before), context },
        { onSuccess: (answer) => setMessages((m) => [...m, assistantMessage(answer)]), onError: onError(attempt) },
      );
    };
    attempt();
  };

  const runChip = (chip: Chip) => {
    const kind = chipKind(chip);
    if (!kind) return;
    if (kind.kind === "navigate") {
      router.push(kind.href);
      return;
    }
    setFailed(null);
    setMessages((m) => [...m, userMessage(chip.label)]);
    const attempt = () => {
      setFailed(null);
      chipAction.mutate(chip, { onSuccess: (answer) => setMessages((m) => [...m, assistantMessage(answer)]), onError: onError(attempt) });
    };
    attempt();
  };

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scroller} role="log" aria-label="Suhbat" tabIndex={0} className="-mx-1 flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-1 py-1">
        {messages.length === 0 ? (
          <div>
            {hint ? <p className="text-[14px] text-text-2">{hint}</p> : null}
            {suggestions.data?.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {suggestions.data.map((q) => (
                  <Button key={q} disabled={pending} onClick={() => ask(q)}>
                    {q}
                  </Button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {messages.map((m) => {
          if (m.role === "user")
            return (
              <p key={m.id} className="fade-in max-w-[85%] self-end rounded-[16px] bg-[rgb(15_23_22/0.06)] px-4 py-3 text-[14px]">
                {m.text}
              </p>
            );
          const chips = m === lastAssistant ? m.answer.chips.filter((c) => chipKind(c) !== null) : [];
          return (
            <div key={m.id} className="fade-in flex flex-col gap-3">
              <div className={cn("flex flex-col gap-4 rounded-[16px] bg-white/70", compact ? "p-3" : "p-4")}>
                {m.answer.text ? <p className="text-[14px] leading-[21px]">{m.answer.text}</p> : null}
                {m.answer.blocks.map((block, i) => (
                  <BlockView key={i} block={block} compact={compact} />
                ))}
              </div>
              {chips.length ? (
                <div className="flex flex-wrap gap-2">
                  {chips.map((chip) => (
                    <Button key={chip.label} disabled={pending} onClick={() => runChip(chip)}>
                      {chip.label}
                    </Button>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
        {pending ? (
          <div role="status" aria-label="Javob tayyorlanmoqda" className="flex flex-col gap-2">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-5 w-1/2" />
          </div>
        ) : null}
        {failed ? (
          <div role="alert" className="flex items-center gap-2 text-[14px] text-text-2">
            {failed.message}
            <Button variant="plain" onClick={failed.retry}>
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
          if (!text || pending) return;
          setInput("");
          ask(text);
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
            maxLength={2000}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Savol bering"
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
