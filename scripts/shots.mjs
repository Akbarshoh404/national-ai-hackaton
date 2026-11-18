// Captures every screen into docs/screens. Requires `npm run dev` on port 3000.
// Usage: npm run shots            all screens at 1440x900 and 1280x800
//        npm run shots -- bugun   only screens whose name contains "bugun"
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const BASE = process.env.RAFT_URL ?? "http://localhost:3000";
const OUT = "docs/screens";
const filter = process.argv[2];
mkdirSync(OUT, { recursive: true });

const SCREENS = [
  { name: "login", account: null, path: "/login" },
  { name: "bugun", account: "chilonzor-owner", path: "/bugun" },
  { name: "narxlar-ombor", account: "chilonzor-owner", path: "/narxlar?tab=ombor" },
  { name: "narxlar-baholash", account: "chilonzor-owner", path: "/narxlar?tab=baholash" },
  { name: "birja-rfq", account: "chilonzor-owner", path: "/birja" },
  { name: "birja-radar", account: "chilonzor-owner", path: "/birja?tab=radar" },
  { name: "birja-lotlar", account: "chilonzor-owner", path: "/birja?tab=lotlar" },
  { name: "birja-talab", account: "chilonzor-owner", path: "/birja?tab=talab" },
  { name: "birja-supplier", account: "techopt", path: "/birja" },
  { name: "kitoblar-tekshiruv", account: "chilonzor-owner", path: "/kitoblar" },
  { name: "kitoblar-budjet", account: "chilonzor-owner", path: "/kitoblar?tab=budjet" },
  { name: "kitoblar-hisobotlar", account: "chilonzor-owner", path: "/kitoblar?tab=hisobotlar" },
  { name: "maslahat", account: "chilonzor-owner", path: "/maslahat" },
  { name: "partner", account: "demo-bank", path: "/partner" },
  { name: "partner-garov", account: "demo-bank", path: "/partner/garov" },
  { name: "partner-hisobot", account: "demo-bank", path: "/partner/hisobot" },
  { name: "sozlama", account: "chilonzor-owner", path: "/sozlama" },
  { name: "model", account: "chilonzor-owner", path: "/model" },
];

const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
];

const browser = await chromium.launch();
const problems = [];

for (const size of SIZES) {
  const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1 });
  const page = await context.newPage();
  let current = "";
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`${current} ${size.width}: console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => problems.push(`${current} ${size.width}: exception: ${err.message}`));

  for (const screen of SCREENS) {
    if (filter && !screen.name.includes(filter)) continue;
    current = screen.name;
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
    await page.evaluate((id) => {
      localStorage.removeItem("raft_demo_state_v1");
      if (id) localStorage.setItem("raft_account", id);
      else localStorage.removeItem("raft_account");
    }, screen.account);
    await page.goto(`${BASE}${screen.path}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 0) problems.push(`${screen.name} ${size.width}: page overflows by ${overflow}px`);
    await page.screenshot({ path: `${OUT}/${screen.name}-${size.width}.png`, fullPage: true });
    console.log(`ok ${screen.name} ${size.width}`);
  }
  await context.close();
}

await browser.close();
if (problems.length) {
  console.log("\nProblems:");
  for (const p of problems) console.log(` - ${p}`);
  process.exitCode = 1;
} else {
  console.log("\nNo console errors or horizontal overflow.");
}
