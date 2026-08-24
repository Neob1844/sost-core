# 05 — Security Model (classical today, where quantum changes it)

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## Classical assumptions today

SOST's spend security rests on the classical hardness of the elliptic-curve discrete logarithm
problem (ECDLP) over secp256k1: given a public key, an attacker cannot feasibly recover the private
key. LOW-S enforcement additionally removes signature malleability (`src/tx_signer.cpp:210-277`).
Addresses commit to `RIPEMD160(SHA256(pubkey))`, so a public key is not on-chain until its coin is
first spent.

## The correct quantum threat framing for signatures

The quantum risk to **signatures** is **not** "harvest now, decrypt later" — that phrase describes
the **encryption/KEM** risk (relevant to ML-KEM, FIPS 203), which SOST does not use for spend.

The correct framing for signatures is:

> An adversary can **collect public keys now** (from public keys revealed on-chain) and **forge
> signatures later**, once a cryptographically-relevant quantum computer exists. Shor's algorithm
> recovers the private key from the public key.

### Exposure depends on whether the public key is revealed

- **Revealed pubkeys are exposed.** Once a coin is spent (or an address is reused), the public key
  appears on-chain. Funds still sitting at a revealed pubkey are the exposed set.
- **Unrevealed pubkeys have a smaller window.** Funds at a never-spent, hash-locked address expose
  only the 20-byte hash until spend time. However, at spend the public key and signature enter the
  mempool, creating a **front-running window** — an attacker with the capability could try to forge
  and race a competing spend before confirmation.

## Where quantum changes the model

| Assumption today | Under a relevant quantum adversary |
| --- | --- |
| ECDLP hard → private key safe given public key | Shor recovers private key from public key |
| Revealed pubkey is safe | Revealed pubkey becomes forgeable |
| Address hash hides the key until spend | Only delays exposure; mempool reveals at spend |
| LOW-S prevents malleability | Unaffected (malleability is a separate property) |

## What the research direction changes

The prototype direction (research only) is a **versioned witness** carrying ML-DSA (FIPS 204), with a
**hybrid ECDSA-AND-ML-DSA** option so that a forgery requires breaking **both** schemes. OR-hybrids
are rejected because breaking either scheme would suffice to forge (see
`03-transactions-and-signatures.md` and `11-glossary.md`). None of this is active; see
`08-activation-and-governance.md`.

## Honest limitations

The exposed-pubkey and address-reuse risks above are **present today** and are not mitigated by this
document. See `10-known-limitations.md`.
