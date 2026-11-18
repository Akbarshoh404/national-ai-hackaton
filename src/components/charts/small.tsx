"use client";

import { usd } from "@/lib/format";
import type { ScheduleRow } from "@/lib/api/schemas";
import { cn, clamp } from "@/lib/utils";
import { ChartTip, TickText, linePath, useCursor, useWidth } from "./base";

/* TickBar */
export function TickBar({ value, max, ticks = 40, color = "var(--accent)", label }: { value: number; max: number; ticks?: number; color?: string; label: string }) {
  const filled = Math.round((value / max) * ticks);
  return (
    <div role="img" aria-label={label} className="flex h-5 items-center justify-between">
      {Array.from({ length: ticks }, (_, i) => (
        <span
          key={i}
          className="block w-0.5 rounded-full"
          style={{ height: i % 7 === 0 ? 20 : 14, background: i < filled ? color : "var(--border-strong)", opacity: i < filled ? 1 : 0.6 }}
        />
      ))}
    </div>
  );
}

/* TickGauge */
export interface GaugeSegment {
  label: string;
  value: number;
  color: string;
}

export function TickGauge({ segments, center, caption, label }: { segments: GaugeSegment[]; center: string; caption: string; label: string }) {
  const W = 260;
  const H = 140;
  const cx = W / 2;
  const cy = 130;
  const R = 118;
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
  const COUNT = 57;
  let cursor = 0;
  const colors: string[] = [];
  for (const seg of segments) {
    const end = cursor + (seg.value / total) * COUNT;
    while (colors.length < Math.round(end) && colors.length < COUNT) colors.push(seg.color);
    cursor = end;
  }
  while (colors.length < COUNT) colors.push(segments[segments.length - 1]?.color ?? "var(--border)");

  return (
    <div className="relative mx-auto w-full max-w-[260px]" role="img" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" aria-hidden>
        {colors.map((color, i) => {
          const angle = Math.PI - (i / (COUNT - 1)) * Math.PI;
          const long = i % 7 === 0;
          const inner = R - (long ? 20 : 14);
          const c = Math.cos(angle);
          const s = Math.sin(angle);
          return <line key={i} x1={cx + inner * c} y1={cy - inner * s} x2={cx + R * c} y2={cy - R * s} stroke={color} strokeWidth={2.5} strokeLinecap="round" />;
        })}
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex flex-col items-center">
        <span className="serif text-[40px]">{center}</span>
        <span className="t-cap text-text-2">{caption}</span>
      </div>
    </div>
  );
}

/* Sparkline with band */
export function Sparkline({ series, height = 72, label }: { series: { median: number; p25: number; p75: number }[]; height?: number; label: string }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(series.length);
  const min = Math.min(...series.map((d) => d.p25));
  const max = Math.max(...series.map((d) => d.p75));
  const x = (i: number) => 2 + (i / (series.length - 1)) * (width - 8);
  const y = (v: number) => 4 + (1 - (v - min) / (max - min)) * (height - 8);
  const band = [...series.map((d, i) => [x(i), y(d.p75)] as [number, number]), ...[...series].reverse().map((d, i) => [x(series.length - 1 - i), y(d.p25)] as [number, number])];
  const point = active !== null ? series[active] : null;
  return (
    <div ref={ref} className="relative" style={{ height }}>
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={label}
          {...chartProps}
          onPointerMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            setActive(clamp(Math.round(((e.clientX - box.left - 2) / (width - 8)) * (series.length - 1)), 0, series.length - 1));
          }}
        >
          <path d={`${linePath(band)}Z`} fill="var(--chart-s1)" opacity={0.14} />
          <path d={linePath(series.map((d, i) => [x(i), y(d.median)]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={x(active ?? series.length - 1)} cy={y(series[active ?? series.length - 1].median)} r={3} fill="var(--chart-s1)" />
        </svg>
      ) : null}
      {point && active !== null ? (
        <ChartTip x={x(active)} y={0} width={width} flipAt={120}>
          <div className="mono">{usd(point.median)}</div>
          <div className="meta mono">
            {usd(point.p25)} – {usd(point.p75)}
          </div>
        </ChartTip>
      ) : null}
    </div>
  );
}

/* Generic line for copilot blocks */
export function MiniLine({ labels, values, format, height = 96, label }: { labels: string[]; values: number[]; format: (v: number) => string; height?: number; label: string }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(values.length);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const x = (i: number) => 4 + (i / (values.length - 1)) * (width - 8);
  const y = (v: number) => 6 + (1 - (v - min) / (max - min || 1)) * (height - 12);
  return (
    <div ref={ref} className="relative" style={{ height }}>
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={label}
          {...chartProps}
          onPointerMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            setActive(clamp(Math.round(((e.clientX - box.left - 4) / (width - 8)) * (values.length - 1)), 0, values.length - 1));
          }}
        >
          <path d={linePath(values.map((v, i) => [x(i), y(v)]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {active !== null ? <circle cx={x(active)} cy={y(values[active])} r={3} fill="var(--chart-s1)" /> : null}
        </svg>
      ) : null}
      {active !== null ? (
        <ChartTip x={x(active)} y={0} width={width} flipAt={120}>
          <div className="mono">{format(values[active])}</div>
          <div className="meta">{labels[active]}</div>
        </ChartTip>
      ) : null}
    </div>
  );
}

/* RangeBar */
export interface RangeMarker {
  value: number;
  label: string;
  tone: "accent" | "text" | "warning";
}

const toneColor = { accent: "var(--accent)", text: "var(--text)", warning: "var(--warning)" };
const toneText = { accent: "text-accent-text", text: "text-text", warning: "text-warning" };

export function RangeBar({ min, max, bandLow, bandHigh, markers, ends, ariaLabel }: { min: number; max: number; bandLow: number; bandHigh: number; markers: RangeMarker[]; ends?: string; ariaLabel: string }) {
  const pos = (v: number) => clamp(((v - min) / (max - min)) * 100, 0, 100);
  const ordered = [...markers].sort((a, b) => a.value - b.value);
  return (
    <div role="img" aria-label={ariaLabel}>
      <div className="relative h-5">
        <div className="absolute inset-x-0 top-2 h-1 rounded-full bg-[rgb(15_23_22/0.08)]" />
        <div className="absolute top-1.5 h-2 rounded-full bg-border-strong" style={{ left: `${pos(bandLow)}%`, width: `${pos(bandHigh) - pos(bandLow)}%` }} />
        {ordered.map((m) => (
          <span key={m.label} className="absolute top-0 h-5 w-0.5 -translate-x-1/2 rounded-full" style={{ left: `${pos(m.value)}%`, background: toneColor[m.tone] }} />
        ))}
      </div>
      <div className="relative mt-2 h-4 text-[12px] leading-4 font-medium">
        {ordered.map((m) => {
          const p = pos(m.value);
          const edge = p < 18 ? "translate-x-0" : p > 82 ? "-translate-x-full" : "-translate-x-1/2";
          return (
            <span key={m.label} className={cn("absolute whitespace-nowrap", edge, toneText[m.tone])} style={{ left: `${p}%` }}>
              {m.label}
            </span>
          );
        })}
      </div>
      {ends ? <p className="t-mono-cap mt-1 text-right">{ends}</p> : null}
    </div>
  );
}

/* ScheduleBars */
export function ScheduleBars({ schedule, height = 120, format }: { schedule: ScheduleRow[]; height?: number; format: (v: number) => string }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(schedule.length);
  const max = Math.max(...schedule.map((r) => r.principal + r.interest));
  const gap = schedule.length > 30 ? 1 : 4;
  const barW = width ? (width - gap * (schedule.length - 1)) / schedule.length : 0;
  const row = active !== null ? schedule[active] : null;
  const middle = Math.ceil(schedule.length / 2);
  return (
    <div ref={ref} className="relative">
      {width > 0 ? (
        <svg width={width} height={height + 20} role="img" aria-label={`To‘lov jadvali, ${schedule.length} oy`} {...chartProps}>
          {schedule.map((r, i) => {
            const x = i * (barW + gap);
            const ph = (r.principal / max) * height;
            const ih = (r.interest / max) * height;
            const faded = active !== null && active !== i;
            return (
              <g key={r.month} opacity={faded ? 0.45 : 1} onPointerEnter={() => setActive(i)} onPointerDown={() => setActive(i)}>
                <rect x={x - gap / 2} y={0} width={barW + gap} height={height} fill="transparent" />
                <rect x={x} y={height - ph - ih} width={barW} height={Math.max(ih, 0.5)} fill="var(--chart-s3)" rx={Math.min(2, barW / 2)} />
                <rect x={x} y={height - ph} width={barW} height={ph} fill="var(--chart-s1)" />
              </g>
            );
          })}
          <TickText x={0} y={height + 16} anchor="start">
            1-oy
          </TickText>
          <TickText x={(middle - 0.5) * (barW + gap)} y={height + 16}>
            {middle}-oy
          </TickText>
          <TickText x={width} y={height + 16} anchor="end">
            {schedule.length}-oy
          </TickText>
        </svg>
      ) : (
        <div style={{ height: height + 20 }} />
      )}
      {row && active !== null ? (
        <ChartTip x={active * (barW + gap) + barW / 2} y={8} width={width} flipAt={160}>
          <div className="meta">{row.month}-oy</div>
          <div className="mono">Asosiy qarz {format(row.principal)}</div>
          <div className="mono">Foiz {format(row.interest)}</div>
        </ChartTip>
      ) : null}
    </div>
  );
}
