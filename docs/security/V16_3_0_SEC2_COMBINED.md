# SOST v16.3.0 sec2 — combined security update (sec1 + RPC crash hardening)

**Status: PREPARED AND VERIFIED — NOT published, NOT deployed (awaiting owner authorization).**
Branch `release/v16.3.0-sec1-rpc`. Does NOT modify the frozen sec1 code, the v16.3.0 tag, or
the original binaries. Node-only; miner and cli are byte-identical to v16.3.0/sec1.

## What sec2 contains
- **sec1** (unchanged, cherry-pick base `32cabab2`): fork/orphan-store hardening + beacon base64
  UB fix. Node hash was `d3212aea`.
- **+ two RPC crash-hardening fixes** (`ebe4f790`, +18 lines in `src/sost-node.cpp`, RPC I/O only):
  1. `dispatch_rpc` try/catch → any uncaught handler exception becomes a JSON-RPC error.
  2. `json_get_params` advances past a delimiter sitting at the cursor + 256-param cap
     (kills the infinite loop that OOMed the node on nested-array params).
- Diff vs sec1 is EXACTLY those two hunks + docs. No consensus/emission/P2P path touched.

## The two defects (pre-existing; reproduce on the ORIGINAL sec1/main binary)
| Defect | Trigger (one unauthenticated call) | Original sec1 | sec2 |
|---|---|---|---|
| Uncaught `std::stoll` | `getblockhash ["str"]` | 💥 abort (core dumped) | ✅ RPC error, alive |
| `json_get_params` OOM | `getblock [[[[1]]]]` | 🔴 ~6 GB/call → OOM-kill (RSS 4.7 GB @1 call) | ✅ error, RSS flat 9 MB |

## Remote exposure (code+config review, no attack on production)
- Public gateway `ops/sost-rpc-proxy.py`: forwards ANY method WITHOUT credentials and relies on
  the node's own gate (reads need no auth); injects node credentials only for
  `sendrawtransaction`; denies `getblocktemplate`.
- Node `rpc_is_readonly_method`: **both `getblock` and `getblockhash` are read-only (no auth).**
- ⇒ Both defects are reachable ANONYMOUSLY from the internet via `/rpc` and `/rpc/public`.
  nginx limits 10 r/s, burst 5, body 16 KB — **does not mitigate**: defect 1 needs one call,
  defect 2 needs 2–4 tiny calls. **Both are unauthenticated remote DoS in production.**

## Verification (all on the sec2 binary unless noted)
- **Bugs reproduced on original sec1, gone on sec2** (side-by-side).
- **Unit tests:** ctest 119/119.
- **ASan + UBSan** (`-fno-sanitize-recover=all`, halt_on_error=1): 0 findings after mining +
  120 malformed RPC calls incl. both culprit inputs.
- **RPC fuzz:** 250–300 malformed calls (garbage, nested arrays/objects, huge hex, nulls,
  huge ints) → responsive, RSS flat 9 MB; valid RPC (`getblockhash[2]`, `getblock[hash]`) OK.
- **Block-reception fuzz:** 300 mutated blocks → node survives, RSS 11 MB.
- **Consensus/DTD/Jackpot/NODE_BIND/emission/reorg E2E:** reorg 9/0, payout 9/0, mempool 8/0,
  rollover 9/0, jackpot_v2 9/0 (V2 rollover + first PAID node-gated weighted jackpot).
- **Full sync from empty:** height + best-block hash + all 28 per-block hashes + subsidy +
  UTXO identical vs source (emission/UTXO/consensus preserved byte-for-byte).
- **RPC parser audit:** the only no-progress loop was `json_get_params` (fixed); every other
  parser helper (`json_get_string`/`jint`/`juint`/`jstr`/`json_get_tx_hexes`) provably advances;
  all `std::sto*`/`from_hex`/`bad_alloc` now caught by the dispatch try/catch; no unbounded
  param-driven allocation (`build_casert_meta` window-capped at 512).

## Binary hashes (definitive, reproducible)
```
sost-node-sec2  5b50a448f3e319ef6137da61093750bd6d286cc508ff69fe994cf3532c4fa157
sost-miner      2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  (== v16.3.0)
sost-cli        489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  (== v16.3.0)
```
Reproducibility: node hash is deterministic ONLY when the build dir is named exactly `build`
AND lives inside the source tree (verified: 2 clean builds → identical `5b50a448`; a build named
`build2` or placed out-of-tree yields a different node hash while miner/cli stay identical).
That miner/cli reproduce v16.3.0/sec1 byte-for-byte confirms the toolchain matches the release.

## Consensus integrity (step 7) — INTACT
Consensus, emission, SbPoW, cASERT, DTD, Jackpot, NODE_BIND and the #30,000 fork are byte-for-byte
unchanged: the sec2 diff vs sec1 is only RPC I/O (dispatch + param tokenizer), miner/cli are
identical, all consensus/jackpot/emission E2E pass, and a full sync reproduces every block hash.

## Residual risks
- **Node hash is build-path/name sensitive** (known reproducibility item): the release build MUST
  use a `build` dir inside the source tree. Documented above.
- **O(N) read RPCs** (`getaddressbalance`/`getaddressflows`/history) scan the whole chain per
  call and are anonymous+read-only; not a crash, but a spammed CPU cost bounded by nginx rate
  limits. Out of sec2 scope; candidate for a later result cache / auth tier.
- sec2 does NOT include the P2P fork-convergence work (separate branch `feat/p2p-headers-first-ibd`),
  by design — this update is strictly sec1 + RPC hardening.

## Publish procedure (execute ONLY on explicit owner authorization — do NOT run yet)
1. Build sost-node from `release/v16.3.0-sec1-rpc` with a `build` dir inside the source tree,
   flags as above; confirm `sha256sum sost-node == 5b50a448…`.
2. Publish the single asset `sost-node-sec2` on the existing v16.3.0 release page alongside
   `sost-node-sec1`; do NOT move the v16.3.0 tag, do NOT overwrite `sost-node`, `sost-node-sec1`,
   `sost-miner`, or `sost-cli`. Upload `SHA256SUMS.v16.3.0-sec2`.
3. Operator note: sec2 supersedes sec1 (contains all sec1 fixes); miner/cli unchanged.
4. VPS deploy (separate authorization): stop node, swap in sost-node-sec2 (miner untouched),
   restart; verify getblockcount, then confirm `getblockhash ["str"]` and `getblock [[[[1]]]]`
   return errors and RSS stays flat.
