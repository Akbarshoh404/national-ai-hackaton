"use client";

import { Download } from "lucide-react";
import { MiniLine, RangeBar, ScheduleBars } from "@/components/charts/small";
import { Button } from "@/components/ui/button";
import type { Block } from "@/lib/api/schemas";
import { mln, usd } from "@/lib/format";
import { cn, downloadText } from "@/lib/utils";
import { Swatch } from "./tile";

export function BlockView({ block, compact }: { block: Block; compact?: boolean }) {
  switch (block.type) {
    case "text":
      return <p className="text-[14px] leading-[21px]">{block.text}</p>;
    case "kpi_row":
      return (
        <dl className={cn("grid gap-4", compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-[repeat(var(--n),minmax(0,1fr))]")} style={{ "--n": block.items.length } as React.CSSProperties}>
          {block.items.map((item, i) => (
            <div key={item.label} className={cn("min-w-0", !compact && i > 0 && "md:border-l md:border-[rgb(15_23_22/0.08)] md:pl-4")}>
              <dt className="text-[12px] text-text-2">{item.label}</dt>
              <dd className={cn("serif truncate", compact ? "text-[24px]" : "text-[28px]")} title={item.value}>
                {item.value}
              </dd>
            </div>
          ))}
        </dl>
      );
    case "price_range":
      return (
        <div>
          <h3 className="mb-3 text-[13px] font-semibold">{block.title}</h3>
          <RangeBar
            min={Math.min(block.low, block.marker ?? block.low) * 0.92}
            max={block.high * 1.04}
            bandLow={block.low}
            bandHigh={block.high}
            markers={[{ value: block.median, label: `Mediana ${usd(block.median)}`, tone: "text" }, ...(block.marker ? [{ value: block.marker, label: usd(block.marker), tone: "accent" as const }] : [])]}
            ends={`${usd(block.low)} – ${usd(block.high)}`}
            ariaLabel={`${block.title}: mediana ${usd(block.median)}`}
          />
        </div>
      );
    case "comparables":
      return (
        <div>
          <h3 className="text-[13px] font-semibold">{block.title}</h3>
          <ul className="mt-1">
            {block.items.map((item, i) => (
              <li key={i} className="flex items-baseline justify-between gap-3 py-2 text-[13px]">
                <span className="min-w-0">
                  <span className="font-medium">{item.title}</span> <span className="text-text-2">{item.meta}</span>
                </span>
                <span className="shrink-0 text-text-2">{item.value}</span>
              </li>
            ))}
          </ul>
        </div>
      );
    case "bar_chart": {
      const max = Math.max(...block.items.map((i) => i.value));
      return (
        <div>
          <h3 className="text-[13px] font-semibold">{block.title}</h3>
          <ul className="mt-2 flex flex-col gap-2">
            {block.items.map((item) => (
              <li key={item.label} className="grid grid-cols-[80px_minmax(0,1fr)_64px] items-center gap-2 text-[12px]">
                <span className="truncate">{item.label}</span>
                <span className="h-2 rounded-full bg-[rgb(15_23_22/0.06)]">
                  <span className="block h-full rounded-full bg-[var(--chart-s1)]" style={{ width: `${(item.value / max) * 100}%` }} />
                </span>
                <span className="mono text-right">{item.display}</span>
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case "line_chart":
      return (
        <div>
          <h3 className="mb-2 text-[13px] font-semibold">{block.title}</h3>
          <MiniLine labels={block.labels} values={block.values} format={usd} label={block.title} />
        </div>
      );
    case "table":
      return (
        <div>
          <h3 className="text-[13px] font-semibold">{block.title}</h3>
          <div className="mt-1 overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  {block.columns.map((c, i) => (
                    <th key={c} className={i ? "r" : undefined}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, i) => (
                      <td key={i} className={i ? "r mono" : undefined}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );
    case "steps":
      return (
        <div>
          <h3 className="text-[13px] font-semibold">{block.title}</h3>
          <ol className="mt-2 flex flex-col gap-2 text-[14px]">
            {block.items.map((item, i) => (
              <li key={item} className="flex gap-2">
                <span className="mono text-[13px] text-muted">{i + 1}</span>
                {item}
              </li>
            ))}
          </ol>
        </div>
      );
    case "loan_schedule":
      return (
        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="text-[13px] font-semibold">To‘lov jadvali</h3>
            <ul className="flex gap-3 text-[12px] text-text-2">
              <li className="flex items-center gap-2">
                <Swatch color="var(--chart-s1)" />
                Asosiy qarz
              </li>
              <li className="flex items-center gap-2">
                <Swatch color="var(--chart-s3)" />
                Foiz
              </li>
            </ul>
          </div>
          <ScheduleBars schedule={block.schedule} format={(v) => `${mln(v / 1e6, 1)} so‘m`} height={compact ? 88 : 116} />
          <p className="t-mono-cap mt-2">Jami foiz: {mln(block.total_interest / 1e6, 1)} so‘m · Foiz ulushi vaqt o‘tishi bilan kamayadi</p>
        </div>
      );
    case "file":
      return (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => downloadText(block.name, block.content)}>
            <Download size={16} strokeWidth={1.75} aria-hidden />
            {block.name}
          </Button>
          <span className="text-[13px] text-text-2">{block.note}</span>
        </div>
      );
  }
}
