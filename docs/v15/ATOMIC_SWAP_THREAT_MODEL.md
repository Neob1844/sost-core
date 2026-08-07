# SOST Atomic Swap — Security Threat Model

**Subsystem:** SOST ↔ EVM / BTC cross-chain atomic swap (HTLC)
**Commit:** `4f8753be` (branch `feat/v15-jackpot-explorer-card`)
**Analysis type:** static code review only — NO build, mine, deploy, package-install, or test run was performed. Every MITIGATED claim cites the actual source read at this commit.

## Ground truth at this commit

| Fact | Evidence |
|---|---|
| EVM HTLC consensus gate is LIVE (finite, not sentinel) | `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_5_HEIGHT` → mainnet `16000` (`include/sost/atomic_swap.h:143`, `include/sost/params.h:1052`). `IsAtomicSwapHtlcEnabled()` returns `!= INT64_MAX` → **true** (`src/atomic_swap_helpers.cpp:16`). |
| Relay/mempool gate is HIGHER (flag-day) | `ATOMIC_SWAP_RELAY_ACTIVATION_HEIGHT = V14_7_HEIGHT` → mainnet `17000` (`include/sost/atomic_swap.h:181`). Between 16000–17000 HTLC txs are consensus-valid but NON-relayable. |
| BTC funding/claim/refund signing is compiled OFF | `IsBtcHtlcSigningEnabled()` returns **false unconditionally** — even with `SOST_BTC_HTLC_SIGNING=ON` the runtime toggle is absent (`src/atomic_swap_btc_signing.cpp:46-61`). All four legacy stubs return the disabled error unless `SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY` is defined. |
| EVM Foundry suite | 57/57 pass (asserted by task; test source read: `contracts/atomic-swap/test/AtomicSwapHTLC.t.sol`, `OtcRehearsal.t.sol`). |
| C++ atomic-swap ctest coverage | 15 registered tests (`CMakeLists.txt:485-553`): `atomic-swap-btc-script`, `-btc-test-vectors`, `-btc-signing`, `-coordinator`, `-e2e-sim`, `-htlc-lock`, `-htlc-helpers`, `-htlc-rpc`, `-orderbook`, `-watcher`, `-status`, `-session`, `-policy`, `htlc-block-path-v14-5`, `htlc-expired-lock-template`. |

## Two material findings surfaced by this review

1. **EVM asset-support over-claim (policy layer vs deployed contract).** `src/atomic_swap_policy.cpp:290-298,345-356` asserts the contract "now uses a SafeERC20 path (no-bool tolerant) + balance-delta accounting" and reports USDT/PAXG/XAUT as `Testing` (offerable). **The deployed contract does neither.** `AtomicSwapHTLC.sol:54` is a *minimal* `IERC20` and `lockERC20`/`claim` use `bool ok = ...transfer...; require(ok)` (`AtomicSwapHTLC.sol:194-195,229,257`). The tests prove the real behaviour: no-bool USDT **reverts at lock** (`AtomicSwapHTLC.t.sol:545-556`) and fee-on-transfer PAXG **locks-then-fails-claim** (`AtomicSwapHTLC.t.sol:567-582`). The contract fails *closed* (no theft), but the C++ policy comments/status are factually wrong and could steer a wallet into offering tokens that get stuck-until-refund. → `NEEDS_EXTERNAL_AUDIT` + fix the comment/status.

2. **Dashboard advertises a stale activation height.** `website/atomic-swap-console.html` gates on block **15,000 / 15,010** (`:183,:237,:505-509`) while the live consensus gate is **16,000** and relay is **17,000**. A founder following the dashboard at height 15,010 would build a `createhtlclock` whose `OUT_HTLC_LOCK` is rejected (`atomic_swap_htlc_active_at(15010)==false`), and even at 16,000–16,999 the LOCK is non-relayable. No fund loss (tx simply fails) but the UI is misleading. → `ACCEPTED` (fails safe) with a UI-correction recommendation.

---

## 1. Threat table

STATUS ∈ {MITIGATED, ACCEPTED, BLOCKING, NEEDS_REAL_E2E, NEEDS_EXTERNAL_AUDIT}. "MITIGATED" is used only with concrete code/test evidence. Paths are repo-relative.

| ID | THREAT | ATTACK / FAILURE SCENARIO | IMPACT | CURRENT MITIGATION | CODE / TEST EVIDENCE | RESIDUAL RISK | STATUS |
|---|---|---|---|---|---|---|---|
| T01 | Theft / unilateral capture (EVM) | 3rd party submits `claim`/`refund` hoping to redirect funds | Loss of escrow | Funds always routed to recorded `claimer`/`refunder`, never `msg.sender`; CEI ordering | `AtomicSwapHTLC.sol:212-234,240-261`; `test_claimNative_happyPath` (carol submits, bob paid) `t.sol:96-107` | none for native/std-ERC20 | MITIGATED |
| T02 | Theft / unilateral capture (SOST leg) | Craft CLAIM/REFUND spending a LOCK without preimage/timeout | Loss of locked SOST | Consensus rules R17–R24 + block-path guard; unit + regression tests | `htlc-block-path-v14-5` test (`CMakeLists.txt:547-549`); builders `src/atomic_swap_helpers.cpp:24-127` | Multi-node mainnet behaviour not exercised here | NEEDS_REAL_E2E |
| T03 | Replay (EVM) | Re-submit a prior lock/claim tx | Double execution | `swapId` single-use (`DUPLICATE_SWAP_ID`), one-way state machine | `AtomicSwapHTLC.sol:138,179,214`; `test_..._cannotClaimTwice` `t.sol:125-131` | none | MITIGATED |
| T04 | Replay (BTC sighash) | Reuse a signature across txs/networks | Loss of BTC leg | BIP-143 sighash w/ network HRP; path compiled OFF | `src/atomic_swap_btc_signing.cpp:197-210,151-156`; gate `:46-61` | Real regtest signing unproven | NEEDS_REAL_E2E |
| T05 | Front-running a claim | Attacker races the claim tx | none (pays intended claimer) | Claim credits recorded `claimer` regardless of submitter | `AtomicSwapHTLC.sol:220,233`; `t.sol:102-104` | none | MITIGATED |
| T06 | Front-running swapId (squatting) | Pre-register victim's `swapId` to force `DUPLICATE_SWAP_ID` | Griefing DoS (no fund loss) | `swapId` derived over participants+secret `nonce` kept private until broadcast | `src/atomic_swap_policy.cpp:139-181` (esp. nonce `:136-137` header) | Predictable swapId in a wallet re-opens DoS | MITIGATED |
| T07 | Preimage exposure | Secret becomes public | Enables the paired claim (intended) | Reveal is the protocol mechanism; every consumer re-verifies `sha256(preimage)==hashlock` | `AtomicSwapHTLC.sol:216`; `src/atomic_swap_watcher.cpp:49-56`; `src/atomic_swap_session.cpp:279-288` | none | MITIGATED |
| T08 | Premature preimage revelation | Secret leaks before both legs locked | Counterparty claims, initiator un-hedged | Session refuses `PreimageRevealed` before `CounterpartyLocked` → `RecoveryNeeded` | `src/atomic_swap_session.cpp:245` | Off-chain secret handling is wallet's job | MITIGATED |
| T09 | Timeout ordering wrong | Initiator refund opens before responder's | Responder griefed / unilateral claim | T2<T1 & gap≥margin enforced in 3 independent layers | orderbook `src/atomic_swap_orderbook.cpp:96-115`; policy `src/atomic_swap_policy.cpp:83-140`; coordinator `src/atomic_swap_coordinator.cpp:70-100` | Correct cross-chain normalisation assumed (see T10) | MITIGATED |
| T10 | BTC/EVM timeout mismatch | Two chains' block-times misconverted; margin evaporates | Reaction window lost | Wallet must normalise to a common axis before feeding heights; contract deliberately does not check | `AtomicSwapHTLC.sol:20-24`; `atomic_swap_policy.h:70-93`; margin default 6 `atomic_swap_coordinator.h:155` | Adequacy of the normalisation + default margin unverified on real chains | NEEDS_REAL_E2E |
| T11 | Chain reorg (funding) | Act on a lock that later un-mines | False "locked" | `ClassifyFunding` requires ≥`min_confirmations`; never settle on 0-conf | `src/atomic_swap_policy.cpp:196-209`; `FundingIsSettled==Confirmed` `:209` | Caller supplies `min_confirmations`; must be set sanely | MITIGATED |
| T12 | Deep reorg after claim | Reorg un-mines a claim after secret is public | Loss on the reorged leg | Not handled in pure modules; classic cross-chain risk | Acknowledged only in UI `atomic-swap-console.html:224` | No code-level defence; needs conf-depth policy + live testing | NEEDS_REAL_E2E |
| T13 | BTC tx malleability | Mutate txid before confirmation | Broken funding tracking | SegWit P2WSH → txid witness-independent; funding keys on vout 0 | `AtomicSwapHTLC`? n/a; `src/atomic_swap_btc_signing.cpp:1107-1133,472`; path OFF | Unproven on regtest | NEEDS_REAL_E2E |
| T14 | RBF / replacement | Replace a broadcast HTLC tx | Double-spend of funding | Spends use `sequence=0xFFFFFFFE` (non-RBF, CLTV active) | `src/atomic_swap_btc_signing.cpp:292,327` | BTC broadcast layer not built | NEEDS_REAL_E2E |
| T15 | Fee spike / stuck tx | Fee too low; claim can't confirm before timeout | Miss claim window → loss | No fee-bump/CPFP in pure modules; `DecideRpcRecovery` halts near deadline on bad view | `src/atomic_swap_policy.cpp:265-284` | Live fee-estimation + bump path unbuilt | NEEDS_REAL_E2E |
| T16 | Insufficient confirmations | Treat mempool sighting as final | Reorg loss | `Confirmed` only at ≥`min_confirmations`; `InMempool`/`Confirming` never "settled" | `src/atomic_swap_policy.cpp:196-209` | Caller-supplied threshold | MITIGATED |
| T17 | Counterparty disappearance | Peer vanishes mid-swap | Funds stranded | Refund path always reachable after timeout (invariant F) | coordinator `RefundAvailable` `src/atomic_swap_coordinator.cpp:298-304`; session `RefundReady` `src/atomic_swap_session.cpp:259-267` | Requires the operator to actually refund | MITIGATED |
| T18 | Coordinator crash / restart | Process dies mid-swap | Lost swap state | Deterministic serialize/resume for session + watchlist | `SerializeSession/ParseSession` `src/atomic_swap_session.cpp:379-452`; watcher `:89-157` | Disk durability/atomicity is wallet's job | MITIGATED |
| T19 | Persistent-state corruption | Tampered/partial session record | Act on bad state | Parse rejects missing id/phase/hashlock, verifies stored secret vs hashlock, zero-hashlock reject; `Corruption`→`RecoveryNeeded` | `src/atomic_swap_session.cpp:439-449,225` | none evident | MITIGATED |
| T20 | RPC compromise / malicious response | Node feeds stale/forged tip | Act on false chain view | `DecideRpcRecovery`: never act on stale/unavailable; halt on failures; session ingests only pre-verified facts | `src/atomic_swap_policy.cpp:265-284`; session `:222-277` | Only as good as the caller wiring the policy in | MITIGATED |
| T21 | Duplicate swapId | Overwrite an existing swap | Fund confusion/loss | `require(state==NONE)` on both locks | `AtomicSwapHTLC.sol:138,179`; `test_..._rejectsDuplicateSwapId` `t.sol:84-90,457-465` | none | MITIGATED |
| T22 | swapId collision | Two swaps derive same id | Cross-claim | `sha256` over locker/claimer/refunder/token/amount/hashlock/refundTime/chainId/nonce | `src/atomic_swap_policy.cpp:156-181` (mirrors `computeSwapId`) | Collision-resistance of SHA-256 assumed | MITIGATED |
| T23 | Wrong asset / token / amount | Human enters wrong leg params | Fund loss/mismatch | `ValidateOffer` structural checks; EVM records token+amount immutably | `src/atomic_swap_orderbook.cpp:71-123`; contract `:140-199` | Human input error; dashboard must display authoritative values (see §7) | NEEDS_REAL_E2E |
| T24 | Decimal / rounding / dust | Sub-dust outputs, decimal drift | Unspendable dust / rejects | `DUST_THRESHOLD` guards; BTC sub-dust change folded to fee | `src/atomic_swap_helpers.cpp:151,188`; `src/atomic_swap_btc_signing.cpp:342,438` | EVM token decimals are the wallet's responsibility | MITIGATED |
| T25 | Fee-on-transfer ERC-20 (PAXG) | Escrow receives less than recorded `amount` | Claim reverts; funds stuck until refund | Contract fails closed (claim `require(ok)`); **but policy layer wrongly reports it handled** | `AtomicSwapHTLC.sol:229`; `test_lockERC20_feeOnTransfer..._lockSucceedsClaimFails` `t.sol:567-582`; wrong comment `src/atomic_swap_policy.cpp:352-356` | Policy over-claim → must blacklist FoT tokens in wallet & fix comment/status | NEEDS_EXTERNAL_AUDIT |
| T26 | False-return ERC-20 | Token returns `false` on transfer | Inconsistent escrow | Rejected at lock via `require(ok,"TRANSFER_FAILED")` | `AtomicSwapHTLC.sol:194-195`; `test_lockERC20_rejectsFailingToken` `t.sol:247-251` | none | MITIGATED |
| T27 | No-bool-return ERC-20 (real USDT) | `transferFrom` returns no data | Decode revert | Lock **reverts** (abi-decode of bool on empty data) — fails closed; **policy wrongly says "handled"** | `test_lockERC20_rejectsNoReturnERC20` `t.sol:545-556`; wrong comment `src/atomic_swap_policy.cpp:345-348` | Real USDT unsupported; fix comment/status; wallet must exclude | NEEDS_EXTERNAL_AUDIT |
| T28 | Malicious / reentrant ERC-20 | Token re-enters `lockERC20` during `transferFrom` | Reentrancy | `nonReentrant` guard + state roll-back | `AtomicSwapHTLC.sol:103-108`; `test_lockERC20_blocksMaliciousTokenReentrancy` `t.sol:587-602` | none | MITIGATED |
| T29 | Reentrancy on native claim | Malicious receiver re-enters `claim` on ETH send | Double drain | `nonReentrant` + CEI + state guard; outer reverts, state untouched | `AtomicSwapHTLC.sol:212-234`; `test_reentrancy_blockedByGuardAndStateMachine` `t.sol:316-338` | none | MITIGATED |
| T30 | Allowance issues | Insufficient/again-spent approval | Lock fails | `transferFrom` reverts on short allowance; state rolled back before interaction sees it | `AtomicSwapHTLC.sol:181-195` | Standard ERC-20 approval UX | MITIGATED |
| T31 | Double redeem | Claim twice | Double pay | `require(state==LOCKED)` → 2nd hits `NOT_LOCKED` | `t.sol:125-131,474-479` | none | MITIGATED |
| T32 | Double refund | Refund twice | Double pay | Same one-way guard | `t.sol:163-170,487-493` | none | MITIGATED |
| T33 | Redeem after refund | Claim a refunded swap | Double pay | `NOT_LOCKED` | `test_claimAfterRefund_rejected` `t.sol:181-188,503-509` | none | MITIGATED |
| T34 | Refund after redeem | Refund a claimed swap | Double pay | `NOT_LOCKED` | `test_refundAfterClaim_rejected` `t.sol:172-179,495-501` | none | MITIGATED |
| T35 | Incorrect signer / key misuse | Wrong key signs a leg | Loss / stuck | EVM routes by recorded address, not signer; BTC verifies privkey range before use | `AtomicSwapHTLC.sol:220,247`; `src/atomic_swap_btc_signing.cpp:147-150,388-391` (behind gate) | BTC end-to-end unproven | MITIGATED |
| T36 | Tx mutation / calldata tampering | Alter calldata before signing | Funds to wrong dest | Dashboard builds calldata against the ABI; EVM signature commits to calldata | `atomic-swap-console.html:299` | Depends on user verifying the shown box | NEEDS_REAL_E2E |
| T37 | Cross-chain partial execution | One leg settles, other frozen by issuer | Non-atomic loss | Issuer-freeze surfaced as explicit warning; atomicity promised only for non-freezable legs | `src/atomic_swap_orderbook.cpp:43-56,117-119`; session `:164-170` | Inherent to centrally-issued tokens | ACCEPTED |
| T38 | Partial DB write | Crash mid-write of session/watchlist | Corrupt resume | Full-record serialise; parser validates completeness before use | `src/atomic_swap_session.cpp:408-452`; `src/atomic_swap_watcher.cpp:106-138` | fsync/atomic-rename is the wallet's job | MITIGATED |
| T39 | Stale UI state | Dashboard shows wrong height/status | Acts too early | Live `/rpc` height poll + readiness gating | `atomic-swap-console.html:499-526` | **Dashboard gate 15,000/15,010 is stale vs consensus 16,000 / relay 17,000** — fails safe (LOCK rejected) but misleading | ACCEPTED |
| T40 | User repeats action after timeout | Refund after preimage already public | Wasted/failed tx, confusion | Session refuses refund once preimage public ("claim, do not refund"); coordinator terminal-idempotent | `src/atomic_swap_session.cpp:257`; coordinator `:168-191` | none | MITIGATED |
| T41 | Forged quote / order | Fake offer with bad params | Enter unsafe swap | `ValidateOffer` structural + non-zero hashlock; offers are off-chain (no on-chain trust); HTLC still protects funds | `src/atomic_swap_orderbook.cpp:71-123` | Offers are unsigned P2P metadata — trust the HTLC, not the quote | ACCEPTED |
| T42 | Stale quote | Act on an expired offer | Margin gone | `RESPONDER_DEADLINE_PASSED`/`_NEAR` warnings; refuse to lock when margin gone | `src/atomic_swap_policy.cpp:113-123` | none | MITIGATED |
| T43 | Unavailable counterparty | Peer offline | Stranded funds | Refund fallback (see T17) | coordinator `:298-304`; session `:259-267` | Operator must execute refund | MITIGATED |
| T44 | DoS affecting timeout safety | Flood RPC / node down near deadline | Miss reaction window | `DecideRpcRecovery` halts & escalates; refund remains reachable after timeout | `src/atomic_swap_policy.cpp:265-284` | Live monitoring/alerting unbuilt | NEEDS_REAL_E2E |
| T45 | Clock / time assumptions | Miner manipulates timestamp | Skew timeout | EVM uses **`block.number`** (not `block.timestamp`); SOST uses block height | `AtomicSwapHTLC.sol:72,137,215,243`; contract note `:21-24` | Block-rate variance folded into margin (T10) | MITIGATED |
| T46 | Integer overflow / underflow | Overflow amount/fee/height math | Wrong amounts | Solidity 0.8 checked arithmetic; C++ parse+arith overflow guards | `AtomicSwapHTLC.sol:2` (0.8.24); `src/atomic_swap_helpers.cpp:442`; BTC `src/atomic_swap_btc_signing.cpp:375-378` | none | MITIGATED |
| T47 | Secret leakage in logs / RPC / dashboard | Preimage written where it can leak | Premature reveal | Dashboard keeps secret in-tab only, never uploaded; session redacts unless `include_secret`; no RPC returns the secret before it is on-chain | `atomic-swap-console.html:272,406,413`; `src/atomic_swap_session.cpp:382-405` | **Watcher serialises preimage in cleartext** in the watchlist file (`src/atomic_swap_watcher.cpp:100`) — only after reveal / claimant-side, but on disk | MITIGATED |
| T48 | Malicious RPC (double / inconsistent) | Node returns contradictory facts | Bad decision | Fail-safe recovery policy; ingest verifies preimage vs hashlock | `src/atomic_swap_policy.cpp:265-284`; `src/atomic_swap_session.cpp:279-288` | Wiring-dependent | MITIGATED |
| T49 | Contract creates value | Forced ETH / stray transfer inflates balance | Accounting break / drain | `receive`/`fallback` revert; claim pays recorded `amount` only; forced-ETH stays orphaned, no state corruption | `AtomicSwapHTLC.sol:272-278`; `test_forcedEthViaSelfdestruct_doesNotCorruptState` `t.sol:617-634`; drain-to-zero tests `t.sol:381-425` | Orphaned forced-ETH is un-withdrawable by design | MITIGATED |
| T50 | Preimage cross-swap reuse | Same secret across two swaps | One reveal unlocks both | No code enforces a fresh secret per swap; convention only | (absence) `src/atomic_swap_session.cpp:174-194` sets but never uniqueness-checks | Wallet MUST generate a fresh 32-byte secret per swap | ACCEPTED |
| T51 | Policy over-claims EVM asset support | Wallet offers USDT/PAXG believing "SafeERC20 + balance-delta" | Stuck-until-refund / failed swaps | (finding) contract is minimal `IERC20`, not SafeERC20; fails closed | `AtomicSwapHTLC.sol:54,194-195,229`; wrong comment `src/atomic_swap_policy.cpp:290-298` | Fix comment + downgrade USDT/PAXG/XAUT status; wallet blacklist | NEEDS_EXTERNAL_AUDIT |
| T52 | Dashboard stale activation height | Founder acts at 15,010; LOCK rejected until 16,000, non-relay until 17,000 | Failed tx / confusion (no loss) | Consensus gate rejects early LOCK; relay gate blocks broadcast | `atomic-swap-console.html:183,505-509` vs `include/sost/atomic_swap.h:143,181` | Correct the UI to 16,000/17,000 | ACCEPTED |
| T53 | Relay/consensus gate window (16000–17000) | HTLC consensus-valid but non-relayable | Broadcast rejected `bad-capsule` | Deliberate flag-day; keeps mempools homogeneous | `include/sost/atomic_swap.h:162-185` | Operator must recompile in the 16900–17000 window | MITIGATED |
| T54 | BTC signing accidentally enabled | Build flips `SOST_BTC_HTLC_SIGNING=ON` | Unaudited BTC fund movement | Runtime toggle absent → `IsBtcHtlcSigningEnabled()` still false; stubs fail closed | `src/atomic_swap_btc_signing.cpp:46-61` | none until a future, reviewed sprint wires it | MITIGATED |

---

## 2. Security invariants A–J

| Inv | Statement | Verdict | Evidence |
|---|---|---|---|
| A | No party can obtain both assets via valid protocol execution | PROVEN_BY_TEST (EVM leg) / NEEDS_REAL_E2E (cross-chain) | EVM leg: one-way state machine + mutual-exclusion of claim/refund (`AtomicSwapHTLC.sol:214,242`; `t.sol:172-188,495-509`). Cross-chain double-take requires the timeout ordering to be honoured on both chains — enforced in model (`src/atomic_swap_policy.cpp:98-123`) but the *joint* execution is not tested against two live chains. |
| B | Preimage knowledge only enables intended actions | PROVEN_BY_CODE + PROVEN_BY_TEST | Every consumer verifies `sha256(preimage)==hashlock`: contract `AtomicSwapHTLC.sol:216` + `testFuzz_claim_onlyAcceptsExactPreimage` `t.sol:364-371`; watcher `src/atomic_swap_watcher.cpp:49-56`; session `src/atomic_swap_session.cpp:279-288`; policy `src/atomic_swap_policy.cpp:54-58,218-226`. |
| C | No valid refund before timeout | PROVEN_BY_TEST | EVM `require(block.number >= s.refundTime)` `AtomicSwapHTLC.sol:243`; boundary is sharp at `refundTime` (`testFuzz_refundTime_boundaryIsSharpAtRefundTime` `t.sol:641-668`; `test_refundNative_rejectsBeforeTimeout` `:155-161`). SOST-side: watcher refunds only at `current>=refund_height` `src/atomic_swap_watcher.cpp:44-46`. |
| D | No second economic execution after finality | PROVEN_BY_TEST | `NONE→LOCKED→{CLAIMED|REFUNDED}` strictly one-way; all four re-entry cases revert `NOT_LOCKED` (`t.sol:125-131,163-170,172-188,474-509`). |
| E | Restart never loses enough state to lose funds | PROVEN_BY_CODE / NEEDS_REAL_E2E (durability) | Session + watchlist round-trip with completeness + secret-vs-hashlock validation `src/atomic_swap_session.cpp:408-452`; watcher `:89-157`; ctest `atomic-swap-session`. Disk fsync/atomic-rename is out of these modules. |
| F | Counterparty failure ends in completion or eventual refund (never a permanent local-logic lock) | PROVEN_BY_CODE / NEEDS_REAL_E2E | Coordinator/session always expose a refund action after timeout (`src/atomic_swap_coordinator.cpp:298-304,382-412`; `src/atomic_swap_session.cpp:259-267,340-341,368-369`). No state is terminal-without-exit before a lock exists (Draft/Expired are fund-free). |
| G | swapId cannot be reused to claim another swap's funds | PROVEN_BY_TEST | `DUPLICATE_SWAP_ID` guard + per-participant derivation (`AtomicSwapHTLC.sol:138,179`; `src/atomic_swap_policy.cpp:156-181`; `t.sol:84-90,457-465`). |
| H | Contract cannot create value | PROVEN_BY_TEST | `receive`/`fallback` revert `AtomicSwapHTLC.sol:272-278`; drain-to-zero on claim/refund `t.sol:381-425`; forced-ETH doesn't corrupt state `t.sol:617-634`. |
| I | Locked/redeemed/refunded amounts conserve value modulo explicit fees | PROVEN_BY_TEST (native/standard) / FAIL (fee-on-transfer nominal) | Native & standard ERC-20 conserve exactly (`t.sol:381-425`). **Fee-on-transfer breaks nominal delivery**: escrow holds `amount-FEE`, claim of `amount` reverts (`t.sol:567-582`) — documented UNSUPPORTED; value is not *created*, but nominal conservation does not hold, so such tokens must be excluded. |
| J | BTC/EVM timeout gap leaves the second party enough time to react after preimage revelation | NEEDS_REAL_E2E | Ordering + margin + deadline warnings exist (`src/atomic_swap_policy.cpp:98-123`; default margin 6 `atomic_swap_coordinator.h:155`), but the adequacy of the margin under real block-time variance, confirmation depth and congestion is not established without a live cross-chain run. |

No invariant evaluates to a hard FAIL that permits theft. Invariant I is qualified (fee-on-transfer) and drives finding T25/T51.

---

## 3. Timeout analysis (cross-chain)

**Where the numbers live (all caller/wallet-supplied, none hardcoded in consensus):**

- `T1 = initiator_refund_height` — the SOST/initiator refund; must open **LAST**.
- `T2 = responder_refund_height` — the counterparty/responder refund; must open **FIRST**.
- Rule: `T2 < T1` and `gap = T1 - T2 ≥ safety_margin_min_blocks` (**default 6**).
  - `include/sost/atomic_swap_coordinator.h:152-155` (default 6), `atomic_swap_orderbook.h:69`, `atomic_swap_policy.h:88`.
- Enforced identically in three layers: `src/atomic_swap_orderbook.cpp:96-115`, `src/atomic_swap_policy.cpp:83-140`, `src/atomic_swap_coordinator.cpp:70-100`.
- Both heights must be strictly in the future; if `current_height ≥ T2` the swap is refused (`RESPONDER_DEADLINE_PASSED`, `src/atomic_swap_policy.cpp:113-117`); if within margin, a `RESPONDER_DEADLINE_NEAR` warning fires (`:118-123`).

**Timeout primitive:** EVM uses absolute `block.number` (`AtomicSwapHTLC.sol:72,137,215,243`), not `block.timestamp` — removes miner-timestamp manipulation. SOST uses absolute block height. There is no wall-clock in consensus.

**Required ordering & margin:** correct (responder-first). The margin is expressed in *normalised* blocks on a wallet-chosen common axis (`atomic_swap_policy.h:70-93`, `atomic_swap_coordinator.h:128-137`). **The contract explicitly does NOT verify cross-chain ordering** (`AtomicSwapHTLC.sol:20-24`) — it is the wallet's responsibility.

**Assumed confirmations:** not hardcoded — `ClassifyFunding(min_confirmations)` with a floor of 1 (`src/atomic_swap_policy.cpp:196-209`). A lock is "settled" only at `Confirmed`.

**Behaviour under congestion / reorg:** funding classification protects against 0-conf/shallow reorg by requiring depth; `DecideRpcRecovery` refuses time-sensitive actions on a stale/unavailable view (`:265-284`). There is **no** code that re-plans after a *deep reorg that un-mines a claim once the secret is public* (T12) and **no** fee-bump/CPFP path (T15).

**BLOCKING assessment:** The model enforces ordering, margin and deadline-passed refusal, so no code path leaves a party with a *provably* zero reaction window. However, whether the **default 6-block margin** is a "reasonable reaction time" once mapped onto real, differently-paced chains under fee pressure is **not established here** → **NEEDS_REAL_E2E**, not BLOCKING. Recommendation: pick per-pair margins from real block-time + target confirmation depth (e.g., BTC leg wants hours, not 6 generic blocks) before any non-founder use.

---

## 4. Preimage lifecycle

| Stage | What happens | Length/format & checks | Evidence |
|---|---|---|---|
| Generation | 32 random bytes | `crypto.getRandomValues(32)` in-browser (founder console) | `atomic-swap-console.html:541` |
| Hash | `H = sha256(S)` | 32-byte SHA-256; identical primitive on all three legs | `atomic-swap-console.html:542`; contract `AtomicSwapHTLC.sol:15-18,216`; BTC `OP_SHA256` `include/sost/atomic_swap_btc.h:20-34` |
| Lock A (initiator) | `H` embedded in the LOCK; `S` kept private | Offer/session reject zero hashlock; initiator's `S` checked vs `H` at CreateSession | orderbook `src/atomic_swap_orderbook.cpp:84-87`; session `src/atomic_swap_session.cpp:179-185` |
| Lock B (counterparty) | Same `H`, earlier refund | shared-`H` link asserted | `OtcRehearsal.t.sol:105-108` |
| Redeem | Claimer submits `S` | Contract verifies `sha256(preimage)==hashlock` before paying | `AtomicSwapHTLC.sol:216`; fuzz `t.sol:364-371` |
| **Revelation (public point)** | `S` becomes public **the instant the first CLAIM is broadcast** | EVM: `claim(swapId,preimage)` calldata (68 bytes) **and** the `Claimed` event carries `preimage`; SOST: HTLC_CLAIM tx carries preimage in `OUT_HTLC_CLAIM_WITNESS` payload; BTC: preimage sits in the spend witness | EVM `AtomicSwapHTLC.sol:95,233`; SOST `src/atomic_swap_helpers.cpp:90,287,666`; BTC `src/atomic_swap_btc_signing.cpp:1016-1047` |
| Observation | Counterparty extracts `S` and re-verifies | Hash-match extraction (never trust by position); rejects non-matching | policy `src/atomic_swap_policy.cpp:231-251`; watcher `src/atomic_swap_watcher.cpp:49-56`; BTC `src/atomic_swap_btc_signing.cpp:1016-1105` |
| Second redeem | Responder claims SOST with public `S` | Same `sha256` check on the SOST side (R21) | `src/atomic_swap_session.cpp:360-367` |

**Logging:** `policy::ToHex` exists for ids/logging but the secret is never auto-logged (`atomic_swap_policy.h:150-151`). **RPC exposure:** `decodehtlc` returns the preimage of a CLAIM tx, but only for a tx that already reveals it publicly (`src/atomic_swap_helpers.cpp:662-666`); no RPC exposes the secret *before* it is on-chain. **UI exposure:** browser-only, never uploaded (`atomic-swap-console.html:272,406,413`). **Persistence:** session redacts the secret unless `include_secret` (`src/atomic_swap_session.cpp:403-404`); **the watcher writes the preimage in cleartext into the watchlist file** (`src/atomic_swap_watcher.cpp:100`) — only relevant post-reveal / claimant-side, but a disk-at-rest exposure worth hardening. **Cross-swap reuse:** not enforced in code (T50) — wallets must generate a fresh secret per swap.

**Exact point the secret becomes public:** the broadcast of the first CLAIM (initiator claiming the counterparty/receiving leg). Everything before that keeps `S` private to the initiator; everything after assumes `S` is public and drives the responder's SOST claim.

---

## 5. BTC gate (`SOST_BTC_HTLC_SIGNING = OFF`)

**What OFF makes inaccessible / stub:**
- `IsBtcHtlcSigningEnabled()` returns **false unconditionally** — even `SOST_BTC_HTLC_SIGNING=ON` still returns false because the runtime acknowledgement toggle does not exist in this commit (`src/atomic_swap_btc_signing.cpp:46-61`).
- The four production entry points — `SignBtcHtlcClaim`, `SignBtcHtlcRefund`, `SignBtcHtlcLockFunding`, `EncodeP2WSHAddress` — return `{ok=false,"...disabled..."}` unless `SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY` is defined (`:274-604`). With libwally absent (default), every helper (C.5–C.8: key derivation, ECDSA sign/verify, witness assembly, funding tx, preimage extraction, txid) is inert (`:651-1138`).
- Pure, always-compiled pieces remain usable and are safe on their own: the redeem-script byte builder and witness-program hash (`src/atomic_swap_btc.cpp`) — no keys, no I/O, no network.

**What must change OFF→ON (do NOT do here):**
1. Build with `-DSOST_BTC_HTLC_SIGNING=ON` (defines the macro + vendors/links libwally — `CMakeLists.txt:475-482`).
2. Wire the currently-absent runtime acknowledgement so `IsBtcHtlcSigningEnabled()` can return true (`src/atomic_swap_btc_signing.cpp:51-57`).
3. Separately, flip the **SOST consensus** BTC path (still governed by `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`); the header notes BTC funding stays deferred to V15 even though EVM went live at V14.5 (`include/sost/atomic_swap.h:138`).
4. External cryptographic review of the sighash/Bech32/witness code BEFORE the flip (`include/sost/atomic_swap_btc_signing.h:24-42`).

**Rollback mechanism:** rebuild with the flag OFF (macro undefined → stubs fail closed) and/or leave the runtime toggle absent; no fork, no consensus change — the BTC path never touched consensus.

**What bitcoind-regtest MUST demonstrate before flipping (per module intent):** full LOCK→CLAIM→REFUND lifecycle on regtest with (a) BIP-143 sighash correctness against Core, (b) Bech32 address round-trip on regtest HRP `bcrt`, (c) P2WSH witness accepted by a real node, (d) CLTV refund rejected before `refund_height` and accepted at/after, (e) preimage extraction from a real claim witness, (f) txid/funding-detection stability under SegWit. None of this is exercised at this commit → the entire BTC leg is **NEEDS_REAL_E2E**.

---

## 6. EVM — Foundry test coverage vs threats

| Foundry test class / test | Threats covered |
|---|---|
| `test_lockNative_*` / `test_lockERC20_*` (param validation, zero-checks, duplicate id, refund-in-past) `t.sol:45-90,242-251,437-465` | T21, T23 (structural), T03 |
| `test_claimNative_*` / `test_claimERC20_*` (wrong preimage, after-timeout, twice, unknown swap) `t.sol:96-137,467-479` | T01, T02(EVM), T07, T31, C |
| `test_refundNative_*` / `test_refundERC20_*` (before timeout, twice) `t.sol:143-170,481-493` | T32, C |
| `test_refundAfterClaim` / `test_claimAfterRefund` (both asset types) `t.sol:172-188,495-509` | T33, T34, D |
| `test_reentrancy_blockedByGuardAndStateMachine` `t.sol:316-338` | T29 |
| `test_lockERC20_blocksMaliciousTokenReentrancy` `t.sol:587-602` | T28 |
| `test_lockERC20_rejectsFailingToken` `t.sol:247-251` | T26 |
| `test_lockERC20_rejectsNoReturnERC20` `t.sol:545-556` | T27 (documents revert) |
| `test_lockERC20_feeOnTransfer..._lockSucceedsClaimFails` `t.sol:567-582` | T25 (documents stuck-until-refund) |
| `test_rejectsPlainEthTransfer` `t.sol:298-306` | T49 |
| `test_forcedEthViaSelfdestruct_doesNotCorruptState` `t.sol:617-634` | T49, H |
| `test_balance_*_drainsContractToZero` `t.sol:381-425` | H, I |
| `test_noOwnerFunctionsExist_runtime` `t.sol:344-359` | admin/backdoor absence |
| `testFuzz_claim_onlyAcceptsExactPreimage` `t.sol:364-371` | B, T07 |
| `testFuzz_refundTime_boundaryIsSharpAtRefundTime` `t.sol:641-668` | C |
| `test_event_*` (LockCreated/Claimed/Refunded, native+ERC20) `t.sol:270-292,513-536` | observability of the reveal |
| `OtcRehearsal.*` (native/erc20 claim, refund, wrong preimage, hashlock link) | end-to-end EVM narration; cross-leg hashlock identity |

**Threats NOT covered by the current EVM suite:**
- Cross-chain joint execution & timeout race (T02 SOST↔EVM together, T10, J) — no dual-chain harness.
- Deep reorg after reveal (T12), RBF/malleability/fee (T13–T15) — BTC/live-chain concerns.
- Front-running swapId squatting (T06) — nonce logic is C++-side, not asserted in Solidity tests.
- FoT/no-bool tokens beyond documenting the failure — no positive support path (by design; but T25/T51 remain).
- Gas-griefing on the native `claim`/`refund` `call{value}` to a contract claimer that consumes all gas (not tested; low risk given nonReentrant + CEI, but unproven) — **NEEDS_EXTERNAL_AUDIT**.

---

## 7. Dashboard / operator risk

Console: `website/atomic-swap-console.html` — founder-only, read-only + command/calldata generator, never holds keys, never uploads the secret.

| Operator / UI error | Current handling | What the dashboard MUST display to avoid fund loss |
|---|---|---|
| Wrong destination address / claimer / refunder | Free-text inputs `:346-347` | Echo the exact recorded `claimer`/`refunder` back from `getSwap` after LOCK, before any CLAIM |
| Wrong asset / amount | Asset dropdown + amount `:323-335` | Show human-units AND on-chain base units; re-read `amount`/`token` from `getSwap` and require a match |
| Expired quote / near-timeout | Height poll `:499-517` | Surface `RESPONDER_DEADLINE_PASSED/_NEAR` (policy) and refuse to build a LOCK when margin is gone |
| Insufficient confirmations | none explicit in UI | Show confirmation depth vs required `min_confirmations`; block "settled" until `Confirmed` |
| Repeated redeem | contract reverts `NOT_LOCKED` | Read state first; hide CLAIM/REFUND when state ≠ LOCKED |
| Closed browser / lost secret | secret in-tab only `:272`; download log `:417` | Prominent "save your secret — without it you cannot claim" (present `:221,441`); keep it |
| Backend / node restart | live re-poll on load | Re-derive status from chain, never from cached UI state |
| RPC offline | catch + "node unreachable" `:512-516` | Never show "no lock" as "safe"; treat unreachable as unknown |
| Counterparty offline | — | Show the refund deadline and the refund action path |
| Near-timeout | height hint `:510` | Countdown to `refundTime`/`refund_height`; warn to CLAIM immediately when T2 passed |
| Desynced local state | — | Read-only "Query node" path `:416`; reconcile against chain before acting |
| **Stale activation height (finding T52)** | gates on 15,000/15,010 `:237,505-509` | **Correct to consensus 16,000 / relay 17,000**; otherwise an early LOCK is rejected |
| **USDT/PAXG/XAUT offered (finding T25/T51)** | dropdown lists them `:325-331`; glossary warns native-first `:225` | Hard-disable no-bool USDT and fee-on-transfer PAXG at compose time (contract rejects/strands them) |

Positive controls already present: founder-gate sentence unlock (`:530-536`), "verify contract code" before operate (`:318,439`), refund-before-claim rehearsal ordering (`:376,449-450`), and an explicit Emergency runbook (`:459-471`).

---

## 8. Final tally

- **THREATS TOTAL:** 54
- **MITIGATED:** 36
- **ACCEPTED:** 5 (T37 issuer-freeze, T39 stale-UI/fails-safe, T41 off-chain quote trust, T50 secret-reuse convention, T52 stale-height/fails-safe)
- **BLOCKING:** 0
- **NEEDS_REAL_E2E:** 10 (T02, T04, T10, T12, T13, T14, T15, T23, T36, T44)
- **NEEDS_EXTERNAL_AUDIT:** 3 (T25, T27, T51) + the untested native-call gas-griefing note in §6

Invariants: A–J show **no theft-enabling FAIL**; A/E/F/J carry NEEDS_REAL_E2E qualifiers; I is qualified for fee-on-transfer tokens (must be excluded).

**ATOMIC SWAP SECURITY REVIEW: PASS** — zero BLOCKING items.

**PASS is conditional and does NOT mean production-ready.** The EVM HTLC mechanism is sound and fails closed, but the subsystem must NOT be used beyond founder-only, tiny, native-asset tests until:
(1) the 10 NEEDS_REAL_E2E items are closed by a live cross-chain (bitcoind-regtest + anvil/testnet) run, especially timeout-margin adequacy (J) and deep-reorg handling (T12);
(2) the 3 NEEDS_EXTERNAL_AUDIT items are resolved — fix the `atomic_swap_policy.cpp` SafeERC20/balance-delta over-claim (T25/T27/T51), and obtain the external contract audit the contract header itself demands (`AtomicSwapHTLC.sol:39-50`);
(3) the dashboard activation height is corrected to 16,000/17,000 and no-bool/fee-on-transfer tokens are hard-disabled.
