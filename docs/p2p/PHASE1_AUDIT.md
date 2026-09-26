# Fast & Secure IBD — Phase 1 audit (P2P), STATIC findings

Branch `feat/p2p-headers-first-ibd` (separate from sec1). Node-only, NON-CONSENSUS intent.
Static code analysis of src/sost-node.cpp. Empirical reproduction of bugs A/B (forked nodes)
is DEFERRED so it does not contaminate the in-progress clean sync-time measurement.

## Bug A — "peer height frozen after handshake" — PARTIALLY PRESENT
`their_height` write sites:
- 7834: init `-1` on peer creation.
- 8071: set to `their_h` at the VERS handshake (`version_acked=true`).
- 8266: `if (blk_height > p.their_height) p.their_height = blk_height;` when a BLOCK is received.
**Finding:** it is NOT frozen at VERS — it advances when the peer sends a higher block (8266).
BUT there is **no headers/inv announcement path** (SOST has no `getheaders`/`sendheaders`), so a peer
whose tip advances without pushing us a block is not reflected, and the **sync target**
(`sync.peer_height`) is taken from the VERS value. So the *live peer height* updates on blocks, but
peer-tip discovery is push-only and coarse. Real defect surface, milder than "frozen". Empirical
repro pending.

## Bug B — "height-based sync does not converge across forks" — STRUCTURALLY PRESENT
Sync requests blocks by **height** (`GETB` from a height, `GETB_BATCH_MAX=100`/msg). There is **no
block locator and no getheaders**. If a node is on fork X, below/beside a peer on fork Y at the same
heights, GETB-by-height returns fork-Y blocks that do not connect to fork-X's tip → they land as
orphans/forks. Convergence then depends entirely on the fork-store + `try_reorganize` (higher-work
reorg), not on the download path finding the common ancestor. This is exactly the case a block
locator fixes at the source. **Structurally confirmed in code; empirical repro (two forked nodes)
pending.**

Orphan handling: orphans are stored (`g_orphans_by_prev`) and connected later by
`process_orphans_for_parent`, but the node does **not actively request the missing parent** on orphan
receipt (no getheaders/locator round-trip). Gap.

## ConvergenceX header-verifiability — the gating question for headers-first
`bits_q` (difficulty) is in the header. The **SbPoW/ConvergenceX proof recomputation is expensive**
(the ~4 GB/block SbPoW) and must be established as header-only-verifiable or not before headers-first
can attribute *verified work* to a header. **Open item (needs a focused block/header field audit):
which proof fields live in the header vs the body.** Until proven, headers-first must NOT attribute
verified CX work to a header — below a checkpoint only the hash-link may be checked (documented
limitation), matching the existing assumevalid discipline.

## Proposed protocol changes (Phase 2+), non-consensus, backward-compatible
1. `getheaders`(locator, hash_stop) / `headers`(≤2000) messages — exponential locator over the active
   chain + genesis; find common ancestor regardless of fork/height. Fixes B.
2. Update per-peer `best_known_header` on every headers/inv/block; announce new tips by header
   (BIP130-style). Fixes A.
3. On orphan: send `getheaders` with locator to fill the gap (instead of store-and-wait).
4. **Capability negotiation** in VERS so new nodes speak locator to new peers and fall back to the
   current height-based GETB with old peers — no hard network break.
5. Selection by **verified cumulative work**, never announced height.
Consensus rules, block format and consensus-state persistence: UNCHANGED.

## Delivery split (per the deadline)
- **Small, verifiable-soon P2P fixes** (candidate for a later node revision, tested first): peer-tip
  update on all messages (A), orphan-parent request, ping/pong timeout.
- **Full headers-first + parallel download**: larger; do NOT rush a P2P rewrite in before #29,900.

## Next (deferred until the clean sync measurement finishes, to avoid CPU contamination)
- Empirical repro of A and B on forked devnet nodes (Phase 8 lab).
- Block/header field audit for CX header-verifiability.
- Benchmark ANTES/DESPUÉS.
