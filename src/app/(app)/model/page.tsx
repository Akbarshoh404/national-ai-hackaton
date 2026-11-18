import type { Metadata } from "next";
import { ModelScreen } from "@/components/screens/model-card";

export const metadata: Metadata = { title: "Model kartasi" };

export default function ModelPage() {
  return <ModelScreen />;
}
