"use client";

import { Page, useShell } from "@/components/raft/shell";
import { useT } from "@/i18n";
import { DemandView, LotsView, RadarView } from "./birja-market";
import { RfqView } from "./birja-rfq";
import { SupplierView } from "./birja-supplier";

const TABS = [
  { key: "sorovlar", label: "So‘rovlarim", href: "/birja" },
  { key: "radar", label: "Bozordan arzon", href: "/birja?tab=radar" },
  { key: "lotlar", label: "Ulgurji lotlar", href: "/birja?tab=lotlar" },
  { key: "talab", label: "Talab", href: "/birja?tab=talab" },
];

export function BirjaScreen({ tab }: { tab: string }) {
  const nav = useT().nav;
  const { account } = useShell();
  if (account.kind === "supplier") {
    return (
      <Page title={nav.birja} subtitle={`${account.name} · yetkazib beruvchi`}>
        <SupplierView />
      </Page>
    );
  }
  return (
    <Page title={nav.birja} tabs={TABS} active={tab}>
      {tab === "radar" ? <RadarView /> : tab === "lotlar" ? <LotsView /> : tab === "talab" ? <DemandView /> : <RfqView />}
    </Page>
  );
}
