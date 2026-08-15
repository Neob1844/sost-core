# V15 FINAL — cutover package

Status: **PREPARED, NOT EXECUTED.**

| File | Runs on | Purpose |
|---|---|---|
| `v15-final.env` | — | Single source of truth: commit, the four authoritative SHA256, paths, deadline height. Sourced by all scripts. |
| `V15_NODE_CUTOVER.sh` | build machine → VPS | **Step 1.** Verify → stage → re-verify on VPS → timestamped backup → stop/install/start → health-check. |
| `V15_MINER_CUTOVER.sh` | the mining machine | **Step 2, only after the node is healthy.** Auto-detects the live miner, replays its command line verbatim. |
| `V15_NODE_ROLLBACK.sh` | build machine → VPS | Restore the pre-cutover node binaries from a verified backup. |
| `V15_MINER_ROLLBACK.sh` | the mining machine | Restore the pre-cutover miner binary and command line. |

All four: `set -euo pipefail`, mandatory SHA256 verification that **aborts** before
installing anything, timestamped backups, `--dry-run` and `--list` where useful,
and rollbacks that are themselves reversible.

Order is enforced in code: `V15_MINER_CUTOVER.sh` refuses to run until the VPS
node's sha256 equals the release node hash.

## The `--realtime` flag

`V15_MINER_CUTOVER.sh` never composes a command line. It reads the live process's
`/proc/<pid>/cmdline` and replays it argument-for-argument, so `--realtime` is
preserved exactly as it is today. If no miner process is running, the script
**aborts** rather than guess — a miner started without `--realtime` stamps blocks
~600 s in the future and the node rejects every one of them.

## FINDING: the chain's active block producer is NOT ours

Established by measurement on 2026-08-15 (all read-only):

- Blocks keep arriving (~12 min apart: 22035 @15:18:02, 22036 @15:30:24,
  22037 @15:42:16 UTC).
- Across those blocks the node's `getblocktemplate` counter stayed at **10396**
  and `submitblock` at **6498** — **no RPC block submission at all**.
- The laptop's SSH tunnel (`-L 18232`) moved **52 bytes** across a block event:
  keepalive only. Sampling the WSL side at 0.1 s for ~14 minutes recorded
  **zero** connections to the tunnel port.
- No `sost-miner` process exists in this WSL instance (exhaustive `/proc` scan)
  nor on the VPS (`pgrep` empty). Windows interop is disabled here, so the
  Windows host and any other WSL distro cannot be enumerated from this machine.
- No mining traffic through the public path either: `getblocktemplate`/
  `submitblock` appear **0** times in the last 200 000 nginx access-log lines.
- `getpeerinfo`: the only peer at the tip is **175.158.x.x** (inbound, height
  tracks the tip exactly). The other three peers are stale (20896, 20896, 20285).
- The block-producing address `sost17a8985…` is **not present in any wallet on
  this laptop**, and this laptop's public egress is <laptop egress IP redacted> — a different
  network from the peer.

**Conclusion:** blocks are produced by an external node+miner at ~175.158.x.x and
reach the VPS over P2P. We do not operate it, cannot inspect it, and cannot patch
it. `V15_MINER_CUTOVER.sh` is still correct and required for *our* miner, but
running it changes nothing about who is currently advancing the chain.

## Consequence: block 30000 is a coordinated hard fork

The DTD-PoPC gate fix changes the **expected DTD lottery winner** from block
**30000** onward, and the winner is committed in the coinbase and enforced by
`CB13_LOTTERY_WINNER`:

- an **un-upgraded** node computes an EMPTY eligibility set → expects no winner;
- an **upgraded** node computes a non-empty set → expects a winner.

They will therefore reject each other's blocks from 30000. The reserve freeze at
**25000** is a narrower divergence (it only bites if a reserve-spending tx is
actually broadcast), but it is still a consensus rule change.

**The external miner MUST upgrade before block 30000, and should upgrade before
25000.** This needs a public miner notice; it cannot be solved by a script in
this directory. Treat it as a release blocker for the *fork*, not for the build.
