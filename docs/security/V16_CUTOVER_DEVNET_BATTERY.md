# V16 Cutover — Fresh Devnet Battery (protects mainnet #30.000)

**Status:** LAB VERIFIED (devnet). Mainnet height/rules UNTOUCHED.
DEVNET_FAST maps the V16 activation (`HIST_JACKPOT_V2_HEIGHT` / `DTD_V16_ELIGIBILITY_HEIGHT`)
to **N = 42**, reproducing the mainnet **#30.000** cutover at low height. Binaries: `build-sacs`
(`-DSOST_DEVNET_FORKS=ON`). Tests: `tests/v16_cutover_battery.sh`, `tests/v16_reorg_across_activation.sh`.

## Part 1 — straight cutover (N-2..N+2)
Mined 0→44 with no stall. Per-block acceptance across the boundary:
```
[BLOCK] Height 40 accepted: df6f8571d2a90d21 (chainwork=0x30b0)
[BLOCK] Height 41 accepted: 27afaf7b6680c314 (chainwork=0x30b1)
[BLOCK] Height 42 accepted: 38661f28d304bbd5 (chainwork=0x30b2)   <- ACTIVATION
[BLOCK] Height 43 accepted: 84087c3802582422 (chainwork=0x30b3)
[BLOCK] Height 44 accepted: 7f9e93712273bbb1 (chainwork=0x30b4)
```
`getjackpotv2audit(42)` → `is_v2_jackpot:true, activation_height:42, epoch_length:6` — V16 Historical
Jackpot V2 activates EXACTLY at N. `devchainstate` consistent (chain_height 44, active_index 44).
getinfo height 44 (version string "0.3.2" is a hardcoded internal API string, not the release tag).

## Part 2 — restart persistence
Node restarted → tip `7f9e9371…` at h=44 stable=YES (chain + activation state persisted).

## Part 3 — reorg ACROSS the activation boundary
Shared prefix 0..40 (fed A→B); A mined 41..44; B mined a heavier divergent 41..45 (more work).
Feeding B[41..45]→A:
```
[REORG] Fork detected at height 40
[REORG] Disconnecting 4 blocks (h=41..44)      <- disconnects the activation block 42
[REORG] Connecting 5 blocks
[REORG] Success: new tip = a62259cec24993f1 at height 45
```
A converged to B (tip a62259ce…, h=45). Post-reorg `getjackpotv2audit(42)` → `is_v2_jackpot:true,
activation_height:42` — activation state CONSISTENT after a reorg that spanned the boundary.
Restart after reorg: stable=YES.

## Conclusion
V16 activation, restart/recovery, and reorg-across-activation behave correctly in the lab at the
mapped height. The mainnet activation height (#30.000) and all consensus rules were NOT modified.
Recommended: re-run this battery in the pre-#29.900 safety window on the exact release binary.

## NOT covered here (honest)
NODE_BIND/PoPC eligibility deep paths and emission/supply invariants across the boundary were not
individually asserted in this run (only jackpot-V2 activation + chain continuity + reorg). A fuller
assertion set is future work for the safety window.
