/**
 * Advisor (Maslahat) — zod schemas of the REAL backend responses and maps to what the screens render.
 * Backend: app/api/routers/advisor.py, app/api/routers/lender.py (borrower side), app/api/schemas/{advisor,blocks,lender}.py.
 */
import { z } from "zod";

/* ------------------------------------------------------------------ answer blocks (app/api/schemas/blocks.py) */

const Series = z.object({ name: z.string(), values: z.array(z.number().nullable()) });

export const Block = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("price_range"),
    title: z.string(),
    fair_uzs: z.number(),
    p25_uzs: z.number(),
    p75_uzs: z.number(),
    your_price_uzs: z.number().nullable().optional(),
    buy_price_uzs: z.number().nullable().optional(),
    currency: z.string(),
    basis: z.string(),
    comparables: z.number(),
    confidence: z.string(),
  }),
  z.object({
    type: z.literal("comparables"),
    title: z.string(),
    samples: z.array(
      z.object({
        title: z.string(),
        price_uzs: z.number(),
        condition: z.string().nullable().optional(),
        district: z.string().nullable().optional(),
        seller_type: z.string().nullable().optional(),
        posted_at: z.string().nullable().optional(),
        source_url: z.string().nullable().optional(),
      }),
    ),
  }),
  z.object({
    type: z.literal("kpi_row"),
    title: z.string(),
    items: z.array(
      z.object({
        label: z.string(),
        value_uzs: z.number().nullable().optional(),
        value: z.union([z.number(), z.string()]).nullable().optional(),
        delta_pct: z.number().nullable().optional(),
      }),
    ),
  }),
  z.object({ type: z.literal("bar_chart"), title: z.string(), x: z.array(z.string()), series: z.array(Series), unit: z.string() }),
  z.object({ type: z.literal("line_chart"), title: z.string(), x: z.array(z.string()), series: z.array(Series), unit: z.string() }),
  z.object({
    type: z.literal("table"),
    title: z.string(),
    columns: z.array(z.string()),
    rows: z.array(z.array(z.unknown())),
    row_ids: z.array(z.number()).nullable().optional(),
  }),
  z.object({
    type: z.literal("steps"),
    title: z.string(),
    steps: z.array(z.object({ label: z.string(), status: z.enum(["done", "todo"]), detail: z.string().nullable().optional() })),
  }),
  z.object({
    type: z.literal("loan_schedule"),
    title: z.string(),
    principal_uzs: z.number(),
    months: z.number(),
    annual_rate_pct: z.number(),
    monthly_payment_uzs: z.number(),
    total_interest_uzs: z.number(),
    rows: z.array(z.object({ month: z.number(), payment_uzs: z.number(), principal_uzs: z.number(), interest_uzs: z.number(), balance_uzs: z.number() })),
  }),
  z.object({ type: z.literal("file"), title: z.string(), url: z.string(), mime: z.string() }),
]);
export type Block = z.infer<typeof Block>;

export const Chip = z.object({
  label: z.string(),
  action: z.object({
    endpoint: z.string(),
    method: z.enum(["GET", "POST", "PUT", "PATCH", "DELETE"]),
    body: z.record(z.unknown()).nullable().optional(),
  }),
});
export type Chip = z.infer<typeof Chip>;

/* ------------------------------------------------------------------ POST /advisor/chat */

export const ChatOut = z.object({
  answer: z.string(),
  used_data: z.array(z.string()),
  language: z.enum(["uz", "ru", "en"]),
  source: z.enum(["llm", "rules"]),
  intent: z.string(),
  intent_source: z.string(),
  blocks: z.array(Block),
  chips: z.array(Chip),
});

/** What a chat bubble renders: an optional sentence, typed blocks and next-step chips. */
export interface Answer {
  text: string | null;
  blocks: Block[];
  chips: Chip[];
}

export const mapChat = (d: z.output<typeof ChatOut>): Answer => ({ text: d.answer || null, blocks: d.blocks, chips: d.chips });

/** Backend `ChatContext`. */
export interface ChatContext {
  screen?: "stock" | "books" | "budget" | "exchange" | "advisor";
  inventory_ids?: number[];
  transaction_ids?: number[];
  rfq_id?: number;
}

/** Frontend screen names (useCopilotScreen) → backend chat context. */
export function chatContext(ctx: { screen: string; selected_ids: string[] }): ChatContext {
  const screens: Record<string, ChatContext["screen"]> = {
    narxlar: "stock",
    baholash: "stock",
    kitoblar: "books",
    hisobotlar: "books",
    budjet: "budget",
    birja: "exchange",
    radar: "exchange",
    lotlar: "exchange",
    talab: "exchange",
    maslahat: "advisor",
  };
  const out: ChatContext = {};
  const screen = screens[ctx.screen];
  if (screen) out.screen = screen;
  const ids = ctx.selected_ids.map(Number).filter((n) => Number.isInteger(n) && n > 0);
  if (ids.length && ctx.screen === "narxlar") out.inventory_ids = ids;
  if (ids.length && (ctx.screen === "kitoblar" || ctx.screen === "hisobotlar")) out.transaction_ids = ids;
  return out;
}

/* ------------------------------------------------------------------ POST /advisor/credit */

export const CREDIT_PRODUCTS = ["business_loan", "auto_loan", "mortgage", "leasing"] as const;
export type CreditProduct = (typeof CREDIT_PRODUCTS)[number];

const ScheduleRowOut = z.object({ month: z.number(), payment_uzs: z.number(), principal_uzs: z.number(), interest_uzs: z.number(), balance_uzs: z.number() });

export const CreditOut = z.object({
  principal_uzs: z.number(),
  months: z.number(),
  annual_rate_pct: z.number(),
  monthly_payment_uzs: z.number(),
  total_payment_uzs: z.number(),
  total_interest_uzs: z.number(),
  avg_monthly_net_uzs: z.number(),
  debt_service_ratio_pct: z.number().nullable(),
  max_debt_service_ratio_pct: z.number(),
  affordable: z.boolean(),
  max_loan_uzs: z.number(),
  max_loan_by_term: z.record(z.number()),
  verdict: z.string(),
  rate_note: z.string(),
  product: z.string(),
  down_payment_pct: z.number().nullable(),
  down_payment_uzs: z.number().nullable(),
  asset_value_uzs: z.number().nullable(),
  ltv: z.number().nullable(),
  schedule: z.array(ScheduleRowOut),
});
export type CreditOut = z.infer<typeof CreditOut>;

/** Schedule row in the shape the ScheduleBars chart takes. */
export const scheduleRows = (rows: z.infer<typeof ScheduleRowOut>[]) =>
  rows.map((r) => ({ month: r.month, principal: r.principal_uzs, interest: r.interest_uzs, balance: r.balance_uzs }));

/** Chip → POST /advisor/credit: the same blocks the copilot's credit tool builds. */
export const creditAnswer = (c: CreditOut, kpi: { payment: string; avgNet: string; maxLoan: string; title: string }): Answer => ({
  text: c.verdict,
  blocks: [
    {
      type: "loan_schedule",
      title: kpi.title,
      principal_uzs: c.principal_uzs,
      months: c.months,
      annual_rate_pct: c.annual_rate_pct,
      monthly_payment_uzs: c.monthly_payment_uzs,
      total_interest_uzs: c.total_interest_uzs,
      rows: c.schedule,
    },
    {
      type: "kpi_row",
      title: kpi.title,
      items: [
        { label: kpi.payment, value_uzs: c.monthly_payment_uzs },
        { label: kpi.avgNet, value_uzs: c.avg_monthly_net_uzs },
        { label: kpi.maxLoan, value_uzs: c.max_loan_uzs },
      ],
    },
  ],
  chips: [],
});

/* ------------------------------------------------------------------ GET /advisor/loan-readiness */

export const LoanReadinessOut = z.object({
  score: z.number(),
  grade: z.enum(["A", "B", "C", "D"]),
  factors: z.array(z.object({ key: z.string(), label: z.string(), points: z.number(), max_points: z.number(), explanation: z.string() })),
  how_to_improve: z.array(z.string()),
});
export type LoanReadiness = z.infer<typeof LoanReadinessOut>;

export const readinessAnswer = (r: LoanReadiness, title: string, score: string): Answer => ({
  text: null,
  blocks: [
    { type: "kpi_row", title, items: [{ label: score, value: r.score }, { label: "Grade", value: r.grade }] },
    {
      type: "steps",
      title,
      steps: r.factors.map((f) => ({ label: f.label, status: f.points >= 0.7 * f.max_points ? "done" : "todo", detail: `${f.points}/${f.max_points} — ${f.explanation}` })),
    },
  ],
  chips: [],
});

/* ------------------------------------------------------------------ GET /advisor/tax */

export const TaxOut = z.object({
  months: z.array(z.string()),
  turnover_uzs: z.number(),
  expenses_uzs: z.number(),
  turnover_regime: z.object({ rate_pct: z.number(), tax_uzs: z.number() }),
  vat_regime: z.object({
    vat_rate_pct: z.number(),
    profit_tax_rate_pct: z.number(),
    output_vat_uzs: z.number(),
    input_vat_uzs: z.number(),
    vat_payable_uzs: z.number(),
    taxable_profit_uzs: z.number(),
    profit_tax_uzs: z.number(),
    total_uzs: z.number(),
  }),
  current_regime: z.string(),
  cheaper_regime: z.enum(["turnover", "vat"]),
  saving_uzs: z.number(),
  explanation: z.string(),
  rates_verified: z.boolean(),
  disclaimer: z.string(),
});
export type Tax = z.infer<typeof TaxOut>;

/** Tax under the regime the shop is on now. */
export const currentTax = (t: Tax) => (t.current_regime === "vat" ? t.vat_regime.total_uzs : t.turnover_regime.tax_uzs);

export const taxAnswer = (t: Tax, l: { turnover: string; vat: string; saving: string; tax: string }): Answer => ({
  text: t.explanation,
  blocks: [
    {
      type: "kpi_row",
      title: `${l.tax} (${t.months.join(", ")})`,
      items: [
        { label: l.turnover, value_uzs: t.turnover_regime.tax_uzs },
        { label: l.vat, value_uzs: t.vat_regime.total_uzs },
        { label: l.saving, value_uzs: t.saving_uzs },
      ],
    },
    { type: "bar_chart", title: l.tax, x: [l.turnover, l.vat], series: [{ name: l.tax, values: [t.turnover_regime.tax_uzs, t.vat_regime.total_uzs] }], unit: "UZS" },
  ],
  chips: [],
});

/* ------------------------------------------------------------------ GET /advisor/cashflow */

export const CashflowOut = z.object({
  months: z.array(z.object({ month: z.string(), income_uzs: z.number(), expense_uzs: z.number(), net_uzs: z.number(), partial: z.boolean() })),
  avg_monthly_net_uzs: z.number(),
});

export const cashflowAnswer = (c: z.infer<typeof CashflowOut>, l: { title: string; income: string; expense: string; net: string; avgNet: string }): Answer => ({
  text: null,
  blocks: [
    {
      type: "line_chart",
      title: l.title,
      x: c.months.map((m) => m.month),
      series: [
        { name: l.income, values: c.months.map((m) => m.income_uzs) },
        { name: l.expense, values: c.months.map((m) => m.expense_uzs) },
        { name: l.net, values: c.months.map((m) => m.net_uzs) },
      ],
      unit: "UZS",
    },
    { type: "kpi_row", title: l.title, items: [{ label: l.avgNet, value_uzs: c.avg_monthly_net_uzs }] },
  ],
  chips: [],
});

/* ------------------------------------------------------------------ lenders and loan applications (lender.py) */

export const LenderRef = z.object({ id: z.number(), name: z.string() });
export const Lenders = z.array(LenderRef);
export type Lender = z.infer<typeof LenderRef>;

export const LoanApplicationOut = z.object({
  id: z.number(),
  company_id: z.number(),
  company_name: z.string(),
  lender_id: z.number(),
  lender_name: z.string(),
  product: z.string(),
  principal_uzs: z.number(),
  months: z.number(),
  purpose: z.string(),
  status: z.enum(["submitted", "reviewing", "approved", "rejected"]),
  decision_note: z.string().nullable(),
  readiness_score: z.number().nullable(),
  consent_at: z.string(),
  created_at: z.string(),
});
export type LoanApplication = z.infer<typeof LoanApplicationOut>;

export const LoanApplicationDetail = LoanApplicationOut.extend({ snapshot: z.record(z.unknown()) });

export const LoanApplicationsPage = z.object({ items: z.array(LoanApplicationOut), next_cursor: z.string().nullable(), total: z.number() });

export interface LoanApplicationIn {
  lender_id: number;
  product: CreditProduct;
  principal_uzs: number;
  months: number;
  purpose: string;
  consent: boolean;
  collateral_inventory_ids?: number[];
}

/* ------------------------------------------------------------------ chip actions that mutate data */

/** POST /stock/reprice → RepriceOut (only the count is shown). */
export const RepriceOut = z.object({ updated: z.number() }).passthrough();
/** POST /stock/list-on-exchange → list[OfferOut] (only the count is shown). */
export const OffersOut = z.array(z.object({ id: z.number() }).passthrough());

/* ------------------------------------------------------------------ GET /advisor/chat/suggestions */

export const ChatSuggestionsOut = z.object({
  screen: z.string().nullable(),
  questions: z.array(z.object({ question: z.string(), intent: z.string() })),
});
