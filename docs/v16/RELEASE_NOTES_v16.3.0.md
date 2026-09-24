# SOST v16.3.0 — release notes

**Commit:** `4b1e970f51a5a188488bef59ace15e04d128ecfb` (main)
**Type:** node functional update. Consensus activation heights are UNCHANGED
(V16 still activates by height at #30,000; first DTD Jackpot V2 at #30,186).

## Why a new version, and how it differs from v16.2.3

v16.2.0–v16.2.3 all shipped the **same** `sost-node` and `sost-miner`; only the
CLI changed. **v16.3.0 changes the node.** A node built from v16.2.3 cannot do a
full sync from genesis; v16.3.0 can. Anyone who downloaded v16.2.3 should update
their node and miner.

## What is in the new `sost-node`

- **P2P block serving fix** — never serves an incomplete block frame; serves the
  initial-block-download batch over the negotiated (encrypted) transport; aborts
  on the first failed frame instead of desynchronising the peer.
- **66 historical replay exceptions**, strictly bounded — 19 with recomputed
  cASERT values (heights 4,160–5,410) and 47 with a since-corrected
  profile-parameter table (4,715–5,038). Each is pinned by **height AND full
  block hash**; it changes NO rule for any new block and cannot fire above its
  hard height cut (5,410 / 5,038).
- **Sync rate-limit fix** — a freshly-synced node no longer bans the peer that
  just served it the chain; abuse limits still apply to genuinely unsolicited
  new blocks.

`sost-miner` and `sost-cli` carry the same v16.2.3 features (mining algorithm,
consensus, wallets unchanged; CLI keeps NODE_BIND `--mining-key-label` /
`--node-key-file`, `sendrawtransaction`, `wallet-export/import` AES-256-GCM).

## SHA256SUMS (real hashes of this release)

```
5a45ffeb4ab2120bb6877ad1151c300391b9ecb211652417e46590d850fec90e  sost-node
89b43c07dda17553eb56ecf3bb17ecb433a8c882710b650b1907aad96d171a92  sost-miner
212ecbddbfa6f77815e390e07b02687582ca7d6d955a9f34201cd9b8f39baf6c  sost-cli
```

## Install (new node from scratch)

```bash
# 1. download the three binaries + SHA256SUMS from the release, then verify
sha256sum -c SHA256SUMS        # must print: sost-node: OK / sost-miner: OK / sost-cli: OK
chmod +x sost-node sost-miner sost-cli
# 2. a full sync from genesis now completes — no chain.json seed needed:
./sost-node --genesis genesis_block.json --chain chain.json \
    --profile mainnet --rpc-user <you> --rpc-pass-file <file> --p2p-enc on
```

## Update (already running v16.2.x)

```bash
sha256sum -c SHA256SUMS
# stop the node by its PID (never pkill), swap the binary, start again:
systemctl stop sost-node               # or kill <PID>
cp sost-node /opt/sost/build/sost-node
systemctl start sost-node
# the miner binary is byte-identical in code to v16.2.3; swapping it is optional.
```

Consensus is unchanged, so a v16.3.0 node and a v16.2.3 node interoperate:
verified both directions, encrypted and plaintext, same tip, zero rejects.

## Rollback

```bash
sha256sum -c SHA256SUMS.v16.2.3        # keep the old binary + its hash
systemctl stop sost-node
cp sost-node.v16.2.3 /opt/sost/build/sost-node
systemctl start sost-node
```

No on-disk migration: the chain a v16.3.0 node writes is read unchanged by a
v16.2.3 node (the only difference is an explicit `"version":1` field on
pre-Phase-2 blocks, which the old binary already infers).

## Test results (on the release binary, commit 4b1e970f)

- **119/119** automated tests pass.
- **Full genesis→tip sync** to #26,973, encrypted and plaintext: same block
  hashes as the reference node across all 26,974 blocks, 0 rejects, all 66
  exceptions used once each (verified on the byte-identical `.text` binary).
- **Genesis sync through the 66 exceptions** re-verified on this exact build:
  47/47 + 19/19 used, 0 rejects, 0 invalid-block bans.
- **Adversarial**: a different block at an exception height is rejected; altered
  `subsidy` / rewards split / `x_bytes` / `round_witnesses` / `profile_index`
  all rejected; rate-limit abuse (unsolicited new blocks) still banned.

## Not changed

Consensus rules, reward economics, Jackpot V2 parameters, the mining algorithm,
and wallet formats are untouched.
