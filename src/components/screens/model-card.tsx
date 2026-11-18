"use client";

import { Page } from "@/components/raft/shell";
import { Async, SkeletonLines } from "@/components/raft/states";
import { Tile } from "@/components/raft/tile";
import { useT } from "@/i18n";
import { useModelCard } from "@/lib/api/hooks";

export function ModelScreen() {
  const nav = useT().nav;
  const query = useModelCard();
  return (
    <Page title={nav.model} subtitle="Telegram e’lonlarini o‘qiydigan o‘z modelimiz">
      <Tile>
        <Async query={query} skeleton={<SkeletonLines rows={8} />}>
          {(m) => (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h2 className="serif text-[32px]">Bizning modelimiz: {m.name}</h2>
                <p className="t-mono-cap">{m.dataset}</p>
              </div>
              <p className="mt-1 text-[14px] text-text-2">{m.base}</p>
              <div className="mt-4 overflow-x-auto">
                <table className="data-table min-w-[560px] text-[14px]">
                  <thead>
                    <tr>
                      <th>Metrika</th>
                      <th className="r">{m.name}</th>
                      <th className="r">Gemini</th>
                      <th className="r">Qoida parseri</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.metrics.map((row) => (
                      <tr key={row.name}>
                        <td>{row.name}</td>
                        <td className="r mono font-medium">{row.raft}</td>
                        <td className="r mono text-text-2">{row.cloud}</td>
                        <td className="r mono text-text-2">{row.rule}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {m.sample ? <p className="mt-4 text-[13px] text-warning">Namuna raqamlar. Model o‘qitilgandan keyin haqiqiy test natijalari bilan almashtiring.</p> : null}
            </>
          )}
        </Async>
      </Tile>
    </Page>
  );
}
