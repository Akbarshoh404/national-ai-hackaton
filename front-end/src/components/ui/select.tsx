"use client";

import { Check, ChevronDown } from "lucide-react";
import { Select as S } from "radix-ui";
import { cn } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
}

export function Select({
  id,
  value,
  onValueChange,
  options,
  className,
  "aria-label": ariaLabel,
}: {
  id?: string;
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <S.Root value={value} onValueChange={onValueChange}>
      <S.Trigger id={id} aria-label={ariaLabel} className={cn("input group flex items-center justify-between gap-2 text-left data-[state=open]:border-text-2", className)}>
        <span className="truncate-1">
          <S.Value />
        </span>
        <S.Icon asChild>
          <ChevronDown size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-text-2 transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </S.Icon>
      </S.Trigger>
      <S.Portal>
        <S.Content position="popper" sideOffset={8} collisionPadding={16} className="pop fade-in z-[60] bg-surface max-h-[var(--radix-select-content-available-height)] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-[20px]">
          <S.Viewport className="p-2">
            {options.map((option) => (
              <S.Item
                key={option.value}
                value={option.value}
                className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-[12px] px-3 text-[14px] outline-none transition-colors duration-150 select-none data-[highlighted]:bg-[var(--nested)] data-[state=checked]:bg-accent-soft data-[state=checked]:font-medium data-[state=checked]:text-accent-text"
              >
                <S.ItemText>{option.label}</S.ItemText>
                <S.ItemIndicator>
                  <Check size={16} strokeWidth={1.75} aria-hidden />
                </S.ItemIndicator>
              </S.Item>
            ))}
          </S.Viewport>
        </S.Content>
      </S.Portal>
    </S.Root>
  );
}
