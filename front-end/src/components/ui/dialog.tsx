"use client";

import { X } from "lucide-react";
import { Dialog as D } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({
  title,
  description,
  className,
  children,
  hideTitle,
  ...props
}: ComponentProps<typeof D.Content> & { title: string; description?: string; hideTitle?: boolean; children: ReactNode }) {
  return (
    <D.Portal>
      <D.Overlay className="fade-in fixed inset-0 z-40 bg-[rgb(15_23_22/0.24)]" />
      <D.Content
        className={cn(
          "pop fade-in fixed top-1/2 left-1/2 z-50 max-h-[calc(100vh-40px)] w-[calc(100vw-32px)] max-w-[520px] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-[36px] p-5",
          className,
        )}
        {...props}
      >
        {hideTitle ? (
          <D.Title className="sr-only">{title}</D.Title>
        ) : (
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <D.Title className="serif text-[24px]">{title}</D.Title>
              {description ? <D.Description className="mt-1 text-[13px] text-text-2">{description}</D.Description> : null}
            </div>
            <D.Close className="icon-btn -mt-2 -mr-2 shrink-0" aria-label="Yopish">
              <X size={18} strokeWidth={1.75} />
            </D.Close>
          </div>
        )}
        {hideTitle || !description ? <D.Description className="sr-only">{description ?? title}</D.Description> : null}
        {children}
      </D.Content>
    </D.Portal>
  );
}
