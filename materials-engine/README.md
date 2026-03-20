# SOST Materials Discovery Engine

> **Current phase: IV.E — Pre-DFT Triage Gate (v1.8.0)**

## What exists (implemented and tested)

### Data Foundation (Phase I)
- **Schema** (`src/schema.py`): Canonical IDs, provenance, structure support, validation
- **4-source ingestion**: MP, AFLOW, COD, JARVIS normalizers
- **Storage** (`src/storage/db.py`): SQLite with upsert, compound search, audit queries
- **API** (`src/api/server.py`): FastAPI with 60 endpoints
- **Audit + Export**: Corpus audit (JSON + Markdown), reproducible ML-ready CSV export

### Corpus (Phase III.C + III.J — 75,993 materials)
- **Source**: JARVIS DFT 3D bulk ingestion (via jarvis-tools)
- **Coverage**: All 75,993 have band_gap, formation_energy, spacegroup
- **Structure coverage**: **100%** — all 75,993 have validated CIF structures (backfilled from JARVIS atoms)
- **ML-ready**: 100% — all have the fields needed for prediction and scoring

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

### Cost-Constrained Execution Mode
- **Current mode**: Prototype ($0/month on existing VPS)
- **Corpus**: 76K materials from open JARVIS database, zero API cost
- **Retrieval**: CPU numpy, no cloud services

## What does NOT exist yet

- Physics-based T/P conditioning (phonon, EOS, CALPHAD) — Phase IV+
- Structural relaxation (M3GNet/CHGNet) — Phase IV+
- Ab-initio validation of generated candidates — Phase IV+
- Blockchain proof-of-discovery — Phase V+

## Quick Start

```bash
cd materials-engine
pip install -r requirements.txt

# Run all tests (602 tests)
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

## Tests (602 total)

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
