# V13 Beacon Phase II-B — threshold sigs, revocation, mirror metadata

## TL;DR

V13 ships Beacon Phase II-B alongside Phase II-A. It is **advisory-only**:
no Beacon code path touches block validation, mining, rewards, cASERT,
DTD, PoPC, Gold Vault, or the canonical chain. Adding II-B does not
change any consensus rule.

II-B extends the Phase II-A notice schema with four optional fields
that close three operational gaps:

| Field | Purpose | Threat closed |
|---|---|---|
| `threshold` (uint, 0 = legacy) | N-of-M threshold sig requirement | Single stolen key cannot publish a critical notice. |
| `signatures[]` (array of b64 DER) | Multi-signer payload | — (paired with `threshold`) |
| `revokes` (notice_id, "" = none) | Retire a previous notice | Outdated notices linger in the channel. |
| `mirror_url` (string, "" = none) | Metadata pointer to off-chain mirror | None inherently — UI hint only. Never fetched by the node. |

Default deployment: **3-of-5** (`BEACON_THRESHOLD_REQUIRED = 3`,
`BEACON_THRESHOLD_KEY_COUNT = 5`).

Phase II-A single-signature notices (`threshold == 0`) continue to
work bit-identically. Canonical bytes for a pre-II-B notice are
unchanged.

## Hard invariants

1. **Advisory only.** No Beacon code references `block_validation.cpp`,
   `AcceptBlock`, `ValidateSbPoW`, or anything in the canonical-chain
   decision path. A separate test (`test_v13_beacon_phase2b.cpp:t14`)
   pins this by relying on link-time isolation.
2. **Fail-closed defaults.** The hardcoded `BEACON_THRESHOLD_PUBKEYS[]`
   in `src/beacon.cpp:47` is five syntactically-valid curve points owned
   by no one. Every real signature fails until the operator replaces
   them.
3. **Dedup by signer index.** Even with five copies of the same valid
   signature from key 0, the verifier counts key 0 at most **once**.
4. **Revocation requires threshold.** A single-sig (II-A) notice with
   `revokes` set has no revocation power — that policy guards against a
   stolen single key being used to silence threshold-signed advisories.
5. **`mirror_url` never opens a socket.** The node parses it, surfaces
   it via RPC, prints it on banners (Phase 1 explorer / future UI), and
   does nothing else with it.
6. **Notice that fails threshold is silently dropped.** `is_active()`
   returns false; `load_active_notices()` filters it out. The chain
   never branches on the outcome.
7. **`commands` MUST still be empty.** Inherited from II-A. A non-empty
   `commands` array causes the notice to be rejected — Beacon never
   surfaces actionable commands.

## Schema reference

```jsonc
{
  "notice_id":          "v13-iib-2026-05-22-001",
  "network":            "mainnet",
  "severity":           "critical",
  "title_en":           "V13 hard fork imminent",
  "message_en":         "All nodes should upgrade by block 11,999.",
  "activation_height":  12000,
  "expires_height":     13000,
  "created_at":         "2026-05-22T00:00:00Z",
  "commands":           [],
  // ---- Phase II-B fields (all optional) ----
  "threshold":          3,
  "signatures":         ["MEYC...sig1...==", "MEUC...sig2...==", "MEQC...sig3...=="],
  "revokes":            "v13-iib-2026-05-15-007",
  "mirror_url":         "https://sostcore.com/beacon/notices.json"
}
```

For Phase II-A backwards compatibility, omit `threshold`, `signatures`,
`revokes`, `mirror_url`, and use the single `"signature"` field as before.

## Canonical payload — lex-ordered, signatures dropped

II-A (legacy):
```
activation_height, commands, created_at, expires_height,
message_en, network, notice_id, severity, title_en
```

II-B (additive — emitted **only** when at least one II-B field is set):
```
activation_height, commands, created_at, expires_height,
message_en, mirror_url, network, notice_id, revokes,
severity, threshold, title_en
```

The `signature` (singular) and `signatures` (plural) fields are
**never** part of the canonical payload — they sign over the payload,
they are not signed by it.

## Verification algorithm

```cpp
ThresholdVerifyResult verify_threshold_signatures(n, keys, M):
    if n.threshold == 0:      return {ok=false}        # not a II-B notice
    if n.signatures.empty():  return {ok=false}
    if n.threshold > M:       return {ok=false}        # unreachable

    canon = canonical_payload(n)
    digest = SHA256(canon)
    signer_seen[M] = {false, ...}
    distinct = 0
    for sig in n.signatures:
        for i in 0..M-1:
            if signer_seen[i]: continue
            if ecdsa_verify(keys[i], digest, sig):
                signer_seen[i] = true
                distinct += 1
                break
        if distinct >= n.threshold:
            return {ok=true, distinct, required=n.threshold}
    return {ok=(distinct >= n.threshold), distinct, required=n.threshold}
```

## Revocation algorithm

```cpp
load_active_notices(datadir, h, network, single_pubkey):
    # 1. Pre-V13 dormancy gate.
    if h < BEACON_PHASE2A_ACTIVATION_HEIGHT: return []

    # 2. Read + parse notices.json (capped 256 KB).
    all = parse_notices_array(file_bytes)

    # 3. First pass — keep only notices that pass is_active().
    survived = [n for n in all if is_active(n, h, network, single_pubkey)]

    # 4. Collect revocations issued by threshold-signed notices ONLY.
    revoked_ids = {n.revokes for n in survived if n.threshold > 0 and n.revokes != ""}

    # 5. Drop any notice whose id is in revoked_ids. The revoking
    #    notice itself is kept (for audit).
    return [n for n in survived if n.notice_id not in revoked_ids]
```

## Code map

| Layer | File | Symbol |
|---|---|---|
| Schema | `include/sost/beacon.h:48` | `Notice` (extended) |
| Constants | `include/sost/beacon.h:99` | `BEACON_THRESHOLD_REQUIRED = 3`, `BEACON_THRESHOLD_KEY_COUNT = 5` |
| Keys | `src/beacon.cpp:47` | `BEACON_THRESHOLD_PUBKEYS[5]` (placeholder fail-closed) |
| Parser | `src/beacon.cpp:267` | accepts `threshold` / `signatures` / `revokes` / `mirror_url` |
| Canonical payload | `src/beacon.cpp:404` | emits II-B fields only if any II-B field is set |
| Threshold verifier | `src/beacon.cpp:483` | `verify_threshold_signatures()` |
| is_active branch | `src/beacon.cpp:548` | `threshold > 0` → threshold path, else legacy |
| Revocation filter | `src/beacon.cpp:617` | 3-pass: validate → collect revokes → filter |
| RPC surface | `src/beacon.cpp:660` | `serialize_notices_for_rpc()` exposes threshold / revokes / mirror_url |

## Activation

- **Height gate**: shared with II-A — `BEACON_PHASE2A_ACTIVATION_HEIGHT
  = V13_HEIGHT = 12000`. Pre-V13: every Beacon entry point returns
  empty regardless of file contents.
- **No separate II-B activation height**. II-B is the same gate as
  II-A; it is purely an extension of the schema.
- **No header_version bump** (Beacon has no header; this is the V13
  block-validation path's job, which is unrelated).
- **Phase III (P2P) remains DORMANT**. `BEACON_P2P_ACTIVATION_HEIGHT =
  INT64_MAX` per `include/sost/params.h`. Shipping II-B does NOT
  enable P2P.

## Operator key requirements

For II-B to produce useful notices in production, the operator must:

1. Generate **five** ECDSA secp256k1 keypairs offline, ideally on
   air-gapped HSM-class hardware. Use `scripts/beacon-keygen.sh` (run
   five times, save each key as `beacon-key-0..4`).
2. Replace `BEACON_THRESHOLD_PUBKEYS[5]` in `src/beacon.cpp:47` with the
   five 65-byte uncompressed public keys (hex-encoded, 130 chars
   each).
3. Rebuild and re-sign the release binary (`SHA256SUMS` ceremony — same
   discipline as the existing Phase II-A pubkey).
4. Keep the five **private** keys distributed across operators /
   geographic / legal jurisdictions. The whole point of 3-of-5 is no
   single key holder can publish a critical advisory alone.

For test and CI environments, leave the placeholders — they fail
closed by construction, so notices.json files are silently ignored
and the chain is unaffected.

## Test coverage

`tests/test_v13_beacon_phase2b.cpp` — **14 test functions, 33
assertions, all passing**:

| # | Test | What it pins |
|---|---|---|
| 1 | `threshold_3_of_5_pass` | 3 distinct valid sigs → ok=true. |
| 2 | `threshold_under_required` | 2-of-5 → ok=false. |
| 3 | `duplicate_signer_counts_once` | Replayed sig from key 0 not double-counted. |
| 4 | `unknown_signer_ignored` | A sig from an outsider key is dropped. |
| 5 | `malformed_signature_dropped` | Bad base64 / bad DER silently skipped (good sigs still count). |
| 6 | `empty_sigs_rejected` | `threshold > 0` AND `signatures.empty()` → reject. |
| 7 | `threshold_greater_than_keyset_rejected` | `threshold = 6` with 5 keys → reject. |
| 8 | `iia_backwards_compat_end_to_end` | Legacy single-sig notice loads via `load_active_notices`. |
| 9 | `iia_notice_cannot_revoke` | Single-sig notice with `revokes` set cannot retire a victim. |
| 10 | `expired_iib_ignored` | Sigs OK in isolation; `is_active` still rejects on expiry. |
| 11 | `mirror_url_metadata_only` | Field round-trips through `serialize_notices_for_rpc`; no socket. |
| 12 | `canonical_iia_vs_iib_differ` | Canonical bytes differ; II-A bytes byte-stable. |
| 13 | `tampered_threshold_rejected` | Downgrading `threshold` after sign invalidates every sig. |
| 14 | `no_consensus_side_effects` | Compile/link-time invariant: Beacon does not depend on `block_validation`. |

Existing II-A tests continue to pass unmodified (29 assertions).
Trinity: 1861/1861 PASS, 38 skipped (no Python changes in this task).

## Out of scope (deferred to V14)

- **Phase III P2P gossip** — scaffold is in tree and dormant
  (`BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX`). Implementation work
  estimated 2-3 sprints + a P2P gossip primitive precondition.
- **Beacon-driven consensus actions** — explicitly never. Beacon will
  remain advisory in every future phase.
- **Memory-Lock per-instance** — rejected by numerical analysis.
- **PoPC + Gold Vault governance** — see
  `docs/V13_POPC_GOLDVAULT_IMPLEMENTATION_PLAN.md`.

## Risk register

| Risk | Mitigation |
|---|---|
| Operator forgets to replace the 5 placeholder keys before V13 RC. | Placeholders fail-closed: notices simply don't surface. No chain impact. Document the swap as a checklist item in `docs/V13_MINER_OPERATOR_CHECKLIST.md` (next pass). |
| Malicious notices.json drops onto a node and silences real advisories. | Revocation requires threshold; a rogue single-sig notice cannot retire anything. A rogue threshold-signed notice requires compromise of 3 of 5 distributed keys. |
| `mirror_url` social-engineering (operator tricked into clicking a malicious link). | mirror_url is documented as informational only; the node itself never fetches it. UI consumers are responsible for their own URL handling. |
| Future schema bump breaks canonical_payload byte stability for II-A signers. | The current implementation emits II-B fields ONLY when at least one is set. Any future extension MUST preserve this rule (test 12 catches violations). |
