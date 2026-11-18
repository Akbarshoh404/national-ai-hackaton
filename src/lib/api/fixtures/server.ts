"use client";

import { getAccount } from "@/lib/auth";
import { dateLong, DEMO_TODAY, mln, shortSoum, usd } from "@/lib/format";
import { toCsv } from "@/lib/utils";
import { ApiError } from "../client";
import type {
  ActivityRow,
  AuditFlag,
  Block,
  Budget,
  ChatAnswer,
  Chip,
  Collateral,
  Credit,
  Deal,
  Decision,
  IncomingRfq,
  LoanApplication,
  Lot,
  ParsedInput,
  PriceVerdict,
  Quote,
  RadarFind,
  Rfq,
  StockUnit,
  Transaction,
  Valuation,
} from "../schemas";
import * as seed from "./seed";

const STORAGE_KEY = "raft_demo_state_v1";

interface DemoState {
  decisions: Decision[];
  units: StockUnit[];
  finds: RadarFind[];
  feedIndex: number;
  previous: { time: string; title: string; value: string }[];
  quotes: seed.SeedQuote[];
  rfqNote: string | null;
  deal: Deal | null;
  incoming: IncomingRfq[];
  lots: Lot[];
  flags: AuditFlag[];
  resolvedFlags: string[];
  transactions: Transaction[];
  totalRecords: number;
  budget: Budget;
  applications: LoanApplication[];
  collateral: Collateral[];
  activity: ActivityRow[];
  synced: Record<string, string>;
}

function fresh(): DemoState {
  const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
  return {
    decisions: clone(seed.SEED_DECISIONS),
    units: seed.seedUnits(),
    finds: clone(seed.SEED_FINDS),
    feedIndex: 0,
    previous: clone(seed.SEED_PREVIOUS),
    quotes: clone(seed.SEED_QUOTES),
    rfqNote: null,
    deal: null,
    incoming: clone(seed.SEED_INCOMING),
    lots: clone(seed.SEED_LOTS),
    flags: clone(seed.SEED_FLAGS),
    resolvedFlags: [],
    transactions: clone(seed.SEED_TRANSACTIONS),
    totalRecords: 412,
    budget: clone(seed.SEED_BUDGET),
    applications: clone(seed.SEED_APPLICATIONS),
    collateral: clone(seed.SEED_COLLATERAL),
    activity: clone(seed.SEED_ACTIVITY),
    synced: {},
  };
}

let memo: DemoState | null = null;

function load(): DemoState {
  if (memo) return memo;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) memo = JSON.parse(raw) as DemoState;
  } catch {
    memo = null;
  }
  memo ??= fresh();
  return memo;
}

function save() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(memo));
  } catch {
    /* the demo keeps working from memory */
  }
}

export function resetDemo() {
  memo = fresh();
  save();
}

const nowTime = () => new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

function log(s: DemoState, text: string, value: string) {
  s.activity.unshift({ time: nowTime(), text, value, actor: getAccount()?.role ?? "Tizim" });
}

const notFound = () => new ApiError(404, "not_found", "Topilmadi");

/* Derived views */

function rate(u: StockUnit, price: number): StockUnit {
  const vs = u.market_price ? ((price - u.market_price) / u.market_price) * 100 : null;
  const rating = vs === null ? "no_data" : vs > 6 ? "over" : vs < -6 ? "under" : "fair";
  const expected = rating === "over" ? u.expected_days : rating === "no_data" ? null : Math.min(u.expected_days ?? 9, 9);
  return { ...u, list_price: price, vs_market_pct: vs, margin: price - u.cost, rating, expected_days: expected };
}

function stockSummary(s: DemoState) {
  const over = s.units.filter((u) => u.rating === "over");
  return {
    total: s.units.length,
    value_cost: s.units.reduce((sum, u) => sum + u.cost, 0),
    value_market: s.units.reduce((sum, u) => sum + (u.market_price ?? u.list_price), 0),
    overpriced: over.length,
    aging: s.units.filter((u) => u.days_in_stock >= seed.AGING_DAYS).length,
    margin_at_risk: over.reduce((sum, u) => sum + (u.list_price - (u.suggested_price ?? u.list_price)), 0),
    stores: ["Chilonzor", "Yunusobod"],
  };
}

function budgetWarning(b: Budget) {
  const daily = b.burn.ads + b.burn.purchases + b.burn.other;
  const day = b.day + Math.floor((b.limit - b.spent) / daily);
  return day <= b.days_in_month ? `Limit ${day}-noyabrda tugaydi` : null;
}

function buildQuotes(s: DemoState): Quote[] {
  const market = 262;
  const sorted = [...s.quotes].sort((a, b) => a.price - b.price);
  return sorted.map((q, i) => ({
    id: q.id,
    supplier: q.supplier,
    verification: q.verification,
    price: q.price,
    qty: q.qty,
    total: q.price * q.qty,
    delivery: q.delivery,
    warranty: q.warranty,
    diff_pct: ((q.price - market) / market) * 100,
    why: i === 0 && q.id !== "q-samxit" ? [{ text: "Uch taklif ichida eng arzoni", warn: false }, ...q.why] : q.why,
    recommended: i === 0,
  }));
}

function buildRfq(s: DemoState): Rfq {
  return {
    id: 148,
    title: "20 dona Redmi Note 13",
    qty: 20,
    specs: [
      { label: "Xotira", value: "8 / 256 GB" },
      { label: "Holati", value: "Yangi" },
      { label: "Yetkazish", value: "Chilonzor · juma" },
      { label: "To‘lov", value: "Bank o‘tkazmasi" },
    ],
    market_unit: 262,
    market_total: 5240,
    listings: 85,
    created: "15-noyabr",
    market_dots: seed.marketDots(),
    quotes: buildQuotes(s),
    note: s.rfqNote,
    deal: s.deal,
  };
}

function resolveFlag(s: DemoState, id: string, how: "fix" | "ignore") {
  const flag = s.flags.find((f) => f.id === id);
  if (!flag) throw new ApiError(409, "already_resolved", "Bu yozuv allaqachon ko‘rib chiqilgan");
  s.flags = s.flags.filter((f) => f.id !== id);
  s.resolvedFlags.push(id);
  s.decisions = s.decisions.map((d) => (d.flag_id === id && d.status === "pending" ? { ...d, status: how === "fix" ? "approved" : "ignored" } : d));
  log(s, how === "fix" ? `Tuzatildi: ${flag.crumb}` : `O‘tkazib yuborildi: ${flag.crumb}`, flag.amount);
}

function annuity(amount: number, months: number, rate: number): Credit {
  const r = rate / 100 / 12;
  const monthly = (amount * r) / (1 - (1 + r) ** -months);
  let balance = amount;
  const schedule = Array.from({ length: months }, (_, i) => {
    const interest = balance * r;
    const principal = monthly - interest;
    balance = Math.max(0, balance - principal);
    return { month: i + 1, principal, interest, balance };
  });
  return {
    product: "Biznes krediti",
    amount,
    months,
    rate,
    monthly,
    total_interest: schedule.reduce((sum, row) => sum + row.interest, 0),
    schedule,
  };
}

const PRODUCT_RATES: Record<string, { name: string; rate: number }> = {
  business: { name: "Biznes krediti", rate: 24 },
  auto: { name: "Avto kredit", rate: 26 },
  mortgage: { name: "Ipoteka", rate: 19 },
  leasing: { name: "Lizing", rate: 22 },
};

function priceModel(text: string) {
  const q = text.toLowerCase();
  return seed.PRICE_MODELS.find((m) => m.keys.some((k) => q.includes(k)));
}

function priceVerdict(body: { query?: string; condition?: string; battery?: number; box?: boolean }): PriceVerdict {
  const model = priceModel(body.query ?? "") ?? seed.PRICE_MODELS[0];
  const condition = body.condition ?? "A";
  const battery = body.battery ?? 87;
  const box = body.box ?? true;
  const conditionDelta = condition === "B" ? -Math.round(model.median * 0.08) : condition === "C" ? -Math.round(model.median * 0.2) : 0;
  const batteryDelta = -Math.round((100 - battery) * (model.median / 450));
  const boxDelta = box ? Math.round(model.median / 52) : 0;
  const adjusted = model.median + conditionDelta + batteryDelta + boxDelta;
  const max = Math.round((adjusted * 0.8) / 5) * 5;
  const first = Math.round((max * 0.93) / 5) * 5;
  const resale = model.median + conditionDelta;
  const steps: PriceVerdict["steps"] = [
    { label: "Bozor medianasi", sub: `${condition} holat`, delta: model.median, kind: "start", reason: `${model.listings} ta e’lonning 30 kunlik medianasi` },
    ...(conditionDelta ? [{ label: "Tashqi holat", sub: condition, delta: conditionDelta, kind: "minus" as const, reason: "Izlar sotish narxini pasaytiradi" }] : []),
    { label: "Batareya", sub: `${battery}%`, delta: batteryDelta, kind: "minus", reason: `Batareya ${battery}%, xaridor shuncha kam to‘laydi` },
    { label: "Quti va hujjatlar", sub: box ? "bor" : "yo‘q", delta: boxDelta, kind: "plus", reason: box ? "To‘liq komplekt tezroq sotiladi" : "Quti yo‘q, qo‘shimcha yo‘q" },
    { label: "Sizning marjangiz", sub: "20%", delta: max - adjusted, kind: "margin", reason: "Do‘kon sozlamasidagi maqsadli marja" },
    { label: "Maksimal xarid narxi", sub: "", delta: max, kind: "end", reason: "Shundan yuqori to‘lamang" },
  ];
  const c = (delta: number, meta: string, n: number): PriceVerdict["comparables"][number] => ({
    price: model.median + delta,
    meta,
    rating: "Adolatli",
    diff_pct: (delta / model.median) * 100,
    url: `https://t.me/iphone_bozor_uz/${3900 + n}`,
  });
  return {
    model: model.model,
    detail: model.detail,
    max_price: max,
    soum: max * seed.USD_RATE,
    first_offer: first,
    resale,
    profit: resale - max,
    days: model.days + (condition === "C" ? 3 : condition === "B" ? 1 : 0),
    median: model.median,
    range_low: model.low,
    range_high: model.high,
    listings: model.listings,
    steps,
    comparables: [c(-5, "A · 89% · quti · 2 soat oldin", 1), c(10, "A · 86% · quti · kecha", 2), c(-15, "A · 84% · qutisiz · 3 kun oldin", 3)],
  };
}

function parseText(text: string, source: ParsedInput["source"]): ParsedInput {
  const model = priceModel(text);
  if (!model) throw new ApiError(422, "unknown_model", "Modelni aniqlab bo‘lmadi. Masalan: iphone 13 pro 256 87% quti bor");
  const q = text.toLowerCase();
  const battery = /(\d{2,3})\s*%/.exec(q);
  const boxYes = /(korobka|karobka|quti)\s*(bor)?/.test(q);
  const boxNo = /(korobka|karobka|quti)(si)?\s*(yo.?q)|qutisiz/.test(q);
  const condition = /\bideal\b|\ba holat/.test(q) ? "A" : /\bb holat|mayda|chizilgan/.test(q) ? "B" : /\bc holat|singan|shikast/.test(q) ? "C" : null;
  return {
    query: model.model,
    model: model.model,
    detail: source === "link" ? "Telegram e’lonidan o‘qildi" : "Matndan o‘qildi",
    condition,
    battery: battery ? Math.min(100, Number(battery[1])) : null,
    box: boxNo ? false : boxYes ? true : null,
    source,
  };
}

const money = (v: number) => shortSoum(v);

function loanAnswer(amount: number, months: number): ChatAnswer {
  const c = annuity(amount, months, 24);
  const share = Math.round((c.monthly / 42_000_000) * 100);
  return {
    blocks: [
      {
        type: "kpi_row",
        items: [
          { label: "Kredit", value: mln(amount / 1e6) },
          { label: "Muddat", value: `${months} oy` },
          { label: "Stavka", value: "24% yillik" },
          { label: "Oylik to‘lov", value: mln(c.monthly / 1e6, 1) },
        ],
      },
      {
        type: "text",
        text: `Oylik to‘lov o‘rtacha sof foydangizning ${share}% ini tashkil qiladi (oyiga ~42 mln so‘m). Banklar odatda 50% gacha bo‘lgan yukni qabul qiladi.`,
      },
      { type: "loan_schedule", schedule: c.schedule, total_interest: c.total_interest },
    ],
    chips: [
      months === 24
        ? { label: "Muddatni 36 oyga o‘zgartirish", action: { endpoint: "/advisor/chat", method: "POST", body: { message: "Muddatni 36 oyga o‘zgartir", amount, months: 36 } } }
        : { label: "Muddatni 24 oyga qaytarish", action: { endpoint: "/advisor/chat", method: "POST", body: { message: "Muddatni 24 oyga qaytar", amount, months: 24 } } },
      { label: "Ariza tayyorlash", action: { endpoint: "/advisor/chat", method: "POST", body: { message: "Ariza tayyorla" } } },
      { label: "Jadvalni Excel’ga yuklash", action: { endpoint: "/advisor/credit/export", method: "POST", body: { amount, months } } },
    ] satisfies Chip[],
  };
}

export const INITIAL_QUESTION = "300 mln kredit olsam, oylik to‘lov foydamning qancha qismi bo‘ladi?";
export const initialAnswer = () => loanAnswer(300_000_000, 24);

function chat(s: DemoState, body: { message?: string; amount?: number; months?: number; context?: { screen?: string; selected_ids?: string[] } }): ChatAnswer {
  const q = (body.message ?? "").toLowerCase();
  const selected = body.context?.selected_ids ?? [];
  if (body.months || /kredit|qarz|oylik to.?lov/.test(q)) {
    const months = body.months ?? (/(\d{2})\s*oy/.exec(q) ? Number(/(\d{2})\s*oy/.exec(q)![1]) : 24);
    const amountMatch = /(\d{2,4})\s*mln/.exec(q);
    return loanAnswer(body.amount ?? (amountMatch ? Number(amountMatch[1]) * 1e6 : 300_000_000), months);
  }
  if (/ariza/.test(q)) {
    return {
      blocks: [
        { type: "text", text: "Ariza kitoblaringizdagi tasdiqlangan raqamlardan tayyorlanadi. Bankka faqat roziligingizdan keyin yuboriladi." },
        { type: "steps", title: "Keyingi qadamlar", items: ["4 ta tekshiruvni yoping", "Summani va muddatni tasdiqlang", "“Bankka ariza yuborish” tugmasini bosing"] },
      ],
      chips: [],
    };
  }
  if (selected.length || /ombor|qimmat|narxla/.test(q)) {
    const units = selected.length ? s.units.filter((u) => selected.includes(u.id)) : s.units.filter((u) => u.rating === "over");
    const rows = units.slice(0, 6).map((u) => [u.model, usd(u.list_price), u.market_price ? usd(u.market_price) : "yo‘q", u.suggested_price ? usd(u.suggested_price) : "yo‘q"]);
    return {
      blocks: [
        { type: "text", text: `${units.length} ta birlik ko‘rib chiqildi. Tavsiya narxlar bozor medianasiga asoslangan.` },
        { type: "table", title: "Birliklar", columns: ["Model", "Narx", "Bozor", "Tavsiya"], rows },
      ],
      chips: [],
    };
  }
  if (/budjet|xarajat|limit/.test(q)) {
    return {
      blocks: [
        { type: "kpi_row", items: [{ label: "Sarflandi", value: "148 mln" }, { label: "Limit", value: "240 mln" }, { label: "Limit tugashi", value: "26-noyabr" }] },
        { type: "bar_chart", title: "Toifalar bo‘yicha sarf", items: s.budget.categories.map((c) => ({ label: c.name, value: c.fact, display: mln(c.fact) })) },
      ],
      chips: [],
    };
  }
  if (/savdo|sotuv/.test(q)) {
    const days = seed.stripDays().slice(-14);
    return {
      blocks: [
        { type: "text", text: "So‘nggi 14 kunlik savdo. Bugungi natija kechagidan 8,4% yuqori." },
        { type: "line_chart", title: "Kunlik savdo", labels: days.map((d) => dateLong(d.date)), values: days.map((d) => d.value) },
      ],
      chips: [],
    };
  }
  const model = priceModel(q);
  if (model) {
    const v = priceVerdict({ query: q });
    return {
      blocks: [
        { type: "price_range", title: v.model, low: v.range_low, median: v.median, high: v.range_high, marker: v.max_price, marker_label: "Sizning chegarangiz" },
        { type: "comparables", title: "Eng yaqin e’lonlar", items: v.comparables.map((c) => ({ title: usd(c.price), meta: c.meta, value: c.rating })) },
      ],
      chips: [],
    };
  }
  return {
    blocks: [{ type: "text", text: "Kredit, budjet, savdo, ombor yoki aniq model narxi haqida so‘rang. Javob kitoblaringiz va bozor ma’lumotlaridan olinadi." }],
    chips: [
      { label: "300 mln kredit hisobi", action: { endpoint: "/advisor/chat", method: "POST", body: { message: "300 mln kredit" } } },
      { label: "Budjet holati", action: { endpoint: "/advisor/chat", method: "POST", body: { message: "budjet" } } },
    ],
  };
}

function readiness(s: DemoState) {
  const mine = s.applications.find((a) => a.id === "a-chilonzor") ?? null;
  return {
    score: 78,
    factors: [
      { name: "Kitoblar tozaligi", value: 92 },
      { name: "Savdo barqarorligi", value: 81 },
      { name: "Birja tarixi", value: 64 },
      { name: "Qarz yuki", value: 70 },
    ],
    tips: [
      { text: "4 ta tekshiruvni yoping", points: 5 },
      { text: "Birjada yana 3 ta bitim", points: 4 },
    ],
    tax: { amount: 9_800_000, note: "Aylanmadan soliq 4% · 245 mln so‘m aylanma" },
    application: mine,
  };
}

function valuation(body: { query?: string; inventory_id?: string }, s: DemoState): Valuation {
  if (body.inventory_id) {
    const unit = s.units.find((u) => u.id === body.inventory_id);
    if (!unit) throw new ApiError(422, "unknown_item", "Bunday ombor raqami topilmadi");
    const fair = unit.market_price ?? unit.list_price;
    return {
      title: unit.model,
      subtitle: `${unit.attrs} · ${unit.store}`,
      fair,
      p25: Math.round(fair * 0.95),
      p75: Math.round(fair * 1.05),
      liquidation: Math.round(fair * 0.85),
      listings: 42,
      window_days: 30,
      change_30d: -2.1,
      comparables: [{ title: unit.model, meta: `${unit.store} · 1 kun oldin`, price: Math.round(fair * 1.01) }],
    };
  }
  const q = (body.query ?? "cobalt").toLowerCase();
  if (q.includes("malibu")) {
    return {
      title: "Chevrolet Malibu 2 2019",
      subtitle: "pozitsiya 3 · 88 000 km · Sergeli Avto",
      fair: 16900,
      p25: 15800,
      p75: 18100,
      liquidation: 14500,
      listings: 21,
      window_days: 30,
      change_30d: -4.6,
      comparables: [
        { title: "Malibu 2 2019 · poz 3 · 92 000 km", meta: "Chilonzor · 1 kun oldin", price: 16700 },
        { title: "Malibu 2 2020 · poz 2 · 74 000 km", meta: "Yunusobod · 3 kun oldin", price: 17400 },
      ],
    };
  }
  if (q.includes("cobalt") || q.includes("t.me")) {
    return {
      title: "Chevrolet Cobalt 2021",
      subtitle: "pozitsiya 4 · 62 000 km · Sergeli Avto",
      fair: 11400,
      p25: 10600,
      p75: 12100,
      liquidation: 9800,
      listings: 36,
      window_days: 30,
      change_30d: -1.8,
      comparables: [
        { title: "Cobalt 2021 · poz 4 · 58 000 km", meta: "Yunusobod · 2 kun oldin", price: 11600 },
        { title: "Cobalt 2021 · poz 4 · 71 000 km", meta: "Chilonzor · 4 kun oldin", price: 11100 },
      ],
    };
  }
  const model = priceModel(q);
  if (!model) throw new ApiError(422, "no_market_data", "Bu obyekt bo‘yicha yetarli e’lon topilmadi");
  return {
    title: model.model.replace(" · ", " "),
    subtitle: model.detail,
    fair: model.median,
    p25: Math.round(model.median * 0.96),
    p75: Math.round(model.median * 1.04),
    liquidation: Math.round(model.median * 0.85),
    listings: model.listings,
    window_days: 30,
    change_30d: -2.4,
    comparables: [{ title: model.model, meta: "Chilonzor · 2 soat oldin", price: model.median - 5 }],
  };
}

function search(s: DemoState, q: string) {
  const text = q.toLowerCase();
  const seen = new Set<string>();
  const products = s.units
    .filter((u) => `${u.model} ${u.attrs}`.toLowerCase().includes(text))
    .filter((u) => (seen.has(u.model) ? false : (seen.add(u.model), true)))
    .slice(0, 4)
    .map((u) => ({ group: "Mahsulotlar", title: u.model, meta: `${u.attrs} · ${usd(u.list_price)}`, href: "/narxlar?tab=ombor" }));
  const invoices = s.transactions
    .filter((t) => t.kind === "purchase" && `${t.title} ${t.counterparty}`.toLowerCase().includes(text))
    .slice(0, 3)
    .map((t) => ({ group: "Fakturalar", title: t.title, meta: `${t.counterparty} · ${t.amount}`, href: "/kitoblar" }));
  const partners = ["TechOpt Wholesale", "Sam Xit Trade", "MobiGross", "Smart Store Sergeli", "Gadget House"]
    .filter((p) => p.toLowerCase().includes(text))
    .slice(0, 3)
    .map((p) => ({ group: "Hamkorlar", title: p, meta: "Birja", href: "/birja" }));
  return { items: [...products, ...invoices, ...partners] };
}

type Ctx = { body: Record<string, unknown>; query: Record<string, unknown>; s: DemoState; m: RegExpExecArray };
type Handler = (ctx: Ctx) => unknown;

const routes: [string, RegExp, Handler][] = [
  [
    "GET",
    /^\/dashboard$/,
    ({ s }) => {
      const units = s.units;
      const last = s.budget;
      return {
        insight: "iPhone 13 narxlari 7 kunda 3% tushdi. 9 donani shu hafta soting.",
        sales_today: 3940,
        sales_delta: 310,
        sales_delta_pct: 8.4,
        plan: seed.PLAN,
        strip: seed.stripDays(),
        sales: { today_index: seed.TODAY_INDEX, window_start: seed.WINDOW_START, days: seed.salesDays() },
        stock_health: {
          under: units.filter((u) => u.rating === "under").length,
          fair: units.filter((u) => u.rating === "fair").length,
          over: units.filter((u) => u.rating === "over").length,
          no_data: units.filter((u) => u.rating === "no_data").length,
          total: units.length,
        },
        cash_flow: seed.CASH_FLOW,
        avg_net: 42,
        budget: { spent: last.spent, limit: last.limit, warning: budgetWarning(last) },
        credit: { score: 78, offers: 2 },
        activity: s.activity.slice(0, 5),
        index: {
          title: "Bozor narx indeksi",
          subtitle: "iPhone 13 128GB · Toshkent · 214 e’lon",
          price: 412,
          change_pct: -3.1,
          from: "2026-10-18",
          series: seed.indexSeries(),
        },
        rfq: {
          id: 148,
          subtitle: "20 dona Redmi Note 13",
          quotes: buildQuotes(s)
            .slice(0, 3)
            .map((q) => ({ name: q.supplier.replace(" Trade", "").replace(" Wholesale", ""), price: q.price, best: q.recommended })),
        },
      };
    },
  ],
  ["GET", /^\/decisions$/, ({ s }) => ({ items: s.decisions.filter((d) => d.status === "pending"), next_cursor: null, total: s.decisions.filter((d) => d.status === "pending").length })],
  [
    "POST",
    /^\/decisions\/([^/]+)\/(approve|ignore)$/,
    ({ s, m }) => {
      const d = s.decisions.find((x) => x.id === m[1]);
      if (!d) throw notFound();
      if (d.status !== "pending") throw new ApiError(409, "already_resolved", "Bu qaror allaqachon hal qilingan");
      d.status = m[2] === "approve" ? "approved" : "ignored";
      if (m[2] === "approve") {
        if (d.unit_id) {
          s.units = s.units.map((u) => (u.id === d.unit_id ? rate(u, u.suggested_price ?? u.list_price) : u));
        }
        if (d.flag_id && s.flags.some((f) => f.id === d.flag_id)) resolveFlag(s, d.flag_id, "fix");
        else log(s, `Tasdiqlandi: ${d.title}`, d.amount);
      } else {
        log(s, `O‘tkazib yuborildi: ${d.short}`, d.amount);
      }
      return { ok: true };
    },
  ],
  ["GET", /^\/stock\/units$/, ({ s }) => ({ items: s.units, next_cursor: null, total: s.units.length })],
  ["GET", /^\/stock\/summary$/, ({ s }) => stockSummary(s)],
  [
    "POST",
    /^\/stock\/reprice$/,
    ({ s, body }) => {
      const prices = body.prices as { id: string; price: number }[] | undefined;
      const ids = (body.unit_ids as string[] | undefined) ?? [];
      const changed: { id: string; from: number; to: number }[] = [];
      s.units = s.units.map((u) => {
        const target = prices ? prices.find((p) => p.id === u.id)?.price : ids.includes(u.id) ? (u.suggested_price ?? undefined) : undefined;
        if (target === undefined || target === u.list_price) return u;
        changed.push({ id: u.id, from: u.list_price, to: target });
        return rate(u, target);
      });
      if (!prices) log(s, `${changed.length} ta narx bozorga moslandi`, `${changed.length} dona`);
      return { changed };
    },
  ],
  [
    "POST",
    /^\/stock\/list-on-exchange$/,
    ({ s, body }) => {
      const ids = (body.unit_ids as string[]) ?? [];
      const units = s.units.filter((u) => ids.includes(u.id));
      units.forEach((u) => {
        const market = u.market_price ?? u.list_price;
        s.lots.unshift({
          id: `l-${u.id}`,
          title: `${u.model} ${u.attrs}`,
          seller: "Chilonzor Phone Market",
          qty: 1,
          unit_price: u.list_price,
          market,
          diff_pct: ((u.list_price - market) / market) * 100,
          location: u.store,
          kind: "Ortiqcha qoldiq",
        });
      });
      log(s, `${units.length} ta birlik birjaga chiqarildi`, `${units.length} dona`);
      return { ok: true };
    },
  ],
  [
    "POST",
    /^\/stock\/units$/,
    ({ s, body }) => {
      const b = body as { model: string; detail: string; price: number; resale: number; median: number; days: number; condition: string; battery: number };
      const category: StockUnit["category"] = /macbook|thinkpad/i.test(b.model) ? "laptop" : "phone";
      const [name, attr] = b.model.split(" · ");
      const unit: StockUnit = {
        id: `u-${1001 + s.units.length}`,
        model: name,
        attrs: `${attr ?? ""} · ${b.condition} · ${b.battery}%`,
        category,
        store: "Chilonzor",
        list_price: b.resale,
        cost: b.price,
        market_price: b.median,
        vs_market_pct: ((b.resale - b.median) / b.median) * 100,
        margin: b.resale - b.price,
        days_in_stock: 0,
        expected_days: b.days,
        rating: "fair",
        suggested_price: b.resale,
      };
      s.units.unshift(unit);
      log(s, `Trade-in: ${name} omborga qo‘shildi`, usd(b.price));
      return { ok: true };
    },
  ],
  ["POST", /^\/market\/price$/, ({ body }) => priceVerdict(body)],
  [
    "GET",
    /^\/market\/sourcing-radar$/,
    ({ s }) => {
      const post = seed.FEED_POSTS[Math.max(0, s.feedIndex - 1)];
      return {
        items: s.finds,
        total: s.finds.length,
        avg_discount: -11,
        expected_profit: s.finds.reduce((sum, f) => sum + f.profit, 0),
        channels: 15,
        feed: post,
        previous: s.previous,
        has_more_posts: s.feedIndex < seed.FEED_POSTS.length,
      };
    },
  ],
  [
    "POST",
    /^\/market\/sourcing-radar\/next$/,
    ({ s }) => {
      const post = seed.FEED_POSTS[s.feedIndex];
      if (!post) throw new ApiError(409, "no_posts", "Hozircha yangi e’lon yo‘q");
      if (s.feedIndex > 0) {
        const prev = seed.FEED_POSTS[s.feedIndex - 1];
        s.previous.unshift({ time: prev.time, title: prev.prev, value: `${usd(prev.price)} · ${String(prev.diff_pct).replace("-", "−")}%` });
      }
      s.finds = [post.find, ...s.finds.map((f) => ({ ...f, is_new: false }))];
      s.feedIndex += 1;
      log(s, `Raft-Extractor yangi topilma qo‘shdi: ${post.prev}`, usd(post.price));
      return { ok: true };
    },
  ],
  ["POST", /^\/market\/price-from-link$/, ({ body }) => parseText(`iphone 13 pro 256 87% korobka bor ${String(body.url ?? "")}`, "link")],
  ["POST", /^\/input\/parse$/, ({ body }) => parseText(String(body.text ?? ""), "text")],
  [
    "POST",
    /^\/input\/imei$/,
    ({ body }) => {
      const digits = String(body.imei ?? "").replace(/\D/g, "");
      if (digits.length !== 15) throw new ApiError(422, "bad_imei", "IMEI 15 ta raqamdan iborat bo‘lishi kerak");
      return { query: "iPhone 13 Pro · 256 GB", model: "iPhone 13 Pro · 256 GB", detail: "Sierra Blue · IMEI ro‘yxatdan o‘tgan", condition: null, battery: null, box: null, source: "imei" };
    },
  ],
  [
    "POST",
    /^\/input\/voice$/,
    () => {
      throw new ApiError(503, "voice_unavailable", "Ovozli kiritish hozir ishlamayapti. Matn bilan yozing.");
    },
  ],
  [
    "GET",
    /^\/books\/audit$/,
    ({ s }) => ({
      flags: s.flags,
      total_records: s.totalRecords,
      ok_records: s.totalRecords - s.flags.length,
      invoices: seed.SEED_INVOICES,
    }),
  ],
  [
    "POST",
    /^\/books\/audit\/([^/]+)\/(fix|ignore)$/,
    ({ s, m }) => {
      resolveFlag(s, m[1], m[2] as "fix" | "ignore");
      return { ok: true };
    },
  ],
  ["GET", /^\/books\/transactions$/, ({ s }) => ({ items: s.transactions, next_cursor: null, total: s.totalRecords })],
  [
    "POST",
    /^\/books\/upload\/preview$/,
    ({ body }) => {
      const rows = (body.rows as string[][]) ?? [];
      const header = rows[0] ?? [];
      const guess = (name: string) => {
        const n = name.toLowerCase();
        if (/sana|date|дата/.test(n)) return "date";
        if (/summa|jami|amount|сумма/.test(n)) return "amount";
        if (/hamkor|kontragent|partner|контрагент|supplier/.test(n)) return "counterparty";
        if (/nomi|mahsulot|izoh|title|name|наимен|товар/.test(n)) return "title";
        return "skip";
      };
      return {
        filename: String(body.filename ?? "fayl"),
        rows: Math.max(0, rows.length - 1),
        columns: header.map((source) => ({ source, target: guess(source) })),
        sample: rows.slice(1, 5),
        targets: [
          { value: "date", label: "Sana" },
          { value: "title", label: "Nomi" },
          { value: "counterparty", label: "Hamkor" },
          { value: "amount", label: "Summa" },
          { value: "skip", label: "O‘tkazib yuborish" },
        ],
      };
    },
  ],
  [
    "POST",
    /^\/books\/upload$/,
    ({ s, body }) => {
      const count = Number(body.rows ?? 0);
      s.totalRecords += count;
      s.transactions.unshift({
        id: `t-up-${s.totalRecords}`,
        date: DEMO_TODAY,
        title: `Import: ${String(body.filename)}`,
        counterparty: `${count} ta yozuv`,
        amount: "fayldan",
        kind: "purchase",
        source: "Fayl",
      });
      log(s, `Fayl import qilindi: ${String(body.filename)}`, `${count} ta`);
      return { ok: true };
    },
  ],
  ["GET", /^\/books\/budget$/, ({ s }) => s.budget],
  [
    "POST",
    /^\/integrations\/didox\/sync$/,
    ({ s }) => {
      s.synced.didox = nowTime();
      let found = 0;
      s.flags = s.flags.map((f) => {
        if (f.source !== "didox") return f;
        found += 1;
        return { ...f, is_new: true };
      });
      log(s, "Didox’dan 6 ta faktura olindi", "6 ta");
      return {
        new_flags: found,
        message: found ? `Didox: 6 ta faktura olindi, ${found} tasida muammo topildi.` : "Didox: 6 ta faktura olindi, yangi muammo yo‘q.",
      };
    },
  ],
  [
    "POST",
    /^\/integrations\/([^/]+)\/sync$/,
    ({ s, m }) => {
      s.synced[m[1]] = nowTime();
      return { ok: true };
    },
  ],
  ["GET", /^\/exchange\/rfqs\/148$/, ({ s }) => buildRfq(s)],
  [
    "POST",
    /^\/exchange\/quotes\/([^/]+)\/accept$/,
    ({ s, m }) => {
      if (s.deal) throw new ApiError(409, "already_accepted", "Bu so‘rov bo‘yicha taklif allaqachon qabul qilingan");
      const q = buildQuotes(s).find((x) => x.id === m[1]);
      if (!q) throw notFound();
      const deal: Deal = {
        id: "RB-148",
        label: "Raft bitim yozuvi",
        rfq_id: 148,
        supplier: q.supplier,
        buyer: "Chilonzor Phone Market",
        item: "Redmi Note 13 8/256",
        qty: q.qty,
        unit_price: q.price,
        total: q.total,
        date: DEMO_TODAY,
      };
      s.deal = deal;
      s.totalRecords += 1;
      s.transactions.unshift({ id: "t-deal-148", date: DEMO_TODAY, title: "RFQ #148 bitimi", counterparty: q.supplier, amount: usd(q.total), kind: "deal", source: "Raft birja" });
      s.incoming = s.incoming.map((r) => (r.id === 148 ? { ...r, accepted: q.id === "q-techopt" } : r));
      log(s, `${q.supplier} bilan bitim kitobga yozildi`, usd(q.total));
      return deal;
    },
  ],
  [
    "POST",
    /^\/exchange\/quotes\/([^/]+)\/counter$/,
    ({ s, m, body }) => {
      const q = s.quotes.find((x) => x.id === m[1]);
      if (!q) throw notFound();
      const asked = Number(body.price);
      const floor = Math.round(q.price * 0.98);
      const agreed = Math.max(asked, floor);
      q.price = agreed;
      s.rfqNote = asked >= floor ? `${q.supplier} ${usd(agreed)} narxga rozi bo‘ldi.` : `${q.supplier} ${usd(asked)} ga rozi bo‘lmadi, ${usd(agreed)} taklif qildi.`;
      log(s, `Narx kelishildi: ${q.supplier}`, usd(agreed));
      return { ok: true };
    },
  ],
  ["GET", /^\/exchange\/incoming$/, ({ s }) => ({ items: s.incoming, next_cursor: null, total: s.incoming.length })],
  [
    "POST",
    /^\/exchange\/rfqs\/(\d+)\/quotes$/,
    ({ s, m, body }) => {
      const id = Number(m[1]);
      const rfq = s.incoming.find((r) => r.id === id);
      if (!rfq) throw notFound();
      if (id === 148 && s.deal) throw new ApiError(409, "closed", "Xaridor allaqachon taklifni tanlagan");
      const price = Number(body.price);
      rfq.my_quote = price;
      if (id === 148) {
        s.quotes = s.quotes.map((q) =>
          q.id === "q-techopt"
            ? { ...q, price, qty: Number(body.qty ?? q.qty), delivery: String(body.delivery ?? q.delivery), warranty: String(body.warranty ?? q.warranty) }
            : q,
        );
        s.rfqNote = `TechOpt Wholesale yangi taklif yubordi: ${usd(price)}.`;
      }
      log(s, `TechOpt taklif yubordi: so‘rov #${id}`, usd(price * Number(body.qty ?? rfq.qty)));
      return { ok: true };
    },
  ],
  ["GET", /^\/exchange\/lots$/, ({ s }) => ({ items: s.lots, next_cursor: null, total: s.lots.length })],
  ["GET", /^\/exchange\/demand$/, () => seed.DEMAND],
  ["POST", /^\/advisor\/chat$/, ({ s, body }) => chat(s, body)],
  [
    "POST",
    /^\/advisor\/credit\/export$/,
    ({ body }) => {
      const c = annuity(Number(body.amount ?? 300_000_000), Number(body.months ?? 24), 24);
      const content = toCsv([
        ["Oy", "Asosiy qarz", "Foiz", "Qoldiq"],
        ...c.schedule.map((r) => [r.month, Math.round(r.principal), Math.round(r.interest), Math.round(r.balance)]),
      ]);
      const answer: ChatAnswer = {
        blocks: [{ type: "file", name: `kredit-jadvali-${c.months}-oy.csv`, content, note: "Excel’da ochiladi" } satisfies Block],
        chips: [],
      };
      return answer;
    },
  ],
  [
    "POST",
    /^\/advisor\/credit$/,
    ({ body }) => {
      const product = PRODUCT_RATES[String(body.product ?? "business")] ?? PRODUCT_RATES.business;
      const c = annuity(Number(body.amount), Number(body.months), Number(body.rate ?? product.rate));
      return { ...c, product: product.name };
    },
  ],
  ["GET", /^\/advisor\/readiness$/, ({ s }) => readiness(s)],
  [
    "POST",
    /^\/advisor\/loan-applications$/,
    ({ s, body }) => {
      if (body.consent !== true) throw new ApiError(422, "consent_required", "Roziligingiz kerak");
      if (s.applications.some((a) => a.id === "a-chilonzor")) throw new ApiError(409, "exists", "Ariza allaqachon yuborilgan");
      const amount = Number(body.amount ?? 300_000_000);
      const months = Number(body.months ?? 24);
      const c = annuity(amount, months, 24);
      const value = stockSummary(s).value_market;
      const app: LoanApplication = {
        id: "a-chilonzor",
        borrower: "Chilonzor Phone Market",
        stir: "305 412 889",
        product: "Biznes krediti",
        amount,
        months,
        monthly: c.monthly,
        readiness: 78,
        avg_profit: 42_000_000,
        payment_ratio: Math.round((c.monthly / 42_000_000) * 100),
        collateral: `Ombor: ${s.units.length} dona · ${usd(value)}`,
        source: "Raft kitoblari · rozilik 18-noyabr",
        status: "new",
      };
      s.applications.unshift(app);
      log(s, "Kredit arizasi Demo Bank’ka yuborildi", money(amount));
      return app;
    },
  ],
  ["POST", /^\/lender\/valuations$/, ({ s, body }) => valuation(body, s)],
  ["GET", /^\/lender\/collateral$/, ({ s }) => ({ items: s.collateral, next_cursor: null, total: 128 })],
  [
    "GET",
    /^\/lender\/collateral\/summary$/,
    ({ s }) => ({
      portfolio_soum: 4_200_000_000,
      objects: 128,
      avg_ltv: 58,
      ltv_cap: 75,
      watch: 3,
      new_applications: s.applications.filter((a) => a.status === "new").length,
      revalued_at: "bugun 06:00",
    }),
  ],
  ["GET", /^\/lender\/applications$/, ({ s }) => ({ items: s.applications, next_cursor: null, total: s.applications.length })],
  [
    "POST",
    /^\/lender\/applications\/([^/]+)\/decision$/,
    ({ s, m, body }) => {
      const app = s.applications.find((a) => a.id === m[1]);
      if (!app) throw notFound();
      if (app.status !== "new") throw new ApiError(409, "already_decided", "Ariza bo‘yicha qaror qabul qilingan");
      app.status = body.decision === "approve" ? "approved" : "rejected";
      log(s, `Demo Bank qarori: ${app.borrower}`, app.status === "approved" ? "tasdiqlandi" : "rad etildi");
      return { ok: true };
    },
  ],
  ["GET", /^\/partner\/market-report$/, () => seed.SEED_REPORT],
  [
    "GET",
    /^\/integrations$/,
    ({ s }) => ({
      items: seed.SEED_INTEGRATIONS.map((i) => ({ ...i, last_sync: s.synced[i.kind] ?? i.last_sync })),
      next_cursor: null,
      total: seed.SEED_INTEGRATIONS.length,
    }),
  ],
  ["GET", /^\/activity$/, ({ s }) => ({ items: s.activity, next_cursor: null, total: s.activity.length })],
  ["GET", /^\/meta$/, () => seed.META],
  ["GET", /^\/model$/, () => seed.MODEL_CARD],
  ["GET", /^\/search$/, ({ s, query }) => search(s, String(query.q ?? ""))],
];

export async function mockRequest(method: string, path: string, opts: { body?: unknown; query?: Record<string, unknown> | undefined }) {
  await new Promise((r) => setTimeout(r, 60));
  const s = load();
  for (const [verb, pattern, handler] of routes) {
    if (verb !== method) continue;
    const m = pattern.exec(path);
    if (!m) continue;
    const result = handler({ body: (opts.body ?? {}) as Record<string, unknown>, query: opts.query ?? {}, s, m });
    if (method !== "GET") save();
    return JSON.parse(JSON.stringify(result)) as unknown;
  }
  throw new ApiError(404, "not_found", `Fixture yo‘q: ${method} ${path}`);
}
