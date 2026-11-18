"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useCopilotScreen } from "@/components/raft/shell";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { KpiStrip, Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { useDemand, useLots, useNextPost, useRadar } from "@/lib/api/hooks";
import type { Demand, Radar, RadarFind } from "@/lib/api/schemas";
import { num, pct, pctSigned, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS: { key: "all" | RadarFind["category"]; label: string }[] = [
  { key: "all", label: "Hammasi" },
  { key: "phone", label: "Telefon" },
  { key: "laptop", label: "Noutbuk" },
  { key: "car", label: "Avto" },
  { key: "realty", label: "Ko‘chmas mulk" },
];

function LiveFeed({ radar }: { radar: Radar }) {
  const next = useNextPost();
  const [reading, setReading] = useState(false);
  const post = radar.feed;

  const readNext = async () => {
    setReading(true);
    try {
      await Promise.all([next.mutateAsync(), new Promise((r) => setTimeout(r, 800))]);
    } finally {
      setReading(false);
    }
  };

  return (
    <Tile className="flex flex-col">
      <TileHeader title="Jonli lenta" right="hozir" />
      <div className="panel mt-3 p-4">
        <p className="t-mono-cap">
          {post.channel} · {post.time}
        </p>
        <p className="mt-1 text-[14px]">{post.text}</p>
      </div>
      {reading ? (
        <div className="mt-4" role="status" aria-label="E’lon o‘qilmoqda">
          <p className="t-mono-cap mb-3">Raft-Extractor o‘qimoqda</p>
          <SkeletonLines rows={5} height={20} />
        </div>
      ) : (
        <div key={post.id} className="fade-in">
          <p className="t-mono-cap mt-4">
            <Link href="/model" className="hover:underline">
              Raft-Extractor
            </Link>{" "}
            o‘qidi · {num(post.latency_s, 1)} s
          </p>
          <dl className="mt-2 flex flex-col gap-2">
            {post.fields.map((f) => (
              <div key={f.label} className="kv text-[13px]">
                <dt>{f.label}</dt>
                <dd>{f.value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-[13px] text-text-2">{post.median_label}</p>
          <p className="mt-1 flex items-baseline gap-2">
            <span className="serif text-[32px]">{usd(post.price)}</span>
            <span className="mono text-[12px] font-medium text-success">bozordan {pct(post.diff_pct, 0)}</span>
          </p>
        </div>
      )}
      <div className="mt-3">
        {radar.has_more_posts ? (
          <Button onClick={() => void readNext()} disabled={reading}>
            Keyingi e’lonni o‘qish
          </Button>
        ) : (
          <p className="text-[13px] text-text-2">Yangi e’lon kutilmoqda.</p>
        )}
      </div>
      {radar.previous.length ? (
        <div className="mt-auto pt-5">
          <h3 className="text-[13px] text-text-2">Oldingi</h3>
          <ul className="mt-2 flex flex-col gap-2 text-[13px]">
            {radar.previous.slice(0, 3).map((p) => (
              <li key={p.time} className="flex items-baseline gap-2">
                <span className="t-mono-cap">{p.time}</span>
                <span className="truncate-1 flex-1" title={p.title}>
                  {p.title}
                </span>
                <span className="t-mono-cap shrink-0">{p.value}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Tile>
  );
}

export function RadarView() {
  useCopilotScreen("radar");
  const query = useRadar();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const [showAll, setShowAll] = useState(false);

  return (
    <Async query={query} skeleton={<Skeleton className="h-[480px] rounded-[36px]" />}>
      {(radar) => {
        const rows = radar.items.filter((f) => filter === "all" || f.category === filter);
        const visible = showAll ? rows : rows.slice(0, 8);
        return (
          <>
            <KpiStrip
              items={[
                { label: "Bugun topildi", value: String(radar.total), note: "e’lon bozordan 8% va undan arzon" },
                { label: "O‘rtacha chegirma", value: pct(radar.avg_discount, 0), note: "bozor medianasiga nisbatan" },
                { label: "Kutilgan foyda", value: `~${usd(radar.expected_profit)}`, note: `${radar.total} ta topilma bo‘yicha` },
                { label: "Kanallar", value: String(radar.channels), note: "5 kategoriya, jonli rejim" },
              ]}
            />
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,938fr)_minmax(0,300fr)]">
              <Tile>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <TileHeader title="Topilmalar" sub="Kutilgan foyda bo‘yicha saralangan" />
                  <div className="seg max-w-full overflow-x-auto" role="group" aria-label="Toifa">
                    {FILTERS.map((f) => (
                      <button key={f.key} type="button" className="seg-item" data-active={filter === f.key} aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
                        {f.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="relative mt-3 overflow-x-auto">
                  {rows.length === 0 ? (
                    <EmptyState text="Bu toifada bugun topilma yo‘q." action={<Button variant="plain" className="-ml-2" onClick={() => setFilter("all")}>Hammasini ko‘rsatish</Button>} />
                  ) : (
                    <table className="data-table min-w-[760px]">
                      <thead>
                        <tr>
                          <th>Mahsulot</th>
                          <th className="r">Narx</th>
                          <th className="r">Bozor</th>
                          <th className="r">Farq</th>
                          <th className="r">Foyda</th>
                          <th className="r">Sotilish</th>
                          <th>Manba</th>
                          <th>
                            <span className="sr-only">Havola</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((f) => (
                          <tr key={f.id} className={cn(f.is_new && "fade-in bg-accent-soft")}>
                            <td>
                              <div className="font-medium">
                                {f.title}
                                {f.is_new ? <span className="ml-2 text-[12px] font-medium text-accent-text">yangi</span> : null}
                              </div>
                              <div className="t-mono-cap">{f.meta}</div>
                            </td>
                            <td className="r mono font-medium">{usd(f.price)}</td>
                            <td className="r mono text-text-2">{usd(f.market)}</td>
                            <td className="r mono text-success">{pct(f.diff_pct, 0)}</td>
                            <td className="r mono font-medium">~{usd(f.profit)}</td>
                            <td className="r mono text-text-2">{f.days} kun</td>
                            <td>
                              <div>{f.channel}</div>
                              <div className="t-mono-cap">{f.age}</div>
                            </td>
                            <td className="r">
                              <a href={f.url} target="_blank" rel="noreferrer" className="link" aria-label={`${f.title} e’lonini ochish`}>
                                Ochish
                              </a>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                {rows.length > 8 ? (
                  <Button variant="plain" className="-ml-2 mt-1" onClick={() => setShowAll((v) => !v)}>
                    {showAll ? "Kamroq ko‘rsatish" : `Yana ${rows.length - 8} tasini ko‘rsatish`}
                  </Button>
                ) : null}
                <p className="mt-2 text-[12px] text-text-2">Bozor narxi: 30 kunlik taqqoslanadigan e’lonlar medianasi. Har bir narx manba e’longa bog‘langan.</p>
              </Tile>
              <LiveFeed radar={radar} />
            </div>
          </>
        );
      }}
    </Async>
  );
}

export function LotsView() {
  useCopilotScreen("lotlar");
  const query = useLots();
  const [kind, setKind] = useState("Hammasi");
  const kinds = ["Hammasi", "Ulgurji", "Ortiqcha qoldiq"];
  const rows = useMemo(() => (query.data?.items ?? []).filter((l) => kind === "Hammasi" || l.kind === kind), [query.data, kind]);
  return (
    <Tile>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <TileHeader title="Ulgurji lotlar" sub="Do‘konlar va yetkazib beruvchilarning ulgurji va ortiqcha tovarlari" />
        <div className="seg" role="group" aria-label="Lot turi">
          {kinds.map((k) => (
            <button key={k} type="button" className="seg-item" data-active={kind === k} aria-pressed={kind === k} onClick={() => setKind(k)}>
              {k}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-3 overflow-x-auto">
        <Async query={query} skeleton={<SkeletonLines rows={6} />}>
          {() => (
            <table className="data-table min-w-[760px]">
              <thead>
                <tr>
                  <th>Lot</th>
                  <th>Sotuvchi</th>
                  <th>Joy</th>
                  <th className="r">Miqdor</th>
                  <th className="r">Narx</th>
                  <th className="r">Bozor</th>
                  <th className="r">Farq</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((l) => (
                  <tr key={l.id}>
                    <td>
                      <div className="font-medium">{l.title}</div>
                      <div className="t-cap">{l.kind}</div>
                    </td>
                    <td className="text-text-2">{l.seller}</td>
                    <td className="text-text-2">{l.location}</td>
                    <td className="r mono">{l.qty} dona</td>
                    <td className="r mono font-medium">{usd(l.unit_price)}</td>
                    <td className="r mono text-text-2">{usd(l.market)}</td>
                    <td className={cn("r mono", l.diff_pct < 0 ? "text-success" : "text-danger")}>{pctSigned(l.diff_pct)}</td>
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

export function DemandBars({ data }: { data: Demand }) {
  const max = Math.max(...data.districts.map((d) => d.count));
  return (
    <ul className="flex flex-col gap-2">
      {data.districts.map((d) => (
        <li key={d.name} className="grid grid-cols-[110px_minmax(0,1fr)_28px] items-center gap-3 text-[13px] lg:grid-cols-[130px_minmax(0,1fr)_28px_minmax(0,240px)]">
          <span className="truncate">{d.name}</span>
          <div className="h-2.5 rounded-full bg-[rgb(15_23_22/0.06)]" role="img" aria-label={`${d.name}: ${d.count} ta so‘rov`}>
            <div className="h-full rounded-full bg-[var(--chart-s1)]" style={{ width: `${(d.count / max) * 100}%` }} />
          </div>
          <span className="mono text-right font-medium">{d.count}</span>
          <span className="truncate text-text-2 max-lg:hidden" title={d.models}>
            {d.models}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DemandView() {
  useCopilotScreen("talab");
  const query = useDemand();
  return (
    <Async query={query} skeleton={<Skeleton className="h-[320px] rounded-[36px]" />}>
      {(data) => (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <Tile className="xl:col-span-2">
            <TileHeader title="Talab: tumanlar bo‘yicha" sub="Birjadagi so‘rovlar soni va eng ko‘p so‘ralgan modellar" right="oxirgi 30 kun" />
            <div className="mt-4">
              <DemandBars data={data} />
            </div>
          </Tile>
          <Tile>
            <TileHeader title="Eng ko‘p so‘ralgan" right="30 kun" />
            <ul className="mt-3">
              {data.models.map((m) => (
                <li key={m.name} className="flex items-baseline gap-3 py-2 text-[13px]">
                  <span className="truncate-1 flex-1" title={m.name}>
                    {m.name}
                  </span>
                  <span className="mono font-medium">{m.requests}</span>
                  <span className={cn("mono w-12 text-right text-[12px]", m.change_pct >= 0 ? "text-success" : "text-danger")}>{pctSigned(m.change_pct, 0)}</span>
                </li>
              ))}
            </ul>
          </Tile>
        </div>
      )}
    </Async>
  );
}
