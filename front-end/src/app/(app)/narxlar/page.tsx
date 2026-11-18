import type { Metadata } from "next";
import { NarxlarScreen } from "@/components/screens/narxlar";

export const metadata: Metadata = { title: "Narxlar" };

export default async function NarxlarPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  return <NarxlarScreen tab={tab === "baholash" ? "baholash" : "ombor"} />;
}
