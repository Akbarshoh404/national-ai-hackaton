"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../client";
import {
  BApplication,
  BApplicationDetail,
  BApplications,
  BCollateralSummary,
  BCollaterals,
  BCompany,
  BMarketReport,
  BValuation,
  mapApplication,
  mapApplicationDetail,
  mapApplications,
  mapCollateralSummary,
  mapCollaterals,
  mapMarketReport,
  mapValuation,
  type ReportCategory,
  type ValuationInput,
} from "../backend/partner";
import { invalidate } from "./shared";

/** The signed-in partner company (bank or bazaar administration). */
export const usePartnerCompany = () => useQuery({ queryKey: ["partner", "company"], queryFn: () => api("/companies/me", { schema: BCompany }), staleTime: 5 * 60_000 });

export const useApplications = () =>
  useQuery({ queryKey: ["applications"], queryFn: () => api("/lender/applications", { schema: BApplications, query: { limit: 200 }, map: mapApplications }) });

export const useApplication = (id: number | null) =>
  useQuery({
    queryKey: ["applications", id],
    queryFn: () => api(`/lender/applications/${id}`, { schema: BApplicationDetail, map: mapApplicationDetail }),
    enabled: id !== null,
  });

export function useDecideApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, note }: { id: number; status: "reviewing" | "approved" | "rejected"; note?: string }) =>
      api(`/lender/applications/${id}/decision`, { method: "POST", schema: BApplication, body: { status, note: note || null }, map: mapApplication }),
    onSettled: () => invalidate(qc, "applications", "collateral", "activity"),
  });
}

export const useCollateral = () => useQuery({ queryKey: ["collateral", "items"], queryFn: () => api("/lender/collateral", { schema: BCollaterals, map: mapCollaterals }) });

export const useCollateralSummary = () =>
  useQuery({ queryKey: ["collateral", "summary"], queryFn: () => api("/lender/collateral/summary", { schema: BCollateralSummary, map: mapCollateralSummary }) });

export function useValuation(input: ValuationInput | null) {
  return useQuery({
    queryKey: ["valuation", input],
    queryFn: () => api("/lender/valuations", { method: "POST", schema: BValuation, body: input, map: mapValuation }),
    enabled: input !== null,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: Infinity,
  });
}

export const useMarketReport = (category: ReportCategory = "phone") =>
  useQuery({
    queryKey: ["report", category],
    queryFn: () => api("/partner/market-report", { schema: BMarketReport, query: { category }, map: mapMarketReport }),
    placeholderData: keepPreviousData,
  });

/** The backend's own Excel export of the market report. */
export const downloadMarketReport = (category: ReportCategory, district?: string) =>
  download("/partner/market-report", `raft-bozor-hisoboti-${category}.xlsx`, { category, district, format: "xlsx" });
