# Novelty Audit Report

**Corpus size:** 2000  
**Mean novelty score:** 0.0  
**Median novelty score:** 0.0  

## Novelty Bands

| Band | Count |
|------|-------|
| known | 2000 |
| near_known | 0 |
| novel_candidate | 0 |

## Top 20 Exotic Candidates

| Rank | Formula | SG | Exotic | Novelty | Top Reason |
|------|---------|-----|--------|---------|------------|
| 1 | Nb2Ru | 69 | 0.3212 | 0.0000 | rare_structure |
| 2 | Xe | 225 | 0.3089 | 0.0000 | rare_elements |
| 3 | SiS | 53 | 0.3002 | 0.0000 | rare_structure |
| 4 | YbCrSb3 | 57 | 0.3000 | 0.0000 | rare_structure |
| 5 | Nd5Ir3 | 130 | 0.2965 | 0.0000 | rare_structure |
| 6 | LuAg4 | 87 | 0.2963 | 0.0000 | rare_structure |
| 7 | CdAu | 157 | 0.2928 | 0.0000 | rare_structure |
| 8 | TlZn2Sb2 | 108 | 0.2919 | 0.0000 | rare_structure |
| 9 | SmSb12Os4 | 204 | 0.2882 | 0.0000 | rare_structure |
| 10 | ErB4Rh4 | 142 | 0.2872 | 0.0000 | rare_structure |
| 11 | HgBr2 | 36 | 0.2871 | 0.0000 | rare_structure |
| 12 | LiY3WO8 | 21 | 0.2869 | 0.0000 | rare_structure |
| 13 | GaBr2 | 52 | 0.2843 | 0.0000 | rare_structure |
| 14 | NbP | 109 | 0.2841 | 0.0000 | rare_structure |
| 15 | TcBr3 | 59 | 0.2828 | 0.0000 | rare_structure |
| 16 | NaCaLaF6 | 143 | 0.2818 | 0.0000 | rare_structure |
| 17 | UTe3 | 11 | 0.2813 | 0.0000 | rare_structure |
| 18 | DyInCo2 | 51 | 0.2810 | 0.0000 | rare_structure |
| 19 | MnMoAs2 | 31 | 0.2807 | 0.0000 | rare_structure |
| 20 | USe3 | 11 | 0.2807 | 0.0000 | rare_structure |

## Limitations

- Novelty is relative to current ingested corpus only (not all literature)
- Fingerprint does not capture full structural detail (e.g., atomic positions)
- Exotic != better or useful — just rarer/less explored
- Band gap and formation energy included in fingerprint (data leakage risk for novelty)
- Cosine similarity may not capture all relevant structural differences

> Novelty is relative to the current ingested corpus only, not to all scientific literature.
