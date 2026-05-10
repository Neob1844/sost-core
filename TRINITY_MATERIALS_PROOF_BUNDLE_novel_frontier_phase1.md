# Trinity Proof Bundle — `novel_frontier_phase1`

> **DRY-RUN ONLY.** This document is a cryptographic binding of the dossier, plan and campaign manifest produced for one AOI. The bundle is `ready_to_register=true` and `registered=false`. No transaction has been broadcast, no rewards are active, no wallet was touched.

- **Schema**: `trinity-proof-bundle/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **AOI**: `novel_frontier`
- **proof_bundle_sha256**: `03e04c2a5e6389133ef6cf7e430d110d8bf05dd711a6e68c7c7ed7c2acae4595`

## Anchor hashes

| Anchor | SHA-256 | Basename |
| --- | --- | --- |
| scorecard | `7355afc86a4056c7b87b15b4125fbecc7dcfab2fa15ffb7fc0b2d2f1c1e4f9f8` | `<external; sha256 only>` |
| dossier | `2d266fb607e3bbd130b70b7185545e4746df2d1da2fd0fca3f5b640d8a48b9f8` | `TRINITY_MATERIALS_DOSSIER_novel_frontier_phase1.json` |
| useful_compute_plan | `4b9a0aa16e8f68c3b4510e3a795bf4fdd31cf739ad08e6596f86d8796dbcc5ac` | `TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_novel_frontier_phase1.json` |
| campaign | `73037a420f791ea92da97bcd64620769fb3a466acd3024f53e30d10b25d89ddb` | `TRINITY_MATERIALS_CAMPAIGN_novel_frontier_phase1.json` |

## Merkle root

- **Root**: `10b84f5b6ef5a76550d688b0abedd9748ed11e572ef09417a05cb472d621a03d`
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

- **OPEN_NOTE_INLINE template** (max 80 bytes): `trinity-proof novel_frontier_phase1 sha:<first16hex>`
- **DOC_REF_OPEN intended locator**: `https://<your-public-mirror>/proof_bundles/novel_frontier_phase1.json`
- **DOC_REF_OPEN embedded hash field**: `<proof_bundle_sha256>`
- **Execution status**: `NOT_EXECUTED — this script never broadcasts or signs. The fields above are reference values the operator can use to compose the capsule manually.`

**Manual `sost-cli` command (operator-driven, NOT executed):**

```
# OPERATOR-DRIVEN. Do NOT automate. Read the bundle and the campaign manifest before running.
./sost-cli --wallet <your-wallet>.json send <your-address> 0.01 --capsule-mode open-note --capsule-text 'trinity-proof novel_frontier_phase1 <first16hex>'
```

## Verification

- **Verifier**: `scripts/trinity/verify_trinity_bundle.py`
- **Instructions**: Run `python3 scripts/trinity/verify_trinity_bundle.py <bundle.json>` from the sost-core repo root. The verifier re-hashes any local artefact whose basename matches a recorded anchor and reports a non-zero exit code on any mismatch.

## What this document is NOT

- This is **not** a broadcasted SOST capsule. The `proof_bundle_sha256` is ready to inscribe; doing so is a manual operator step.
- This is **not** a guarantee of geological or material content. The campaign manifest carries the upstream evidence; this document is the cryptographic root only.
- This is **not** an announcement of active Useful Compute rewards.

