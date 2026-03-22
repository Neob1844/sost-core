# Materials Engine Release Manifest — v3.2.0 RC1

## Corpus
- Total: 76,193
- Sources: {'aflow': 200, 'jarvis': 75993}
- With FE: 76,193
- With BG: 76,124

## Production Models
- **formation_energy**: cgcnn (20,000), MAE=0.1528
- **band_gap**: alignn_lite (20,000), MAE=0.3422

## API: 145 endpoints (101 production, 44 research)

## Limitations
- Band gap prediction MAE=0.34 eV — acceptable baseline, not state-of-art
- No bulk modulus or shear modulus predictions yet
- External data sources (AFLOW, MP, COD) unreachable from current environment
- CPU-only training — GPU would improve convergence and allow deeper models
- Hierarchical BG pipeline not promoted due to narrow-gap tradeoff
