# PoPC Bond v2 — Real On-Chain Bond Collateral (DESIGN / EPIC)

> **Status:** DESIGN ONLY. No consensus code, no gate change, no activation, no
> deploy. This document opens the engineering epic; it does not implement it.
>
> **Scope guard:** nothing in here changes the current mainnet V15 gates. The V15
> PoPC carrier v1 subsystem stays exactly as shipped. Bond v2 is a *future*,
> height-gated hardening step that will be built, tested, and coordinated
> separately.

---

## 0. TL;DR

The V15 PoPC on-chain carrier (v1) records a commitment's **owner, model,
commitment id, and end height** — but it **does not carry the bond amount**, and
nothing in the consensus/canonical fold binds a commitment to an actual
`OUT_BOND_LOCK` UTXO. The only place the bond figure lives is the per-node RPC
registry (`g_popc_registry` → `popc_registry.json`), which is an
**application-layer local view, not consensus state**.

Consequence: **bond-denominated pool caps and slashing cannot be enforced
deterministically today.** Any cap computed from the RPC registry is bypassable
(a miner can emit a carrier directly without ever touching the registry), and any
cap that tried to read the registry from the consensus path would split the chain
(two nodes with different JSON files compute different sets).

**Bond v2** fixes this by (a) extending the carrier to include `bond_stocks` +
term binding, and (b) requiring the canonical fold to verify that a real
`OUT_BOND_LOCK` from the same owner, of at least `bond_stocks`, locked until at
least `end_height`, actually exists on-chain. Only once the bond is represented
in canonical chain state do the caps become security-relevant.

> [!WARNING]
> **PoPC caps cannot be made security-relevant until bond collateral is
> represented in canonical chain state.** Until Bond v2 lands, any pool cap is
> advisory at best and trivially bypassable via the carrier path. Do not ship,
> announce, or rely on "enforced" caps before Bond v2.

---

## 1. The finding (evidence-cited)

### 1.1 The V15 carrier (v1) does NOT include `bond_stocks`

The event that actually rides on-chain and drives the deterministic active-set
fold is `PopcV15Event`:

- `include/sost/popc_v15.h:159-166` — `PopcV15Event { type, commitment_id,
  owner_pkh, model, height, end_height }`. **There is no `bond_stocks`, no
  `start_height`, no `duration_months` field.**

The carrier wire format matches — v1 base is 67 bytes with no bond field:

- `include/sost/popc_v15.h:378-386` — carrier layout v1:
  `magic(4) | version(1) | event_type(1) | model(1) | commitment_id(32) |
  owner_pkh(20) | end_height(8)` = `POPC_V15_CARRIER_BASE_LEN = 67`. The Activate
  variant (`POPC_V15_CARRIER_ATTEST_LEN = 180`) appends a *gold balance*
  attestation (`balance_mg`, `attest_height`, pubkey, sig) — **still no SOST bond
  amount**. The signed non-attest variant (`POPC_V15_CARRIER_SIGNED_LEN = 164`)
  appends only owner pubkey+sig.
- `include/sost/popc_v15.h:404-436` — `popc_v15_encode_event` /
  `popc_v15_encode_signed_event` / `popc_v15_encode_attest`: none serialize a
  bond amount.
- `include/sost/popc_v15.h:440-471` — `popc_v15_decode_carrier`: parses only the
  fields above; there is no bond to decode.

Note the *local* struct `PopcV15Commitment`
(`include/sost/popc_v15.h:56-65`) **does** have `bond_stocks` (line 61),
`start_height` (line 62), `end_height` (line 63) — and `popc_v15_commitment_id`
(`include/sost/popc_v15.h:75-85`) folds `bond_stocks` into the commitment-id
hash. **But the commitment id is a one-way hash: the bond value is committed to,
not recoverable, and never re-checked against any on-chain lock.** The struct is
never serialized into a carrier.

### 1.2 The carrier path cannot enforce bond-denominated caps

- `src/sost-node.cpp:4631-4663` — `node_collect_popc_events(height)` walks all
  blocks, decodes carrier outputs, verifies owner authorization / attestation
  signatures, and returns `std::vector<PopcV15Event>`. **The events it emits have
  no bond amount**, so any downstream consumer of the canonical set has no
  bond-denominated quantity to cap on.
- `include/sost/popc_v15.h:255-338` — `chain_popc_recompute` /
  `chain_active_popc_set`: the pure canonical fold operates purely on
  `PopcV15Event`; it produces `PopcActiveEntry { commitment_id, owner_pkh, model,
  end_height }` (`include/sost/popc_v15.h:168-173`) — again **no bond field** to
  sum or bound.

There is therefore no path from canonical chain state to a per-commitment or
per-owner bond figure, and thus no way to enforce `min(1000 SOST, 5% pool)` (or
any bond-denominated cap) deterministically on the carrier path.

### 1.3 The RPC registry has bond data, but it is NOT consensus

- `src/sost-node.cpp:110-111` — `static PoPCRegistry g_popc_registry;` persisted
  to `popc_registry.json`.
- `include/sost/popc.h:80-103` — `PoPCCommitment.bond_sost_stocks` (line 86),
  `duration_months` (87), `start_height` (88), `end_height` (89): the registry
  record **does** hold the bond and the full term.
- `include/sost/popc.h:437` — `PoPCRegistry::total_bonded_stocks()`; used at
  `src/sost-node.cpp:3168` for RPC status only.
- `src/sost-node.cpp:3068`, `3072`, `3076` — `popc_register` RPC writes the bond
  into the registry and saves the JSON.

But this is explicitly a **per-node local view, not the source of truth**:

- `src/sost-node.cpp:4618` — comment on the collector: "*it NEVER reads
  popc_registry.json*".
- `src/lottery.cpp:236` — "*V15 active: use the chain-derived active set, NEVER
  popc_registry.json.*"
- `include/sost/params.h:970-992` — the CONSENSUS NOTE: PoPC state lives in
  `popc_registry.json`, is "**NOT derivable from chain state alone**", and if the
  consensus path read it "*two nodes with different files would compute different
  eligibility sets and the chain would split*". Prerequisite (3): "*popc_registry.json
  becomes a cache/view, not source of truth.*"
- `include/sost/params.h:1029-1041` — prerequisites 1-3 are noted as met **for
  eligibility** (a commitment's existence/active-state rides on carriers), but the
  **bond amount specifically was never migrated to the carrier** — that is exactly
  the gap Bond v2 closes.

### 1.4 `OUT_BOND_LOCK` exists but is NOT linked to the PoPC carrier

- `include/sost/transaction.h:46` — `constexpr uint8_t OUT_BOND_LOCK = 0x10;`
- `include/sost/transaction.h:142-143`, `include/sost/consensus_constants.h:20-27`
  — `BOND_LOCK_PAYLOAD_LEN = 8`: payload is `lock_until` (uint64 LE height) only.
- `src/tx_validation.cpp:33-40`, `182-205`, `290-305`, `373` — BOND_LOCK is a
  validated output type (activation-gated, exact 8-byte payload, timelock
  honored), and `src/popc_tx_builder.cpp:39-55` can spend an expired BOND_LOCK
  back to the owner (`include/sost/popc_tx_builder.h:19`).

So a real, timelocked SOST bond UTXO **can exist on-chain** — but:

- The BOND_LOCK payload carries **only `lock_until`**; it has **no
  `commitment_id`** tying it to a specific PoPC commitment.
- **No consensus code correlates a BOND_LOCK UTXO with a PopcV15 carrier.** The
  carrier fold (`node_collect_popc_events` → `chain_active_popc_set`) never
  inspects UTXOs of type `OUT_BOND_LOCK`; the two subsystems are disjoint.

**Therefore: RPC-only caps are not acceptable.** The bond amount used for any cap
must come from canonical chain state, and today it does not.

---

## 2. Design: Carrier v2 with real on-chain bond binding

### 2.1 Carrier v2 must include `bond_stocks`

Carrier v2 extends the on-chain PoPC carrier to bind the commitment, deterministically,
to its bond and full term. Carrier v2 MUST include and bind:

| Field             | Purpose                                                            |
|-------------------|-------------------------------------------------------------------|
| `owner_pkh`       | the bonded owner (already in v1)                                   |
| `commitment_id`   | the commitment being bonded (already in v1)                        |
| `bond_stocks`     | **NEW** — SOST bond amount claimed, in stocks                      |
| `start_height`    | **NEW** — commitment start                                         |
| `end_height`      | commitment end / bond-unlock floor (already in v1)                 |
| `duration_months` | **NEW** — canonical term (1/3/6/9/12), consistent with the reward schedule |

These fields must be part of the signed, domain-separated carrier payload (bump
`POPC_V15_CARRIER_VERSION` and add a v2 magic/length so v1 and v2 decode
unambiguously). The owner authorization signature (already present for
Register/Renew/Suspend, `include/sost/popc_v15.h:181-208`) must cover the new
fields so `bond_stocks`/term cannot be forged or mutated.

### 2.2 The canonical fold must verify a real SOST bond lock

A carrier v2 Register/Activate is only **valid** (contributes to the canonical
active set and to cap accounting) if the fold can find, in canonical chain state,
a matching `OUT_BOND_LOCK` UTXO such that:

1. **Same owner** — the bond lock pays to `owner_pkh` (bond returns to the
   committer).
2. **Amount sufficient** — the locked amount `>= bond_stocks` declared on the
   carrier.
3. **Locked long enough** — the lock's `lock_until >= end_height` (the bond
   cannot be reclaimed before the commitment term ends).
4. **Spendable/slashable by protocol rules** — the bond output is a
   protocol-recognized bond UTXO (linkable to the commitment; see §2.3) so that
   auto-slash can direct it per the slashing policy (redistribution — never
   burned, per `include/sost/transaction.h:60-63`) and auto-settle can release
   it.

If no such bond lock exists, the commitment is **not bonded**, contributes **zero**
to any bond-denominated cap, and (under Bond v2 rules, height-gated) does not
enter the active set as a bonded commitment.

### 2.3 The bond must be deterministic from chain state, not RPC

- The bond amount used for caps/slashing is derived **only** from the on-chain
  BOND_LOCK UTXO + carrier v2 fields, recomputed by every node from the active
  chain (the same pure-fold, reorg-safe pattern as `chain_active_popc_set` and
  `gv_g3b_derive_state` at `src/sost-node.cpp:4678`).
- To make the correlation deterministic and unambiguous, Bond v2 needs an
  explicit **on-chain link between the BOND_LOCK UTXO and the `commitment_id`**.
  Two candidate mechanisms (to be chosen in the format-bump phase):
  - **(A) Extend the BOND_LOCK payload** with a `commitment_id` (32 bytes) — a
    new payload length gated by the Bond v2 height (pre-gate BOND_LOCK stays
    exactly 8 bytes so replay is byte-identical).
  - **(B) Carry the bond outpoint on the carrier v2** (txid+index reference), and
    have the fold resolve + validate that outpoint against the four rules in §2.2.
  Either way the binding is a pure function of the canonical chain.
- `popc_registry.json` becomes strictly a **cache/view** (params.h prerequisite
  3) — never consulted for bond amounts or caps.

### 2.4 RPC `popc_register` may help construct, but is not the source of truth

`popc_register` (`src/sost-node.cpp:3068`, and the carrier workflow in
`docs/V15_POPC_CARRIER_GUIDE.md`) may continue to **construct** the BOND_LOCK
transaction + carrier v2 hex for the user to broadcast (Option B: return
ready-to-broadcast, never auto-spend). But the **truth** about whether a
commitment is bonded, and for how much, comes solely from the on-chain BOND_LOCK
+ carrier v2 recomputed by the fold. A commitment that appears in the registry
but has no valid on-chain bond lock is simply **not bonded** as far as consensus
is concerned.

### 2.5 Caps enforced only after the bond is on-chain

Bond-denominated caps (§3) are computed **only** from the chain-derived bonded
set. They are meaningless — and must not be advertised as enforced — until §2.1-2.3
are live. Ordering is strict: **bond on-chain first, caps second.**

### 2.6 Backwards compatibility / phase-out

- **Carrier v1 remains decodable and backwards-compatible.** v1 carriers already
  in the chain (and any minted before the v2 gate) keep their current meaning:
  they establish eligibility/active-state but carry **zero verifiable bond**, so
  under Bond v2 rules they contribute **zero** to bond caps.
- Carrier v2 is introduced behind a **new future height gate**
  (`POPC_BOND_V2_HEIGHT`, initially `INT64_MAX` on mainnet, early on
  `-DSOST_TESTNET_FORKS`). From that height, new bonded commitments MUST use v2
  and MUST have a verified bond lock to count toward caps / be slashable for
  bond.
- Whether v1 is fully **phased out** (i.e. after some height only v2 counts even
  for eligibility) is a policy decision made at the coordinated-release phase; the
  format supports both a soft (v1 = unbonded) and a hard (v1 rejected past
  height) cut-over.

> Do NOT change current mainnet gates. Do NOT activate Bond v2. Do NOT deploy.

---

## 3. Future cap model (**requires Bond v2**)

> These caps are **inert and non-security-relevant** until §2 is implemented and
> activated. They are recorded here as the target, not as current behavior.

Let `pool` = the PoPC pool balance and let each commitment's `bond` be the
**chain-verified** bonded amount (§2.2).

- **Per commitment:** `bond <= min(1000 SOST, 5% of pool)`
- **Per owner (aggregate across their commitments):** `sum(bond) <= min(3000
  SOST, 10% of pool)`
- **Global max exposure:** total exposure `<= 50% of pool`
- **Exposure definition:** `exposure = bond * 2400 bps` (i.e. `bond * 0.24`),
  summed for the global cap.

A pure, deterministic checker (proposed `popc_pool_caps_check`) will evaluate
these against the chain-derived bonded set at a given height, mirroring the
existing pure-fold style. It is **not written in this epic** — only specified.

---

## 4. Phased implementation plan (no code in this epic)

Each phase is a separate, reviewed, tested change. Nothing below activates on
mainnet until the final coordinated release.

1. **Carrier v2 format bump** — add `bond_stocks`, `start_height`,
   `duration_months` to the carrier; bump `POPC_V15_CARRIER_VERSION` / add v2
   magic + lengths; sign the new fields; keep v1 decode intact. Pure
   encode/decode + unit tests. No fold change yet.
2. **`OUT_BOND_LOCK` linkage in the fold** — choose §2.3 mechanism (A or B), add
   the deterministic bond derivation (owner match, amount `>=`, `lock_until >=
   end_height`, protocol-slashable), recomputed reorg-safely from the active
   chain. BOND_LOCK payload change (if A) is height-gated so pre-gate replay is
   byte-identical.
3. **Pure `popc_pool_caps_check`** — the deterministic cap evaluator over the
   chain-derived bonded set (§3), with exhaustive unit tests (boundaries, whale,
   global-exposure, multi-commitment owners).
4. **New future height gate** — introduce `POPC_BOND_V2_HEIGHT` (=`INT64_MAX`
   mainnet, early on `-DSOST_TESTNET_FORKS`), wire caps + bond verification behind
   it. Mainnet stays byte-identical.
5. **Testnet soak** — full end-to-end on a testnet build (BOND_LOCK + carrier v2
   → active → cap enforcement → auto-slash directs the bond → auto-settle releases
   it). Produce a soak report like `docs/V15_POPC_SOAK_REPORT.md`.
6. **Coordinated release** — mainnet gate flip at a fresh fork height with a
   documented miner-announcement window (mandatory-binary-update fork), exactly as
   V14.5 / V15 were coordinated.

---

## 5. Internal messaging framing

> **PoPC V15 introduces the registration/activation framework and single-model
> design. The next hardening step is Bond v2: representing the SOST bond
> collateral directly on-chain so caps and slashing can be enforced
> deterministically.**

This is a natural, honest progression:
- **V15 (live):** commitments and their lifecycle (Register/Activate/Renew/
  Suspend + auto-slash/auto-settle) are deterministic on-chain carriers; DTD
  eligibility is chain-derived.
- **Bond v2 (next):** the *collateral itself* moves into canonical chain state,
  which is the prerequisite for meaningful pool caps and for the bond being the
  slashable object the model already describes.

---

## 6. Public-copy note (whitepaper / popc-page)

This epic **does not change** the public whitepaper or the popc-page copy. Those
already present PoPC as **design intent, not-yet-fully-active** (activating with
V15 and subject to testing), which remains accurate.

However, flag one precision point: the statement **"the SOST bond is the only
slashable collateral"** is only *fully* true once **Bond v2** lands. Until then
the bond exists in the RPC registry and can exist as a standalone `OUT_BOND_LOCK`,
but consensus does not yet bind that lock to the commitment for deterministic
slashing. No public-copy edit is required now; this is a note for when Bond v2
ships (at which point the claim becomes unconditionally true and can be stated
without caveat).

---

## 7. Cross-references

- `docs/V15_POPC_MODEL_AB_DESIGN.md` — the V15 design this builds on.
- `docs/V15_POPC_CARRIER_GUIDE.md` — the v1 carrier workflow.
- `docs/V15_POPC_MAINNET_ACTIVATION.md` — V15 activation record.
- `docs/POPC_SINGLE_MODEL_DRAFT.md` — single-model (native SOST bond + optional
  Gold Boost) framing.
- `include/sost/popc_v15.h`, `include/sost/popc.h`,
  `include/sost/transaction.h`, `src/sost-node.cpp`, `src/tx_validation.cpp`,
  `src/popc_tx_builder.cpp` — the code cited above.
