# Raft frontend — master prompt for Claude Code

You are building the **frontend of Raft** in this folder (`D:\Raft`, Windows). It must run at **http://localhost:3000** with `npm run dev`.

Raft is a B2B operating system for Uzbek businesses that trade phones, laptops, cars and real estate. It prices every unit from the live Telegram market, audits the books, connects businesses on a B2B exchange, and turns clean books into a bank-ready loan application. It solves Chamber of Commerce problems #19, #20, #25 and #26 for the National AI Hackathon (Tashkent stage).

**The demo checkpoint is today, 18 Nov, 15:00.** Build in the phase order of section 11. Each phase ends in a working, demo-able state and a git commit. Work on your own and do not ask questions unless truly blocked. Record every decision in `DECISIONS.md`.

---

## 0. Before writing code

1. Run `git init` if needed.
2. Check `node -v` (need 20+).
3. The backend is a separate FastAPI app that runs locally on **http://localhost:8000**.
   - Fetch `http://localhost:8000/openapi.json`. If it answers, generate types with `openapi-typescript` into `src/lib/api/schema.d.ts`, and use the real paths and response shapes from it. The prefix is probably `/api/v1`; confirm it there.
   - If the backend is not running, continue with fixtures (section 3) and tell me at the end which endpoints still need checking.
4. **Read the design file if the Figma MCP is available.** File key `MFQ5HAaBBKVs9EnsfeOSdt`. Main frames:

   | Screen | Page | Frame ID |
   |---|---|---|
   | Bugun (home) | 03 | `73:98` |
   | Narxlar: Pricing Desk (trade-in) | 04 | `28:60` |
   | Bozordan arzon (Sourcing Radar) | 05 | `82:2` |
   | Birja: request for quote | 06 | `29:66` |
   | Kitoblar: audit review | 07 | `30:2` |
   | Maslahat | 08 | `82:486` |
   | Supplier workspace (TechOpt) | 09 | `82:284` |
   | Partner console (Demo Bank) | 10 | `82:698` |
   | Demo storyboard + own-model card | 11 | `82:927` |

   - Interactive chart components are on page 02 ("Components"):
     - `Chart/Sales forecast`
     - `Chart/Price waterfall`
     - `Chart/Quote spread`
     - `Chart/Invoice anomalies`
     - `Bento/Sales strip`
     - `Bento/Cash flow`
   - If the MCP is not available, build from this document. It describes every screen.

### Name: Raft

The product is called **Raft**. Older backend code and docs may still say "BozorPilot", and the Figma file may still say "BussinessPilot". Never show either name.

- **UI:** the logo tile is "R", the browser title is `Raft`, and the page titles are `Bugun · Raft`, and so on.
- **Code:**
  - `package.json` name is `raft-frontend`
  - localStorage keys use the `raft_` prefix
  - components may use a `Raft` prefix
- **Copy:** the deal document label reads "Raft bitim yozuvi". The own model is "Raft-Extractor".
- **Backend data:** if the backend returns a string containing "BozorPilot" (for example in deal document titles or bot texts), list it in your final report so the backend can be renamed. Do not patch it on the frontend.

---

## 1. Stack

- **Next.js 15** (App Router, TypeScript strict, `src/` directory), port 3000.
- **Tailwind CSS v4** with CSS variables for every design token.
- **shadcn/ui** as the component base: init it, then restyle it to the tokens below. Never ship the default shadcn look.
- **TanStack Query** for data. **Zod** for parsing API responses at the boundary.
- **Recharts** only where it fits without fighting the design. Hand-built SVG components are preferred for the signature charts (section 6).
- **`next/font/google`:** `Newsreader` (500), `Onest` (400/500/600) and `IBM Plex Mono` (400/500).
- **Icons:** `lucide-react` with a 1.75 stroke, 16–20 px, always in the text colour. Never put icons in tinted squares or circles.
- No other UI kits. No animation libraries; use CSS transitions of 150–250 ms with `cubic-bezier(.22,1,.36,1)`, and honour `prefers-reduced-motion`.

Folder layout:

```
src/app/(app)/...        retailer & supplier screens (sidebar layout)
src/app/(partner)/...    lender & bazaar console (own sidebar)
src/app/login/page.tsx   demo account picker
src/components/ui/       shadcn primitives, restyled
src/components/raft/     Tile, Sidebar, Toolbar, Kpi, DataTable, Copilot, etc.
src/components/charts/   SalesForecast, PriceWaterfall, QuoteSpread, InvoiceAnomalies, SalesStrip, CashFlowMirror, TickGauge, TickBar, Sparkline, RangeBar, ScheduleBars
src/lib/api/             client, hooks, schema, fixtures
src/lib/format.ts        money, dates, percentages
src/i18n/                uz.ts (complete), ru.ts, en.ts
```

---

## 2. Design system (non-negotiable)

### Colours

Use the Malachite jade palette as CSS variables, light mode only for the demo:

| Token | Value | Token | Value |
|---|---|---|---|
| `--bg` | `#F4F6F5` | `--accent` | `#0E7C70` |
| `--surface` | `#FFFFFF` | `--accent-hover` | `#0B6B61` |
| `--surface-2` | `#EBEFEE` | `--accent-text` | `#0B6B61` |
| `--border` | `#DDE3E1` | `--accent-soft` | `#E1F2EF` |
| `--border-strong` | `#C5CDCB` | `--success` | `#3F7A16` |
| `--text` | `#0F1716` | `--danger` | `#C23B2E` |
| `--text-2` | `#56605E` | `--warning` | `#8F5A00` |
| `--text-muted` | `#5E6765` | `--on-accent` | `#FFFFFF` |

Chart series:

| Token | Value | Use |
|---|---|---|
| `--chart-s1` | `#00897A` | this year, the main series |
| `--chart-s2` | `#D2861F` | amber |
| `--chart-s3` | `#4F6CC4` | indigo: last year, spending, "underpriced" |
| `--chart-grid` | `#EBEFEE` | |
| `--chart-zone` | `#F4F6F5` | |

Colour rules:
- Jade is used **only** for:
  - the one primary button on a screen
  - the active nav item
  - links
  - the one solid "decision" tile on Bugun
  - the main chart series
- Money numbers use `--text`.
- Positive and negative changes are coloured text (`--success` / `--danger`), never pills.
- Stock rating uses a diverging scale:
  - underpriced: indigo
  - fair: `#B9C2BF`
  - overpriced: amber
  - no data: `--text-muted` at 30%

### Glass (classic frosted glass, not Apple liquid glass)

- **Page background:** a fixed backdrop.
  - A 135° linear gradient: `#D6E8E3` → `#EEF1F0` (55%) → `#DEE5EC`.
  - Two very faint blurred washes: jade at 16% opacity in the top right, indigo at 10% in the bottom left.
  - Both washes use `filter: blur(220px)` and `pointer-events: none`.
- **Tiles, sidebar and top bar:**
  - `background: rgb(255 255 255 / .55)`
  - `backdrop-filter: blur(32px)`
  - `border: 1px solid rgb(255 255 255 / .75)`
  - `box-shadow: 0 10px 36px rgb(15 23 22 / .05)`
- **Nested panels inside a tile:** `rgb(15 23 22 / .04)`, no border.
- Text never sits directly on the blur without the 55% white layer.

### Radius and spacing (concentric rule)

Inner radius = outer radius − padding.

| Element | Radius | Padding |
|---|---|---|
| Tiles | 36 | 20 |
| Panels and inputs inside tiles | 16 | |
| Buttons in tiles | 16 | |
| Sidebar | 36 | |
| Nav items | 28 | |
| Top bar | 36 | |
| Search field | 20 (pill) | |
| Tooltips | 12 | |

- Spacing scale: **4, 8, 12, 16, 20, 24, 32** only.
- The page margin, the gap between tiles and the tile padding are all **20**.
- Layout is 1440 wide:
  - sidebar 88 px, a 20 px gap, content 1292 px
  - a 4-column grid of 308 px columns with 20 px gaps
  - below 1280 px, collapse to 2 columns, then to 1

### Typography

| Use | Font | Size |
|---|---|---|
| Headlines and big money figures | **Newsreader** 500, letter-spacing −1%, line-height 1.12 | 24–56 |
| UI text | **Onest** | 15/600 titles · 13–14 body · 12 captions |
| Dates, IDs, invoice numbers, times, chart axes, small data | **IBM Plex Mono**, tabular numbers | 11–13 |

- No uppercase, no letter-spaced "eyebrow" labels.
- Sentence case everywhere.

### Number and text formatting (`src/lib/format.ts`)

- Thousands are separated by a space: `$3 940`, `31 000 000 so‘m`.
- Decimals use a comma: `8,4%`, `148,2 mln`.
- Minus is `−` (U+2212).
- Uzbek apostrophes are `‘` and `’`: `so‘m`, `o‘tgan`, `e’lon`.
- Short money: `148,2 mln so‘m`, `4,2 mlrd so‘m`.
- Dates: `17-noyabr`, short `17-noy`.

### Buttons

- **Primary:** accent background, white text, height 48 (large) or 40.
- **Secondary:** white at 80% with a `--border-strong` border.
- **Plain:** accent-text, no background.
- **At most one primary button per view.**
- All touch targets are at least 44 px.

---

## 3. Data layer

### Environment

- `.env.local`:
  ```
  NEXT_PUBLIC_API_URL=http://localhost:8000
  NEXT_PUBLIC_USE_FIXTURES=auto
  ```
- `auto` means: try the API, and if it is unreachable or returns a 5xx, fall back to fixtures and show a small muted line "Demo ma’lumotlari" in the top bar.

### Client and auth

- `src/lib/api/client.ts` is a fetch wrapper that:
  - sends `X-API-Key` and `Accept-Language`
  - parses the `{error:{code,message,details}}` error shape
  - pages lists in `{items, next_cursor, total}` form
  - times out after 15 s
- **Auth:** `/login` lists the demo accounts as plain rows (name, role, one line about what they see). Choosing one stores the key in `localStorage` and routes to:
  - `/bugun` for businesses
  - `/partner` for the bank or the bazaar administration
- Read the real demo keys from the backend README or seed. They are probably:
  - `demo-chilonzor` (owner)
  - `demo-chilonzor-manager`
  - `demo-chilonzor-appraiser`
  - TechOpt's key
  - `demo-demo-bank`
  - `demo-bozor-admin`
- A small account switcher sits behind the avatar at the bottom of the sidebar.

### Fixtures

- `src/lib/api/fixtures/*.ts` holds realistic data matching the Figma frames. Section 5 lists the exact numbers.
- Every hook returns the same shape whether the data is live or from fixtures.

### Endpoints to use

Confirm all of these against `openapi.json`.

| Area | Endpoints |
|---|---|
| Dashboard and decisions | `GET /dashboard`, `GET /decisions?status=pending`, `POST /decisions/{id}/approve`, `POST /decisions/{id}/ignore` |
| Stock | `GET /stock/units`, `GET /stock/summary`, `POST /stock/reprice`, `POST /stock/list-on-exchange`, `GET /stock/export?format=` |
| Market and pricing | `POST /market/price`, `GET /market/sourcing-radar`, `POST /market/price-from-link` |
| Fast inputs | `POST /input/parse`, `POST /input/imei`, `POST /input/voice` |
| Books | `/books/transactions`, `/books/upload/preview`, `/books/upload`, audit flags, budgets |
| Exchange | RFQs, quotes (`counter`, `respond`), offers, deals (`/document`), `GET /exchange/demand` |
| Advisor | `POST /advisor/chat` (with `context`; renders `blocks` + `chips`), `POST /advisor/credit`, loan readiness, `POST /advisor/loan-applications` |
| Lender | `POST /lender/valuations`, `GET /lender/collateral`, `GET /lender/collateral/summary`, `GET /lender/applications`, `POST /lender/applications/{id}/decision`, `GET /partner/market-report` |
| Platform | `GET /integrations`, `POST /integrations/{kind}/sync`, `GET /activity`, `GET /meta`, `GET /model` (own-model card) |

**Approve and Ignore are optimistic:** the card leaves at once, and is restored with an inline error if the call fails. A 409 means "already resolved"; refetch.

---

## 4. Shell

### Sidebar (88 px, glass)

- Logo tile "R" at the top.
- Nav items, icon above a 11 px label:
  - **Bugun**, **Narxlar**, **Birja**, **Kitoblar**, **Maslahat**
  - **Sozlama** at the bottom, then the avatar
- The active item gets `--accent-soft` with accent-text icon and label.
- The partner console has its own items: **Arizalar**, **Garov**, **Hisobot**.

### Top bar (64 px, glass, radius 36)

- Left: the page title (Onest 600, 17) and a muted subtitle, e.g. "Seshanba, 17-noyabr".
- Some pages put a segmented section switch next to the title.
- Right:
  - The search pill: 320×40, white at 72%, hairline border, a 16 px muted search icon, placeholder "Qidirish", and "Ctrl K" in mono on the right. **Ctrl K** opens a command palette that searches products, invoices, partners and pages.
  - The copilot toggle (a plain icon button).
  - Notifications, with a 6 px red dot only when there are unread items.

### Copilot side panel

- 400 px wide, slides over from the right. It is available on every business screen.
- It sends `context` (`screen` + selected IDs) and renders answer blocks (section 6.9).

---

## 5. Screens (data shown is the demo seed; match the numbers)

### 5.1 Bugun (home) — `/bugun`

A 4-column bento, row heights 330 / 472 / 320 / 300.

**Row 1**
- **Greeting tile (2 columns)**
  - Left: Newsreader 34 "Xayrli tong, Chilonzor Phone", with a one-line insight under it: "iPhone 13 narxlari 7 kunda 3% tushdi. 9 donani shu hafta soting."
  - Right, aligned right: "Bugungi savdo" / **$3 940** (Newsreader 44) / mono "+$310 · 8,4%" in success, then muted "kechaga nisbatan".
  - Below: the **SalesStrip**.
- **"Bozordan arzon" tile (1 column):** 3 sourcing-radar rows. Each row has the name, mono "$780 · bozor $875", the % in success, and "~$70 foyda". The link "Barcha 23 ta topilmani ko‘rish" goes to the radar.
- **Decision tile (1 column, rows 1–2, solid `--accent`, white text, padding 24, the only solid tile)**
  - Header: "Bugungi eng muhim qaror" and mono "1 / 4".
  - Newsreader 30 title, e.g. "MacBook Air M2 narxini $775 ga tushiring".
  - Two lines of reasons.
  - An evidence panel (white at 12%, radius 12) with 4 key/value rows: Hozirgi narx $870, Bozor medianasi $760, Sotilish vaqti "45+ → 9 kun", Kutilgan foyda +$95.
  - "Keyingi qarorlar": 3 rows with amounts.
  - At the bottom: a white button with accent text ("Narxni $775 qilish"), which runs the approve call, and a plain "O‘tkazib yuborish", which runs ignore.
  - Both buttons take the next pending decision from `/decisions`.

**Row 2**
- **Sales tile (3 columns):** "Savdo" with the **SalesForecast** chart.

**Row 3**
- **"Ombor holati" (1 column):** a **TickGauge** of the 80 units: 9 underpriced, 51 fair, 14 overpriced, 6 no data. The centre reads "14" (Newsreader 40) over "dona bozordan qimmat". A legend sits below with counts.
- **"Pul oqimi" (2 columns):** the **CashFlowMirror** chart.
- **Limits tile (1 column):**
  - "Budjet · noyabr": 148 / 240 mln with a **TickBar** and the warning "Limit 26-noyabrda tugaydi".
  - A divider.
  - "Kredit tayyorligi": 78 / 100 with a TickBar, and "2 ta bank taklif bermoqda".

**Row 4**
- **"So‘nggi faoliyat" (2 columns):** 5 rows with a mono time, the text, and a mono value.
- **"Bozor narx indeksi" (1 column):** iPhone 13 128GB · Toshkent · 214 e’lon, **$412** with "−3,1% 7 kunda", and a **Sparkline** with the p25–p75 band.
- **"Birja · RFQ #148" (1 column):** "3 ta taklif" and 3 horizontal price bars: Sam Xit $249 (jade), TechOpt $262, MobiGross $271.

### 5.2 Narxlar — `/narxlar` (switch: **Ombor** | **Baholash**)

**Ombor (stock command center)**
- A row of KPI tiles:
  - stock value at cost
  - stock value at market
  - units overpriced (14)
  - aging units (6)
  - margin at risk
- A data table of `/stock/units` with columns:
  - model + attributes
  - list price
  - market price
  - % vs market (coloured text)
  - margin
  - days in stock
  - expected days to sell
  - rating (coloured text with a 8 px square swatch, not a pill)
  - suggested price
  - action
- Filters: category, rating, aging only, store.
- Row selection checkboxes and a sticky bottom action bar: "**14 tasini tavsiya narxga o‘zgartirish**" (the one primary), plus secondary "Birjaga chiqarish" and "Excel / CSV / 1C".
- The copilot gets the selected IDs.

**Baholash (Pricing Desk, Figma frame `28:60`)**
- Left tile, the form:
  - IMEI or model field, 56 px high, with a scan icon button
  - the detected model card
  - condition A / B / C as large selectable cards
  - battery slider with its value
  - "Qo‘shimcha ma’lumotlar" collapsed
- Fast inputs live here too: free text, voice (falls back to typing on 503), and a pasted `t.me` link.
- Right top, the verdict:
  - "Ko‘pi bilan shuncha to‘lang", **$410** (Newsreader 64) with ≈ so‘m
  - a 4-cell panel: Avval taklif qiling $380, Qayta sotish narxi $520, Sizning foydangiz +$110, Sotilish vaqti ~6 kun
  - a **RangeBar** marking your limit, the median and the listing range
  - one primary button "Sotib olish va omborga qo‘shish" and plain "Mijoz rad etdi"
- Right bottom left: "Narx nimadan iborat", the **PriceWaterfall**.
- Right bottom right: "Eng yaqin e’lonlar", 3 comparables with source links.

### 5.3 Birja — `/birja` (switch: **So‘rovlarim** | **Bozordan arzon** | **Ulgurji lotlar** | **Talab**)

**So‘rovlarim (RFQ, frame `29:66`)**
- Left column, the request card:
  - specs
  - market estimate "$5 240 = $262 × 20, 85 ta e’lon medianasi"
  - a status stepper: Yuborildi → 3 ta taklif keldi → Taklifni tanlang → Bitim kitoblarga yoziladi
- Right column:
  - **Recommended quote** tile with a 1.5 px jade outline: supplier name, verification line, **$249 / dona**, "Arzon −5%", "Jami $4 980 · bozor bahosidan $260 kam", and a "Nega aynan shu taklif" panel of plain lines (no checkmark icons; the warning line in warning colour). One primary button "Taklifni qabul qilish · $4 980", plus plain "Narxni kelishish", which opens the counter-offer flow.
  - "Takliflar bozorga nisbatan" tile with the **QuoteSpread** chart and the summary "$13 arzon".
  - "Boshqa 2 ta taklif" rows.

**Bozordan arzon (Sourcing Radar, frame `82:2`)**
- A KPI strip: 23 topildi, −11%, ~$1 240, 15 kanal.
- The finds table: product (2 lines), price, market, difference, profit, days, source channel + age, and "Ochish".
- A "Jonli lenta" tile showing one raw Telegram post, "Raft-Extractor o‘qidi · 0,8 s", the extracted key/value fields, and the verdict "$490 bozordan −9%".

**Ulgurji lotlar:** the wholesale and surplus board, with the market difference as coloured text.

**Talab:** demand by district as horizontal bars, plus the most-requested models.

**Supplier role** (TechOpt key, frame `82:284`) sees **Kelgan so‘rovlar**:
- a list with the selected row inset (radius 16)
- a quote form with the market reference and a **RangeBar** marker for "Sizning narxingiz $258"
- fields: price, quantity, delivery, warranty
- total **$5 160**, "bozordan 1,5% arzon"
- primary "Taklif yuborish · $5 160"
- the demand-by-district tile

### 5.4 Kitoblar — `/kitoblar` (switch: **Tekshiruv** | **Budjet** | **Hisobotlar**)

**Tekshiruv (frame `30:2`)**
- Left: the issues list: "4 ta yozuv tekshiruv kutmoqda · 412 ta yozuvdan".
  - Rows have the title, a mono subtitle and the amount. No icon tiles.
  - The selected row has a tinted background.
  - A collapsed "408 ta yozuv to‘g‘ri" at the bottom.
- Right: the selected issue:
  - breadcrumb "1 / 4 · Faktura #2231 · TechOpt Wholesale"
  - title "Fakturada jami summa 1 mln so‘m ortiqcha"
  - a calculation table (radius 16, the danger-soft row clipped to the radius)
  - a "Kuzatuv" note
  - an invoice replica (mono)
  - the **InvoiceAnomalies** chart
  - primary "31 000 000 deb tuzatish" and plain "Bu to‘g‘ri, o‘tkazib yuborish"
- Upload: drag-and-drop for Excel, CSV and 1C files, with a column-mapping preview table before import. An invoice-photo upload is also available.
- "Didox’dan sinxronlash" calls `POST /integrations/didox/sync`.

**Budjet**
- Plan vs fact per category as a bar chart.
- A month-end forecast line.
- What-if sliders (ads %, purchases) that recompute the limit date.
- The early-warning state.

### 5.5 Maslahat — `/maslahat` (frame `82:486`)

- **Left, 3 columns: the copilot conversation.**
  - The user's question in a tinted bubble on the right.
  - The answer as blocks: a 4-cell KPI row (Kredit 300 mln, Muddat 24 oy, Stavka 24% yillik, Oylik to‘lov 15,9 mln), two sentences, **ScheduleBars** (principal vs interest, 24 months), and "Jami foiz: 80,7 mln so‘m".
  - Chips rendered as secondary buttons: "Muddatni 36 oyga o‘zgartirish", "Ariza tayyorlash", "Jadvalni Excel’ga yuklash".
  - A 52 px input at the bottom: "Savol bering yoki ovozli xabar yuboring" with "Enter".
- **Right, 1 column:**
  - "Kreditga tayyorlik" **78** / 100
  - 4 factor bars: Kitoblar tozaligi 92, Savdo barqarorligi 81, Birja tarixi 64, Qarz yuki 70
  - "Qanday oshirish", with +ball values
  - "Soliq taxmini · noyabr": 9,8 mln so‘m
  - primary "Bankka ariza yuborish", which opens a consent dialog; the user must tick explicit consent before it submits
- A credit calculator dialog covers 4 products (business loan, auto loan, mortgage, leasing) and shows the full schedule.

### 5.6 Partner console — `/partner` (Demo Bank key, frame `82:698`)

- A KPI strip: Garov portfeli 4,2 mlrd so‘m, O‘rtacha LTV 58%, Kuzatuvda 3 (warning), Yangi arizalar 2.
- **"Kredit arizalari":** the selected application panel (the borrower's snapshot as key/value rows), primary "Tasdiqlash", secondary "Rad etish", and the next application below.
- **"Garov qiymati":** item title, **$11 400** "adolatli narx", a **RangeBar** with the p25–p75 band and the liquidation marker ($9 800, warning), key/value rows, and comparables. The valuation form takes parameters, a `t.me` link or an inventory ID.
- **"Garov portfeli" table:** object, borrower, value, 30-day change, LTV, and status as coloured text (Normal / Kuzatuv / Chegaradan oshdi).
- `/partner/hisobot`: the market report by model and district (table, weekly trend, xlsx export), for the bank and the bazaar administration.

### 5.7 Sozlama — `/sozlama`

Tabs:
- **Integratsiyalar:** status rows (Telegram live; Didox, Soliq, BILLZ, 1C and bank marked "sinov rejimi")
- **Foydalanuvchilar:** roles owner / manager / appraiser; the API key is shown once
- **Do‘konlar**
- **Faoliyat jurnali**
- **Til:** uz / ru / en

### 5.8 Model card — `/model`

"Bizning modelimiz: Raft-Extractor" with its base model line and the accuracy table: Raft-Extractor vs Gemini vs rule parser for valid JSON, category, brand/model, price, currency, latency and cost per 1000 posts.
- Data comes from `GET /model`.
- If that call fails, show the fixture values with a warning line: "Namuna raqamlar".

---

## 6. Signature components (`src/components/charts`)

All charts are hand-built SVG with these rules:
- one axis per chart
- muted grid
- 2 px lines
- data ends rounded 4 px
- a legend when there are 2 or more series
- a hover layer with a crosshair or per-mark tooltip; hit targets are larger than the marks
- keyboard support where noted
- text in text colours, never in series colours

Tooltips are dark (`--text` background, radius 12): white value lines, muted meta.

1. **SalesForecast**
   - 180 days of history + 60 days of forecast.
   - This year is a solid jade line; last year an indigo line at 1.5 px; the forecast is dashed jade with a p-band at 14% and a shaded "Prognoz" zone after the "Bugun" line.
   - Header: period text, total in Newsreader 32, change vs last year.
   - **Drag left or right to pan the 60-day window.** It also pans with arrow keys (Shift = 7 days).
   - A navigator strip with a draggable window.
   - The y-scale is fixed while panning.
2. **PriceWaterfall**
   - $520 → −$15 (battery, danger) → +$10 (box, success) → −$105 (margin, neutral) → **$410** (accent).
   - The axis starts at $350 with a "≈" break mark.
   - Hovering a step dims the others and shows its reason.
3. **QuoteSpread**
   - 85 market listings as grey dots in a beeswarm strip, with the median dashed (stopping above the quotes row).
   - Quotes on their own row with two-line labels; the recommended quote is jade.
   - Hover shows a tooltip.
4. **InvoiceAnomalies**
   - 8 invoices.
   - A green dot when the total matched; a red bar for the overstatement in mln (+0,6, +1,2, +1,0). The current invoice is outlined.
   - The tooltip sits beside the bar, not over it.
5. **SalesStrip**
   - 30 daily bars against a dashed $3 500 plan.
   - Days that met the plan are jade, the rest `--border-strong`.
   - Hover shows the day and the % against plan.
6. **CashFlowMirror**
   - 6 months, in mln so‘m.
   - Income above a centred month axis (jade), spending below it (indigo), last year at 35% opacity.
   - Hovering a month shows a crosshair and income / spending / net.
7. **TickGauge**
   - A half-circle of 57 tick marks (longer every 7th), coloured by segment.
   - A centre value. Used for stock health.
8. **TickBar, Sparkline (median + band), RangeBar (band + markers + labels), ScheduleBars (stacked principal/interest)**
9. **Copilot blocks**
   - One React component per block type: `price_range`, `comparables`, `kpi_row`, `bar_chart`, `line_chart`, `table`, `steps`, `loan_schedule`, `file`.
   - Chips run their `{endpoint, method, body}` action.

---

## 7. Interaction and states

- Every data view has a **loading skeleton** in the tile's shape (no spinners), an **empty state** (one muted sentence plus one action), and an **error state** (sentence + "Qayta urinish").
- **Optimistic updates** for approve, ignore and reprice, with an "Bekor qilish" undo bar for 5 s after bulk actions.
- Focus rings use 2 px accent at 40% opacity, offset 2.
- Everything is reachable by keyboard; Esc closes the panel, dialog and palette.
- Respect `prefers-reduced-motion`.

---

## 8. Avoid AI-made website mistakes (review every screen against this list)

1. No gradient text, purple/blue gradients, neon accents or glowing blobs. Only the one faint backdrop.
2. No sparkle icons (✦ ✨) or "AI" badges. Do not personify the AI as "Pilot". Use "Kuzatuv" for observations and "Tavsiya" for recommendations.
3. No pill badges or dot-plus-label chips for statuses. Use coloured text, with an 8 px square swatch only in legends.
4. No icons in tinted squares or circles. No tick-in-a-circle lists.
5. No uppercase or letter-spaced eyebrow labels.
6. No em dashes (—) in copy. Use commas or full stops. An en dash only in ranges (`$10 600 – $12 100`).
7. No decorative "→" arrows after links.
8. No emoji anywhere in the UI.
9. Do not use Inter, Geist, Poppins or Space Grotesk.
10. One primary button per view. No two equally loud actions.
11. No identical 3-up feature card grids. Every tile has a different job and size.
12. No centred-everything layouts. Left-align text; right-align numbers in tables.
13. No lorem or generic copy ("Unlock the power of…"). Use the real Uzbek copy from section 5.
14. No fake live jitter (random numbers changing every second). Only real data moves.
15. No numbered step circles. Steps are plain mono numbers.
16. No border-left accent stripes on cards.
17. Low-contrast text is not allowed: body text has at least 4.5:1 contrast on glass.
18. Spacing only from the scale; radii only from the concentric rule.
19. No default shadcn look: restyle every primitive.
20. No heavy drop shadows: one soft shadow level for tiles, one for tooltips and popovers.
21. No mixed icon stroke widths.
22. No uneven baselines in rows: align numbers on the baseline, use tabular numbers.
23. No text overflow: truncate with a `title` tooltip, never let it collide.
24. No modal for things that fit inline.
25. No scroll-jacking or parallax.
26. No placeholder-as-label inputs: every field has a visible label.
27. No disabled buttons without a reason: show why next to them.
28. No hover-only information on touch: tooltips also open on tap and focus.
29. No orphaned single words in headlines; set `text-wrap: balance` on headings.
30. No "made by" badges or credits in the product.

---

## 9. Internationalisation

- Uzbek (Latin) is the default and must be complete.
- Russian and English dictionaries exist with the same keys.
- Fill Russian for the shell and Bugun; elsewhere fall back to Uzbek.
- Use the `‘` and `’` characters, never a plain `'` in Uzbek words.

---

## 10. Quality bar

- `npm run build` passes, with no TypeScript errors and no console errors.
- Lighthouse accessibility is at least 95 on Bugun.
- Each screen is checked in the browser at 1440×900 and 1280×800.
- Take a screenshot of each screen into `docs/screens/` with a Playwright script (`npm run shots`) and look at every one for overlaps, clipping and misalignment before you call a phase done.

---

## 11. Build order (each phase = working app + commit)

1. **Foundation (≈30 min):**
   - Next.js + Tailwind v4 + shadcn + fonts + tokens + backdrop
   - Sidebar, top bar, search pill, command palette shell
   - `/login`, API client, fixtures fallback
2. **Bugun:** all tiles, SalesStrip, SalesForecast (with drag), TickGauge, CashFlowMirror, decisions approve/ignore wired.
3. **Narxlar:** the stock command center table + bulk reprice; Pricing Desk with PriceWaterfall, RangeBar and fast inputs (text + IMEI; voice and link if time allows).
4. **Kitoblar:** the audit review with InvoiceAnomalies, Didox sync, upload with mapping preview; Budjet with what-if.
5. **Birja:** RFQ + QuoteSpread + accept/counter; Sourcing Radar; supplier view with the quote form; demand.
6. **Maslahat + copilot panel:** block renderer, credit calculator, readiness, consented loan application.
7. **Partner console:** applications, valuation, portfolio, market report; `/model` card; Sozlama.
8. **Polish pass** against section 8, screenshots, README with run steps and the demo click path.

**Cut order if time runs out** (drop from the end):
- Russian/English copy
- Sozlama tabs other than integrations
- market report xlsx
- the customizable widget edit mode on Bugun (MVP feature; build it last with dnd-kit: add, remove, reorder, resize, presets, saved per user)
- voice input
- counter-offers

**Never cut** Bugun, the stock command center, the Pricing Desk, the audit review, the RFQ flow, Maslahat and the partner console: they carry the demo.

---

## 12. Demo click path (must work end to end, live or on fixtures)

1. **Birja → Bozordan arzon:** a new post in "Jonli lenta" becomes a priced find (own model).
2. **Narxlar → Ombor:** 80 units, 14 overpriced, 6 aging → select the 14 → reprice in one click → undo bar.
3. **Kitoblar:** Didox sync → wrong total and an above-market purchase appear → fix → the decision leaves Bugun.
4. **Bugun:** the budget tile shows the limit warning (the Telegram alert fires on the backend).
5. **Birja:** RFQ #148 → switch to the TechOpt account → send a quote → switch back → accept → the deal appears in Kitoblar.
6. **Maslahat:** apply for a loan with consent → switch to Demo Bank → the same numbers appear, and the collateral is valued live.
7. **/model:** our model vs the cloud model vs the rule parser.

---

## 13. When done, print

- How to run: `npm install`, `npm run dev`, and which backend URL and keys are used.
- Which endpoints were live and which still run on fixtures.
- The list from section 8 with a ✓ per item, plus any screen where you had to deviate from Figma and why.
