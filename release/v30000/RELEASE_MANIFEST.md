# SOST V30000 FINAL release — manifest

- Branch: feat/v30000-native-assets
- FINAL commit: 619d5d657eed094b19b47f6c0e62c576d3bb5c44 (SEC2 RPC hardening cherry-picked in)
- Admin authority (public): sost1ad01a1ce3ae7d0dbcc1baae7a11e9ecde28683a2
  -> ADMIN_AUTHORITY_PKH = ad01a1ce3ae7d0dbcc1baae7a11e9ecde28683a2 (baked, non-zero; NOT fail-closed)
- Build: CLEAN from scratch (build-v30000-final) · Release · -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF (MAINNET)
- Node: SOST Node v0.4.0 (Profile MAINNET; native-assets + admin gate activate at #30000)
- Bundles: V16 + SEC2 + SACS V1 + SACS V2 + native-asset layer + 4 modalities + DEX + admin consensus gate (S14)
- Builds are NOT bit-reproducible (embedded metadata); hashes below are from this clean final build.

## Binaries (SHA256)
    78fefb67a15615f3df1b0a4f498239ccba07ba47ce6e333d13d5d2afdcecbb56  sost-node
    eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951  sost-miner
    c8ae00b9a6745f7c84cc8791b9994d32052a07d1fed12aa82c4e283fba2f691b  sost-cli


## SEC2 (RPC node hardening) — INCLUDED
The two pre-existing unauthenticated RPC remote-DoS defects (getblockhash non-numeric -> std::terminate; getblock nested-array -> OOM) are fixed in this build (dispatch try/catch + json param delimiter-advance + 256 cap, cherry-pick ebe4f790). Re-tested on the final node: both inputs -> clean error, node ALIVE, RSS flat 9MB. No consensus path touched.

## Admin consensus gate (ACTIVE, not fail-closed)
Only transactions carrying an input whose pubkey hashes to the admin authority above may
execute native-asset ops from #30000; all others are rejected by consensus (S14). Lifting
= future height-gated release (docs/v30000/ADMIN_CONSENSUS_GATE.md). The admin PRIVATE key
is never used/stored by the build; only the public address is baked.
