# SACS Delivery B — Automatic convergence past MAX_REORG_DEPTH (research; future fork, NOT V16)

Answers the core question: after reconnect, can nodes OBJECTIVELY recognise a valid chain with more
work, and what change lets SOST recover convergence WITHOUT manual intervention?

## Can nodes objectively recognise a more-work valid chain? — YES (already)
This half already works and needs no trust assumption:
- Selection is by **highest cumulative VALID work** (`compare_chainwork`, `cumulative_work` per block),
  not longest chain, not announced work.
- `try_reorganize()` replays the competing branch through the **FULL validation path** (ConvergenceX PoW
  proofs, cASERT difficulty, emission, signatures, UTXO/BlockUndo). A peer cannot impose a chain by
  claiming work; the node recomputes it from independently-validated blocks.
So the OBJECTIVE recognition of a heavier valid chain is present today.

## Why convergence still fails past 500 (the only obstacle)
Two hard caps on the SAME constant refuse an objectively-heavier chain once divergence > 500:
- `:7199` block-accept: rejects any incoming block whose `height < local_tip − 500`.
- `:7479` reorg: aborts if adopting the winner requires `disconnect_count > 500`.
Net (code-traced, definitive): fork-depth ≤500 → converge; ≥501 → **persistent split even though the
other chain has more validated work**. It is the CAP, not the work comparison, that breaks convergence.

## The change that restores automatic convergence (proposed, devnet-first)
Separate the CONSENSUS rule from the OPERATIONAL alarm:
1. **Consensus (future coordinated fork):** remove the hard depth cap from ACCEPTANCE and REORG; a node
   always adopts the chain with the highest **fully-validated** cumulative work, at any depth — exactly
   Bitcoin's model. This alone lets the loser objectively recognise and reorg to the heavier chain after
   reconnect → automatic convergence, no manual intervention.
2. **Operational safety (SACS, no consensus change — Delivery A, already built):** keep 500 ONLY as a
   `DEEP_REORG_ALERT`. When a reorg exceeds it, SACS emits the event and the tx-safety state machine
   (`sacs-tx-safety.js`, PENDING/CONFIRMED/REORGED/…) + the exchange credit policy SUSPEND sensitive
   operations (deposit crediting) until the chain stabilises — but the node does NOT refuse the heavier
   chain. This gives the protection the hard cap was meant to give, without the persistent-split failure.
3. **Anti-abuse (unchanged cost):** the competing chain must be FULLY validated before adoption (no
   trusting announced work) — the attacker must produce real ConvergenceX work, same cost as any deep
   reorg; and alternative-branch storage stays bounded to prevent memory exhaustion.

## Security comparison
- `< limit` reorgs: identical to today.
- `> limit` reorgs: today → persistent split (a real availability/partition failure); proposed → converge
  to most-validated-work (Bitcoin-equivalent) + SACS operational suspension of payments during the event.
- Does NOT create absolute finality and does NOT stop a genuine majority-hashpower deep reorg — no PoW
  system can, without an external trust assumption (which SOST rejects: no ChainLocks/masternodes/quorums).

## Activation
Consensus change (#1) is version-incompatible: a node with the cap and one without will diverge, so it
needs a **coordinated future fork**, prototyped on devnet first. **NOT the V16 #30000 fork.** The SACS
operational layer (#2) ships with no consensus change and is safe for Delivery A now.

## Empirical status (honest)
Real-node scaled partition test (MAX_REORG_DEPTH=8 devnet build) is BLOCKED-ENVIRONMENT: the devnet node
contacts the mainnet DNS seed (`seed.sostcore.com`) and enters fast-sync/IBD, and this sandbox has no root
to isolate network egress and no `--noseed` flag. Mining + chainwork tracking are demonstrated (v1: height
9, real blocks). A clean converge/split PASS needs an isolated devnet network (no external seed) — the
executable next step once egress can be blocked or a devnet seed-disable flag exists.
