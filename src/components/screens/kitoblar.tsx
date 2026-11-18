"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { BudgetLine } from "@/components/charts/budget-line";
import { InvoiceAnomalies } from "@/components/charts/invoice-anomalies";
import { Page, useCopilotScreen } from "@/components/raft/shell";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { KpiStrip, Swatch, Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { useT } from "@/i18n";
import type { AuditFlagView, AuditView, BudgetView, TxKind } from "@/lib/api/backend/books";
import { exportTransactions, useAudit, useBooksSummary, useBudget, useDidoxSync, useResolveFlag, useRfq, useTransactions } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/client";
import { dateLong, dateShort, mln, num, pctSigned, shortSoum, soum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { UploadPanel } from "./kitoblar-upload";

const TABS = [
  { key: "tekshiruv", label: "Tekshiruv", href: "/kitoblar" },
  { key: "budjet", label: "Budjet", href: "/kitoblar?tab=budjet" },
  { key: "hisobotlar", label: "Hisobotlar", href: "/kitoblar?tab=hisobotlar" },
];

const KIND: Record<TxKind, string> = { sale: "Savdo", purchase: "Xarid", expense: "Xarajat", deal: "Bitim" };
const FIX_LABEL = { delete_duplicates: "Ortiqchalarini o‘chirish", correct_total: "Summani tuzatish" } as const;

/** "2026-11" → "noyabr" / "noy". */
const monthName = (month: string) => dateLong(`${month}-01`).split("-")[1];
const monthShortName = (month: string) => dateShort(`${month}-01`).split("-")[1];

function FlagDetail({ flag, index, total, onResolved }: { flag: AuditFlagView; index: number; total: number; onResolved: () => void }) {
  const resolve = useResolveFlag();
  const act = (action: "fix" | "ignore") => resolve.mutate({ id: flag.id, action }, { onSuccess: onResolved });
  const atRisk = flag.history.filter((h) => h.over > 0);
  const atRiskTotal = atRisk.reduce((sum, h) => sum + h.over, 0);
  const shown = flag.transactions.slice(0, 5);
  const docTotal = flag.transactions.reduce((sum, t) => sum + t.total, 0);
  const first = flag.transactions[0];

  return (
    <div key={flag.id} className="fade-in">
      <p className="text-[13px] text-text-2">
        <span className="mono">
          {index + 1} / {total}
        </span>{" "}
        · {flag.title}
      </p>
      <h2 className="serif mt-2 text-[30px]">{flag.heading}</h2>

      <div className={cn("mt-4 grid gap-5", first && "lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]")}>
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
            <p className="mt-1 text-[14px] leading-5">{flag.fixNote}</p>
          </div>
        </div>
        {first ? (
          <figure className="panel flex flex-col p-4">
            <div className="flex-1 rounded-[12px] bg-surface p-4 text-[12px] shadow-[var(--shadow-tile)]">
              <p className="text-[13px] font-semibold">{flag.counterparty ?? "Kontragent ko‘rsatilmagan"}</p>
              <p className="t-mono-cap mt-1">
                {flag.transactions.length > 1 ? `${flag.transactions.length} ta yozuv` : `#${first.id} · ${dateShort(first.date)}`}
              </p>
              <dl className="mono mt-4 flex flex-col gap-2">
                {shown.map((t) => (
                  <div key={t.id} className="flex justify-between gap-2">
                    <dt className="truncate text-text-2">
                      #{t.id} · {dateShort(t.date)} · {t.title}
                    </dt>
                    <dd className="shrink-0">{soum(t.total)}</dd>
                  </div>
                ))}
                {flag.transactions.length > shown.length ? <p className="text-text-2">va yana {flag.transactions.length - shown.length} ta</p> : null}
              </dl>
              <p className="mono mt-4 flex justify-between rounded-[12px] border border-danger px-2 py-1 text-danger">
                <span className="font-medium text-text">Jami</span>
                {soum(docTotal)}
              </p>
            </div>
            <figcaption className="t-cap mt-2 text-center">Kitobdagi yozuv · {flag.sourceLabel}</figcaption>
          </figure>
        ) : null}
      </div>

      {flag.history.length >= 2 && atRisk.length ? (
        <div className="panel mt-5 grid gap-4 p-4 lg:grid-cols-[200px_minmax(0,1fr)]">
          <div className="self-center">
            <h3 className="text-[14px] font-semibold">{flag.counterparty} yozuvlari</h3>
            <p className="serif mt-1 text-[28px]">
              {atRisk.length} / {flag.history.length}
            </p>
            <p className="mt-1 text-[13px] text-text-2">so‘nggi yozuvda muammo topilgan, jami {mln(atRiskTotal, 1)} so‘m.</p>
          </div>
          <div className="min-w-0">
            <ul className="mb-2 flex gap-4 text-[12px] text-text-2">
              <li className="flex items-center gap-2">
                <Swatch color="var(--danger)" />
                Xavf ostidagi summa
              </li>
              <li className="flex items-center gap-2">
                <Swatch color="var(--success)" />
                Muammo yo‘q
              </li>
            </ul>
            <InvoiceAnomalies invoices={flag.history} />
          </div>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {flag.fix ? (
          <Button variant="primary" size="lg" disabled={resolve.isPending} onClick={() => act("fix")}>
            {FIX_LABEL[flag.fix]}
          </Button>
        ) : null}
        <Button variant={flag.fix ? "plain" : "primary"} size={flag.fix ? undefined : "lg"} disabled={resolve.isPending} onClick={() => act("ignore")}>
          Tekshirildi, to‘g‘ri
        </Button>
        {resolve.isError ? (
          <p role="alert" className="text-[13px] text-danger">
            {resolve.error instanceof ApiError && resolve.error.status === 409 ? resolve.error.message : "Saqlanmadi. Qayta urinib ko‘ring."}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function OkRecords({ audit }: { audit: AuditView }) {
  const [open, setOpen] = useState(false);
  const tx = useTransactions();
  const flagged = new Set(audit.flags.flatMap((f) => f.transactionIds));
  return (
    <details className="group mt-auto border-t border-[rgb(15_23_22/0.06)]" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex min-h-[56px] list-none items-center justify-between gap-3 px-5 text-[14px] text-text-2 [&::-webkit-details-marker]:hidden">
        {audit.okRecords} ta yozuv to‘g‘ri
        <ChevronDown size={18} strokeWidth={1.75} aria-hidden className="transition-transform duration-200 group-open:rotate-180" />
      </summary>
      {open ? (
        <ul className="max-h-[280px] overflow-auto px-5 pb-4">
          {(tx.data?.items ?? [])
            .filter((t) => !flagged.has(t.id))
            .map((t) => (
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
  const newTx = new Set(sync.data?.transactionIds ?? []);
  const isNew = (f: AuditFlagView) => f.transactionIds.some((id) => newTx.has(id));
  // Nothing picked yet: show the first flag from the last Didox sync, else the first flag.
  const index = Math.max(0, flags.findIndex((f) => (selectedId ? f.id === selectedId : isNew(f))));
  const selected = flags[index];

  return (
    <div className="grid grid-cols-1 items-stretch gap-5 xl:grid-cols-[minmax(0,390fr)_minmax(0,848fr)]">
      <Tile className="flex min-h-[640px] flex-col overflow-hidden p-0 max-xl:min-h-0">
        <div className="p-5 pb-3">
          <h2 className="text-[17px] leading-6 font-semibold">{query.data ? (flags.length ? `${flags.length} ta yozuv tekshiruv kutmoqda` : "Tekshiruv yakunlandi") : "Tekshiruv"}</h2>
          {query.data ? (
            <p className="mt-1 text-[13px] text-text-2">
              {query.data.totalRecords} ta yozuvdan{query.data.atRisk > 0 ? ` · ${shortSoum(query.data.atRisk)} xavf ostida` : ""}
              {query.data.checked ? ` · ${query.data.checked} tasi tekshirilgan` : ""}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              disabled={sync.isPending}
              onClick={() =>
                sync.mutate(undefined, {
                  onSuccess: () => {
                    setSelectedId(null);
                    setMode("issue");
                  },
                })
              }
            >
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
                          {isNew(f) ? <span className="font-medium text-accent-text"> · Didox’dan yangi</span> : null}
                        </span>
                      </span>
                      <span className="shrink-0 text-[14px] font-medium tabular-nums">{f.amount}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <OkRecords audit={audit} />
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
            {(audit) => (selected ? <FlagDetail flag={selected} index={index} total={audit.flags.length} onResolved={() => setSelectedId(audit.flags[index + 1]?.id ?? null)} /> : null)}
          </Async>
        )}
      </Tile>
    </div>
  );
}

/** Categories the "what if" sliders act on (backend category keys). */
const SLIDERS = [
  { key: "ads", label: "Reklama" },
  { key: "stock_purchase", label: "Xaridlar" },
] as const;

function BudgetContent({ b }: { b: BudgetView }) {
  const [adj, setAdj] = useState<Record<string, number>>({});
  const daysLeft = b.daysInMonth - b.day;
  // Backend forecast per category; the sliders only rescale the part still to be spent.
  const forecast = b.categories.reduce((sum, c) => sum + c.fact + (c.forecast - c.fact) * (1 + (adj[c.key] ?? 0) / 100), 0);
  const daily = daysLeft > 0 ? (forecast - b.spent) / daysLeft : 0;
  const hasLimit = b.limit > 0;
  const pastBreach = b.cumulative.findIndex((v) => v > b.limit);
  const limitDay = !hasLimit ? null : pastBreach >= 0 ? pastBreach + 1 : daily > 0 ? b.day + Math.floor((b.limit - b.spent) / daily) + 1 : null;
  const breach = limitDay !== null && limitDay <= b.daysInMonth;
  const over = forecast - b.limit;
  const maxBar = Math.max(1e-9, ...b.categories.flatMap((c) => [c.plan, c.fact]));
  const mName = monthName(b.month);
  const dayLabel = (d: number) => `${d}-${mName}`;
  const sliders = SLIDERS.filter((s) => b.categories.some((c) => c.key === s.key));

  return (
    <>
      <KpiStrip
        items={[
          { label: "Sarflandi", value: mln(b.spent), note: b.day ? `${dayLabel(b.day)} holatiga` : undefined },
          { label: "Oylik limit", value: hasLimit ? mln(b.limit) : "belgilanmagan", note: hasLimit ? (b.limit >= b.spent ? `${mln(b.limit - b.spent)} qoldi` : `${mln(b.spent - b.limit)} oshib ketdi`) : undefined, noteClass: hasLimit && b.spent > b.limit ? "text-warning" : undefined },
          { label: "Oy oxiri prognozi", value: mln(forecast, 0), note: hasLimit ? (over > 0 ? `limitdan ${mln(over, 0)} ortiq` : `limitdan ${mln(-over, 0)} kam`) : undefined, noteClass: hasLimit ? (over > 0 ? "text-warning" : "text-success") : undefined },
          { label: "Limit tugashi", value: !hasLimit ? "—" : breach && limitDay ? dayLabel(limitDay) : "tugamaydi", note: daysLeft > 0 ? `kuniga ${mln(daily, 1)} so‘m` : undefined, noteClass: breach ? "text-warning" : undefined },
        ]}
      />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Tile className={sliders.length ? "xl:col-span-2" : "xl:col-span-3"}>
          <TileHeader title="Oy oxiri prognozi" sub="Mln so‘m, jamlangan xarajat. Punktir: joriy sur’at bo‘yicha." />
          <div className="mt-3">
            <BudgetLine cumulative={b.cumulative} limit={b.limit} daysInMonth={b.daysInMonth} daily={daily} monthShort={monthShortName(b.month)} />
          </div>
          {!hasLimit ? null : breach && limitDay ? (
            <p role="status" className="mt-3 text-[14px] font-medium text-warning">
              {limitDay <= b.day ? `Ogohlantirish: limit ${dayLabel(limitDay)}da tugagan.` : `Ogohlantirish: shu sur’atda limit ${dayLabel(limitDay)}da tugaydi.`}
            </p>
          ) : (
            <p role="status" className="mt-3 text-[14px] font-medium text-success">
              Shu sozlamalarda oy limit ichida yakunlanadi.
            </p>
          )}
        </Tile>
        {sliders.length ? (
          <Tile>
            <TileHeader title="Agar shunday qilsam" sub="Qolgan kunlardagi sur’atni o‘zgartiring, prognoz qayta hisoblanadi." />
            {sliders.map((s) => (
              <div key={s.key} className="mt-4">
                <div className="flex items-baseline justify-between text-[13px]">
                  <span className="text-text-2">{s.label}</span>
                  <span className="mono font-medium">{pctSigned(adj[s.key] ?? 0, 0)}</span>
                </div>
                <Slider aria-label={`${s.label} o‘zgarishi`} min={-50} max={50} step={5} value={[adj[s.key] ?? 0]} onValueChange={([v]) => setAdj((a) => ({ ...a, [s.key]: v }))} />
              </div>
            ))}
            {Object.values(adj).some(Boolean) ? (
              <Button variant="plain" className="-ml-2" onClick={() => setAdj({})}>
                Asl holatga qaytarish
              </Button>
            ) : null}
          </Tile>
        ) : null}
      </div>
      <Tile>
        <TileHeader title="Reja va amal" sub="Toifalar bo‘yicha, mln so‘m" />
        <ul className="mt-4 flex flex-col gap-3">
          {b.categories.map((c) => (
            <li key={c.key} className="grid grid-cols-[100px_minmax(0,1fr)_96px] items-center gap-3 text-[13px]">
              <span>{c.name}</span>
              <div className="relative h-3 rounded-full bg-[rgb(15_23_22/0.06)]" role="img" aria-label={`${c.name}: reja ${num(c.plan, 1)}, amal ${num(c.fact, 1)} mln`}>
                <div className="absolute inset-y-0 left-0 rounded-full bg-[var(--chart-s1)]" style={{ width: `${(c.fact / maxBar) * 100}%` }} />
                {c.plan > 0 ? <div className="absolute -inset-y-1 w-0.5 rounded-full bg-text" style={{ left: `${(c.plan / maxBar) * 100}%` }} /> : null}
              </div>
              <span className="mono text-right text-[12px] text-text-2">
                {num(c.fact, 1)} / {c.plan > 0 ? num(c.plan, 1) : "—"}
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
  const summary = useBooksSummary();
  const rfq = useRfq();
  const deal = rfq.data?.deal;
  const rows = tx.data?.items ?? [];
  const [exporting, setExporting] = useState(false);
  const s = summary.data;
  return (
    <>
      {s ? (
        <KpiStrip
          items={[
            { label: `${monthName(s.month)[0].toUpperCase()}${monthName(s.month).slice(1)} tushumi`, value: shortSoum(s.income_uzs), note: "aylanma" },
            { label: "Xarajat", value: shortSoum(s.expense_uzs), note: `${s.transactions} ta yozuv` },
            { label: "Sof foyda", value: shortSoum(s.net_uzs), note: s.net_uzs >= 0 ? "tushum − xarajat" : "zarar", noteClass: s.net_uzs >= 0 ? "text-success" : "text-danger" },
            { label: "Soliq taxmini", value: shortSoum(s.tax_estimate_uzs), note: s.tax_rate_pct !== null ? `aylanmadan ${num(s.tax_rate_pct, 0)}%` : "QQS + foyda solig‘i" },
          ]}
        />
      ) : summary.isError ? (
        <p role="alert" className="text-[13px] text-danger">
          Oylik hisobot yuklanmadi.
        </p>
      ) : (
        <Skeleton className="h-[96px] rounded-[24px]" />
      )}
      {deal ? (
        <Tile className="fade-in">
          <TileHeader title={`${deal.label} · ${deal.id}`} sub={`${deal.buyer} va ${deal.supplier}`} right={dateShort(deal.date)} />
          <dl className="panel mt-3 grid grid-cols-2 gap-4 p-4 text-[14px] md:grid-cols-4">
            {[
              ["Mahsulot", deal.item],
              ["Miqdor", `${deal.qty} dona`],
              ["Narx", soum(deal.unit_price)],
              ["Jami", soum(deal.total)],
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
              disabled={exporting}
              onClick={() => {
                setExporting(true);
                void exportTransactions("csv").finally(() => setExporting(false));
              }}
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
