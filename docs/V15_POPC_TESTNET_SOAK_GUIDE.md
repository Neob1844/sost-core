# V15 PoPC — Live Testnet Soak Guide (operator package)

Run the live soak that signs off `docs/V15_POPC_SOAK_REPORT.md` before any
`DTD_POPC_GATE_CONSENSUS_ACTIVE` flip. **This guide touches only a separate
testnet chain — it does not affect mainnet, and the DTD-PoPC flag stays `false`
throughout.** All flags/commands below are quoted from the real binaries.

Testnet fork heights (built with `-DSOST_TESTNET_FORKS=ON`):
- **V15_HEIGHT = 300** — PoPC automation + Gold Vault governance go live.
- **DTD_POPC_ELIGIBILITY_HEIGHT = 1300** — DTD *would* start requiring PoPC (only if the flag were on; it is not).
- Audit interval 1440 blocks, grace 288 (so a contract activated near 300 stays good well past 1300).

---

## 1. Build the testnet binaries

```bash
cd /opt/sost            # or your checkout
git pull origin main    # ensure latest (P5 + soak tooling)

cmake -S . -B build-testnet -DCMAKE_BUILD_TYPE=Release \
      -DSOST_TESTNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON
cmake --build build-testnet -j"$(nproc)" sost-node sost-miner sost-cli popc15-carrier
```

Notes:
- `SOST_TESTNET_FORKS=ON` lowers the fork heights (V14=200, V15=300) — **testnet only**.
- `SOST_ENABLE_PHASE2_SBPOW=ON` keeps the real SbPoW path (mainnet uses it; harmless on testnet).
  `--profile testnet` skips the mainnet-only SbPoW strings self-check, so OFF also works if you prefer a lighter build.
- `popc15-carrier` is the carrier-payload generator (soak tooling).

Keep this build in its own dir (`build-testnet/`) so you never run it against mainnet data.

---

## 2. Start a testnet node + miner (separate chain, never touches mainnet)

Use a **separate chain file and ports**, and `--profile testnet` (different magic bytes ⇒ cannot
mix with mainnet peers):

```bash
# Node (testnet)
./build-testnet/sost-node \
  --profile testnet \
  --genesis genesis_block.json \
  --chain testnet_chain.json \
  --port 19334 --rpc-port 18233 \
  --rpc-user soak --rpc-pass soakpass &

# Miner (points at the testnet node's RPC)
./build-testnet/sost-miner \
  --profile testnet \
  --rpc 127.0.0.1:18233 --rpc-user soak --rpc-pass soakpass \
  --address <YOUR_TESTNET_ADDRESS> \
  --blocks 100000 --threads 2 &
```

CLI talks to the testnet node by pointing `--node` at its RPC port:
```bash
CLI="./build-testnet/sost-cli --node 127.0.0.1:18233 --rpc-user soak --rpc-pass soakpass"
$CLI getnewaddress         # create YOUR_TESTNET_ADDRESS, fund the miner to it
```

For the reorg test (step F) start a **second** node on other ports with its own chain file and
`--connect 127.0.0.1:19334`, then briefly partition it.

---

## 3. Soak steps (maps 1:1 to docs/V15_POPC_SOAK_REPORT.md)

Throughout, watch the node log and use `$CLI getinfo` / `getblockcount` for the tip height.

### A. Mine past block 300 (PoPC live)
Let the miner run to height ≥ 300. Confirm Gold Vault governance + PoPC carriers are now recognized
(pre-300 a carrier output is just an unspendable UTXO; from 300 the node decodes it).

### B. Register + Activate a valid contract (in the 300→1300 window)
Get your owner private key (the key for YOUR_TESTNET_ADDRESS):
```bash
$CLI dumpprivkey <YOUR_TESTNET_ADDRESS>      # -> OWNER_SK (64 hex)
```
Generate and broadcast the carriers (end height comfortably past 1300):
```bash
# Register (declares the commitment -> Pending)
REG=$(./build-testnet/popc15-carrier --event register --privkey <OWNER_SK> --model A --end 130000 \
        | sed -n 's/^.*--popc-carrier //p')
$CLI send <YOUR_TESTNET_ADDRESS> 0.00000001 --popc-carrier $REG

# Activate (owner-signed attestation -> Active). REUSE the SAME commitment_id the
# generator printed for Register (pass it with --commitment <64hex>).
ACT=$(./build-testnet/popc15-carrier --event activate --privkey <OWNER_SK> --model A --end 130000 \
        --commitment <COMMITMENT_ID_FROM_REGISTER> --balance 311035 --attest-height <CURRENT_HEIGHT> \
        | sed -n 's/^.*--popc-carrier //p')
$CLI send <YOUR_TESTNET_ADDRESS> 0.00000001 --popc-carrier $ACT
```
Expected: both txs accepted; after the Activate confirms, the owner holds an **Active** commitment.

### C. Register-only does NOT count
Post only a Register (no Activate) for a second commitment. Expected: it stays **Pending** — never
appears as active custody.

### D. Unauthorized carrier is ignored
Build a forged carrier whose owner_pkh ≠ signer and broadcast it:
```bash
BAD=$(./build-testnet/popc15-carrier --event renew --privkey <OWNER_SK> --model A --end 200000 \
        --commitment <COMMITMENT_ID> --forge-owner aabbccddeeff00112233445566778899aabbccdd \
        | sed -n 's/^.*--popc-carrier //p')
$CLI send <YOUR_TESTNET_ADDRESS> 0.00000001 --popc-carrier $BAD
```
Expected: the node **ignores** this event (signature not by the owner) — the commitment's state is
unchanged. (The tx itself may still confirm; the carrier event must not take effect.)

### E. Cross block 1300 with the flag false
Let the chain pass height 1300. Expected: **no miner is dropped from the lottery** — eligibility is
unchanged, because `DTD_POPC_GATE_CONSENSUS_ACTIVE` is `false` (the gate is wired but inert).

### F. Reorg around the gates
With a 2-node setup, partition the second node across height 300 (and again across 1300), let both
sides mine a few blocks, then reconnect. Expected: both nodes converge on the same chain and the
**same active-PoPC set** with no stale state (it is recomputed from the chain every block).

### G. Replay byte-identity
Replay the full **mainnet** chain with a mainnet binary built from this same commit and confirm the
UTXO-set root + height match the pre-V15 binary (gates deferred ⇒ no divergence):
```bash
./build/sost-node --profile mainnet --genesis genesis_block.json \
  --chain mainnet_chain.json --dry-run-replay
# compare the printed UTXO-set root + height against the previous release
```

---

## 4. Go / No-Go criteria

**GO (all must hold):**
- A: node crosses 300; PoPC carriers recognized; Gold Vault governance active; no crashes.
- B: Register then owner-signed Activate ⇒ commitment shows **Active**; owner eligible.
- C: register-only commitment stays **Pending** (never active).
- D: forged/unauthorized carrier has **no effect** on the commitment.
- E: crossing 1300 with the flag false changes **nobody's** eligibility.
- F: after reorg, all nodes agree on the identical active-PoPC set.
- G: mainnet replay UTXO-set root + height are **byte-identical** to the previous release.

**NO-GO (any of these blocks the flip):**
- A carrier with `owner_pkh != signer` (forged) actually changes commitment state.
- A register-only commitment counts as active.
- Nodes diverge / disagree on the active set after a reorg.
- Crossing 1300 drops or alters eligibility while the flag is false.
- Mainnet replay root/height differs from the previous release (any divergence).
- The node rejects well-formed carrier txs at the mempool so the flow can't run
  (if so: that mempool/standardness rule for the 0-value marker output is finding #1 to fix first).
- Any crash, assertion, or non-deterministic result.

Record heights, node IDs and the resulting state hashes in `docs/V15_POPC_SOAK_REPORT.md`
and sign off. **Only then** is a coordinated `DTD_POPC_GATE_CONSENSUS_ACTIVE` flip
(under a fresh, announced fork height) considered — never from this guide.

---

## What is NOT in scope here
- No mainnet changes. No flip of `DTD_POPC_GATE_CONSENSUS_ACTIVE`. No OTC/P2P work.
- This guide only prepares + runs the testnet soak. The flip is a separate, later, coordinated step.
```
