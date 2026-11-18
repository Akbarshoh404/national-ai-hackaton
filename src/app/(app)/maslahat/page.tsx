import type { Metadata } from "next";
import { MaslahatScreen } from "@/components/screens/maslahat";

export const metadata: Metadata = { title: "Maslahat" };

export default function MaslahatPage() {
  return <MaslahatScreen />;
}
