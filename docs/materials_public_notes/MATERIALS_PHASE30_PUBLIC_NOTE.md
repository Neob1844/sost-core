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
