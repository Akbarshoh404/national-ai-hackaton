"use client";

import { Slider as S } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Slider({ className, "aria-label": label, ...props }: ComponentProps<typeof S.Root>) {
  return (
    <S.Root className={cn("relative flex h-11 w-full touch-none items-center select-none", className)} {...props}>
      <S.Track className="relative h-1 w-full grow rounded-full bg-[rgb(15_23_22/0.1)]">
        <S.Range className="absolute h-full rounded-full bg-text" />
      </S.Track>
      <S.Thumb aria-label={label} className="block h-6 w-6 rounded-full border border-border bg-surface shadow-[0_2px_8px_rgb(15_23_22/0.16)]" />
    </S.Root>
  );
}
