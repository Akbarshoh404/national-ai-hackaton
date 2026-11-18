// Runs axe-core on each screen and checks for sideways scrolling at narrow widths.
// Usage: RAFT_URL=http://localhost:3000 node scripts/a11y.mjs
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { chromium } from "playwright";

const BASE = process.env.RAFT_URL ?? "http://localhost:3000";
const axeSource = readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
const SCREENS = [
  ["chilonzor-owner", "/bugun"],
  ["chilonzor-owner", "/narxlar"],
  ["chilonzor-owner", "/narxlar?tab=baholash"],
  ["chilonzor-owner", "/birja"],
  ["chilonzor-owner", "/birja?tab=radar"],
  ["chilonzor-owner", "/birja?tab=lotlar"],
  ["chilonzor-owner", "/birja?tab=talab"],
  ["techopt", "/birja"],
  ["chilonzor-owner", "/kitoblar"],
  ["chilonzor-owner", "/kitoblar?tab=budjet"],
  ["chilonzor-owner", "/kitoblar?tab=hisobotlar"],
  ["chilonzor-owner", "/maslahat"],
  ["demo-bank", "/partner"],
  ["demo-bank", "/partner/garov"],
  ["demo-bank", "/partner/hisobot"],
  ["chilonzor-owner", "/sozlama"],
  ["chilonzor-owner", "/model"],
];

const browser = await chromium.launch({ channel: "chrome" }).catch(() => chromium.launch({ channel: "msedge" }));
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
let problems = 0;

async function open(id, path) {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate((v) => localStorage.setItem("raft_account", v), id);
  await page.goto(`${BASE}${path}`, { waitUntil: "load" });
  await page.waitForTimeout(500);
}

for (const [id, path] of SCREENS) {
  await open(id, path);
  await page.evaluate(axeSource);
  const violations = await page.evaluate(async () => {
    const result = await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"] });
    return result.violations.map((v) => ({ id: v.id, impact: v.impact, count: v.nodes.length, sample: v.nodes[0].html.slice(0, 110) }));
  });
  console.log(`${violations.length ? "FAIL" : "ok  "} ${id} ${path}`);
  for (const v of violations) {
    problems += 1;
    console.log(`   ${v.impact} ${v.id} x${v.count}: ${v.sample}`);
  }
}

for (const size of [{ width: 1024, height: 768 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  await page.setViewportSize(size);
  for (const [id, path] of SCREENS) {
    await open(id, path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 0) {
      problems += 1;
      console.log(`overflow ${size.width}px ${path} (${id}): ${overflow}px`);
    }
  }
}

await browser.close();
console.log(problems ? `\n${problems} problem(s)` : "\nNo accessibility violations or sideways scrolling.");
process.exitCode = problems ? 1 : 0;
