"use client";

import type { InvoiceHistory } from "@/lib/api/schemas";
import { num } from "@/lib/format";
import { ChartTip, FONT_MONO, TickText, roundedTopBar, useCursor, useWidth } from "./base";

const H = 132;
const TOP = 20;
const LEFT = 32;
const LABELS = 36;

/** `over` is the money at risk per entry in mln so‘m; the scale follows the data. */
export function InvoiceAnomalies({ invoices }: { invoices: InvoiceHistory[] }) {
  const [ref, width] = useWidth();
  const { active, setActive, chartProps } = useCursor(invoices.length);
  const peak = Math.max(0.1, ...invoices.map((i) => i.over));
  const pow = 10 ** Math.floor(Math.log10(peak / 3));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * pow * 3 >= peak) ?? 10) * pow;
  const max = step * 3;
  const digits = step < 1 ? 1 : 0;
  const y = (v: number) => TOP + (1 - v / max) * (H - TOP);
  const plotW = Math.max(1, width - LEFT);
  const col = plotW / invoices.length;
  const cx = (i: number) => LEFT + col * i + col / 2;
  const barW = Math.min(24, col * 0.5);
  const item = active !== null ? invoices[active] : null;

  return (
    <div ref={ref} className="relative">
      {width > 0 ? (
        <svg width={width} height={H + LABELS} role="img" aria-label={`Yozuvlar: ${invoices.filter((i) => i.over > 0).length} tasida muammo topilgan`} {...chartProps}>
          {[step, step * 2, step * 3].map((t) => (
            <g key={t}>
              <line x1={LEFT} x2={width} y1={y(t)} y2={y(t)} stroke="rgb(15 23 22 / 0.07)" />
              <TickText x={LEFT - 8} y={y(t) + 4} anchor="end">
                {num(t, digits)}
              </TickText>
            </g>
          ))}
          <line x1={LEFT} x2={width} y1={H} y2={H} stroke="var(--border-strong)" />
          <TickText x={LEFT - 8} y={H + 4} anchor="end">
            mln
          </TickText>
          {invoices.map((inv, i) => {
            const dim = active !== null && active !== i ? 0.45 : 1;
            return (
              <g key={inv.id} onPointerEnter={() => setActive(i)} onPointerDown={() => setActive(i)}>
                <rect x={LEFT + col * i} y={0} width={col} height={H + LABELS} fill="transparent" />
                <g opacity={dim} style={{ transition: "opacity 150ms" }}>
                  {inv.over > 0 ? (
                    <>
                      <path d={roundedTopBar(cx(i) - barW / 2, y(inv.over), barW, H - y(inv.over))} fill="var(--danger)" stroke={inv.current ? "var(--text)" : "none"} strokeWidth={1.5} />
                      <text x={cx(i)} y={y(inv.over) - 6} textAnchor="middle" fontSize={11} fontFamily={FONT_MONO} fill="var(--text)">
                        +{num(inv.over, 1)}
                      </text>
                    </>
                  ) : (
                    <circle cx={cx(i)} cy={H - 8} r={4} fill="var(--success)" />
                  )}
                </g>
                <TickText x={cx(i)} y={H + 16} weight={inv.current ? 500 : undefined}>
                  {inv.id}
                </TickText>
                <TickText x={cx(i)} y={H + 30} weight={inv.current ? 500 : undefined}>
                  {inv.date}
                </TickText>
              </g>
            );
          })}
        </svg>
      ) : (
        <div style={{ height: H + LABELS }} />
      )}
      {item && active !== null ? (
        <ChartTip x={cx(active) + barW / 2} y={Math.max(0, y(item.over) - 8)} width={width} flipAt={150}>
          <div className="meta mono">
            {item.id} · {item.date}
          </div>
          <div>{item.over > 0 ? `${num(item.over, 1)} mln so‘m xavf ostida` : "Muammo topilmagan"}</div>
        </ChartTip>
      ) : null}
    </div>
  );
}
