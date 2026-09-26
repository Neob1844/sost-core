# P2P Fork Convergence — empirical reproduction of bugs A & B, and the fix

Branch: `feat/p2p-headers-first-ibd` (NOT merged to main). Devnet harness only
(`SOST_DEVNET_FORKS=ON`, trivial PoW). Nothing here changes consensus rules — only how
a node *locates and downloads* an alternative chain over the existing height-based GETB.

## What was claimed vs. what we proved

The Phase-1 audit (`PHASE1_AUDIT.md`) flagged two suspected P2P defects:

- **A** — the peer's height, read once at the VERSION handshake, drives sync forever.
- **B** — sync requests blocks strictly *above our own height*, so two nodes that
  forked below the requesting node's tip can never find their common ancestor and never
  converge.

We reproduced both **empirically** with two connected devnet nodes, and turned the audit
suspicion into an exact, logged failure mechanism.

### Experiment 1 — genesis-deep fork (no shared history)
`scratchpad/p2p_converge.sh`: node A mines its own chain to height 10, node B mines a
*different* chain to height 15 (they share only genesis). A then dials B over P2P.

### Experiment 2 — realistic shallow fork
`scratchpad/p2p_converge_shallow.sh`: a shared chain to height 12, then A extends to 14
and B extends to 16. A dials B; the common ancestor is 4 blocks back. This is the
mainnet-realistic case (two miners find competing tips a few blocks apart).

## ANTES — the failure (verbatim from A's sync log)

```
[SYNC] Peer has height 16, we have 14 — requesting blocks 15..16
[ORPHAN] Block h=15 stored (parent ... unknown).
[FORK]   Block h=16 ... Fork stored but has LESS cumulative work (no reorg). 0x15 vs 0x3002
[SYNC] Peer sent 3 consecutive empty DONEs (claims height 16 but sends no blocks)
       — disconnecting as suspicious
[P2P]  Misbehavior +50 (empty DONE spam (fake height))
```

Height-based sync only ever asked for blocks **above** our tip, so the peer's divergent
branch arrived as disconnected orphans/fragments. Their cumulative work was computed from
the fragment alone (`0x15`), never from genesis, so a genuinely heavier chain looked
lighter and never triggered a reorg. Worse, the node then **mislabelled the honest,
higher-work peer as an attacker** and banned it. Neither node ever converged.

This is a four-layer defect:

1. **Request** — GETB only asks for `height+1..peer_height`; the pre-fork blocks that
   locate the common ancestor are never requested.
2. **Assembly** — a block that lands on a *fork* returned without ever reconnecting the
   orphans waiting on it, so an out-of-order branch never assembled past its first fragment.
3. **Dedup (×2)** — a block held only as an orphan/fork fragment was treated as a "known"
   duplicate at *both* the BLCK receive layer and the top of `process_block`, so the later
   in-order re-delivery that would have fixed its work was silently dropped.
4. **Progress** — sync measured progress by "a BLCK arrived", not "the chain advanced", so a
   reorg driven by the orphan cascade (which never touches that counter) was invisible: the
   node reorged partway, then walked *past* the tip it had just reached and banned the peer.

## The fix (backward-compatible, no new message type)

All four layers, in `src/sost-node.cpp`, expressed over the existing height-based GETB
(the serving peer is unchanged — old peers interoperate):

1. **Ancestor walk-back.** On an empty batch while the peer claims more height, step the
   GETB start height backwards (exponential back-off toward genesis) to locate the common
   ancestor — a block locator expressed as a sequence of height requests. Only after a full
   walk-back to genesis still yields nothing is the peer treated as bogus.
2. **Orphan cascade on fork storage.** After storing a fork candidate, call
   `process_orphans_for_parent(bid)` so children that arrived first reconnect and the
   alternative chain accumulates block-by-block until it out-works the active tip.
3. **Dedup carve-out (both layers).** A block held *only* as an ORPHAN or unconnected FORK
   is not a benign duplicate: let it reach `process_block` (and re-process orphans with the
   reorg-connect dedup bypass) so in-order re-delivery recomputes its true work. Settled
   (active-chain) blocks still deduplicate.
4. **Progress = chain advanced.** Sync now treats `g_chain_height` advancing during a batch
   as progress (a cascade-driven reorg counts), so it resumes forward from the new tip
   instead of walking back past it.

## DESPUÉS — automatic convergence (no manual restart)

```
#### SHALLOW (A→14, B→16, common@12) ####
  *** CONVERGED to B (h16) at t=3s ***
  AUTOMATIC CONVERGENCE — A reorged across a 2-block fork to B's higher-work chain over P2P.
#### GENESIS-DEEP (A→10, B→15) ####
  *** CONVERGED: A adopted B's chain (h15, tip match) at t=3s ***
  AUTOMATIC CONVERGENCE — lower-work node adopted higher-work chain over P2P.
```

Both bifurcated nodes recover on their own and end on the same highest-work chain, with no
manual restart — the acceptance criterion for the new sync.

## Regression validation (same modified binary)

- Normal linear IBD (empty node → 18): PASS (tip match).
- `run_v15_devnet_reorg` (submitblock reorg + jackpot disconnect/connect + equivalence): PASS.
- `run_v15_devnet_payout` 9/0 · `run_v15_devnet_mempool` 8/0 · `run_v15_devnet_rollover` 9/0
  · `run_v16_devnet_jackpot_v2` 9/0: all PASS.
- Compiles clean in the mainnet profile (`build/`, `-DSOST_ENABLE_PHASE2_SBPOW=ON
  -DSOST_TESTNET_FORKS=OFF`).

## Status & scope

This is the minimal, backward-compatible convergence fix over the current protocol. The
fuller **headers-first** architecture (download the header chain first to know the fork
point and target before pulling blocks, then parallel block download) remains the P3 goal
and is unaffected by — and complementary to — this fix. Do not merge/publish without
owner authorization; the live mainnet cutover window (activation @25000) is unchanged.
