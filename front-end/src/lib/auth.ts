"use client";

import { useSyncExternalStore } from "react";

export type AccountKind = "business" | "supplier";

export interface Account {
  id: string;
  key: string;
  name: string;
  short: string;
  initials: string;
  role: string;
  roleCode: "owner" | "manager" | "appraiser" | "supplier";
  kind: AccountKind;
  about: string;
}

/** Keys are `demo-<company slug>` / `demo-<user slug>` from the backend seed (app.api.routers.auth.demo_key). */
export const ACCOUNTS: Account[] = [
  {
    id: "chilonzor-owner",
    key: "demo-chilonzor-phone",
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
  if (account.kind === "supplier") return "/birja";
  if (account.roleCode === "appraiser") return "/narxlar?tab=baholash";
  return "/bugun";
}
