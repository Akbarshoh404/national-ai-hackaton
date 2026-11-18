"use client";

import { useMemo, useState } from "react";
import { RangeBar } from "@/components/charts/small";
import { Page, useShell } from "@/components/raft/shell";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Delta, KpiStrip, Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import { useApplications, useCollateral, useCollateralSummary, useDecideApplication, useMarketReport, useValuation } from "@/lib/api/hooks";
import type { Collateral, LoanApplication } from "@/lib/api/schemas";
import { linePath } from "@/components/charts/base";
import { pct, pctSigned, shortSoum, usd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { downloadXlsx } from "@/lib/xlsx";

const COLLATERAL_STATUS: Record<Collateral["status"], { text: string; tone: string }> = {
  normal: { text: "Normal", tone: "text-text-2" },
  watch: { text: "Kuzatuv", tone: "text-warning" },
  breach: { text: "Chegaradan oshdi", tone: "text-danger" },
};

function Summary() {
  const q = useCollateralSummary();
  if (!q.data) return <Skeleton className="h-[122px] rounded-[36px]" />;
  const s = q.data;
  return (
    <KpiStrip
      items={[
        { label: "Garov portfeli", value: shortSoum(s.portfolio_soum), note: `${s.objects} ta obyekt` },
        { label: "O‘rtacha LTV", value: `${s.avg_ltv}%`, note: `chegara ${s.ltv_cap}%` },
        { label: "Kuzatuvda", value: String(s.watch), note: "LTV 70% dan yuqori", noteClass: "text-warning" },
        { label: "Yangi arizalar", value: String(s.new_applications), note: "bugun" },
      ]}
    />
  );
}

function ApplicationPanel({ app, onDecide }: { app: LoanApplication; onDecide: (id: string) => void }) {
  const mutation = useDecideApplication();
  // Pinning the selection keeps the confirmation on screen when the next application exists.
  const decide = {
    ...mutation,
    mutate: (vars: { id: string; decision: "approve" | "reject" }) => {
      onDecide(vars.id);
      mutation.mutate(vars);
    },
  };
  const error = decide.error instanceof ApiError ? decide.error.message : decide.isError ? "Saqlanmadi. Qayta urinib ko‘ring." : null;
  const rows: [string, string, string?][] = [
    ["So‘ralgan", `${shortSoum(app.amount)} · ${app.months} oy`],
    ["Mahsulot", app.product],
    ["Kreditga tayyorlik", `${app.readiness} / 100`],
    ["O‘rtacha oylik foyda", shortSoum(app.avg_profit)],
    ["To‘lov / foyda", `${app.payment_ratio}%`, app.payment_ratio <= 50 ? "text-success" : "text-warning"],
    ["Garov", app.collateral],
    ["Ma’lumot manbai", app.source],
  ];
  return (
    <div key={app.id} className="fade-in">
      <div className="panel p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-[15px] font-semibold">{app.borrower}</h3>
          <span className="t-mono-cap shrink-0">STIR {app.stir}</span>
        </div>
        <dl className="mt-2 flex flex-col gap-2">
          {rows.map(([k, v, tone]) => (
            <div key={k} className="kv text-[13px]">
              <dt className="shrink-0">{k}</dt>
              <dd className={cn("mono text-[13px]", tone)}>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      {app.status === "new" ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="primary" size="lg" disabled={decide.isPending} onClick={() => decide.mutate({ id: app.id, decision: "approve" })}>
            Tasdiqlash
          </Button>
          <Button className="h-12" disabled={decide.isPending} onClick={() => decide.mutate({ id: app.id, decision: "reject" })}>
            Rad etish
          </Button>
          <span className="t-cap">Qarz oluvchiga Telegram orqali xabar boradi</span>
          {error ? (
            <span role="alert" className="text-[13px] text-danger">
              {error}
            </span>
          ) : null}
        </div>
      ) : (
        <p role="status" className={cn("mt-3 flex min-h-12 items-center text-[14px] font-medium", app.status === "approved" ? "text-success" : "text-danger")}>
          {app.status === "approved" ? "Ariza tasdiqlandi." : "Ariza rad etildi."}
        </p>
      )}
    </div>
  );
}

function ApplicationsTile() {
  const query = useApplications();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const items = query.data?.items ?? [];
  const fresh = items.filter((a) => a.status === "new").length;
  const selected = items.find((a) => a.id === selectedId) ?? items.find((a) => a.status === "new") ?? items[0];
  const others = items.filter((a) => a.id !== selected?.id);
  return (
    <Tile className="flex flex-col">
      <TileHeader title="Kredit arizalari" sub="Raft orqali, qarz oluvchi roziligi bilan" right={`${fresh} ta yangi`} />
      <div className="mt-3 flex flex-1 flex-col">
        <Async query={query} skeleton={<SkeletonLines rows={4} />} isEmpty={(d) => d.items.length === 0} empty={<EmptyState text="Hozircha ariza yo‘q." />}>
          {() => (
            <>
              {selected ? <ApplicationPanel app={selected} onDecide={setSelectedId} /> : null}
              <ul className="mt-auto pt-4">
                {others.map((a) => (
                  <li key={a.id} className="border-t border-[rgb(15_23_22/0.06)]">
                    <button type="button" onClick={() => setSelectedId(a.id)} className="flex min-h-[56px] w-full items-center justify-between gap-3 rounded-[16px] py-2 text-left hover:bg-[var(--nested)]">
                      <span className="min-w-0">
                        <span className="block text-[14px] font-medium">{a.borrower}</span>
                        <span className="block truncate text-[13px] text-text-2">
                          {a.product} · {shortSoum(a.amount)} · {a.months} oy
                        </span>
                      </span>
                      <span className="t-mono-cap shrink-0">tayyorlik {a.readiness}</span>
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

function ValuationTile() {
  const [text, setText] = useState("");
  const [input, setInput] = useState<{ query?: string; inventory_id?: string }>({ query: "cobalt" });
  const query = useValuation(input);
  const v = query.data;
  return (
    <Tile className="flex flex-col">
      <TileHeader title="Garov qiymati" sub={v ? `${v.title} · ${v.subtitle}` : undefined} right="jonli" />
      <form
        className="mt-3 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const value = text.trim();
          if (value) setInput(/^u-\d+$/i.test(value) ? { inventory_id: value.toLowerCase() } : { query: value });
        }}
      >
        <div className="min-w-0 flex-1">
          <label className="field-label mb-1 text-[12px]" htmlFor="valuation-input">
            Obyekt, t.me havola yoki ombor raqami
          </label>
          <input id="valuation-input" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Malibu 2019 yoki u-1001" />
        </div>
        <Button type="submit">Baholash</Button>
      </form>
      {query.isError ? (
        <p role="alert" className="mt-2 text-[13px] text-danger">
          {query.error instanceof ApiError ? query.error.message : "Baholab bo‘lmadi."}
        </p>
      ) : null}
      {v ? (
        <div key={v.title} className="fade-in mt-3">
          <p className="flex items-baseline gap-2">
            <span className="serif text-[48px]">{usd(v.fair)}</span>
            <span className="text-[13px] text-text-2">adolatli narx</span>
          </p>
          <div className="mt-3">
            <RangeBar
              min={v.liquidation * 0.94}
              max={v.p75 * 1.04}
              bandLow={v.p25}
              bandHigh={v.p75}
              markers={[
                { value: v.liquidation, label: `${usd(v.liquidation)} likvidatsiya`, tone: "warning" },
                { value: v.fair, label: usd(v.fair), tone: "text" },
              ]}
              ariaLabel={`Adolatli narx ${usd(v.fair)}, likvidatsiya ${usd(v.liquidation)}`}
            />
          </div>
          <dl className="mt-3 flex flex-col gap-2">
            {[
              ["Oraliq (p25–p75)", `${usd(v.p25)} – ${usd(v.p75)}`, ""],
              ["Likvidatsiya qiymati", usd(v.liquidation), "text-warning"],
              ["Asos", `${v.listings} ta e’lon · ${v.window_days} kun`, ""],
              ["30 kunlik o‘zgarish", pct(v.change_30d), v.change_30d < 0 ? "text-danger" : "text-success"],
            ].map(([k, value, tone]) => (
              <div key={k} className="kv text-[13px]">
                <dt>{k}</dt>
                <dd className={cn("mono", tone)}>{value}</dd>
              </div>
            ))}
          </dl>
          <h3 className="mt-4 text-[13px] text-text-2">Eng yaqin e’lonlar</h3>
          <ul className="mt-1">
            {v.comparables.map((c) => (
              <li key={c.title} className="flex items-baseline justify-between gap-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-[13px]">{c.title}</span>
                  <span className="t-mono-cap">{c.meta}</span>
                </span>
                <span className="mono shrink-0 text-[13px] font-medium">{usd(c.price)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : query.isPending ? (
        <Skeleton className="mt-3 h-[280px]" />
      ) : null}
    </Tile>
  );
}

function PortfolioTile() {
  const query = useCollateral();
  const summary = useCollateralSummary();
  return (
    <Tile>
      <TileHeader title="Garov portfeli" sub="Har kuni bozor narxi bo‘yicha qayta baholanadi" right={summary.data ? `qayta baholandi: ${summary.data.revalued_at}` : undefined} />
      <div className="mt-3 overflow-x-auto">
        <Async query={query} skeleton={<SkeletonLines rows={6} />}>
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
                    <td className="font-medium">{c.object}</td>
                    <td className="text-text-2">{c.borrower}</td>
                    <td className="r mono font-medium">{usd(c.value)}</td>
                    <td className="r mono">
                      <Delta value={c.change_30d}>{pctSigned(c.change_30d)}</Delta>
                    </td>
                    <td className="r mono">{c.ltv}%</td>
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
  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((v, i): [number, number] => [2 + (i / (values.length - 1)) * (W - 4), 3 + (1 - (v - min) / (max - min || 1)) * (H - 6)]);
  return (
    <svg width={W} height={H} role="img" aria-label={label} className="ml-auto block">
      <path d={linePath(points)} fill="none" stroke="var(--chart-s1)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ReportTile() {
  const query = useMarketReport();
  const [district, setDistrict] = useState("all");
  const rows = useMemo(() => query.data?.rows ?? [], [query.data]);
  const districts = [...new Set(rows.map((r) => r.district))];
  const visible = rows.filter((r) => district === "all" || r.district === district);
  return (
    <Tile>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <TileHeader title="Bozor hisoboti" sub={query.data ? `Model va tuman bo‘yicha · ${query.data.week}` : undefined} />
        <div className="flex items-end gap-2">
          <div className="w-[180px]">
            <label className="field-label mb-1 text-[12px]" htmlFor="report-district">
              Tuman
            </label>
            <Select id="report-district" value={district} onValueChange={setDistrict} options={[{ value: "all", label: "Hammasi" }, ...districts.map((d) => ({ value: d, label: d }))]} />
          </div>
          <Button onClick={() => downloadXlsx("raft-bozor-hisoboti.xlsx", "Bozor hisoboti", [["Model", "Tuman", "Mediana, $", "7 kun, %", "E’lonlar"], ...visible.map((r) => [r.model, r.district, r.median, r.change_7d, r.listings])])}>Excel’ga yuklash</Button>
        </div>
      </div>
      <div className="mt-3 overflow-x-auto">
        <Async query={query} skeleton={<SkeletonLines rows={6} />}>
          {() => (
            <table className="data-table min-w-[720px]">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Tuman</th>
                  <th className="r">Mediana</th>
                  <th className="r">7 kun</th>
                  <th className="r">E’lonlar</th>
                  <th className="r">Haftalik trend</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={`${r.model}-${r.district}`}>
                    <td className="font-medium">{r.model}</td>
                    <td className="text-text-2">{r.district}</td>
                    <td className="r mono font-medium">{usd(r.median)}</td>
                    <td className="r mono">
                      <Delta value={r.change_7d}>{pctSigned(r.change_7d)}</Delta>
                    </td>
                    <td className="r mono text-text-2">{r.listings}</td>
                    <td className="r">
                      <Trend values={r.trend} label={`${r.model}: haftalik trend`} />
                    </td>
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

function usePartnerSubtitle() {
  const { account } = useShell();
  return { account, subtitle: account.kind === "bank" ? "Hamkor konsoli · garov va kredit arizalari" : "Bozor ma’muriyati · narx hisoboti" };
}

export function PartnerScreen() {
  const { account, subtitle } = usePartnerSubtitle();
  return (
    <Page title={account.name} subtitle={subtitle}>
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
  const { account, subtitle } = usePartnerSubtitle();
  return (
    <Page title={account.name} subtitle={subtitle}>
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
  const { account, subtitle } = usePartnerSubtitle();
  return (
    <Page title={account.name} subtitle={subtitle}>
      <ReportTile />
    </Page>
  );
}
