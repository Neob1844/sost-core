# SOST Materials Discovery Engine — Strategic Plan

> **Document status: OPERATIONALLY ACCEPTED — v3.2.0-RC1 (Phase IV.U)**
> Last updated: 2026-03-22

---

## 1. Current Implementation Status

### Operational (tested, deployed)

| Component | Status | Details |
|-----------|--------|---------|
| Schema + canonical IDs | Production | SHA256-based dedup, provenance tracking |
| 4-source ingestion | Production | MP, AFLOW, COD, JARVIS normalizers |
| Structure validation | Production | pymatgen CIF + JARVIS atoms adapter |
| SQLite storage | Production | Upsert, compound search, audit queries |
| FastAPI (25 endpoints) | Production | /predict, /similar, /novelty, /exotic, /shortlist, /screening, /campaigns, /retrieval |
| Corpus (JARVIS) | Production | 75,993 materials, all with band_gap + formation_energy |
| Fingerprint store | Production | 75,993 precomputed 104-dim vectors, numpy-backed |
| Retrieval index | Production | L2-normalized cosine search, <100K CPU-friendly |
| Campaign mode | Production | 5 presets + custom, persistent results |
| Candidate generation | Production (Phase III.D) | 3 strategies, novelty-first pipeline, 4 presets |
| Structure lift + evaluation | Production (Phase III.E) | Prototype lift, real GNN prediction, ranked output |
| Material Intelligence Layer | Production | Comprehensive reports, evidence tagging, applications, comparison |
| CGCNN model | Baseline | 2000 samples, formation_energy R²=0.934 |
| ALIGNN-Lite model | Baseline | 2000 samples, formation_energy R²=0.930 |
| Similarity search | Baseline | 104-dim structural fingerprint, cosine |
| Data export | Production | Reproducible CSV + manifests |
| Corpus audit | Production | JSON + Markdown reports |

### Baseline / Experimental

| Component | Status | Details |
|-----------|--------|---------|
| Band gap prediction | Baseline | MAE=0.40 eV (ALIGNN-Lite), needs more data |
| Formation energy prediction | Strong baseline | MAE=0.23 eV/atom (ALIGNN-Lite) |
| Thermo-Pressure screening | Experimental proxy (Phase III.B) | Heuristic risk assessment, crystal-system + symmetry-based |
| Novelty filter | Production (Phase III.A) | 104-dim fingerprint, cosine similarity, bands |
| Exotic candidate ranking | Production (Phase III.A) | Weighted score: novelty + rarity + sparsity |
| Shortlist engine | Production (Phase III.B) | Configurable criteria, ranked decisions, T/P integration |
| Cost-constrained mode | Documented (Phase II.8) | Strategy formalized, not enforced in code |

### Planned (not yet implemented)

| Component | Target Phase | Notes |
|-----------|-------------|-------|
| Phonon stability (T-aware) | Phase III | Requires phonopy or ML surrogate |
| Equation of state (P-aware) | Phase III | Birch-Murnaghan / ML-EOS |
| Phase diagram integration | Phase IV | CALPHAD / thermodynamic databases |
| Relaxation (M3GNet/CHGNet) | Phase III | Structural optimization |
| Novelty-first exotic ranking | Phase III | Beyond similarity — true novelty scoring |
| Digital Twin Materials Lab | Phase IV+ | Full lifecycle simulation |
| Blockchain proof-of-discovery | Phase V+ | SOST token integration |

---

## 2. Vision

Build a zero-cost-first materials discovery engine that predicts properties of crystalline materials, screens them under thermodynamic conditions, and surfaces novel candidates — all running on open data, open models, and CPU-first infrastructure.

**Not a goal (yet):** DFT computation, experimental validation, generative design, or marketplace features.

---

## 3. Data Foundation (Phase I — Complete)

### Sources
- **Materials Project (MP)**: DFT-computed properties, API-gated
- **AFLOW**: Autonomous computational framework, REST API
- **COD**: Crystallography Open Database, no key needed
- **JARVIS-DFT**: NIST curated DFT data, bulk download

### Corpus
- 2000 JARVIS materials ingested (current working set)
- All with valid crystal structures
- All with band_gap + formation_energy
- Canonical schema with SHA256 dedup

---

## 4. Proposed Architecture

### 4.1 ML Prediction Pipeline (Phase II — Operational)

```
CIF/Structure → pymatgen → Crystal Graph → GNN (CGCNN/ALIGNN-Lite) → Property
```

- Single-sample inference (no batching requirement)
- LayerNorm (not BatchNorm) for single-sample compatibility
- Model registry with MAE/RMSE/R² tracking
- Automatic best-model selection per target

### 4.2 Thermo-Pressure Screening (Phase II.8 — Scaffold)

**Purpose:** Evaluate material predictions in the context of real operating conditions (temperature and pressure), enabling screening for stability, phase transitions, and operational suitability.

**Input contract:**
```json
{
  "cif": "<CIF text>",
  "target": "formation_energy",
  "temperature_K": 1200.0,
  "pressure_GPa": 10.0
}
```

Optional range parameters for sweep screening:
- `temperature_min_K`, `temperature_max_K`
- `pressure_min_GPa`, `pressure_max_GPa`

**Output contract:**
```json
{
  "prediction": -1.234,
  "target": "formation_energy",
  "model": "alignn_lite",
  "screening": {
    "conditions": {"temperature_K": 1200.0, "pressure_GPa": 10.0},
    "base_prediction": -1.234,
    "base_target": "formation_energy",
    "base_model": "alignn_lite",
    "stability_flag": "unknown",
    "phase_transition_risk": "unknown",
    "reliability": "experimental_scaffold",
    "note": "Real T/P-conditioned prediction not yet implemented..."
  }
}
```

**What it provides (Phase II.8):**
- Validated condition objects with physical bounds
- Standard presets (ambient, high-T, high-P, extreme)
- API hook: `/predict` accepts `temperature_K` and `pressure_GPa`
- Honest tagging: every result declares its reliability level
- Serialization for storage/audit trail

**What it does NOT provide (yet):**
- Phonon-based thermal stability calculation
- Equation of state / pressure-volume response
- Phase transition detection
- T/P-conditioned property correction
- Experimental validation

**Reliability levels:**
- `baseline_model` — ambient prediction from trained GNN
- `experimental_scaffold` — conditions accepted but no real T/P engine
- `phonon_validated` — (Phase III) stability confirmed via phonon analysis
- `eos_corrected` — (Phase III) pressure response via EOS fitting
- `phase_aware` — (Phase IV) checked against phase diagram

**Honest status:** Phase II.8 provides the contract, validation, and API surface. Real thermodynamic conditioning begins in Phase III with phonon calculations and EOS fitting.

### 4.3 Cost-Constrained Execution Mode

**Principle:** The materials engine operates at near-zero cost until revenue justifies scaling. Every architectural decision defaults to the cheapest option that delivers value.

#### Mode 1: Prototype / Near-Zero-Cost (Current)

| Resource | Strategy |
|----------|----------|
| Data | Open databases only (JARVIS, COD, AFLOW, MP-free-tier) |
| Models | Self-trained CGCNN/ALIGNN-Lite on CPU |
| Compute | Single CPU server, no GPU |
| Storage | SQLite, local filesystem |
| Inference | Synchronous, single-request |
| Training | Small datasets (2K-10K), 15-40 epochs |
| Dependencies | Open-source only (PyTorch CPU, pymatgen, FastAPI) |

**Cost: ~$0/month** (runs on existing VPS)

#### Mode 2: Validation (When early users exist)

| Resource | Strategy |
|----------|----------|
| Data | Expand to 50K+ materials, multi-source |
| Models | Fine-tune on larger datasets, ensemble |
| Compute | CPU primary + GPU burst (pay-per-hour spot instances) |
| Storage | PostgreSQL, S3 for artifacts |
| Inference | Queue-based for heavy predictions |
| Training | Fine-tune existing weights, not from scratch |

**Cost: ~$20-50/month** (spot GPU bursts only when retraining)

#### Mode 3: Full-Scale Production (Revenue-funded)

| Resource | Strategy |
|----------|----------|
| Data | 500K+ materials, proprietary + experimental |
| Models | Multi-task, multi-fidelity, T/P-aware |
| Compute | Dedicated GPU for inference, auto-scaling |
| Storage | Distributed DB, model versioning |
| Inference | Real-time + batch screening pipelines |
| Training | Full ALIGNN, GNoME-scale, periodic retraining |

**Cost: Revenue-justified** (never before)

#### Cost Principles (immutable)

1. **Open data first.** Never pay for data that exists free.
2. **Fine-tune, don't retrain.** Transfer learning over training from scratch.
3. **CPU until proven insufficient.** GPU only when CPU cannot deliver acceptable latency.
4. **No always-on cloud before revenue.** Spot/burst compute only.
5. **Local before cloud.** SQLite before PostgreSQL. Filesystem before S3.
6. **Ship before optimize.** Working > fast > pretty.

### 4.4 Novelty Filter + Exotic Candidate Layer (Phase III.A — Operational)

**Purpose:** Detect whether a material is already known, near-duplicate, or genuinely novel relative to the ingested corpus. Rank materials by how exotic/unexplored they are.

**Important:** "Novel" means "not seen in this corpus" — not "never theorized in science". "Exotic" means "rare/unexplored" — not "better" or "useful".

**Fingerprint (104-dim):**
- 94-dim: element frequency (normalized to sum=1)
- 10-dim: spacegroup/230, a/20, b/20, c/20, alpha/180, beta/180, gamma/180, nsites/50, band_gap/10, (formation_energy+5)/10

**Novelty scoring:**
- `novelty_score = 1.0 - max_cosine_similarity(material, corpus)`
- Bands: `known` (exact match or sim>0.98), `near_known` (sim>0.85), `novel_candidate` (sim<=0.85)

**Exotic scoring (weighted, 0-1):**
- 40% novelty_score
- 20% element_rarity (IDF of elements in corpus)
- 15% structure_rarity (IDF of spacegroup in corpus)
- 25% neighbor_sparsity (1 - mean_similarity_to_top_5)

**Reason codes:** `exact_formula_and_structure_match`, `high_composition_similarity`, `high_structure_similarity`, `low_neighbor_density`, `outlier_candidate`

### 4.5 Shortlist Engine (Phase III.B — Operational)

**Purpose:** Configurable candidate selection pipeline that integrates all scoring layers into ranked, reproducible shortlists.

**Pipeline:**
```
Corpus / Materials → Hard Filters → Scoring → T/P Proxy → Ranking → Decisions
```

**Hard filters (reject):** require_valid_structure, require_properties, max_formation_energy, novelty_min

**Scoring (4 components, configurable weights):**
- Novelty (default 25%): from NoveltyFilter
- Exotic (default 25%): from ExoticResult
- Stability (default 30%): sigmoid mapping of formation_energy
- Property fit (default 20%): distance to band_gap target

**Decision bands:**
- `accepted` — shortlist_score >= 0.35
- `watchlist` — shortlist_score >= 0.15
- `rejected` — below threshold or hard filter

**T/P integration:** If conditions provided, applies heuristic proxy screening and annotates each candidate with screening_reliability.

### 4.6 T/P Experimental Proxy Screening (Phase III.B — Operational)

**Purpose:** Cheap, reproducible risk assessment under T/P conditions.

**Method: heuristic_proxy** — NOT physics simulation:
- Crystal-system thermal sensitivity (cubic=0.2, triclinic=0.6)
- Symmetry-based pressure resilience (high-SG cubic tolerates more pressure)
- Condition severity scaling

**Output:**
- `risk_level`: low / medium / high
- `stability_flag`: assumed_stable / caution / high_risk
- `phase_transition_risk`: low / medium / high / unknown
- `property_drift_risk`: low / medium / high
- `operating_window_hint`: human-readable note
- `method`: always "heuristic_proxy"
- `reliability`: baseline_ambient / experimental_proxy

**Honest limitations:** Cannot predict specific failure temperatures, confirm phase transitions, or compute properties under pressure. Phase IV+ will add phonon/EOS/CALPHAD.

### 4.7 Similarity Search (Phase II — Operational)

104-dimensional structural fingerprint:
- 94-dim: element frequency (composition)
- 10-dim: spacegroup, lattice params (a,b,c,α,β,γ), nsites, band_gap, formation_energy

Cosine similarity, brute-force scan (sufficient for <50K materials).

---

## 5. Roadmap

### Phase I — Data Foundation ✅
- 4-source ingestion pipeline
- Canonical schema with provenance
- Structure validation + SHA256 hashing
- SQLite storage with compound search
- FastAPI with search/audit/export
- 65+ tests passing

### Phase II — Baseline ML ✅
- CGCNN + ALIGNN-Lite models
- /predict endpoint with real GNN inference
- /similar endpoint with structural fingerprints
- Model registry with metrics tracking

### Phase II.5 — ALIGNN + Better Similarity ✅
- ALIGNN-Lite outperforms CGCNN on formation_energy
- 104-dim structural fingerprint (composition + lattice + properties)

### Phase II.75 — Data Scale ✅
- 2000 JARVIS materials (all with valid structures)
- 4 models retrained on full dataset
- Formation energy R²=0.93, band gap R²=0.71

### Phase II.8 — Thermo-Pressure + Cost-Constrained Hardening ✅
- T/P condition contract and validation
- API hooks: /predict accepts temperature_K, pressure_GPa
- Screening scaffold with honest reliability tagging
- Cost-constrained execution mode formalized
- Storage/reporting prepared for T/P metadata

### Phase III.A — Novelty Filter + Exotic Candidate Layer ✅
- 104-dim fingerprint: 94 compositional + 10 structural
- Novelty scoring: 0-1 scale, cosine-similarity-based
- Novelty bands: known / near_known / novel_candidate
- Exotic scoring: weighted combination of novelty, element rarity, structural rarity, neighbor sparsity
- 4 new API endpoints
- 60 dedicated tests

### Phase III.B — Shortlist Engine + T/P Experimental Screening (Current) ✅
- Shortlist engine: configurable criteria → hard filters → scoring → ranking → decisions
- Decision bands: accepted / watchlist / rejected
- T/P proxy screening: crystal-system thermal sensitivity + symmetry-based pressure heuristic
- Reliability levels: baseline_ambient / experimental_proxy / not_available
- 4 new API endpoints: /shortlist/build, /shortlist/default-criteria, /screening/thermo-pressure, /screening/thermo-pressure/batch
- Strategy: shortlist-first, then validate top candidates with heavier methods
- 63 dedicated tests + all existing 161 tests passing (224 total)

### Phase III.C — Corpus Scale + Fast Retrieval + Campaign Mode (Current) ✅
- Corpus scaled from 2,000 → 75,993 materials (JARVIS DFT 3D bulk)
- Persistent fingerprint store: 75,993 vectors, build in 4.1s
- Fast retrieval index: L2-normalized cosine dot-product, index build 0.019s
- Campaign mode: 5 presets + custom, reproducible, persistent
- 5 new API endpoints: /campaigns/presets, /campaigns/run, /campaigns/{id}, /retrieval/status, /similar/search
- 43 dedicated tests + all existing 224 tests passing (267 total)

### Phase III.D — Controlled Candidate Generation + Novelty-First Filtering (Current) ✅
- 3 generation strategies: element substitution, stoichiometry perturbation, prototype remix
- Novelty-first pipeline: generate → sanity → dedup → novelty check → viability → scored output
- Decisions: rejected_invalid/known/near_known, watchlist_novel, accepted_novel/exotic
- Plausibility scoring: element count, family membership, spacegroup, parent traceability
- 4 presets: exotic_search, stable_search, band_gap_search, tp_sensitive_search
- 5 new API endpoints: /generation/presets, /generation/status, /generation/run, /generation/{id}, /generation/check
- 43 dedicated tests + all existing 267 tests passing (310 total)
- On 76K corpus: exotic_search produces 51 accepted_exotic + 153 accepted_novel in 2.2s

### Phase III.E — Prototype-Structure Lift + Candidate Evaluation (Current) ✅
- Structure lift: parent prototype → element substitution → valid pymatgen Structure
- Lift confidence: 0.7 for clean substitution, 0.5 for prototype remix, 0.4 for stoichiometry proxy
- Real GNN prediction on lifted structures (formation_energy + band_gap)
- Evaluation ranking: novelty + exotic + plausibility + predicted_fe + target_fit + lift_confidence
- Decision bands: accepted_for_validation, accepted_for_watchlist, watchlist_only, rejected
- 4 new API endpoints: evaluate-run, evaluations/status, evaluation/{id}, lift-check
- On real corpus: 95% lift rate, 23 accepted for validation from 100 candidates, 4.4s
- 26 dedicated tests + all existing 310 tests passing (336 total)

### Material Intelligence Layer (Current) ✅
- Comprehensive, honest, auditable material reports
- Existence: exact_known_match, near_known_match, not_found_in_integrated_corpus
- Evidence tagging: known/predicted/proxy/unavailable for every property
- Application classification: semiconductor, PV, thermoelectric, catalytic, magnetic, structural
- Comparison tables: multi-parameter vs corpus neighbors
- 3 new API endpoints: /intelligence/{id}, /intelligence/report, /intelligence/compare
- 34 dedicated tests + all existing 336 tests (370 total)

### Phase III.F — Material Intelligence + Validation Dossier (Current) ✅
- Validation Dossier: comprehensive, actionable document for any material or candidate
- Existence: exact_known_match, near_known_match, not_found_in_integrated_corpus, generated_hypothesis
- Validation priority: high/medium/low with weighted rationale and reason codes
- Proxy properties: thermal_risk, pressure_sensitivity, mechanical_rigidity, phase_transition_risk
- Integration with evaluated candidates: dossier from evaluation pipeline
- Honest limitations always included
- 3 new API endpoints: /intelligence/status, /intelligence/dossier/from-evaluation, /intelligence/dossier/{id}
- 32 dedicated tests + all existing 370 tests (402 total)
- Version bumped to 1.0.0

### Phase III.G — Validation Queue + Learning Loop Scaffold (Current) ✅
- Validation queue: persistent, prioritized, dedup-aware
- Cheap-first ladder: 6 stages (dedup → novelty → proxy → DFT → external → learning)
- ROI scoring: favors high info value + low cost
- Feedback memory: records predictions vs observations
- Learning scaffold: identifies failures and promising regions
- 10 new API endpoints
- 35 dedicated tests + all existing 402 tests (437 total)

### Phase III.H — Evidence Bridge + Benchmark + Calibration (Current) ✅
- Evidence bridge: structured import of external evidence (JSON/CSV/manual)
- Benchmark suite: reproducible accuracy measurement (FE MAE=0.23, BG MAE=0.42)
- Confidence calibration: empirical error-based bands by element count and value range
- 10 new API endpoints
- 28 dedicated tests + all existing 437 tests (465 total)
- III.H Delta: Calibration integrated into dossier/intelligence, validation queue calibrated,
  evidence→feedback auto-linking, 4 new endpoints, 18 delta tests (483 total)

### Phase III.I — Real Structure Analytics & Physical Descriptor Layer (Current) ✅
- 28 physical descriptors: density, volume, lattice, bonds, symmetry, composition stats, class fractions
- Evidence levels: computed_from_structure, computed_from_composition, proxy, unavailable
- Integrated into dossier as structure_analytics section
- 2 new API endpoints: /analytics/material/{id}, /analytics/report
- 21 dedicated tests + all existing 483 tests (504 total)
- Structure coverage: 2,000/75,993 (2.6%) — composition descriptors always available

### Phase III.J — Corpus Structure Backfill (Current) ✅
- Backfill: 73,993 JARVIS structures recovered from jarvis-tools atoms dicts in 399s
- Coverage: 2.6% → 100% (75,993/75,993 with validated CIF structures)
- Zero failures, zero data loss, database intact
- Analytics unlocked: density, volume, lattice, bonds, symmetry for entire corpus
- Note: Training on 5K/10K/20K/40K/76K should only happen after structure
  coverage expansion and coverage audit are complete — NOW READY.

### Phase IV.A — Scaled Retraining Ladder: Formation Energy (Current) ✅
- Training ladder: 5 rungs (5K→10K→20K→40K→76K) for CGCNN + ALIGNN-Lite
- Best model: **rung_20k CGCNN** — MAE=0.1528, R²=0.9499 (promoted to production)
- CGCNN outperforms ALIGNN-Lite at 20K (0.1528 vs 0.2162)
- Full corpus (76K) underperformed at 10 epochs — needs hyperparameter tuning at scale
- CTO Decision: PROMOTE_MID_SCALE_MODEL (20K is optimal cost/quality tradeoff)
- 16 dedicated tests + all existing 514 tests (530 total)
- Next: Phase IV.B — Band Gap ladder

### Phase IV.B — Band Gap Scaled Retraining (Current) ✅
- Training ladder: 6 rungs (5K→10K→20K CGCNN+ALIGNN→40K→76K) for band_gap
- Best model: **rung_20k ALIGNN-Lite** — MAE=0.3422, R²=0.707 (promoted to production)
- ALIGNN-Lite outperforms CGCNN at 20K for band_gap (0.3422 vs 0.3931)
- Full corpus (76K) did not improve MAE — same pattern as formation_energy
- CTO Decision: PROMOTE_MID_SCALE_MODEL (ALIGNN-Lite 20K)
- 9 new tests + all existing tests (539 total)

### Phase IV.C — Dual-Target Frontier Engine (Current) ✅
- Multiobjectve scoring: stability + band_gap_fit + novelty + exotic + structure_quality + validation_priority
- 4 profiles: balanced_frontier, stable_semiconductor, wide_gap_exotic, high_novelty_watchlist
- Uses promoted models: CGCNN FE (MAE=0.1528) + ALIGNN-Lite BG (MAE=0.3422)
- Supports corpus, generated, and mixed candidate pools
- Evidence propagation: known/predicted/proxy/unavailable on every property
- Reason codes for every candidate explaining ranking
- 4 API endpoints + 29 dedicated tests (568 total)

### Phase V — Physics-Based Screening (Planned)
- Phonon-based thermal stability (phonopy or ML surrogate)
- Equation of state fitting (Birch-Murnaghan)
- T/P-conditioned property correction
- Phase diagram / CALPHAD integration
- Relaxation integration (M3GNet/CHGNet)
- Scale to 10K-50K materials

### Phase IV — Advanced Integration (Planned)
- Phase diagram lookup / CALPHAD
- Digital Twin Materials Lab concept
- Phase-Aware Screening (multi-polymorph)
- Materials Aging Predictor
- Synthesis feasibility scoring
- Thermodynamic Condition Maps

### Phase V+ — Platform (Future)
- Blockchain proof-of-discovery (SOST integration)
- Community compute / federated training
- API marketplace for predictions

---

## 6. Innovative Concepts

### 6.1 Thermodynamic Condition Maps

**Concept:** For each material, generate a 2D map of predicted stability/properties across temperature and pressure ranges. Visual and queryable representation of where a material is expected to perform.

**Connects to:**
- **Phase-Aware Screening**: Different polymorphs may be stable at different T/P points. Condition maps reveal the polymorph landscape.
- **Digital Twin Materials Lab**: A condition map is the first layer of a digital twin — predicting behavior before synthesis.
- **Synthetic Feasibility Score**: If a material's best properties exist only at extreme T/P, the synthesis cost goes up. The condition map feeds feasibility scoring.
- **Materials Aging Predictor**: Degradation under thermal cycling or pressure fatigue maps onto condition map trajectories.

**Phase II.8 status:** Contract and data model defined. Population requires Phase III+ capabilities (phonon, EOS).

### 6.2 Phase-Aware Screening

Screen the same composition across all known polymorphs. Different crystal structures of the same formula can have drastically different properties.

### 6.3 Digital Twin Materials Lab

Simulate material behavior across conditions, aging, and processing without physical experimentation. Long-term vision requiring Phase IV+ capabilities.

### 6.4 Synthetic Feasibility Score

Estimate how difficult/expensive it is to synthesize a candidate material, considering required T/P conditions, precursor availability, and known synthesis routes.

### 6.5 Materials Aging Predictor

Predict property degradation over time under operating conditions — thermal cycling, pressure fatigue, oxidation exposure.

---

## 7. API Reference

| Method | Path | Phase | Status |
|--------|------|-------|--------|
| GET | /status | I | ✅ Production |
| GET | /health | I | ✅ Production |
| GET | /stats | I | ✅ Production |
| GET | /materials | I | ✅ Production |
| GET | /materials/{id} | I | ✅ Production |
| GET | /materials/{id}/structure-status | I | ✅ Production |
| GET | /search | I | ✅ Production |
| GET | /audit/summary | I | ✅ Production |
| POST | /predict | II | ✅ Baseline ML |
| POST | /predict (with T/P) | II.8 | ✅ Scaffold |
| GET | /similar/{id} | II | ✅ Baseline |
| GET | /novelty/{id} | III.A | ✅ Production |
| POST | /novelty/check | III.A | ✅ Production |
| GET | /candidates/exotic | III.A | ✅ Production |
| POST | /candidates/exotic/rank | III.A | ✅ Production |
| GET | /shortlist/default-criteria | III.B | ✅ Production |
| POST | /shortlist/build | III.B | ✅ Production |
| POST | /screening/thermo-pressure | III.B | ✅ Production |
| POST | /screening/thermo-pressure/batch | III.B | ✅ Production |
| GET | /campaigns/presets | III.C | ✅ Production |
| POST | /campaigns/run | III.C | ✅ Production |
| GET | /campaigns/{id} | III.C | ✅ Production |
| GET | /retrieval/status | III.C | ✅ Production |
| POST | /similar/search | III.C | ✅ Production |
| GET | /generation/presets | III.D | ✅ Production |
| GET | /generation/status | III.D | ✅ Production |
| POST | /generation/run | III.D | ✅ Production |
| GET | /generation/{id} | III.D | ✅ Production |
| POST | /generation/check | III.D | ✅ Production |
| POST | /generation/evaluate-run | III.E | ✅ Production |
| GET | /generation/evaluations/status | III.E | ✅ Production |
| GET | /generation/evaluation/{id} | III.E | ✅ Production |
| POST | /generation/lift-check | III.E | ✅ Production |
| GET | /intelligence/{id} | MIL | ✅ Production |
| POST | /intelligence/report | MIL | ✅ Production |
| POST | /intelligence/compare | MIL | ✅ Production |
| GET | /intelligence/status | III.F | ✅ Production |
| POST | /intelligence/dossier/from-evaluation | III.F | ✅ Production |
| GET | /intelligence/dossier/{id} | III.F | ✅ Production |

### Phase IV.D — Frontier-to-Validation Bridge (Current) ✅
- Validation Packs: concrete, exportable packages with evidence, risk flags, and next-step recommendations
- Bridge: converts frontier shortlists into validation queue entries with dedup
- Risk flags: known_material, weak_band_gap_confidence, generated_not_validated, etc.
- Next steps: keep_as_known_reference, watch_only, queue_for_proxy_review, queue_for_dft_when_budget_allows
- Export: JSON + Markdown + CSV summary
- 3 new API endpoints + 17 dedicated tests (585 total)

### Phase IV.E — Pre-DFT Triage Gate (Current) ✅
- Triage decisions: approved_for_budgeted_validation / needs_manual_review / watchlist_only / reject_for_now
- Hard gates: known_material_low_novelty, too_many_risk_flags, no_structure_required
- 4 profiles: strict_budget_gate, balanced_review_gate, exotic_patience_gate, stable_semiconductor_gate
- Next actions: promote_to_budget / review_with_human / keep_in_queue / defer / drop
- Reason codes: strong_frontier_score, good_calibration_support, generated_candidate_requires_review, etc.
- 4 API endpoints + 17 dedicated tests (602 total)

### Phase IV.F — Niche Discovery Campaign Engine (Current) ✅
- Themed campaigns: frontier → validation pack → triage in a single orchestrated run
- 5 presets: stable_semiconductor_hunt, wide_gap_exotic_hunt, high_novelty_watchlist, balanced_exotic_opportunities, generated_candidate_review
- Niche tags: stable_semiconductor, wide_gap_exotic, novel_watchlist, generated_high_interest, known_reference, budget_candidate
- Cross-campaign comparison with signal/risk ratio
- Batch execution: run multiple campaigns in one call
- 5 API endpoints + 17 dedicated tests (619 total)

### Phase IV.G — Active Learning + Corpus Expansion Orchestrator (Current) ✅
- Chemical space coverage: 89 elements, 213 spacegroups, dense/sparse region maps
- Error hotspot detection from calibration buckets (3 hotspots found)
- Retraining proposals: reasoned, prioritized, with recommended rung sizes
- Corpus expansion planner: 5 free sources (MP ~150K, COD ~530K, AFLOW ~3.5M, OQMD ~1M, NOMAD ~12M)
- Exotic niche analysis: rare earths, actinides, heavy pnictides, quaternary+ materials
- Action summary: what to improve, what not to touch, what data to seek
- 4 API endpoints + 17 dedicated tests (636 total)
- Version bumped to 2.0.0

### Phase IV.H — Multi-Source Corpus Expansion + Dedup Foundation (Current) ✅
- Source registry: 6 sources (JARVIS active, MP/COD/AFLOW/OQMD planned, NOMAD deferred)
- Normalization layer: common schema for any external source
- Dedup engine: exact (formula+SG), same_formula_different_structure, unique
- Staging mode: dry-run analysis before any merge (simulated MP: 22% unique from 200 sample)
- Expansion recommendation: scored ranking with action (ingest_next / defer)
- 4 API endpoints + 19 dedicated tests (655 total)
- Version 2.1.0

### Phase IV.I — Targeted AFLOW Ingestion Pilot (Current) ✅
- Pilot ingestion: 200 materials selected from 600 candidates (434 unique, 166 deduped)
- Corpus expanded: 75,993 → 76,193 (+200 AFLOW-simulated materials)
- New element added: Gd (was sparse in coverage analysis)
- AFLOW API was down — simulated data used with real pipeline, clearly labeled
- Plan/apply separation with dry-run mode
- Full audit trail: plan, run, audit, recommendation artifacts
- Recommendation: continue_aflow_expansion
- 4 API endpoints + 13 dedicated tests
- Version 2.2.0

### Phase IV.J — Real-Source COD Pilot + Labeled/Unlabeled Corpus Tiers ✅
- **Corpus Tiers**: 5-tier classification system (training_ready, structure_only, reference_only, generated_candidate, external_unlabeled)
- **Tier result**: 100% of 76,193 materials are training_ready (all JARVIS+AFLOW have FE+BG)
- **COD Pilot**: Attempted real COD API integration — server unreachable (158.129.170.82, 100% packet loss)
- **Fallback**: Used representative COD entries (real COD IDs) with full pipeline
- **COD result**: 13 unique structures identified, all classified as structure_only tier
- **Training impact**: NONE — COD provides experimental structures only, no computed FE/BG
- **Enhanced dedup**: 7 decision types (exact_duplicate, probable_duplicate, same_formula_different_structure, structure_near_match, unique_material, unique_structure_only, unique_training_candidate)
- **Value report**: Quantified COD contribution — structural reference expansion only, no training value
- **Decision**: `pause_cod_keep_as_reference_layer` — wait for AFLOW/MP real API for training data
- **Critical rule**: Only training_ready tier enters ML training. NO retraining on COD-only materials.
- **Coverage**: 89 elements, 213 spacegroups, 99.74% structure coverage
- 6 new API endpoints + 46 dedicated tests (714 total)
- Version 2.3.0

### Phase IV.K — Hard-Case Mining + Selective Retraining Datasets ✅
- Hard-case mining: 76,124 BG materials classified by difficulty (69.87% easy, 23.16% medium, 6.32% hard)
- FE model strong: 97.58% easy → low priority for retraining
- BG weakest regions: 3-6 eV (MAE=1.12 LOW), 1-3 eV (MAE=0.87 MEDIUM), 5+ elements (MAE=0.73 MEDIUM)
- 6 selective datasets prepared: bg_sparse_exotic_10k (#1), bg_hotspots_10k (#2), bg_balanced_hardmix_20k (#3), fe_sparse_mix_10k (#4), curriculum_20k (#5), fe_hardcases_10k (#6)
- Priority scoring: benefit (30%) + difficulty (20%) + diversity (15%) + sparse (15%) + exotic (10%) - overfit (5%) - cost (5%)
- Decision: `retrain_band_gap_hotspots_next` with bg_sparse_exotic_10k on rung_20k
- **NO training executed** — datasets prepared only
- 5 new API endpoints + 37 dedicated tests (751 total)
- Version 2.4.0

### Phase IV.L — Selective Band Gap Retraining + Promotion Decision ✅
- 3 ALIGNN-Lite challengers trained on selective datasets (REAL training, ~65 min total)
- Challenger 1 (bg_hotspots_10k): MAE=0.6374, R²=0.5977 — WORSE than production
- Challenger 2 (bg_sparse_exotic_10k): MAE=0.5926, R²=0.7336 — WORSE than production
- Challenger 3 (bg_balanced_hardmix_20k): MAE=0.6991, R²=0.6745 — WORSE than production
- Production (ALIGNN-Lite 20K random): MAE=0.3422, R²=0.707 — STILL BEST
- **Decision: HOLD** — no promotion, production model unchanged
- **Root cause**: Selective subsets exclude the metal/narrow-gap majority. Model never learns easy baseline.
- **Lesson**: Need stratified sampling or curriculum learning that includes ALL BG ranges
- Model registry NOT updated — production unchanged
- 4 API endpoints + 21 dedicated tests (772 total)
- Version 2.5.0

### Phase IV.M — Stratified/Curriculum Band Gap Retraining ✅
- 3 challengers: stratified 20K (MAE=0.6547), curriculum 20K (MAE=0.6287), stratified balanced 30K (MAE=0.6771)
- ALL worse than production random 20K (MAE=0.3422)
- **Decision: HOLD** — production model retained again
- **Key insight**: Random sampling on a metal-dominated corpus is naturally well-distributed. Overweighting hard cases distorts the distribution more than it helps. Improving beyond MAE=0.34 requires architectural changes, not data selection.
- Combined with IV.L: 6 challengers tried across 2 phases, none beat production
- Total retraining compute: ~163 minutes of GPU-free CPU training
- 4 API endpoints + 22 tests (794 total), version 2.6.0

### Phase IV.N — Hierarchical Band Gap Modeling ✅
- Metal gate (CGCNN binary classifier): 90.8% accuracy, F1_metal=0.94, F1_nonmetal=0.81
- Non-metal regressor (ALIGNN-Lite): MAE=0.7609 on 19,879 non-metals
- **Combined pipeline MAE=0.2793** vs production 0.3422 (**-18.4%**)
- Metal bucket: 0.3154 → 0.0048 (massive improvement — trivial case correctly handled)
- Wide-gap bucket: 1.1223 → 0.9067 (improved)
- **Regression: narrow-gap 0.05-1.0 eV: 0.509 → 0.907** (gate misclassifies some semiconductors as metals)
- Decision: **WATCHLIST** — overall improvement proven, but narrow-gap regression blocks promotion
- **Key insight**: Hierarchical approach IS the right architecture direction. Just needs better gate for borderline materials.
- Production model unchanged (ALIGNN-Lite 20K, MAE=0.3422)
- 5 API endpoints + 20 tests (814 total), version 2.7.0

### Phase IV.O — Gate Calibration + Borderline Routing ✅
- Threshold sweep (10 values) + 11 routing policy configurations on 4,000 real test samples
- Best overall MAE: 0.2187 (36.1% better than production 0.3422)
- Lowering gate threshold 0.5→0.25 reduces FN from 220→78 but doesn't fix narrow-gap (0.60→0.68)
- **Key insight**: Narrow-gap regression is NOT caused by gate misclassification — it's the regressor's MAE=0.76 on non-metals
- Even with perfect gate (0 FN), narrow-gap materials get regressor error of ~0.68 vs production's 0.51
- Decision: **WATCHLIST** — overall improvement real but regressor needs improvement for promotion
- Next step: retrain non-metal regressor (more epochs, lower LR) to reduce MAE below 0.50
- 5 API endpoints + 22 tests (836 total), version 2.8.0

### Phase IV.P — Non-Metal Regressor Improvement ✅
- 3 challengers: longer (MAE=0.7369), lower_lr (MAE=0.6654), both (MAE=0.6679)
- Best: `nonmetal_lower_lr` (20ep, lr=0.002) — **12.5% regressor improvement** vs V1
- Pipeline MAE: 0.7609→0.6654 regressor → 0.2793→0.2568 pipeline (**25% better than production**)
- Lower LR is the key driver. More epochs has diminishing/negative returns (overfitting observed).
- Decision: **WATCHLIST** — strong overall improvement, projected narrow-gap still elevated
- Total hierarchical BG effort: IV.N (gate+reg) + IV.O (calibration) + IV.P (regressor) = focused pipeline
- 4 API endpoints + 18 tests (854 total), version 2.9.0

### Phase IV.Q — Final Hierarchical Promotion Benchmark ✅
- Direct benchmark on 2,000 real materials (not projections)
- Production: MAE=0.3407 | Hierarchical V2: MAE=0.2628 (**-22.9%**)
- Metals: 0.1907 → 0.0892 (massive improvement)
- Wide-gap: 0.8682 → 0.8116 (improved)
- **Narrow-gap: 0.5135 → 0.6495 (+0.136 REGRESSION)** — blocks promotion
- Scorecard: 4/5 PASS, narrow-gap FAIL
- **Decision: HOLD_SINGLE_STAGE_BG** — production retained
- Registry NOT updated
- The hierarchical architecture IS superior overall but needs better gate for borderline semiconductors
- 4 API endpoints + 16 tests (870 total), version 3.0.0

### Phase IV.R — Narrow-Gap Rescue / Three-Tier Pipeline ✅
- Narrow-gap specialist: MAE=0.2221 on 7,618 materials (0.05-1.0 eV)
- 3-tier: production 0.3407 → 2-tier 0.2628 → 3-tier 0.2596
- Narrow-gap: 0.5135 (prod) → 0.6495 (2-tier) → 0.6187 (3-tier) — improved but still +0.1052
- Only 48/142 narrow-gap materials reached specialist (rest FN'd by gate)
- **Decision: HOLD** — specialist works but gate FN limits impact
- **Irreducible bottleneck**: Gate misclassifies ~20% of narrow-gap as metal
- Total BG pipeline effort: IV.L→IV.R = 8 phases, 20+ models, 2 definitive benchmarks
- 5 API endpoints + 18 tests (888 total), version 3.1.0

### Phase IV.S — Gate Recall Rescue ✅
- Oversampled gate: 8K metal + 6K narrow + 6K wide (was 14K+6K)
- Gate recall for non-metals: 0.80 → 0.97 at threshold=0.35
- Narrow reaching specialist: 48/142 → 135/142 (95% routing)
- Narrow-gap delta: +0.08 (PASS, within +0.10 tolerance)
- **BUT metals regressed**: 0.1907 → 0.2506 (+0.06, fails +0.05 tolerance)
- Medium/wide-gap dramatically improved: 0.795→0.552, 0.868→0.658
- **Decision: HOLD** — threshold tradeoff: better routing = worse metal accuracy
- The gate binary threshold is fundamentally a tradeoff slider between metal/non-metal accuracy
- Total BG effort: IV.L→IV.S = 9 phases, 22+ real models, 3 direct benchmarks
- 5 API endpoints + 9 tests (897 total), version 3.2.0

### Phase IV.U — Public Demo + Operational Acceptance ✅
- Operational acceptance: **10/10 checks PASS — ACCEPTED**
- Demo surface: 16 endpoints safe for public demo
- 5 golden workflows documented (search, predict, discover, campaign, frontier)
- Release notes: full capabilities, limitations, next steps
- 4 API endpoints + 13 tests (922 total)
- **This is the official closure of the Materials Engine standalone project**

### Phase IV.T — Engine Stabilization + Release Candidate ✅
- Release manifest: v3.2.0-RC1, corpus 76,193, 2 production models, 145 API endpoints
- Production freeze: FE CGCNN (MAE=0.1528) + BG ALIGNN-Lite (MAE=0.3422) — locked
- API audit: 105 production-ready, 40 research/internal endpoints
- Artifact audit: 33 directories organized by function
- Research watchlist: hierarchical BG pipeline (24% improvement, not promoted)
- 4 API endpoints + 12 tests (909 total)
- **This is the official state of the Materials Discovery Engine**

### What has NOT been retrained
- Models remain at Phase IV.A/B levels (CGCNN FE MAE=0.1528, ALIGNN-Lite BG MAE=0.3422)
- No retraining on AFLOW pilot or COD pilot materials
- Retraining blocked until more labeled data from real DFT sources is available
- Next retraining should use curated training_ready tier only
