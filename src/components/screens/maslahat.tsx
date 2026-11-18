"use client";

import { useMemo, useState } from "react";
import { ScheduleBars } from "@/components/charts/small";
import { assistantMessage, Conversation, userMessage } from "@/components/raft/conversation";
import { Page, useCopilotScreen, useShell } from "@/components/raft/shell";
import { Async, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { initialAnswer, INITIAL_QUESTION } from "@/lib/api/fixtures/server";
import { useApplyLoan, useCredit, useReadiness } from "@/lib/api/hooks";
import type { LoanApplication, Readiness } from "@/lib/api/schemas";
import { mln, shortSoum, soum } from "@/lib/format";
import { cn } from "@/lib/utils";

const PRODUCTS = [
  { value: "business", label: "Biznes krediti" },
  { value: "auto", label: "Avto kredit" },
  { value: "mortgage", label: "Ipoteka" },
  { value: "leasing", label: "Lizing" },
];

function CreditCalculator({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [product, setProduct] = useState("business");
  const [amountMln, setAmountMln] = useState("300");
  const [months, setMonths] = useState(24);
  const amount = Number(amountMln) * 1e6;
  const query = useCredit({ product, amount: amount || 1e6, months });
  const c = query.data;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Kredit kalkulyatori" description="To‘lov jadvali annuitet usulida hisoblanadi." className="max-w-[640px]">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="field-label" htmlFor="calc-product">
              Mahsulot
            </label>
            <select id="calc-product" className="input" value={product} onChange={(e) => setProduct(e.target.value)}>
              {PRODUCTS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="calc-amount">
              Summa, mln so‘m
            </label>
            <input id="calc-amount" className="input mono" inputMode="numeric" value={amountMln} onChange={(e) => setAmountMln(e.target.value.replace(/\D/g, ""))} />
          </div>
        </div>
        <div className="mt-3">
          <div className="flex justify-between text-[13px]">
            <span className="text-text-2">Muddat</span>
            <span className="mono font-medium">{months} oy</span>
          </div>
          <Slider aria-label="Muddat, oy" min={6} max={60} step={6} value={[months]} onValueChange={([v]) => setMonths(v)} />
        </div>
        {c ? (
          <>
            <dl className="panel mt-2 grid grid-cols-3 gap-3 p-4">
              {[
                ["Stavka", `${c.rate}% yillik`],
                ["Oylik to‘lov", mln(c.monthly / 1e6, 1)],
                ["Jami foiz", mln(c.total_interest / 1e6, 1)],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[12px] text-text-2">{k}</dt>
                  <dd className="serif text-[24px]">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-4">
              <ScheduleBars schedule={c.schedule} height={88} format={(v) => `${mln(v / 1e6, 1)} so‘m`} />
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
                      <td className="r">{mln(r.principal / 1e6, 1)}</td>
                      <td className="r">{mln(r.interest / 1e6, 1)}</td>
                      <td className="r">{mln(r.balance / 1e6, 1)}</td>
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

function ConsentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const apply = useApplyLoan();
  const [consent, setConsent] = useState(false);
  const error = apply.error instanceof ApiError ? apply.error.message : apply.isError ? "Yuborilmadi. Qayta urinib ko‘ring." : null;
  const rows = [
    ["Bank", "Demo Bank"],
    ["Summa", soum(300_000_000)],
    ["Muddat", "24 oy"],
    ["Oylik to‘lov", "15,9 mln so‘m"],
    ["O‘rtacha oylik foyda", "42 mln so‘m"],
    ["Garov", "Ombor: 80 dona · $48 200"],
  ];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Bankka ariza yuborish" description="Bank quyidagi raqamlarni ko‘radi. Boshqa ma’lumot yuborilmaydi.">
        <dl className="panel flex flex-col gap-2 p-4">
          {rows.map(([k, v]) => (
            <div key={k} className="kv">
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <label className="mt-4 flex min-h-11 items-start gap-3 text-[14px]">
          <span className="pt-0.5">
            <Checkbox checked={consent} onCheckedChange={(v) => setConsent(v === true)} aria-label="Ma’lumotlarni bankka berishga roziman" />
          </span>
          Kitoblarim va ombor ma’lumotlarini shu ariza uchun Demo Bank’ka berishga roziman.
        </label>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="primary" size="lg" disabled={!consent || apply.isPending} onClick={() => apply.mutate({ amount: 300_000_000, months: 24, consent: true }, { onSuccess: () => onOpenChange(false) })}>
            Arizani yuborish
          </Button>
          {!consent ? <span className="text-[13px] text-text-2">Avval roziligingizni belgilang.</span> : null}
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

const STATUS: Record<LoanApplication["status"], { text: string; tone: string }> = {
  new: { text: "Ariza yuborildi. Demo Bank ko‘rib chiqmoqda.", tone: "text-text" },
  approved: { text: "Demo Bank arizani tasdiqladi.", tone: "text-success" },
  rejected: { text: "Demo Bank arizani rad etdi.", tone: "text-danger" },
};

function ReadinessContent({ data }: { data: Readiness }) {
  const { account } = useShell();
  const [consentOpen, setConsentOpen] = useState(false);
  const [calcOpen, setCalcOpen] = useState(false);
  const isOwner = account.roleCode === "owner";
  return (
    <>
      <p className="mt-2 flex items-baseline gap-2">
        <span className="serif text-[56px]">{data.score}</span>
        <span className="mono text-[13px] text-text-2">/ 100</span>
      </p>
      <ul className="mt-2 flex flex-col gap-3">
        {data.factors.map((f) => (
          <li key={f.name}>
            <div className="flex items-baseline justify-between text-[13px]">
              <span>{f.name}</span>
              <span className="mono text-[12px] font-medium">{f.value}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-[rgb(15_23_22/0.06)]" role="img" aria-label={`${f.name}: ${f.value} / 100`}>
              <div className="h-full rounded-full" style={{ width: `${f.value}%`, background: f.value >= 80 ? "var(--chart-s1)" : "var(--border-strong)" }} />
            </div>
          </li>
        ))}
      </ul>
      <h3 className="mt-5 text-[13px] text-text-2">Qanday oshirish</h3>
      <ul className="mt-1">
        {data.tips.map((t) => (
          <li key={t.text} className="flex items-baseline justify-between gap-2 py-1.5 text-[13px]">
            <span>{t.text}</span>
            <span className="mono shrink-0 text-[12px] text-success">+{t.points} ball</span>
          </li>
        ))}
      </ul>
      <h3 className="mt-4 text-[13px] text-text-2">Soliq taxmini · noyabr</h3>
      <p className="serif mt-1 text-[28px]">{shortSoum(data.tax.amount)}</p>
      <p className="t-cap mt-1">{data.tax.note}</p>
      <div className="mt-auto flex flex-col gap-1 pt-5">
        <Button variant="plain" onClick={() => setCalcOpen(true)}>
          Kredit kalkulyatori
        </Button>
        {data.application ? (
          <p role="status" className={cn("py-3 text-[14px] font-medium", STATUS[data.application.status].tone)}>
            {STATUS[data.application.status].text}
          </p>
        ) : (
          <>
            <Button variant="primary" size="lg" className="w-full" disabled={!isOwner} onClick={() => setConsentOpen(true)}>
              Bankka ariza yuborish
            </Button>
            <p className="t-cap mt-1 text-center">{isOwner ? "Raqamlar bankka faqat sizning roziligingiz bilan yuboriladi." : "Arizani faqat do‘kon egasi yuboradi."}</p>
          </>
        )}
      </div>
      <ConsentDialog open={consentOpen} onOpenChange={setConsentOpen} />
      <CreditCalculator open={calcOpen} onOpenChange={setCalcOpen} />
    </>
  );
}

export function MaslahatScreen() {
  const nav = useT().nav;
  useCopilotScreen("maslahat");
  const readiness = useReadiness();
  const initial = useMemo(() => [userMessage(INITIAL_QUESTION), assistantMessage(initialAnswer())], []);
  return (
    <Page title={nav.maslahat} subtitle="Kredit, soliq va kreditga tayyorlik">
      <div className="grid grid-cols-1 gap-5 xl:min-h-[calc(100vh-124px)] xl:grid-cols-[minmax(0,936fr)_minmax(0,300fr)]">
        <Tile className="flex h-[780px] min-h-0 flex-col xl:h-auto xl:max-h-[max(860px,calc(100vh-124px))]">
          <TileHeader title="Yordamchi" sub="Ekrandagi raqamlarni tushuntiradi. Raqamlarni Python hisoblaydi." />
          <div className="mt-3 flex min-h-0 flex-1 flex-col">
            <Conversation initial={initial} context={{ screen: "maslahat", selected_ids: [] }} />
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
