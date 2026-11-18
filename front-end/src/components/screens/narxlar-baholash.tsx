"use client";

import { ChevronDown, Mic, Square } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PriceWaterfall } from "@/components/charts/price-waterfall";
import { RangeBar } from "@/components/charts/small";
import { useCopilotScreen, useShell } from "@/components/raft/shell";
import { Async, Skeleton, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { InputNotRecognized, useBuyUnit, useParseInput, usePriceVerdict, type ParseInput, type PriceParams } from "@/lib/api/hooks";
import type { Detected } from "@/lib/api/backend/prices";
import { ApiError } from "@/lib/api/client";
import { group, num, pctSigned, shortNum, shortSoum, soum, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

const CONDITIONS = [
  { key: "new", short: "Yangi", label: "Ishlatilmagan" },
  { key: "A", short: "A", label: "Chiziqsiz" },
  { key: "B", short: "B", label: "Mayda izlar" },
  { key: "C", short: "C", label: "Shikastlangan" },
] as const;
type Condition = (typeof CONDITIONS)[number]["key"];
const GRADED = new Set(["phone", "laptop"]);
const CONFIDENCE: Record<string, string> = { high: "yuqori", medium: "o‘rtacha", low: "past" };

function detectKind(value: string) {
  if (/t\.me\//i.test(value)) return "link" as const;
  if (/^[\d\s-]{14,}$/.test(value.trim())) return "imei" as const;
  return "text" as const;
}

const errorText = (e: unknown, fallback: string) => (e instanceof InputNotRecognized || e instanceof ApiError ? e.message : fallback);

export function BaholashView() {
  useCopilotScreen("baholash");
  const inputRef = useRef<HTMLInputElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const [input, setInput] = useState("");
  const [detected, setDetected] = useState<Detected | null>(null);
  const [condition, setCondition] = useState<Condition>("A");
  const [storage, setStorage] = useState<number | null>(null);
  const [repaired, setRepaired] = useState(false);
  const [imeiRegistered, setImeiRegistered] = useState(true);
  const [paid, setPaid] = useState("");
  const [recording, setRecording] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<"bought" | "declined" | null>(null);

  const graded = detected ? GRADED.has(detected.category) : false;
  const isPhone = detected?.category === "phone";
  const params: PriceParams | null = detected
    ? {
        category: detected.category,
        brand: detected.brand,
        model: detected.model,
        condition: graded ? condition : detected.condition,
        attrs: {
          ...detected.attrs,
          ...(storage ? { storage_gb: storage } : {}),
          ...(isPhone ? { repaired, imei_registered: imeiRegistered } : {}),
        },
      }
    : null;

  const parse = useParseInput();
  const verdict = usePriceVerdict(params);
  const buy = useBuyUnit();
  // Appraisers price only; buying into stock is done by the owner or a manager (backend core/permissions.py).
  const canBuy = useShell().account.roleCode !== "appraiser";
  const v = verdict.data;

  useEffect(() => {
    if (v) setPaid(String(v.max_uzs));
  }, [v?.max_uzs]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => recorder.current?.stream.getTracks().forEach((t) => t.stop()), []);

  const apply = (d: Detected) => {
    setOutcome(null);
    setDetected(d);
    const c = d.condition && CONDITIONS.some((x) => x.key === d.condition) ? (d.condition as Condition) : "A";
    setCondition(c);
    setStorage(typeof d.attrs.storage_gb === "number" ? d.attrs.storage_gb : d.storage_options.length === 1 ? d.storage_options[0] : null);
    setRepaired(d.attrs.repaired === true);
    setImeiRegistered(d.attrs.imei_registered !== false);
  };

  const run = (value: ParseInput, fallback: string) => {
    setInputError(null);
    parse.mutate(value, { onSuccess: apply, onError: (e) => setInputError(errorText(e, fallback)) });
  };

  const submit = (value = input) => {
    if (!value.trim()) return;
    run({ kind: detectKind(value), value }, "Aniqlab bo‘lmadi. Qayta urinib ko‘ring.");
  };

  const voice = async () => {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    setInputError(null);
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setInputError("Brauzer ovoz yozishni qo‘llamaydi. Matn bilan yozing.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        recorder.current = null;
        setRecording(false);
        const audio = new Blob(chunks, { type: (rec.mimeType || "audio/webm").split(";")[0] });
        run({ kind: "voice", audio }, "Ovozli kiritish ishlamadi. Matn bilan yozing.");
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
    } catch {
      setInputError("Mikrofonga ruxsat berilmadi. Matn bilan yozing.");
      inputRef.current?.focus();
    }
  };

  const change = (fn: () => void) => {
    setOutcome(null);
    fn();
  };

  const paidValue = Number(paid.replace(/\s/g, ""));

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
              className="input mono h-14 pr-[60px] text-[15px]"
            />
            <div className="absolute top-1.5 right-1.5 flex gap-1">
              <button type="button" className={cn("icon-btn", recording && "text-danger")} aria-label={recording ? "Yozishni to‘xtatish" : "Ovoz bilan kiritish"} aria-pressed={recording} onClick={voice}>
                {recording ? <Square size={16} strokeWidth={1.75} aria-hidden /> : <Mic size={18} strokeWidth={1.75} aria-hidden />}
              </button>
            </div>
          </div>
          <p className="t-cap mt-1">{recording ? "Gapiring, tugatgach to‘xtatish tugmasini bosing." : parse.isPending ? "Aniqlanmoqda…" : "Enter bosing yoki Telegram havolasini joylang."}</p>
          {inputError ? (
            <p id="price-error" role="alert" className="mt-1 text-[13px] text-danger">
              {inputError}
            </p>
          ) : null}
        </form>

        <div className="panel mt-3 p-4" aria-live="polite">
          {detected ? (
            <>
              <p className="text-[15px] font-semibold">{detected.label}</p>
              <p className="mt-1 text-[13px] text-text-2">{detected.detail}</p>
            </>
          ) : (
            <p className="text-[13px] text-text-2">Mahsulot hali kiritilmagan.</p>
          )}
        </div>

        {detected && detected.storage_options.length > 1 ? (
          <fieldset className="mt-5">
            <legend className="field-label">Xotira</legend>
            <div className="flex flex-wrap gap-2">
              {detected.storage_options.map((gb) => (
                <label
                  key={gb}
                  className={cn(
                    "cursor-pointer rounded-[16px] border bg-white/60 px-4 py-2 text-[14px] font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[rgb(14_124_112/0.4)]",
                    storage === gb ? "border-[1.5px] border-text bg-white" : "border-border hover:border-border-strong",
                  )}
                >
                  <input type="radio" name="storage" className="sr-only" checked={storage === gb} onChange={() => change(() => setStorage(gb))} />
                  {gb} GB
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}

        {!detected || graded ? (
          <fieldset className="mt-5" disabled={!detected}>
            <legend className="field-label">Tashqi holati</legend>
            <div className="grid grid-cols-4 gap-2">
              {CONDITIONS.map((c) => (
                <label
                  key={c.key}
                  className={cn(
                    "cursor-pointer rounded-[16px] border bg-white/60 p-3 transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[rgb(14_124_112/0.4)]",
                    condition === c.key ? "border-[1.5px] border-text bg-white" : "border-border hover:border-border-strong",
                  )}
                >
                  <input type="radio" name="condition" className="sr-only" checked={condition === c.key} onChange={() => change(() => setCondition(c.key))} />
                  <span className="block text-[17px] font-semibold">{c.short}</span>
                  <span className="mt-1 block truncate text-[12px] text-text-2" title={c.label}>
                    {c.label}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}

        {isPhone ? (
          <details className="group panel mt-auto">
            <summary className="flex min-h-[64px] list-none items-center justify-between gap-3 rounded-[16px] p-4 [&::-webkit-details-marker]:hidden">
              <span>
                <span className="block text-[14px] font-medium">Qo‘shimcha ma’lumotlar</span>
                <span className="block text-[13px] text-text-2">
                  {imeiRegistered ? "IMEI ro‘yxatdan o‘tgan" : "IMEI ro‘yxatdan o‘tmagan"} · {repaired ? "ta’mirlangan" : "ta’mirlanmagan"}
                </span>
              </span>
              <ChevronDown size={18} strokeWidth={1.75} aria-hidden className="shrink-0 transition-transform duration-200 group-open:rotate-180" />
            </summary>
            <div className="flex flex-col gap-1 px-4 pb-3 text-[13px]">
              <label className="flex min-h-11 items-center gap-3">
                <Checkbox checked={imeiRegistered} onCheckedChange={(c) => change(() => setImeiRegistered(c === true))} aria-label="IMEI ro‘yxatdan o‘tgan" />
                IMEI ro‘yxatdan o‘tgan
              </label>
              <label className="flex min-h-11 items-center gap-3">
                <Checkbox checked={repaired} onCheckedChange={(c) => change(() => setRepaired(c === true))} aria-label="Ta’mirlangan" />
                Ta’mirlangan (almashtirilgan qism bor)
              </label>
            </div>
          </details>
        ) : null}
      </Tile>

      <Tile className="md:col-span-2">
        {!params ? (
          <div className="flex min-h-[200px] flex-col justify-center">
            <h2 className="text-[13px] text-text-2">Ko‘pi bilan shuncha to‘lang</h2>
            <p className="mt-2 text-[15px] text-text-2">IMEI, model nomi, ovoz yoki Telegram havolasini kiriting — narx bozordagi e’lonlardan hisoblanadi.</p>
          </div>
        ) : !v ? (
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
              <p className="text-[12px] font-medium text-text-2" title={v.basis}>
                {v.listings} ta e’lon asosida · ishonch {CONFIDENCE[v.confidence]}
              </p>
            </div>
            <p className={cn("mt-2 flex flex-wrap items-baseline gap-x-3", verdict.isFetching && "opacity-60")}>
              <span className="serif text-[64px]">{usd(v.max_usd)}</span>
              <span className="text-[15px] text-text-2">≈ {soum(v.max_uzs)}</span>
            </p>
            <dl className="panel mt-4 grid grid-cols-2 sm:grid-cols-4">
              {[
                ["Qayta sotish narxi", shortSoum(v.resale)],
                ["Sotish xarajati", shortSoum(v.handling)],
                ["Sizning foydangiz", `+${shortSoum(v.profit)}`],
                ["Sotilish vaqti", v.days === null ? "yo‘q" : `~${Math.round(v.days)} kun`],
              ].map(([label, value], i) => (
                <div key={label} className={cn("min-w-0 p-4", i > 0 && "sm:border-l sm:border-[rgb(15_23_22/0.06)]")} title={label === "Sotilish vaqti" ? (v.days_basis ?? undefined) : undefined}>
                  <dt className="truncate text-[13px] text-text-2" title={label}>
                    {label}
                  </dt>
                  <dd className="mt-1 text-[20px] leading-7 font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-4">
              <RangeBar
                min={Math.min(v.max_uzs, v.range_low) * 0.92}
                max={Math.max(v.range_high, v.median) * 1.04}
                bandLow={v.range_low}
                bandHigh={v.range_high}
                markers={[
                  { value: v.max_uzs, label: `Sizning chegarangiz ${shortNum(v.max_uzs)}`, tone: "accent" },
                  { value: v.median, label: `Bozor medianasi ${shortNum(v.median)}`, tone: "text" },
                ]}
                ends={`E’lonlar (25–75%) ${shortNum(v.range_low)} – ${shortSoum(v.range_high)}`}
                ariaLabel={`Chegarangiz ${soum(v.max_uzs)}, bozor medianasi ${soum(v.median)}, e’lonlar ${soum(v.range_low)} dan ${soum(v.range_high)} gacha`}
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              {outcome === "bought" ? (
                <p role="status" className="flex min-h-12 items-center gap-2 text-[14px]">
                  {detected?.label} omborga qo‘shildi.
                  <Link className="link" href="/narxlar?tab=ombor">
                    Omborni ochish
                  </Link>
                </p>
              ) : outcome === "declined" ? (
                <p role="status" className="flex min-h-12 items-center text-[14px] text-text-2">
                  Mijoz rad etdi, bitim yozilmadi.
                </p>
              ) : detected && !canBuy ? (
                <p className="flex min-h-12 items-center text-[14px] text-text-2">Sotib olishni ega yoki menejer omborga yozadi.</p>
              ) : detected ? (
                <>
                  <label className="flex items-center gap-2 text-[13px] text-text-2">
                    To‘langan narx
                    <input
                      inputMode="numeric"
                      value={paid ? group(Number(paid.replace(/\s/g, "")) || 0) : ""}
                      onChange={(e) => setPaid(e.target.value.replace(/\D/g, ""))}
                      className={cn("input mono h-12 w-[150px] text-right text-[14px]", paidValue > v.max_uzs && "border-warning")}
                      aria-label="To‘langan narx, so‘m"
                    />
                    so‘m
                  </label>
                  <Button
                    variant="primary"
                    size="lg"
                    disabled={buy.isPending || !(paidValue > 0)}
                    onClick={() =>
                      buy.mutate(
                        {
                          category: detected.category,
                          brand: detected.brand,
                          model: detected.model,
                          condition: params.condition,
                          attrs: params.attrs,
                          unit_cost: paidValue,
                          list_price_uzs: v.resale,
                          identifier: detected.identifier,
                        },
                        { onSuccess: () => setOutcome("bought") },
                      )
                    }
                  >
                    Sotib olish va omborga qo‘shish
                  </Button>
                  <Button variant="plain" onClick={() => setOutcome("declined")}>
                    Mijoz rad etdi
                  </Button>
                  {paidValue > v.max_uzs ? <p className="text-[13px] text-warning">Chegaradan {num(paidValue - v.max_uzs)} so‘m qimmat.</p> : null}
                  {buy.isError ? (
                    <p role="alert" className="text-[13px] text-danger">
                      {errorText(buy.error, "Saqlanmadi. Qayta urinib ko‘ring.")}
                    </p>
                  ) : null}
                </>
              ) : null}
            </div>
          </>
        )}
      </Tile>

      <Tile>
        <TileHeader title="Narx nimadan iborat" sub="Bozor narxidan maksimal xarid narxigacha. Har bir qadam ustiga olib boring." />
        <div className="mt-4">
          {v ? (
            <PriceWaterfall steps={v.steps} format={shortSoum} tickFormat={shortNum} />
          ) : params && !verdict.isError ? (
            <Skeleton className="h-[200px]" />
          ) : (
            <p className="text-[13px] text-text-2">Narx hisoblangach ko‘rinadi.</p>
          )}
        </div>
      </Tile>

      <Tile className="flex flex-col">
        <TileHeader title="So‘nggi o‘xshash e’lonlar" />
        <div className="mt-2 flex-1">
          {v ? (
            v.comparables.length ? (
              <ul>
                {v.comparables.map((c, i) => (
                  <li key={c.key} className={cn("flex items-center justify-between gap-3 py-3", i > 0 && "border-t border-[rgb(15_23_22/0.06)]")}>
                    <div className="min-w-0">
                      {c.url ? (
                        <a href={c.url} target="_blank" rel="noreferrer" className="text-[15px] font-semibold tabular-nums hover:underline">
                          {soum(c.price)}
                        </a>
                      ) : (
                        <span className="text-[15px] font-semibold tabular-nums">{soum(c.price)}</span>
                      )}
                      <p className="truncate text-[13px] text-text-2" title={c.meta}>
                        {c.meta}
                      </p>
                    </div>
                    <p className="shrink-0 text-[13px] text-text-2">
                      {c.condition} <span className="mono font-medium text-text">{pctSigned(c.diff_pct, 0)}</span>
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-text-2">E’lonlar yo‘q.</p>
            )
          ) : params && !verdict.isError ? (
            <SkeletonLines rows={3} height={48} />
          ) : (
            <p className="text-[13px] text-text-2">Narx hisoblangach ko‘rinadi.</p>
          )}
        </div>
      </Tile>
    </div>
  );
}
