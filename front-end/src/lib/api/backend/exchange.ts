/**
 * Exchange (Birja) + sourcing radar — zod schemas of the REAL backend responses and maps to what the screens render.
 * Backend: app/api/routers/exchange.py, app/api/schemas/exchange.py, app/api/routers/market.py (sourcing-radar,
 * listings, price), app/api/schemas/market.py.
 * Exchange money is UZS (so‘m). Radar money is USD, converted with each listing's own rate (price_uzs / price_usd).
 */
import { z } from "zod";

const Attrs = z.record(z.string(), z.unknown());
const nullableNum = z.number().nullable();

/* ------------------------------------------------------------------ helpers */

export interface KeyValue {
  label: string;
  value: string;
}

const ATTR_LABELS: Record<string, string> = {
  storage_gb: "Xotira",
  ram_gb: "RAM",
  ssd_gb: "SSD",
  battery_pct: "Batareya",
  cpu: "Protsessor",
  year: "Yil",
  mileage_km: "Yurgan",
  rooms: "Xonalar",
  area_m2: "Maydon",
  floor: "Qavat",
  furnished: "Jihozlangan",
  has_box: "Quti",
  imei_registered: "IMEI ro‘yxatda",
  color: "Rang",
  region_version: "Versiya",
  repaired: "Ta’mirlangan",
};

const ATTR_UNITS: Record<string, string> = { storage_gb: " GB", ram_gb: " GB", ssd_gb: " GB", battery_pct: "%", mileage_km: " km", area_m2: " m²" };

/** Readable attribute rows; internal keys (`_extracted_by`) and empty values are skipped. */
export function attrRows(attrs: Record<string, unknown>): KeyValue[] {
  const rows: KeyValue[] = [];
  for (const [key, raw] of Object.entries(attrs)) {
    if (key.startsWith("_") || raw === null || raw === undefined || raw === "") continue;
    const value = typeof raw === "boolean" ? (raw ? "ha" : "yo‘q") : `${String(raw)}${ATTR_UNITS[key] ?? ""}`;
    rows.push({ label: ATTR_LABELS[key] ?? key.replace(/_/g, " "), value });
  }
  return rows;
}

const CONDITION: Record<string, string> = { new: "yangi", A: "A (a’lo)", B: "B (yaxshi)", C: "C (o‘rtacha)" };
export const conditionLabel = (c: string | null) => (c ? (CONDITION[c] ?? c) : null);

/** "Apple iPhone 13 128GB" from brand, model and the key attribute. */
export function itemTitle(o: { category: string; brand: string | null; model: string; attrs: Record<string, unknown>; district?: string | null }) {
  const a = o.attrs;
  const parts = [o.brand ?? "", o.model];
  if (o.category === "phone" && a.storage_gb) parts.push(`${a.storage_gb}GB`);
  else if (o.category === "laptop" && a.ram_gb && a.ssd_gb) parts.push(`${a.ram_gb}/${a.ssd_gb}`);
  else if (o.category === "car" && a.year) parts.push(String(a.year));
  else if ((o.category === "house" || o.category === "rent") && a.rooms) return [`${a.rooms}-xonali`, o.district ?? ""].filter(Boolean).join(" ");
  return parts.filter(Boolean).join(" ").trim();
}

/** "t.me/channel/123" → "@channel"; seed or missing URLs → null. */
export function channelOf(url: string | null) {
  const m = url?.match(/t\.me\/(?:s\/)?([A-Za-z0-9_]+)/);
  return m ? `@${m[1]}` : null;
}

/* ------------------------------------------------------------------ quotes, RFQs (app/api/schemas/exchange.py) */

export const QuoteRaw = z.object({
  id: z.number(),
  rfq_id: z.number(),
  supplier_id: z.number(),
  unit_price: z.number(),
  qty: z.number(),
  delivery_days: z.number(),
  note: z.string().nullable(),
  status: z.string(),
  counter_unit_price: nullableNum.optional(),
  counter_note: z.string().nullable().optional(),
  created_at: z.string(),
});
export type QuoteRaw = z.infer<typeof QuoteRaw>;

export const RfqRaw = z.object({
  id: z.number(),
  company_id: z.number(),
  company_name: z.string(),
  category: z.string(),
  brand: z.string().nullable(),
  model: z.string(),
  condition: z.string().nullable(),
  attrs: Attrs,
  qty: z.number(),
  target_unit_price: nullableNum,
  district: z.string().nullable(),
  deadline: z.string().nullable(),
  note: z.string().nullable(),
  status: z.string(),
  created_at: z.string(),
  quotes_count: z.number(),
  my_quote_id: nullableNum,
  my_quote: QuoteRaw.nullable().optional(),
});
export type RfqRaw = z.infer<typeof RfqRaw>;

export const page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item), next_cursor: z.string().nullable(), total: z.number() });

export interface MyQuote {
  id: number;
  unit_price: number;
  qty: number;
  delivery_days: number;
  note: string | null;
  status: string;
  counter_unit_price: number | null;
  counter_note: string | null;
}

/** What /market/price needs to price the requested item. */
export interface ItemSpec {
  category: string;
  brand: string | null;
  model: string;
  condition: string | null;
  district: string | null;
  attrs: Record<string, unknown>;
}

export interface RfqItem {
  id: number;
  title: string;
  category: string;
  buyer: string;
  qty: number;
  target_unit_price: number | null;
  status: "open" | "awarded" | "closed" | string;
  created_at: string;
  deadline: string | null;
  district: string | null;
  note: string | null;
  quotes_count: number;
  specs: KeyValue[];
  spec: ItemSpec;
  my_quote: MyQuote | null;
}

export const mapMyQuote = (q: QuoteRaw): MyQuote => ({
  id: q.id,
  unit_price: q.unit_price,
  qty: q.qty,
  delivery_days: q.delivery_days,
  note: q.note,
  status: q.status,
  counter_unit_price: q.counter_unit_price ?? null,
  counter_note: q.counter_note ?? null,
});

export function mapRfq(r: RfqRaw): RfqItem {
  const specs: KeyValue[] = [];
  const cond = conditionLabel(r.condition);
  if (cond) specs.push({ label: "Holati", value: cond });
  specs.push(...attrRows(r.attrs));
  specs.push({ label: "Miqdor", value: `${r.qty} dona` });
  if (r.district) specs.push({ label: "Hudud", value: r.district });
  if (r.note) specs.push({ label: "Izoh", value: r.note });
  return {
    id: r.id,
    title: itemTitle(r),
    category: r.category,
    buyer: r.company_name,
    qty: r.qty,
    target_unit_price: r.target_unit_price,
    status: r.status,
    created_at: r.created_at,
    deadline: r.deadline,
    district: r.district,
    note: r.note,
    quotes_count: r.quotes_count,
    specs,
    spec: { category: r.category, brand: r.brand, model: r.model, condition: r.condition, district: r.district, attrs: r.attrs },
    my_quote: r.my_quote ? mapMyQuote(r.my_quote) : null,
  };
}

export const RankedQuotesRaw = z.object({
  rfq_id: z.number(),
  fair_price_uzs: nullableNum,
  fair_buy_price_uzs: nullableNum,
  quotes: z.array(
    z.object({
      id: z.number(),
      rfq_id: z.number(),
      rank: z.number(),
      supplier: z.object({ id: z.number(), name: z.string(), rating: nullableNum, ratings_count: z.number(), deals_count: z.number() }),
      unit_price_uzs: z.number(),
      qty: z.number(),
      delivery_days: z.number(),
      note: z.string().nullable(),
      status: z.string(),
      counter_unit_price: nullableNum.optional(),
      counter_note: z.string().nullable().optional(),
      score: z.number(),
      score_breakdown: z.object({ price: z.number(), rating: z.number(), delivery: z.number(), quantity: z.number(), penalty: z.number() }),
      vs_fair_purchase_pct: nullableNum,
      reasons: z.array(z.string()),
    }),
  ),
  recommendation: z
    .object({ quote_id: z.number(), supplier_name: z.string(), score: z.number(), saving_vs_worst_uzs: z.number(), text: z.string() })
    .nullable(),
});
export type RankedQuotesRaw = z.infer<typeof RankedQuotesRaw>;

export interface RfqQuote {
  id: number;
  rank: number;
  supplier: string;
  /** "★ 4.67 · 3 ta baho · 3 bitim" from the supplier's reputation. */
  verification: string;
  price: number;
  qty: number;
  total: number;
  delivery_days: number;
  delivery: string;
  note: string | null;
  status: string;
  counter_unit_price: number | null;
  score: number;
  /** vs the market fair purchase price; negative = cheaper. */
  diff_pct: number | null;
  why: string[];
  recommended: boolean;
}

export function mapQuotes(raw: RankedQuotesRaw): RfqQuote[] {
  const best = raw.recommendation?.quote_id ?? null;
  return raw.quotes.map((q) => {
    const s = q.supplier;
    const verification = [s.rating !== null ? `★ ${s.rating} · ${s.ratings_count} ta baho` : "Hali baholanmagan", `${s.deals_count} bitim`].join(" · ");
    return {
      id: q.id,
      rank: q.rank,
      supplier: s.name,
      verification,
      price: q.unit_price_uzs,
      qty: q.qty,
      total: q.unit_price_uzs * q.qty,
      delivery_days: q.delivery_days,
      delivery: q.delivery_days === 0 ? "bugun" : `${q.delivery_days} kunda`,
      note: q.note,
      status: q.status,
      counter_unit_price: q.counter_unit_price ?? null,
      score: q.score,
      diff_pct: q.vs_fair_purchase_pct,
      why: q.reasons,
      recommended: q.id === best,
    };
  });
}

/* ------------------------------------------------------------------ market estimate (POST /market/price) */

export const PriceEstimateRaw = z.object({
  category: z.string(),
  fair_price_uzs: z.number(),
  fair_price_usd: z.number(),
  range_uzs: z.tuple([z.number(), z.number()]),
  fair_buy_price_uzs: z.number(),
  fair_buy_price_usd: z.number(),
  comparables: z.number(),
  basis: z.string(),
  confidence: z.string(),
  samples: z.array(z.object({ listing_id: z.number(), price_uzs: z.number() }).passthrough()),
});

export interface MarketEstimate {
  fair_price: number;
  fair_buy_price: number;
  p25: number;
  p75: number;
  comparables: number;
  basis: string;
  confidence: string;
  /** Prices of the comparable listings the backend returned as samples. */
  dots: number[];
}

export const mapEstimate = (e: z.infer<typeof PriceEstimateRaw>): MarketEstimate => ({
  fair_price: e.fair_price_uzs,
  fair_buy_price: e.fair_buy_price_uzs,
  p25: e.range_uzs[0],
  p75: e.range_uzs[1],
  comparables: e.comparables,
  basis: e.basis,
  confidence: e.confidence,
  dots: e.samples.map((s) => s.price_uzs),
});

/* ------------------------------------------------------------------ deals */

export const DealRaw = z.object({
  id: z.number(),
  buyer_id: z.number(),
  seller_id: z.number(),
  buyer_name: z.string(),
  seller_name: z.string(),
  rfq_id: nullableNum,
  quote_id: nullableNum,
  offer_id: nullableNum,
  category: z.string(),
  brand: z.string().nullable(),
  model: z.string(),
  condition: z.string().nullable(),
  attrs: Attrs,
  qty: z.number(),
  unit_price: z.number(),
  total: z.number(),
  status: z.string(),
  created_at: z.string(),
  my_rating: nullableNum,
});

/** Field names follow the old `Deal` UI type; money is UZS. */
export interface DealView {
  id: string;
  deal_id: number;
  label: string;
  rfq_id: number | null;
  supplier: string;
  buyer: string;
  item: string;
  qty: number;
  unit_price: number;
  total: number;
  date: string;
  my_rating: number | null;
}

export const mapDeal = (d: z.infer<typeof DealRaw>): DealView => ({
  id: `#${d.id}`,
  deal_id: d.id,
  label: "Bitim",
  rfq_id: d.rfq_id,
  supplier: d.seller_name,
  buyer: d.buyer_name,
  item: itemTitle(d),
  qty: d.qty,
  unit_price: d.unit_price,
  total: d.total,
  date: d.created_at,
  my_rating: d.my_rating,
});

/* ------------------------------------------------------------------ offers (lots, matches) */

const SupplierRef = z.object({ id: z.number(), name: z.string(), rating: nullableNum, ratings_count: z.number(), deals_count: z.number() });

export const OfferRaw = z.object({
  id: z.number(),
  company: SupplierRef,
  kind: z.string(),
  category: z.string(),
  brand: z.string().nullable(),
  model: z.string(),
  title: z.string(),
  condition: z.string().nullable(),
  attrs: Attrs,
  qty: z.number(),
  unit_price_uzs: z.number(),
  district: z.string().nullable(),
  commission_split: nullableNum,
  note: z.string().nullable(),
  status: z.string(),
  created_at: z.string(),
  market_fair_price_uzs: nullableNum,
  market_diff_pct: nullableNum,
  market_badge: z.string().nullable(),
  match_reasons: z.array(z.string()).optional(),
});

const OFFER_KIND: Record<string, string> = { wholesale: "Ulgurji", surplus: "Ortiqcha qoldiq", car_trade: "Avto savdo", cobroker: "Hamkorlik (rieltor)" };

export interface Lot {
  id: number;
  title: string;
  seller: string;
  seller_id: number;
  qty: number;
  unit_price: number;
  market: number | null;
  /** Negative = below market. */
  diff_pct: number | null;
  badge: string | null;
  location: string | null;
  kind: string;
  kind_label: string;
  note: string | null;
  reasons: string[];
  buyable: boolean;
}

export const mapOffer = (o: z.infer<typeof OfferRaw>): Lot => ({
  id: o.id,
  title: o.title,
  seller: o.company.name,
  seller_id: o.company.id,
  qty: o.qty,
  unit_price: o.unit_price_uzs,
  market: o.market_fair_price_uzs,
  diff_pct: o.market_diff_pct,
  badge: o.market_badge,
  location: o.district,
  kind: o.kind,
  kind_label: OFFER_KIND[o.kind] ?? o.kind,
  note: o.note,
  reasons: o.match_reasons ?? [],
  buyable: o.kind !== "cobroker" && o.status === "active",
});

/* ------------------------------------------------------------------ demand */

export const DemandRaw = z.object({
  days: z.number(),
  most_requested: z.array(z.object({ category: z.string(), model: z.string(), requests: z.number(), units: z.number() })),
  most_listed: z.array(z.object({ category: z.string(), model: z.string(), listings: z.number(), avg_price_uzs: z.number() })),
  by_district: z.array(z.object({ district: z.string(), category: z.string(), model: z.string(), requests: z.number(), units: z.number() })),
});

export interface DemandView {
  days: number;
  districts: { name: string; count: number; models: string }[];
  models: { name: string; requests: number; units: number }[];
  listed: { name: string; listings: number; avg_price: number }[];
}

export function mapDemand(d: z.infer<typeof DemandRaw>): DemandView {
  const byName = new Map<string, { name: string; count: number; models: string[] }>();
  for (const row of d.by_district) {
    const name = row.district === "—" ? "Hudud ko‘rsatilmagan" : row.district;
    const e = byName.get(name) ?? { name, count: 0, models: [] };
    e.count += row.requests;
    if (!e.models.includes(row.model)) e.models.push(row.model);
    byName.set(name, e);
  }
  return {
    days: d.days,
    districts: [...byName.values()].sort((a, b) => b.count - a.count).map((e) => ({ name: e.name, count: e.count, models: e.models.join(", ") })),
    models: d.most_requested.map((m) => ({ name: m.model, requests: m.requests, units: m.units })),
    listed: d.most_listed.map((m) => ({ name: m.model, listings: m.listings, avg_price: m.avg_price_uzs })),
  };
}

/* ------------------------------------------------------------------ sourcing radar + live feed (ListingOut) */

export const ListingRaw = z.object({
  id: z.number(),
  category: z.string(),
  brand: z.string().nullable(),
  model: z.string(),
  title: z.string(),
  condition: z.string().nullable(),
  price: z.number(),
  currency: z.string(),
  price_uzs: z.number(),
  price_usd: z.number(),
  city: z.string().nullable(),
  district: z.string().nullable(),
  attrs: Attrs,
  seller_type: z.string(),
  posted_at: z.string(),
  source_url: z.string().nullable(),
  origin: z.string(),
  fair_price_uzs: nullableNum.optional(),
  discount_pct: nullableNum.optional(),
  expected_resale_margin_uzs: nullableNum.optional(),
  expected_days_to_sell: nullableNum.optional(),
});
type ListingRaw = z.infer<typeof ListingRaw>;
export const ListingPage = page(ListingRaw);

export type RadarCategory = "phone" | "laptop" | "car" | "realty";
const radarCategory = (c: string): RadarCategory => (c === "house" || c === "rent" ? "realty" : (c as RadarCategory));

/** Field names follow the old `RadarFind` UI type (bugun.tsx reads id, title, price, market, profit, diff_pct). USD. */
export interface RadarFind {
  id: string;
  title: string;
  meta: string;
  category: RadarCategory;
  price: number;
  market: number;
  /** Positive = below the fair price. */
  diff_pct: number;
  profit: number;
  days: number | null;
  channel: string;
  posted_at: string;
  url: string | null;
  is_new: boolean;
}

export interface RadarView {
  items: RadarFind[];
  total: number;
  avg_discount: number;
  expected_profit: number;
  channels: number;
  categories: number;
  min_discount: number;
  days: number;
}

/** UZS → USD with the rate the backend used for this listing. */
const toUsd = (l: ListingRaw, uzs: number) => (l.price_usd > 0 ? (uzs * l.price_usd) / l.price_uzs : 0);

function listingMeta(l: ListingRaw) {
  const parts = [conditionLabel(l.condition), l.district ?? l.city, l.attrs.battery_pct ? `batareya ${l.attrs.battery_pct}%` : null];
  return parts.filter(Boolean).join(" · ");
}

const NEW_HOURS = 6;

export function mapRadar(p: z.infer<typeof ListingPage>, opts: { min_discount: number; days: number; now?: number }): RadarView {
  const now = opts.now ?? Date.now();
  const items: RadarFind[] = p.items.map((l) => {
    const fair = l.fair_price_uzs ?? l.price_uzs;
    return {
      id: String(l.id),
      title: l.title || itemTitle(l),
      meta: listingMeta(l),
      category: radarCategory(l.category),
      price: l.price_usd,
      market: toUsd(l, fair),
      diff_pct: l.discount_pct ?? 0,
      profit: toUsd(l, l.expected_resale_margin_uzs ?? 0),
      days: l.expected_days_to_sell ?? null,
      channel: channelOf(l.source_url) ?? (l.origin === "telegram" ? "Telegram" : l.origin),
      posted_at: l.posted_at,
      url: l.source_url?.startsWith("http") ? l.source_url : null,
      is_new: now - Date.parse(l.posted_at) < NEW_HOURS * 3_600_000,
    };
  });
  const n = items.length;
  return {
    items: [...items].sort((a, b) => b.profit - a.profit),
    total: p.total,
    avg_discount: n ? items.reduce((s, f) => s + f.diff_pct, 0) / n : 0,
    expected_profit: items.reduce((s, f) => s + Math.max(0, f.profit), 0),
    channels: new Set(items.map((f) => f.channel)).size,
    categories: new Set(items.map((f) => f.category)).size,
    min_discount: opts.min_discount,
    days: opts.days,
  };
}

export interface FeedPost {
  id: number;
  channel: string;
  posted_at: string;
  title: string;
  extractor: string | null;
  fields: KeyValue[];
  price: number;
  /** USD fair price, null when the market has too few comparables. */
  market: number | null;
  /** Positive = below the fair price. */
  diff_pct: number | null;
  url: string | null;
}

export function mapFeedPost(l: ListingRaw): FeedPost {
  const fields: KeyValue[] = [{ label: "Mahsulot", value: l.title || itemTitle(l) }];
  const cond = conditionLabel(l.condition);
  if (cond) fields.push({ label: "Holati", value: cond });
  fields.push(...attrRows(l.attrs));
  if (l.district || l.city) fields.push({ label: "Joy", value: (l.district ?? l.city) as string });
  fields.push({ label: "Narx", value: `${l.price} ${l.currency}` });
  const extractor = typeof l.attrs._extracted_by === "string" ? l.attrs._extracted_by : null;
  return {
    id: l.id,
    channel: channelOf(l.source_url) ?? "Telegram",
    posted_at: l.posted_at,
    title: l.title || itemTitle(l),
    extractor,
    fields,
    price: l.price_usd,
    market: l.fair_price_uzs ? toUsd(l, l.fair_price_uzs) : null,
    diff_pct: l.discount_pct ?? null,
    url: l.source_url?.startsWith("http") ? l.source_url : null,
  };
}
