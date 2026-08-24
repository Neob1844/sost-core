# 10 — Known Limitations (honest)

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

These are the honest, current limitations. None of them is fixed by this document set.

1. **Not post-quantum today.** Spend uses classical ECDSA secp256k1
   (`src/tx_signer.cpp`, `README.md:196`). SOST is not quantum-safe and does not claim to be
   (`website/index.html:1413`).

2. **Exposed-pubkey risk.** Once a public key is revealed on-chain (any spend, or any address reuse),
   its coins are the set an eventual quantum adversary could target by recovering the private key
   from the public key (`05-security-model.md`).

3. **Address reuse increases exposure.** Reusing an address republishes the public key and keeps it
   exposed while it still holds funds. Wallets should discourage reuse.

4. **Dormant coins at revealed keys.** Coins left at already-revealed public keys (e.g. old reused
   addresses) cannot be protected retroactively without being moved; a migration, if it ever
   activated, could not un-reveal an already-published key.

5. **Mempool front-running window at spend.** Even hash-locked (unrevealed) coins expose their public
   key and signature in the mempool at spend time, creating a race window
   (`05-security-model.md`).

6. **No external security audit.** No independent audit of the current scheme or the PQ prototype has
   been completed. Reviewers are welcome (`website/index.html:1413`).

7. **No activation date or height.** There is deliberately none. `PQ_ACTIVATION_HEIGHT = INT64_MAX`
   ("never active"). Website dates (2027/2028/2030) are aspirational and **not canonical** under V3.

8. **Fixed input layout blocks PQ in place.** The 64/33-byte fixed `TxInput` fields
   (`include/sost/transaction.h:72-73`) cannot hold ML-DSA-sized data; a versioned variable-length
   witness is required (`03-transactions-and-signatures.md`) and is not yet implemented on mainnet.

9. **Provisional registry.** The `alg_id` registry is PROVISIONAL and reassigns ids relative to V2;
   it must be finalised and audited before any use (`06-post-quantum-roadmap.md`).

10. **Legacy naming residue.** `include/sost/proposals.h:44` still labels the reserved proposal
    "SPHINCS+/Dilithium"; this is historical and inert, but should eventually be reworded to ML-DSA.
