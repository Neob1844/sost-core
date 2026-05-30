# V14 — DTD PoPC Eligibility Gate (preparatory, consensus-deferred)

**Activation height (gate wiring):** `V14_HEIGHT = 15000`
**Consensus enforcement flag:** `DTD_POPC_GATE_CONSENSUS_ACTIVE = false`
**Status:** WIRED but DEFERRED. Helper short-circuits to `true`; the
gate is a no-op on eligibility in this build.

This document describes what the V14 PoPC eligibility gate is meant
to do, why it is shipped deferred, and what must happen before the
flag can be flipped to `true`.

---

## 1. Intended rule

From height `h >= V14_HEIGHT`, in addition to all V13 filters:

> A miner_pkh is eligible for the DTD lottery only if the pkh holds
> at least one ACTIVE, non-expired, canonical-type PoPC contract at
> height `h`, as seen by a CONSENSUS-DETERMINISTIC source.

"Canonical types" refers to the existing Model A and Model B
contract definitions in `include/sost/popc.h`:

- Model A — durations `{1, 3, 6, 9, 12}` months, base reward rates
  `{1 %, 4 %, 9 %, 14 %, 20 %}`.
- Model B — same durations, base reward rates
  `{0.4 %, 1.5 %, 3.5 %, 5.5 %, 8 %}`.

The protocol-wide hard cap `POPC_MAX_ACTIVE_CONTRACTS = 1000`
applies (enforced by PoPC transaction validation, not by the lottery
gate).

"Active" means `PoPCStatus == ACTIVE` AND
`current_height < commitment.end_height` AND the commitment has not
been slashed or completed. The lottery gate is a YES/NO predicate
per pkh; it does not score, weight, or aggregate.

---

## 2. Why the gate is shipped deferred

The current PoPC implementation in `src/popc.cpp` and the runtime
state in `src/sost-node.cpp` use a **per-node local file**:

```c++
// src/sost-node.cpp:101
static std::string g_popc_registry_path = "popc_registry.json";
```

This file is loaded at node start and updated as PoPC operations are
processed. It is NOT derived from chain state alone. Two nodes can
hold different versions of `popc_registry.json` — through partial
sync, lost state, manual edits, or simply having processed different
RPC sequences — and still believe their view is correct.

If the V14 lottery gate read `popc_registry.json` from the consensus
path, two nodes with divergent registries would compute different
eligibility sets at every DTD block. They would then disagree on the
DTD winner, produce different valid-from-their-side blocks, and the
chain would split at every DTD block after `V14_HEIGHT`. This is the
worst possible class of consensus bug — silent, deterministic per
node but divergent across nodes, and unrecoverable without a
coordinated rebuild.

`include/sost/popc.h:9-11` already documents the principle that PoPC
remains application-layer:

> Key design principle: "No consensus changes. All PoPC logic remains
> operational/application-layer except that the PoPC Pool receives
> 25 % coinbase by consensus." — Whitepaper Section 6

The V14 gate is the first scenario where PoPC state would need to
participate in consensus. Until PoPC is migrated to chain-state, the
gate cannot enforce.

---

## 3. Current wiring (what this PR ships)

`include/sost/params.h`:

```c++
inline constexpr int64_t V14_HEIGHT                       = 15000;
inline constexpr int64_t DTD_POPC_ELIGIBILITY_HEIGHT      = V14_HEIGHT;
inline constexpr bool    DTD_POPC_GATE_CONSENSUS_ACTIVE   = false;
```

`include/sost/lottery.h`:

```c++
bool has_active_canonical_popc(const PubKeyHash& pkh, int64_t height);
```

`src/lottery.cpp::compute_lottery_eligibility_set`, after the V13
anti-dominance check:

```c++
if (height >= DTD_POPC_ELIGIBILITY_HEIGHT &&
    DTD_POPC_GATE_CONSENSUS_ACTIVE &&
    !has_active_canonical_popc(pkh, height)) {
    continue;
}
```

The helper body in `src/lottery.cpp`:

```c++
bool has_active_canonical_popc(const PubKeyHash& pkh, int64_t height) {
    (void)pkh; (void)height;
    if (!sost::DTD_POPC_GATE_CONSENSUS_ACTIVE) return true;
    return false;  // unreachable in this build
}
```

Net effect on this build: the V14 gate is a no-op on eligibility for
every pkh at every height. Tests
`test_v14_popc_gate_consensus_deferred` and
`test_v14_helper_returns_true_under_flag_false` lock this in. A
compile-time `static_assert(!DTD_POPC_GATE_CONSENSUS_ACTIVE, …)` in
the test file fires if a future commit flips the flag without
revising the test.

---

## 4. Migration prerequisites (before flipping the flag)

The flip from `false` to `true` is a separate, future, coordinated
event — NOT part of this PR. Required prerequisites:

1. **PoPC commitments expressible on-chain.** A well-defined
   transaction class for PoPC create / extend / slash / complete
   operations, validated by `tx_validation` and persisted via
   `utxo_set` or an analogous chain-state structure. The contract
   record's canonical fields (pkh, gold amount, duration, start /
   end height, status) must be reconstructable from chain history
   alone.

2. **Deterministic active-PoPC set per height.** A pure function
   `chain_active_popc_set(height)` that, given a fully-validated
   chain up to `height`, returns the same set of `(pkh, contract_id)`
   pairs on every node. No reads from `popc_registry.json` or any
   other local file.

3. **`popc_registry.json` becomes a cache / view.** The on-disk file
   is regenerated from chain state at node start (or on demand) and
   never serves as a source of truth in the consensus path.

4. **Coordinated point release.** A fresh fork height (separate from
   `V14_HEIGHT` — for example `V14_POPC_GATE_ACTIVATION_HEIGHT`),
   announced publicly with a binary release whose SHA256SUMS is
   signed by the same release key documented in
   `docs/V13_PUBLIC_SCOPE_UPDATE.md`. The flag flip is accompanied
   by a real implementation of `has_active_canonical_popc` that
   reads chain-derived state only.

Until items 1-3 land, the flag stays `false` regardless of how close
the chain is to `V14_HEIGHT`.

---

## 5. What this PR does NOT do

- Does NOT modify `popc_registry.json` format or contents.
- Does NOT add any read of `popc_registry.json` to the consensus
  path.
- Does NOT change reward rates, durations, status enum, or any
  existing PoPC validation rule.
- Does NOT flip `DTD_POPC_GATE_CONSENSUS_ACTIVE` to `true`.
- Does NOT define a hard fork at `V14_HEIGHT` for PoPC enforcement.
  `V14_HEIGHT` is a separate constant from the eventual
  consensus-gate height; flipping the flag will require its own
  documented fork.

The gate is shipped wired so that the activation, when it eventually
happens, is a single-line constant change in `params.h` plus the
replacement of the helper body — no architectural churn in
`compute_lottery_eligibility_set` itself.

---

## 6. Rollback (current build)

The gate is already inert. No rollback needed for this build. If a
future build flips the flag and an incident requires reverting,
revert the flag to `false` and rebuild — every node that processes
the rebuild will return to the no-op eligibility path.

---

## 7. Open questions for the future implementation

These are NOT decisions to be made in this PR. They are recorded so
the next implementer doesn't lose context:

- Should the gate accept Model A and Model B contracts equally, or
  prefer one over the other for DTD eligibility weighting? (Current
  spec: equally — any active canonical contract qualifies.)
- Should the gate check the contract's gold-amount minimum, or
  accept any active contract regardless of size? (Current spec: any
  size — the canonical-type constraint already prevents sybil
  contracts outside the protocol's defined tiers.)
- Should the activation height be `V14_HEIGHT = 15000` itself, or a
  later height once items 1-3 are confirmed deployed and live? (To
  be decided at flip time; do not assume 15000.)
- Should pkh that loses an active contract mid-cooldown be
  retroactively excluded? (Current spec: no — eligibility is
  evaluated per DTD block independently.)
