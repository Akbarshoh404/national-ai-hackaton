"use client";

import { Page } from "@/components/raft/shell";
import { useT } from "@/i18n";
import { BaholashView } from "./narxlar-baholash";
import { OmborView } from "./narxlar-ombor";

const TABS = [
  { key: "ombor", label: "Ombor", href: "/narxlar?tab=ombor" },
  { key: "baholash", label: "Baholash", href: "/narxlar?tab=baholash" },
];

export function NarxlarScreen({ tab }: { tab: string }) {
  const nav = useT().nav;
  return (
    <Page title={nav.narxlar} tabs={TABS} active={tab}>
      {tab === "baholash" ? <BaholashView /> : <OmborView />}
    </Page>
  );
}
