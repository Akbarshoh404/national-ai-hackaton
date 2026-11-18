import type { Metadata } from "next";
import { PartnerScreen } from "@/components/screens/partner";

export const metadata: Metadata = { title: "Arizalar" };

export default function PartnerPage() {
  return <PartnerScreen />;
}
