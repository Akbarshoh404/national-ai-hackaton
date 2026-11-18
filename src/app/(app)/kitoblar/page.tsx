import type { Metadata } from "next";
import { KitoblarScreen } from "@/components/screens/kitoblar";

export const metadata: Metadata = { title: "Kitoblar" };

export default async function KitoblarPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  return <KitoblarScreen tab={tab === "budjet" || tab === "hisobotlar" ? tab : "tekshiruv"} />;
}
