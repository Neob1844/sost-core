# Gate 8 — Release composition & naming (proposal)

## One source, one commit, one set of binaries, one SHA256SUMS, one guide
- **Source commit (candidate):** `eca62d7d` on `feat/p2p-autonomy-d1` (off `v30000`/`c9e0d629`).
- **Binaries:** sost-node, sost-miner, sost-cli — built once from that commit with the
  mandatory flags `-DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON
  -DSOST_TESTNET_FORKS=OFF` on the pinned toolchain (gcc 11.4.0 / binutils 2.38 /
  cmake 3.22.1, Ubuntu 22.04).
- **SHA256SUMS.txt:** the single cryptographic source of truth for operators.
- **Operator guide:** one upgrade guide; **activation height stays #30,000** — this is a
  binary/P2P revision of the v30000 line, NOT a consensus or schedule change.

## Naming proposal
Primary: **V30000 (one release; the improved candidate = V30000 FINAL CANDIDATE)** — reads as "the v30000 consensus line, binary revision 1".
It keeps #30,000 unambiguous, matches the dotted-tag convention already in use
(v16.2.3), and signals to operators that consensus is unchanged from v30000 while the
node binary gained the D1/D2 peer-autonomy layer. The deployed `v30000` (`c9e0d629`,
node 78fefb67) stays valid and fork-compatible; `V30000 FINAL CANDIDATE` is a drop-in node upgrade.

Alternative: `v30000-final`. Rejected as primary because the deployed v30000 is already
live and "final" would wrongly imply it was provisional.

## Composition rule (enforced)
- miner and cli are byte-identical to v30000 in a controlled build (Gate 1) — they are
  republished in V30000 FINAL CANDIDATE ONLY so the release is one coherent set with one SHA256SUMS;
  their code did not change.
- node is the only binary with a code delta (sost-node.cpp +310/-36, P2P only).
- Zero consensus files changed vs v30000 (Gate 5).
