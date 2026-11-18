"use client";

import { useMemo, useState } from "react";
import { RangeBar } from "@/components/charts/small";
import { Page, useShell } from "@/components/raft/shell";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Delta, KpiStrip, Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import {
  downloadMarketReport,
  useApplication,
  useApplications,
  useCollateral,
  useCollateralSummary,
  useDecideApplication,
  useMarketReport,
  usePartnerCompany,
  useValuation,
} from "@/lib/api/hooks";
import { REPORT_CATEGORIES, type AppStatus, type CollateralStatus, type PartnerApplication, type ReportCategory, type ValuationInput } from "@/lib/api/backend/partner";
import { linePath } from "@/components/charts/base";
import { dateLong, pct, pctSigned, shortSoum } from "@/lib/format";
import { cn } from "@/lib/utils";

const COLLATERAL_STATUS: Record<CollateralStatus, { text: string; tone: string }> = {
  ok: { text: "Normal", tone: "text-text-2" },
  watch: { text: "Kuzatuv", tone: "text-warning" },
  breach: { text: "Chegaradan oshdi", tone: "text-danger" },
  no_data: { text: "Narx ma’lumoti yo‘q", tone: "text-muted" },
};

const APP_STATUS: Record<AppStatus, string> = {
  submitted: "yangi",
  reviewing: "ko‘rib chiqilmoqda",
  approved: "tasdiqlangan",
  rejected: "rad etilgan",
};

const CATEGORY_LABEL: Record<ReportCategory, string> = {
  phone: "Telefonlar",
  laptop: "Noutbuklar",
  car: "Avtomobillar",
  house: "Kvartira sotuvi",
  rent: "Kvartira ijarasi",
};

const SELLER_LABEL: Record<string, string> = { shop: "do‘kon", private: "xususiy" };

const isOpen = (a: PartnerApplication) => a.status === "submitted" || a.status === "reviewing";

function Summary() {
  const q = useCollateralSummary();
  const apps = useApplications();
  if (!q.data) return <Skeleton className="h-[122px] rounded-[36px]" />;
  const s = q.data;
  const fresh = apps.data ? apps.data.items.filter((a) => a.status === "submitted").length : null;
  const open = apps.data ? apps.data.items.filter(isOpen).length : null;
  return (
    <KpiStrip
      items={[
        { label: "Garov portfeli", value: shortSoum(s.marketValue), note: `${s.objects} ta obyekt · likvidatsiya ${shortSoum(s.liquidationValue)}` },
        { label: "Portfel LTV", value: s.portfolioLtv === null ? "—" : `${s.portfolioLtv}%`, note: `qarz qoldig‘i ${shortSoum(s.loanBalance)}` },
        { label: "Kuzatuvda", value: String(s.watch), note: `${s.breach} ta chegaradan oshgan`, noteClass: s.breach > 0 ? "text-danger" : undefined },
        { label: "Yangi arizalar", value: fresh === null ? "—" : String(fresh), note: open === null ? undefined : `${open} ta ochiq ariza` },
      ]}
    />
  );
}

function ApplicationPanel({ app, onDecide }: { app: PartnerApplication; onDecide: (id: number) => void }) {
  const detail = useApplication(app.id);
  const mutation = useDecideApplication();
  // Pinning the selection keeps the confirmation on screen when the next application exists.
  const decide = (status: "approved" | "rejected") => {
    onDecide(app.id);
    mutation.mutate({ id: app.id, status });
  };
  const error = mutation.error instanceof ApiError ? mutation.error.message : mutation.isError ? "Saqlanmadi. Qayta urinib ko‘ring." : null;
  const d = detail.data;
  const rows: [string, string, string?][] = [
    ["So‘ralgan", `${shortSoum(app.amount)} · ${app.months} oy`],
    ["Mahsulot", app.product],
    ["Maqsad", app.purpose],
    ["Kreditga tayyorlik", app.readiness === null ? "—" : `${app.readiness} / 100${d ? ` · ${d.grade}` : ""}`],
  ];
  if (d) {
    rows.push(
      ["Oylik to‘lov", shortSoum(d.monthlyPayment)],
      ["O‘rtacha oylik foyda", shortSoum(d.avgProfit)],
      [
        "To‘lov / foyda",
        d.paymentRatio === null ? "—" : `${pct(d.paymentRatio)} (chegara ${pct(d.maxPaymentRatio, 0)})`,
        d.paymentRatio !== null && d.paymentRatio <= d.maxPaymentRatio ? "text-success" : "text-warning",
      ],
      ["Garov", d.collateralUnits > 0 ? `${d.collateralUnits} dona · ${shortSoum(d.collateralValue)}` : "ko‘rsatilmagan"],
      ["Audit", `${d.auditIssues} ta muammo · ${d.auditHigh} ta jiddiy`, d.auditHigh > 0 ? "text-warning" : undefined],
      ["Ma’lumot holati", dateLong(d.snapshotAt)],
    );
  }
  return (
    <div key={app.id} className="fade-in">
      <div className="panel p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-[15px] font-semibold">{app.borrower}</h3>
          {d?.stir ? <span className="t-mono-cap shrink-0">STIR {d.stir}</span> : null}
        </div>
        <dl className="mt-2 flex flex-col gap-2">
          {rows.map(([k, v, tone]) => (
            <div key={k} className="kv text-[13px]">
              <dt className="shrink-0">{k}</dt>
              <dd className={cn("mono text-[13px]", tone)}>{v}</dd>
            </div>
          ))}
        </dl>
        {detail.isPending ? <SkeletonLines rows={3} /> : null}
        {detail.isError ? (
          <p role="alert" className="mt-2 text-[13px] text-danger">
            {detail.error instanceof ApiError ? detail.error.message : "Ariza tafsilotlari yuklanmadi."}
          </p>
        ) : null}
        {d ? <p className="mt-2 text-[13px] text-text-2">{d.verdict}</p> : null}
      </div>
      {isOpen(app) ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="primary" size="lg" disabled={mutation.isPending} onClick={() => decide("approved")}>
            Tasdiqlash
          </Button>
          <Button className="h-12" disabled={mutation.isPending} onClick={() => decide("rejected")}>
            Rad etish
          </Button>
          <span className="t-cap">Qarz oluvchiga bildirishnoma boradi</span>
          {error ? (
            <span role="alert" className="text-[13px] text-danger">
              {error}
            </span>
          ) : null}
        </div>
      ) : (
        <p role="status" className={cn("mt-3 flex min-h-12 items-center text-[14px] font-medium", app.status === "approved" ? "text-success" : "text-danger")}>
          {app.status === "approved" ? "Ariza tasdiqlandi." : "Ariza rad etildi."}
          {app.note ? <span className="ml-2 font-normal text-text-2">{app.note}</span> : null}
        </p>
      )}
    </div>
  );
}

function ApplicationsTile() {
  const query = useApplications();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const items = query.data?.items ?? [];
  const fresh = items.filter((a) => a.status === "submitted").length;
  const selected = items.find((a) => a.id === selectedId) ?? items.find(isOpen) ?? items[0];
  const others = items.filter((a) => a.id !== selected?.id);
  return (
    <Tile className="flex flex-col">
      <TileHeader title="Kredit arizalari" sub="Raft orqali, qarz oluvchi roziligi bilan" right={query.data ? `${fresh} ta yangi` : undefined} />
      <div className="mt-3 flex flex-1 flex-col">
        <Async query={query} skeleton={<SkeletonLines rows={4} />} isEmpty={(d) => d.items.length === 0} empty={<EmptyState text="Hozircha ariza yo‘q." />}>
          {() => (
            <>
              {selected ? <ApplicationPanel key={selected.id} app={selected} onDecide={setSelectedId} /> : null}
              <ul className="mt-auto pt-4">
                {others.map((a) => (
                  <li key={a.id} className="border-t border-[rgb(15_23_22/0.06)]">
                    <button type="button" onClick={() => setSelectedId(a.id)} className="flex min-h-[56px] w-full items-center justify-between gap-3 rounded-[16px] py-2 text-left hover:bg-[var(--nested)]">
                      <span className="min-w-0">
                        <span className="block text-[14px] font-medium">{a.borrower}</span>
                        <span className="block truncate text-[13px] text-text-2">
                          {a.product} · {shortSoum(a.amount)} · {a.months} oy · {APP_STATUS[a.status]}
                        </span>
                      </span>
                      {a.readiness !== null ? <span className="t-mono-cap shrink-0">tayyorlik {a.readiness}</span> : null}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Async>
      </div>
    </Tile>
  );
}

const TME = /(?:https?:\/\/)?(?:t\.me|telegram\.me)\/\S+/i;

function toValuationInput(value: string): ValuationInput {
  if (TME.test(value)) return { url: value };
  const unit = /^#?(\d+)$/.exec(value);
  if (unit) return { inventory_id: Number(unit[1]) };
  return { text: value };
}

function ValuationTile() {
  const [text, setText] = useState("");
  const [input, setInput] = useState<ValuationInput | null>(null);
  const query = useValuation(input);
  const v = query.data;
  return (
    <Tile className="flex flex-col">
      <TileHeader title="Garov qiymati" sub={v ? `${v.title} · ${v.subtitle}` : undefined} right={v ? `bu oy ${v.valuationsThisMonth} ta baholash` : undefined} />
      <form
        className="mt-3 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const value = text.trim();
          if (value) setInput(toValuationInput(value));
        }}
      >
        <div className="min-w-0 flex-1">
          <label className="field-label mb-1 text-[12px]" htmlFor="valuation-input">
            Obyekt, t.me havola yoki ombor raqami
          </label>
          <input id="valuation-input" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Model va yili, t.me/… havola yoki #raqam" />
        </div>
        <Button type="submit" disabled={query.isFetching}>
          Baholash
        </Button>
      </form>
      {query.isError ? (
        <p role="alert" className="mt-2 text-[13px] text-danger">
          {query.error instanceof ApiError ? query.error.message : "Baholab bo‘lmadi."}
        </p>
      ) : null}
      {v ? (
        <div key={v.title} className={cn("fade-in mt-3", query.isFetching && "opacity-60")}>
          <p className="flex items-baseline gap-2">
            <span className="serif text-[48px]">{shortSoum(v.fair)}</span>
            <span className="text-[13px] text-text-2">adolatli narx</span>
          </p>
          <div className="mt-3">
            <RangeBar
              min={Math.min(v.liquidation, v.p25) * 0.94}
              max={Math.max(v.p75, v.fair) * 1.04}
              bandLow={v.p25}
              bandHigh={v.p75}
              markers={[
                { value: v.liquidation, label: `${shortSoum(v.liquidation)} likvidatsiya`, tone: "warning" },
                { value: v.fair, label: shortSoum(v.fair), tone: "text" },
              ]}
              ariaLabel={`Adolatli narx ${shortSoum(v.fair)}, likvidatsiya ${shortSoum(v.liquidation)}`}
            />
          </div>
          <dl className="mt-3 flex flex-col gap-2">
            {(
              [
                ["Oraliq (p25–p75)", `${shortSoum(v.p25)} – ${shortSoum(v.p75)}`, ""],
                [`Likvidatsiya qiymati (−${pct(v.haircutPct, 0)})`, shortSoum(v.liquidation), "text-warning"],
                ...(v.qty > 1 ? [[`Jami, ${v.qty} dona`, `${shortSoum(v.totalMarket)} · likv. ${shortSoum(v.totalLiquidation)}`, ""]] : []),
                ["Asos", `${v.listings} ta e’lon · ishonch: ${v.confidence}`, ""],
                ...(v.change30d !== null ? [["30 kunlik o‘zgarish", pctSigned(v.change30d), v.change30d < 0 ? "text-danger" : "text-success"]] : []),
              ] as [string, string, string][]
            ).map(([k, value, tone]) => (
              <div key={k} className="kv text-[13px]">
                <dt>{k}</dt>
                <dd className={cn("mono", tone)}>{value}</dd>
              </div>
            ))}
          </dl>
          {v.comparables.length ? (
            <>
              <h3 className="mt-4 text-[13px] text-text-2">Eng yaqin e’lonlar</h3>
              <ul className="mt-1">
                {v.comparables.map((c) => (
                  <li key={c.id} className="flex items-baseline justify-between gap-3 py-2">
                    <span className="min-w-0">
                      <span className="block truncate text-[13px]">{c.title}</span>
                      <span className="t-mono-cap">{c.meta}</span>
                    </span>
                    <span className="mono shrink-0 text-[13px] font-medium">{shortSoum(c.price)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : query.isFetching ? (
        <Skeleton className="mt-3 h-[280px]" />
      ) : !query.isError ? (
        <EmptyState text="Obyektni yozing: narx bozor e’lonlaridan hisoblanadi." />
      ) : null}
    </Tile>
  );
}

function timeOf(ms: number) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function PortfolioTile() {
  const query = useCollateral();
  return (
    <Tile>
      <TileHeader title="Garov portfeli" sub="Har ochilganda bozor narxi bo‘yicha qayta baholanadi" right={query.data ? `qayta baholandi: ${timeOf(query.dataUpdatedAt)}` : undefined} />
      <div className="mt-3 overflow-x-auto">
        <Async query={query} skeleton={<SkeletonLines rows={6} />} isEmpty={(d) => d.items.length === 0} empty={<EmptyState text="Garov portfeli bo‘sh." />}>
          {(data) => (
            <table className="data-table min-w-[720px]">
              <thead>
                <tr>
                  <th>Obyekt</th>
                  <th>Qarz oluvchi</th>
                  <th className="r">Qiymat</th>
                  <th className="r">30 kun</th>
                  <th className="r">LTV</th>
                  <th className="r">Holat</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="block font-medium">{c.object}</span>
                      {c.detail ? <span className="t-mono-cap">{c.detail}</span> : null}
                    </td>
                    <td className="text-text-2">{c.borrower}</td>
                    <td className="r mono font-medium">{c.value === null ? "—" : shortSoum(c.value)}</td>
                    <td className="r mono">{c.change30d === null ? "—" : <Delta value={c.change30d}>{pctSigned(c.change30d)}</Delta>}</td>
                    <td className="r mono" title={`chegara ${c.ltvLimit}%`}>
                      {c.ltv === null ? "—" : `${c.ltv}%`}
                      <span className="text-text-2"> / {c.ltvLimit}%</span>
                    </td>
                    <td className={cn("r", COLLATERAL_STATUS[c.status].tone)}>{COLLATERAL_STATUS[c.status].text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </div>
    </Tile>
  );
}

function Trend({ values, label }: { values: number[]; label: string }) {
  const W = 88;
  const H = 24;
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((v, i): [number, number] => [2 + (i / (values.length - 1)) * (W - 4), 3 + (1 - (v - min) / (max - min || 1)) * (H - 6)]);
  return (
    <svg width={W} height={H} role="img" aria-label={label} className="block">
      <path d={linePath(points)} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ReportTile() {
  const [category, setCategory] = useState<ReportCategory>("phone");
  const query = useMarketReport(category);
  const [district, setDistrict] = useState("all");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const r = query.data;
  const rows = useMemo(() => r?.rows ?? [], [r]);
  const districts = [...new Set(rows.map((x) => x.district))].sort();
  const visible = rows.filter((x) => district === "all" || x.district === district);
  const sub = r
    ? [`${CATEGORY_LABEL[category]} · ${r.days} kun · ${r.total} ta e’lon`, r.sellers.map((s) => `${SELLER_LABEL[s.type] ?? s.type} ${s.listings}`).join(", ")].filter(Boolean).join(" · ")
    : undefined;
  const exportXlsx = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await downloadMarketReport(category, district === "all" || district === "—" ? undefined : district);
    } catch (e) {
      setExportError(e instanceof ApiError ? e.message : "Yuklab bo‘lmadi.");
    } finally {
      setExporting(false);
    }
  };
  return (
    <Tile>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <TileHeader title="Bozor hisoboti" sub={sub} />
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-[180px]">
            <label className="field-label mb-1 text-[12px]" htmlFor="report-category">
              Toifa
            </label>
            <Select
              id="report-category"
              value={category}
              onValueChange={(v) => {
                setCategory(v as ReportCategory);
                setDistrict("all");
              }}
              options={REPORT_CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABEL[c] }))}
            />
          </div>
          <div className="w-[180px]">
            <label className="field-label mb-1 text-[12px]" htmlFor="report-district">
              Tuman
            </label>
            <Select id="report-district" value={district} onValueChange={setDistrict} options={[{ value: "all", label: "Hammasi" }, ...districts.map((d) => ({ value: d, label: d === "—" ? "Ko‘rsatilmagan" : d }))]} />
          </div>
          <Button disabled={exporting} onClick={() => void exportXlsx()}>
            Excel’ga yuklash
          </Button>
        </div>
      </div>
      {exportError ? (
        <p role="alert" className="mt-2 text-[13px] text-danger">
          {exportError}
        </p>
      ) : null}
      {r && r.trend.length >= 2 ? (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-[13px]">
          <span className="text-text-2">Haftalik mediana</span>
          <Trend values={r.trend.map((p) => p.median)} label={`${CATEGORY_LABEL[category]}: haftalik mediana`} />
          <span className="mono">{shortSoum(r.trend[r.trend.length - 1].median)}</span>
          {r.weekChange !== null ? (
            <span className="mono">
              <Delta value={r.weekChange}>{pctSigned(r.weekChange)}</Delta> <span className="text-text-2">o‘tgan haftaga nisbatan</span>
            </span>
          ) : null}
        </div>
      ) : null}
      <div className="mt-3 overflow-x-auto">
        <Async query={query} skeleton={<SkeletonLines rows={6} />} isEmpty={(d) => d.rows.length === 0} empty={<EmptyState text="Bu davrda e’lonlar yo‘q." />}>
          {() => (
            <table className="data-table min-w-[560px]">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Tuman</th>
                  <th className="r">Mediana</th>
                  <th className="r">E’lonlar</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((x) => (
                  <tr key={`${x.model}-${x.district}`}>
                    <td className="font-medium">{x.model}</td>
                    <td className="text-text-2">{x.district}</td>
                    <td className="r mono font-medium">{shortSoum(x.median)}</td>
                    <td className="r mono text-text-2">{x.listings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </div>
    </Tile>
  );
}

const ROLE_LABEL: Record<string, string> = { lender: "Bank", market_admin: "Bozor ma’muriyati" };

/** Title and subtitle from the signed-in company as the backend knows it (/companies/me). */
function usePartnerSubtitle() {
  const { account } = useShell();
  const company = usePartnerCompany();
  const c = company.data;
  const place = c ? [c.district, c.city].filter(Boolean).join(", ") : "";
  const subtitle = c ? [ROLE_LABEL[c.role] ?? c.role, place, c.stir ? `STIR ${c.stir}` : null].filter(Boolean).join(" · ") : undefined;
  return { account, title: c?.name ?? "", subtitle };
}

export function PartnerScreen() {
  const { account, title, subtitle } = usePartnerSubtitle();
  return (
    <Page title={title} subtitle={subtitle}>
      {account.kind === "bank" ? (
        <>
          <Summary />
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <ApplicationsTile />
            <ValuationTile />
          </div>
          <PortfolioTile />
        </>
      ) : (
        <ReportTile />
      )}
    </Page>
  );
}

export function GarovScreen() {
  const { account, title, subtitle } = usePartnerSubtitle();
  return (
    <Page title={title} subtitle={subtitle}>
      {account.kind === "bank" ? (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <ValuationTile />
          <PortfolioTile />
        </div>
      ) : (
        <ReportTile />
      )}
    </Page>
  );
}

export function HisobotScreen() {
  const { title, subtitle } = usePartnerSubtitle();
  return (
    <Page title={title} subtitle={subtitle}>
      <ReportTile />
    </Page>
  );
}
