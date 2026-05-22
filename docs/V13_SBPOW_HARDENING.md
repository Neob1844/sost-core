# V13 SbPoW hardening — preimage upgrade for the height-gated v13 fork

## TL;DR

At `V13_HEIGHT = 12000` the SbPoW signed preimage is upgraded from the
V11 layout (7 fields, 129 B) to a hardened V13 layout (11 fields, 205 B)
that additionally binds the block `timestamp`, `bits_q`, `merkle_root`,
and a chain-specific `genesis_hash` salt. Below `V13_HEIGHT` the
legacy V11 preimage remains in force so old blocks stay reproducible.

Activation is **height-gated only**. `header_version` stays at 2 — no
new wire format version. Every miner running V13 code automatically
switches preimages at the boundary; pre-V13 miners cannot produce
acceptable blocks at height ≥ 12000 (their V11-format signature does
not verify under the V13 preimage at the validator).

## Why

The V11 preimage covered `prev_hash`, `height`, ConvergenceX `commit`,
`nonce`, `extra_nonce`, and `miner_pubkey`. Four block fields it did
**not** cover left small but real non-outsourceability seams that a
disciplined pool could exploit:

1. **`timestamp`** — a pool could re-stamp the same PoW solution with
   different timestamps and re-sign without redoing the work. Pre-V13
   the signature was not invalidated by a timestamp change because
   timestamp was not in the preimage.
2. **`bits_q` (difficulty)** — at a difficulty boundary a pool could
   present the same PoW with two different `bits_q` values and have
   both accepted as long as the rest of the header matched. Under V13
   the difficulty is committed, so any `bits_q` rewrite invalidates
   the signature.
3. **`merkle_root`** — a pool could keep the PoW and rotate the
   transaction set (different fees, different censoring choices)
   without re-signing. Under V13 the tx-set commitment is part of
   the signed preimage.
4. **Chain-id (`genesis_hash`)** — V11 had **no network-specific
   salt**. A signature created on testnet for `(height, prev,
   commit, nonce, pubkey)` was bit-identical to a valid mainnet
   signature for the same tuple — a cross-chain replay surface that
   was not exploited in practice but was structurally open. Under
   V13 the genesis hash is bound to the preimage, so the chain
   identity is intrinsic to every signed block.

None of these gaps were Critical-in-the-blockchain-is-broken sense
under the V11 design, because the signing key was still required to
hold a valid mining identity, and the coinbase output binding
(`derive_pkh_from_pubkey(miner_pubkey) == coinbase_miner_pkh`) prevents
sig-key/spend-key spoofing. But the four omissions reduced the
*economic* friction of pool delegation more than the project's
non-outsourceability target accepts.

The V13 preimage **does not** introduce Memory-Lock. The Memory-Lock
proposal was evaluated and rejected — numerical analysis showed it
would penalise small miners more than rigs without materially
improving non-outsourceability. The decision is final for V13.

## The V13 preimage

```text
sbpow_message_v13 = SHA256(
    SBPOW_DOMAIN_TAG_V13   (16 B, "SOST/POW-SIG/v13", no NUL) ||
    genesis_hash           (32 B) ||   NEW v13  — closes cross-chain replay
    prev_hash              (32 B) ||
    height                 ( 8 B, LE) ||
    timestamp              ( 8 B, LE) ||   NEW v13  — closes timestamp re-stamp
    bits_q                 ( 4 B, LE) ||   NEW v13  — closes difficulty-fork
    commit                 (32 B) ||
    merkle_root            (32 B) ||       NEW v13  — closes tx-set mutation
    nonce                  ( 4 B, LE) ||
    extra_nonce            ( 4 B, LE) ||
    miner_pubkey           (33 B)
)
```

Total preimage length: **205 B**. Output is 32 B as before (SHA-256).
Field order is locked by `tests/test_sbpow_v13_hardening.cpp` (test 10,
`every v13 field is part of the preimage`).

## Code map

| Layer | File | Function / symbol |
|---|---|---|
| Domain tag constant | `include/sost/sbpow.h` | `SBPOW_DOMAIN_TAG_V13` |
| Preimage builder | `include/sost/sbpow.h` + `src/sbpow.cpp` | `build_sbpow_message_v13(...)` |
| Validation inputs | `include/sost/sbpow.h` | `ValidationInputs { ..., v13_height, timestamp, bits_q, merkle_root, genesis_hash }` |
| Validator branch | `src/sbpow.cpp` | `validate_sbpow_for_block(...)` — `if (in.height >= in.v13_height) use v13 preimage` |
| Wrapper | `include/sost/block_validation.h` + `src/block_validation.cpp` | `ValidateSbPoW(..., genesis_hash, phase2_height, v13_height, err)` |
| Node call site | `src/sost-node.cpp` | accept-block path passes `ts64`, `bits_q`, `mrkl32`, `g_genesis_hash`, `V13_HEIGHT` |
| Node RPC | `src/sost-node.cpp` | `handle_getinfo` exposes `"genesis_hash"` |
| Miner globals | `src/sost-miner.cpp` | `g_genesis_hash_for_sig`, `g_genesis_hash_loaded`, `ensure_genesis_hash_for_sig_loaded()` |
| Miner signing sites | `src/sost-miner.cpp` | both threaded + single-thread paths branch on `h >= sost::V13_HEIGHT` |

## Activation

- **Height gate**: `V13_HEIGHT = 12000` (set in `include/sost/params.h`).
- **No `header_version` bump**. V13 reuses `header_version = 2` from
  V11 Phase 2. The version gate is unchanged: pre-Phase 2 = v1, Phase 2
  (height ≥ 7100) = v2. The V13 change is preimage-only.
- **Backwards-reproducibility**: blocks at height < 12000 keep using
  the V11 preimage. Re-syncing the chain from genesis is bit-stable.
- **Genesis-hash source**:
  - On the validator: `g_genesis_hash` (already computed at node
    startup from the local genesis block — different on
    mainnet vs testnet).
  - On the miner: lazy-loaded via RPC `getinfo` the first time a
    block at height ≥ V13_HEIGHT is signed. Cached for the rest of
    the miner session. If the node does not return a usable
    `genesis_hash`, the miner aborts the candidate cleanly rather
    than emitting an unverifiable block.

## Migration / upgrade

| Operator action | Required? | When |
|---|---|---|
| Pull a V13-capable binary | YES | Before block 11999 — same UPGRADE WINDOW as the other V13 changes (see `docs/V13_RELEASE_CANDIDATE.md`). |
| Re-issue mining key | NO | The signing key is the same wallet key as in V11 Phase 2. |
| Reconfigure miner | NO | The miner detects `h >= V13_HEIGHT` automatically and fetches `genesis_hash` from the node. |
| Change CLI flags | NO | `--wallet PATH --mining-key-label LABEL` continues to work. |

A miner running a pre-V13 binary at height ≥ 12000 will emit V11-format
signatures. The validator computes the V13 preimage, the V11 signature
fails verification, and the block is rejected with
`SIGNATURE_INVALID`. There is no silent failure: the miner sees its
candidate rejected via RPC `submitblock`.

## Test coverage

`tests/test_sbpow_v13_hardening.cpp` — 12 test functions, 36
individual assertions, all passing:

1. `v13_vs_v11_differ` — V13 preimage differs from V11 for shared
   inputs.
2. `v13_happy_path` — freshly signed V13 block validates OK.
3. `timestamp_binding` — mutating timestamp → `SIGNATURE_INVALID`.
4. `bits_q_binding` — mutating `bits_q` → `SIGNATURE_INVALID`.
5. `merkle_root_binding` — mutating `merkle_root` →
   `SIGNATURE_INVALID`.
6. `cross_chain_replay` — swapping `genesis_hash` →
   `SIGNATURE_INVALID`.
7. `pre_v13_uses_v11_preimage` — at height < `v13_height`, V11
   preimage accepted (backwards compat); v13 fields ignored.
8. `boundary_at_v13_height` — at exactly height == `v13_height`, V11
   signature rejected (boundary is inclusive on the v13 side).
9. `coinbase_mismatch_under_v13` — V13 + mismatched coinbase pkh →
   `COINBASE_MISMATCH` (existing gate still fires).
10. `all_fields_committed` — mutating any single committed field
    yields a different message hash (locks field order).
11. `signature_does_not_cross_genesis` — same as 6, full-signature
    replay attempt.
12. `message_is_32_bytes_and_stable` — output size + determinism.

Pre-existing SbPoW tests (signing, validation, adversarial,
submit-integration) all continue to pass under the V13 wiring (their
height < `v13_height` fixture exercises the V11 path).

## Risk register

| Risk | Mitigation |
|---|---|
| Miner fails to fetch genesis_hash from a still-pre-V13 node at h ≥ 12000. | Miner aborts the candidate with an explicit `[MINER] FATAL` message and instructions to upgrade the node. No silent failure. |
| Tests inject `v13_height = INT64_MAX` (sentinel) and accidentally exercise the V13 path in production. | The miner code branches on `sost::V13_HEIGHT` (a `constexpr` in `params.h`) — there is no way to inject a finite test height into the live binary. |
| Future preimage extension (e.g. Beacon Phase III state binding) requires another version bump. | Add `build_sbpow_message_v14(...)` + new domain tag + new `v14_height` field. The validator branch ordering becomes `v14 > v13 > v11`. The change here establishes that pattern. |

## Out of scope

- **Memory-Lock per-instance** — REJECTED (numerical analysis showed
  worse outcomes for small miners). Will NOT be reopened.
- **PoW seed binding** (`derive_seed_v11`) — already a follow-up
  documented in the V11 spec. Not touched here.
- **PoPC / Gold Vault governance lifecycle** — deferred to V14 (see
  `docs/V13_POPC_GOLDVAULT_IMPLEMENTATION_PLAN.md` and
  `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md`).
- **Wallet privkey zeroing on shutdown** — separate hardening pass.
