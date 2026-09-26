# Security Gauntlet — P2P fork-convergence node

Target: the modified node on `feat/p2p-headers-first-ibd` (convergence fixes `73b85b1b`
+ orphan-dedup DoS fix `b5178dd0`). Devnet harness (`SOST_DEVNET_FORKS=ON`, trivial PoW),
real two-node P2P + submitblock injection. Every result is empirical (logs/metrics).

## 3. Do the dedup carve-outs allow infinite reprocessing or bypass validation?  — NO
- **No validation bypass (empirical).** A corrupted-nonce block that is "known" as a fork is
  still REJECTED (`[SUBMITBLOCK] REJECTED by process_block`, RPC -25), node alive. Code audit
  confirms `reorg_connect` is checked in exactly one place and lifts ONLY the relay-dedup
  cache — `verify_cx_proof` (PoW) and every consensus check still run on re-processed blocks.
- **Bounded reprocessing.** Block ids are content hashes → the orphan/fork graph is a DAG
  (cycles cryptographically infeasible); `process_orphans_for_parent` erases each orphan
  before re-running it; caps `MAX_ORPHAN_BLOCKS=200`, `MAX_FORK_INDEX_ENTRIES=1000`,
  `MAX_REORG_DEPTH=500` still gate storage.
- **Orphan-pool DoS found AND fixed.** The carve-out initially let a peer RESEND one orphan
  to insert duplicate `g_orphans_by_prev` entries, filling the pool to the 200 cap with one
  block (300 resends → 200 orphans) and evicting real orphans. Fixed (`b5178dd0`): skip
  re-parking a block already in the index. Re-tested: 300 resends → **1** orphan; RSS flat.

## 2. Adversarial tests
- **Malicious duplicate / orphan / out-of-order blocks:** duplicate flood (300×) deduped, RSS
  flat; out-of-order fork replay reconnects via the cascade; resent-orphan pool stays at 1.
- **Adversarial reorg:** `run_v15_devnet_reorg` PASS (deep reorg undoes J_A, connects J_B,
  reorganised state == clean reference). Fork convergence (shallow + genesis-deep) auto-recovers.
- **Partition → heal:** two partitioned nodes converge to the same highest-work tip, no manual
  restart.
- **Restart/recovery during forks:** 5/5 clean recoveries — node SIGKILLed at a random
  sub-second point mid-reorg reloads a VALID chain.json at the converged height every time
  (atomic `.tmp`+rename; no corruption).
- **Memory/CPU/storage limits:** node RSS stays ~10 MB under every flood; orphan/fork caps
  hold; node O(1) block validation keeps CPU bounded; unsolicited blocks stay rate-limited.

## 1. Fuzzing (block reception + orphan management)
- 400 mutated blocks via submitblock (bit-flipped ints, nulled/deleted/duplicated fields,
  junk hex, wrong types) → node survived, still responsive. No crash, no hang, RSS bounded.

## 4. Full sync + emission / UTXO / consensus (with the P2P fixes)
- Normal linear IBD (empty → 18) PASS. Full-chain sync (empty → 28): height + best-block hash
  identical; **all 28 per-block hashes identical** A vs B; subsidy/miner/tx_count identical at
  h=1,7,14,21,28; UTXO set size identical. Consensus/emission/UTXO preserved byte-for-byte.
- E2E on the modified binary: reorg 9/0, payout 9/0, mempool 8/0, rollover 9/0, jackpot_v2 9/0.

## Side finding (separate branch)
Fuzzing also surfaced two PRE-EXISTING remote-DoS defects in the RPC layer (not caused by the
P2P work; reproduce on unmodified `main`): an uncaught `stoll` exception aborts the node, and a
nested-array param OOM-kills it (~6 GB/call). Fixed on `fix/rpc-crash-hardening`
(`docs/security/RPC_CRASH_HARDENING.md`). Recommend landing before block 29,900.

## Verdict
The P2P convergence changes are **memory-safe, validation-safe, and recovery-safe** under
adversarial input; the one DoS they introduced (orphan-pool duplication) is fixed and
re-verified. Branch only — no merge/publish/deploy without authorization; not mixed with sec1.
