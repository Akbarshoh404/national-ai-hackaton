// Walks the seven-step demo click path from section 12 against a running app.
// Usage: RAFT_URL=http://localhost:3000 node scripts/demo-path.mjs
import { chromium } from "playwright";

const BASE = process.env.RAFT_URL ?? "http://localhost:3000";
const browser = await chromium.launch({ channel: "chrome" }).catch(() => chromium.launch({ channel: "msedge" }));
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(e.message));

let failed = 0;
async function step(name, fn) {
  try {
    await fn();
    console.log(`pass  ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${String(e.message).split("\n")[0]}`);
  }
}
const see = (text, timeout = 5000) =>
  page
    .getByText(text, { exact: false })
    .first()
    .waitFor({ state: "visible", timeout })
    .catch(() => {
      throw new Error(`not visible: ${text} (on ${page.url()})`);
    });
const click = (name) => page.getByRole("button", { name, exact: false }).first().click();
const open = async (path) => {
  await page.goto(`${BASE}${path}`, { waitUntil: "load" });
};
async function switchTo(id, path) {
  await page.evaluate((v) => localStorage.setItem("raft_account", v), id);
  await open(path);
}

await open("/login");
await page.evaluate(() => {
  localStorage.clear();
  localStorage.setItem("raft_account", "chilonzor-owner");
});

await step("1 Radar: a new post becomes a priced find", async () => {
  await open("/birja?tab=radar");
  await see("Jonli lenta");
  await click("Keyingi e’lonni o‘qish");
  await see("Galaxy S24 Ultra 512GB");
  await page.getByRole("cell", { name: /yangi/ }).first().waitFor({ timeout: 5000 });
  await see("~$1 324");
});

await step("2 Ombor: 80 units, select 14, reprice, undo bar", async () => {
  await open("/narxlar?tab=ombor");
  await see("80 dona");
  await click("Qimmat 14 tasini tanlash");
  await click("14 tasini tavsiya narxga o‘zgartirish");
  await see("14 ta narx o‘zgartirildi");
  await click("Bekor qilish");
  await see("14 ta birlik bozordan qimmat");
  await click("Qimmat 14 tasini tanlash");
  await click("14 tasini tavsiya narxga o‘zgartirish");
  await see("Barcha narxlar bozorga mos");
});

await step("3 Kitoblar: Didox sync, fix, decision leaves Bugun", async () => {
  await open("/bugun");
  await see("Faktura #2231: 1 mln ortiqcha");
  await open("/kitoblar");
  await click("Didox’dan sinxronlash");
  await see("2 tasida muammo topildi");
  await see("Didox’dan yangi");
  await click("31 000 000 deb tuzatish");
  await see("3 ta yozuv tekshiruv kutmoqda");
  await open("/bugun");
  await see("Galaxy S23 arzon qo‘yilgan");
  if (await page.getByText("Faktura #2231: 1 mln ortiqcha").count()) throw new Error("decision still listed");
});

await step("4 Bugun: approve moves to the next decision, budget warning shows", async () => {
  await see("Limit 26-noyabrda tugaydi");
  await click("Narxni $775 qilish");
  await see("Galaxy S23 narxini $470 ga ko‘taring");
});

await step("5 Birja: TechOpt quotes, shop accepts, deal reaches Kitoblar", async () => {
  await switchTo("techopt", "/birja");
  await click("Taklif yuborish · $5 160");
  await see("$258 taklif yuborildi");
  await switchTo("chilonzor-owner", "/birja");
  await see("TechOpt Wholesale yangi taklif yubordi");
  await see("$258");
  await click("Taklifni qabul qilish · $4 980");
  await see("Raft bitim yozuvi RB-148");
  await open("/kitoblar?tab=hisobotlar");
  await see("Raft bitim yozuvi · RB-148");
  await see("RFQ #148 bitimi");
});

await step("6 Maslahat: consented application reaches Demo Bank", async () => {
  await open("/maslahat");
  await click("Bankka ariza yuborish");
  await page.getByRole("dialog").getByRole("button", { name: "Arizani yuborish" }).waitFor();
  if (await page.getByRole("dialog").getByRole("button", { name: "Arizani yuborish" }).isEnabled()) throw new Error("submit enabled without consent");
  await page.getByRole("dialog").getByRole("checkbox").click();
  await page.getByRole("dialog").getByRole("button", { name: "Arizani yuborish" }).click();
  await see("Demo Bank ko‘rib chiqmoqda");
  await switchTo("demo-bank", "/partner");
  await see("Chilonzor Phone Market");
  await see("300 mln so‘m · 24 oy");
  await see("38%");
  await see("$11 400");
  await page.getByLabel("Obyekt, t.me havola yoki ombor raqami").fill("Malibu 2019");
  await click("Baholash");
  await see("$16 900");
  await click("Tasdiqlash");
  await see("Ariza tasdiqlandi");
});

await step("7 Model card compares the three extractors", async () => {
  await open("/model");
  await see("Bizning modelimiz: Raft-Extractor");
  await see("Qoida parseri");
  await see("Namuna raqamlar");
});

await step("Extras: palette, copilot and chat chips", async () => {
  await switchTo("chilonzor-owner", "/maslahat");
  await click("Muddatni 36 oyga o‘zgartirish");
  await see("36 oy");
  await click("Jadvalni Excel’ga yuklash");
  await see("kredit-jadvali-36-oy.csv");
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox").fill("techopt");
  await page.getByRole("option", { name: /TechOpt Wholesale/ }).first().waitFor({ timeout: 5000 });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Yordamchi" }).click();
  await page.getByRole("complementary", { name: "Yordamchi" }).getByRole("button", { name: "Budjet holati" }).click();
  await page.getByRole("complementary", { name: "Yordamchi" }).getByText("Toifalar bo‘yicha sarf").waitFor({ timeout: 5000 });
  await page.keyboard.press("Escape");
  await page.getByRole("complementary", { name: "Yordamchi" }).waitFor({ state: "hidden", timeout: 3000 });
});

await browser.close();
if (errors.length) {
  console.log("\nConsole errors:");
  [...new Set(errors)].forEach((e) => console.log(` - ${e}`));
}
console.log(failed || errors.length ? `\n${failed} step(s) failed, ${errors.length} console error(s)` : "\nAll steps passed, no console errors.");
process.exitCode = failed || errors.length ? 1 : 0;
