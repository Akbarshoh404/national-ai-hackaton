# Raft frontend

Raft is a B2B operating system for Uzbek businesses that trade phones, laptops, cars and real estate. This repository is the Next.js frontend.

## Run

Requires Node 20 or newer.

```bash
npm install
npm run dev
```

Open http://localhost:3000 and choose a demo account.

The app expects the FastAPI backend at `http://localhost:8000`. When it is unreachable, every screen runs on the built-in demo data and the top bar shows "Demo ma’lumotlari". Settings live in `.env.local` (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend address |
| `NEXT_PUBLIC_USE_FIXTURES` | `auto` | `auto` tries the API first, `true` is demo data only, `false` is API only |

Once the backend is running, generate its types:

```bash
npm run gen:api
```

## Demo accounts

| Account | Key | Opens |
|---|---|---|
| Chilonzor Phone Market, owner | `demo-chilonzor` | `/bugun` |
| Chilonzor Phone Market, manager | `demo-chilonzor-manager` | `/bugun` |
| Chilonzor Phone Market, appraiser | `demo-chilonzor-appraiser` | `/bugun` |
| TechOpt Wholesale, supplier | `demo-techopt` | `/birja` |
| Demo Bank | `demo-demo-bank` | `/partner` |
| Malika bozori, bazaar administration | `demo-bozor-admin` | `/partner` |

Switch accounts from the avatar at the bottom of the sidebar. To rehearse again, use "Demo ma’lumotlarini tiklash" on the login page or in Sozlama → Til.

## Demo click path

1. **Birja → Bozordan arzon.** Press "Keyingi e’lonni o‘qish". The post is read and appears at the top of the finds.
2. **Narxlar → Ombor.** 80 units, 14 overpriced, 6 aging. Press "Qimmat 14 tasini tanlash", then "14 tasini tavsiya narxga o‘zgartirish". The undo bar stays for 5 seconds.
3. **Kitoblar.** Press "Didox’dan sinxronlash", then "31 000 000 deb tuzatish". The invoice decision leaves Bugun.
4. **Bugun.** The budget tile shows "Limit 26-noyabrda tugaydi".
5. **Birja.** Switch to TechOpt and send the quote. Switch back and accept. The deal appears in Kitoblar → Hisobotlar.
6. **Maslahat.** Press "Bankka ariza yuborish", tick consent and send. Switch to Demo Bank: the same numbers appear, and collateral can be valued live.
7. **/model.** Raft-Extractor against the cloud model and the rule parser.

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

`demo:check` walks the click path above, `a11y` runs axe-core and a narrow-width check, and `shots` writes every screen to `docs/screens`. Do not run `npm run build` while `npm run dev` is active: both use `.next`. Set `RAFT_DIST_DIR=.next-prod` to build beside it.

Design and data decisions are recorded in [DECISIONS.md](DECISIONS.md).
