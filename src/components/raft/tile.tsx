import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Tile({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("tile", className)} {...props} />;
}

export function TileHeader({ title, sub, right, className }: { title: ReactNode; sub?: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <header className={cn("flex items-start justify-between gap-4", className)}>
      <div className="min-w-0">
        <h2 className="t-title">{title}</h2>
        {sub ? <p className="mt-0.5 text-[13px] leading-[18px] text-text-2">{sub}</p> : null}
      </div>
      {right ? <div className="t-mono-cap shrink-0 pt-0.5">{right}</div> : null}
    </header>
  );
}

export function KpiStrip({ items }: { items: { label: string; value: string; note?: ReactNode; noteClass?: string }[] }) {
  return (
    <section className="tile grid grid-cols-2 gap-5 xl:grid-cols-[repeat(var(--n),minmax(0,1fr))]" style={{ "--n": items.length } as React.CSSProperties}>
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <p className="text-[13px] text-text-2">{item.label}</p>
          <p className="serif mt-1 truncate text-[32px]" title={item.value}>
            {item.value}
          </p>
          {item.note ? <p className={cn("mt-1 text-[13px] text-text-2", item.noteClass)}>{item.note}</p> : null}
        </div>
      ))}
    </section>
  );
}

export function Delta({ value, children, inverse }: { value: number; children: ReactNode; inverse?: boolean }) {
  const good = inverse ? value < 0 : value > 0;
  const tone = Math.abs(value) < 1e-9 ? "text-text-2" : good ? "text-success" : "text-danger";
  return <span className={tone}>{children}</span>;
}

export function Swatch({ color }: { color: string }) {
  return <span aria-hidden className="inline-block h-2 w-2 shrink-0 rounded-[2px]" style={{ background: color }} />;
}
