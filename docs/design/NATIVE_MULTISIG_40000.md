# Native M-of-N multisig for SOST — design for the #40,000 fork target

Status: **DESIGN ONLY — not implemented, not activated, IMPLEMENTATION NOT AUTHORIZED.**
Target: the coordinated #40,000 hard fork (a target, not a commitment; it moves if review is not complete).
Author: Neob. Date: 2026-10-12. Revision 3 (OUT_BURN registry correction; production baseline 59a4e666).
**Baseline: production consensus source `3acd952b` (tag `v30000-final`) and production node source `59a4e666` (tag `v30000-final.1`, the binary running on the production node; it changes only `src/sost-node.cpp`).** Note: `main` is NOT a descendant of this commit (it lacks the dormant native-assets code); every statement below was checked against `3acd952b`.

---

## 0. Summary

| Item | Proposal |
|---|---|
| New output type | `OUT_MULTISIG = 0x50` (new "custody" range 0x50–0x5F) |
| Lock | 20-byte **policy hash** `MSH = RIPEMD160(SHA256("SOST-MS1" ‖ policy))` in the existing `pubkey_hash` field |
| Spend | **transaction version 2**; each input carries an explicit *auth kind*: single-sig (as today) or multisig (policy + exactly M indexed signatures) |
| Signatures | compact 64-byte ECDSA, LOW-S, exactly **M** signatures, **strictly increasing key index** → canonical, no duplicates, exactly M verifications |
| Sighash | v2 preimage adds a fixed consensus **CHAIN_ID** (32 bytes per network) and, for multisig inputs, the **MSH** |
| Limits | `1 ≤ M ≤ N ≤ 15`, consensus; block cap `MAX_BLOCK_SIGCHECKS = 12,000` counted structurally (§2.6) |
| Address | new **bech32m** addresses `sostms1…` / `tsostms1…` / `dsostms1…`, fully specified with test vectors (§3) |
| Capsules | **requires a #40,000 R14/S9 extension** so `OUT_MULTISIG` may carry an existing Capsule v1 payload; capsule format unchanged (§2.2) |
| Activation | `MULTISIG_HEIGHT = 40000` (profile constant): before it, `version 2` and `OUT_MULTISIG` are rejected exactly as today (R1 / R11) |
| Bridge vault | 3-of-5 |
| Offline flow | `buildtx` → N × `signtx` (offline, independent) → `combinetx` → `verifytx` → `sendrawtransaction` |
| Consensus change | **YES** (new output type, tx version 2, v2 sighash, R11/S9/R14 extensions, sig-check cap) — the only piece of the wSOST / Atomic Swap programme that needs one |

---

## 1. Audit of the current baseline (what exists today)

**Transaction format (consensus, `src/transaction.cpp`).**
`version u32 ‖ tx_type u8 ‖ CompactSize(nin) ‖ inputs ‖ CompactSize(nout) ‖ outputs`.
Input = `prev_txid 32 ‖ prev_index u32 ‖ signature 64 ‖ pubkey 33` (133 bytes, exactly one signature).
Output = `amount i64 ‖ type u8 ‖ pubkey_hash 20 ‖ payload_len u16 ‖ payload (≤ 512)`.
`txid = SHA256d(serialization)` — signatures are part of the txid today.

**Rule R1:** `version == 1`. Any other version is rejected → a version-2 transaction is a clean, unambiguous fork point.

**Payload rules today (consensus vs policy).** R14 (consensus) allows a payload of up to 512 bytes (R13) on `OUT_TRANSFER` after capsule activation **without checking the capsule format**; asset outputs get a strict format check; everything else forbids payload. The **Capsule v1 format** is enforced only by relay/mining policy (`ValidateTransactionPolicy → ValidateCapsulePolicy`). S9 (consensus) separately whitelists the output types a standard transaction may create.

**Sighash (`ComputeSighash`).** `SHA256d(version ‖ tx_type ‖ hashPrevouts ‖ prev_txid[i] ‖ prev_index[i] ‖ spent_amount[i] ‖ spent_type[i] ‖ hashOutputs ‖ genesis_hash)`. `hashOutputs` covers every output including capsule payloads. **Finding:** mainnet, testnet and devnet share the same genesis hash, so today a signature is not bound to a network. The v2 sighash fixes this for the new primitive.

**Canonical type registry (audited across every local and remote branch, 2026-10-12).** Output type and transaction type are separate enums.

Output types (`TxOutput.type`):

| Code | Name | Status on mainnet (`3acd952b`) |
|---|---|---|
| 0x00 | OUT_TRANSFER | ACTIVE (payload ≤ 512 B allowed by consensus after capsule activation) |
| 0x01–0x03 | OUT_COINBASE_MINER / GOLD / POPC | ACTIVE |
| 0x04 | OUT_COINBASE_LOTTERY | ACTIVE (coinbase rules CB4/CB13) |
| 0x05–0x0F | — | FREE |
| 0x10 / 0x11 | OUT_BOND_LOCK / OUT_ESCROW_LOCK | ACTIVE after bond activation |
| 0x12 / 0x13 | OUT_HTLC_LOCK / OUT_HTLC_CLAIM_WITNESS | ACTIVE ≥ 16,000 (relay ≥ 17,000) |
| 0x14 | (named `OUT_HTLC_REFUND` in older branch docs) | **RESERVED — do not use** (avoid confusion) |
| 0x15–0x1F | — | FREE |
| 0x20 | OUT_BURN | **RESERVED / INACTIVE — DO NOT ACTIVATE.** Not in `IsActiveOutputType` (R11 rejects creating it); S12 rejects spending it. **Native SOST has no burn mechanism and must never gain one** (the code comment: "SOST supply is immutable … nothing is ever burned"). |
| 0x21–0x2F | — | FREE |
| 0x30 | OUT_NODE_PROTOCOL | ACTIVE (V16 NODE_BIND / HEARTBEAT) — ⚠ the dead library `script.h` also defines `OUT_SCRIPT_HASH = 0x30` (collision in unused code; see §1, legacy) |
| 0x31–0x3F | — | FREE |
| 0x40 / 0x41 / 0x42 / 0x43 | OUT_ASSET_TRANSFER / ISSUE_AUTH / **ASSET_BURN** / GENESIS_DEF — `OUT_ASSET_BURN 0x42` destroys units of an *issued native asset* only, **never native SOST** | DEFINED in production code, **dormant**: `NATIVE_ASSETS_ACTIVATION_HEIGHT = INT64_MAX` on mainnet (devnet 42, testnet 30,000). (A comment in `transaction.h` still says "mainnet 30000" — stale.) |
| 0x44–0x4F | — | **RESERVED: native assets** |
| **0x50** | **OUT_MULTISIG (proposed)** | **PROPOSED, #40,000** |
| 0x51–0x5F | — | **RESERVED: custody / multisig** |
| 0x60–0xFF | — | FREE |

Transaction types (`Transaction.tx_type`): 0x00 STANDARD, 0x01 COINBASE, 0x02 JACKPOT, 0x10/0x11 HTLC_CLAIM/REFUND, 0x20/0x21 NODE_BIND/HEARTBEAT, 0x30–0x33 ASSET_GENESIS/ISSUE/TRANSFER/BURN (dormant). **Multisig needs no new tx_type** — it uses transaction *version* 2.

**0x50 collision: NO.** The only concrete asset allocations are 0x40–0x43; the research note "0x40+ range is FREE — natural home for OUT_ASSET_*" was informal. This design formally fixes **0x40–0x4F = native assets** and **0x50–0x5F = custody/multisig**; the registry above should be copied into `transaction.h` as a comment when implemented.

**Legacy multisig code.** `include/sost/script.h` / `src/script.cpp` (a small script engine with `OP_CHECKMULTISIG`, `sost3` P2SH-style addresses, `MULTISIG_ACTIVATION_HEIGHT = 2000`) and `src/psbt.cpp` are **library-only**: no validation, mempool or block code includes them. They are **not consensus** and are **not reused**: a stack/script engine is a much larger attack surface than this primitive needs, its constant `2000` is meaningless at today's height, and the `sost3` prefix is already associated with a feature that was publicly withdrawn. **Implementation requirement:** before native multisig is activated, `script.h` / `script.cpp` / the multisig path of `psbt.cpp` must be **removed** (preferred) or hard-fenced (compiled out, no symbols reachable from wallet/CLI/node, a test asserting no consensus file includes them). Its `OUT_SCRIPT_HASH = 0x30` already collides with `OUT_NODE_PROTOCOL`; no second multisig system may ship.

**Addresses.** `sost1` + 40 hex = `"sost1" ‖ hex(pkh)`, **no checksum**, same string on every network.

---

## 2. Protocol specification

### 2.1 Policy

```
policy = M (u8) ‖ N (u8) ‖ PK_1 ‖ … ‖ PK_N          (each PK = 33-byte compressed secp256k1)
```

Canonical rules (consensus):
- `1 ≤ M ≤ N ≤ 15`.
- Every `PK_i` is a valid compressed point (prefix 0x02/0x03, on curve).
- Keys **strictly increasing** by byte order (`PK_1 < PK_2 < … < PK_N`) → one canonical encoding per key set; duplicates impossible.
- `MSH = RIPEMD160(SHA256("SOST-MS1" ‖ policy))` — the domain tag prevents a policy hash colliding with a single-key `pkh = RIPEMD160(SHA256(pubkey))`.

### 2.2 Output `OUT_MULTISIG (0x50)`

Same 31-byte+payload layout as every output:

```
amount i64 | type 0x50 | pubkey_hash = MSH (20) | payload_len | payload
```

- `amount ≥ DUST_THRESHOLD`.
- `payload`: **empty, or a valid Capsule v1** (so a bridge deposit can pay the multisig vault *and* carry `WSOST:0x…`). Today R14 would reject any payload on a non-`OUT_TRANSFER` type, so this **is a #40,000 consensus extension** (below). The Capsule v1 format itself is unchanged; no Capsule v2, no new encoding.
- Valid only at `height ≥ MULTISIG_HEIGHT`.

**Required #40,000 consensus extensions for the output:**

| Rule | Today | At `height ≥ MULTISIG_HEIGHT` |
|---|---|---|
| R11 (`IsActiveOutputType`) | 0x50 inactive → rejected | 0x50 active |
| S9 (standard-tx output whitelist) | 0x50 not allowed | 0x50 allowed in a standard tx |
| R14 (payload) | payload on 0x50 forbidden | payload allowed **only if** it passes `ValidateCapsuleHeader` + `ValidateCapsuleBody` (Capsule v1 structure) **at consensus level**; arbitrary bytes rejected |
| Relay policy | — | `ValidateCapsulePolicy`, identical to `OUT_TRANSFER` |

Consensus is deliberately *stricter* for `OUT_MULTISIG` than for `OUT_TRANSFER` (which accepts arbitrary bytes for historical reasons): a brand-new type has no legacy to preserve, so it never admits non-capsule data. Validation is not loosened for any existing type.
- UTXO representation: unchanged (amount, type, pkh field, payload). No new UTXO fields, so reorg handling is unchanged.

### 2.3 Spend — transaction version 2

Version 2 keeps the header and outputs identical and changes only the **input** encoding by adding an auth kind:

```
input v2 = prev_txid 32 | prev_index u32 | auth_kind u8 | auth
  auth_kind 0x00  single-sig : signature 64 | pubkey 33           (identical to v1)
  auth_kind 0x01  multisig   : policy (2 + 33N) | K u8 | K × (key_index u8 | signature 64)
```

```
 ┌──────────── multisig input (3-of-5) ─────────────────────────────────────────────┐
 │ txid 32 │ vout 4 │ 0x01 │ M=3 N=5 │ PK1..PK5 (165) │ K=3 │ (i,sig)(i,sig)(i,sig) (195) │
 └──────────────────────────────────────────────────────────────────────────────────┘
   = 36 + 1 + 167 + 1 + 195 = 400 bytes
```

Consensus rules for a multisig input:
1. The spent UTXO has `type == OUT_MULTISIG`; `MSH(policy) == utxo.pubkey_hash`.
2. `policy` is canonical (2.1).
3. `K == M` exactly — no extra signatures (canonical, bounded work).
4. `key_index` **strictly increasing**, each `< N` → no duplicate signer, no reordering variants.
5. Each signature: 64 bytes, non-zero `r,s` in range, **LOW-S**, verifies against `PK[key_index]` and the v2 sighash.
6. Exactly `M` ECDSA verifications per input (indices tell the verifier which key; no trial-and-error like Bitcoin's `CHECKMULTISIG`).

A v2 transaction may mix single-sig and multisig inputs. A `auth_kind 0x01` input that spends a non-multisig UTXO, or `0x00` spending an `OUT_MULTISIG` UTXO, is rejected. Unknown `auth_kind` values are rejected (no "anyone can spend" upgrade hooks).

`txid` stays `SHA256d(full serialization)` as today — consistent with v1, where signatures are in the txid. Consequence (documented): before confirmation a signer could re-sign with a different valid signature and change the txid; this only affects chains of unconfirmed transactions, exactly as with today's single-sig transactions, and it never changes what is paid. A witness-excluding txid would be a larger redesign and is out of scope.

### 2.4 v2 sighash and the consensus CHAIN_ID

```
SHA256d( "SOST-SIGHASH-V2" ‖ CHAIN_ID(32) ‖ version ‖ tx_type ‖ hashPrevouts ‖ prev_txid[i] ‖ prev_index[i]
         ‖ spent_amount[i] ‖ spent_type[i] ‖ auth_kind[i] ‖ (auth_kind==1 ? MSH : 20×0x00)
         ‖ hashOutputs ‖ genesis_hash )
```

**CHAIN_ID** is a 32-byte constant stored as **literal bytes in each network's consensus parameter set** (next to its genesis and fork heights). It is never computed at runtime and never derived from a profile name, config file or command-line string; renaming a profile cannot change it. The values were generated once, reproducibly, as `SHA256("SOST-CHAIN-ID-V1|<network>|<genesis hex>")`, and are then frozen as literals. Consensus uses the literal bytes; they are **never regenerated automatically** (a test asserts the literals, not the derivation):

| Network | CHAIN_ID |
|---|---|
| mainnet | `3ed1273b38ad28c61f591fed49dd8ec8f4684953f17ad371f5c3d741c1d1a2e4` |
| testnet | `301a71e109f7728f83c4fd96d114231c13fafd98a6cb1533caa1267fd385bec3` |
| devnet | `9d651d4c8aada0dde1b7f17cf680c05b76fabff8711d232cb870cb55da007fbe` |

- Commits to every outpoint, spent amount and type, all outputs (amounts, destinations, capsule payloads), the policy hash, the CHAIN_ID and the genesis.
- Changing any material byte after signing invalidates every signature. Signatures are not part of the sighash, so collecting them never changes the signed message.
- Required replay tests: mainnet-v2 signature on testnet and devnet → FAIL; testnet-v2 and devnet-v2 signatures on mainnet → FAIL; fixed sighash test vectors per network.

**v1 / v2 policy.**
- **v1 stays valid after #40,000** with its existing sighash (no CHAIN_ID). Historical and future v1 transactions are never reinterpreted.
- **v2** introduces `auth_kind`, multisig, and the network-bound sighash; v2 single-sig inputs (`auth_kind 0`) also get the CHAIN_ID protection.
- After activation, wallets should build **v2 by default**. The cross-network replay improvement applies to v2 only; it does **not** retroactively change v1 signing semantics (v1 keeps the existing residual risk; keep keys separate per network).
- Retiring v1 for new transactions would be a separate, later decision.

### 2.5 Fees and limits

Fee = Σ inputs − Σ outputs, unchanged. Size limits unchanged (`MAX_TX_BYTES_CONSENSUS 100,000`, standard 16,000; `MAX_INPUTS_CONSENSUS 256`).

| Limit | Value | Reason |
|---|---|---|
| `MAX_MULTISIG_N` | 15 | 15-of-15 input = 1,510 B, still ≤ 10 per standard tx; covers any realistic custody set; above 15 key ceremonies stop being operable |
| `M ≥ 1` | consensus | `M = 0` would be anyone-can-spend |
| `MAX_BLOCK_SIGCHECKS` | 12,000 | consensus limit (§2.6); a v1-only block can contain at most ≈ 7,518 signatures (1 MB / 133 B), so no valid post-fork v1 block can reach it; multisig densities reach ≈ 9,900 |
| Standardness | `N ≤ 15`, one multisig policy per input, ≤ 16,000 B tx | mempool keeps the existing standard size |

### 2.6 Sig-check accounting (consensus)

Counted **structurally from the parsed transactions, before any signature is verified**:

| Transaction / input | sig-checks |
|---|---|
| coinbase, jackpot | 0 |
| v1 standard, HTLC claim/refund, asset tx — per input | 1 |
| v2 input `auth_kind 0` | 1 |
| v2 input `auth_kind 1` | `K` (the declared signature count; must equal `M`) |
| NODE_BIND | 2 (mining signature + node signature slot, counted whether or not the optional node signature is present) |
| NODE_HEARTBEAT | 1 |

`block_sigchecks = Σ over all transactions`. Rule (only at `height ≥ MULTISIG_HEIGHT`): **`block_sigchecks ≤ 12,000` valid; `12,001` → block invalid** (`BLOCK_TOO_MANY_SIGCHECKS`), rejected before verification starts. Mempool: a single transaction may use at most 1,500 sig-checks (policy). Tests: blocks at exactly 12,000 and 12,001; a tx whose declared `K` mismatches `M` is rejected structurally.

The consensus limit is fixed; the timing figures in §9 are a **reference measurement on one machine**, not a consensus input.

### 2.7 Why a 20-byte policy hash (and the ceremony that makes it safe)

`MSH = RIPEMD160(SHA256("SOST-MS1" ‖ policy))`, 160 bits.
- **Second preimage** (outsider builds a different policy matching an existing vault's MSH): ~2¹⁶⁰ work — not a practical risk.
- **Collision** (~2⁸⁰ work): only relevant to an **insider** who chooses their own key *after* seeing the others' and grinds two policies with the same hash — one honest-looking, one they control alone. This is the reason Bitcoin moved multi-party scripts from 20-byte P2SH to 32-byte P2WSH. 2⁸⁰ is very expensive but not unthinkable for a well-funded adversary over the life of a vault.
- **Compatibility:** the output's `pubkey_hash` field is a fixed 20 bytes in the serialization, UTXO set, RPCs, indexers and explorer. A 32-byte commitment would need either a new output layout (UTXO-format change) or putting the hash in the payload, which the bridge needs for the capsule — a second redesign inside #40,000.

**Recommendation: KEEP 20 bytes for #40,000, with a mandatory commit-then-reveal key ceremony**: every signer first publishes `SHA256(pubkey)`; only after all commitments are recorded are the public keys revealed and the policy assembled. No signer can then choose a key as a function of the others, which removes the insider-collision attack. Record the commitments with the vault documentation. A 32-byte policy output (`0x51`) remains possible later inside the reserved custody range if ever justified.

---

## 3. Address format (bech32m, fully specified)

**Encoding**
- Checksum: **bech32m** (BIP-350 constant `0x2bc830a3`), standard bech32 alphabet `qpzry9x8gf2tvdw0s3jn54khce6mua7l`.
- HRP: `sostms` (mainnet), `tsostms` (testnet), `dsostms` (devnet). The HRP belongs to the network's consensus parameter set like CHAIN_ID.
- Data bytes: `0x01` (SOST multisig address format v1) ‖ `MSH` (20 bytes) = 21 bytes. This is **not** a SegWit witness program; the leading byte is an address-format version owned by SOST.
- `convertbits(data, 8 → 5, pad = true)` → 34 five-bit groups; decoders run `convertbits(5 → 8, pad = false)` and reject non-zero padding or leftover ≥ 5 bits.
- Lengths: mainnet 47 characters, testnet/devnet 48. Decoders reject anything other than exactly 21 decoded bytes, a first byte other than `0x01`, or a total length > 90.
- Case: canonical form is **all lowercase**; decoders reject mixed case; wallets display and copy lowercase only.
- Invalid: wrong checksum, wrong HRP for the active network (a testnet address on mainnet is rejected — it also fails the checksum because the HRP is part of it), unknown format byte, wrong length, characters outside the alphabet, missing separator `1`.
- `sost1…` decoders reject these strings by construction (different prefix/length/alphabet), so old wallets cannot pay a multisig address by mistake; `sost3` is not revived.

**Test vectors** (implementation checked against the official BIP-350 vectors `a1lqfn3a` and `abcdef1l7aum6echk45nj3s0wdvt2fg8x9yrzpqzd3ryx`).

Test keys: private keys 1, 2, 3, 4, 5; sorted compressed public keys:
```
PK[0] 022f8bde4d1a07209355b4a7250a5c5128e88b84bddc619ab7cba8d569b240efe4
PK[1] 0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
PK[2] 02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5
PK[3] 02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13
PK[4] 02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9
```

| Vector | Value |
|---|---|
| 3-of-5 policy (167 B) | `0305` ‖ PK[0..4] |
| 3-of-5 MSH | `6b53fe0baa7da53368ba82cad9e6fe5c7c09f0f9` |
| mainnet | `sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7` |
| testnet | `tsostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxl49ad` |
| devnet | `dsostms1q9448lst4f762vmgh2pv4k0xlew8cz0sly5ayfew` |
| invalid checksum (last char changed) | `sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6jq` → REJECT |
| wrong network (mainnet body, testnet HRP) | `tsostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7` → REJECT |
| 2-of-3 (keys 1,2,3) MSH | `c0a3dc4d068c839533cf632be94b4ad683c5d4b3` |
| 2-of-3 mainnet | `sostms1q8q28hzdq6xg89fnea3jh62tfttg83w5kvhukhmh` |

## 4. Security model

### 4.1 Rejection rules (all consensus unless noted)

| Case | Rule |
|---|---|
| `M = 0`, `N = 0`, `M > N`, `N > 15` | policy invalid |
| duplicate public key | impossible: keys strictly increasing |
| invalid / uncompressed key | policy invalid |
| policy not hashing to the UTXO's MSH | input invalid |
| fewer or more than M signatures | input invalid |
| duplicate signature / duplicate signer | impossible: indices strictly increasing |
| reordered signatures | rejected (indices must increase) — one canonical form |
| index ≥ N | input invalid |
| high-S, zero, out-of-range signature | input invalid |
| signature verifying under another key | rejected: each signature is checked only against `PK[index]` |
| wrong network | v2 sighash includes the consensus CHAIN_ID → invalid; address HRP also differs |
| malformed serialization / trailing bytes / unknown auth kind | tx invalid |
| oversize | existing size limits + sig-check cap |
| partial malformed spend | whole transaction invalid (no partial acceptance) |
| signature reuse on another tx or input | sighash commits to the input index, outpoint and all outputs |
| mutation after signing | any change alters the sighash → all signatures fail |
| pre-activation use | version 2 rejected by R1; `0x50` rejected by R11/S9; payload on `0x50` rejected by R14 |
| non-capsule payload on `0x50` | rejected by the R14 extension (Capsule v1 structure required) |
| block over 12,000 sig-checks | block invalid (§2.6) |

### 4.2 Threat model (custody)

| Threat | Effect with 3-of-5 |
|---|---|
| 1 key stolen | no spend possible; replace the set (§6.4) |
| 2 keys stolen | still no spend; urgent rotation |
| 3 keys stolen | **funds at risk** — threshold reached; mitigations: independent signers, hardware keys, geographic separation, bridge caps, mint pause |
| 1–2 keys lost | still spendable (3 of the remaining) |
| 3 keys lost | **funds frozen** — mitigated by rotating as soon as one key is lost |
| malicious coordinator | can only propose; each signer sees and checks the full transaction offline |
| tampered PSST file | signatures only ever commit to what the signer displayed |
| wrong-network replay | blocked by the CHAIN_ID (v2) |

---

## 5. Offline signing and the partially-signed container

### 5.1 Why not copy PSBT
SOST has no script engine and a fixed sighash, so a SOST-native container needs far less than Bitcoin PSBT.

### 5.2 `sost-psst-v1` (Partially Signed SOST Transaction) — extends the existing `sost-unsigned-tx-v1`

```json
{
  "format": "sost-psst-v1",
  "network": "mainnet",
  "genesis": "6517…9f37",
  "unsigned_hex": "<v2 tx with every multisig input's signature list empty>",
  "inputs": [
    {"txid": "…", "vout": 0, "amount": 10000000000, "output_type": 80,
     "auth": "multisig", "policy_hex": "0305<5×33-byte keys>", "msh": "…",
     "signatures": {"1": "<64-byte hex>", "3": "<64-byte hex>"}}
  ],
  "outputs_decoded": [...],
  "fee": 2020,
  "capsule": {"mode": "open-note", "text": "WSOST-RELEASE:0x…", "sha256": "…"},
  "htlc": null
}
```

- The transaction to sign (`unsigned_hex`) **never changes** while signatures are collected — signatures live only in `inputs[i].signatures`.
- Every signer recomputes the sighash locally from `unsigned_hex` + declared amounts/types + policy; a lying file can only produce invalid signatures.

### 5.3 Commands (extend the existing `buildtx` / `signtx` CLI)

```
ONLINE   sost-cli --from-multisig policy.json buildtx <to> <amt> [--capsule-*] --out release.psst
OFFLINE  signer k:  sost-cli --wallet signer_k.v2.json signtx release.psst --out release.k.psst   (adds 1 signature)
ONLINE   sost-cli combinetx release.1.psst release.3.psst release.4.psst --out release.full.psst
ONLINE   sost-cli verifytx release.full.psst     # threshold reached? every signature valid? canonical order?
ONLINE   sost-cli sendrawtransaction $(sost-cli finalizetx release.full.psst)
```

- `createmultisig M PK… → address + policy.json` (keys sorted canonically, the file records M, N, keys, MSH, address, network).
- `signtx` shows network, every input (with M-of-N and which keys have already signed), every output, destination, amount, fee, capsule text/hash, then asks for `yes`. Encrypted v2 wallets via passphrase file/fd (never on a command line). No signer needs another signer's key.
- `combinetx` refuses files whose `unsigned_hex`, network or policy differ.

---

## 6. Bridge use

### 6.1 Two different security layers

| Layer | Who | Authorises | Compromise effect |
|---|---|---|---|
| **Observers 2-of-3** | read SOST, sign EIP-712 attestations | **minting** wSOST on Ethereum | can mint unbacked wSOST (bounded by caps; reconciliation → CRITICAL → mint pause) |
| **Vault signers 3-of-5** | hold native SOST custody keys | **spending** the Bridge Vault (releases) | can move locked SOST |

They must not be conflated: observer compromise controls **mint authorisation**; vault-signer compromise controls **native SOST custody**.

**Mandatory invariant: ZERO key overlap and ZERO machine overlap** — no observer private key is ever a vault key, no machine holds keys of both layers, and no observer host can reach a vault signer's key material. Plus **strong organisational separation** (different custodians/roles, separate credentials and backups, different hosting for observers).

**Zero personnel overlap** is the stronger target but not made a hard rule for the capped pilot, where the team is small and forcing it could push keys onto weaker setups. It becomes **required before bridge caps are raised beyond pilot levels**. Rationale: with independent sets an attacker needs 2 observer keys **and** 3 vault keys on different machines; a person holding both kinds of key collapses that to one social-engineering target.

### 6.2 Normal release
`BurnedForRelease` on Ethereum → indexer → release request → `buildtx --from-multisig` with the `WSOST-RELEASE:0x<burnId>` capsule → 3 offline signatures → combine → verify → broadcast → reconciliation `BALANCED`. The existing `ReleaseSigner` interface gets a `NativeMultisigSigner` implementation (placeholder already in `ops/sostbridge/signer.py`).

### 6.3 Emergency pause
Observers / admin pause **minting** on Ethereum (exists). Vault signers simply stop signing releases. Neither layer can alter the other.

### 6.4 Signer replacement and migration
A UTXO's policy can never be mutated in place — the MSH is committed in the output. Replacing signers = **spend the vault into a new `OUT_MULTISIG` output** with the new policy, signed by the current threshold.

Migration from today's pilot (`ColdSingleSigner`, single `sost1` vault) to `NativeMultisigSigner`:

1. Pause new mints (`pauseMint`); stop accepting new deposits to the old vault (announce, observers stop attesting new deposits to it).
2. Reconcile: `BALANCED`, no pending releases.
3. Create the 3-of-5 policy; publish address + policy + MSH.
4. Old vault → new multisig vault (one tx, release capsule `WSOST-MIGRATE:<new MSH>`).
5. Wait for finality; proof of reserves on the new vault ≥ totalSupply.
6. Update the authorised vault identifier on Ethereum through the existing 2-day timelocked config (`bridgeVault` hash) and the observers' config.
7. Resume.

wSOST `totalSupply`, deposit history and burn history are untouched; no SOST is burned; every step is an on-chain event an auditor can replay.

---

## 7. Compatibility

- **HTLC / Atomic Swap:** HTLC transactions remain version 1 with tx_type 0x10/0x11 and are unchanged; existing HTLC UTXOs are unaffected. Limitation: an HTLC's `claim_pkh` / `refund_pkh` is a single key, so a multisig cannot be the claimant of an HTLC in this design (a future "HTLC to MSH" variant is possible but out of scope).
- **Capsules:** the capsule *format* is unchanged. A multisig **spend** can create any existing capsule on its `OUT_TRANSFER` outputs (Open Note, `WSOST-RELEASE`, governance vote) with no rule change. A capsule **on an `OUT_MULTISIG` output** (e.g. a deposit paying the vault with `WSOST:0x…`) needs the #40,000 R14/S9 extension in §2.2. A governance vote **from** a multisig identity needs the indexer to accept a multisig input as the voter — tooling, not consensus.
- **Native assets (dormant, 0x40–0x43):** asset outputs are locked by a single-key `pubkey_hash`. In this design a multisig cannot hold assets. Because the lock is just "this 20-byte MSH must authorise the spend", a later asset revision can accept `auth_kind 0x01` on asset outputs whose lock is an MSH, without a second multisig design. Nothing here activates or presupposes assets.

---

## 8. Activation

- New profile constant `MULTISIG_HEIGHT` (mainnet 40000; testnet/devnet low values for testing).
- `< MULTISIG_HEIGHT`: R1 rejects `version != 1`; R11/S9 reject output type `0x50`; R14 rejects any payload on it; no sig-check cap is evaluated. Identical to today.
- `≥ MULTISIG_HEIGHT`: version 2, `0x50` (R11/S9), Capsule v1 payload on `0x50` (R14 extension), the v2 sighash with CHAIN_ID and the 12,000 sig-check block cap all take effect together.
- No reinterpretation of any pre-fork output; historical blocks validate byte-for-byte as before.
- Ships in the same coordinated release as the rest of the #40,000 package; miners and nodes must upgrade before the height.

---

## 9. Performance — REFERENCE MEASUREMENT (not a consensus input; one laptop, ECDSA verify ≈ 68 µs with the production miner running)

| Spend | Input size | Verifications | Verify time / input | Worst-case block (1 MB) |
|---|---|---|---|---|
| single-sig (v1) | 133 B | 1 | ~0.07 ms | ≈ 7,500 sigs ≈ 0.51 s |
| 2-of-3 | 36+1+101+1+130 = **269 B** | 2 | ~0.14 ms | ≈ 7,400 sigs ≈ 0.50 s |
| 3-of-5 | **400 B** | 3 | ~0.20 ms | ≈ 7,500 sigs ≈ 0.51 s |
| 5-of-5 | 530 B | 5 | ~0.34 ms | ≈ 9,400 sigs ≈ 0.64 s |
| 15-of-15 | 1,510 B | 15 | ~1.0 ms | ≈ 9,900 sigs ≈ 0.67 s |

A typical 3-of-5 bridge release (1 multisig input, a release output with a 92-byte capsule, change back to the vault) ≈ **560 bytes**. Signature density per byte is at most ~1.3× today's, so validation cost is not a meaningful DoS lever; `MAX_BLOCK_SIGCHECKS = 12,000` makes the bound explicit.

---

## 10. Test plan (for the future implementation branch)

Unit / consensus:
- policies 1-of-1, 2-of-3, 3-of-5, 5-of-5, 15-of-15; invalid M=0, N=0, M>N, N=16, unsorted keys, duplicate key, bad point.
- spends: exact threshold; threshold − 1; M+1 signatures; wrong signer; duplicate index; reordered indices; index ≥ N; high-S; zero sig; signature from another input; another tx; wrong CHAIN_ID (other network); mutation of each field (amount, destination, capsule byte, outpoint, fee) after signing.
- malformed: truncated policy, unknown auth kind, trailing bytes, auth_kind/UTXO-type mismatch.
- mixed v2 tx with single-sig + multisig inputs; many multisig inputs up to size limits; block at the sig-check cap and one over it.
- activation: every rule at height `MULTISIG_HEIGHT − 1` (rejected) and `MULTISIG_HEIGHT` (accepted).
- capsules on `OUT_MULTISIG`: valid Open Note; bridge recipient capsule; governance vote capsule; malformed capsule (bad magic / body length); oversize (> per-type limit and > 512); unknown capsule type; non-capsule bytes; payload on 0x50 before activation → all as specified in §2.2.
- CHAIN_ID: fixed sighash vectors per network; mainnet↔testnet↔devnet replay → FAIL; v1 signatures unchanged.
- bech32m: every vector and invalid case in §3; mixed case; bad padding; wrong format byte.
- sig-checks: block at 12,000 → valid; 12,001 → invalid; NODE_BIND counted as 2.
- legacy: a test asserting no consensus/wallet/CLI file includes `script.h`/`psbt.cpp` (or that they are deleted).
- **historical regression:** full re-validation of mainnet blocks 0 → tip byte-identical (including the two known historic-exception classes).

Integration (devnet):
- mempool accept/reject, block inclusion, 1–5 block reorg of a multisig deposit and of a multisig spend.
- offline: buildtx → 3 independent signtx (v1 and encrypted v2 signer wallets) → combinetx → verifytx → broadcast; tampered PSST; combinetx with mismatched files.
- capsule spends (Open Note, bridge recipient, governance vote); HTLC lock/claim/refund regression; Atomic Swap E2E regression.
- wallet recovery from policy.json + any M keys; signer loss and rotation; full bridge migration rehearsal (§6.4) with proof of reserves before/after.

---

## 11. Open design questions

1. **Witness-excluding txid** (segwit-style) — would remove signer-side txid malleability for multisig; cost: block/merkle/RPC changes. Recommendation: not in #40,000.
2. **Schnorr/MuSig aggregation** — one signature per input regardless of M; much smaller and private, but a new signature scheme and key-aggregation ceremony. Recommendation: later, if ever.
3. ~~Network binding for single-sig~~ — decided: v2 single-sig inputs carry the CHAIN_ID; v1 keeps its sighash (§2.4).
4. **Timelocked recovery path** (e.g. 2-of-5 after N blocks) — useful against key loss but adds complexity; out of scope for v1.
5. **HTLC with an MSH claimant** — would let a multisig vault take part in atomic swaps directly.
6. **Bridge vault size per policy** — split the vault into several 3-of-5 outputs to limit the blast radius of a single compromised set.
7. ~~Fate of legacy `script.h` / `psbt.cpp`~~ — decided: remove (or hard-fence) before activation (§1).
8. Repository hygiene: `main` and production diverged at `440defe5` (main +237 commits, production +82). The #40,000 implementation must branch from the reconciled production-derived baseline (`reconcile/v30000-production-main`, from `59a4e666`), never from `main`. See docs/reconcile/RECONCILIATION_PLAN.md on that branch.

---

## 12. Bridge network target (decided separately)

The canonical wSOST, Gold Reserve V2 and the official HTLC v2 target **Ethereum L1** (Sepolia is the matching testnet), XAUT being native ERC-20 on Ethereum L1. L2 deployments, if any, come later as distribution layers and never hold the canonical supply or the reserve.

---

## Final report (design review, revision 2)

```
OUTPUT_TYPE_0x50_COLLISION:      NO (concrete asset types are 0x40–0x43; ranges now fixed formally)
CANONICAL_OUTPUT_REGISTRY:       §1 — 0x00–0x04 active · 0x10–0x13 active · 0x14 reserved/do-not-use · 0x20 OUT_BURN RESERVED_INACTIVE (native SOST burn: NEVER) · 0x30 node protocol
                                 · 0x40–0x43 assets (dormant) · 0x44–0x4F reserved assets · 0x50 multisig · 0x51–0x5F reserved custody
FINAL_MULTISIG_OUTPUT_TYPE:      0x50 OUT_MULTISIG
NATIVE_ASSET_RESERVED_RANGE:     0x40–0x4F (outputs); tx types 0x30–0x33
OUT_BURN_0x20_STATUS:            RESERVED_INACTIVE (do not activate)
NATIVE_SOST_BURN:                NEVER
OUT_ASSET_BURN_0x42:             ASSET_ONLY (dormant with the asset layer)
CAPSULE_RULE_CURRENT:            R14 consensus: payload ≤ 512 B on OUT_TRANSFER after capsule activation, format NOT checked by
                                 consensus (Capsule v1 enforced by relay policy only); asset outputs strict format; others forbidden
CAPSULE_RULE_40000_PROPOSED:     at ≥ MULTISIG_HEIGHT, OUT_MULTISIG payload = empty OR valid Capsule v1 (header+body checked at
                                 consensus); same relay policy as OUT_TRANSFER; plus R11 and S9 extensions for 0x50
CAPSULE_FORMAT_CHANGED:          NO
CHAIN_ID_DESIGN:                 32-byte literal per network in consensus params, inside the v2 sighash; values in §2.4
RUNTIME_PROFILE_USED_AS_CONSENSUS_ID: NO
V1_POST_40000_STATUS:            valid, unchanged sighash; wallets default to v2; v2-only replay protection
BECH32M_ENCODING_FULLY_SPECIFIED: YES (+ vectors, checked against BIP-350 official vectors)
SIGCHECK_COUNTING_FULLY_SPECIFIED: YES (structural, before verification; 12,000 valid / 12,001 invalid)
POLICY_HASH_20_BYTE_RECOMMENDATION: KEEP (+ mandatory commit-then-reveal key ceremony)
LEGACY_MULTISIG_DISPOSITION:     REMOVE (hard-fence only as a fallback)
BRIDGE_THRESHOLD:                3-of-5
OBSERVER_THRESHOLD:              2-of-3
KEY_MACHINE_OVERLAP:             NO (mandatory); zero personnel overlap required before caps exceed pilot levels
NATIVE_MULTISIG_FEASIBLE:        YES
OFFLINE_SIGNING_COMPATIBLE:      YES
HTLC_COMPATIBLE:                 YES (HTLC untouched; multisig cannot be an HTLC claimant in v1)
BRIDGE_MIGRATION_FEASIBLE:       YES
ESTIMATED_TX_SIZE_3_OF_5:        ≈ 400 B per input; ≈ 560 B typical release
IMPLEMENTATION_AUTHORIZED:       NO
```
