# SOST V30000 — Native Tokenization + DEX (usage & activation)

**Status:** IMPLEMENTED & DEVNET-VALIDATED. Activates at **block #30,000**
(developer-gated). NOT yet live on mainnet. Public execution restricted pending
regulatory readiness. *Technical availability does not constitute regulatory
authorization.*

The #30,000 hard fork bundles the native **asset layer** + the four
**tokenization modalities** + the **SOST-layer DEX**. All four modalities are
functional on-chain (no mocks). The only NEW consensus surface is the asset
layer; the modalities COMPOSE it with primitives that are already consensus-
validated (OUT_ESCROW_LOCK, OUT_HTLC_LOCK).

---

## 1. Native asset layer (consensus)

- **Activation:** `native_assets_active_at(h) == (h >= NATIVE_ASSETS_ACTIVATION_HEIGHT)`
  — mainnet **30000**, DEVNET_FAST **42**. Below it, asset tx/output types are
  byte-inert (R2 rejects the tx types, R11 rejects the output types).
- **Tx types:** `ASSET_GENESIS 0x30`, `ASSET_ISSUE 0x31`, `ASSET_TRANSFER 0x32`,
  `ASSET_BURN 0x33`.
- **Output types:** `OUT_ASSET_TRANSFER 0x40`, `OUT_ASSET_ISSUE_AUTH 0x41`,
  `OUT_ASSET_BURN 0x42`, `OUT_ASSET_GENESIS_DEF 0x43`.
- **asset_id** = `SHA256(first-input txid || vout LE)` — unforgeable, unique.
- **Supply policies:** `FIXED` (mint-once == cap, no authority) and
  `CAPPED_REISSUABLE` (an OUT_ASSET_ISSUE_AUTH UTXO authorises further issuance
  up to the cap). Per-asset conservation, supply/cap and `__int128` overflow are
  enforced; SOST dust flows separately from the asset amount (payload-carried).
- **Index:** `NativeAssetIndex` is derived chain state with journaled
  apply/undo (reorg-safe, same pattern as node-participation) and is rebuilt
  from the chain on restart.

## 2. CLI

```
# create (FIXED: mint == max). <symbol> <name> <decimals> <fixed|capped> <max_supply> <mint>
sost-cli createasset GOLD "Gold Token" 8 fixed 1000000 1000000 --from-address <addr>

# create (CAPPED_REISSUABLE: mint <= max, keeps an issuance authority)
sost-cli createasset SILVER "Silver" 8 capped 5000000 1000000 --from-address <addr>

sost-cli issueasset   <asset_id> <amount>                 # mint more (capped only)
sost-cli transferasset <asset_id> <to_address> <amount>   # move asset
sost-cli burnasset     <asset_id> <amount>                 # destroy (supply-accounted)

# RPC: getasset <id> · listassets · getassetbalance <addr> <id>
```

## 3. The four modalities

| Modality | On-chain mechanism | Trust model |
|---|---|---|
| **Tokenize** | genesis/issue/transfer/burn | fully consensus-enforced |
| **Auction** | `create_asset_swap` — ONE atomic tx {asset in, SOST in} → {asset→buyer, SOST→seller} | all-or-nothing settlement; two parties co-sign (single custodian in test). CLI `auctionsettle <id> <amount> <seller> <buyer> <price>` |
| **Draw** | entries are real on-chain txs; winner = `be64(SHA256(close_block_hash \|\| draw_id \|\| N)) % N` over txid-ordered entries; settlement pays that winner | entropy is a COMMITTED future block hash (unknown at entry, recomputable by anyone). Verify with CLI `drawwinner <block_hash> <draw_id> <N>` |
| **Project Funding** | each contribution is an HTLC: claim=project (goal-secret hashlock), refund=contributor (after deadline) | goal-met → project reveals the secret and claims; goal-unmet → each contributor refunds after the deadline. Trust-minimised: wrong secret R21, late claim R22, early refund R24 |

## 4. SOST-layer DEX

- **Settlement:** HTLC atomic swap (`OUT_HTLC_LOCK`, live since block 16000) for
  gold-token pairs; `create_asset_swap` cooperative single-tx swap for
  native-asset↔SOST. Both are atomic on-chain.
- **Coordination:** signed-offer orderbook (`ValidateOffer` — timeouts ordered,
  margin, non-zero hashlock/amount, issuer-freeze warning).

## 5. Public-access gate + regulatory notice (`website/js/tokenization-gate.js`)

- Flags: `DEX_PUBLIC_ENABLED=false`, `TOKENIZATION_PUBLIC_ENABLED=false`.
  Developer access via `?dev=1` (persisted) bypasses.
- **Real barrier (not CSS):** a capture-phase click interceptor
  `stopImmediatePropagation`s the operation handlers (inline onclick included)
  before they fire; a keydown interceptor covers Enter/Space.
- **Notice auto-switches on tip height:**
  - pre-30000 (or not mainnet-validated): *IMPLEMENTED & DEVNET-VALIDATED /
    ACTIVATES AT BLOCK #30,000 / NOT YET LIVE ON MAINNET / PUBLIC ACCESS
    RESTRICTED / DEVELOPER / CONTROLLED TESTING / PENDING REGULATORY READINESS*.
  - after activation **and** `MAINNET_VALIDATED=true` (hand-set once #30000 has
    activated and mainnet is validated): *LIVE AT PROTOCOL LEVEL / PUBLIC ACCESS
    RESTRICTED / DEVELOPER / CONTROLLED MAINNET USE / PENDING REGULATORY
    READINESS*.
- Applied to: sost-dex, atomic-swap, sost-dex-otc, sost-gold-dex,
  sost-universal-assets. **Not deployed to production** — branch only.

### Going LIVE after #30,000
1. Confirm mainnet crossed 30000 and the asset layer validated on mainnet.
2. Set `MAINNET_VALIDATED = true` in `tokenization-gate.js` (the copy switches to
   LIVE automatically once height ≥ 30000).
3. Flip `DEX_PUBLIC_ENABLED` / `TOKENIZATION_PUBLIC_ENABLED` to `true` only when
   regulatory readiness is confirmed — until then public stays restricted even
   while LIVE at protocol level.

## 6. What is proven (devnet, activation 42)
See `docs/v30000/TEST_MATRIX.md`.
