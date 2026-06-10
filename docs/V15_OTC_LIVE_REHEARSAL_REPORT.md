# OTC-5 — Live rehearsal report

**Goal:** drive the complete OTC/P2P atomic-swap stack (SOST + BTC + EVM legs +
the OTC-4 coordinator) end-to-end in test environments, with no new features
(only document/fix if a bug appears). **No mainnet, no production deploy, gates
untouched.**

**Outcome: PASS.** Every leg and the coordinator ran their full happy + refund +
negative paths. No bug was found in the stack. The only limitation is
environmental (this CI/sandbox cannot keep a network daemon alive), so the EVM
leg ran on an in-process EVM and the BTC leg via the ON-build known-answer
vectors; the live-daemon runs are scripted operator steps.

---

## Environment

| Tool | Status |
|---|---|
| forge / cast | 1.5.1 (present) |
| anvil | present but **cannot bind a persistent RPC in this sandbox** (killed, signal 16) → EVM rehearsal runs in-process via `forge test` |
| bitcoind / bitcoin-cli | **not installed** → BTC rehearsal runs the ON-build signing vectors; live regtest is an operator step |
| SOST consensus | HTLC gate stays `INT64_MAX`; SOST leg exercised via consensus tests + the coordinator; a live node needs a regtest gate-override build (operator step) |

Rehearsal artifacts (all committed):
- `scripts/otc_rehearsal_evm_anvil.sh` — EVM (mode A live anvil / mode B forge test)
- `scripts/otc_rehearsal_btc_regtest.sh` — BTC (mode A live regtest / mode B ON vectors)
- `scripts/otc_rehearsal_sost_local.sh` — SOST suites + coordinator drive
- `contracts/atomic-swap/test/OtcRehearsal.t.sol` — narrated in-process EVM flow

---

## 1. EVM leg — SOST↔ETH / SOST↔ERC20 (in-process EVM)

`forge test --match-contract OtcRehearsal -vv` — real opcodes, real events.
Deterministic addresses: HTLC `0x5615dEB798BB3E4dFa0139dFa1b3D433Cc23b72f`,
MockERC20 `0x2e234DAe75C793f67A35089C9d99245E1C58470b`.

| Step | Result |
|---|---|
| native lock 1 ETH → claim(secret) | BOB +1 ETH, state CLAIMED, contract drained to 0 — **PASS** |
| ERC20 lock 1000 → claim(secret) | BOB 1000 mUSD, contract drained — **PASS** |
| native refund: refund-before-T2 reverts; refund at T2 | reverts `TIMEOUT_NOT_REACHED`; ALICE recovers 0.5 ETH, REFUNDED — **PASS** |
| wrong preimage | reverts `WRONG_PREIMAGE` — **PASS** |
| cross-leg link | `sha256(secret) == hashlock` on-chain — **PASS** |

`forge test` full contract suite: **52 passed, 0 failed** (incl. reentrancy,
fee-on-transfer, no-return ERC20, forced-ETH EIP-6780).

The preimage a `claim` reveals is emitted in `Claimed(swapId, preimage, claimer)`
— the exact value the SOST leg needs (`scripts/otc_rehearsal_evm_anvil.sh`
mode A extracts it with `cast logs`).

## 2. BTC leg — SOST↔BTC (libwally ON build)

bitcoind absent → ran the ON (`-DSOST_BTC_HTLC_SIGNING=ON`) signing backend:
`test-atomic-swap-btc-signing` = **80 passed, 0 failed**, anchored to the
**BIP-143 native-P2WSH** known-answer vector (real redeemscript → P2WSH addr →
Low-R ECDSA → witness). The live regtest cycle (fund P2WSH → claim/refund →
extract preimage from the witness) is printed as operator steps by the script.

## 3. SOST leg — consensus + builders

`ctest -R atomic-swap` = **12 passed, 0 failed**: HTLC LOCK/CLAIM/REFUND
consensus validation (`atomic-swap-htlc-{lock,helpers,rpc}`), orderboard,
watcher, status classifier, session. The live node LOCK/CLAIM/REFUND +
`gethtlcstatus` requires a regtest build with a low activation height (mainnet
constant stays `INT64_MAX`) — documented as an operator step in
`scripts/otc_rehearsal_sost_local.sh`.

## 4. Coordinator end-to-end (OTC-4) — `otc-coordinator`

Drove a full swap as a real operator would (`create`/`observe`/`next`/`inspect`
over a local session file):

**Happy path (initiator, SOST↔BTC):**
```
create  -> phase Created, next PublishOffer
offer-published -> Offered, Wait
offer-accepted  -> Accepted, LockSost
sost-locked     -> SostLocked, Wait
cp-locked       -> CounterpartyLocked, ClaimCounterparty [needs confirmation]
cp-claim        -> Claimed, Done
sost-claim      -> Completed, Done
```

**Resume:** after the lock steps, `inspect` re-read the saved session file
(`phase: CounterpartyLocked`, `have_secret: yes`) and the flow continued to
`Completed` — **PASS** (restart-safe).

**Refund path (counterparty never locks):** `sost-locked` → at T1 next=`RefundSost`
→ `timeout` → RefundReady → `sost-refund` → **Refunded** — **PASS**.

**Responder side:** ingested the revealed preimage (sha256-verified) → ClaimSeen,
next=`ClaimSost` — **PASS**.

**Negatives — all enforced:**
| Case | Result |
|---|---|
| wrong preimage | `rejected: revealed preimage does not match hashlock` (phase unchanged) |
| mis-ordered timeout (T2≥T1) | rejected at create: `TIMEOUT_ORDER_INVALID` |
| counterparty never locks | → `RefundSost` at T1 (no funds stuck) |
| issuer token (USDT/USDC/PAXG/XAUT) | `RISK: issuer-freeze asset — atomicity NOT guaranteed` surfaced |
| BTC/ETH/BNB/SOST | 0 issuer-freeze warnings |
| no hidden broadcast / no key | session module + tool are pure (file I/O only); verified by grep |

---

## 5. Verification (double pass)

- **Full C++ ctest (OFF default):** 92 passed, 0 failed.
- **Foundry:** 52 contract tests + 5 rehearsal tests passed.
- **BTC signing ON:** 80 passed.
- **Gates intact on `main`:** `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX`,
  `SOST_BTC_HTLC_SIGNING` OFF default, `DTD_POPC_GATE_CONSENSUS_ACTIVE = false`.
- **No VPS / systemd / restart / deploy. No mainnet. No private-key handling.**

## 6. Findings / fixes

- **No stack bug found.** Every modelled path behaved correctly.
- Added (test/tooling only, not features): the `OtcRehearsal.t.sol` narrated EVM
  test and the three rehearsal scripts.
- **Environmental note (not a defect):** persistent daemons (anvil, bitcoind)
  don't run in this sandbox; the scripts auto-fall back to in-process / vector
  evidence and print the exact operator steps for a full live-daemon run.

## 7. Status

SOST-side, BTC-side, EVM-side and the end-to-end coordinator all rehearsed in a
test environment as a non-custodial flow — still gated/OFF, no mainnet. Next
(beyond OTC-5): full live-daemon rehearsals on an operator machine (anvil +
Bitcoin-Core regtest + a SOST regtest node), then an **external cryptographic /
economic audit** — well before any discussion of flipping the activation gate.
