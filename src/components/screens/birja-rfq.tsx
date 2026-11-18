"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { QuoteSpread } from "@/components/charts/quote-spread";
import { useCopilotScreen } from "@/components/raft/shell";
import { EmptyState, ErrorState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import type { Lot, RfqQuote } from "@/lib/api/backend/exchange";
import { ApiError } from "@/lib/api/client";
import { type RfqDetail, useAcceptQuote, useBuyOffer, useCounterQuote, useRfq, useRfqs } from "@/lib/api/hooks";
import { dateShort, pct, pctSigned, shortSoum, soum } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS: Record<string, string> = { open: "ochiq", awarded: "bitim tuzildi", closed: "yopilgan" };

function ratingWord(diff: number | null) {
  if (diff === null) return { word: "Bozor bahosi yo‘q", tone: "text-text-2" };
  if (diff > 1) return { word: "Qimmat", tone: "text-warning" };
  if (diff < -1) return { word: "Arzon", tone: "text-success" };
  return { word: "Adolatli", tone: "text-text" };
}

const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : e ? fallback : null);

function RfqList({ selectedId, onSelect }: { selectedId: number | null; onSelect: (id: number) => void }) {
  const list = useRfqs();
  const items = list.data?.items ?? [];
  return (
    <Tile className="p-0">
      <div className="p-5 pb-2">
        <TileHeader title="So‘rovlarim" right={list.data ? `${list.data.total} ta` : undefined} />
      </div>
      {list.isPending ? (
        <div className="px-5 pb-5">
          <SkeletonLines rows={3} height={44} />
        </div>
      ) : list.isError ? (
        <ErrorState onRetry={() => void list.refetch()} />
      ) : (
        <ul className="max-h-[260px] overflow-y-auto pb-2">
          {items.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                aria-current={r.id === selectedId ? "true" : undefined}
                onClick={() => onSelect(r.id)}
                className={cn("grid w-full grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-x-2 px-5 py-2 text-left transition-colors duration-150 hover:bg-[var(--nested)]", r.id === selectedId && "bg-[rgb(15_23_22/0.06)]")}
              >
                <span className="t-mono-cap">#{r.id}</span>
                <span className="min-w-0">
                  <span className="block truncate text-[14px] font-medium">{r.title}</span>
                  <span className="block truncate text-[12px] text-text-2">
                    {r.qty} dona · {r.quotes_count} ta taklif
                  </span>
                </span>
                <span className={cn("text-[12px]", r.status === "open" ? "font-medium text-accent-text" : "text-text-2")}>{STATUS[r.status] ?? r.status}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Tile>
  );
}

function RequestCard({ rfq }: { rfq: RfqDetail }) {
  const steps = [
    { title: "Yuborildi", meta: dateShort(rfq.created_at) },
    { title: `${rfq.quotes.length} ta taklif keldi`, meta: rfq.quotes.length ? STATUS[rfq.status] ?? rfq.status : "kutilmoqda" },
    { title: "Taklifni tanlang", meta: rfq.deal ? rfq.deal.supplier : rfq.status === "open" ? "hozir" : STATUS[rfq.status] ?? rfq.status },
    { title: rfq.deal ? "Bitim kitoblarga yozildi" : "Bitim kitoblarga yoziladi", meta: rfq.deal ? dateShort(rfq.deal.date) : "avtomatik" },
  ];
  const current = rfq.deal ? 4 : rfq.quotes.length ? 2 : 1;
  const fair = rfq.market?.fair_price ?? rfq.fair_price;
  return (
    <Tile className="flex flex-col">
      <p className="text-[13px] text-text-2">
        So‘rov #{rfq.id}
        {rfq.deadline ? ` · muddat ${dateShort(rfq.deadline)}` : ""}
      </p>
      <h2 className="serif mt-3 text-[26px]">{rfq.title}</h2>
      <dl className="mt-4 flex flex-col gap-2">
        {rfq.specs.map((s) => (
          <div key={s.label} className="kv">
            <dt>{s.label}</dt>
            <dd>{s.value}</dd>
          </div>
        ))}
        {rfq.target_unit_price ? (
          <div className="kv">
            <dt>Maqsad narx</dt>
            <dd>{soum(rfq.target_unit_price)}</dd>
          </div>
        ) : null}
      </dl>
      <hr className="my-5 border-[rgb(15_23_22/0.08)]" />
      <p className="text-[13px] text-text-2">Bozor bahosi</p>
      {fair ? (
        <>
          <p className="mt-1 flex flex-wrap items-baseline gap-2">
            <span className="serif text-[32px]">{shortSoum(fair * rfq.qty)}</span>
            <span className="text-[14px] text-text-2">
              = {shortSoum(fair)} × {rfq.qty}
            </span>
          </p>
          <p className="mt-1 text-[13px] text-text-2">{rfq.market ? `${rfq.market.comparables} ta e’lon medianasi · ${rfq.market.basis}` : "e’lonlar medianasi"}</p>
          {rfq.fair_buy_price ? <p className="mt-1 text-[13px] text-text-2">Ulgurji xarid narxi: {soum(rfq.fair_buy_price)} / dona</p> : null}
        </>
      ) : (
        <p className="mt-1 text-[13px] text-text-2">Bu mahsulot uchun bozorda o‘xshash e’lonlar yetarli emas.</p>
      )}
      <hr className="my-5 border-[rgb(15_23_22/0.08)]" />
      <h3 className="text-[13px] text-text-2">Holat</h3>
      <ol className="mt-3 flex flex-col gap-4">
        {steps.map((s, i) => {
          const state = i < current ? "done" : i === current ? "now" : "next";
          return (
            <li key={s.title} className="grid grid-cols-[20px_minmax(0,1fr)] gap-x-2" aria-current={state === "now" ? "step" : undefined}>
              <span className={cn("mono text-[13px]", state === "now" ? "font-medium text-accent-text" : "text-muted")}>{i + 1}</span>
              <span className={cn("text-[14px]", state === "next" ? "text-text-2" : "font-medium", state === "now" && "text-accent-text")}>{s.title}</span>
              <span className="t-mono-cap col-start-2">{s.meta}</span>
            </li>
          );
        })}
      </ol>
    </Tile>
  );
}

function QuoteTile({ rfq, quote }: { rfq: RfqDetail; quote: RfqQuote }) {
  const accept = useAcceptQuote();
  const counter = useCounterQuote();
  const [countering, setCountering] = useState(false);
  const suggested = rfq.fair_buy_price && rfq.fair_buy_price < quote.price ? Math.round(rfq.fair_buy_price / 1000) * 1000 : quote.price;
  const [price, setPrice] = useState(String(suggested));
  const units = Math.min(quote.qty, rfq.qty);
  const fair = rfq.market?.fair_price ?? rfq.fair_price;
  const saving = fair ? (fair - quote.price) * units : null;
  const rating = ratingWord(quote.diff_pct);
  const acceptError = errorText(accept.error, "Bajarilmadi. Qayta urinib ko‘ring.");
  const counterError = errorText(counter.error, "Yuborilmadi. Qayta urinib ko‘ring.");
  const valid = Number(price) > 0;
  const open = rfq.status === "open";
  const canAccept = open && quote.status === "pending";
  const canCounter = canAccept && quote.counter_unit_price === null;

  return (
    <section className="tile outline-[1.5px] -outline-offset-1 outline-accent outline-solid">
      <h2 className="text-[20px] leading-7 font-semibold">{quote.supplier}</h2>
      <p className="text-[13px] text-text-2">
        {quote.verification} · ball {quote.score}
      </p>
      <p className="mt-3 flex flex-wrap items-baseline gap-2">
        <span className="serif text-[48px]">{shortSoum(quote.price)}</span>
        <span className="text-[15px] text-text-2">/ dona</span>
      </p>
      <p className="mt-2 text-[14px] text-text-2">
        {rating.word} {quote.diff_pct !== null ? <span className={cn("mono font-medium", rating.tone)}>{pctSigned(quote.diff_pct, 0)}</span> : null}
        <span className="ml-2">
          Jami {soum(quote.price * units)}
          {saving !== null ? ` · ${saving >= 0 ? `bozor bahosidan ${shortSoum(saving)} kam` : `bozor bahosidan ${shortSoum(-saving)} ko‘p`}` : ""}
          {quote.qty < rfq.qty ? ` · faqat ${quote.qty} dona` : ""} · yetkazish {quote.delivery}
        </span>
      </p>
      <div className="panel mt-4 p-4">
        <h3 className="text-[14px] font-semibold">Nega aynan shu taklif</h3>
        <ul className="mt-2 flex flex-col gap-2 text-[14px]">
          {quote.why.map((w) => (
            <li key={w}>{w}</li>
          ))}
          {quote.note ? <li className="text-text-2">Izoh: {quote.note}</li> : null}
        </ul>
      </div>

      {quote.recommended && rfq.recommendation ? (
        <p role="status" className="mt-3 text-[13px] text-text-2">
          {rfq.recommendation.text}
        </p>
      ) : null}

      {quote.status === "countered" && quote.counter_unit_price !== null ? (
        <p role="status" className="mt-3 text-[14px] font-medium">
          Siz {soum(quote.counter_unit_price)} taklif qildingiz. Yetkazib beruvchi javobini kutmoqda.
        </p>
      ) : null}

      {rfq.deal ? (
        <div role="status" className="mt-4 flex flex-wrap items-center gap-3 text-[14px]">
          <span className="font-medium">
            {rfq.deal.label} {rfq.deal.id}: {rfq.deal.supplier}, {soum(rfq.deal.total)}
          </span>
          <Link href="/kitoblar?tab=hisobotlar" className="link">
            Kitoblarda ko‘rish
          </Link>
        </div>
      ) : canAccept ? (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button variant="primary" size="lg" disabled={accept.isPending} onClick={() => accept.mutate(quote.id)}>
              Taklifni qabul qilish · {shortSoum(quote.price * units)}
            </Button>
            {canCounter ? (
              <Button variant="plain" aria-expanded={countering} onClick={() => setCountering((v) => !v)}>
                Narxni kelishish
              </Button>
            ) : null}
            {acceptError ? (
              <p role="alert" className="text-[13px] text-danger">
                {acceptError}
              </p>
            ) : null}
          </div>
          {countering ? (
            <form
              className="fade-in mt-3 flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (valid) counter.mutate({ id: quote.id, price: Number(price) }, { onSuccess: () => setCountering(false) });
              }}
            >
              <div className="w-[200px]">
                <label className="field-label" htmlFor="counter-price">
                  Sizning narxingiz, so‘m
                </label>
                <input id="counter-price" className="input mono" inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} />
              </div>
              <Button type="submit" disabled={!valid || counter.isPending}>
                Taklif yuborish
              </Button>
              {!valid ? <p className="pb-3 text-[13px] text-text-2">Narxni kiriting.</p> : null}
              {counterError ? (
                <p role="alert" className="pb-3 text-[13px] text-danger">
                  {counterError}
                </p>
              ) : null}
              <p className="w-full text-[12px] text-text-2">Narxni bir marta kelishish mumkin.</p>
            </form>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function MatchesTile({ rfq }: { rfq: RfqDetail }) {
  const buy = useBuyOffer();
  if (!rfq.matches.length) return null;
  const error = errorText(buy.error, "Bajarilmadi. Qayta urinib ko‘ring.");
  return (
    <Tile className="p-0">
      <div className="p-5 pb-3">
        <TileHeader title="Birjada mos e’lonlar" sub="So‘rovingizga mos ulgurji va ortiqcha tovarlar" right={`${rfq.matches.length} ta`} />
      </div>
      <ul>
        {rfq.matches.map((m: Lot) => {
          const qty = Math.min(rfq.qty, m.qty);
          return (
            <li key={m.id} className="flex min-h-[68px] flex-wrap items-center gap-4 border-t border-[rgb(15_23_22/0.06)] px-5 py-3">
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-semibold">
                  {m.title} · {m.seller}
                </span>
                <span className="block truncate text-[13px] text-text-2">{[m.kind_label, m.location, `${m.qty} dona`, ...m.reasons].filter(Boolean).join(" · ")}</span>
              </span>
              {m.diff_pct !== null ? <span className={cn("mono shrink-0 text-[13px]", m.diff_pct < 0 ? "text-success" : "text-text-2")}>{pctSigned(m.diff_pct, 0)}</span> : null}
              <span className="shrink-0 text-right text-[15px] font-semibold">{shortSoum(m.unit_price)}</span>
              {m.buyable ? (
                <Button variant="plain" disabled={buy.isPending} onClick={() => buy.mutate({ id: m.id, qty })}>
                  {qty} dona olish
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
      {error ? (
        <p role="alert" className="px-5 pb-4 text-[13px] text-danger">
          {error}
        </p>
      ) : null}
    </Tile>
  );
}

function RfqBody({ rfq }: { rfq: RfqDetail }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  if (!rfq.quotes.length) {
    return (
      <div className="flex min-w-0 flex-col gap-5">
        <Tile>
          <EmptyState text="Bu so‘rovga hali taklif kelmagan. Taklif kelganda shu yerda paydo bo‘ladi." />
        </Tile>
        <MatchesTile rfq={rfq} />
      </div>
    );
  }
  const recommended = rfq.quotes.find((q) => q.recommended) ?? rfq.quotes[0];
  const selected = rfq.quotes.find((q) => q.id === selectedId) ?? recommended;
  const others = rfq.quotes.filter((q) => q.id !== selected.id);
  const fair = rfq.market?.fair_price ?? rfq.fair_price;
  const gap = fair !== null ? fair - recommended.price : null;
  const dots = rfq.market?.dots ?? [];
  const cheaper = dots.filter((d) => d < recommended.price).length;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <QuoteTile key={selected.id} rfq={rfq} quote={selected} />

      {fair !== null && gap !== null && dots.length ? (
        <Tile className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
          <div className="self-center">
            <h2 className="t-title">Takliflar bozorga nisbatan</h2>
            <p className="serif mt-1 text-[28px]">{gap >= 0 ? `${shortSoum(gap)} arzon` : `${shortSoum(-gap)} qimmat`}</p>
            <p className="mt-2 text-[13px] text-text-2">
              {recommended.supplier} taklifi bozor medianasidan {gap >= 0 ? "past" : "yuqori"} ({pct(Math.abs((gap / fair) * 100), 0)}). Namunadagi {dots.length} ta e’londan {cheaper} tasi bundan arzon.
            </p>
            <p className="t-cap mt-2">Nuqtalar ustiga olib boring</p>
          </div>
          <div className="min-w-0">
            <QuoteSpread dots={dots} median={fair} quotes={rfq.quotes} />
          </div>
        </Tile>
      ) : null}

      {others.length ? (
        <Tile className="p-0">
          <div className="p-5 pb-3">
            <TileHeader title={`Boshqa ${others.length} ta taklif`} right="ball bo‘yicha" />
          </div>
          <ul>
            {others.map((q) => {
              const r = ratingWord(q.diff_pct);
              return (
                <li key={q.id} className="border-t border-[rgb(15_23_22/0.06)]">
                  <button type="button" onClick={() => setSelectedId(q.id)} className="flex min-h-[68px] w-full items-center gap-4 px-5 py-3 text-left transition-colors duration-150 last:rounded-b-[36px] hover:bg-[var(--nested)]">
                    <span className="min-w-0 flex-1">
                      <span className="block text-[14px] font-semibold">{q.supplier}</span>
                      <span className="block truncate text-[13px] text-text-2">
                        {q.verification} · yetkazish {q.delivery} · {q.qty} dona
                      </span>
                    </span>
                    <span className="shrink-0 text-[13px] text-text-2">
                      {r.word} {q.diff_pct !== null ? <span className={cn("mono font-medium", r.tone)}>{pctSigned(q.diff_pct, 0)}</span> : null}
                    </span>
                    <span className="w-24 shrink-0 text-right text-[15px] font-semibold">{shortSoum(q.price)}</span>
                    <ChevronRight size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-muted" />
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="px-5 pt-1 pb-5 text-[13px] text-text-2">Yangi taklif kelsa, ogohlantirish yuboramiz.</p>
        </Tile>
      ) : null}

      <MatchesTile rfq={rfq} />
    </div>
  );
}

export function RfqView() {
  useCopilotScreen("birja");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const query = useRfq(selectedId ?? undefined);
  const rfq = query.data ?? null;

  return (
    <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,350fr)_minmax(0,886fr)]">
      <div className="flex min-w-0 flex-col gap-5">
        <RfqList selectedId={rfq?.id ?? selectedId} onSelect={setSelectedId} />
        {query.isPending ? <Skeleton className="h-[520px] rounded-[36px]" /> : rfq ? <RequestCard rfq={rfq} /> : null}
      </div>
      {query.isPending ? (
        <Skeleton className="h-[460px] rounded-[36px]" />
      ) : query.isError ? (
        <Tile>
          <ErrorState onRetry={() => void query.refetch()} message={query.error instanceof ApiError ? query.error.message : undefined} />
        </Tile>
      ) : rfq ? (
        <RfqBody key={rfq.id} rfq={rfq} />
      ) : (
        <Tile>
          <EmptyState text="Hali so‘rov yubormagansiz. So‘rov yuborilganda yetkazib beruvchilar takliflari shu yerda chiqadi." />
        </Tile>
      )}
    </div>
  );
}
