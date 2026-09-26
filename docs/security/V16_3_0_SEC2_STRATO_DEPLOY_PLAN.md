# sec2 — controlled, reversible STRATO deployment plan (DO NOT EXECUTE YET)

Awaiting EXPLICIT owner authorization to deploy. Deploy authorization is SEPARATE from the
publish authorization. Touches ONLY the node binary on the VPS — NOT the WSL miner, wallet,
NODE_BIND, consensus, or the scheduled #30,000 fork. Node-only swap; miner keeps running.

## Pre-flight (must all hold before starting)
- [ ] `sost-node-sec2` present on VPS; `sha256sum` == `5b50a448…` (verify the EXACT bytes to run).
- [ ] Current running node binary identified and its sha256 recorded (for rollback identity).
- [ ] Free disk for a full chain-state backup.
- [ ] A maintenance window; note the current block height and best-block hash.
- [ ] (Recommended) the interim proxy mitigation already applied, so exposure is closed even
      before the swap and the swap is not time-pressured.

## Backup (recoverable state)
1. `systemctl stop sost-node` (miner may keep running; it will reconnect).
2. Copy the data dir (chain.json + wallet/peers/state) to a timestamped backup dir on the VPS.
3. Copy the CURRENT node binary to `sost-node.rollback-<ts>` (records the exact pre-sec2 binary).
4. Record: pre-swap height, best-block hash, `sha256sum` of chain.json.

## Swap
5. Install `sost-node-sec2` as the node binary (keep the old one as the rollback copy).
6. `systemctl start sost-node`.

## Health checks (all must pass; else rollback)
7. Node boots: log shows `Node running`, `Chain: N blocks, height=<pre-swap height>` (no reload
   loss), `[RPC] Listening`, `[P2P] Listening`.
8. `getblockcount` == pre-swap height (± new blocks); `getbestblockhash` matches or advances.
9. Peers reconnect (`getpeerinfo` non-empty within a few minutes); height keeps advancing.
10. Miner still submitting (miner stats: accepted increments) — miner binary untouched.
11. Security confirm: `getblockhash ["str"]` → RPC error (not a crash); `getblock [[[[1]]]]` →
    error and RSS stays flat (the whole point of sec2).
12. No new reject/exception spam in the node log for ~10 min; chain does not stall.

## Rollback (if any check fails)
R1. `systemctl stop sost-node`.
R2. Restore the pre-sec2 binary (`sost-node.rollback-<ts>`).
R3. If chain state looks wrong, restore the backed-up data dir.
R4. `systemctl start sost-node`; confirm height/best-block match the pre-swap values.
R5. Re-apply the interim proxy mitigation if it was rolled back; capture logs; report.

## Notes
- The node loads chain.json atomically (verified: 5/5 SIGKILL-mid-reorg recoveries), so an
  interrupted start does not corrupt state; still, the data-dir backup is the belt-and-braces.
- Do the swap on ONE node first; only after it is healthy consider any others.
