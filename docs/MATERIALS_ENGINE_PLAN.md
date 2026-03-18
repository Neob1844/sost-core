# SOST Materials Discovery Engine — Strategic Plan

**Version:** 1.0
**Date:** 2026-03-18
**Status:** Pre-implementation (all content on the website page is narrative/placeholder)
**Document type:** Strategic architecture and competitive analysis

---

## Table of Contents

1. [Current State](#1-current-state)
2. [Competitive Analysis](#2-competitive-analysis)
3. [Available Databases](#3-available-databases)
4. [Proposed Architecture](#4-proposed-architecture)
5. [Innovative Concepts](#5-innovative-concepts)
6. [Technology Stack](#6-technology-stack)
7. [Roadmap](#7-roadmap)
8. [Competitive Advantage Matrix](#8-competitive-advantage-matrix)

---

## 1. Current State

### 1.1 What the Website Page Describes

The SOST Materials Discovery Engine website page (`sost-materials-engine.html`) presents a narrative vision for an independent research platform within the SOST ecosystem. The page describes the following components, **none of which are implemented**:

**Platform Identity:**
- An independent research platform for computational materials science
- Explicitly stated as separate from the ConvergenceX mining engine
- Accessible via SOST escrow payments (PoPC Model B mechanism)
- The algorithm itself is described as free; the escrow deposit is framed as a spam-prevention mechanism, fully refundable upon tier expiry

**Five-Layer Architecture (described, not built):**

| Layer | Name | Description on Page |
|-------|------|-------------------|
| Layer 1 | Data Foundation | ~150K known materials sourced from Materials Project, JARVIS, and AFLOW |
| Layer 2 | Inverse Search | Specify desired properties, receive ranked candidate compositions |
| Layer 3 | Property Prediction | Graph neural networks (CGCNN, MEGNet, ALIGNN) predict properties of hypothetical compositions |
| Layer 4 | Generative Discovery | Evolutionary algorithms mutate and recombine known compositions; fitness evaluated by Layer 3 |
| Layer 5 | Continuous Learning | Feedback loop: validated predictions refine models, user data enriches database, discoveries seed further exploration |

**Computational Approach (described, not built):**
- ML Models: CGCNN, MEGNet, ALIGNN for property prediction
- Optimization: Evolutionary algorithms and numerical optimization for composition search and structure relaxation
- DFT Integration: API access to VASP, Quantum ESPRESSO, GPAW for ab initio validation
- Community Compute: Miners donate idle CPU cycles between blocks (voluntary, opt-in)

**Community Compute Marketplace (described as "FUTURE"):**
- Researchers publish materials discovery problems
- Mining community contributes idle CPU time for simulations
- Miners earn rewards from the PoPC Pool
- Results published on-chain as immutable open data

**Access Tiers (described, not built):**
- Tier 1: $10 USD equivalent in SOST, 1-month lock — Layers 1-3 (search + prediction)
- Tier 2: $20 USD equivalent in SOST, 2-month lock — Layers 1-4 (+ generative discovery)
- Tier 3: $50 USD equivalent in SOST, 6-month lock — Layers 1-5 (full access including DFT validation queue)

### 1.2 What Actually Exists

**Nothing.** There is no backend, no API, no trained models, no database ingestion pipeline, no escrow integration, and no compute marketplace. The website page is a design document rendered as HTML. The disclaimer on the page itself acknowledges this: "This is a research direction, not a product commitment."

### 1.3 Gap Analysis

| Component | Website Claims | Reality | Effort to Build |
|-----------|---------------|---------|-----------------|
| Materials database (150K) | Described as operational | No database, no ingestion | 2-4 weeks (API integration) |
| Inverse search | Described as functional | No search engine | 4-6 weeks (indexing + query engine) |
| CGCNN/MEGNet/ALIGNN models | Listed as available | No trained models | 2-3 months (training + validation) |
| Evolutionary generation | Described as working | No optimizer | 4-8 weeks (algorithm + integration) |
| DFT integration | "API access" described | No VASP/QE/GPAW interface | 2-3 months (license + interface) |
| Community compute | Tagged "FUTURE" | No marketplace code | 6+ months (P2P protocol + scheduling) |
| SOST escrow access | Tiers described | No escrow contract code | 4-8 weeks (after node supports escrow) |
| Continuous learning loop | Described | No feedback pipeline | 3-4 months (after models exist) |

---

## 2. Competitive Analysis

### 2.1 JARVIS (NIST)

**Full name:** Joint Automated Repository for Various Integrated Simulations
**Institution:** National Institute of Standards and Technology (NIST)
**URL:** https://jarvis.nist.gov/
**First release:** 2017

**Database scope:**
- 80,000+ materials with DFT-computed properties (JARVIS-DFT)
- 55,000+ 3D materials, 1,000+ 2D materials
- Properties: formation energy, band gap (OPT/MBJ), elastic constants, piezoelectric, dielectric, solar efficiency, thermoelectric figure of merit, topological spin-orbit spillage
- Additional datasets: JARVIS-FF (force fields), JARVIS-ML (ML descriptors), JARVIS-STM (scanning tunneling microscopy), JARVIS-HETERO (heterostructure data)

**ML capabilities:**
- ALIGNN (Atomistic Line Graph Neural Network) — currently state-of-the-art on MatBench leaderboard for most property prediction tasks
- ALIGNN achieves MAE of 0.033 eV/atom on formation energy (Materials Project test set) and 0.14 eV on band gap (JARVIS-DFT)
- Pre-trained models available via `alignn` Python package on PyPI
- ALIGNN-FF: force field models for molecular dynamics

**Access:**
- `jarvis-tools` Python package (`pip install jarvis-tools`)
- REST API at `https://jarvis.nist.gov/jarvisdft/` with JSON endpoints
- Bulk download via Figshare (DOI: 10.6084/m9.figshare.6815699)
- No API key required for most endpoints

**Strengths:**
- Government-backed (NIST), guaranteed long-term funding and stability
- ALIGNN is the best-performing GNN for crystalline materials property prediction as of 2025
- Comprehensive DFT data with consistent computational settings (OptB88vdW functional)
- Covers both 3D and 2D materials, rare among databases
- Public domain data (no license restrictions as a US government work)
- Active development with regular updates (monthly database refreshes)

**Weaknesses:**
- Update cadence is slower than community-driven projects (quarterly for major additions)
- Limited generative capabilities — ALIGNN is predictive only, no inverse design
- API documentation is sparse; some endpoints are undocumented
- Web interface is functional but not polished
- No multi-objective optimization built in
- No marketplace or collaborative features

### 2.2 Materials Project (Berkeley Lab)

**Full name:** The Materials Project
**Institution:** Lawrence Berkeley National Laboratory (LBNL), UC Berkeley
**URL:** https://materialsproject.org/
**First release:** 2011
**Funding:** DOE Office of Science (BES)

**Database scope:**
- ~154,000 inorganic materials with computed properties (as of 2025)
- ~130,000 molecules (Materials Project Molecules, MPcules)
- Properties: formation energy, energy above hull, band gap (PBE and HSE), elastic tensor (bulk/shear modulus), piezoelectric tensor, dielectric constant, magnetic ordering, density of states, band structure, X-ray diffraction patterns
- Phase diagrams for all computed chemical systems
- Pourbaix diagrams (electrochemical stability)
- Surface energies for selected materials

**Core library:**
- `pymatgen` (Python Materials Genomics) — the most widely used materials science Python library
- 15,000+ GitHub stars, used in 3,000+ published papers
- Classes: Structure, Molecule, Element, Composition, Phase Diagram, Pourbaix, DOS, BandStructure
- I/O for all major DFT codes (VASP, QE, ABINIT, Gaussian, CP2K)
- Symmetry analysis via spglib integration

**Access:**
- REST API v2 (MP API) via `mp-api` Python client (`pip install mp-api`)
- Requires free API key (register at materialsproject.org)
- MongoDB-style queries: `mpr.materials.summary.search(band_gap=(1.0, 2.0), is_stable=True)`
- Rate limit: 40 requests/second with API key
- Bulk download available for registered users

**Strengths:**
- Gold standard for inorganic computed materials data; most cited materials database
- pymatgen is the de facto standard library for materials informatics
- Excellent API design with powerful query language
- Phase diagram and thermodynamic stability tools are unmatched
- Regular data releases with quality control
- Large, active community (Discourse forum, Slack, yearly workshops)

**Weaknesses:**
- Inorganic crystalline materials only — no organic molecules, polymers, or biological materials
- PBE functional underestimates band gaps (~40% too low); only ~8,000 materials have HSE corrections
- Limited ML model integration — relies on community tools like MEGNet (deprecated in favor of M3GNet/CHGNet) rather than providing built-in prediction
- No generative or inverse design capabilities
- Elastic data available for only ~13,000 materials (subset of full database)
- API key system adds friction for quick prototyping

### 2.3 AFLOW (Duke University)

**Full name:** Automatic FLOW for Materials Discovery
**Institution:** Duke University, Center for Autonomous Materials Design
**URL:** http://aflowlib.org/
**First release:** 2012
**PI:** Stefano Curtarolo

**Database scope:**
- ~3.5 million compound entries (largest curated materials database)
- ~700,000 unique materials with DFT calculations
- Properties: formation enthalpy, band gap, elastic properties, Bader charges, magnetic moment, electronic DOS, phonon dispersions (for subset)
- AFLOW Prototypes: 590+ crystal structure prototypes covering most known structure types

**Key tools:**
- AFLOW Descriptors: 283 compositional and structural features per material, purpose-built for ML
- AFLOW-ML: REST API endpoint that returns ML predictions for any composition
- AFLOW-SYM: symmetry analysis library
- AFLOW-CHULL: convex hull construction for thermodynamic stability
- AFLOW-CCE: coordination-corrected enthalpies (improved accuracy over raw DFT)

**Access:**
- REST API at `http://aflowlib.org/API/aflux/`
- AFLUX query language: `http://aflowlib.org/API/aflux/?species(Si),Egap(1*,2*),paging(0)`
- Bulk download via `aflow` command-line tool
- Python wrapper: `aflow` package (`pip install aflow`)
- No API key required

**Strengths:**
- Largest curated database by entry count — 3.5M+ entries provide unmatched chemical space coverage
- AFLOW Descriptors provide ready-to-use ML feature vectors without requiring graph construction
- CCE correction significantly improves formation enthalpy accuracy
- Crystal structure prototypes are invaluable for systematic enumeration
- Automated workflow for adding new calculations (truly "automatic flow")

**Weaknesses:**
- API is powerful but complex — AFLUX query syntax has a steep learning curve
- Documentation quality varies; some endpoints are poorly described
- Web interface feels dated compared to Materials Project
- Less active community engagement; fewer tutorials and workshops
- Data consistency can vary across different calculation batches
- No built-in inverse design or generative capabilities

### 2.4 NOMAD (Novel Materials Discovery)

**Full name:** Novel Materials Discovery Laboratory
**Institution:** NOMAD Centre of Excellence (EU), hosted at Fritz Haber Institute, Berlin
**URL:** https://nomad-lab.eu/
**Funding:** European Commission Horizon 2020/Europe

**Database scope:**
- 100M+ total calculations archived (largest raw calculation archive)
- Covers DFT, DMFT, GW, BSE, quantum chemistry, molecular dynamics, Monte Carlo
- Parses output from 60+ simulation codes (VASP, QE, FHI-aims, ABINIT, Gaussian, ORCA, LAMMPS, etc.)
- Standardized metadata schema (NOMAD MetaInfo) normalizes all uploaded data
- NOMAD Oasis: self-hosted instances for group-private data before publication

**Key features:**
- FAIR data principles: Findable, Accessible, Interoperable, Reusable
- NOMAD Encyclopedia: curated subset of ~2M materials with standardized properties
- NOMAD AI Toolkit: Jupyter-based analytics environment with pre-loaded data access
- Electronic Lab Notebook (ELN) integration for experimental data
- DOI assignment for datasets (proper academic citation)

**Access:**
- REST API v1 at `https://nomad-lab.eu/prod/v1/api/v1/`
- Python client: `nomad-lab` package
- GraphQL query interface
- Bulk download via NOMAD Archive (structured) or NOMAD Repository (raw files)

**Strengths:**
- Massive data volume — 100M+ calculations is orders of magnitude beyond any competitor
- Code-agnostic parser architecture handles virtually any simulation software output
- FAIR compliance makes data genuinely interoperable with other repositories
- NOMAD Oasis provides private staging before public release — appeals to groups wanting to publish data with a paper
- Strong institutional backing with EU funding commitments

**Weaknesses:**
- Volume comes at the cost of curation — much of the data is raw, unvalidated upload
- Complex to query effectively; requires understanding the MetaInfo schema
- Primarily archival — designed for data preservation, not active discovery
- Search latency can be high for complex queries across 100M+ entries
- ML integration is limited to the AI Toolkit (Jupyter) rather than built-in models
- No generative or inverse design capabilities

### 2.5 OQMD (Open Quantum Materials Database)

**Full name:** Open Quantum Materials Database
**Institution:** Northwestern University
**URL:** http://oqmd.org/
**PI:** Chris Wolverton
**First release:** 2013

**Database scope:**
- ~1,000,000 DFT calculations (as of 2025)
- Focus on thermodynamic stability: formation energy, energy above hull, decomposition products
- Primarily ternary and quaternary compounds from systematic enumeration of ICSD prototypes
- All calculations performed with consistent VASP settings (PBE, PAW, 520 eV cutoff)

**Access:**
- REST API at `http://oqmd.org/api/`
- `qmpy` Python package for programmatic access and local calculation management
- Bulk download as SQL dump (~30 GB)
- Django-based web interface with filtering

**Strengths:**
- Systematic enumeration approach means excellent coverage of ternary/quaternary phase space
- Consistent computational settings across all entries — minimizes artifacts from mixing methods
- Thermodynamic stability predictions (convex hull) are highly reliable
- Large scale: 1M entries provides dense sampling of formation energy landscape
- qmpy integrates with VASP for users who want to run their own calculations in the same framework

**Weaknesses:**
- Limited property coverage — primarily formation energy and stability; no elastic, piezoelectric, or optical properties
- API is functional but basic; lacks the query power of AFLUX or MP API
- Update frequency has slowed since initial burst of calculations
- No ML models integrated
- Web interface is minimalist
- No 2D materials, surfaces, or defect calculations

### 2.6 Google DeepMind GNoME

**Full name:** Graph Networks for Materials Exploration
**Institution:** Google DeepMind
**Published:** November 2023 (Nature, doi:10.1038/s41586-023-06735-9)

**Key results:**
- 2.2 million new stable crystal structures predicted (381,000 on the convex hull)
- 45x expansion over previously known stable materials in the ICSD
- Two complementary GNN pipelines: (1) structural candidates from known prototypes, (2) compositional candidates from element substitution
- Active learning loop: GNN predicts stability → DFT validates top candidates → validated data retrains GNN → repeat
- 736 of the GNoME-predicted materials were independently synthesized by autonomous lab (A-Lab at LBNL) — experimental validation rate of ~71%

**Technical approach:**
- Graph neural network on crystal structure graphs (nodes = atoms, edges = bonds within cutoff)
- Trained on ~69,000 Materials Project entries, iteratively expanded to millions
- Each active learning round: GNN screens ~10M candidates, DFT validates top ~100K, retrain
- Final model trained on ~500,000 DFT-validated stable structures

**Data availability:**
- 381,000 stable structures released to Materials Project (integrated into MP database as of 2024)
- Additional ~1.8M structures released via Google Research GitHub
- No training code released
- No model weights released for the final GNN

**Strengths:**
- Massive scale: 2.2M predictions dwarfs any previous computational materials discovery effort
- Experimental validation (A-Lab synthesis) provides real-world proof
- Active learning methodology is sound and well-documented in the paper
- Data contribution to Materials Project benefits the entire community
- Google's compute resources make the scale feasible

**Weaknesses:**
- Not reproducible: no training code, no model weights, no hyperparameter details sufficient to replicate
- Google-dependent: if DeepMind deprioritizes materials, the project could stall or disappear
- Only predicts thermodynamic stability (formation energy, energy above hull) — no band gap, elasticity, or other functional properties
- The 2.2M number includes metastable materials; the truly novel stable count (on hull) is 381K
- No inverse design capability — the pipeline discovers materials but cannot target specific properties
- No open API for running predictions on user-supplied structures

### 2.7 Microsoft MatterGen

**Full name:** MatterGen: A Generative Model for Inorganic Materials Design
**Institution:** Microsoft Research AI for Science
**Published:** 2024 (Nature, doi:10.1038/s41586-025-08628-5)

**Technical approach:**
- Diffusion model that generates crystal structures by denoising from random noise
- Operates on three modalities simultaneously: atom types (categorical), atom positions (continuous), lattice parameters (continuous)
- Conditional generation: specify target properties (e.g., band gap = 1.5 eV, bulk modulus > 200 GPa) and the model generates structures satisfying those constraints
- Property conditioning via classifier-free guidance (same technique used in image diffusion models like DALL-E/Stable Diffusion)
- Training data: ~608,000 structures from Materials Project and Alexandria database

**Key results:**
- Generated materials are 3-5x more likely to be stable than prior generative methods (CDVAE, SyMat, DiffCSP)
- Conditional generation: 87.5% of band-gap-conditioned samples fall within 0.5 eV of target
- Successfully generated novel compositions not in training data, validated by DFT
- Demonstrated for magnets (high magnetic density), superconductors (target Tc), and bulk modulus optimization

**Availability:**
- Paper published with detailed architecture description
- Limited open source: evaluation code released, but full training pipeline is proprietary
- No public API
- Model weights not released

**Strengths:**
- True inverse design: specify what you want, get a material that satisfies it — this is the holy grail of computational materials science
- Multi-property conditioning: can target multiple properties simultaneously
- Diffusion framework is principled and extensible
- Joint generation of composition + structure + lattice (other methods often fix one and vary the others)
- Microsoft's sustained investment in AI for Science suggests longevity

**Weaknesses:**
- Proprietary: cannot be reproduced or extended without Microsoft's code and compute
- Limited to inorganic crystalline materials (same limitation as Materials Project)
- Small unit cells only (up to ~20 atoms) — cannot generate complex structures, defects, or interfaces
- Stability validation still requires external DFT — the model generates candidates, not guaranteed stable structures
- Early stage: impressive proof-of-concept, but not yet a production tool
- No community access or marketplace

### 2.8 CDVAE (Crystal Diffusion Variational Autoencoder)

**Full name:** Crystal Diffusion Variational Autoencoder
**Institution:** MIT, Xie et al.
**Published:** 2022 (ICLR 2022, arXiv:2110.06197)
**Code:** https://github.com/txie-93/cdvae

**Technical approach:**
- Variational autoencoder (VAE) that encodes crystal structures into a continuous latent space
- Diffusion process applied to atom positions for generation (denoising score matching)
- Encoder: multi-graph neural network on periodic crystal graph
- Decoder: iteratively refines atom types, positions, and lattice from latent code
- Property prediction head on the latent space enables property-directed optimization

**Key results:**
- Generates valid crystal structures with 78% validity rate (valid composition + reasonable interatomic distances)
- Outperforms prior methods (G-SchNet, P-G-SchNet) on structure and composition validity metrics
- Property optimization via gradient ascent in latent space: demonstrated for formation energy and band gap
- Trained on three datasets: Perov-5 (perovskites), Carbon-24, MP-20 (Materials Project, <=20 atoms/cell)

**Availability:**
- Fully open source (MIT license) on GitHub
- Training code, model architecture, and pre-trained weights all available
- Dependencies: PyTorch, PyTorch Geometric, hydra-core, pymatgen
- Reproducible with single GPU (NVIDIA V100 or equivalent, ~24h training on MP-20)

**Strengths:**
- Fully open source and reproducible — the gold standard for academic generative materials models
- Continuous latent space enables smooth interpolation between materials
- Property optimization via latent space gradient ascent is elegant and efficient
- Foundation that MatterGen and subsequent work builds upon
- Active academic community extending and improving CDVAE

**Weaknesses:**
- Limited to small unit cells (<=20 atoms in the original paper; <=40 atoms with modifications)
- Validity rate of 78% means ~1 in 5 generated structures is chemically unreasonable
- No conditioning mechanism in the original model (added in follow-up work)
- Lattice prediction quality is lower than atom position quality
- Does not handle partial occupancy, disorder, or defects
- Training is sensitive to hyperparameters; requires careful tuning for new datasets

---

## 3. Available Databases

### 3.1 Comprehensive Database Inventory

| Database | Size | Properties | Access Method | License | Update Frequency |
|----------|------|------------|---------------|---------|-----------------|
| **Materials Project** | ~154K materials, ~130K molecules | Band gap (PBE/HSE), formation energy, elastic tensor, piezoelectric, dielectric, magnetic ordering, DOS, band structure, phase diagrams | REST API v2 (`mp-api` Python client), API key required, 40 req/s | CC-BY-4.0 | Monthly |
| **JARVIS-DFT** | ~80K materials (55K 3D, 1K 2D) | Formation energy, band gap (OPT/MBJ), elastic constants, piezoelectric, dielectric, solar efficiency, thermoelectric ZT, topological spillage | REST API (`jarvis.nist.gov`), `jarvis-tools` Python package, no API key | Public domain (NIST) | Quarterly |
| **AFLOW** | ~3.5M entries (~700K unique) | Formation enthalpy, band gap, elastic properties, Bader charges, magnetic moment, DOS, phonon dispersions | REST API (AFLUX query language), `aflow` Python package, no API key | CC-BY-4.0 | Continuous |
| **NOMAD** | 100M+ calculations | Varies by upload (DFT, DMFT, GW, MD, MC), standardized via MetaInfo schema | REST API v1, GraphQL, `nomad-lab` Python client, bulk download | CC-BY-4.0 | Continuous (community upload) |
| **OQMD** | ~1M DFT calculations | Formation energy, energy above hull, decomposition products, thermodynamic stability | REST API (`oqmd.org/api`), `qmpy` Python package, SQL dump | Open (custom license, free for academic use) | Infrequent |
| **COD** | 530K+ structures | Crystal structure (unit cell, space group, atom positions), bibliographic references | REST API, CIF download, MySQL dump, `cod-tools` | Public domain (for structures from public literature) | Weekly |
| **ICSD** | 280K+ structures | Crystal structure, space group, Wyckoff positions, bibliographic data, mineral names | Licensed web portal, CIF export, no public API | Commercial (FIZ Karlsruhe), ~$5K-20K/year | Biannual |
| **PubChem** | 115M+ compounds | Molecular formula, SMILES/InChI, molecular weight, XLogP, H-bond donors/acceptors, TPSA, pharmacological data, bioassay results | REST API (PUG REST), `pubchempy` Python package, FTP bulk download | Public domain (NCBI/NIH) | Daily |
| **Open Catalyst (OC20/OC22)** | 1.3M+ DFT relaxations | Adsorption energies, relaxed structures, forces, adsorbate-catalyst interactions | Direct download (tar.gz), `ocpmodels` Python package, pre-trained models | CC-BY-4.0 | Per release (~yearly) |
| **MatBench** | 13 benchmark datasets | Formation energy, band gap, dielectric, elastic (log10 Kvrh, log10 Gvrh), glass transition, exfoliation energy, etc. | `matbench` Python package (`pip install matminer`), direct download | CC-BY-4.0 | Stable (benchmark, not updated) |
| **C2DB** | 4,000+ 2D materials | Band gap, magnetic properties, elastic stiffness, Raman spectra, effective masses, Berry phases, topological invariants | Web download (DTU), `ase` integration | CC-BY-4.0 | Annual |

### 3.2 Database Selection Strategy

**Tier 1 — Ingest immediately (highest value, easiest access):**
- Materials Project: gold standard data quality, excellent API, CC-BY-4.0
- JARVIS-DFT: unique properties (solar efficiency, thermoelectric), public domain, ALIGNN training data
- AFLOW: largest curated set, excellent ML descriptors

**Tier 2 — Ingest in Phase 2 (valuable but requires more effort):**
- OQMD: thermodynamic stability focus, SQL dump requires parsing
- COD: crystal structures only (no computed properties), useful for structure templates
- Open Catalyst: catalysis-specific, requires domain expertise to integrate
- C2DB: small but unique 2D materials focus

**Tier 3 — Integrate as needed:**
- NOMAD: massive but requires careful filtering and normalization
- PubChem: molecular/organic — different domain than crystalline materials
- ICSD: commercial license makes it unsuitable for open platform unless institutional subscription exists
- MatBench: benchmarking only, not a discovery database

### 3.3 Data Harmonization Challenges

Different databases use different DFT settings, which means formation energies are not directly comparable:

| Database | DFT Code | Functional | Pseudopotential | Cutoff |
|----------|----------|-----------|-----------------|--------|
| Materials Project | VASP | PBE+U | PAW | 520 eV |
| JARVIS-DFT | VASP | OptB88vdW | PAW | 600 eV |
| AFLOW | VASP | PBE | PAW | varies (AFLOW standard) |
| OQMD | VASP | PBE+U | PAW | 520 eV |

Cross-database normalization requires either: (a) re-computing all entries with a single set of settings (prohibitively expensive), (b) learning a correction function between databases using overlapping entries, or (c) treating each database as a separate training domain and using domain adaptation techniques. Option (b) is the most practical — Materials Project and OQMD share ~60,000 overlapping compositions that can anchor a correction model.

---

## 4. Proposed Architecture

### 4.1 Trial-Error-Learning Loop

The core engine operates as a closed-loop discovery cycle, fundamentally different from the query-and-retrieve model of existing databases:

```
                    +------------------+
                    |  PROPOSE         |
                    |  Candidate       |
                    |  (generative     |
                    |   model output)  |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  SIMULATE        |
                    |  (GNN predict    |
                    |   or DFT calc)   |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  COMPARE         |
                    |  (predicted vs   |
                    |   target props)  |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  LEARN           |
                    |  (update model   |
                    |   weights/prior) |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  CORRECT         |
                    |  (adjust search  |
                    |   distribution)  |
                    +--------+---------+
                             |
                             +-----------> back to PROPOSE
```

**Propose:** The generative model (diffusion-based crystal structure generator or evolutionary composition optimizer) produces a batch of candidate materials. Each candidate is a complete specification: composition, crystal structure (space group, lattice parameters, Wyckoff positions), and optionally defect configuration.

**Simulate:** Each candidate is evaluated through a tiered prediction pipeline. Fast GNN screening (ALIGNN, ~10ms/structure) eliminates obviously unstable candidates. Surviving candidates are evaluated by an ensemble of GNN models for target properties. The top 1% are queued for DFT validation (Quantum ESPRESSO or GPAW, ~1-24 hours/structure depending on cell size).

**Compare:** Predicted properties are compared against the user-specified target property window. A fitness score combines multiple objectives using scalarization (weighted sum) or Pareto dominance (if multi-objective mode is active). Fitness scores are logged with full provenance: which model predicted each property, what uncertainty estimate was provided, and what the DFT result was (if computed).

**Learn:** Newly DFT-validated results are added to the training set. The GNN ensemble is fine-tuned (not retrained from scratch) using the new data, with particular emphasis on the chemical space where the current search is focused. This constitutes online learning within the discovery campaign.

**Correct:** The search distribution is adjusted based on which regions of chemical/structural space yielded the best fitness scores. For evolutionary search, this means biasing mutation/crossover operators toward promising subspaces. For diffusion models, this means adjusting the conditioning vector.

**Audit trail:** Every iteration is logged as an immutable record: `{iteration_id, candidates[], predictions[], dft_results[], fitness_scores[], model_version, timestamp}`. This enables full reproducibility — any discovery can be traced back through its entire computational genealogy.

**Convergence criteria:** The loop terminates when: (a) a candidate exceeds all target property thresholds, (b) a maximum iteration budget is exhausted, (c) the fitness improvement rate drops below a threshold for N consecutive iterations (stagnation detection), or (d) the user manually stops the campaign.

### 4.2 Multi-Objective Pareto Optimization

Real materials discovery almost always involves trade-offs. A thermoelectric material needs high Seebeck coefficient AND high electrical conductivity AND low thermal conductivity — optimizing one often degrades another. Single-objective optimization is insufficient.

**Pareto front construction:**
- Maintain a non-dominated set (Pareto front) of candidate materials across all objectives
- Use NSGA-III (Non-dominated Sorting Genetic Algorithm III, Deb & Jain 2014) for evolutionary multi-objective optimization with 3+ objectives
- Reference-point-based selection ensures uniform coverage of the Pareto front, preventing clustering in easy-to-optimize regions
- Implementation via DEAP library (`deap.tools.selNSGA3`) with custom material-specific mutation operators

**Objective specifications:**

Users define objectives as:
```
objectives:
  - property: band_gap
    target: 1.5 eV
    type: minimize_distance   # want exactly 1.5 eV
    weight: 1.0
  - property: bulk_modulus
    target: 200 GPa
    type: maximize             # want as high as possible, 200 is minimum
    weight: 0.8
  - property: formation_energy
    target: -1.0 eV/atom
    type: minimize             # want as negative as possible (stable)
    weight: 1.0
```

**Trade-off visualization:**
- 2D Pareto front plots for any pair of objectives (interactive, Plotly-based)
- 3D Pareto surface for three objectives (Three.js visualization)
- Parallel coordinates plot for 4+ objectives showing all candidates colored by dominance rank
- Hypervolume indicator tracking convergence of the Pareto front over iterations

**Decision support:**
- Knee-point detection on the Pareto front (highest curvature = best compromise)
- TOPSIS (Technique for Order of Preference by Similarity to Ideal Solution) ranking with user-adjustable weights
- "What-if" analysis: relax one constraint and see how the Pareto front expands

### 4.3 Blockchain Integration (Unique to SOST)

This is the single most differentiating feature of the SOST Materials Engine compared to every competitor. No existing materials discovery platform has any blockchain integration whatsoever.

**4.3.1 Proof of Discovery**

When a user's discovery campaign identifies a novel material that (a) is not present in any ingested database, (b) passes DFT stability validation, and (c) has at least one predicted property exceeding a significance threshold, a Proof-of-Discovery transaction is constructed:

```
PoD Transaction:
  Input:  user's SOST UTXO (fee payment)
  Output[0]: OP_RETURN + Capsule v1 payload containing:
    - SHA-256(composition || space_group || lattice_params || wyckoff_positions)
    - Predicted properties (compressed)
    - Model version hash
    - Discovery campaign ID
    - Timestamp (block height)
  Output[1]: change back to user

Capsule payload (<=243 bytes):
  [4 bytes]  discovery_type (0x01 = novel composition, 0x02 = novel structure, 0x03 = novel property)
  [32 bytes] material_hash = SHA-256(canonical CIF representation)
  [32 bytes] properties_hash = SHA-256(JSON properties blob)
  [8 bytes]  model_version (first 8 bytes of SHA-256 of model weights)
  [4 bytes]  campaign_id
  [remaining] compressed property summary (band_gap, formation_energy as Q16.16 fixed-point)
```

This creates an immutable, timestamped, publicly verifiable record of discovery priority. Unlike a preprint or patent filing, this record cannot be backdated, altered, or disputed — it exists in the SOST blockchain with the same finality guarantees as any SOST transaction.

**4.3.2 Discovery Attribution and Incentives**

- Discoverers receive on-chain credit: their SOST address is permanently linked to the material_hash
- If the material is later experimentally synthesized and validated (confirmed by an oracle or manual attestation), the discoverer's on-chain record serves as proof of computational prediction priority
- Future: SOST token bounties for discoveries in targeted property spaces (e.g., "first stable material with band gap 1.3-1.5 eV and bulk modulus > 300 GPa earns 10 SOST")

**4.3.3 Decentralized Verification**

- Any node can independently verify a Proof-of-Discovery by: (1) parsing the Capsule payload, (2) retrieving the full material specification from the Materials Engine API, (3) running the same GNN prediction with the specified model version, (4) confirming the properties hash matches
- This enables trust-minimized verification without relying on the Materials Engine operator

**4.3.4 Community Compute Marketplace**

- Researchers publish discovery campaigns as on-chain bounties (Capsule payload specifying target properties + SOST reward)
- Miners and compute providers claim tasks, run simulations, and submit results
- SOST escrow ensures payment only upon verified result submission
- Task verification: multiple independent workers must produce consistent results (Byzantine fault tolerance via majority agreement)
- Compute pricing: market-driven, denominated in SOST per CPU-hour or per DFT-relaxation

### 4.4 Generative + Predictive Hybrid

The engine combines generative and predictive models in a unified pipeline, unlike competitors that offer only one or the other.

**4.4.1 Crystal Structure Generation (Diffusion Model)**

Architecture based on CDVAE with significant extensions:
- Denoising diffusion on atom positions (continuous) + atom types (discrete, D3PM) + lattice parameters (continuous)
- Conditional generation via classifier-free guidance: train with property labels dropped 10% of the time, at inference use guidance scale w=2.0 to steer generation toward target properties
- Maximum unit cell size: 64 atoms (2x the original CDVAE limit, achieved through improved positional encoding using sinusoidal functions on fractional coordinates)
- Training data: combined Materials Project + JARVIS + AFLOW (after harmonization), ~200K structures
- Training compute: 1x A100 80GB, ~72 hours for full training
- Inference: ~2 seconds per structure on A100, ~30 seconds on CPU

**4.4.2 Property Prediction (GNN Ensemble)**

Ensemble of three complementary GNN architectures:
- **ALIGNN** (Atomistic Line Graph Neural Network): operates on both atom graph and bond-angle line graph. Best single-model accuracy on MatBench. Pre-trained weights from JARVIS team, fine-tuned on combined dataset. Predicts: formation energy, band gap, elastic moduli, dielectric constant.
- **M3GNet** (Materials 3-body Graph Network): successor to MEGNet, includes 3-body interactions. Universal potential mode for structure relaxation. Pre-trained on Materials Project. Predicts: energy, forces, stress (enables structure relaxation without DFT).
- **CHGNet** (Crystal Hamiltonian Graph Neural Network): charge-informed GNN from Berkeley. Tracks magnetic moments and charge states during relaxation. Complements M3GNet for magnetic materials.

Ensemble prediction = weighted average of individual models, with uncertainty estimated as inter-model disagreement (standard deviation across the three predictions). High uncertainty triggers DFT validation.

**4.4.3 Composition Optimization (Evolutionary Algorithm)**

For cases where crystal structure is not the primary variable (e.g., optimizing dopant concentrations in a known host structure):
- Representation: composition vector `[x_1, x_2, ..., x_n]` where `x_i` is the fraction of element `i`
- Constraints: `sum(x_i) = 1`, `x_i >= 0`, optional per-element bounds
- Operators: SBX crossover (simulated binary crossover, eta=20), polynomial mutation (eta=20), constraint repair
- Selection: NSGA-III for multi-objective, tournament for single-objective
- Population: 100 individuals, 200 generations typical
- Implementation: DEAP framework with custom material-specific operators
- Evaluation: GNN ensemble (fast, ~10ms/composition) or DFT (slow, queued)

**4.4.4 Validation Pipeline (DFT Integration)**

Three-tier validation with increasing cost and accuracy:

| Tier | Method | Speed | Accuracy | Cost |
|------|--------|-------|----------|------|
| V1 | GNN ensemble prediction | ~10ms | MAE ~0.05 eV/atom (formation energy) | Free (inference) |
| V2 | M3GNet/CHGNet force-field relaxation | ~10s | Close to DFT for geometry, ~0.03 eV/atom | Minimal (CPU) |
| V3 | Full DFT (QE/GPAW) | 1-24h | Ground truth (within DFT accuracy, ~0.01 eV/atom) | ~$0.50-5.00 per structure (cloud GPU) |

Automated workflow:
1. Generate 1,000 candidates (diffusion model, ~30 min)
2. V1 screen: eliminate unstable candidates (formation energy > 0), keep top 100 (~1 second)
3. V2 relax: force-field relaxation of top 100 structures (~15 min)
4. V3 validate: full DFT on top 10 relaxed structures (~24h, parallelizable)
5. Log results, update training set, retrain ensemble

DFT integration specifics:
- **Quantum ESPRESSO** (open source, GPL): preferred for production. Interface via ASE (`ase.calculators.espresso`). Pseudopotentials: SSSP Efficiency v1.3. k-point mesh: automatic (Monkhorst-Pack, 30/Angstrom density). Job management via `aiida-core` workflow engine.
- **GPAW** (open source, GPL): alternative for smaller cells and molecular systems. PAW + LCAO mode for fast approximate calculations. Grid mode for high-accuracy reference.
- **VASP** (commercial, licensed): available for users with their own license. Interface via `ase.calculators.vasp`. Not bundled with the platform due to license restrictions.

### 4.5 Explainability

Materials science demands explainability — a black-box prediction of "band gap = 1.5 eV" is useless without understanding which structural or compositional features drive that prediction.

**4.5.1 Structure-Property-Application Knowledge Graph**

A graph database (Neo4j or Apache AGE on PostgreSQL) connecting:
- **Material nodes**: composition, structure, space group, point group
- **Property nodes**: band gap, formation energy, bulk modulus, etc. (with values and uncertainty)
- **Feature nodes**: structural motifs (octahedral coordination, layered structure, cage structure), electronic features (d-electron count, electronegativity difference), compositional features (Herfindahl index, electronegativity variance)
- **Application nodes**: solar cell absorber, thermoelectric, battery cathode, catalyst, structural material
- **Edges**: "has_property", "exhibits_feature", "suitable_for", "similar_to" (cosine similarity of Material DNA vectors > 0.9)

This enables queries like: "What structural features do all materials with band gap 1.3-1.5 eV AND high dielectric constant share?" — answerable by graph traversal, not just ML prediction.

**4.5.2 Feature Attribution for Predictions**

For every GNN prediction, the system provides:
- **Integrated Gradients** (Sundararajan et al. 2017): attribute the predicted property value to input features (atom types, bond lengths, angles). Implementation via Captum library (`captum.attr.IntegratedGradients`) adapted for graph inputs.
- **GNNExplainer** (Ying et al. 2019): identify the subgraph (atoms + bonds) most responsible for the prediction. Shows, for example, that the predicted high band gap is driven by the oxygen coordination environment around the transition metal site.
- **Attention weight visualization**: for transformer-based models, display attention maps showing which atom-atom interactions the model considers most important.

Output format: annotated 3D crystal structure where each atom/bond is colored by its attribution score (red = increases predicted property, blue = decreases it).

**4.5.3 Natural Language Explanations**

Template-based explanation generation (not LLM — deterministic and reproducible):

```
"The predicted band gap of 2.1 eV for Sr2TiO4 is primarily attributed to:
 (1) the Ti-O octahedral coordination (attribution: +0.8 eV),
 (2) the large electronegativity difference between Ti (1.54) and O (3.44)
     (attribution: +0.6 eV),
 (3) the layered Ruddlesden-Popper structure (attribution: +0.4 eV).
 Confidence: HIGH (87%) — 342 similar structures in training data within
 cosine distance 0.1 of this material's DNA vector."
```

These explanations are generated automatically for every prediction and stored alongside the numerical result. They are composed from a library of ~200 structure-property relationship templates derived from materials science textbook knowledge, parameterized by the actual attribution scores.

---

## 5. Innovative Concepts

### 5.1 Material DNA

A compact, fixed-length vector encoding that uniquely represents any crystalline material regardless of unit cell size. The Material DNA vector is 256-dimensional: the first 64 dimensions encode composition (element fractions weighted by Magpie elemental features), the next 64 encode structure (radial distribution function sampled at 64 evenly spaced bins from 0 to 10 Angstroms), the next 64 encode symmetry (one-hot space group + point group + Bravais lattice), and the final 64 are the latent representation from a pre-trained ALIGNN encoder. This provides a universal fingerprint for similarity search, clustering, and retrieval — any two materials can be compared by cosine distance of their DNA vectors. The encoding is deterministic (same material always produces the same vector) and invertible for the composition and structure components (the latent component is one-way).

### 5.2 Evolutionary Materials

Genetic algorithms where materials are treated as organisms that mutate and reproduce according to Darwinian fitness. A "genome" is the composition vector + Wyckoff position parameters. Mutation operators include element substitution (swap one element for another in the same group), composition perturbation (adjust stoichiometric ratios by +/-5%), and structural mutation (distort lattice parameters or shift Wyckoff positions). Crossover operators include composition interpolation (convex combination of two parent compositions) and structure swapping (take lattice from one parent, atomic sites from another). Fitness is evaluated by the GNN ensemble and is defined by the user's multi-objective target. Population dynamics include speciation (materials cluster by space group, preventing structural monoculture) and niching (Pareto front sharing to maintain diversity).

### 5.3 Inverse Design Pipeline

The user specifies a target property profile — for example, "band gap between 1.3 and 1.6 eV, bulk modulus above 150 GPa, formation energy below -1.0 eV/atom, must contain only earth-abundant elements (no rare earths, no platinum group)" — and the system generates candidate materials satisfying all constraints. The pipeline works in three stages: (1) database search for known materials within relaxed constraints, (2) conditional diffusion model generation of novel structures targeting the property window, (3) evolutionary refinement of the top candidates. Each stage narrows the candidate pool while increasing prediction confidence. The output is a ranked list of 10-50 candidates with predicted properties, confidence scores, synthetic feasibility scores, and estimated raw material costs.

### 5.4 Materials Genealogy Tree

Every discovered material maintains a provenance chain showing how it was derived from its predecessors. If evolutionary optimization produced a novel composition by mutating Sr2TiO4 (parent 1) and crossing with BaTiO3 (parent 2) to produce SrBaTi2O7 (offspring), the genealogy tree records this relationship with the specific operators applied. Over time, this creates a rich evolutionary history of the discovery process, enabling researchers to understand why certain compositional regions are fruitful and to replay successful evolutionary trajectories in new chemical systems. The tree is visualized as an interactive graph where nodes are materials, edges are evolutionary operations, and node color indicates fitness.

### 5.5 Confidence Scoring

Every prediction includes a calibrated confidence score that reflects how well the training data covers the region of chemical space where the prediction is made. The score is computed from three signals: (1) GNN ensemble disagreement — if all three models agree, confidence is high; if they diverge, it is low, (2) distance to nearest training example in Material DNA space — predictions far from any training point are flagged as extrapolation, (3) epistemic uncertainty from Monte Carlo dropout (run inference 20 times with dropout active, measure prediction variance). The three signals are combined via a calibrated logistic regression model trained on a held-out validation set where true DFT values are known. The output is a percentage: "87% confidence that band gap is 1.5 +/- 0.2 eV." Predictions below 50% confidence are automatically flagged for DFT validation.

### 5.6 Synthetic Feasibility Score

A predicted material is useless if it cannot be manufactured. The Synthetic Feasibility Score (SFS) estimates the likelihood that a candidate material can be synthesized using known techniques. The score incorporates: (1) thermodynamic stability — formation energy relative to the convex hull (materials on the hull are synthesizable; materials >50 meV/atom above the hull are unlikely), (2) kinetic accessibility — whether known precursors and reaction pathways exist (determined by searching a database of ~500,000 published synthesis recipes extracted from the Inorganic Crystal Structure Database and text-mined literature), (3) historical synthesis success rate for materials in the same structural prototype family, (4) temperature and pressure requirements estimated from phase diagrams. The score ranges from 0 (impossible with current technology) to 100 (routine synthesis, multiple published methods).

### 5.7 Cost-Aware Discovery

Discovery is meaningless if the resulting material costs $10,000/gram to produce. The engine incorporates raw material costs from real-time commodity pricing (London Metal Exchange for metals, USGS Mineral Commodity Summaries for non-metals) and estimates total production cost by combining: (1) raw element cost per kg (weighted by composition fractions), (2) estimated synthesis energy cost (furnace time x temperature x energy price), (3) precursor processing cost (if rare or toxic precursors are required), (4) scaling factor based on synthesis complexity (sol-gel = 1.0x, high-pressure synthesis = 5.0x, molecular beam epitaxy = 50x). Users can set a maximum cost threshold, and the engine excludes candidates above it. This prevents the common failure mode where a computationally predicted "wonder material" turns out to be economically impractical.

### 5.8 Environmental Impact Score

Each candidate material receives an estimated carbon footprint for its synthesis, measured in kg CO2 per kg of material produced. The calculation includes: (1) embodied carbon of raw elements (from ecoinvent database LCA data), (2) energy consumption of the synthesis process (estimated from process type and temperature/duration), (3) waste stream toxicity (penalty for synthesis routes producing hazardous byproducts), (4) recyclability at end-of-life. The score enables environmentally conscious materials selection — when two candidates have similar performance, the one with lower environmental impact should be preferred. This is particularly relevant for battery materials, where the environmental cost of mining lithium, cobalt, and nickel is a growing concern.

### 5.9 Digital Twin Materials Lab

A full computational simulation of the synthesis process before any real laboratory work begins. Given a candidate material and a proposed synthesis route (e.g., solid-state reaction at 1200C for 12h), the digital twin simulates: (1) thermodynamic phase evolution using CALPHAD (Calculation of Phase Diagrams) models, (2) reaction kinetics using Arrhenius-parameterized rate equations, (3) grain growth and microstructure evolution using phase-field models, (4) final material properties predicted from the simulated microstructure. This allows researchers to optimize synthesis conditions computationally (temperature profile, atmosphere, precursor ratios) before committing real laboratory resources. The simulation results are stored as provenance data alongside the material record.

### 5.10 Collaborative Discovery Protocol

A structured protocol for multi-researcher evaluation of candidate materials. When a discovery campaign produces promising candidates, the researcher can publish them to a shared evaluation workspace. Other researchers can: (1) vote on which candidates to prioritize for DFT validation, (2) contribute additional property predictions from their own models, (3) flag potential issues (e.g., "this structure is known to be dynamically unstable at room temperature"), (4) claim candidates for experimental synthesis. All contributions are tracked on-chain via SOST Capsule transactions, ensuring attribution is permanent. Consensus scoring: a candidate's overall priority score combines automated fitness with human expert votes, weighted by each voter's track record (previous correct predictions increase vote weight).

### 5.11 Materials Aging Predictor

Predicting how material properties degrade over time under operational conditions. The predictor uses: (1) thermodynamic driving force for decomposition (formation energy relative to competing phases at operating temperature), (2) diffusion kinetics (estimated activation energies for relevant diffusion mechanisms from the NIST Diffusion Data Center), (3) corrosion susceptibility (Pourbaix diagram analysis for aqueous environments), (4) radiation damage susceptibility (displacement energy thresholds from literature). The output is an estimated property lifetime curve: "band gap degrades by <5% after 10 years at 85C and 85% relative humidity" or "structural integrity compromised after 2 years at 500C due to grain boundary diffusion." This is critical for applications like photovoltaics (25-year warranty required), nuclear materials (decades of operation), and aerospace (thermal cycling endurance).

### 5.12 Cross-Domain Transfer

Insights from one materials domain (e.g., semiconductor band gap engineering) can accelerate discovery in an unrelated domain (e.g., battery cathode voltage optimization). The mechanism is transfer learning on Material DNA embeddings: the ALIGNN encoder pre-trained on formation energy (universal property, all materials) produces embeddings that capture fundamental structure-property relationships. These embeddings can be fine-tuned for any specific property with as few as 100-500 labeled examples. This means that breakthroughs in understanding what makes a good thermoelectric (Seebeck coefficient, thermal conductivity) can inform the search for good piezoelectrics (structural distortion modes, polar character) because both properties correlate with specific bonding motifs captured in the shared embedding space. The engine actively identifies cross-domain opportunities by clustering Material DNA vectors and flagging when a high-performing material in one domain has a close neighbor that has been under-explored in another domain.

### 5.13 Adversarial Validation

Systematic identification of model blind spots by generating adversarial examples — materials that are designed to fool the GNN ensemble. The approach uses gradient-based perturbation of the Material DNA vector to find directions in chemical space where the model is most uncertain or most wrong. Concretely: take a well-predicted material, perturb its composition by epsilon in the direction of maximum loss gradient, and check whether the perturbed composition (a) is physically plausible and (b) has a drastically different DFT-computed property than the model predicts. The collection of adversarial examples defines the model's failure modes. These are then prioritized for DFT computation and added to the training set, systematically patching the model's weakest areas. This active learning strategy is more efficient than random sampling because it targets exactly the regions where the model needs improvement.

### 5.14 Autonomous Lab Integration

Direct connection to robotic synthesis laboratories (A-Lab at LBNL, or future SOST-partnered labs) for closed-loop experimental validation. The integration pipeline: (1) Materials Engine identifies top candidates from computational screening, (2) synthesis recipe generator produces a detailed protocol (precursors, amounts, temperatures, durations, atmosphere) compatible with the target robotic platform, (3) protocol is transmitted via API to the lab scheduler, (4) robot executes synthesis and characterization (XRD, SEM-EDS, electrical measurements), (5) experimental results are returned to the Materials Engine and compared with computational predictions, (6) discrepancies between prediction and experiment become high-value training data that rapidly improves the models. This closes the loop between computation and experiment, which is the fundamental bottleneck in materials discovery — today it takes 15-20 years to move a material from computational prediction to commercial product.

### 5.15 Materials Constitution

An immutable on-chain document, stored as a series of SOST Capsule transactions, that governs the rules of discovery attribution, data sharing, and community governance for the Materials Engine. The Constitution specifies: (1) discovery priority is determined exclusively by block height of the Proof-of-Discovery transaction (earliest block wins), (2) all data generated by the engine is open access (CC-BY-4.0) and cannot be paywalled or restricted after publication, (3) model weights are published on-chain (hash of weights) with each version update, enabling anyone to verify predictions, (4) disputes over attribution are resolved by a deterministic protocol examining the blockchain record, not by any human committee. The Constitution itself can only be amended by a supermajority (>67%) of active Materials Engine users voting via signed SOST transactions, ensuring that governance is decentralized and community-driven rather than controlled by a single entity.

### 5.16 Phase-Aware Screening

Most discovery pipelines consider only the ground-state (0 K) properties of materials. Phase-Aware Screening additionally checks whether a candidate material undergoes phase transitions at relevant operating temperatures. The screener queries computed phonon data (from JARVIS and AFLOW) and published phase diagrams to determine if structural transitions (e.g., cubic-to-tetragonal) occur between 200K and 1000K. Materials with transitions near room temperature are flagged, as their properties may differ drastically between the computed ground state and the operational state. This prevents the common failure mode of predicting excellent properties at 0 K that vanish at room temperature due to a structural phase transition.

### 5.17 Defect-Tolerant Predictions

Real materials contain defects (vacancies, interstitials, antisites, grain boundaries) that are absent from idealized DFT calculations. The engine provides defect-tolerant property estimates by: (1) computing defect formation energies for the most common point defects using the Freysoldt correction scheme, (2) estimating equilibrium defect concentrations at the target operating temperature via the law of mass action, (3) predicting the effect of equilibrium defect concentrations on target properties using trained defect-property models. This adds realism to predictions — a predicted band gap of 1.5 eV in the pristine crystal might be 1.3 eV with realistic vacancy concentrations, which could be the difference between a viable and non-viable solar absorber.

---

## 6. Technology Stack

### 6.1 Core Platform

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Language | Python | 3.11+ | Core platform, ML training, API |
| ML Framework | PyTorch | 2.2+ | GNN training, diffusion model, inference |
| Graph Neural Networks | PyTorch Geometric (PyG) | 2.5+ | Graph construction, message passing, pooling |
| Graph Neural Networks (alt) | DGL (Deep Graph Library) | 2.1+ | Alternative backend for ALIGNN (uses DGL natively) |
| Materials I/O | pymatgen | 2024.2+ | Structure parsing, CIF/POSCAR I/O, phase diagrams, symmetry |
| Atomic Simulation | ASE (Atomic Simulation Environment) | 3.23+ | Calculator interface for DFT codes, structure manipulation |
| Diffusion Models | Custom (PyTorch) | N/A | Crystal structure generation via denoising score matching |
| VAE | Custom (PyTorch) | N/A | Latent space encoding (CDVAE-based architecture) |

### 6.2 ML Models

| Model | Source | Input | Output | Use Case |
|-------|--------|-------|--------|----------|
| ALIGNN | NIST/JARVIS (`alignn` package v2024.1+) | Crystal structure (CIF/POSCAR) | Formation energy, band gap, elastic moduli, 50+ properties | Primary property predictor |
| M3GNet | Materials Virtual Lab (`matgl` package v0.9+) | Crystal structure | Energy, forces, stress (universal potential) | Structure relaxation without DFT |
| CHGNet | Berkeley (`chgnet` package v0.3+) | Crystal structure | Energy, forces, stress, magnetic moments | Magnetic materials relaxation |
| CGCNN | Xie & Grossman (`cgcnn` GitHub) | Crystal structure | Formation energy, band gap | Baseline predictor, ensemble member |
| SchNet | PyG built-in (`torch_geometric.nn.SchNet`) | Crystal structure | Energy, forces | Molecular dynamics, small molecules |
| DimeNet++ | PyG built-in (`torch_geometric.nn.DimeNetPlusPlus`) | Crystal structure | Energy, forces | High-accuracy molecular properties |

### 6.3 Optimization

| Library | Version | Purpose |
|---------|---------|---------|
| DEAP | 1.4+ | Evolutionary algorithms: NSGA-III, tournament selection, SBX crossover, polynomial mutation |
| Ax (Adaptive Experimentation) | 0.4+ | Bayesian optimization with Gaussian processes for hyperparameter tuning and small-budget optimization |
| Optuna | 3.6+ | Hyperparameter optimization for ML model training (TPE sampler, pruning) |
| scipy.optimize | 1.12+ | Local optimization (L-BFGS-B, Nelder-Mead) for structure relaxation post-evolutionary search |

### 6.4 DFT Integration

| Code | License | Interface | Use Case |
|------|---------|-----------|----------|
| Quantum ESPRESSO | GPL v2 | ASE calculator (`ase.calculators.espresso.Espresso`) | Primary DFT engine (open source) |
| GPAW | GPL v3 | ASE calculator (`ase.calculators.gpaw.GPAW`) | Fast approximate DFT (LCAO mode), high-accuracy reference (grid mode) |
| VASP | Commercial | ASE calculator (`ase.calculators.vasp.Vasp`) | Available for users with own license |
| AiiDA | MIT | `aiida-core` v2.5+ | Workflow management, provenance tracking, job scheduling for DFT calculations |
| Pseudopotentials | N/A | SSSP Efficiency v1.3 (for QE), GBRV (for QE), PAW (for GPAW) | Validated pseudopotential sets |

### 6.5 Database and Storage

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Primary database | PostgreSQL 16 | Materials metadata, properties, users, campaigns |
| Vector store | pgvector extension (v0.6+) | Material DNA embeddings for similarity search (HNSW index) |
| Object storage | MinIO (S3-compatible) | CIF files, DFT output files, model checkpoints |
| Cache | Redis 7.2+ | API response caching, rate limiting, job queue |
| Search index | PostgreSQL full-text + trigram | Composition search, formula matching |
| Graph database | Apache AGE (PostgreSQL extension) | Knowledge graph (structure-property-application relationships) |

### 6.6 API and Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API framework | FastAPI 0.110+ | REST API with automatic OpenAPI docs, async support |
| Task queue | Celery 5.3+ with Redis broker | Async DFT job submission, GNN inference queuing, long-running campaigns |
| Worker pool | Celery workers (CPU) + Ray (GPU) | CPU workers for data processing, GPU workers for GNN inference and training |
| Authentication | JWT tokens + SOST address signature verification | API access control, escrow tier verification |
| Rate limiting | Redis-based token bucket | Per-tier rate limits (Tier 1: 100 req/min, Tier 2: 500 req/min, Tier 3: 2000 req/min) |
| Serialization | msgpack (binary) + JSON (API) | Efficient internal communication, standard API format |

### 6.7 Frontend and Visualization

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web framework | React 18+ | Single-page application |
| 3D visualization | Three.js + react-three-fiber | Crystal structure visualization, Pareto front 3D plots |
| Charts | Plotly.js | Property plots, convergence curves, parallel coordinates |
| Crystal renderer | Custom (Three.js) | Atom spheres, bond sticks, unit cell wireframe, symmetry elements |
| Structure editor | Custom (Three.js) | Interactive modification of crystal structures (drag atoms, adjust lattice) |

### 6.8 Infrastructure Requirements

**Development environment:**
- 1x machine with NVIDIA GPU (RTX 3090 or better, 24GB VRAM minimum)
- 64 GB RAM (for pymatgen phase diagram construction with large chemical systems)
- 1 TB SSD (database + DFT results + model checkpoints)
- Ubuntu 22.04 or 24.04 LTS

**Production environment (minimum viable):**
- 1x NVIDIA A100 40GB (GNN training and inference)
- 128 GB RAM (database + in-memory caching)
- 2 TB NVMe SSD (fast storage for active data)
- 4 TB HDD (archive storage for DFT results)
- 16-core CPU (Celery workers, DFT calculations via QE)
- Estimated cloud cost: ~$3,000/month (AWS p4d.xlarge equivalent)

**Production environment (full scale):**
- 4x NVIDIA A100 80GB (parallel GNN training, large diffusion model)
- 512 GB RAM
- 10 TB NVMe SSD
- 50 TB HDD (full DFT archive)
- 64-core CPU (parallel DFT workers)
- Estimated cloud cost: ~$15,000/month

**Storage breakdown:**
- Materials Project data: ~50 GB (JSON + CIF)
- JARVIS data: ~30 GB
- AFLOW data: ~200 GB (3.5M entries)
- NOMAD subset: ~100 GB (curated subset only)
- OQMD data: ~30 GB (SQL dump)
- Model checkpoints: ~20 GB (all models, all versions)
- DFT results (generated): ~2 TB after 12 months of operation
- Total: ~2.5 TB active, growing ~2 TB/year

---

## 7. Roadmap

### Phase 1: Foundation (Months 0-3)

**Objective:** Ingest existing data, train baseline models, deploy searchable API.

**Month 1: Data Ingestion**
- [ ] Set up PostgreSQL 16 + pgvector on production server
- [ ] Write Materials Project ingestion pipeline using `mp-api` client
  - Ingest all ~154K materials: composition, structure (CIF), formation energy, band gap, elastic tensor
  - Store raw CIF in MinIO, parsed properties in PostgreSQL
  - Estimated time: 3-4 days (API rate limit: 40 req/s, ~4K materials/hour with property fetching)
- [ ] Write JARVIS ingestion pipeline using `jarvis-tools`
  - Ingest all ~80K materials with available properties
  - Download bulk JSON from Figshare (faster than API for full dataset)
  - Estimated time: 1-2 days
- [ ] Write AFLOW ingestion pipeline using AFLUX API
  - Ingest top 200K entries (prioritize entries with elastic data and band gap)
  - Estimated time: 5-7 days (AFLOW API is slower, pagination required)
- [ ] Build cross-database deduplication pipeline
  - Match materials across databases by reduced composition + space group
  - ~60K overlapping entries between MP and OQMD, ~30K between MP and JARVIS
  - Create unified material IDs with source provenance
- [ ] Compute Material DNA vectors for all ingested materials
  - 256-dimensional vector per material
  - Build HNSW index in pgvector for similarity search (ef_construction=128, m=32)

**Month 2: Baseline Models**
- [ ] Train CGCNN on formation energy prediction
  - Training data: Materials Project + JARVIS (combined, deduplicated), ~200K structures
  - Architecture: 3 convolutional layers, 64-dimensional atom features, 128-dimensional crystal features
  - Training: 300 epochs, Adam optimizer, lr=1e-3 with cosine annealing, batch size 256
  - Target performance: MAE < 0.06 eV/atom on held-out 10% test set
  - Training time: ~8 hours on 1x A100
- [ ] Fine-tune pre-trained ALIGNN for band gap prediction
  - Start from JARVIS pre-trained weights (`alignn` package)
  - Fine-tune on combined MP+JARVIS band gap data (~120K materials with band gap values)
  - Target performance: MAE < 0.3 eV (band gap) on held-out test set
  - Training time: ~4 hours on 1x A100
- [ ] Set up M3GNet from `matgl` for structure relaxation
  - Use pre-trained universal potential (no training needed)
  - Validate on 1000 random MP structures: compare relaxed geometry with MP DFT geometry
  - Target: <0.05 Angstrom average position deviation from DFT
- [ ] Build GNN ensemble inference pipeline
  - Accept CIF/POSCAR input → parse with pymatgen → build graph → run all 3 models → aggregate predictions
  - Report mean prediction + uncertainty (inter-model standard deviation)
  - Inference latency target: <100ms per structure (GPU), <2s per structure (CPU)

**Month 3: API and Inverse Search**
- [ ] Deploy FastAPI REST API with endpoints:
  - `POST /predict` — submit structure, get property predictions
  - `GET /search` — inverse search: specify property ranges, get ranked candidates
  - `GET /material/{id}` — retrieve full material record
  - `GET /similar/{id}` — find similar materials by Material DNA cosine distance
  - `GET /status` — API health, model versions, database statistics
- [ ] Implement inverse search engine
  - PostgreSQL range queries on indexed property columns
  - Compound queries: `band_gap BETWEEN 1.3 AND 1.6 AND formation_energy < -1.0 AND bulk_modulus > 150`
  - Ranked by multi-criteria distance from target property centroid
  - Pagination with cursor-based keyset pagination (not OFFSET)
- [ ] Implement SOST address authentication
  - User signs a challenge message with their SOST private key
  - Server verifies signature against the claimed address using libsecp256k1
  - JWT token issued with escrow tier level (initially: all users get Tier 1 for free during beta)
- [ ] Write API documentation (OpenAPI/Swagger auto-generated by FastAPI)
- [ ] Deploy monitoring (Prometheus + Grafana for API latency, model inference times, database query performance)

**Phase 1 deliverable:** A working API that can search ~300K materials by property ranges and predict properties of user-submitted structures using a 3-model GNN ensemble. No generative capabilities yet.

### Phase 2: Intelligence (Months 3-6)

**Objective:** Add ALIGNN and MEGNet ensemble, implement evolutionary search, build multi-objective optimization, launch proof-of-discovery.

**Month 4: Enhanced ML Models**
- [ ] Train ALIGNN from scratch on combined dataset (not just fine-tune)
  - Full training on ~300K structures, 12 target properties simultaneously (multi-task)
  - Properties: formation energy, band gap (PBE), band gap (MBJ), bulk modulus, shear modulus, Poisson ratio, dielectric constant, piezoelectric constant, Seebeck coefficient, power factor, solar efficiency (SLME), thermoelectric ZT
  - Multi-task training with uncertainty weighting (Kendall et al. 2018)
  - Training time: ~48 hours on 1x A100
  - Target performance: match or exceed published ALIGNN benchmarks on MatBench
- [ ] Integrate CHGNet for magnetic materials
  - Use pre-trained weights from Berkeley team
  - Add magnetic moment to the prediction output for materials containing Fe, Co, Ni, Mn, Cr
- [ ] Build uncertainty quantification pipeline
  - Monte Carlo dropout: 20 forward passes with dropout rate 0.1
  - Deep ensemble: train 5 ALIGNN models with different random seeds
  - Calibrate uncertainty estimates on held-out validation set
  - Target: 90% of true values fall within predicted 90% confidence interval

**Month 5: Evolutionary Composition Search**
- [ ] Implement evolutionary composition optimizer using DEAP
  - Genome: composition vector [x_1, ..., x_n] with element selection
  - Fitness: GNN ensemble prediction of user-specified target properties
  - Operators: SBX crossover (eta=20), polynomial mutation (eta=20), element swap mutation
  - Constraints: charge neutrality, Pauling electronegativity rules, earth-abundance filter (optional)
  - Selection: NSGA-III with 91 reference points (for 3 objectives)
  - Population: 100, generations: 200, runtime: ~30 minutes per campaign on GPU
- [ ] Implement multi-objective Pareto optimization
  - NSGA-III implementation with 3-15 objectives
  - Pareto front storage and retrieval per campaign
  - Hypervolume indicator computation (exact for <=4 objectives, Monte Carlo approximation for more)
  - Knee-point detection via maximum curvature on 2D projections
- [ ] Build campaign management system
  - Create campaign with target properties, constraints, and budget (max iterations)
  - Async execution via Celery + Redis
  - Real-time progress updates via WebSocket
  - Campaign state persistence: can resume after interruption

**Month 6: Blockchain Proof-of-Discovery**
- [ ] Implement Proof-of-Discovery transaction construction
  - Use SOST Capsule v1 protocol (12-byte header + up to 243-byte body)
  - Payload format: discovery_type (4B) + material_hash (32B) + properties_hash (32B) + model_version (8B) + campaign_id (4B) + compressed properties (remaining)
  - Transaction construction via `sost-cli` RPC calls
- [ ] Build discovery registry
  - PostgreSQL table: (material_hash, discoverer_address, block_height, tx_id, campaign_id, properties_json)
  - Index on material_hash for uniqueness check before submitting new discoveries
  - Query: "has this material been discovered before?" in O(1) via hash lookup
- [ ] Implement discovery verification endpoint
  - `GET /verify/{tx_id}` — parse Capsule from blockchain, re-run prediction, compare hashes
  - Returns: VERIFIED (hashes match), MISMATCH (hashes differ), or NOT_FOUND (tx not on chain)
- [ ] Deploy on SOST mainnet (not testnet — real immutable records)

**Phase 2 deliverable:** Multi-objective evolutionary composition search with on-chain proof-of-discovery. Users can launch discovery campaigns targeting multiple properties simultaneously and claim priority for novel materials on the SOST blockchain.

### Phase 3: Generation (Months 6-12)

**Objective:** Train crystal structure diffusion model, implement full inverse design pipeline, add DFT validation, launch community compute.

**Months 7-8: Crystal Structure Diffusion Model**
- [ ] Prepare training data
  - Filter combined database for structures with <=64 atoms/cell, all properties computed
  - Data augmentation: apply all symmetry operations to create equivalent representations
  - Train/val/test split: 80/10/10, stratified by space group
  - Estimated training set: ~150K structures
- [ ] Implement diffusion model architecture
  - Atom type diffusion: D3PM (discrete diffusion, Austin et al. 2021) on element types
  - Position diffusion: continuous denoising score matching on fractional coordinates
  - Lattice diffusion: continuous denoising on 6 lattice parameters (a, b, c, alpha, beta, gamma)
  - Score network: equivariant GNN (SE(3)-transformer, Fuchs et al. 2020) for position, MLP for lattice
  - Conditioning: concatenate target property vector to node/graph features (classifier-free guidance)
- [ ] Train diffusion model
  - 1000 diffusion steps, cosine noise schedule
  - Training: 500 epochs, batch size 64, lr=1e-4 with warmup, gradient clipping at 1.0
  - Training time: ~72 hours on 1x A100 80GB (memory-intensive due to large graphs)
  - Validation: generate 10K structures, evaluate validity (reasonable interatomic distances, charge-balanced composition), uniqueness, and property accuracy

**Months 9-10: Inverse Design Pipeline and DFT Validation**
- [ ] Build end-to-end inverse design pipeline
  - Input: target property specification (JSON)
  - Step 1: Database search (existing materials within relaxed constraints)
  - Step 2: Conditional diffusion generation (1000 novel candidates targeting properties)
  - Step 3: GNN ensemble screening (keep top 100 by predicted fitness)
  - Step 4: M3GNet force-field relaxation of top 100 (refine structures)
  - Step 5: Evolutionary refinement of top 20 (composition tweaks)
  - Step 6: DFT validation of top 5 (Quantum ESPRESSO, full structural relaxation + property calculation)
  - Output: ranked list with predicted properties, confidence, SFS, cost estimate, DFT-validated properties
- [ ] Deploy Quantum ESPRESSO integration
  - Install QE 7.3+ on compute server
  - ASE calculator interface with automatic input generation
  - SSSP Efficiency v1.3 pseudopotentials
  - AiiDA workflow for job management and provenance
  - Automatic k-point mesh selection (30/Angstrom density)
  - Job timeout: 24 hours per structure, with checkpoint/restart

**Months 11-12: Community Compute Marketplace**
- [ ] Design compute task protocol
  - Task specification: (target_properties, budget_sost, max_compute_hours, deadline_block_height)
  - Worker registration: SOST address + hardware specification (CPU cores, RAM, GPU)
  - Result format: (task_id, worker_address, result_hash, compute_time, proof_of_work)
- [ ] Implement task matching and escrow
  - Researcher deposits SOST escrow proportional to requested compute
  - Workers claim tasks based on hardware compatibility and estimated completion time
  - Multi-worker redundancy: each task assigned to 3 workers for Byzantine fault tolerance
  - Result accepted when 2/3 workers produce matching result hashes (within numerical tolerance)
  - SOST released to workers upon verified completion
- [ ] Build worker client (Python package)
  - `pip install sost-compute-worker`
  - Auto-detects available hardware
  - Runs sandboxed (Docker container) for security
  - Communicates with Materials Engine API for task retrieval and result submission
- [ ] Deploy marketplace beta with invited researchers

**Phase 3 deliverable:** Full inverse design pipeline from target properties to DFT-validated candidates. Community compute marketplace operational in beta. Crystal structure generation via diffusion model.

### Phase 4: Autonomy (Months 12-18)

**Objective:** Self-improving loop operational, autonomous lab connection, full explainability, cross-domain transfer.

**Months 13-14: Self-Improving Loop**
- [ ] Implement continuous learning pipeline
  - DFT validation results automatically added to training set
  - GNN ensemble retrained weekly with accumulated data (incremental training, not from scratch)
  - Model version tracking: each retrained model gets a new version hash committed on-chain
  - Performance tracking: monitor test-set MAE over time; alert if degradation detected
- [ ] Active learning agent
  - Identifies highest-value structures to compute next (max uncertainty + max novelty)
  - Maintains a "frontier" of chemical space regions with sparse training data
  - Automatically submits DFT calculations for frontier materials
  - Budget: up to 100 DFT calculations per week (automated, no human approval needed)

**Months 15-16: Explainability and Knowledge Graph**
- [ ] Deploy Apache AGE graph database
  - Import all materials, properties, structural features, and application tags
  - Build edges: has_property, exhibits_feature, suitable_for, similar_to
  - ~300K material nodes, ~3M property nodes, ~500K feature nodes, ~100 application nodes
  - ~20M edges total
- [ ] Implement feature attribution
  - Integrated Gradients via Captum for all ALIGNN predictions
  - GNNExplainer for subgraph identification
  - Attribution results cached per material-property pair (computed once, served from cache)
- [ ] Build natural language explanation generator
  - Template library: 200+ structure-property relationship templates
  - Parameterized by attribution scores and material features
  - Output: human-readable 3-5 sentence explanation for each prediction

**Months 17-18: Cross-Domain Transfer and Lab Integration**
- [ ] Implement cross-domain transfer learning
  - Train domain-specific heads on shared ALIGNN backbone
  - Domains: thermoelectric, photovoltaic, catalytic, structural, magnetic, superconducting
  - Transfer protocol: freeze backbone, train new head on domain-specific data (few-shot: 100-500 examples)
  - Cross-domain recommendation: "Material X, discovered for solar cells, has a DNA vector 0.92-similar to known thermoelectric Y — consider evaluating thermoelectric properties"
- [ ] Autonomous lab integration API
  - Define synthesis recipe format (JSON: precursors, amounts, temperatures, durations, atmosphere)
  - API endpoint: `POST /synthesize` — submit candidate for robotic synthesis
  - Webhook: receive experimental results (XRD pattern, SEM image, measured properties)
  - Automated comparison: predicted vs measured properties, log discrepancy
  - Integration partner: target A-Lab (LBNL) or similar autonomous synthesis facility
- [ ] Deploy Materials Constitution on-chain
  - Series of Capsule transactions encoding governance rules
  - Voting mechanism for Constitution amendments (signed SOST transactions)
  - Initial Constitution text reviewed by advisory board before deployment

**Phase 4 deliverable:** Self-improving platform that autonomously identifies and fills gaps in its own knowledge. Full explainability for all predictions. Cross-domain discovery recommendations. API-ready connection to autonomous synthesis labs.

---

## 8. Competitive Advantage Matrix

### 8.1 Feature Comparison

| Feature | Materials Project | JARVIS | AFLOW | GNoME | MatterGen | CDVAE | **SOST Engine** |
|---------|------------------|--------|-------|-------|-----------|-------|-----------------|
| **Database size** | 154K | 80K | 3.5M | 2.2M predicted | N/A | N/A | **All combined (~4M+)** |
| **Inverse design** | No | Limited (ALIGNN-based) | No | No | Yes (conditional diffusion) | Latent optimization | **Yes (diffusion + evolutionary + database)** |
| **Generative model** | No | No | No | Predictive only | Yes (diffusion) | Yes (VAE + diffusion) | **Yes (diffusion + VAE + evolutionary)** |
| **Multi-objective optimization** | No | No | No | No | Limited (multi-property conditioning) | No | **Yes (NSGA-III, Pareto front, knee detection)** |
| **On-chain proof of discovery** | No | No | No | No | No | No | **Yes (SOST Capsule, immutable)** |
| **Token incentives** | No | No | No | No | No | No | **Yes (SOST escrow + compute rewards)** |
| **Community compute** | No | No | No | No | No | No | **Yes (marketplace, Byzantine FT)** |
| **Explainability** | No | No | No | No | No | No | **Yes (attribution, knowledge graph, NL)** |
| **Cost-aware discovery** | No | No | No | No | No | No | **Yes (commodity pricing, synthesis cost)** |
| **Environmental scoring** | No | No | No | No | No | No | **Yes (CO2/kg, LCA data)** |
| **Synthetic feasibility** | No | No | No | No | No | No | **Yes (SFS 0-100 score)** |
| **DFT validation pipeline** | Internal only | Internal only | Internal only | Internal only | Internal only | No | **Yes (QE/GPAW, automated)** |
| **Open data** | Yes (CC-BY-4.0) | Yes (public domain) | Yes (CC-BY-4.0) | Partial (data yes, model no) | No | Yes (MIT) | **Yes (CC-BY-4.0, on-chain hash)** |
| **Open source** | pymatgen (BSD) | jarvis-tools (NIST) | aflow (Duke) | No | No | Yes (MIT) | **Yes (planned MIT)** |
| **Confidence scoring** | No | No | No | No | No | No | **Yes (calibrated, 3-signal)** |
| **Cross-domain transfer** | No | No | No | No | No | No | **Yes (shared embeddings)** |
| **Aging prediction** | No | No | No | No | No | No | **Yes (thermodynamic + kinetic)** |
| **Autonomous lab integration** | No | No | No | Indirect (A-Lab) | No | No | **Yes (API-based, planned)** |
| **Decentralized governance** | No | No | No | No | No | No | **Yes (Materials Constitution)** |

### 8.2 Unique Value Propositions

**Why SOST Materials Engine is differentiated from every competitor:**

1. **Blockchain-native discovery attribution.** No other platform provides immutable, decentralized, timestamped proof of computational materials discovery. In a field where priority disputes over who predicted a material first are common and contentious, on-chain proof is a fundamental innovation.

2. **Aggregated data from all major databases.** Every existing platform operates on its own silo. SOST Engine is the first to ingest, harmonize, and cross-reference Materials Project + JARVIS + AFLOW + OQMD + COD in a single searchable system, providing the most comprehensive view of known materials space.

3. **Full-stack discovery: search + predict + generate + validate + explain.** Competitors offer one or two of these capabilities. Materials Project has search. JARVIS has prediction. MatterGen has generation. No platform offers the complete pipeline from target specification to DFT-validated candidates with human-readable explanations.

4. **Economic realism.** No competitor considers cost, environmental impact, or synthetic feasibility. A material that requires platinum-group elements and high-pressure synthesis is useless for most applications regardless of its computed properties. SOST Engine is the first to integrate economic and environmental constraints into the discovery loop.

5. **Community compute marketplace.** Decentralized compute for materials science does not exist. The combination of SOST escrow payments, Byzantine fault-tolerant task verification, and miner idle-time donation creates a new economic model for computational materials research.

### 8.3 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| GNN models do not achieve competitive accuracy | Low (ALIGNN is proven) | High | Use pre-trained weights, extensive hyperparameter tuning, MatBench benchmarking |
| Diffusion model generates mostly invalid structures | Medium | High | Start from proven CDVAE architecture, extensive validity filtering, conservative generation |
| DFT compute costs exceed budget | Medium | Medium | Tiered validation (GNN first, DFT only for top candidates), GPAW LCAO mode for fast approximate DFT |
| Low community adoption of compute marketplace | High (early stage) | Medium | Start with internal compute, offer generous SOST rewards for early adopters |
| Database harmonization introduces systematic errors | Medium | Medium | Train separate correction models per database pair using overlapping entries |
| SOST token volatility makes escrow pricing unstable | Medium | Low | USD-denominated tiers converted at market rate (already designed this way) |
| Competitor releases similar open platform | Low (no one has blockchain) | Medium | Accelerate development of blockchain-unique features |
| Commercial DFT license issues (VASP) | Low | Low | QE and GPAW are fully open source; VASP is optional, not required |

---

## Appendix A: Key References

1. Xie, T. & Grossman, J.C. "Crystal Graph Convolutional Neural Networks for an Accurate and Interpretable Prediction of Material Properties." Physical Review Letters 120, 145301 (2018). [CGCNN]
2. Chen, C. et al. "Graph Networks as a Universal Machine Learning Framework for Molecules and Crystals." Chemistry of Materials 31, 3564-3572 (2019). [MEGNet]
3. Choudhary, K. & DeCost, B. "Atomistic Line Graph Neural Network for Improved Materials Property Predictions." npj Computational Materials 7, 185 (2021). [ALIGNN]
4. Xie, T. et al. "Crystal Diffusion Variational Autoencoder for Periodic Material Generation." ICLR 2022. [CDVAE]
5. Merchant, A. et al. "Scaling deep learning for materials discovery." Nature 624, 80-85 (2023). [GNoME]
6. Zeni, C. et al. "A generative model for inorganic materials design." Nature (2025). [MatterGen]
7. Chen, C. & Ong, S.P. "A Universal Graph Deep Learning Interatomic Potential for the Periodic Table." Nature Computational Science 2, 718-728 (2022). [M3GNet]
8. Deng, B. et al. "CHGNet as a Pretrained Universal Neural Network Potential for Charge-Informed Atomistic Modelling." Nature Machine Intelligence 5, 1031-1041 (2023). [CHGNet]
9. Jain, A. et al. "Commentary: The Materials Project: A materials genome approach to accelerating materials innovation." APL Materials 1, 011002 (2013). [Materials Project]
10. Choudhary, K. et al. "The Joint Automated Repository for Various Integrated Simulations (JARVIS) for Data-Driven Materials Design." npj Computational Materials 6, 173 (2020). [JARVIS]
11. Curtarolo, S. et al. "AFLOW: An automatic framework for high-throughput materials discovery." Computational Materials Science 58, 218-226 (2012). [AFLOW]
12. Deb, K. & Jain, H. "An Evolutionary Many-Objective Optimization Algorithm Using Reference-Point-Based Nondominated Sorting Approach, Part I." IEEE Transactions on Evolutionary Computation 18, 577-601 (2014). [NSGA-III]

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **ALIGNN** | Atomistic Line Graph Neural Network — GNN that operates on both atom graph and bond-angle line graph |
| **Capsule v1** | SOST binary metadata protocol for transaction outputs (12-byte header + up to 243-byte body) |
| **CDVAE** | Crystal Diffusion Variational Autoencoder — generative model for crystal structures |
| **CIF** | Crystallographic Information File — standard format for crystal structure data |
| **Convex hull** | The set of lowest-energy phases at each composition; materials on the hull are thermodynamically stable |
| **D3PM** | Discrete Denoising Diffusion Probabilistic Models — diffusion for categorical (non-continuous) data |
| **DFT** | Density Functional Theory — quantum mechanical method for computing material properties from first principles |
| **GNN** | Graph Neural Network — neural network that operates on graph-structured data (atoms = nodes, bonds = edges) |
| **HNSW** | Hierarchical Navigable Small World — approximate nearest neighbor index for vector similarity search |
| **Material DNA** | 256-dimensional fixed-length vector encoding composition + structure + symmetry + latent representation |
| **MatBench** | Standardized benchmark suite for evaluating ML models on materials property prediction |
| **MEGNet** | MatErials Graph Network — GNN for materials property prediction (predecessor to M3GNet) |
| **NSGA-III** | Non-dominated Sorting Genetic Algorithm III — multi-objective evolutionary optimization algorithm |
| **Pareto front** | Set of solutions where no objective can be improved without degrading another |
| **PBE** | Perdew-Burke-Ernzerhof — standard exchange-correlation functional for DFT calculations |
| **PoD** | Proof of Discovery — on-chain hash commitment of a novel material prediction |
| **POSCAR** | VASP structure input format (lattice vectors + atomic positions) |
| **pymatgen** | Python Materials Genomics — standard Python library for materials science |
| **SFS** | Synthetic Feasibility Score — 0-100 estimate of whether a material can be manufactured |
| **SSSP** | Standard Solid-State Pseudopotentials — validated pseudopotential library for Quantum ESPRESSO |
| **Stocks** | SOST base unit (1 SOST = 100,000,000 stocks), used for all on-chain monetary values |
| **Wyckoff positions** | Symmetry-equivalent atomic positions within a crystal structure's space group |
