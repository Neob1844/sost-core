# SOST Atomic Swap — External Audit Scope Package

**Prepared for:** an independent third-party security auditor.
**Repository:** SOST core (`sost-core`).
**Exact commit under audit:** `4f8753be` — `docs(v15): atomic-swap inventory + EVM Foundry suite PASS 57/57`.
**Branch:** `feat/v15-jackpot-explorer-card`.
**Companion:** `docs/v15/ATOMIC_SWAP_THREAT_MODEL.md` (threat table + invariants + timeout/preimage/BTC/EVM/dashboard analysis at the same commit).

This package defines what to audit, what is intentionally out of scope, the architecture and trust boundaries, the invariants to attempt to break, the assumptions we make, the test evidence we already have, known limitations, and the deliverables we expect.

---

## 1. In-scope

### 1.1 EVM contract (primary, LIVE on mainnet at height 16,000)
- `contracts/atomic-swap/src/AtomicSwapHTLC.sol` (Solidity `0.8.24`).
  - Functions: `lockNative`, `lockERC20`, `claim`, `refund`, `getSwap` (view), `receive`, `fallback`.
  - State machine `NONE→LOCKED→{CLAIMED|REFUNDED}`; `nonReentrant` guard; CEI ordering; `sha256(preimage)` hashlock; absolute `block.number` timelock.
- `contracts/atomic-swap/test/AtomicSwapHTLC.t.sol`, `contracts/atomic-swap/test/OtcRehearsal.t.sol`, `contracts/atomic-swap/test/mocks/MockERC20.sol` (57/57 Foundry tests).

### 1.2 SOST-side C++ HTLC support (consensus builders/decoders/RPC + orchestration)
- Consensus-tx helpers: `include/sost/atomic_swap_helpers.h`, `src/atomic_swap_helpers.cpp` (LOCK/CLAIM/REFUND builders, decoder, status, 5 RPC handlers; gated by `IsAtomicSwapHtlcEnabled()`).
- Activation gates: `include/sost/atomic_swap.h` (consensus gate `V14_5_HEIGHT`=16000; relay gate `V14_7_HEIGHT`=17000).
- Pure orchestration/policy (non-custodial, no I/O, no keys):
  - `include/sost/atomic_swap_coordinator.h` / `src/atomic_swap_coordinator.cpp` (state machine + timeout-order gate).
  - `include/sost/atomic_swap_orderbook.h` / `src/atomic_swap_orderbook.cpp` (offer validation, issuer-freeze honesty).
  - `include/sost/atomic_swap_policy.h` / `src/atomic_swap_policy.cpp` (canonical timeout rule, `DeriveSwapId`, funding depth, EVM preimage extraction, RPC-recovery, EVM asset matrix).
  - `include/sost/atomic_swap_session.h` / `src/atomic_swap_session.cpp` (end-to-end phase machine + persistence).
  - `include/sost/atomic_swap_watcher.h` / `src/atomic_swap_watcher.cpp` (auto-pilot decision + watchlist persistence).

### 1.3 BTC HTLC components (present but compile-gated OFF — audit as future-activation code)
- `include/sost/atomic_swap_btc.h` / `src/atomic_swap_btc.cpp` — pure BIP-199-style redeem-script byte builder + witness-program hash (no keys/I/O; always compiled).
- `include/sost/atomic_swap_btc_signing.h` / `src/atomic_swap_btc_signing.cpp` — libwally-backed signing/witness/tx/preimage/txid, all behind `SOST_BTC_HTLC_SIGNING(_HAS_LIBWALLY)`; **default build = fail-closed stubs**.

### 1.4 Operator surface
- `website/atomic-swap-console.html` (founder-only console: read-only + command/calldata generator; never holds keys, never uploads the secret).

---

## 2. Excluded scope

- SOST consensus outside the HTLC rules (SbPoW/cASERT, emission, PoPC, Gold Vault, DTD jackpot) — unchanged by this subsystem.
- The SOST consensus validator internals R17–R24 and block-path acceptance in `src/tx_validation.cpp` / `src/sost-node.cpp` / `src/utxo_set.cpp` are referenced by the builders but were **not** re-read for this package; they carry their own tests (`htlc-block-path-v14-5`) and should be pulled into scope if the auditor wants full SOST-leg coverage.
- `contracts/` other than `contracts/atomic-swap/` (SOSTEscrow, PoPC DEX, security, interfaces) — untouched (`docs/design/ATOMIC_SWAP_EVM_CONTRACT_REVIEW.md §1`).
- libwally-core vendored library internals (audit the *use*, not the library).
- Website pages other than the atomic-swap console.
- Off-chain P2P transport for offers (out of protocol; offers are unsigned metadata).

---

## 3. Architecture

Two-leg, non-custodial HTLC. SOST is always one leg; the counterparty leg is EVM (live) or BTC (deferred). One shared `hashlock = sha256(secret)` links the legs; revealing the secret to claim one leg exposes it for the other.

```
 Initiator (maker, holds S)                       Responder (taker)
   │  lock SOST HTLC  (H, T1=refund LAST) ───────────┐
   │                                                 │  observe SOST lock (≥ min_confirmations)
   │                          lock EVM/BTC HTLC (H, T2=refund FIRST, T2 < T1 - margin)
   │  claim counterparty leg with S  ── reveals S ──▶ │
   │                                                 │  extract S, claim SOST leg with S
   ▼                                                 ▼
 both legs settled by claim                    (or: timeout → each refunds own leg)
```

Layering (SOST side, all pure/non-custodial except the on-chain consensus tx path):
`orderbook (validate offer) → session (phase machine) → coordinator (core states) + policy (timeout/swapId/funding/recovery) + watcher (auto-pilot) → helpers (build unsigned LOCK/CLAIM/REFUND) → wallet signs & broadcasts → consensus R17–R24`.

Gates: consensus acceptance at `V14_5_HEIGHT`=16000; relay/mempool at `V14_7_HEIGHT`=17000; BTC signing at compile flag `SOST_BTC_HTLC_SIGNING` (OFF).

---

## 4. Contracts (paths + key functions)

`contracts/atomic-swap/src/AtomicSwapHTLC.sol`:
- `lockNative(swapId,hashlock,refundTime,claimer,refunder) payable` — escrows `msg.value`; requires non-zero amount/claimer/refunder, `refundTime>block.number`, `state==NONE`.
- `lockERC20(swapId,token,amount,hashlock,refundTime,claimer,refunder)` — CEI: record swap, then `transferFrom`, `require(ok)`.
- `claim(swapId,preimage)` — `require(state==LOCKED && block.number<refundTime && sha256(abi.encodePacked(preimage))==hashlock)`; set CLAIMED then pay `claimer`.
- `refund(swapId)` — `require(state==LOCKED && block.number>=refundTime)`; set REFUNDED then pay `refunder`.
- `receive()`/`fallback()` — revert (reject stray transfers).
- No owner/admin/pause/upgrade/drain/`selfdestruct`/`delegatecall`/`tx.origin`.

Cross-language `swapId` derivation must match byte-for-byte: `src/atomic_swap_policy.cpp::DeriveSwapId` (`:156-181`) mirrors `computeSwapId` (`sha256` over `"SOST-ATOMIC-SWAP-ID-v1"` ‖ locker ‖ claimer ‖ refunder ‖ token ‖ amount(u256 BE) ‖ hashlock ‖ refundTime(u256 BE) ‖ chainId(u256 BE) ‖ nonce).

---

## 5. BTC components

- Redeem script (always compiled, pure): `OP_IF OP_SHA256 <hashlock> OP_EQUALVERIFY <claim_pub> OP_CHECKSIG OP_ELSE <refund_height> OP_CHECKLOCKTIMEVERIFY OP_DROP <refund_pub> OP_CHECKSIG OP_ENDIF` → P2WSH via `sha256(script)` (`src/atomic_swap_btc.cpp:96-136`). ScriptNum minimal encoding and pushdata are BIP-compliant (`:29-90`).
- Signing backend (gated OFF): BIP-143 sighash via `wally_tx_get_btc_signature_hash`, ECDSA Low-R (`EC_FLAG_GRIND_R`), claim/refund witness assembly, funding tx with dust-fold to fee, preimage extraction by hash-match, witness-independent txid (`src/atomic_swap_btc_signing.cpp`). All fail-closed unless `SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY`; `IsBtcHtlcSigningEnabled()` returns false even with the build flag on (`:46-61`).

Audit BTC as *future-activation* code: verify the sighash domain separation, Bech32 HRP handling, CLTV refund `nLockTime`/`sequence` semantics, and preimage-extraction fund-safety — but note nothing here is reachable in a default build.

---

## 6. Security invariants to attempt to break

(Full evidence in the threat-model companion, §2.)

- **A** No party obtains both assets via valid execution.
- **B** Preimage knowledge enables only intended actions (every consumer re-checks `sha256(preimage)==hashlock`).
- **C** No valid refund before timeout (`block.number>=refundTime`; boundary sharp at `refundTime`).
- **D** No second economic execution after finality (one-way state).
- **E** Restart never loses enough state to lose funds (serialize/resume with validation).
- **F** Counterparty failure ends in completion or eventual refund — never a permanent local-logic lock.
- **G** `swapId` cannot be reused to claim another swap's funds.
- **H** Contract cannot create value (`receive`/`fallback` revert; drain-to-zero).
- **I** Amounts conserve value modulo explicit fees (qualified: fee-on-transfer tokens excluded).
- **J** Timeout gap leaves the second party time to react after reveal (default margin 6 normalised blocks — adequacy unverified).

---

## 7. Assumptions

- The wallet correctly **normalises two chains' block-times onto a common axis** before feeding `T1/T2` and the margin; the contract does not check cross-chain ordering (`AtomicSwapHTLC.sol:20-24`).
- Confirmation depth (`min_confirmations`) is set sanely by the caller; a lock is trusted only when `Confirmed` (`src/atomic_swap_policy.cpp:196-209`).
- The `swapId` `nonce` is locally random and secret until the lock is broadcast (anti-squatting; `atomic_swap_policy.h:136-137`).
- A fresh 32-byte secret is generated per swap (not enforced in code — T50).
- Issuer-freezable tokens (USDT/USDC/PAXG/XAUT) are **best-effort, not trustless**; the issuer can freeze mid-swap (`src/atomic_swap_orderbook.cpp:49-56`).
- SHA-256 collision/preimage resistance; secp256k1 ECDSA soundness (libwally).
- The operator runs the console founder-only, tiny amounts, native-first, refund-rehearsal-before-claim.

---

## 8. Trust boundaries

- **Consensus boundary:** SOST validators (R17–R24 + block-path) accept/reject HTLC txs at ≥16,000; relay at ≥17,000. The C++ builders produce *unsigned* txs and never move funds.
- **Custody boundary:** every C++ module is non-custodial — no key material, no signing, no broadcast, no sockets (asserted in each header; e.g. `atomic_swap_coordinator.h:8-44`, `atomic_swap_session.h:30-41`). Signing happens only in the wallet (SOST side) or MetaMask (EVM side).
- **Contract boundary:** the contract IS the escrow; no operator, no admin key. Anyone may submit `claim`/`refund` but funds route to the recorded `claimer`/`refunder`.
- **UI boundary:** the console never receives a private key or the secret; it emits commands/calldata only.
- **BTC boundary:** entirely behind a compile flag + absent runtime toggle → unreachable by default.

---

## 9. Test evidence already in place

- **EVM Foundry: 57/57 pass** — `contracts/atomic-swap/test/AtomicSwapHTLC.t.sol` (locks/claims/refunds, param validation, duplicate id, reentrancy native + malicious token, false-return/no-bool/fee-on-transfer weird tokens, forced-ETH via selfdestruct, balance-conservation, no-admin, preimage fuzz, refundTime boundary fuzz, event coverage) + `OtcRehearsal.t.sol` (native/ERC-20 claim, refund, wrong preimage, hashlock-link).
- **C++ ctest: 15 atomic-swap/HTLC tests** (`CMakeLists.txt:485-553`): `atomic-swap-btc-script`, `atomic-swap-btc-test-vectors`, `atomic-swap-btc-signing`, `atomic-swap-coordinator`, `atomic-swap-e2e-sim`, `atomic-swap-htlc-lock`, `atomic-swap-htlc-helpers`, `atomic-swap-htlc-rpc`, `atomic-swap-orderbook`, `atomic-swap-watcher`, `atomic-swap-status`, `atomic-swap-session`, `atomic-swap-policy`, `htlc-block-path-v14-5`, `htlc-expired-lock-template`.
- Threat→test mapping: companion doc §6 (EVM) and the CODE/TEST column of the threat table.

---

## 10. Known limitations (disclosed up front)

1. **EVM ERC-20 support is minimal `IERC20`, not SafeERC20/balance-delta.** No-bool USDT reverts at lock; fee-on-transfer PAXG locks then fails claim (stuck-until-refund). Contract fails closed, but `src/atomic_swap_policy.cpp:290-298,345-356` **wrongly claims** a SafeERC20/balance-delta path — a comment/status defect to fix (threat T25/T27/T51).
2. **No live cross-chain E2E.** No dual-chain (bitcoind-regtest + anvil/testnet) run has exercised joint execution, timeout races, deep reorg after reveal, RBF/malleability, or fee-spike handling.
3. **Default timeout margin (6 normalised blocks)** is unvalidated against real, differently-paced chains under congestion (invariant J).
4. **BTC leg is unreachable** in a default build and unproven on regtest.
5. **Dashboard advertises a stale activation height** (15,000/15,010 vs consensus 16,000 / relay 17,000) — fails safe but misleading.
6. **Watcher persists the preimage in cleartext** in the watchlist file (`src/atomic_swap_watcher.cpp:100`) — post-reveal/claimant-side, but an at-rest exposure.
7. **Native `claim`/`refund` gas-griefing** (a contract claimer consuming all forwarded gas on the `call{value}`) is untested — low risk under nonReentrant+CEI but unproven.
8. The contract is **NOT externally audited** (its own header, `AtomicSwapHTLC.sol:39-50`).

---

## 11. Open questions for the auditor

1. Is the minimal-`IERC20` + `require(ok)` pattern acceptable given the contract fails closed, or should SafeERC20 be adopted so the C++ policy matrix can honestly offer USDT (and to avoid the current comment/code divergence)?
2. Is the `nonReentrant` + CEI + state-machine combination sufficient against gas-griefing and unusual token callbacks on the native `call{value}` path?
3. Is `DeriveSwapId`/`computeSwapId`'s `abi.encodePacked` layout free of ambiguity (variable-length concat) given all fields are fixed-width — confirm no packing collision.
4. Is a default cross-chain safety margin of 6 normalised blocks defensible, or must per-pair margins be mandated (BTC vs ETH vs BNB block rates)?
5. Does the absence of any deep-reorg re-planning create an exploitable window once the secret is public (T12)?
6. Are there griefing vectors in the off-chain offer/`swapId` flow beyond the nonce-protected squatting case (T06)?
7. For the deferred BTC path: is the BIP-143 sighash/Bech32/CLTV witness construction correct enough to enter a regtest sprint, or are there latent fund-loss bugs to fix first?

---

## 12. Expected auditor deliverables

1. Written findings report with severity ratings (critical/high/medium/low/informational) mapped to the threat IDs (T01–T54) and invariants (A–J) in the companion doc.
2. An explicit verdict on each invariant A–J: upheld / broken / conditional, with reproduction where broken.
3. Confirmation or refutation of the three `NEEDS_EXTERNAL_AUDIT` items (T25/T27/T51 — ERC-20 handling & the policy over-claim) and the gas-griefing question.
4. A cross-chain timeout/margin adequacy opinion (invariant J / T10) and any required minimum margins per asset pair.
5. Remediation guidance and a re-review gate: the concrete conditions under which the subsystem may move from *founder-only, native, tiny* to public use.
6. A statement on the BTC deferred code: what must be fixed and demonstrated on bitcoind-regtest before `SOST_BTC_HTLC_SIGNING` may flip ON.
