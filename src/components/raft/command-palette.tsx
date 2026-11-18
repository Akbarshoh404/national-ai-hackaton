"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useT } from "@/i18n";
import { useSearch } from "@/lib/api/hooks";
import type { Account } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { navFor } from "./shell";

interface Row {
  group: string;
  title: string;
  meta: string;
  href: string;
}

const SUBPAGES: Row[] = [
  { group: "", title: "Ombor", meta: "Narxlar", href: "/narxlar?tab=ombor" },
  { group: "", title: "Baholash", meta: "Narxlar", href: "/narxlar?tab=baholash" },
  { group: "", title: "Bozordan arzon", meta: "Birja", href: "/birja?tab=radar" },
  { group: "", title: "Ulgurji lotlar", meta: "Birja", href: "/birja?tab=lotlar" },
  { group: "", title: "Talab", meta: "Birja", href: "/birja?tab=talab" },
  { group: "", title: "Budjet", meta: "Kitoblar", href: "/kitoblar?tab=budjet" },
  { group: "", title: "Hisobotlar", meta: "Kitoblar", href: "/kitoblar?tab=hisobotlar" },
];

export function CommandPalette({ open, onOpenChange, account }: { open: boolean; onOpenChange: (open: boolean) => void; account: Account }) {
  const t = useT();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [index, setIndex] = useState(0);
  const isBusiness = account.kind === "business";
  const search = useSearch(isBusiness ? q : "");

  const rows = useMemo<Row[]>(() => {
    const text = q.trim().toLowerCase();
    const pages: Row[] = [
      ...navFor(account).map((item) => ({ group: t.shell.pages, title: t.nav[item.label], meta: "", href: item.href })),
      ...(isBusiness ? SUBPAGES.map((p) => ({ ...p, group: t.shell.pages })) : []),
      { group: t.shell.pages, title: t.nav.sozlama, meta: "", href: "/sozlama" },
      { group: t.shell.pages, title: t.nav.model, meta: "Raft-Extractor", href: "/model" },
    ].filter((p) => !text || `${p.title} ${p.meta}`.toLowerCase().includes(text));
    return [...pages, ...(text.length > 1 ? (search.data?.items ?? []) : [])];
  }, [account, isBusiness, q, search.data, t]);

  useEffect(() => setIndex(0), [q, open]);
  useEffect(() => {
    if (!open) setQ("");
  }, [open]);

  const go = (row?: Row) => {
    if (!row) return;
    onOpenChange(false);
    router.push(row.href);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={t.shell.search} hideTitle className="top-[96px] max-w-[600px] translate-y-0 p-3">
        <div className="relative">
          <Search size={16} strokeWidth={1.75} aria-hidden className="absolute top-1/2 left-4 -translate-y-1/2 text-muted" />
          <label className="sr-only" htmlFor="palette-input">
            {t.shell.search}
          </label>
          <input
            id="palette-input"
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIndex((i) => Math.min(rows.length - 1, i + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setIndex((i) => Math.max(0, i - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                go(rows[index]);
              }
            }}
            placeholder={t.shell.searchHint}
            role="combobox"
            aria-expanded
            aria-controls="palette-list"
            aria-activedescendant={rows[index] ? `palette-${index}` : undefined}
            className="input h-12 rounded-[20px] pl-10"
          />
        </div>
        <ul id="palette-list" role="listbox" aria-label={t.shell.search} className="mt-2 max-h-[400px] overflow-auto">
          {rows.length === 0 ? <li className="px-3 py-4 text-[14px] text-muted">{t.shell.noResults}</li> : null}
          {rows.map((row, i) => (
            <li key={`${row.group}-${row.title}-${row.meta}-${i}`}>
              {i === 0 || rows[i - 1].group !== row.group ? <p className="t-cap px-3 pt-3 pb-1">{row.group}</p> : null}
              <button
                id={`palette-${i}`}
                type="button"
                role="option"
                aria-selected={i === index}
                tabIndex={-1}
                onMouseEnter={() => setIndex(i)}
                onClick={() => go(row)}
                className={cn("flex min-h-11 w-full items-baseline justify-between gap-3 rounded-[12px] px-3 py-2 text-left text-[14px]", i === index && "bg-accent-soft")}
              >
                <span className="truncate-1">{row.title}</span>
                <span className="t-cap truncate-1 shrink">{row.meta}</span>
              </button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
