import { DEMO_TODAY, addDays } from "@/lib/format";
import type {
  ActivityRow,
  AuditFlag,
  Collateral,
  Decision,
  Demand,
  FeedPost,
  IncomingRfq,
  Integration,
  InvoiceHistory,
  LoanApplication,
  Lot,
  MarketReport,
  Meta,
  ModelCard,
  RadarFind,
  SalesDay,
  StockUnit,
  Transaction,
  Budget,
  Rating,
  CashMonth,
} from "../schemas";

function rng(seed: number) {
  let t = seed;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

const round5 = (v: number) => Math.round(v / 5) * 5;

export const USD_RATE = 12_800;
export const PLAN = 3500;

export const STRIP_VALUES = [
  3780, 3810, 3120, 3660, 3050, 3600, 3680, 3520, 3790, 3090, 3700, 3680, 3640, 2950, 3560, 3140, 3820, 3200, 3700, 3720, 3260, 3020, 3650, 3210,
  3100, 3060, 3610, 3880, 3630, 3940,
];

export function stripDays() {
  return STRIP_VALUES.map((value, i) => ({ date: addDays(DEMO_TODAY, i - 29), value }));
}

export const TODAY_INDEX = 179;
export const WINDOW_START = 135;
const WINDOW_LEN = 60;

export function salesDays(): SalesDay[] {
  const rand = rng(148);
  const total = TODAY_INDEX + 61;
  const values = Array.from({ length: total }, (_, i) => {
    if (i > TODAY_INDEX) return Math.round(3900 + 240 * Math.sin((i - 180) / 6.5 + 0.3) + (rand() - 0.5) * 90);
    const wave = 220 * Math.sin(i / 8.5) + 120 * Math.sin(i / 3.1);
    return 3620 + wave + (rand() - 0.5) * 300;
  });
  STRIP_VALUES.forEach((v, i) => (values[TODAY_INDEX - 29 + i] = v));

  // Only the older history is scaled, so the line runs through today into the forecast without a jump.
  const inWindow = (i: number) => i >= WINDOW_START && i < WINDOW_START + WINDOW_LEN;
  const older = (i: number) => i < TODAY_INDEX - 29;
  const fixedSum = values.reduce((sum, v, i) => (inWindow(i) && !older(i) ? sum + v : sum), 0);
  const olderSum = values.reduce((sum, v, i) => (inWindow(i) && older(i) ? sum + v : sum), 0);
  const factor = (223_210 - fixedSum) / olderSum;
  for (let i = 0; i < total; i++) if (older(i)) values[i] = Math.round(values[i] * factor);
  const drift = 223_210 - values.reduce((sum, v, i) => (inWindow(i) ? sum + v : sum), 0);
  values[WINDOW_START] += drift;

  const lastYear = values.map((v, i) => v * (0.88 + 0.03 * Math.sin(i / 11)) + (rand() - 0.5) * 120);
  const lyWindow = lastYear.reduce((sum, v, i) => (inWindow(i) ? sum + v : sum), 0);
  const lyFactor = 223_210 / 1.136 / lyWindow;

  return values.map((value, i) => {
    const isForecast = i > TODAY_INDEX;
    const spread = isForecast ? 0.05 + 0.0016 * (i - TODAY_INDEX) : 0;
    const bridge = i === TODAY_INDEX;
    return {
      date: addDays(DEMO_TODAY, i - TODAY_INDEX),
      actual: isForecast ? null : value,
      last_year: Math.round(lastYear[i] * lyFactor),
      forecast: isForecast || bridge ? value : null,
      low: isForecast ? Math.round(value * (1 - spread)) : bridge ? value : null,
      high: isForecast ? Math.round(value * (1 + spread)) : bridge ? value : null,
    };
  });
}

export const CASH_FLOW: CashMonth[] = [
  { month: "Iyn", income: 218, spend: 180, income_ly: 190, spend_ly: 164 },
  { month: "Iyl", income: 226, spend: 186, income_ly: 196, spend_ly: 170 },
  { month: "Avg", income: 232, spend: 190, income_ly: 204, spend_ly: 176 },
  { month: "Sen", income: 240, spend: 196, income_ly: 210, spend_ly: 180 },
  { month: "Okt", income: 252, spend: 208, income_ly: 218, spend_ly: 188 },
  { month: "Noy", income: 245, spend: 201, income_ly: 214, spend_ly: 184 },
];

export function indexSeries() {
  const rand = rng(412);
  const n = 30;
  return Array.from({ length: n }, (_, i) => {
    const t = i / (n - 1);
    const median = i === n - 1 ? 412 : Math.round(425 - 13 * t + (rand() - 0.5) * 5);
    return { median, p25: median - 11 - Math.round(rand() * 3), p75: median + 12 + Math.round(rand() * 3) };
  });
}

const CATALOG: { model: string; attrs: string[]; category: "phone" | "laptop"; market: number }[] = [
  { model: "iPhone 13", attrs: ["128 GB", "A", "89%"], category: "phone", market: 412 },
  { model: "iPhone 13 Pro", attrs: ["256 GB", "A", "87%"], category: "phone", market: 520 },
  { model: "iPhone 14", attrs: ["128 GB", "A", "92%"], category: "phone", market: 540 },
  { model: "iPhone 14 Pro", attrs: ["256 GB", "A", "91%"], category: "phone", market: 875 },
  { model: "iPhone 15", attrs: ["128 GB", "Yangi"], category: "phone", market: 705 },
  { model: "iPhone 15 Pro", attrs: ["256 GB", "A"], category: "phone", market: 985 },
  { model: "Galaxy S23 Ultra", attrs: ["256 GB", "A"], category: "phone", market: 690 },
  { model: "Galaxy S23", attrs: ["128 GB", "A"], category: "phone", market: 480 },
  { model: "Galaxy A55", attrs: ["128 GB", "Yangi"], category: "phone", market: 305 },
  { model: "Redmi Note 13", attrs: ["8/256", "Yangi"], category: "phone", market: 262 },
  { model: "MacBook Air M1", attrs: ["8/256", "A"], category: "laptop", market: 610 },
  { model: "MacBook Air M2", attrs: ["8/256", "A"], category: "laptop", market: 760 },
  { model: "ThinkPad T14", attrs: ["16/512", "B"], category: "laptop", market: 470 },
];

export function seedUnits(): StockUnit[] {
  const rand = rng(80);
  const ratings: Rating[] = [
    ...Array<Rating>(14).fill("over"),
    ...Array<Rating>(9).fill("under"),
    ...Array<Rating>(6).fill("no_data"),
    ...Array<Rating>(51).fill("fair"),
  ];
  for (let i = ratings.length - 1; i > 1; i--) {
    const j = 1 + Math.floor(rand() * i);
    [ratings[i], ratings[j]] = [ratings[j], ratings[i]];
  }

  const units = ratings.map((rating, i): StockUnit => {
    const item = i === 0 ? CATALOG.find((c) => c.model === "MacBook Air M2")! : CATALOG[(i * 5) % CATALOG.length];
    const market = i === 0 ? 760 : round5(item.market * (0.98 + rand() * 0.04));
    const factor =
      rating === "over" ? 1.08 + rand() * 0.08 : rating === "under" ? 0.87 + rand() * 0.05 : rating === "fair" ? 0.97 + rand() * 0.07 : 1;
    const list = i === 0 ? 870 : round5(market * factor);
    const cost = round5(market * (0.82 + rand() * 0.05));
    const noData = rating === "no_data";
    const suggested = noData ? null : rating === "fair" ? list : round5(market * (rating === "over" ? 1.02 : 0.98));
    const days = i === 0 ? 41 : rating === "over" ? 8 + Math.floor(rand() * 26) : 1 + Math.floor(rand() * 30);
    const expected = noData ? null : rating === "over" ? 22 + Math.floor(rand() * 26) : rating === "under" ? 2 + Math.floor(rand() * 3) : 5 + Math.floor(rand() * 10);
    return {
      id: `u-${String(1001 + i)}`,
      model: item.model,
      attrs: item.attrs.join(" · "),
      category: item.category,
      store: i % 3 === 2 ? "Yunusobod" : "Chilonzor",
      list_price: list,
      cost,
      market_price: noData ? null : market,
      vs_market_pct: noData ? null : ((list - market) / market) * 100,
      margin: list - cost,
      days_in_stock: days,
      expected_days: i === 0 ? 45 : expected,
      rating,
      suggested_price: i === 0 ? 775 : suggested,
    };
  });

  // Exactly six aging units, the first being the MacBook from today’s decision.
  let aging = 1;
  for (const unit of units) {
    if (unit.id === "u-1001") continue;
    if (aging < 6 && (unit.rating === "over" || unit.rating === "no_data")) {
      unit.days_in_stock = 42 + aging * 4;
      aging++;
    } else if (unit.days_in_stock >= 40) unit.days_in_stock = 30;
  }

  // Stock at market totals $48 200, the collateral value the bank sees.
  const value = (u: StockUnit) => u.market_price ?? u.list_price;
  // Units without market data absorb the difference, so model prices stay true to the market index.
  let diff = 48_200 - units.reduce((sum, u) => sum + value(u), 0);
  const unpriced = units.filter((u) => u.rating === "no_data");
  for (let i = 0; Math.abs(diff) >= 5; i = (i + 1) % unpriced.length) {
    const d = diff > 0 ? 5 : -5;
    unpriced[i].list_price += d;
    unpriced[i].margin += d;
    diff -= d;
  }
  return units;
}

export const AGING_DAYS = 40;

export const SEED_DECISIONS: Decision[] = [
  {
    id: "d-1",
    kind: "reprice",
    short: "MacBook Air M2 narxi bozordan qimmat",
    amount: "+$95",
    title: "MacBook Air M2 narxini $775 ga tushiring",
    reasons: "41 kundan beri sotilmayapti. 18 ta o‘xshash e’lonning medianasi $760, sizning narxingiz 14% qimmat.",
    evidence: [
      { label: "Hozirgi narx", value: "$870" },
      { label: "Bozor medianasi", value: "$760" },
      { label: "Sotilish vaqti", value: "45+ → 9 kun" },
      { label: "Kutilgan foyda", value: "+$95" },
    ],
    action_label: "Narxni $775 qilish",
    status: "pending",
    flag_id: null,
    unit_id: "u-1001",
  },
  {
    id: "d-2",
    kind: "invoice",
    short: "Faktura #2231: 1 mln ortiqcha",
    amount: "+1 mln",
    title: "Faktura #2231 ni 31 000 000 deb tuzating",
    reasons: "TechOpt fakturasida jami summa 1 mln so‘m ortiq yozilgan. To‘lashdan oldin tuzating.",
    evidence: [
      { label: "Fakturada", value: "32 000 000" },
      { label: "To‘g‘ri hisob", value: "31 000 000" },
      { label: "Farq", value: "1 000 000" },
      { label: "Manba", value: "Didox" },
    ],
    action_label: "31 000 000 deb tuzatish",
    status: "pending",
    flag_id: "f-2231",
    unit_id: null,
  },
  {
    id: "d-3",
    kind: "raise",
    short: "Galaxy S23 arzon qo‘yilgan",
    amount: "+$40",
    title: "Galaxy S23 narxini $470 ga ko‘taring",
    reasons: "Narxingiz bozordan 9% past. Bu model 3 kunda sotilmoqda, shoshilish shart emas.",
    evidence: [
      { label: "Hozirgi narx", value: "$430" },
      { label: "Bozor medianasi", value: "$480" },
      { label: "Sotilish vaqti", value: "3 → 5 kun" },
      { label: "Kutilgan foyda", value: "+$40" },
    ],
    action_label: "Narxni $470 qilish",
    status: "pending",
    flag_id: null,
    unit_id: null,
  },
  {
    id: "d-4",
    kind: "buy",
    short: "iPhone 14 Pro bozordan 11% arzon",
    amount: "+$70",
    title: "iPhone 14 Pro 256GB ni $780 ga oling",
    reasons: "Chilonzorda e’lon qilingan, bozor medianasi $875. Bu model o‘rtacha 4 kunda sotiladi.",
    evidence: [
      { label: "E’lon narxi", value: "$780" },
      { label: "Bozor medianasi", value: "$875" },
      { label: "Sotilish vaqti", value: "4 kun" },
      { label: "Kutilgan foyda", value: "+$70" },
    ],
    action_label: "Sotuvchiga yozish",
    status: "pending",
    flag_id: null,
    unit_id: null,
  },
];

const find = (
  id: number,
  title: string,
  meta: string,
  category: RadarFind["category"],
  price: number,
  market: number,
  profit: number,
  days: number,
  channel: string,
  age: string,
): RadarFind => ({
  id: `r-${id}`,
  title,
  meta,
  category,
  price,
  market,
  diff_pct: ((price - market) / market) * 100,
  profit,
  days,
  channel,
  age,
  url: `https://t.me/${channel.replace("@", "")}/${4100 + id}`,
  is_new: false,
});

export const SEED_FINDS: RadarFind[] = [
  find(1, "iPhone 14 Pro 256GB", "A · 91% · Chilonzor", "phone", 780, 875, 70, 4, "@iphone_bozor_uz", "12 daqiqa oldin"),
  find(2, "MacBook Air M1 8/256", "Yangi kabi · Yunusobod", "laptop", 540, 610, 55, 6, "@macbook_tashkent", "25 daqiqa oldin"),
  find(3, "Galaxy S23 Ultra 256GB", "A · Sergeli", "phone", 610, 690, 60, 5, "@samsung_uz_market", "40 daqiqa oldin"),
  find(4, "iPhone 13 128GB", "B · 86% · Chilonzor", "phone", 355, 400, 32, 3, "@iphone_bozor_uz", "1 soat oldin"),
  find(5, "Chevrolet Cobalt 2021", "pozitsiya 4 · 62 000 km", "car", 10300, 11400, 650, 12, "@avto_bozor_toshkent", "1 soat oldin"),
  find(6, "Redmi Note 13 8/256", "Yangi · 10 dona ulgurji", "phone", 231, 262, 210, 7, "@optom_telefon", "2 soat oldin"),
  find(7, "Lenovo ThinkPad T14", "B · Mirzo Ulug‘bek", "laptop", 420, 470, 38, 9, "@noutbuk_bozor", "3 soat oldin"),
  find(8, "AirPods Pro 2", "Yangi · Chilonzor", "phone", 148, 165, 9, 3, "@iphone_bozor_uz", "3 soat oldin"),
  find(9, "Galaxy A55 128GB", "Yangi · Sergeli", "phone", 272, 305, 10, 4, "@samsung_uz_market", "3 soat oldin"),
  find(10, "Redmi 13C 128GB", "Yangi · Yakkasaroy", "phone", 112, 126, 7, 5, "@optom_telefon", "4 soat oldin"),
  find(11, "iPhone 12 64GB", "B · 83% · Olmazor", "phone", 228, 255, 9, 4, "@iphone_bozor_uz", "4 soat oldin"),
  find(12, "Apple Watch SE 44", "A · Yunusobod", "phone", 142, 160, 8, 6, "@iphone_bozor_uz", "4 soat oldin"),
  find(13, "Galaxy Tab A9", "Yangi · Chilonzor", "phone", 158, 176, 7, 7, "@samsung_uz_market", "5 soat oldin"),
  find(14, "HP 250 G9", "A · Sergeli", "laptop", 305, 342, 9, 8, "@noutbuk_bozor", "5 soat oldin"),
  find(15, "Acer Aspire 5", "B · Yashnobod", "laptop", 268, 300, 8, 9, "@noutbuk_bozor", "6 soat oldin"),
  find(16, "Honor X8b", "Yangi · Mirobod", "phone", 176, 198, 8, 6, "@optom_telefon", "6 soat oldin"),
  find(17, "Poco X6 Pro", "A · Chilonzor", "phone", 248, 278, 9, 5, "@optom_telefon", "7 soat oldin"),
  find(18, "Vivo Y36", "Yangi · Olmazor", "phone", 138, 155, 6, 6, "@optom_telefon", "7 soat oldin"),
  find(19, "Tecno Spark 20", "Yangi · Yunusobod", "phone", 104, 117, 5, 5, "@optom_telefon", "8 soat oldin"),
  find(20, "iPad 9 64GB", "A · Yakkasaroy", "phone", 232, 260, 9, 6, "@iphone_bozor_uz", "9 soat oldin"),
  find(21, "Asus VivoBook 15", "B · Bektemir", "laptop", 286, 320, 8, 10, "@noutbuk_bozor", "10 soat oldin"),
  find(22, "Xiaomi Pad 6", "A · Sergeli", "phone", 246, 276, 7, 7, "@optom_telefon", "11 soat oldin"),
  find(23, "Galaxy Buds 2 Pro", "Yangi · Chilonzor", "phone", 92, 104, 6, 4, "@samsung_uz_market", "12 soat oldin"),
];

export const FEED_POSTS: (FeedPost & { find: RadarFind; prev: string })[] = [
  {
    id: "p-1",
    channel: "@iphone_bozor_uz",
    time: "12:41",
    text: "iphone 13 pro 256 87% korobka bor, 6 mln 300 ga, Chilonzor. Tel: yashirildi",
    latency_s: 0.8,
    fields: [
      { label: "Kategoriya", value: "Telefon" },
      { label: "Model", value: "iPhone 13 Pro 256GB" },
      { label: "Holat", value: "B · quti bor" },
      { label: "Batareya", value: "87%" },
      { label: "Narx", value: "6 300 000 so‘m ≈ $490" },
      { label: "Tuman", value: "Chilonzor" },
    ],
    median_label: "Bozor medianasi $540 · 47 e’lon",
    price: 490,
    diff_pct: -9,
    find: { ...find(24, "iPhone 13 Pro 256GB", "B · 87% · Chilonzor", "phone", 490, 540, 38, 5, "@iphone_bozor_uz", "hozir"), is_new: true },
    prev: "iPhone 13 Pro 256GB",
  },
  {
    id: "p-2",
    channel: "@samsung_uz_market",
    time: "12:44",
    text: "S24 ultra 512 ideal holatda, karobka, chek bor. 11 mln 500, Yunusobod",
    latency_s: 0.7,
    fields: [
      { label: "Kategoriya", value: "Telefon" },
      { label: "Model", value: "Galaxy S24 Ultra 512GB" },
      { label: "Holat", value: "A · quti bor" },
      { label: "Batareya", value: "ma’lum emas" },
      { label: "Narx", value: "11 500 000 so‘m ≈ $898" },
      { label: "Tuman", value: "Yunusobod" },
    ],
    median_label: "Bozor medianasi $1 010 · 22 e’lon",
    price: 898,
    diff_pct: -11,
    find: { ...find(25, "Galaxy S24 Ultra 512GB", "A · Yunusobod", "phone", 898, 1010, 84, 6, "@samsung_uz_market", "hozir"), is_new: true },
    prev: "Galaxy S24 Ultra 512GB",
  },
  {
    id: "p-3",
    channel: "@avto_bozor_toshkent",
    time: "12:47",
    text: "Gentra 2022 3 pozitsiya, 41 ming km, kraska toza. 12 600 $ kelishamiz. Sergeli",
    latency_s: 0.9,
    fields: [
      { label: "Kategoriya", value: "Avto" },
      { label: "Model", value: "Chevrolet Gentra 2022" },
      { label: "Holat", value: "pozitsiya 3" },
      { label: "Yurgani", value: "41 000 km" },
      { label: "Narx", value: "$12 600" },
      { label: "Tuman", value: "Sergeli" },
    ],
    median_label: "Bozor medianasi $13 700 · 31 e’lon",
    price: 12600,
    diff_pct: -8,
    find: { ...find(26, "Chevrolet Gentra 2022", "pozitsiya 3 · 41 000 km", "car", 12600, 13700, 720, 11, "@avto_bozor_toshkent", "hozir"), is_new: true },
    prev: "Chevrolet Gentra 2022",
  },
];

export const SEED_PREVIOUS = [
  { time: "12:38", title: "Galaxy A55 128GB", value: "$300 · ±0%" },
  { time: "12:35", title: "Cobalt 2020 poz 4", value: "$9 900 · +3%" },
];

export const SEED_LOTS: Lot[] = [
  { id: "l-1", title: "Redmi Note 13 8/256", seller: "Sam Xit Trade", qty: 40, unit_price: 244, market: 262, diff_pct: -6.9, location: "Chilonzor", kind: "Ulgurji" },
  { id: "l-2", title: "iPhone 13 128GB, A holat", seller: "TechOpt Wholesale", qty: 12, unit_price: 392, market: 412, diff_pct: -4.9, location: "Yunusobod", kind: "Ulgurji" },
  { id: "l-3", title: "Galaxy A55 128GB", seller: "MobiGross", qty: 25, unit_price: 289, market: 305, diff_pct: -5.2, location: "Sergeli", kind: "Ulgurji" },
  { id: "l-4", title: "MacBook Air M1 8/256", seller: "Smart Store Sergeli", qty: 6, unit_price: 625, market: 610, diff_pct: 2.5, location: "Sergeli", kind: "Ortiqcha qoldiq" },
  { id: "l-5", title: "AirPods Pro 2", seller: "Gadget House", qty: 30, unit_price: 151, market: 165, diff_pct: -8.5, location: "Mirobod", kind: "Ortiqcha qoldiq" },
  { id: "l-6", title: "ThinkPad T14 16/512", seller: "Yunusobod Mobile", qty: 8, unit_price: 468, market: 470, diff_pct: -0.4, location: "Yunusobod", kind: "Ortiqcha qoldiq" },
];

export const DEMAND: Demand = {
  districts: [
    { name: "Chilonzor", count: 34, models: "Redmi Note 13, iPhone 13" },
    { name: "Yunusobod", count: 27, models: "iPhone 15, AirPods Pro 2" },
    { name: "Sergeli", count: 19, models: "Galaxy A55, Redmi 13C" },
    { name: "Yakkasaroy", count: 12, models: "MacBook Air M2" },
    { name: "Mirzo Ulug‘bek", count: 10, models: "iPhone 14, Galaxy S24" },
  ],
  models: [
    { name: "Redmi Note 13 8/256", requests: 21, change_pct: 18 },
    { name: "iPhone 15 128GB", requests: 17, change_pct: 9 },
    { name: "iPhone 13 128GB", requests: 14, change_pct: -6 },
    { name: "Galaxy A55 128GB", requests: 12, change_pct: 4 },
    { name: "MacBook Air M2", requests: 8, change_pct: 12 },
  ],
};

const Q = [
  [0, 241],
  [0.059, 249],
  [0.25, 251],
  [0.5, 262],
  [0.75, 271],
  [0.95, 279],
  [1, 287],
] as const;

export function marketDots() {
  return Array.from({ length: 85 }, (_, i) => {
    const q = (i + 0.5) / 85;
    const k = Q.findIndex(([p]) => p >= q);
    const [p0, v0] = Q[k - 1];
    const [p1, v1] = Q[k];
    return Math.round(v0 + ((q - p0) / (p1 - p0)) * (v1 - v0));
  });
}

export interface SeedQuote {
  id: string;
  supplier: string;
  verification: string;
  price: number;
  qty: number;
  delivery: string;
  warranty: string;
  why: { text: string; warn: boolean }[];
}

export const SEED_QUOTES: SeedQuote[] = [
  {
    id: "q-samxit",
    supplier: "Sam Xit Trade",
    verification: "STIR tasdiqlangan · 18 bitim · 4,6 reyting",
    price: 249,
    qty: 20,
    delivery: "ertaga",
    warranty: "3 oy",
    why: [
      { text: "Uch taklif ichida eng arzoni", warn: false },
      { text: "Ertaga yetkazadi, muddatingizdan 3 kun oldin", warn: false },
      { text: "20 donaning barchasi omborda bor", warn: false },
      { text: "E’tibor bering: kafolat 3 oy (TechOpt’da 6 oy)", warn: true },
    ],
  },
  {
    id: "q-techopt",
    supplier: "TechOpt Wholesale",
    verification: "64 bitim · 4,9",
    price: 262,
    qty: 20,
    delivery: "payshanba",
    warranty: "6 oy",
    why: [
      { text: "Eng uzoq kafolat: 6 oy", warn: false },
      { text: "64 ta yakunlangan bitim", warn: false },
      { text: "Payshanba kuni yetkazadi", warn: false },
    ],
  },
  {
    id: "q-mobigross",
    supplier: "MobiGross",
    verification: "9 bitim · 4,4",
    price: 271,
    qty: 15,
    delivery: "juma",
    warranty: "3 oy",
    why: [{ text: "Faqat 15 dona bor", warn: true }],
  },
];

export const SEED_INCOMING: IncomingRfq[] = [
  { id: 148, title: "20 dona Redmi Note 13 8/256", spec: "Chilonzor, juma gacha", buyer: "Chilonzor Phone Market", due: "juma", qty: 20, market_unit: 262, p25: 251, p75: 271, listings: 85, time_left: "2 soat qoldi", urgent: true, my_quote: 262, accepted: false },
  { id: 151, title: "10 dona iPhone 15 128GB", spec: "Yunusobod, 22-noyabr gacha", buyer: "Yunusobod Mobile", due: "22-noyabr", qty: 10, market_unit: 705, p25: 688, p75: 722, listings: 41, time_left: "1 kun", urgent: false, my_quote: null, accepted: false },
  { id: 152, title: "5 dona MacBook Air M2", spec: "Sergeli, 25-noyabr gacha", buyer: "Smart Store Sergeli", due: "25-noyabr", qty: 5, market_unit: 760, p25: 738, p75: 785, listings: 18, time_left: "2 kun", urgent: false, my_quote: null, accepted: false },
  { id: 155, title: "30 dona AirPods Pro 2", spec: "Mirobod, 24-noyabr gacha", buyer: "Gadget House", due: "24-noyabr", qty: 30, market_unit: 165, p25: 158, p75: 172, listings: 63, time_left: "3 kun", urgent: false, my_quote: null, accepted: false },
  { id: 156, title: "8 dona Galaxy A55", spec: "Chilonzor, 26-noyabr gacha", buyer: "Chilonzor Phone Market", due: "26-noyabr", qty: 8, market_unit: 305, p25: 294, p75: 316, listings: 52, time_left: "4 kun", urgent: false, my_quote: null, accepted: false },
];

export const SEED_FLAGS: AuditFlag[] = [
  {
    id: "f-2231",
    title: "Jami summa noto‘g‘ri",
    subtitle: "Faktura #2231 · TechOpt",
    amount: "1 mln so‘m",
    crumb: "Faktura #2231 · TechOpt Wholesale",
    heading: "Fakturada jami summa 1 mln so‘m ortiqcha",
    explain: "Miqdor va narxni ko‘paytirganda boshqa summa chiqadi. Yetkazib beruvchiga to‘lashdan oldin tuzating.",
    calc: [
      { label: "Mahsulot", value: "iPhone 13 128GB", bad: false },
      { label: "Miqdor", value: "5 dona", bad: false },
      { label: "Narx", value: "6 200 000 so‘m", bad: false },
      { label: "To‘g‘ri hisob", value: "31 000 000 so‘m", bad: false },
      { label: "Fakturada", value: "32 000 000 so‘m", bad: true },
    ],
    note: "TechOpt’ning oktyabrdagi 2 ta fakturasida ham jami summa ortiq yozilgan edi. Keyingi fakturalarni avtomatik tekshirib boramiz.",
    invoice: {
      title: "Hisob-faktura № 2231",
      meta: "12.11.2026 · TechOpt Wholesale",
      lines: [
        { label: "iPhone 13 128GB", value: "5 dona" },
        { label: "Narx", value: "6 200 000" },
      ],
      total: "32 000 000",
    },
    chart: true,
    fix_label: "31 000 000 deb tuzatish",
    ignore_label: "Bu to‘g‘ri, o‘tkazib yuborish",
    source: "didox",
    is_new: false,
  },
  {
    id: "f-internet",
    title: "Takroriy to‘lov",
    subtitle: "Internet · 14-noyabr",
    amount: "450 ming",
    crumb: "Xarajat · Internet provayder",
    heading: "Internet uchun to‘lov ikki marta yozilgan",
    explain: "Bir xil summa bir kunda ikki marta o‘tkazilgan. Bittasini o‘chirsangiz, xarajatlar to‘g‘ri ko‘rinadi.",
    calc: [
      { label: "Birinchi yozuv", value: "450 000 so‘m · 09:14", bad: false },
      { label: "Ikkinchi yozuv", value: "450 000 so‘m · 09:16", bad: true },
      { label: "Oylik tarif", value: "450 000 so‘m", bad: false },
    ],
    note: "So‘nggi 6 oyda bu provayderga oyiga bir marta to‘lov qilingan.",
    invoice: null,
    chart: false,
    fix_label: "Takroriy yozuvni o‘chirish",
    ignore_label: "Ikkalasi ham to‘g‘ri",
    source: "billz",
    is_new: false,
  },
  {
    id: "f-power",
    title: "Ortiqcha nol bo‘lishi mumkin",
    subtitle: "Elektr · 18,4 mln (odatda 1,84)",
    amount: "16,5 mln",
    crumb: "Xarajat · Elektr energiyasi",
    heading: "Elektr xarajatida ortiqcha nol bo‘lishi mumkin",
    explain: "Summa odatdagidan 10 baravar katta. Kiritishda xato ketgan bo‘lishi ehtimoli yuqori.",
    calc: [
      { label: "Yozilgan summa", value: "18 400 000 so‘m", bad: true },
      { label: "O‘rtacha oylik", value: "1 840 000 so‘m", bad: false },
      { label: "Farq", value: "16 560 000 so‘m", bad: false },
    ],
    note: "So‘nggi 6 oyda elektr xarajati 1,7 mln va 2,0 mln so‘m oralig‘ida bo‘lgan.",
    invoice: null,
    chart: false,
    fix_label: "1 840 000 deb tuzatish",
    ignore_label: "Summa to‘g‘ri",
    source: "manual",
    is_new: false,
  },
  {
    id: "f-a55",
    title: "Bozordan qimmat xarid",
    subtitle: "3 × Samsung A55 · +14%",
    amount: "1,8 mln",
    crumb: "Xarid · Faktura #2228 · MobiGross",
    heading: "Samsung A55 bozordan 14% qimmat olingan",
    explain: "Shu kuni bozor medianasi $305 edi, faktura bo‘yicha $348 dan olingan. Keyingi xaridda boshqa taklif so‘rang.",
    calc: [
      { label: "Miqdor", value: "3 dona", bad: false },
      { label: "Xarid narxi", value: "$348", bad: true },
      { label: "Bozor medianasi", value: "$305", bad: false },
      { label: "Ortiqcha to‘lov", value: "1 800 000 so‘m", bad: false },
    ],
    note: "MobiGross so‘nggi 3 xaridda bozordan o‘rtacha 9% qimmat bergan.",
    invoice: null,
    chart: false,
    fix_label: "Yetkazib beruvchiga belgilash",
    ignore_label: "Narx kelishilgan",
    source: "didox",
    is_new: false,
  },
];

export const SEED_INVOICES: InvoiceHistory[] = [
  { id: "#2140", date: "12-iyl", over: 0, current: false },
  { id: "#2158", date: "29-iyl", over: 0, current: false },
  { id: "#2171", date: "14-avg", over: 0, current: false },
  { id: "#2189", date: "3-sen", over: 0, current: false },
  { id: "#2203", date: "7-okt", over: 0.6, current: false },
  { id: "#2214", date: "24-okt", over: 1.2, current: false },
  { id: "#2222", date: "2-noy", over: 0, current: false },
  { id: "#2231", date: "12-noy", over: 1.0, current: true },
];

export const SEED_TRANSACTIONS: Transaction[] = [
  { id: "t-1", date: "2026-11-17", title: "Kunlik savdo", counterparty: "BILLZ kassa", amount: "$3 940", kind: "sale", source: "BILLZ" },
  { id: "t-2", date: "2026-11-16", title: "Kunlik savdo", counterparty: "BILLZ kassa", amount: "$3 630", kind: "sale", source: "BILLZ" },
  { id: "t-3", date: "2026-11-16", title: "RFQ #147 bitimi", counterparty: "TechOpt Wholesale", amount: "$4 120", kind: "deal", source: "Raft birja" },
  { id: "t-4", date: "2026-11-14", title: "Internet", counterparty: "Uztelecom", amount: "450 000 so‘m", kind: "expense", source: "Bank" },
  { id: "t-5", date: "2026-11-12", title: "Faktura #2231", counterparty: "TechOpt Wholesale", amount: "32 000 000 so‘m", kind: "purchase", source: "Didox" },
  { id: "t-6", date: "2026-11-10", title: "Do‘kon ijarasi", counterparty: "Chilonzor savdo majmuasi", amount: "12 000 000 so‘m", kind: "expense", source: "Bank" },
  { id: "t-7", date: "2026-11-08", title: "Faktura #2228", counterparty: "MobiGross", amount: "13 360 000 so‘m", kind: "purchase", source: "Didox" },
  { id: "t-8", date: "2026-11-05", title: "Instagram reklama", counterparty: "Meta", amount: "4 200 000 so‘m", kind: "expense", source: "Bank" },
];

export const SEED_BUDGET: Budget = {
  month: "noyabr",
  limit: 240,
  spent: 148,
  day: 17,
  days_in_month: 30,
  burn: { ads: 1.4, purchases: 6.8, other: 2.0 },
  categories: [
    { name: "Xaridlar", plan: 150, fact: 98 },
    { name: "Ish haqi", plan: 36, fact: 18 },
    { name: "Reklama", plan: 24, fact: 16 },
    { name: "Ijara", plan: 18, fact: 12 },
    { name: "Boshqa", plan: 12, fact: 4 },
  ],
};

export const SEED_APPLICATIONS: LoanApplication[] = [
  {
    id: "a-sergeli",
    borrower: "Sergeli Avto",
    stir: "307 118 240",
    product: "Avto kredit",
    amount: 1_200_000_000,
    months: 36,
    monthly: 47_100_000,
    readiness: 71,
    avg_profit: 118_000_000,
    payment_ratio: 40,
    collateral: "Avtomobillar: 14 dona · $168 400",
    source: "Raft kitoblari · rozilik 16-noyabr",
    status: "new",
  },
];

export const SEED_COLLATERAL: Collateral[] = [
  { id: "c-1", object: "Chevrolet Cobalt 2021", borrower: "Sergeli Avto", value: 11400, change_30d: -1.8, ltv: 61, status: "normal" },
  { id: "c-2", object: "Ombor: 80 dona", borrower: "Chilonzor Phone Market", value: 48200, change_30d: -3.1, ltv: 58, status: "normal" },
  { id: "c-3", object: "Kvartira, Yunusobod, 3 xona", borrower: "Uy Invest", value: 96000, change_30d: 0.9, ltv: 52, status: "normal" },
  { id: "c-4", object: "Chevrolet Malibu 2 2019", borrower: "Sergeli Avto", value: 16900, change_30d: -4.6, ltv: 72, status: "watch" },
  { id: "c-5", object: "Ombor: 40 noutbuk", borrower: "TechOpt Wholesale", value: 31500, change_30d: -6.2, ltv: 78, status: "breach" },
  { id: "c-6", object: "Damas 2022", borrower: "Avto Lider", value: 7200, change_30d: -0.5, ltv: 49, status: "normal" },
];

export const SEED_REPORT: MarketReport = {
  week: "11–17-noyabr",
  rows: [
    { model: "iPhone 13 128GB", district: "Chilonzor", median: 412, change_7d: -3.1, listings: 214, trend: [425, 424, 421, 419, 416, 414, 412] },
    { model: "iPhone 14 Pro 256GB", district: "Yunusobod", median: 875, change_7d: -1.2, listings: 96, trend: [886, 884, 882, 880, 878, 876, 875] },
    { model: "Galaxy S23 Ultra 256GB", district: "Sergeli", median: 690, change_7d: 0.6, listings: 73, trend: [686, 687, 688, 690, 689, 690, 690] },
    { model: "Redmi Note 13 8/256", district: "Chilonzor", median: 262, change_7d: -0.8, listings: 85, trend: [264, 264, 263, 263, 263, 262, 262] },
    { model: "MacBook Air M2 8/256", district: "Yakkasaroy", median: 760, change_7d: -2.2, listings: 18, trend: [777, 774, 770, 768, 765, 762, 760] },
    { model: "Chevrolet Cobalt 2021", district: "Sergeli", median: 11400, change_7d: -0.6, listings: 36, trend: [11470, 11460, 11450, 11440, 11420, 11410, 11400] },
    { model: "Chevrolet Gentra 2022", district: "Yashnobod", median: 13700, change_7d: 0.4, listings: 31, trend: [13640, 13650, 13660, 13670, 13680, 13690, 13700] },
  ],
};

export const SEED_INTEGRATIONS: Integration[] = [
  { kind: "telegram", name: "Telegram", mode: "live", detail: "15 kanal, bot xabarlari", last_sync: "hozir" },
  { kind: "didox", name: "Didox", mode: "test", detail: "Elektron fakturalar", last_sync: "09:12" },
  { kind: "soliq", name: "Soliq", mode: "test", detail: "STIR tekshiruvi", last_sync: "kecha" },
  { kind: "billz", name: "BILLZ", mode: "test", detail: "Ombor va kassa", last_sync: "08:40" },
  { kind: "1c", name: "1C", mode: "test", detail: "Hisob eksporti", last_sync: "15-noyabr" },
  { kind: "bank", name: "Bank", mode: "test", detail: "Hisob ko‘chirmasi", last_sync: "07:30" },
];

export const SEED_ACTIVITY: ActivityRow[] = [
  { time: "09:12", text: "Didox’dan 6 ta faktura olindi", value: "6 ta", actor: "Tizim" },
  { time: "08:40", text: "BILLZ ombori sinxronlandi", value: "80 dona", actor: "Tizim" },
  { time: "07:55", text: "Telegram: 1 284 e’lon tahlil qilindi", value: "1 284", actor: "Tizim" },
  { time: "kecha", text: "TechOpt bilan bitim kitobga yozildi", value: "$4 120", actor: "Ega" },
  { time: "kecha", text: "Sam Xit taklifi qabul qilindi", value: "RFQ #147", actor: "Menejer" },
];

export const META: Meta = {
  stores: [
    { name: "Chilonzor", address: "Chilonzor tumani, Qatortol ko‘chasi", units: 54 },
    { name: "Yunusobod", address: "Yunusobod tumani, Amir Temur shoh ko‘chasi", units: 26 },
  ],
  users: [
    { name: "Do‘kon egasi", role: "Ega", last_seen: "hozir" },
    { name: "Menejer", role: "Menejer", last_seen: "09:40" },
    { name: "Baholovchi", role: "Baholovchi", last_seen: "kecha" },
  ],
};

export const MODEL_CARD: ModelCard = {
  name: "Raft-Extractor",
  base: "Llama-3.1-8B-Instruct-Uz asosida, LoRA bilan o‘qitilgan · Ollama orqali lokal ishlaydi · faqat mahsulot tahlili",
  dataset: "Haqiqiy e’lonlardagi test to‘plami",
  sample: true,
  metrics: [
    { name: "Valid JSON", raft: "99%", cloud: "97%", rule: "100%" },
    { name: "Kategoriya", raft: "97%", cloud: "95%", rule: "88%" },
    { name: "Brend va model", raft: "91%", cloud: "89%", rule: "62%" },
    { name: "Narx", raft: "95%", cloud: "93%", rule: "71%" },
    { name: "Valyuta", raft: "98%", cloud: "97%", rule: "84%" },
    { name: "Kechikish", raft: "0,8 s", cloud: "1,6 s", rule: "0,01 s" },
    { name: "Narx / 1000 e’lon", raft: "$0", cloud: "~$0,4", rule: "$0" },
  ],
};

export const PRICE_MODELS = [
  { keys: ["13 pro", "13pro"], model: "iPhone 13 Pro · 256 GB", detail: "Sierra Blue", median: 520, low: 430, high: 610, listings: 47, days: 6 },
  { keys: ["iphone 13", "ayfon 13"], model: "iPhone 13 · 128 GB", detail: "Midnight", median: 412, low: 350, high: 480, listings: 214, days: 4 },
  { keys: ["14 pro"], model: "iPhone 14 Pro · 256 GB", detail: "Deep Purple", median: 875, low: 780, high: 960, listings: 96, days: 4 },
  { keys: ["s23 ultra", "s23"], model: "Galaxy S23 Ultra · 256 GB", detail: "Phantom Black", median: 690, low: 610, high: 770, listings: 73, days: 5 },
  { keys: ["redmi", "note 13"], model: "Redmi Note 13 · 8/256", detail: "Graphite", median: 262, low: 231, high: 287, listings: 85, days: 5 },
  { keys: ["macbook", "air m2", "m2"], model: "MacBook Air M2 · 8/256", detail: "Midnight", median: 760, low: 690, high: 870, listings: 18, days: 9 },
];
