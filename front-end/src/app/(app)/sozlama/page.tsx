import type { Metadata } from "next";
import { SozlamaScreen } from "@/components/screens/sozlama";

export const metadata: Metadata = { title: "Sozlama" };

export default async function SozlamaPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  return <SozlamaScreen tab={tab ?? "integratsiyalar"} />;
}
