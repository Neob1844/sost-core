# COD Value Contribution Report

## What COD Adds

- New materials: 10
- New structures: 10
- New compositions: 9
- New elements: C, Ca, Cs, Cu, H, In, N, Ru, S
- New spacegroups: []

## Coverage Impact

- Structural coverage: 100.0% → 100.0%
- Element coverage: 8 → 17
- Spacegroup coverage: 5 → 5

## Training Value

**NONE**

COD provides experimental crystal structures without computed formation_energy or band_gap. These materials CANNOT be used for ML training of FE/BG models. They are classified as structure_only tier.

## Search Space Benefit

- **novelty_detection**: +9 new compositions expand novelty reference space
- **exotic_candidate_ranking**: +9 new elements improve exotic scoring baseline
- **structural_reference_pool**: +10 new crystal structures for polymorph comparison
- **comparison_quality**: COD experimental structures provide validation anchors for DFT predictions
- **frontier_contextualization**: Structure-only materials cannot rank in FE/BG frontiers, but expand the neighbor pool for similarity search

## Recommendation

**continue_cod_expansion**
