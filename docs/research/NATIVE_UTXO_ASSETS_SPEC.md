# SOST Native UTXO Assets — Consensus Specification (DESIGN ONLY)

**Status: SPECIFICATION / DESIGN ONLY.** No engine, no web, no code, **no V16 change, no
mainnet, no activation height**. This is the Phase-2 design referenced by
`SOST_UNIVERSAL_ASSETS.md` §1. Anything requiring validator changes is **[CONSENSUS]** and
would ship only after adversarial tests, devnet-first bring-up, external audit and a
coordinated network upgrade — never folded into an in-flight release.

Notation: **[VERIFIED]** = checked against this repo; **[DESIGN]** = proposed here;
**[OPEN]** = needs a decision before any implementation.

---

## 0. Scope and non-goals

**In scope:** a minimal, UTXO-native, colored-coin-style asset layer where each asset is a
first-class ledger object with its own issuer, supply policy and history, and where SOST the
coin only pays fees (supply untouched). Closest priors: Cardano Native Assets and Liquid
Issued Assets (native issuance + unique asset id + controlled reissuance).

**Non-goals:** no VM / smart contracts, no ERC-20 clone, no EVM, no per-token bytecode, no
oracle of off-chain truth. The chain proves *issuer, policy, unit count, control and history*
— never legal meaning, value, custody or off-chain enforcement.

---

## 1. Output-type allocation [VERIFIED free range]

In-use output types: `OUT_TRANSFER 0x00`, coinbases `0x01–0x04`, `OUT_BOND_LOCK 0x10`,
`OUT_ESCROW_LOCK 0x11`, `OUT_HTLC_LOCK 0x12`, `OUT_HTLC_CLAIM_WITNESS 0x13`, `OUT_BURN 0x20`,
`OUT_NODE_PROTOCOL 0x30` (`include/sost/transaction.h`). The **`0x40+` range is FREE**.

Proposed [DESIGN]:

| Type | Value | Meaning |
|---|---|---|
| `OUT_ASSET_GENESIS`  | `0x40` | Defines a new asset; carries the genesis commitment. |
| `OUT_ASSET_HOLDING`  | `0x41` | Holds `N` units of an existing asset at a pkh (the transferable UTXO). |
| `OUT_ASSET_REISSUE`  | `0x42` | Reissuance-authority UTXO (spendable only by the issuance key; mints more). |
| `OUT_ASSET_FREEZE`   | `0x43` | Freeze/thaw control record (only if `freezable` at genesis). |
| `OUT_ASSET_BURN`     | `0x44` | Provable destruction of units (removes from supply). |

Every asset output carries, in its typed payload: `asset_id` (32 B), `amount` (uint64 units),
and for genesis/reissue the policy fields below. SOST value on these outputs is an ordinary
fee-bearing amount (dust rules apply); **units are tracked separately from SOST value**.

---

## 2. Operations

- **ASSET_ISSUE (genesis).** One `OUT_ASSET_GENESIS` output. Derives a unique `asset_id`,
  fixes the immutable policy, and creates the initial supply as `OUT_ASSET_HOLDING` output(s).
  If `reissuable`, it also creates exactly one `OUT_ASSET_REISSUE` authority output.
- **ASSET_TRANSFER.** Spends `OUT_ASSET_HOLDING` inputs of one asset and creates
  `OUT_ASSET_HOLDING` outputs of the **same** `asset_id`; **Σ input units == Σ output units**
  (no fee taken in asset units — fees are always SOST). Change works exactly like SOST change.
- **ASSET_REISSUE.** Spends the `OUT_ASSET_REISSUE` authority; mints additional
  `OUT_ASSET_HOLDING` units and re-creates the authority output (unless the tx retires it).
  Rejected if the asset is `fixed` (non-reissuable) at genesis.
- **ASSET_BURN.** Spends holdings into `OUT_ASSET_BURN`; those units leave circulating supply
  permanently and are provable in the burn output.
- **ASSET_FREEZE.** Only if `freezable=true` at genesis. The freeze authority marks a set of
  holdings frozen (unspendable) or thaws them. **[OPEN]** exact enforcement (per-UTXO flag via a
  freeze registry vs. address-scoped) — see §7 restricted transfers.
- **ASSET_PROOF.** A read-only, no-state SPV-style proof: "these units of `asset_id` existed
  at height H controlled by pkh". Built from existing UTXO/merkle machinery; **no new
  consensus rule** — it is a client/explorer construction.

---

## 3. Asset identity, genesis commitment, authority

- **asset_id [DESIGN]** = `H( genesis_outpoint || issuer_pkh || policy_hash )` (32 B), where
  `genesis_outpoint` is the specific input consumed by the genesis tx. Binding to a concrete
  spent outpoint makes the id **globally unique and non-replayable** — the same policy issued
  twice yields different ids because the consumed outpoint differs (this defeats duplicate
  issuance, §6.4).
- **genesis commitment** = the hash of the canonical policy record, stored in the genesis
  output so every validator recomputes and pins it. The policy is **immutable after genesis**.
- **issuance authority** = the key that can spend `OUT_ASSET_REISSUE` / `OUT_ASSET_FREEZE`.
  Declared at genesis; if `reissuable=false` no authority output is ever created, so supply is
  fixed forever by construction (not by a mutable flag).

### Policy fields (immutable, committed at genesis)
`name/ticker` (advisory), `decimals`, `supply_cap` (or `unlimited`), `reissuable` (bool),
`freezable` (bool), `transfer_restriction` (none | allowlist | issuer-cosign — §7),
`asset_class` (fungible | nft | semi_fungible), `recovery` (none | issuer_recovery declared
here or never — §8), `passport_docref` (optional 32 B link to an Asset Passport capsule).

- **fungible:** `decimals ≥ 0`, arbitrary amounts.
- **nft:** `supply_cap == 1`, `decimals == 0`, exactly one unit ever.
- **semi_fungible:** fixed `supply_cap > 1`, `decimals == 0`, indivisible units.

---

## 4. Validation rules (per tx) [CONSENSUS, DESIGN]

1. **Conservation per asset:** for every `asset_id` appearing in inputs/outputs of a transfer,
   `Σ in == Σ out`. Genesis creates ≤ `supply_cap`; reissue keeps running supply ≤ `supply_cap`.
2. **Single-asset transfer rule [OPEN]:** MVP restricts each tx to *one* `asset_id` (plus SOST
   for fees). Multi-asset txs are a later relaxation; the single-asset rule keeps indexing and
   supply accounting simple and auditable first.
3. **Authority checks:** reissue/freeze require spending the matching authority UTXO with a
   valid signature. `fixed` assets have no authority UTXO → reissue is unrepresentable.
4. **Policy immutability:** the policy is only ever read from the genesis commitment; no tx can
   alter it.
5. **NFT/semi-fungible integrity:** amounts are integers within `supply_cap`; NFTs are never
   split.
6. **Fees always SOST:** asset units are never consumed as fees; a tx with no SOST fee input is
   invalid exactly as today.
7. **Freeze:** a frozen holding cannot be spent in a transfer until thawed by the authority.

---

## 5. Supply accounting

- **circulating(asset_id)** = Σ units in unspent `OUT_ASSET_HOLDING` − Σ in `OUT_ASSET_BURN`.
- Maintained as an **incremental per-asset counter** in the asset index (§6.2), updated on
  connect/disconnect exactly like the UTXO set, so a reorg rewinds supply correctly.
- Invariant checked continuously: `0 ≤ circulating ≤ supply_cap`. A block that would violate it
  is rejected (defends against a reissue bug or a duplicate-issuance attempt).

---

## 6. Risk analysis (the reason this is Phase 2, not a quick add)

### 6.1 UTXO-set bloat
Colored outputs enlarge every UTXO entry (asset_id + amount + policy ref). **Mitigations:**
asset metadata (name/policy) lives once in the asset index keyed by `asset_id`, **not** copied
into each holding (holdings store only `asset_id`+`amount`); dust rules still apply so
economically-worthless holdings are discouraged; consider a minimum SOST "carrier" amount per
asset output. **[OPEN]** carrier amount and whether NFTs get a distinct (cheaper) encoding.

### 6.2 Indexing
A new **asset index** is required alongside the UTXO set: `asset_id → {policy, circulating,
authority_outpoint, freeze_set}`. It must be **derivable purely from block data** (so a fresh
node rebuilds it during IBD) and be reorg-safe (connect/disconnect symmetric). This is the
single largest engineering item.

### 6.3 Reorg
On disconnect, asset genesis/reissue/burn/freeze effects must reverse precisely: re-credit
burned units, un-mint reissued units, restore prior freeze state, and **delete** an asset whose
genesis block is disconnected. Because `asset_id` binds to the genesis outpoint, a disconnected
genesis can never silently "reappear" with the same id after a different history — it must be
re-issued, getting a new id.

### 6.4 Duplicate issuance
Prevented by construction: `asset_id` includes the consumed `genesis_outpoint`; that outpoint
can be spent once, so two genesis txs cannot share an id. A second tx trying to reuse a spent
outpoint is an ordinary double-spend and is rejected.

### 6.5 Double-spend of units
Identical to SOST double-spend defense — a holding is a UTXO; spending it twice is caught by
the UTXO set. The added rule is per-asset conservation (§4.1), which stops "inflation by
transfer".

### 6.6 Wallet
Wallets must track per-asset balances, keep asset outputs out of ordinary SOST coin-selection
(never spend a holding to pay a SOST fee), display units with policy `decimals`, and warn that
a token is a claim, not the asset. Ties into the existing coin-selection work
(`coin_select.h`): asset holdings become a filtered class excluded from SOST selection.

### 6.7 Explorer
Needs per-asset pages: policy, circulating supply, holder distribution, issuance/burn history,
and the Asset Passport link — with strict RPC cost limits (paginate; never full-scan on
request). Mirrors the P8 explorer-history discipline.

### 6.8 Pruning
Genesis + policy records must be retained (or committed to a compact snapshot) even under
block pruning, because they define assets still in circulation. **[OPEN]** either exempt
genesis txs from pruning or maintain a signed asset-registry snapshot that a pruned node keeps.

---

## 7. Restricted transfers [DESIGN, OPEN enforcement]
`transfer_restriction`:
- **none** — free transfer (default).
- **allowlist** — outputs must pay pkhs in an issuer-maintained allowlist (itself an on-chain
  record updated by the authority). Cost: allowlist storage + lookup per transfer.
- **issuer-cosign** — every transfer requires a second signature from the issuance key
  (strong control; weakens censorship-resistance — must be explicit and visible to holders).

These exist so regulated real-world assets *can* be modelled honestly, but the restriction is
**declared at genesis and immutable** — a holder always knows the rules before acquiring.

---

## 8. Recovery
Only if `recovery=issuer_recovery` is declared **at genesis**. It lets the issuance authority
move a holding without the holder's signature (e.g. lost-key recovery for a regulated
security). This is a powerful, dangerous capability: it MUST be genesis-declared, visible on
the asset page, and **never** retrofittable to an asset that launched with `recovery=none`.
Default is `none`.

---

## 9. Explicit boundaries
- **No consensus code is written by this document.** Implementation is gated behind adversarial
  test suites, devnet-first bring-up, an external audit, and a coordinated upgrade.
- **SOST supply is never touched;** assets pay SOST fees only.
- **The chain does not certify off-chain truth.** Native assets add *ledger-enforced supply and
  control*; they do not make a token proof of ownership, authenticity or value. That distinction
  is the same four-state honesty enforced by the Asset Passport
  (DECLARED / VERIFIED / ANCHORED / LEGAL-RIGHT-NOT-VERIFIED).

## 10. Open decisions before any prototype
1. Multi-asset-per-tx (§4.2) — MVP single-asset, or design multi from the start?
2. Carrier SOST amount per asset output and NFT-specific encoding (§6.1).
3. Pruning strategy for genesis/policy (§6.8): exemption vs. signed snapshot.
4. Freeze enforcement model (§2 / §7): per-UTXO flag vs. address-scoped registry.
5. Whether restricted transfers ship at all in a first version, or only `none` + `fixed`/`reissuable`.
