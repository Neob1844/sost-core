# SOST v16.3.0 — Security revision "sec1" (node-only, NON-CONSENSUS)

Candidate commit (frozen): **260ffd02** on `feat/fork-store-hardening`.
Baseline: **v16.3.0** (`ec2bea2c`). Not published, not deployed — pending owner authorisation.

## 1. What this release is

A node-only, non-consensus security update over v16.3.0. It fixes availability and
resource-exhaustion defects found in the adversarial lab; it changes **no** consensus
rule. Miner and CLI are **byte-identical to v16.3.0/v16.2.3** — operators swap only
`sost-node`.

| Fix | What it does | Consensus? |
|-----|--------------|-----------|
| V1 | Fork/orphan index poisoning — per-IP + per-/24 quotas with eviction; honest forks still admitted | No |
| V2 | ACTIVE entries no longer share the fork cap; transient-only accounting | No |
| V3 | Subnet false-positive — honest peer sharing a /24 with attackers is not blocked | No |
| V4 | Security CI (unit+consensus, ASan/UBSan, fuzz-smoke) | No |
| V5 | tx/block deserialiser fuzzing (corpus retained) | No |
| **V6** | **SIGPIPE ignored** — a peer closing mid-write no longer kills the node (DoS) | No |
| P4 | P2P frame parser extracted to `sost/p2p_frame.h` so the fuzzer tests production code (behaviour-identical) | No |

## 2. Binaries and hashes

Built in the canonical `build/` directory (Ubuntu 22.04.5, gcc 11.4.0, glibc 2.35),
`-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release`.

```
c2b06b91eb9da9f4736cd514df3f7e7616a8961f46b17442d7c171c2f345ac2c  sost-node    (v16.3.0 (security revision sec1) — new; was 304d056d… in v16.3.0)
2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  sost-miner   (byte-identical to v16.3.0/v16.2.3)
489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  sost-cli     (byte-identical to v16.3.0/v16.2.3)
```

> The node hash is finalised from a CLEAN reproducible build before publication
> (see §5). The miner/cli hashes above already reproduce the published v16.3.0
> values exactly, which is direct evidence the `build/` directory is reproducible.

## 3. Update procedure — SWAP THE NODE ONLY

Only `sost-node` changed. The miner and CLI are the same binaries as v16.3.0 — do
not stop or reinstall the miner. Activation at #30,000 is automatic by height; no
restart is required at that block.

```bash
# 0. download + verify (all three lines must say OK; miner/cli will match what you already run)
sha256sum -c SHA256SUMS

# 1. back up the running node binary and its hash (one-command rollback)
TS=$(date -u +%Y%m%d-%H%M%S)
cd /path/to/your/build
cp -a sost-node sost-node.v1630.$TS
sha256sum sost-node.v1630.$TS > sost-node.v1630.$TS.sha256

# 2. swap the node
sudo systemctl stop sost-node          # or kill its exact PID
sudo install -m 0755 ~/sost-v1631/sost-node /path/to/your/build/sost-node
sudo systemctl start sost-node
sleep 20 && systemctl status sost-node --no-pager | head -8

# 3. verify the RUNNING binary is the new one
PID=$(systemctl show sost-node -p MainPID --value)
sha256sum "$(readlink -f /proc/$PID/exe)"     # must equal the v16.3.0 (security revision sec1) node hash

# the miner keeps running untouched — its binary did not change.
```

## 4. Rollback plan

The on-disk chain format is unchanged (v16.3.0 (security revision sec1) and v16.3.0 read the same files),
so rollback is one binary and nothing else — no reindex, no migration.

```bash
sudo systemctl stop sost-node
sudo install -m 0755 /path/to/your/build/sost-node.v1630.<timestamp> /path/to/your/build/sost-node
sudo systemctl start sost-node
```

Caveat: v16.3.0 (security revision sec1), like v16.3.0, is required for a full sync from genesis. Roll back
only a node that is already synced. A v16.3.0 (security revision sec1) node and a v16.3.0 node interoperate
in both directions (verified — §5 of the acceptance report).

## 5. Reproducible build (to finalise the node hash before publishing)

```bash
git clone --depth 1 --branch <v16.3.0 (security revision sec1) tag> https://github.com/Neob1844/sost-core.git src && cd src
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"
sha256sum build/sost-node build/sost-miner build/sost-cli
```
The build directory MUST be named `build` (the source path is normalised out of
the binary, the directory name is not). Matching hashes are guaranteed only for the
environment above; a different toolchain legitimately produces a different hash.
