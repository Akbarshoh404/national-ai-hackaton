"use client";

import { useCallback, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { clamp } from "@/lib/utils";

export const FONT_MONO = "var(--font-plex-mono), monospace";

export function useWidth<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** One tab stop per chart: arrow keys move between marks, pointer and tap select directly. */
export function useCursor(count: number) {
  const [active, setActive] = useState<number | null>(null);
  const onKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const dir = e.key === "ArrowRight" ? 1 : -1;
        setActive((v) => clamp((v ?? (dir > 0 ? -1 : count)) + dir, 0, count - 1));
      } else if (e.key === "Escape") setActive(null);
    },
    [count],
  );
  const chartProps = {
    tabIndex: 0,
    onKeyDown,
    onFocus: () => setActive((v) => v ?? count - 1),
    onBlur: () => setActive(null),
    onPointerLeave: (e: React.PointerEvent) => {
      if (e.pointerType === "mouse") setActive(null);
    },
  };
  return { active, setActive, chartProps };
}

export function ChartTip({ x, y, width, flipAt, children }: { x: number; y: number; width: number; flipAt?: number; children: ReactNode }) {
  const tipWidth = flipAt ?? 160;
  const flip = x + tipWidth + 16 > width;
  return (
    <div className="chart-tip fade-in" style={{ top: y, left: flip ? undefined : x + 12, right: flip ? width - x + 12 : undefined }}>
      {children}
    </div>
  );
}

export function TickText({ x, y, children, anchor = "middle", weight }: { x: number; y: number; children: ReactNode; anchor?: "start" | "middle" | "end"; weight?: number }) {
  return (
    <text x={x} y={y} textAnchor={anchor} fontSize={11} fontFamily={FONT_MONO} fill="var(--text-muted)" fontWeight={weight} style={{ fontVariantNumeric: "tabular-nums" }}>
      {children}
    </text>
  );
}

export function roundedTopBar(x: number, y: number, w: number, h: number, r = 4) {
  const radius = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + radius}Q${x},${y} ${x + radius},${y}H${x + w - radius}Q${x + w},${y} ${x + w},${y + radius}V${y + h}Z`;
}

export function linePath(points: [number, number][]) {
  return points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
}

export function smoothPath(points: [number, number][]) {
  if (points.length < 2) return "";
  let d = `M${points[0][0].toFixed(1)},${points[0][1].toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[i + 1];
    const mx = (x0 + x1) / 2;
    d += `C${mx.toFixed(1)},${y0.toFixed(1)} ${mx.toFixed(1)},${y1.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return d;
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean; faded?: boolean }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-text-2">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-2">
          <svg width="16" height="8" aria-hidden>
            <line x1="1" x2="15" y1="4" y2="4" stroke={item.color} strokeWidth="2" strokeLinecap="round" strokeDasharray={item.dashed ? "3 3" : undefined} opacity={item.faded ? 0.35 : 1} />
          </svg>
          {item.label}
        </li>
      ))}
    </ul>
  );
}
