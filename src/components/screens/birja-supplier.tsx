"use client";

import { useState } from "react";
import { RangeBar } from "@/components/charts/small";
import { Async, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useDemand, useIncoming, useSendQuote } from "@/lib/api/hooks";
import type { IncomingRfq } from "@/lib/api/schemas";
import { num, usd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DemandBars } from "./birja-market";

interface Draft {
  price: string;
  qty: string;
  delivery: string;
  warranty: string;
}

const draftKey = (id: number) => `raft_quote_draft_${id}`;

function initialDraft(rfq: IncomingRfq): Draft {
  try {
    const saved = window.localStorage.getItem(draftKey(rfq.id));
    if (saved) return JSON.parse(saved) as Draft;
  } catch {
    /* no saved draft */
  }
  return {
    price: String(rfq.id === 148 ? 258 : Math.round(rfq.market_unit * 0.985)),
    qty: String(rfq.qty),
    delivery: rfq.id === 148 ? "Payshanba, 20-noyabr" : rfq.due,
    warranty: "6 oy",
  };
}

function QuoteForm({ rfq }: { rfq: IncomingRfq }) {
  const [form, setForm] = useState<Draft>(() => initialDraft(rfq));
  const [saved, setSaved] = useState(false);
  const [editing, setEditing] = useState(false);
  const send = useSendQuote();
  const price = Number(form.price) || 0;
  const qty = Number(form.qty) || 0;
  const total = price * qty;
  const diff = ((price - rfq.market_unit) / rfq.market_unit) * 100;
  const valid = price > 0 && qty > 0;
  const sentPrice = rfq.id === 148 && rfq.my_quote === 262 ? null : rfq.my_quote;
  const showSent = sentPrice !== null && !editing;
  const set = (key: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setSaved(false);
    const value = key === "price" || key === "qty" ? e.target.value.replace(/\D/g, "") : e.target.value;
    setForm((f) => ({ ...f, [key]: value }));
  };
  const error = send.error instanceof ApiError ? send.error.message : send.isError ? "Yuborilmadi. Qayta urinib ko‘ring." : null;

  const fields: { key: keyof Draft; label: string; suffix?: string; mono?: boolean }[] = [
    { key: "price", label: "Narx, $", suffix: "/ dona", mono: true },
    { key: "qty", label: "Miqdor", suffix: "dona", mono: true },
    { key: "delivery", label: "Yetkazish" },
    { key: "warranty", label: "Kafolat" },
  ];

  return (
    <Tile className="flex flex-col">
      <TileHeader title={`Taklif · So‘rov #${rfq.id}`} sub={`${rfq.title}, ${rfq.spec}`} />
      <div className="panel mt-3 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="flex items-baseline gap-2">
            <span className="serif text-[32px]">{usd(rfq.market_unit)}</span>
            <span className="text-[13px] text-text-2">/ dona bozor medianasi</span>
          </p>
          <p className="t-mono-cap">
            {rfq.listings} e’lon · p25–p75 {usd(rfq.p25)} – {usd(rfq.p75)}
          </p>
        </div>
        <div className="mt-3">
          <RangeBar
            min={rfq.p25 * 0.94}
            max={rfq.p75 * 1.06}
            bandLow={rfq.p25}
            bandHigh={rfq.p75}
            markers={[{ value: price || rfq.market_unit, label: `Sizning narxingiz ${usd(price)}`, tone: "accent" }]}
            ariaLabel={`Sizning narxingiz ${usd(price)}, bozor oralig‘i ${usd(rfq.p25)} dan ${usd(rfq.p75)} gacha`}
          />
        </div>
      </div>
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
      <div className="mt-auto pt-5">
        <div className="flex items-baseline justify-between gap-3">
          <p className="flex items-baseline gap-2">
            <span className="text-[13px] text-text-2">Jami</span>
            <span className="serif text-[32px]">{usd(total)}</span>
          </p>
          <p className={cn("mono text-[12px] font-medium", diff <= 0 ? "text-success" : "text-warning")}>
            bozordan {num(Math.abs(diff), 1)}% {diff <= 0 ? "arzon" : "qimmat"}
          </p>
        </div>
        {rfq.accepted ? (
          <p role="status" className="mt-3 flex min-h-12 items-center text-[14px] font-medium text-success">
            Xaridor taklifingizni qabul qildi. Bitim kitoblarga yozildi.
          </p>
        ) : showSent ? (
          <div role="status" className="mt-3 flex min-h-12 flex-wrap items-center gap-3 text-[14px]">
            <span className="font-medium">{usd(sentPrice as number)} taklif yuborildi. Xaridor javobini kutmoqda.</span>
            <Button variant="plain" onClick={() => setEditing(true)}>
              Narxni o‘zgartirish
            </Button>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              size="lg"
              disabled={!valid || send.isPending}
              onClick={() =>
                send.mutate(
                  { id: rfq.id, price, qty, delivery: form.delivery, warranty: form.warranty },
                  {
                    onSuccess: () => {
                      setEditing(false);
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
              Taklif yuborish · {usd(total)}
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
            {!valid ? <span className="text-[13px] text-text-2">Narx va miqdorni kiriting.</span> : null}
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
        )}
      </div>
    </Tile>
  );
}

export function SupplierView() {
  const query = useIncoming();
  const demand = useDemand();
  const [selectedId, setSelectedId] = useState(148);
  const items = query.data?.items ?? [];
  const selected = items.find((r) => r.id === selectedId) ?? items[0];

  return (
    <>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Tile className="flex flex-col">
          <TileHeader title="Kelgan so‘rovlar" sub="Sizning toifalaringiz bo‘yicha" right={`${items.length} ta ochiq`} />
          <div className="mt-3 flex-1">
            <Async query={query} skeleton={<SkeletonLines rows={5} height={56} />}>
              {() => (
                <ul className="flex flex-col gap-1">
                  {items.map((r) => (
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
                          <span className="block truncate text-[13px] text-text-2">
                            {r.buyer} · {r.due}
                          </span>
                        </span>
                        <span className="text-right">
                          <span className="t-mono-cap block">
                            bozor {usd(r.market_unit)} × {r.qty}
                          </span>
                          <span className={cn("mono block text-[12px]", r.urgent ? "font-medium text-warning" : "text-text-2")}>{r.time_left}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Async>
          </div>
          <p className="mt-3 text-[13px] text-text-2">Xaridor kimligi taklif qabul qilingandan keyin ochiladi.</p>
        </Tile>
        {selected ? <QuoteForm key={selected.id} rfq={selected} /> : <Skeleton className="h-[480px] rounded-[36px]" />}
      </div>
      <Tile>
        <TileHeader title="Talab: tumanlar bo‘yicha" sub="Birjadagi so‘rovlar soni va eng ko‘p so‘ralgan modellar" right="oxirgi 30 kun" />
        <div className="mt-4">
          <Async query={demand} skeleton={<SkeletonLines rows={5} height={20} />}>
            {(data) => <DemandBars data={data} />}
          </Async>
        </div>
      </Tile>
    </>
  );
}
