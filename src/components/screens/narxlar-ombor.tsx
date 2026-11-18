"use client";

import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { RatingLabel, RATING } from "@/components/raft/rating";
import { useCopilotScreen, useShell } from "@/components/raft/shell";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { KpiStrip, Tile } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useListOnExchange, useReprice, useStockSummary, useStockUnits } from "@/lib/api/hooks";
import type { Rating, StockUnit } from "@/lib/api/schemas";
import { daysLabel, pctSigned, usd, usdSigned } from "@/lib/format";
import { cn, downloadText, toCsv } from "@/lib/utils";

const AGING = 40;

function exportUnits(units: StockUnit[], format: "xlsx" | "csv" | "1c") {
  const rows = [
    ["Model", "Xususiyatlar", "Do‘kon", "Narx", "Bozor", "Tannarx", "Omborda kun", "Baho", "Tavsiya"],
    ...units.map((u) => [u.model, u.attrs, u.store, u.list_price, u.market_price ?? "", u.cost, u.days_in_stock, RATING[u.rating].label, u.suggested_price ?? ""]),
  ];
  downloadText(`raft-ombor${format === "1c" ? "-1c" : format === "xlsx" ? "-excel" : ""}.csv`, toCsv(rows));
}

function SelectField({ id, label, value, onChange, options }: { id: string; label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div className="w-[168px] max-md:w-full">
      <label className="field-label mb-1 text-[12px]" htmlFor={id}>
        {label}
      </label>
      <select id={id} className="input h-11" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function OmborView() {
  const { showUndo } = useShell();
  const summary = useStockSummary();
  const units = useStockUnits();
  const reprice = useReprice();
  const listOnExchange = useListOnExchange();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [category, setCategory] = useState("all");
  const [rating, setRating] = useState("all");
  const [store, setStore] = useState("all");
  const [agingOnly, setAgingOnly] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  useCopilotScreen("narxlar", [...selected]);

  const all = useMemo(() => units.data?.items ?? [], [units.data]);
  const rows = useMemo(() => {
    const order: Record<Rating, number> = { over: 0, under: 1, no_data: 2, fair: 3 };
    return all
      .filter((u) => (category === "all" || u.category === category) && (rating === "all" || u.rating === rating) && (store === "all" || u.store === store) && (!agingOnly || u.days_in_stock >= AGING))
      .sort((a, b) => order[a.rating] - order[b.rating] || b.days_in_stock - a.days_in_stock);
  }, [all, category, rating, store, agingOnly]);

  const overpriced = all.filter((u) => u.rating === "over");
  const chosen = all.filter((u) => selected.has(u.id));
  const repriceable = chosen.filter((u) => u.suggested_price !== null && u.suggested_price !== u.list_price);
  const visibleIds = rows.map((u) => u.id);
  const visibleSelected = visibleIds.filter((id) => selected.has(id)).length;

  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const applyReprice = (ids: string[]) => {
    setNotice(null);
    reprice.mutate(
      { unit_ids: ids },
      {
        onSuccess: (result) => {
          setSelected(new Set());
          if (result.changed.length === 0) return;
          showUndo({
            text: `${result.changed.length} ta narx o‘zgartirildi`,
            onUndo: () => reprice.mutate({ prices: result.changed.map((c) => ({ id: c.id, price: c.from })) }),
          });
        },
      },
    );
  };

  const kpi = summary.data;

  return (
    <>
      {kpi ? (
        <KpiStrip
          items={[
            { label: "Tannarx bo‘yicha", value: usd(kpi.value_cost), note: `${kpi.total} dona` },
            { label: "Bozor bo‘yicha", value: usd(kpi.value_market), note: `${usdSigned(kpi.value_market - kpi.value_cost)} farq` },
            { label: "Bozordan qimmat", value: String(kpi.overpriced), note: "dona, narxni tushiring", noteClass: "text-warning" },
            { label: "Uzoq turgan", value: String(kpi.aging), note: `${AGING} kundan ortiq` },
            { label: "Xavfdagi marja", value: usd(kpi.margin_at_risk), note: "qimmat narxlar tufayli" },
          ]}
        />
      ) : summary.isError ? null : (
        <Skeleton className="h-[122px] rounded-[36px]" />
      )}

      <Tile className="pb-3">
        <div className="flex flex-wrap items-end gap-3">
          <SelectField id="f-category" label="Toifa" value={category} onChange={setCategory} options={[{ value: "all", label: "Hammasi" }, { value: "phone", label: "Telefon" }, { value: "laptop", label: "Noutbuk" }]} />
          <SelectField
            id="f-rating"
            label="Baho"
            value={rating}
            onChange={setRating}
            options={[{ value: "all", label: "Hammasi" }, ...(Object.keys(RATING) as Rating[]).map((r) => ({ value: r, label: RATING[r].label }))]}
          />
          <SelectField id="f-store" label="Do‘kon" value={store} onChange={setStore} options={[{ value: "all", label: "Hammasi" }, ...(kpi?.stores ?? []).map((s) => ({ value: s, label: s }))]} />
          <label className="flex h-11 items-center gap-2 text-[13px]">
            <Checkbox checked={agingOnly} onCheckedChange={(v) => setAgingOnly(v === true)} aria-label="Faqat uzoq turganlar" />
            Faqat uzoq turganlar
          </label>
          <p className="t-mono-cap ml-auto self-center">{rows.length} ta qator</p>
        </div>

        <div className="relative mt-3 overflow-x-auto">
          <Async
            query={units}
            skeleton={<SkeletonLines rows={8} height={44} />}
            isEmpty={() => rows.length === 0}
            empty={
              <EmptyState
                text="Bu filtrlarga mos mahsulot yo‘q."
                action={
                  <Button
                    variant="plain"
                    className="-ml-2"
                    onClick={() => {
                      setCategory("all");
                      setRating("all");
                      setStore("all");
                      setAgingOnly(false);
                    }}
                  >
                    Filtrlarni tozalash
                  </Button>
                }
              />
            }
          >
            {() => (
              <table className="data-table min-w-[1020px]">
                <thead>
                  <tr>
                    <th className="w-8">
                      <Checkbox
                        aria-label="Barcha qatorlarni tanlash"
                        checked={visibleSelected === 0 ? false : visibleSelected === visibleIds.length ? true : "indeterminate"}
                        onCheckedChange={(v) =>
                          setSelected((prev) => {
                            const next = new Set(prev);
                            visibleIds.forEach((id) => (v === true ? next.add(id) : next.delete(id)));
                            return next;
                          })
                        }
                      />
                    </th>
                    <th>Model</th>
                    <th className="r">Narx</th>
                    <th className="r">Bozor</th>
                    <th className="r">Farq</th>
                    <th className="r">Marja</th>
                    <th className="r">Omborda</th>
                    <th className="r">Sotilish</th>
                    <th>Baho</th>
                    <th className="r">Tavsiya</th>
                    <th className="r">
                      <span className="sr-only">Amal</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((u) => {
                    const canApply = u.suggested_price !== null && u.suggested_price !== u.list_price;
                    return (
                      <tr key={u.id} className={cn(selected.has(u.id) && "bg-accent-soft/60")}>
                        <td>
                          <Checkbox aria-label={`${u.model} tanlash`} checked={selected.has(u.id)} onCheckedChange={(v) => toggle(u.id, v === true)} />
                        </td>
                        <td>
                          <div className="font-medium">{u.model}</div>
                          <div className="t-mono-cap">
                            {u.attrs} · {u.store}
                          </div>
                        </td>
                        <td className="r mono font-medium">{usd(u.list_price)}</td>
                        <td className="r mono text-text-2">{u.market_price ? usd(u.market_price) : "yo‘q"}</td>
                        <td className={cn("r mono", u.vs_market_pct === null ? "text-muted" : u.vs_market_pct > 6 ? "text-danger" : u.vs_market_pct < -6 ? "text-success" : "text-text-2")}>
                          {u.vs_market_pct === null ? "yo‘q" : pctSigned(u.vs_market_pct, 0)}
                        </td>
                        <td className="r mono">{usd(u.margin)}</td>
                        <td className={cn("r mono", u.days_in_stock >= AGING ? "text-warning" : "text-text-2")}>{u.days_in_stock} kun</td>
                        <td className="r mono text-text-2">{u.expected_days === null ? "yo‘q" : daysLabel(u.expected_days)}</td>
                        <td>
                          <RatingLabel rating={u.rating} />
                        </td>
                        <td className="r mono font-medium">{u.suggested_price ? usd(u.suggested_price) : "yo‘q"}</td>
                        <td className="r">
                          {canApply ? (
                            <button type="button" className="link -my-3 h-11 px-1 text-[13px]" aria-label={`${u.model} narxini ${usd(u.suggested_price as number)} qilish`} onClick={() => applyReprice([u.id])}>
                              Qo‘llash
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Async>
        </div>
      </Tile>

      <div className="glass sticky bottom-5 z-10 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[36px] py-2 pr-2 pl-5 max-md:bottom-24">
        <p className="text-[13px] text-text-2" role="status">
          {notice ?? (reprice.isError ? "Narxlar saqlanmadi. Qayta urinib ko‘ring." : selected.size ? `${selected.size} ta tanlandi` : overpriced.length ? `${overpriced.length} ta birlik bozordan qimmat` : "Barcha narxlar bozorga mos")}
        </p>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {selected.size ? (
            <Button variant="plain" onClick={() => setSelected(new Set())}>
              Tozalash
            </Button>
          ) : null}
          <Popover>
            <PopoverTrigger className="btn btn-secondary">
              Excel / CSV / 1C
              <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
            </PopoverTrigger>
            <PopoverContent align="end" side="top" className="w-[200px]">
              {(
                [
                  ["xlsx", "Excel uchun"],
                  ["csv", "CSV"],
                  ["1c", "1C uchun"],
                ] as const
              ).map(([format, label]) => (
                <button key={format} type="button" className="flex min-h-11 w-full items-center rounded-[12px] px-2 text-left text-[13px] hover:bg-[var(--nested)]" onClick={() => exportUnits(chosen.length ? chosen : rows, format)}>
                  {label}
                </button>
              ))}
            </PopoverContent>
          </Popover>
          {selected.size ? (
            <Button
              onClick={() =>
                listOnExchange.mutate([...selected], {
                  onSuccess: () => {
                    setNotice(`${selected.size} ta birlik birjaga chiqarildi`);
                    setSelected(new Set());
                  },
                })
              }
            >
              Birjaga chiqarish
            </Button>
          ) : null}
          {repriceable.length ? (
            <Button variant="primary" onClick={() => applyReprice(repriceable.map((u) => u.id))}>
              {repriceable.length} tasini tavsiya narxga o‘zgartirish
            </Button>
          ) : !selected.size && overpriced.length ? (
            <Button
              variant="primary"
              onClick={() => {
                setRating("over");
                setSelected(new Set(overpriced.map((u) => u.id)));
              }}
            >
              Qimmat {overpriced.length} tasini tanlash
            </Button>
          ) : null}
        </div>
      </div>
    </>
  );
}
