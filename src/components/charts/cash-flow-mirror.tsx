"use client";

import type { CashMonth } from "@/lib/api/schemas";
import { mln } from "@/lib/format";
import { clamp } from "@/lib/utils";
import { ChartTip, TickText, smoothPath, useCursor, useWidth } from "./base";

const AXIS_H = 28;
const LEFT = 32;
const RIGHT = 16;

export function CashFlowMirror({ months, height = 196, labels }: { months: CashMonth[]; height?: number; labels: { income: string; spend: string; net: string; lastYear: string } }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(months.length);
  const half = (height - AXIS_H) / 2;
  const domain = 300;
  const ticks = [100, 200, 300];
  const plotW = Math.max(1, width - LEFT - RIGHT);
  const x = (i: number) => LEFT + (i / (months.length - 1)) * plotW;
  const up = (v: number) => half - (v / domain) * (half - 4);
  const down = (v: number) => half + AXIS_H + (v / domain) * (half - 4);
  const line = (fn: (m: CashMonth) => number, map: (v: number) => number) => smoothPath(months.map((m, i) => [x(i), map(fn(m))]));
  const month = active !== null ? months[active] : null;

  const pick = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    setActive(clamp(Math.round(((e.clientX - box.left - LEFT) / plotW) * (months.length - 1)), 0, months.length - 1));
  };

  return (
    <div ref={ref} className="relative" style={{ height }}>
      {width > 0 ? (
        <svg width={width} height={height} role="img" aria-label="6 oylik tushum va xarajat, mln so‘m" {...chartProps} onPointerMove={pick} onPointerDown={pick}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={LEFT} x2={LEFT + plotW} y1={up(t)} y2={up(t)} stroke="var(--chart-grid)" />
              <line x1={LEFT} x2={LEFT + plotW} y1={down(t)} y2={down(t)} stroke="var(--chart-grid)" />
              <TickText x={LEFT - 8} y={up(t) + 4} anchor="end">
                {t}
              </TickText>
              <TickText x={LEFT - 8} y={down(t) + 4} anchor="end">
                {t}
              </TickText>
            </g>
          ))}
          {months.map((m, i) => (
            <TickText key={m.month} x={x(i)} y={half + AXIS_H / 2 + 4} anchor={i === 0 ? "start" : i === months.length - 1 ? "end" : "middle"}>
              {m.month}
            </TickText>
          ))}
          <path d={line((m) => m.income_ly, up)} fill="none" stroke="var(--chart-s1)" strokeWidth={2} opacity={0.35} />
          <path d={line((m) => m.spend_ly, down)} fill="none" stroke="var(--chart-s3)" strokeWidth={2} opacity={0.35} />
          <path d={line((m) => m.income, up)} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinecap="round" />
          <path d={line((m) => m.spend, down)} fill="none" stroke="var(--chart-s3)" strokeWidth={2} strokeLinecap="round" />
          {month && active !== null ? (
            <g pointerEvents="none">
              <line x1={x(active)} x2={x(active)} y1={0} y2={height} stroke="var(--text-muted)" strokeDasharray="3 3" />
              <circle cx={x(active)} cy={up(month.income)} r={4} fill="var(--chart-s1)" stroke="#fff" strokeWidth={2} />
              <circle cx={x(active)} cy={down(month.spend)} r={4} fill="var(--chart-s3)" stroke="#fff" strokeWidth={2} />
            </g>
          ) : null}
        </svg>
      ) : null}
      {month && active !== null ? (
        <ChartTip x={x(active)} y={height / 2 - 44} width={width} flipAt={170}>
          <div className="meta mono">{month.month}</div>
          <div className="mono">
            {labels.income} {mln(month.income)}
          </div>
          <div className="mono">
            {labels.spend} {mln(month.spend)}
          </div>
          <div className="mono">
            {labels.net} +{mln(month.income - month.spend)}
          </div>
          <div className="meta mono">
            {labels.lastYear}: {mln(month.income_ly - month.spend_ly)}
          </div>
        </ChartTip>
      ) : null}
    </div>
  );
}
