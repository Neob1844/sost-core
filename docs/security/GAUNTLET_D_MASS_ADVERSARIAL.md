# Gauntlet D — mass adversarial lab (isolated, reproducible)

Isolated lab (devnet, localhost only — NOT run against STRATO or mainnet). Peers are
**SIMULATED** via a protocol-accurate Python client (`sostpeer.py`: real SOST wire framing
`[u32 P2P_MAGIC][4B cmd][u32 len][payload]`, VERS handshake incl. VACK) — NOT hundreds of real
full nodes. One real victim node + one real honest node + N simulated adversarial peers.

## Adversarial behaviors (mixed across N peers)
fake-height-then-silent · orphan/malformed BLCK flood · GETB serving-saturation flood ·
connect/disconnect churn · handshake-then-silent · raw frame junk (bad magic/oversize/partial) ·
duplicate-block spam. Resource + time limits enforced (40–60 s windows, bounded threads on a
14-core/12 GB host).

## Results — victim = sec2 node (200 sim-peers, 40–60 s)
| metric | result |
|---|---|
| peak RSS | **9 MB (flat)** |
| CPU | 2–4 % |
| RPC availability during storm | **20/20 (and 14/14)** samples, avg latency 3–4 ms |
| connection attempts absorbed | 24k–34k (churn) |
| fork-store orphans (max) | **2** (cap 200 — malformed flood did NOT saturate it) |
| crashes / OOM | **0** |
| unfair penalties on the honest peer (127.0.0.1:20102) | **0** |

The node closes misbehaving/half-open adversarial sockets promptly; resource use is flat
regardless of connection volume. No download-queue or fork-store blow-up.

## Results — victim = P2P-fix node (150 sim-peers, 45 s) — convergence UNDER attack
Victim on a divergent chain (h15) dialing an honest higher-work peer (h20) while 150 adversarial
peers attack: **converged to the honest peer's h20 tip under the noise**, RSS 11 MB, RPC 15/15,
0 crashes, orphans max 3, **0 unfair bans on the honest peer**. Automatic recovery to the common
valid chain, no manual intervention.
(On the sec2 node, convergence to a divergent fork does NOT occur — that is sec1's height-based
sync; the convergence fix lives on `feat/p2p-headers-first-ibd` and is integrated/re-tested in
Phase 3.)

## Coverage limits (honest)
- SIMULATED peers, not real independent nodes (real-operator diversity is a separate,
  externally-dependent milestone — Phase 5).
- Eclipse/partition are exercised via the honest+adversarial mix + convergence; a full
  many-real-node eclipse test needs the multi-operator lab (Phase 5), marked accordingly.

## Reproduce
`tests/security/gauntlet_D/run_D.sh [N] [seconds]`  (env `GD_BIN`/`MINER` to target another build).
