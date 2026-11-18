"use client";

import { useState } from "react";
import { ScheduleBars } from "@/components/charts/small";
import { Conversation } from "@/components/raft/conversation";
import { Page, useCopilotScreen, useShell } from "@/components/raft/shell";
import { Async, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useT } from "@/i18n";
import { type CreditProduct, currentTax, type LoanApplication, type LoanReadiness, scheduleRows } from "@/lib/api/backend/advisor";
import { ApiError } from "@/lib/api/client";
import { useApplyLoan, useCredit, useLenders, useMyLoanApplications, useReadiness, useTax } from "@/lib/api/hooks";
import { mln, num, shortSoum, soum } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Products offered in the calculator (phone and laptop shops: no car loans or mortgages). */
const PRODUCTS: { value: CreditProduct; label: string }[] = [
  { value: "business_loan", label: "Biznes krediti" },
  { value: "leasing", label: "Lizing" },
];
const PRODUCT_LABEL: Record<string, string> = { business_loan: "Biznes krediti", auto_loan: "Avto kredit", mortgage: "Ipoteka", leasing: "Lizing" };
const productLabel = (p: string) => PRODUCT_LABEL[p] ?? p;

/** Loan terms shared by the calculator and the application dialog. */
interface Terms {
  product: CreditProduct;
  amountMln: string;
  months: number;
}

function TermsFields({ terms, onChange, idPrefix }: { terms: Terms; onChange: (t: Terms) => void; idPrefix: string }) {
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="field-label" htmlFor={`${idPrefix}-product`}>
            Mahsulot
          </label>
          <Select id={`${idPrefix}-product`} value={terms.product} onValueChange={(v) => onChange({ ...terms, product: v as CreditProduct })} options={PRODUCTS} />
        </div>
        <div>
          <label className="field-label" htmlFor={`${idPrefix}-amount`}>
            Summa, mln so‘m
          </label>
          <input id={`${idPrefix}-amount`} className="input mono" inputMode="numeric" value={terms.amountMln} onChange={(e) => onChange({ ...terms, amountMln: e.target.value.replace(/\D/g, "") })} />
        </div>
      </div>
      <div className="mt-3">
        <div className="flex justify-between text-[13px]">
          <span className="text-text-2">Muddat</span>
          <span className="mono font-medium">{terms.months} oy</span>
        </div>
        <Slider aria-label="Muddat, oy" min={6} max={60} step={6} value={[terms.months]} onValueChange={([v]) => onChange({ ...terms, months: v })} />
      </div>
    </>
  );
}

const principalOf = (t: Terms) => Number(t.amountMln) * 1e6;

function CreditCalculator({ open, onOpenChange, terms, onTerms }: { open: boolean; onOpenChange: (v: boolean) => void; terms: Terms; onTerms: (t: Terms) => void }) {
  const principal = principalOf(terms);
  const query = useCredit({ product: terms.product, principal_uzs: principal || 1e6, months: terms.months });
  const c = query.data;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Kredit kalkulyatori" description="To‘lov jadvali annuitet usulida hisoblanadi." className="max-w-[640px]">
        <TermsFields terms={terms} onChange={onTerms} idPrefix="calc" />
        {query.isError ? (
          <p role="alert" className="mt-3 text-[13px] text-danger">
            {query.error instanceof ApiError ? query.error.message : "Hisoblab bo‘lmadi."}
          </p>
        ) : null}
        {c ? (
          <>
            <dl className="panel mt-2 grid grid-cols-3 gap-3 p-4">
              {[
                ["Stavka", `${num(c.annual_rate_pct, 1)}% yillik`],
                ["Oylik to‘lov", mln(c.monthly_payment_uzs / 1e6, 1)],
                ["Jami foiz", mln(c.total_interest_uzs / 1e6, 1)],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[12px] text-text-2">{k}</dt>
                  <dd className="serif text-[24px]">{v}</dd>
                </div>
              ))}
            </dl>
            <p className={cn("mt-3 text-[13px]", c.affordable ? "text-success" : "text-danger")}>{c.verdict}</p>
            <p className="t-cap mt-1">{c.rate_note}</p>
            <div className="mt-4">
              <ScheduleBars schedule={scheduleRows(c.schedule)} height={88} format={(v) => `${mln(v / 1e6, 1)} so‘m`} />
            </div>
            <div className="mt-3 max-h-[200px] overflow-auto" tabIndex={0} role="region" aria-label="To‘liq to‘lov jadvali">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Oy</th>
                    <th className="r">Asosiy qarz</th>
                    <th className="r">Foiz</th>
                    <th className="r">Qoldiq</th>
                  </tr>
                </thead>
                <tbody>
                  {c.schedule.map((r) => (
                    <tr key={r.month} className="mono">
                      <td>{r.month}</td>
                      <td className="r">{mln(r.principal_uzs / 1e6, 1)}</td>
                      <td className="r">{mln(r.interest_uzs / 1e6, 1)}</td>
                      <td className="r">{mln(r.balance_uzs / 1e6, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function ConsentDialog({ open, onOpenChange, terms, onTerms, score }: { open: boolean; onOpenChange: (v: boolean) => void; terms: Terms; onTerms: (t: Terms) => void; score: number }) {
  const apply = useApplyLoan();
  const lenders = useLenders(open);
  const [lenderId, setLenderId] = useState<string>("");
  const [purpose, setPurpose] = useState("");
  const [consent, setConsent] = useState(false);
  const principal = principalOf(terms);
  const credit = useCredit({ product: terms.product, principal_uzs: principal || 1e6, months: terms.months });
  const lender = lenders.data?.find((l) => String(l.id) === lenderId) ?? (lenders.data?.length === 1 ? lenders.data[0] : undefined);
  const error = apply.error instanceof ApiError ? apply.error.message : apply.isError ? "Yuborilmadi. Qayta urinib ko‘ring." : null;
  const ready = !!lender && principal > 0 && purpose.trim().length >= 3 && consent && !apply.isPending;
  const c = credit.data;
  const rows: [string, string][] = [
    ["Bank", lender?.name ?? "—"],
    ["Mahsulot", productLabel(terms.product)],
    ["Summa", principal > 0 ? soum(principal) : "—"],
    ["Muddat", `${terms.months} oy`],
    ["Oylik to‘lov", c && principal > 0 ? shortSoum(c.monthly_payment_uzs) : "—"],
    ["O‘rtacha oylik sof oqim", c ? shortSoum(c.avg_monthly_net_uzs) : "—"],
    ["Kreditga tayyorlik", `${score} / 100`],
  ];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Bankka ariza yuborish" description="Bank quyidagi raqamlarni va tasdiqlangan kitoblaringiz nusxasini ko‘radi.">
        {lenders.data && lenders.data.length > 1 ? (
          <div className="mb-3">
            <label className="field-label" htmlFor="apply-lender">
              Bank
            </label>
            <Select id="apply-lender" value={lender ? String(lender.id) : ""} onValueChange={setLenderId} options={lenders.data.map((l) => ({ value: String(l.id), label: l.name }))} />
          </div>
        ) : null}
        {lenders.data && lenders.data.length === 0 ? <p className="mb-3 text-[13px] text-text-2">Hozircha ariza qabul qiladigan bank yo‘q.</p> : null}
        <TermsFields terms={terms} onChange={onTerms} idPrefix="apply" />
        <div className="mt-3">
          <label className="field-label" htmlFor="apply-purpose">
            Kredit maqsadi
          </label>
          <input id="apply-purpose" className="input" maxLength={1000} value={purpose} onChange={(e) => setPurpose(e.target.value)} />
        </div>
        <dl className="panel mt-3 flex flex-col gap-2 p-4">
          {rows.map(([k, v]) => (
            <div key={k} className="kv">
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <label className="mt-4 flex min-h-11 items-start gap-3 text-[14px]">
          <span className="pt-1">
            <Checkbox checked={consent} onCheckedChange={(v) => setConsent(v === true)} aria-label="Ma’lumotlarni bankka berishga roziman" />
          </span>
          Kitoblarim va ombor ma’lumotlarini shu ariza uchun {lender?.name ?? "bank"}ka berishga roziman.
        </label>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            size="lg"
            disabled={!ready}
            onClick={() =>
              lender &&
              apply.mutate(
                { lender_id: lender.id, product: terms.product, principal_uzs: principal, months: terms.months, purpose: purpose.trim(), consent: true },
                { onSuccess: () => onOpenChange(false) },
              )
            }
          >
            Arizani yuborish
          </Button>
          {!consent ? <span className="text-[13px] text-text-2">Avval roziligingizni belgilang.</span> : purpose.trim().length < 3 ? <span className="text-[13px] text-text-2">Kredit maqsadini yozing.</span> : null}
          {error ? (
            <span role="alert" className="text-[13px] text-danger">
              {error}
            </span>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function statusOf(a: LoanApplication): { text: string; tone: string } {
  switch (a.status) {
    case "submitted":
      return { text: `Ariza yuborildi. ${a.lender_name} ko‘rib chiqmoqda.`, tone: "text-text" };
    case "reviewing":
      return { text: `${a.lender_name} arizani ko‘rib chiqmoqda.`, tone: "text-text" };
    case "approved":
      return { text: `${a.lender_name} arizani tasdiqladi.`, tone: "text-success" };
    case "rejected":
      return { text: `${a.lender_name} arizani rad etdi.${a.decision_note ? ` ${a.decision_note}` : ""}`, tone: "text-danger" };
  }
}

function TaxEstimate() {
  const tax = useTax();
  const t = tax.data;
  if (!t) return null;
  const period = t.months.length ? `${t.months[0]} – ${t.months[t.months.length - 1]}` : "";
  return (
    <>
      <h3 className="mt-4 text-[13px] text-text-2">Soliq taxmini{period ? ` · ${period}` : ""}</h3>
      <p className="serif mt-1 text-[28px]">{shortSoum(currentTax(t))}</p>
      <p className="t-cap mt-1">{t.explanation}</p>
      <p className="t-cap mt-1 text-text-2">{t.disclaimer}</p>
    </>
  );
}

function ReadinessContent({ data }: { data: LoanReadiness }) {
  const { account } = useShell();
  const isOwner = account.roleCode === "owner";
  const applications = useMyLoanApplications(isOwner);
  const [consentOpen, setConsentOpen] = useState(false);
  const [calcOpen, setCalcOpen] = useState(false);
  const [terms, setTerms] = useState<Terms>({ product: "business_loan", amountMln: "100", months: 24 });
  const latest = applications.data?.[0];
  const active = latest && latest.status !== "rejected" ? latest : undefined;
  return (
    <>
      <p className="mt-2 flex items-baseline gap-2">
        <span className="serif text-[56px]">{data.score}</span>
        <span className="mono text-[13px] text-text-2">/ 100 · {data.grade}</span>
      </p>
      <ul className="mt-2 flex flex-col gap-3">
        {data.factors.map((f) => {
          const pct = f.max_points ? (f.points / f.max_points) * 100 : 0;
          return (
            <li key={f.key} title={f.explanation}>
              <div className="flex items-baseline justify-between text-[13px]">
                <span>{f.label}</span>
                <span className="mono text-[12px] font-medium">
                  {num(f.points, Number.isInteger(f.points) ? 0 : 1)} / {f.max_points}
                </span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-[rgb(15_23_22/0.06)]" role="img" aria-label={`${f.label}: ${f.points} / ${f.max_points}. ${f.explanation}`}>
                <div className="h-full rounded-full" style={{ width: `${pct}%`, background: pct >= 70 ? "var(--chart-s1)" : "var(--border-strong)" }} />
              </div>
              <p className="t-cap mt-1 text-text-2">{f.explanation}</p>
            </li>
          );
        })}
      </ul>
      {data.how_to_improve.length ? (
        <>
          <h3 className="mt-5 text-[13px] text-text-2">Qanday oshirish</h3>
          <ul className="mt-1">
            {data.how_to_improve.map((t) => (
              <li key={t} className="py-2 text-[13px]">
                {t}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <TaxEstimate />
      <div className="mt-auto flex flex-col gap-1 pt-5">
        <Button variant="plain" onClick={() => setCalcOpen(true)}>
          Kredit kalkulyatori
        </Button>
        {latest ? (
          <p role="status" className={cn("py-3 text-[14px] font-medium", statusOf(latest).tone)}>
            {statusOf(latest).text}
            <span className="t-cap block font-normal text-text-2">
              {productLabel(latest.product)} · {shortSoum(latest.principal_uzs)} · {latest.months} oy
            </span>
          </p>
        ) : null}
        {!active ? (
          <>
            <Button variant="primary" size="lg" className="w-full" disabled={!isOwner} onClick={() => setConsentOpen(true)}>
              Bankka ariza yuborish
            </Button>
            <p className="t-cap mt-1 text-center">{isOwner ? "Raqamlar bankka faqat sizning roziligingiz bilan yuboriladi." : "Arizani faqat do‘kon egasi yuboradi."}</p>
          </>
        ) : null}
      </div>
      <ConsentDialog open={consentOpen} onOpenChange={setConsentOpen} terms={terms} onTerms={setTerms} score={data.score} />
      <CreditCalculator open={calcOpen} onOpenChange={setCalcOpen} terms={terms} onTerms={setTerms} />
    </>
  );
}

export function MaslahatScreen() {
  const nav = useT().nav;
  useCopilotScreen("maslahat");
  const readiness = useReadiness();
  return (
    <Page title={nav.maslahat} subtitle="Kredit, soliq va kreditga tayyorlik">
      <div className="grid grid-cols-1 gap-5 xl:min-h-[calc(100vh-124px)] xl:grid-cols-[minmax(0,936fr)_minmax(0,300fr)]">
        <Tile className="flex h-[780px] min-h-0 flex-col xl:h-auto xl:max-h-[max(860px,calc(100vh-124px))]">
          <TileHeader title="Yordamchi" sub="Ekrandagi raqamlarni tushuntiradi. Raqamlarni Python hisoblaydi." />
          <div className="mt-3 flex min-h-0 flex-1 flex-col">
            <Conversation context={{ screen: "maslahat", selected_ids: [] }} hint="Kredit, soliq, pul oqimi yoki ombor haqida so‘rang." />
          </div>
        </Tile>
        <Tile className="flex flex-col">
          <TileHeader title="Kreditga tayyorlik" sub="Tasdiqlangan kitoblar va bitimlar asosida" />
          <Async query={readiness} skeleton={<div className="mt-4"><SkeletonLines rows={6} height={32} /></div>}>
            {(data) => <ReadinessContent data={data} />}
          </Async>
        </Tile>
      </div>
    </Page>
  );
}
