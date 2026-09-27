# Peer persistence — remember-and-redial (isolated branch `feat/peer-persistence`)

Closes the "a fresh node depends on STRATO forever / no peer memory" gap: a node that has connected
once now bootstraps from a local `peers.json` on restart, with NO `--connect` and NO working seeds.

## Design (safe subset; anti-poisoning / anti-eclipse by construction)
- `peers.json` (mode 0600, atomic temp+rename, capped at 128) lives next to `chain.json`.
- We persist ONLY addresses we ourselves dialed **outbound** and that **completed the version
  handshake** (`remember_peer` at the `version_acked` point, guarded by `p.outbound`). A peer can
  NOT make us store an address of its choosing — no gossip/relay, no inbound source address is ever
  persisted — so the classic address-injection / eclipse-seeding vector does not exist here.
- On startup we `load_peers_file()` and dial every remembered peer **in addition to** seeds /
  `--connect`. On peer-loss the reconnect loop also redials remembered peers.
- Addresses are validated (`host:port`, port 1..65535) on load and store.
- Full ADDR gossip (discovering brand-new peers from peers) is a SEPARATE, review-gated protocol
  change and is intentionally NOT enabled here.

## Test — clean environment (PASSED; `docs/p2p/peer_persistence_test.sh`)
1. Node A (p2p 20310). Node B started with `--connect 127.0.0.1:20310`.
2. After the handshake, **B's `peers.json` = `["127.0.0.1:20310"]`** (it remembered A).
3. B stopped and restarted with **NO `--connect`** (seeds unreachable in the lab).
4. B's log: `redialing 1 remembered peer(s) from …/peers.json` then
   `[P2P] Peer connected: 127.0.0.1:20310 (outbound)` — **B reconnected to A purely from
   `peers.json`, independent of STRATO.**

## Not done (correctly)
- The real 24-hour independence test with external operators/miners is BLOCKED-EXTERNAL (people,
  not code) — the persistence + redial CODE is implemented and lab-tested here, not blocked.
- ADDR gossip for discovering unknown peers: designed, review-gated, not shipped.
