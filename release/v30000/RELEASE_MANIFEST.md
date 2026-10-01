# SOST V30000 FINAL release candidate — manifest

- Branch: feat/v30000-native-assets
- FINAL commit: ba64978f7ba5fc26218d0454daf651033baa1700
- Build: CLEAN from scratch (build-v30000-final) · Release · -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF (MAINNET)
- Node: SOST Node v0.4.0 (Profile MAINNET; enforces native-assets + admin gate activation at #30000)
- Bundles: V16 + SEC2 + SACS V1 + SACS V2 + native-asset layer + 4 modalities + DEX + admin consensus gate (S14)
- Builds are NOT bit-reproducible (embedded build metadata); hashes below are from this clean final build.

## Binaries (SHA256)
    66fb9428970ed02de1e3c80d0e646f2b05fc9d2dab3dc316fbf361f309c22e8f  sost-node
    eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951  sost-miner
    ecd7e7eb978c212920649af7e18040aa3e8dd14d75ee9ab24f73e428909f1f74  sost-cli

## Admin authority (REQUIRED before the truly-final mainnet binary)
Built with the ALL-ZERO ADMIN_AUTHORITY_PKH placeholder = FAIL-CLOSED (no native-asset op
executes until the operator's real admin address pkh is baked). Baking it changes the
hashes; regenerate SHA256SUMS. Procedure: docs/v30000/ADMIN_CONSENSUS_GATE.md. The admin
PUBLIC key/address is all that is needed; the private key never touches the build.

## Consensus (verified on this build, mainnet activation = 30000)
- native-assets + admin restricted gate activate at #30000; pre-30000 inert (byte-identical replay)
- restricted developer mode indefinite (RESTRICTED_DEV_MODE_END_HEIGHT = INT64_MAX); lifting = future height-gated release (fork)
