const NBSP = " ";
export const MINUS = "−";

const MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
const MONTHS_SHORT = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
const WEEKDAYS = ["Yakshanba", "Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"];

export function group(value: number) {
  const rounded = Math.round(Math.abs(value));
  return String(rounded).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

function decimal(value: number, digits: number) {
  const fixed = Math.abs(value).toFixed(digits);
  const [whole, frac] = fixed.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return frac ? `${grouped},${frac}` : grouped;
}

function sign(value: number) {
  if (value > 0) return "+";
  if (value < 0) return MINUS;
  return "";
}

export function num(value: number, digits = 0) {
  return `${value < 0 ? MINUS : ""}${decimal(value, digits)}`;
}

export function usd(value: number) {
  return `${value < 0 ? MINUS : ""}$${group(value)}`;
}

export function usdSigned(value: number) {
  return `${sign(value)}$${group(value)}`;
}

export function soum(value: number) {
  return `${value < 0 ? MINUS : ""}${group(value)}${NBSP}so‘m`;
}

export function pct(value: number, digits = 1) {
  return `${value < 0 ? MINUS : ""}${decimal(value, digits)}%`;
}

export function pctSigned(value: number, digits = 1) {
  if (Math.abs(value) < 1e-9) return `±${decimal(0, digits)}%`;
  return `${sign(value)}${decimal(value, digits)}%`;
}

function trimDecimal(value: number) {
  return Math.abs(value - Math.round(value)) < 0.05 ? 0 : 1;
}

/** Amount given in so‘m: `148,2 mln`, `4,2 mlrd`, `450 ming`. */
export function shortNum(value: number) {
  const abs = Math.abs(value);
  const prefix = value < 0 ? MINUS : "";
  if (abs >= 1e9) {
    const v = abs / 1e9;
    return `${prefix}${decimal(v, trimDecimal(v))}${NBSP}mlrd`;
  }
  if (abs >= 1e6) {
    const v = abs / 1e6;
    return `${prefix}${decimal(v, trimDecimal(v))}${NBSP}mln`;
  }
  if (abs >= 1e3) return `${prefix}${decimal(abs / 1e3, 0)}${NBSP}ming`;
  return `${prefix}${decimal(abs, 0)}`;
}

export function shortSoum(value: number) {
  return `${shortNum(value)}${NBSP}so‘m`;
}

/** Value already expressed in millions: `15,9 mln`. */
export function mln(value: number, digits?: number) {
  const d = digits ?? trimDecimal(value);
  return `${value < 0 ? MINUS : ""}${decimal(value, d)}${NBSP}mln`;
}

function parse(date: string | Date) {
  if (date instanceof Date) return date;
  const [y, m, d] = date.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function dateLong(date: string | Date) {
  const d = parse(date);
  return `${d.getUTCDate()}-${MONTHS[d.getUTCMonth()]}`;
}

export function dateShort(date: string | Date) {
  const d = parse(date);
  return `${d.getUTCDate()}-${MONTHS_SHORT[d.getUTCMonth()]}`;
}

export function weekdayDate(date: string | Date) {
  const d = parse(date);
  return `${WEEKDAYS[d.getUTCDay()]}, ${dateLong(d)}`;
}

export function addDays(date: string, days: number) {
  const d = parse(date);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysLabel(value: number) {
  return value >= 45 ? "45+ kun" : `${value} kun`;
}

export function compactUsd(value: number) {
  return value >= 1000 ? `$${Math.round(value / 100) / 10}k`.replace(".", ",") : `$${value}`;
}
