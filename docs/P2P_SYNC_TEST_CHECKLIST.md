# P2P Sync Test Checklist — SOST v0.3.2+

Pre-launch verification checklist for P2P networking and chain sync.
Run these tests between two nodes (Node A = seed, Node B = new peer).

## Environment Setup

| Item | Node A (Seed) | Node B (Peer) |
|------|---------------|---------------|
| OS | Ubuntu 24.04 | Ubuntu 24.04 |
| Binary version | sost-node v0.3.2 | sost-node v0.3.2 |
| Profile | --profile mainnet | --profile mainnet |
| Genesis file | genesis_block.json | genesis_block.json (same) |
| P2P port | 19333 | 19333 |
| RPC port | 18232 | 18232 |

## Test 1: Initial Connection

```bash
# Node A (seed): start with some blocks already mined
./sost-node --genesis genesis_block.json --chain chain_a.json \
    --rpc-user test --rpc-pass test --port 19333

# Node B: connect to Node A
./sost-node --genesis genesis_block.json --chain chain_b.json \
    --rpc-user test --rpc-pass test --connect <NodeA_IP>:19333
```

| Check | Expected | Result |
|-------|----------|--------|
| B connects to A | `[P2P] Peer connected: <IP> (outbound)` | [ ] |
| Version handshake | `[P2P] <IP>: version OK, their height=N` on both | [ ] |
| Genesis match | No `genesis mismatch` message | [ ] |
| VACK exchange | Both peers show version_acked=true | [ ] |

## Test 2: Initial Block Download (IBD)

| Check | Expected | Result |
|-------|----------|--------|
| B requests blocks | `[P2P] Requesting blocks from 1` | [ ] |
| Blocks arrive in order | Height 1, 2, 3... accepted sequentially | [ ] |
| PoW validated | No `PoW invalid` rejections | [ ] |
| Merkle roots match | No `merkle_root mismatch` | [ ] |
| Coinbase validated | No `coinbase invalid` | [ ] |
| UTXO set matches | B's getinfo shows same UTXO count as A | [ ] |
| Chain tip matches | Both nodes same height + tip hash | [ ] |
| Batch continuation | `Batch done, requesting from N` until caught up | [ ] |
| Sync complete | `[P2P] Sync complete, height=N` | [ ] |

Verify with RPC:
```bash
# On both nodes:
curl -s -u test:test -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getinfo","params":[]}' \
    http://127.0.0.1:18232
```

## Test 3: Live Block Relay

Mine a new block on Node A while B is connected.

| Check | Expected | Result |
|-------|----------|--------|
| A mines block N+1 | `[BLOCK] Height N+1 accepted` on A | [ ] |
| A relays to B | B receives BLCK message | [ ] |
| B validates and accepts | `[BLOCK] Height N+1 accepted` on B | [ ] |
| Heights stay in sync | getblockcount matches on both | [ ] |

## Test 4: Transaction Relay

Submit a transaction on Node A, verify it reaches Node B's mempool.

```bash
# On Node A:
curl -s -u test:test -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"sendrawtransaction","params":["<tx_hex>"]}' \
    http://127.0.0.1:18232

# On Node B:
curl -s -u test:test -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getrawmempool","params":[]}' \
    http://127.0.0.1:18232
```

| Check | Expected | Result |
|-------|----------|--------|
| TX accepted on A | `sendrawtransaction` returns txid | [ ] |
| TX relayed via TXXX | B receives TXXX P2P message | [ ] |
| TX in B's mempool | `getrawmempool` on B includes txid | [ ] |
| TX confirmed in block | After mining, TX removed from both mempools | [ ] |

## Test 5: Reconnection and Resume

Kill Node B, restart it, verify it re-syncs any blocks mined while offline.

| Check | Expected | Result |
|-------|----------|--------|
| B loads chain from disk | `chain.json loaded, height=N` | [ ] |
| B reconnects to A | `[P2P] Peer connected` | [ ] |
| B catches up | Requests blocks from N+1, syncs to A's tip | [ ] |
| No duplicate blocks | No errors about height mismatch | [ ] |

## Test 6: Genesis Mismatch Rejection

Start Node B with a different genesis file.

| Check | Expected | Result |
|-------|----------|--------|
| B connects | TCP connection established | [ ] |
| Mismatch detected | `[P2P] <IP>: genesis mismatch, disconnecting` | [ ] |
| B disconnected | Peer removed from peer list | [ ] |

## Test 7: DoS/Ban Protection (v0.4+)

| Check | Expected | Result |
|-------|----------|--------|
| Invalid block → +50 score | `Misbehavior +50 (invalid block)` | [ ] |
| Invalid TX → +10 score | `Misbehavior +10 (invalid tx)` | [ ] |
| Ban at 100 | `BANNED <IP>: <reason> (24h)` | [ ] |
| Banned IP rejected | Subsequent connections silently closed | [ ] |
| Max inbound peers (64) | 65th connection rejected | [ ] |
| Oversized message (>4MB) | Connection dropped, `p2p_recv` returns false | [ ] |

## Test 8: Default Seed Connection

Start Node B with no `--connect` flag.

| Check | Expected | Result |
|-------|----------|--------|
| Default seed used | `[P2P] No --connect specified, using default seed: seed.sostcore.com:19333` | [ ] |
| DNS resolves | No `Cannot resolve` error | [ ] |
| Connection established | `[P2P] Peer connected` (or timeout if seed is offline pre-launch) | [ ] |

## Test 9: Checkpoint Validation (post-launch)

After adding checkpoints to `g_checkpoints[]` in sost-node.cpp:

| Check | Expected | Result |
|-------|----------|--------|
| Correct checkpoint passes | `[BLOCK] Checkpoint verified at height N` | [ ] |
| Wrong block at checkpoint height | `[BLOCK] REJECTED: checkpoint mismatch` | [ ] |
| Reorg past checkpoint blocked | `[BLOCK] REJECTED: would reorg past checkpoint` | [ ] |

## Test 10: write_exact() Reliability

| Check | Expected | Result |
|-------|----------|--------|
| Large block transfer | Blocks >64KB transfer without truncation | [ ] |
| Partial write handled | write_exact() loops until all bytes sent | [ ] |
| RPC responses complete | No truncated JSON in RPC responses | [ ] |

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| Tester | | | |

**All tests must PASS before mainnet genesis on 2026-03-13.**
