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
import { Select } from "@/components/ui/select";
import { exportStock, useListOnExchange, useReprice, useStockSummary, useStockUnits } from "@/lib/api/hooks";
import type { Rating } from "@/lib/api/backend/prices";
import { daysLabel, num, pctSigned, shortNum, shortSoum } from "@/lib/format";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<string, string> = { phone: "Telefon", laptop: "Noutbuk", car: "Avtomobil", house: "Uy", rent: "Ijara" };
const signedSoum = (v: number) => `${v > 0 ? "+" : ""}${shortSoum(v)}`;

function SelectField({ id, label, value, onChange, options }: { id: string; label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div className="w-[168px] max-md:w-full">
      <label className="field-label mb-1 text-[12px]" htmlFor={id}>
        {label}
      </label>
      <Select id={id} value={value} onValueChange={onChange} options={options} />
    </div>
  );
}

export function OmborView() {
  const { showUndo, account } = useShell();
  // Appraisers have read-only stock access (backend core/permissions.py): no reprice, listing or export.
  const canEdit = account.roleCode !== "appraiser";
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
  const [exportError, setExportError] = useState<string | null>(null);
  useCopilotScreen("narxlar", [...selected]);

  const kpi = summary.data;
  const aging = kpi?.aging_days ?? null;
  const all = useMemo(() => units.data?.items ?? [], [units.data]);
  const categories = useMemo(() => [...new Set(all.map((u) => u.category))], [all]);
  const stores = useMemo(() => [...new Set(all.map((u) => u.store))].sort(), [all]);
  const isAging = (days: number) => aging !== null && days > aging;
  const rows = useMemo(() => {
    const order: Record<Rating, number> = { over: 0, under: 1, no_data: 2, fair: 3 };
    return all
      .filter(
        (u) =>
          (category === "all" || u.category === category) &&
          (rating === "all" || u.rating === rating) &&
          (store === "all" || u.store === store) &&
          (!agingOnly || (aging !== null && u.days_in_stock > aging)),
      )
      .sort((a, b) => order[a.rating] - order[b.rating] || b.days_in_stock - a.days_in_stock);
  }, [all, category, rating, store, agingOnly, aging]);

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
      { ids },
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

  const runExport = (format: "xlsx" | "csv" | "1c") => {
    setExportError(null);
    exportStock(format).catch(() => setExportError("Eksport bajarilmadi. Qayta urinib ko‘ring."));
  };

  return (
    <>
      {kpi ? (
        <KpiStrip
          items={[
            { label: "Tannarx bo‘yicha", value: shortSoum(kpi.value_cost), note: `${kpi.total} dona` },
            { label: "Bozor bo‘yicha", value: shortSoum(kpi.value_market), note: `${signedSoum(kpi.value_market - kpi.value_cost)} farq` },
            { label: "Bozordan qimmat", value: String(kpi.overpriced), note: "dona, narxni tushiring", noteClass: "text-warning" },
            { label: "Uzoq turgan", value: String(kpi.aging), note: `${kpi.aging_days} kundan ortiq · ${kpi.slow} tasi ${kpi.slow_days}+ kun` },
            { label: "Xavfdagi marja", value: shortSoum(kpi.margin_at_risk), note: `qimmat narx ${shortNum(kpi.overpricing_at_risk)} + muzlagan ${shortNum(kpi.aging_cash_tied)}` },
          ]}
        />
      ) : summary.isError ? null : (
        <Skeleton className="h-[122px] rounded-[36px]" />
      )}

      <Tile className="pb-3">
        <div className="flex flex-wrap items-end gap-3">
          <SelectField id="f-category" label="Toifa" value={category} onChange={setCategory} options={[{ value: "all", label: "Hammasi" }, ...categories.map((c) => ({ value: c, label: CATEGORY_LABEL[c] ?? c }))]} />
          <SelectField
            id="f-rating"
            label="Baho"
            value={rating}
            onChange={setRating}
            options={[{ value: "all", label: "Hammasi" }, ...(Object.keys(RATING) as Rating[]).map((r) => ({ value: r, label: RATING[r].label }))]}
          />
          <SelectField id="f-store" label="Do‘kon" value={store} onChange={setStore} options={[{ value: "all", label: "Hammasi" }, ...stores.map((s) => ({ value: s, label: s }))]} />
          <label className="flex h-11 items-center gap-2 text-[13px]">
            <Checkbox checked={agingOnly} disabled={aging === null} onCheckedChange={(v) => setAgingOnly(v === true)} aria-label="Faqat uzoq turganlar" />
            Faqat uzoq turganlar{aging !== null ? ` (${aging}+ kun)` : ""}
          </label>
          <p className="t-mono-cap ml-auto self-center">{rows.length} ta qator · narxlar so‘mda</p>
        </div>

        <div className="relative mt-3 overflow-x-auto">
          <Async
            query={units}
            skeleton={<SkeletonLines rows={8} height={44} />}
            isEmpty={() => rows.length === 0}
            empty={
              <EmptyState
                text={all.length === 0 ? "Omborda mahsulot yo‘q." : "Bu filtrlarga mos mahsulot yo‘q."}
                action={
                  all.length === 0 ? undefined : (
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
                  )
                }
              />
            }
          >
            {() => (
              <table className="data-table min-w-[1020px]">
                <thead>
                  <tr>
                    <th className="check-cell">
                      <Checkbox
                        className="flex"
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
                        <td className="check-cell">
                          <Checkbox className="flex" aria-label={`${u.model} tanlash`} checked={selected.has(u.id)} onCheckedChange={(v) => toggle(u.id, v === true)} />
                        </td>
                        <td>
                          <div className="font-medium">{u.model}</div>
                          <div className="t-mono-cap">{[u.attrs, u.store, u.qty > 1 ? `${u.qty} dona` : null].filter(Boolean).join(" · ")}</div>
                        </td>
                        <td className="r mono font-medium">{u.list_price === null ? "yo‘q" : num(u.list_price)}</td>
                        <td className="r mono text-text-2" title={u.range ? `Bozor oralig‘i ${num(u.range[0])} – ${num(u.range[1])} so‘m` : undefined}>
                          {u.market_price ? num(u.market_price) : "yo‘q"}
                        </td>
                        <td className={cn("r mono", u.vs_market_pct === null ? "text-muted" : u.rating === "over" ? "text-danger" : u.rating === "under" ? "text-success" : "text-text-2")}>
                          {u.vs_market_pct === null ? "yo‘q" : pctSigned(u.vs_market_pct, 0)}
                        </td>
                        <td className={cn("r mono", u.margin !== null && u.margin < 0 && "text-danger")}>{u.margin === null ? "yo‘q" : num(u.margin)}</td>
                        <td className={cn("r mono", isAging(u.days_in_stock) ? "text-warning" : "text-text-2")}>{u.days_in_stock} kun</td>
                        <td className="r mono text-text-2" title={u.days_basis}>
                          {u.expected_days === null ? "yo‘q" : daysLabel(Math.round(u.expected_days))}
                        </td>
                        <td title={u.reasons.join("\n")}>
                          <RatingLabel rating={u.rating} />
                        </td>
                        <td className="r mono font-medium">{u.suggested_price ? num(u.suggested_price) : "yo‘q"}</td>
                        <td className="r">
                          {canApply ? (
                            <button type="button" className="link -my-3 h-11 px-1 text-[13px]" aria-label={`${u.model} narxini ${num(u.suggested_price as number)} so‘m qilish`} onClick={() => applyReprice([u.id])}>
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
          {notice ??
            exportError ??
            (reprice.isError
              ? "Narxlar saqlanmadi. Qayta urinib ko‘ring."
              : listOnExchange.isError
                ? "Birjaga chiqarilmadi. Qayta urinib ko‘ring."
                : selected.size
                  ? `${selected.size} ta tanlandi`
                  : overpriced.length
                    ? `${overpriced.length} ta birlik bozordan qimmat`
                    : "Barcha narxlar bozorga mos")}
        </p>
        {canEdit ? (
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
                  ["xlsx", "Excel (.xlsx)"],
                  ["csv", "CSV (.csv)"],
                  ["1c", "1C uchun (.csv)"],
                ] as const
              ).map(([format, label]) => (
                <button key={format} type="button" className="flex min-h-11 w-full items-center rounded-[12px] px-2 text-left text-[13px] hover:bg-[var(--nested)]" onClick={() => runExport(format)}>
                  {label}
                </button>
              ))}
            </PopoverContent>
          </Popover>
          {selected.size ? (
            <Button
              disabled={listOnExchange.isPending}
              onClick={() =>
                listOnExchange.mutate([...selected], {
                  onSuccess: (offers) => {
                    setNotice(`${selected.size} ta birlik birjaga chiqarildi (${offers} ta taklif)`);
                    setSelected(new Set());
                  },
                })
              }
            >
              Birjaga chiqarish
            </Button>
          ) : null}
          {repriceable.length ? (
            <Button variant="primary" disabled={reprice.isPending} onClick={() => applyReprice(repriceable.map((u) => u.id))}>
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
        ) : null}
      </div>
    </>
  );
}
