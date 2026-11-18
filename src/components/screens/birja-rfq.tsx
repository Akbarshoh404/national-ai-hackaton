"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { QuoteSpread } from "@/components/charts/quote-spread";
import { useCopilotScreen } from "@/components/raft/shell";
import { ErrorState, Skeleton } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useAcceptQuote, useCounterQuote, useRfq } from "@/lib/api/hooks";
import type { Quote, Rfq } from "@/lib/api/schemas";
import { pct, pctSigned, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

function ratingWord(diff: number) {
  if (diff > 1) return { word: "Qimmat", tone: "text-warning" };
  if (diff < -1) return { word: "Arzon", tone: "text-success" };
  return { word: "Adolatli", tone: "text-text" };
}

function RequestCard({ rfq }: { rfq: Rfq }) {
  const steps = [
    { title: "Yuborildi", meta: rfq.created },
    { title: `${rfq.quotes.length} ta taklif keldi`, meta: "bugun" },
    { title: "Taklifni tanlang", meta: rfq.deal ? rfq.deal.supplier : "hozir" },
    { title: rfq.deal ? "Bitim kitoblarga yozildi" : "Bitim kitoblarga yoziladi", meta: rfq.deal ? "bugun" : "avtomatik" },
  ];
  const current = rfq.deal ? 4 : 2;
  return (
    <Tile className="flex flex-col xl:row-span-3">
      <p className="text-[13px] text-text-2">So‘rov #{rfq.id}</p>
      <h2 className="serif mt-3 text-[26px]">{rfq.title}</h2>
      <dl className="mt-4 flex flex-col gap-2">
        {rfq.specs.map((s) => (
          <div key={s.label} className="kv">
            <dt>{s.label}</dt>
            <dd>{s.value}</dd>
          </div>
        ))}
      </dl>
      <hr className="my-5 border-[rgb(15_23_22/0.08)]" />
      <p className="text-[13px] text-text-2">Bozor bahosi</p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="serif text-[32px]">{usd(rfq.market_total)}</span>
        <span className="text-[14px] text-text-2">
          = {usd(rfq.market_unit)} × {rfq.qty}
        </span>
      </p>
      <p className="mt-1 text-[13px] text-text-2">{rfq.listings} ta e’lon medianasi</p>
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

function QuoteTile({ rfq, quote }: { rfq: Rfq; quote: Quote }) {
  const accept = useAcceptQuote();
  const counter = useCounterQuote();
  const [countering, setCountering] = useState(false);
  const [price, setPrice] = useState(String(quote.price - 4));
  const saving = rfq.market_total - quote.total * (rfq.qty / quote.qty);
  const rating = ratingWord(quote.diff_pct);
  const acceptError = accept.error instanceof ApiError ? accept.error.message : accept.isError ? "Bajarilmadi. Qayta urinib ko‘ring." : null;
  const valid = Number(price) > 0;

  return (
    <section className="tile outline-[1.5px] -outline-offset-1 outline-accent outline-solid">
      <h2 className="text-[20px] leading-7 font-semibold">{quote.supplier}</h2>
      <p className="text-[13px] text-text-2">{quote.verification}</p>
      <p className="mt-3 flex items-baseline gap-2">
        <span className="serif text-[56px]">{usd(quote.price)}</span>
        <span className="text-[15px] text-text-2">/ dona</span>
      </p>
      <p className="mt-2 text-[14px] text-text-2">
        {rating.word} <span className={cn("mono font-medium", rating.tone)}>{pct(quote.diff_pct, 0)}</span>
        <span className="ml-2">
          Jami {usd(quote.total)} · {saving >= 0 ? `bozor bahosidan ${usd(saving)} kam` : `bozor bahosidan ${usd(-saving)} ko‘p`}
          {quote.qty !== rfq.qty ? ` · faqat ${quote.qty} dona` : ""}
        </span>
      </p>
      <div className="panel mt-4 p-4">
        <h3 className="text-[14px] font-semibold">Nega aynan shu taklif</h3>
        <ul className="mt-2 flex flex-col gap-2 text-[14px]">
          {quote.why.map((w) => (
            <li key={w.text} className={w.warn ? "text-warning" : undefined}>
              {w.text}
            </li>
          ))}
        </ul>
      </div>

      {rfq.note ? (
        <p role="status" className="mt-3 text-[13px] text-text-2">
          {rfq.note}
        </p>
      ) : null}

      {rfq.deal ? (
        <div role="status" className="mt-4 flex flex-wrap items-center gap-3 text-[14px]">
          <span className="font-medium">
            {rfq.deal.label} {rfq.deal.id}: {rfq.deal.supplier}, {usd(rfq.deal.total)}
          </span>
          <Link href="/kitoblar?tab=hisobotlar" className="link">
            Kitoblarda ko‘rish
          </Link>
        </div>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button variant="primary" size="lg" disabled={accept.isPending} onClick={() => accept.mutate(quote.id)}>
              Taklifni qabul qilish · {usd(quote.total)}
            </Button>
            <Button variant="plain" aria-expanded={countering} onClick={() => setCountering((v) => !v)}>
              Narxni kelishish
            </Button>
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
              <div className="w-[160px]">
                <label className="field-label" htmlFor="counter-price">
                  Sizning narxingiz, $
                </label>
                <input id="counter-price" className="input mono" inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} />
              </div>
              <Button type="submit" disabled={!valid || counter.isPending}>
                Taklif yuborish
              </Button>
              {!valid ? <p className="pb-3 text-[13px] text-text-2">Narxni kiriting.</p> : null}
            </form>
          ) : null}
        </>
      )}
    </section>
  );
}

export function RfqView() {
  useCopilotScreen("birja");
  const query = useRfq();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (query.isPending) {
    return (
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,350fr)_minmax(0,886fr)]" role="status" aria-label="Yuklanmoqda">
        <Skeleton className="h-[640px] rounded-[36px]" />
        <Skeleton className="h-[460px] rounded-[36px]" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <Tile>
        <ErrorState onRetry={() => void query.refetch()} />
      </Tile>
    );
  }

  const rfq = query.data;
  const recommended = rfq.quotes.find((q) => q.recommended) ?? rfq.quotes[0];
  const selected = rfq.quotes.find((q) => q.id === selectedId) ?? recommended;
  const others = rfq.quotes.filter((q) => q.id !== selected.id);
  const gap = rfq.market_unit - recommended.price;
  const cheaper = rfq.market_dots.filter((d) => d < recommended.price).length;

  return (
    <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,350fr)_minmax(0,886fr)] xl:items-stretch">
      <RequestCard rfq={rfq} />
      <div className="flex min-w-0 flex-col gap-5">
        <QuoteTile key={selected.id} rfq={rfq} quote={selected} />

        <Tile className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
          <div className="self-center">
            <h2 className="t-title">Takliflar bozorga nisbatan</h2>
            <p className="serif mt-1 text-[28px]">{gap >= 0 ? `${usd(gap)} arzon` : `${usd(-gap)} qimmat`}</p>
            <p className="mt-2 text-[13px] text-text-2">
              {recommended.supplier.replace(" Trade", "")} taklifi bozor medianasidan past. {rfq.listings} ta e’londan atigi {cheaper} tasi bundan arzon.
            </p>
            <p className="t-cap mt-2">Nuqtalar ustiga olib boring</p>
          </div>
          <div className="min-w-0">
            <QuoteSpread dots={rfq.market_dots} median={rfq.market_unit} quotes={rfq.quotes} />
          </div>
        </Tile>

        <Tile className="p-0">
          <div className="p-5 pb-3">
            <TileHeader title={`Boshqa ${others.length} ta taklif`} right="narx bo‘yicha" />
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
                        {q.verification} · {q.delivery} · kafolat {q.warranty}
                      </span>
                    </span>
                    <span className="shrink-0 text-[13px] text-text-2">
                      {r.word} <span className={cn("mono font-medium", r.tone)}>{pctSigned(q.diff_pct, 0)}</span>
                    </span>
                    <span className="w-16 shrink-0 text-right text-[17px] font-semibold">{usd(q.price)}</span>
                    <ChevronRight size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-muted" />
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="px-5 pt-1 pb-5 text-[13px] text-text-2">Yangi takliflar kelsa, Telegram orqali xabar beramiz.</p>
        </Tile>
      </div>
    </div>
  );
}
