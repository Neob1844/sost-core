# V15 PoPC — carrier workflow (no hidden manual step)

> Companion to the V15 PoPC mainnet activation (PR #25). This PR makes the on-chain
> carrier step **visible and one-command** so a miner never silently fails DTD
> eligibility for not knowing they had to emit a carrier.

## The problem this fixes
The DTD-PoPC lottery reads the PoPC active set **from on-chain carriers**
(`node_collect_popc_events` → `chain_active_popc_set`), NEVER from the local
`popc_registry.json`. So registering a PoPC via `popc_register` is **not enough**:
the owner-signed **carrier transaction** must also be on chain. Previously that step
was implicit/manual — a miner could register, do nothing else, and be excluded at
block 25,000 without understanding why.

## What `popc_register` now returns
The RPC response now self-documents the carrier step (Option B — return a
ready-to-broadcast carrier, never auto-spend):

```json
{
  "commitment_id": "…",
  "activation_height": 20000,        // POPC_V15_ACTIVATION_HEIGHT (mainnet)
  "eligibility_height": 25000,       // DTD_POPC_ELIGIBILITY_HEIGHT (mainnet)
  "carrier_required": true,          // popc_v15_active_at(current_height)
  "active_after_activate": true,     // commitment is ACTIVE only after BOTH carriers land
  "register_carrier_status": "ready_to_broadcast",
  "activate_carrier_status": "broadcast_after_register",
  "register_carrier_hex": "5031 35c0 …",   // signed Register carrier (Pending)
  "register_carrier_cmd":  "sost-cli send --to <addr> --amount 1 --popc-carrier <register_hex>",
  "activate_carrier_hex":  "5031 35c0 …",   // signed Activate/attestation carrier (-> Active)
  "activate_carrier_cmd":  "sost-cli send --to <addr> --amount 1 --popc-carrier <activate_hex>",
  "carrier_note": "Register alone leaves the PoPC PENDING. Broadcast BOTH (Register then Activate) to be ACTIVE / DTD-eligible from 25000; create AND maintain."
}
```

**Register alone is NOT enough.** Register leaves the commitment **Pending**; the DTD lottery
requires an **Active** PoPC, which needs the **Activate** carrier too. The response therefore
returns BOTH, in order:
1. broadcast `register_carrier_cmd`, wait for it to confirm,
2. broadcast `activate_carrier_cmd`, wait for it to confirm → commitment is **Active**.

Status values:
- `not_required_yet` — before block 20,000 carriers are rejected by consensus, so none are produced.
- `needs_owner_key_in_wallet` — this node's wallet does not hold the registering address's key; sign from the wallet that does.
- `ready_to_broadcast` / `broadcast_after_register` — the hexes are signed and ready; broadcast Register, then Activate.

The node **does not broadcast** the carrier itself (no surprise spend), does not
touch consensus, and the carrier is rejected pre-V15 anyway — so this is inert on
mainnet until block 20,000 (after PR #25).

## Miner steps (from block 20,000)
1. **Create** the PoPC: `sost-cli popc register --sost-address … --eth-wallet … --token … --gold-mg … --duration …`
2. **Broadcast the Register carrier** using the returned `carrier_broadcast_cmd` and wait for it to confirm (`carrier_status` → confirmed).
3. **Activate / attest**: emit the Activate (attestation) carrier and **re-attest every audit interval** (`sost-cli popc carrier-hex --type activate …` → `send --popc-carrier`).
4. **Maintain**: a PoPC **auto-slashes** if an audit goes unanswered (~every 1,728 blocks). Create AND maintain.
5. **Eligible from block 25,000** if your PoPC is active and in good standing.

## Safety / invariants
- Eligibility is **chain-derived** — no off-chain registry can fake it.
- Failed/again broadcast does not fake eligibility; you simply retry the broadcast.
- A duplicate Register carrier is idempotent in the deterministic recompute (first wins).
- Gold Boost, Gold Vault Governance, emission and PoPC DEX are **untouched** by this PR.

## Status surfaces (wallet dashboard — follow-up)
The wallet PoPC Bond dashboard should display: carrier pending → broadcast →
confirmed → active for DTD eligibility (not eligible yet / eligible from 25,000).
The RPC fields above are the data source for that UI.
