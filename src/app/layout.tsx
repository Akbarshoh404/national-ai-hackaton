import type { Metadata } from "next";
import { IBM_Plex_Mono, Newsreader, Onest } from "next/font/google";
import type { ReactNode } from "react";
import { Providers } from "@/components/raft/providers";
import "./globals.css";

const newsreader = Newsreader({ subsets: ["latin", "latin-ext"], weight: "500", variable: "--font-newsreader", display: "swap" });
const onest = Onest({ subsets: ["latin", "latin-ext", "cyrillic"], weight: ["400", "500", "600"], variable: "--font-onest", display: "swap" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin", "latin-ext", "cyrillic"], weight: ["400", "500"], variable: "--font-plex-mono", display: "swap" });

const STRIP_EXTENSION_ATTRS = `(function(){
  var bad = function (n) { return n.indexOf("bis_") === 0 || n.indexOf("__processed_") === 0; };
  var clean = function (el) {
    if (!el.attributes) return;
    for (var i = el.attributes.length - 1; i >= 0; i--) { var n = el.attributes[i].name; if (bad(n)) el.removeAttribute(n); }
  };
  var obs = new MutationObserver(function (list) {
    for (var i = 0; i < list.length; i++) { var m = list[i]; if (m.type === "attributes" && bad(m.attributeName)) clean(m.target); }
  });
  obs.observe(document.documentElement, { attributes: true, subtree: true });
  window.addEventListener("load", function () { setTimeout(function () { obs.disconnect(); }, 3000); });
})();`;

export const metadata: Metadata = {
  title: { default: "Raft", template: "%s · Raft" },
  description: "O‘zbekiston savdo bizneslari uchun operatsion tizim.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="uz" className={`${newsreader.variable} ${onest.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        {/* Some browser extensions (e.g. Bitdefender's bis_skin_checked / bis_register) stamp attributes on the
            server HTML before React hydrates, which React reports as a hydration mismatch. Strip them first. */}
        <script dangerouslySetInnerHTML={{ __html: STRIP_EXTENSION_ATTRS }} />
      </head>
      <body suppressHydrationWarning>
        <div className="backdrop" aria-hidden />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
