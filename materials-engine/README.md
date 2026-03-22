# SOST Materials Discovery Engine

> **Release Candidate: v3.2.0-RC1 — Engine Stabilization (Phase IV.T)**

## What exists (implemented and tested)

### Data Foundation (Phase I)
- **Schema** (`src/schema.py`): Canonical IDs, provenance, structure support, validation
- **4-source ingestion**: MP, AFLOW, COD, JARVIS normalizers
- **Storage** (`src/storage/db.py`): SQLite with upsert, compound search, audit queries
- **API** (`src/api/server.py`): FastAPI with 60 endpoints
- **Audit + Export**: Corpus audit (JSON + Markdown), reproducible ML-ready CSV export

### Corpus (Phase III.C + III.J + IV.I — 76,193 materials)
- **Sources**: JARVIS DFT 3D bulk (75,993) + AFLOW pilot (200)
- **Coverage**: 76,193 with formation_energy, 76,124 with band_gap, all with spacegroup
- **Structure coverage**: **99.74%** — 75,993 have validated CIF structures
- **ML-ready**: 100% of current corpus is training_ready tier
- **Tier distribution**: See Phase IV.J below

### Corpus Tiers (Phase IV.J)
- **training_ready** (76,193 — 100%): Has formation_energy and/or band_gap. Can enter ML training.
- **structure_only** (0 currently): Has crystal structure but no computed properties. COD pilot ready.
- **reference_only**: Formula/composition only. Reference for dedup and coverage mapping.
- **generated_candidate**: Computationally generated. NOT validated. Do NOT train on.
- **external_unlabeled**: External source without computed labels. Search space expansion only.

**Critical rule**: Only `training_ready` tier enters ML training pipelines. Other tiers expand search/reference space only.

### ML Prediction (Phase II → IV.A)
- **Formation energy**: CGCNN on 20K samples — **MAE=0.1528, R²=0.9499** (Phase IV.A)
- **Band gap**: ALIGNN-Lite on 20K samples — **MAE=0.3422, R²=0.707** (Phase IV.B)
- **Training ladder**: 5 rungs (5K→10K→20K→40K→76K) per target — 20K optimal for both
- **`/predict`**: Real GNN inference from CIF input
- **`/similar`**: 104-dim fingerprint similarity

### Novelty Filter + Exotic Candidates (Phase III.A)
- **Novelty**: 104-dim fingerprint, cosine similarity, bands (known/near_known/novel_candidate)
- **Exotic**: Weighted rarity score — all relative to ingested corpus only

### Shortlist Engine + T/P Screening (Phase III.B)
- **Shortlist**: Configurable criteria → filter → rank → decide (accepted/watchlist/rejected)
- **T/P Proxy**: Heuristic risk assessment — NOT physics simulation

### Persistent Fingerprints + Fast Retrieval (Phase III.C)
- **Fingerprint store**: 75,993 precomputed 104-dim vectors in numpy (4.1s build)
- **Retrieval index**: L2-normalized cosine dot-product search (0.019s index build, O(N) per query)
- **Sufficient for <100K materials on CPU** — add ANN index for >100K if needed

### Campaign Mode (Phase III.C)
- **What it is**: Formal, reproducible search campaigns with configurable criteria, T/P conditions, and persistent results
- **5 presets**: exotic_materials, low_formation_energy, band_gap_window, tp_sensitive, high_novelty
- **Custom campaigns**: Any criteria combination via API
- **Persistence**: Each campaign run saved as JSON artifact with full traceability

### Controlled Candidate Generation (Phase III.D)
- **What it is**: Generates plausible material candidates from corpus parents using 3 cheap strategies, then filters novelty-first
- **Strategies**: Element substitution (same-family swap), stoichiometry perturbation (±1 counts), prototype remix (same-SG composition mixing)
- **Pipeline**: Parents → Generate → Sanity → Dedup → Novelty Check → Viability → Scored Output
- **Decisions**: rejected_invalid, rejected_known, rejected_near_known, watchlist_novel, accepted_novel, accepted_exotic
- **NOT ab-initio validated** — candidates are heuristic hypotheses for further screening
- **API**: `POST /generation/run`, `GET /generation/presets`, `POST /generation/check`

### Prototype-Structure Lift + Candidate Evaluation (Phase III.E)
- **What it is**: Takes generated candidates, lifts approximate crystal structures from parent prototypes, then runs real GNN prediction (formation_energy + band_gap)
- **Structure lift**: Element substitution on parent structures produces valid pymatgen Structures. Lift confidence documented (0.4-0.7). Strategies that can't be lifted cleanly are marked `not_liftable`.
- **Real predictions**: Lifted structures are fed through existing CGCNN/ALIGNN-Lite models for actual property prediction
- **Evaluation ranking**: 20% novelty + 15% exotic + 15% plausibility + 25% predicted_fe + 15% target_fit + 10% lift_confidence
- **NOT relaxed structures** — lattice and positions inherited from parent, species swapped
- **API**: `POST /generation/evaluate-run`, `POST /generation/lift-check`, `GET /generation/evaluations/status`

### Material Intelligence Layer
- **What it is**: Comprehensive, auditable technical reports for any material — known or hypothetical
- **Existence classification**: `exact_known_match`, `near_known_match`, `not_found_in_integrated_corpus`
- **Evidence tagging**: Every property labeled `known`, `predicted`, `proxy`, or `unavailable`
- **Application hypotheses**: Rule-based classification (semiconductor, PV, thermoelectric, catalytic, magnetic, structural)
- **Comparison tables**: Multi-parameter comparison vs corpus neighbors
- **Honest**: "Existence assessed relative to integrated corpus only, not all published science"
- **API**: `GET /intelligence/material/{id}`, `POST /intelligence/report`, `POST /intelligence/compare`

### Validation Dossier (Phase III.F)
- **What it is**: Comprehensive validation dossier that combines intelligence report + validation priority + candidate context into one actionable document
- **Validation priority**: high/medium/low/reject based on weighted novelty, exotic, evaluation score, stability, structure quality, and application plausibility
- **Existence status**: `exact_known_match`, `near_known_match`, `not_found_in_integrated_corpus`, `generated_hypothesis`
- **Proxy properties**: thermal_risk_proxy, pressure_sensitivity_proxy, mechanical_rigidity_proxy, phase_transition_risk_proxy
- **Limitations**: Honest list of what the system cannot do — always included
- **API**: `GET /intelligence/status`, `POST /intelligence/dossier/from-evaluation`, `GET /intelligence/dossier/{id}`

### Validation Queue + Learning Loop (Phase III.G)
- **Validation queue**: Persistent, prioritized, dedup-aware queue of candidates awaiting validation
- **Cheap-first ladder**: 6 stages from zero-cost dedup → CPU proxy → DFT → external → learning
- **ROI scoring**: Prioritizes high information value + low cost candidates
- **Feedback memory**: Records prediction vs observation for future model improvement
- **Learning scaffold**: Identifies model failures and promising chemical regions
- **Anti-rework**: Dedup by formula+SG, rejects duplicates before scoring
- **API**: `/validation/queue/*`, `/validation/feedback/*`, `/learning/*`

### Evidence Bridge + Benchmark + Calibration (Phase III.H)
- **Evidence bridge**: Import external evidence (JSON/CSV) — experimental values, literature, manual notes
- **Benchmark suite**: Reproducible prediction accuracy measurement on known corpus materials (FE MAE=0.23, BG MAE=0.42)
- **Confidence calibration**: Empirical error-based confidence bands (high/medium/low) derived from benchmark
- **NOT statistical probability** — empirical error bands only
- **Integrated**: Calibration appears inside dossiers. Evidence auto-links to feedback. Validation queue shows calibrated bands.
- **API**: `/evidence/*`, `/benchmark/*`, `/calibration/*`, `/validation/queue/calibrated`, `/intelligence/material/{id}/calibrated`, `/intelligence/report/calibrated`, `/evidence/feedback-links`

### Real Structure Analytics (Phase III.I)
- **28 physical descriptors** computed from structure geometry + composition
- **Structure-derived** (requires CIF): density, volume, lattice params, bond distances, symmetry, centrosymmetry
- **Composition-derived** (always available): formula weight, element statistics, class fractions
- **Evidence tagging**: `computed_from_structure`, `computed_from_composition`, `proxy`, `unavailable`
- **Integrated into dossier**: `structure_analytics` section with descriptor counts by evidence
- **API**: `GET /analytics/material/{id}`, `POST /analytics/report`
- **Coverage**: **75,993/75,993** materials have CIF structures (100% after Phase III.J backfill)

### Dual-Target Frontier Engine (Phase IV.C)
- **What it is**: Multiobjectve candidate selection combining formation_energy (CGCNN) + band_gap (ALIGNN-Lite) + novelty + exotic + structure quality + validation priority
- **4 profiles**: balanced_frontier, stable_semiconductor, wide_gap_exotic, high_novelty_watchlist
- **Sources**: corpus-only, generated-only, or mixed
- **Evidence propagation**: Every property tagged known/predicted/proxy/unavailable
- **Reason codes**: strong_stability, good_bg_fit, high_novelty, high_exotic, etc.
- **API**: `GET /frontier/presets`, `POST /frontier/run`, `GET /frontier/{id}`

### Real-Source COD Pilot (Phase IV.J)
- **What it is**: Attempted real integration with Crystallography Open Database (COD)
- **COD API status**: Unreachable from current environment (158.129.170.82 — 100% packet loss)
- **Fallback**: Used representative COD entries (real COD IDs, simulated fetch) with real pipeline
- **Result**: 13 unique structures identified, all classified as `structure_only` tier
- **Training impact**: **NONE** — COD has no formation_energy or band_gap data
- **Value**: Structural reference expansion only — improves novelty detection and polymorph comparison
- **Decision**: `pause_cod_keep_as_reference_layer` — wait for real AFLOW or MP API for training data
- **API**: `POST /corpus-sources/cod/pilot/plan`, `POST /corpus-sources/cod/pilot/run`, `GET /corpus-sources/cod/recommendation`
- **Tier API**: `GET /corpus-sources/tiers/status`, `GET /corpus-sources/tiers/summary`

### Hard-Case Mining + Selective Retraining Datasets (Phase IV.K)
- **What it is**: Analyzes model weaknesses using calibration data, mines hard cases, builds focused retraining datasets
- **Hard-case mining**: Classified 76,124 BG materials: 69.87% easy, 23.16% medium, 6.32% hard, 0.65% high-value retrain
- **FE model is strong**: 97.58% easy, only 2.42% medium — low priority for retraining
- **BG weakest buckets**: 3-6 eV (MAE=1.12, LOW), 1-3 eV (MAE=0.87, MEDIUM)
- **6 selective datasets prepared** (NOT trained):
  - `bg_sparse_exotic_10k` (rank #1, score 0.713) — 4+ element materials with BG
  - `bg_hotspots_10k` (rank #2, score 0.657) — materials in hard calibration regions
  - `bg_balanced_hardmix_20k` (rank #3, score 0.603) — combined difficulty signals
  - `fe_sparse_mix_10k` (rank #4, score 0.591) — complex FE materials
  - `curriculum_easy_to_hard_20k` (rank #5) — progressive difficulty BG
  - `fe_hardcases_10k` (rank #6, deferred) — FE model already strong
- **Recommendation**: `retrain_band_gap_hotspots_next` using sparse exotic dataset on rung_20k
- **Status**: Datasets PREPARED. Training NOT executed. Models unchanged.
- **API**: `GET /retraining-prep/status`, `GET /retraining-prep/hardcases`, `POST /retraining-prep/datasets/build`, `GET /retraining-prep/recommendation`

### Selective Band Gap Retraining (Phase IV.L)
- **What it is**: Trained 3 ALIGNN-Lite challengers on selective datasets, compared vs production
- **Challengers trained** (REAL, not simulated):
  - `bg_hotspots_10k`: MAE=0.6374, R²=0.5977 (9,921 materials, 978s)
  - `bg_sparse_exotic_10k`: MAE=0.5926, R²=0.7336 (9,953 materials, 992s)
  - `bg_balanced_hardmix_20k`: MAE=0.6991, R²=0.6745 (19,885 materials, 1917s)
- **Production**: ALIGNN-Lite 20K random sample: MAE=0.3422, R²=0.707
- **Decision: HOLD** — No challenger beat production. All challengers worse by +0.25 to +0.36 MAE
- **Root cause**: Training only on hard/exotic subsets excludes the metal/narrow-gap majority (~70% of corpus). The model never learns the easy baseline, so overall accuracy drops.
- **Lesson**: Selective subsets alone do NOT improve overall MAE. Next approach should use stratified sampling or curriculum learning that includes all BG ranges.
- **Production model UNCHANGED**: ALIGNN-Lite 20K (MAE=0.3422) remains in production
- **API**: `GET /selective-retraining/band-gap/status`, `GET /selective-retraining/band-gap/challengers`, `GET /selective-retraining/band-gap/comparison`, `GET /selective-retraining/band-gap/decision`

### Stratified/Curriculum Band Gap Retraining (Phase IV.M)
- **What it is**: Trained 3 challengers using stratified/curriculum strategies to fix IV.L's pure-subset failure
- **Challengers trained** (REAL, ~98 min total):
  - `bg_stratified_20k` (50% random + 30% hard + 20% exotic): MAE=0.6547, R²=0.6437
  - `bg_curriculum_20k` (phase1 random → phase2 hard finetune): MAE=0.6287, R²=0.4697
  - `bg_stratified_balanced_30k` (6-stratum mix, 27K materials): MAE=0.6771, R²=0.6273
- **Production still wins**: ALIGNN-Lite 20K random: MAE=0.3422, R²=0.707
- **Decision: HOLD** — stratified/curriculum challengers still worse than random baseline
- **Deep lesson**: The production model's random 20K sample is naturally well-distributed because band_gap=0 (metals) dominates 70% of the corpus. Any reweighting toward hard cases distorts this distribution, and the model struggles to learn the dominant pattern. The ALIGNN-Lite architecture at 15 epochs cannot compensate.
- **Implication**: Improving BG MAE beyond 0.34 likely requires architectural changes (deeper model, more epochs, or explicit multi-head approach for metals vs insulators), not just data selection.
- **API**: `GET /stratified-retraining/band-gap/status`, `/challengers`, `/comparison`, `/decision`

### Hierarchical Band Gap Modeling (Phase IV.N)
- **What it is**: Metal gate classifier + non-metal regressor pipeline to handle the 70/30 metal/non-metal imbalance
- **Metal gate (CGCNN)**: Accuracy=90.8%, F1_metal=0.94, F1_nonmetal=0.81 (1,421s training)
- **Non-metal regressor (ALIGNN-Lite)**: MAE=0.7609, R²=0.6378 on 19,879 non-metal materials (1,847s)
- **Combined pipeline MAE: 0.2793** vs production 0.3422 — **18.4% improvement**
- **Bucket results**: Metals massively improved (0.3154→0.0048), wide-gap improved (1.12→0.91)
- **Regression**: Narrow-gap 0.05-1.0 eV regressed (+0.40 MAE) — gate misclassifications hurt this range
- **Decision: WATCHLIST** — clear overall improvement but narrow-gap regression needs fixing
- **Next step**: Improve gate recall for narrow-gap semiconductors, or add 3rd tier for narrow-gap
- **Production model UNCHANGED** pending regression fix
- **API**: `GET /hierarchical-band-gap/status`, `/gate`, `/regressor`, `/comparison`, `/decision`

### Gate Calibration + Borderline Routing (Phase IV.O)
- **What it is**: Calibrate IV.N's metal gate threshold and routing to fix narrow-gap regression
- **Threshold sweep**: 10 thresholds (0.25-0.70), evaluated on 4,000 test materials with real gate model
- **Routing policies**: original, conservative, borderline_to_regressor, three_zone — 11 configurations tested
- **Best calibrated MAE: 0.2187** (36.1% improvement over production 0.3422)
- **Key finding**: Gate threshold tuning is NOT the bottleneck. Even with zero FN (all non-metals correctly routed), the regressor's MAE=0.76 on non-metals still causes narrow-gap regression (0.60 vs prod 0.51)
- **Decision: WATCHLIST** — overall improvement proven but narrow-gap regression from regressor quality
- **Root cause shift**: The problem moved from gate misclassification → regressor accuracy on non-metals
- **Next step**: Retrain the non-metal regressor specifically (not the gate) to reduce its MAE below 0.50
- **Production model UNCHANGED** (ALIGNN-Lite 20K, MAE=0.3422)
- **API**: `GET /hierarchical-band-gap-calibration/status`, `/thresholds`, `/routing`, `/comparison`, `/decision`

### Non-Metal Regressor Improvement (Phase IV.P)
- **What it is**: Improve the non-metal regressor (IV.O identified it as the single remaining blocker)
- **3 challengers trained** (REAL, ~162 min total):
  - `nonmetal_longer_train` (25ep, lr=0.005): MAE=0.7369 (Δ-0.024 vs v1)
  - `nonmetal_lower_lr` (20ep, lr=0.002): **MAE=0.6654** (Δ-0.096 vs v1, **best**)
  - `nonmetal_longer_lower_lr` (30ep, lr=0.002): MAE=0.6679 (overfits after ep10)
- **Key finding**: Lower learning rate (0.002 vs 0.005) is the main driver. More epochs has diminishing returns.
- **Best pipeline MAE: 0.2568** (25.0% improvement over production 0.3422)
- **Regressor progression**: 0.7609 (v1) → 0.6654 (v2) = **12.5% improvement**
- **Decision: WATCHLIST** — overall improvement strong, narrow-gap bucket projection still elevated
- **Note**: Bucket MAE projections are conservative estimates, not direct measurements. The actual narrow-gap performance may be better than projected.
- **Production model UNCHANGED** (ALIGNN-Lite 20K, MAE=0.3422)
- **API**: `GET /hierarchical-band-gap-regressor/status`, `/challengers`, `/comparison`, `/decision`

### Final Hierarchical Promotion Benchmark (Phase IV.Q)
- **What it is**: Direct, definitive benchmark comparing production vs hierarchical on 2,000 real test materials
- **Key difference from previous phases**: ALL bucket MAE measured directly, not projected
- **Results** (DIRECT measurement on 2,000 materials):

| Pipeline | Overall MAE | Metals | Narrow-gap | Wide-gap |
|----------|------------|--------|-----------|----------|
| Production | 0.3407 | 0.1907 | **0.5135** | 0.8682 |
| Hierarchical V2 | **0.2628** | **0.0892** | 0.6495 | **0.8116** |
| Delta | **-0.0779 (-22.9%)** | **-0.1015** | **+0.1360** | **-0.0566** |

- **Scorecard**: Overall PASS, metals PASS, wide-gap PASS, **narrow-gap FAIL** (+0.136 > +0.10 tolerance)
- **Decision: HOLD_SINGLE_STAGE_BG** — narrow-gap regression (0.514→0.650) blocks promotion
- **Root cause**: Gate sends ~20% of narrow-gap semiconductors to BG=0 (false negatives)
- **Production model UNCHANGED**: ALIGNN-Lite 20K (MAE=0.3422) remains
- **Total BG effort**: IV.L→IV.Q = 7 phases, 17+ real models, 1 definitive benchmark
- **Conclusion**: Hierarchical IS architecturally superior overall, but needs better gate recall for 0.05-1.0 eV materials before promotion
- **API**: `GET /hierarchical-band-gap-final/status`, `/benchmark`, `/scorecard`, `/decision`

### Narrow-Gap Rescue / Three-Tier Pipeline (Phase IV.R)
- **What it is**: Dedicated narrow-gap specialist (0.05-1.0 eV) as 3rd tier to fix the single remaining blocker
- **Specialist trained**: ALIGNN-Lite on 7,618 narrow-gap materials, MAE=0.2221 (vs 0.6495 from general regressor)
- **3-tier pipeline**: gate → narrow specialist OR general regressor

| Pipeline | Overall MAE | Metals | Narrow-gap | Wide-gap |
|----------|------------|--------|-----------|----------|
| Production | 0.3407 | 0.1907 | **0.5135** | 0.8682 |
| 2-Tier | 0.2628 | 0.0892 | 0.6495 | 0.8116 |
| **3-Tier** | **0.2596** | **0.0860** | 0.6187 | **0.8116** |

- **Scorecard**: Overall PASS (-23.8%), metals PASS, wide-gap PASS, **narrow-gap FAIL** (+0.1052, exceeds +0.10)
- **Root cause**: Only 48/142 narrow-gap materials reached the specialist — rest were FN'd by gate
- **Decision: HOLD** — specialist works but gate FN rate limits its impact
- **Honest conclusion**: The gate FN for borderline semiconductors is the irreducible bottleneck. Fixing it requires retraining the gate with better narrow-gap training data or a softer threshold.
- **Production model UNCHANGED**: ALIGNN-Lite 20K (MAE=0.3422)
- **API**: `GET /three-tier-band-gap/status`, `/specialist`, `/pipeline`, `/scorecard`, `/decision`

### Gate Recall Rescue (Phase IV.S)
- **What it is**: Retrained gate with oversampled narrow-gap (8K metal + 6K narrow + 6K wide) at threshold=0.35
- **Gate improvement**: Narrow-gap reaching specialist: 48/142 → **135/142** (95% routing)
- **Key result** (direct benchmark, 2000 materials):

| Pipeline | MAE | Metals | Narrow | Medium | Wide | Ultra |
|----------|-----|--------|--------|--------|------|-------|
| Production | 0.3407 | **0.1907** | 0.5135 | 0.7950 | 0.8682 | 1.6707 |
| Rescued 3-Tier | 0.3419 | 0.2506 | 0.5963 | **0.5519** | **0.6581** | **0.7725** |

- **Scorecard**: Narrow-gap PASS (+0.08), Wide-gap PASS (-0.21), **Metals FAIL** (+0.06 > +0.05)
- **Decision: HOLD** — lower gate threshold trades metals accuracy for better routing
- **Insight**: Gate threshold is a tradeoff slider. 0.50→metals win, 0.35→routing wins. The optimal balance likely needs a threshold-per-region approach or a continuous-output gate (no binary cutoff).
- **Medium+wide-gap dramatically improved**: 0.795→0.552 and 0.868→0.658
- **Production UNCHANGED**: ALIGNN-Lite 20K (MAE=0.3422)
- **API**: `GET /gate-recall-rescue/status`, `/challengers`, `/thresholds`, `/benchmark`, `/decision`

### Engine Stabilization + Release Candidate (Phase IV.T)
- **Release**: v3.2.0-RC1 — engine stabilization, no new experiments
- **Production freeze**: FE (CGCNN, MAE=0.1528) + BG (ALIGNN-Lite, MAE=0.3422) — locked
- **API audit**: 145 endpoints (105 production, 40 research)
- **Corpus**: 76,193 materials, 89 elements, 213 spacegroups
- **Artifacts**: 33 organized directories with full audit trail
- **Tests**: 41 test files
- **Research watchlist**: Hierarchical BG (MAE=0.2596, 24% better but narrow-gap blocks promotion)
- **API**: `GET /release/status`, `/manifest`, `/api-audit`, `/production-freeze`

### Cost-Constrained Execution Mode
- **Current mode**: Prototype ($0/month on existing VPS)
- **Corpus**: 76K materials from open JARVIS + AFLOW databases, zero API cost
- **Retrieval**: CPU numpy, no cloud services

## What does NOT exist yet

- Physics-based T/P conditioning (phonon, EOS, CALPHAD) — Phase IV+
- Structural relaxation (M3GNet/CHGNet) — Phase IV+
- Ab-initio validation of generated candidates — Phase IV+
- Real AFLOW/MP API integration (APIs unreachable from current env)
- Blockchain proof-of-discovery — Phase V+
- Retraining on expanded corpus — blocked until labeled data from DFT sources available

## Quick Start

```bash
cd materials-engine
pip install -r requirements.txt

# Run all tests (909 tests)
pytest tests/ -v

# Start API (http://localhost:8000/docs)
python -m src.api.server

# Run a campaign
curl -X POST http://localhost:8000/campaigns/run \
  -H "Content-Type: application/json" \
  -d '{"name": "My Search", "campaign_type": "exotic_hunt", "top_k": 10}'

# See campaign presets
curl http://localhost:8000/campaigns/presets

# Similar material search
curl -X POST http://localhost:8000/similar/search \
  -H "Content-Type: application/json" \
  -d '{"formula": "Fe2O3", "elements": ["Fe", "O"], "spacegroup": 167, "top_k": 5}'

# Generate exotic material candidates
curl -X POST http://localhost:8000/generation/run \
  -H "Content-Type: application/json" \
  -d '{"strategy": "mixed", "max_parents": 50, "max_candidates": 100}'

# Check a candidate against corpus
curl -X POST http://localhost:8000/generation/check \
  -H "Content-Type: application/json" \
  -d '{"formula": "BaCuTe", "elements": ["Ba", "Cu", "Te"]}'

# See generation presets
curl http://localhost:8000/generation/presets
```

## API Endpoints (30 total)

| Method | Path | Status |
|--------|------|--------|
| GET | /status | Production |
| GET | /health | Production |
| GET | /stats | Production |
| GET | /materials | Production |
| GET | /materials/{id} | Production |
| GET | /materials/{id}/structure-status | Production |
| GET | /search | Production |
| GET | /audit/summary | Production |
| POST | /predict | Baseline ML |
| GET | /similar/{id} | Baseline |
| GET | /novelty/{id} | Production |
| POST | /novelty/check | Production |
| GET | /candidates/exotic | Production |
| POST | /candidates/exotic/rank | Production |
| GET | /shortlist/default-criteria | Production |
| POST | /shortlist/build | Production |
| POST | /screening/thermo-pressure | Production |
| POST | /screening/thermo-pressure/batch | Production |
| GET | /campaigns/presets | Production |
| POST | /campaigns/run | Production |
| GET | /campaigns/{id} | Production |
| GET | /retrieval/status | Production |
| POST | /similar/search | Production |
| GET | /generation/presets | Production |
| GET | /generation/status | Production |
| POST | /generation/run | Production |
| GET | /generation/{id} | Production |
| POST | /generation/check | Production |
| POST | /generation/evaluate-run | Production |
| GET | /generation/evaluations/status | Production |
| GET | /generation/evaluation/{id} | Production |
| POST | /generation/lift-check | Production |
| GET | /intelligence/{id} | Production |
| POST | /intelligence/report | Production |
| POST | /intelligence/compare | Production |
| GET | /intelligence/status | Production |
| POST | /intelligence/dossier/from-evaluation | Production |
| GET | /intelligence/dossier/{id} | Production |

## Tests (714 total)

| File | Tests | Coverage |
|------|-------|----------|
| test_schema.py | 12 | ID, validation, serialization |
| test_normalizer.py | 9 | MP, AFLOW, COD, JARVIS, provenance |
| test_chemistry.py | 8 | pymatgen parsing, edge cases |
| test_structure.py | 12 | CIF validation, loading, hashing |
| test_db.py | 10 | CRUD, upsert, compound search |
| test_api.py | 12 | All endpoints, errors |
| test_models.py | 7 | CGCNN, ALIGNN, registry, prediction |
| test_audit.py | 2 | Audit counts, artifact generation |
| test_export.py | 4 | Export, manifest, reproducibility |
| test_thermo.py | 27 | Conditions, validation, screening, API |
| test_novelty.py | 60 | Fingerprints, scoring, filter, exotic, API |
| test_shortlist.py | 63 | Criteria, ranking, T/P proxy, engine, API |
| test_campaigns.py | 43 | FP store, retrieval, campaigns, presets, API |
| test_generation.py | 43 | Rules, spec, engine, novelty-first, API |
| test_evaluation.py | 26 | Structure lift, evaluator, ranking, API |
| test_intelligence.py | 34 | Evidence, applications, comparison, reports, API |
| test_dossier.py | 32 | Dossier build, evidence, priority, persistence, API |
| test_validation_learning.py | 35 | Queue, feedback, learning, dedup, API |
| test_cod_tiers.py | 46 | Tier classification, COD pilot, dedup, value report, API |
| test_retraining_prep.py | 37 | Hard-case mining, difficulty tiers, datasets, priority, API |
| test_selective_retraining.py | 21 | Challenger comparison, promotion rules, bucket analysis, API |
| test_stratified_retraining.py | 22 | Stratified sampler, curriculum, comparison, promotion, API |
| test_hierarchical_bandgap.py | 20 | Metal gate, regressor, pipeline, promotion rules, API |
| test_gate_calibration.py | 22 | Threshold sweep, routing policies, calibration, API |
| test_regressor_improvement.py | 18 | Regressor challengers, pipeline comparison, promotion, API |
| test_final_benchmark.py | 16 | Final benchmark, scorecard, promotion decision, registry, API |
| test_three_tier.py | 18 | Three-tier pipeline, narrow-gap specialist, scorecard, API |
| test_gate_recall_rescue.py | 9 | Gate recall, oversampling, threshold selection, API |
| test_release.py | 12 | Release manifest, production freeze, API audit, endpoints |
