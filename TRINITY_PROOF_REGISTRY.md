# Trinity Proof Registry — v0

> **Public registry document.** This file records on-chain Trinity proof-bundle anchors. It does not broadcast, sign or register anything. Each entry is the cryptographic record of an operator-driven manual capsule registration that already happened on the SOST chain.

- **Schema**: `trinity-proof-registry/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Network**: SOST mainnet

## Kalgoorlie Phase 1

- **id**: `kalgoorlie_phase1`
- **AOI**: `kalgoorlie`
- **Status**: `registered`
- **Registration method**: `manual-cli`
- **Operator**: NeoB
- **Block height**: `8085`
- **TXID**: `d68678b5d15ca8a60b70a7aa17647bfa12271d342eef066e1b4a832f4624f3db`
- **Capsule mode**: `open-note`
- **Capsule text**: `trinity-proof kalgoorlie_phase1 3a28a4b112fe95df`
- **proof_bundle_sha256**: `3a28a4b112fe95df85ab2ab91deb7698ebeb1d9182297f06635fd12fd4053a02`
- **proof_bundle_sha16**: `3a28a4b112fe95df`
- **Merkle root**: `a818a1e4799ec34fd5a65b17d180a9534f791d4cd49f54c97b21c11d7b0e28b4`
- **Anchor files**:
  - `campaign`: `TRINITY_CAMPAIGN_kalgoorlie_phase1.json`
  - `dossier`: `TRINITY_DEMO_DOSSIER_kalgoorlie.json`
  - `proof_bundle`: `TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json`
  - `useful_compute_plan`: `TRINITY_USEFUL_COMPUTE_PLAN_kalgoorlie.json`
- **Safety status**:
  - `no_active_useful_compute_rewards`: `True`
  - `no_auto_broadcast`: `True`
  - `no_consensus_change`: `True`
  - `not_a_geological_conclusion`: `True`
  - `not_a_mineral_reserve_claim`: `True`

## What this document is NOT

- **Not** a mineral reserve claim. Each entry records cryptographic priority over a Trinity scientific workflow output, not over a deposit.
- **Not** an announcement of active Useful Compute rewards. The Useful Compute layer is dry-run by design.
- **Not** an automated broadcaster. The registry only documents operator-driven manual registrations after the fact.
- **Not** a consensus, RPC, node or wallet change. Building or verifying the registry never touches any of those layers.
