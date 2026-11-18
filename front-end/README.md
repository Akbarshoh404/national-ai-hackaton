# Raft frontend

Raft is a B2B operating system for Uzbek businesses that trade phones, laptops, cars and real estate. This repository is the Next.js frontend.

## Run

Requires Node 20 or newer.

```bash
npm install
npm run dev
```

Open http://localhost:3000 and choose a demo account.

Every screen reads from the Raft FastAPI backend; there is no built-in demo data. Start the backend first
(`start-raft.cmd` in the Raft repo). Settings live in `.env.local` (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend address |

Once the backend is running, generate its types:

```bash
npm run gen:api
```

## Demo accounts

| Account | Key | Opens |
|---|---|---|
| Chilonzor Phone Market, owner | `demo-chilonzor-phone` | `/bugun` |
| Chilonzor Phone Market, manager | `demo-chilonzor-manager` | `/bugun` |
| Chilonzor Phone Market, appraiser | `demo-chilonzor-appraiser` | `/narxlar?tab=baholash` |
| TechOpt Wholesale, supplier | `demo-techopt` | `/birja` |

The app covers phones and laptops only. The backend hides cars and apartments (`ACTIVE_CATEGORIES=phone,laptop`).

Switch accounts from the avatar at the bottom of the sidebar.

## Demo click path

Every number below comes from the backend database, so counts change as Telegram posts arrive and data is edited.

1. **Bugun.** Today's sales against the 30-day average, the pending decisions queue (approve or ignore), the cheapest market finds and the budget warning.
2. **Narxlar → Ombor.** Stock rated against the market. Select the overpriced units and apply the suggested prices; undo restores the old prices. Export to Excel, CSV or 1C from the backend.
3. **Narxlar → Baholash.** Type a model, an IMEI or a t.me link (or record voice). The price, its breakdown and the comparable listings come from the market engine.
4. **Kitoblar.** Audit flags with their calculation; fix or mark as checked. Budget plan vs fact with the month-end forecast, and the month summary under Hisobotlar.
5. **Birja.** Create or open an RFQ, compare ranked quotes, counter or accept. Switch to TechOpt to answer as the supplier.
6. **Maslahat.** Ask the copilot; credit, tax, cash flow and loan readiness are calculated in Python. Send a loan application to a partner bank.
7. **/model.** The extraction model in use, its provider order and its share of parsed posts.

## Checks

These need the app running. Set `RAFT_URL` if it is not on port 3000.

```bash
npm run typecheck
```

```bash
npm run build
```

```bash
npm run demo:check
```

```bash
npm run a11y
```

```bash
npm run shots
```

`demo:check` walks a scripted click path (written for the old demo data; it may need updating), `a11y` runs axe-core and a narrow-width check, and `shots` writes every screen to `docs/screens`. Do not run `npm run build` while `npm run dev` is active: both use `.next`. Set `RAFT_DIST_DIR=.next-prod` to build beside it.

Design and data decisions are recorded in [DECISIONS.md](DECISIONS.md).
