# SACS V2 — devnet lab evidence (activation=42, MAX_REORG_DEPTH=8)

Branch: feat/sacs-v2-deep-reorg (off V1 b59dcf5a). Devnet build, Release, SOST_DEVNET_FORKS=ON.
NOT built for mainnet, NOT merged, NOT deployed. STRATO untouched.

## Activation-boundary lab (sacs_v2_boundary.sh) — REAL NODES

### PRE_ACTIVATION  fork_point=5 (< 42), depth 9 > cap 8
common H=5 (0x2b64); A h=15 (0x301c, heavier+taller); B(active) h=14 (0x3002).
Decision: "[REORG] Rejected: depth 9 exceeds REORG_LIMIT 8"
B keeps its own chain (tip != A). => LEGACY HARD REJECT. Pre-fork history protected.
RESULT: PASS

### POST_ACTIVATION  fork_point=44 (>= 42), depth 9 > cap 8
common H=44 (0x30b4); A h=54 (0x30be, heavier); B(active) h=53 (0x30bd).
Decision log (B):
  [REORG][SACS-V2] Deep reorg: fork_point=44 depth=9 exceeds cap 8 — ALARM +
     full-validation path (fork_point>=SACS_V2_ACTIVATION_HEIGHT). Winner decided
     by strictly higher VALID work, never height.
  [REORG][SACS] fork_point=44 disconnect_count=9 connect_count=10
     active_chainwork=0x30bd candidate_chainwork=0x30be
  [REORG] Disconnecting 9 blocks (h=45..53), connecting 10
B converged to A (tip ebbab0fd..., h=54). Adopted ONLY because candidate work
(0x30be) > active work (0x30bd). => V2 DEEP-REORG PROCEED.
RESULT: PASS

## Interpretation
Same depth (9 > cap 8), OPPOSITE outcome decided purely by fork_point vs activation
height, and the post-activation reorg proceeded ONLY on strictly-greater cumulative
work (never height). Boundary semantics = as specified.

## Still pending (adversarial suite — NOT yet run; do not treat as done)
off-by-one fork_point 41/42/43; depth matrix at larger scale; CASE A taller-but-lower-work
reject; CASE D invalid-high-work reject; A/B/C partition; eclipse; private-chain;
crash/disk-full/SIGKILL mid-reorg; resource bounds; wallet/DEX/CEX reconciliation;
old-node (no V2) vs new-node divergence; final regression + consensus-diff allowlist + RC.
