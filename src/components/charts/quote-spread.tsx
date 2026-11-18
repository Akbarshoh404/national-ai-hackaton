"use client";

import { useMemo, useState } from "react";
import type { Quote } from "@/lib/api/schemas";
import { pctSigned, usd } from "@/lib/format";
import { ChartTip, TickText, useCursor, useWidth } from "./base";

const SWARM_Y = 62;
const QUOTE_Y = 136;
const H = 214;
const PAD = 16;
const DOT = 2.5;

const short = (name: string) => name.replace(" Trade", "").replace(" Wholesale", "");

export function QuoteSpread({ dots, median, quotes }: { dots: number[]; median: number; quotes: Quote[] }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(quotes.length);
  const [dotHover, setDotHover] = useState<number | null>(null);
  const min = 240;
  const max = 290;
  const x = (v: number) => PAD + ((v - min) / (max - min)) * (width - PAD * 2);

  const swarm = useMemo(() => {
    const seen = new Map<number, number>();
    return dots.map((value) => {
      const n = seen.get(value) ?? 0;
      seen.set(value, n + 1);
      const offset = Math.ceil(n / 2) * (n % 2 ? -1 : 1) * (DOT * 2 + 1);
      return { value, offset };
    });
  }, [dots]);

  // Labels that would touch move down one line.
  const sorted = [...quotes].sort((a, b) => a.price - b.price);
  const rows = new Map<string, number>();
  let lastX = -Infinity;
  let lastRow = 0;
  for (const q of sorted) {
    const px = x(q.price);
    const row = px - lastX < 76 ? (lastRow ? 0 : 1) : 0;
    rows.set(q.id, row);
    lastX = px;
    lastRow = row;
  }

  const quote = active !== null ? sorted[active] : null;
  const count = dotHover !== null ? dots.filter((d) => d === dotHover).length : 0;

  return (
    <div ref={ref} className="relative" style={{ height: H }}>
      {width > 0 ? (
        <svg width={width} height={H} role="img" aria-label={`Bozordagi ${dots.length} ta e’lon va ${quotes.length} ta taklif, mediana ${usd(median)}`} {...chartProps}>
          <text x={0} y={12} fontSize={12} fill="var(--text-muted)">
            Bozordagi {dots.length} ta e’lon
          </text>
          <text x={0} y={QUOTE_Y - 16} fontSize={12} fill="var(--text-muted)">
            Sizga kelgan takliflar
          </text>
          <line x1={x(median)} x2={x(median)} y1={24} y2={QUOTE_Y - 24} stroke="var(--text)" strokeDasharray="3 3" />
          <text x={x(median) + 6} y={32} fontSize={12} fontWeight={500} fill="var(--text)">
            Mediana {usd(median)}
          </text>
          {swarm.map((d, i) => (
            <circle key={i} cx={x(d.value)} cy={SWARM_Y + d.offset} r={DOT} fill="var(--border-strong)" />
          ))}
          {Array.from({ length: max - min + 1 }, (_, i) => min + i).map((v) => (
            <rect key={v} x={x(v) - 5} y={SWARM_Y - 26} width={10} height={52} fill="transparent" onPointerEnter={() => setDotHover(v)} onPointerLeave={() => setDotHover(null)} />
          ))}
          {sorted.map((q, i) => {
            const px = x(q.price);
            const anchor = px < 36 ? "start" : px > width - 36 ? "end" : "middle";
            const dy = (rows.get(q.id) ?? 0) * 28;
            const fill = q.recommended ? "var(--accent-text)" : "var(--text-2)";
            return (
              <g key={q.id} onPointerEnter={() => setActive(i)} onPointerDown={() => setActive(i)} onPointerLeave={() => setActive(null)} opacity={active !== null && active !== i ? 0.5 : 1}>
                <rect x={px - 32} y={QUOTE_Y - 10} width={64} height={48 + dy} fill="transparent" />
                <circle cx={px} cy={QUOTE_Y} r={4.5} fill={q.recommended ? "var(--chart-s1)" : "var(--text-2)"} stroke="#fff" strokeWidth={1.5} />
                <text x={px} y={QUOTE_Y + 20 + dy} textAnchor={anchor} fontSize={12} fontWeight={q.recommended ? 600 : 400} fill={fill}>
                  {short(q.supplier)}
                </text>
                <text x={px} y={QUOTE_Y + 34 + dy} textAnchor={anchor} fontSize={12} fontWeight={q.recommended ? 600 : 400} fill={fill}>
                  {usd(q.price)}
                </text>
              </g>
            );
          })}
          {[240, 250, 260, 270, 280, 290].map((t, i, list) => (
            <TickText key={t} x={x(t)} y={H - 2} anchor={i === 0 ? "start" : i === list.length - 1 ? "end" : "middle"}>
              {usd(t)}
            </TickText>
          ))}
        </svg>
      ) : null}
      {quote && active !== null ? (
        <ChartTip x={x(quote.price)} y={QUOTE_Y - 64} width={width} flipAt={170}>
          <div>{quote.supplier}</div>
          <div className="mono">
            {usd(quote.price)} · bozorga {pctSigned(quote.diff_pct, 0)}
          </div>
          <div className="meta">
            {quote.delivery} · kafolat {quote.warranty}
          </div>
        </ChartTip>
      ) : dotHover !== null && count > 0 ? (
        <ChartTip x={x(dotHover)} y={SWARM_Y - 48} width={width} flipAt={120}>
          <div className="mono">{usd(dotHover)}</div>
          <div className="meta">{count} ta e’lon</div>
        </ChartTip>
      ) : null}
    </div>
  );
}
