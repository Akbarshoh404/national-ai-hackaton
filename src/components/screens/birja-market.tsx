"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useCopilotScreen } from "@/components/raft/shell";
import { Async, EmptyState, Skeleton, SkeletonLines } from "@/components/raft/states";
import { KpiStrip, Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import type { DemandView as Demand, FeedPost, RadarCategory } from "@/lib/api/backend/exchange";
import { useDemand, useLots, useRadar, useRadarFeed } from "@/lib/api/hooks";
import { pct, pctSigned, shortSoum, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS: { key: "all" | RadarCategory; label: string }[] = [
  { key: "all", label: "Hammasi" },
  { key: "phone", label: "Telefon" },
  { key: "laptop", label: "Noutbuk" },
  { key: "car", label: "Avto" },
  { key: "realty", label: "Ko‘chmas mulk" },
];

/** "12 daq oldin", "3 soat oldin", "2 kun oldin". */
function ago(iso: string) {
  const min = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000));
  if (min < 60) return `${min} daq oldin`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} soat oldin`;
  return `${Math.round(h / 24)} kun oldin`;
}

function PostCard({ post }: { post: FeedPost }) {
  return (
    <div key={post.id} className="fade-in">
      <div className="panel mt-3 p-4">
        <p className="t-mono-cap">
          {post.channel} · {ago(post.posted_at)}
        </p>
        <p className="mt-1 text-[14px] font-medium">
          {post.url ? (
            <a href={post.url} target="_blank" rel="noreferrer" className="hover:underline">
              {post.title}
            </a>
          ) : (
            post.title
          )}
        </p>
      </div>
      <p className="t-mono-cap mt-4">
        <Link href="/model" className="hover:underline">
          {post.extractor ?? "Model"}
        </Link>{" "}
        o‘qidi
      </p>
      <dl className="mt-2 flex flex-col gap-2">
        {post.fields.map((f) => (
          <div key={f.label} className="kv text-[13px]">
            <dt>{f.label}</dt>
            <dd>{f.value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-[13px] text-text-2">{post.market !== null ? `Bozor narxi ${usd(post.market)}` : "Bozor narxi uchun o‘xshash e’lonlar yetarli emas"}</p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="serif text-[32px]">{usd(post.price)}</span>
        {post.diff_pct !== null ? (
          <span className={cn("mono text-[12px] font-medium", post.diff_pct >= 0 ? "text-success" : "text-text-2")}>
            {post.diff_pct >= 0 ? `bozordan ${pct(post.diff_pct, 0)} arzon` : `bozordan ${pct(-post.diff_pct, 0)} qimmat`}
          </span>
        ) : null}
      </p>
    </div>
  );
}

/** The newest Telegram posts read by the live listener (polled every 30 s). */
function LiveFeed() {
  const feed = useRadarFeed();
  return (
    <Tile className="flex flex-col">
      <TileHeader title="Jonli lenta" right={feed.isFetching ? "yangilanmoqda" : "har 30 s"} />
      <Async query={feed} skeleton={<SkeletonLines rows={5} height={20} />} isEmpty={(posts) => posts.length === 0} empty={<EmptyState text="Telegram kanallaridan hali e’lon o‘qilmagan." />}>
        {(posts) => (
          <>
            <PostCard post={posts[0]} />
            {posts.length > 1 ? (
              <div className="mt-auto pt-5">
                <h3 className="text-[13px] text-text-2">Oldingi</h3>
                <ul className="mt-2 flex flex-col gap-2 text-[13px]">
                  {posts.slice(1).map((p) => (
                    <li key={p.id} className="flex items-baseline gap-2">
                      <span className="t-mono-cap shrink-0">{ago(p.posted_at)}</span>
                      <span className="truncate-1 flex-1" title={p.title}>
                        {p.title}
                      </span>
                      <span className="t-mono-cap shrink-0">{usd(p.price)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
      </Async>
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
                { label: `${radar.days} kunda topildi`, value: String(radar.total), note: `e’lon bozordan ${radar.min_discount}% va undan arzon` },
                { label: "O‘rtacha chegirma", value: pct(radar.avg_discount, 0), note: "bozor medianasiga nisbatan" },
                { label: "Kutilgan foyda", value: `~${usd(radar.expected_profit)}`, note: `${radar.items.length} ta topilma bo‘yicha` },
                { label: "Kanallar", value: String(radar.channels), note: `${radar.categories} kategoriya` },
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
                    <EmptyState
                      text={filter === "all" ? "Hozircha bozordan arzon e’lon topilmadi." : "Bu toifada topilma yo‘q."}
                      action={
                        filter === "all" ? undefined : (
                          <Button variant="plain" className="-ml-2" onClick={() => setFilter("all")}>
                            Hammasini ko‘rsatish
                          </Button>
                        )
                      }
                    />
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
                              {f.meta ? <div className="t-mono-cap">{f.meta}</div> : null}
                            </td>
                            <td className="r mono font-medium">{usd(f.price)}</td>
                            <td className="r mono text-text-2">{usd(f.market)}</td>
                            <td className="r mono text-success">{pct(f.diff_pct, 0)}</td>
                            <td className="r mono font-medium">~{usd(f.profit)}</td>
                            <td className="r mono text-text-2">{f.days !== null ? `${Math.round(f.days)} kun` : "—"}</td>
                            <td>
                              <div>{f.channel}</div>
                              <div className="t-mono-cap">{ago(f.posted_at)}</div>
                            </td>
                            <td className="r">
                              {f.url ? (
                                <a href={f.url} target="_blank" rel="noreferrer" className="link" aria-label={`${f.title} e’lonini ochish`}>
                                  Ochish
                                </a>
                              ) : null}
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
                <p className="mt-2 text-[12px] text-text-2">
                  Bozor narxi: taqqoslanadigan e’lonlar medianasi. Foyda: bozor narxi − 3% xarajat − xarid narxi. Sotilish: do‘koningiz savdo tarixidan. Har bir narx manba e’longa bog‘langan.
                </p>
              </Tile>
              <LiveFeed />
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
  const [kind, setKind] = useState("all");
  const kinds = useMemo(() => {
    const seen = new Map<string, string>();
    for (const l of query.data?.items ?? []) seen.set(l.kind, l.kind_label);
    return [{ key: "all", label: "Hammasi" }, ...[...seen].map(([key, label]) => ({ key, label }))];
  }, [query.data]);
  const rows = useMemo(() => (query.data?.items ?? []).filter((l) => kind === "all" || l.kind === kind), [query.data, kind]);
  return (
    <Tile>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <TileHeader title="Ulgurji lotlar" sub="Do‘konlar va yetkazib beruvchilarning ulgurji va ortiqcha tovarlari" />
        <div className="seg" role="group" aria-label="Lot turi">
          {kinds.map((k) => (
            <button key={k.key} type="button" className="seg-item" data-active={kind === k.key} aria-pressed={kind === k.key} onClick={() => setKind(k.key)}>
              {k.label}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-3 overflow-x-auto">
        <Async query={query} skeleton={<SkeletonLines rows={6} />} isEmpty={(d) => d.items.length === 0} empty={<EmptyState text="Birjada hozircha faol lot yo‘q." />}>
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
                      <div className="t-cap">{[l.kind_label, l.note].filter(Boolean).join(" · ")}</div>
                    </td>
                    <td className="text-text-2">{l.seller}</td>
                    <td className="text-text-2">{l.location ?? "—"}</td>
                    <td className="r mono">{l.qty} dona</td>
                    <td className="r mono font-medium">{shortSoum(l.unit_price)}</td>
                    <td className="r mono text-text-2">{l.market !== null ? shortSoum(l.market) : "—"}</td>
                    <td className={cn("r mono", l.diff_pct === null ? "text-text-2" : l.diff_pct < 0 ? "text-success" : "text-danger")}>{l.diff_pct !== null ? pctSigned(l.diff_pct) : "—"}</td>
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
  const max = Math.max(1, ...data.districts.map((d) => d.count));
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
            <TileHeader title="Talab: tumanlar bo‘yicha" sub="Birjadagi so‘rovlar soni va eng ko‘p so‘ralgan modellar" right={`oxirgi ${data.days} kun`} />
            <div className="mt-4">{data.districts.length ? <DemandBars data={data} /> : <EmptyState text="So‘nggi kunlarda so‘rov bo‘lmagan." />}</div>
          </Tile>
          <Tile>
            <TileHeader title="Eng ko‘p so‘ralgan" right="so‘rov · dona" />
            <ul className="mt-3">
              {data.models.map((m) => (
                <li key={m.name} className="flex items-baseline gap-3 py-2 text-[13px]">
                  <span className="truncate-1 flex-1" title={m.name}>
                    {m.name}
                  </span>
                  <span className="mono font-medium">{m.requests}</span>
                  <span className="mono w-14 text-right text-[12px] text-text-2">{m.units} dona</span>
                </li>
              ))}
            </ul>
            {data.listed.length ? (
              <>
                <h3 className="mt-4 text-[13px] text-text-2">Telegramda eng ko‘p e’lon qilingan</h3>
                <ul className="mt-2">
                  {data.listed.slice(0, 5).map((m) => (
                    <li key={m.name} className="flex items-baseline gap-3 py-1.5 text-[13px]">
                      <span className="truncate-1 flex-1" title={m.name}>
                        {m.name}
                      </span>
                      <span className="mono font-medium">{m.listings}</span>
                      <span className="mono w-20 text-right text-[12px] text-text-2">{shortSoum(m.avg_price)}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </Tile>
        </div>
      )}
    </Async>
  );
}
