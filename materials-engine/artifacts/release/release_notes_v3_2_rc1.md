# SOST Materials Discovery Engine — Release Notes v3.2.0-RC1

## What It Does
The Materials Discovery Engine is a CPU-friendly ML platform for computational materials science. It ingests crystal structure data, trains GNN models, predicts material properties, and discovers novel materials through automated campaigns.

## Production Models
| Target | Model | MAE | R² | Dataset |
|--------|-------|-----|-----|---------|
| Formation Energy | CGCNN | 0.1528 eV/atom | 0.9499 | 20K materials |
| Band Gap | ALIGNN-Lite | 0.3422 eV | 0.707 | 20K materials |

## Corpus
- **76,193 materials** from JARVIS (75,993) + AFLOW pilot (200)
- 89 elements, 213 spacegroups, 7 crystal systems
- 99.74% have validated crystal structures
- 100% have formation energy, 99.9% have band gap

## Key Capabilities
- **Search**: Formula, element, property range, source filtering
- **Predict**: Band gap and formation energy from CIF structure
- **Discover**: Novelty scoring, exotic ranking, campaign engine
- **Analyze**: Frontier selection, intelligence reports, dossiers
- **Validate**: Benchmark suite, calibration, evidence bridge

## API
- **145 endpoints** (105 production, 40 research)
- FastAPI with OpenAPI docs at /docs
- JSON responses, no authentication required for read

## Research Watchlist
- **Hierarchical band gap pipeline**: 24% better overall MAE but narrow-gap regression blocks promotion
- **9 optimization phases** (IV.L→IV.S): 22+ models trained, gate/specialist/calibration explored
- Architecture proven correct; binary gate threshold tradeoff remains unsolved

## Limitations
- Band gap MAE=0.34 eV — useful baseline, not state-of-art
- No bulk/shear modulus predictions
- External sources (AFLOW, MP, COD) unreachable from current environment
- CPU-only training limits model depth
- Hierarchical pipeline not promoted

## What's Next
- Deploy API on production VPS
- Acquire Materials Project API key
- GeoForge unified platform integration
- Blockchain proof-of-discovery (Phase V)

---
*Built with SOST Protocol. 41 test files. Zero external ML dependencies beyond PyTorch + pymatgen.*
