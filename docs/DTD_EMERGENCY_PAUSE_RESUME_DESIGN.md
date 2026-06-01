# DTD Lottery Emergency Pause / Resume — Design

**Status:** DESIGNED · consensus-DEFERRED · reference state machine shipped and
unit-tested · active enforcement deferred to a future coordinated fork.

**Scope of this document:** the consensus-safe mechanism that lets the protocol
operator **pause** and later **resume** the DTD lottery redistribution through a
**signed control signal that every node verifies and applies identically** —
never a local VPS / password / admin / RPC toggle that could split consensus.

---

## 1. Why this exists (and why it ships OFF)

The DTD lottery (V11 Phase 2 Proof-of-Participation lottery, see
`include/sost/lottery.h`) redistributes, on a scheduled subset of blocks, the
share that would otherwise go to the Gold Vault and PoPC pool. If a fault were
ever found in that redistribution (eligibility, rollover, or payout
accounting), the protocol needs a way to **stop the redistribution** without a
disruptive emergency hard fork, and to **restart it** once fixed.

This is, explicitly, a **centralized emergency safety brake**. It is justified
only by the asymmetry that a faulty *redistribution* can quietly harm fairness,
while the brake itself is tightly bounded and cannot harm anything else. It must
therefore satisfy two hard requirements at once:

1. **No unilateral, invisible consensus change.** No environment variable, no
   config file, no VPS password, no web admin panel, no database flag, no
   RPC-only local toggle. Anything a single node could flip in private is
   forbidden — it would fork the chain.
2. **Verifiable by every node from the same data.** The pause/resume decision
   must come from a signed object that every node checks against a hardcoded
   public custody set and applies deterministically.

**It ships consensus-INACTIVE.** Two reasons:

- The DTD lottery **coinbase shape itself is not yet consensus-wired** (the C8
  coinbase split lands later — `include/sost/lottery.h` documents `apply_block`
  / coinbase shaping as deferred). Gating a payout path that is not yet enforced
  would be premature.
- The same discipline already used for the **V14 PoPC eligibility gate**
  (`DTD_POPC_GATE_CONSENSUS_ACTIVE = false`) applies here: wire the mechanism,
  prove it with tests, and flip a single constant under an announced fork when
  the prerequisites are met.

While `DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE` (params.h) is `false`,
`is_dtd_emergency_paused_at()` returns `false` for every height and
`is_dtd_lottery_active_at()` reduces **exactly** to
`sost::lottery::is_lottery_block()`. Historical replay is bit-identical.

---

## 2. What the brake may and may not touch

**PAUSE_DTD (in force):**
- Scheduled DTD redistribution is disabled.
- A would-be DTD block behaves like a normal block: the standard
  **50 % miner / 25 % Gold Vault / 25 % PoPC** split.
- No DTD winner is selected; no DTD payout is made.

**RESUME_DTD (in force):**
- Scheduled DTD redistribution resumes from the effective height.
- Normal DTD eligibility rules apply again: SbPoW activity from block ≥ 7,100
  (`is_sbpow_eligible`), anti-dominance < 10 % over the previous 288 blocks
  (`is_dtd_dominant`), recent-winner cooldown, and rollover when no eligible
  miner exists.

**The brake CANNOT, under any code path:**
- change the miner's 50 % block reward;
- alter Proof-of-Work validation;
- change total emission / mint coins;
- change ordinary transaction validation;
- move existing balances;
- touch Gold Vault or PoPC accounting **outside** the DTD redistribution rules.

It is a single boolean gate in front of one payout branch. Nothing else.

---

## 3. Signed control message — `SOST_DTD_CONTROL_V1`

Canonical signed fields (see `dtd_control::canonical_payload`):

| field | type | meaning |
|---|---|---|
| `version` | u32 | format version (1) |
| `chain_tag` | 32 B | binds to one chain: `sha256(network MAGIC bytes)` (params.h `MAGIC_*`) |
| `action` | enum | `PAUSE_DTD` \| `RESUME_DTD` (committed as text) |
| `effective_height` | i64 | height from which the action takes **effect** |
| `nonce` | u64 | strictly-increasing replay counter |
| `reason_hash` | 32 B | hash of an off-chain human reason note (advisory) |
| `created_at_height` | i64 | mint height (audit) |
| `expiry_height` | i64 | rejected once tip ≥ this (0 = never) |
| `key_id` | u8 | custody-set index (diagnostics) |

The signed preimage is the deterministic, newline-separated
`canonical_payload`, hashed with `sha256` — byte-identical on x86 and ARM.

### 3.1 Signing layer — REUSE Beacon custody, do not reinvent

SOST already ships an operator signing/custody facility: the **Beacon**
threshold set `BEACON_THRESHOLD_PUBKEYS` (3-of-5, `include/sost/beacon.h`),
verified with libsecp256k1 ECDSA-DER exactly as `beacon::verify_signature`
does. The shipped pubkeys are **fail-closed placeholders** (valid curve points
owned by no one) until the production release ceremony replaces them.

> **Important distinction.** Beacon itself is, by hard invariant, **advisory
> only** — it "does not, and cannot, change consensus" and its `commands` array
> must be empty. The DTD control signal therefore does **not** ride inside a
> Beacon notice. It **reuses Beacon's custody keys and secp256k1 verify path**
> as its signing layer, but is its own consensus object with its own validation
> rules. This keeps one operator key ceremony, not two.

At activation, `apply_dtd_control` receives `signature_valid` from a verify
function that requires **≥ 3 distinct valid signatures** from the custody set
over `sha256(canonical_payload)` — mirroring `verify_threshold_signatures`.

---

## 4. Validation & state machine

Consensus state (persisted at activation, with pre-block snapshot as reorg undo
data):

```
struct DTDControlState {
    bool      paused;
    uint64_t  last_nonce;
    int64_t   last_effective_height;
    Bytes32   last_reason_hash;
    DTDAction last_action;
};
```

`apply_dtd_control(state, msg, signature_valid, expected_chain_tag, tip)`
rejects in a **fixed order** (each leaves state untouched):

1. **bad signature** → `REJECTED_BAD_SIG` (fail-closed);
2. **wrong chain** (`chain_tag != expected`) → `REJECTED_WRONG_CHAIN`;
3. **bad action** → `REJECTED_BAD_ACTION`;
4. **below minimum** (`effective_height < DTD_EMERGENCY_CONTROL_MIN_HEIGHT`) →
   `REJECTED_BELOW_MIN`;
5. **expired** (`expiry_height != 0 && tip >= expiry_height`) →
   `REJECTED_EXPIRED`;
6. **replay** (`nonce <= last_nonce`) → `REJECTED_REPLAY_NONCE`.

On acceptance: a **higher nonce supersedes** the prior message; `paused` is set
from the action; the snapshot is returned for undo.

### 4.1 Replay protection
Strictly-increasing `nonce`. Equal or lower nonce is rejected. The accepted
nonce becomes `last_nonce`. A message can only ever be applied once, and only in
nonce order.

### 4.2 Height gating
Two distinct heights. **Acceptance** updates the nonce/flag bookkeeping
immediately, but the **effect** (`is_dtd_emergency_paused_core`) only bites at
`height >= last_effective_height`. So a signal can be published ahead of when it
takes hold, and a node validating block `h` reads a deterministic answer for `h`.

### 4.3 Reorg safety
Every `apply_dtd_control` returns `prev` (the full pre-apply state).
`undo_dtd_control(state, applied)` restores it when the carrying block is
disconnected; undo of a rejected (non-mutating) apply is a no-op. Symmetric with
the lottery rollover's existing undo discipline (`undo_lottery_block`).

---

## 5. The single chokepoint

```
is_dtd_lottery_active_at(height, phase2_height, state) =
    sost::lottery::is_lottery_block(height, phase2_height)
    && !is_dtd_emergency_paused_at(state, height)
```

At activation, **both miner and validator** route the DTD payout decision
through this one helper. While the consensus flag is `false`,
`is_dtd_emergency_paused_at` is constant `false`, so the helper is identically
`is_lottery_block`.

---

## 6. Pending jackpot while paused (chosen behavior)

**Freeze.** While paused:
- the existing `pending_lottery_amount` is **frozen** — neither paid out nor
  grown by new scheduled DTD amounts;
- paused DTD-scheduled blocks emit the normal 50/25/25 coinbase (the
  Gold-Vault/PoPC shares are paid normally, exactly as on a non-DTD block), so
  no value is diverted into the jackpot during the pause;
- on `RESUME_DTD` effective height, normal DTD accounting continues from the
  frozen `pending_lottery_amount`.

This is the safest deterministic choice: a pause changes only *whether* the DTD
branch runs, never the jackpot arithmetic. **If, at wiring time, the C8 coinbase
accounting cannot freeze the pending jackpot with full test coverage, active
pause MUST NOT be enabled** until it can — documented here as a hard gate on
flipping the constant.

---

## 7. Explorer / app surfacing (at activation)

- **active:** `DTD Lottery: active`
- **paused:** `DTD Lottery: paused by signed emergency signal` · `Effective
  height: X` · `Last control nonce: N` · `Reason hash: 0x…`
- **resumed:** `DTD Lottery: active` · `Last resume height: X`

Until the flag flips, the explorer/app simply show `DTD Lottery: active` (the
mechanism is designed but inactive).

---

## 8. Prerequisites before flipping `DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE`

1. DTD lottery coinbase shape (C8) wired into block validation.
2. `DTDControlState` persisted in chain state with reorg undo data, and the
   control message carried in a deterministic, consensus-visible location every
   node reads identically.
3. The pending-jackpot freeze (§6) implemented and fully test-covered.
4. `BEACON_THRESHOLD_PUBKEYS` replaced with the real operator 3-of-5 set.
5. Coordinated point release flips the constant under a fresh fork height
   `>= DTD_EMERGENCY_CONTROL_MIN_HEIGHT` with an announced window.

---

## 9. Trust assumptions / limitations

- This is a **centralized** brake. Its authority is exactly the Beacon 3-of-5
  custody — no more, no less.
- It is **strictly limited to DTD lottery pause/resume**. It cannot mint, cannot
  change PoW, cannot move balances, cannot touch the miner reward.
- It is **fail-closed**: any verification failure leaves DTD running normally.
- It exists only to prevent a faulty DTD redistribution from harming protocol
  fairness — a safety valve, not a governance mechanism.

---

## 10. Code map

| file | role |
|---|---|
| `include/sost/dtd_control.h` | message, state, chokepoint, gate predicates |
| `src/dtd_control.cpp` | pure state machine (parse / nonce / undo) |
| `tests/test_dtd_control.cpp` | 44 assertions across all rules above |
| `include/sost/params.h` | `DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE` (false), `DTD_EMERGENCY_CONTROL_MIN_HEIGHT` (= `V14_HEIGHT`) |
| `include/sost/beacon.h` | reused 3-of-5 custody + secp256k1 verify path |
