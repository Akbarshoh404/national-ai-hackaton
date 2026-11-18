"use client";

import Link from "next/link";
import { useState } from "react";
import { Page, useShell } from "@/components/raft/shell";
import { Async, SkeletonLines } from "@/components/raft/states";
import { Tile, TileHeader } from "@/components/raft/tile";
import { Button } from "@/components/ui/button";
import { setLang, useLang, useT, type Lang } from "@/i18n";
import { useActivity, useCreateUser, useIntegrations, useMeta, useStores, useSyncIntegration, useUsers } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/client";
import { dateShort } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS: Record<string, string> = { connected: "ulangan", not_connected: "ulanmagan", error: "xato" };

function Integrations() {
  const query = useIntegrations();
  const sync = useSyncIntegration();
  return (
    <Tile>
      <TileHeader title="Integratsiyalar" sub="Ma’lumot manbalari va ularning holati" />
      <div className="mt-2">
        <Async query={query} skeleton={<SkeletonLines rows={6} height={48} />}>
          {(items) => (
            <ul>
              {items.map((i, n) => (
                <li key={i.kind} className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 py-3", n > 0 && "border-t border-[rgb(15_23_22/0.06)]")}>
                  <span className="min-w-[200px] flex-1">
                    <span className="block text-[14px] font-medium">{i.label}</span>
                    <span className="block text-[13px] text-text-2">{i.note}</span>
                  </span>
                  <span className={cn("w-[100px] text-[13px]", i.mode === "live" ? "font-medium text-success" : "text-text-2")}>
                    {i.mode === "live" ? "jonli" : "sinov rejimi"}
                    <span className={cn("block text-[12px]", i.status === "error" ? "text-danger" : "text-text-2")}>{STATUS[i.status]}</span>
                  </span>
                  <span className="t-mono-cap w-[100px]">{i.last_sync_at ? dateShort(i.last_sync_at) : "—"}</span>
                  {i.mode === "mock" ? (
                    <Button disabled={sync.isPending && sync.variables === i.kind} onClick={() => sync.mutate(i.kind)}>
                      Sinxronlash
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Async>
        {sync.isSuccess ? (
          <p role="status" className="mt-2 text-[13px] text-text-2">
            {sync.data.kind}: {sync.data.created} ta yozuv import qilindi, {sync.data.audit_flags.length} ta tekshiruv belgisi.
          </p>
        ) : null}
        {sync.isError ? (
          <p role="alert" className="mt-2 text-[13px] text-danger">
            {sync.error.message}
          </p>
        ) : null}
      </div>
    </Tile>
  );
}

function Users() {
  const query = useUsers();
  const meta = useMeta();
  const create = useCreateUser();
  const lang = useLang();
  const roles = meta.data?.user_roles.filter((r) => r.code === "manager" || r.code === "appraiser") ?? [];
  const roleLabel = (code: string) => meta.data?.user_roles.find((r) => r.code === code)?.label[lang] ?? code;
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const selected = role || roles[0]?.code || "";
  return (
    <Tile>
      <TileHeader title="Foydalanuvchilar" sub="Rollar: ega, menejer, baholovchi" />
      <div className="mt-2">
        <Async query={query} skeleton={<SkeletonLines rows={3} />}>
          {(data) => (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Foydalanuvchi</th>
                  <th>Rol</th>
                  <th className="r">Qo‘shilgan</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.id}>
                    <td className="font-medium">{u.name}</td>
                    <td className="text-text-2">{roleLabel(u.role)}</td>
                    <td className="r mono text-text-2">{dateShort(u.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </div>
      <div className="mt-4">
        {create.data ? (
          <div className="panel p-4" role="status">
            <p className="text-[13px] text-text-2">
              {create.data.user.name} uchun API kalit faqat bir marta ko‘rsatiladi. Hozir nusxa oling.
            </p>
            <p className="mono mt-1 text-[13px] break-all">{create.data.api_key}</p>
            <Button className="mt-2" onClick={() => create.reset()}>
              Yana qo‘shish
            </Button>
          </div>
        ) : (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim().length >= 2 && selected) create.mutate({ name: name.trim(), role: selected }, { onSuccess: () => setName("") });
            }}
          >
            <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-[13px] text-text-2">
              Ism
              <input className="input h-11" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={120} required />
            </label>
            <label className="flex flex-col gap-1 text-[13px] text-text-2">
              Rol
              <select className="input h-11" value={selected} onChange={(e) => setRole(e.target.value)}>
                {roles.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.label[lang]}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" disabled={create.isPending || name.trim().length < 2 || !selected}>
              Foydalanuvchi va API kalit yaratish
            </Button>
          </form>
        )}
        {create.isError ? (
          <p role="alert" className="mt-2 text-[13px] text-danger">
            {create.error instanceof ApiError && create.error.status === 403 ? "Faqat do‘kon egasi foydalanuvchi qo‘sha oladi." : create.error.message}
          </p>
        ) : null}
      </div>
    </Tile>
  );
}

function Stores() {
  const query = useStores();
  return (
    <Tile>
      <TileHeader title="Do‘konlar" />
      <div className="mt-2">
        <Async query={query} skeleton={<SkeletonLines rows={2} />}>
          {(data) => (
            <ul>
              {data.items.map((s, i) => (
                <li key={s.id} className={cn("flex items-baseline justify-between gap-4 py-3", i > 0 && "border-t border-[rgb(15_23_22/0.06)]", !s.active && "opacity-60")}>
                  <span>
                    <span className="block text-[14px] font-medium">{s.name}</span>
                    <span className="block text-[13px] text-text-2">
                      {[s.district, s.area_m2 ? `${s.area_m2} m²` : null, s.active ? null : "faol emas"].filter(Boolean).join(" · ") || "—"}
                    </span>
                  </span>
                  <span className="mono text-[13px]">{s.units_in_stock ?? 0} dona</span>
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
                  <th className="r">Kim</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <td className="mono text-text-2">{row.time}</td>
                    <td>{row.text}</td>
                    <td className="r text-text-2">{row.actor}</td>
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
      <p className="mt-4 text-[13px]">
        <Link href="/model" className="link">
          Model kartasi
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
