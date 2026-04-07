# Materials Engine Phase 30 — public note

Materials Engine now includes:

- **Consensus multi-track ranking** — candidates scored across exotic, photovoltaic, and catalyst tracks
- **Photovoltaic risk flags** — 6 physics-informed flags to reduce false positives (ferrimagnetic oxides, d-electron recombination, spinel structures)
- **DFT triage queues** — exploit (highest confidence), explore (novel compositions), cross-track (multi-track consensus)

## Results

- 22 raw candidates across 3 tracks → 21 unique → **11 DFT-queued**
- 1 cross-track consensus candidate (accepted in 2+ tracks)
- 3 PV false positives caught and penalized
- 9 single-track heroes identified

This improves candidate prioritization and reduces wasted compute on false positives.

Detailed candidate identities, full score breakdowns, and complete DFT queues remain private.

## Phase 32 Update — Novelty-aware scoring

- Known-material filter: 42 entries + 3 pattern matchers
- **Rediscovery rate: 63.6% → 0.0%**
- Famous materials (LiCoO2, EGaIn) correctly penalized
- New top candidates are genuinely unexplored compositions
- 9 novel materials in DFT queue (was 1)

## Phase 34 Update — ML Surrogate Prescreen (CHGNet)

- **17 candidates screened in 40 seconds** (vs ~200h if all went to DFT)
- CHGNet predicts formation energy and stability before committing to expensive DFT
- Results: 7 PASS, 6 FLAG, 4 REJECT
- **64 CPU-hours of DFT saved** by eliminating unstable candidates early
- Top candidate confirmed: FeMgO2 (-2.09 eV/atom, strongly stable)
- InNP rejected: +1.84 eV/atom (would have wasted 12h DFT)
