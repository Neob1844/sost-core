# SOST — post-quantum exposure of the mining identity

**Status: documentation only. Nothing here changes consensus, activates an algorithm, or
implies a fork. It records an exposure that is specific to SOST and that a future
migration has to be designed around.**

## The thing that makes SOST different from Bitcoin here

In Bitcoin, an address that has never spent does not reveal its public key: the chain
holds only a hash. The key becomes public at spend time, which is why "do not reuse
addresses" is the standing advice — it keeps the window in which a public key is exposed
as short as possible.

SOST does not have that property for miners. Since SbPoW activated at **#7,100**, every
v2 block header carries, in clear:

```
MinerPubkey     33 bytes   (include/sost/sbpow.h:38)  — secp256k1 compressed
MinerSignature  64 bytes   (include/sost/sbpow.h:39)  — BIP-340 Schnorr
```

and the miner's payout address is **not separable** from that key: the miner overrides
any `--address` with the address derived from the signing key (`src/sost-miner.cpp:2501`),
because SbPoW requires the block to be signed by the identity that gets paid.

Two consequences follow, and both are permanent:

1. **Every active miner's public key is on-chain from its first block**, and stays there.
   There is no equivalent of "spend once, then move to a fresh address": the identity has
   to keep signing with the same key to keep mining.
2. **That same key controls the mining rewards.** The exposed public key and the key
   holding the funds are one and the same.

V16 adds a second long-lived key of the same family: `NODE_BIND` publishes a 33-byte
node public key bound to the mining identity, and every heartbeat is a signature under it
(`include/sost/node_participation.h:33-43`). Node keys can be rotated with a higher
`bind_seq`; mining identities effectively cannot, without abandoning their history.

## Why it matters for a migration, not for today

Neither ECDSA nor Schnorr over secp256k1 is post-quantum secure. Against a
cryptographically relevant quantum computer, an exposed public key is the target — and in
SOST the most valuable keys are the ones guaranteed to be exposed. A migration therefore
cannot rely on "most funds sit behind unexposed hashes", which is the assumption that
makes Bitcoin's own transition look tractable.

What a design has to provide, in rough order:

* a new output/authorisation type secured by a PQ signature, height-gated, so existing
  coins stay spendable under the old rules until their owners move them — never an
  invalidation of existing UTXOs;
* a path for a miner to retire an exposed identity: today a new identity starts from zero
  DTD history, zero jackpot PoW weight and a new NODE_BIND, so rotation has an economic
  cost that the design must absorb deliberately;
* sizing that the block format can absorb. Today an identity costs 33 + 64 = 97 bytes per
  header. The NIST standards published in 2024 are far larger — ML-DSA-44 (FIPS 204) is
  on the order of a 1.3 KB public key and a 2.4 KB signature, SLH-DSA-128s (FIPS 205) a
  32-byte key with a signature around 7.8 KB. Those figures must be re-read from the
  standards before any design work; the point is the order of magnitude, which is one to
  two decimal orders above what the header carries now.

## What is NOT being proposed

No algorithm is being added, no height is being reserved, no fork is being scheduled.
The V16.1 consensus is frozen and activates at #30,000 unchanged. This file exists so
that the exposure is written down before anyone designs the migration, and so that the
public claim stays accurate: SOST's mining identities are **permanently exposed public
keys**, which is a stronger exposure than Bitcoin's address model, and that is a property
of requiring signed Proof-of-Work.
