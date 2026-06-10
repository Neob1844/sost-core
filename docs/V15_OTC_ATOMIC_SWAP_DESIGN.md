# V15 OTC / P2P Atomic Swap — Design & Impact Map (OTC-0)

Non-custodial, bridge-less, escrow-less cross-chain swaps between SOST and
BTC / ETH / BNB / USDT / USDC / PAXG / XAUT, using Hashed-Time-Locked Contracts
(HTLC) on each side. **No funds ever pass through the SOST Foundation. No human
escrow. No bridge. No oracle in the consensus path.**

> Build-now / flip-later. Every consensus gate ships at `INT64_MAX` (mainnet
> no-op, byte-identical replay). The activation flip is a separate, explicit,
> coordinated decision after soak + review — never in this phase. This mirrors
> PoPC V15 (`POPC_V15_ACTIVATION_HEIGHT`) and Gold Vault (`GV_SLICE1_*`).

---

## 0. Current state (audit) — what already exists vs what's missing

There is substantial groundwork already, **but it lives on the branch
`feat/atomic-swap-htlc-v13-candidate`, NOT on `main`**, and is gated OFF.

| Component | Where | Status |
|---|---|---|
| HTLC activation gate (`atomic_swap_htlc_active_at`, `INT64_MAX`) | feat: `include/sost/atomic_swap.h` | scaffolding, dormant |
| `OUT_HTLC_LOCK 0x12 / CLAIM 0x13 / REFUND 0x14` (proposed) | feat: design + partial LOCK | **LOCK structural validation only**; CLAIM/REFUND **not** implemented (gate forced back to `INT64_MAX` to avoid permanent locks) |
| BTC HTLC redeem-script builder (P2WSH, `OP_SHA256`+`OP_CLTV`) | feat: `include/sost/atomic_swap_btc.h`, `src/atomic_swap_btc.cpp` | complete (pure byte-assembly, no signing) |
| BTC signing backend (libwally) | feat: `atomic_swap_btc_signing.*`, gate `SOST_BTC_HTLC_SIGNING` | exists, **OFF** by CMake flag |
| EVM HTLC contract (ETH/BNB/ERC-20) | feat: `contracts/atomic-swap/src/AtomicSwapHTLC.sol` (+28 tests) | coded, **not deployed/audited** |
| Local swap coordinator state machine | feat: `atomic_swap_coordinator.*` | complete, **local-only** (no chain/sign/network) |
| Helpers (sha256 preimage/hashlock) | feat: `atomic_swap_helpers.*` | complete |
| Tests (BTC script/signing/vectors, coordinator, e2e-sim, htlc lock/helpers/rpc) | feat: `tests/test_atomic_swap_*` | ~8 files, dormant |
| Design docs (map, plan, assets, BTC/EVM decisions, reviews) | feat: `docs/design/ATOMIC_SWAP_*` | ~20 docs |
| `SOSTEscrow.sol` (PoPC Model B gold timelock) | **main**: `contracts/SOSTEscrow.sol` | active design (separate from OTC) |
| `OUT_BOND_LOCK 0x10` / `OUT_ESCROW_LOCK 0x11` | **main**: live since block 10000 | **the reference primitive** for HTLC typed locks |
| libwally-core 1.5.3 | **main**: `vendor/libwally-core/` | vendored |

**Missing for a working V15 OTC swap:** HTLC CLAIM/REFUND consensus rules + a
clean integration of the feat-branch groundwork into `main`, wallet/RPC builders,
a non-custodial watcher/resume, and the cross-chain wiring.

---

## 1. Non-custodial architecture (principles — non-negotiable)

1. **Funds never touch SOST Foundation.** Every leg is locked by the *parties'*
   own keys into an HTLC on its own chain. The protocol only defines the lock and
   the two spend paths.
2. **One secret, two locks.** A 32-byte preimage `S`; `H = SHA-256(S)` is the
   hashlock used identically on the SOST side, the BTC redeem script, and the EVM
   contract. Claiming one side reveals `S`, enabling the claim of the other.
3. **Timeout ordering is a safety invariant.** Two absolute timeouts `T1` (the
   side that must be claimable *longer*) and `T2` (`T2 < T1`). The party who
   moves second must have the *shorter* refund window so they cannot be cheated.
   Concretely (from the coordinator boundary doc): **the initiator's refund must
   open LAST; the responder's refund must open FIRST.** The wallet computes and
   enforces this; a swap with bad timeout ordering is refused before any lock.
4. **Claim/refund are automatic.** The wallet/CLI (and an optional watcher)
   claim with the preimage when the counterparty locks, and refund after timeout
   if the swap stalls — no manual steps, resumable after a restart.
5. **SOST consensus never reads another chain.** Determinism requires that block
   validation depends only on SOST chain state. Cross-chain awareness lives
   entirely in the wallet/watcher (off-chain), never in a consensus rule.

---

## 2. What REQUIRES SOST consensus (the only consensus surface)

A minimal, deterministic HTLC primitive, modelled exactly on the existing
BOND_LOCK / ESCROW_LOCK typed outputs (proven since block 10000).

### 2.1 Output / tx types (proposed)
- `OUT_HTLC_LOCK = 0x12` — locks SOST under `hashlock + refund_height + claim_pkh + refund_pkh`.
- `OUT_HTLC_CLAIM = 0x13` — spend path; requires a preimage `S` with `SHA-256(S)==hashlock` **and** a `claim_pkh` signature, before `refund_height`.
- `OUT_HTLC_REFUND = 0x14` — spend path; requires a `refund_pkh` signature **and** `height >= refund_height`.

(Alternative shape — encode CLAIM/REFUND as ordinary spends of the LOCK utxo
with a witness rather than new output types — is on the table; the LOCK output +
two spend rules is the consensus core either way.)

### 2.2 LOCK payload (parallels ESCROW_LOCK's 28-byte payload)
```
hashlock(32) | refund_height(u64 LE,8) | claim_pkh(20) | refund_pkh(20)   = 80 bytes
```
Add `HTLC_LOCK_PAYLOAD_LEN / HTLC_CLAIM_PAYLOAD_LEN / HTLC_REFUND_PAYLOAD_LEN`
to `include/sost/tx_validation.h`, beside `BOND_LOCK_PAYLOAD_LEN / ESCROW_LOCK_PAYLOAD_LEN`.

### 2.3 Deterministic validation rules (all gated by `atomic_swap_htlc_active_at(height)`)
- **LOCK** (structural — already drafted on feat): well-formed payload, `value >= DUST`, `refund_height > height`. Pre-activation a LOCK output is rejected (R11) ⇒ byte-identical replay.
- **CLAIM**: spends a LOCK utxo; witness carries `S`; require `SHA-256(S)==hashlock`, valid `claim_pkh` signature over the spend, and `height < refund_height`. The revealed `S` is now on the SOST chain for the counterparty's wallet to read.
- **REFUND**: spends a LOCK utxo; require valid `refund_pkh` signature and `height >= refund_height`.
- **Mutual exclusion**: once a LOCK utxo is spent (by CLAIM or REFUND) it is gone from the UTXO set — the other path is automatically unspendable. No extra rule needed; the UTXO model gives atomicity for free.
- **Indexing for wallet/RPC**: the node exposes (read-only RPC) the open HTLC locks, their hashlocks, timeouts, and — crucially — any **revealed preimage** from a CLAIM (so the counterparty wallet can auto-claim the other leg). Read-only, gated, no consensus impact (precedent: `getpopcv15status`).

### 2.4 NOT consensus (deliberately off-chain)
Orderbook / maker-taker board, matching, pricing, the swap UI/wizard, reputation,
counterparty-chain monitoring, and the legal/issuer warnings. None of these may
ever influence SOST block validation.

---

## 3. Cross-chain flows

Notation: Alice has SOST, wants BTC/ETH/…; Bob has the other asset. `S` secret,
`H=SHA-256(S)`. `T1` later timeout, `T2` earlier timeout (`T2 < T1`).

### 3.1 SOST ↔ BTC (cleanest, fully trust-minimized)
1. Alice picks `S`, computes `H`. Alice LOCKs SOST: `OUT_HTLC_LOCK(H, refund_height=T1, claim_pkh=Bob, refund_pkh=Alice)`.
2. Bob verifies the SOST lock, then funds a **BTC P2WSH HTLC** with the same `H`, `claim=Alice`, `refund=Bob`, `OP_CHECKLOCKTIMEVERIFY=T2` (`T2<T1`). (Redeem script already built by `BuildBtcHtlcRedeemScript`.)
3. Alice claims BTC by publishing a BTC tx that reveals `S` (BTC witness). 
4. Bob reads `S` from the BTC chain and CLAIMs the SOST lock with `S` before `T1`.
5. If either stalls: after `T2` Bob refunds BTC; after `T1` Alice refunds SOST. Ordering (`T2<T1`) guarantees the second mover can't be stranded.

### 3.2 SOST ↔ ETH / BNB (EVM HTLC contract)
Same five-step dance; the EVM leg is `AtomicSwapHTLC.sol` (`lock/claim/refund`,
`SHA-256` hashlock, **absolute `block.number`** timeout). BNB Chain is EVM-identical;
timeouts are computed in *that chain's* block heights (≈3s blocks) — the wallet
does the unit conversion. BNB/ETH at the asset level are not issuer-freezable.

### 3.3 SOST ↔ USDT / USDC / PAXG / XAUT (issuer-token — atomic*)
Same EVM HTLC contract (ERC-20 `approve`+`lock`). **Issuer-freeze risk:** Tether
(USDT, XAUT), Circle (USDC) and Paxos (PAXG) can freeze the address holding the
locked token mid-swap, which breaks atomicity for that leg (the token becomes
uncollectible until/unless unfrozen). **Design requirements:**
- The wallet/UI MUST show an explicit *issuer-freeze* warning before any
  issuer-token swap; the "atomic" label carries an asterisk for these assets.
- Recommend small amounts and prefer ETH/BNB/BTC for trust-minimized swaps.
- This is a UX/warning requirement, **not** a consensus rule.

| Asset | Chain | Mechanism | Trust-minimized | Issuer-freeze |
|---|---|---|---|---|
| BTC | Bitcoin | Script HTLC (P2WSH) | yes | no |
| ETH | Ethereum | Solidity HTLC | yes | no |
| BNB | BNB Chain | Solidity HTLC | yes | no (asset-level) |
| USDT | Eth/Tron | Solidity HTLC | partial | **YES (Tether)** |
| USDC | Ethereum | Solidity HTLC | partial | **YES (Circle)** |
| PAXG | Ethereum | Solidity HTLC | partial | **YES (Paxos)** |
| XAUT | Ethereum | Solidity HTLC | partial | **YES (Tether Gold)** |

---

## 4. Phases (build-now, flip-later)

- **OTC-0** ✅ (this doc) — design + impact map; confirm groundwork lives on the feat branch; gates stay `INT64_MAX`.
- **OTC-0.5** ✅ DONE — ported the *pure, non-consensus* dormant groundwork from
  `feat/atomic-swap-htlc-v13-candidate` onto `main`, all gated/OFF, mainnet byte-identical:
  - `include/sost/atomic_swap.h` — activation gate `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX`
    + `atomic_swap_htlc_active_at()` (cleaned: the stray local `V14_HEIGHT` redefine was removed so
    it never shadows `params.h`; doc now points at `V15_HEIGHT`).
  - `atomic_swap_btc.{h,cpp}` — BTC P2WSH HTLC redeem-script builder (pure byte assembly).
  - `atomic_swap_btc_signing.{h,cpp}` — signing surface compiled as **inert stubs** (every call returns
    `ok=false`) unless built with `-DSOST_BTC_HTLC_SIGNING=ON` (an OTC-3 step; default OFF).
  - `atomic_swap_coordinator.{h,cpp}` — local swap state machine (no chain, no signing, no network).
  - Tests wired into CMake + CI hard-gate: `test-atomic-swap-btc-script`, `-btc-test-vectors`,
    `-btc-signing`, `-coordinator`, `-e2e-sim`. full ctest **80/80** on mainnet AND testnet.
  - EVM artifacts (not C++-built): `contracts/atomic-swap/{README.md,foundry.toml,src/AtomicSwapHTLC.sol,
    test/AtomicSwapHTLC.t.sol,test/mocks/MockERC20.sol}` (forge-std fetched via `forge install`, not vendored).
  - All ~20 atomic-swap design docs ported under `docs/{design,release,reviews}/ATOMIC_SWAP_*`.
  - **Deferred to OTC-1 (consensus surface):** `atomic_swap_helpers.{h,cpp}` and the
    `test_atomic_swap_htlc_{lock,helpers,rpc}` tests were NOT ported, because they require the
    `OUT_HTLC_LOCK/CLAIM/REFUND` output types + payload parsers in `transaction.h`/`tx_validation.*`.
    The feat branch forked from `main` **before** the V15 PoPC/Gold-Vault work, so its versions of the
    shared consensus files must NOT be taken wholesale — those additions will be hand-grafted onto
    current `main` in OTC-1 together with the CLAIM/REFUND rules (LOCK+CLAIM+REFUND as one gated set,
    so there is never a LOCK without a spend path).
- **OTC-1 — SOST-side HTLC consensus** ✅ DONE — hand-grafted the complete LOCK+CLAIM+REFUND
  consensus core onto current `main` (no V15 shared files overwritten), all gated by
  `atomic_swap_htlc_active_at()` (gate still `INT64_MAX` → mainnet byte-identical / no-op):
  - **Types** (`transaction.h`): `OUT_HTLC_LOCK 0x12`, `OUT_HTLC_CLAIM_WITNESS 0x13` (carries the
    32-byte preimage), tx types `TX_TYPE_HTLC_CLAIM 0x10` / `TX_TYPE_HTLC_REFUND 0x11`. CLAIM/REFUND
    are **spend paths of the LOCK utxo** (not new output types) — a LOCK can never exist without both.
  - **Payload** (`transaction.h`): `HTLC_LOCK_PAYLOAD_LEN=80` = `[hashlock(32)|refund_height(8 LE)|claim_pkh(20)|refund_pkh(20)]`;
    `HTLC_CLAIM_WITNESS_PAYLOAD_LEN=32` = preimage; pure short-payload-tolerant reader/writer helpers.
  - **Rules** (`tx_validation.{h,cpp}`, codes R17–R24): R11 type-activation gate; R17 LOCK payload
    (80B, `refund_height > height`, amount ≥ DUST); R18 witness payload (32B, only in a CLAIM tx); R2
    tx-type gate; R19 CLAIM structure (1 input, exactly 1 witness marker); R20 a LOCK is only spendable
    by CLAIM/REFUND (and CLAIM/REFUND only spend a LOCK); R21 `sha256(preimage)==hashlock`; R22 CLAIM
    strictly before `refund_height`; R23 REFUND structure (no witness marker); R24 REFUND only at/after
    `refund_height`. CLAIM verifies the signature against `claim_pkh`, REFUND against `refund_pkh`
    (both overriding the LOCK's own `pubkey_hash`). The UTXO model makes CLAIM and REFUND mutually
    exclusive (one output spent once) → claim-then-refund and refund-then-claim are both impossible.
  - **Helpers + read-only RPC** (`atomic_swap_helpers.{h,cpp}`, all gated): unsigned LOCK/CLAIM/REFUND
    tx builders; `createhtlclock/claimhtlc/refundhtlc/decodehtlc/gethtlcstatus` pure handlers over an
    `IUtxoView` — list locks, report `locked/claimed/refunded/expired`, and expose a revealed preimage
    so the counterparty's watcher can claim the mirror HTLC. No broadcast, no signing, no network.
  - **Tests**: `test-atomic-swap-htlc-{lock,helpers,rpc}` cover valid + every adversarial path (bad
    payload, wrong preimage, claim-after-timeout, refund-before-timeout, refund-by-non-owner, mutual
    exclusion, pre-activation no-op, byte-identical replay with gate off). **Full ctest 88/88** green;
    the 85 pre-existing tests unchanged → no consensus regression, mainnet untouched.
- **OTC-2 — wallet + automation** — wallet builders (`createhtlclock/claimhtlc/refundhtlc/decodehtlc/gethtlcstatus`), the maker/taker order board (off-chain), and the non-custodial **watcher**: auto-claim on counterparty lock + preimage reveal, auto-refund after timeout, resume after restart, with timeout-ordering enforcement.
- **OTC-3 — cross-chain legs** — enable BTC signing (libwally) behind review; deploy + external-audit the EVM `AtomicSwapHTLC.sol`; issuer-freeze warnings in wallet/UI; end-to-end testnet swaps (SOST↔BTC regtest, SOST↔EVM testnet).
- **OTC-FLIP** — only after soak + external cryptographic/economic review: a single-line flip of `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` from `INT64_MAX` to the chosen V15-era height. Separate, explicit, coordinated. Rollback = back to `INT64_MAX`, no fork.

---

## 5. Gates & safety

- `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` until OTC-FLIP. While deferred: LOCK outputs are rejected, CLAIM/REFUND tx types rejected, replay byte-identical.
- **Never flip with CLAIM/REFUND unimplemented** — a LOCK with no spend path locks SOST permanently. The 3-condition checklist (CLAIM done+tested, REFUND done+tested, external review) is mandatory before any finite height.
- Independent of `DTD_POPC_GATE_CONSENSUS_ACTIVE` (untouched) and of mainnet (untouched). No VPS action.

## 6. Risks
- **Permanent lock** if activated before CLAIM/REFUND — mitigated by the gate + checklist.
- **Issuer freeze** on USDT/USDC/PAXG/XAUT — mitigated by warnings, amount limits, asset preference; cannot be removed (it is the token's nature).
- **Timeout misordering** — mitigated by wallet-enforced `T2<T1` and "responder refund opens first".
- **Counterparty-chain reorg** — mitigated by sufficient confirmations before claiming + conservative timeouts.
- **Non-determinism** — forbidden by construction: consensus never reads another chain; cross-chain logic is wallet/watcher only.

## 7. Tests (target)
SOST consensus: LOCK structural (done on feat) + CLAIM/REFUND happy-path and ~12
adversarial cases; mempool acceptance; reorg around the gate; replay byte-identity;
read-only RPC. BTC: redeem-script vectors (done on feat) + BIP-143 sighash +
signing (gated). EVM: the 28+ Foundry tests + external audit. Coordinator: state
machine + e2e simulation (done on feat). All gated; mainnet no-op throughout.

---

## What this phase does NOT do
No mainnet change. No flip of any gate. No `DTD_POPC_GATE_CONSENSUS_ACTIVE` change.
No VPS deploy/restart. No EVM deployment. OTC-0 is design + impact map only; the
groundwork integration begins at OTC-0.5.
