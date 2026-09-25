# SOST v16.3.0 — Security revision "sec1" (node-only, NON-CONSENSUS)

Public version stays **v16.3.0**. Revision label **sec1**. Source commit **1a675744**
(revision tag **v16.3.0-sec1**). Baseline v16.3.0 (`ec2bea2c`). Not published, not
deployed — pending owner authorisation.

## 1. What this revision is

A node-only, non-consensus security revision of v16.3.0. It fixes availability and resource-exhaustion defects found in the adversarial lab, plus a
pre-existing base64 signed-shift UB reachable over P2P (beacon notices); it changes **no**
consensus rule. `sost-miner` and `sost-cli` are **byte-identical to v16.3.0** — operators swap
only the node.

| Fix | What it does | Consensus? |
|-----|--------------|-----------|
| V1 | Fork/orphan index poisoning — per-IP + per-/24 quotas with eviction; honest forks still admitted | No |
| V2 | ACTIVE entries no longer share the fork cap; transient-only accounting | No |
| V3 | Subnet false-positive — honest peer sharing a /24 with attackers is not blocked | No |
| V4 | Security CI (unit+consensus, ASan/UBSan, fuzz-smoke) | No |
| V5 | tx/block deserialiser fuzzing (corpus retained) | No |
| **V6** | **SIGPIPE ignored** — a peer closing mid-write no longer kills the node (DoS) | No |
| P4 | P2P frame parser extracted to `sost/p2p_frame.h` so the fuzzer tests production code (behaviour-identical) | No |

## 2. Assets and hashes

The revised node is published as a **new, distinctly-named asset** on the existing
v16.3.0 release, so the original `sost-node` stays downloadable for traceability.

```
d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213  sost-node-sec1   (NEW — the revised node)
2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  sost-miner       (unchanged, == v16.3.0)
489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  sost-cli         (unchanged, == v16.3.0)
304d056d504960b4179543672f14bee28146788b985363a5e95d476cc6b1492e  sost-node        (ORIGINAL v16.3.0, kept for traceability)
```

Reproducible: built in a directory named `build`, Ubuntu 22.04.5 / gcc 11.4.0 /
glibc 2.35, `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF
-DCMAKE_BUILD_TYPE=Release`. A clean build and an incremental build both produce the
node hash above; the miner/cli hashes reproduce the published v16.3.0 values exactly.

## 3. Update procedure — SWAP THE NODE ONLY

Only the node changed. Do **not** stop or reinstall the miner. Activation at #30,000
is automatic by height; nothing to restart at that block.

```bash
# 0. download the sec1 node + its manifest into an EMPTY directory and verify
mkdir -p ~/sost-sec1 && cd ~/sost-sec1
curl -fsSL -O https://github.com/Neob1844/sost-core/releases/download/v16.3.0/sost-node-sec1
curl -fsSL -O https://github.com/Neob1844/sost-core/releases/download/v16.3.0/SHA256SUMS.sec1
sha256sum -c SHA256SUMS.sec1          # must print exactly:  sost-node-sec1: OK
chmod +x sost-node-sec1

# 1. back up the node binary you currently run, with its hash (one-command rollback).
#    Replace BUILD with the directory your node binary lives in.
BUILD=/path/to/your/build            # <-- your node's directory
TS=$(date -u +%Y%m%d-%H%M%S)
cp -a "$BUILD/sost-node" "$BUILD/sost-node.orig.$TS"
sha256sum "$BUILD/sost-node.orig.$TS" > "$BUILD/sost-node.orig.$TS.sha256"

# 2. install the sec1 node AS sost-node (swap). The miner is NOT touched.
sudo systemctl stop sost-node         # or kill the node's exact PID
sudo install -m 0755 ~/sost-sec1/sost-node-sec1 "$BUILD/sost-node"
sudo systemctl start sost-node
sleep 20 && systemctl status sost-node --no-pager | head -8

# 3. verify the RUNNING node is the sec1 build (not the file on disk)
PID=$(systemctl show sost-node -p MainPID --value)
sha256sum "$(readlink -f /proc/$PID/exe)"
#    must equal  d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213
```

The miner keeps running untouched — its binary did not change. On Windows/WSL the same
idea applies: stop the node process (Ctrl+C or `kill` its PID), install `sost-node-sec1`
in place of `sost-node`, start it again with your usual command; the miner stays up.

## 4. Rollback plan

The on-disk chain format is unchanged (sec1 and the original v16.3.0 read the same
files), so rollback is one binary — no reindex, no migration.

```bash
BUILD=/path/to/your/build
sudo systemctl stop sost-node
sudo install -m 0755 "$BUILD"/sost-node.orig.*  "$BUILD/sost-node"   # the backup from step 1
sudo systemctl start sost-node
```

Caveat: sec1, like v16.3.0, is required for a full sync from genesis — roll back only a
node that is already synced. A sec1 node and a v16.3.0 node interoperate in both
directions (verified — see the acceptance report).

## 5. Reproducible build (to confirm the node hash from source)

```bash
git clone --depth 1 --branch v16.3.0-sec1 https://github.com/Neob1844/sost-core.git src && cd src
git rev-parse HEAD          # the sec1 revision commit
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"
sha256sum build/sost-node       # must equal d3212aea…
```
The build directory MUST be named `build` (the source path is normalised out of the
binary, the directory name is not). Matching hashes are guaranteed only for the
environment in §2; a different toolchain legitimately produces a different hash.
