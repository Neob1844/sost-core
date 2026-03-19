# SOST Materials Discovery Engine — Strategic Plan

> **Document status: Active implementation — Phase III.H Final (v1.2.1)**
> Last updated: 2026-03-18

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

### Phase IV — Physics-Based Screening (Planned)
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
