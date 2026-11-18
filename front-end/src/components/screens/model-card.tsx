"use client";

import { Page } from "@/components/raft/shell";
import { Async, SkeletonLines } from "@/components/raft/states";
import { Tile } from "@/components/raft/tile";
import { useT } from "@/i18n";
import { useModelCard } from "@/lib/api/hooks";
import { pct } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ModelScreen() {
  const nav = useT().nav;
  const query = useModelCard();
  return (
    <Page title={nav.model} subtitle="Telegram e’lonlarini o‘qiydigan o‘z modelimiz">
      <Tile>
        <Async query={query} skeleton={<SkeletonLines rows={8} />}>
          {(m) => {
            const ordered = m.provider_order.map((p) => Object.keys(m.counts).find((k) => k === p || k.startsWith(`${p}:`)) ?? (p === "local" ? m.provider : p));
            const providers = [...ordered, ...Object.keys(m.counts).filter((k) => !ordered.includes(k))];
            return (
              <>
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h2 className="serif text-[32px]">Bizning modelimiz: {m.model}</h2>
                  <p className={cn("t-mono-cap", m.local_reachable ? "text-success" : "text-warning")}>{m.local_reachable ? "ishlayapti" : "ulanmagan"}</p>
                </div>
                <p className="mt-1 text-[14px] text-text-2">
                  {m.provider}
                  {m.local_detail ? ` · ${m.local_detail}` : ""}
                </p>
                <p className="mt-1 text-[13px] text-text-2">Navbat: {m.provider_order.join(" → ")}</p>
                <div className="mt-4 overflow-x-auto">
                  <table className="data-table min-w-[480px] text-[14px]">
                    <thead>
                      <tr>
                        <th>Manba</th>
                        <th className="r">E’lonlar · {m.window_hours} soat</th>
                        <th className="r">Ulush</th>
                      </tr>
                    </thead>
                    <tbody>
                      {providers.map((key) => (
                        <tr key={key}>
                          <td className={cn(key === m.provider && "font-medium")}>{key}</td>
                          <td className="r mono">{m.counts[key] ?? 0}</td>
                          <td className="r mono text-text-2">{pct((m.share[key] ?? 0) * 100)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-4 text-[13px] text-text-2">Jami {m.listings} ta e’lon so‘nggi {m.window_hours} soatda o‘qildi.</p>
              </>
            );
          }}
        </Async>
      </Tile>
    </Page>
  );
}
