import type { Metadata } from "next";
import { HisobotScreen } from "@/components/screens/partner";

export const metadata: Metadata = { title: "Hisobot" };

export default function HisobotPage() {
  return <HisobotScreen />;
}
