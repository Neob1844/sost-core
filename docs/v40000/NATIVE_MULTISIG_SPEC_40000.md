# Native M-of-N multisig — normative specification (#40,000 target)

Status: **NORMATIVE SPEC, revision r4 + implementation notes (§16, 2026-10-14). IMPLEMENTED on branch
`feat/v40k-ms` under the owner-frozen V17 decisions (activation constant `V17_HEIGHT`). Not merged, not deployed.**
Author: Neob. Date: 2026-10-13 (r4), 2026-10-14 (§16).

Supersedes, for every consensus rule it states: `docs/design/NATIVE_MULTISIG_40000.md` r3
(branch `design/native-multisig-40000` @ `13b02df4`) and the multisig parts of
`docs/bridge/NATIVE_MULTISIG_FUTURE.md`. Every open item from `docs/v40000/V40000_CONSENSUS_SCOPE.md`
§A.4 (and five more found while writing this revision) is closed in
`docs/v40000/MULTISIG_OPEN_DECISIONS_CLOSED.md`; the decision IDs D1–D13 used below refer to it.

Baseline: branch `release/v40000-prep` @ `11dc2fcc`. It contains the production consensus source
`3acd952b` (tag `v30000-final`) and the production node source `59a4e666` (tag `v30000-final.1`) as
ancestors. `src/tx_validation.cpp`, `src/tx_signer.cpp`, `src/transaction.cpp` and
`include/sost/transaction.h` are byte-identical to `59a4e666` (D8).

The words MUST, MUST NOT, REQUIRED and MAY are normative. "MH" means `MULTISIG_HEIGHT`. "h" is the
height of the block that contains the transaction (for the mempool: tip height + 1). All integers
are little-endian unless stated. `‖` is byte concatenation. `SHA256d(x) = SHA256(SHA256(x))`.

---

## 1. Scope

At heights `h ≥ MH`, exactly these consensus changes take effect together, and nothing else:

1. Output type `OUT_MULTISIG = 0x50` becomes creatable and spendable (§4, §7).
2. Transaction **version 2** becomes valid for `tx_type = TX_TYPE_STANDARD` only, with per-input
   `auth_kind` (single-sig or multisig) and a new sighash bound to a per-network CHAIN_ID (§3, §6).
3. NODE_BIND / NODE_HEARTBEAT transactions MUST carry outer `version == 1` (§7.6, D2).
4. Block limits enforced on the live block path: serialized transaction bytes ≤ 1,000,000,
   transaction count ≤ 65,536, sigchecks ≤ 12,000 (§8, D4, D9).

Unchanged at every height: version-1 serialization, the v1 sighash, every existing output and tx
type, coinbase and jackpot rules, the capsule format, HTLC rules, native-asset rules (dormant),
emission, PoW and difficulty. Below MH every rule is exactly as today, so historical replay is
byte-identical.

Out of scope (decided, not deferred): witness-excluding txid (D6), Schnorr/MuSig aggregation, a
timelocked recovery path, HTLC with a multisig claimant, multisig-held native assets (D5), any
native SOST burn (never).

---

## 2. Constants and type registry

### 2.1 Constants

| Name | Value | Class |
|---|---|---|
| `OUT_MULTISIG` | `0x50` | consensus |
| reserved custody range (outputs) | `0x51`–`0x5F` (no meaning; R11 rejects) | consensus (by absence) |
| `TX_VERSION_V2` | `2` | consensus |
| `AUTH_SINGLE` / `AUTH_MULTISIG` | `0x00` / `0x01` | consensus |
| `MAX_MULTISIG_N` | `15` | consensus |
| `MS_DOMAIN` | ASCII `SOST-MS1` (8 bytes) | consensus |
| `SIGHASH_V2_TAG` | ASCII `SOST-SIGHASH-V2` (15 bytes, no length prefix, no terminator) | consensus |
| `MAX_BLOCK_SIGCHECKS` | `12,000` | consensus, `h ≥ MH` |
| `MAX_BLOCK_TX_BYTES` | `1,000,000` (= existing `MAX_BLOCK_BYTES_CONSENSUS`) | consensus on the live path, `h ≥ MH` |
| `MAX_BLOCK_TXS` | `65,536` (= existing `MAX_BLOCK_TXS_CONSENSUS`) | consensus on the live path, `h ≥ MH` |
| `MULTISIG_DUST` | `10,000` stocks (= `DUST_THRESHOLD`) | consensus for `OUT_MULTISIG` outputs |
| `MAX_TX_SIGCHECKS_STANDARD` | `1,500` | relay/mining policy |
| `MULTISIG_HEIGHT` mainnet | `40000` (fallback `50000`, §11) | consensus |
| `MULTISIG_HEIGHT` testnet (`SOST_TESTNET_FORKS`) | `INT64_MAX` until the testnet soak release sets it | consensus (testnet only) |
| `MULTISIG_HEIGHT` devnet (`SOST_DEVNET_FORKS`) | `60` | consensus (devnet only) |

### 2.2 CHAIN_ID (frozen literals)

Stored as literal bytes in each network profile next to its fork heights; selected by the same
compile-time profile switch as every other fork height (`SOST_DEVNET_FORKS` → devnet,
`SOST_TESTNET_FORKS` → testnet, otherwise mainnet). Never computed at runtime, never read from a
file, flag or profile name.

| Network | CHAIN_ID (32 bytes, hex, byte order as written) |
|---|---|
| mainnet | `3ed1273b38ad28c61f591fed49dd8ec8f4684953f17ad371f5c3d741c1d1a2e4` |
| testnet | `301a71e109f7728f83c4fd96d114231c13fafd98a6cb1533caa1267fd385bec3` |
| devnet  | `9d651d4c8aada0dde1b7f17cf680c05b76fabff8711d232cb870cb55da007fbe` |

Provenance (informative, never recomputed by code): `SHA256("SOST-CHAIN-ID-V1|<mainnet|testnet|devnet>|6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37")`,
re-derived independently for r4. The CLI string `--network dev` selects the devnet literal.

### 2.3 Type registry and the 0x30 fence (D13)

Two separate one-byte namespaces exist: `Transaction.tx_type` and `TxOutput.type`.
`include/sost/type_registry.h` (added in r4; non-consensus, included by no production file) lists
every allocation and enforces with `static_assert`:

* uniqueness inside each namespace and literal pins of every constant in `transaction.h`;
* output `0x40–0x4F` = native assets (0x40–0x43 allocated, dormant); output `0x50–0x5F` = custody
  (nothing allocated until the implementation adds `0x50`); tx `0x30–0x3F` = native assets;
  no tx type in `0x50–0x5F`;
* `OUT_BURN = 0x20` is `RESERVED_INACTIVE`. **Native SOST is never burned**; R11 rejects creating
  0x20 and S12 rejects spending it, at every height, forever;
* cross-namespace overlaps are frozen to exactly `{0x00, 0x01, 0x02, 0x10, 0x11, 0x20, 0x30}`;
  any new allocation that reuses a value of the other namespace fails the build.

**The 0x30 collision.** `include/sost/script.h:29` defines `OUT_SCRIPT_HASH = 0x30`, identical to
the LIVE `OUT_NODE_PROTOCOL = 0x30` (`transaction.h:87`). Fence, in force now and REQUIRED to stay
in force until the legacy code is deleted:

1. `OUT_SCRIPT_HASH` is not a registry entry; the ctest `type-registry` asserts it.
2. No file under `src/`, `src/pow/` or `include/sost/` other than `src/script.cpp`,
   `src/psbt.cpp`, `include/sost/script.h`, `include/sost/psbt.h` may contain `sost/script.h`,
   `sost/psbt.h`, `OUT_SCRIPT_HASH`, `eval_script`, `eval_p2sh` or `MULTISIG_ACTIVATION_HEIGHT`
   (source scan in `type-registry`).
3. Deletion (REQUIRED before the multisig implementation is merged, as its first commit):
   remove `include/sost/script.h`, `src/script.cpp`, `include/sost/psbt.h`, `src/psbt.cpp`,
   `tests/test_multisig.cpp`, `tests/test_psbt.cpp`, the two `sost-core` source lines
   (`CMakeLists.txt:237-238`) and the `psbt` / `multisig` ctests. The fence test then switches to
   asserting the files do not exist. Native multisig uses no script engine, no `OP_CHECKMULTISIG`,
   no `sost3` prefix and no trial-and-error signature matching.

---

## 3. Serialization

### 3.1 Version 1 (unchanged, reference)

```
tx_v1   = version u32 (=1) ‖ tx_type u8 ‖ CompactSize(nin) ‖ input_v1 × nin ‖ CompactSize(nout) ‖ output × nout
input_v1 = prev_txid[32] ‖ prev_index u32 ‖ signature[64] ‖ pubkey[33]                    (133 bytes)
output  = amount i64 ‖ type u8 ‖ pubkey_hash[20] ‖ payload_len u16 ‖ payload[payload_len]  (31 + len bytes)
```

CompactSize is canonical (minimal) as today (`ReadCompactSize` rejects non-minimal forms).
`nin` is 1..256 except NODE_BIND/NODE_HEARTBEAT (0 allowed); `nout` is 1..256.
No trailing bytes.

### 3.2 Layout dispatch

The parser reads `version` first. **If `version == 2` the inputs use `input_v2`; for every other
value they use `input_v1`.** The dispatch does not depend on height. This is safe for history:
every mainnet transaction is version 1 (30,596 measured to #30,428); R1 has always rejected
`version ≠ 1` for standard/HTLC/asset txs, CB rejects it for coinbase, the jackpot pins version 1;
the only txs that could carry `version = 2` before MH are NODE_BIND/HEARTBEAT, which have zero
inputs, so their bytes parse identically under both layouts.

### 3.3 Version 2

```
tx_v2    = version u32 (=2) ‖ tx_type u8 ‖ CompactSize(nin) ‖ input_v2 × nin ‖ CompactSize(nout) ‖ output × nout
input_v2 = prev_txid[32] ‖ prev_index u32 ‖ auth_kind u8 ‖ auth
auth (auth_kind = 0x00, single-sig) = signature[64] ‖ pubkey[33]                                 (97 bytes)
auth (auth_kind = 0x01, multisig)   = M u8 ‖ N u8 ‖ PK[33] × N ‖ K u8 ‖ ( key_index u8 ‖ signature[64] ) × K
```

`policy = M ‖ N ‖ PK_0 ‖ … ‖ PK_{N-1}` is the byte string `M u8 ‖ N u8 ‖ 33·N bytes` exactly as it
appears inside `auth`.

Parse rules (failure = the bytes are not a transaction; it is rejected with the listed reason
string, carries no TxValCode, and a block containing it is invalid):

| ID | Rule |
|---|---|
| X1 `truncated` | any field extends past the end of the buffer |
| X2 `trailing_bytes` | bytes remain after the last output (`Deserialize`) |
| X3 `unknown_auth_kind` | `auth_kind ∉ {0x00, 0x01}` |
| X4 `policy_n_range` | `N = 0` or `N > 15` |
| X5 `sig_count_range` | `K > 15` |
| X6 (existing) | input count 0 for a non-node tx type, > 256; output count 0 or > 256; non-canonical CompactSize |

`K = 0` parses (it is the unsigned template, §12) and is rejected by R27. `M` is not checked at
parse time (R26).

Sizes: v2 single-sig input = 134 B. Multisig input = `36 + 1 + 2 + 33N + 1 + 65K`: 1-of-1 138 B,
2-of-3 269 B, 3-of-5 400 B, 5-of-5 530 B, 15-of-15 1,510 B (the maximum).

### 3.4 Output `OUT_MULTISIG (0x50)`

Same layout as every output: `amount i64 ‖ 0x50 ‖ MSH[20] ‖ payload_len u16 ‖ payload`.
UTXO representation unchanged (amount, type, 20-byte field, payload); reorg undo unchanged.

### 3.5 txid

`txid = SHA256d(serialization)` for v1 and v2 alike, signatures included (D6). Merkle root, block
id, RPC and storage are unchanged.

### 3.6 Exact size

`tx_size(tx) = length of the canonical serialization` (§3.1/§3.3). For v1 this equals the existing
`EstimateTxSerializedSize` byte for byte; for v2 the 133-byte-per-input estimate MUST NOT be used.
R9 (`tx_size ≤ 100,000`), S8 (`fee ≥ tx_size × 1`) and every policy size/fee rule use `tx_size` (D11).

---

## 4. Policy hash

```
MSH = RIPEMD160( SHA256( "SOST-MS1" ‖ policy ) )      (20 bytes)
```

Canonical policy (consensus, R26):
1. `1 ≤ M ≤ N ≤ 15` (the `N` range is already enforced at parse time by X4).
2. Every `PK_j` is 33 bytes, `PK_j[0] ∈ {0x02, 0x03}`, and `secp256k1_ec_pubkey_parse(PK_j, 33)`
   succeeds (the point is on the curve).
3. `PK_0 < PK_1 < … < PK_{N-1}` under unsigned lexicographic comparison of all 33 bytes
   (`memcmp`). Strict order makes duplicates impossible and gives one encoding per key set.

Domain separation: a single-key `pkh = RIPEMD160(SHA256(pubkey33))` hashes a 33-byte string; an MSH
hashes a string of at least 8 + 2 + 33 = 43 bytes beginning with `SOST-MS1`. Equal 20-byte values
require a SHA-256 or RIPEMD-160 collision.

Ceremony (operational, REQUIRED for the bridge vault): commit-then-reveal. Each signer publishes
`SHA256(pubkey)` first; keys are revealed and the policy assembled only after every commitment is
recorded. This removes the insider 2⁸⁰ collision-grinding attack on the 20-byte MSH.

---

## 5. Sighash

### 5.1 v1 (unchanged)

`SHA256d(version u32 ‖ tx_type ‖ hashPrevouts ‖ prev_txid[i] ‖ prev_index[i] u32 ‖ spent_amount[i] i64 ‖ spent_type[i] ‖ hashOutputs_v1 ‖ genesis_hash)`
(146-byte preimage, `src/tx_signer.cpp:154-181`). `hashOutputs_v1` encodes `payload_len` as ONE
byte and returns an all-zero hash when any payload exceeds 255 bytes; `VerifyTransactionInput`
rejects such txs, so **a signed v1 transaction can carry at most 255 payload bytes per output**,
whatever R13 says (D1). v1 is never reinterpreted.

### 5.2 v2

Used for every input of a version-2 transaction, single-sig and multisig. There are no sighash
flags; a signature always commits to the whole transaction.

```
hashPrevouts      = SHA256d( ‖_{j=0..nin-1} prev_txid[j] ‖ prev_index[j] u32 )                     (as v1)
hashSpentOutputs  = SHA256d( ‖_{j=0..nin-1} ser(spent_output[j]) )                               (NEW)
hashOutputs_v2    = SHA256d( ‖_{k=0..nout-1} ser(output[k]) )                                    (NEW encoding)
ser(o)            = amount i64 ‖ type u8 ‖ pubkey_hash[20] ‖ payload_len u16 ‖ payload           (= wire output encoding)
```

`spent_output[j]` is the UTXO entry referenced by input j, serialized from its stored amount, type,
20-byte field and payload.

Preimage for input i (exactly 246 bytes):

| Offset | Size | Field |
|---|---|---|
| 0 | 15 | `SIGHASH_V2_TAG` = `SOST-SIGHASH-V2` |
| 15 | 32 | `CHAIN_ID` of the validating network |
| 47 | 4 | `version` u32 (= 2) |
| 51 | 1 | `tx_type` (= 0x00) |
| 52 | 32 | `hashPrevouts` |
| 84 | 32 | `hashSpentOutputs` |
| 116 | 32 | `prev_txid[i]` |
| 148 | 4 | `prev_index[i]` u32 |
| 152 | 8 | `spent_amount[i]` i64 |
| 160 | 1 | `spent_type[i]` |
| 161 | 1 | `auth_kind[i]` |
| 162 | 20 | `auth_kind[i] == 0x01 ? MSH(policy_i) : 20 × 0x00` |
| 182 | 32 | `hashOutputs_v2` |
| 214 | 32 | `genesis_hash` |

`sighash_v2[i] = SHA256d(preimage)`. Every multisig signature of input i signs the same
`sighash_v2[i]`; key indexes, `K` and signatures are not committed (they are what is being produced).

Properties: commits to the network (CHAIN_ID), every outpoint, **every spent output** (amount,
type, lock, payload — so an offline signer's computed fee is exact: if any declared spent output
is false the signature is invalid on-chain), every output byte (payloads up to 512 bytes, D1), the
signed input's policy, and the genesis.

Implementation requirement (consensus-neutral): `hashPrevouts`, `hashSpentOutputs` and
`hashOutputs_v2` MUST be computed once per transaction and reused for all inputs (linear, not
quadratic, hashing).

---

## 6. Authorization of an input

`auth_kind(i)` is `0x00` for every input of a v1 transaction and the declared byte for v2.

| Spent UTXO type | v1 input | v2 `auth_kind 0x00` | v2 `auth_kind 0x01` |
|---|---|---|---|
| `OUT_MULTISIG` | **S16 reject** | **S16 reject** | multisig rules (§7.4) |
| `OUT_HTLC_LOCK` | HTLC rules (unchanged) | R20 reject (v2 is STANDARD only) | S16 reject |
| any other spendable type | v1 single-sig (unchanged) | v2 single-sig (§7.4) | S16 reject |

Consequences (D5): a multisig cannot be the claimant or refund key of an HTLC, cannot hold or
authorize native assets, cannot own a BOND/ESCROW lock, and cannot appear in any 20-byte lock
field other than an `OUT_MULTISIG` output. Consensus cannot tell an MSH from a pkh, so funds sent to
an MSH in any other lock field are unspendable (a second preimage would be needed); wallets MUST
refuse to build such outputs (§10.3).

---

## 7. Validation algorithm

### 7.1 Block path (live `process_block` and every library block validator)

For a block at height h, after every transaction has been deserialized (§3) and BEFORE merkle
verification, coinbase/jackpot/node-tx checks and any signature verification:

1. If `h ≥ MH`:
   a. `txcount ≤ 65,536` else reject `BLOCK_TOO_MANY_TXS`.
   b. `Σ tx_size(tx) ≤ 1,000,000` over all txs including the coinbase (header and JSON envelope
      not counted) else reject `BLOCK_TX_BYTES_EXCEEDED`.
   c. `Σ sigchecks(tx) ≤ 12,000` (§8) else reject `BLOCK_TOO_MANY_SIGCHECKS`.
2. Everything else in the existing order. For each non-coinbase tx: the tx-type allow-list
   (unchanged; v2 txs are tx_type STANDARD), the S13 reserve backstop, `ValidateTransactionConsensus`
   (§7.2–7.5) for non-jackpot, non-node txs; the node-tx path (§7.6) for NODE_BIND/HEARTBEAT.

### 7.2 Structural rules (`ValidateStructure`, no UTXO access), in order

| Step | Rule |
|---|---|
| R1 | `h < MH`: `version == 1`. `h ≥ MH`: `version ∈ {1, 2}`. Else `R1_BAD_VERSION`. |
| R25 | `h ≥ MH` and `version == 2`: `tx_type == TX_TYPE_STANDARD`, else `R25_V2_TX_TYPE`. |
| R2, S14, R3, R4 | unchanged |
| per output k | R5, R6, R7 unchanged; **R11**: at `h ≥ MH` `0x50` is active (all other types unchanged; `0x51–0x5F` stay inactive); **R29** for `type == 0x50`: `amount ≥ 10,000` and payload rule §7.3, else `R29_MULTISIG_OUTPUT`; R15–R18 unchanged; R13 (`payload ≤ 512`) unchanged; **R14**: a payload on `0x50` is allowed iff R29 passed (and never through the generic `OUT_TRANSFER` capsule branch) |
| per multisig input i (v2, `auth_kind 0x01`) | **R26** canonical policy (§4) else `R26_MS_POLICY`; **R27** `K == M` else `R27_MS_SIG_COUNT`; **R28** `key_index` strictly increasing and each `< N` else `R28_MS_KEY_INDEX` |
| R9 | `tx_size(tx) ≤ 100,000` (§3.6) |

### 7.3 Payload on `OUT_MULTISIG` (consensus envelope, D10)

The payload MUST be empty, or satisfy all of:

1. `12 ≤ len ≤ 255`;
2. `payload[0] = 0x53`, `payload[1] = 0x43` ("SC"), `payload[2] = 0x01` (capsule v1);
3. `payload[9] == len − 12` (body_len);
4. `payload[10] = payload[11] = 0x00` (reserved);
5. `payload[4] & 0xC0 == 0` (flag bits 6–7 clear).

`capsule_type` and the body are NOT consensus; they are checked by relay policy
(`ValidateCapsulePolicy`) exactly as on `OUT_TRANSFER`. The consensus check MUST be implemented as
its own pure function of the payload bytes, not by calling `ValidateCapsuleHeader` (which also
applies the policy `capsule_type` list and may evolve).

### 7.4 Input rules (`ValidateInputs`), for each input i in order

1. S1 (UTXO exists), S12 (not OUT_BURN), S15 (asset UTXO only by asset tx), S13 (reserve freeze),
   S11 (bond/escrow lock), the HTLC dispatch and R20, S10 (coinbase maturity): unchanged, and they
   apply to v2 inputs exactly as to v1 inputs.
2. Authorization table §6: on mismatch `S16_AUTH_KIND_MISMATCH`.
3. v1 input: existing `VerifyTransactionInput` with the v1 sighash (unchanged).
4. v2 `auth_kind 0x00`: identical checks to v1 (`RIPEMD160(SHA256(pubkey)) == utxo.pubkey_hash`
   else S2; signature not all-zero else S4; `r, s ∈ [1, n−1]` and `s ≤ n/2` else S5; pubkey parses
   and ECDSA verifies else S6), but against `sighash_v2[i]`.
5. v2 `auth_kind 0x01`:
   a. `MSH(policy) == utxo.pubkey_hash` else `S17_MSH_MISMATCH`;
   b. compute `sighash_v2[i]` once;
   c. for each `(key_index, signature)` in order: all-zero → S4; out of range or high-S → S5;
      `secp256k1_ecdsa_verify(signature, sighash_v2[i], PK[key_index])` false →
      `S18_MS_SIG_INVALID`. Exactly `M` verifications; no signature is tried against any other key.
6. Input sum and overflow checks unchanged.

### 7.5 Transaction-level rules after inputs

S7 (`Σin ≥ Σout`) unchanged; S8 uses `tx_size`; **S9**: at `h ≥ MH`, `0x50` is added to the
output-type allow-list for every tx type validated here (STANDARD v1/v2, HTLC_CLAIM, HTLC_REFUND,
and asset txs when assets are active). All other S9 behaviour unchanged. Coinbase output rules are
unchanged, so a coinbase can never create `0x50`.

### 7.6 Node transactions (D2)

At `h ≥ MH`, a NODE_BIND or NODE_HEARTBEAT whose outer `Transaction.version ≠ 1` is invalid
(`R30_NODE_TX_VERSION`, reason string `node_tx_bad_version`). Enforced inside the authoritative
node-tx rule (`connect_block_node_txs` / `extract_payload` with the height), so the block path,
the mempool validator (`SetNodeTxValidator`) and `RevalidateNodeTxs` share one predicate. The
NODE_BIND payload's own `version` byte (1/2, `node_participation.cpp:164-168`) is a different field
and is unchanged. Below MH node txs are accepted exactly as today.

### 7.7 Error codes

| Code | Value | Meaning |
|---|---|---|
| `R1_BAD_VERSION` | 101 (existing) | version not allowed at h |
| `R25_V2_TX_TYPE` | 123 | version 2 with tx_type ≠ STANDARD |
| `R26_MS_POLICY` | 124 | M = 0, M > N, bad key prefix, off-curve key, keys not strictly increasing |
| `R27_MS_SIG_COUNT` | 125 | K ≠ M |
| `R28_MS_KEY_INDEX` | 126 | key indexes not strictly increasing, or an index ≥ N |
| `R29_MULTISIG_OUTPUT` | 127 | 0x50 output below 10,000 stocks or payload fails §7.3 |
| `R30_NODE_TX_VERSION` | 128 | node tx outer version ≠ 1 at h ≥ MH |
| `S16_AUTH_KIND_MISMATCH` | 216 | auth kind does not match the spent UTXO type (§6) |
| `S17_MSH_MISMATCH` | 217 | MSH(policy) ≠ UTXO lock |
| `S18_MS_SIG_INVALID` | 218 | a multisig signature does not verify against PK[key_index] |
| S2, S4, S5, S6 | existing | as today, for single-sig v1/v2 and (S4/S5) per multisig signature |
| `P_TOO_MANY_SIGCHECKS` | 411 | policy: tx sigchecks > 1,500 |
| block reasons | strings | `BLOCK_TOO_MANY_TXS`, `BLOCK_TX_BYTES_EXCEEDED`, `BLOCK_TOO_MANY_SIGCHECKS` |
| parse reasons | strings | X1–X6 (§3.3) |

Codes are diagnostics. Validity is binary; the first failing rule in the order above decides the
reported code.

---

## 8. Sigcheck accounting (D4)

`sigchecks(tx)` is computed from the parsed transaction alone (no UTXO, no verification):

| Transaction | sigchecks |
|---|---|
| COINBASE (0x01) | 0 |
| JACKPOT (0x02) | 0 (keyless) |
| STANDARD v1, HTLC_CLAIM, HTLC_REFUND, ASSET_* (all version 1) | number of inputs |
| STANDARD v2 | Σ over inputs: `auth_kind 0x00` → 1; `auth_kind 0x01` → `K` (= M when valid) |
| NODE_BIND | 2 (mining-key + node-key Schnorr signature; counted as 2 on every network) |
| NODE_HEARTBEAT | 1 |
| any other tx_type | number of inputs (the block is invalid anyway) |

`block_sigchecks = Σ sigchecks(tx)` over every transaction including the coinbase. The block
header's SbPoW signature is not counted (exactly one per block, outside the budget).
Rule (`h ≥ MH`): `block_sigchecks ≤ 12,000` valid; `≥ 12,001` invalid, decided before any
signature is verified.

Worst case under the 1,000,000-byte limit (bytes per sigcheck, densest form):

| Form | Bytes | Sigchecks | Max per block |
|---|---|---|---|
| v1 input | 133 | 1 | 7,518 |
| v2 single-sig input | 134 | 1 | 7,462 |
| NODE_HEARTBEAT tx | 175 | 1 | 5,714 |
| NODE_BIND tx (v2 payload 202 B) | 240 | 2 | 8,333 |
| 15-of-15 input | 1,510 | 15 | 9,933 (in 66-input txs of 99,698 B) |

So no block within 1,000,000 bytes can exceed 12,000; the cap is an explicit backstop that
remains binding if the byte limit is ever raised or bypassed. It cannot invalidate any historical
block because it is evaluated only at `h ≥ MH`; the historical replay ctest additionally records
the maximum historical `block_sigchecks` and asserts it is ≤ 12,000.

---

## 9. Mempool, relay and mining policy

1. All consensus rules at `spend_height = tip + 1`. Before MH no v2 tx and no tx creating or
   spending `0x50` is accepted.
2. `sigchecks(tx) ≤ 1,500` else `P_TOO_MANY_SIGCHECKS`.
3. Existing standardness unchanged and measured with `tx_size`: ≤ 16,000 bytes, ≤ 128 inputs,
   ≤ 32 outputs, ≥ 1 stock/byte relay fee (or the dynamic minimum), dust ≥ 10,000 stocks, at most
   one capsule payload per tx. A payload on `0x50` counts as a capsule payload and MUST pass
   `ValidateCapsulePolicy` (identical to `OUT_TRANSFER`).
4. Block template: the builder MUST keep `Σ sigchecks ≤ 12,000`, `Σ tx_size ≤ 1,000,000` (the
   existing 500 KiB template cap is stricter and stays) and `txcount ≤ 65,536`.
5. Reorg across activation: whenever the new `tip + 1 < MH`, the mempool MUST evict every v2 tx
   and every tx that creates or spends `0x50` (re-run consensus on all entries at the new height,
   as `RevalidateNodeTxs` does for node txs).
6. No misbehaviour score is added for relaying a tx that fails validation (current behaviour,
   kept), so pre-fork relay of v2 txs to old nodes cannot cause bans.

---

## 10. Addresses

### 10.1 Encoding (bech32m, BIP-350 constant `0x2bc830a3`)

* HRP: `sostms` (mainnet), `tsostms` (testnet), `dsostms` (devnet), fixed by the build profile.
* Data: `0x01` (SOST multisig address format v1) ‖ `MSH` = 21 bytes; `convertbits(8→5, pad)` =
  34 groups; alphabet `qpzry9x8gf2tvdw0s3jn54khce6mua7l`. Not a SegWit program.
* Lengths: mainnet 47 characters, testnet/devnet 48.
* Decoders MUST reject: mixed or upper case, wrong HRP for the active network, bad checksum,
  characters outside the alphabet, missing `1`, total length > 90, decoded length ≠ 21, first byte
  ≠ 0x01, non-zero padding or ≥ 5 leftover bits.
* `sost1…` (single-key, `"sost1" ‖ hex(pkh)`, unchanged) and `sostms1…` are disjoint by
  construction; `sost3` is not revived.

### 10.2 Vectors (re-derived independently for r4)

Keys: private keys 1–5; sorted compressed public keys
`PK[0] 022f8bde…40efe4` (priv 5), `PK[1] 0279be66…f81798` (priv 1), `PK[2] 02c6047f…709ee5`
(priv 2), `PK[3] 02e493db…c4cd13` (priv 4), `PK[4] 02f9308a…e036f9` (priv 3). Full values in
`tests/vectors/native_multisig_40000.json`.

| Vector | Value |
|---|---|
| 3-of-5 MSH | `6b53fe0baa7da53368ba82cad9e6fe5c7c09f0f9` |
| mainnet | `sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7` |
| testnet | `tsostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxl49ad` |
| devnet | `dsostms1q9448lst4f762vmgh2pv4k0xlew8cz0sly5ayfew` |
| 2-of-3 (priv 1,2,3) MSH | `c0a3dc4d068c839533cf632be94b4ad683c5d4b3` |
| 2-of-3 mainnet | `sostms1q8q28hzdq6xg89fnea3jh62tfttg83w5kvhukhmh` |
| last char changed | `sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6jq` → REJECT |
| testnet HRP on mainnet body | `tsostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7` → REJECT |

### 10.3 Wallet rules (non-consensus, REQUIRED)

Refuse, before MH, to build any output to a `sostms` address. Refuse at all heights to place an
MSH in an HTLC claim/refund field, a BOND/ESCROW lock, an asset output or any field other than an
`OUT_MULTISIG` output. Display and copy lowercase only.

---

## 11. Activation

* `MULTISIG_HEIGHT` is a profile constant (§2.1). Mainnet value is **40000** if the gates in
  `V40000_CONSENSUS_SCOPE.md` §F are green at the go/no-go cutoff (~#36,000); otherwise the release
  ships with **50000**. The released binary carries exactly one value; only these two are allowed
  (`static_assert`). Required static ordering: `MULTISIG_HEIGHT > HIST_JACKPOT_V2_HEIGHT`,
  `MULTISIG_HEIGHT > V15_HEIGHT`, `MULTISIG_HEIGHT ≥ NODE_BIND_V2_HEIGHT` (mainnet/devnet).
* `h < MH`: identical to today (R1 rejects version ≠ 1; R11/S9 reject 0x50; no byte, count or
  sigcheck rule on the live path; node txs any outer version).
* `h ≥ MH`: §1 items 1–4 together.
* Hard fork: nodes without the release reject v2 txs and 0x50 outputs and split at the first block
  that contains one. Miner/operator notice ≥ 4 weeks before MH.
* Native assets stay at `INT64_MAX` on mainnet; if they activate later, asset txs remain version 1
  (R25), so they can never carry a multisig input.

---

## 12. Offline workflow (non-consensus)

`buildtx → signtx (× M, offline, independent) → combinetx → verifytx → sendrawtransaction`, with
`createmultisig` to set up a policy.

* `createmultisig M PK…` → sorts keys, checks §4, writes `policy.json` {network, M, N, keys, MSH,
  address, ceremony commitments}.
* `buildtx --from-multisig policy.json …` → `sost-psst-v1` JSON: `format`, `network`, `chain_id`,
  `genesis`, `unsigned_hex` (v2 tx; each multisig input with `K = 0`; each single-sig input with
  zero signature and pubkey), per input `{txid, vout, spent_output: {amount, type, pubkey_hash,
  payload_hex}, auth, policy_hex, msh, signatures: {key_index: sig_hex}}`, `outputs_decoded`, `fee`,
  `tx_size`, `sigchecks`, capsule text/hash.
* `signtx` (offline signer) recomputes `sighash_v2` from `unsigned_hex` + the declared spent
  outputs + policy + its built-in CHAIN_ID; refuses if `network`/`chain_id`/`genesis` differ from
  its build, if `MSH(policy) ≠ msh`, or if its key is not in the policy; displays network, every
  input (M-of-N, signatures present), every output, fee, capsule; requires `yes`; adds one
  signature. Passphrases via file/fd only.
* `combinetx` merges files with identical `unsigned_hex`, network, chain_id and policies; when every
  multisig input has ≥ M signatures it selects the **M lowest key indexes** (deterministic) and
  emits `final_hex`.
* `verifytx` runs §7.2–7.5 locally (without UTXO existence) on `final_hex` or a PSST and reports
  threshold status, txid, size, fee, sigchecks; non-zero exit if incomplete or invalid.
* `sendrawtransaction final_hex` (existing).

Rotation: spend the old vault into a new `OUT_MULTISIG` output under the new policy, signed by the
old threshold. No UTXO policy is ever mutated.

---

## 13. Bridge invariants (design invariant, non-consensus)

* Amounts are integers in stocks only. `1 SOST = 100,000,000 stocks` (`STOCKS_PER_SOST`,
  `consensus_constants.h:10`). wSOST has 8 decimals (`contracts/wsost/src/WSOST.sol:17`,
  `uint8 public constant decimals = 8`). **1 stock ⇔ 1 wSOST base unit**, no scaling factor.
* At BALANCED: `native_locked_stocks == wsost_base_units` (the indexer's ledgers G and H, plus
  the in-flight terms defined in `docs/bridge/ARCHITECTURE.md` when not BALANCED). No float or
  double anywhere in amount handling (the Python tooling already parses with `Decimal` and refuses
  floats, `ops/sostbridge/common.py`).
* Vault layout (D7): one 3-of-5 policy (one MSH) per vault; each deposit is its own UTXO under that
  MSH; release change returns to the same MSH; consolidation when the vault holds more than 32
  UTXOs. Observers 2-of-3 with zero key and machine overlap with vault signers.

---

## 14. Residual risks (accepted, documented)

1. **v1 cross-network replay.** All networks share genesis `6517…9f37`; the v1 sighash has no
   CHAIN_ID, so a v1 signature replays on another network wherever the same outpoint exists.
   v2 fixes this; v1 is not changed. Mitigation: wallets build v2 by default after MH; separate
   keys per network.
2. **Signer/combiner txid malleability** before confirmation (D6): re-signing, or choosing another
   M-subset when more than M signatures exist, changes the txid but never the effect. Third-party
   malleability is closed (LOW-S, canonical encoding, exact M, increasing indexes, no trailing
   bytes, node-tx version fence). The bridge keys on spent outpoints and the release capsule, never
   on an unconfirmed txid, and never chains spends of unconfirmed vault outputs.
3. **20-byte MSH**: collision resistance 2⁸⁰; neutralized by the ceremony (§4). A 32-byte policy
   output can be allocated later in `0x51–0x5F`.

---

## 15. Test vector and test plan

Committed now: `tests/vectors/native_multisig_40000.json` and its independent generator
`tools/research/native_multisig_vectors.py` (pure Python, stdlib only): policy, MSH, addresses,
CHAIN_IDs, a full v2 sighash preimage, sighashes per network, and a fully signed 2-input
mainnet v2 transaction (`V2-TX-1`, RFC 6979 deterministic LOW-S ECDSA, 618 bytes,
txid `0a46ff228968ffb450ce65c8443404f42f05af353cf309076d082b5d26d76db5`). The implementation MUST
reproduce every value byte for byte. The named test cases per ctest target are listed per decision
in `MULTISIG_OPEN_DECISIONS_CLOSED.md` §3 and summarized there; every one is REQUIRED before the
implementation can be proposed for merge.

---

## 16. Implementation notes (settled by the implementation, 2026-10-14)

Everything in §1–§15 is implemented as written. This section records the details the
implementation had to settle; none of them changes a rule above.

### 16.1 Activation constant

* `include/sost/params.h`: `V17_HEIGHT` is the single shared activation constant of the
  #40,000 package (mainnet `40000`, `SOST_DEVNET_FORKS` `60`, `SOST_TESTNET_FORKS`
  `INT64_MAX`). `MULTISIG_HEIGHT = V17_HEIGHT`. Gates: `multisig_active_at(h)`,
  `v17_block_limits_active_at(h)`, `node_tx_version_fence_at(h)` (all `h >= V17_HEIGHT`).
* The §11 static assertions are in params.h (mainnet value ∈ {40000, 50000}; ordering against
  `HIST_JACKPOT_V2_HEIGHT`, `V15_HEIGHT`, `NODE_BIND_V2_HEIGHT`).
* The CHAIN_ID literals (`CHAIN_ID_MAINNET/TESTNET/DEVNET`, `ACTIVE_CHAIN_ID`) sit next to the fork
  heights in params.h. `TxValidationContext::chain_id` defaults to `ACTIVE_CHAIN_ID`.

### 16.2 Where each rule lives

| Rule | Location |
|---|---|
| X1–X5 parse, layout dispatch | `TxInput::DeserializeV2From`, `Transaction::Deserialize[From]` (`src/transaction.cpp`) |
| MSH, R26, §7.3 envelope, v2 sighash, sigchecks, exact size, bech32m | `src/multisig.cpp` (`include/sost/multisig.h`) |
| R1, R25, R11/S9 (0x50), R29, R14, R26–R28, R9/S8 exact size, S16–S18 | `src/tx_validation.cpp` |
| §7.1 block limits | `CheckBlockLimitsV17` (`src/block_validation.cpp`), called by `process_block` right after the transactions are parsed (before merkle / coinbase / jackpot / node-tx / signature work) and by `ValidateBlockTransactionsConsensus` |
| R30 | `node_participation::extract_bind_at` / `extract_heartbeat_at` — the one predicate used by the block path (`apply_node_state_for_block`), the mempool validator and the template selector (`judge_node_tx`, `node_txs_valid_for_block`) |
| P_TOO_MANY_SIGCHECKS | `ValidateTransactionPolicy` |
| §9.4 template | `Mempool::BuildBlockTemplate[CPFP]` keep Σ sigchecks ≤ 12,000 (applied at every height: no historical template comes close) |
| §9.5 eviction | `Mempool::RemoveMultisigBeforeActivation(next_height)`, called after every block connect and at the end of every successful reorg (descendants of evicted txs are evicted too) |

`process_block` is the single live acceptance path: P2P relay, `submitblock` and the
`reorg_connect` replay of fork blocks inside `try_reorganize` all pass through it, so the
§7.1 limits are enforced on all three. `load_chain` (re-reading the node's own already-validated
chain file at start-up) is unchanged.

### 16.3 Ordering details

* **S16 placement.** S16 is evaluated after S1, S12, S15, S13, S11 and **before** the HTLC
  dispatch. This makes the §6 table exact: a v2 `auth_kind 0x01` input spending `OUT_HTLC_LOCK`
  reports S16, a v2 `auth_kind 0x00` input spending it reports R20. Consequence (diagnostic only):
  a v1 HTLC_CLAIM/REFUND input spending `OUT_MULTISIG` reports S16 instead of R20.
* **R29** runs right after R11 for every `0x50` output; R14 then allows the payload because R29
  passed (the generic capsule branch is never used for 0x50).
* **R26–R28** run after all outputs, immediately before R9.
* v2 single-sig: an unparseable pubkey reports S6 (§7.4 step 4: "pubkey parses and ECDSA
  verifies else S6"); a pubkey whose hash differs from the lock reports S2 first.
* A version-2 input with `auth_kind ∉ {0x00, 0x01}` cannot be parsed (X3); if one is constructed in
  memory, ValidateStructure rejects it with R26.
* The v2 spent-output list is gathered once per transaction, the first time a v2 input needs its
  sighash; a missing UTXO of ANY input is then reported as S1 at that input's index.

### 16.4 Reason strings

Parse: `truncated`, `unknown_auth_kind`, `policy_n_range`, `sig_count_range` (X2 keeps the existing
"trailing bytes" message). Block: `BLOCK_TOO_MANY_TXS`, `BLOCK_TX_BYTES_EXCEEDED`,
`BLOCK_TOO_MANY_SIGCHECKS`. Node tx: `node_tx_bad_version`. Policy-file / address decoder reasons
(`wrong_hrp`, `bad_checksum`, `mixed_case`, `upper_case`, `char_not_in_alphabet`,
`nonzero_padding`, `bad_padding`, `bad_length`, `bad_format_byte`, `too_long`,
`missing_separator`) are wallet-level, not consensus.

### 16.5 Sigcheck cap reachability

Every VALID form costs at least 98 bytes per sigcheck (§8), so a valid block within 1,000,000
bytes never exceeds 9,933 sigchecks. The count is taken from the bytes before any validation,
however, and a structurally parseable input with `N = 1` and `K = 15` costs 65 bytes per declared
sigcheck: 12,001 sigchecks fit in ~0.84 MB. The ctest `multisig-sigchecks` uses exactly that
construction to prove the cap is enforced (12,000 passes the limit check, 12,001 is rejected with
`BLOCK_TOO_MANY_SIGCHECKS` before any transaction or signature is validated).

### 16.6 Offline workflow as implemented (§12)

* `sost-cli createmultisig <M> <pubkey_hex>... [--out policy.json] [--network N]` writes
  `sost-ms-policy-v1` {network, m, n, keys (sorted), policy_hex, msh, address,
  ceremony_commitments = SHA256(pubkey) per key}. `sost-cli --wallet w getpubkey [addr]` prints a
  wallet key for the ceremony.
* `buildtx --from-multisig policy.json <to> <amount> --out tx.json` (vault spend; `<to>` = sost1 or
  sostms — paying a new policy is the rotation; change returns to the same MSH, D7) and
  `--from-address sost1… buildtx <sostms…> <amount> --out tx.json` (funding: version-2 single-sig
  inputs, `OUT_MULTISIG` output). Both are watch-only, exclude inputs spent in the node mempool, use
  the exact final size for the fee, refuse a non-standard result, and refuse before the network's
  `MULTISIG_HEIGHT` (`--allow-before-activation` exists only so tests can prove the node rejects
  such a tx).
* `signtx tx.json --out signed.json` recognises `sost-psst-v1`; refuses a network, CHAIN_ID or
  genesis different from the signer's, any template inconsistency (template inputs ≠ declared
  inputs, MSH ≠ msh ≠ spent lock, declared fee ≠ computed fee, a carried signature that does not
  verify), and a wallet that holds no usable key; shows network, inputs (M-of-N, signatures
  present), outputs, capsule text + SHA-256, fee, size, sigchecks; requires `yes` (or `--yes`);
  passphrases only by `--passphrase-file`/`--passphrase-fd`/tty. It adds one signature per wallet
  key that belongs to an input (normally exactly one).
* `combinetx a.json b.json … --out c.json` merges identical templates, verifies every signature,
  and when complete emits `final_hex` using the M lowest key indexes.
* `verifytx <file|hex>`: exit 0 = complete and valid (§7.2–7.5 against the declared spent outputs),
  1 = invalid, 2 = incomplete, 3 = raw hex whose structure is valid but whose signatures cannot be
  checked without the spent outputs.
* Node RPCs `getaddressutxos`, `getmempoolspends`, `validateaddress` accept the build's bech32m
  multisig address; it matches only `OUT_MULTISIG` outputs with that MSH (a sost1 address no longer
  lists `OUT_MULTISIG` outputs).
* Wallet refusals (§10.3): a sostms address is refused as an HTLC claim/refund key
  (createhtlclock/claimhtlc/refundhtlc), in BOND/ESCROW locks, and as a destination of the legacy
  single-key builders (send/createtx/sendmany).

### 16.7 Tests (ctest, mainnet flags)

`multisig-vectors`, `-serial`, `-policy`, `-bech32m`, `-sighash`, `-validation`, `-sigchecks`, `-fuzzlite` (deterministic 300,000-mutation parser campaign + 200,000 address corruptions),
`-activation` (mainnet boundaries 39998/39999/40000/40001), `-reorg`, `-mempool`, `-psst`, `-cli`,
plus the updated `type-registry`. Devnet end to end with the real node and miner across the devnet
activation: `tests/run_v17_devnet_multisig.sh <devnet build dir>`.

Still outstanding from §15 / the decisions document: the ≥ 10⁷-exec fuzz campaigns, the testnet
soak across a testnet `MULTISIG_HEIGHT`, the D8 lineage-check script, and external review.

