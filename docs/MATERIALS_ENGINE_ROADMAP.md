# Materials Discovery Engine — Expansion Roadmap

## Current State (April 2026)
- 76,193 materials corpus (JARVIS + AFLOW)
- 29 campaign profiles, 16 industrial domains
- CGCNN (formation energy) + ALIGNN-Lite (band gap) + CHGNet (pre-DFT validation)
- 50+ validated candidates
- $0/month compute cost

## Expansion Plan (6 Lines of Attack)

### 1. Expand Database (76K → 500K+)

Target sources (all open):
- Materials Project (~150K structures, API available)
- OQMD (~1M DFT calculations)
- AFLOW (~3.5M entries, already partially integrated)
- JARVIS (already primary source, expand to full catalog)
- NOMAD (~12M calculations, CC-BY)
- Materials Cloud (curated datasets)
- Open Catalyst Project (catalysis-specific, ~1.5M relaxations)

Priority: Materials Project API integration first (best quality, well-documented API).

### 2. PGM Replacement Engine

New module for finding cheap alternatives to platinum group metals:
- **Target metals to replace:** Pt, Pd, Rh, Ir, Ru
- **Replacement elements:** Fe, Ni, Mn, Co, Cu, Ti, Mo, W, Al, C, N, S

Target material families:
- Perovskites (ABO₃)
- Spinels (AB₂O₄)
- Sulfides (MoS₂, WS₂, NiS)
- Nitrides (TiN, Fe₃N)
- Carbides (WC, TiC, Mo₂C)
- Phosphides (Ni₂P, CoP, FeP)
- Fe–N–C systems (ORR catalysts)
- Mixed oxides (La₁₋ₓSrₓCoO₃)

Applications:
- Hydrogen fuel cells (ORR/HER/OER catalysts)
- Exhaust catalysis (three-way catalysts)
- Water electrolysis
- Chemical synthesis

### 3. Reduce Computational Cost (Pyramid Strategy)

```
Level 1: Chemical filter (instant) — reject impossible candidates
Level 2: GNN fast pass (~1s) — CGCNN/ALIGNN formation energy + band gap
Level 3: MLIP relaxation (~40s) — CHGNet/M3GNet/MACE structural optimization
Level 4: DFT validation (~hours) — VASP/QE only for top 0.1% finalists
```

Key principle: DFT only for finalists, not for candidates.

### 4. Improve GNN Predictions

Current: 2 properties (formation energy, band gap)
Target: 12+ properties

Priority additions:
1. Thermodynamic stability (above/below hull)
2. Ionic conductivity
3. Electronic conductivity
4. Magnetism (ferro/antiferro/para)
5. Thermal conductivity
6. Catalytic activity descriptors (d-band center)
7. Toxicity score
8. Elemental cost index
9. Crustal abundance score
10. Corrosion resistance

Add uncertainty quantification:
- Ensemble predictions
- MC dropout
- If uncertain → queue for validation, don't claim discovery

### 5. Structure Generation v2

Beyond element substitution. New generators:
- Isovalent substitution (same oxidation state swaps)
- Controlled doping (1-5% dopant concentration)
- Vacancy defects (oxygen/cation vacancies)
- Perovskite template generator (any ABO₃)
- 2D material slicer (exfoliate from bulk)
- Layered material stacker (van der Waals heterostructures)
- High-entropy alloy generator (≥5 elements, equimolar)
- Single-atom catalyst scaffold (metal@support)

### 6. Free/Cheap Computation

Available resources:
- Google Colab (free tier: T4 GPU, 12h sessions)
- Kaggle notebooks (P100 GPU, 30h/week)
- GitHub Actions (2000 min/month free)
- CPU local (current approach, $0)
- Academic cloud credits (Azure/AWS/GCP programs)

Future vision:
- SOST Proof-of-Useful-Computation network
- Volunteer nodes run relaxations/predictions
- Reputation/reward for completed tasks
- Validated results feed back to corpus

## New Modules to Create

| Module | Purpose | Priority |
|--------|---------|----------|
| PGM-Replacement Engine | Find cheap Pt/Pd/Rh substitutes | HIGH |
| Abundance & Cost Score | Penalize rare/toxic/expensive | HIGH |
| Structure Generator v2 | Perovskites, spinels, 2D, HEA | MEDIUM |
| MLIP Validation Layer | CHGNet/M3GNet/MACE pre-DFT | HIGH |
| DFT Budget Manager | Route only top 0.1% to DFT | MEDIUM |
| Multi-Property GNN | 12+ property predictions | HIGH |
| Uncertainty Quantifier | MC dropout / ensemble | MEDIUM |

## Mission Profiles (New Campaigns)

1. **Platinum-free H₂ catalyst** — Fe/N/C, Ni/Mo/S for HER/OER/ORR
2. **Cheap OER catalyst** — Mn/Co/Ni perovskites for water electrolysis
3. **Lithium capture material** — Li-ion sieves, spinel LiMn₂O₄ variants
4. **Desalination membrane** — ceramic/polymer for affordable water treatment
5. **PV without rare elements** — Cu₂ZnSnS₄ (CZTS), perovskite ABX₃ variants
6. **Corrosion-resistant alloys** — for deep mining/GeaSpirit drill targets
7. **Thermal storage material** — phase-change materials for solar thermal
8. **CO₂ capture sorbent** — MOFs, amines on cheap supports

## Success Metrics

| Metric | Current | Target (6 months) | Target (12 months) |
|--------|---------|-------------------|---------------------|
| Corpus size | 76K | 300K+ | 1M+ |
| Properties predicted | 2 | 6+ | 12+ |
| Campaigns | 29 | 40+ | 60+ |
| PGM replacements found | 0 | 10+ | 50+ |
| DFT-validated discoveries | 0 | 5+ | 20+ |
| Compute cost | $0 | $0-50 | $0-200 |
