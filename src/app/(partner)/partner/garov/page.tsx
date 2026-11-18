import type { Metadata } from "next";
import { GarovScreen } from "@/components/screens/partner";

export const metadata: Metadata = { title: "Garov" };

export default function GarovPage() {
  return <GarovScreen />;
}
