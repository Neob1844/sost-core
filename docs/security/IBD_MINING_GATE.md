# IBD mining gate — do not mine on a known-stale tip (Gauntlet E follow-up)

## Finding
Gauntlet E showed a corrupt/unreadable `chain.json` makes the node fall back to genesis (h=0)
and re-sync — safe in isolation. But `handle_getblocktemplate` had **no sync gate**: it served
a template on `g_chain_height + 1` regardless of whether the node was behind the network. So a
node that restarted at genesis (or any lagging node) could hand its local miner a template and
**mine a competing block on a stale tip**, forking the network — even though it *knew* (from a
peer's advertised height) that it was behind.

## Fix (branch `fix/ibd-mining-gate`, NON-CONSENSUS)
At the top of `handle_getblocktemplate`, before building the template: if any connected,
version-acked peer advertises `their_height > local_height + IBD_MINING_LAG_MARGIN` (2 blocks),
return RPC error `-10 "node still syncing … refusing block template to avoid mining on a stale
tip"`. Does NOT change block validation/acceptance — only prevents the LOCAL miner from starting
on a known-behind tip. Locks `g_peers_mu` only (released) before `g_chain_mu`, so no lock-order
inversion. Bootstrap/solo (no peers, or at/above every peer) is unaffected.

## Verification (devnet)
- **Bootstrap/solo, no peers:** template served, miner produced blocks to h=10 — gate does NOT
  break chain bootstrap. ✅
- **Peer advertises h=999999 (stalled/lying), local h=0:** template REFUSED with the -10 error —
  node will not mine on the stale tip. ✅ (When the peer proves unable to serve, the node
  disconnects it and resumes mining — correct.)
- Synced node (local == peer height): template served normally. ✅

## Scope / status
Node-policy safety fix; NOT consensus, NOT an activation-height change. On its own dev branch,
not merged/deployed. Recommended for the Phase-3 integrated candidate. A production node with a
corrupt chain.json will now re-sync before its miner can build on a stale tip.
