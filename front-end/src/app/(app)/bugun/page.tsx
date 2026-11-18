import type { Metadata } from "next";
import { BugunScreen } from "@/components/screens/bugun";

export const metadata: Metadata = { title: "Bugun" };

export default function BugunPage() {
  return <BugunScreen />;
}
