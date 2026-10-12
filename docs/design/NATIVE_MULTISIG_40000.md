# Native M-of-N multisig for SOST — design for the #40,000 fork target

Status: **DESIGN ONLY — not implemented, not activated, IMPLEMENTATION NOT AUTHORIZED.**
Target: the coordinated #40,000 hard fork (a target, not a commitment; it moves if review is not complete).
Author: Neob. Date: 2026-10-12. Baseline: mainnet validation as of the V30000 release.

---

## 0. Summary

| Item | Proposal |
|---|---|
| New output type | `OUT_MULTISIG = 0x50` (new "custody" range 0x50–0x5F) |
| Lock | 20-byte **policy hash** `MSH = RIPEMD160(SHA256("SOST-MS1" ‖ policy))` in the existing `pubkey_hash` field |
| Spend | **transaction version 2**; each input carries an explicit *auth kind*: single-sig (as today) or multisig (policy + exactly M indexed signatures) |
| Signatures | compact 64-byte ECDSA, LOW-S, exactly **M** signatures, **strictly increasing key index** → canonical, no duplicates, exactly M verifications |
| Sighash | v2 preimage adds a **network tag** and, for multisig inputs, the **MSH** |
| Limits | `1 ≤ M ≤ N ≤ 15`, consensus; block cap `MAX_BLOCK_SIGCHECKS = 12,000` |
| Address | new **bech32m** addresses `sostms1…` (mainnet), `tsostms1…` (testnet), `dsostms1…` (devnet) — never parseable as `sost1` |
| Activation | `MULTISIG_HEIGHT = 40000` (profile constant): before it, `version 2` and `OUT_MULTISIG` are rejected exactly as today (R1 / R11) |
| Bridge vault | 3-of-5 |
| Offline flow | `buildtx` → N × `signtx` (offline, independent) → `combinetx` → `verifytx` → `sendrawtransaction` |
| Consensus change | **YES** (new output type, new tx version, new sighash domain) — this is the only piece of the wSOST / Atomic Swap programme that needs one |

---

## 1. Audit of the current baseline (what exists today)

**Transaction format (consensus, `src/transaction.cpp`).**
`version u32 ‖ tx_type u8 ‖ CompactSize(nin) ‖ inputs ‖ CompactSize(nout) ‖ outputs`.
Input = `prev_txid 32 ‖ prev_index u32 ‖ signature 64 ‖ pubkey 33` (133 bytes, exactly one signature).
Output = `amount i64 ‖ type u8 ‖ pubkey_hash 20 ‖ payload_len u16 ‖ payload (≤ 512)`.
`txid = SHA256d(serialization)` — signatures are part of the txid today.

**Rule R1:** `version == 1`. Any other version is rejected → a version-2 transaction is a clean, unambiguous fork point.

**Sighash (`ComputeSighash`).** `SHA256d(version ‖ tx_type ‖ hashPrevouts ‖ prev_txid[i] ‖ prev_index[i] ‖ spent_amount[i] ‖ spent_type[i] ‖ hashOutputs ‖ genesis_hash)`. `hashOutputs` covers every output including capsule payloads. **Finding:** mainnet, testnet and devnet share the same genesis hash, so today a signature is not bound to a network. The v2 sighash fixes this for the new primitive.

**Allocated identifiers (must not collide).**

| Range | Use |
|---|---|
| `tx_type` 0x00 / 0x01 / 0x02 | standard / coinbase / jackpot |
| `tx_type` 0x10 / 0x11 | HTLC claim / refund |
| `tx_type` 0x20 / 0x21 | NODE_BIND / NODE_HEARTBEAT |
| `OUT` 0x00–0x04 | transfer, coinbase miner / gold / popc / lottery |
| `OUT` 0x10 / 0x11 | BOND_LOCK / ESCROW_LOCK |
| `OUT` 0x12 / 0x13 | HTLC_LOCK / HTLC_CLAIM_WITNESS |
| `OUT` 0x14 | appears as `OUT_HTLC_REFUND` in older branch documentation — **avoid** |
| `OUT` 0x20 | BURN |
| `OUT` 0x30 | NODE_PROTOCOL |
| `OUT` 0x40+ | reserved by the native-assets research spec |
| **`OUT` 0x50** | **proposed: OUT_MULTISIG** |

**Legacy multisig code.** `include/sost/script.h` / `src/script.cpp` (a small script engine with `OP_CHECKMULTISIG`, `sost3` P2SH-style addresses, `MULTISIG_ACTIVATION_HEIGHT = 2000`) and `src/psbt.cpp` are **library-only**: no validation, mempool or block code includes them. They are **not consensus** and are **not reused**: a stack/script engine is a much larger attack surface than this primitive needs, its constant `2000` is meaningless at today's height, and the `sost3` prefix is already associated with a feature that was publicly withdrawn. They should be deleted or clearly fenced off when this design is implemented, to avoid confusion.

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
- `payload`: **same capsule rules as `OUT_TRANSFER`** (a bridge deposit's `WSOST:0x…` capsule rides on the vault output exactly as today). No new capsule rule.
- Valid only at `height ≥ MULTISIG_HEIGHT`; before it, rule R11 rejects the type as it does any inactive type.
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

### 2.4 v2 sighash

```
SHA256d( "SOST-SIGHASH-V2" ‖ network_tag ‖ version ‖ tx_type ‖ hashPrevouts ‖ prev_txid[i] ‖ prev_index[i]
         ‖ spent_amount[i] ‖ spent_type[i] ‖ auth_kind[i] ‖ (auth_kind==1 ? MSH : 20×0x00)
         ‖ hashOutputs ‖ genesis_hash )
network_tag = 8 bytes: "MAINNET\0" | "TESTNET\0" | "DEVNET\0\0"
```

- Commits to every input outpoint, the spent amount and type, all outputs (amounts, destinations, capsule payloads), the policy hash, the network and the genesis.
- Changing any material byte after signing invalidates every signature. `hashPrevouts` covers only outpoints, so collecting signatures never changes the signed message (signatures are not part of the sighash).
- `v1` transactions keep the existing sighash forever (historical behaviour unchanged).

### 2.5 Fees and limits

Fee = Σ inputs − Σ outputs, unchanged. Size limits unchanged (`MAX_TX_BYTES_CONSENSUS 100,000`, standard 16,000; `MAX_INPUTS_CONSENSUS 256`).

| Limit | Value | Reason |
|---|---|---|
| `MAX_MULTISIG_N` | 15 | 15-of-15 input = 1,510 B, still ≤ 10 per standard tx; covers any realistic custody set; above 15 key ceremonies stop being operable |
| `M ≥ 1` | consensus | `M = 0` would be anyone-can-spend |
| `MAX_BLOCK_SIGCHECKS` | 12,000 | worst single-sig block today ≈ 7,500 verifications (1 MB / 133 B); multisig densities (below) reach ≈ 10,000; 12,000 bounds a block at ≈ 0.8 s of verification on a laptop core with headroom, and is far above any real use |
| Standardness | `N ≤ 15`, one multisig policy per input, ≤ 16,000 B tx | mempool keeps the existing standard size |

---

## 3. Address format

Bech32m (BIP-350 checksum) with a distinct human-readable part per network:

| Network | HRP | Example |
|---|---|---|
| mainnet | `sostms` | `sostms1q…` |
| testnet | `tsostms` | `tsostms1q…` |
| devnet | `dsostms` | `dsostms1q…` |

Data = version 0 ‖ 20-byte `MSH`. Properties:
- Cannot be confused with `sost1…` (different prefix, length and alphabet); today's `address_decode` rejects it, so an old wallet **cannot** pay it by accident — it refuses until upgraded.
- 6-character checksum detects typos (a gap of today's `sost1`, which has none).
- Network-separated: a testnet multisig address is rejected on mainnet by prefix.
- `sost3` is **not revived**.

---

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
| wrong network | v2 sighash includes the network tag → invalid; address prefix also differs |
| malformed serialization / trailing bytes / unknown auth kind | tx invalid |
| oversize | existing size limits + sig-check cap |
| partial malformed spend | whole transaction invalid (no partial acceptance) |
| signature reuse on another tx or input | sighash commits to the input index, outpoint and all outputs |
| mutation after signing | any change alters the sighash → all signatures fail |
| pre-activation use | version 2 rejected by R1; `0x50` rejected by R11 |

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
| wrong-network replay | blocked by the network tag |

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

They must not be conflated. Recommendation: **independent sets** — no person or machine holds both an observer key and a vault key. Overlap would let a correlated compromise both mint unbacked wSOST and drain the vault; with independent sets an attacker needs 2 observer keys **and** 3 vault keys, on different machines held by different people.

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
- **Capsules:** unchanged. Capsules ride on outputs; a multisig spend can create an Open Note, a bridge recipient capsule or a governance vote capsule on any output. A governance vote **from** a multisig identity needs the indexer to accept a multisig input as the voter — tooling, not consensus.
- **Native assets (future):** the lock is just "this 20-byte MSH must authorise the spend". A future asset module can reuse `auth_kind 0x01` against an asset-holding output's lock without a second multisig design. Nothing here activates or presupposes assets.

---

## 8. Activation

- New profile constant `MULTISIG_HEIGHT` (mainnet 40000; testnet/devnet low values for testing).
- `< MULTISIG_HEIGHT`: R1 rejects `version != 1`; R11 rejects output type `0x50`. Identical to today.
- `≥ MULTISIG_HEIGHT`: version 2 and `0x50` accepted under §2.
- No reinterpretation of any pre-fork output; historical blocks validate byte-for-byte as before.
- Ships in the same coordinated release as the rest of the #40,000 package; miners and nodes must upgrade before the height.

---

## 9. Performance (measured on this laptop: ECDSA verify ≈ 68 µs with the production miner running)

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
- spends: exact threshold; threshold − 1; M+1 signatures; wrong signer; duplicate index; reordered indices; index ≥ N; high-S; zero sig; signature from another input; another tx; wrong network tag; mutation of each field (amount, destination, capsule byte, outpoint, fee) after signing.
- malformed: truncated policy, unknown auth kind, trailing bytes, auth_kind/UTXO-type mismatch.
- mixed v2 tx with single-sig + multisig inputs; many multisig inputs up to size limits; block at the sig-check cap and one over it.
- activation: every rule at height `MULTISIG_HEIGHT − 1` (rejected) and `MULTISIG_HEIGHT` (accepted).
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
3. **Network tag for single-sig** — the cross-network replay gap also exists for v1; adopt the v2 sighash for single-sig v2 inputs too (it already does) and encourage wallets to build v2 after activation.
4. **Timelocked recovery path** (e.g. 2-of-5 after N blocks) — useful against key loss but adds complexity; out of scope for v1.
5. **HTLC with an MSH claimant** — would let a multisig vault take part in atomic swaps directly.
6. **Bridge vault size per policy** — split the vault into several 3-of-5 outputs to limit the blast radius of a single compromised set.
7. Fate of the legacy `script.h` / `psbt.cpp` library: delete or fence off.

---

## 12. Bridge network target (decided separately)

The canonical wSOST, Gold Reserve V2 and the official HTLC v2 target **Ethereum L1** (Sepolia is the matching testnet), XAUT being native ERC-20 on Ethereum L1. L2 deployments, if any, come later as distribution layers and never hold the canonical supply or the reserve.

---

## Final report (design review)

```
NATIVE_MULTISIG_FEASIBLE:        YES
RECOMMENDED_THRESHOLD:           3-of-5 (bridge vault)
RECOMMENDED_MAX_N:               15
NEW_OUTPUT_TYPE_REQUIRED:        YES — OUT_MULTISIG 0x50 + transaction version 2
ADDRESS_FORMAT_PROPOSAL:         bech32m sostms1 / tsostms1 / dsostms1 (20-byte policy hash)
CONSENSUS_CHANGE_REQUIRED:       YES
TARGET_FORK:                     40000
OFFLINE_SIGNING_COMPATIBLE:      YES (sost-psst-v1: buildtx → signtx ×M → combinetx → verifytx → send)
CAPSULE_COMPATIBLE:              YES (no capsule rule change)
HTLC_COMPATIBLE:                 YES (HTLC untouched; multisig cannot be an HTLC claimant in v1)
BRIDGE_MIGRATION_FEASIBLE:       YES (spend old vault → new MSH, timelocked vault-id update, PoR before/after)
OBSERVER_AND_VAULT_SIGNER_SEPARATION: independent sets; no person/machine holds both
ESTIMATED_TX_SIZE_3_OF_5:        ≈ 400 B per input; ≈ 560 B typical release
ESTIMATED_VALIDATION_COST:       3 × ~68 µs ≈ 0.2 ms per 3-of-5 input; worst block ≈ 0.5–0.7 s, capped by 12,000 sig-checks
SECURITY RISKS:                  threshold compromise (3 keys), correlated observer+signer compromise, key-loss freeze,
                                 signer-side txid malleability (unconfirmed chains only), implementation bugs in a new consensus path
OPEN_DESIGN_QUESTIONS:           §11
IMPLEMENTATION_AUTHORIZED:       NO
```
