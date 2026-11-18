"use client";

import Link from "next/link";
import { useRef } from "react";
import { Legend } from "@/components/charts/base";
import { SalesStrip } from "@/components/charts/sales-strip";
import { Sparkline, TickBar, TickGauge } from "@/components/charts/small";
import { Page, useCopilotScreen, useShell } from "@/components/raft/shell";
import { Async, EmptyState, ErrorState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Swatch, Tile, TileHeader } from "@/components/raft/tile";
import { fill, useLang, useT, type Lang } from "@/i18n";
import { useActivity, useDashboard, useDecide, useDecisions, useRadar } from "@/lib/api/hooks";
import type { TodayDashboard as Dashboard } from "@/lib/api/backend/today";
import { ApiError } from "@/lib/api/client";
import { dateShort, mln, pct, pctSigned, shortSoum, usd, usdSigned, weekdayDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Labels for tiles whose wording follows the real data (no sales plan, forecast or last-year series exist in the books). */
const LOCAL: Record<Lang, { dailyAvg: string; vsAvg: string; salesSub: string; grade: string; noIndex: string; noRfq: string; noActivity: string; cashSub: string }> = {
  uz: {
    dailyAvg: "Kunlik savdo · punktir, 30 kunlik o‘rtacha",
    vsAvg: "o‘rtachaga",
    salesSub: "Kunlik tushum · so‘nggi 90 kun, punktir — 30 kunlik o‘rtacha",
    grade: "Baho",
    noIndex: "Narx indeksi uchun yetarli e’lon yo‘q.",
    noRfq: "Takliflari bor ochiq so‘rovingiz yo‘q.",
    noActivity: "Hali faoliyat yo‘q.",
    cashSub: "O‘rtacha sof natija {v} oyiga",
  },
  ru: {
    dailyAvg: "Продажи по дням · пунктир, среднее за 30 дней",
    vsAvg: "к среднему",
    salesSub: "Выручка по дням · последние 90 дней, пунктир — среднее за 30 дней",
    grade: "Оценка",
    noIndex: "Недостаточно объявлений для индекса цен.",
    noRfq: "Нет открытых запросов с предложениями.",
    noActivity: "Пока нет действий.",
    cashSub: "Средний чистый результат {v} в месяц",
  },
  en: {
    dailyAvg: "Daily sales · dashed, 30-day average",
    vsAvg: "vs average",
    salesSub: "Daily revenue · last 90 days, dashed — 30-day average",
    grade: "Grade",
    noIndex: "Not enough listings for a price index.",
    noRfq: "No open requests with quotes.",
    noActivity: "No activity yet.",
    cashSub: "Average net result {v} a month",
  },
};

function DecisionTile() {
  const { bugun: t, shell } = useT();
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
          <p>{shell.loadError}</p>
          <button type="button" className="btn -ml-5 text-white underline" onClick={() => void query.refetch()}>
            {shell.retry}
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
            <p className="mt-4 text-[14px] leading-5">{current.message}</p>
            {current.reasons.length ? (
              <ul className="mt-2 flex flex-col gap-1 text-[13px] leading-[18px] opacity-90">
                {current.reasons.map((r) => (
                  <li key={r}>· {r}</li>
                ))}
              </ul>
            ) : null}
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
                  <li key={d.id} className={cn("flex items-baseline justify-between gap-3 py-2 text-[13px]", i > 0 && "border-t border-white/20")}>
                    <span className="min-w-0">{d.title}</span>
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

function SourcingTile() {
  const t = useT().bugun;
  const query = useRadar();
  return (
    <Tile className="flex flex-col">
      <TileHeader
        title={t.sourcing}
        right={
          <>
            <span className="hidden min-[1400px]:inline">Telegram · </span>
            {t.today_lower}
          </>
        }
      />
      <div className="mt-3 flex-1">
        <Async query={query} skeleton={<SkeletonLines rows={3} height={40} />}>
          {(data) => (
            <ul>
              {data.items.slice(0, 3).map((f, i) => (
                <li key={f.id} className={cn("py-2", i > 0 && "border-t border-[rgb(15_23_22/0.06)]")}>
                  <div className="flex items-baseline justify-between gap-2 text-[13px]">
                    <span className="truncate-1 font-medium" title={f.title}>
                      {f.title.replace(/ 8\/256$/, "")}
                    </span>
                    <span className="mono shrink-0 text-[12px] font-medium text-success">{pct(f.diff_pct, 0)}</span>
                  </div>
                  <div className="t-mono-cap mt-1 flex items-baseline justify-between gap-2">
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
      {query.data ? (
        <Link href="/birja?tab=radar" className="link text-[13px]">
          {fill(t.allFinds, { n: query.data.total })}
        </Link>
      ) : null}
    </Tile>
  );
}

function GreetingTile({ data }: { data: Dashboard }) {
  const t = useT().bugun;
  const local = LOCAL[useLang()];
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
            <span className={cn("mono font-medium", data.sales_delta < 0 ? "text-danger" : "text-success")}>
              {usdSigned(data.sales_delta)}
              {data.sales_delta_pct !== null ? ` · ${pctSigned(data.sales_delta_pct)}` : ""}
            </span>{" "}
            <span className="text-text-2">{t.vsYesterday}</span>
          </p>
        </div>
      </div>
      <SalesStrip days={data.strip30} plan={data.avg_daily} caption={local.dailyAvg} vsLabel={local.vsAvg} todayLabel={t.today} />
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
      <ul className="mt-auto flex flex-col gap-1 pt-2 text-[13px]">
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
  const local = LOCAL[useLang()];
  const budgetTitle = `${t.budget.split(" · ")[0]} · ${data.budget.month}`;
  return (
    <Tile className="flex flex-col">
      <p className="text-[13px] text-text-2">{budgetTitle}</p>
      <p className="serif mt-1 text-[28px]">
        {mln(data.budget.spent)} / {mln(data.budget.limit)}
      </p>
      <div className="mt-2">
        <TickBar value={Math.min(data.budget.spent, data.budget.limit)} max={data.budget.limit || 1} label={`${budgetTitle}: ${data.budget.spent} / ${data.budget.limit} mln`} />
      </div>
      {data.budget.warning ? <p className="mt-1 text-[12px] font-medium text-warning">{data.budget.warning}</p> : null}
      <hr className="my-4 border-[rgb(15_23_22/0.06)]" />
      <p className="text-[13px] text-text-2">{t.credit}</p>
      <p className="serif mt-1 text-[28px]">{data.credit.score} / 100</p>
      <div className="mt-2">
        <TickBar value={data.credit.score} max={100} label={`${t.credit}: ${data.credit.score} / 100`} />
      </div>
      <p className="mt-1 text-[12px] text-text-2">
        {local.grade}: {data.credit.grade}
      </p>
    </Tile>
  );
}

/** Six months of income (up) and spend (down), millions of so‘m, straight from the books. */
function CashBars({ months, labels }: { months: Dashboard["cash"]; labels: { income: string; spend: string; net: string } }) {
  const max = Math.max(1, ...months.flatMap((m) => [m.income, m.spend]));
  const half = 72;
  return (
    <ul className="grid gap-2" style={{ gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` }} aria-label={`${labels.income} / ${labels.spend}, mln so‘m`}>
      {months.map((m) => (
        <li key={m.month} className="flex flex-col items-center" title={`${m.month}: ${labels.income} ${mln(m.income)}, ${labels.spend} ${mln(m.spend)}, ${labels.net} ${mln(m.net)}`}>
          <div className="flex w-full items-end justify-center" style={{ height: half }}>
            <div className="w-3/5 rounded-t-[4px]" style={{ height: (m.income / max) * half, background: "var(--chart-s1)", opacity: m.partial ? 0.6 : 1 }} />
          </div>
          <span className="t-mono-cap py-1">{m.month.slice(5)}</span>
          <div className="flex w-full items-start justify-center" style={{ height: half }}>
            <div className="w-3/5 rounded-b-[4px]" style={{ height: (m.spend / max) * half, background: "var(--chart-s3)", opacity: m.partial ? 0.6 : 1 }} />
          </div>
          <span className={cn("mono mt-1 text-[11px]", m.net < 0 ? "text-danger" : "text-text-2")}>{mln(m.net)}</span>
        </li>
      ))}
    </ul>
  );
}

function ActivityTile() {
  const t = useT().bugun;
  const local = LOCAL[useLang()];
  const query = useActivity();
  return (
    <Tile className="md:col-span-2">
      <TileHeader title={t.activity} />
      <div className="mt-3">
        <Async query={query} skeleton={<SkeletonLines rows={5} height={28} />} isEmpty={(d) => d.items.length === 0} empty={<EmptyState text={local.noActivity} />}>
          {(d) => (
            <ul>
              {d.items.slice(0, 6).map((row) => (
                <li key={row.id} className="flex items-baseline gap-4 py-2 text-[13px]">
                  <span className="t-mono-cap w-11 shrink-0">{row.time}</span>
                  <span className="truncate-1 flex-1" title={row.text}>
                    {row.text}
                  </span>
                  <span className="t-mono-cap shrink-0 text-right">{row.actor}</span>
                </li>
              ))}
            </ul>
          )}
        </Async>
      </div>
    </Tile>
  );
}

function BugunContent({ data }: { data: Dashboard }) {
  const t = useT().bugun;
  const local = LOCAL[useLang()];
  const rfqPrices = data.rfq?.quotes.map((q) => q.price) ?? [];
  const minQuote = Math.min(...rfqPrices);
  const maxQuote = Math.max(...rfqPrices);
  return (
    <>
      <GreetingTile data={data} />
      <SourcingTile />
      <DecisionTile />

      <Tile className="min-w-0 md:col-span-2 xl:col-span-3">
        <TileHeader title={t.sales} sub={local.salesSub} />
        <div className="mt-3">
          <SalesStrip days={data.strip90} plan={data.avg_daily} caption={local.dailyAvg} vsLabel={local.vsAvg} todayLabel={t.today} height={320} />
        </div>
      </Tile>

      <StockTile data={data.stock_health} />
      <Tile className="flex flex-col md:col-span-2">
        <TileHeader title={t.cash} sub={fill(local.cashSub, { v: `${data.avg_net > 0 ? "+" : ""}${mln(data.avg_net)} so‘m` })} />
        <div className="mt-2">
          <Legend
            items={[
              { label: t.income, color: "var(--chart-s1)" },
              { label: t.spend, color: "var(--chart-s3)" },
            ]}
          />
        </div>
        <div className="mt-auto pt-2">
          <CashBars months={data.cash} labels={{ income: t.income, spend: t.spend, net: t.net }} />
        </div>
      </Tile>
      <LimitsTile data={data} />

      <ActivityTile />

      <Tile className="flex flex-col">
        {data.index ? (
          <>
            <TileHeader title={t.index} sub={data.index.subtitle} />
            <p className="mt-2 flex items-baseline gap-2">
              <span className="serif text-[32px]">{usd(data.index.price)}</span>
              {data.index.change_pct !== null ? (
                <span className={cn("mono text-[12px]", data.index.change_pct < 0 ? "text-danger" : "text-success")}>
                  {pctSigned(data.index.change_pct)} <span className="font-sans text-text-2">{t.in7}</span>
                </span>
              ) : null}
            </p>
            <div className="mt-2">
              <Sparkline series={data.index.series} label={`${data.index.subtitle}: ${t.band}`} height={64} />
            </div>
            <div className="mt-1 flex justify-between">
              <span className="t-mono-cap">{dateShort(data.index.from)}</span>
              <span className="t-mono-cap">{t.today}</span>
            </div>
            <p className="t-cap mt-auto">{t.band}</p>
          </>
        ) : (
          <>
            <TileHeader title={t.index} />
            <EmptyState text={local.noIndex} />
          </>
        )}
      </Tile>

      <Tile className="flex flex-col">
        {data.rfq ? (
          <>
            <TileHeader title={`Birja · RFQ #${data.rfq.id}`} sub={data.rfq.subtitle} />
            <p className="serif mt-2 text-[28px]">{fill(t.quotes, { n: data.rfq.quotes.length })}</p>
            <ul className="mt-2 flex flex-col gap-2">
              {data.rfq.quotes.map((q) => (
                <li key={q.name}>
                  <div className="flex items-baseline justify-between text-[13px]">
                    <span className={cn(q.best && "font-medium")}>{q.name}</span>
                    <span className="mono text-[12px] font-medium">{shortSoum(q.price)}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-[rgb(15_23_22/0.06)]">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${maxQuote > minQuote ? 30 + ((q.price - minQuote) / (maxQuote - minQuote)) * 70 : 100}%`, background: q.best ? "var(--chart-s1)" : "var(--border-strong)" }}
                    />
                  </div>
                </li>
              ))}
            </ul>
            <Link href="/birja" className="link mt-auto pt-2 text-[13px]">
              {t.compare}
            </Link>
          </>
        ) : (
          <>
            <TileHeader title="Birja · RFQ" />
            <EmptyState text={local.noRfq} />
          </>
        )}
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
    <Page title={nav.bugun} subtitle={query.data ? weekdayDate(query.data.today) : undefined}>
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
