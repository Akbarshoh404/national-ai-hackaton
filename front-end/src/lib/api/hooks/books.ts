"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BAudit,
  BAuditFix,
  BBooksSummary,
  BBudget,
  BInvoiceResult,
  BOk,
  BSyncResult,
  BTransactionPage,
  BUploadPreview,
  BUploadResult,
  mapAudit,
  mapBudget,
  mapSync,
  mapTransactionPage,
} from "../backend/books";
import { api, download, upload } from "../client";
import { invalidate } from "./shared";

const BOOKS_KEYS = ["audit", "transactions", "budget", "books-summary", "decisions", "dashboard", "activity"] as const;

export const useAudit = () => useQuery({ queryKey: ["audit"], queryFn: () => api("/books/audit", { schema: BAudit, map: mapAudit }) });

/** fix → POST /books/audit/{id}/fix (deterministic correction); ignore → POST /books/audit/{id}/ignore (mark as checked). */
export function useResolveFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "fix" | "ignore" }): Promise<void> => {
      if (action === "fix") await api(`/books/audit/${encodeURIComponent(id)}/fix`, { method: "POST", schema: BAuditFix });
      else await api(`/books/audit/${encodeURIComponent(id)}/ignore`, { method: "POST", schema: BOk });
    },
    onSettled: () => invalidate(qc, ...BOOKS_KEYS),
  });
}

export function useDidoxSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/integrations/didox/sync", { method: "POST", schema: BSyncResult, map: mapSync }),
    onSuccess: () => invalidate(qc, ...BOOKS_KEYS, "integrations"),
  });
}

export const useTransactions = (limit = 50) =>
  useQuery({ queryKey: ["transactions", limit], queryFn: () => api("/books/transactions", { schema: BTransactionPage, query: { limit }, map: mapTransactionPage }) });

export const exportTransactions = (format: "xlsx" | "csv" | "1c" = "csv") => download("/books/transactions/export", `raft-yozuvlar.${format === "xlsx" ? "xlsx" : "csv"}`, { format });

export const useBudget = () => useQuery({ queryKey: ["budget"], queryFn: () => api("/books/budget", { schema: BBudget, map: mapBudget }) });

export const useBooksSummary = () => useQuery({ queryKey: ["books-summary"], queryFn: () => api("/books/summary", { schema: BBooksSummary }) });

function fileForm(file: File, mapping?: Record<string, string | null>) {
  const form = new FormData();
  form.append("file", file);
  if (mapping) form.append("mapping", JSON.stringify(mapping));
  return form;
}

export function useUploadPreview() {
  return useMutation({
    mutationFn: ({ file, mapping }: { file: File; mapping?: Record<string, string | null> }) => upload("/books/upload/preview", fileForm(file, mapping), { schema: BUploadPreview }),
  });
}

export function useUploadCommit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, mapping }: { file: File; mapping: Record<string, string | null> }) => upload("/books/upload", fileForm(file, mapping), { schema: BUploadResult }),
    onSuccess: () => invalidate(qc, ...BOOKS_KEYS),
  });
}

/** Invoice photo → OCR → transactions (saved immediately). */
export function useInvoiceUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => upload("/books/invoice", fileForm(file), { schema: BInvoiceResult, query: { commit: true } }),
    onSuccess: () => invalidate(qc, ...BOOKS_KEYS),
  });
}

export const downloadUploadTemplate = () => download("/books/upload/template", "raft_template.csv");
