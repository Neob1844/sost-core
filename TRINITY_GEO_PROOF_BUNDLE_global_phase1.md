# Trinity Proof Bundle — `global_phase1`

> **DRY-RUN ONLY.** This document is a cryptographic binding of the dossier, plan and campaign manifest produced for one AOI. The bundle is `ready_to_register=true` and `registered=false`. No transaction has been broadcast, no rewards are active, no wallet was touched.

- **Schema**: `trinity-proof-bundle/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **AOI**: `geo_global_phase1`
- **proof_bundle_sha256**: `3506dc5b32d17f29a4e5fcebbd38a4bbbfca510c478286b5644d00b680a9b517`

## Anchor hashes

| Anchor | SHA-256 | Basename |
| --- | --- | --- |
| scorecard | `afd8e578bd1fef42603648a47bc71a40d85e6dd7824df598ca83dec93c82963b` | `<external; sha256 only>` |
| dossier | `8eea473a272e4b651868d63e5a11307397ad3e9ecf71f74c11593f53e1c1ac97` | `TRINITY_GEO_DOSSIER_global_phase1.json` |
| useful_compute_plan | `44e731fee8066a8ef57edd77b097fd55a172f7ae94797b3437cf306eb4f236d2` | `TRINITY_GEO_USEFUL_COMPUTE_PLAN_global_phase1.json` |
| campaign | `9142a23636749304ecd64615a2921ff8cd7cadf60948a2e97a3f02e29bed940a` | `TRINITY_GEO_CAMPAIGN_global_phase1.json` |

## Merkle root

- **Root**: `da8338ce75ecc6e408bf4c9c87e70d55706baf8e618175824016acfa8fc70bdf`
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

- **OPEN_NOTE_INLINE template** (max 80 bytes): `trinity-proof global_phase1 sha:<first16hex>`
- **DOC_REF_OPEN intended locator**: `https://<your-public-mirror>/proof_bundles/global_phase1.json`
- **DOC_REF_OPEN embedded hash field**: `<proof_bundle_sha256>`
- **Execution status**: `NOT_EXECUTED — this script never broadcasts or signs. The fields above are reference values the operator can use to compose the capsule manually.`

**Manual `sost-cli` command (operator-driven, NOT executed):**

```
# OPERATOR-DRIVEN. Do NOT automate. Read the bundle and the campaign manifest before running.
./sost-cli --wallet <your-wallet>.json send <your-address> 0.01 --capsule-mode open-note --capsule-text 'trinity-proof global_phase1 <first16hex>'
```

## Verification

- **Verifier**: `scripts/trinity/verify_trinity_bundle.py`
- **Instructions**: Run `python3 scripts/trinity/verify_trinity_bundle.py <bundle.json>` from the sost-core repo root. The verifier re-hashes any local artefact whose basename matches a recorded anchor and reports a non-zero exit code on any mismatch.

## What this document is NOT

- This is **not** a broadcasted SOST capsule. The `proof_bundle_sha256` is ready to inscribe; doing so is a manual operator step.
- This is **not** a guarantee of geological or material content. The campaign manifest carries the upstream evidence; this document is the cryptographic root only.
- This is **not** an announcement of active Useful Compute rewards.

