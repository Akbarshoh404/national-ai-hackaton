/** Real backend shapes for the prices section (Narxlar: Ombor + Baholash) and maps to what the screens render. */
import { z } from "zod";
import type { PriceStep } from "../schemas";

const num = z.number();
const numOrNull = z.number().nullable();
const strOrNull = z.string().nullable();
const attrsSchema = z.record(z.unknown());

/* ---------------------------------------------------------------- stock */

export const BRating = z.enum(["underpriced", "fair", "overpriced", "no_data"]);

export const BStockUnit = z.object({
  inventory_id: num,
  store_id: numOrNull,
  category: z.string(),
  brand: strOrNull,
  model: z.string(),
  condition: strOrNull,
  attrs: attrsSchema,
  identifier: strOrNull,
  qty: num,
  list_price_uzs: numOrNull,
  unit_cost_uzs: num,
  days_in_stock: num,
  fair_price_uzs: numOrNull,
  range_uzs: z.array(num).nullable(),
  fair_buy_price_uzs: numOrNull,
  confidence: strOrNull,
  comparables: num,
  basis: strOrNull,
  rating: BRating,
  vs_market_pct: numOrNull,
  margin_at_list_uzs: numOrNull,
  expected_days_to_sell: numOrNull,
  days_basis: z.string(),
  suggested_price_uzs: numOrNull,
  suggested_action: z.enum(["reprice_down", "reprice_up", "list_on_exchange", "keep"]),
  reasons: z.array(z.string()),
});
export type BStockUnit = z.infer<typeof BStockUnit>;

export const BStockPage = z.object({ items: z.array(BStockUnit), next_cursor: strOrNull, total: num });

export const BStockSummary = z.object({
  stock_value_cost_uzs: num,
  stock_value_market_uzs: num,
  units_total: num,
  units_overpriced: num,
  units_underpriced: num,
  units_no_data: num,
  units_older_30d: num,
  units_older_slow: num,
  slow_stock_days: num,
  overpricing_at_risk_uzs: num,
  aging_cash_tied_uzs: num,
  margin_at_risk_uzs: num,
  aging_days: num,
});

export const BStores = z.object({ items: z.array(z.object({ id: num, name: z.string() }).passthrough()) });

export const BRepriceOut = z.object({ updated: num, units: z.array(BStockUnit) });

/** `POST /stock/list-on-exchange` returns the created surplus offers (shape owned by the exchange section). */
export const BOffers = z.array(z.object({ id: num }).passthrough());

export type Rating = "under" | "fair" | "over" | "no_data";
export type StockAction = BStockUnit["suggested_action"];

export interface StockRow {
  id: string;
  inventoryId: number;
  model: string;
  attrs: string;
  category: string;
  store: string;
  qty: number;
  list_price: number | null;
  cost: number;
  market_price: number | null;
  range: [number, number] | null;
  vs_market_pct: number | null;
  margin: number | null;
  days_in_stock: number;
  expected_days: number | null;
  days_basis: string;
  rating: Rating;
  suggested_price: number | null;
  action: StockAction;
  reasons: string[];
}

const RATING: Record<z.infer<typeof BRating>, Rating> = { underpriced: "under", fair: "fair", overpriced: "over", no_data: "no_data" };

/** Human attribute line from the real attrs dict (keys starting with `_` are internal). */
export function attrsLine(attrs: Record<string, unknown>, condition: string | null) {
  const parts: string[] = [];
  if (attrs.storage_gb) parts.push(`${attrs.storage_gb} GB`);
  if (attrs.ram_gb) parts.push(`${attrs.ram_gb} GB RAM`);
  if (attrs.ssd_gb) parts.push(`${attrs.ssd_gb} GB SSD`);
  if (typeof attrs.cpu === "string") parts.push(attrs.cpu);
  if (typeof attrs.color === "string") parts.push(attrs.color);
  if (attrs.repaired === true) parts.push("ta’mirlangan");
  if (attrs.imei_registered === false) parts.push("IMEI ro‘yxatdan o‘tmagan");
  if (condition) parts.push(condition === "new" ? "yangi" : `${condition} holat`);
  return parts.join(" · ");
}

export function mapStockUnit(u: BStockUnit, stores: Map<number, string>): StockRow {
  return {
    id: String(u.inventory_id),
    inventoryId: u.inventory_id,
    model: u.model,
    attrs: attrsLine(u.attrs, u.condition),
    category: u.category,
    store: u.store_id === null ? "Do‘kon ko‘rsatilmagan" : (stores.get(u.store_id) ?? `Do‘kon ${u.store_id}`),
    qty: u.qty,
    list_price: u.list_price_uzs,
    cost: u.unit_cost_uzs,
    market_price: u.fair_price_uzs,
    range: u.range_uzs && u.range_uzs.length === 2 ? [u.range_uzs[0], u.range_uzs[1]] : null,
    vs_market_pct: u.vs_market_pct,
    margin: u.margin_at_list_uzs,
    days_in_stock: u.days_in_stock,
    expected_days: u.expected_days_to_sell,
    days_basis: u.days_basis,
    rating: RATING[u.rating],
    suggested_price: u.suggested_price_uzs,
    action: u.suggested_action,
    reasons: u.reasons,
  };
}

export interface StockKpi {
  total: number;
  value_cost: number;
  value_market: number;
  overpriced: number;
  underpriced: number;
  no_data: number;
  aging: number;
  aging_days: number;
  slow: number;
  slow_days: number;
  overpricing_at_risk: number;
  aging_cash_tied: number;
  margin_at_risk: number;
}

export const mapStockSummary = (s: z.infer<typeof BStockSummary>): StockKpi => ({
  total: s.units_total,
  value_cost: s.stock_value_cost_uzs,
  value_market: s.stock_value_market_uzs,
  overpriced: s.units_overpriced,
  underpriced: s.units_underpriced,
  no_data: s.units_no_data,
  aging: s.units_older_30d,
  aging_days: s.aging_days,
  slow: s.units_older_slow,
  slow_days: s.slow_stock_days,
  overpricing_at_risk: s.overpricing_at_risk_uzs,
  aging_cash_tied: s.aging_cash_tied_uzs,
  margin_at_risk: s.margin_at_risk_uzs,
});

/* ---------------------------------------------------------------- pricing desk */

const BPriceSample = z.object({
  listing_id: num,
  title: z.string(),
  price_uzs: num,
  price_usd: num,
  condition: strOrNull,
  district: strOrNull,
  seller_type: strOrNull,
  posted_at: z.string(),
  source_url: strOrNull,
  attrs: attrsSchema,
});

const BBuyQuote = z.object({
  resale_price_uzs: num,
  handling_pct: num,
  handling_uzs: num,
  dealer_margin_pct: num,
  expected_profit_uzs: num,
  max_buy_price_uzs: num,
  max_buy_price_usd: num,
  expected_days_to_sell: numOrNull,
  days_basis: strOrNull,
});

export const BPriceEstimate = z.object({
  category: z.string(),
  fair_price_uzs: num,
  fair_price_usd: num,
  range_uzs: z.tuple([num, num]),
  fair_buy_price_uzs: num,
  fair_buy_price_usd: num,
  comparables: num,
  basis: z.string(),
  confidence: z.enum(["high", "medium", "low"]),
  samples: z.array(BPriceSample),
  buy_quote: BBuyQuote.nullable().optional(),
});
export type BPriceEstimate = z.infer<typeof BPriceEstimate>;

export interface Comparable {
  key: string;
  price: number;
  meta: string;
  condition: string;
  diff_pct: number;
  url: string | null;
}

export interface PriceVerdict {
  max_uzs: number;
  max_usd: number;
  resale: number;
  handling: number;
  profit: number;
  days: number | null;
  days_basis: string | null;
  median: number;
  range_low: number;
  range_high: number;
  listings: number;
  basis: string;
  confidence: "high" | "medium" | "low";
  steps: PriceStep[];
  comparables: Comparable[];
}

const pct0 = (v: number) => `${Math.round(v * 100)}%`;
const SELLER: Record<string, string> = { shop: "do‘kon", private: "shaxsiy" };

export function mapPriceEstimate(e: BPriceEstimate): PriceVerdict {
  const q = e.buy_quote ?? null;
  const handling = q?.handling_uzs ?? 0;
  const profit = q?.expected_profit_uzs ?? e.fair_price_uzs - e.fair_buy_price_uzs;
  const steps: PriceStep[] = [
    { label: "Bozor narxi", sub: `${e.comparables} e’lon`, delta: e.fair_price_uzs, kind: "start", reason: e.basis },
    ...(q && handling
      ? [{ label: "Sotish xarajati", sub: pct0(q.handling_pct), delta: -handling, kind: "minus" as const, reason: "Qayta sotishdagi xarajatlar bozor narxining ulushi sifatida" }]
      : []),
    {
      label: "Sizning foydangiz",
      sub: q ? pct0(q.dealer_margin_pct - q.handling_pct) : "",
      delta: -profit,
      kind: "margin",
      reason: q ? `Diler marjasi ${pct0(q.dealer_margin_pct)}, sotish xarajati chiqarilgan` : "Bozor narxi va maksimal xarid narxi farqi",
    },
    { label: "Maks. xarid", sub: "", delta: e.fair_buy_price_uzs, kind: "end", reason: "Bundan qimmatga olsangiz, marja qolmaydi" },
  ];
  return {
    max_uzs: e.fair_buy_price_uzs,
    max_usd: e.fair_buy_price_usd,
    resale: e.fair_price_uzs,
    handling,
    profit,
    days: q?.expected_days_to_sell ?? null,
    days_basis: q?.days_basis ?? null,
    median: e.fair_price_uzs,
    range_low: e.range_uzs[0],
    range_high: e.range_uzs[1],
    listings: e.comparables,
    basis: e.basis,
    confidence: e.confidence,
    steps,
    comparables: e.samples.map((s) => ({
      key: String(s.listing_id),
      price: s.price_uzs,
      meta: [s.title, attrsLine(s.attrs, null), s.seller_type ? (SELLER[s.seller_type] ?? s.seller_type) : null, s.district, s.posted_at.slice(0, 10)].filter(Boolean).join(" · "),
      condition: s.condition ? (s.condition === "new" ? "yangi" : `${s.condition} holat`) : "",
      diff_pct: e.fair_price_uzs ? (s.price_uzs / e.fair_price_uzs - 1) * 100 : 0,
      url: s.source_url,
    })),
  };
}

/* ---------------------------------------------------------------- fast inputs */

export const BParsedItem = z.object({
  category: strOrNull,
  brand: strOrNull,
  model: strOrNull,
  condition: strOrNull,
  district: strOrNull,
  attrs: attrsSchema,
  price: numOrNull.optional(),
  currency: z.enum(["USD", "UZS"]).nullable(),
  missing_fields: z.array(z.string()),
  confidence: z.enum(["high", "medium", "low"]),
  source: z.enum(["llm", "rules"]),
});

export const BVoiceOut = z.object({ transcript: z.string(), parsed: BParsedItem });

export const BImeiOut = z.object({
  imei: z.string(),
  valid: z.boolean(),
  tac: strOrNull,
  brand: strOrNull,
  model: strOrNull,
  storage_options: z.array(num),
  category: strOrNull,
  source: z.string(),
});

const BListing = z.object({
  id: num,
  category: z.string(),
  brand: strOrNull,
  model: z.string(),
  title: z.string(),
  condition: strOrNull,
  price_uzs: num,
  price_usd: num,
  district: strOrNull,
  attrs: attrsSchema,
  source_url: strOrNull,
});

export const BLinkPrice = z.object({
  listing: BListing,
  estimate: BPriceEstimate,
  diff_pct: num,
  badge: z.string(),
  fetched: z.enum(["database", "telegram"]),
});

/** What the pricing desk identified from the seller's input. */
export interface Detected {
  category: string;
  brand: string | null;
  model: string;
  condition: string | null;
  attrs: Record<string, unknown>;
  storage_options: number[];
  identifier: string | null;
  label: string;
  detail: string;
}

const cleanAttrs = (attrs: Record<string, unknown>) => Object.fromEntries(Object.entries(attrs).filter(([k, v]) => !k.startsWith("_") && v !== null && v !== undefined));
const label = (brand: string | null, model: string) => (brand && !model.toLowerCase().startsWith(brand.toLowerCase()) ? `${brand} ${model}` : model);

export class InputNotRecognized extends Error {}

export function mapParsedItem(p: z.infer<typeof BParsedItem>, transcript?: string): Detected {
  if (!p.model || !p.category) throw new InputNotRecognized(transcript ? `“${transcript}” dan model aniqlanmadi. Aniqroq yozing.` : "Model aniqlanmadi. Masalan: iphone 13 pro 256 A holat.");
  const attrs = cleanAttrs(p.attrs);
  const missing = p.missing_fields.length ? `Yetishmaydi: ${p.missing_fields.join(", ")}` : null;
  return {
    category: p.category,
    brand: p.brand,
    model: p.model,
    condition: p.condition,
    attrs,
    storage_options: [],
    identifier: null,
    label: [label(p.brand, p.model), attrsLine(attrs, null)].filter(Boolean).join(" · "),
    detail: [transcript ? `Ovoz: “${transcript}”` : null, p.source === "llm" ? "AI tahlil qildi" : "Qoidalar bilan aniqlandi", missing].filter(Boolean).join(" · "),
  };
}

export function mapImei(r: z.infer<typeof BImeiOut>): Detected {
  if (!r.valid) throw new InputNotRecognized("IMEI noto‘g‘ri: 15 raqam va to‘g‘ri nazorat raqami kerak.");
  if (!r.model || !r.category) throw new InputNotRecognized("Bu IMEI bo‘yicha model topilmadi. Modelni yozib kiriting.");
  const storage = r.storage_options.length === 1 ? { storage_gb: r.storage_options[0] } : {};
  return {
    category: r.category,
    brand: r.brand,
    model: r.model,
    condition: null,
    attrs: storage,
    storage_options: r.storage_options,
    identifier: r.imei,
    label: label(r.brand, r.model),
    detail: `IMEI ${r.imei} · TAC ${r.tac ?? "yo‘q"}${r.storage_options.length > 1 ? " · xotirani tanlang" : ""}`,
  };
}

export function mapLinkPrice(r: z.infer<typeof BLinkPrice>): Detected {
  const l = r.listing;
  const attrs = cleanAttrs(l.attrs);
  return {
    category: l.category,
    brand: l.brand,
    model: l.model,
    condition: l.condition,
    attrs,
    storage_options: [],
    identifier: null,
    label: [label(l.brand, l.model), attrsLine(attrs, null)].filter(Boolean).join(" · "),
    detail: `E’londagi narx ${Math.round(l.price_uzs).toLocaleString("ru-RU")} so‘m · ${r.badge}`,
  };
}
