"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Page, useShell } from "@/components/raft/shell";
import { Async, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { setLang, useLang, useT, type Lang } from "@/i18n";
import { resetDemo } from "@/lib/api/fixtures/server";
import { useActivity, useIntegrations, useMeta, useSyncIntegration } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

function Integrations() {
  const query = useIntegrations();
  const sync = useSyncIntegration();
  return (
    <Tile>
      <TileHeader title="Integratsiyalar" sub="Ma’lumot manbalari va ularning holati" />
      <div className="mt-2">
        <Async query={query} skeleton={<SkeletonLines rows={6} height={48} />}>
          {(data) => (
            <ul>
              {data.items.map((i, n) => (
                <li key={i.kind} className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 py-3", n > 0 && "border-t border-[rgb(15_23_22/0.06)]")}>
                  <span className="min-w-[200px] flex-1">
                    <span className="block text-[14px] font-medium">{i.name}</span>
                    <span className="block text-[13px] text-text-2">{i.detail}</span>
                  </span>
                  <span className={cn("w-[100px] text-[13px]", i.mode === "live" ? "font-medium text-success" : "text-text-2")}>{i.mode === "live" ? "jonli" : "sinov rejimi"}</span>
                  <span className="t-mono-cap w-[100px]">{i.last_sync}</span>
                  <Button disabled={sync.isPending && sync.variables === i.kind} onClick={() => sync.mutate(i.kind)}>
                    Sinxronlash
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Async>
      </div>
    </Tile>
  );
}

function Users() {
  const query = useMeta();
  const [key, setKey] = useState<string | null>(null);
  return (
    <Tile>
      <TileHeader title="Foydalanuvchilar" sub="Rollar: ega, menejer, baholovchi" />
      <div className="mt-2">
        <Async query={query} skeleton={<SkeletonLines rows={3} />}>
          {(m) => (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Foydalanuvchi</th>
                  <th>Rol</th>
                  <th className="r">Oxirgi kirish</th>
                </tr>
              </thead>
              <tbody>
                {m.users.map((u) => (
                  <tr key={u.name}>
                    <td className="font-medium">{u.name}</td>
                    <td className="text-text-2">{u.role}</td>
                    <td className="r mono text-text-2">{u.last_seen}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </div>
      <div className="mt-4">
        {key ? (
          <div className="panel p-4" role="status">
            <p className="text-[13px] text-text-2">API kalit faqat bir marta ko‘rsatiladi. Hozir nusxa oling.</p>
            <p className="mono mt-1 text-[13px] break-all">{key}</p>
          </div>
        ) : (
          <Button
            onClick={() => {
              const bytes = crypto.getRandomValues(new Uint8Array(16));
              setKey(`raft_demo_${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`);
            }}
          >
            API kalit yaratish
          </Button>
        )}
      </div>
    </Tile>
  );
}

function Stores() {
  const query = useMeta();
  return (
    <Tile>
      <TileHeader title="Do‘konlar" />
      <div className="mt-2">
        <Async query={query} skeleton={<SkeletonLines rows={2} />}>
          {(m) => (
            <ul>
              {m.stores.map((s, i) => (
                <li key={s.name} className={cn("flex items-baseline justify-between gap-4 py-3", i > 0 && "border-t border-[rgb(15_23_22/0.06)]")}>
                  <span>
                    <span className="block text-[14px] font-medium">{s.name}</span>
                    <span className="block text-[13px] text-text-2">{s.address}</span>
                  </span>
                  <span className="mono text-[13px]">{s.units} dona</span>
                </li>
              ))}
            </ul>
          )}
        </Async>
      </div>
    </Tile>
  );
}

function ActivityLog() {
  const query = useActivity();
  return (
    <Tile>
      <TileHeader title="Faoliyat jurnali" />
      <div className="mt-2">
        <Async query={query} skeleton={<SkeletonLines rows={6} />}>
          {(data) => (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vaqt</th>
                  <th>Hodisa</th>
                  <th>Kim</th>
                  <th className="r">Qiymat</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row, i) => (
                  <tr key={`${row.text}-${i}`}>
                    <td className="mono text-text-2">{row.time}</td>
                    <td>{row.text}</td>
                    <td className="text-text-2">{row.actor}</td>
                    <td className="r mono">{row.value}</td>
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

const LANGS: { key: Lang; label: string; note: string }[] = [
  { key: "uz", label: "O‘zbekcha", note: "To‘liq" },
  { key: "ru", label: "Русский", note: "Menyu va Bugun ekrani" },
  { key: "en", label: "English", note: "Menyu va Bugun ekrani" },
];

function Language() {
  const lang = useLang();
  const qc = useQueryClient();
  const [reset, setReset] = useState(false);
  return (
    <Tile>
      <fieldset>
        <legend className="t-title">Til</legend>
        <div className="mt-2 flex flex-col">
          {LANGS.map((l) => (
            <label key={l.key} className="flex min-h-11 items-center gap-3 text-[14px]">
              <input type="radio" name="lang" className="h-4 w-4 accent-[var(--accent)]" checked={lang === l.key} onChange={() => setLang(l.key)} />
              <span className="font-medium">{l.label}</span>
              <span className="text-[13px] text-text-2">{l.note}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <hr className="my-4 border-[rgb(15_23_22/0.06)]" />
      <h2 className="t-title">Demo</h2>
      <p className="mt-1 text-[13px] text-text-2">Barcha o‘zgarishlarni bekor qilib, boshlang‘ich raqamlarga qaytaradi.</p>
      <div className="mt-2 flex items-center gap-3">
        <Button
          onClick={() => {
            resetDemo();
            void qc.invalidateQueries();
            setReset(true);
          }}
        >
          Demo ma’lumotlarini tiklash
        </Button>
        {reset ? <span role="status" className="text-[13px] text-text-2">Tiklandi</span> : null}
      </div>
      <p className="mt-4 text-[13px]">
        <Link href="/model" className="link">
          Raft-Extractor model kartasi
        </Link>
      </p>
    </Tile>
  );
}

export function SozlamaScreen({ tab }: { tab: string }) {
  const nav = useT().nav;
  const { account } = useShell();
  const isBusiness = account.kind === "business";
  const tabs = [
    { key: "integratsiyalar", label: "Integratsiyalar", href: "/sozlama" },
    ...(isBusiness
      ? [
          { key: "foydalanuvchilar", label: "Foydalanuvchilar", href: "/sozlama?tab=foydalanuvchilar" },
          { key: "dokonlar", label: "Do‘konlar", href: "/sozlama?tab=dokonlar" },
        ]
      : []),
    { key: "faoliyat", label: "Faoliyat jurnali", href: "/sozlama?tab=faoliyat" },
    { key: "til", label: "Til", href: "/sozlama?tab=til" },
  ];
  const active = tabs.some((t) => t.key === tab) ? tab : "integratsiyalar";
  return (
    <Page title={nav.sozlama} tabs={tabs} active={active}>
      {active === "foydalanuvchilar" ? <Users /> : active === "dokonlar" ? <Stores /> : active === "faoliyat" ? <ActivityLog /> : active === "til" ? <Language /> : <Integrations />}
    </Page>
  );
}
