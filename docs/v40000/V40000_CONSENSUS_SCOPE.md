# V40000 CONSENSUS SCOPE AUDIT

Status: **AUDIT / DESIGN REVIEW ONLY.** No consensus code was changed. Native multisig is
not implemented, native assets are not activated and reward consensus is not changed by
this document. **#40,000 is a target, not a commitment.**

Baseline audited: `release/v40000-prep` @ `bc8a45d9` (src/, include/, tests/, docs/),
the multisig design at `origin/design/native-multisig-40000` @ `13b02df4`
(`docs/design/NATIVE_MULTISIG_40000.md`, "DESIGN ONLY — IMPLEMENTATION NOT AUTHORIZED"),
and the real mainnet chain to height 30,428.

Chain pace: about 144 blocks/day (5,000 blocks in 34.7 days, V15 window). #40,000 is
about 9,570 blocks, or about 66 days, after 30,428.

## Verdicts

| Verdict | Value |
|---|---|
| NATIVE_MULTISIG_DESIGN_READY | **NO**. The design is sound in shape and consistent with the codebase on most points. Eight concrete design defects or gaps must be closed in a revision (§A.4). |
| NATIVE_ASSETS_ACTIVATION_READY | **NO**. The code is wired but deferred on mainnet (INT64_MAX). Fuzz/property tests, mempool asset validation, a live reorg test and replay automation are missing, and there are three accounting bugs (§B). |
| ECONOMIC_80_15_5 | **WATCH**. Not for #40,000 (ECONOMICS_80_15_5.md). |
| DECENTRALIZATION_40000_GATES_READY | **YES as defined and testable / NO as met** (DECENTRALIZATION_GATES_40000.md). |
| **BLOCK_40000_READINESS** | **NOT_YET** |

## Classification legend

| Code | Meaning |
|---|---|
| CONSENSUS_FORK | changes block or tx validity; needs a height-gated release |
| NODE_HARDENING | node code, policy or P2P change; no validity change |
| WALLET_CLI | sost-cli and wallet only |
| ETHEREUM_EXTERNAL | Solidity and EVM tooling; nothing on SOST |
| WEB_UI | website and explorer |
| RESEARCH_ONLY | analysis; nothing ships |

---

## A. Native multisig

### A.1 Target design vs codebase (validated item by item)

| # | Design item | Codebase today (`bc8a45d9`) | Assessment | Class |
|---|---|---|---|---|
| 1 | `OUT_MULTISIG = 0x50`, 0x51–0x5F reserved for custody | 0x50–0x5F unused in **both** tx-type and output-type namespaces. Validators are exact-match allow-lists, with no range tests on type bytes: R11 `IsActiveOutputType` `src/tx_validation.cpp:51-73`, R2 `:137-154`, S9 `:758-797`, block allow-list `src/sost-node.cpp:6842`. The only range check is on capsule sub-types (`capsule.h:48`). Today 0x50 is rejected by R11 and S9. | **OK**. Clean allocation. | CONSENSUS_FORK |
| 2 | `pubkey_hash` = `MSH = RIPEMD160(SHA256("SOST-MS1" ‖ policy))` | The output already has a 20-byte pkh field (`TxOutput`) | OK. 20-byte hash with a mandatory commit-then-reveal ceremony; a 32-byte variant is reserved for 0x51. | CONSENSUS_FORK |
| 3 | tx **version 2** with per-input `auth_kind` (0x00 single, 0x01 multisig) | R1 requires `version == 1` (`tx_validation.cpp:128-132`). The parser accepts any u32 version, and inputs are a fixed 133 bytes (`transaction.cpp:351,423`). **NODE_BIND/HEARTBEAT skip the per-tx validator** (`sost-node.cpp:6826-6832`), and their shape check (`src/node_participation.cpp:91-103`) **does not check the outer `tx.version`**; jackpot pins version 1 (`jackpot.h:339`). All 30,596 mainnet txs are version 1 (measured). | **Gap.** "Version 2" is not yet a clean namespace. A v2-encoded 0-input node tx is accepted today. The design must fence it: v2 auth only for STANDARD (and any explicitly listed types), and outer version == 1 required for node txs from the fork height. | CONSENSUS_FORK |
| 4 | 1 ≤ M ≤ N ≤ 15; 3-of-5 for the bridge vault (observers 2-of-3, no key/machine overlap) | Nothing exists | OK as specified. N = 15 gives policy 2 + 33·15 = 497 B per input. Inputs ≤ 256, and MAX_TX_BYTES_STANDARD = 16,000, which allows about 25 3-of-5 inputs per standard tx. | CONSENSUS_FORK |
| 5 | Canonical pubkeys: 33-byte compressed, on curve, strictly increasing byte order | Input pubkeys are already 33 bytes and parsed with `secp256k1_ec_pubkey_parse(…,33)` (`tx_signer.cpp:361`); prefix checked at `:478` | OK. Reuse. | CONSENSUS_FORK |
| 6 | Exactly M signatures; strictly increasing key indexes < N; each sig checked only against `PK[idx]` | Nothing exists. Legacy `script.cpp` CHECKMULTISIG is Bitcoin-style trial verification (`script.cpp:245-323`), which is precisely what the design forbids | OK. Deterministic M verifications, no trial-and-error. | CONSENSUS_FORK |
| 7 | LOW-S only | **Already consensus.** `ValidateRSRange` rejects zero, out-of-range and high-S values (`tx_signer.cpp:255-283`, code S5_HIGH_S) | OK. Reuse. | — |
| 8 | Sigcheck cap 12,000 per block, counted structurally before verification; 1,500 per tx policy | **No sigop/sigcheck limit exists today** (grep finds nothing). Limits are 1 MB/block, 100 kB/tx consensus, 65,536 txs/block, inputs/outputs ≤ 256 | **New consensus rule.** The design's counting table (coinbase/jackpot 0, v1 input 1, v2 multisig K, NODE_BIND 2, HEARTBEAT 1) must be checked against the worst case existing today. A 1 MB block of v1 inputs at 133 B each is about 7,500 sigchecks, so 12,000 cannot invalidate any historical block. A historical replay must still assert this. | CONSENSUS_FORK |
| 9 | Frozen 32-byte CHAIN_ID per network in sighash v2 | Sighash v1 = `version ‖ tx_type ‖ hashPrevouts ‖ prev_txid ‖ prev_index ‖ spent_amount ‖ spent_type ‖ hashOutputs ‖ genesis_hash` (`tx_signer.cpp:154-181`). **There is no chain id, and genesis is shared by all three networks** (sost-cli hardcodes one genesis for every `--network`, `sost-cli.cpp:1573`). So today a v1 signature replays across mainnet/testnet/devnet when the prevout exists | OK. The design fixes this for v2 only, with v1 unchanged. The literals are pinned in the design (mainnet `3ed1273b…a2e4`, testnet `301a71e1…bec3`, devnet `9d651d4c…7fbe`), and a test must assert them byte-for-byte. | CONSENSUS_FORK |
| 10 | bech32m (0x2bc830a3) with HRPs `sostms` / `tsostms` / `dsostms`; 21-byte data (0x01 ‖ MSH); lowercase only | **Not implemented.** The current address is `"sost1" + 40 hex` with **no checksum**, the same string on every network (`src/address.cpp:16-42`). The only bech32 code is the BTC HRP helper via libwally | New WALLET_CLI code: an encoder/decoder plus the design's vectors. Not consensus (consensus sees only MSH). | WALLET_CLI |
| 11 | Offline flow `createmultisig` / `buildtx` / `signtx` / `combinetx` / `verifytx` / `finalizetx` / `sendrawtransaction` with the `sost-psst-v1` file | `buildtx`, `signtx` (`sost-cli.cpp:1556-1805`, single-sig, `sost-unsigned-tx-v1`) and `sendrawtransaction` exist. **`createmultisig`, `combinetx`, `verifytx`, `finalizetx` and `sost-psst-v1` do not** | Build on the existing offline signer. | WALLET_CLI |
| 12 | Rotation by spending to a new policy; never mutate UTXO policy | The UTXO model has no mutable policy | OK. The design's 7-step bridge migration is operational. | WALLET_CLI + ETHEREUM_EXTERNAL |
| 13 | Legacy script/CHECKMULTISIG must NOT become consensus | `include/sost/script.h`, `src/script.cpp` (stack engine, CHECKMULTISIG, P2SH, `sost3` addresses, `MULTISIG_ACTIVATION_HEIGHT = 2000`) and `src/psbt.cpp` (multisig finalisation is a stub, `:419`) are **compiled into the `sost-core` library** (CMakeLists `:237-238`). They are reached only by `tests/test_multisig.cpp` and `tests/test_psbt.cpp`; nothing in src/ includes them | Not consensus-reachable today, but dangerous to keep (see 0x30 below). The design itself (§11 q7) decides "remove". | NODE_HARDENING (removal) |
| 14 | Output payload "≤ 512" (design text) | **Signed txs are effectively capped at 255-byte payloads.** `ComputeHashOutputs` encodes the payload length as **1 byte** and returns a poison hash if > 255 (`tx_signer.cpp:133-141`). `ValidateOutputsForSighash` rejects > 255 (`:500-512`). R13's 512 only matters for unsigned paths | **Design defect.** Correct the text, and decide whether sighash v2 `hashOutputs` keeps the 1-byte length (and the 255 cap) or moves to u16. | CONSENSUS_FORK |

### A.2 The 0x30 collision (finding)

The byte value **0x30 has three meanings** in the tree:

| Namespace | Constant | Where | Status |
|---|---|---|---|
| output type | `OUT_NODE_PROTOCOL = 0x30` | `include/sost/transaction.h:87` | **LIVE on mainnet.** 5 outputs since height 30,194 (NODE_BIND/HEARTBEAT carriers, amount 0, never in the UTXO set) |
| tx type | `TX_TYPE_ASSET_GENESIS = 0x30` | `include/sost/transaction.h:98` | dormant (native assets INT64_MAX on mainnet) |
| output type | `OUT_SCRIPT_HASH = 0x30` | `include/sost/script.h:29` (legacy P2SH/multisig) | dead code, compiled into `sost-core` |

* **TX_TYPE_ASSET_GENESIS vs OUT_NODE_PROTOCOL** sit in separate namespaces: `Transaction.tx_type` (u8 after version) vs `TxOutput.type` (u8 after amount). This is not a parse ambiguity. `transaction.h:95-96` documents the separation, but it is a readability and explorer hazard. The same pattern holds at 0x20: `TX_TYPE_NODE_BIND` vs reserved `OUT_BURN`.
* **OUT_SCRIPT_HASH vs OUT_NODE_PROTOCOL is a real collision in the same output namespace.** If the legacy script/P2SH path were ever wired (the "simple" route to multisig), a P2SH output would be byte-identical in type to a node-protocol carrier:
  * the carrier is unspendable, so funds sent there would be lost or ambiguous;
  * any range or type dispatch would split consensus.
* This is why `docs/bridge/NATIVE_MULTISIG_FUTURE.md` says "never 0x30", and why the design moves custody to 0x50.

**Proposed fence** (part of the #40,000 consensus release, or earlier as NODE_HARDENING):

1. **Delete the legacy code**: `script.h`, `script.cpp` and the multisig/P2SH-script parts of `psbt.cpp`, plus their two tests. Do this before any multisig implementation lands, so `OUT_SCRIPT_HASH` cannot be imported by accident.
2. **Add a single type registry** (`include/sost/type_registry.h`) listing every tx type and every output type with its status (ACTIVE / RESERVED_INACTIVE / DORMANT) and its activation constant. It carries `static_assert` uniqueness within each namespace and the reserved ranges:
   * output 0x40–0x4F native assets
   * output 0x50–0x5F custody/multisig
   * tx type 0x30–0x3F native assets
   * OUT_BURN 0x20 RESERVED/INACTIVE (native SOST never burned)
3. **Add a ctest `type-registry`** that enumerates the registry and asserts:
   * R11, S9, R2 and the block allow-list accept exactly the ACTIVE set at representative heights;
   * 0x50 is rejected before `MULTISIG_HEIGHT`.
4. **Allocation rule:** new allocations must not reuse a numeric value that already exists in the *other* namespace (for example, no new tx type 0x50). Multisig uses tx **version 2**, not a tx type, so it already complies.
5. **Fix the stale comments** that say "mainnet 30000" for native assets: `transaction.h:93`, `params.h:708-710`, `utxo_set.cpp:340`.

### A.3 Test plan (required before the design can become an implementation candidate)

* **Unit**
  * Policy canonicalisation: unsorted keys, duplicate keys, uncompressed or off-curve keys, M = 0, M > N and N > 15 are each rejected.
  * MSH vectors.
  * The bech32m vectors from the design, including wrong HRP per network, mixed case and length ≠ 21.
  * K ≠ M; key indexes non-increasing or ≥ N; high-S; r or s zero; a signature checked against the wrong index.
  * auth_kind does not match the spent type; unknown auth_kind.
* **Sighash v2**
  * CHAIN_ID literals pinned byte-for-byte.
  * Cross-network replay is rejected for v2 and unchanged for v1.
  * The `hashOutputs` encoding decision (§A.1 #14) is pinned.
* **Sigchecks**
  * A block at exactly 12,000 is valid; one at 12,001 is invalid.
  * Counting happens before any verification (timing test on an invalid-at-the-end block).
  * Per-tx policy limit of 1,500.
* **Activation boundary**: 0x50 outputs and v2 txs are rejected at `MULTISIG_HEIGHT − 1` and accepted at `MULTISIG_HEIGHT` (block-level, not only tx-level).
* **Fence tests**
  * A NODE_BIND/HEARTBEAT with outer version ≠ 1 is rejected from the fork height.
  * v2 with a non-STANDARD tx_type is rejected.
  * The `type-registry` ctest passes.
* **Historical replay**: a full mainnet replay 0 → tip is byte-identical (UTXO hash + tip), automated in ctest from a pinned chain snapshot.
* **Reorg**: spend a multisig UTXO, disconnect, reconnect; mempool re-acceptance of a v2 tx across a reorg.
* **Fuzz**: the v2 input parser, the policy parser and the bech32m decoder (libFuzzer/ASan), at least 10⁷ execs each with no crash.
* **E2E (devnet, then testnet soak of at least 2,016 blocks)**
  * 3-of-5 vault round trip through `createmultisig` → `buildtx` → 3× offline `signtx` → `combinetx` → `verifytx` → `finalizetx` → `sendrawtransaction`.
  * Rotation to a new policy.
  * The 7-step bridge migration rehearsal on Sepolia.
* **Mixed-version network**: old nodes (v16.x) reject v2 txs after the height, so the activation is a hard fork. The miner/operator notice and the binary-adoption threshold must be measured.

### A.4 Open design questions and defects (blocking DESIGN_READY)

1. **Payload cap.** The design says 512, but the effective limit is 255 (§A.1 #14). The v2 `hashOutputs` length encoding is undecided.
2. **Version-2 fence.** Node txs do not check the outer version today (§A.1 #3). The design must specify which tx types may use v2.
3. **Shared genesis.** All networks share one genesis, and the CLI hardcodes it. CHAIN_ID fixes v2 only. The design should state explicitly that v1 cross-network replay remains, as accepted residual risk.
4. **Sigcheck table completeness.** It must cover HTLC claim/refund (they carry a witness output and a signature), asset txs, and every input kind. The 12,000 cap needs a recorded proof against the historical maximum.
5. **Witness-excluding txid** (design §11 q1). It is recommended as not in #40,000. Txid malleability before confirmation therefore remains, and the bridge observers must key on (txid, vout) only after the 30 confirmations.
6. **HTLC with an MSH claimant, and assets held by multisig.** Both are excluded in v1. They must be listed as explicit rejections with tests, not as silent gaps.
7. **Single 3-of-5 output vs several outputs** (design §11 q6). This is operational, but it affects the sigcheck and tx-size budget.
8. **Repo base.** The design says to build from the v30000-final lineage (`3acd952b` + `59a4e666`), never from `main`. The release branch audited here (`release/v40000-prep`) must be confirmed as that lineage before implementation starts.

Not blocking: Schnorr/MuSig (later, if ever); a timelocked recovery path (out of scope). Note that `docs/PSBT_MULTISIG_ASSESSMENT.md` (March) is superseded. Its MuSig2 → ECDSA statement is wrong: MuSig2 yields Schnorr signatures, which the ECDSA verifier cannot accept.

**NATIVE_MULTISIG_DESIGN_READY = NO.** The design becomes ready after a revision (r4) that closes items 1–4 and 6, and records decisions for 5, 7 and 8, with the vectors committed as test files.

---

## B. Native assets

**Code facts:**
* Tx types 0x30–0x33 (GENESIS/ISSUE/TRANSFER/BURN); outputs 0x40–0x43 (TRANSFER/ISSUE_AUTH/BURN/GENESIS_DEF).
* `NATIVE_ASSETS_ACTIVATION_HEIGHT`: devnet 42, testnet 30,000, **mainnet INT64_MAX** (`params.h:718-727`, emergency deferral 2026-10-08).
* Wired into validation: R2, R11 and R14, the S14 admin gate (`tx_validation.cpp:156-171`), S15 non-asset isolation, `apply_asset_state_for_block` before ConnectBlock, and reorg undo.
* RPCs `getasset` / `listassets` / `getassetbalance`; CLI `createasset` / `issueasset` / `transferasset` / `burnasset`.
* There is no separate DB: the asset index is rebuilt from chain replay.
* On mainnet: 0 asset txs and 0 asset outputs (chain scan to 30,428).
* OUT_BURN 0x20 for native SOST is RESERVED/INACTIVE (R11 on create, S12 on spend). `OUT_ASSET_BURN` 0x42 applies only to separately issued assets.

| Gate | Exists? | Evidence (ctest target: case) | Gap |
|---|---|---|---|
| Supply accounting | PARTIAL | `native-assets-consensus`: "FIXED mint<cap reject", "issue over cap reject", "genesis CAPPED mint<cap +auth OK"; `emergency-v30000`: "supply overflow (issue beyond max_supply) REJECTED"; 128-bit sums (`native_assets_validation.h:91-94`) | No Σ(asset UTXOs) = issued − burned invariant test. **Bug 4a:** a multi-asset BURN attributes every burn to the last asset_id seen (`native_assets_index.h:85-98`) |
| UTXO accounting / conservation | YES, with holes | `native-assets-consensus`: "transfer inflate reject", "transfer mint-from-air reject", "burn miscount reject", …; `emergency-v30000`: S15 cases | **Bug 4b:** ISSUE/GENESIS can consume *another* asset's units or its ISSUE_AUTH without a burn record. **Bug 4c:** `validate_asset_tx` skips inputs it cannot find (`if (!u) continue;`) and runs on the pre-block UTXO set, so chained in-block asset spends vanish units |
| Issue authority | YES | FIXED vs CAPPED_REISSUABLE; ISSUE must spend the live ISSUE_AUTH; `admin-gate` cases 1–5 | No sealing test. The "fail-closed: no authority set" case passes only because the baked admin PKH ≠ the test key |
| Replay | IMPLICIT | UTXO model; sighash commits tx_type, spent type and genesis; GENESIS_DUP "duplicate genesis reject" | No asset-specific replay test. Genesis is shared across networks (see A.4 #3) |
| Malformed corpus | PARTIAL | `native-assets-serial`: 11 parse rejects (bad version, trailing bytes, decimals > 18, …) | No corpus files; no end-to-end R14 malformed-payload test through `ValidateTransactionConsensus` |
| Reorg | PARTIAL | `native-assets-index`: "undo burn/issue/genesis" | No live-node asset reorg test (`docs/v30000/TEST_MATRIX.md` admits this) |
| Property / fuzz | **MISSING** | — (the only fuzz target is JSON-RPC) | parse_asset_def / validate_asset_tx / index apply-undo fuzz + property tests |
| Historical compatibility | YES (by deferral) | `emergency-v30000`: "mainnet NATIVE_ASSETS_ACTIVATION_HEIGHT == INT64_MAX", "mainnet assets inactive at 30000 / 30186 / 40000" | `tests/run_v162_historical_replay.sh` is manual, not in ctest |
| Activation boundary | YES (devnet/testnet only) | `native-assets-activation`: "BOUNDARY: inert at A-1, active at A", "PRE: ASSET_GENESIS rejected (R2_BAD_TX_TYPE)" | Tx-level only, not block-level; not built for mainnet params; consensus test hard-codes height 41 |
| Mempool / template validation | **MISSING** | AcceptToMempool runs only R/S + S14; no asset validator hook (unlike `SetNodeTxValidator`) | An asset-invalid tx can enter a template and cause a rejected block |
| Asset Passport compatibility | DOC only | `AssetDef.manifest_hash` documented as the Passport manifest SHA-256; Passport anchors via capsule `doc_ref` | No test linking the two; `docs/ASSET_REGISTRY_V2.md` says the native layer is "not built" (stale) |
| Legal / public gating | YES (docs + web) | `ASSET_REGISTRY_LEGAL_OVERVIEW.md` ("does not determine legal classification"); web flags `DEX_PUBLIC_ENABLED` / `TOKENIZATION_PUBLIC_ENABLED` / `MAINNET_VALIDATED` all false | `native_assets_public_enabled` is referenced in `params.h:710` but does not exist in code. S14 needs an external audit + regulatory review |

Also stale: `docs/v30000/TOKENIZATION_AND_DEX.md`, `UPGRADE_GUIDE.md` and `TEST_MATRIX.md` still say mainnet activates at 30,000. TEST_MATRIX claims an activation suite PASS against a mainnet build, which is impossible now.

**NATIVE_ASSETS_ACTIVATION_READY = NO.** Required before any activation height is set:
* fix bugs 4a–4c, with regression tests;
* mempool and template asset validation;
* fuzz and property suites;
* a live reorg E2E;
* automated full-chain replay in ctest;
* a block-level boundary test under mainnet params;
* an external audit;
* a legal/public gating decision.

**Recommendation:** do not activate at #40,000. Target **#50,000 or later**, behind the S14 lifting criteria.

## C. Economic research

See `docs/v40000/ECONOMICS_80_15_5.md` and `tools/research/sim_80_15_5.py`.

* **Current split, verified from code:** from #25,000, 50 % PoW miner / 50 % DTD (every block). The Historical Jackpot is funded only by the frozen historical reserve (66,474 SOST at 30,428; 3.64-year runway at 100 SOST / 288 blocks).
* **80/15/5:**
  * miner revenue per block rises from 3.93 to 6.28 SOST;
  * the top-3 share of all flows rises from 49.9 % to 77.9 %;
  * the small-participant share falls from 52.4 % to 25.7 %;
  * jackpot runway rises from 3.6 to 12.2 years.
* **ECONOMIC_80_15_5 = WATCH.** Not in #40,000 scope (RESEARCH_ONLY now; it would be a CONSENSUS_FORK later).

## D. Decentralization

See `docs/v40000/DECENTRALIZATION_GATES_40000.md`.

* Gates G1–G9 are defined with procedures and thresholds.
* The lab P2P gates pass. The D1/D2 peer store and ADDR gossip are already on the release branch.
* Not met:
  * independent seeds: 0
  * providers/regions: 1/1
  * active producers: 2
  * user recovery path without sostcore.com
  * 24 h independence test
* All of these are NODE_HARDENING or operational. None is a consensus fork.

## E. Full item classification

| Item | Class | In #40,000? |
|---|---|---|
| OUT_MULTISIG 0x50 + reserved 0x51–0x5F | CONSENSUS_FORK | candidate (design r4 first) |
| tx v2 per-input auth (single / multisig), exact-M, increasing indexes, LOW-S | CONSENSUS_FORK | candidate |
| Sighash v2 with frozen CHAIN_ID | CONSENSUS_FORK | candidate |
| MAX_BLOCK_SIGCHECKS 12,000 | CONSENSUS_FORK | candidate |
| Outer version == 1 for node/jackpot txs from the fork height (v2 fence) | CONSENSUS_FORK | candidate (small, required by multisig) |
| Type registry + uniqueness static_asserts + `type-registry` ctest | NODE_HARDENING | yes (pre-req) |
| Removal of legacy script.h/script.cpp/psbt multisig | NODE_HARDENING | yes (pre-req) |
| 1,500 sigchecks/tx mempool policy | NODE_HARDENING | with multisig |
| bech32m `sostms`/`tsostms`/`dsostms` encoder/decoder | WALLET_CLI | with multisig |
| `createmultisig` / `combinetx` / `verifytx` / `finalizetx`, `sost-psst-v1` | WALLET_CLI | with multisig |
| `buildtx` / `signtx` offline single-sig | WALLET_CLI | already implemented |
| Native assets activation (lift INT64_MAX / S14) | CONSENSUS_FORK | **no → #50,000+** |
| Native assets bugs 4a–4c (validator/index) | CONSENSUS_FORK (code is dormant on mainnet, so the fix is safe pre-activation) | fix now, activate later |
| Mempool asset validator hook | NODE_HARDENING | fix before any activation |
| 80/15/5 reward split | CONSENSUS_FORK (future) / RESEARCH_ONLY (now) | **no** |
| P2P orphan-parent fetch / GETB by hash; "empty DONE" penalty (`docs/bridge/CAPSULE_FAST_DEVNET.md`) | NODE_HARDENING | yes (not a fork) |
| Independent seeds, fallback IPs, signed releases, mirrors | NODE_HARDENING + operational | yes (not a fork) |
| wSOST, Bridge contracts, PoR, Gold Reserve V2, QuarantineVault, AtomicSwapHTLCv2 | ETHEREUM_EXTERNAL | independent of the height |
| Native Asset Passport, Asset Market UI, decentralization status page | WEB_UI | independent of the height |
| Governance/voting tooling | WALLET_CLI + WEB_UI | independent of the height |
| Stale docs (BOOTSTRAP_AUDIT, decentralization-status.json, TEST_MATRIX, ASSET_REGISTRY_V2, CLI_CAPSULE_OFFLINE_DESIGN, params/transaction comments) | WEB_UI / docs | fix now |

## F. Recommended scope and readiness

**Consensus scope for #40,000 (recommended, if anything forks at all):** native multisig only. That means:
* OUT_MULTISIG 0x50;
* tx v2 single|multisig auth;
* sighash v2 with CHAIN_ID;
* the 12,000 sigcheck cap;
* the version fence for node/jackpot txs.

This rests on the type-registry fence and the legacy-code removal. Nothing else forks.

**Non-consensus scope:**
* multisig CLI (bech32m, psst flow);
* type registry and legacy removal;
* the P2P orphan fetch fix;
* independent seeds and signed mirrors;
* native-asset bug fixes, mempool hook and fuzz suites (dormant code);
* the Ethereum package (wSOST, Bridge, PoR, Gold Reserve V2, QuarantineVault, HTLCv2);
* the web pages;
* stale-doc corrections.

**BLOCK_40000_READINESS = NOT_YET.** Blocking gates:
1. Multisig design r4 closing A.4 items 1–4 and 6, with vectors committed.
2. An implementation on the confirmed v30000-final lineage, passing the full A.3 test plan.
3. A testnet soak of at least 2,016 blocks across the activation height, with a mixed-version network.
4. Automated full-chain historical replay in ctest (byte-identical UTXO hash at tip).
5. The type registry and legacy script removal merged first.
6. A published miner/operator notice at least 4 weeks before the height. This is a hard fork, so old nodes split.
7. An external review of the multisig consensus diff.

**Schedule check.** There are about 66 days to #40,000. Gates 1–3 plus a 4-week notice leave about 4 weeks to implement and test. Recommendation:
* Set a **go/no-go cutoff at about #36,000**. If gates 1–5 are not green by then, move native multisig to **#50,000**.
* In that case #40,000 carries no consensus change, and only the non-consensus scope ships.
* Native assets and 80/15/5 belong at **#50,000 or later** in any case.

---

## G. Scope confirmation — 2026-10-13 (`release/v40000-prep` @ `11dc2fcc`)

This section is added; nothing above was rewritten. It re-checks §F against the
tree after the merges since `bc8a45d9`:
* `75f6790d` buildtx mempool awareness;
* `4934fd50` deep-fork P2P;
* `8b0c8bb9` full-verify early chain;
* `5efccd0f` sanitizers;
* `d05e0a12` EVM gas.

It also sweeps every activation constant for anything that activates silently at
or before #40,000.

### G.1 Verdict

| Proposed item | Verdict | Reason |
|---|---|---|
| **CONSENSUS at #40,000 = native multisig only** | **CONFIRMED as the upper bound; CHALLENGED as the expected outcome** | Nothing else in the tree is consensus-ready (§G.3), so "only multisig" is right. But "native multisig" is not one rule. It is five consensus changes that ship together: OUT_MULTISIG 0x50, tx v2 per-input auth, sighash v2 with CHAIN_ID, the 12,000-sigcheck cap, and the outer-version fence for node/jackpot txs (§E). A partial subset must not ship. The design is still NOT READY (§A.4, 8 defects). The 4-week hard-fork notice (about 4,032 blocks) puts the latest notice at about #35,968. A 2,016-block testnet soak must finish before that, so implementation would have to be complete by about #34,000. The realistic default is therefore **#40,000 = no consensus change**, with multisig moved to #50,000 unless the #36,000 go/no-go is green. The scope statement should read "native multisig only, **or nothing**". |
| **NOT #40,000: native assets activation** | **CONFIRMED** | Mainnet `NATIVE_ASSETS_ACTIVATION_HEIGHT = INT64_MAX` (`include/sost/params.h:723`). `RESTRICTED_DEV_MODE_END_HEIGHT = INT64_MAX` (`:748`). Bugs 4a–4c, the mempool hook, fuzz and live-reorg gates are still open (§B). The asset bug fixes touch dormant consensus code. Keep them out of the #40,000 binary and ship them with the asset release, so the #40,000 diff stays reviewable and replay-tested. |
| **NOT #40,000: 80/15/5 economics** | **CONFIRMED** | It is a reward-split hard fork, WATCH (§C, `ECONOMICS_80_15_5.md`). There is no code in the tree. |
| NONCONSENSUS: deep-fork P2P fix | CONFIRMED non-consensus, **on the block-acceptance path** | `fork_block_id_check` (`src/sost-node.cpp:6391-6426`, used at `:6561`) rejects fork/orphan bodies whose recomputed id ≠ claimed id. `process_block` applies the same derivation and rejection when the block is connected (`:7404-7465`: same version defaulting, same `build_full_header_bytes`, same `compute_block_id`), so no block valid under consensus is refused. Because it sits in front of fork storage, the reorg and historical-replay tests must cover it. Random orphan eviction and the "already have" sync accounting are P2P-only. |
| NONCONSENSUS: buildtx mempool awareness | CONFIRMED | CLI plus a read-only `getmempoolspends` RPC and `Mempool::SpentBy` (a const lookup). No policy or validity change. |
| NONCONSENSUS: offline signing | CONFIRMED | `buildtx`/`signtx` in `bc8a45d9`; CLI only. |
| NONCONSENSUS: cASERT RPC metadata fix | CONFIRMED non-consensus, **NOT on the release branch** | `9039c16d` (`include/sost/casert_meta_window.h`) is reachable only from `devnet/capsule-fast-300`. It changes the window used by `build_casert_meta` (getinfo/getblocktemplate/getblock) for heights < `CASERT_V6PP_HEIGHT` = 5175 only. Validation always uses the full chain, and at the mainnet tip it returns the old window. It must be cherry-picked if it is in the package. |
| NONCONSENSUS: Stage 2 tooling, EVM deployment tooling | CONFIRMED | Ethereum-side and scripts. `d05e0a12` changes no SOST source. |
| NONCONSENSUS: verification tooling | CONFIRMED | `8b0c8bb9` (full-verify early chain) is explained and gated; no validity change. |
| NONCONSENSUS: decentralization improvements | CONFIRMED | P1–P8 in `DECENTRALIZATION_ACTION_PLAN_40000.md` are P2P/CLI/docs only. VERS gains optional trailing bytes; old peers already ignore the extra capability byte. |
| **Missing from the proposed nonconsensus list** | ADD | The type registry with uniqueness `static_assert`s and the `type-registry` ctest; removal of the legacy `script.h`/`script.cpp`/psbt multisig (the 0x30 collision, §A.2); automated full-chain historical replay in ctest. These are prerequisites even if multisig slips. |

### G.2 Consensus-adjacent changes since `bc8a45d9` (reviewed)

The diff `bc8a45d9..11dc2fcc` over `src/` and `include/` changed 8 files
(+599/−8):
* `src/beacon.cpp`, `src/mempool.cpp`, `src/psbt.cpp`, `src/sost-cli.cpp`,
  `src/sost-node.cpp`, `src/utxo_reservations.cpp`;
* `include/sost/mempool.h`, `include/sost/utxo_reservations.h`.

Of these:

* `src/beacon.cpp:138` changes the `b64_decode` accumulator from `int` to
  `uint32_t`. Only the low bits are emitted, so the output bytes are identical
  for every input where the old code was defined. The signed overflow was UB.
  Beacon P2P is active since V13 (`params.h:976`), so this is
  **behaviour-preserving, not consensus-neutral by construction**. Keep it inside
  the historical-replay test.
* `src/psbt.cpp` touches only the base64 helpers. It is not reachable from node
  validation (§A.1 #13).
* `fork_block_id_check` is discussed above.
* Every other change is CLI, RPC or mempool lookup.

### G.3 Activation-height sweep (mainnet branch, `SOST_TESTNET_FORKS=OFF`, no `SOST_DEVNET_FORKS`)

Every height-gated constant in `include/` and `src/` was enumerated.

**Already active, ≤ #30,000:**
* `V14_HEIGHT` 15,000;
* `V14_5_HEIGHT` 16,000;
* `V14_7_HEIGHT` 17,000;
* `V15_HEIGHT` 25,000 and its dependents (`RESERVE_FREEZE`, `POPC_V15`,
  `POPC_SINGLE_MODEL`, `HIST_JACKPOT_ACTIVATION`);
* `DTD_POPC_ELIGIBILITY_HEIGHT` 30,000, which is inert because
  `DTD_POPC_GATE_CONSENSUS_ACTIVE = false` (`params.h:1226`);
* `HIST_JACKPOT_V2_HEIGHT` 30,000 (`:1415`);
* `NODE_BIND_V2_HEIGHT` = 30,000 (`:1426`);
* `DTD_V16_ELIGIBILITY_HEIGHT` = 30,000 (`:1475`).

**Deferred (INT64_MAX or equivalent), will not activate:**
* `SACS_V2_ACTIVATION_HEIGHT` (`params.h:702`);
* `NATIVE_ASSETS_ACTIVATION_HEIGHT` (`:723`);
* `RESTRICTED_DEV_MODE_END_HEIGHT` (`:748`);
* `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT` (`:968`);
* `POPC_GOLD_BOOST_HEIGHT` (`:1294`);
* `GV_G4_ACTIVATION_HEIGHT` (`gv_g4.h:57`);
* `GV_G5_ACTIVATION_HEIGHT` (`gv_g5.h:50`);
* `GV_SLICE1_ACTIVATION_HEIGHT` (`gold_vault_slice1.h:86`);
* `DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE = false` (`params.h:1529`);
* `CASERT_BURST_HEIGHT` = 999,999 (`:455`, not active).

**Fixed heights above 30,000:**
* `GV_G5_AUTO_DISCONNECT_HEIGHT` = 100,000 (`gv_g5.h:37`). It only turns G5
  *off*, and G5 is INT64_MAX on mainnet.
* `263106` in `gold_vault_governance.h:133,156` (epoch-2 threshold, 90 → 90,
  numerically unchanged).
* `BLOCKS_PER_EPOCH` = 131,553 (`params.h:51`).

**Legacy `MULTISIG_ACTIVATION_HEIGHT = 2000` (`include/sost/script.h:38`).** It is
past, but no validator references it: the legacy engine is reachable only from
`tests/test_multisig.cpp` and `tests/test_psbt.cpp` (§A.1 #13). This is one more
reason to delete that code before a real multisig height constant exists, so two
constants with the same meaning cannot coexist.

**There are no timestamp-based activations.** The only epoch timestamps are
`GENESIS_TIME` and `GENESIS_TIMESTAMP`.

**Finding: nothing consensus-relevant activates silently between the current tip
and #40,000.** The only height-dependent behaviours in that range are periodic
rules already active: jackpot cadence 288, NODE_EPOCH 288, the DTD windows and
the cASERT windows.

**Comment drift (not a consensus issue).** `params.h:750-753` says "the shipped
default is the all-zero fail-closed placeholder", but `SOST_ADMIN_PKH_BYTES`
(`:756`) bakes a real 20-byte PKH. It is dormant behind
`NATIVE_ASSETS_ACTIVATION_HEIGHT = INT64_MAX`. Correct the comment together with
the S14 work, never in the #40,000 consensus diff.

### G.4 Confirmed #40,000 scope

* **CONSENSUS:** native multisig as the complete five-rule bundle of §E,
  **if and only if** the §F gates 1–7 are green at the **#36,000** go/no-go.
  Otherwise **none**, and multisig moves to #50,000.
* **NOT #40,000:**
  * native assets activation, plus its dormant-code bug fixes in the shipped
    binary;
  * 80/15/5;
  * any change to existing-height rules.
* **NONCONSENSUS package:**
  * deep-fork P2P fix (merged);
  * buildtx mempool awareness (merged);
  * offline signing (merged);
  * cASERT RPC metadata fix (**cherry-pick needed**);
  * Stage 2 and EVM deployment tooling;
  * verification tooling;
  * decentralization P1–P8 (`DECENTRALIZATION_ACTION_PLAN_40000.md`; P1, P2 and P3
    are release blockers there);
  * the type registry, legacy-script removal and automated historical replay.
* **DECENTRALIZATION_GATES_MET = NO.** Independent seeds 0; providers 1;
  regions 1; producers 2. The release blockers that are in core-dev control are
  listed in the action plan §3.
