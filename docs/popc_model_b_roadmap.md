# PoPC Model B — Smart Contract Roadmap

**Status:** specification draft. Not ready to deploy.
**Target:** Q3 2026 mainnet activation (after Model A stabilizes).
**Scope:** this document defines what is missing between the current
SOST-side Model B code (which exists and compiles) and a fully operational
end-to-end Model B that accepts real gold escrow on Ethereum mainnet.

> Model A is ready at SOST block 5000. Model B needs an Ethereum smart
> contract to exist before any participant can actually deposit gold,
> and that contract does not exist yet. The SOST side of Model B is
> complete and waiting.

---

## 1. What Model B promises (from whitepaper Section 6.8)

A gold holder deposits XAUT or PAXG into an **immutable Ethereum escrow
contract** with a fixed unlock height. At deposit time the SOST node is
notified via an on-chain event, and the SOST reward (calculated from
`ESCROW_REWARD_RATES` — 0.4% to 8.0% depending on duration) is paid
**immediately** to the depositor's SOST address. When the unlock height
is reached, the depositor calls `withdraw()` on the Ethereum contract
and recovers 100% of the gold.

**No audits. No bond. No slash.** Custody is guaranteed by the escrow
contract itself, not by trust in the depositor.

**Advantages over Model A:** zero slash risk, no SOST bond purchase
required, simpler for gold holders unfamiliar with the SOST chain.

**Disadvantage:** the gold is locked in a third-party contract. The
depositor must trust the contract code (which is why it must be
immutable, audited, and verifiable).

---

## 2. Current state of the SOST-side code

**Implemented and ready:**

| Component | File | Status |
|---|---|---|
| Escrow registry data structures | `include/sost/popc_model_b.h` | ✓ LIVE |
| `calculate_escrow_reward()` | `src/popc_model_b.cpp:128` | ✓ LIVE |
| `EscrowRegistry::register_escrow()` | `src/popc_model_b.cpp:147` | ✓ LIVE |
| `ESCROW_REWARD_RATES` table | `include/sost/popc.h:171` | ✓ LIVE, aligned with whitepaper |
| ESCROW_LOCK (0x11) tx type | `src/tx_validation.cpp` | ✓ LIVE at block 5000 |
| Unit tests (escrow) | `tests/test_escrow.cpp` | ✓ passing |
| RPC commands (4 endpoints) | `src/sost-node.cpp` | ✓ LIVE |

**What the SOST side does not yet have:**

- An **Ethereum event listener** that watches the escrow contract and
  automatically calls `EscrowRegistry::register_escrow()` when a deposit
  event is emitted.
- **Automatic reward payment** from the PoPC Pool to the depositor's SOST
  address on event receipt.

Both of these are application-layer daemons, not consensus changes. They
can be built after the smart contract is deployed and verified.

---

## 3. What is missing on the Ethereum side

### 3.1 The smart contract itself

No Solidity contract has been written or deployed. This is the largest
single piece of work remaining for Model B.

**Contract requirements:**

- **Immutable**: no `owner`, no `pause`, no upgrade proxy, no admin keys.
  Once deployed, the code never changes. This is a hard constraint — a
  contract with admin powers defeats the whole point of Model B.
- **Multi-token**: accepts both XAUT (6 decimals, address
  `0x68749665FF8D2d112Fa859AA293F07A622782F38`) and PAXG (18 decimals,
  address `0x45804880De22913dAFE09f4980848ECE6EcbAf78`).
- **Per-deposit tracking**: each deposit is independent. Users can have
  multiple simultaneous escrows with different unlock times.
- **Time-locked withdrawal**: withdraw can only succeed after the unlock
  timestamp has passed. Before that, `withdraw()` reverts.
- **Full return**: at unlock, the depositor gets back **100%** of their
  deposit. No fees, no slippage, no rounding down beyond wei precision.
- **Event-driven**: emit a `Deposited` event at registration and a
  `Withdrawn` event at withdrawal. The SOST node indexes these events.
- **SOST address binding**: the deposit transaction must include the
  target SOST address (as bytes) so the SOST node knows where to pay
  the reward. Stored in the `Deposit` struct, emitted in the event.

**Data structure sketch:**

```solidity
struct Deposit {
    address depositor;        // Ethereum address that deposited
    address token;            // XAUT or PAXG contract
    uint256 amount;           // raw token amount (respect decimals)
    uint64  unlockTimestamp;  // unix timestamp — withdraw allowed after
    bytes   sostAddress;      // 25-byte SOST bech32-decoded pubkey hash
    bool    withdrawn;        // true after successful withdraw
}

mapping(bytes32 => Deposit) public deposits;  // depositId -> Deposit

event Deposited(
    bytes32 indexed depositId,
    address indexed depositor,
    address indexed token,
    uint256 amount,
    uint64  unlockTimestamp,
    bytes   sostAddress
);

event Withdrawn(bytes32 indexed depositId, address indexed depositor, uint256 amount);
```

**Functions:**

- `deposit(address token, uint256 amount, uint64 durationSeconds, bytes sostAddress) returns (bytes32 depositId)`
  - Must have `approve` called on the token contract first by the user
  - Transfers tokens in via `safeTransferFrom`
  - Validates `token` is XAUT or PAXG (hardcoded addresses)
  - Validates `durationSeconds` matches one of the allowed durations
    (1, 3, 6, 9, 12 months expressed in seconds)
  - Computes `depositId = keccak256(depositor, token, amount, block.timestamp, sostAddress)`
  - Stores the deposit, emits `Deposited`
- `withdraw(bytes32 depositId)`
  - Reverts if `msg.sender != deposit.depositor`
  - Reverts if `block.timestamp < deposit.unlockTimestamp`
  - Reverts if `deposit.withdrawn == true`
  - Marks withdrawn, `safeTransfer`s tokens back, emits `Withdrawn`
- `getDeposit(bytes32 depositId) view returns (Deposit memory)`
  - Public read for the SOST indexer

**Security requirements:**

- Use OpenZeppelin's `SafeERC20` for all token transfers (defensive)
- Use `ReentrancyGuard` on `withdraw()` even though deposits are per-id
  (defense in depth; gas cost is negligible)
- **No delegatecall anywhere** — the contract must not be a proxy
- **No `selfdestruct`** — removed in Solidity 0.8+ but confirm in tests
- Fixed Solidity version pragma (`pragma solidity 0.8.24;` or similar —
  do not allow a range)
- Deploy with `--optimize-runs=200` and publish the source on Etherscan
  immediately after deployment for verification

### 3.2 Testnet deployment

Before mainnet, the contract must be deployed on at least two testnets
and exercised:

- **Sepolia**: primary testnet, most realistic. Deploy, run the full
  test matrix, confirm gas costs.
- **A local Hardhat fork of mainnet**: lets you test against real XAUT
  and PAXG contract state without spending real money.

Required test cases (minimum):

1. Deposit 0.1 XAUT → event emitted → correct storage
2. Deposit 0.01 PAXG → event emitted → correct storage
3. Withdraw before unlock → reverts
4. Withdraw after unlock → tokens returned in full
5. Withdraw twice → second call reverts
6. Withdraw by non-depositor → reverts
7. Deposit with wrong token → reverts
8. Deposit with zero amount → reverts
9. Deposit with invalid duration → reverts
10. Multiple concurrent deposits by same user → all tracked independently
11. Reentrancy attack simulation on malicious token → defended
12. Event data decodable from off-chain listener

### 3.3 Security audit

**This is non-negotiable.** A Model B contract holds real user gold
indefinitely. If the contract has a bug that lets anyone else withdraw,
the whole SOST project's credibility collapses overnight.

Options, in order of preference:

1. **Professional external audit** from a firm like Trail of Bits,
   ConsenSys Diligence, OpenZeppelin, or Certora. Cost: $25,000 -
   $80,000 USD depending on scope. Turnaround: 3-6 weeks. **Recommended
   for mainnet deployment.**
2. **Community bug bounty** via Immunefi or a dedicated pool posted on
   Bitcointalk. Offer 10% of the TVL in the contract (or a fixed SOST
   bounty) for any exploit found. Complement, not replacement, to a
   professional audit.
3. **Internal multi-reviewer review** (minimum 3 engineers unfamiliar
   with each other's work) plus automated analysis with Slither,
   Mythril, and Certora Prover. **Only acceptable if the contract is
   intentionally capped at a small TVL for the first N months.**

A sensible path: internal review + Slither/Mythril → Sepolia + Certora
→ limited mainnet launch with a hardcoded TVL cap → professional audit
before lifting the cap.

### 3.4 Deployment cost

At current Ethereum mainnet gas prices (~30 gwei typical, can spike to
200+ gwei):

- Contract deployment: ~1,500,000 gas → ~$30-$200 USD depending on
  gas price and ETH price
- Each `deposit()` call: ~120,000 gas → ~$3-$30 USD per user
- Each `withdraw()` call: ~80,000 gas → ~$2-$20 USD per user

**Implication:** small deposits (0.01 oz = ~$20 value) are uneconomic
for the depositor. Realistic minimum is probably 0.1 oz (~$200 value)
or consider deploying the contract on an L2 (Arbitrum, Base) instead
of mainnet. L2 gas costs would drop per-call costs to cents.

**Decision needed:** mainnet L1 or L2? L2 is cheaper for users but
requires the L2 to be secure and liquid enough to hold the gold tokens.
XAUT and PAXG are natively on mainnet; bridging them to L2 adds another
trust layer.

---

## 4. SOST-side integration work

Once the Ethereum contract is deployed, the SOST node needs a daemon
that watches for `Deposited` events and reacts by:

1. Parsing the event to extract depositor, token, amount, unlock time,
   SOST address
2. Calling `calculate_escrow_reward(gold_value_stocks, duration_months)`
   to get the SOST reward amount
3. Registering the commitment via `EscrowRegistry::register_escrow()`
4. Sending the SOST reward tx from the PoPC Pool to the depositor's
   SOST address (same path as Model A reward payment, requires pool
   private key unlock)

**Components needed:**

| Component | Estimated work | Notes |
|---|---|---|
| Ethereum RPC client in Python | 1 week | Use `web3.py` + Etherscan for event filtering |
| Event polling daemon | 1 week | Long-running, handles reorgs (wait for 12 confirmations) |
| Gold price oracle | 1 week | Same one used by Model A (`scripts/popc_oracle.py` logic) |
| Reward tx builder integration | 2-3 days | Reuses existing `build_reward_tx()` from `popc_tx_builder.cpp` |
| Monitoring + alerting | 2-3 days | Log all events, alert on daemon crash, CSV audit trail |
| End-to-end test on Sepolia | 1 week | Real deposit → real SOST reward on SOST testnet |

**Total SOST-side integration: ~4-5 weeks** once the contract is
deployed on a testnet.

---

## 5. Open design questions

Questions that need answers before a contract is written, not during:

1. **Mainnet L1 vs L2?** Decision affects gas cost, minimum deposit
   viability, and trust model. Community input recommended.
2. **Are XAUT and PAXG the only acceptable tokens, or also wrapped
   gold variants (e.g. CAUR, KAU, DGLD)?** The whitepaper says XAUT
   and PAXG — sticking to that for v1 is safer.
3. **Does the escrow accept partial deposits toward a single commitment,
   or is each deposit a separate commitment?** The cleanest design is
   one deposit = one commitment. Simpler contract, simpler accounting,
   better event semantics.
4. **What happens if a deposited token contract gets paused/blacklisted
   by its issuer after the deposit?** The user's gold is trapped until
   the token contract unfreezes. This is an unavoidable third-party
   risk — must be disclosed to depositors upfront.
5. **What is the minimum deposit amount?** Below some USD value the gas
   cost makes it uneconomic. Recommend ~0.1 oz hard minimum (or more
   for mainnet, less for L2).
6. **How does the SOST node handle a Deposited event for an already-known
   depositId?** Ignore (idempotent). How does it handle an event older
   than the chain tip? Re-process if within the last N blocks, otherwise
   ignore.
7. **What SOST pays out the reward?** The PoPC Pool (same as Model A).
   This means Model A and Model B compete for the same pool — the PUR
   and tier system must track both unified.
8. **Duration values**: the SOST side uses months (1, 3, 6, 9, 12).
   Ethereum uses seconds. Conversion factor: `1 month = 30.4375 * 86400
   = 2,629,800 seconds`. Contract should validate that
   `durationSeconds ∈ {1*M, 3*M, 6*M, 9*M, 12*M}` where M = 2_629_800.

---

## 6. Realistic timeline

| Phase | Duration | Deliverable |
|---|---|---|
| Design review (whitepaper alignment, open questions above) | 1 week | Signed-off spec document |
| Solidity contract v1 (with OZ SafeERC20 + ReentrancyGuard) | 2 weeks | Verified source + test suite |
| Sepolia deployment + full test matrix | 1 week | 12/12 tests green, events decodable |
| Internal security review (Slither, Mythril, manual) | 2 weeks | Issue list + fixes |
| Professional audit (external firm) | 4-6 weeks | Audit report |
| Audit issue remediation | 1-2 weeks | v2 contract |
| Final testnet run + decisions lock | 1 week | — |
| Mainnet deployment | 1 day | Verified contract on Etherscan |
| SOST-side daemon implementation | 4-5 weeks | Event listener + reward payer |
| Soft launch with TVL cap | 2 weeks | First 10 deposits monitored manually |
| Full launch | — | Model B live |

**Grand total (realistic):** 16-22 weeks from green-light to full
Model B launch.

**Fastest unsafe path (skip external audit, launch with cap):** 8-10
weeks. Not recommended for mainnet.

**Parallelization note:** the SOST-side daemon can be developed in
parallel with the Solidity work, since both sides share the same
interface contract (event shape + function signatures). Realistic
wall-clock time with parallel work: 10-14 weeks.

---

## 7. What does NOT need to be done

Explicit non-requirements, so scope does not creep:

- ❌ No new SOST consensus rules. `ESCROW_LOCK` is already live.
- ❌ No new cASERT changes.
- ❌ No new coinbase split changes. The 25% PoPC Pool already funds
  both models.
- ❌ No changes to `ESCROW_REWARD_RATES`. They are aligned with the
  whitepaper.
- ❌ No new reputation system. Model B has no slashing, so reputation
  is irrelevant for it.
- ❌ No multisig, no governance, no DAO. The contract is intentionally
  as simple as possible.
- ❌ No cross-chain bridges. XAUT and PAXG stay on their native chain.
- ❌ No price oracle inside the contract. Price is only used by SOST
  when computing reward at deposit time, and the SOST node has its
  own oracle via `popc_oracle.py`.

---

## 8. Go / no-go criteria for mainnet launch

The contract can be launched on mainnet only when ALL of the following
are green:

1. ✅ Solidity source is published and verified on Etherscan
2. ✅ At least one external professional audit report is published
3. ✅ All audit issues rated medium or higher are fixed
4. ✅ Sepolia testnet has processed at least 100 deposits and 100
      withdrawals without incident
5. ✅ SOST node daemon has indexed testnet events end-to-end for at
      least 4 weeks without crashing or missing events
6. ✅ A TVL soft cap is in place (e.g. `require(totalDeposited < 100
      * 10**decimals)` for the first month), removable only by
      redeployment
7. ✅ Emergency response plan documented: what to do if an exploit is
      found, how to warn users, what alternative path depositors have
8. ✅ Clear user-facing documentation explaining that Model B has
      smart-contract risk that Model A does not

Missing any of these → delay launch. There is no rush. Model A is
enough for the first ~6 months of PoPC operation.

---

## 9. Next concrete action

Before any code is written:

1. Decide **L1 vs L2** (open question #1). This decision affects every
   other choice.
2. Write a 1-page formal spec of the `deposit()` / `withdraw()` /
   `getDeposit()` interface so Solidity engineers and SOST-side
   engineers can work in parallel without drift.
3. Post a draft of this roadmap on Bitcointalk ANN thread asking for
   community input on the open design questions.

None of the above involves writing Solidity. Solidity comes only after
the open questions are resolved and the spec is signed off.

---

**Document status:** draft, pending design decisions.
**Owner:** NeoB (SOST Protocol).
**Last updated:** 2026-04-15 (block ~4420).
