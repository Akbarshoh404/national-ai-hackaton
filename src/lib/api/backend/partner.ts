/**
 * Partner section (bank console + bazaar-admin market report): zod schemas of the REAL backend responses
 * (backend/app/api/schemas/lender.py, auth.py) and maps to what the partner screens render.
 */
import { z } from "zod";

const page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item), next_cursor: z.string().nullable(), total: z.number() });

// --- company (title / subtitle of the console) -------------------------------------------------

export const BCompany = z.object({
  id: z.number(),
  name: z.string(),
  stir: z.string().nullable(),
  role: z.string(),
  city: z.string().nullable(),
  district: z.string().nullable(),
});
export type PartnerCompany = z.infer<typeof BCompany>;

// --- loan applications ------------------------------------------------------------------------

const AppStatus = z.enum(["submitted", "reviewing", "approved", "rejected"]);
export type AppStatus = z.infer<typeof AppStatus>;

export const BApplication = z.object({
  id: z.number(),
  company_id: z.number(),
  company_name: z.string(),
  lender_id: z.number(),
  product: z.string(),
  product_label: z.string(),
  principal_uzs: z.number(),
  months: z.number(),
  purpose: z.string(),
  status: AppStatus,
  decision_note: z.string().nullable(),
  readiness_score: z.number().nullable(),
  consent_at: z.string(),
  created_at: z.string(),
});
export const BApplications = page(BApplication);

const BSnapshot = z.object({
  company: z.object({ name: z.string(), stir: z.string().nullable() }),
  loan_readiness: z.object({ score: z.number(), grade: z.string() }),
  audit_summary: z.object({ issues: z.number(), by_severity: z.record(z.number()) }),
  credit: z.object({
    monthly_payment_uzs: z.number(),
    avg_monthly_net_uzs: z.number(),
    debt_service_ratio_pct: z.number().nullable(),
    max_debt_service_ratio_pct: z.number(),
    verdict: z.string(),
  }),
  collateral: z.array(z.object({ inventory_id: z.number(), model: z.string().nullable(), qty: z.number() })),
  collateral_market_value_uzs: z.number(),
  generated_at: z.string(),
});
export const BApplicationDetail = BApplication.extend({ snapshot: BSnapshot });

export interface PartnerApplication {
  id: number;
  borrower: string;
  product: string;
  amount: number;
  months: number;
  purpose: string;
  readiness: number | null;
  status: AppStatus;
  note: string | null;
  createdAt: string;
}

export interface PartnerApplicationDetail extends PartnerApplication {
  stir: string | null;
  grade: string;
  monthlyPayment: number;
  avgProfit: number;
  paymentRatio: number | null;
  maxPaymentRatio: number;
  verdict: string;
  collateralValue: number;
  collateralUnits: number;
  auditIssues: number;
  auditHigh: number;
  snapshotAt: string;
}

export const mapApplication = (a: z.output<typeof BApplication>): PartnerApplication => ({
  id: a.id,
  borrower: a.company_name,
  product: a.product_label,
  amount: a.principal_uzs,
  months: a.months,
  purpose: a.purpose,
  readiness: a.readiness_score,
  status: a.status,
  note: a.decision_note,
  createdAt: a.created_at,
});

export const mapApplications = (d: z.output<typeof BApplications>) => ({ items: d.items.map(mapApplication), total: d.total });

export const mapApplicationDetail = (a: z.output<typeof BApplicationDetail>): PartnerApplicationDetail => {
  const s = a.snapshot;
  return {
    ...mapApplication(a),
    stir: s.company.stir,
    grade: s.loan_readiness.grade,
    monthlyPayment: s.credit.monthly_payment_uzs,
    avgProfit: s.credit.avg_monthly_net_uzs,
    paymentRatio: s.credit.debt_service_ratio_pct,
    maxPaymentRatio: s.credit.max_debt_service_ratio_pct,
    verdict: s.credit.verdict,
    collateralValue: s.collateral_market_value_uzs,
    collateralUnits: s.collateral.reduce((n, c) => n + c.qty, 0),
    auditIssues: s.audit_summary.issues,
    auditHigh: s.audit_summary.by_severity.high ?? 0,
    snapshotAt: s.generated_at,
  };
};

// --- collateral -------------------------------------------------------------------------------

const CollateralStatus = z.enum(["ok", "watch", "breach", "no_data"]);
export type CollateralStatus = z.infer<typeof CollateralStatus>;

export const BCollateral = z.object({
  id: z.number(),
  loan_application_id: z.number().nullable(),
  borrower_name: z.string(),
  category: z.string(),
  brand: z.string().nullable(),
  model: z.string().nullable(),
  condition: z.string().nullable(),
  district: z.string().nullable(),
  attrs: z.record(z.unknown()),
  qty: z.number(),
  loan_balance_uzs: z.number(),
  ltv_limit: z.number(),
  market_value_uzs: z.number().nullable(),
  liquidation_value_uzs: z.number().nullable(),
  ltv: z.number().nullable(),
  status: CollateralStatus,
  value_change_30d_pct: z.number().nullable(),
  basis: z.string().nullable(),
  confidence: z.string().nullable(),
  comparables: z.number(),
  created_at: z.string(),
});
export const BCollaterals = page(BCollateral);

export interface PartnerCollateral {
  id: number;
  object: string;
  detail: string;
  borrower: string;
  value: number | null;
  change30d: number | null;
  /** Percent, e.g. 51.1 */
  ltv: number | null;
  ltvLimit: number;
  status: CollateralStatus;
}

/** "Chevrolet Cobalt", "2021 · 50 000 km · ×2" — built from the item's own fields. */
export function itemTitle(i: { category: string; brand: string | null; model: string | null; district?: string | null; attrs: Record<string, unknown> }) {
  const name = [i.brand, i.model].filter(Boolean).join(" ");
  if (name) return name;
  const rooms = typeof i.attrs.rooms === "number" ? `${i.attrs.rooms} xonali` : null;
  return [rooms, i.district].filter(Boolean).join(", ") || i.category;
}

function attrBits(attrs: Record<string, unknown>) {
  const bits: string[] = [];
  if (typeof attrs.year === "number") bits.push(String(attrs.year));
  if (typeof attrs.mileage_km === "number") bits.push(`${attrs.mileage_km.toLocaleString("ru-RU")} km`);
  if (typeof attrs.storage_gb === "number") bits.push(`${attrs.storage_gb} GB`);
  if (typeof attrs.area_m2 === "number") bits.push(`${attrs.area_m2} m²`);
  return bits;
}

export const mapCollateral = (c: z.output<typeof BCollateral>): PartnerCollateral => ({
  id: c.id,
  object: itemTitle(c),
  detail: [...attrBits(c.attrs), c.qty > 1 ? `×${c.qty}` : null].filter(Boolean).join(" · "),
  borrower: c.borrower_name,
  value: c.market_value_uzs,
  change30d: c.value_change_30d_pct,
  ltv: c.ltv === null ? null : Math.round(c.ltv * 1000) / 10,
  ltvLimit: Math.round(c.ltv_limit * 100),
  status: c.status,
});

export const mapCollaterals = (d: z.output<typeof BCollaterals>) => ({ items: d.items.map(mapCollateral), total: d.total });

export const BCollateralSummary = z.object({
  items: z.number(),
  total_loan_balance_uzs: z.number(),
  total_market_value_uzs: z.number(),
  total_liquidation_value_uzs: z.number(),
  portfolio_ltv: z.number().nullable(),
  by_status: z.record(z.number()),
  by_category: z.record(z.number()),
  valuations_this_month: z.number(),
});

export interface PartnerCollateralSummary {
  objects: number;
  marketValue: number;
  liquidationValue: number;
  loanBalance: number;
  /** Percent */
  portfolioLtv: number | null;
  watch: number;
  breach: number;
  noData: number;
  valuationsThisMonth: number;
}

export const mapCollateralSummary = (s: z.output<typeof BCollateralSummary>): PartnerCollateralSummary => ({
  objects: s.items,
  marketValue: s.total_market_value_uzs,
  liquidationValue: s.total_liquidation_value_uzs,
  loanBalance: s.total_loan_balance_uzs,
  portfolioLtv: s.portfolio_ltv === null ? null : Math.round(s.portfolio_ltv * 1000) / 10,
  watch: s.by_status.watch ?? 0,
  breach: s.by_status.breach ?? 0,
  noData: s.by_status.no_data ?? 0,
  valuationsThisMonth: s.valuations_this_month,
});

// --- valuation --------------------------------------------------------------------------------

export type ValuationInput = { text: string } | { url: string } | { inventory_id: number };

const BSample = z.object({
  listing_id: z.number(),
  title: z.string(),
  price_uzs: z.number(),
  price_usd: z.number().nullable(),
  condition: z.string().nullable(),
  district: z.string().nullable(),
  seller_type: z.string().nullable(),
  posted_at: z.string(),
  source_url: z.string().nullable(),
  attrs: z.record(z.unknown()),
});

export const BValuation = z.object({
  category: z.string(),
  qty: z.number(),
  fair_price_uzs: z.number(),
  fair_price_usd: z.number(),
  range_uzs: z.array(z.number()).length(2),
  liquidation_value_uzs: z.number(),
  haircut_pct: z.number(),
  total_market_value_uzs: z.number(),
  total_liquidation_value_uzs: z.number(),
  confidence: z.string(),
  comparables: z.number(),
  basis: z.string(),
  samples: z.array(BSample),
  source: z.record(z.unknown()),
  item: z.object({
    category: z.string(),
    brand: z.string().nullable(),
    model: z.string().nullable(),
    condition: z.string().nullable(),
    district: z.string().nullable(),
    attrs: z.record(z.unknown()),
  }),
  value_change_30d_pct: z.number().nullable(),
  valuations_this_month: z.number(),
});

export interface PartnerValuation {
  title: string;
  subtitle: string;
  qty: number;
  fair: number;
  p25: number;
  p75: number;
  liquidation: number;
  haircutPct: number;
  totalMarket: number;
  totalLiquidation: number;
  listings: number;
  confidence: string;
  change30d: number | null;
  valuationsThisMonth: number;
  comparables: { id: number; title: string; meta: string; price: number }[];
}

export const mapValuation = (v: z.output<typeof BValuation>): PartnerValuation => ({
  title: [itemTitle(v.item), ...attrBits(v.item.attrs)].join(" · "),
  subtitle: v.basis,
  qty: v.qty,
  fair: v.fair_price_uzs,
  p25: v.range_uzs[0],
  p75: v.range_uzs[1],
  liquidation: v.liquidation_value_uzs,
  haircutPct: v.haircut_pct,
  totalMarket: v.total_market_value_uzs,
  totalLiquidation: v.total_liquidation_value_uzs,
  listings: v.comparables,
  confidence: v.confidence,
  change30d: v.value_change_30d_pct,
  valuationsThisMonth: v.valuations_this_month,
  comparables: v.samples.map((s) => ({
    id: s.listing_id,
    title: [s.title, ...attrBits(s.attrs)].join(" · "),
    meta: [s.district, s.condition, s.posted_at.slice(0, 10)].filter(Boolean).join(" · "),
    price: s.price_uzs,
  })),
});

// --- market report ----------------------------------------------------------------------------

export const REPORT_CATEGORIES = ["phone", "laptop", "car", "house", "rent"] as const;
export type ReportCategory = (typeof REPORT_CATEGORIES)[number];

export const BMarketReport = z.object({
  category: z.string(),
  district: z.string().nullable(),
  days: z.number(),
  total_listings: z.number(),
  by_model_district: z.array(z.object({ model: z.string(), district: z.string(), listings: z.number(), median_price_uzs: z.number() })),
  weekly_trend: z.array(z.object({ week_start: z.string(), median_price_uzs: z.number(), median_price_usd: z.number().nullable(), listings: z.number() })),
  by_seller_type: z.record(z.number()),
});

export interface PartnerMarketReport {
  category: string;
  days: number;
  total: number;
  rows: { model: string; district: string; median: number; listings: number }[];
  trend: { week: string; median: number; listings: number }[];
  /** Last week's median vs the week before, percent (null with fewer than two weeks). */
  weekChange: number | null;
  sellers: { type: string; listings: number }[];
}

export const mapMarketReport = (r: z.output<typeof BMarketReport>): PartnerMarketReport => {
  const t = r.weekly_trend;
  const last = t.at(-1);
  const prev = t.at(-2);
  return {
    category: r.category,
    days: r.days,
    total: r.total_listings,
    rows: r.by_model_district.map((x) => ({ model: x.model, district: x.district, median: x.median_price_uzs, listings: x.listings })),
    trend: t.map((p) => ({ week: p.week_start, median: p.median_price_uzs, listings: p.listings })),
    weekChange: last && prev && prev.median_price_uzs ? Math.round((last.median_price_uzs / prev.median_price_uzs - 1) * 1000) / 10 : null,
    sellers: Object.entries(r.by_seller_type).map(([type, listings]) => ({ type, listings })),
  };
};
