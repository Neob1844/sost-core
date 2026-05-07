# SOST Beacon

Signed network-notice channel. Multiple phases share a single notice
schema and a single signing pubkey; each phase adds a new surface where
notices appear. Phases ship one at a time so each new surface can be
audited in isolation.

| Phase    | Surface                            | Status                  | Activation             |
|----------|------------------------------------|-------------------------|------------------------|
| 1        | Browser explorer banner            | LIVE                    | (always-on, browser)   |
| **II-A** | C++ node RPC + miner advisory      | **LIVE from V13_HEIGHT**| `BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT = 12 000` |
| III      | P2P gossip across nodes            | DISABLED scaffold       | `BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX` (sentinel)    |

The Phase II-A operator runbook lives in `docs/V13_SPEC.md`. Phase III
remains gated until a separate, explicit fork plan lowers
`BEACON_P2P_ACTIVATION_HEIGHT`.

## Hard rule (every phase)

```
Beacon puede informar.
Beacon no puede reiniciar.
Beacon no puede bloquear.
Beacon no puede cambiar consensus.
Beacon no puede cambiar mining.
Beacon no puede ejecutar comandos (`commands` MUST be []).
```

Any future phase that wants to do more must amend this document and ship
under a new explicit fork plan.

## Trust model

A single **operator pubkey** signs every notice. The pubkey is hardcoded
in **two** places that must stay in sync:

  1. `website/js/beacon.js` (`BEACON_PUBKEY_HEX`) — the explorer Phase 1 path.
  2. `src/beacon.cpp` (`BEACON_PUBKEY_HEX`) — the node Phase II-A path.

Neither is read from a file at runtime. To roll the key, both files are
edited in the same PR, audited, redeployed (explorer redeploy + node
binary roll). The shipped values in both files are placeholders that
fail-close; the operator replaces them after running
`scripts/beacon-keygen.sh` on an offline host.

Cross-channel publication of the public key fingerprint is mandatory. At
minimum it MUST appear in:

- this file (`docs/beacon.md`)
- the public website index (`sostprotocol.com`)
- the BCT announcement thread
- a tagged GitHub release note

A fingerprint mismatch in any one of these channels MUST be treated as a
compromise warning — verify before trusting any banner.

The fingerprint is `sha256(uncompressed pubkey hex)`. Both values are
printed by `scripts/beacon-keygen.sh`.

## Notice schema (shared by Phase 1 and Phase II-A)

```json
{
  "notice_id": "v12-postfork-audit-001",
  "network": "mainnet",
  "severity": "info",
  "title_en": "SOST network notice",
  "message_en": "Explorer display audit completed. No funds lost.",
  "activation_height": 7500,
  "expires_height": 7900,
  "created_at": "2026-05-07T00:00:00Z",
  "commands": [],
  "signature": "<base64 ECDSA-SHA256 over secp256k1>"
}
```

Required fields (all of them):

| Field | Type | Notes |
|---|---|---|
| `notice_id` | string | unique, human-meaningful slug |
| `network` | string | `mainnet` or `testnet` |
| `severity` | string | `info` / `warn` / `critical` |
| `title_en` | string | one short line |
| `message_en` | string | one paragraph max — banners are not blog posts |
| `activation_height` | integer | banner appears at tip ≥ this height |
| `expires_height` | integer | banner stops appearing at tip ≥ this height |
| `created_at` | string | ISO-8601 UTC, informational |
| `commands` | array | MUST be `[]` (reserved; no Phase implemented so far acts on it; non-empty `commands` causes Phase II-A to reject the notice at the schema layer) |
| `signature` | string | base64 of DER-encoded ECDSA-SHA256 of canonical payload |

## Canonical payload

`canonical_payload = jq -cSj 'del(.signature)' <unsigned.json>`

- `-c` compact, `-S` recursive key sort, `-j` no trailing newline.
- The browser reproduces this byte-for-byte via `canonicalize()` in
  `website/js/beacon.js`.
- The signature is `base64(ECDSA-SHA256(canonical_payload))` over secp256k1.
- DER encoding is what `openssl dgst -sign` emits; the browser parses DER
  to compact (r||s) before calling `noble.verify`.

## Pipelines

### Sign (operator only)

```bash
scripts/beacon-keygen.sh ~/secrets/beacon-priv.pem website/api/beacon-pub.pem
# (one-time, store priv key OFFLINE; record fingerprint in all channels)

scripts/beacon-sign.sh ~/secrets/beacon-priv.pem unsigned.json signed.json
# atomically signs with ECDSA-SHA256 over canonical payload
```

### Shell-side verification (CI / sanity checks)

```bash
scripts/beacon-verify.sh website/api/beacon-pub.pem signed.json
# exits 0 if the signature verifies, 1 otherwise
```

### Browser-side verification (Phase 1 — production path)

`website/js/beacon.js` is loaded as `<script type="module">` at the very
end of `<body>` in `website/sost-explorer.html`. It:

1. Fetches `/api/notices.json` (same origin, 5 s timeout, 256 KB cap).
2. Validates schema, drops malformed entries.
3. Reproduces canonical payload via `canonicalize()`.
4. Verifies ECDSA-SHA256 with the vendored `noble-secp256k1` against
   `BEACON_PUBKEY_HEX`.
5. Filters notices by `[activation_height, expires_height)` against the
   tip height (best-effort; if tip unknown, the height filter is skipped).
6. Renders a banner only for notices that pass every check above.

Any failure mode at any step ⇒ no banner. Beacon never throws to the page.

### Node-side verification (Phase II-A — production path)

`src/beacon.cpp` exposes `sost::beacon::load_active_notices(...)` which:

1. Reads `<datadir>/notices.json` (no HTTP, 256 KB cap).
2. Validates schema, drops malformed entries.
3. Reproduces canonical payload via `canonical_payload()` — byte-identical
   to the explorer's `canonicalize()`.
4. Verifies ECDSA-SHA256 with libsecp256k1 against the same
   `BEACON_PUBKEY_HEX` (mirrored in `src/beacon.cpp`). lowS is
   normalised, not enforced — openssl produces both forms.
5. Filters by `[activation_height, expires_height)` against the
   chain tip and by network match against the active profile.
6. Returns the surviving notices to `getbeaconnotices` RPC; the miner
   polls and prints an advisory banner per unique `notice_id`.

Pre-V13_HEIGHT the entire path returns empty regardless of file
contents (Phase II-A dormancy gate). Any failure mode ⇒ empty result.
Beacon never throws to a node or miner caller.

## Vendor integrity

```
website/vendor/
  noble-secp256k1-2.2.3.js   # 27 KB, hash-pinned
  HASHES.txt                 # sha256sum -c manifest
  README.md                  # vendoring policy
```

`scripts/beacon-vendor-fetch.sh` downloads from a fixed upstream URL and
refuses to write the file unless the SHA-256 matches the pin. Bumping the
vendored version requires editing the script's pinned `EXPECTED_HASH`
explicitly; silent bumps are impossible by construction.

CI MUST run, in this order:

```bash
( cd website/vendor && sha256sum -c HASHES.txt )
tests/beacon_verify_test.sh
tests/beacon_cross_verify_test.sh
```

## Tests

| Script | Coverage |
|---|---|
| `tests/beacon_verify_test.sh` | shell-only adversarial cases (7) — fabricated, missing, attacker-signed, tampered, malformed JSON, re-sign refusal |
| `tests/beacon_cross_verify_test.sh` | shell signs → browser JS verifies the same artefact (7) — proves the sign and verify halves cannot diverge |

The cross-fixture suite is the load-bearing test. If shell sign and JS
verify ever drift apart (canonical-payload mismatch, signature encoding
change, hash function change), this test fails first.

## Key rotation

1. Generate the new key on an offline machine with `beacon-keygen.sh`.
2. Publish the new fingerprint on every channel listed in *Trust model*
   (note that the OLD key is being rotated out).
3. Open a PR that changes only `BEACON_PUBKEY_HEX` in
   `website/js/beacon.js`.
4. Have the PR reviewed by a second operator who independently fetches
   the fingerprint from at least two of the public channels.
5. Merge and redeploy. Drop the old `priv.pem` from operator hardware.

The old key remains valid for any cached `notices.json` until the next
explorer refresh; this is acceptable for an informational banner.

## Out of scope (deferred)

- Mandatory client-side action on a notice (`commands`) — must stay `[]`
  in every phase shipped so far.
- Multi-signer (k-of-n) — current phases are single-signer.
- P2P gossip — Phase III scaffold ships in V13 but is **DISABLED** by
  the `INT64_MAX` activation gate. Enabling requires a separate fork.
- i18n beyond `_en` fields — banners are English-only.
