# Trinity Proof Bundle — `oxide_frontier_v01`

> **DRY-RUN ONLY.** This document is a cryptographic binding of the dossier, plan and campaign manifest produced for one AOI. The bundle is `ready_to_register=true` and `registered=false`. No transaction has been broadcast, no rewards are active, no wallet was touched.

- **Schema**: `trinity-proof-bundle/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **AOI**: `materials_oxide_frontier`
- **proof_bundle_sha256**: `3d2c8dc3c8f280e93ae3fec59a2538a39de7d1d36352f3dfd51c618595a69cd1`

## Anchor hashes

| Anchor | SHA-256 | Basename |
| --- | --- | --- |
| scorecard | `389dafeffa71b9bb031d6672ed73904cf2fd981716755d7785d5e03ac228a7f6` | `<external; sha256 only>` |
| dossier | `0426b8924a7d60aeee4d74f59b70ccd879c08d9b59c4d4db4cfc62b455ae8ffb` | `TRINITY_MATERIALS_DOSSIER_oxide_frontier_v01.json` |
| useful_compute_plan | `5638fb286bfc8d20f37e55afa8ed7fa3d84293f5e4949c499d19d5711a448853` | `TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_oxide_frontier_v01.json` |
| campaign | `4645abe41eeedc0fc9ee0e65fc7a9256f7e4beb271bfaf89b16105f69be4349f` | `TRINITY_MATERIALS_CAMPAIGN_oxide_frontier_v01.json` |

## Merkle root

- **Root**: `5ee1db78e10a1dcc1c81abf2a0a80f697eaf42b0d8612e4bfb0702acba09cfe0`
- **Leaf order**: `scorecard_sha256`, `dossier_sha256`, `useful_compute_plan_sha256`, `campaign_sha256`
- **Algorithm**: `sha256-binary-fixed-order: L0=bytes.fromhex(scorecard_sha256), L1=bytes.fromhex(dossier_sha256), L2=bytes.fromhex(useful_compute_plan_sha256), L3=bytes.fromhex(campaign_sha256). node01=sha256(L0||L1), node23=sha256(L2||L3), merkle_root=sha256(node01||node23).`

## Safety status

- `dry_run`: `True`
- `no_chain_broadcast`: `True`
- `no_consensus_modification`: `True`
- `no_public_publication`: `True`
- `no_rewards_active`: `True`
- `no_wallet_action`: `True`
- `ready_to_register`: `True`
- `registered`: `False`

## Capsule registration preview (manual)

- **OPEN_NOTE_INLINE template** (max 80 bytes): `trinity-proof oxide_frontier_v01 sha:<first16hex>`
- **DOC_REF_OPEN intended locator**: `https://<your-public-mirror>/proof_bundles/oxide_frontier_v01.json`
- **DOC_REF_OPEN embedded hash field**: `<proof_bundle_sha256>`
- **Execution status**: `NOT_EXECUTED — this script never broadcasts or signs. The fields above are reference values the operator can use to compose the capsule manually.`

**Manual `sost-cli` command (operator-driven, NOT executed):**

```
# OPERATOR-DRIVEN. Do NOT automate. Read the bundle and the campaign manifest before running.
./sost-cli --wallet <your-wallet>.json send <your-address> 0.01 --capsule-mode open-note --capsule-text 'trinity-proof oxide_frontier_v01 <first16hex>'
```

## Verification

- **Verifier**: `scripts/trinity/verify_trinity_bundle.py`
- **Instructions**: Run `python3 scripts/trinity/verify_trinity_bundle.py <bundle.json>` from the sost-core repo root. The verifier re-hashes any local artefact whose basename matches a recorded anchor and reports a non-zero exit code on any mismatch.

## What this document is NOT

- This is **not** a broadcasted SOST capsule. The `proof_bundle_sha256` is ready to inscribe; doing so is a manual operator step.
- This is **not** a guarantee of geological or material content. The campaign manifest carries the upstream evidence; this document is the cryptographic root only.
- This is **not** an announcement of active Useful Compute rewards.

