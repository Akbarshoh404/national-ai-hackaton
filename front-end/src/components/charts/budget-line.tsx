"use client";

import { mln } from "@/lib/format";
import { clamp } from "@/lib/utils";
import { ChartTip, TickText, linePath, useCursor, useWidth } from "./base";

const H = 200;
const TOP = 12;
const LEFT = 36;

/** Round step for ~5 grid lines. */
function niceStep(max: number) {
  const raw = Math.max(max, 1) / 5;
  const pow = 10 ** Math.floor(Math.log10(raw));
  return ([1, 2, 2.5, 5, 10].find((m) => m * pow >= raw) ?? 10) * pow;
}

/** Values in mln so‘m. `cumulative[i]` = real cumulative spend at the end of day i+1; after that a straight projection at `daily`. */
export function BudgetLine({ cumulative, limit, daysInMonth, daily, monthShort }: { cumulative: number[]; limit: number; daysInMonth: number; daily: number; monthShort: string }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(daysInMonth);
  const day = cumulative.length;
  const spent = day ? cumulative[day - 1] : 0;
  const valueAt = (d: number) => (d <= day ? (d >= 1 ? cumulative[d - 1] : 0) : spent + daily * (d - day));
  const end = valueAt(daysInMonth);
  const step = niceStep(Math.max(limit, end));
  const max = Math.ceil(Math.max(limit, end) / step) * step + step / 3;
  const plotW = Math.max(1, width - LEFT - 8);
  const x = (d: number) => LEFT + ((d - 1) / (daysInMonth - 1)) * plotW;
  const y = (v: number) => TOP + (1 - v / max) * (H - TOP - 20);
  const past = Array.from({ length: day }, (_, i) => i + 1);
  const future = day ? Array.from({ length: daysInMonth - day + 1 }, (_, i) => day + i) : [];
  const ticks = Array.from({ length: Math.floor(max / step) + 1 }, (_, i) => i * step).filter((t) => t < max);
  const current = active !== null ? active + 1 : null;

  return (
    <div ref={ref} className="relative" style={{ height: H }}>
      {width > 0 ? (
        <svg
          width={width}
          height={H}
          role="img"
          aria-label={`Oy oxiri prognozi ${mln(end, 0)} so‘m${limit > 0 ? `, limit ${mln(limit)} so‘m` : ""}`}
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
                {Math.round(t)}
              </TickText>
            </g>
          ))}
          {limit > 0 ? (
            <>
              <line x1={LEFT} x2={LEFT + plotW} y1={y(limit)} y2={y(limit)} stroke="var(--warning)" strokeDasharray="4 3" />
              <text x={LEFT + 4} y={y(limit) - 6} fontSize={12} fill="var(--warning)">
                Limit {mln(limit)}
              </text>
            </>
          ) : null}
          {past.length > 1 ? <path d={linePath(past.map((d) => [x(d), y(valueAt(d))]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinecap="round" /> : null}
          {future.length > 1 ? <path d={linePath(future.map((d) => [x(d), y(valueAt(d))]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeDasharray="5 4" /> : null}
          {[1, 10, 20, daysInMonth].map((d) => (
            <TickText key={d} x={x(d)} y={H - 4} anchor={d === 1 ? "start" : d === daysInMonth ? "end" : "middle"}>
              {d}-{monthShort}
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
            {current}-{monthShort}
            {current > day ? " · prognoz" : ""}
          </div>
          <div className="mono">{mln(valueAt(current), 0)} so‘m</div>
        </ChartTip>
      ) : null}
    </div>
  );
}
