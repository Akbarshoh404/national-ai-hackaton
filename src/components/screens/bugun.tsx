"use client";

import Link from "next/link";
import { useRef } from "react";
import { CashFlowMirror } from "@/components/charts/cash-flow-mirror";
import { Legend } from "@/components/charts/base";
import { SalesForecast } from "@/components/charts/sales-forecast";
import { SalesStrip } from "@/components/charts/sales-strip";
import { Sparkline, TickBar, TickGauge } from "@/components/charts/small";
import { Page, useCopilotScreen, useShell } from "@/components/raft/shell";
import { Async, ErrorState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Swatch, Tile, TileHeader } from "@/components/raft/tile";
import { fill, useT } from "@/i18n";
import { useDashboard, useDecide, useDecisions, useRadar } from "@/lib/api/hooks";
import type { Dashboard } from "@/lib/api/schemas";
import { ApiError } from "@/lib/api/client";
import { DEMO_TODAY, dateShort, mln, pct, pctSigned, usd, usdSigned, weekdayDate } from "@/lib/format";
import { cn } from "@/lib/utils";

function DecisionTile() {
  const t = useT().bugun;
  const query = useDecisions();
  const decide = useDecide();
  const seen = useRef(0);
  const items = query.data?.items ?? [];
  seen.current = Math.max(seen.current, items.length);
  const current = items[0];
  const failed = decide.isError && !(decide.error instanceof ApiError && decide.error.status === 409);

  return (
    <section className="flex min-h-[640px] min-w-0 flex-col rounded-[36px] bg-accent p-6 text-on-accent shadow-[var(--shadow-tile)] md:col-span-2 xl:col-span-1 xl:col-start-4 xl:row-span-2 xl:row-start-1 xl:min-h-0 [&_:focus-visible]:outline-white">
      <header className="flex items-baseline justify-between gap-2 text-[13px]">
        <h2>{t.decisionTitle}</h2>
        {current ? (
          <span className="mono text-[12px]">
            {seen.current - items.length + 1} / {seen.current}
          </span>
        ) : null}
      </header>

      {query.isPending ? (
        <div className="mt-4 flex flex-col gap-3" role="status" aria-label="Yuklanmoqda">
          {[96, 56, 136].map((h) => (
            <div key={h} className="animate-pulse rounded-[12px] bg-white/10" style={{ height: h }} />
          ))}
        </div>
      ) : query.isError ? (
        <div className="mt-4">
          <p>{useTError}</p>
          <button type="button" className="btn -ml-5 text-white underline" onClick={() => void query.refetch()}>
            Qayta urinish
          </button>
        </div>
      ) : !current ? (
        <div className="mt-4">
          <p className="serif text-[30px]">{t.noDecisions}</p>
          <p className="mt-3 text-[14px]">{t.noDecisionsBody}</p>
        </div>
      ) : (
        <>
          <div key={current.id} className="fade-in">
            <h3 className="serif mt-4 text-[30px]">{current.title}</h3>
            <p className="mt-4 text-[14px] leading-5">{current.reasons}</p>
            <dl className="mt-4 flex flex-col gap-2 rounded-[12px] bg-white/[0.06] p-4 text-[13px]">
              {current.evidence.map((row) => (
                <div key={row.label} className="flex items-baseline justify-between gap-3">
                  <dt>{row.label}</dt>
                  <dd className="mono text-[13px] font-medium whitespace-nowrap">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
          {items.length > 1 ? (
            <div className="mt-5">
              <h3 className="text-[13px]">{t.nextDecisions}</h3>
              <ul className="mt-1">
                {items.slice(1, 4).map((d, i) => (
                  <li key={d.id} className={cn("flex items-baseline justify-between gap-3 py-2.5 text-[13px]", i > 0 && "border-t border-white/20")}>
                    <span className="min-w-0">{d.short}</span>
                    <span className="mono shrink-0 text-[12px]">{d.amount}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-auto flex flex-col gap-1 pt-4">
            {failed ? (
              <p role="alert" className="pb-2 text-[13px]">
                {t.decisionError}
              </p>
            ) : null}
            <button type="button" onClick={() => decide.mutate({ id: current.id, action: "approve" })} className="h-12 rounded-[12px] bg-white px-4 text-[15px] font-semibold text-accent-text transition-colors duration-150 hover:bg-accent-soft">
              {current.action_label}
            </button>
            <button type="button" onClick={() => decide.mutate({ id: current.id, action: "ignore" })} className="h-11 rounded-[12px] text-[14px] font-medium transition-colors duration-150 hover:bg-white/10">
              {t.skip}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

const useTError = "Qarorlarni yuklab bo‘lmadi.";

function SourcingTile() {
  const t = useT().bugun;
  const query = useRadar();
  return (
    <Tile className="flex flex-col">
      <TileHeader title={t.sourcing} right={`Telegram · ${t.today_lower}`} />
      <div className="mt-3 flex-1">
        <Async query={query} skeleton={<SkeletonLines rows={3} height={40} />}>
          {(data) => (
            <ul>
              {data.items.slice(0, 3).map((f, i) => (
                <li key={f.id} className={cn("py-2.5", i > 0 && "border-t border-[rgb(15_23_22/0.06)]")}>
                  <div className="flex items-baseline justify-between gap-2 text-[13px]">
                    <span className="truncate-1 font-medium" title={f.title}>
                      {f.title.replace(/ 8\/256$/, "")}
                    </span>
                    <span className="mono shrink-0 text-[12px] font-medium text-success">{pct(f.diff_pct, 0)}</span>
                  </div>
                  <div className="t-mono-cap mt-0.5 flex items-baseline justify-between gap-2">
                    <span className="truncate-1">
                      {usd(f.price)} · {t.market} {usd(f.market)}
                    </span>
                    <span className="shrink-0">
                      ~{usd(f.profit)} {t.profit}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Async>
      </div>
      <Link href="/birja?tab=radar" className="link text-[13px]">
        {fill(t.allFinds, { n: query.data?.total ?? 23 })}
      </Link>
    </Tile>
  );
}

function GreetingTile({ data }: { data: Dashboard }) {
  const t = useT().bugun;
  const { account } = useShell();
  return (
    <Tile className="flex flex-col justify-between gap-4 md:col-span-2">
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-[260px]">
          <h2 className="serif text-[34px]">
            {t.greeting},
            <br />
            {account.short}
          </h2>
          <p className="mt-2 max-w-[320px] text-[13px] leading-[18px] text-text-2">{data.insight}</p>
        </div>
        <div className="text-right">
          <p className="text-[12px] text-text-2">{t.todaySales}</p>
          <p className="serif mt-1 text-[44px]">{usd(data.sales_today)}</p>
          <p className="mt-1 text-[12px]">
            <span className="mono font-medium text-success">
              {usdSigned(data.sales_delta)} · {pct(data.sales_delta_pct)}
            </span>{" "}
            <span className="text-text-2">{t.vsYesterday}</span>
          </p>
        </div>
      </div>
      <SalesStrip days={data.strip} plan={data.plan} caption={t.dailySales} todayLabel={t.today} />
    </Tile>
  );
}

function StockTile({ data }: { data: Dashboard["stock_health"] }) {
  const t = useT().bugun;
  const segments = [
    { label: t.under, value: data.under, color: "var(--rating-under)" },
    { label: t.fair, value: data.fair, color: "var(--rating-fair)" },
    { label: t.over, value: data.over, color: "var(--rating-over)" },
    { label: t.noData, value: data.no_data, color: "var(--rating-none)" },
  ];
  return (
    <Tile className="flex flex-col">
      <TileHeader title={t.stock} right={`${data.total} ${t.units}`} />
      <div className="mt-2">
        <TickGauge segments={segments} center={String(data.over)} caption={t.overpricedCaption} label={`${t.stock}: ${segments.map((s) => `${s.label} ${s.value}`).join(", ")}`} />
      </div>
      <ul className="mt-auto flex flex-col gap-0.5 pt-2 text-[13px]">
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <Swatch color={s.color} />
            <span className="flex-1">{s.label}</span>
            <span className="mono text-[12px] text-text-2">{s.value}</span>
          </li>
        ))}
      </ul>
    </Tile>
  );
}

function LimitsTile({ data }: { data: Dashboard }) {
  const t = useT().bugun;
  return (
    <Tile className="flex flex-col">
      <p className="text-[13px] text-text-2">{t.budget}</p>
      <p className="serif mt-1 text-[28px]">
        {data.budget.spent} / {mln(data.budget.limit)}
      </p>
      <div className="mt-2">
        <TickBar value={data.budget.spent} max={data.budget.limit} label={`${t.budget}: ${data.budget.spent} / ${data.budget.limit} mln`} />
      </div>
      {data.budget.warning ? <p className="mt-1 text-[12px] font-medium text-warning">{data.budget.warning}</p> : null}
      <hr className="my-4 border-[rgb(15_23_22/0.06)]" />
      <p className="text-[13px] text-text-2">{t.credit}</p>
      <p className="serif mt-1 text-[28px]">{data.credit.score} / 100</p>
      <div className="mt-2">
        <TickBar value={data.credit.score} max={100} label={`${t.credit}: ${data.credit.score} / 100`} />
      </div>
      <p className="mt-1 text-[12px] text-text-2">{fill(t.offers, { n: data.credit.offers })}</p>
    </Tile>
  );
}

function BugunContent({ data }: { data: Dashboard }) {
  const t = useT().bugun;
  const maxQuote = 280;
  const baseQuote = 200;
  return (
    <>
      <GreetingTile data={data} />
      <SourcingTile />
      <DecisionTile />

      <Tile className="min-w-0 md:col-span-2 xl:col-span-3">
        <TileHeader title={t.sales} sub={t.salesSub} />
        <div className="mt-3">
          <SalesForecast days={data.sales.days} todayIndex={data.sales.today_index} initialStart={data.sales.window_start} />
        </div>
      </Tile>

      <StockTile data={data.stock_health} />
      <Tile className="flex flex-col md:col-span-2">
        <TileHeader title={t.cash} sub={fill(t.cashSub, { v: `+${mln(data.avg_net)} so‘m` })} />
        <div className="mt-2">
          <Legend
            items={[
              { label: t.income, color: "var(--chart-s1)" },
              { label: t.spend, color: "var(--chart-s3)" },
              { label: t.lastYear, color: "var(--text-muted)", faded: true },
            ]}
          />
        </div>
        <div className="mt-auto pt-2">
          <CashFlowMirror months={data.cash_flow} labels={{ income: t.income, spend: t.spend, net: t.net, lastYear: t.lastYear }} />
        </div>
      </Tile>
      <LimitsTile data={data} />

      <Tile className="md:col-span-2">
        <TileHeader title={t.activity} right={t.today_lower} />
        <ul className="mt-3">
          {data.activity.map((row, i) => (
            <li key={`${row.text}-${i}`} className="flex items-baseline gap-4 py-2 text-[13px]">
              <span className="t-mono-cap w-11 shrink-0">{row.time}</span>
              <span className="truncate-1 flex-1" title={row.text}>
                {row.text}
              </span>
              <span className="t-mono-cap shrink-0 text-right">{row.value}</span>
            </li>
          ))}
        </ul>
      </Tile>

      <Tile className="flex flex-col">
        <TileHeader title={t.index} sub={data.index.subtitle} />
        <p className="mt-2 flex items-baseline gap-2">
          <span className="serif text-[32px]">{usd(data.index.price)}</span>
          <span className={cn("mono text-[12px]", data.index.change_pct < 0 ? "text-danger" : "text-success")}>
            {pctSigned(data.index.change_pct)} <span className="font-sans text-text-2">{t.in7}</span>
          </span>
        </p>
        <div className="mt-2">
          <Sparkline series={data.index.series} label={`${data.index.subtitle}: ${t.band}`} height={64} />
        </div>
        <div className="mt-1 flex justify-between">
          <span className="t-mono-cap">{dateShort(data.index.from)}</span>
          <span className="t-mono-cap">{t.today}</span>
        </div>
        <p className="t-cap mt-auto">{t.band}</p>
      </Tile>

      <Tile className="flex flex-col">
        <TileHeader title={`Birja · RFQ #${data.rfq.id}`} sub={data.rfq.subtitle} />
        <p className="serif mt-2 text-[28px]">{fill(t.quotes, { n: data.rfq.quotes.length })}</p>
        <ul className="mt-2 flex flex-col gap-2">
          {data.rfq.quotes.map((q) => (
            <li key={q.name}>
              <div className="flex items-baseline justify-between text-[13px]">
                <span className={cn(q.best && "font-medium")}>{q.name}</span>
                <span className="mono text-[12px] font-medium">{usd(q.price)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-[rgb(15_23_22/0.06)]">
                <div className="h-full rounded-full" style={{ width: `${((q.price - baseQuote) / (maxQuote - baseQuote)) * 100}%`, background: q.best ? "var(--chart-s1)" : "var(--border-strong)" }} />
              </div>
            </li>
          ))}
        </ul>
        <Link href="/birja" className="link mt-auto pt-2 text-[13px]">
          {t.compare}
        </Link>
      </Tile>
    </>
  );
}

const gridClass = "grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4 xl:grid-rows-[330px_472px_320px_300px]";

export function BugunScreen() {
  const nav = useT().nav;
  const query = useDashboard();
  useCopilotScreen("bugun");
  return (
    <Page title={nav.bugun} subtitle={weekdayDate(DEMO_TODAY)}>
      {query.isPending ? (
        <div className={gridClass} role="status" aria-label="Yuklanmoqda">
          <Skeleton className="h-[330px] rounded-[36px] md:col-span-2" />
          <Skeleton className="h-[330px] rounded-[36px]" />
          <Skeleton className="rounded-[36px] xl:col-start-4 xl:row-span-2 xl:row-start-1" />
          <Skeleton className="h-[472px] rounded-[36px] md:col-span-2 xl:col-span-3" />
        </div>
      ) : query.isError ? (
        <section className="tile">
          <ErrorState onRetry={() => void query.refetch()} />
        </section>
      ) : (
        <div className={gridClass}>
          <BugunContent data={query.data} />
        </div>
      )}
    </Page>
  );
}
