# SOST V30000 release candidate — manifest

- Branch: feat/v30000-native-assets
- Commit: 52b7be70a2fecfad759e1d3c9c5a55a15297979d
- Build: clean, from scratch; Release; -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF (MAINNET profile)
- Node version: v0.4.0 (Profile: MAINNET, enforces activation at #30000)
- Bundles: V16 + SEC2 + SACS V1 + SACS V2 + native-asset layer + 4 modalities + DEX + admin consensus gate (S14)

## Binaries (SHA256 — see SHA256SUMS.txt)
    edde13dccb8ef80853b6d0196203e2bb95ba042b536e3ed441864e5714e8f133  sost-node
    85a07bfca401f6aee3e2fd87593cabeb9d4106b2fe681660d3412d678e1ce1bc  sost-miner
    61643f6984e7f972dce41bda58eb92b678d279a36cab76ac4408a3ba0f2e959b  sost-cli

## IMPORTANT — admin authority not yet baked
This RC was built with the ALL-ZERO ADMIN_AUTHORITY_PKH placeholder (fail-closed:
no native-asset op executes until a real admin address is baked). The FINAL mainnet
build must set ADMIN_AUTHORITY_PKH to the operator's admin address pkh (public value;
see docs/v30000/ADMIN_CONSENSUS_GATE.md) — this changes the binary hashes. Regenerate
SHA256SUMS after that build.

## Mainnet consensus (verified on this build)
- native_assets activation height = 30000
- restricted developer mode active from 30000, admin-gated (S14), indefinite (END=INT64_MAX)
- pre-30000 asset tx/out types inert (R2/R11) — byte-identical historical replay
