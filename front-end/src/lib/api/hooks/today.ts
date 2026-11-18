"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as B from "../backend/today";
import { getAccount } from "@/lib/auth";
import { api, ApiError } from "../client";
import { invalidate } from "./shared";

export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: () => api("/dashboard", { schema: B.BDashboard, map: B.toDashboard }) });

type DecisionPage = { items: B.DecisionCard[]; next_cursor: string | null; total: number };

export const useDecisions = () =>
  useQuery({
    queryKey: ["decisions"],
    queryFn: () =>
      api("/decisions", {
        schema: B.BDecisionPage,
        query: { status: "pending", limit: 50 },
        map: (d): DecisionPage => ({ ...d, items: d.items.map(B.toDecision) }),
      }),
  });

export function useDecide() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "approve" | "ignore" }): Promise<{ status: string }> =>
      action === "approve"
        ? api(`/decisions/${Number(id)}/approve`, { method: "POST", schema: B.BDecisionResult })
        : api(`/decisions/${Number(id)}/ignore`, { method: "POST", schema: B.BDecision }),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: ["decisions"] });
      const previous = qc.getQueryData<DecisionPage>(["decisions"]);
      if (previous) qc.setQueryData<DecisionPage>(["decisions"], { ...previous, items: previous.items.filter((d) => d.id !== id), total: previous.total - 1 });
      return { previous };
    },
    onError: (error, _vars, ctx) => {
      if (error instanceof ApiError && error.status === 409) return;
      if (ctx?.previous) qc.setQueryData(["decisions"], ctx.previous);
    },
    onSettled: () => invalidate(qc, "decisions", "dashboard", "stock", "audit", "activity"),
  });
}

export const useActivity = () =>
  useQuery({
    queryKey: ["activity"],
    queryFn: () => api("/activity", { schema: B.BActivityPage, query: { limit: 50 }, map: (d) => ({ ...d, items: d.items.map(B.toActivity) }) }),
    // Appraisers only have read access to market, pricing and inventory (backend core/permissions.py).
    enabled: getAccount()?.roleCode !== "appraiser",
  });

/** Settings data: stores (with units in stock), users (owner only) and role labels from /meta. */
export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: () => api("/meta", { schema: B.BMeta }) });

export const useStores = () => useQuery({ queryKey: ["stores"], queryFn: () => api("/stores", { schema: B.BStorePage }) });

export const useUsers = () => useQuery({ queryKey: ["users"], queryFn: () => api("/users", { schema: B.BUserPage }) });

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; role: string }) => api("/users", { method: "POST", schema: B.BUserCreated, body }),
    onSuccess: () => invalidate(qc, "users", "activity"),
  });
}

export const useModelCard = () => useQuery({ queryKey: ["model"], queryFn: () => api("/model", { schema: B.BModel }) });

export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: () => api("/search", { schema: B.BSearch, query: { q: q.trim() }, map: B.toSearch }),
    enabled: q.trim().length > 1,
    placeholderData: keepPreviousData,
  });

export const useIntegrations = () => useQuery({ queryKey: ["integrations"], queryFn: () => api("/integrations", { schema: B.BIntegrations }) });

export function useSyncIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kind: string) => api(`/integrations/${kind}/sync`, { method: "POST", schema: B.BSyncResult }),
    onSuccess: () => invalidate(qc, "integrations", "audit", "activity", "dashboard"),
  });
}
