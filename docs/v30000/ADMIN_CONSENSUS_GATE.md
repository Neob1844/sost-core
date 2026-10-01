# V30000 — Protocol-level admin authority gate (RESTRICTED DEVELOPER MODE)

## What it does
While RESTRICTED DEVELOPER MODE is active, every **native-asset** operation
(`ASSET_GENESIS`, `ASSET_ISSUE`, `ASSET_TRANSFER`, `ASSET_BURN` — i.e. Tokenize,
and the Auction/Draw settlements which are ASSET_TRANSFER txs) is rejected by
**consensus** unless the transaction carries an input whose public key hashes to
the configured admin authority. This is enforced in
`ValidateTransactionConsensus` (rule **S14_RESTRICTED_DEV_MODE**), which runs on
the block-connect path, so an unauthorised asset tx **cannot be mined even if
hand-crafted via CLI / RPC / third-party software** — web-UI protection alone is
explicitly NOT relied upon.

## Which pubkey/address has temporary authority
`ADMIN_AUTHORITY_PKH` in `include/sost/params.h` — the 20-byte RIPEMD160(SHA256(pubkey))
of the admin address (a `sost1…` address decoded). It is a **public** value; the
private key never leaves the operator. The shipped default is the **all-zero
placeholder**, which is fail-closed: it matches no real pubkey, so NO asset op can
execute until a real admin address is baked in.

## How it is verified
`sost_tx_has_admin_authorization(tx, admin_pkh)` returns true iff any `tx.inputs[i]`
has `ComputePubKeyHash(inputs[i].pubkey) == admin_pkh`. That input's ECDSA signature
is already consensus-verified by the R/S signature rules, so authorisation reuses the
existing signature machinery — **no new cryptography, smallest possible consensus
surface.** The authority pkh is read from `TxValidationContext.admin_authority_pkh`
(the node sets it from `ADMIN_AUTHORITY_PKH`), falling back to the compile-time
constant so every node agrees deterministically.

## What happens to an unauthorised transaction
`ValidateTransactionConsensus` returns `S14_RESTRICTED_DEV_MODE` → the tx is rejected
by mempool AND by block validation. It never confirms. (Below the activation height
the asset tx types are already inert via R2/R11.)

## Setting the real admin authority (operator procedure)
The admin **public** key hash is the only thing baked in. To set it for the final
mainnet build, provide your admin `sost1…` address; its 20-byte pkh is placed in
`ADMIN_AUTHORITY_PKH`. Two supported ways:
1. Build-time define (no repo edit):
   `cmake -D CMAKE_CXX_FLAGS="-DSOST_ADMIN_PKH_BYTES={0x..,0x..,…20 bytes…}"`
2. Edit `ADMIN_AUTHORITY_PKH` in `params.h` to the 20 bytes of your address pkh.
The private key stays solely with you and is NEVER committed, logged, or placed in
JavaScript. (Decode an address to its pkh with `sost-cli decodeaddress <addr>` or the
bech32 payload.)

## Removing the restriction later
Set `RESTRICTED_DEV_MODE_END_HEIGHT` (currently `INT64_MAX`) to a real future height
in a new release and ship it to the network before that height. Because this changes
a consensus rule, **lifting the gate is a coordinated height-gated release — i.e. a
further fork** (all nodes must run the new binary before the end height). Until then
the restriction is indefinite. Alternatively `RESTRICTED_DEV_MODE_ENABLED=false` in a
future release disables it from that release's activation — also a coordinated upgrade.

## Scope note
The gate covers the NEW V30000 native-asset tx types. The pre-existing SOST-native
HTLC atomic-swap primitive (live since block 16000) is intentionally out of scope —
restricting it retroactively would break the already-live atomic swap. Project
Funding built on that HTLC therefore inherits the pre-existing primitive's rules,
documented in TOKENIZATION_AND_DEX.md.
