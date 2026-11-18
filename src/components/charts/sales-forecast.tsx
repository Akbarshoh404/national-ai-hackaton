"use client";

import { ArrowLeftRight } from "lucide-react";
import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { SalesDay } from "@/lib/api/schemas";
import { compactUsd, dateShort, pctSigned, usd } from "@/lib/format";
import { clamp } from "@/lib/utils";
import { ChartTip, Legend, TickText, linePath, useWidth } from "./base";

const WINDOW = 60;
const M = { top: 20, right: 8, bottom: 24, left: 44 };
const PLOT_H = 196;
const NAV_H = 36;

const valueOf = (d: SalesDay) => d.actual ?? d.forecast ?? 0;

export function SalesForecast({ days, todayIndex, initialStart }: { days: SalesDay[]; todayIndex: number; initialStart: number }) {
  const [ref, width] = useWidth();
  const [start, setStart] = useState(initialStart);
  const [hover, setHover] = useState<number | null>(null);
  const drag = useRef<{ x: number; start: number } | null>(null);
  const navDrag = useRef<{ x: number; start: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const maxStart = days.length - WINDOW;
  const plotW = Math.max(1, width - M.left - M.right);
  const dayW = plotW / (WINDOW - 1);

  // The y-scale spans all days, so it stays still while panning.
  const { yMin, yMax, ticks } = useMemo(() => {
    const all = days.flatMap((d) => [d.actual, d.last_year, d.high, d.low].filter((v): v is number => v !== null));
    const lo = Math.floor(Math.min(...all) / 1000) * 1000;
    const hi = Math.ceil(Math.max(...all) / 1000) * 1000;
    const list: number[] = [];
    for (let v = lo; v <= hi; v += 1000) list.push(v);
    return { yMin: lo, yMax: hi, ticks: list };
  }, [days]);

  const x = (i: number) => M.left + (i - start) * dayW;
  const y = (v: number) => M.top + (1 - (v - yMin) / (yMax - yMin)) * (PLOT_H - M.top);

  const from = Math.max(0, start - 1);
  const to = Math.min(days.length - 1, start + WINDOW);
  const slice = days.slice(from, to + 1).map((d, k) => ({ d, i: from + k }));
  const actual = slice.filter(({ d }) => d.actual !== null);
  const forecast = slice.filter(({ d }) => d.forecast !== null);
  const band = slice.filter(({ d }) => d.low !== null && d.high !== null);

  const visible = days.slice(start, start + WINDOW);
  const total = visible.reduce((sum, d) => sum + valueOf(d), 0);
  const lastYear = visible.reduce((sum, d) => sum + d.last_year, 0);
  const change = ((total - lastYear) / lastYear) * 100;
  const todayX = x(todayIndex);
  const todayVisible = todayIndex >= start && todayIndex < start + WINDOW;
  const zoneStart = clamp(todayX, M.left, M.left + plotW);
  const zoneVisible = todayIndex < start + WINDOW - 1;

  const period = `${dateShort(visible[0].date)} – ${dateShort(visible[visible.length - 1].date)}`;
  const includesForecast = start + WINDOW - 1 > todayIndex;

  const pan = (next: number) => setStart(clamp(Math.round(next), 0, maxStart));

  const indexAt = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    return clamp(Math.round((e.clientX - box.left - M.left) / dayW) + start, start, start + WINDOW - 1);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 7 : 1;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      pan(start - step);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      pan(start + step);
    } else if (e.key === "Home") {
      e.preventDefault();
      pan(0);
    } else if (e.key === "End") {
      e.preventDefault();
      pan(maxStart);
    }
  };

  const point = hover !== null ? days[hover] : null;
  const dateTicks = visible.map((d, k) => ({ d, i: start + k })).filter((_, k) => k % 12 === 0);

  const navX = (i: number) => (i / (days.length - 1)) * width;
  const navValues = days.map(valueOf);
  const navMin = Math.min(...navValues);
  const navMax = Math.max(...navValues);
  const navY = (v: number) => 6 + (1 - (v - navMin) / (navMax - navMin)) * (NAV_H - 12);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div>
          <p className="mono text-[12px] text-text-2">
            {period}
            {includesForecast ? <span className="font-sans"> · prognoz bilan</span> : null}
          </p>
          <p className="mt-1 flex flex-wrap items-baseline gap-x-3">
            <span className="serif text-[32px]">{usd(total)}</span>
            <span className="text-[13px]">
              <span className={`mono font-medium ${change >= 0 ? "text-success" : "text-danger"}`}>{pctSigned(change)}</span> <span className="text-text-2">o‘tgan yilga nisbatan</span>
            </span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Legend
            items={[
              { label: "Bu yil", color: "var(--chart-s1)" },
              { label: "O‘tgan yil", color: "var(--chart-s3)" },
              { label: "Prognoz (ehtimoliy oraliq)", color: "var(--chart-s1)", dashed: true },
            ]}
          />
          <p className="t-cap flex items-center gap-1">
            <ArrowLeftRight size={16} strokeWidth={1.75} aria-hidden />
            Sudrang: vaqt bo‘ylab yuring
          </p>
        </div>
      </div>

      <div ref={ref} className="relative mt-2 select-none" style={{ height: PLOT_H + M.bottom + 8 + NAV_H }}>
        {width > 0 ? (
          <>
            <svg
              width={width}
              height={PLOT_H + M.bottom}
              role="slider"
              tabIndex={0}
              aria-label="Savdo grafigi: 60 kunlik oynani surish"
              aria-valuemin={0}
              aria-valuemax={maxStart}
              aria-valuenow={start}
              aria-valuetext={`${period}, jami ${usd(total)}`}
              onKeyDown={onKeyDown}
              style={{ cursor: dragging ? "grabbing" : "grab", touchAction: "pan-y" }}
              onPointerDown={(e) => {
                e.currentTarget.setPointerCapture(e.pointerId);
                drag.current = { x: e.clientX, start };
                setDragging(true);
                setHover(indexAt(e));
              }}
              onPointerMove={(e) => {
                if (drag.current) {
                  pan(drag.current.start - (e.clientX - drag.current.x) / dayW);
                  setHover(null);
                } else setHover(indexAt(e));
              }}
              onPointerUp={() => {
                drag.current = null;
                setDragging(false);
              }}
              onPointerLeave={() => !drag.current && setHover(null)}
            >
              <defs>
                <clipPath id="sales-clip">
                  <rect x={M.left} y={0} width={plotW} height={PLOT_H} />
                </clipPath>
              </defs>
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={M.left} x2={M.left + plotW} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} />
                  <TickText x={M.left - 8} y={y(t) + 4} anchor="end">
                    {compactUsd(t)}
                  </TickText>
                </g>
              ))}
              <g clipPath="url(#sales-clip)">
                {zoneVisible ? <rect x={zoneStart} y={0} width={M.left + plotW - zoneStart} height={PLOT_H} fill="var(--chart-zone)" opacity={0.75} /> : null}
                {band.length > 1 ? (
                  <path
                    d={`${linePath(band.map(({ d, i }) => [x(i), y(d.high as number)]))}L${[...band]
                      .reverse()
                      .map(({ d, i }) => `${x(i).toFixed(1)},${y(d.low as number).toFixed(1)}`)
                      .join("L")}Z`}
                    fill="var(--chart-s1)"
                    opacity={0.14}
                  />
                ) : null}
                <path d={linePath(slice.map(({ d, i }) => [x(i), y(d.last_year)]))} fill="none" stroke="var(--chart-s3)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
                {actual.length > 1 ? <path d={linePath(actual.map(({ d, i }) => [x(i), y(d.actual as number)]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" /> : null}
                {forecast.length > 1 ? <path d={linePath(forecast.map(({ d, i }) => [x(i), y(d.forecast as number)]))} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeDasharray="5 4" strokeLinejoin="round" /> : null}
              </g>
              {todayVisible ? (
                <g>
                  <line x1={todayX} x2={todayX} y1={4} y2={PLOT_H} stroke="var(--text)" strokeWidth={1} />
                  <text x={todayX - 6} y={14} textAnchor="end" fontSize={12} fontWeight={600} fill="var(--text)">
                    Bugun
                  </text>
                  {zoneVisible ? (
                    <text x={todayX + 6} y={14} fontSize={12} fill="var(--text-2)">
                      Prognoz
                    </text>
                  ) : null}
                </g>
              ) : null}
              {dateTicks.map(({ d, i }, k) => (
                <TickText key={d.date} x={x(i)} y={PLOT_H + 16} anchor={k === 0 ? "start" : "middle"}>
                  {dateShort(d.date)}
                </TickText>
              ))}
              {point && hover !== null ? (
                <g pointerEvents="none">
                  <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={PLOT_H} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="3 3" />
                  <circle cx={x(hover)} cy={y(valueOf(point))} r={4} fill="var(--chart-s1)" stroke="#fff" strokeWidth={2} />
                  <circle cx={x(hover)} cy={y(point.last_year)} r={3.5} fill="var(--chart-s3)" stroke="#fff" strokeWidth={2} />
                </g>
              ) : null}
            </svg>

            <svg
              width={width}
              height={NAV_H}
              aria-hidden
              className="absolute left-0"
              style={{ top: PLOT_H + M.bottom + 8, touchAction: "none", cursor: "ew-resize" }}
              onPointerDown={(e) => {
                e.currentTarget.setPointerCapture(e.pointerId);
                const box = e.currentTarget.getBoundingClientRect();
                const at = ((e.clientX - box.left) / width) * (days.length - 1);
                const inside = at >= start && at <= start + WINDOW;
                const base = inside ? start : clamp(Math.round(at - WINDOW / 2), 0, maxStart);
                if (!inside) setStart(base);
                navDrag.current = { x: e.clientX, start: base };
              }}
              onPointerMove={(e) => {
                if (navDrag.current) pan(navDrag.current.start + ((e.clientX - navDrag.current.x) / width) * (days.length - 1));
              }}
              onPointerUp={() => (navDrag.current = null)}
            >
              <rect x={0} y={0} width={width} height={NAV_H} rx={12} fill="rgb(15 23 22 / 0.04)" />
              <path d={linePath(navValues.map((v, i) => [navX(i), navY(v)]))} fill="none" stroke="var(--text-muted)" strokeWidth={1} opacity={0.5} />
              <rect x={navX(start)} y={1} width={navX(start + WINDOW - 1) - navX(start)} height={NAV_H - 2} rx={12} fill="rgb(14 124 112 / 0.12)" stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={navX(todayIndex)} x2={navX(todayIndex)} y1={0} y2={NAV_H} stroke="var(--text)" strokeWidth={1} />
            </svg>

            {point && hover !== null ? (
              <ChartTip x={x(hover)} y={28} width={width} flipAt={170}>
                <div className="meta mono">
                  {dateShort(point.date)}
                  {point.actual === null ? " · prognoz" : ""}
                </div>
                <div className="mono">Bu yil {usd(valueOf(point))}</div>
                <div className="mono">O‘tgan yil {usd(point.last_year)}</div>
                {point.actual === null && point.low !== null && point.high !== null ? (
                  <div className="meta mono">
                    {usd(point.low)} – {usd(point.high)}
                  </div>
                ) : null}
              </ChartTip>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
