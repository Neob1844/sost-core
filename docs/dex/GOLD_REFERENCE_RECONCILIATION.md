# Gold reference — 1.14 mg vs "31.1034768 / 35": resolution (documentary, no policy change)

A concern was raised that the site shows **1.14 mg gold per SOST** while an earlier note used
**31.1034768 / 35 ≈ 0.8887**. These are **not two competing SOST figures** — they measure
different things. Verified against the code; the canonical SOST reference is unchanged.

## The three numbers, disentangled
1. **1.14 mg gold per SOST** — the SOST monetary reference. It is the SOLE SOST figure, and it is
   canonical across the site: `website/sost-reference.html` title/hero/cards, and
   `website/js/sost-gold-reference.js` (`WEIGHT_MG = 1.14`, `MG_PER_TROY_OZ = 31103.4768`,
   `sostFromOz = goldUsdPerOz * 1.14 / 31103.4768`). It is chosen so that
   `1.14 mg × gold-spot ≈ $0.15`, SOST's stated INITIAL sale/listing price. Informational
   reference, not a peg, not redeemable (see the page disclaimer).
2. **31.1034768** — this is ONLY the physical constant *grams per troy ounce* (equivalently
   `MG_PER_TROY_OZ = 31103.4768`). It appears in the code purely as a unit conversion
   (`gramFromOz(oz) = oz / 31.1034768`), NEVER as a SOST reference weight. It is not "a formula for
   SOST".
3. **31.1034768 / 35 ≈ 0.8887 g** — this is the **1944 Bretton Woods** peg: $35 bought one troy
   ounce, so $1 ≈ 0.888 **grams** of gold. On `sost-reference.html` it is shown explicitly as the
   1944 **US-dollar** peg ("In 1944, Bretton Woods fixed the dollar at $1 = 0.888 g of gold"),
   used ONLY as a historical analogy — never as the SOST figure.

## Why there is no contradiction
- #1 is **milligrams of gold per SOST (2026 reference)**; #3 is **grams of gold per 1944 US
  dollar (historical peg)**. Different asset, different era, different unit (mg vs g). Comparing
  1.14 mg to 0.888 g is a category error (0.888 g = 888.7 mg is the *dollar's* 1944 gold content,
  not SOST's).
- The string "0.8887 **mg**" for SOST does **not** exist anywhere in the repo. A grep for
  `0.8886`/`0.88867` returns nothing; `31.1034768` occurs only as the troy-ounce constant.

## Official, current reference
**1 SOST ≡ 1.14 mg gold** is the official, current, single SOST reference. No economic parameter
is changed by this note. The DEX must therefore NOT use the gold reference as an executable market
price (it is informational); when SOST trades, the market price is set by supply and demand and
may differ materially from the reference.
