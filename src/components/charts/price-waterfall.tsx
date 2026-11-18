"use client";

import type { PriceStep } from "@/lib/api/schemas";
import { usd, usdSigned } from "@/lib/format";
import { ChartTip, TickText, useCursor, useWidth } from "./base";

const H = 168;
const TOP = 24;
const BOTTOM = 8;
const LEFT = 40;

const COLOR: Record<PriceStep["kind"], string> = {
  start: "var(--text-2)",
  minus: "var(--danger)",
  plus: "var(--success)",
  margin: "var(--border-strong)",
  end: "var(--accent)",
};

export function PriceWaterfall({ steps }: { steps: PriceStep[] }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(steps.length);
  const start = steps[0].delta;
  const end = steps[steps.length - 1].delta;
  const axisStep = start > 2000 ? 1000 : start > 600 ? 100 : 50;
  const axisMin = Math.floor((end * 0.86) / axisStep) * axisStep;
  const axisMax = Math.ceil((start * 1.03) / axisStep) * axisStep;
  const y = (v: number) => TOP + (1 - (v - axisMin) / (axisMax - axisMin)) * (H - TOP - BOTTOM);
  const plotW = Math.max(1, width - LEFT);
  const col = plotW / steps.length;
  const barW = Math.min(36, col * 0.62);
  const barX = (i: number) => LEFT + i * col + (col - barW) / 2;

  let running = 0;
  const bars = steps.map((s) => {
    if (s.kind === "start" || s.kind === "end") {
      running = s.delta;
      return { top: s.delta, bottom: axisMin, level: s.delta };
    }
    const before = running;
    running += s.delta;
    return { top: Math.max(before, running), bottom: Math.min(before, running), level: running };
  });

  const ticks: number[] = [];
  const tickStep = (axisMax - axisMin) / axisStep > 5 ? axisStep * 2 : axisStep;
  for (let v = axisMin + tickStep; v <= axisMax; v += tickStep) ticks.push(v);
  const step = active !== null ? steps[active] : null;

  return (
    <div ref={ref} className="relative">
      {width > 0 ? (
        <>
          <svg width={width} height={H + 8} role="img" aria-label={`Narx tarkibi: ${steps.map((s) => `${s.label} ${s.kind === "start" || s.kind === "end" ? usd(s.delta) : usdSigned(s.delta)}`).join(", ")}`} {...chartProps}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={LEFT} x2={width} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" />
                <TickText x={LEFT - 8} y={y(t) + 4} anchor="end">
                  {usd(t)}
                </TickText>
              </g>
            ))}
            <line x1={LEFT} x2={width} y1={H - BOTTOM} y2={H - BOTTOM} stroke="var(--border-strong)" />
            <TickText x={LEFT - 8} y={H - BOTTOM + 4} anchor="end">
              ≈
            </TickText>
            {bars.slice(0, -1).map((b, i) => (
              <line key={i} x1={barX(i) + barW} x2={barX(i + 1)} y1={y(b.level)} y2={y(b.level)} stroke="var(--text-muted)" strokeDasharray="2 3" />
            ))}
            {steps.map((s, i) => {
              const b = bars[i];
              const top = y(b.top);
              const height = Math.max(4, y(b.bottom) - top);
              const anchored = s.kind === "start" || s.kind === "end";
              const r = Math.min(4, height / 2);
              return (
                <g key={s.label} opacity={active !== null && active !== i ? 0.35 : 1} style={{ transition: "opacity 150ms" }} onPointerEnter={() => setActive(i)} onPointerDown={() => setActive(i)}>
                  <rect x={LEFT + i * col} y={0} width={col} height={H} fill="transparent" />
                  {anchored ? (
                    <path d={`M${barX(i)},${top + height}V${top + r}Q${barX(i)},${top} ${barX(i) + r},${top}H${barX(i) + barW - r}Q${barX(i) + barW},${top} ${barX(i) + barW},${top + r}V${top + height}Z`} fill={COLOR[s.kind]} />
                  ) : (
                    <rect x={barX(i)} y={top} width={barW} height={height} rx={r} fill={COLOR[s.kind]} />
                  )}
                  <text x={barX(i) + barW / 2} y={top - 6} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--text)">
                    {anchored ? usd(s.delta) : usdSigned(s.delta)}
                  </text>
                </g>
              );
            })}
          </svg>
          <div className="grid text-center text-[11px] leading-[14px] text-text-2" style={{ marginLeft: LEFT, gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
            {steps.map((s) => (
              <div key={s.label} className="px-1">
                {s.label}
                {s.sub ? <div>{s.sub}</div> : null}
              </div>
            ))}
          </div>
          {step && active !== null ? (
            <ChartTip x={barX(active) + barW / 2} y={8} width={width} flipAt={200}>
              <div>{step.label}</div>
              <div className="meta">{step.reason}</div>
            </ChartTip>
          ) : null}
        </>
      ) : (
        <div style={{ height: H + 40 }} />
      )}
    </div>
  );
}
