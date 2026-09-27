# Asset Passport ↔ SOST Capsule doc-ref — format compatibility (validated offline)

**Goal (P5/item 5):** register + verify a real Asset Passport as an on-chain Capsule `doc_ref`.
This document records what was **validated offline** and the exact procedure for the on-chain
step, which is **BLOCKED-ENVIRONMENT**.

## Validated offline (executable, reproducible)
The `sost-cli` doc-ref capsule (`--capsule-mode doc-ref`) commits `file_hash = SHA-256(file)`
plus an optional `--capsule-locator`. The Asset Passport's `manifestHash` is the SHA-256 of the
canonical manifest JSON. **They are byte-identical**, so the hash the Passport UI shows *is* the
on-chain `file_hash`:

```
passport.manifestHash        = fbac19f03de9af6175d25e7fe96c66285d98ea4abb518c15991715803da2adf1
sha256(canonical manifest)   = fbac19f03de9af6175d25e7fe96c66285d98ea4abb518c15991715803da2adf1   ✓ MATCH
capsuleDocRef payload        = 130 / 243 bytes  ✓ (CAPSULE_MAX_BODY)
locator "ipfs://Qm…"         = 35 / 96 bytes    ✓ (CAPSULE_DOC_REF_MAX_LOCATOR = 96)
```

So: write the passport's canonical manifest to a file, upload it to the locator (IPFS/HTTPS),
and anchor it — the on-chain `file_hash` will match the Passport, and `verify()` re-hashing the
retrieved manifest detects any tampering. Verified against `include/sost/capsule.h`
(`DOC_REF_OPEN`, `file_hash: Hash256`, `CAPSULE_DOC_REF_MAX_LOCATOR = 96`) and the live
`--capsule-mode doc-ref --capsule-file` CLI.

## The on-chain step (BLOCKED-ENVIRONMENT) — exact procedure
Blocked here because it needs a **devnet-fast node build** (mainnet SbPoW uses a ~4 GB
scratchpad per block — infeasible in-sandbox) and **persistent node/miner processes** (the
sandbox kills long-lived servers via RLIMIT_FSIZE / SIGXFSZ). On a normal machine:

1. Build node+miner+cli with the devnet-fast flags:
   `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=ON`
   (devnet `COINBASE_MATURITY=5`, fast blocks — never on mainnet).
2. Start an isolated node (exclusive ports, e.g. `--port 19333 --rpc-port 19332`, own data dir).
   **Do not** dial the mainnet node (RPC `127.0.0.1:18444`).
3. Mine a few blocks to a wallet address (`--realtime` mandatory) and wait `COINBASE_MATURITY`.
4. Write the passport manifest to a file, then anchor it:
   ```
   sost-cli send <recipient-sost1…> 10 \
     --capsule-mode doc-ref \
     --capsule-file  passport-manifest.json \
     --capsule-locator ipfs://<CID> \
     --yes                                   # --yes is REQUIRED or the send is cancelled before broadcast
   ```
5. Confirm acceptance (`getrawmempool` on the SAME node — a bare txid is NOT acceptance), mine 1
   block, then read it back and confirm `file_hash == passport.manifestHash`.
6. **Reorg test:** with the devnet reorg failpoint, disconnect the anchoring block and confirm
   the passport's ANCHORED state flips back to VERIFIED/DECLARED (anchor no longer canonical),
   then re-anchors on reconnect — exercises `classify(anchored=…)`.
7. **Revocation test:** attach a third-party attestation with `revoked:1` / expired `expiresAt`
   and confirm `classify()` drops VERIFIED_BY_THIRD_PARTY (already unit-tested; this repeats it
   against the real capsule round-trip).

## State
- Format compatibility: **VALIDATED (offline)**.
- On-chain register/verify/reorg/revocation round-trip: **BLOCKED-ENVIRONMENT** (devnet build +
  persistent processes); procedure above is ready to run on real hardware.
