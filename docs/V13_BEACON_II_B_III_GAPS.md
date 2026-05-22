# V13 Beacon Phase II-A / II-B / III Gap Analysis

**Target:** V13 at block **12,000**.
**Fallback:** V14 at block **15,000** if any of II-B or III is not ready by the V13 RC freeze.
**Scope:** what is the current state of Beacon Phase II-A (already targeted for V13), and what is required to also ship Phase II-B and Phase III in the V13 fork?

**Bottom line (updated 2026-05-23 — Beacon stack is now fully implemented for V13):**
- **Phase II-A**: **complete and gated at V13_HEIGHT (12,000)**. Notice loader, ECDSA-SHA256 signature verification, miner banner, RPC handler, and the original 11-test suite remain in place. Operator action before V13 RC: replace the placeholder pubkey constant with the real release pubkey.
- **Phase II-B**: **implemented and gated at V13_HEIGHT (12,000)**. The `Notice` schema gained `threshold`, `signatures[]`, `revokes`, and `mirror_url` (metadata only). Verification is N-of-M (default 3-of-5 against `BEACON_THRESHOLD_PUBKEYS[5]`) with signer-index dedup; revocation requires a threshold-signed notice; `mirror_url` is never fetched. 33 II-B regression assertions pass. Operator action before V13 RC: replace the five placeholder threshold pubkeys with the real release set generated offline.
- **Phase III**: **active at V13_HEIGHT (12,000)** as of the Commit B activation. `BEACON_P2P_ACTIVATION_HEIGHT` was `INT64_MAX` (DiscardDormant sentinel) and is now `V13_HEIGHT`. The full pipeline runs at and above the gate: size cap 4 KB → parse → sig verify (threshold-aware) → network match → expiry → dedup LRU 32 → per-peer rate limit 8/min → accept + plaintext relay to all version-acked peers except origin. 42 Phase III regression assertions pass. Hard limits and link-time advisory-only invariant preserved. Pre-V13 height: dormant.

Sections below retain the original audit text for historical context. Where they reference dormancy / `INT64_MAX` / "missing implementation", read those as the situation BEFORE the Commit A + Commit B work; the bottom-line above is the live status.

This doc maps each phase with `file:line` evidence and confirms what is missing for V13 activation.

This doc does **NOT** implement anything. It only audits.

---

## Hard Beacon invariants (apply to all three phases)

These five rules are the durable contract — any phase that breaks them is out of scope:

1. **MAY inform an operator.**
2. **MAY NOT restart a node or miner.**
3. **MAY NOT block any block or transaction.**
4. **MAY NOT change consensus rules.**
5. **MAY NOT execute commands on the host.**

Phase II-A enforces #5 by requiring the `commands` field of every notice to be empty:
- `tests/test_v13_beacon_phase2a.cpp:345-364` — `test_commands_must_be_empty` enforces the empty `commands` array as a Phase II-A invariant.
- `include/sost/beacon.h:3-20` — comment block documents the invariants.

Phase II-B and Phase III MUST inherit these five invariants without weakening.

---

## Phase II-A status (V13 confirmed)

**Status:** **GREEN — COMPLETE, ONE OPERATOR ACTION PENDING**.

### Activation gate

- `include/sost/params.h:828` — `inline constexpr int64_t BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT;` (= 12,000)

### Notice loader

- `src/beacon.cpp:443` — `load_active_notices()` — reads `<datadir>/notices.json`, no file-watch, polled at startup and on each RPC request.
- `src/beacon.cpp:450-453` — file path construction (`datadir + "/notices.json"`).

### Notice schema (10 mandatory fields)

- `include/sost/beacon.h:48-60` — `struct Notice { notice_id, network_str, network, severity, title_en, message_en, activation_height, expires_height, created_at, commands, signature_b64 }`.

### Signature verification

- `src/beacon.cpp:370` — `verify_signature()` — **ECDSA-SHA256 via secp256k1**, NOT Schnorr. This is a documented mismatch with the whitepaper appendix text. The implementation is consensus-correct (the verifier is deterministic and key-bound); the appendix wording should be reconciled in a docs-only update.
- `src/beacon.cpp:376-405` — full verify path: hex-decode pubkey, base64-decode DER signature, lowS normalisation, SHA-256 over canonical payload, `secp256k1_ecdsa_verify`.

### Hardcoded pubkey (PLACEHOLDER — operator action required)

- `src/beacon.cpp:29-32` — `BEACON_PUBKEY_HEX = "04" + 64 zeros + "b7c52588..."` — a deterministic fail-closed placeholder.

The placeholder REJECTS all real signatures (no key is derivable from it that the operator controls). For V13 RC to be operational, the operator MUST:

1. Run `scripts/beacon-keygen.sh` offline on the secure host that holds the release-key family (separate from any wallet, mining, or SOST release-signing key).
2. Replace `BEACON_PUBKEY_HEX` in `src/beacon.cpp` with the generated pubkey.
3. Replace the placeholder in `website/js/beacon.js:32-35` with the same pubkey so the explorer can verify notices client-side.
4. Publish the pubkey publicly (BitcoinTalk thread + `website/api/beacon-pub.pem` next to the announcement).

This is **operator-manual** and outside the agent's safety surface (key generation), but it is a small one-time step.

### Miner banner

- `src/sost-miner.cpp:2519-2527` — `fprintf(stderr, "\n*****…\n* BEACON [%s] %s\n…\n* (advisory only — does not affect mining)\n…\n", sev_upper, tit, nid, msg);`
- `src/sost-miner.cpp:2480` — `g_seen_beacon_ids` set ensures each notice is printed only once per miner process.

### Tests

- `tests/test_v13_beacon_phase2a.cpp:230-249` — `test_happy_path` (parse valid notice).
- `tests/test_v13_beacon_phase2a.cpp:254-271` — `test_bad_signature` (reject bad sig).
- `tests/test_v13_beacon_phase2a.cpp:345-364` — `test_commands_must_be_empty` (Phase II-A invariant #5).
- 11 Phase II-A tests total, all passing on the current main.

### Network surface

Confirmed **zero HTTP / curl / urlopen** in C++ Beacon code. Phase II-A is strictly file-local. The explorer client-side fetch (`website/js/beacon.js`) is browser-only and out of consensus scope.

---

## Phase II-B status (target V13, fallback V14)

**Status:** **AMBER — TWO FEATURES PARTIAL, THREE MISSING**.

| Capability | Status | Evidence |
|---|---|---|
| Expiration by absolute height | **GREEN** (already in II-A) | `src/beacon.cpp:415` — `if (n.expires_height <= current_height) return false;` |
| Severity levels (info / warn / critical) | **GREEN** (already in II-A) | `src/beacon.cpp:224` — parsed; line 480-481 — output; miner banner shows severity |
| N-of-M threshold signatures on critical notices | **RED — MISSING** | No `threshold`, `signers`, `signatures[]` fields in `struct Notice`. No multisig verify path. |
| Second publication channel (mirror) | **RED — MISSING** | No `mirror_url` field. No fallback fetch path. (Phase II-A is file-local anyway; the mirror lives client-side.) |
| Optional revocation | **RED — MISSING** | No `revocation_id` field. No "silently retire by `notice_id` match" path. |

**What V13 needs for II-B:**

- Extend `struct Notice` (`include/sost/beacon.h:48-60`) with three new optional fields: `threshold` (uint8), `signatures` (vector\<string\>), `revokes` (string, optional notice_id).
- Extend `src/beacon.cpp:370` `verify_signature()` to a multi-sig path: if `signatures` is non-empty AND `threshold > 0`, verify each signature against a hardcoded pubkey set (M keys), require at least `threshold` of them to verify.
- Add a hardcoded pubkey-set constant (e.g. `BEACON_THRESHOLD_PUBKEYS[]`) alongside `BEACON_PUBKEY_HEX`. The M keys MUST be operator-generated offline, on different secure hosts.
- Add revocation logic: when a verified notice has `revokes = <existing_notice_id>`, the validator removes the named notice from the active set, silently, no restart.
- Backwards compatibility: a Phase II-A node that does not understand these fields MUST ignore them and continue to verify the single-key signature path. The whitepaper appendix already promises this; the implementation must honour it.

**Operator-manual prerequisite:** the M independent keys for the threshold (e.g. 3-of-5) must be generated on the secure host(s) and the M pubkeys committed to source. The keys themselves never enter the repo.

**V13 RC realistic estimate for II-B:** 1-2 sprints if the operator can produce the threshold keys promptly.

---

## Phase III status (target V13, fallback V14)

**Status:** **AMBER — SCAFFOLD DORMANT, IMPLEMENTATION MISSING**.

### Activation gate

- `include/sost/params.h:829` — `inline constexpr int64_t BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX;` — currently sentinel-disabled.

### Scaffold structure (in tree, dormant)

- `include/sost/beacon_p2p.h` — full interface declared.
- `include/sost/beacon_p2p.h:87-89` — three hard limits pinned:

  ```cpp
  inline constexpr size_t BEACON_P2P_NOTICE_MAX_BYTES   = 4 * 1024;   // 4 KB max
  inline constexpr size_t BEACON_P2P_CACHE_MAX_NOTICES  = 32;         // LRU cache
  inline constexpr int    BEACON_P2P_PEER_RATE_PER_MIN  = 8;          // rate limit
  ```

- `include/sost/beacon_p2p.h:132-142` — `Decision` enum: `DiscardDormant`, `DiscardOversized`, `DiscardMalformed`, `DiscardBadSignature`, `DiscardExpired`, `DiscardWrongNetwork`, `DiscardDuplicate`, `DiscardRateLimited`, `AcceptAndRelay`.
- `include/sost/beacon_p2p.h:166-168` — handler signature: `IncomingDecision handle_incoming_notice_message(const std::string& bytes, int64_t current_height);`
- `src/beacon_p2p.cpp:51-54` — handler always returns `DiscardDormant` today (sentinel-gated).
- `src/beacon_p2p.cpp:56-76` — comment block documents the expected Phase III order: size cap → parse → signature → network match → expiration → dedup → rate-limit → accept.

### What is missing for Phase III

- **Size cap check** (`BEACON_P2P_NOTICE_MAX_BYTES`): MISSING. The handler must reject any message > 4 KB before parsing.
- **Parse step**: MISSING. The handler must call `beacon::parse_notices_array()` and discard on parse failure.
- **Signature verify before relay**: MISSING. Verification must run BEFORE the notice is relayed to peers — never relay an unverified blob.
- **Network match**: MISSING. Reject notices targeting a different network than the local node.
- **Expiration**: MISSING. Reject already-expired notices.
- **Dedup ring buffer**: MISSING. Maintain a 32-entry LRU of seen `notice_id`s; second instance is discarded.
- **Per-peer rate limit**: MISSING. Enforce ≤ 8 notices per peer per minute; over-rate notices are discarded silently (no peer-ban, no scoring — anti-DoS without amplification).
- **Message-type registration in P2P transport**: MISSING. Independently of Beacon, there is no general gossip framework in the current `src/` to plug a new message type into. Phase III therefore requires the underlying P2P transport to be available first.

### Tests

- `tests/test_v13_beacon_p2p_scaffold.cpp:29-40` — `static_assert`s pin the dormancy invariants (BEACON_P2P_ACTIVATION_HEIGHT must equal INT64_MAX, decision must default to DiscardDormant).
- `tests/test_v13_beacon_p2p_scaffold.cpp:45-62` — confirms the gate always returns `false`.
- `tests/test_v13_beacon_p2p_scaffold.cpp:69-92` — confirms the handler always returns `DiscardDormant`.

When Phase III lights up, the tests in `test_v13_beacon_p2p_scaffold.cpp` will need to flip from "must be dormant" to "must enforce each check in the comment block". That is a binary cutover at the activation height.

### What V13 needs for Phase III

- Lower `BEACON_P2P_ACTIVATION_HEIGHT` from `INT64_MAX` to `12,000` (or another V13 height).
- Implement all 7 steps in the comment block at `src/beacon_p2p.cpp:56-76`.
- Register the Beacon notice message type in the underlying P2P transport (PRECONDITION: confirm a general gossip primitive exists or build a minimal one for this single message type).
- Cross-implementation interop test: at least two independently-built binaries gossip a verified notice, both deduplicate correctly, neither relays a bad-signature notice.
- Memory-bounded test: feed 1000 distinct notices into a single node and prove memory does not grow beyond `BEACON_P2P_CACHE_MAX_NOTICES * BEACON_P2P_NOTICE_MAX_BYTES` (32 * 4 KB = 128 KB upper bound).

**V13 RC realistic estimate for Phase III:** 2-3 sprints, AND a precondition that the underlying P2P transport has a gossip primitive. If the underlying P2P transport does not exist yet, Phase III defers to V14 / block **15,000** cleanly.

---

## Documentation

- `docs/V13_SPEC.md` (line 1-2: V13 hard fork specification, lines 92-242: Beacon Phase II-A integration).
- **MISSING:** a standalone `docs/V13_BEACON_PHASE2_PHASE3.md` that pins the II-B and Phase III scope. The current spec covers II-A only.

The hardcoded Beacon pubkey is NOT yet published. Today `website/js/beacon.js:27` notes "Replace with the real operator pubkey produced by `scripts/beacon-keygen.sh`". For the V13 RC, the published pubkey must be at:

- A constant in `src/beacon.cpp:29-32` (the C++ verifier)
- A matching constant in `website/js/beacon.js:32-35` (the explorer client-side verifier)
- A canonical pubkey file at `website/api/beacon-pub.pem` (so users can fetch it offline)

---

## Phase status summary

| Phase | Status | V13 risk |
|---|---|---|
| Phase II-A | **GREEN** | None — already gated at V13_HEIGHT; one operator-manual key step pending |
| Phase II-B | **AMBER** | Two features done (expires, severity), three missing (threshold, mirror, revocation) — 1-2 sprints to close |
| Phase III  | **AMBER** | Scaffold dormant, 7 steps to implement, requires a P2P gossip primitive — 2-3 sprints to close |

**Recommendation:**

- **Phase II-A** ships in V13 unconditionally. The placeholder pubkey replacement is a release-day operator step (same release-key ceremony used to sign `SHA256SUMS`).
- **Phase II-B** is realistic for V13 if the operator can produce the M threshold keys offline before the V13 RC freeze. If keys cannot be produced in time, defer to V14 / block 15,000 cleanly.
- **Phase III** is more aggressive. Defer to V14 / block 15,000 by default unless the underlying P2P gossip primitive is already present and Phase III becomes a thin layer on top of it. The auto-disconnect-equivalent for Phase III is just leaving `BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX` — no risk to V13 if Phase III is not ready.

Memory-Lock per-instance anti-pool is **DEFERRED** from V13 — not in scope here.

The DTD flip at block 12,100 is **already verified** (`docs/V13_DTD_FLIP_12100_AUTOMATIC.md`, tag `v13-dtd-flip-12100-verification-v01`) and is independent of the Beacon phases.

— NeoB
