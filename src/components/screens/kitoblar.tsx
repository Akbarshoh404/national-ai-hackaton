"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { BudgetLine } from "@/components/charts/budget-line";
import { InvoiceAnomalies } from "@/components/charts/invoice-anomalies";
import { Page, useCopilotScreen } from "@/components/raft/shell";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { KpiStrip, Swatch, Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { useT } from "@/i18n";
import { useAudit, useBudget, useDidoxSync, useResolveFlag, useRfq, useTransactions } from "@/lib/api/hooks";
import type { Audit, AuditFlag, Budget, Transaction } from "@/lib/api/schemas";
import { dateShort, mln, pctSigned, usd } from "@/lib/format";
import { cn, downloadText, toCsv } from "@/lib/utils";
import { UploadPanel } from "./kitoblar-upload";

const TABS = [
  { key: "tekshiruv", label: "Tekshiruv", href: "/kitoblar" },
  { key: "budjet", label: "Budjet", href: "/kitoblar?tab=budjet" },
  { key: "hisobotlar", label: "Hisobotlar", href: "/kitoblar?tab=hisobotlar" },
];

const KIND: Record<Transaction["kind"], string> = { sale: "Savdo", purchase: "Xarid", expense: "Xarajat", deal: "Bitim" };

function FlagDetail({ flag, index, total, audit, onResolved }: { flag: AuditFlag; index: number; total: number; audit: Audit; onResolved: () => void }) {
  const resolve = useResolveFlag();
  const act = (action: "fix" | "ignore") => resolve.mutate({ id: flag.id, action }, { onSuccess: onResolved });
  const overInvoices = audit.invoices.filter((i) => i.over > 0);
  const overTotal = overInvoices.reduce((sum, i) => sum + i.over, 0);

  return (
    <div key={flag.id} className="fade-in">
      <p className="text-[13px] text-text-2">
        <span className="mono">
          {index + 1} / {total}
        </span>{" "}
        · {flag.crumb}
      </p>
      <h2 className="serif mt-2 text-[30px]">{flag.heading}</h2>
      <p className="mt-3 max-w-[600px] text-[15px] leading-[22px] text-text-2">{flag.explain}</p>

      <div className={cn("mt-4 grid gap-5", flag.invoice && "lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]")}>
        <div className="flex min-w-0 flex-col gap-3">
          <dl className="panel overflow-hidden">
            {flag.calc.map((row, i) => (
              <div key={row.label} className={cn("flex items-baseline justify-between gap-4 px-4 py-3 text-[14px]", i > 0 && "border-t border-[rgb(15_23_22/0.06)]", row.bad && "bg-danger-soft text-danger")}>
                <dt className={row.bad ? "" : "text-text-2"}>{row.label}</dt>
                <dd className="text-right font-medium tabular-nums">{row.value}</dd>
              </div>
            ))}
          </dl>
          <div className="rounded-[16px] bg-accent-soft p-4">
            <p className="text-[13px] font-medium text-accent-text">Kuzatuv</p>
            <p className="mt-1 text-[14px] leading-5">{flag.note}</p>
          </div>
        </div>
        {flag.invoice ? (
          <figure className="panel flex flex-col p-4">
            <div className="flex-1 rounded-[12px] bg-surface p-4 text-[12px] shadow-[var(--shadow-tile)]">
              <p className="text-[13px] font-semibold">{flag.invoice.title}</p>
              <p className="t-mono-cap mt-1">{flag.invoice.meta}</p>
              <dl className="mono mt-4 flex flex-col gap-2">
                {flag.invoice.lines.map((l) => (
                  <div key={l.label} className="flex justify-between gap-2">
                    <dt className="truncate text-text-2">{l.label}</dt>
                    <dd className="shrink-0">{l.value}</dd>
                  </div>
                ))}
              </dl>
              <p className="mono mt-4 flex justify-between rounded-[12px] border border-danger px-2 py-1 text-danger">
                <span className="font-medium text-text">Jami</span>
                {flag.invoice.total}
              </p>
            </div>
            <figcaption className="t-cap mt-2 text-center">Didox · asl hujjat</figcaption>
          </figure>
        ) : null}
      </div>

      {flag.chart ? (
        <div className="panel mt-5 grid gap-4 p-4 lg:grid-cols-[200px_minmax(0,1fr)]">
          <div className="self-center">
            <h3 className="text-[14px] font-semibold">TechOpt fakturalari</h3>
            <p className="serif mt-1 text-[28px]">
              {overInvoices.length} / {audit.invoices.length}
            </p>
            <p className="mt-1 text-[13px] text-text-2">faktura ortiqcha yozilgan, jami {mln(overTotal, 1)} so‘m. Ikkitasi allaqachon to‘langan.</p>
          </div>
          <div className="min-w-0">
            <ul className="mb-2 flex gap-4 text-[12px] text-text-2">
              <li className="flex items-center gap-2">
                <Swatch color="var(--danger)" />
                Ortiqcha summa
              </li>
              <li className="flex items-center gap-2">
                <Swatch color="var(--success)" />
                Summa to‘g‘ri
              </li>
            </ul>
            <InvoiceAnomalies invoices={audit.invoices} />
          </div>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button variant="primary" size="lg" disabled={resolve.isPending} onClick={() => act("fix")}>
          {flag.fix_label}
        </Button>
        <Button variant="plain" disabled={resolve.isPending} onClick={() => act("ignore")}>
          {flag.ignore_label}
        </Button>
        {resolve.isError ? (
          <p role="alert" className="text-[13px] text-danger">
            Saqlanmadi. Qayta urinib ko‘ring.
          </p>
        ) : null}
      </div>
    </div>
  );
}

function OkRecords({ count }: { count: number }) {
  const [open, setOpen] = useState(false);
  const tx = useTransactions();
  return (
    <details className="group mt-auto border-t border-[rgb(15_23_22/0.06)]" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex min-h-[56px] list-none items-center justify-between gap-3 px-5 text-[14px] text-text-2 [&::-webkit-details-marker]:hidden">
        {count} ta yozuv to‘g‘ri
        <ChevronDown size={18} strokeWidth={1.75} aria-hidden className="transition-transform duration-200 group-open:rotate-180" />
      </summary>
      {open ? (
        <ul className="max-h-[280px] overflow-auto px-5 pb-4">
          {(tx.data?.items ?? []).map((t) => (
            <li key={t.id} className="flex items-baseline justify-between gap-3 py-2 text-[13px]">
              <span className="min-w-0">
                <span className="block truncate">{t.title}</span>
                <span className="t-mono-cap">
                  {dateShort(t.date)} · {t.source}
                </span>
              </span>
              <span className="mono shrink-0 text-[12px]">{t.amount}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </details>
  );
}

function TekshiruvView() {
  useCopilotScreen("kitoblar");
  const query = useAudit();
  const sync = useDidoxSync();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<"issue" | "upload">("issue");
  const flags = query.data?.flags ?? [];
  const index = Math.max(0, flags.findIndex((f) => f.id === selectedId));
  const selected = flags[index];

  return (
    <div className="grid grid-cols-1 items-stretch gap-5 xl:grid-cols-[minmax(0,390fr)_minmax(0,848fr)]">
      <Tile className="flex min-h-[640px] flex-col overflow-hidden p-0 max-xl:min-h-0">
        <div className="p-5 pb-3">
          <h2 className="text-[17px] leading-6 font-semibold">{query.data ? (flags.length ? `${flags.length} ta yozuv tekshiruv kutmoqda` : "Tekshiruv yakunlandi") : "Tekshiruv"}</h2>
          {query.data ? <p className="mt-1 text-[13px] text-text-2">{query.data.total_records} ta yozuvdan · noyabr · Didox va BILLZ’dan</p> : null}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button disabled={sync.isPending} onClick={() => sync.mutate(undefined, { onSuccess: (r) => r.new_flags && setSelectedId("f-2231") })}>
              {sync.isPending ? "Sinxronlanmoqda" : "Didox’dan sinxronlash"}
            </Button>
            <Button variant="plain" onClick={() => setMode("upload")}>
              Fayl yuklash
            </Button>
          </div>
          {sync.data ? (
            <p role="status" className="mt-2 text-[13px] text-text-2">
              {sync.data.message}
            </p>
          ) : sync.isError ? (
            <p role="alert" className="mt-2 text-[13px] text-danger">
              Didox bilan aloqa bo‘lmadi.
            </p>
          ) : null}
        </div>
        <Async query={query} skeleton={<div className="px-5"><SkeletonLines rows={4} height={56} /></div>}>
          {(audit) => (
            <>
              <ul>
                {audit.flags.map((f, i) => (
                  <li key={f.id} className="border-t border-[rgb(15_23_22/0.06)]">
                    <button
                      type="button"
                      aria-current={i === index && mode === "issue" ? "true" : undefined}
                      onClick={() => {
                        setSelectedId(f.id);
                        setMode("issue");
                      }}
                      className={cn("flex min-h-[68px] w-full items-center justify-between gap-3 px-5 py-3 text-left transition-colors duration-150 hover:bg-[var(--nested)]", i === index && mode === "issue" && "bg-[rgb(15_23_22/0.06)]")}
                    >
                      <span className="min-w-0">
                        <span className="block text-[14px] font-semibold">{f.title}</span>
                        <span className="block truncate text-[13px] text-text-2">
                          {f.subtitle}
                          {f.is_new ? <span className="font-medium text-accent-text"> · Didox’dan yangi</span> : null}
                        </span>
                      </span>
                      <span className="shrink-0 text-[14px] font-medium tabular-nums">{f.amount}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <OkRecords count={audit.ok_records} />
            </>
          )}
        </Async>
      </Tile>

      <Tile>
        {mode === "upload" ? (
          <UploadPanel onClose={() => setMode("issue")} />
        ) : (
          <Async
            query={query}
            skeleton={
              <div className="flex flex-col gap-4" role="status" aria-label="Yuklanmoqda">
                <Skeleton className="h-10 w-2/3" />
                <Skeleton className="h-[220px]" />
                <Skeleton className="h-[180px]" />
              </div>
            }
            isEmpty={(a) => a.flags.length === 0}
            empty={
              <EmptyState
                text="Barcha yozuvlar tekshirildi. Kitoblaringiz toza."
                action={
                  <Link className="btn btn-plain -ml-2" href="/kitoblar?tab=hisobotlar">
                    Hisobotlarni ochish
                  </Link>
                }
              />
            }
          >
            {(audit) => selected ? <FlagDetail flag={selected} index={index} total={audit.flags.length} audit={audit} onResolved={() => setSelectedId(audit.flags[index + 1]?.id ?? null)} /> : null}
          </Async>
        )}
      </Tile>
    </div>
  );
}

function BudgetContent({ b }: { b: Budget }) {
  const [ads, setAds] = useState(0);
  const [purchases, setPurchases] = useState(0);
  const daily = b.burn.ads * (1 + ads / 100) + b.burn.purchases * (1 + purchases / 100) + b.burn.other;
  const forecast = b.spent + daily * (b.days_in_month - b.day);
  const limitDay = b.day + Math.floor((b.limit - b.spent) / daily);
  const breach = limitDay <= b.days_in_month;
  const over = forecast - b.limit;
  const maxBar = Math.max(...b.categories.flatMap((c) => [c.plan, c.fact]));

  return (
    <>
      <KpiStrip
        items={[
          { label: "Sarflandi", value: mln(b.spent), note: `${b.day}-noyabr holatiga` },
          { label: "Oylik limit", value: mln(b.limit), note: `${mln(b.limit - b.spent)} qoldi` },
          { label: "Oy oxiri prognozi", value: mln(forecast, 0), note: breach ? `limitdan ${mln(over, 0)} ortiq` : `limitdan ${mln(-over, 0)} kam`, noteClass: breach ? "text-warning" : "text-success" },
          { label: "Limit tugashi", value: breach ? `${limitDay}-noyabr` : "tugamaydi", note: `kuniga ${mln(daily, 1)} so‘m`, noteClass: breach ? "text-warning" : undefined },
        ]}
      />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Tile className="xl:col-span-2">
          <TileHeader title="Oy oxiri prognozi" sub="Mln so‘m, jamlangan xarajat. Punktir: joriy sur’at bo‘yicha." />
          <div className="mt-3">
            <BudgetLine spent={b.spent} limit={b.limit} day={b.day} daysInMonth={b.days_in_month} daily={daily} />
          </div>
          {breach ? (
            <p role="status" className="mt-3 text-[14px] font-medium text-warning">
              Ogohlantirish: shu sur’atda limit {limitDay}-noyabrda tugaydi.
            </p>
          ) : (
            <p role="status" className="mt-3 text-[14px] font-medium text-success">
              Shu sozlamalarda oy limit ichida yakunlanadi.
            </p>
          )}
        </Tile>
        <Tile>
          <TileHeader title="Agar shunday qilsam" sub="Sur’atni o‘zgartiring, sana qayta hisoblanadi." />
          {[
            { label: "Reklama", value: ads, set: setAds },
            { label: "Xaridlar", value: purchases, set: setPurchases },
          ].map((s) => (
            <div key={s.label} className="mt-4">
              <div className="flex items-baseline justify-between text-[13px]">
                <span className="text-text-2">{s.label}</span>
                <span className="mono font-medium">{pctSigned(s.value, 0)}</span>
              </div>
              <Slider aria-label={`${s.label} o‘zgarishi`} min={-50} max={50} step={5} value={[s.value]} onValueChange={([v]) => s.set(v)} />
            </div>
          ))}
          {ads || purchases ? (
            <Button
              variant="plain"
              className="-ml-2"
              onClick={() => {
                setAds(0);
                setPurchases(0);
              }}
            >
              Asl holatga qaytarish
            </Button>
          ) : null}
        </Tile>
      </div>
      <Tile>
        <TileHeader title="Reja va amal" sub="Toifalar bo‘yicha, mln so‘m" />
        <ul className="mt-4 flex flex-col gap-3">
          {b.categories.map((c) => (
            <li key={c.name} className="grid grid-cols-[100px_minmax(0,1fr)_96px] items-center gap-3 text-[13px]">
              <span>{c.name}</span>
              <div className="relative h-3 rounded-full bg-[rgb(15_23_22/0.06)]" role="img" aria-label={`${c.name}: reja ${c.plan}, amal ${c.fact} mln`}>
                <div className="absolute inset-y-0 left-0 rounded-full bg-[var(--chart-s1)]" style={{ width: `${(c.fact / maxBar) * 100}%` }} />
                <div className="absolute -inset-y-1 w-0.5 rounded-full bg-text" style={{ left: `${(c.plan / maxBar) * 100}%` }} />
              </div>
              <span className="mono text-right text-[12px] text-text-2">
                {c.fact} / {c.plan}
              </span>
            </li>
          ))}
        </ul>
      </Tile>
    </>
  );
}

function BudjetView() {
  useCopilotScreen("budjet");
  const query = useBudget();
  return (
    <Async query={query} skeleton={<Skeleton className="h-[320px] rounded-[36px]" />}>
      {(b) => <BudgetContent b={b} />}
    </Async>
  );
}

function HisobotView() {
  useCopilotScreen("hisobotlar");
  const tx = useTransactions();
  const rfq = useRfq();
  const deal = rfq.data?.deal;
  const rows = useMemo(() => tx.data?.items ?? [], [tx.data]);
  return (
    <>
      <KpiStrip
        items={[
          { label: "Noyabr tushumi", value: "245 mln", note: "so‘m, aylanma" },
          { label: "Xarajat", value: "201 mln", note: "so‘m" },
          { label: "Sof foyda", value: "44 mln", note: "so‘m", noteClass: "text-success" },
          { label: "Soliq taxmini", value: "9,8 mln", note: "aylanmadan 4%" },
        ]}
      />
      {deal ? (
        <Tile className="fade-in">
          <TileHeader title={`${deal.label} · ${deal.id}`} sub={`${deal.buyer} va ${deal.supplier}`} right={dateShort(deal.date)} />
          <dl className="panel mt-3 grid grid-cols-2 gap-4 p-4 text-[14px] md:grid-cols-4">
            {[
              ["Mahsulot", deal.item],
              ["Miqdor", `${deal.qty} dona`],
              ["Narx", usd(deal.unit_price)],
              ["Jami", usd(deal.total)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-[13px] text-text-2">{k}</dt>
                <dd className="font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </Tile>
      ) : null}
      <Tile>
        <TileHeader
          title="Yozuvlar"
          sub={tx.data ? `Jami ${tx.data.total} ta, so‘nggilari ko‘rsatilgan` : undefined}
          right={
            <Button
              className="-mt-2 font-sans"
              onClick={() =>
                downloadText(
                  "raft-yozuvlar.csv",
                  toCsv([["Sana", "Yozuv", "Hamkor", "Turi", "Manba", "Summa"], ...rows.map((t) => [t.date, t.title, t.counterparty, KIND[t.kind], t.source, t.amount])]),
                )
              }
            >
              CSV yuklash
            </Button>
          }
        />
        <div className="mt-3 overflow-x-auto">
          <Async query={tx} skeleton={<SkeletonLines rows={6} />}>
            {() => (
              <table className="data-table min-w-[720px]">
                <thead>
                  <tr>
                    <th>Sana</th>
                    <th>Yozuv</th>
                    <th>Hamkor</th>
                    <th>Turi</th>
                    <th>Manba</th>
                    <th className="r">Summa</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.id}>
                      <td className="mono text-text-2">{dateShort(t.date)}</td>
                      <td className="font-medium">{t.title}</td>
                      <td className="text-text-2">{t.counterparty}</td>
                      <td className={t.kind === "deal" ? "text-accent-text" : "text-text-2"}>{KIND[t.kind]}</td>
                      <td className="text-text-2">{t.source}</td>
                      <td className="r mono font-medium">{t.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Async>
        </div>
      </Tile>
    </>
  );
}

export function KitoblarScreen({ tab }: { tab: string }) {
  const nav = useT().nav;
  return (
    <Page title={nav.kitoblar} tabs={TABS} active={tab}>
      {tab === "budjet" ? <BudjetView /> : tab === "hisobotlar" ? <HisobotView /> : <TekshiruvView />}
    </Page>
  );
}
