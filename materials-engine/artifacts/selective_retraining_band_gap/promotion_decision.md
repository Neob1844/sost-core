# Promotion Decision: **HOLD**

**Target:** band_gap
**Production MAE:** 0.3422
**Best Challenger:** bg_sparse_exotic_10k (MAE=0.5926)
**Improvement:** -0.2504 eV (-73.2%)

## Rationale

Overall MAE improvement (-0.2504) below threshold (0.01); Bucket regression detected: worst delta=0.8212

## No promotion — production model retained

## Do NOT

- Do NOT deploy challenger without full benchmark validation
- Do NOT delete production checkpoint
- Do NOT retrain formation_energy — it's already strong
