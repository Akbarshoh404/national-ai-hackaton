"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../client";
import * as B from "../backend/exchange";
import { invalidate } from "./shared";

/* ------------------------------------------------------------------ RFQs (buyer) */

/** My own requests for quotes, newest first. */
export const useRfqs = () =>
  useQuery({
    queryKey: ["rfqs"],
    queryFn: () => api("/exchange/rfqs", { schema: B.page(B.RfqRaw), query: { scope: "mine", limit: 100 }, map: (p) => ({ ...p, items: p.items.map(B.mapRfq) }) }),
  });

export interface RfqDetail extends B.RfqItem {
  quotes: B.RfqQuote[];
  recommendation: { quote_id: number; text: string; saving: number } | null;
  /** Fair retail price and fair purchase (wholesale) price of the item, UZS. */
  fair_price: number | null;
  fair_buy_price: number | null;
  /** Comparable listings (p25–p75, sample prices); null when the market has too few of them. */
  market: B.MarketEstimate | null;
  deal: B.DealView | null;
  matches: B.Lot[];
}

/** Market estimate for an item; null when the backend has too few comparables (4xx). */
async function estimate(spec: B.ItemSpec): Promise<B.MarketEstimate | null> {
  try {
    return await api("/market/price", { method: "POST", body: spec, schema: B.PriceEstimateRaw, map: B.mapEstimate });
  } catch (error) {
    if (error instanceof ApiError && error.status >= 400 && error.status < 500) return null;
    throw error;
  }
}

async function loadRfq(id: number | undefined): Promise<RfqDetail | null> {
  let raw: B.RfqRaw;
  if (id === undefined) {
    const latest = await api("/exchange/rfqs", { schema: B.page(B.RfqRaw), query: { scope: "mine", limit: 1 } });
    if (!latest.items.length) return null;
    raw = latest.items[0];
  } else {
    raw = await api(`/exchange/rfqs/${id}`, { schema: B.RfqRaw });
  }
  const rfq = B.mapRfq(raw);
  const [ranked, market, deals, matches] = await Promise.all([
    api(`/exchange/rfqs/${rfq.id}/quotes`, { schema: B.RankedQuotesRaw }),
    estimate(rfq.spec),
    api("/exchange/deals", { schema: B.page(B.DealRaw), query: { rfq_id: rfq.id, limit: 1 } }),
    api(`/exchange/rfqs/${rfq.id}/matches`, { schema: B.OfferRaw.array() }),
  ]);
  return {
    ...rfq,
    quotes: B.mapQuotes(ranked),
    recommendation: ranked.recommendation ? { quote_id: ranked.recommendation.quote_id, text: ranked.recommendation.text, saving: ranked.recommendation.saving_vs_worst_uzs } : null,
    fair_price: ranked.fair_price_uzs,
    fair_buy_price: ranked.fair_buy_price_uzs,
    market,
    deal: deals.items[0] ? B.mapDeal(deals.items[0]) : null,
    matches: matches.map(B.mapOffer),
  };
}

/**
 * One of my requests with its ranked quotes, market estimate, booked deal and matching board offers.
 * Without an id: my most recent request (null when I have none).
 */
export const useRfq = (id?: number | null) =>
  useQuery({
    queryKey: ["rfq", id ?? "latest"],
    queryFn: () => loadRfq(id ?? undefined),
    enabled: id !== null,
  });

export function useAcceptQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api(`/exchange/quotes/${id}/accept`, { method: "POST", schema: B.DealRaw, map: B.mapDeal }),
    onSettled: () => invalidate(qc, "rfq", "rfqs", "deals", "incoming", "transactions", "audit", "activity", "dashboard"),
  });
}

export function useCounterQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, price, note }: { id: number; price: number; note?: string }) =>
      api(`/exchange/quotes/${id}/counter`, { method: "POST", schema: B.QuoteRaw, body: { unit_price: price, note: note || null } }),
    onSuccess: () => invalidate(qc, "rfq", "dashboard", "activity"),
  });
}

/* ------------------------------------------------------------------ supplier side */

/** Open requests from other companies in my categories (each with my own quote, if any). */
export const useIncoming = () =>
  useQuery({
    queryKey: ["incoming"],
    queryFn: () => api("/exchange/rfqs", { schema: B.page(B.RfqRaw), query: { scope: "incoming", limit: 100 }, map: (p) => ({ ...p, items: p.items.map(B.mapRfq) }) }),
  });

/** Market estimate (fair price, p25–p75, comparables) for a requested item. */
export const useRfqMarket = (spec: B.ItemSpec | null) =>
  useQuery({ queryKey: ["rfq-market", spec], queryFn: () => estimate(spec as B.ItemSpec), enabled: spec !== null });

export function useSendQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, price, qty, delivery_days, note }: { id: number; price: number; qty: number; delivery_days: number; note?: string }) =>
      api(`/exchange/rfqs/${id}/quotes`, { method: "POST", schema: B.QuoteRaw, body: { unit_price: price, qty, delivery_days, note: note || null } }),
    onSuccess: () => invalidate(qc, "incoming", "rfq", "dashboard", "activity"),
  });
}

/** Supplier answers a buyer's counter: accept it, or set a final price. */
export function useRespondCounter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, accept, price }: { id: number; accept: boolean; price?: number }) =>
      api(`/exchange/quotes/${id}/respond`, { method: "POST", schema: B.QuoteRaw, body: accept ? { accept: true } : { accept: false, unit_price: price } }),
    onSuccess: () => invalidate(qc, "incoming", "rfq", "dashboard", "activity"),
  });
}

/* ------------------------------------------------------------------ board, deals, demand */

/** Active offers on the board (wholesale lots, surplus stock, car trade, co-brokerage). */
export const useLots = () =>
  useQuery({
    queryKey: ["lots"],
    queryFn: () => api("/exchange/offers", { schema: B.page(B.OfferRaw), query: { limit: 100 }, map: (p) => ({ ...p, items: p.items.map(B.mapOffer) }) }),
  });

export function useBuyOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, qty }: { id: number; qty: number }) => api(`/exchange/offers/${id}/buy`, { method: "POST", schema: B.DealRaw, body: { qty }, map: B.mapDeal }),
    onSettled: () => invalidate(qc, "lots", "rfq", "deals", "transactions", "activity", "dashboard"),
  });
}

/** My deals (as buyer or seller), newest first. UZS. */
export const useDeals = () =>
  useQuery({
    queryKey: ["deals"],
    queryFn: () => api("/exchange/deals", { schema: B.page(B.DealRaw), query: { limit: 50 }, map: (p) => ({ ...p, items: p.items.map(B.mapDeal) }) }),
  });

export const useDemand = () => useQuery({ queryKey: ["demand"], queryFn: () => api("/exchange/demand", { schema: B.DemandRaw, query: { days: 30 }, map: B.mapDemand }) });

/* ------------------------------------------------------------------ sourcing radar */

export const RADAR_MIN_DISCOUNT = 15;
export const RADAR_DAYS = 7;

export const useRadar = () =>
  useQuery({
    queryKey: ["radar"],
    queryFn: () =>
      api("/market/sourcing-radar", {
        schema: B.ListingPage,
        query: { min_discount_pct: RADAR_MIN_DISCOUNT, days: RADAR_DAYS, limit: 200 },
        map: (p) => B.mapRadar(p, { min_discount: RADAR_MIN_DISCOUNT, days: RADAR_DAYS }),
      }),
  });

/** The newest Telegram posts the extractor has read (live listener), polled. First = current, rest = previous. */
export const useRadarFeed = () =>
  useQuery({
    queryKey: ["radar-feed"],
    queryFn: () =>
      api("/market/listings", {
        schema: B.ListingPage,
        query: { limit: 30 },
        map: (p) => p.items.filter((l) => l.origin === "telegram").slice(0, 4).map(B.mapFeedPost),
      }),
    refetchInterval: 30_000,
  });

