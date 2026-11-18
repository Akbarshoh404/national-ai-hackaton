import type { ReactNode } from "react";
import { AppShell } from "@/components/raft/shell";

export default function PartnerLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
