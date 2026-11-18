# Raft frontend decisions

Each entry records a choice made while building, and why.

## Environment and data

- **Backend was not running during the build.** `http://localhost:8000/openapi.json` refused connections, so `src/lib/api/schema.d.ts` is not generated. Run `npm run gen:api` once it is up. All endpoint paths and response shapes are provisional until then.
- **Fixtures are a stateful in-browser server** (`src/lib/api/fixtures/server.ts`), stored in `localStorage` under `raft_demo_state_v1`. A plain static fixture could not carry the demo path across account switches (a TechOpt quote reaching the shop, a loan application reaching the bank).
- **Fallback rule.** In `auto` mode the client falls back on network failure, 5xx, and also on 404, 405 or a response that fails Zod parsing. The last three go beyond the brief, because real paths and shapes are unconfirmed and a demo should not break on them.
- **Same-origin health check.** `/api/health` probes the backend from the server. A direct browser call to a stopped backend logs a console error, which the quality bar forbids.
- **Demo keys** come from the master prompt. `demo-techopt` is a guess, since no backend README was available.
- **Demo date.** The seed is anchored to Tuesday 17 November 2026 (`DEMO_TODAY`), as in the Figma frames, so the top bar date agrees with "Bugun" in the charts.

## Stack

- **shadcn/ui was set up by hand** (`components.json` plus primitives on `radix-ui` in `src/components/ui`). The CLI would have rewritten `globals.css`, and every primitive had to be restyled anyway.
- **Recharts is not used.** All charts are hand-built SVG, as the brief prefers.
- **Command palette** is built on the Dialog primitive, without adding `cmdk`.

## Design conflicts: the master prompt wins over Figma

- Section switches follow the prompt: Narxlar is Ombor and Baholash, Birja is So‘rovlarim, Bozordan arzon, Ulgurji lotlar and Talab.
- The Maslahat nav icon in Figma is a sparkle, which section 8 forbids. It uses a message icon.
- The RFQ stepper in Figma has ticks in circles and supplier initials in tinted squares. Both are replaced by plain mono numbers and plain text.
- The copilot toggle exists in the prompt but not in the Figma top bar. It is included.

## Contrast

- The decision tile's evidence panel uses white at 6%, not the 12% in the brief. White 13 px text on 12% measures about 4.05:1, below the 4.5:1 rule; 6% measures about 4.54:1.
- All text on the decision tile is pure white, because reduced-opacity white fails contrast on jade.
- Rating text uses darker variants of indigo. The series colour is kept for the swatch.

## Seed numbers

- Figma's cash flow tile says "+28 mln" average profit, while the credit screens say ~42 mln a month. The cash flow seed now averages 42 mln, so the 38% payment ratio and the bank's numbers agree everywhere.
- Figma's activity feed mentions a finished TechOpt deal and an accepted Sam Xit quote. They are attributed to RFQ #147, so they do not contradict the open RFQ #148.
- "iPhone 14 bozordan 16% arzon" in Figma disagrees with the radar's −11% for the same item. The decision uses −11%.

## Roles

- TechOpt lands on `/birja`, not `/bugun`. Its frame is the supplier workspace, and the shop's dashboard would show another company's numbers.
- The bazaar administration sees the market report at `/partner`.
- Sergeli Avto appears in the Figma account list but has no key in the prompt, so it is not offered as a login. It still exists as a borrower.

## i18n

- Shell and Bugun are fully translated in `uz`, `ru` and `en`. Other screens keep their Uzbek copy in the components. The prompt lists Russian and English copy first in the cut order.
