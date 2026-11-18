"use client";

import { dateShort, pctSigned, usd } from "@/lib/format";
import { clamp } from "@/lib/utils";
import { ChartTip, roundedTopBar, useCursor, useWidth } from "./base";

/** Daily sales bars against a reference line (e.g. the 30-day average); `vsLabel` prefixes the tooltip delta. */
export function SalesStrip({ days, plan, caption, todayLabel, vsLabel, height = 88 }: { days: { date: string; value: number }[]; plan: number; caption: string; todayLabel: string; vsLabel: string; height?: number }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(days.length);
  const max = Math.max(...days.map((d) => d.value), plan) * 1.04;
  const y = (v: number) => height - (v / max) * height;
  const step = width / days.length;
  const barW = Math.max(2, step - 4);
  const day = active !== null ? days[active] : null;

  return (
    <div>
      <div ref={ref} className="relative" style={{ height }}>
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={`So‘nggi ${days.length} kunlik savdo, ${caption} ${usd(plan)}`}
            {...chartProps}
            onPointerMove={(e) => {
              const box = e.currentTarget.getBoundingClientRect();
              setActive(clamp(Math.floor((e.clientX - box.left) / step), 0, days.length - 1));
            }}
            onPointerDown={(e) => {
              const box = e.currentTarget.getBoundingClientRect();
              setActive(clamp(Math.floor((e.clientX - box.left) / step), 0, days.length - 1));
            }}
          >
            {days.map((d, i) => {
              const top = y(d.value);
              return (
                <path
                  key={d.date}
                  d={roundedTopBar(i * step + 2, top, barW, height - top)}
                  fill={d.value >= plan ? "var(--chart-s1)" : "var(--border-strong)"}
                  opacity={active !== null && active !== i ? 0.55 : 1}
                  style={{ transition: "opacity 150ms" }}
                />
              );
            })}
            <line x1={0} x2={width} y1={y(plan)} y2={y(plan)} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="3 3" />
          </svg>
        ) : null}
        {day && active !== null ? (
          <ChartTip x={active * step + step / 2} y={-8} width={width} flipAt={130}>
            <div className="meta mono">{dateShort(day.date)}</div>
            <div className="mono">{usd(day.value)}</div>
            <div className="meta">{vsLabel} {pctSigned(((day.value - plan) / plan) * 100)}</div>
          </ChartTip>
        ) : null}
      </div>
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <span className="t-mono-cap">{dateShort(days[0].date)}</span>
        <span className="t-cap truncate-1">
          {caption} {usd(plan)}
        </span>
        <span className="t-mono-cap">{todayLabel}</span>
      </div>
    </div>
  );
}
