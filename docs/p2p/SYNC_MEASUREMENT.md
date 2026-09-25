# Clean initial-sync measurement + bottleneck (evidence-based)

## Setup (uncontaminated)
Single node, empty dir, from genesis, plaintext, against a local reference; NO concurrent
builds/tests/load. Node = sec1 binary d3212aea. Host: i9-10885H (14 threads), 23 GB RAM,
WSL2 disk reporting rotational=1. Chain: 26,973 blocks / ~412 MB.

## Result (real, measured 2026-09-25)
| Phase | Time |
|---|---|
| launch → RPC ready | 0.3 s |
| RPC → first block | 0.1 s |
| first block → tip | 12,122.4 s |
| **TOTAL genesis → tip** | **12,122.7 s = 202.0 min** for 26,973 blocks |
| tip → first getblocktemplate | 0.0 s (mining-ready immediately) |
| peak RSS | 515 MB |

Average 2.23 blk/s, but the per-block cost GROWS with height (measured):
| Segment | blk/s |
|---|---|
| 0–5,000 | ~35.4 |
| 5,000–10,000 | ~4.84 |
| 10,000–15,000 | ~2.51 |
| 15,000–20,000 | ~1.67 |
| 20,000–25,000 | ~1.24 |
| 25,000–26,973 | ~1.02 |

## Bottleneck #1 — full chain.json rewrite per block (O(N²)) — CONFIRMED IN CODE
`process_block` calls `save_chain_internal(g_chain_path)` **after every accepted block**
(src/sost-node.cpp:7607, comment "Auto-save chain immediately after every accepted block").
`save_chain_internal` (line 9263) writes ALL of `g_blocks` (`for i<g_blocks.size()`) to a
`.tmp` file and renames it. So each accepted block rewrites the entire chain (up to ~412 MB) →
O(N) write per block, O(N²) over the sync. On the slow WSL/HDD disk this dominates and exactly
matches the 35→1 blk/s deceleration. It is a persistence inefficiency, NOT SbPoW (which is flat
per block) and NOT consensus.

## Fix (non-consensus, node-only) — proposed, to benchmark ANTES/DESPUÉS
During initial block download, do NOT rewrite the whole chain every block. Options (pick one,
measure):
- **Batched/periodic save during IBD:** save the full chain every N blocks (e.g. 1,000) or every
  T seconds while catching up; save per-block only when at the tip (live). A crash during IBD just
  resumes from the last save. Simplest, high impact, tiny change.
- **Append-only chain file:** append each new block's JSON to the array (O(1)/block) with a known
  trailer, rewriting fully only on compaction. Larger change.
Neither changes block validity, format on the wire, emission, or any consensus rule — the on-disk
chain content is identical, only the write cadence changes.

## Other costs (ranked, to profile next)
2. SbPoW/ConvergenceX per-block validation — real CPU floor (~constant/block; the ~1 blk/s tail).
3. cASERT/lottery per-block meta — bounded windows (288); confirm not an O(N) history rebuild.

## <60 min target (item 5) — honest read
On THIS WSL/HDD host, 202 min is disk-bound by the O(N²) rewrite. Fixing #1 alone should cut the
tail dramatically; an SSD host plus the fix is the realistic path to the <60 min goal. Not promised
until measured DESPUÉS.

## Fix implemented + ANTES/DESPUÉS (partial, real)
Change: during IBD, save the full chain every 2,000 accepted blocks instead of every block; keep
per-block saving once at the live tip (block timestamp within ~40 min of now). `src/sost-node.cpp`
at the auto-save site. Non-consensus, node-only; on-disk content unchanged.

| Metric | ANTES (save every block) | DESPUÉS (save every 2,000 in IBD) |
|---|---|---|
| genesis → block 10,000 | 1,174.2 s | **96.6 s** (~12.2× faster) |

The O(N²) disk-write cost is eliminated; per-block cost is flat again. Node built
(53101a42…) from feat/p2p-headers-first-ibd (main base + this fix).

## Pending before this can ship
- Full DESPUÉS measurement genesis→tip (state the total; do not promise <60 min until measured).
- Re-run consensus / reorg / P2P-adversarial / genesis-sync tests after the change (fast-sync item 7):
  the on-disk chain must still load to the identical tip/UTXO after an IBD crash+resume.
- Confirm crash-during-IBD resume: restart mid-sync must load the last periodic save and re-sync the
  gap to the identical tip hash.

## DESPUÉS full + correctness (real, measured)
Full genesis→tip with the fix: **1,092.8 s = 18.2 min** (was 202 min) — **~11.1× faster**, and
**under the 60-minute target on this WSL/HDD host** (demonstrated, not promised). Peak RSS 510 MB,
mining-ready (first getblocktemplate) at the tip in 0.0 s.

Crash-during-IBD resume test: synced to 7,558, `kill -9`, restarted → loaded ~6,607 (last periodic
save, not from 0), re-synced the gap, and block hashes at 6,000 / 8,000 / 10,000 / 12,000 all MATCH
the reference node with 0 rejects. The periodic-save chain file is valid and resumes to the identical
chain. Consensus/validation path is unchanged — only write cadence.

## Regression gate (fast-sync item 7)
Full ctest on the fixed binary (53101a42…): **115/115 pass** (only the 4 btc-* tests excluded — need
a live bitcoind). No regression from the save-cadence change.

## Verdict
Bottleneck #1 (O(N²) full chain.json rewrite per block) is CONFIRMED and FIXED, node-only and
non-consensus: genesis→tip **202 min → 18.2 min (~11×)** on WSL/HDD, meeting the <60 min target here;
crash-during-IBD resumes to the identical chain (hashes match, 0 rejects); 115/115 tests pass.
READY for a node-only sync revision once combined and re-verified with the sec1 hardening (kept
separate for now). Bugs A/B (block-locator / getheaders convergence) remain the next sync workstream.

## Write-interruption atomicity (P2 next-step 1) — VERIFIED
save_chain_internal writes `chain.json.tmp` then atomically renames it over `chain.json`. Killed the
node with `kill -9` at height 6015 — during/just after the periodic 6000 save. On-disk `chain.json`
was left at height 6000 (2001... 6001 blocks), valid and JSON-parseable; the partial `.tmp` is
discarded. Restart log: "Chain: 6001 blocks, height=6000, UTXOs=17964 · Node running · Peer
connected" — loaded the last complete save and resumed. A mid-write crash NEVER corrupts chain.json;
the worst case is losing up to one save interval (≤2000 blocks) which is re-synced. Combined with the
earlier crash-resume run (hashes at 6k/8k/10k/12k MATCH, 0 rejects), write-interruption recovery holds.
Still pending: adversarial reorgs with the batched save; fresh-install on Windows + Linux.
