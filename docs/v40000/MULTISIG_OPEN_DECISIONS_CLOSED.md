# Native multisig — open decisions, closed (design revision r4)

Status: **DESIGN ONLY. No consensus code is changed. Implementation is NOT authorized by this
document.** Normative result: `docs/v40000/NATIVE_MULTISIG_SPEC_40000.md` (the "spec").
Author: Neob. Date: 2026-10-13. Baseline `release/v40000-prep` @ `11dc2fcc`.

Sources reviewed: `docs/v40000/V40000_CONSENSUS_SCOPE.md` §A (eight open items in §A.4),
`docs/design/NATIVE_MULTISIG_40000.md` r3 (`origin/design/native-multisig-40000` @ `13b02df4`),
`docs/bridge/NATIVE_MULTISIG_FUTURE.md`, `docs/PSBT_MULTISIG_ASSESSMENT.md`, and the source files
cited per item.

## 1. Summary

| ID | Item | Origin | Decision (one line) | State |
|---|---|---|---|---|
| D1 | Payload cap (255 signed vs 512 design text) | §A.4 #1 | v1 keeps 255 (unchangeable); v2 `hashOutputs` uses the wire u16 length, so v2 signed payloads reach R13's 512; `OUT_MULTISIG` payload ≤ 255 (capsule envelope) | CLOSED |
| D2 | Outer version marker / v2 fence | §A.4 #2 | v2 only for STANDARD (R25); node txs outer version == 1 from MH (R30); layout dispatch on `version == 2`, height-independent | CLOSED |
| D3 | CHAIN_ID and shared genesis | §A.4 #3 | frozen literals in v2 sighash only; v1 cross-network replay is an accepted, documented residual risk | CLOSED |
| D4 | Sigcheck cap and counting table | §A.4 #4 | 12,000/block over all txs, structural, before verification; complete table; 1,500/tx policy; worst case ≤ 9,933 under 1 MB | CLOSED |
| D5 | HTLC and assets vs multisig | §A.4 #6 | explicit rejections: `auth_kind` table (S16), v2 STANDARD-only (R25); wallet refusals for MSH in other lock fields | CLOSED |
| D6 | txid includes signatures (malleability) | §A.4 #5 | keep `txid = SHA256d(full tx)`; third-party malleability closed; signer/combiner malleability accepted with bridge rules | CLOSED |
| D7 | Single vs split vault outputs | §A.4 #7 | one 3-of-5 policy per vault, one UTXO per deposit, change to same MSH, consolidate > 32 UTXOs; no consensus rule | CLOSED |
| D8 | v30000-final lineage | §A.4 #8 | verified: `3acd952b` and `59a4e666` are ancestors of `11dc2fcc`; tx consensus files byte-identical to `59a4e666` | CLOSED |
| D9 | 1 MB / 65,536 not enforced on the live block path | **new** | enforce both on `process_block` from MH, before signatures | CLOSED |
| D10 | Consensus scope of the capsule on `OUT_MULTISIG` | **new** (r3 conflict) | consensus checks a byte-level capsule v1 envelope only; capsule type/body stay policy | CLOSED |
| D11 | Consensus tx size assumes 133-byte inputs | **new** | `tx_size` = exact serialization length for R9/S8/policy (identical for v1) | CLOSED |
| D12 | Sighash lacks a spent-output commitment | **new** | v2 sighash adds `hashSpentOutputs` over every spent output | CLOSED |
| D13 | 0x30 collision + type registry + legacy fence | §A.2 / required | registry header + `type-registry` ctest added now (no runtime change); legacy deletion is the first commit of the implementation | CLOSED |

**MULTISIG_OPEN_DECISIONS: 0/13 open.** Not counted as decisions: the MuSig2 documentation error
(corrected in `docs/PSBT_MULTISIG_ASSESSMENT.md`, §4 below) and the testnet activation height
(a testnet-only parameter, `INT64_MAX` until the testnet soak release sets it).

---

## 2. Items

### D1 — Payload cap

* **Issue.** `ComputeHashOutputs` writes `payload_len` as one byte and returns an all-zero hash if
  any payload exceeds 255 bytes (`src/tx_signer.cpp:133-141`); `SignTransactionInput` and
  `VerifyTransactionInput` both refuse such transactions (`ValidateOutputsForSighash`,
  `src/tx_signer.cpp:504-512`). R13 allows 512 (`src/tx_validation.cpp:326-331`) and the r3 design
  text said "payload ≤ 512". Capsule v1 itself is capped at 255 (`include/sost/capsule.h:28`,
  `src/capsule.cpp:78`).
* **Security impact.** Low today (a > 255-byte signed payload is simply unspendable-to-sign, i.e.
  rejected). Risk is a specification error: a v2 that copied the one-byte encoding would inherit a
  poison-hash path in consensus code.
* **Consensus impact.** v1: none possible (changing it would reinterpret history). v2: the
  `hashOutputs` encoding is a consensus choice.
* **Options.** (a) v2 keeps the one-byte length and the 255 cap; (b) v2 hashes the exact wire
  encoding (u16 length), cap = R13 512; (c) v2 lowers R13 to 255.
* **Decision.** (b). `hashOutputs_v2 = SHA256d(‖ wire-serialized outputs)` (spec §5.2). v1 is
  documented as capped at 255 for signed txs. `OUT_MULTISIG` payloads are limited to 255 by the
  capsule envelope rule (D10). Relay policy is unchanged (`MAX_PAYLOAD_STANDARD` 512, capsule
  policy ≤ 255).
* **Rationale.** No poison value, no special case, one encoding shared by the wire and the
  sighash; does not loosen anything relayed today (capsule policy still caps at 255).
* **Tests.** `multisig-sighash-v2`: `v2_hashoutputs_u16_len_256_payload`,
  `v2_hashoutputs_512_payload_signs_and_verifies`, `v2_hashoutputs_matches_wire_bytes`;
  `v1_sighash_255_cap_unchanged` (a v1 tx with a 256-byte payload is still S6-rejected);
  `multisig-validation`: `ms_output_payload_256_rejected_R29`.

### D2 — Outer version marker

* **Issue.** R1 (`version == 1`) runs only inside `ValidateTransactionConsensus`
  (`src/tx_validation.cpp:128-132`). NODE_BIND/HEARTBEAT skip it (`src/sost-node.cpp:6942-6944`,
  `node_block_tx`), and their shape check `extract_payload` (`src/node_participation.cpp:91-103`)
  never reads the outer version; `wrap_protocol_tx` writes 1 (`:70`). Coinbase pins 1 (CB check),
  the jackpot pins 1 (`include/sost/jackpot.h:339`). The parser accepts any u32 version.
* **Security impact.** Today any relayer can change a node tx's outer version and obtain a new
  txid for the same payload (the Schnorr signatures do not cover it): third-party malleability of
  node txs. After v2 exists, an unfenced version byte would also leave ambiguity about which layout
  a node tx uses.
* **Consensus impact.** New rules R25 and R30 from MH; layout dispatch.
* **Options.** (a) fence from MH only; (b) fence retroactively (forbidden: changes rules at
  existing heights); (c) leave node txs unfenced.
* **Decision.** (a). From MH: `version ∈ {1,2}`; `version == 2` only with `tx_type == STANDARD`
  (R25); NODE_BIND/HEARTBEAT outer version must be 1 (R30, enforced inside the shared node-tx rule
  so block, mempool and `RevalidateNodeTxs` agree). Parse layout = `input_v2` iff `version == 2`,
  independent of height (spec §3.2).
* **Rationale.** Smallest fence that makes "version 2" mean exactly one thing. Height-independent
  dispatch is safe: all 30,596 mainnet txs to #30,428 are version 1 and every non-node path already
  rejects other versions; node txs have zero inputs, so their bytes parse identically under both
  layouts even if a version-2 node tx is mined before MH.
* **Tests.** `multisig-serial`: `ms_dispatch_version2_uses_v2_inputs`,
  `ms_dispatch_version3_uses_v1_inputs`, `ms_node_tx_v2_zero_inputs_parses_identically`;
  `multisig-activation`: `v2_htlc_claim_rejected_R25`, `v2_htlc_refund_rejected_R25`,
  `v2_asset_tx_rejected_R25`, `v2_coinbase_rejected_CB`, `node_bind_outer_v2_accepted_below_MH`,
  `node_bind_outer_v2_rejected_at_MH_R30`, `node_heartbeat_outer_v0_rejected_at_MH_R30`,
  `mempool_node_tx_outer_v2_rejected_at_MH`.

### D3 — CHAIN_ID and the shared genesis

* **Issue.** One genesis (`6517916b…fe699f37`) for every network; `sost-cli` hardcodes it for all
  `--network` values (`src/sost-cli.cpp:1681`); the node loads it from file (`src/sost-node.cpp:9879`).
  The v1 sighash has no network binding.
* **Security impact.** A v1 signature replays on another network wherever the same outpoint
  exists (identical premine/genesis outputs, or deliberately mirrored UTXOs). Funds risk is bounded
  to coins that exist on both chains with the same keys.
* **Consensus impact.** v2 sighash carries a 32-byte CHAIN_ID. v1 is not changed.
* **Options.** (a) CHAIN_ID in v2 only; (b) also change v1 (reinterprets valid signatures,
  invalidates pre-signed v1 txs: rejected); (c) new genesis per network (resets testnet/devnet,
  out of scope).
* **Decision.** (a). Literals frozen per network, selected by the compile-time profile, never
  computed (spec §2.2); re-derived independently and pinned in
  `tests/vectors/native_multisig_40000.json`. v1 replay is an accepted residual risk (spec §14.1);
  wallets build v2 by default after MH.
* **Rationale.** Binds every new signature to one network without touching history.
* **Tests.** `multisig-sighash-v2`: `chain_id_literals_pinned_mainnet_testnet_devnet`,
  `chain_ids_pairwise_distinct`, `v2_sig_mainnet_rejected_on_testnet`,
  `v2_sig_mainnet_rejected_on_devnet`, `v2_sig_testnet_rejected_on_mainnet`,
  `v2_sig_devnet_rejected_on_mainnet`, `v1_sighash_bytes_unchanged_vector`,
  `cli_network_dev_maps_to_devnet_chain_id`.

### D4 — Sigcheck limit and counting table

* **Issue.** No sigop/sigcheck limit exists (grep: none). The r3 table omitted HTLC/asset
  specifics, the block header signature and unknown types, and the 12,000 proof assumed a 1 MB
  block that the live path does not enforce (D9).
* **Security impact.** Without an explicit bound, verification cost per block depends only on
  bytes; multisig raises signature density ~1.33× (100.7 B/sig at 15-of-15 vs 133 B/sig for v1).
* **Consensus impact.** New block rule from MH.
* **Options.** (a) count by declared `K`; (b) count by policy `M`; (c) weight bytes instead of
  counting signatures.
* **Decision.** (a), table in spec §8: coinbase 0; jackpot 0; v1 STANDARD/HTLC/asset = inputs;
  v2 = Σ (single 1, multisig K); NODE_BIND 2 (every network); HEARTBEAT 1; unknown types =
  inputs; header SbPoW signature not counted. Block cap 12,000 at MH, computed right after
  deserialization and before any verification; policy 1,500 per tx (`P_TOO_MANY_SIGCHECKS` 411).
  Implementation must hash `hashPrevouts`/`hashSpentOutputs`/`hashOutputs_v2` once per tx.
* **Rationale.** `K` is exactly the number of verifications attempted, known from the bytes alone;
  for valid txs `K == M`. Worst case under 1,000,000 bytes is 9,933 (15-of-15), so the cap never
  binds honest or adversarial blocks while the byte limit holds, and it bounds work if that limit
  ever moves. It cannot affect history (evaluated only at h ≥ MH).
* **Tests.** `multisig-sigchecks`: `count_coinbase_0`, `count_jackpot_0`, `count_v1_inputs`,
  `count_htlc_claim_1`, `count_v2_single_1`, `count_v2_3of5_3`, `count_node_bind_2`,
  `count_heartbeat_1`, `block_exactly_12000_valid`, `block_12001_invalid_before_verification`
  (block whose last tx has a bad signature still reports `BLOCK_TOO_MANY_SIGCHECKS`, no ECDSA call
  counted), `cap_not_applied_below_MH`, `policy_tx_1501_rejected`, `template_respects_cap`;
  `historical-replay`: `max_historical_block_sigchecks_le_12000`.

### D5 — HTLC claimants and multisig-held assets

* **Issue.** HTLC `claim_pkh`/`refund_pkh` are single-key (`include/sost/transaction.h`, HTLC
  helpers; R21/R22 in `src/tx_validation.cpp`); asset outputs use a single-key pkh and are
  spendable only by asset txs (S15). r3 left these as silent gaps.
* **Security impact.** Funds locked to an MSH placed in a single-key field are unspendable; a
  silent gap invites wallet bugs that lose funds.
* **Consensus impact.** Explicit rejections: S16 table, R25, existing R20.
* **Options.** (a) explicit rejection now, separate design later; (b) add HTLC-to-MSH and
  multisig assets in #40,000 (larger surface, assets are not activating).
* **Decision.** (a). Spec §6: `OUT_MULTISIG` spendable only by v2 `auth_kind 0x01` (S16);
  `auth_kind 0x01` spends only `OUT_MULTISIG` (S16); HTLC and asset txs must be v1 (R25), so they
  never carry a multisig input; v2 spending `OUT_HTLC_LOCK` → R20. A multisig MAY fund an HTLC
  (its outputs follow normal S9) and an HTLC claim MAY pay to `OUT_MULTISIG`. Wallets refuse to put
  an MSH in any other lock field (spec §10.3).
* **Rationale.** Every combination has a defined outcome; no consensus rule depends on whether a
  20-byte value "looks like" an MSH (it cannot be told apart).
* **Tests.** `multisig-validation`: `v1_input_spending_0x50_rejected_S16`,
  `v2_single_spending_0x50_rejected_S16`, `v2_multisig_spending_transfer_rejected_S16`,
  `v2_multisig_spending_htlc_lock_rejected_S16`, `v2_single_spending_htlc_lock_rejected_R20`,
  `htlc_claim_v2_rejected_R25`, `htlc_claim_paying_to_0x50_ok`, `multisig_funding_htlc_lock_ok`,
  `asset_tx_spending_0x50_rejected_S16` (devnet build, assets active),
  `asset_output_with_msh_lock_unspendable`; `multisig-cli`: `wallet_refuses_msh_as_htlc_claimant`,
  `wallet_refuses_msh_in_bond_lock`, `wallet_refuses_sostms_before_MH`.

### D6 — txid includes signatures (malleability)

* **Issue.** `txid = SHA256d(serialization)` including signatures (`src/transaction.cpp`).
* **Security impact.** Third party: closed — LOW-S is consensus (`ValidateRSRange`,
  `src/tx_signer.cpp:247-283`), CompactSize is canonical, no trailing bytes, exact `K == M`,
  strictly increasing indexes, canonical sorted policy, and (from MH) the node-tx version fence.
  Remaining: a signer can re-sign (new nonce), and a combiner holding more than M signatures can
  pick another subset; both change the txid, never the effect. Affects only unconfirmed chains.
* **Consensus impact.** None if kept.
* **Options.** (a) keep; (b) witness-excluding txid (changes merkle, RPC, indexers, explorer,
  undo; second redesign).
* **Decision.** (a). Tooling picks the M lowest key indexes (deterministic). Bridge rules: release
  completion is recognized by a confirmed tx spending vault outpoints and carrying
  `WSOST-RELEASE:<burnId>`; never by an unconfirmed txid; no spend of unconfirmed vault outputs;
  observers key deposits on `(txid, vout)` only after the required confirmations.
* **Rationale.** Same malleability class as today's single-sig transactions; the cost of a
  witness txid is not justified for #40,000.
* **Tests.** `multisig-validation`: `third_party_cannot_reorder_sigs_R28`,
  `third_party_cannot_add_sig_R27`, `high_s_variant_rejected_S5`,
  `noncanonical_compactsize_rejected`, `combiner_subset_changes_txid_not_effect`;
  `multisig-psst`: `combinetx_selects_lowest_indexes`.

### D7 — Single vs split vault outputs

* **Issue.** r3 §11 q6.
* **Security impact.** Splitting across several key sets limits blast radius but multiplies
  ceremonies; splitting across UTXOs of one policy limits nothing.
* **Consensus impact.** None (any number of `OUT_MULTISIG` outputs/policies is valid).
* **Options.** (a) one policy, many UTXOs; (b) several policies; (c) one UTXO only.
* **Decision.** (a) for the pilot and until caps exceed pilot levels: one 3-of-5 MSH per vault;
  each deposit is its own UTXO; release change returns to the same MSH; consolidate when > 32
  UTXOs. Size budget: a 3-of-5 input is 400 B, so a 16,000-B standard tx holds ≤ 39 vault inputs
  (117 sigchecks). (b) remains available later without any consensus change.
* **Rationale.** Proof of reserves = Σ unspent UTXOs at one MSH; simple reconciliation
  (`docs/bridge/ARCHITECTURE.md` ledgers G/H).
* **Tests.** `multisig-e2e-devnet`: `vault_deposits_create_separate_utxos`,
  `release_change_returns_to_same_msh`, `consolidate_39_inputs_standard`,
  `consolidate_40_inputs_exceeds_standard_size`, `por_sum_equals_wsost_supply_integer`.

### D8 — v30000-final lineage

* **Issue.** r3 required building from the production lineage (`3acd952b` / `59a4e666`), never
  from a diverged `main`.
* **Security impact.** Building on the wrong base could drop or alter live consensus rules.
* **Consensus impact.** None directly.
* **Verification (2026-10-13).** `git merge-base --is-ancestor` succeeds for `3acd952b`
  (`v30000-final`), `59a4e666` (`v30000-final.1`) and `440defe5` against `11dc2fcc`; `origin/main`
  is also an ancestor (reconciled). `git diff 59a4e666 11dc2fcc` is empty for
  `src/tx_validation.cpp`, `src/tx_signer.cpp`, `src/transaction.cpp`, `include/sost/transaction.h`.
* **Decision.** Implementation branches from `release/v40000-prep`; CI asserts both ancestor
  checks on every implementation commit.
* **Tests.** `lineage-check` (script): `ancestor_3acd952b`, `ancestor_59a4e666`.

### D9 — Block byte and tx-count limits not enforced on the live path (new)

* **Issue.** `ValidateBlockStructure` enforces 1,000,000 bytes and 65,536 txs
  (`src/block_validation.cpp:38-55`), but the live accept path `process_block`
  (`src/sost-node.cpp:6429`) never calls it. The effective bound is the 4 MiB P2P message
  (`src/sost-node.cpp:715`) on hex-in-JSON, i.e. roughly 2 MB of tx bytes.
* **Security impact.** With ~2 MB of 15-of-15 inputs a block could reach ~19,800 signatures;
  without the sigcheck cap that is ~2× the intended verification bound.
* **Consensus impact.** New rule on the live path from MH (a tightening of future blocks only;
  the template already caps at 500 KiB, `src/sost-node.cpp:3006`).
* **Options.** (a) enforce from MH; (b) rely on the sigcheck cap only.
* **Decision.** (a), spec §7.1: `Σ tx_size ≤ 1,000,000`, `txcount ≤ 65,536`, then sigchecks, all
  before signatures.
* **Rationale.** Makes the documented consensus limit real and keeps the §8 proof valid.
* **Tests.** `multisig-activation`: `block_tx_bytes_1000000_valid_at_MH`,
  `block_tx_bytes_1000001_invalid_at_MH`, `block_65537_txs_invalid_at_MH`,
  `oversize_block_unchanged_below_MH`.

### D10 — Capsule on `OUT_MULTISIG`: consensus scope (new)

* **Issue.** r3 required `ValidateCapsuleHeader + ValidateCapsuleBody` at consensus for payloads on
  0x50. Those are policy functions: the header check enforces the policy capsule-type list
  (`src/capsule.cpp:95-99`) and the body check enforces per-type policy limits (e.g. open note
  ≤ 80 chars). Freezing them would make every future capsule type or limit change a hard fork, and
  any bug in body parsing a chain split.
* **Security impact.** Consensus-split risk and permanent ossification of policy.
* **Consensus impact.** Defines R29.
* **Options.** (a) full header+body (r3); (b) byte-level envelope only; (c) no payload on 0x50.
* **Decision.** (b), spec §7.3: empty, or `12 ≤ len ≤ 255`, `"SC"`, version `0x01`, `body_len ==
  len − 12`, reserved bytes zero, flag bits 6–7 clear; plus `amount ≥ 10,000` stocks. Type and body
  remain relay policy (`ValidateCapsulePolicy`, same as `OUT_TRANSFER`). Implemented as its own
  pure function.
* **Rationale.** Keeps 0x50 free of arbitrary data (stricter than `OUT_TRANSFER`), keeps bridge
  deposits able to carry `WSOST:0x…` on the vault output, and freezes only bytes that cannot need
  to change within capsule v1.
* **Tests.** `multisig-validation`: `ms_output_payload_empty_ok`, `ms_output_open_note_ok`,
  `ms_output_bad_magic_R29`, `ms_output_version2_R29`, `ms_output_body_len_mismatch_R29`,
  `ms_output_reserved_nonzero_R29`, `ms_output_flag_bit6_R29`, `ms_output_len_11_R29`,
  `ms_output_unknown_capsule_type_consensus_ok_policy_reject`, `ms_output_amount_9999_R29`,
  `ms_output_payload_before_MH_R11`.

### D11 — Consensus size assumes 133-byte inputs (new)

* **Issue.** `EstimateTxSerializedSize` (`src/tx_validation.cpp:103-121`, used by R9, S8 and policy fee)
  multiplies inputs by 133.
* **Security impact.** For v2 it would under-count multisig inputs (up to 1,510 B): R9 bypass and
  fees below 1 stock/byte.
* **Consensus impact.** R9/S8 definition for v2.
* **Options.** (a) exact serialized length; (b) a per-auth-kind estimator.
* **Decision.** (a): `tx_size` = canonical serialization length, identical to the current value for
  every v1 tx.
* **Tests.** `multisig-validation`: `tx_size_equals_serialized_len_v1_corpus`,
  `tx_size_15of15_input_1510`, `r9_counts_v2_exact_size`, `s8_fee_uses_exact_size`.

### D12 — Spent-output commitment in the sighash (new)

* **Issue.** The v1 sighash and the r3 v2 draft commit only the signed input's own amount and type.
  An offline signer cannot verify the other inputs' amounts, so the fee shown to it can be wrong
  while its signature stays valid.
* **Security impact.** Fee/amount deception of air-gapped multisig signers by a malicious
  coordinator (the Bitcoin pre-Taproot fee-lying class).
* **Consensus impact.** v2 sighash field.
* **Options.** (a) add `hashSpentOutputs` over every spent output; (b) amounts only; (c) none.
* **Decision.** (a), spec §5.2: `SHA256d(‖ ser(spent_output[j]))` with the wire output encoding
  (amount, type, lock, payload). Preimage fixed at 246 bytes.
* **Tests.** `multisig-sighash-v2`: `vector_V2_SH_1_preimage_bytes`, `vector_V2_SH_1_per_network`,
  `lying_spent_amount_other_input_invalidates_sig`, `lying_spent_type_invalidates_sig`,
  `lying_spent_payload_invalidates_sig`, `vector_V2_TX_1_signed_hex_and_txid`.

### D13 — 0x30 collision, type registry, legacy fence

* **Issue.** `OUT_SCRIPT_HASH = 0x30` (`include/sost/script.h:29`) equals the live
  `OUT_NODE_PROTOCOL = 0x30` (`include/sost/transaction.h:87`); `TX_TYPE_ASSET_GENESIS = 0x30`
  (`transaction.h:98`, dormant) shares the number in the other namespace. `script.cpp`/`psbt.cpp`
  are compiled into `sost-core` (`CMakeLists.txt:237-238`) and reached only by
  `tests/test_multisig.cpp` / `tests/test_psbt.cpp`.
* **Security impact.** Wiring the legacy path would make a P2SH output byte-identical in type to an
  unspendable node-protocol carrier (lost funds, consensus split on type dispatch).
* **Consensus impact.** None (fence only).
* **Options.** (a) delete now; (b) quarantine now and delete as the first implementation commit;
  (c) keep.
* **Decision.** (b). Added in r4, no runtime change: `include/sost/type_registry.h` (static_assert
  uniqueness, literal pins, reserved ranges, exact cross-namespace grandfather list
  `{00,01,02,10,11,20,30}`, `OUT_BURN` RESERVED_INACTIVE, nothing in tx `0x50–0x5F`) and ctest
  `type-registry` (`tests/test_type_registry.cpp`). Deletion list in spec §2.3, executed as the
  first commit of the implementation. Allocation rule: new codes must not reuse a value of the
  other namespace; multisig uses tx version 2, not a tx type.
* **Tests (implemented now).** `type-registry` (45 checks): compile-time asserts; R11 output-type
  and R2 tx-type allow-lists equal the registry set at mainnet heights 7349, 15999, 16000, 30000,
  39999, 40000, 50000; 0x50, 0x20, 0x30 rejected by R11 and tx version 2 by R1 at each; source
  scan finds no production reference to the legacy engine; `OUT_SCRIPT_HASH` is not a registry
  entry. After deletion: `legacy_files_absent`.

---

## 3. Consolidated required test list (implementation gate)

ctest targets to add with the implementation (every named case above), plus:
`multisig-policy` (`policy_1of1`, `2of3`, `3of5`, `5of5`, `15of15` accept; `m0`, `m_gt_n`,
`unsorted`, `duplicate`, `prefix_04`, `off_curve` → R26; `msh_vector_3of5`, `msh_vector_2of3`),
`multisig-bech32m` (every §10.2 vector; mixed case, wrong HRP, bad checksum, bad padding,
format byte ≠ 0x01, length ≠ 21, BIP-350 official checksum vectors),
`multisig-psst` (round trip, tampered `unsigned_hex`, mismatched policy in `combinetx`, wrong
`chain_id` refused by `signtx`), `multisig-reorg` (spend a 0x50 UTXO, disconnect, reconnect;
mempool eviction when tip + 1 < MH), fuzz targets for the v2 input parser, the policy parser and
the bech32m decoder (≥ 10⁷ execs each, ASan/UBSan, no crash), `historical-replay` (0 → tip
byte-identical UTXO hash), devnet E2E (3-of-5: `createmultisig → buildtx → 3 × signtx →
combinetx → verifytx → sendrawtransaction`, rotation, bridge migration rehearsal) and a testnet
soak of ≥ 2,016 blocks across MH with a mixed-version network.

## 4. Documentation corrections made in r4

* `docs/PSBT_MULTISIG_ASSESSMENT.md`: the statement "MuSig2 — multiple signers produce a single
  standard ECDSA signature" is wrong. MuSig2 produces a BIP-340 **Schnorr** signature for an
  aggregated key; SOST transaction inputs are verified with ECDSA only
  (`secp256k1_ecdsa_verify` in `VerifySighash`, `src/tx_signer.cpp`), so a MuSig2 signature cannot
  authorize a SOST input without a consensus change. Corrected in place.
* `docs/bridge/NATIVE_MULTISIG_FUTURE.md`: pointer to the spec; its "sost3-style" address
  requirement is replaced by bech32m `sostms` (spec §10).
* `docs/v40000/V40000_CONSENSUS_SCOPE.md` §A.4: pointer to this document; design numbers corrected
  (3-of-5 input 400 B → ≤ 39 inputs per standard tx, not ~25; the 497 B figure is the N = 15
  policy, not a 3-of-5 input).

## 5. Verdict

| Verdict | Value |
|---|---|
| MULTISIG_OPEN_DECISIONS | **0/13** |
| MULTISIG_DESIGN_READY | **YES** — every consensus rule (serialization, sighash, validation order, limits, activation, error codes) is specified without TBD in the spec, with independently generated and libsecp256k1-cross-checked vectors |
| IMPLEMENTATION_AUTHORIZED | **NO** (separate decision) |
| BLOCK_40000_READINESS | **NOT_YET** (implementation, full test plan, soak, replay automation, notice and external review are all outstanding; go/no-go at ~#36,000, fallback #50,000) |
