"use client";

import { ChevronDown, Mic, ScanLine } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { PriceWaterfall } from "@/components/charts/price-waterfall";
import { RangeBar } from "@/components/charts/small";
import { useCopilotScreen } from "@/components/raft/shell";
import { Async, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import { useBuyUnit, useParseInput, usePriceVerdict, type PriceParams } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/client";
import { pctSigned, shortSoum, usd, usdSigned } from "@/lib/format";
import { cn } from "@/lib/utils";

const CONDITIONS = [
  { key: "A", label: "Chiziqsiz" },
  { key: "B", label: "Mayda izlar" },
  { key: "C", label: "Shikastlangan" },
] as const;

const SAMPLE_IMEI = "352918110000004";

function detectKind(value: string) {
  if (/t\.me\//i.test(value)) return "link" as const;
  if (/^[\d\s-]{14,}$/.test(value.trim())) return "imei" as const;
  return "text" as const;
}

export function BaholashView() {
  useCopilotScreen("baholash");
  const inputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState(SAMPLE_IMEI);
  const [detected, setDetected] = useState({ model: "iPhone 13 Pro · 256 GB", detail: "Sierra Blue · IMEI ro‘yxatdan o‘tgan" });
  const [params, setParams] = useState<PriceParams>({ query: "iPhone 13 Pro 256", condition: "A", battery: 87, box: true });
  const [repaired, setRepaired] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<"bought" | "declined" | null>(null);

  const parse = useParseInput();
  const verdict = usePriceVerdict(params);
  const buy = useBuyUnit();

  const update = (patch: Partial<PriceParams>) => {
    setOutcome(null);
    setParams((p) => ({ ...p, ...patch }));
  };

  const submit = (value = input) => {
    if (!value.trim()) return;
    setInputError(null);
    parse.mutate(
      { kind: detectKind(value), value },
      {
        onSuccess: (r) => {
          setDetected({ model: r.model, detail: r.detail });
          update({ query: r.query, ...(r.condition ? { condition: r.condition } : {}), ...(r.battery ? { battery: r.battery } : {}), ...(r.box !== null ? { box: r.box } : {}) });
        },
        onError: (e) => setInputError(e instanceof ApiError ? e.message : "Aniqlab bo‘lmadi. Qayta urinib ko‘ring."),
      },
    );
  };

  const voice = () => {
    setInputError(null);
    parse.mutate(
      { kind: "voice", value: "" },
      {
        onError: (e) => {
          setInputError(e instanceof ApiError ? e.message : "Ovozli kiritish ishlamadi. Matn bilan yozing.");
          setInput("");
          inputRef.current?.focus();
        },
      },
    );
  };

  const v = verdict.data;

  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-[minmax(0,390fr)_minmax(0,434fr)_minmax(0,394fr)]">
      <Tile className="flex flex-col md:col-span-2 xl:col-span-1 xl:row-span-2">
        <h2 className="text-[20px] leading-[28px] font-semibold">Mijoz nima sotmoqda?</h2>
        <form
          className="mt-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <label className="field-label" htmlFor="price-input">
            IMEI, model yoki t.me havola
          </label>
          <div className="relative">
            <input
              id="price-input"
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPaste={(e) => {
                const text = e.clipboardData.getData("text");
                if (/t\.me\//i.test(text)) {
                  e.preventDefault();
                  setInput(text);
                  submit(text);
                }
              }}
              placeholder="iphone 13 pro 256 87% quti bor"
              aria-describedby={inputError ? "price-error" : undefined}
              className="input mono h-14 pr-[100px] text-[15px]"
            />
            <div className="absolute top-1.5 right-1.5 flex gap-1">
              <button type="button" className="icon-btn bg-[var(--nested)]" aria-label="Ovoz bilan kiritish" onClick={voice}>
                <Mic size={18} strokeWidth={1.75} aria-hidden />
              </button>
              <button
                type="button"
                className="icon-btn bg-[var(--nested)]"
                aria-label="Namuna IMEI’ni skanerlash"
                onClick={() => {
                  setInput(SAMPLE_IMEI);
                  submit(SAMPLE_IMEI);
                }}
              >
                <ScanLine size={18} strokeWidth={1.75} aria-hidden />
              </button>
            </div>
          </div>
          <p className="t-cap mt-1">Enter bosing yoki Telegram havolasini joylang.</p>
          {inputError ? (
            <p id="price-error" role="alert" className="mt-1 text-[13px] text-danger">
              {inputError}
            </p>
          ) : null}
        </form>

        <div className="panel mt-3 p-4" aria-live="polite">
          <p className="text-[15px] font-semibold">{detected.model}</p>
          <p className="mt-0.5 text-[13px] text-text-2">{detected.detail}</p>
        </div>

        <fieldset className="mt-5">
          <legend className="field-label">Tashqi holati</legend>
          <div className="grid grid-cols-[1fr_1fr_1.25fr] gap-2">
            {CONDITIONS.map((c) => (
              <label
                key={c.key}
                className={cn(
                  "cursor-pointer rounded-[16px] border bg-white/60 p-3 transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[rgb(14_124_112/0.4)]",
                  params.condition === c.key ? "border-[1.5px] border-text bg-white" : "border-border hover:border-border-strong",
                )}
              >
                <input type="radio" name="condition" className="sr-only" checked={params.condition === c.key} onChange={() => update({ condition: c.key })} />
                <span className="block text-[17px] font-semibold">{c.key}</span>
                <span className="mt-1 block truncate text-[12px] text-text-2" title={c.label}>
                  {c.label}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="mt-5">
          <div className="flex items-baseline justify-between">
            <span id="battery-label" className="text-[13px] text-text-2">
              Batareya salomatligi
            </span>
            <span className="mono text-[14px] font-medium">{params.battery}%</span>
          </div>
          <Slider aria-label="Batareya salomatligi" min={60} max={100} step={1} value={[params.battery]} onValueChange={([value]) => update({ battery: value })} />
        </div>

        <details className="group panel mt-auto">
          <summary className="flex min-h-[64px] list-none items-center justify-between gap-3 rounded-[16px] p-4 [&::-webkit-details-marker]:hidden">
            <span>
              <span className="block text-[14px] font-medium">Qo‘shimcha ma’lumotlar</span>
              <span className="block text-[13px] text-text-2">
                {params.box ? "Quti bor" : "Quti yo‘q"} · {repaired ? "ta’mirlangan" : "ta’mirlanmagan"}
              </span>
            </span>
            <ChevronDown size={18} strokeWidth={1.75} aria-hidden className="shrink-0 transition-transform duration-200 group-open:rotate-180" />
          </summary>
          <div className="flex flex-col gap-1 px-4 pb-3 text-[13px]">
            <label className="flex min-h-11 items-center gap-3">
              <Checkbox checked={params.box} onCheckedChange={(c) => update({ box: c === true })} aria-label="Quti va hujjatlar bor" />
              Quti va hujjatlar bor
            </label>
            <label className="flex min-h-11 items-center gap-3">
              <Checkbox checked={repaired} onCheckedChange={(c) => setRepaired(c === true)} aria-label="Ta’mirlangan" />
              Ta’mirlangan
            </label>
          </div>
        </details>
      </Tile>

      <Tile className="md:col-span-2">
        {!v ? (
          verdict.isError ? (
            <Async query={verdict} skeleton={null}>
              {() => null}
            </Async>
          ) : (
            <div className="flex flex-col gap-3" role="status" aria-label="Yuklanmoqda">
              <Skeleton className="h-[72px] w-1/2" />
              <Skeleton className="h-[80px]" />
              <Skeleton className="h-12" />
            </div>
          )
        ) : (
          <>
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-[13px] text-text-2">Ko‘pi bilan shuncha to‘lang</h2>
              <p className="text-[12px] font-medium text-text-2">{v.listings} ta e’lon asosida</p>
            </div>
            <p className="mt-2 flex flex-wrap items-baseline gap-x-3">
              <span className="serif text-[64px]">{usd(v.max_price)}</span>
              <span className="text-[15px] text-text-2">≈ {shortSoum(v.soum)}</span>
            </p>
            <dl className="panel mt-4 grid grid-cols-2 sm:grid-cols-4">
              {[
                ["Avval taklif qiling", usd(v.first_offer)],
                ["Qayta sotish narxi", usd(v.resale)],
                ["Sizning foydangiz", usdSigned(v.profit)],
                ["Sotilish vaqti", `~${v.days} kun`],
              ].map(([label, value], i) => (
                <div key={label} className={cn("min-w-0 p-4", i > 0 && "sm:border-l sm:border-[rgb(15_23_22/0.06)]")}>
                  <dt className="truncate text-[13px] text-text-2" title={label}>
                    {label}
                  </dt>
                  <dd className="mt-1 text-[20px] leading-7 font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-4">
              <RangeBar
                min={Math.min(v.max_price, v.range_low) * 0.92}
                max={v.range_high * 1.04}
                bandLow={v.range_low}
                bandHigh={v.range_high}
                markers={[
                  { value: v.max_price, label: `Sizning chegarangiz ${usd(v.max_price)}`, tone: "accent" },
                  { value: v.median, label: `Bozor medianasi ${usd(v.median)}`, tone: "text" },
                ]}
                ends={`E’lonlar ${usd(v.range_low)} – ${usd(v.range_high)}`}
                ariaLabel={`Chegarangiz ${usd(v.max_price)}, bozor medianasi ${usd(v.median)}, e’lonlar ${usd(v.range_low)} dan ${usd(v.range_high)} gacha`}
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              {outcome === "bought" ? (
                <p role="status" className="flex min-h-12 items-center gap-2 text-[14px]">
                  {v.model} omborga qo‘shildi.
                  <Link className="link" href="/narxlar?tab=ombor">
                    Omborni ochish
                  </Link>
                </p>
              ) : outcome === "declined" ? (
                <p role="status" className="flex min-h-12 items-center text-[14px] text-text-2">
                  Mijoz rad etdi, bitim yozilmadi.
                </p>
              ) : (
                <>
                  <Button
                    variant="primary"
                    size="lg"
                    disabled={buy.isPending}
                    onClick={() =>
                      buy.mutate(
                        { model: v.model, detail: v.detail, price: v.max_price, resale: v.resale, median: v.median, days: v.days, condition: params.condition, battery: params.battery },
                        { onSuccess: () => setOutcome("bought") },
                      )
                    }
                  >
                    Sotib olish va omborga qo‘shish
                  </Button>
                  <Button variant="plain" onClick={() => setOutcome("declined")}>
                    Mijoz rad etdi
                  </Button>
                  {buy.isError ? (
                    <p role="alert" className="text-[13px] text-danger">
                      Saqlanmadi. Qayta urinib ko‘ring.
                    </p>
                  ) : null}
                </>
              )}
            </div>
          </>
        )}
      </Tile>

      <Tile>
        <TileHeader title="Narx nimadan iborat" sub="Bozor medianasidan maksimal xarid narxigacha. Har bir qadam ustiga olib boring." />
        <div className="mt-4">{v ? <PriceWaterfall steps={v.steps} /> : <Skeleton className="h-[200px]" />}</div>
      </Tile>

      <Tile className="flex flex-col">
        <TileHeader title="Eng yaqin e’lonlar" right="30 kun" />
        <div className="mt-2 flex-1">
          {v ? (
            <ul>
              {v.comparables.map((c, i) => (
                <li key={c.url} className={cn("flex items-center justify-between gap-3 py-3", i > 0 && "border-t border-[rgb(15_23_22/0.06)]")}>
                  <div className="min-w-0">
                    <a href={c.url} target="_blank" rel="noreferrer" className="text-[15px] font-semibold tabular-nums hover:underline">
                      {usd(c.price)}
                    </a>
                    <p className="truncate text-[13px] text-text-2" title={c.meta}>
                      {c.meta}
                    </p>
                  </div>
                  <p className="shrink-0 text-[13px] text-text-2">
                    {c.rating} <span className="mono font-medium text-text">{pctSigned(c.diff_pct, 0)}</span>
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <SkeletonLines rows={3} height={48} />
          )}
        </div>
        {v ? (
          <Link href="/birja?tab=radar" className="link text-[13px]">
            Barcha {v.listings} ta e’lonni ko‘rish
          </Link>
        ) : null}
      </Tile>
    </div>
  );
}
