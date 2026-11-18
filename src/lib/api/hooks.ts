"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "./client";
import * as S from "./schemas";

const invalidate = (qc: ReturnType<typeof useQueryClient>, ...keys: string[]) =>
  Promise.all(keys.map((key) => qc.invalidateQueries({ queryKey: [key] })));

export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: () => api("/dashboard", { schema: S.Dashboard }) });

export const useDecisions = () =>
  useQuery({
    queryKey: ["decisions"],
    queryFn: () => api("/decisions", { schema: S.paged(S.Decision), query: { status: "pending" } }),
  });

export function useDecide() {
  const qc = useQueryClient();
  type Page = { items: S.Decision[]; next_cursor: string | null; total: number };
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "ignore" }) => api(`/decisions/${id}/${action}`, { method: "POST", schema: S.Ok, body: {} }),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: ["decisions"] });
      const previous = qc.getQueryData<Page>(["decisions"]);
      if (previous) qc.setQueryData<Page>(["decisions"], { ...previous, items: previous.items.filter((d) => d.id !== id), total: previous.total - 1 });
      return { previous };
    },
    onError: (error, _vars, ctx) => {
      if (error instanceof ApiError && error.status === 409) return;
      if (ctx?.previous) qc.setQueryData(["decisions"], ctx.previous);
    },
    onSettled: () => invalidate(qc, "decisions", "dashboard", "stock", "audit", "activity"),
  });
}

export const useStockUnits = () => useQuery({ queryKey: ["stock", "units"], queryFn: () => api("/stock/units", { schema: S.paged(S.StockUnit) }) });
export const useStockSummary = () => useQuery({ queryKey: ["stock", "summary"], queryFn: () => api("/stock/summary", { schema: S.StockSummary }) });

export function useReprice() {
  const qc = useQueryClient();
  type Units = { items: S.StockUnit[]; next_cursor: string | null; total: number };
  return useMutation({
    mutationFn: (body: { unit_ids: string[] } | { prices: { id: string; price: number }[] }) => api("/stock/reprice", { method: "POST", schema: S.RepriceResult, body }),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["stock", "units"] });
      const previous = qc.getQueryData<Units>(["stock", "units"]);
      if (previous) {
        const target = (u: S.StockUnit) => ("prices" in body ? body.prices.find((p) => p.id === u.id)?.price : body.unit_ids.includes(u.id) ? (u.suggested_price ?? undefined) : undefined);
        qc.setQueryData<Units>(["stock", "units"], {
          ...previous,
          items: previous.items.map((u) => {
            const price = target(u);
            if (price === undefined) return u;
            const vs = u.market_price ? ((price - u.market_price) / u.market_price) * 100 : null;
            const rating: S.Rating = vs === null ? "no_data" : vs > 6 ? "over" : vs < -6 ? "under" : "fair";
            return { ...u, list_price: price, vs_market_pct: vs, margin: price - u.cost, rating };
          }),
        });
      }
      return { previous };
    },
    onError: (_error, _body, ctx) => {
      if (ctx?.previous) qc.setQueryData(["stock", "units"], ctx.previous);
    },
    onSettled: () => invalidate(qc, "stock", "dashboard", "decisions", "activity"),
  });
}

export function useListOnExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (unit_ids: string[]) => api("/stock/list-on-exchange", { method: "POST", schema: S.Ok, body: { unit_ids } }),
    onSuccess: () => invalidate(qc, "lots", "activity"),
  });
}

export interface PriceParams {
  query: string;
  condition: "A" | "B" | "C";
  battery: number;
  box: boolean;
}

export const usePriceVerdict = (params: PriceParams) =>
  useQuery({
    queryKey: ["price", params],
    queryFn: () => api("/market/price", { method: "POST", schema: S.PriceVerdict, body: params }),
    placeholderData: keepPreviousData,
  });

export function useParseInput() {
  return useMutation({
    mutationFn: (input: { kind: "imei" | "text" | "link" | "voice"; value: string }) => {
      if (input.kind === "imei") return api("/input/imei", { method: "POST", schema: S.ParsedInput, body: { imei: input.value } });
      if (input.kind === "link") return api("/market/price-from-link", { method: "POST", schema: S.ParsedInput, body: { url: input.value } });
      if (input.kind === "voice") return api("/input/voice", { method: "POST", schema: S.ParsedInput, body: {} });
      return api("/input/parse", { method: "POST", schema: S.ParsedInput, body: { text: input.value } });
    },
  });
}

export function useBuyUnit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api("/stock/units", { method: "POST", schema: S.Ok, body }),
    onSuccess: () => invalidate(qc, "stock", "dashboard", "activity"),
  });
}

export const useRadar = () => useQuery({ queryKey: ["radar"], queryFn: () => api("/market/sourcing-radar", { schema: S.Radar }) });

export function useNextPost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/market/sourcing-radar/next", { method: "POST", schema: S.Ok, body: {} }),
    onSuccess: () => invalidate(qc, "radar", "activity"),
  });
}

export const useRfq = () => useQuery({ queryKey: ["rfq"], queryFn: () => api("/exchange/rfqs/148", { schema: S.Rfq }) });

export function useAcceptQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/exchange/quotes/${id}/accept`, { method: "POST", schema: S.Deal, body: {} }),
    onSettled: () => invalidate(qc, "rfq", "incoming", "transactions", "audit", "activity", "dashboard"),
  });
}

export function useCounterQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, price }: { id: string; price: number }) => api(`/exchange/quotes/${id}/counter`, { method: "POST", schema: S.Ok, body: { price } }),
    onSuccess: () => invalidate(qc, "rfq", "dashboard", "activity"),
  });
}

export const useIncoming = () => useQuery({ queryKey: ["incoming"], queryFn: () => api("/exchange/incoming", { schema: S.paged(S.IncomingRfq) }) });

export function useSendQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; price: number; qty: number; delivery: string; warranty: string }) => api(`/exchange/rfqs/${id}/quotes`, { method: "POST", schema: S.Ok, body }),
    onSuccess: () => invalidate(qc, "incoming", "rfq", "dashboard", "activity"),
  });
}

export const useLots = () => useQuery({ queryKey: ["lots"], queryFn: () => api("/exchange/lots", { schema: S.paged(S.Lot) }) });
export const useDemand = () => useQuery({ queryKey: ["demand"], queryFn: () => api("/exchange/demand", { schema: S.Demand }) });

export const useAudit = () => useQuery({ queryKey: ["audit"], queryFn: () => api("/books/audit", { schema: S.Audit }) });

export function useResolveFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "fix" | "ignore" }) => api(`/books/audit/${id}/${action}`, { method: "POST", schema: S.Ok, body: {} }),
    onSettled: () => invalidate(qc, "audit", "decisions", "dashboard", "activity"),
  });
}

export function useDidoxSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/integrations/didox/sync", { method: "POST", schema: S.SyncResult, body: {} }),
    onSuccess: () => invalidate(qc, "audit", "transactions", "activity", "integrations"),
  });
}

export const useTransactions = () => useQuery({ queryKey: ["transactions"], queryFn: () => api("/books/transactions", { schema: S.paged(S.Transaction) }) });
export const useBudget = () => useQuery({ queryKey: ["budget"], queryFn: () => api("/books/budget", { schema: S.Budget }) });

export function useUploadPreview() {
  return useMutation({
    mutationFn: (body: { filename: string; rows: string[][] }) => api("/books/upload/preview", { method: "POST", schema: S.UploadPreview, body }),
  });
}

export function useUploadCommit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { filename: string; rows: number; mapping: Record<string, string> }) => api("/books/upload", { method: "POST", schema: S.Ok, body }),
    onSuccess: () => invalidate(qc, "audit", "transactions", "activity"),
  });
}

export function useChat() {
  return useMutation({
    mutationFn: ({ endpoint = "/advisor/chat", body }: { endpoint?: string; body: Record<string, unknown> }) => api(endpoint, { method: "POST", schema: S.ChatAnswer, body }),
  });
}

export const useCredit = (params: { product: string; amount: number; months: number }) =>
  useQuery({
    queryKey: ["credit", params],
    queryFn: () => api("/advisor/credit", { method: "POST", schema: S.Credit, body: params }),
    placeholderData: keepPreviousData,
  });

export const useReadiness = () => useQuery({ queryKey: ["readiness"], queryFn: () => api("/advisor/readiness", { schema: S.Readiness }) });

export function useApplyLoan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { amount: number; months: number; consent: boolean }) => api("/advisor/loan-applications", { method: "POST", schema: S.LoanApplication, body }),
    onSettled: () => invalidate(qc, "readiness", "applications", "collateral", "activity"),
  });
}

export const useApplications = () => useQuery({ queryKey: ["applications"], queryFn: () => api("/lender/applications", { schema: S.paged(S.LoanApplication) }) });

export function useDecideApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) => api(`/lender/applications/${id}/decision`, { method: "POST", schema: S.Ok, body: { decision } }),
    onSettled: () => invalidate(qc, "applications", "collateral", "readiness", "activity"),
  });
}

export const useCollateral = () => useQuery({ queryKey: ["collateral", "items"], queryFn: () => api("/lender/collateral", { schema: S.paged(S.Collateral) }) });
export const useCollateralSummary = () => useQuery({ queryKey: ["collateral", "summary"], queryFn: () => api("/lender/collateral/summary", { schema: S.CollateralSummary }) });

export function useValuation(input: { query?: string; inventory_id?: string }) {
  return useQuery({
    queryKey: ["valuation", input],
    queryFn: () => api("/lender/valuations", { method: "POST", schema: S.Valuation, body: input }),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export const useMarketReport = () => useQuery({ queryKey: ["report"], queryFn: () => api("/partner/market-report", { schema: S.MarketReport }) });
export const useIntegrations = () => useQuery({ queryKey: ["integrations"], queryFn: () => api("/integrations", { schema: S.paged(S.Integration) }) });

export function useSyncIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kind: string) => api(`/integrations/${kind}/sync`, { method: "POST", schema: z.object({}).passthrough(), body: {} }),
    onSuccess: () => invalidate(qc, "integrations", "audit", "activity"),
  });
}

export const useActivity = () => useQuery({ queryKey: ["activity"], queryFn: () => api("/activity", { schema: S.paged(S.ActivityRow) }) });
export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: () => api("/meta", { schema: S.Meta }) });
export const useModelCard = () => useQuery({ queryKey: ["model"], queryFn: () => api("/model", { schema: S.ModelCard }) });

const SearchResult = z.object({ items: z.array(z.object({ group: z.string(), title: z.string(), meta: z.string(), href: z.string() })) });

export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: () => api("/search", { schema: SearchResult, query: { q } }),
    enabled: q.trim().length > 1,
    placeholderData: keepPreviousData,
  });
