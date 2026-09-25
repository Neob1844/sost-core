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
