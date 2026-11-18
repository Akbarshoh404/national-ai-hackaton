"use client";

import { Check, Minus } from "lucide-react";
import { Checkbox as C } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Checkbox({ className, ...props }: ComponentProps<typeof C.Root>) {
  return (
    <C.Root
      className={cn(
        "relative inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-[6px] border border-border-strong bg-white/85 text-on-accent transition-colors duration-150 after:absolute after:-inset-3 after:content-[''] data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent",
        className,
      )}
      {...props}
    >
      <C.Indicator>
        {props.checked === "indeterminate" ? <Minus size={14} strokeWidth={1.75} /> : <Check size={14} strokeWidth={1.75} />}
      </C.Indicator>
    </C.Root>
  );
}
