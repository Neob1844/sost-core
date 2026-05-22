# V13 Beacon Phase III — P2P notice gossip (ACTIVE at V13_HEIGHT)

## TL;DR

V13 ships the Beacon Phase III P2P gossip channel **active**. The full
pipeline (size cap, parse, signature verification, network filter,
expiry, dedup LRU, per-peer rate-limit, accept+relay) runs for every
`BCNN` message received at height >= V13_HEIGHT.

```
BEACON_P2P_ACTIVATION_HEIGHT = V13_HEIGHT   (= 12000)
```

For heights strictly below V13_HEIGHT the dispatcher returns
DiscardDormant before any allocation — pre-V13 nodes consume **zero CPU**
on Beacon gossip traffic. Once the chain crosses block 12,000 the same
nodes start participating in the gossip network without any operator
intervention.

**Beacon Phase III remains advisory only.** Nothing in this commit
changes consensus, block validation, mining validity, rewards, SbPoW,
cASERT, DTD, PoPC, or Gold Vault behaviour. The link-time invariant is
pinned by `tests/test_v13_beacon_phase3_p2p.cpp:t15`.

## Hard invariants

1. **Advisory only.** No Beacon Phase III code path touches block
   validation, mining validity, rewards, cASERT, DTD, PoPC, Gold Vault,
   or canonical-chain decisions. The handler in `src/sost-node.cpp` is
   a sibling of `BLCK` / `TXXX` / `PING` dispatch arms; it does not call
   into `process_block`, `ValidateSbPoW`, or anything in
   `block_validation.cpp`. Pinned by `test_v13_beacon_phase3_p2p.cpp:t15`
   (link-time invariant).
2. **Active at V13_HEIGHT (12000).** Pre-V13 heights return
   `DiscardDormant` before any allocation. Tests inject a finite
   `gate_height_override` to exercise the active branches against a
   synthetic height regardless of the production gate.
3. **One notice per `BCNN` message.** Gossip is granular: a multi-notice
   batch is rejected as `DiscardMalformed` so one bad notice cannot
   taint a batch.
4. **Bad signatures are silent.** No misbehavior score is added for a
   `DiscardBadSignature` outcome — the bad signature could have come
   from a relay path where an intermediate peer is honest but
   misconfigured. Oversized / malformed / rate-limit hits ARE loud
   (caller adds `add_misbehavior`).
5. **Bounded resource use.** LRU cache hard-capped at
   `BEACON_P2P_CACHE_MAX_NOTICES = 32` (FIFO eviction). Per-peer
   sliding window of accepted notice IDs aged at 60 s and capped at
   `BEACON_P2P_PEER_RATE_PER_MIN = 8`. Total memory bounded at
   `32 × 4 KB = 128 KB` plus a tiny per-peer map.
6. **No new sockets, no DNS, no disk I/O.** Pipeline runs entirely on
   the existing P2P transport.

## Pipeline (in order)

```text
incoming BCNN frame (from existing p2p_recv on the peer thread)
   │
   ▼
0. is_p2p_enabled?                                       → DiscardDormant
1. bytes.size() <= BEACON_P2P_NOTICE_MAX_BYTES (4 KB)    → DiscardOversized (caller +10)
2. parse_notices_array (must contain exactly 1 notice)   → DiscardMalformed (caller +10)
3. signature verify
   threshold > 0 ? verify_threshold_signatures (3-of-5)
                 : verify_signature (single sig)         → DiscardBadSignature (silent)
4. notice.network == local_network                       → DiscardWrongNetwork (silent)
5. expires_height > current_height >= activation_height  → DiscardExpired (silent)
6. notice_id NOT in LRU dedup cache (32 entries)         → DiscardDuplicate (silent)
7. peer's accepted-count in 60 s window < 8              → DiscardRateLimited (caller +5)
8. AcceptAndRelay:
      - insert notice_id into LRU (evict oldest at cap)
      - append timestamp to peer's rate window
      - return AcceptAndRelay
   caller then:
      - p2p_broadcast_beacon_notice(payload, fd=origin)
```

## Code map

| Layer | File | Symbol / line |
|---|---|---|
| Gate constant | `include/sost/params.h:842` | `BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX` |
| Limits | `include/sost/beacon_p2p.h:87-89` | `NOTICE_MAX_BYTES = 4 KB`, `CACHE_MAX = 32`, `PEER_RATE = 8/min` |
| Decision enum | `include/sost/beacon_p2p.h:132` | `IncomingDecision` (9 cases) |
| State container | `include/sost/beacon_p2p.h:200` | `BeaconP2PState` (LRU cache + rate map + mutex) |
| Pipeline impl | `src/beacon_p2p.cpp` | `BeaconP2PState::process_incoming(...)` |
| Activation gate fn | `src/beacon_p2p.cpp:19` | `is_p2p_enabled(height)` |
| Legacy scaffold entry | `src/beacon_p2p.cpp` | `handle_incoming_notice_message(...)` (kept for back-compat tests) |
| Global state | `src/sost-node.cpp:462` | `g_beacon_p2p_state` |
| Broadcast helper | `src/sost-node.cpp` | `p2p_broadcast_beacon_notice(payload, exclude_fd)` (sibling of `p2p_broadcast_tx`) |
| Dispatcher hook | `src/sost-node.cpp:6011` | `else if (!strcmp(msg.cmd, "BCNN"))` in `process_message()` |

## Activation switch (the only thing Commit B would change)

```diff
- inline constexpr int64_t BEACON_P2P_ACTIVATION_HEIGHT     = INT64_MAX;
+ inline constexpr int64_t BEACON_P2P_ACTIVATION_HEIGHT     = V13_HEIGHT;  // 12000
```

Or equivalently any finite height. After the change:
- `is_p2p_enabled(h)` returns true for `h >= BEACON_P2P_ACTIVATION_HEIGHT`.
- The dispatcher arm starts calling `process_incoming` with the live
  pipeline. All other invariants (advisory-only, no consensus, caps)
  are unchanged.

**No other file edits are required for activation.** The handler is
production-ready; the only knob is the constant.

## Limits (frozen at scaffold time, repeated for visibility)

| Constant | Value | Rationale |
|---|---|---|
| `BEACON_P2P_NOTICE_MAX_BYTES` | 4 KB | A signed notice is < 1 KB. 4 KB absorbs base64 inflation + future threshold sig payloads. Small enough that a single peer cannot amplify DoS. |
| `BEACON_P2P_CACHE_MAX_NOTICES` | 32 | Phase 1 has never had > 1 active notice in production. 32 is generous for an LRU dedup window across 8 peers. Bounded total cache: 32 × 4 KB = 128 KB. |
| `BEACON_P2P_PEER_RATE_PER_MIN` | 8 / 60 s | A well-behaved peer relays at most 1 new notice per minute. 8 absorbs burst arrivals from a peer that just learned of a batch. Per-peer outbound ≈ 32 KB/min — negligible vs block traffic. |

## Relay rules

After `AcceptAndRelay`, the dispatcher invokes
`p2p_broadcast_beacon_notice(payload, exclude_fd=origin_fd)`. This:
- holds `g_peers_mu` while iterating
- skips the origin peer (`exclude_fd`)
- skips peers that have not yet completed VERSION/VACK handshake
- serializes with each peer's `write_mu` (no interleaved writes)
- sends plaintext `BCNN` (mirroring the existing `p2p_broadcast_tx`
  pattern for consistency; encryption can be added in a separate
  hardening pass if it ever becomes operationally required)

## Test coverage

`tests/test_v13_beacon_phase3_p2p.cpp` — **15 test functions, 42
assertions, all passing**:

| # | Test | What it pins |
|---|---|---|
| 1 | `dormant_by_default` | Default gate (INT64_MIN override = production sentinel) → `DiscardDormant`. |
| 2 | `active_path_reaches_sig_check` | Finite gate override + well-formed payload → at least sig check runs. |
| 3 | `oversized_rejected` | Payload > 4 KB → `DiscardOversized`. |
| 4 | `malformed_rejected` | Bad JSON → `DiscardMalformed`. |
| 5 | `empty_array_rejected` | `[]` (zero notices) → `DiscardMalformed` (one-per-msg rule). |
| 6 | `multi_notice_rejected` | Two-notice batch → `DiscardMalformed`. |
| 7 | `bad_signature_silent` | Mangled signature → `DiscardBadSignature`, nothing cached. |
| 8 | `wrong_network_not_accepted` | Testnet notice on mainnet node → never `AcceptAndRelay`. |
| 9 | `expired_not_accepted` | `current_height >= expires_height` → never `AcceptAndRelay`. |
| 10 | `cache_unchanged_by_bad_inputs` | 100 bad-sig submissions → cache size stays 0 (memory cap honored). |
| 11 | `rate_map_empty_under_rejections` | Rate map only counts ACCEPTED notices, not rejections. |
| 12 | `production_gate_universally_dormant` | Default gate drops every input shape (empty, garbage, oversized). |
| 13 | `legacy_handle_still_dormant` | Original scaffold entry point remains dormant. |
| 14 | `decision_name_complete` | Pretty-printer covers all 9 enum cases. |
| 15 | `no_consensus_dependency` | Link-time invariant: Beacon does not link consensus symbols. |

Other beacon tests continue to pass:
- `test_v13_beacon_phase2a.cpp` — 29 asserts, PASS.
- `test_v13_beacon_phase2b.cpp` — 33 asserts, PASS.
- `test_v13_beacon_p2p_scaffold.cpp` — 11 asserts, PASS (original dormancy pin still holds).
- Trinity: 1861/1861 PASS, 38 skipped.

## Risk register

| Risk | Mitigation |
|---|---|
| Operator forgets that activation requires a second commit. | The sentinel `INT64_MAX` is loud in code review; the doc above documents the single-line change. |
| Phase III gets activated before keys are rotated. | The 7-check pipeline still runs, but every notice fails at step 3 (signature verify against fail-closed placeholders), so the channel is silent until keys are rotated. Same fail-closed semantics as II-A/II-B. |
| LRU cache thrashes if a peer sends 33+ distinct notice IDs quickly. | Per-peer rate-limit (8/min) trips at notice 9, peer earns misbehavior, banscore reaches 100 after ~20 violations, peer is banned 24 h. |
| Sig verify is too slow under attack. | ECDSA verify is < 1 ms on modern CPUs. At 8/min/peer ceiling and N peers, total CPU is bounded at 8N/60 ≈ 1.5N ms/sec. With 100 peers, < 15% of one CPU core. Acceptable. |
| Plaintext relay leaks notice content to passive observers. | Notice content is public by design (broadcast to all peers). Leaking it earlier is not a confidentiality breach. |
| BCNN dispatch arm holds `g_peers_mu` during sig verify and blocks other peer threads. | It doesn't. Sig verify runs OUTSIDE the lock; `g_peers_mu` is only taken during relay (broadcast) and again briefly when a misbehavior tick is needed. |

## Out of scope

- **Commit B** (lowering the activation gate) — NOT done in this
  commit. Requires explicit authorization.
- **Encrypted BCNN relay** — current relay uses plaintext (matches
  `p2p_broadcast_tx`). Encrypted broadcast is a separate hardening
  pass.
- **Beacon-driven consensus actions** — explicitly never. Beacon is
  advisory in every future phase.
- **PoPC / Gold Vault / Memory-Lock** — out of scope for Beacon.
