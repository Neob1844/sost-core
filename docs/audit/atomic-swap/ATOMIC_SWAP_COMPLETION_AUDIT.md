# SOST ⇄ wSOST Atomic Swap — Completion Audit

**Date:** 2026-10-15. **Type:** audit only. No fixes were implemented and nothing was deployed. No mainnet node or miner was touched, no Ethereum Mainnet was used, and Sepolia was accessed read-only.

**Revisions audited:**

| Ref | Commit |
|---|---|
| origin/main (production lineage) | `36ea6d4f` |
| origin/release/v40000-prep (V17 candidate) | `3d322551` |
| origin/feat/wsost-stage2-real-e2e | `8d28c881` |
| origin/feat/btc-atomic-swap-complete | `f898f11a` |
| origin/fix/htlc-claim-refund-block-path-v14-5 | `3272b1f5` (already an ancestor of main and release) |
| origin/feat/sost-dex-v2 | `b7bb9e3d` |

**Workspace:** `/home/sost/SOST/sostcore/atomic-swap-audit/`

| Path | Contents |
|---|---|
| `wt-*` | worktrees |
| `build-devnet` | built from release/v40000-prep with `-DSOST_DEVNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`. HTLC activates at V14_5=11 and relays at V14_7=12. |
| `build-main-mainnet` | built from origin/main with mainnet flags |
| `harness/` | E2E scripts |
| `foundry-audit/` | adversarial Solidity tests |
| `work/` | run directories, logs and `results.json` files |

> **Bottom line:** the primitives are real and they interoperate. I ran a real SOST devnet HTLC against the real AtomicSwapHTLCv2 + WSOST on Anvil in both directions, and the claim, refund, boundary and secret-extraction cases all pass (43/43). But two real users cannot complete a swap with shipped tools today:
> - No shipped signer accepts HTLC transactions. The V17 `signtx` refuses all three HTLC tx types.
> - There is no swap CLI, watcher or relayer integration.
> - No tool enforces confirmation depth or timelock orientation.
>
> The audit also found two serious defects, each with a verified repro:
> - **K-1 (CRITICAL, EVM):** `AtomicSwapHTLCv2.claimNative` can drain every native-ETH escrow. This contract is the one deployed on Sepolia.
> - **K-2 (CRITICAL, SOST liveness, production lineage):** an HTLC CLAIM accepted near its deadline stays in the mempool after it expires and poisons every block template. Mining stalls.

---

## A. Inventory

**Status legend:**

| Status | Meaning |
|---|---|
| IMPL | code exists |
| T_LOCAL | unit or Foundry tests |
| T_DEVNET | ran on a real devnet node in this audit |
| T_SEPOLIA | ran on Sepolia (by the stage2 branch; I verified it read-only) |
| MAINNET_READY | ready for mainnet |
| MISSING | not present |

| Piece | Where (file:line, main unless noted) | Status |
|---|---|---|
| SOST HTLC consensus: tx types 0x10/0x11, outputs 0x12/0x13 | `include/sost/transaction.h:40-41,70,76`; payload layout `:215-271` (hashlock 32, refund_height u64 LE, claim_pkh 20, refund_pkh 20; witness = 32-byte preimage) | IMPL, T_LOCAL, **T_DEVNET**. Consensus-live on mainnet since 16000. |
| Activation gates | `include/sost/params.h:1149-1175` (V14_5 = 16000 mainnet / 11 devnet; V14_7 = 17000 / 12); `include/sost/atomic_swap.h:143,156,181` | IMPL, T_LOCAL (block-path test 33/33 on the mainnet build) |
| Validation rules R17–R24 | `src/tx_validation.cpp:277-323` (R17/R18), `:508-650` (R19 structure, R21 sha256, R22 claim < refund_height, R23/R24 refund ≥ refund_height, claim/refund key from payload), `:772` (S9), `:893` (relay typed-payload exemption) | IMPL, T_LOCAL, **T_DEVNET** |
| Block-path exemption | `src/utxo_set.cpp:316-322`; `src/sost-node.cpp:6806` | IMPL, T_DEVNET |
| Mempool / policy | `src/mempool.cpp:429` (expired LOCK eviction), `:483` (template filter, **LOCK only**); `src/sost-node.cpp` post-block cleanup (`release:9054`) | IMPL. **Defective for CLAIM (K-2).** |
| Create (lock builder) | `src/atomic_swap_helpers.cpp:24-63,133-171`; RPC-shaped handler `:500-554` (`"unsigned":true`) | IMPL, T_DEVNET. Single input, change back to sender, no coin selection. |
| Claim builder | `src/atomic_swap_helpers.cpp:66-103,173-208,556-598` | IMPL, T_DEVNET |
| Refund builder | `src/atomic_swap_helpers.cpp:105-127,210-237,600-636` | IMPL, T_DEVNET |
| CLI | `src/sost-cli.cpp:1463-1525`: `createhtlclock` / `claimhtlc` / `refundhtlc` / `decodehtlc` (local, unsigned) and `gethtlcstatus` / `listhtlclocks` (node) | IMPL, T_DEVNET. **Produces unsigned hex only.** |
| Signing (official) | none. `sost-cli send` / `createtx` cannot build HTLC txs. | **MISSING** |
| Signing (founder tool) | `tools/sost_signtx.cpp` (`sost-signtx <hex> <privkey_hex> …`), documented in `docs/V15_OTC_FOUNDER_TEST_RUNBOOK.md:87-136` | IMPL, T_DEVNET (B5). **Raw private key on argv.** Not a user tool. |
| Signing (lab) | `tests/bridge/lab/sost_lab_sign.cpp` (release/stage2 only) | LAB only |
| V17 offline signing (buildtx/signtx/verifytx/combinetx, PSST) | release `src/sost-cli.cpp:2109-2440`; `src/multisig_psst.cpp:246,337` | IMPL for STANDARD txs. **Refuses HTLC: B1–B3** (`:2386` tx_type, `:2409` spent type 0x12, `:2415` output type). |
| Broadcast | `sendrawtransaction` (node and CLI) | IMPL, T_DEVNET |
| Secret extraction (SOST) | `gethtlcstatus` → `revealed_preimage` (`src/sost-node.cpp:4919-5017`, chain scan); `decodehtlc` on the claim tx | IMPL, **T_DEVNET** (E4, E5, D2.4) |
| Secret extraction (EVM) | `Claimed(swapId, preimage, …)` event | IMPL, T_DEVNET (E3, via `eth_getLogs`) |
| Timelocks | SOST: absolute height (claim < rh ≤ refund). EVM: absolute `block.number` (claim < refundTime ≤ refund). | IMPL, T_DEVNET (D6/D7). **Cross-chain ordering: MISSING in tooling.** |
| Watcher | `include/sost/atomic_swap_watcher.h`, `src/atomic_swap_watcher.cpp` (pure decision library, never wired to a node or EVM; comment still says "gate INT64_MAX") | IMPL, T_LOCAL only |
| Session / coordinator | `src/atomic_swap_session.cpp:299-365`, `tools/otc_swap_coordinator.cpp` (`otc-coordinator`, persists to file, never signs). Models only the SOST-initiator orientation and compares the counterparty timeout in **SOST heights**. | IMPL, T_LOCAL |
| Relayer | none for swaps (the bridge relayer in `ops/sostbridge` is for wrap/unwrap, not swaps) | **MISSING** |
| Ethereum AtomicSwapHTLCv2 | `contracts/atomic-swap/src/AtomicSwapHTLCv2.sol` (identical on main, release and stage2) | IMPL, T_LOCAL (71 + 63 Foundry pass), T_DEVNET (Anvil), T_SEPOLIA. **CRITICAL bug K-1.** |
| Sepolia deployment | `0x395295622fDE4702BA199e4898F85B9d85175794`. Read-only check: runtime keccak `0x0aab418f…7167` = documented; executable bytecode equals the source compile (metadata stripped); ETH balance 0, wSOST balance 0 at block 11,921,639. | T_SEPOLIA (stage2 doc 28/28). **Carries K-1.** |
| wSOST integration | WSOST is a plain 8-decimal ERC-20 with no transfer pause and no hooks (`contracts/wsost/src/WSOST.sol:17,123-144`) | T_LOCAL, T_DEVNET |
| Web UI | `website/atomic-swap.html`, `atomic-swap-console.html`, `js/atomic-swap-evm.js`, `sost-dex-dashboard.html` | DEMO_ONLY / PARTIAL (§I) |
| Tests | SOST unit (release devnet build): htlc-lock 44, helpers 22, rpc 16, policy 49, coordinator 39, status/watcher/session/e2e-sim pass. Block-path test: 33/33 on the mainnet build (on devnet only the 3 mainnet-constant asserts fail, as expected). `test-htlc-expired-lock-template` is **SKIPPED on both builds** (it only runs under TESTNET_FORKS). | T_LOCAL |
| Docs | `docs/ATOMIC_SWAP_CLI_GUIDE.md` (says "sign" without naming any shipped signer), `docs/bridge/ATOMIC_SWAP_WSOST.md`, `docs/v15/ATOMIC_SWAP_THREAT_MODEL.md` | Partly stale. Not reproducible for users. |

**MAINNET_READY:** none of the pieces above. The SOST consensus layer is live and behaves correctly, but its mempool/template companion is unsafe (K-2).

---

## B. SOST-side real E2E (devnet)

I ran this on a real DEVNET_FAST node with the real `sost-miner --realtime`, and broadcast every tx with `sendrawtransaction`. Run directories: `work/run-cases`, `work/run-reorg`.

| Step | Result |
|---|---|
| Create lock (`sost-cli createhtlclock`) | builds correctly; `decodehtlc` round-trips the fields |
| Sign | only possible with the **lab signer** or `sost-signtx` (privkey on argv) |
| Verify | V17 `verifytx <raw hex>` reports `INVALID: R17 … refund_height 60 must be > current height 60` for a valid lock (B4). It validates at the fixed MULTISIG activation height instead of the tip, so it is not HTLC-aware. |
| Broadcast / confirm | accepted, mined, `gethtlcstatus` = locked, all fields verified (D1.1) |
| Claim with secret | accepted, +amount−fee (D1.4, D2.3) |
| Extract secret from chain | `revealed_preimage` and `decodehtlc(getrawtransaction)` both match (E4, E5) |
| Refund after timeout | rejected before rh (R24), accepted at rh (D3, D4, D7) |

**V17 offline-tool integration: does not work.** Repro: `harness/e2e_reorg_tools.py` B1–B3. I wrapped real unsigned HTLC txs in `sost-unsigned-tx-v1` files and ran `sost-cli --wallet … signtx f.json --network dev --yes`:
- LOCK → `Error: unsupported output type in transaction`
- CLAIM and REFUND → `Error: only standard transfers are supported by signtx`

The PSST path also rejects them (`multisig_psst.cpp:337`: only v2 STANDARD).

**Missing to integrate with the V17 offline tools:**
1. `buildtx`-style **watch-only builders that emit a `sost-unsigned-tx-v1` JSON** for lock, claim and refund. Each must carry the spent output's amount and type (0x12 for claim/refund), the signer address and the decoded HTLC terms (hashlock, refund_height, claim/refund address, amount). The current builders print bare hex and need the caller to supply prev_amount and pkh by hand.
2. `signtx` must accept:
   - tx_type 0x10/0x11
   - spent type 0x12
   - outputs 0x12 (lock) and 0x13 (claim witness)

   It should resolve the signing key from the LOCK payload: claim_pkh for CLAIM, refund_pkh for REFUND. That cannot be the `address` field in the file, which an attacker could edit, so it must be checked against the payload. Before signing it must **display** the HTLC terms (hashlock, refund height vs current height, counterparty, amount) and, for a CLAIM, warn when `refund_height - tip` is small (K-2).
3. `verifytx` must validate HTLC txs at the **current tip height**, and with the spent LOCK output's payload, so it can check R21–R24 offline.
4. Reservation-ledger support for the LOCK's funding input, like `buildtx`.
5. A coin-selecting lock builder. Today it takes exactly one input, chosen by hand.

**No consensus change is required for any of this.**

---

## C. Ethereum side

**Suites run:**
- `contracts/atomic-swap`: **71/71 PASS**
- `contracts/wsost` (incl. `WsostAtomicSwap.t.sol` fuzz + 3 invariants): **63/63 PASS**
- Audit suite `foundry-audit/test/AuditHTLCv2.t.sol`: **9/9 PASS**. The tests are written to *demonstrate* the findings.

| Property | Result |
|---|---|
| Hashlock | `sha256(abi.encodePacked(bytes32))` = sha256 of 32 raw bytes, the same as SOST R21 (vector test E0, plus E2–E5 on devnet) |
| Timelock / boundary | claim at refundTime−1 OK, at refundTime `EXPIRED`; refund at refundTime−1 `NOT_YET`, at refundTime OK. Fuzz proves exactly one of claim/refund is possible at every block. Confirmed on Anvil with manual mining (D6.3–D7.4). |
| Token transfers / fee-on-transfer | balance-delta accounting plus `minReceive` (existing tests). wSOST is not fee-on-transfer. |
| Replay / duplicate swap | `SWAP_EXISTS`, `NOT_LOCKED` on double claim or refund-after-claim (existing tests + D5.8) |
| Reentrancy | `nonReentrant` + state-before-interaction (existing test) |
| Approvals | an allowance granted to the HTLC is usable only by its owner, because `transferFrom(msg.sender…)` (audit test) |
| Wrong secret / caller / recipient | `BAD_PREIMAGE`, `NOT_CLAIMER`, `NOT_REFUNDER`. Claims cannot be redirected. |
| Wrong token / decimals | **not bound.** Any token and amount is accepted; the counterparty must verify (audit test `test_K_decimals_and_token_not_bound`) |
| Pause / failure | the HTLC has no pause. If a token freezes transfers, claim *and* refund both revert until it unfreezes (audit test). WSOST has no transfer pause (its mint pause only stops mints), so this does not apply to wSOST. |
| **claimNative on an ERC-20 swap** | **CRITICAL K-1** (below) |
| swapId front-run / look-alike | **K-3** (below) |

---

## D. Local cross-chain E2E (real SOST devnet + Anvil + real WSOST/HTLCv2)

**Harness:** `harness/e2e_cases.py` → **43/43 PASS** (`work/run-cases.out`, `work/run-cases/results.json`) and `harness/e2e_reorg_tools.py` → **13/14** (`work/run-reorg.out`). The one "FAIL" is B4, which is itself a finding (`verifytx` is not HTLC-aware).

The SOST side has no mocks. SOST txs are built by the unchanged `sost-cli` and signed by the lab signer, because no shipped signer exists.

| # | Case | Result |
|---|---|---|
| 1 | SOST→wSOST success | PASS (D1.1–D1.5). Alice locks SOST (rh = tip+40), Bob verifies every field + 1 conf, Bob locks wSOST (refundTime +20), Alice claims wSOST, Bob extracts the preimage from the `Claimed` log by swapId and claims SOST. |
| 2 | wSOST→SOST success | PASS (D2.1–D2.6). Bob initiates on EVM (longer timeout), Alice locks SOST (shorter), Bob claims SOST revealing the secret on SOST, Alice reads `revealed_preimage` and claims wSOST. |
| 3 | Alice disappears | PASS (D3). Early refunds are rejected on both chains (NOT_YET / R24); both refund after their timeouts; status `refunded`. |
| 4 | Bob disappears | PASS (D4). Alice refunds at rh. |
| 5 | Wrong secret | PASS (D5.1–D5.8): R21, wrong key, early refund by the claim key, BAD_PREIMAGE, NOT_CLAIMER, non-32-byte preimage refused by the CLI, SOST replay rejected (S1), EVM double claim. |
| 6 | Claim just before timeout | PASS. SOST: broadcast at tip = rh−2 and mined in block rh−1; at tip = rh−1 it is rejected R22. EVM: claim in block rt−1 succeeds, in rt reverts. **This exact timing exposes K-2.** |
| 7 | Refund just after timeout | PASS. SOST: rejected at spend height rh−1, mined in block rh. EVM: reverts in rt−1, succeeds in rt. |
| 8 | Node / tool restart midway | Node: PASS (D8.1). SIGTERM + restart keeps the height and the open lock; the swap then completes. Tool: **MISSING.** There is no swap tool holding state; the harness re-derived everything from chain data (lock txid + swapId). `otc-coordinator` persists sessions but drives no chain. |
| 9 | SOST reorg before finality | **Real reorg, loss demonstrated** (D9.1–D9.4). Alice's lock has 1 conf on node A, and Bob locks wSOST. Alice double-spends the funding input on node B (offline), mines a longer branch and delivers it with `submitblock`. Node A reorganises, the lock disappears, Alice claims Bob's wSOST, and Bob's SOST claim fails (`S1 missing UTXO`). **The protocol is fine; nothing enforces a confirmation depth.** |
| 10 | Ethereum reorg equivalent | Demonstrated with `evm_snapshot`/`evm_revert` (D10.1). Alice acted on a 1-block EVM lock, the lock was reverted, Bob still claimed SOST, and Alice's wSOST claim reverts `NOT_LOCKED`. The responder must wait for EVM finality. |
| K-TP | Near-deadline claim → template poisoning | **Defect reproduced** (K-2, below) |

**Bridge invariants:** after every phase, wSOST totalSupply, totalMinted, totalBurned, burnNonce and mintPaused, plus the Bridge Vault's SOST balance, are unchanged.

---

## E. Secret flow (byte order and encoding)

Fixed vector: `P = 000102…1f` and `H = sha256(P) = 630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd`.

| Step | Check | Evidence |
|---|---|---|
| E0 | python `hashlib` gives H | e2e_cases |
| Solidity | `sha256(abi.encodePacked(P)) == H` | `foundry-audit/test/AuditHTLCv2.t.sol::test_E_hash_vector_matches_sost_R21` |
| E1 | SOST `createhtlclock` hashlock hex → `decodehtlc` shows the identical hex (raw byte order, no reversal) | devnet |
| E2 | `gethtlcstatus.hashlock` == EVM `getSwap.hashlock` (bytes32 hex) == H | devnet + Anvil |
| E3 | first claim (EVM) emits `Claimed`; counterparty extracts P via `eth_getLogs` filtered on topic1 = swapId | Anvil |
| E4 | second claim (SOST) with the extracted hex is accepted (R21 recomputes sha256 over the 32 payload bytes); `revealed_preimage` == P | devnet |
| E5 | independent path: `decodehtlc(getrawtransaction(claim))` preimage == P | devnet |

**Hash function, size and representation:** both chains use SHA-256 over exactly 32 bytes and lowercase hex of the raw bytes. SOST enforces the 32-byte length with R18 and the CLI (D5.6); the EVM type is bytes32. The reverse direction (secret revealed on SOST, used on EVM) is covered by D2.

Gap: these checks live in my audit harness. The repository itself has no cross-chain vector test that pins this, so one should be added to CI (see blockers).

---

## F. Timelock safety rule

**Definitions:**
- **Initiator:** the party that generates the secret and locks first, on chain X.
- **Responder:** the party that locks second, on chain Y, with the same hashlock.
- Every deadline must be compared in **wall-clock** terms, because the chains count different units: SOST heights (target 600 s, cASERT) vs EVM `block.number` (12 s slots, ~1 % missed).

**Rule:** `T_X(earliest plausible wall time) ≥ T_Y(latest plausible wall time) + Δ`, with `Δ = detect + operate + include + bury`.

| Component | Value |
|---|---|
| detect | watcher latency ≤ 10 min |
| operate | build + **offline/manual signing** ≤ 6 h for a human operator (≤ 30 min if automated) |
| include + bury on chain X | SOST: claim mined at least 6 blocks before rh (this also avoids K-2). EVM: `finalized` ≈ 13 min. |
| lock confirmation before the responder locks | SOST ≥ 6 blocks (more for large swaps: one miner holds ~90 % of hashrate and can reorg at will). EVM: `finalized` tag. Bounded by D9 and D10. |
| responder's own claim | must be submitted with ≥ 6 SOST blocks / ≥ 2 epochs of headroom before its deadline |

**Orientation:**
- **SOST→wSOST (SOST holder initiates): `T_SOST > T_EVM + Δ`.** The risk is SOST blocks arriving *fast*. I computed this with a Poisson tail at 1e-6. With T_EVM = 24 h (≈7,200 blocks, plus 2 % for missed slots) and Δ = 6 h:
  - at the current hashrate SOST needs ≥ 248 + 6 blocks
  - under a 2× hashrate surge before cASERT reacts, ≥ 455 + 6 blocks
  - **Recommendation: T_EVM = 24 h, T_SOST = tip + 480 blocks (~80 h nominal).**
- **wSOST→SOST (EVM holder initiates): `T_EVM > T_SOST + Δ`.** The risk is SOST blocks arriving *slowly*. The responder's SOST deadline then falls later in wall time, the initiator can reveal late, and the responder's EVM claim window can close. With T_SOST = tip + 36 (6 h nominal), the 1e-6 latest wall time to reach that height is:
  - 13 h at full hashrate
  - 25 h at 0.5×
  - 121 h at 0.1×. That is realistic if the ~90 % miner leaves.

  **Recommendation: T_SOST = tip + 36 and T_EVM ≥ 6 days, or restrict v1 to the SOST-initiator orientation until hashrate decentralises.**
- The existing tests used arbitrary pairs (+120 SOST vs +40 EVM; +12 vs +5) with no wall-clock comparison. `otc-coordinator` compares the counterparty deadline in SOST heights and supports only the SOST-initiator orientation. The web console only shows a warning text. **Nothing enforces this rule.**

---

## G. What the swap cannot touch (confirmed)

- **No wSOST mint and no burn.** AtomicSwapHTLCv2 contains no mint, burn or vault call (grep), and it only calls `transfer`/`transferFrom`/`balanceOf` on the token. Foundry invariants (wsost) plus my E2E show totalSupply, totalMinted, totalBurned, burnNonce and mintPaused unchanged after every phase.
- **Bridge Vault not unlocked.** The vault address's SOST balance was unchanged in every run. The swap never references the vault.
- **Gold Reserve / PoR untouched.** There are no references in `src/atomic_swap*`, `include/sost/atomic_swap*` or the contract (the only hit is a comment). The wsost invariant also checks the Gold Reserve balance.
- **Native SOST is never burned.** LOCK → CLAIM/REFUND conserves value: claim pays `lock − fee` (marker dust + transfer, both to the claimant); refund pays `lock − fee`. The fee goes to the miner.

---

## H. CLI (minimal usable flow)

**Today (main):** `createhtlclock`/`claimhtlc`/`refundhtlc` produce unsigned hex. Using them requires:
1. hand-picking a UTXO and typing prev_amount and the pkh
2. a non-shipped signer
3. `sendrawtransaction`
4. polling `gethtlcstatus`
5. reading the preimage by hand

**Proposed commands** (all wallet-side; no consensus change):

```
sost-cli swap new        --role initiator|responder --give SOST:<amt> --want wSOST:<amt> --counterparty-sost <sost1..>
                         --counterparty-evm <0x..> --evm-chain <id> --evm-htlc <0x..> --evm-token <0x..>
                         [--hashlock H] --out swap.json            # generates secret (initiator), applies §F rule, stores encrypted
sost-cli swap inspect    swap.json [--evm-rpc URL]                  # both legs, confirmations, deadlines in blocks AND wall time, next safe action
sost-cli --from-address A swap build-lock   swap.json --out lock.unsigned.json      # watch-only, coin selection, reservation ledger
sost-cli --wallet cold.json signtx lock.unsigned.json --out lock.hex               # signtx extended to HTLC (B.2)
sost-cli verifytx lock.hex --swap swap.json                                        # tip-height HTLC checks
sost-cli sendrawtransaction lock.hex
sost-cli swap verify-counterparty swap.json --evm-rpc URL --min-evm finalized       # token/amount/hashlock/claimer/refundTime/chainId/contract
sost-cli swap extract-secret swap.json --evm-rpc URL | --sost              # Claimed log by swapId, or revealed_preimage
sost-cli swap build-claim  swap.json --out claim.unsigned.json            # refuses when refund_height - tip < 6
sost-cli swap build-refund swap.json --out refund.unsigned.json           # refuses before refund_height
sost-cli swap watch        swap.json --evm-rpc URL                         # resumable: prints/queues the next action after restart
```

The EVM leg can stay in any wallet. `swap inspect` and `swap verify-counterparty` must be **read-only** against the EVM RPC.

**Missing node RPC:** `gethtlcstatus` lacks `confirmations` / `lock_height` / `spent_by_txid` (the lock height is computed internally at `sost-node.cpp:4993` but not returned).

---

## I. Web DEX / Atomic Swap UI

**Overall: DEMO_ONLY / PARTIAL. Not FUNCTIONAL.**

| Page | Classification | Details |
|---|---|---|
| `website/atomic-swap.html` | DEMO_ONLY | No signing or broadcast. Every pair has `htlc:null` (`:351-365`). Generates the secret in WebCrypto (`:461-466`). The confirm path (unreachable today) would store the **plaintext preimage in `localStorage`** (`:491,533,577`). Timelocks are SOST +240 and EVM +240 with no ordering check (`:469-470`). |
| `atomic-swap-console.html` + `js/atomic-swap-evm.js` | PARTIAL founder tool | Real `eth_sendTransaction` behind a typed phrase, but the **v1 ABI** (`claim`/`refund` selectors, `evm.js:21-31`): it cannot drive v2 on Sepolia and does not know wSOST. The SOST leg only prints CLI text. The preimage is pasted through `prompt()`. Extraction is not automatic (the `Claimed` topic is defined and never used). The timelock ordering is warning text only (`:346`); defaults are SOST +20 / EVM +240, never compared. |
| `sost-dex-dashboard.html` (in main) | DEMO_ONLY, labelled | A random-walk chart ("Demo series", `:355`, LCG `:652-666`), a fake **completed swap** `CUR=9` shown as a lifecycle (`:706`, "Demo" pill), "Demo · empty" orders, and the `dex-liquidity-sim.js` hardcoded refPrice 0.15 / $1000 reserves (loaded but unused). |
| `dex-crypto-test.html` | test page | Generates private keys in the browser and sits in the production `website/` directory. |
| feat/sost-dex-v2 | DEMO_ONLY, unmerged | Unconditional `RELAY='http://127.0.0.1:8781'`. |

No page invents prices or balances presented as real without a label, but the "completed swap" lifecycle demo is in production.

**A real UI needs:**
- the v2 ABI and the configured wSOST/HTLC per chainId
- a SOST leg signed by the wallet (never by the page)
- counterparty-lock verification at finality depth
- automatic extraction
- the enforced §F rule in wall time
- encrypted secret persistence plus a refund watcher that survives a restart
- removal of the demo lifecycle from production
- a contract fix and audit first (K-1)

**And only after the CLI E2E exists.**

---

## J. BTC ⇄ SOST (separate; not part of the done criterion)

**BTC_SWAP_STATUS: main = DISABLED, branch = LAB.**

**On main:**
- Off by build flag `SOST_BTC_HTLC_SIGNING` (OFF, `CMakeLists.txt:498`) **and** runtime env `SOST_BTC_ATOMIC_SWAP_ENABLED`. Without the flag, `SignBtcHtlcLockFunding` returns `disabled_result()`; the real libwally body (`src/atomic_swap_btc_signing.cpp:346-567`) is compiled out.
- Claim, refund and funding signers, the P2WSH script (`OP_SHA256` + CLTV, `src/atomic_swap_btc.cpp:96-128`), a bitcoind backend, the watcher, the state machine and the coordinator all exist.
- There is **no BTC CLI/RPC**.

**On `feat/btc-atomic-swap-complete` (11 commits, unmerged):** claims a regtest + SOST devnet E2E (claim, refund, reorg, wrong preimage), but:
- only prose results are committed; there are no logs
- the scripts hard-code a scratchpad path
- the docs are stale

**Missing for READY:**
- `OP_SIZE 32 OP_EQUALVERIFY` in the redeem script. Without it a non-32-byte preimage revealed on BTC is unusable on SOST.
- reproducible committed evidence
- a merge
- wall-clock cross-chain timeouts
- BTC CLI/RPC
- a release build with libwally plus a hash
- an external audit
- an operator sign-off

---

## K. Security findings

| ID | Finding | Severity | Repro | Fix | Consensus change |
|---|---|---|---|---|---|
| **K-1** | `AtomicSwapHTLCv2.claimNative` does not check `s.token == address(0)`. The claimer of **any ERC-20 swap**, including a self-made worthless 18-decimal token, is paid `lockedAmount` **wei of native ETH** from other users' native escrows; the swap is marked CLAIMED. It drains every native escrow. The same contract is deployed on Sepolia (bytecode-equal), and `DEPLOY_HTLCV2.md` describes a mainnet deploy. The SOST⇄wSOST ERC-20 leg itself is not drained by this, but any ETH lock in the same contract is. | **CRITICAL** | `foundry-audit` → `test_K1_claimNative_on_erc20_swap_drains_native_escrow` (attacker gets the victim's 10 ETH; the victim's claim reverts `SEND_FAILED`) | add `require(s.token == address(0), "NOT_NATIVE")` to `claimNative`; redeploy as v3 (immutable); mark the Sepolia v2 deprecated; never deploy v2 to mainnet | no (EVM contract) |
| **K-2** | A near-deadline HTLC **CLAIM** accepted when `tip+1 < refund_height` stays in the mempool once block rh−1 is mined without it. At rh it is invalid (R22), but `BuildBlockTemplate` filters only expired **LOCKs** (`mempool.cpp:483`), and the post-block cleanup only evicts LOCKs (`:429`). Every template carries it, and every block the miner submits is rejected (`REJECTED: tx consensus fail: R22`). This is **permissionless and cheap**: anyone can lock dust to themselves and broadcast the claim just after block rh−2, since miners only refresh templates on a tip change. It is present on main (production lineage, HTLC relay live since 17000) and on release/v40000-prep. | **CRITICAL** (liveness) | `harness/e2e_reorg_tools.py` K-TP.1–5: two real nodes; block rh−1 mined without the claim; node A mined 0 blocks in 240 s; the claim is still in the mempool | policy only: evict and filter HTLC_CLAIM txs whose spent lock has `refund_height ≤ next_height` (store refund_height in the mempool entry at acceptance), or generically re-validate the template against `next_height` before serving it; optionally refuse claims with `refund_height − next_height < 2` at admission. Add a devnet regression test (the existing expired-lock template test is skipped on both mainnet and devnet builds). Urgent hot-fix candidate. | **no** (mempool/template policy) |
| K-3 | The swapId is caller-chosen. A mempool observer can front-run `lockERC20` with the same id (griefing), or pre-create a look-alike swap with the right hashlock but a different claimer, amount or token. | MEDIUM | `test_K2_swapId_frontrun_and_lookalike` | tools must verify every `getSwap` field and the `LockCreated` locker; derive the id with an unpredictable salt; in v3, consider `swapId = keccak(locker, params, salt)` | no |
| K-4 | Confirmation depth is not enforced anywhere. A responder acting on 1 conf loses funds after a reorg on either chain. On SOST one miner holds ~90 % of hashrate. | HIGH (tooling) | D9 (real SOST reorg + double-spend), D10 | the tool must require ≥ 6 SOST blocks (scaled with value) and EVM `finalized` before the second lock; `gethtlcstatus` should return confirmations | no |
| K-5 | Timelock orientation and margin are not enforced (§F); the coordinator mixes units | HIGH (tooling) | code review + §F computation | implement the §F rule in wall time in `swap new` / `verify-counterparty` | no |
| K-6 | No shipped signer for HTLC. The only in-tree one, `sost-signtx`, takes a **raw private key on argv** (ps-visible, shell history) and is the documented founder flow. | HIGH (key hygiene / usability) | B1–B3 (signtx refuses), B5 (sost-signtx works) | extend V17 `signtx` (§B) and deprecate `sost-signtx` | no |
| K-7 | `verifytx` (raw) validates at the fixed activation height, not the tip, and reports false INVALID for valid HTLC locks | LOW | B4 | validate at the node tip / a supplied height | no |
| K-8 | Wrong token / decimals / chainId are not bound by the contract (no signatures, any ERC-20) | MEDIUM (tooling) | `test_K_decimals_and_token_not_bound` | verify the token address == configured wSOST for that chainId, decimals == 8 and the contract code hash before locking | no |
| K-9 | Refund race / double claim / replay | none | D5.7, D5.8, fuzz partition | — | — |
| K-10 | Front-running a revealed preimage | none | SOST sighash commits to all outputs and the claim key (D5.2); EVM `NOT_CLAIMER` (D5.5) | — | — |
| K-11 | Secret reuse: a secret revealed once lets anyone who saw it claim any other swap with the same hashlock where they are the claimer | LOW (procedural) | by construction | tools must generate a fresh 32-byte CSPRNG secret per swap and refuse a known hashlock | no |
| K-12 | Hash collision / length | none | SHA-256 over exactly 32 bytes on both sides (R18, bytes32). The BTC leg lacks OP_SIZE (§J). | — | — |
| K-13 | Malformed HTLC | none | R17/R18/R19/R20/R23 unit tests (44 + 33 pass) | — | — |
| K-14 | Malleability | low | low-S enforced; the txid changes only if a signer re-signs; watchers key on the lock outpoint, not the claim txid | — | — |
| K-15 | SOST cross-network replay: the sighash binds the genesis hash, which devnet/testnet share with mainnet | INFO | code (`tx_signer.cpp` sighash) | the outpoints differ in practice; V17's PSST already binds chain_id. Optionally add network separation to HTLC tooling files. | no |
| K-16 | Watcher failure: there is no running watcher. If the responder misses the reveal before its deadline, it loses. | HIGH (operational) | D2/D1 needed manual extraction | resumable `swap watch` + alerting | no |
| K-17 | Web: plaintext preimage would be stored in localStorage; the browser-side key generator test page is in production `website/` | MEDIUM | §I file:line | encrypt or omit; move test pages out of the production tree | no |
| K-18 | `ComputeSighash` prints `[SIGHASH-DEBUG]` lines to stdout on every sign. They are noisy and break tool output parsing; they contain no secrets. | LOW | any signer run | remove or gate behind verbose | no |

---

## L. Done criterion

| # | Criterion | Status |
|---|---|---|
| 1 | Real SOST lock | ✅ devnet (lab-signed) |
| 2 | Real EVM lock | ✅ Anvil; Sepolia (stage2) |
| 3 | Claim on both sides | ✅ |
| 4 | Refund on both sides | ✅ |
| 5 | Secret extraction automatic or clearly operable | ⚠️ operable via RPC/logs (proved), not automated |
| 6 | SOST offline signing | ❌ V17 `signtx` refuses HTLC |
| 7 | Restart recovery | ⚠️ node yes; no swap tool to recover |
| 8 | Reorg handling | ❌ no depth enforcement (D9/D10 loss) |
| 9 | Timelock safety | ❌ rule defined here, not enforced |
| 10 | Full CLI E2E | ❌ needs a lab signer + manual steps |
| 11 | Adversarial tests | ⚠️ extensive, but they found 2 CRITICALs |
| 12 | No keys in browser | ⚠️ no private keys in the swap pages; preimage handled in the page and plaintext localStorage planned |
| 13 | Reproducible docs | ❌ CLI guide names no signer; BTC/stage2 evidence not portable |

---

## M. Final report

| Field | Status |
|---|---|
| SOST_HTLC_CONSENSUS | IMPLEMENTED + TESTED_DEVNET; mainnet consensus-live since 16000 (relay 17000), 0 mainnet txs; rules R17–R24 behave correctly |
| SOST_BUILD | PARTIAL — `createhtlclock`/`claimhtlc`/`refundhtlc` build correct unsigned hex; no coin selection, no unsigned-tx file |
| SOST_OFFLINE_SIGN | MISSING — V17 `signtx`/PSST refuse all HTLC types (B1–B3); only the lab signer or `sost-signtx` (privkey on argv) |
| SOST_BROADCAST | WORKS (`sendrawtransaction`, devnet) |
| SOST_CLAIM | WORKS on devnet (lab-signed); boundary correct (claim < rh) |
| SOST_REFUND | WORKS on devnet (lab-signed); boundary correct (refund ≥ rh) |
| SECRET_EXTRACTION | WORKS manually on both chains (`gethtlcstatus.revealed_preimage`, `decodehtlc`, EVM `Claimed` log); not automated; byte-identical vector proven |
| EVM_HTLC | FUNCTIONAL for ERC-20 legs, **CRITICAL K-1** (claimNative drains native ETH escrows); not externally audited |
| LOCAL_CROSSCHAIN_E2E | PASS 43/43 + 13/14 (the one fail is finding K-7) on a real SOST devnet + Anvil + real WSOST/HTLCv2 |
| SUCCESS_SWAP_BOTH_DIRECTIONS | PASS (D1, D2), lab signer |
| REFUND_BOTH_DIRECTIONS | PASS (D3, D4, D7) |
| RESTART_RECOVERY | PARTIAL — node restart OK; no stateful swap tool |
| REORG_HANDLING | FAIL (tooling) — real reorg causes responder loss without depth enforcement (D9, D10); protocol itself sound |
| TIMELOCK_SAFETY | NOT ENFORCED — rule + margins defined in §F |
| CLI_COMPLETE | NO |
| WEB_UI_STATUS | DEMO_ONLY / PARTIAL (v1-ABI founder console; demo lifecycle in production) |
| SEPOLIA_STATUS | TESTED (stage2, 28/28); deployed v2 bytecode verified read-only and carries K-1; holds 0 ETH / 0 wSOST now |
| ETHEREUM_MAINNET_STATUS | NOT DEPLOYED (`htlc-v2-config.json` addresses null) — must not be deployed as v2 |
| BTC_SWAP_STATUS | main DISABLED; feat/btc-atomic-swap-complete LAB |
| SECURITY_FINDINGS | 2 CRITICAL (K-1 EVM theft, K-2 SOST mining liveness), 4 HIGH (K-4 depth, K-5 timelock, K-6 signer, K-16 watcher), 4 MEDIUM, several LOW/INFO |
| CONSENSUS_CHANGE_REQUIRED | NO — every fix is wallet/CLI/mempool-policy/contract-redeploy. K-2 is policy (template/mempool) and needs a coordinated binary update, not a fork. |
| V17_DEPENDENCY | The offline-signing path must be built on V17's `buildtx`/`signtx`/`verifytx` (release/v40000-prep), which today exclude HTLC; the swap itself does not depend on V17 consensus (works on main's consensus) |

### ATOMIC_SWAP_STATUS = **NOT_READY**

The primitives are proven to interoperate (PARTIAL engineering). But two CRITICAL defects exist, one of them live on the production lineage, and there is no user-operable signing or CLI path. That rules out PARTIAL as a release status.

### BLOCKERS_TO_FUNCTIONAL

1. **Fix K-2:** filter and evict expired HTLC_CLAIM (and generally re-validate templates at `next_height`) in main and release; add a devnet regression test; ship as a coordinated policy update. This is urgent independent of swaps, because the mainnet relay is live.
2. **Fix K-1:** add `NOT_NATIVE` to `claimNative`, deploy v3, deprecate the Sepolia v2, and never deploy v2 to mainnet. Then get an external audit of v3.
3. Extend V17 `signtx` (+ `verifytx` at tip, + unsigned-file builders with coin selection and reservations) to HTLC LOCK/CLAIM/REFUND, binding the signing key to the LOCK payload and displaying the HTLC terms (§B items 1–5).
4. Build the `sost-cli swap` command family (§H): `new`, `inspect`, `verify-counterparty`, `build-lock`/`claim`/`refund`, `extract-secret`, `watch`. It needs persisted, encrypted swap state and restart recovery.
5. Enforce the §F timelock rule in wall time for both orientations, with defaults SOST-first T_EVM = 24 h / T_SOST = +480 blocks; EVM-first T_SOST = +36 / T_EVM ≥ 6 days, or disable EVM-first in v1. Refuse claims closer than 6 blocks to rh.
6. Enforce confirmation depth before the second lock (SOST ≥ 6 blocks scaled with value; EVM `finalized`). Add `confirmations`/`lock_height`/`spent_by` to `gethtlcstatus`.
7. Verify the counterparty fully: token == configured wSOST for that chainId, contract code hash, amount, claimer/refunder, refundTime, locker (K-3, K-8).
8. Add a repository CI test pinning the cross-chain hash vector (sha256, 32 bytes, raw-hex) on both the C++ and Solidity sides, plus a CLI-only E2E (no lab signer) on devnet + Anvil, both directions, refund paths, restart and reorg.
9. Write reproducible user docs (CLI guide naming the real signer and the §F/§K-4 rules); retire `sost-signtx` from the documented flows.
10. Web only after 1–9: v2/v3 ABI, wallet-side SOST signing, no plaintext preimage persistence, demo lifecycle removed from production.

---

## Reproduce

```
cd /home/sost/SOST/sostcore/atomic-swap-audit
# devnet build (release/v40000-prep):  cmake ../wt-release-v40000-prep -DSOST_DEVNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF
python3 harness/bootstrap.py work/base 30                     # fresh devnet, 30 blocks mined to a disposable Alice wallet
python3 harness/e2e_cases.py work/base work/run-cases         # D1-D8, D10, E   -> 43/43
python3 harness/e2e_reorg_tools.py work/base work/run-reorg   # B, D9, K-2      -> 13/14 (B4 = K-7)
(cd foundry-audit && forge test)                              # K-1, K-3, E vector, boundaries -> 9/9
(cd wt-release-v40000-prep/contracts/atomic-swap && forge test)   # 71/71
(cd wt-release-v40000-prep/contracts/wsost && forge test)         # 63/63
```

The harness's ports are SOST 19801/19811 (A) and 19802/19812 (B), and Anvil 18547/18548. It starts and stops only its own processes, by process group. All keys are disposable devnet/Anvil keys created in `work/`.
