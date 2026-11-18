"use client";

import { useState } from "react";
import { RangeBar } from "@/components/charts/small";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import type { MyQuote, RfqItem } from "@/lib/api/backend/exchange";
import { ApiError } from "@/lib/api/client";
import { useDemand, useIncoming, useRespondCounter, useRfqMarket, useSendQuote } from "@/lib/api/hooks";
import { dateShort, num, shortNum, shortSoum, soum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DemandBars } from "./birja-market";

interface Draft {
  price: string;
  qty: string;
  days: string;
  note: string;
}

const draftKey = (id: number) => `raft_quote_draft_${id}`;
const DAY_MS = 86_400_000;

function initialDraft(rfq: RfqItem): Draft {
  try {
    const saved = window.localStorage.getItem(draftKey(rfq.id));
    if (saved) return JSON.parse(saved) as Draft;
  } catch {
    /* no saved draft */
  }
  return { price: rfq.target_unit_price ? String(Math.round(rfq.target_unit_price)) : "", qty: String(rfq.qty), days: "", note: "" };
}

/** "3 kun qoldi" from the deadline; null when the request has none. */
function timeLeft(deadline: string | null) {
  if (!deadline) return null;
  const days = Math.ceil((Date.parse(`${deadline}T23:59:59Z`) - Date.now()) / DAY_MS);
  if (days < 0) return { text: "muddati o‘tgan", urgent: true };
  return { text: days === 0 ? "bugun tugaydi" : `${days} kun qoldi`, urgent: days <= 1 };
}

const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : e ? fallback : null);

function SentQuote({ quote }: { quote: MyQuote }) {
  const respond = useRespondCounter();
  const [finalPrice, setFinalPrice] = useState(String(Math.round(quote.unit_price)));
  const error = errorText(respond.error, "Yuborilmadi. Qayta urinib ko‘ring.");
  if (quote.status === "accepted") {
    return (
      <p role="status" className="mt-3 flex min-h-12 items-center text-[14px] font-medium text-success">
        Xaridor taklifingizni qabul qildi. Bitim kitoblarga yozildi.
      </p>
    );
  }
  if (quote.status === "rejected") {
    return (
      <p role="status" className="mt-3 flex min-h-12 items-center text-[14px] text-text-2">
        Xaridor boshqa taklifni tanladi.
      </p>
    );
  }
  if (quote.status === "countered" && quote.counter_unit_price !== null) {
    const valid = Number(finalPrice) > 0;
    return (
      <div className="mt-3 flex flex-col gap-3 text-[14px]">
        <p role="status" className="font-medium">
          Xaridor {soum(quote.counter_unit_price)} taklif qildi (sizniki {soum(quote.unit_price)}).
          {quote.counter_note ? <span className="font-normal text-text-2"> “{quote.counter_note}”</span> : null}
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <Button variant="primary" disabled={respond.isPending} onClick={() => respond.mutate({ id: quote.id, accept: true })}>
            {shortSoum(quote.counter_unit_price)} ga rozi bo‘lish
          </Button>
          <div className="w-[180px]">
            <label className="field-label" htmlFor="final-price">
              Yakuniy narx, so‘m
            </label>
            <input id="final-price" className="input mono" inputMode="numeric" value={finalPrice} onChange={(e) => setFinalPrice(e.target.value.replace(/\D/g, ""))} />
          </div>
          <Button disabled={!valid || respond.isPending} onClick={() => respond.mutate({ id: quote.id, accept: false, price: Number(finalPrice) })}>
            Yakuniy narxni yuborish
          </Button>
        </div>
        {error ? (
          <p role="alert" className="text-[13px] text-danger">
            {error}
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <p role="status" className="mt-3 flex min-h-12 items-center text-[14px] font-medium">
      {soum(quote.unit_price)} × {quote.qty} taklif yuborildi. Xaridor javobini kutmoqda.
    </p>
  );
}

function QuoteForm({ rfq }: { rfq: RfqItem }) {
  const [form, setForm] = useState<Draft>(() => initialDraft(rfq));
  const [saved, setSaved] = useState(false);
  const send = useSendQuote();
  const market = useRfqMarket(rfq.spec);
  const est = market.data ?? null;
  const price = Number(form.price) || 0;
  const qty = Number(form.qty) || 0;
  const days = form.days === "" ? NaN : Number(form.days);
  const total = price * qty;
  const diff = est && price ? ((price - est.fair_price) / est.fair_price) * 100 : null;
  const valid = price > 0 && qty > 0 && Number.isInteger(days) && days >= 0;
  const set = (key: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setSaved(false);
    const value = key === "note" ? e.target.value : e.target.value.replace(/\D/g, "");
    setForm((f) => ({ ...f, [key]: value }));
  };
  const error = errorText(send.error, "Yuborilmadi. Qayta urinib ko‘ring.");

  const fields: { key: keyof Draft; label: string; suffix?: string; mono?: boolean }[] = [
    { key: "price", label: "Narx, so‘m", suffix: "/ dona", mono: true },
    { key: "qty", label: "Miqdor", suffix: "dona", mono: true },
    { key: "days", label: "Yetkazish", suffix: "kunda", mono: true },
    { key: "note", label: "Izoh (kafolat, holati)" },
  ];

  return (
    <Tile className="flex flex-col">
      <TileHeader title={`Taklif · So‘rov #${rfq.id}`} sub={`${rfq.title} · ${rfq.qty} dona${rfq.note ? ` · ${rfq.note}` : ""}`} />
      <div className="panel mt-3 p-4">
        {market.isPending ? (
          <SkeletonLines rows={2} height={20} />
        ) : est ? (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="flex items-baseline gap-2">
                <span className="serif text-[32px]">{shortSoum(est.fair_price)}</span>
                <span className="text-[13px] text-text-2">/ dona bozor medianasi</span>
              </p>
              <p className="t-mono-cap">
                {est.comparables} e’lon · p25–p75 {shortNum(est.p25)} – {shortNum(est.p75)}
              </p>
            </div>
            <div className="mt-3">
              <RangeBar
                min={Math.min(est.p25, price || est.p25) * 0.94}
                max={Math.max(est.p75, price || est.p75) * 1.06}
                bandLow={est.p25}
                bandHigh={est.p75}
                markers={[{ value: price || est.fair_price, label: price ? `Sizning narxingiz ${shortNum(price)}` : `Mediana ${shortNum(est.fair_price)}`, tone: "accent" }]}
                ariaLabel={`Sizning narxingiz ${soum(price)}, bozor oralig‘i ${soum(est.p25)} dan ${soum(est.p75)} gacha`}
              />
            </div>
            <p className="mt-2 text-[12px] text-text-2">Ulgurji xarid narxi: {soum(est.fair_buy_price)} / dona</p>
          </>
        ) : market.isError ? (
          <p className="text-[13px] text-text-2">Bozor bahosini yuklab bo‘lmadi.</p>
        ) : (
          <p className="text-[13px] text-text-2">Bu mahsulot uchun bozorda o‘xshash e’lonlar yetarli emas.</p>
        )}
      </div>
      {rfq.my_quote ? null : (
        <div className="mt-4 grid grid-cols-2 gap-3">
          {fields.map((f) => (
            <div key={f.key} className="min-w-0">
              <label className="field-label" htmlFor={`q-${f.key}`}>
                {f.label}
              </label>
              <div className="relative">
                <input id={`q-${f.key}`} className={cn("input", f.mono && "mono", f.suffix && "pr-16")} inputMode={f.mono ? "numeric" : undefined} value={form[f.key]} onChange={set(f.key)} />
                {f.suffix ? <span className="t-cap pointer-events-none absolute top-1/2 right-3 -translate-y-1/2">{f.suffix}</span> : null}
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-auto pt-5">
        {rfq.my_quote ? (
          <SentQuote quote={rfq.my_quote} />
        ) : (
          <>
            <div className="flex items-baseline justify-between gap-3">
              <p className="flex items-baseline gap-2">
                <span className="text-[13px] text-text-2">Jami</span>
                <span className="serif text-[32px]">{shortSoum(total)}</span>
              </p>
              {diff !== null ? (
                <p className={cn("mono text-[12px] font-medium", diff <= 0 ? "text-success" : "text-warning")}>
                  bozordan {num(Math.abs(diff), 1)}% {diff <= 0 ? "arzon" : "qimmat"}
                </p>
              ) : null}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                size="lg"
                disabled={!valid || send.isPending}
                onClick={() =>
                  send.mutate(
                    { id: rfq.id, price, qty, delivery_days: days, note: form.note.trim() },
                    {
                      onSuccess: () => {
                        try {
                          window.localStorage.removeItem(draftKey(rfq.id));
                        } catch {
                          /* nothing to clear */
                        }
                      },
                    },
                  )
                }
              >
                Taklif yuborish · {shortSoum(total)}
              </Button>
              <Button
                variant="plain"
                onClick={() => {
                  try {
                    window.localStorage.setItem(draftKey(rfq.id), JSON.stringify(form));
                    setSaved(true);
                  } catch {
                    setSaved(false);
                  }
                }}
              >
                Qoralama sifatida saqlash
              </Button>
              {!valid ? <span className="text-[13px] text-text-2">Narx, miqdor va yetkazish muddatini kiriting.</span> : null}
              {saved ? (
                <span role="status" className="text-[13px] text-text-2">
                  Saqlandi
                </span>
              ) : null}
              {error ? (
                <span role="alert" className="text-[13px] text-danger">
                  {error}
                </span>
              ) : null}
            </div>
          </>
        )}
      </div>
    </Tile>
  );
}

export function SupplierView() {
  const query = useIncoming();
  const demand = useDemand();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const items = query.data?.items ?? [];
  const selected = items.find((r) => r.id === selectedId) ?? items[0];

  return (
    <>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Tile className="flex flex-col">
          <TileHeader title="Kelgan so‘rovlar" sub="Sizning toifalaringiz bo‘yicha" right={`${items.length} ta ochiq`} />
          <div className="mt-3 flex-1">
            <Async query={query} skeleton={<SkeletonLines rows={5} height={56} />} isEmpty={(d) => d.items.length === 0} empty={<EmptyState text="Hozircha toifalaringizda ochiq so‘rov yo‘q." />}>
              {() => (
                <ul className="flex flex-col gap-1">
                  {items.map((r) => {
                    const left = timeLeft(r.deadline);
                    return (
                      <li key={r.id}>
                        <button
                          type="button"
                          aria-current={r.id === selected?.id ? "true" : undefined}
                          onClick={() => setSelectedId(r.id)}
                          className={cn("grid min-h-[60px] w-full grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-x-2 rounded-[16px] px-3 py-2 text-left transition-colors duration-150 hover:bg-[var(--nested)]", r.id === selected?.id && "bg-[rgb(15_23_22/0.06)]")}
                        >
                          <span className="t-mono-cap">#{r.id}</span>
                          <span className="min-w-0">
                            <span className="block truncate text-[14px] font-medium">{r.title}</span>
                            <span className="block truncate text-[13px] text-text-2">{[r.buyer, r.district, r.deadline ? `muddat ${dateShort(r.deadline)}` : null].filter(Boolean).join(" · ")}</span>
                          </span>
                          <span className="text-right">
                            <span className="t-mono-cap block">{r.target_unit_price ? `maqsad ${shortNum(r.target_unit_price)} × ${r.qty}` : `${r.qty} dona`}</span>
                            <span className={cn("mono block text-[12px]", r.my_quote ? "text-accent-text" : left?.urgent ? "font-medium text-warning" : "text-text-2")}>
                              {r.my_quote ? (r.my_quote.status === "countered" ? "qarshi taklif keldi" : "taklif yuborilgan") : (left?.text ?? `${r.quotes_count} ta taklif`)}
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Async>
          </div>
        </Tile>
        {selected ? <QuoteForm key={selected.id} rfq={selected} /> : query.isPending ? <Skeleton className="h-[480px] rounded-[36px]" /> : null}
      </div>
      <Tile>
        <TileHeader title="Talab: tumanlar bo‘yicha" sub="Birjadagi so‘rovlar soni va eng ko‘p so‘ralgan modellar" right={demand.data ? `oxirgi ${demand.data.days} kun` : undefined} />
        <div className="mt-4">
          <Async query={demand} skeleton={<SkeletonLines rows={5} height={20} />} isEmpty={(d) => d.districts.length === 0} empty={<EmptyState text="So‘nggi kunlarda so‘rov bo‘lmagan." />}>
            {(data) => <DemandBars data={data} />}
          </Async>
        </div>
      </Tile>
    </>
  );
}
