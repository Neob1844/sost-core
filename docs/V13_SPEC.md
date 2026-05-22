# V13 — block 12 000 hard fork specification

This document is the operator-facing reference for the V13 hard fork.
Every code change is anchored to a commit hash so the runbook below
remains traceable after merge.

## Activation

```
V13_HEIGHT = 12 000
```

Defined in `include/sost/params.h`. Three coordinated changes activate
together at this height:

| # | Change                                           | Mechanism                          |
|---|--------------------------------------------------|------------------------------------|
| 1 | Lottery recent-winner exclusion window 5 → 6     | `lottery_exclusion_window_at(h)`   |
| 2 | Future-timestamp drift cap 60 s → 30 s           | `max_future_drift_at(h)`           |
| 3 | Beacon Phase II-A — local signed-notice display  | `BEACON_PHASE2A_ACTIVATION_HEIGHT` |

A fourth scaffold ships in the same release but is **DISABLED**:
Beacon Phase III P2P (gate `BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX`).

## Pre-V13 vs post-V13 — what changes for a node operator

| Behaviour                                | h < 12 000          | h ≥ 12 000          |
|------------------------------------------|---------------------|---------------------|
| Lottery cooldown (block-miner exclusion) | last 5 blocks       | last 6 blocks       |
| Future-timestamp drift cap               | 60 s                | 30 s                |
| Beacon notices on RPC `getbeaconnotices` | empty `notices`     | active notices      |
| Beacon advisory banner on miner stderr   | silent              | per-notice banner   |
| Phase III P2P gossip                     | inactive            | inactive (DISABLED) |
| Validator behaviour for replay <6 550    | unchanged (600 s)   | unchanged           |
| Validator behaviour for replay <12 000   | unchanged (60 s)    | unchanged           |

Pre-V13 behaviour is **bit-identical** to the prior release for every
height in `[0, V13_HEIGHT)`. The helpers `lottery_exclusion_window_at`
and `max_future_drift_at` cover all three historical regimes:

```
heights              lottery cooldown   future-drift cap
-------------------  ----------------   ----------------
[0, 6 550)           5                  600 s   (legacy)
[6 550, 12 000)      5                  60 s    (staged-relief)
[12 000, ∞)          6                  10 s    (V13)
```

The helpers are the **single source of truth**. Every consensus call
site goes through them; no other code path may reference the underlying
constants directly.

## Cooldown 5 → 6 — rationale

The bump is justified by a structural-alignment argument, not by
aggregate-metric improvement. See `docs/V13_COOLDOWN_AUDIT.md` for the
full quantitative record.

Summary of the trade:

- Aggregate Monte Carlo metrics (dom_share, sybil_delta, honest_worst,
  rollover_max) regress slightly under window=6 (~0.05 % in dom_share).
- The structural argument: in the permanent-phase 1-of-3 lottery
  cadence, window=6 guarantees a deterministic 2-firing exclusion of
  any recent block miner regardless of `H mod 3`; window=5 is
  alignment-fuzzy (1 firing at `H ≡ 0 mod 3`, 2 firings elsewhere).
- The fork accepts the small aggregate regression as the cost of the
  clean structural guarantee.

This is documented in the audit as a deliberate trade, not an outcome
optimisation.

## Drift 60 s → 30 s — rationale

Future-timestamp drift is the gap a miner can place its candidate
block's timestamp ahead of true time. The pre-V13 cap (60 s) lets a
miner anticipate up to 60 s of cASERT staged-relief or V12 Slingshot
movement by inflating the timestamp; V13 reduces that to 10 s.

The 6× tightening narrows every same-block timestamp-gaming margin.
Slingshot tier T1 (the only tier within reach of the cap) goes from
"can be claimed up to 60 s early via a future-timestamp" to "can be
claimed up to 10 s early".

Critical operator consequence: **NTP synchronisation is now a hard
requirement for any node that mines after V13_HEIGHT.** A miner whose
clock is more than 30 s ahead of true time will produce candidate
blocks that the validator rejects at the future-drift check. The
pre-V13 60-second margin tolerated coarse clocks; the V13 10-second
margin does not.

## Beacon Phase II-A — local signed notices

After V13_HEIGHT the node surfaces signed network notices placed at
`<datadir>/notices.json` by the operator. The path is intentionally
local-file only: no HTTP, no P2P. The operator drops the file; the
node validates and serves; the miner polls and prints.

### Hard rules — Beacon Phase II-A

```
Beacon Phase II-A puede informar.
Beacon Phase II-A no puede reiniciar.
Beacon Phase II-A no puede bloquear.
Beacon Phase II-A no puede cambiar consensus.
Beacon Phase II-A no puede cambiar mining.
Beacon Phase II-A no puede ejecutar comandos (`commands` MUST be []).
```

These rules are mirrored in code:

- `commands` non-empty ⇒ schema-layer reject (`beacon::is_active`).
- All failure paths return empty / silent (`beacon::load_active_notices`).
- The miner hook is read-only: it polls RPC, dedups by `notice_id`,
  prints to stderr, never modifies mining decisions.

### Schema (Phase II-A)

```json
{
  "notice_id": "v13-postfork-001",
  "network": "mainnet",
  "severity": "info",
  "title_en": "Network notice title",
  "message_en": "One-paragraph human-readable body.",
  "activation_height": 12500,
  "expires_height": 13000,
  "created_at": "2026-05-07T00:00:00Z",
  "commands": [],
  "signature": "<base64 ECDSA-SHA256 over secp256k1 of canonical payload>"
}
```

Required fields, types, and limits match the explorer Phase 1 schema
(`docs/beacon.md`). The C++ Beacon path is fully interoperable with
the explorer JS path: the same shell script (`scripts/beacon-sign.sh`)
produces a notice consumed identically by both.

### RPC

```
$ sost-cli getbeaconnotices
{
  "phase": "phase-2a-local",
  "activation_height": 12000,
  "current_height": 12345,
  "dormant": false,
  "p2p_activation_height": 9223372036854775807,
  "p2p_enabled": false,
  "notices": [...]
}
```

Pre-V13 the same call returns `"dormant": true` and `"notices": []`
regardless of file contents.

## Operator checklist (run BEFORE V13_HEIGHT)

The chain is currently at ~h = 7 350. V13_HEIGHT = 12 000. At ~10-minute
target spacing the activation is ~32 days out from h = 7 350 — adjust
to the actual current height when reading.

### 0. Telemetry (do this WEEK 1)

- [ ] Survey miner NTP status. A miner whose clock is > 30 s ahead at
      V13_HEIGHT will start producing rejected candidates. Capture the
      worst-case drift across the active miner set.
- [ ] Decide if the 30 s drift cap is acceptable for the observed
      population. If not, **escalate to the CTO before V13_HEIGHT** —
      the cap can be revisited via a separate fork before activation.

### 1. Beacon keypair (do this WEEK 2 at the latest)

- [ ] Generate the production Beacon keypair on an OFFLINE host:
      ```
      scripts/beacon-keygen.sh ~/secrets/beacon-priv.pem \
                               website/api/beacon-pub.pem
      ```
- [ ] Record the printed sha256 fingerprint in:
      - GitHub README
      - sostprotocol.com index
      - the BCT release thread
      - the whitepaper appendix
- [ ] Replace `BEACON_PUBKEY_HEX` in `src/beacon.cpp` with the
      uncompressed-point hex the script printed.
- [ ] Replace the placeholder pubkey in `website/js/beacon.js`
      (Phase 1 explorer) with the same hex if not already done.
- [ ] Audit the diff: ONLY the `BEACON_PUBKEY_HEX` lines should change.
      No other code path should be touched in this commit.

### 2. NTP enforcement (do this WEEK 3)

- [ ] Confirm every node and every miner is running an NTP daemon
      (`chronyd`, `systemd-timesyncd`, or equivalent).
- [ ] Broadcast a network notice (signed!) reminding operators of the
      V13 NTP requirement. Suggested body:
      > "V13 activates at block 12 000. Future-timestamp drift cap
      > drops from 60 s to 30 s. Confirm NTP is running and your clock
      > is within ±15 s of UTC. Otherwise your blocks will be rejected
      > from V13_HEIGHT onward."

### 3. Build + deploy (WEEK 4 — ahead of activation)

- [ ] Build the V13 binaries on the canonical build host. `cmake ..` +
      `cmake --build .` should produce sost-node, sost-miner, sost-cli
      and the V13 test binaries with no warnings (modulo the existing
      ignored-return-value warnings).
- [ ] Run the full V13 test suite against the build:
      ```
      ./test-v13-helpers
      ./test-v13-lottery-cooldown-fork
      ./test-v13-drift-fork
      ./test-v13-beacon-phase2a
      ./test-v13-beacon-p2p-scaffold
      ```
      Every suite must report `0 failed`.
- [ ] Roll out the V13 binaries to operators. The activation is a flag
      day at h = 12 000; ALL nodes must run V13 binaries before that
      block lands.

### 4. Activation day (WEEK 5)

- [ ] Watch h ≥ 12 000 closely.
- [ ] Confirm cooldown observed at h = 12 000 spans 6 blocks (look at
      `getlotteryaudit` output: `cooldown_addresses` should reflect
      the previous 6 miners, not 5).
- [ ] Confirm drift rejections only fire for clocks > 30 s ahead.
      Coarse clocks > 30 s but < 60 s ahead should now appear in the
      reject log (whereas pre-V13 they were accepted).
- [ ] If a miner shows up with chronic rejected blocks: contact, fix
      NTP, redeploy.

### 5. Beacon Phase II-A live test (WEEK 6 — first day post-V13)

- [ ] Sign a benign info notice via:
      ```
      scripts/beacon-sign.sh ~/secrets/beacon-priv.pem \
        unsigned.json signed.json
      ```
      with body "V13 Beacon test notice. No action required.".
- [ ] Place `signed.json` as `<datadir>/notices.json` on a single node.
- [ ] Confirm `sost-cli getbeaconnotices` surfaces it with
      `"dormant": false` and the notice in the array.
- [ ] Confirm a connected miner prints the advisory banner on its next
      successful mine.
- [ ] Remove the file. Confirm the next RPC call returns empty.

## Phase III P2P — kept disabled

Phase III (P2P gossip of beacon notices) ships as scaffolding only.
The activation gate `BEACON_P2P_ACTIVATION_HEIGHT` is pinned at
`INT64_MAX` (effectively "never"). All four hard limits are pinned at
build time:

```
BEACON_P2P_NOTICE_MAX_BYTES   = 4 KiB
BEACON_P2P_CACHE_MAX_NOTICES  = 32
BEACON_P2P_PEER_RATE_PER_MIN  = 8
```

The dormant handler `handle_incoming_notice_message()` always returns
`DiscardDormant` and the dormancy short-circuit precedes any parsing
or allocation. The P2P transport does NOT register a Beacon message
type at all.

A future fork plan that wishes to enable Phase III must:

1. Lower `BEACON_P2P_ACTIVATION_HEIGHT` below the chain tip in
   `params.h`. The static_assert in
   `tests/test_v13_beacon_p2p_scaffold.cpp` will fail until that test
   is updated alongside.
2. Implement the eight numbered checks documented inline in
   `src/beacon_p2p.cpp::handle_incoming_notice_message`.
3. Register the P2P message type in the existing peer dispatch.
4. Run a separate adversarial test suite with peers sending
   oversized / malformed / replayed / duplicate / rate-limit-violating
   notices.

V13 explicitly does **NOT** ship any of those four steps.

## Reversal procedure (emergency only)

If a critical bug is discovered after V13 activation, the reversal is
not "fork back to pre-V13" — that is harder than going forward. The
emergency procedure is:

1. Decide which of the three changes is at fault.
2. Land a follow-up fork at a new height (e.g. V13.1) that restores
   the affected helper's value — for example, restoring the lottery
   exclusion window to 5 from h = V13_PATCH_HEIGHT. Both helpers are
   already height-gated; reverting one or all of them is a small diff.
3. Coordinate the V13.1 release with the operator network.

The V13 audit + this spec must be cited in any reversal commit so
future reviewers can see why the original change landed and why it
was reverted.

## File index

| Path                                              | Role                              |
|---------------------------------------------------|-----------------------------------|
| `include/sost/params.h`                           | V13_HEIGHT and helper functions   |
| `include/sost/beacon.h`                           | Phase II-A public API             |
| `include/sost/beacon_p2p.h`                       | Phase III scaffold (DISABLED)     |
| `src/beacon.cpp`                                  | Phase II-A implementation         |
| `src/beacon_p2p.cpp`                              | Phase III dormant implementation  |
| `src/sost-node.cpp`                               | Validator wire-ups, RPC handler   |
| `src/sost-miner.cpp`                              | Miner-side beacon poll + banner   |
| `tests/test_v13_helpers.cpp`                      | Helpers boundary                  |
| `tests/test_v13_lottery_cooldown_fork.cpp`        | Lottery wire-up boundary          |
| `tests/test_v13_drift_fork.cpp`                   | Drift wire-up boundary            |
| `tests/test_v13_beacon_phase2a.cpp`               | Phase II-A end-to-end             |
| `tests/test_v13_beacon_p2p_scaffold.cpp`          | Phase III dormancy pin            |
| `docs/V13_COOLDOWN_AUDIT.md`                      | Cooldown audit + structural reason|
| `docs/beacon.md`                                  | Phase 1 explorer spec             |
| `tools/sim/lottery_cooldown_v13.py`               | Cooldown Monte Carlo              |
| `tools/sim/artefacts/v13_cooldown_50k.json`       | Cooldown audit artefact           |

## Commit chain

The V13 work landed in this order. Every commit is reproducible from
the audit and the test pins; every wire-up commit is bit-identical to
its predecessor for every pre-V13 height.

| # | Hash      | Subject                                                             |
|---|-----------|---------------------------------------------------------------------|
| 1 | (TBD)     | tools: add lottery cooldown Monte Carlo simulator for V13 audit     |
| 2 | (TBD)     | docs(audit): justify cooldown 6 by structural alignment for V13     |
| 3 | (TBD)     | v13: add height-gated fork parameter helpers for block 12000        |
| 4 | (TBD)     | v13: set lottery cooldown to 6 from block 12000                     |
| 5 | (TBD)     | v13: reduce future timestamp drift to 30s from block 12000          |
| 6 | (TBD)     | beacon: phase 2a local signed notices for node and miner warnings   |
| 7 | (TBD)     | beacon: add dormant p2p notice scaffold disabled by default         |
| 8 | (TBD)     | docs: V13 block 12000 specification and operator checklist         |

(Hashes filled in by the merger after squash if applicable.)
