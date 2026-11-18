"use client";

import { Download } from "lucide-react";
import { RangeBar, ScheduleBars } from "@/components/charts/small";
import { Button } from "@/components/ui/button";
import { download } from "@/lib/api/client";
import { type Block, scheduleRows } from "@/lib/api/backend/advisor";
import { num, shortSoum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Swatch } from "./tile";

const SERIES_COLORS = ["var(--chart-s1)", "var(--chart-s3)", "var(--accent)", "var(--text-2)"];

const fmtUnit = (unit: string) => (v: number) => (unit === "UZS" ? shortSoum(v) : num(v));

function cell(value: unknown) {
  if (typeof value === "number") return num(value);
  if (value === null || value === undefined) return "—";
  return String(value);
}

function Legend({ names }: { names: string[] }) {
  if (names.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-3 text-[12px] text-text-2">
      {names.map((n, i) => (
        <li key={n} className="flex items-center gap-2">
          <Swatch color={SERIES_COLORS[i % SERIES_COLORS.length]} />
          {n}
        </li>
      ))}
    </ul>
  );
}

function LineChart({ block, compact }: { block: Extract<Block, { type: "line_chart" }>; compact?: boolean }) {
  const W = 100;
  const H = compact ? 80 : 110;
  const all = block.series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  const min = Math.min(0, ...all);
  const max = Math.max(...all, min + 1);
  const n = block.x.length;
  const x = (i: number) => (n > 1 ? (i / (n - 1)) * W : W / 2);
  const y = (v: number) => H - ((v - min) / (max - min)) * H;
  const fmt = fmtUnit(block.unit);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold">{block.title}</h3>
        <Legend names={block.series.map((s) => s.name)} />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="block w-full" style={{ height: H }} role="img" aria-label={block.title}>
        {min < 0 ? <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--border-strong)" strokeWidth={1} vectorEffect="non-scaling-stroke" /> : null}
        {block.series.map((s, si) => (
          <polyline
            key={s.name}
            fill="none"
            stroke={SERIES_COLORS[si % SERIES_COLORS.length]}
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
            points={s.values.flatMap((v, i) => (v === null ? [] : [`${x(i)},${y(v)}`])).join(" ")}
          />
        ))}
      </svg>
      <div className="t-mono-cap mt-1 flex justify-between">
        <span>{block.x[0]}</span>
        <span>{block.x[n - 1]}</span>
      </div>
      <table className="sr-only">
        <tbody>
          {block.x.map((label, i) => (
            <tr key={label}>
              <th>{label}</th>
              {block.series.map((s) => (
                <td key={s.name}>{s.values[i] === null ? "—" : `${s.name}: ${fmt(s.values[i] as number)}`}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BarChart({ block }: { block: Extract<Block, { type: "bar_chart" }> }) {
  const max = Math.max(1, ...block.series.flatMap((s) => s.values.map((v) => Math.abs(v ?? 0))));
  const fmt = fmtUnit(block.unit);
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold">{block.title}</h3>
        <Legend names={block.series.map((s) => s.name)} />
      </div>
      <ul className="mt-2 flex flex-col gap-2">
        {block.x.map((label, i) => (
          <li key={label} className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-2 text-[12px]">
            <span className="truncate" title={label}>
              {label}
            </span>
            <span className="flex flex-col gap-1">
              {block.series.map((s, si) => {
                const v = s.values[i];
                return (
                  <span key={s.name} className="grid grid-cols-[minmax(0,1fr)_72px] items-center gap-2">
                    <span className="h-2 rounded-full bg-[rgb(15_23_22/0.06)]">
                      <span className="block h-full rounded-full" style={{ width: `${(Math.abs(v ?? 0) / max) * 100}%`, background: SERIES_COLORS[si % SERIES_COLORS.length] }} />
                    </span>
                    <span className="mono text-right">{v === null ? "—" : fmt(v)}</span>
                  </span>
                );
              })}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BlockView({ block, compact }: { block: Block; compact?: boolean }) {
  switch (block.type) {
    case "kpi_row":
      return (
        <div>
          <h3 className="mb-2 text-[13px] font-semibold">{block.title}</h3>
          <dl className={cn("grid gap-4", compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-[repeat(var(--n),minmax(0,1fr))]")} style={{ "--n": block.items.length } as React.CSSProperties}>
            {block.items.map((item, i) => {
              const value = item.value_uzs != null ? shortSoum(item.value_uzs) : item.value != null ? (typeof item.value === "number" ? num(item.value, Number.isInteger(item.value) ? 0 : 1) : item.value) : "—";
              return (
                <div key={item.label} className={cn("min-w-0", !compact && i > 0 && "md:border-l md:border-[rgb(15_23_22/0.08)] md:pl-4")}>
                  <dt className="text-[12px] text-text-2">{item.label}</dt>
                  <dd className={cn("serif truncate", compact ? "text-[24px]" : "text-[28px]")} title={value}>
                    {value}
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      );
    case "price_range": {
      const marker = block.your_price_uzs ?? null;
      const lo = Math.min(block.p25_uzs, marker ?? block.p25_uzs, block.buy_price_uzs ?? block.p25_uzs);
      const hi = Math.max(block.p75_uzs, marker ?? block.p75_uzs);
      return (
        <div>
          <h3 className="mb-3 text-[13px] font-semibold">{block.title}</h3>
          <RangeBar
            min={lo * 0.92}
            max={hi * 1.04}
            bandLow={block.p25_uzs}
            bandHigh={block.p75_uzs}
            markers={[
              { value: block.fair_uzs, label: `Bozor ${shortSoum(block.fair_uzs)}`, tone: "text" },
              ...(marker != null ? [{ value: marker, label: shortSoum(marker), tone: "accent" as const }] : []),
            ]}
            ends={`${shortSoum(block.p25_uzs)} – ${shortSoum(block.p75_uzs)}`}
            ariaLabel={`${block.title}: bozor narxi ${shortSoum(block.fair_uzs)}`}
          />
          <p className="t-cap mt-2 text-text-2">
            {block.comparables} ta e’lon · {block.basis} · ishonch: {block.confidence}
            {block.buy_price_uzs != null ? ` · xarid narxi ${shortSoum(block.buy_price_uzs)}` : ""}
          </p>
        </div>
      );
    }
    case "comparables":
      return (
        <div>
          <h3 className="text-[13px] font-semibold">{block.title}</h3>
          <ul className="mt-1">
            {block.samples.map((s, i) => (
              <li key={i} className="flex items-baseline justify-between gap-3 py-2 text-[13px]">
                <span className="min-w-0">
                  {s.source_url ? (
                    <a href={s.source_url} target="_blank" rel="noreferrer" className="font-medium underline-offset-2 hover:underline">
                      {s.title}
                    </a>
                  ) : (
                    <span className="font-medium">{s.title}</span>
                  )}{" "}
                  <span className="text-text-2">{[s.condition, s.district, s.seller_type].filter(Boolean).join(" · ")}</span>
                </span>
                <span className="mono shrink-0 text-text-2">{shortSoum(s.price_uzs)}</span>
              </li>
            ))}
          </ul>
        </div>
      );
    case "bar_chart":
      return <BarChart block={block} />;
    case "line_chart":
      return <LineChart block={block} compact={compact} />;
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
                  <tr key={block.row_ids?.[r] ?? r}>
                    {row.map((value, i) => (
                      <td key={i} className={i ? "r mono" : undefined}>
                        {cell(value)}
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
            {block.steps.map((step, i) => (
              <li key={step.label} className="flex gap-2">
                <span className={cn("mono text-[13px]", step.status === "done" ? "text-success" : "text-muted")}>{step.status === "done" ? "✓" : i + 1}</span>
                <span>
                  {step.label}
                  {step.detail ? <span className="block text-[12px] text-text-2">{step.detail}</span> : null}
                </span>
              </li>
            ))}
          </ol>
        </div>
      );
    case "loan_schedule":
      return (
        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="text-[13px] font-semibold">
              {block.title}: {shortSoum(block.principal_uzs)} · {block.months} oy · {num(block.annual_rate_pct, 1)}%
            </h3>
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
          <ScheduleBars schedule={scheduleRows(block.rows)} format={shortSoum} height={compact ? 88 : 116} />
          <p className="t-mono-cap mt-2">
            Oylik to‘lov: {shortSoum(block.monthly_payment_uzs)} · Jami foiz: {shortSoum(block.total_interest_uzs)}
            {block.rows.length < block.months ? ` · Jadvalda birinchi ${block.rows.length} oy` : ""}
          </p>
        </div>
      );
    case "file": {
      const name = block.url.split("?")[0].split("/").pop() || block.title;
      return (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => void download(block.url.replace(/^\/api\/v1(?=\/)/, ""), name)}>
            <Download size={16} strokeWidth={1.75} aria-hidden />
            {block.title}
          </Button>
        </div>
      );
    }
  }
}
