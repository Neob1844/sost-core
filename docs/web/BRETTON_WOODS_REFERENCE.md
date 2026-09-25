# SOST Bretton Woods monetary reference — rollout plan

Branch `feat/web-bretton-woods-reference` (web/docs only; NO consensus/node/miner/keys). Prepared
without running intensive tests while the clean sync measurement is in progress.

## Exact formula (single source of truth)
- Bretton Woods parity: 35 USD / troy ounce; 1 troy oz = 31.1034768 g.
- 1 SOST ≡ 1/1000 of the dollar's gold content = **31.1034768 / 35 / 1000 g = 0.0008886707657142857 g
  = 0.8886707657142857 mg**.
- `USD/SOST = gold_USD_per_gram × 0.0008886707657142857`.
- Implemented in `website/js/sost-gold-reference.js`: `WEIGHT_MG = 31.1034768 / 35` (0.8886707657142857 mg),
  `sostFromGram = perGram × WEIGHT_MG/1000`. Rounding only for display.
- **Discipline:** voluntary project DENOMINATION, not a peg, not collateral, not redeemable, no gold
  entitlement. The /1000 divisor is a SOST choice, NOT part of the 1944 agreements.

## Phase status
- **DONE (this commit):** single-source constant + header disclaimers → Bretton Woods. Every page that
  computes via the shared JS now yields the new reference. Verified: WEIGHT_MG=0.8886707657142857,
  perGram=0.0008886707657142857, USD/SOST@137.93=0.12257.
- **Inventory of hardcoded occurrences to rewrite** (1.14mg/0.00114/WEIGHT_MG text): `sost-reference.html`,
  `sost-markets.html`, `index.html`, `sost-explorer.html`, `sost-app/index.html` (+ the JS, done).

## Remaining phases (low-CPU web edits; large; queued behind security+sync priority)
1. `sost-reference.html` full rewrite: title/subtitle, Bretton Woods history (1944/44 nations/35-per-oz/
   fixed-but-adjustable/official convertibility mainly between monetary authorities/full operation 1958/
   1960s imbalances/1971-08-15 suspension/1973 float), sourced to federalreservehistory.org; SOST
   philosophy clearly labelled as project view not historical fact; the calculation block; live USD ref
   (UTC + source + spot-vs-XAUT/PAXG distinction); first-listing methodology (snapshot, frozen announced
   price, market independent afterwards — no order/swap activation).
2. Two charts (2019–present) from ONE gold USD/g series: value of 0.8886707657 mg vs value of 1 mg;
   labelled as a reference counterfactual, NOT historical SOST quotes; separate 1944/1971 milestone block.
3. `sost-explorer.html`: SOST GOLD REFERENCE card + chart + MONETARY REFERENCE block → same JS source;
   update link to the detail page; keep market price vs reference distinct.
4. Text audit of the hardcoded 1.14mg strings in index/markets/sost-app → consistent with the JS.
5. Tests: math, cross-page consistency, missing-data/stale handling, mobile/desktop, sources.

Nothing deployed/announced without explicit authorization.
