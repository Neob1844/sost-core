# Stale-tip mining gate — adversarial security review + redesign

## History
- **v1 (VULNERABLE, superseded):** gated `getblocktemplate` on peer-**announced** height (refuse
  if a peer claims height > local + margin). **This was itself a remote mining-DoS:** a single
  unauthenticated peer advertising height 999999 while serving no blocks could deny mining.
  Measured: a persistent lying peer denied a healthy synced node's template in ~6/20 samples
  (intermittent; multiple colluding identities → continuous). **Do not use.**
- **v2 (this branch):** gate ONLY on our OWN validated tip height vs the last hard checkpoint.

## Severity context
A stale-tip block from a confused node is **rejected by the network anyway** (it's a low-work
fork; deep-reorg protection `MAX_REORG_DEPTH=500` blocks it). So this is **defense-in-depth /
hygiene** (don't waste hashrate, don't briefly serve a wrong tip to a co-syncing peer), NOT a
consensus vulnerability. The v1 **DoS**, by contrast, was the more serious problem — and it is
now removed.

## v2 design (attacker-independent)
Node (`handle_getblocktemplate`): refuse the template iff `g_chain_height <
LAST_HARD_CHECKPOINT_HEIGHT` (mainnet). This is a LOCAL, cryptographically-grounded signal (our
tip reached that height through full PoW validation), immune to Sybil/eclipse/lying peers — a
synced node ALWAYS mines regardless of any peer's claim. DEV/TESTNET floor = 0 (solo/bootstrap
mines); DEV-only env `SOST_DEV_MINING_MIN_HEIGHT` for deterministic testing. NON-CONSENSUS.

Miner (`sost-miner`): honors the node's refusal — on the `-10 "…stale/genesis tip"` error it
skips the round (sleeps, does not mine). Required because the miner builds part of the block
locally and previously mined an empty block when `getblocktemplate` failed. **⇒ this fix changes
BOTH the node and the miner** (unlike sec2, which was node-only).

## Deterministic test results (PASS 5/5) — `tests/security/gauntlet_D/ibd_gate_tests.sh`
| test | scenario | result |
|---|---|---|
| T1 | synced node + 1 liar@999999 | **mines** (DoS defeated) ✅ |
| T2 | synced node + 5 colluding liars@999999 | **mines** ✅ |
| T3 | genesis (floor 10) + honest peer | syncs past floor → **mines** (recovery) ✅ |
| T4 | genesis (floor 10) + ONLY liars (eclipse) | **refused, does NOT mine a genesis chain (h=0)** ✅ |
| T7 | solo bootstrap, no peers | **mines** ✅ |
(T5 genuinely-longer-honest-chain = T3's sync; T6 disconnect/stalled = T4, gate is peer-independent.)

## Verification of the required properties
- No new consensus change: getblocktemplate/miner are policy, not validation; **ctest 119/119**
  on the mainnet build.
- No deadlock: the node gate reads `g_chain_height` + a constant/env only (no new locks).
- No permanent mining stall: once synced to/above the checkpoint, the node mines forever.
- No startup bypass: the gate is evaluated on every `getblocktemplate`.
- Simulated peers (Python protocol client) are clearly NOT independent real nodes.

## Peers = simulated
All "peers" here are a protocol-accurate Python client (`sostpeer.py`), not independent real
full nodes.

## Status
Node hash (mainnet) `550ba580…`, miner `5a29cad4…` — a node+miner candidate, dev branch only,
NOT merged/deployed. Recommended for the Phase-3 integrated candidate (not for sec2, which stays
node-only). Requires a coordinated node+miner update at release.
