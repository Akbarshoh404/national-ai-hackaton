"use client";

import { mln } from "@/lib/format";
import { clamp } from "@/lib/utils";
import { ChartTip, TickText, linePath, useCursor, useWidth } from "./base";

const H = 200;
const TOP = 12;
const LEFT = 36;

export function BudgetLine({ spent, limit, day, daysInMonth, daily }: { spent: number; limit: number; day: number; daysInMonth: number; daily: number }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(daysInMonth);
  const valueAt = (d: number) => (d <= day ? spent * (d / day) ** 1.05 : spent + daily * (d - day));
  const end = valueAt(daysInMonth);
  const max = Math.ceil(Math.max(limit, end) / 60) * 60 + 20;
  const plotW = Math.max(1, width - LEFT - 8);
  const x = (d: number) => LEFT + ((d - 1) / (daysInMonth - 1)) * plotW;
  const y = (v: number) => TOP + (1 - v / max) * (H - TOP - 20);
  const past = Array.from({ length: day }, (_, i) => i + 1);
  const future = Array.from({ length: daysInMonth - day + 1 }, (_, i) => day + i);
  const ticks = [0, 60, 120, 180, 240, 300, 360].filter((t) => t < max);
  const current = active !== null ? active + 1 : null;

  return (
    <div ref={ref} className="relative" style={{ height: H }}>
      {width > 0 ? (
        <svg
          width={width}
          height={H}
          role="img"
          aria-label={`Oy oxiri prognozi ${mln(end, 0)} so‘m, limit ${mln(limit)} so‘m`}
          {...chartProps}
          onPointerMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            setActive(clamp(Math.round(((e.clientX - box.left - LEFT) / plotW) * (daysInMonth - 1)), 0, daysInMonth - 1));
          }}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={LEFT} x2={LEFT + plotW} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" />
              <TickText x={LEFT - 8} y={y(t) + 4} anchor="end">
                {t}
              </TickText>
            </g>
          ))}
          <line x1={LEFT} x2={LEFT + plotW} y1={y(limit)} y2={y(limit)} stroke="var(--warning)" strokeDasharray="4 3" />
          <text x={LEFT + 4} y={y(limit) - 6} fontSize={12} fill="var(--warning)">
            Limit {mln(limit)}
          </text>
          <path d={linePath(past.map((d) => [x(d), y(valueAt(d))]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinecap="round" />
          <path d={linePath(future.map((d) => [x(d), y(valueAt(d))]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeDasharray="5 4" />
          {[1, 10, 20, daysInMonth].map((d) => (
            <TickText key={d} x={x(d)} y={H - 4} anchor={d === 1 ? "start" : d === daysInMonth ? "end" : "middle"}>
              {d}-noy
            </TickText>
          ))}
          {current ? (
            <g pointerEvents="none">
              <line x1={x(current)} x2={x(current)} y1={TOP} y2={H - 20} stroke="var(--text-muted)" strokeDasharray="3 3" />
              <circle cx={x(current)} cy={y(valueAt(current))} r={4} fill="var(--chart-s1)" stroke="#fff" strokeWidth={2} />
            </g>
          ) : null}
        </svg>
      ) : null}
      {current ? (
        <ChartTip x={x(current)} y={24} width={width} flipAt={140}>
          <div className="meta mono">
            {current}-noy{current > day ? " · prognoz" : ""}
          </div>
          <div className="mono">{mln(valueAt(current), 0)} so‘m</div>
        </ChartTip>
      ) : null}
    </div>
  );
}
