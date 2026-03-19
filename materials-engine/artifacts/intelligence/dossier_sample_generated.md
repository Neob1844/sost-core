# Validation Dossier: BaCuTe (Generated Candidate)

**Existence:** near_known_match
**Priority:** low
**Eval Score:** 0.58

## Predicted Properties
| Property | Value | Note |
|---|---|---|
| formation_energy | -1.8 | GNN prediction on lifted structure |
| band_gap | 1.2 | GNN prediction on lifted structure |

## Proxy Properties
| Property | Value | Note |
|---|---|---|
| element_diversity | 3 | Number of unique elements |
| thermal_risk_proxy | moderate | T=800.0K — moderate thermal risk. |
| pressure_sensitivity_proxy | moderate_pressure | P=2.0GPa — moderate pressure. |

## Applications
| Label | Score | Evidence |
|---|---|---|
| catalytic_candidate | 0.35 | proxy |

## Validation Rationale
- Priority: low
- Score: 0.4689
- Reasons: ['already_known_in_corpus']

## Limitations
- Existence is assessed relative to the integrated corpus only, not all published scientific literature.
- This is a generated hypothesis — the material may not be experimentally synthesizable. Requires computational or experimental validation before any claims.
- 11 properties are unavailable. Advanced calculations (DFT, phonon, EOS) not yet integrated.
- Predicted properties use baseline GNN models (MAE ~0.23-0.45). Accuracy is limited by training data size and model complexity.
