/**
 * "Books" section (Kitoblar): zod schemas of the REAL backend responses (/books/audit, /books/transactions,
 * /books/budget, /books/summary, /books/upload*, /books/invoice, /integrations/didox/sync) and maps to what the
 * screens render. Every number comes from the backend; this file only formats.
 */
import { z } from "zod";
import { dateShort, num, pct, soum } from "../../format";

const page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item), next_cursor: z.string().nullable(), total: z.number() });

/* --------------------------------------------------------------- transactions */

export const BTransaction = z.object({
  id: z.number(),
  date: z.string(),
  type: z.string(),
  category: z.string(),
  item_category: z.string().nullable(),
  brand: z.string().nullable(),
  model: z.string().nullable(),
  condition: z.string().nullable(),
  qty: z.number(),
  unit_price: z.number().nullable(),
  total: z.number(),
  counterparty: z.string().nullable(),
  note: z.string().nullable(),
  origin: z.string(),
  deal_id: z.number().nullable(),
  store_id: z.number().nullable().optional(),
  created_at: z.string(),
  category_label: z.string().nullable().optional(),
});
type BTransaction = z.infer<typeof BTransaction>;
export const BTransactionPage = page(BTransaction);

const ORIGIN: Record<string, string> = {
  seed: "Kitob",
  manual: "Qo‘lda",
  upload: "Import",
  exchange: "Birja",
  invoice_ocr: "Faktura rasmi",
};
export const originLabel = (origin: string) => ORIGIN[origin] ?? origin;

export type TxKind = "sale" | "purchase" | "expense" | "deal";

export interface TxView {
  id: number;
  date: string;
  title: string;
  counterparty: string;
  amount: string;
  total: number;
  kind: TxKind;
  source: string;
}

function txTitle(t: BTransaction) {
  const item = [t.brand && !t.model?.startsWith(t.brand) ? t.brand : null, t.model].filter(Boolean).join(" ");
  const cat = t.category_label ?? t.category;
  return item ? `${item}${t.qty !== 1 ? ` × ${num(t.qty)}` : ""}` : t.note ? `${cat} · ${t.note}` : cat;
}

export function mapTransaction(t: BTransaction): TxView {
  const kind: TxKind = t.origin === "exchange" || t.deal_id ? "deal" : t.type === "income" ? "sale" : t.category === "stock_purchase" ? "purchase" : "expense";
  return {
    id: t.id,
    date: t.date,
    title: txTitle(t),
    counterparty: t.counterparty ?? "—",
    amount: `${t.type === "income" ? "+" : ""}${soum(t.total)}`,
    total: t.total,
    kind,
    source: originLabel(t.origin),
  };
}

export const mapTransactionPage = (p: z.infer<typeof BTransactionPage>) => ({ items: p.items.map(mapTransaction), total: p.total, next_cursor: p.next_cursor });
export type TxPageView = ReturnType<typeof mapTransactionPage>;

/* ----------------------------------------------------------------------- audit */

const FlagType = z.enum(["duplicate", "qty_mismatch", "extra_zero", "price_spread", "cost_spike", "overpayment", "no_counterparty"]);
type FlagType = z.infer<typeof FlagType>;
const FixKind = z.enum(["delete_duplicates", "correct_total"]);

export const BAuditFlag = z.object({
  id: z.string(),
  type: FlagType,
  severity: z.enum(["high", "medium", "low"]),
  title: z.string(),
  message: z.string(),
  transaction_ids: z.array(z.number()),
  amount_at_risk_uzs: z.number(),
  fair_buy_price_uzs: z.number().nullable().optional(),
  details: z.record(z.string(), z.union([z.number(), z.string()])),
  fix: FixKind.nullable(),
  counterparty: z.string().nullable(),
  transactions: z.array(BTransaction),
  supplier_history: z.array(z.object({ transaction_id: z.number(), date: z.string(), total_uzs: z.number(), at_risk_uzs: z.number() })),
});
type BAuditFlag = z.infer<typeof BAuditFlag>;

export const BAudit = z.object({
  summary: z.object({
    issues: z.number(),
    by_type: z.record(z.string(), z.number()),
    by_severity: z.record(z.string(), z.number()),
    amount_at_risk_uzs: z.number(),
  }),
  flags: z.array(BAuditFlag),
  recommendations: z.array(z.string()),
  recommendations_source: z.enum(["llm", "rules"]),
  total_records: z.number(),
  ok_records: z.number(),
  checked: z.number(),
});

export interface CalcRow {
  label: string;
  value: string;
  bad: boolean;
}

export interface HistoryBar {
  id: string;
  date: string;
  /** Money at risk in this entry, mln so‘m. */
  over: number;
  current: boolean;
}

export interface AuditFlagView {
  id: string;
  type: FlagType;
  severity: "high" | "medium" | "low";
  title: string;
  subtitle: string;
  amount: string;
  heading: string;
  calc: CalcRow[];
  fix: z.infer<typeof FixKind> | null;
  fixNote: string;
  counterparty: string | null;
  transactionIds: number[];
  transactions: TxView[];
  /** Origin of the flagged records (“Kitob”, “Import”, “Birja” …). */
  sourceLabel: string;
  history: HistoryBar[];
}

export interface AuditView {
  flags: AuditFlagView[];
  totalRecords: number;
  okRecords: number;
  checked: number;
  atRisk: number;
  recommendations: string[];
}

const n = (d: BAuditFlag["details"], key: string) => (typeof d[key] === "number" ? (d[key] as number) : 0);
const row = (label: string, value: string, bad = false): CalcRow => ({ label, value, bad });

function calcRows(f: BAuditFlag): CalcRow[] {
  const d = f.details;
  const risk = soum(f.amount_at_risk_uzs);
  switch (f.type) {
    case "duplicate":
      return [row("Yozuv summasi", soum(n(d, "total"))), row("Necha marta kiritilgan", `${num(n(d, "count"))} marta`, true), row("Ortiqcha nusxalar summasi", risk, true)];
    case "qty_mismatch":
      return [
        row("Miqdor", num(n(d, "qty"))),
        row("Birlik narxi", soum(n(d, "unit_price"))),
        row("Miqdor × narx", soum(n(d, "expected"))),
        row("Yozilgan jami", soum(n(d, "total")), true),
        row("Farq", risk, true),
      ];
    case "extra_zero":
      return [row("Yozilgan summa", soum(n(d, "total")), true), row("Odatdagi summa (mediana)", soum(n(d, "median"))), row("Bir nolsiz summa", soum(n(d, "fixed"))), row("Ortiqcha", risk, true)];
    case "price_spread":
      return [row("Eng past narx", soum(n(d, "min_unit"))), row("Eng yuqori narx", soum(n(d, "max_unit")), true), row("Farq", pct(n(d, "pct"), 0), true), row("Ortiqcha to‘langan", risk, true)];
    case "cost_spike":
      return [row("Oy", String(d.month ?? "")), row("Shu oy", soum(n(d, "current")), true), row("Oldingi oylar o‘rtachasi", soum(n(d, "average"))), row("O‘sish", pct(n(d, "pct"), 0), true)];
    case "overpayment":
      return [row("To‘langan narx", soum(n(d, "unit")), true), row("Bozor xarid narxi", soum(n(d, "fair_buy"))), row("Miqdor", num(n(d, "qty"))), row("Ortiqcha to‘lov", risk, true)];
    case "no_counterparty":
      return [row("Summa", soum(n(d, "total"))), row("Kontragent", "ko‘rsatilmagan", true)];
  }
}

function fixNote(f: BAuditFlag) {
  if (f.fix === "delete_duplicates") return "Tuzatish ortiqcha nusxalarni o‘chiradi, birinchi yozuv qoladi. Birja bitimlari yozuvlari o‘chirilmaydi.";
  if (f.fix === "correct_total") return `Tuzatish jami summani ${soum(f.type === "qty_mismatch" ? n(f.details, "expected") : n(f.details, "fixed"))} ga o‘zgartiradi.`;
  if (f.transactions.some((t) => t.origin === "exchange" || t.deal_id)) return "Bu yozuvlar birja bitimlaridan kelgan va avtomatik o‘zgartirilmaydi. Tekshirib, “Tekshirildi” deb belgilang.";
  return "Avtomatik tuzatish yo‘q. Yozuvni tekshirib, “Tekshirildi” deb belgilang.";
}

function mapFlag(f: BAuditFlag): AuditFlagView {
  const first = f.transactions[0];
  const origins = [...new Set(f.transactions.map((t) => originLabel(t.origin)))];
  const flagged = new Set(f.transaction_ids);
  return {
    id: f.id,
    type: f.type,
    severity: f.severity,
    title: f.title,
    subtitle: [f.counterparty, first ? dateShort(first.date) : null].filter(Boolean).join(" · ") || "—",
    amount: f.amount_at_risk_uzs > 0 ? soum(f.amount_at_risk_uzs) : "—",
    heading: f.message,
    calc: calcRows(f),
    fix: f.fix,
    fixNote: fixNote(f),
    counterparty: f.counterparty,
    transactionIds: f.transaction_ids,
    transactions: f.transactions.map(mapTransaction),
    sourceLabel: origins.join(", "),
    history: f.supplier_history.map((h) => ({ id: `#${h.transaction_id}`, date: dateShort(h.date), over: h.at_risk_uzs / 1e6, current: flagged.has(h.transaction_id) })),
  };
}

export const mapAudit = (a: z.infer<typeof BAudit>): AuditView => ({
  flags: a.flags.map(mapFlag),
  totalRecords: a.total_records,
  okRecords: a.ok_records,
  checked: a.checked,
  atRisk: a.summary.amount_at_risk_uzs,
  recommendations: a.recommendations,
});

export const BAuditFix = z.object({ flag_id: z.string(), action: FixKind, deleted_ids: z.array(z.number()), updated_ids: z.array(z.number()) });
export const BOk = z.object({ ok: z.boolean() });

/** POST /integrations/{kind}/sync (platform router). */
export const BSyncResult = z.object({
  kind: z.string(),
  mode: z.enum(["live", "mock"]),
  created: z.number(),
  errors: z.array(z.record(z.string(), z.unknown())),
  audit_flags: z.array(z.record(z.string(), z.unknown())),
  transaction_ids: z.array(z.number()),
});
export interface SyncView {
  message: string;
  created: number;
  newFlags: number;
  transactionIds: number[];
}
export const mapSync = (r: z.infer<typeof BSyncResult>): SyncView => ({
  message: r.created ? `Didox’dan ${r.created} ta yangi yozuv olindi, ${r.audit_flags.length} tasida muammo topildi.` : "Didox’da yangi yozuv yo‘q.",
  created: r.created,
  newFlags: r.audit_flags.length,
  transactionIds: r.transaction_ids,
});

/* ---------------------------------------------------------------------- budget */

export const BBudget = z.object({
  month: z.string(),
  days_elapsed: z.number(),
  days_in_month: z.number(),
  items: z.array(
    z.object({
      category: z.string(),
      label: z.string(),
      planned_uzs: z.number().nullable(),
      fact_uzs: z.number(),
      used_pct: z.number().nullable(),
      forecast_uzs: z.number(),
      status: z.enum(["ok", "at_risk", "over", "no_plan"]),
      explanation: z.string().nullable(),
      top_transactions: z.array(z.object({ id: z.number(), date: z.string(), total_uzs: z.number(), counterparty: z.string().nullable(), note: z.string().nullable() })),
    }),
  ),
  planned_total_uzs: z.number(),
  fact_total_uzs: z.number(),
  forecast_total_uzs: z.number(),
  used_pct: z.number().nullable(),
  explanations: z.array(z.string()),
  cumulative_uzs: z.array(z.number()),
});

/** All amounts in mln so‘m. */
export interface BudgetView {
  month: string;
  monthIndex: number;
  limit: number;
  spent: number;
  forecast: number;
  day: number;
  daysInMonth: number;
  cumulative: number[];
  categories: { key: string; name: string; plan: number; fact: number; forecast: number; status: string }[];
  explanations: string[];
}

const M = 1e6;
export const mapBudget = (b: z.infer<typeof BBudget>): BudgetView => ({
  month: b.month,
  monthIndex: Number(b.month.slice(5, 7)) - 1,
  limit: b.planned_total_uzs / M,
  spent: b.fact_total_uzs / M,
  forecast: b.forecast_total_uzs / M,
  day: b.days_elapsed,
  daysInMonth: b.days_in_month,
  cumulative: b.cumulative_uzs.map((v) => v / M),
  categories: b.items.map((i) => ({ key: i.category, name: i.label, plan: (i.planned_uzs ?? 0) / M, fact: i.fact_uzs / M, forecast: i.forecast_uzs / M, status: i.status })),
  explanations: b.explanations,
});

/* --------------------------------------------------------------------- summary */

export const BBooksSummary = z.object({
  month: z.string(),
  transactions: z.number(),
  income_uzs: z.number(),
  expense_uzs: z.number(),
  net_uzs: z.number(),
  tax_regime: z.string(),
  tax_rate_pct: z.number().nullable(),
  tax_estimate_uzs: z.number(),
  rates_verified: z.boolean(),
});
export type BooksSummary = z.infer<typeof BBooksSummary>;

/* ---------------------------------------------------------------------- upload */

const BTransactionIn = z.object({
  date: z.string(),
  type: z.string(),
  category: z.string(),
  model: z.string().nullable().optional(),
  qty: z.number(),
  unit_price: z.number().nullable().optional(),
  total: z.number(),
  counterparty: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
});
const BUploadError = z.object({ row: z.number(), error: z.string() });

export const BUploadPreview = z.object({
  columns: z.array(z.string()),
  mapping: z.record(z.string(), z.object({ field: z.string().nullable(), confidence: z.number() })),
  fields: z.array(z.string()),
  total_rows: z.number(),
  rows: z.array(BTransactionIn),
  errors: z.array(BUploadError),
});
export type UploadPreviewData = z.infer<typeof BUploadPreview>;

export const BUploadResult = z.object({ created: z.number(), errors: z.array(BUploadError) });
export const BInvoiceResult = z.object({ committed: z.boolean(), extracted: z.array(BTransactionIn), created_ids: z.array(z.number()) });

/** Target field names of the import (UI copy; the list itself comes from the backend). */
export const FIELD_LABELS: Record<string, string> = {
  date: "Sana",
  type: "Turi (kirim/chiqim)",
  category: "Toifa",
  total: "Jami summa",
  qty: "Miqdor",
  unit_price: "Birlik narxi",
  counterparty: "Kontragent",
  note: "Izoh",
  item_category: "Mahsulot turi",
  brand: "Brend",
  model: "Model",
  condition: "Holati",
};
