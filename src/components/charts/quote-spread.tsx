"use client";

import { useMemo, useState } from "react";
import { pctSigned, shortNum, soum } from "@/lib/format";
import { ChartTip, TickText, useCursor, useWidth } from "./base";

const SWARM_Y = 62;
const QUOTE_Y = 136;
const H = 214;
const PAD = 16;
const DOT = 2.5;
const BINS = 40;

export interface SpreadQuote {
  id: number;
  supplier: string;
  price: number;
  recommended: boolean;
  diff_pct: number | null;
  delivery: string;
}

const short = (name: string) => name.replace(/ (Trade|Wholesale|Opt)$/, "");

/** Even, rounded ticks between lo and hi. */
function ticks(lo: number, hi: number, count = 5) {
  const raw = (hi - lo) / (count - 1);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const start = Math.ceil(lo / step) * step;
  const out: number[] = [];
  for (let v = start; v <= hi + 1e-6; v += step) out.push(v);
  return out;
}

/** Market listings (dots) vs the quotes received, with the market median. Values are UZS. */
export function QuoteSpread({ dots, median, quotes }: { dots: number[]; median: number; quotes: SpreadQuote[] }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(quotes.length);
  const [binHover, setBinHover] = useState<number | null>(null);

  const values = [...dots, ...quotes.map((q) => q.price), median];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo) * 0.06 || hi * 0.05 || 1;
  const min = lo - pad;
  const max = hi + pad;
  const x = (v: number) => PAD + ((v - min) / (max - min)) * (width - PAD * 2);
  const binOf = (v: number) => Math.min(BINS - 1, Math.max(0, Math.floor(((v - min) / (max - min)) * BINS)));
  const binCenter = (b: number) => min + ((b + 0.5) / BINS) * (max - min);

  const swarm = useMemo(() => {
    const seen = new Map<number, number>();
    return dots.map((value) => {
      const b = binOf(value);
      const n = seen.get(b) ?? 0;
      seen.set(b, n + 1);
      const offset = Math.ceil(n / 2) * (n % 2 ? -1 : 1) * (DOT * 2 + 1);
      return { value, offset, bin: b };
    });
  }, [dots, min, max]);

  // Labels that would touch move down one line.
  const sorted = [...quotes].sort((a, b) => a.price - b.price);
  const rows = new Map<number, number>();
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
  const inBin = binHover !== null ? swarm.filter((d) => d.bin === binHover) : [];
  const tickValues = ticks(min, max);

  return (
    <div ref={ref} className="relative" style={{ height: H }}>
      {width > 0 ? (
        <svg width={width} height={H} role="img" aria-label={`Bozordagi ${dots.length} ta e’lon va ${quotes.length} ta taklif, mediana ${soum(median)}`} {...chartProps}>
          <text x={0} y={12} fontSize={12} fill="var(--text-muted)">
            Bozordagi {dots.length} ta e’lon
          </text>
          <text x={0} y={QUOTE_Y - 16} fontSize={12} fill="var(--text-muted)">
            Sizga kelgan takliflar
          </text>
          <line x1={x(median)} x2={x(median)} y1={24} y2={QUOTE_Y - 24} stroke="var(--text)" strokeDasharray="3 3" />
          <text x={x(median) + 6} y={32} fontSize={12} fontWeight={500} fill="var(--text)">
            Mediana {shortNum(median)}
          </text>
          {swarm.map((d, i) => (
            <circle key={i} cx={x(d.value)} cy={SWARM_Y + d.offset} r={DOT} fill="var(--border-strong)" />
          ))}
          {Array.from(new Set(swarm.map((d) => d.bin))).map((b) => (
            <rect key={b} x={x(binCenter(b)) - 5} y={SWARM_Y - 26} width={10} height={52} fill="transparent" onPointerEnter={() => setBinHover(b)} onPointerLeave={() => setBinHover(null)} />
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
                  {shortNum(q.price)}
                </text>
              </g>
            );
          })}
          {tickValues.map((t, i, list) => (
            <TickText key={t} x={x(t)} y={H - 2} anchor={i === 0 && x(t) < 30 ? "start" : i === list.length - 1 && x(t) > width - 30 ? "end" : "middle"}>
              {shortNum(t)}
            </TickText>
          ))}
        </svg>
      ) : null}
      {quote && active !== null ? (
        <ChartTip x={x(quote.price)} y={QUOTE_Y - 64} width={width} flipAt={170}>
          <div>{quote.supplier}</div>
          <div className="mono">
            {soum(quote.price)}
            {quote.diff_pct !== null ? ` · xarid narxiga ${pctSigned(quote.diff_pct, 0)}` : ""}
          </div>
          <div className="meta">yetkazish {quote.delivery}</div>
        </ChartTip>
      ) : binHover !== null && inBin.length > 0 ? (
        <ChartTip x={x(binCenter(binHover))} y={SWARM_Y - 48} width={width} flipAt={120}>
          <div className="mono">
            {inBin.length === 1 ? soum(inBin[0].value) : `${shortNum(Math.min(...inBin.map((d) => d.value)))} – ${shortNum(Math.max(...inBin.map((d) => d.value)))}`}
          </div>
          <div className="meta">{inBin.length} ta e’lon</div>
        </ChartTip>
      ) : null}
    </div>
  );
}
