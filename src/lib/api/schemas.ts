import { z } from "zod";

const KeyValue = z.object({ label: z.string(), value: z.string() });
export type KeyValue = z.infer<typeof KeyValue>;

export const SalesDay = z.object({
  date: z.string(),
  actual: z.number().nullable(),
  last_year: z.number(),
  forecast: z.number().nullable(),
  low: z.number().nullable(),
  high: z.number().nullable(),
});
export type SalesDay = z.infer<typeof SalesDay>;

export const CashMonth = z.object({
  month: z.string(),
  income: z.number(),
  spend: z.number(),
  income_ly: z.number(),
  spend_ly: z.number(),
});
export type CashMonth = z.infer<typeof CashMonth>;

export const Dashboard = z.object({
  insight: z.string(),
  sales_today: z.number(),
  sales_delta: z.number(),
  sales_delta_pct: z.number(),
  plan: z.number(),
  strip: z.array(z.object({ date: z.string(), value: z.number() })),
  sales: z.object({ today_index: z.number(), window_start: z.number(), days: z.array(SalesDay) }),
  stock_health: z.object({ under: z.number(), fair: z.number(), over: z.number(), no_data: z.number(), total: z.number() }),
  cash_flow: z.array(CashMonth),
  avg_net: z.number(),
  budget: z.object({ spent: z.number(), limit: z.number(), warning: z.string().nullable() }),
  credit: z.object({ score: z.number(), offers: z.number() }),
  activity: z.array(z.object({ time: z.string(), text: z.string(), value: z.string() })),
  index: z.object({
    title: z.string(),
    subtitle: z.string(),
    price: z.number(),
    change_pct: z.number(),
    from: z.string(),
    series: z.array(z.object({ median: z.number(), p25: z.number(), p75: z.number() })),
  }),
  rfq: z.object({
    id: z.number(),
    subtitle: z.string(),
    quotes: z.array(z.object({ name: z.string(), price: z.number(), best: z.boolean() })),
  }),
});
export type Dashboard = z.infer<typeof Dashboard>;

export const Rating = z.enum(["under", "fair", "over", "no_data"]);
export type Rating = z.infer<typeof Rating>;

export const RepriceResult = z.object({
  changed: z.array(z.object({ id: z.string(), from: z.number(), to: z.number() })),
});
export type RepriceResult = z.infer<typeof RepriceResult>;

export const PriceStep = z.object({
  label: z.string(),
  sub: z.string(),
  delta: z.number(),
  kind: z.enum(["start", "minus", "plus", "margin", "end"]),
  reason: z.string(),
});
export type PriceStep = z.infer<typeof PriceStep>;

export const Comparable = z.object({
  price: z.number(),
  meta: z.string(),
  rating: z.string(),
  diff_pct: z.number(),
  url: z.string(),
});
export type Comparable = z.infer<typeof Comparable>;

export const PriceVerdict = z.object({
  model: z.string(),
  detail: z.string(),
  max_price: z.number(),
  soum: z.number(),
  first_offer: z.number(),
  resale: z.number(),
  profit: z.number(),
  days: z.number(),
  median: z.number(),
  range_low: z.number(),
  range_high: z.number(),
  listings: z.number(),
  steps: z.array(PriceStep),
  comparables: z.array(Comparable),
});
export type PriceVerdict = z.infer<typeof PriceVerdict>;

export const RadarFind = z.object({
  id: z.string(),
  title: z.string(),
  meta: z.string(),
  category: z.enum(["phone", "laptop", "car", "realty"]),
  price: z.number(),
  market: z.number(),
  diff_pct: z.number(),
  profit: z.number(),
  days: z.number(),
  channel: z.string(),
  age: z.string(),
  url: z.string(),
  is_new: z.boolean(),
});
export type RadarFind = z.infer<typeof RadarFind>;

export const FeedPost = z.object({
  id: z.string(),
  channel: z.string(),
  time: z.string(),
  text: z.string(),
  latency_s: z.number(),
  fields: z.array(KeyValue),
  median_label: z.string(),
  price: z.number(),
  diff_pct: z.number(),
});
export type FeedPost = z.infer<typeof FeedPost>;

export const Radar = z.object({
  items: z.array(RadarFind),
  total: z.number(),
  avg_discount: z.number(),
  expected_profit: z.number(),
  channels: z.number(),
  feed: FeedPost,
  previous: z.array(z.object({ time: z.string(), title: z.string(), value: z.string() })),
  has_more_posts: z.boolean(),
});
export type Radar = z.infer<typeof Radar>;

export const Deal = z.object({
  id: z.string(),
  label: z.string(),
  rfq_id: z.number(),
  supplier: z.string(),
  buyer: z.string(),
  item: z.string(),
  qty: z.number(),
  unit_price: z.number(),
  total: z.number(),
  date: z.string(),
});
export type Deal = z.infer<typeof Deal>;

export const Lot = z.object({
  id: z.string(),
  title: z.string(),
  seller: z.string(),
  qty: z.number(),
  unit_price: z.number(),
  market: z.number(),
  diff_pct: z.number(),
  location: z.string(),
  kind: z.string(),
});
export type Lot = z.infer<typeof Lot>;

export const Demand = z.object({
  districts: z.array(z.object({ name: z.string(), count: z.number(), models: z.string() })),
  models: z.array(z.object({ name: z.string(), requests: z.number(), change_pct: z.number() })),
});
export type Demand = z.infer<typeof Demand>;

export const AuditFlag = z.object({
  id: z.string(),
  title: z.string(),
  subtitle: z.string(),
  amount: z.string(),
  crumb: z.string(),
  heading: z.string(),
  explain: z.string(),
  calc: z.array(z.object({ label: z.string(), value: z.string(), bad: z.boolean() })),
  note: z.string(),
  invoice: z
    .object({
      title: z.string(),
      meta: z.string(),
      lines: z.array(KeyValue),
      total: z.string(),
    })
    .nullable(),
  chart: z.boolean(),
  fix_label: z.string(),
  ignore_label: z.string(),
  source: z.enum(["didox", "billz", "manual"]),
  is_new: z.boolean(),
});
export type AuditFlag = z.infer<typeof AuditFlag>;

export const InvoiceHistory = z.object({
  id: z.string(),
  date: z.string(),
  over: z.number(),
  current: z.boolean(),
});
export type InvoiceHistory = z.infer<typeof InvoiceHistory>;

export const Audit = z.object({
  flags: z.array(AuditFlag),
  total_records: z.number(),
  ok_records: z.number(),
  invoices: z.array(InvoiceHistory),
});
export type Audit = z.infer<typeof Audit>;

export const Budget = z.object({
  month: z.string(),
  limit: z.number(),
  spent: z.number(),
  day: z.number(),
  days_in_month: z.number(),
  burn: z.object({ ads: z.number(), purchases: z.number(), other: z.number() }),
  categories: z.array(z.object({ name: z.string(), plan: z.number(), fact: z.number() })),
});
export type Budget = z.infer<typeof Budget>;

const ScheduleRow = z.object({ month: z.number(), principal: z.number(), interest: z.number(), balance: z.number() });
export type ScheduleRow = z.infer<typeof ScheduleRow>;

export const Block = z.discriminatedUnion("type", [
  z.object({ type: z.literal("text"), text: z.string() }),
  z.object({ type: z.literal("kpi_row"), items: z.array(KeyValue) }),
  z.object({
    type: z.literal("price_range"),
    title: z.string(),
    low: z.number(),
    median: z.number(),
    high: z.number(),
    marker: z.number().nullable(),
    marker_label: z.string().nullable(),
  }),
  z.object({
    type: z.literal("comparables"),
    title: z.string(),
    items: z.array(z.object({ title: z.string(), meta: z.string(), value: z.string() })),
  }),
  z.object({
    type: z.literal("bar_chart"),
    title: z.string(),
    items: z.array(z.object({ label: z.string(), value: z.number(), display: z.string() })),
  }),
  z.object({
    type: z.literal("line_chart"),
    title: z.string(),
    labels: z.array(z.string()),
    values: z.array(z.number()),
  }),
  z.object({
    type: z.literal("table"),
    title: z.string(),
    columns: z.array(z.string()),
    rows: z.array(z.array(z.string())),
  }),
  z.object({ type: z.literal("steps"), title: z.string(), items: z.array(z.string()) }),
  z.object({
    type: z.literal("loan_schedule"),
    schedule: z.array(ScheduleRow),
    total_interest: z.number(),
  }),
  z.object({
    type: z.literal("file"),
    name: z.string(),
    content: z.string(),
    note: z.string(),
    rows: z.array(z.array(z.union([z.string(), z.number()]))).optional(),
  }),
]);
export type Block = z.infer<typeof Block>;

export const Chip = z.object({
  label: z.string(),
  action: z.object({
    endpoint: z.string(),
    method: z.enum(["GET", "POST"]),
    body: z.record(z.unknown()).nullable(),
  }),
});
export type Chip = z.infer<typeof Chip>;

export const LoanApplication = z.object({
  id: z.string(),
  borrower: z.string(),
  stir: z.string(),
  product: z.string(),
  amount: z.number(),
  months: z.number(),
  monthly: z.number(),
  readiness: z.number(),
  avg_profit: z.number(),
  payment_ratio: z.number(),
  collateral: z.string(),
  source: z.string(),
  status: z.enum(["new", "approved", "rejected"]),
});
export type LoanApplication = z.infer<typeof LoanApplication>;

export const Collateral = z.object({
  id: z.string(),
  object: z.string(),
  borrower: z.string(),
  value: z.number(),
  change_30d: z.number(),
  ltv: z.number(),
  status: z.enum(["normal", "watch", "breach"]),
});
export type Collateral = z.infer<typeof Collateral>;
