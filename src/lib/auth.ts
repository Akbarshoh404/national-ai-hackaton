"use client";

import { useSyncExternalStore } from "react";

export type AccountKind = "business" | "supplier" | "bank" | "bazaar";

export interface Account {
  id: string;
  key: string;
  name: string;
  short: string;
  initials: string;
  role: string;
  roleCode: "owner" | "manager" | "appraiser" | "supplier" | "lender" | "bazaar";
  kind: AccountKind;
  about: string;
}

/** Keys follow the master prompt; confirm them against the backend seed once it runs. */
export const ACCOUNTS: Account[] = [
  {
    id: "chilonzor-owner",
    key: "demo-chilonzor",
    name: "Chilonzor Phone Market",
    short: "Chilonzor Phone",
    initials: "CP",
    role: "Do‘kon egasi",
    roleCode: "owner",
    kind: "business",
    about: "Barcha ekranlar: qarorlar, ombor, kitoblar, birja va kredit arizasi.",
  },
  {
    id: "chilonzor-manager",
    key: "demo-chilonzor-manager",
    name: "Chilonzor Phone Market",
    short: "Chilonzor Phone",
    initials: "CP",
    role: "Menejer",
    roleCode: "manager",
    kind: "business",
    about: "Ombor, narxlar va birja. Kredit arizasini faqat ega yuboradi.",
  },
  {
    id: "chilonzor-appraiser",
    key: "demo-chilonzor-appraiser",
    name: "Chilonzor Phone Market",
    short: "Chilonzor Phone",
    initials: "CP",
    role: "Baholovchi",
    roleCode: "appraiser",
    kind: "business",
    about: "Trade-in baholash va ombordagi narxlar.",
  },
  {
    id: "techopt",
    key: "demo-techopt",
    name: "TechOpt Wholesale",
    short: "TechOpt",
    initials: "TO",
    role: "Yetkazib beruvchi",
    roleCode: "supplier",
    kind: "supplier",
    about: "Kelgan so‘rovlar, taklif yuborish va tumanlar bo‘yicha talab.",
  },
  {
    id: "demo-bank",
    key: "demo-demo-bank",
    name: "Demo Bank",
    short: "Demo Bank",
    initials: "DB",
    role: "Bank",
    roleCode: "lender",
    kind: "bank",
    about: "Kredit arizalari, garov qiymati va garov portfeli.",
  },
  {
    id: "bozor-admin",
    key: "demo-bozor-admin",
    name: "Malika bozori",
    short: "Malika bozori",
    initials: "MB",
    role: "Bozor ma’muriyati",
    roleCode: "bazaar",
    kind: "bazaar",
    about: "Model va tumanlar bo‘yicha bozor hisoboti.",
  },
];

const STORAGE_KEY = "raft_account";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function getAccount(): Account | null {
  if (typeof window === "undefined") return null;
  const id = read();
  return ACCOUNTS.find((a) => a.id === id) ?? null;
}

export function setAccount(id: string | null) {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: the session simply stays signed out */
  }
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  window.addEventListener("storage", fn);
  return () => {
    listeners.delete(fn);
    window.removeEventListener("storage", fn);
  };
}

/** `undefined` while hydrating, `null` when signed out. */
export function useAccount(): Account | null | undefined {
  return useSyncExternalStore(subscribe, getAccount, () => undefined);
}

export function homeFor(account: Account) {
  if (account.kind === "bank" || account.kind === "bazaar") return "/partner";
  if (account.kind === "supplier") return "/birja";
  return "/bugun";
}
