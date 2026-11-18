/**
 * "Today" section: zod schemas of the REAL backend responses (/dashboard, /decisions, /activity, /stores, /users,
 * /meta, /model, /search, /integrations) and maps to what the screens render.
 */
import { z } from "zod";
import { dateShort, shortSoum } from "../../format";

const page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item), next_cursor: z.string().nullable(), total: z.number() });

/* ------------------------------------------------------------------ decisions */

export const BDecision = z.object({
  id: z.number(),
  type: z.string(),
  title: z.string(),
  message: z.string(),
  amount_uzs: z.number(),
  status: z.enum(["pending", "approved", "ignored", "expired"]),
  reasons: z.array(z.string()),
  transaction_ids: z.array(z.number()),
  inventory_ids: z.array(z.number()),
  action: z.object({ kind: z.string(), endpoint: z.string().nullable().optional(), method: z.string().nullable().optional(), body: z.record(z.unknown()) }),
  created_at: z.string(),
  resolved_at: z.string().nullable(),
});
export const BDecisionPage = page(BDecision);
export const BDecisionResult = z.object({ decision_id: z.number(), type: z.string(), status: z.string(), result: z.record(z.unknown()) });

const ACTION_LABELS: Record<string, string> = {
  reprice: "Narxlarni tushirish",
  list_on_exchange: "Birjaga chiqarish",
  delete_transactions: "Dublikatlarni o‘chirish",
  correct_total: "Summani tuzatish",
  supplier_alert: "Yetkazib beruvchini ogohlantirish",
  watch: "Kuzatuvga olish",
  acknowledge: "Tushunarli",
  open_quote_form: "Taklif berish",
};

export interface DecisionCard {
  id: string;
  type: string;
  title: string;
  message: string;
  amount: string;
  reasons: string[];
  evidence: { label: string; value: string }[];
  action_label: string;
}

export function toDecision(d: z.output<typeof BDecision>): DecisionCard {
  const evidence = [{ label: "Summa", value: shortSoum(d.amount_uzs) }];
  if (d.inventory_ids.length) evidence.push({ label: "Mahsulotlar", value: `${d.inventory_ids.length} ta` });
  if (d.transaction_ids.length) evidence.push({ label: "Tranzaksiyalar", value: `${d.transaction_ids.length} ta` });
  return {
    id: String(d.id),
    type: d.type,
    title: d.title,
    message: d.message,
    amount: shortSoum(d.amount_uzs),
    reasons: [...new Set(d.reasons)],
    evidence,
    action_label: ACTION_LABELS[d.action.kind] ?? "Tasdiqlash",
  };
}

/* ------------------------------------------------------------------ dashboard */

const CashflowMonth = z.object({ month: z.string(), income_uzs: z.number(), expense_uzs: z.number(), net_uzs: z.number(), partial: z.boolean() });

export const BDashboard = z.object({
  today: z.string(),
  fx_usd_uzs: z.number(),
  insight: z.string(),
  sales: z.object({
    today_uzs: z.number(),
    yesterday_uzs: z.number(),
    delta_uzs: z.number(),
    delta_pct: z.number().nullable(),
    avg_daily_uzs: z.number(),
    days: z.array(z.object({ date: z.string(), total_uzs: z.number() })),
  }),
  cashflow: z.array(CashflowMonth),
  avg_net_uzs: z.number(),
  budget: z.object({ month: z.string(), planned_total_uzs: z.number(), fact_total_uzs: z.number(), used_pct: z.number().nullable(), warning: z.string().nullable() }),
  credit: z.object({ score: z.number(), grade: z.string() }),
  stock: z
    .object({ units_total: z.number(), units_overpriced: z.number(), units_underpriced: z.number(), units_no_data: z.number() })
    .passthrough()
    .nullable(),
  price_index: z
    .object({
      category: z.string(),
      model: z.string(),
      points: z.array(z.object({ week_start: z.string(), median_usd: z.number(), p25_usd: z.number(), p75_usd: z.number(), listings: z.number() })),
      change_pct: z.number().nullable(),
    })
    .nullable(),
  rfq_quotes: z
    .object({
      rfq_id: z.number(),
      title: z.string(),
      qty: z.number(),
      quotes: z.array(z.object({ quote_id: z.number(), supplier_name: z.string(), unit_price_uzs: z.number(), delivery_days: z.number(), best: z.boolean() })),
    })
    .nullable(),
});

export interface TodayDashboard {
  today: string;
  insight: string;
  /** Sales figures in USD (converted with the backend's USD/UZS rate, so they match the USD sales chart). */
  sales_today: number;
  sales_delta: number;
  sales_delta_pct: number | null;
  avg_daily: number;
  strip30: { date: string; value: number }[];
  strip90: { date: string; value: number }[];
  stock_health: { under: number; fair: number; over: number; no_data: number; total: number };
  /** Millions of so‘m. */
  cash: { month: string; income: number; spend: number; net: number; partial: boolean }[];
  avg_net: number;
  budget: { month: string; spent: number; limit: number; used_pct: number | null; warning: string | null };
  credit: { score: number; grade: string };
  index: { subtitle: string; price: number; change_pct: number | null; from: string; series: { median: number; p25: number; p75: number }[] } | null;
  rfq: { id: number; subtitle: string; quotes: { name: string; price: number; best: boolean }[] } | null;
}

const MLN = 1_000_000;
const round1 = (v: number) => Math.round(v * 10) / 10;

export function toDashboard(d: z.output<typeof BDashboard>): TodayDashboard {
  const usd = (uzs: number) => uzs / d.fx_usd_uzs;
  const strip = d.sales.days.map((x) => ({ date: x.date, value: usd(x.total_uzs) }));
  const s = d.stock;
  const fair = s ? Math.max(0, s.units_total - s.units_overpriced - s.units_underpriced - s.units_no_data) : 0;
  const ix = d.price_index;
  const last = ix?.points[ix.points.length - 1];
  return {
    today: d.today,
    insight: d.insight,
    sales_today: usd(d.sales.today_uzs),
    sales_delta: usd(d.sales.delta_uzs),
    sales_delta_pct: d.sales.delta_pct,
    avg_daily: usd(d.sales.avg_daily_uzs),
    strip30: strip.slice(-30),
    strip90: strip,
    stock_health: { under: s?.units_underpriced ?? 0, fair, over: s?.units_overpriced ?? 0, no_data: s?.units_no_data ?? 0, total: s?.units_total ?? 0 },
    cash: d.cashflow.map((m) => ({ month: m.month, income: round1(m.income_uzs / MLN), spend: round1(m.expense_uzs / MLN), net: round1(m.net_uzs / MLN), partial: m.partial })),
    avg_net: round1(d.avg_net_uzs / MLN),
    budget: { month: d.budget.month, spent: round1(d.budget.fact_total_uzs / MLN), limit: round1(d.budget.planned_total_uzs / MLN), used_pct: d.budget.used_pct, warning: d.budget.warning },
    credit: d.credit,
    index:
      ix && last
        ? {
            subtitle: `${ix.model} · ${dateShort(ix.points[0].week_start)} – ${dateShort(last.week_start)}`,
            price: last.median_usd,
            change_pct: ix.change_pct,
            from: ix.points[0].week_start,
            series: ix.points.map((p) => ({ median: p.median_usd, p25: p.p25_usd, p75: p.p75_usd })),
          }
        : null,
    rfq: d.rfq_quotes
      ? {
          id: d.rfq_quotes.rfq_id,
          subtitle: `${d.rfq_quotes.title} · ${d.rfq_quotes.qty} dona`,
          quotes: d.rfq_quotes.quotes.map((q) => ({ name: q.supplier_name, price: q.unit_price_uzs, best: q.best })),
        }
      : null,
  };
}

/* ------------------------------------------------------------------ activity */

export const BActivity = z.object({
  id: z.number(),
  user_id: z.number().nullable(),
  user_name: z.string().nullable().optional(),
  action: z.string(),
  entity: z.string(),
  entity_id: z.number().nullable(),
  summary: z.string(),
  created_at: z.string(),
});
export const BActivityPage = page(BActivity);

export interface ActivityItem {
  id: number;
  /** HH:MM when it happened today (local time), otherwise the short date. */
  time: string;
  text: string;
  actor: string;
}

export function toActivity(r: z.output<typeof BActivity>): ActivityItem {
  const at = new Date(r.created_at);
  const now = new Date();
  const sameDay = at.toDateString() === now.toDateString();
  const time = sameDay ? `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}` : dateShort(r.created_at);
  return { id: r.id, time, text: r.summary, actor: r.user_name === "owner" || !r.user_name ? "ega" : r.user_name };
}

/* ------------------------------------------------------------------ stores, users, meta */

export const BStore = z.object({
  id: z.number(),
  name: z.string(),
  district: z.string().nullable(),
  area_m2: z.number().nullable(),
  active: z.boolean(),
  units_in_stock: z.number().nullable().optional(),
});
export const BStorePage = page(BStore);
export type StoreRow = z.output<typeof BStore>;

export const BUser = z.object({ id: z.number(), name: z.string(), role: z.string(), created_at: z.string() });
export const BUserPage = page(BUser);
export const BUserCreated = z.object({ api_key: z.string(), user: BUser });
export type UserRow = z.output<typeof BUser>;

const LabelSet = z.object({ uz: z.string(), ru: z.string(), en: z.string() }).passthrough();
/** Only the parts of /meta the settings screen uses (the rest passes through unchecked). */
export const BMeta = z.object({ user_roles: z.array(z.object({ code: z.string(), label: LabelSet })) }).passthrough();
export type MetaInfo = z.output<typeof BMeta>;

/* ------------------------------------------------------------------ model card */

export const BModel = z.object({
  model: z.string(),
  provider: z.string(),
  provider_order: z.array(z.string()),
  local_reachable: z.boolean(),
  local_detail: z.string().nullable(),
  window_hours: z.number(),
  listings: z.number(),
  share: z.record(z.number()),
  counts: z.record(z.number()),
});
export type ModelInfo = z.output<typeof BModel>;

/* ------------------------------------------------------------------ search */

export const BSearch = z.object({
  q: z.string(),
  items: z.array(z.object({ kind: z.enum(["stock", "transaction", "counterparty", "decision"]), id: z.number().nullable(), title: z.string(), subtitle: z.string() })),
});

const SEARCH_GROUPS = {
  stock: { group: "Ombor", href: "/narxlar?tab=ombor" },
  transaction: { group: "Tranzaksiyalar", href: "/kitoblar" },
  counterparty: { group: "Kontragentlar", href: "/kitoblar" },
  decision: { group: "Qarorlar", href: "/bugun" },
} as const;

export interface SearchRow {
  group: string;
  title: string;
  meta: string;
  href: string;
}

export const toSearch = (d: z.output<typeof BSearch>): { items: SearchRow[] } => ({
  items: d.items.map((h) => ({ group: SEARCH_GROUPS[h.kind].group, title: h.title, meta: h.subtitle, href: SEARCH_GROUPS[h.kind].href })),
});

/* ------------------------------------------------------------------ integrations */

export const BIntegration = z.object({
  kind: z.string(),
  label: z.string(),
  status: z.enum(["connected", "not_connected", "error"]),
  mode: z.enum(["live", "mock"]),
  last_sync_at: z.string().nullable(),
  details: z.record(z.unknown()),
  note: z.string(),
});
export const BIntegrations = z.array(BIntegration);
export type IntegrationRow = z.output<typeof BIntegration>;

export const BSyncResult = z.object({
  kind: z.string(),
  mode: z.enum(["live", "mock"]),
  created: z.number(),
  errors: z.array(z.record(z.unknown())),
  audit_flags: z.array(z.record(z.unknown())),
  transaction_ids: z.array(z.number()),
});
