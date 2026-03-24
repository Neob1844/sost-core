# Materials Engine — Formula & Top Candidate Audit

**Date:** 2026-03-24

---

## Root Cause: Display Bug (Not Chemistry Bug)

The primary issue was a **formula sorting bug** — `sorted(comp.items())` in both `formula_from_dict()` and `normalize_formula()` sorted elements alphabetically, placing anions before cations in many cases:

| Before (bug) | After (fixed) | Issue |
|--------------|---------------|-------|
| OZn2 | **Zn2O** | O before Zn alphabetically |
| NSi | **SiN** | N before Si |
| AsIn | **InAs** | As before In |
| O2TiZn | **TiZnO2** | O before Ti, Zn |
| LiO2Ti | **LiTiO2** | O between Li and Ti |
| CoO2Rb | **CoRbO2** | O between Co and Rb |
| BaTe3Ti | **BaTiTe3** | Te between Ba and Ti |

**Fix:** Cations sorted alphabetically first, then anions sorted alphabetically. Standard chemical convention.

---

## Top 15 Chemical Suspicion Screen

| # | Formula | Status | Verdict |
|---|---------|--------|---------|
| 1 | CoNaO2 | KNOWN | **Reasonable** — NaCoO2 layered oxide family |
| 2 | Zn2O | NOVEL | **Interesting but risky** — zinc suboxide, rare but documented |
| 3 | CdInTe | NOVEL | **Reasonable** — CdTe semiconductor family variant |
| 4 | CdSeTe | NOVEL | **Reasonable** — CdTe/CdSe alloy, known in photovoltaics |
| 5 | CoLiS2 | KNOWN | **Reasonable** — lithium cobalt sulfide, battery family |
| 6 | InAs | KNOWN | **Reasonable** — well-known III-V semiconductor |
| 7 | SiN | KNOWN | **Reasonable** — silicon nitride family (Si3N4) |
| 8 | CdCuTe | NOVEL | **Reasonable** — Cu-doped CdTe, photovoltaic variant |
| 9 | CoKO2 | KNOWN | **Reasonable** — potassium cobalt oxide, layered family |
| 10 | CoRbO2 | KNOWN | **Reasonable** — rubidium cobalt oxide |
| 11 | LiTiO2 | KNOWN | **Reasonable** — lithium titanate, battery anode material |
| 12 | CoLiTe2 | NOVEL | **Reasonable** — chalcogenide variant of CoLiS2 |
| 13 | CoLiSe2 | NOVEL | **Reasonable** — selenide variant |
| 14 | BaTiTe3 | NOVEL | **Interesting but risky** — chalcogenide perovskite variant |
| 15 | BaTiSe3 | KNOWN | **Interesting but risky** — chalcogenide perovskite |

**No critically suspicious candidates found.** The top list is chemically defensible. Main issues were display/canonicalization, not chemistry.

---

## Fixes Applied

1. **`material_mixer/generator.py::formula_from_dict()`** — cation-first sorting
2. **`autonomous_discovery/chem_filters.py::normalize_formula()`** — cation-first sorting
3. **`artifacts/campaign_snapshots.json`** — all formulas re-canonicalized
4. **`website/js/materials-data.js`** — regenerated with canonical formulas
5. **`website/sost-materials-engine.html`** — top candidates table updated
6. **7 new tests** in `test_formula_audit.py`
