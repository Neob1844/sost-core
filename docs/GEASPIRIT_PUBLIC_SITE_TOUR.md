# GeaSpirit Public Site Tour — integration reference

Source: **https://geaspirit.com/** (public site) + demo report. This file is the
reference used to build the SOST ecosystem gateway at
`website/sost-geaspirit.html` and the GeaSpirit section in the SOST app
(`website/sost-app/index.html`). Only public, on-site information is recorded.

## Public positioning
- **Headline:** "GeaSpirit — Second-Chance Mining Intelligence".
- **Tagline:** "Mining Asset Intelligence for overlooked, abandoned and underused
  mining opportunities."

## What GeaSpirit does
- Identifies historic mines, abandoned assets, tailings, underused concessions
  and care-and-maintenance projects.
- Geospatial intelligence on **open data** with **explainable scoring**.
- Interactive **Asset Atlas** map.
- On-demand mining asset analysis **reports**.
- Terrain / geological signal analysis via the **GeaSpirit Engine**.

## What GeaSpirit does NOT do (disclaimers — must be preserved verbatim in spirit)
- "It does not guarantee discovery."
- Provides intelligence, prioritization and research tools on open data — **not
  investment advice, not legal advice, no guaranteed mineral discovery**.
- Not a marketplace; no ownership verification.

## Target asset types
Historic mines · abandoned assets · tailings & waste · underused concessions ·
care-and-maintenance projects · dormant sites.

## GeaSpirit Score
- Core question: *"Why should this asset earn your attention before 10,000
  others?"*
- Transparent **0–100 triage / prioritization score** — not a probability of ore,
  not a discovery guarantee.
- **Four dimensions:**
  - **SIGNAL** — satellite spectral signal blended with geological favourability.
  - **ACCESS / DEPTH** — surface reachability and depth, weighted by
    infrastructure proximity.
  - **PRECISION** — how tightly the target is bounded in space.
  - **CERTAINTY** — validation strength, reduced by a missing-data penalty.
- **Confidence bands:** HIGH / MEDIUM / LOW.

## Reports offered
1. **Asset Scan** — single-asset score, full four-dimension breakdown.
2. **Comparative Asset Ranking** — portfolio prioritization and risk.
3. **Mining Opportunity Brief** — region-level overview of overlooked targets.
4. **Tailings / Abandoned Mine Review** — residual-value signal screening.

## Languages
16: EN, ES, FR, DE, IT, NL, PL, SV, NO, DA, RU, ZH, JA, KO, AR, HE.

## Contact
- `reports@geaspirit.com` — intelligence report requests.
- `contact@geaspirit.com` — general contact.
- On-site contact / request form.

## Navigation / sections
Asset Map (`#platform`) · Second-Chance (`#why`) · Intelligence (`#intelligence`)
· Resources (`/resources/`) · Reports (`#reports`) · Contact (`#contact`) · Demo
Report (`/reports/demo-geaspirit-asset-intelligence-report.html`).

## Relationship with SOST (as integrated)
GeaSpirit is powered by the GeaSpirit Engine and connected to the SOST ecosystem.
SOST may support future payment / verification infrastructure, but GeaSpirit is
**fully usable without any blockchain** and holding SOST is **not** required. No
investment-return implication.

## How it is surfaced in SOST
- `website/sost-geaspirit.html` — leads with the Second-Chance bridge: new logo,
  positioning, GeaSpirit Score, report types, ecosystem note, honest limitations,
  and prominent **OPEN GEASPIRIT PLATFORM** / **READ DEMO REPORT** CTAs
  (`target="_blank" rel="noopener noreferrer"`). Kept as a gateway/explainer, not
  a bare redirect.
- `website/sost-app/index.html` — `SectionRenderers.geaspirit`: same positioning,
  score, reports, limits, and direct CTAs to geaspirit.com. The old restricted
  "login" panel was removed (open ecosystem gateway).
- New brand asset: `website/geaspirit-logo.png` (used in splash, hero, app card,
  OG/Twitter image).
