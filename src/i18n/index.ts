"use client";

import { useSyncExternalStore } from "react";
import { en } from "./en";
import { ru } from "./ru";
import { uz, type Dictionary } from "./uz";

export type Lang = "uz" | "ru" | "en";
const dictionaries: Record<Lang, Dictionary> = { uz, ru, en };
const KEY = "raft_lang";
const listeners = new Set<() => void>();

function current(): Lang {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "ru" || value === "en" ? value : "uz";
  } catch {
    return "uz";
  }
}

export function setLang(lang: Lang) {
  try {
    window.localStorage.setItem(KEY, lang);
  } catch {
    /* falls back to Uzbek on the next load */
  }
  document.documentElement.lang = lang;
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const useLang = () => useSyncExternalStore(subscribe, current, () => "uz" as Lang);

export function useT() {
  return dictionaries[useLang()];
}

export const fill = (text: string, values: Record<string, string | number>) =>
  text.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
