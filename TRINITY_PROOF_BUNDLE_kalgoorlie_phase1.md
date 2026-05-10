# Trinity Proof Bundle — `kalgoorlie_phase1`

> **DRY-RUN ONLY.** This document is a cryptographic binding of the dossier, plan and campaign manifest produced for one AOI. The bundle is `ready_to_register=true` and `registered=false`. No transaction has been broadcast, no rewards are active, no wallet was touched.

- **Schema**: `trinity-proof-bundle/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **AOI**: `kalgoorlie`
- **proof_bundle_sha256**: `3a28a4b112fe95df85ab2ab91deb7698ebeb1d9182297f06635fd12fd4053a02`

## Anchor hashes

| Anchor | SHA-256 | Basename |
| --- | --- | --- |
| scorecard | `836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246` | `<external; sha256 only>` |
| dossier | `d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf` | `TRINITY_DEMO_DOSSIER_kalgoorlie.json` |
| useful_compute_plan | `1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49` | `TRINITY_USEFUL_COMPUTE_PLAN_kalgoorlie.json` |
| campaign | `7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df` | `TRINITY_CAMPAIGN_kalgoorlie_phase1.json` |

## Merkle root

- **Root**: `a818a1e4799ec34fd5a65b17d180a9534f791d4cd49f54c97b21c11d7b0e28b4`
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

- **OPEN_NOTE_INLINE template** (max 80 bytes): `trinity-proof kalgoorlie_phase1 sha:<first16hex>`
- **DOC_REF_OPEN intended locator**: `https://<your-public-mirror>/proof_bundles/kalgoorlie_phase1.json`
- **DOC_REF_OPEN embedded hash field**: `<proof_bundle_sha256>`
- **Execution status**: `NOT_EXECUTED — this script never broadcasts or signs. The fields above are reference values the operator can use to compose the capsule manually.`

**Manual `sost-cli` command (operator-driven, NOT executed):**

```
# OPERATOR-DRIVEN. Do NOT automate. Read the bundle and the campaign manifest before running.
./sost-cli --wallet <your-wallet>.json send <your-address> 0.01 --capsule-mode open-note --capsule-text 'trinity-proof kalgoorlie_phase1 <first16hex>'
```

## Verification

- **Verifier**: `scripts/trinity/verify_trinity_bundle.py`
- **Instructions**: Run `python3 scripts/trinity/verify_trinity_bundle.py <bundle.json>` from the sost-core repo root. The verifier re-hashes any local artefact whose basename matches a recorded anchor and reports a non-zero exit code on any mismatch.

## What this document is NOT

- This is **not** a broadcasted SOST capsule. The `proof_bundle_sha256` is ready to inscribe; doing so is a manual operator step.
- This is **not** a guarantee of geological or material content. The campaign manifest carries the upstream evidence; this document is the cryptographic root only.
- This is **not** an announcement of active Useful Compute rewards.

