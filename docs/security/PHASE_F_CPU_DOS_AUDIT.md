# Phase F — CPU-DoS / parser / allocation audit (partial, evidence-based)

Scope of this pass: the network-facing hostile-input allocations and fixed-offset
reads on the P2P path, plus an inventory of explicit limits. Full per-path
cheap-before-expensive ordering audit and the eclipse/peer-diversity work remain.

## Explicit limits present (evidence)
| Limit | Value | Where |
|---|---|---|
| MAX_P2P_MSG_SIZE | 4 MB | sost-node.cpp:674; p2p_frame.h FRAME_MAX_PAYLOAD |
| MAX_TX_BYTES_CONSENSUS | 100 000 | consensus_constants.h:19 |
| MAX_BLOCK_BYTES_CONSENSUS | 1 000 000 | consensus_constants.h:20 |
| MAX_BLOCK_TXS_CONSENSUS | 65 536 | block_validation.h:37 |
| JSON MAX_DEPTH / MAX_INPUT_SIZE | 64 / 64 MB | json_rpc.h:36-37 |
| MAX_ORPHAN_BLOCKS / MAX_FORK_INDEX_ENTRIES | 200 / 1000 | sost-node.cpp:268-269 |
| MAX_REORG_DEPTH / MAX_KNOWN_BLOCKS | 500 / 50 000 | sost-node.cpp:641,656 |
| MAX_INBOUND_PEERS | 32 | sost-node.cpp:675 |
| mempool caps (entries/per-addr/relay-per-min) | 5000 / 25 / 30 | mempool.h, params.h:738,741 |
| beacon notice / cache | 4 KB / 32 | beacon_p2p.h:99-100 |
| fork-store per-IP/per-/24/global bytes (sec1 V1-V3) | 50 / 150 / 96 MB | sost-node.cpp (sec1) |

## Attacker-controlled allocations — VERIFIED GUARDED
- `p2p_recv` plaintext: `if (len > MAX_P2P_MSG_SIZE) return false;` **before** `payload.resize(len)`. Bounded ≤4 MB.
- `p2p_recv` encrypted: same guard; `clen = len - 16` only after `len < 20 || len > MAX_P2P_MSG_SIZE` reject. Bounded.
- Stateful `sost_p2p::try_parse_frame`: `payload_len > FRAME_MAX_PAYLOAD` rejected before `frame_size` is formed. No overflow (12 + u32 fits size_t).

## Fixed-offset reads — VERIFIED GUARDED
- VERS handler: `if (msg.payload.size() >= 40)` before `read_i64(payload)` + `memcpy(payload+8, 32)`.
- GETB handler: `if (msg.payload.size() >= 8)` before `read_i64(payload)`.
- Capsule parse: `if (payload.size() < 12) return`, `if (12+body_len > payload.size()) return`.

## Result of this pass
No unbounded attacker-controlled allocation and no unguarded fixed-offset read found on
the sampled P2P hostile-input paths. The base64 signed-shift UB (a correctness/UB issue,
not an allocation) is handled separately (sec1 beacon fix + deferred local encoders).

## Pending (Phase F remainder)
- Full cheap→expensive ordering audit of every message handler (size→framing→structure→
  cheap-hash→context→signature→PoW), documented per path.
- Peer management: inbound/outbound separation, outbound diversity, basic eclipse resistance,
  quotas that never block legitimate NAT/VPN (sec1 already added per-/24 eviction for the
  fork store; the connection layer diversity audit is pending).
