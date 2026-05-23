# Beacon Custody Status

**Last updated:** 2026-05-23 (V13 RC preparatorio commit)

## TL;DR — current state

| Component | Current state |
|---|---|
| Phase II-A single-sig key (`BEACON_PUBKEY_HEX`) | Under operator custody (single key, single holder). |
| Phase II-B threshold keys (`BEACON_THRESHOLD_PUBKEYS[5]`) | **V13 bootstrap: all 5 keys under single-operator custody.** |
| Phase II-B threshold path (`BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT`) | **`INT64_MAX` (OFF by default).** No II-B notice can surface until the sentinel is lowered. |
| Phase III P2P gossip (`BEACON_P2P_ACTIVATION_HEIGHT`) | Active at `V13_HEIGHT` (= 12 000). Carries II-A single-sig notices today. |

The 3-of-5 threshold scheme is **wired in code** (verifier, dedup,
revocation, mirror-metadata, tests) but **not active** at the
validator layer. The 5 production threshold pubkeys are committed in
the binary so the layout is auditable and so a future activation does
not require any code-shape change — only a one-line constant flip.

## Why bootstrap-custody is honest, not a downgrade

The naïve reading of "3-of-5 threshold signatures" is that **no single
person** can publish a critical notice. That property only holds when
the 5 private keys are distributed to 5 independent custodians in
different jurisdictions/persons. A 3-of-5 scheme where the same
person holds all 5 keys is mathematically equivalent to a 1-of-1
scheme: that person can always assemble 3 valid signatures.

To avoid the gap between code and reality, this build:

1. **Tells the truth in the constants.** The sentinel
   `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT = INT64_MAX` keeps the
   threshold advisory path OFF for the entire V13 bootstrap period.
   The code does not pretend a threshold is being enforced when only
   one person can publish.
2. **Tells the truth in the comments.** The 5 entries in
   `BEACON_THRESHOLD_PUBKEYS[]` are commented as
   `// V13 bootstrap: under single-operator custody — see docs/BEACON_CUSTODY_STATUS.md`,
   not `// 5 independent custodians`.
3. **Tells the truth in the docs.** This document is the source of
   truth for the custody state. Public-facing docs
   (`docs/V13_BEACON_PHASE_II_B.md`, `website/sost-faq.html`,
   `website/sost-technology.html`) link here when describing the
   threshold scheme.

## Trigger conditions to lower the sentinel (= activate II-B threshold)

The operator should lower `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT`
from `INT64_MAX` to a finite block height **only when all of the
following are true**:

1. At least 5 distinct natural persons or legal entities are
   identified as future II-B threshold custodians.
2. 4 of the 5 private keys have been physically transferred to those
   custodians (in person, via encrypted USB) and the operator has
   confirmed receipt + custody from each. The operator retains at
   most 1 of the 5 private keys.
3. Each custodian has confirmed they understand they cannot
   unilaterally publish a critical notice (3-of-5 means at least 3
   custodians must coordinate to sign).
4. A test threshold-signed notice has been produced end-to-end on
   non-production data and verified with `scripts/beacon-verify.sh`.
5. This document is updated to reflect the new custody structure
   (custodian count + activation height).

If any condition is not met, the sentinel stays at `INT64_MAX`.

## Operational rules during bootstrap

- All 5 II-B private keys are stored on **separate encrypted USB
  sticks** (one .pem per stick). Different passphrase per stick.
  Passphrases stored SEPARATELY from the .pem files.
- The 5 USB sticks are **physically distributed across at least two
  locations** so a single physical loss (theft, fire, drive failure)
  cannot wipe out all 5 keys.
- The II-A private key is stored on its own encrypted USB (separate
  from the II-B set).
- The operator-only II-A path is what publishes V13 notices today
  (binary verification, fingerprint cross-published on
  sostcore.com / GitHub README / whitepaper / BCT).

## What changes the day the sentinel is lowered

When the trigger conditions above hold and the operator distributes
4 of 5 II-B keys to independent custodians:

1. A single-line commit changes
   `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT` to the chosen activation
   height (e.g. a future V14 height, or any finite future height).
2. This document is updated: the bootstrap section moves to a
   "Historical" section; the active section lists the 5 custodians
   (or their pseudonyms) and the activation height.
3. The operator publishes the activation in a Beacon II-A notice
   (single-sig) explaining the transition.

**No fork.** No chain split. No block validation change. Phase III
P2P keeps gossiping notices exactly as before, but the threshold path
now accepts notices with 3 valid sigs from the 5 distributed keys.

## Code references

| File | Symbol | Notes |
|---|---|---|
| `include/sost/params.h` | `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT` | Sentinel = `INT64_MAX`. |
| `include/sost/beacon.h` | `BEACON_THRESHOLD_REQUIRED = 3`, `BEACON_THRESHOLD_KEY_COUNT = 5` | Threshold parameters. Unchanged. |
| `src/beacon.cpp` | `is_active(...)` | Sentinel check fires BEFORE `verify_threshold_signatures`. |
| `src/beacon.cpp` | `BEACON_THRESHOLD_PUBKEYS[5]` | The 5 production threshold pubkeys (installed in a separate `beacon: install V13 operator public keys` commit). |
| `tests/test_v13_beacon_phase2b.cpp` | `t15_iib_sentinel_off_by_default` | Pins the OFF-by-default invariant. |
