"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError, download, upload } from "../client";
import {
  BImeiOut,
  BLinkPrice,
  BOffers,
  BParsedItem,
  BPriceEstimate,
  BRepriceOut,
  BStockPage,
  BStockSummary,
  BStores,
  BVoiceOut,
  InputNotRecognized,
  mapImei,
  mapLinkPrice,
  mapParsedItem,
  mapPriceEstimate,
  mapStockSummary,
  mapStockUnit,
  type Detected,
  type StockRow,
} from "../backend/prices";
import { invalidate } from "./shared";

const UNITS_KEY = ["stock", "units"] as const;
type Units = { items: StockRow[]; total: number };

async function storeNames() {
  try {
    const stores = await api("/stores", { schema: BStores });
    return new Map(stores.items.map((s) => [s.id, s.name]));
  } catch {
    return new Map<number, string>();
  }
}

/** Every unit in stock (all pages), rated against the market, with its store name. */
export const useStockUnits = () =>
  useQuery({
    queryKey: UNITS_KEY,
    queryFn: async (): Promise<Units> => {
      const stores = storeNames();
      const items: StockRow[] = [];
      let cursor: string | null = null;
      let total = 0;
      do {
        const page: z.infer<typeof BStockPage> = await api("/stock/units", { schema: BStockPage, query: { limit: 500, cursor } });
        const names = await stores;
        items.push(...page.items.map((u) => mapStockUnit(u, names)));
        total = page.total;
        cursor = page.next_cursor;
      } while (cursor);
      return { items, total };
    },
  });

export const useStockSummary = () => useQuery({ queryKey: ["stock", "summary"], queryFn: () => api("/stock/summary", { schema: BStockSummary, map: mapStockSummary }) });

export type RepriceInput = { ids: string[] } | { prices: { id: string; price: number }[] };
export interface RepriceResult {
  changed: { id: string; from: number; to: number }[];
}

export function useReprice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: RepriceInput): Promise<RepriceResult> => {
      const before = new Map((qc.getQueryData<Units>(UNITS_KEY)?.items ?? []).map((u) => [u.id, u.list_price]));
      const body =
        "prices" in input
          ? { items: input.prices.map((p) => ({ inventory_id: Number(p.id), new_price_uzs: p.price })) }
          : { inventory_ids: input.ids.map(Number), use_suggested: true };
      const out = await api("/stock/reprice", { method: "POST", schema: BRepriceOut, body });
      const changed: RepriceResult["changed"] = [];
      for (const u of out.units) {
        const from = before.get(String(u.inventory_id));
        if (from != null && u.list_price_uzs != null && from !== u.list_price_uzs) changed.push({ id: String(u.inventory_id), from, to: u.list_price_uzs });
      }
      const current = qc.getQueryData<Units>(UNITS_KEY);
      if (current) {
        const fresh = new Map(out.units.map((u) => [String(u.inventory_id), u]));
        qc.setQueryData<Units>(UNITS_KEY, {
          ...current,
          items: current.items.map((row) => {
            const u = fresh.get(row.id);
            return u ? { ...mapStockUnit(u, new Map()), store: row.store } : row;
          }),
        });
      }
      return { changed };
    },
    onMutate: async (input) => {
      await qc.cancelQueries({ queryKey: UNITS_KEY });
      const previous = qc.getQueryData<Units>(UNITS_KEY);
      if (previous) {
        const target = (u: StockRow) => ("prices" in input ? input.prices.find((p) => p.id === u.id)?.price : input.ids.includes(u.id) ? (u.suggested_price ?? undefined) : undefined);
        qc.setQueryData<Units>(UNITS_KEY, {
          ...previous,
          items: previous.items.map((u) => {
            const price = target(u);
            return price === undefined ? u : { ...u, list_price: price, margin: price - u.cost };
          }),
        });
      }
      return { previous };
    },
    onError: (_error, _input, ctx) => {
      if (ctx?.previous) qc.setQueryData(UNITS_KEY, ctx.previous);
    },
    onSettled: () => invalidate(qc, "stock", "dashboard", "decisions", "activity"),
  });
}

/** Lists units as surplus offers on the exchange; returns how many offers were created. */
export function useListOnExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => api("/stock/list-on-exchange", { method: "POST", schema: BOffers, body: { inventory_ids: ids.map(Number) }, map: (offers) => offers.length }),
    onSuccess: () => invalidate(qc, "stock", "lots", "offers", "exchange", "activity"),
  });
}

/** Server-generated stock export (Excel, CSV or a 1C import CSV). */
export const exportStock = (format: "xlsx" | "csv" | "1c") => download("/stock/export", `raft-ombor${format === "1c" ? "-1c" : ""}.${format === "xlsx" ? "xlsx" : "csv"}`, { format });

export interface PriceParams {
  category: string;
  brand: string | null;
  model: string;
  condition: string | null;
  attrs: Record<string, unknown>;
}

export const usePriceVerdict = (params: PriceParams | null) =>
  useQuery({
    queryKey: ["price", params],
    enabled: params !== null,
    placeholderData: keepPreviousData,
    queryFn: () => api("/market/price", { method: "POST", schema: BPriceEstimate, body: params, map: mapPriceEstimate }),
    retry: (count, error) => !(error instanceof ApiError && error.status === 422) && count < 2,
  });

export type ParseInput = { kind: "imei" | "text" | "link"; value: string } | { kind: "voice"; audio: Blob };

export function useParseInput() {
  return useMutation({
    mutationFn: async (input: ParseInput): Promise<Detected> => {
      if (input.kind === "voice") {
        const form = new FormData();
        form.append("file", input.audio, `voice.${input.audio.type.includes("ogg") ? "ogg" : input.audio.type.includes("mp4") ? "m4a" : "webm"}`);
        return upload("/input/voice", form, { schema: BVoiceOut, map: (r) => mapParsedItem(r.parsed, r.transcript) });
      }
      if (input.kind === "imei") return api("/input/imei", { method: "POST", schema: BImeiOut, body: { imei: input.value.replace(/[\s-]/g, "") }, map: mapImei });
      if (input.kind === "link") return api("/market/price-from-link", { method: "POST", schema: BLinkPrice, body: { url: input.value.trim() }, map: mapLinkPrice });
      return api("/input/parse", { method: "POST", schema: BParsedItem, body: { text: input.value }, map: (p) => mapParsedItem(p) });
    },
  });
}
export { InputNotRecognized };

export interface BuyUnitInput {
  category: string;
  brand: string | null;
  model: string;
  condition: string | null;
  attrs: Record<string, unknown>;
  unit_cost: number;
  list_price_uzs: number | null;
  identifier: string | null;
}

/** Buying a unit from a customer adds it to stock (`POST /books/inventory`). */
export function useBuyUnit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BuyUnitInput) => api("/books/inventory", { method: "POST", schema: z.object({ id: z.number() }).passthrough(), body: { ...body, qty: 1 } }),
    onSuccess: () => invalidate(qc, "stock", "inventory", "books", "dashboard", "activity"),
  });
}
