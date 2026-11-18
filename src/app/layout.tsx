import type { Metadata } from "next";
import { IBM_Plex_Mono, Newsreader, Onest } from "next/font/google";
import type { ReactNode } from "react";
import { Providers } from "@/components/raft/providers";
import "./globals.css";

const newsreader = Newsreader({ subsets: ["latin", "latin-ext"], weight: "500", variable: "--font-newsreader", display: "swap" });
const onest = Onest({ subsets: ["latin", "latin-ext", "cyrillic"], weight: ["400", "500", "600"], variable: "--font-onest", display: "swap" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin", "latin-ext", "cyrillic"], weight: ["400", "500"], variable: "--font-plex-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Raft", template: "%s · Raft" },
  description: "O‘zbekiston savdo bizneslari uchun operatsion tizim.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="uz" className={`${newsreader.variable} ${onest.variable} ${plexMono.variable}`}>
      <body>
        <div className="backdrop" aria-hidden />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
