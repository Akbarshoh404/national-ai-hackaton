import type { Metadata } from "next";
import { BirjaScreen } from "@/components/screens/birja";

export const metadata: Metadata = { title: "Birja" };

export default async function BirjaPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  return <BirjaScreen tab={tab === "radar" || tab === "lotlar" || tab === "talab" ? tab : "sorovlar"} />;
}
