"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import * as A from "../backend/advisor";
import { invalidate } from "./shared";

export type ChatTurn = { role: "user" | "assistant"; content: string };

/** POST /advisor/chat — the copilot answers with a sentence, typed blocks and next-step chips. */
export function useChat() {
  return useMutation({
    mutationFn: ({ question, history, context }: { question: string; history: ChatTurn[]; context: { screen: string; selected_ids: string[] } }) =>
      api("/advisor/chat", {
        method: "POST",
        schema: A.ChatOut,
        body: { question, history: history.slice(-10), context: A.chatContext(context) },
        map: A.mapChat,
      }),
  });
}

/** GET /advisor/chat/suggestions — starter questions for an empty chat on this screen. */
export const useChatSuggestions = (screen: string) => {
  const backendScreen = A.chatContext({ screen, selected_ids: [] }).screen;
  return useQuery({
    queryKey: ["chat-suggestions", backendScreen ?? null],
    queryFn: () => api("/advisor/chat/suggestions", { schema: A.ChatSuggestionsOut, query: { screen: backendScreen }, map: (d) => d.questions.map((q) => q.question) }),
    staleTime: 60_000,
  });
};

/* ------------------------------------------------------------------ chips */

/** Backend chip endpoints carry the `/api/v1` prefix; the client adds it itself. */
const stripPrefix = (endpoint: string) => endpoint.replace(/^\/api\/v1(?=\/)/, "");

/** GET chips that open a screen: the screen itself loads the same endpoint. */
const SCREEN_FOR: [RegExp, string][] = [
  [/^\/market\/trend/, "/narxlar?tab=baholash"],
  [/^\/stock\//, "/narxlar"],
  [/^\/decisions/, "/bugun"],
  [/^\/books\/budget/, "/kitoblar?tab=budjet"],
  [/^\/books\//, "/kitoblar"],
  [/^\/exchange\//, "/birja"],
  [/^\/advisor\/lenders/, "/maslahat"],
];

const ANSWER_CHIPS = [/^\/advisor\/credit$/, /^\/advisor\/loan-readiness$/, /^\/advisor\/tax$/, /^\/advisor\/cashflow(\?|$)/];
const ACTION_CHIPS = [/^\/stock\/reprice$/, /^\/stock\/list-on-exchange$/];

export type ChipKind = { kind: "answer" } | { kind: "action" } | { kind: "navigate"; href: string } | { kind: "ask"; question: string };

/** What clicking a chip does; null for chips the UI cannot run (they are not shown). */
export function chipKind(chip: A.Chip): ChipKind | null {
  const path = stripPrefix(chip.action.endpoint);
  const method = chip.action.method;
  const question = chip.action.body?.question;
  if (path === "/advisor/chat" && typeof question === "string") return { kind: "ask", question };
  if (ANSWER_CHIPS.some((re) => re.test(path))) return { kind: "answer" };
  if (method === "POST" && ACTION_CHIPS.some((re) => re.test(path))) return { kind: "action" };
  if (method === "GET") {
    const hit = SCREEN_FOR.find(([re]) => re.test(path));
    if (hit) return { kind: "navigate", href: hit[1] };
  }
  return null;
}

const L = {
  loan: "Kredit",
  payment: "Oylik to‘lov",
  avgNet: "O‘rtacha sof",
  maxLoan: "Maks. kredit",
  readiness: "Kreditga tayyorlik",
  score: "Ball",
  tax: "Soliq",
  turnover: "Aylanma soliq",
  vat: "QQS + foyda",
  saving: "Tejash",
  cashflow: "Pul oqimi",
  income: "Tushum",
  expense: "Xarajat",
  net: "Sof",
};

/** Runs an "answer" or "action" chip against its real endpoint and returns what the chat shows. */
export function useChipAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (chip: A.Chip): Promise<A.Answer> => {
      const path = stripPrefix(chip.action.endpoint);
      const body = chip.action.body ?? undefined;
      if (/^\/advisor\/credit$/.test(path)) {
        const c = await api(path, { method: "POST", schema: A.CreditOut, body });
        return A.creditAnswer(c, { title: L.loan, payment: L.payment, avgNet: L.avgNet, maxLoan: L.maxLoan });
      }
      if (/^\/advisor\/loan-readiness$/.test(path)) return A.readinessAnswer(await api(path, { schema: A.LoanReadinessOut }), L.readiness, L.score);
      if (/^\/advisor\/tax$/.test(path)) return A.taxAnswer(await api(path, { schema: A.TaxOut }), L);
      if (/^\/advisor\/cashflow/.test(path)) return A.cashflowAnswer(await api(path, { schema: A.CashflowOut }), { title: L.cashflow, income: L.income, expense: L.expense, net: L.net, avgNet: L.avgNet });
      if (/^\/stock\/reprice$/.test(path)) {
        const r = await api(path, { method: "POST", schema: A.RepriceOut, body });
        await invalidate(qc, "stock", "dashboard", "decisions", "activity");
        return { text: `${r.updated} ta mahsulot narxi tavsiya narxga o‘tkazildi.`, blocks: [], chips: [] };
      }
      if (/^\/stock\/list-on-exchange$/.test(path)) {
        const r = await api(path, { method: "POST", schema: A.OffersOut, body });
        await invalidate(qc, "stock", "lots", "radar", "dashboard", "activity");
        return { text: `Birjaga ${r.length} ta e’lon chiqarildi.`, blocks: [], chips: [] };
      }
      throw new Error(`Unsupported chip ${chip.action.method} ${chip.action.endpoint}`);
    },
  });
}

/* ------------------------------------------------------------------ credit, readiness, tax */

export const useCredit = (params: { product: A.CreditProduct; principal_uzs: number; months: number }) =>
  useQuery({
    queryKey: ["credit", params],
    queryFn: () => api("/advisor/credit", { method: "POST", schema: A.CreditOut, body: params }),
    placeholderData: keepPreviousData,
  });

export const useReadiness = () => useQuery({ queryKey: ["readiness"], queryFn: () => api("/advisor/loan-readiness", { schema: A.LoanReadinessOut }) });

export const useTax = () => useQuery({ queryKey: ["tax"], queryFn: () => api("/advisor/tax", { schema: A.TaxOut }) });

export const useLenders = (enabled = true) => useQuery({ queryKey: ["lenders"], queryFn: () => api("/advisor/lenders", { schema: A.Lenders }), enabled });

/** The owner's own applications, newest first (owner only on the backend). */
export const useMyLoanApplications = (enabled = true) =>
  useQuery({
    queryKey: ["applications", "mine"],
    queryFn: () => api("/advisor/loan-applications", { schema: A.LoanApplicationsPage, map: (d) => d.items }),
    enabled,
  });

export function useApplyLoan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: A.LoanApplicationIn) => api("/advisor/loan-applications", { method: "POST", schema: A.LoanApplicationDetail, body }),
    onSettled: () => invalidate(qc, "readiness", "applications", "collateral", "activity"),
  });
}
