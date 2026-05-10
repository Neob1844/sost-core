# Trinity Proof Bundle v0

Branch: `trinity/proof-bundle-v0` (cut from `trinity/campaign-engine-v0`).
Date: 2026-05-10.

The Proof Bundle is the **single root artefact** of Trinity. Where Sprint 3 produced three reproducible files (dossier, plan, campaign) anchored independently, Sprint 4 binds all four base SHAs into one document with a Merkle root and a `proof_bundle_sha256` over its canonical bytes. From here on, the operator registers ONE thing on chain — the Proof Bundle — and any third party can verify the whole chain from that one anchor.

---

## 1. What the bundle contains

```json
{
  "schema": "trinity-proof-bundle/v0",
  "bundle_name": "<short id>",
  "aoi": "<AOI>",
  "generated_at_utc": "<pin-able ISO-8601>",
  "anchors": {
    "scorecard_sha256":            "<64-hex>",
    "dossier_sha256":              "<64-hex>",
    "useful_compute_plan_sha256":  "<64-hex>",
    "campaign_sha256":             "<64-hex>"
  },
  "anchor_basenames": {
    "dossier":              "TRINITY_DEMO_DOSSIER_<aoi>.json",
    "useful_compute_plan":  "TRINITY_USEFUL_COMPUTE_PLAN_<aoi>.json",
    "campaign":             "TRINITY_CAMPAIGN_<name>.json",
    "scorecard":            "<external; sha256 only>"
  },
  "merkle": {
    "algorithm": "<documented string>",
    "leaf_order": ["scorecard_sha256", "dossier_sha256",
                   "useful_compute_plan_sha256", "campaign_sha256"],
    "root": "<64-hex>"
  },
  "safety_status": {
    "dry_run": true, "registered": false, "ready_to_register": true,
    "no_rewards_active": true, "no_public_publication": true,
    "no_chain_broadcast": true, "no_consensus_modification": true,
    "no_wallet_action": true
  },
  "capsule_preview": {
    "open_note_template": "trinity-proof <name> sha:<first16hex>",
    "open_note_max_bytes": 80,
    "doc_ref_open_metadata": { ... },
    "merkle_root": "<64-hex>",
    "manual_sost_cli_template": "<command, never executed>",
    "execution_status": "NOT_EXECUTED — ..."
  },
  "verification": {
    "verifier_script": "scripts/trinity/verify_trinity_bundle.py",
    "instructions": "..."
  }
}
```

Anchor basenames are **never absolute paths**. The verifier searches alongside the bundle and in the current working directory; that is enough for a third party who downloaded all four files together.

## 2. Merkle algorithm (fixed order, four leaves)

```
leaf0 = bytes.fromhex(scorecard_sha256)
leaf1 = bytes.fromhex(dossier_sha256)
leaf2 = bytes.fromhex(useful_compute_plan_sha256)
leaf3 = bytes.fromhex(campaign_sha256)

node01 = SHA256(leaf0 || leaf1)
node23 = SHA256(leaf2 || leaf3)

merkle_root = SHA256(node01 || node23)
```

Order is enforced by `leaf_order` in the bundle and validated by the test `test_merkle_root_matches_documented_algorithm`. Swapping any two leaves produces a different root (test `test_merkle_root_changes_when_leaf_order_changes`). Any non-hex input raises (test `test_merkle_root_rejects_malformed_input`).

The Merkle root is published alongside the four base hashes so an on-chain `OPEN_NOTE_INLINE` capsule can carry a single short token (`trinity-proof <name> sha:<first16hex>`) while a `DOC_REF_OPEN` capsule can point at the full JSON.

## 3. Two scripts, one branch

`sost-core/scripts/trinity/trinity_proof_bundle.py`
  Builder. Reads the dossier, plan and campaign JSON from disk; computes each file's SHA-256 from raw bytes; lifts `scorecard_sha256` from `dossier.source` (or accepts `--scorecard-sha` explicitly); emits the bundle dict, its canonical-bytes hash, and the rendered Markdown.

`sost-core/scripts/trinity/verify_trinity_bundle.py`
  Verifier. Twelve closed checks (C1–C10) covering schema, anchor SHA shapes, Merkle root, safety flags, host-path leak, capsule execution status, and local-file re-hashing. Exit code 0 only if every check passes. Never opens a network connection. Never executes `sost-cli`. Never touches the wallet.

`sost-core/tests/trinity/test_trinity_proof_bundle.py`
  Twenty tests covering the builder and the verifier. Determinism with pinned-time, anchor-shape, Merkle algorithm, host-path anti-leak, and the verifier's behaviour on six classes of tampering (wrong anchor / registered=true / no_rewards_active=false / dry_run=false / wrong Merkle / capsule executed). Static check on both modules' public surfaces for absence of broadcast / activate / publish / move-funds / register-on-chain helpers.

## 4. Demo — Kalgoorlie Phase 1

```
$ python3 scripts/trinity/trinity_proof_bundle.py \
    --dossier TRINITY_DEMO_DOSSIER_kalgoorlie.json \
    --useful-compute-plan TRINITY_USEFUL_COMPUTE_PLAN_kalgoorlie.json \
    --campaign TRINITY_CAMPAIGN_kalgoorlie_phase1.json \
    --aoi kalgoorlie \
    --bundle-name kalgoorlie_phase1 \
    --pinned-time 2026-05-10T00:00:00+00:00

[trinity-pb] wrote MD:   TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.md
[trinity-pb] wrote JSON: TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json
[trinity-pb] aoi:        kalgoorlie
[trinity-pb] bundle:     kalgoorlie_phase1
[trinity-pb] scorecard:  836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246
[trinity-pb] dossier:    d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf
[trinity-pb] plan:       1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49
[trinity-pb] campaign:   7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df
[trinity-pb] merkle:     a818a1e4799ec34fd5a65b17d180a9534f791d4cd49f54c97b21c11d7b0e28b4
[trinity-pb] PROOF_SHA:  3a28a4b112fe95df85ab2ab91deb7698ebeb1d9182297f06635fd12fd4053a02
[trinity-pb] registered: False
[trinity-pb] dry_run:    True
```

Verifier output on the same bundle:

```
[PASS] C1 schema = 'trinity-proof-bundle/v0'
[PASS] C2 anchors: all four are 64-char lowercase hex
[PASS] C3 merkle root matches recomputed value
[PASS] C4 safety_status.dry_run = True
[PASS] C5 safety_status.registered = False
[PASS] C6 safety_status.no_rewards_active = True
[PASS] C7 safety_status.ready_to_register = True
[PASS] C8 canonical JSON contains no absolute host path
[PASS] C9 capsule_preview.execution_status reports NOT_EXECUTED
[PASS] C10 dossier: local SHA matches anchor (d0bbc47e62f3d51b...)
[PASS] C10 useful_compute_plan: local SHA matches anchor (1e7ab30aa1595c8f...)
[PASS] C10 campaign: local SHA matches anchor (7253cf30cf2f45e6...)

[verify] OK — bundle TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json is valid.
```

## 5. How the bundle is intended to be registered (manually)

The bundle is **not registered automatically**. Two manual paths the operator can choose:

**Path A — Short label (OPEN_NOTE_INLINE, ≤80 bytes).**
The capsule body fits a single short token. Example:

```
trinity-proof kalgoorlie_phase1 sha:3a28a4b112fe95df
```

The first 16 hex of `proof_bundle_sha256`. Anyone reading the capsule can:
1. Find the corresponding JSON bundle (published wherever the operator chose).
2. Recompute `sha256(canonical(bundle))` and check it matches the on-chain `sha:` prefix.
3. Run the verifier to confirm the four base anchors.

**Path B — Document reference (DOC_REF_OPEN).**
The capsule carries the URL to the JSON bundle plus the bundle SHA-256 inside the capsule's hash field. The operator publishes the JSON at a public mirror (GitHub raw, IPFS, dedicated server) and inscribes the locator + hash on chain in one transaction.

In both cases the broadcasting step is `sost-cli send … --capsule-mode …` run by the operator. The Proof Bundle script never invokes it.

## 6. Verifying a bundle as a third party

```bash
# Download the bundle JSON (and optionally the three artefacts it
# references) into one directory.
python3 scripts/trinity/verify_trinity_bundle.py \
        TRINITY_PROOF_BUNDLE_<name>.json
```

The verifier expects nothing on the network. If the dossier / plan / campaign JSON files are present alongside the bundle, their SHA-256 is recomputed and checked against the recorded anchors (C10). If they are missing, the corresponding checks SKIP — never FAIL. The Merkle root and safety-status checks pass regardless.

## 7. Sprint 5 candidates (not implemented)

- `--register` flag on the builder that **prepares** (but does not execute) the exact `sost-cli send` command for either OPEN_NOTE_INLINE or DOC_REF_OPEN. The flag never broadcasts; it only emits a ready-to-run shell line and the matching capsule body bytes.
- Multi-bundle index: when the operator has registered N bundles for N AOIs, a meta-bundle (`TRINITY_PROOF_INDEX_<period>.json`) anchoring all N proof_bundle_sha256 values via the same Merkle algorithm at the next layer up.
- Optional ECDSA signature over the proof_bundle_sha256 with the operator's mining key, so the bundle carries an authenticated authorship claim even before chain registration.
- Persistence into `materials-engine-private/src/multi_ai_review/canonical_memory` so Trinity sessions can cross-reference each other's bundles without re-reading every JSON.

Sprint 5 is not in this branch.
