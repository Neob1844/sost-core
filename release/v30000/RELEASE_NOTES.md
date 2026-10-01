# SOST V30000 — release notes

## What activates at block #30,000 (mainnet)
- **Native asset layer** (consensus): ASSET_GENESIS/ISSUE/TRANSFER/BURN; FIXED and
  CAPPED_REISSUABLE supply policies; per-asset conservation / cap / overflow safety;
  reorg-safe derived index.
- **Four tokenization modalities**, all on-chain: Tokenize, Auction (atomic asset↔SOST
  swap), Draw (block-hash entropy, verifiable), Project Funding (HTLC crowdfund).
- **SOST-layer DEX**: atomic-swap settlement + signed-offer orderbook validation.
- **Admin consensus gate (S14, RESTRICTED DEVELOPER MODE)**: while active, every native-
  asset op must be authorised by the admin key or the network rejects it — public use is
  impossible even via CLI/RPC until the gate is lifted by a future height-gated release.

## Access model during RESTRICTED DEVELOPER MODE
- **Consensus authority**: admin-signed inputs only (ADMIN_AUTHORITY_PKH). Fail-closed.
- **Web access**: server-side nginx admin auth (bcrypt, HTTPS, rate-limited, deny-by-default);
  no ?dev=1 / localStorage / JS bypass exists.
- **Public access**: DISABLED. Notices state the real status and that technical
  availability does not constitute regulatory authorization.

## Migration / install → see INSTALL.md ; Rollback → see ROLLBACK.md ; Gate → docs/v30000/ADMIN_CONSENSUS_GATE.md
