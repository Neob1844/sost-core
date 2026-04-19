# SOST Phase II — Trust-Minimized Gold Vault Governance

**Status**: Design + audit document. Drafted at block ~4470. Some pieces buildable now (no fork). Some pieces require bundling into the next protocol fork.
**Goal**: Move control of the Gold Vault from "the Foundation" to "the SOST miners themselves", verified on-chain end to end.
**Architecture**: SOST chain (governance source of truth) ← bot relayer → Reality.eth (oracle on Ethereum) → Zodiac Reality Module → Gnosis Safe (custody) → XAUT/PAXG.
**Out of scope**: cross-chain bridges, wSOST, smart-contract redemption. Endgame is **physical gold custody** in a future Phase III, not deeper smart-contract entanglement.

---

## 1. Audit findings — what is and isn't wired in the codebase

This audit was done by reading the actual source. Verified line numbers as of block ~4470. **Re-verify before implementation.**

### 1.1 What WORKS today (verified)

#### a) Coinbase 25% accumulation — production-enforced
- `src/sost-miner.cpp:163-177` — coinbase tx is built with three outputs: `OUT_COINBASE_MINER` (50%), `OUT_COINBASE_GOLD` (25%) → `ADDR_GOLD_VAULT`, `OUT_COINBASE_POPC` (25%) → `ADDR_POPC_POOL`.
- `src/tx_validation.cpp::ValidateCoinbaseConsensus` (lines 507-612) enforces all of this at consensus level. Rules CB4 (output order), CB5 (amounts), CB6 (PKH match) reject any block whose coinbase deviates.
- Constitutional addresses: `include/sost/params.h:248-250`
  ```
  ADDR_GOLD_VAULT = "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"
  ADDR_POPC_POOL  = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
  ```
- **Result**: the vault accumulates passively and there is no way to mine a block that doesn't pay it. Working as designed.

#### b) Gold Vault rules engine — exists in isolation, fully tested
- `include/sost/gold_vault_governance.h` defines `classify_gv_spend()`, `gv_proposal_passes()`, `GVProposal`, `GVApprovalToken`, `GVMonthlyTracker`, `GVSpendType`.
- `include/sost/consensus_constants.h:36-52` — all the constants are present:
  ```
  GV_GOVERNANCE_ACTIVATION = 5000
  GV_THRESHOLD_EPOCH01 = 75
  GV_THRESHOLD_EPOCH2 = 95
  GV_APPROVAL_WINDOW = 288
  GV_FOUNDATION_VOTE_PCT = 10
  GV_MONTHLY_LIMIT_PCT = 10
  GV_MONTHLY_WINDOW = 4320
  GV_PAYLOAD_GOLD_PURCHASE = 0x47
  ```
- `tests/test_gold_vault.cpp` — **17/17 tests passing** (verified by running `./test-gold-vault` at audit time). The rules logic itself is correct: GV1-GV4 classify spends as expected, foundation bonus works, Epoch 2 transition works, monthly window works.

#### c) Version-bit signaling primitives — defined but not wired
- `include/sost/proposals.h` defines a BIP9-style version-bit signaling system. Bits 8-28 of the block header version field are reserved for 21 concurrent signaling proposals.
- Functions: `version_has_signal()`, `count_version_signals()`, `check_activation()`, `foundation_veto_active()`. All correct in isolation.
- One placeholder proposal is defined: `"post_quantum"` on bit 8 (`get_proposals()` returns it).
- `src/sost-node.cpp:2304` exposes a `getproposals` RPC that returns the proposal list as JSON.

### 1.2 What is BROKEN / MISSING (the gap)

This is where the audit gets uncomfortable. Three structural gaps that nobody seems to have closed.

#### Gap 1 — **`classify_gv_spend()` is dead code in production**

`grep` confirms: `classify_gv_spend` is referenced exactly **once** outside of test files: nowhere in `src/`. It is declared in the header, tested in isolation, but **never called from `tx_validation.cpp`, `block_validation.cpp`, or anywhere else in the validation pipeline**.

**Concrete consequence**: at block 5000 (in ~3-4 days from now), the activation height will trigger **nothing**. The rules will not fire. There is no consensus enforcement that prevents arbitrary spends from `ADDR_GOLD_VAULT`.

The protection of the vault today is purely the **non-existence of a private key** for `ADDR_GOLD_VAULT` (assuming nobody at the Foundation has it — this **needs to be confirmed separately, off-document, before any further public discussion of vault security**).

> ⚠ **CRITICAL OPEN QUESTION**: does anyone hold the private key corresponding to `ADDR_GOLD_VAULT`? Three possible answers, each with different implications:
> - **(a) No one** — it's a burn-style address with no reachable key. The vault is effectively a black hole until consensus rules are wired up. Funds are safe but unreachable.
> - **(b) The Foundation** — the Foundation can spend the vault freely until consensus rules activate. The vault is "trusted custody by NeoB" with no protocol enforcement.
> - **(c) A multisig** — there is already an off-chain multisig holding the key. This is the safest interim state.
>
> The honest answer determines everything that follows. Phase II design depends on this answer.

#### Gap 2 — **`handle_getproposals` reports dummy data**

In `src/sost-node.cpp:2316-2317`:
```cpp
for (int j = start; j < (int)g_blocks.size(); ++j)
    versions.push_back(1); // Current blocks all version=1, no signals yet
```

The signal counting RPC literally hardcodes every block's version to 1 and then asks "how many signals?" — answer is always zero. **The RPC is a placeholder, not a working signal counter.** A bot that calls `getproposals` to read miner sentiment gets nothing.

#### Gap 3 — **No mechanism to create or persist `GVProposal` objects**

The `GVProposal` struct exists in the header. **No code anywhere instantiates one.** No RPC creates it, no mempool entry type holds it, no chain state persists it. There is no path from "I want to propose spending 500 SOST from the vault" to anything observable on-chain.

Same for `GVApprovalToken`: it's a struct in the header, never built by any production code.

### 1.3 Audit summary in 4 lines

1. **Vault accumulation works.** Coinbase enforcement is solid. 25% goes in automatically. ✅
2. **Vault rules engine is correct and tested in isolation.** 17/17 unit tests pass. ✅
3. **Vault rules engine is not connected to anything.** It's a library with no callers. The activation at block 5000 will trigger nothing. ❌
4. **Vault proposal/voting system has no production wiring.** Headers define structs that no one builds, RPCs return dummy data, no chain state persists proposals. ❌

---

## 2. Does Phase II need a hard fork?

### 2.1 Component-by-component decision

| Component | Hard fork needed? | Why |
|---|---|---|
| **Ethereum side**: Gnosis Safe + Zodiac Reality Module + Reality.eth contract | ❌ NO | All Ethereum, all standard. Deployed via existing tooling. Zero SOST changes. |
| **Bot relayer**: reads SOST chain state, posts to Reality.eth | ❌ NO | The bot is an off-chain process. It needs SOST RPCs to work (gap 2 + 3 above), which require node code changes — but those changes are **node-only**, not consensus-affecting. |
| **Adding `gv_propose`, `gv_signal_status`, `getproposals_real` RPCs** | ❌ NO | These are read/write to the local node's mempool and chain state. They expose existing data in new ways. No consensus rule changes. |
| **Letting miners SET version-bit signaling in their headers** | ❌ NO | The 32-bit version field already exists. Miners can flip bits 8-28 today without any node change. The validation rules don't check those bits. This is a *soft* additive change. |
| **`count_version_signals()` actually reading real block versions** | ❌ NO | This is fixing a bug in `handle_getproposals`. Not a consensus change. |
| **Persisting proposal state in chain state** (so all nodes agree which proposals are pending/passed/expired) | ⚠ MAYBE | Depends on implementation. If proposals are tracked **off-chain** (e.g. in a side database keyed by miner signaling), no fork. If proposals are persisted **in chain state** (e.g. as new tx types or coinbase payloads), it changes block validation → fork. |
| **Wiring `classify_gv_spend()` into `tx_validation.cpp`** | ✅ YES | This is the consensus enforcement. Today, a tx that drains the vault would (potentially, depending on the privkey question) be valid. After wiring, the same tx would be rejected. **This is the definitional case of a hard fork.** |
| **Pushing `GV_GOVERNANCE_ACTIVATION` from 5000 to a later height** | ✅ YES | Changing a constitutional constant. But it's a "scheduling" hard fork — minor, well-understood, no behavior change before activation. |

### 2.2 The fork-vs-no-fork decision boils down to one question

> **Do we want soft governance (social contract) or hard governance (consensus enforcement) for Phase II?**

**Soft governance** — the Foundation **commits** to honor the bot's decisions, and anyone can verify that the bot is doing the right thing, but the protocol doesn't enforce it. This requires zero hard forks. It's deployable in 2-4 weeks.

**Hard governance** — the protocol itself rejects any vault spend that doesn't pass GV1-GV4. The Foundation **cannot** spend the vault even if it wanted to. This requires a hard fork to wire the rules engine into validation.

**Recommendation for SOST**: build the **soft governance** version now, because:

1. It's deployable on the timescale of the rest of Phase II (2-4 weeks).
2. It requires no coordination with miners for an upgrade.
3. It establishes the off-chain tooling (bot, Ethereum side, dashboards) that hard governance will reuse later.
4. It demonstrates the model in production with real flows before locking it into consensus.
5. The hard governance fork can then bundle with V6 (signature-bound PoW) into a single coordinated fork, instead of two separate ones.

In practice this means: **build all the wiring, the bot, the Ethereum side, and the RPCs now. Schedule the consensus enforcement of GV1-GV4 as part of the next planned hard fork (V6 or earlier).**

This memo specifies both pieces — the part you can build now and the part to bundle later.

---

## 3. Architecture overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                              SOST CHAIN                               │
│                                                                       │
│  Miners signal GV proposals via header version bits (8-28)            │
│  Bot polls node RPC: gv_get_proposal_status                           │
│  Node tracks proposals in side-database (Phase II)                    │
│  After fork V6: classify_gv_spend() blocks invalid spends             │
└──────────────────────┬────────────────────────────────────────────────┘
                       │
                       │ JSON-RPC over HTTPS
                       ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          BOT RELAYER (off-chain)                      │
│                                                                       │
│  - Polls SOST RPC every block                                         │
│  - Computes signal % from real block versions                         │
│  - When threshold met, posts answer to Reality.eth                    │
│  - Posts bond (~0.1 ETH) backing the answer                           │
│  - Anyone else can run a competing bot — bonds protect honesty        │
└──────────────────────┬────────────────────────────────────────────────┘
                       │
                       │ Ethereum tx
                       ▼
┌───────────────────────────────────────────────────────────────────────┐
│                              ETHEREUM                                 │
│                                                                       │
│  Reality.eth oracle: receives answer with bond, 7-day dispute window  │
│  Kleros (escalation): if disputed, decided by decentralized court     │
│  Zodiac Reality Module: reads Reality.eth verdict                     │
│  Gnosis Safe: receives execution trigger from Zodiac, releases funds  │
│  Funds = XAUT / PAXG → sent to OTC executor for gold purchase         │
└──────────────────────┬────────────────────────────────────────────────┘
                       │
                       │ off-chain
                       ▼
              Gold tokenization purchase
              → returns to Safe
              → vault balance increases
              → published in transparency report
```

The flow has **three trust zones**:

1. **SOST chain** — trusted via PoW consensus (the existing 24+ miners).
2. **Reality.eth + Kleros** — trusted via economic bonds and decentralized arbitration.
3. **OTC execution** — trusted via human reputation + multi-sig + transparency reports.

Phase II eliminates Foundation control over zones 1 and 2. Zone 3 remains human-mediated until Phase III replaces it with self-custody of physical gold.

---

## 4. What to build NOW (no hard fork required)

### 4.1 SOST node-side changes (no consensus impact)

#### Change A: real version-bit reading in `handle_getproposals`

**File**: `src/sost-node.cpp` lines 2304-2338.
**Current (broken)**:
```cpp
for (int j = start; j < (int)g_blocks.size(); ++j)
    versions.push_back(1); // Current blocks all version=1, no signals yet
```
**Fix**:
```cpp
for (int j = start; j < (int)g_blocks.size(); ++j)
    versions.push_back(g_blocks[j].header.version);
```
Trivial change. **Not** a hard fork — it just makes the existing RPC read real data.

#### Change B: let miners set signaling bits in the header version field

**File**: `src/sost-miner.cpp` (around the header construction at line 700+).
**Add**: a CLI flag `--signal-bits 0x00100000` (or read from a config file) that ORs the specified bits into the version field of constructed blocks. Default: zero (no signaling).

This is **soft** — old nodes already accept any version field value. New miners that signal don't break old nodes that don't understand the signal. This is exactly how Bitcoin BIP9 works.

#### Change C: persist GV proposals in a side-database

**Decision**: NOT in chain state (would require fork). Instead, in a local SQLite/JSON file in the node's data directory.

**New files**:
- `include/sost/gv_proposal_store.h`
- `src/gv_proposal_store.cpp`

**Schema**:
```
proposal_id (32-byte hash)  — SHA256 of (start_height || amount || destination || reason)
amount_stocks               — int64, requested spend
destination                 — PubKeyHash (20 bytes)
reason                      — string, max 256 chars
start_height                — int64
end_height                  — start_height + GV_APPROVAL_WINDOW (288)
proposal_type               — 0=general, 1=gold_purchase
status                      — defined / active / passed / failed / expired
signal_count                — refreshed from real block versions
foundation_supported        — bool, default false
```

This store is a **node-local cache**, not consensus state. Different nodes might have slightly different views during reorgs. Acceptable because the cross-chain bot waits for several confirmations before posting to Reality.eth.

#### Change D: new RPCs

| RPC | Purpose | Side effects |
|---|---|---|
| `gv_propose` | Create a new GVProposal | Writes to side-DB, broadcasts via P2P (new message type) |
| `gv_list_proposals` | Return all known proposals with current status | Reads side-DB |
| `gv_get_proposal` | Return one proposal by ID with detailed signal history | Reads side-DB |
| `gv_signal_status` | Return how many signal bits are set in recent blocks for a given proposal_id | Reads chain |
| `gv_check_activation` | For a proposal_id, return whether the threshold has been met | Reads chain + side-DB |

These are **read-mostly** RPCs. Only `gv_propose` writes anything, and only to the local side-DB. No chain state changes.

#### Change E: P2P propagation of proposals

When a node receives a `gv_propose` RPC, it stores it locally **and** broadcasts the proposal to peers via a new P2P message type (`MSG_GV_PROPOSAL`). Peers store it in their side-DB. This is gossip propagation, not consensus.

**Not a fork** because:
- Old nodes that don't understand `MSG_GV_PROPOSAL` will ignore it (P2P protocol allows unknown messages).
- Proposals don't affect block validity.
- Two nodes with different proposal sets still agree on block validity.

If a future fork wants to make proposals consensus-critical, it can promote them from side-DB to chain state at activation height.

---

### 4.2 Ethereum-side smart contracts (no SOST changes)

#### Component 1: Gnosis Safe v1.4.1
- Standard deployment via [Safe Wallet UI](https://app.safe.global/).
- 5-of-7 multisig in Phase II Phase A. Will become observers after Phase II Phase B.
- Initial signers: NeoB + 6 publicly identifiable SOST community members. (See §6 Open Questions.)
- Cost: ~$30 in ETH gas.

#### Component 2: Zodiac Reality Module
- Repo: [`gnosis/zodiac-module-reality`](https://github.com/gnosisguild/zodiac-module-reality).
- Deploy via Zodiac UI → install on the Safe.
- Configuration:
  - Oracle: Reality.eth (mainnet contract address `0xE78996A233895bE74a66F451f1019cA9734205cc`).
  - Question template: `"Did SOST proposal %s pass with ≥%d%% miner signaling at block %d?"`
  - Minimum bond: 0.1 ETH
  - Question timeout: 7 days
  - Cooldown: 24 hours (additional safety buffer after positive answer)
  - Expiration: 14 days
  - Arbitrator: Kleros Court (mainnet contract).
- Cost: ~$50 in ETH gas.

#### Component 3: TimelockController on top
- OpenZeppelin's `TimelockController.sol`, configured with a 30-day delay for **all** Safe-initiated transactions.
- Even if Reality.eth says yes, funds don't move for 30 more days.
- Provides a "panic window" during which the community can detect bot misbehavior and disable the module via emergency multisig action.
- Cost: ~$20 in ETH gas.

#### Component 4 (Phase II Phase B): swap Safe signers for the Reality Module as the executor

After ~3 months of running Phase A successfully:
- The 7 signers of the Safe execute one final transaction: **install Zodiac Reality Module as the only allowed initiator of transactions**.
- After this transaction, the 7 signers can no longer move funds directly. Only Reality.eth verdicts can.
- The signers become **observers and emergency veto holders** (they can only block bad outcomes, not initiate good ones).

This is the moment the Foundation loses executive control. It happens once, publicly, at a specific block on Ethereum. **From that block onward, SOST miners control the gold vault.**

---

### 4.3 Bot relayer (off-chain process)

#### What it does

```python
# Pseudo-code, conceptually:
while True:
    # 1. Read open Reality.eth questions tagged "SOST GV proposal"
    questions = reality_eth.get_open_questions(template_id=SOST_GV_TEMPLATE)

    for q in questions:
        proposal_id = parse_proposal_id(q.text)
        threshold = parse_threshold(q.text)
        block = parse_block_height(q.text)

        # 2. Query SOST node for that proposal's status
        status = sost_rpc("gv_get_proposal", [proposal_id])
        signals = sost_rpc("gv_signal_status", [proposal_id])

        # 3. Decide truthful answer
        passed = (status.signal_pct >= threshold)

        # 4. If we agree with the question's premise, post answer with bond
        if status.end_height <= current_block:  # voting window closed
            if not q.has_answer:
                reality_eth.submit_answer(
                    question_id=q.id,
                    answer=passed,
                    bond_eth=0.1,
                )

    sleep(60)
```

#### Architecture details

- **Run anywhere**: VPS, your laptop, a Raspberry Pi. The bot needs only:
  - Read access to a SOST full node (RPC)
  - Write access to Ethereum mainnet (an Ethereum wallet with ~0.5 ETH for gas + bonds)
  - Internet
- **Multiple bots can compete**: anyone in the world can run a bot. If the official bot is offline or compromised, a community member can post the truthful answer for 0.1 ETH and earn the dispute reward if anyone challenges.
- **Bond reclamation**: when the answer goes unchallenged for 7 days, the bot reclaims its bond + a small Reality.eth fee (negligible).
- **Failure modes**:
  - Bot is offline → nothing happens, vault sits idle. **Safe failure** (no funds moved without consensus).
  - Bot lies (says "passed" when it didn't) → anyone with 0.2 ETH can dispute, win the bond. Economic punishment.
  - Bot is censored → anyone else can run a bot. The protocol doesn't depend on a specific bot operator.

#### Implementation language
**Python with `web3.py` + `requests`** for the SOST RPC. ~300-500 lines total. Lives in a new repo `sost-gv-bot` (kept separate from `sost-core`).

---

### 4.4 Public-facing dashboard

A simple web page (hosted alongside the explorer) that shows:

- All SOST GV proposals (open, active, passed, failed)
- Live signal % per proposal
- Reality.eth question state for each proposal (no answer / pending / answered / disputed)
- Gnosis Safe balance in real time (link to Etherscan)
- Last 10 transparency reports (gold purchases executed)

This is the **single source of truth** for anyone watching how Phase II works in practice. It doesn't enforce anything — it just shows the truth so anyone can verify.

---

## 5. What to bundle with the next hard fork (V6 or earlier)

These changes touch consensus and must be coordinated as a single fork.

### 5.1 Wire `classify_gv_spend()` into `tx_validation.cpp`

**File**: `src/tx_validation.cpp`
**Where**: in the function that validates non-coinbase transactions, **after** UTXO lookup but **before** general output checks.

**Pseudo-code**:
```cpp
// New: detect if any input is from the Gold Vault address
bool has_gv_input = false;
int64_t gv_spend_amount = 0;
for (const auto& input : tx.inputs) {
    const Utxo* utxo = utxo_set.find(input.prev_txid, input.prev_index);
    if (utxo && utxo->pubkey_hash == gold_vault_pkh) {
        has_gv_input = true;
        gv_spend_amount += utxo->amount;
    }
}

if (has_gv_input && height >= GV_GOVERNANCE_ACTIVATION) {
    // Look for GV_PAYLOAD_GOLD_PURCHASE marker in tx payload
    bool has_gold_marker = tx_payload_has_marker(tx, GV_PAYLOAD_GOLD_PURCHASE);

    // Look for GVApprovalToken in tx payload
    GVApprovalToken token{};
    bool has_token = parse_approval_token_from_payload(tx, &token);

    // Read current monthly tracker from chain state
    GVMonthlyTracker tracker = chain_state.gv_monthly_tracker;

    int64_t vault_balance = utxo_set.balance_for(gold_vault_pkh);

    GVSpendType cls = classify_gv_spend(
        vault_balance, gv_spend_amount,
        has_gold_marker, has_token ? &token : nullptr,
        tracker, height);

    if (cls == GVSpendType::REJECTED) {
        return TxValidationResult::Fail(
            TxValCode::GV1_VAULT_SPEND_REJECTED,
            "Gold Vault spend rejected by GV1-GV4 rules"
        );
    }
}
```

### 5.2 Add chain state tracking for proposals

**New chain state component**: `gv_proposal_state` persisted alongside the UTXO set. Per node, rebuilt during reindex.

**Schema**:
```
map<proposal_id, GVProposalChainState>
where GVProposalChainState = {
    proposal: GVProposal
    signal_count: int32  // refreshed every block
    status: defined / active / passed / failed / expired
    activated_height: int64  // -1 if not activated
}
```

Updated by `process_block()`: each block contributes to the signal counts of all open proposals based on its version field.

### 5.3 Define proposal creation as on-chain transaction type

**New transaction type**: `TX_TYPE_GV_PROPOSAL` (0x04 or similar). Carries:
- proposal_id (computed)
- amount_stocks
- destination_pkh
- reason (max 256 bytes)
- start_height
- proposal_type (general / gold_purchase)

These tx are non-spend (no inputs/outputs), they only register intent. They cost the standard tx fee.

### 5.4 Define `GVApprovalToken` payload format

When a tx spends from the vault, its payload must include the matching approval token. The token format:
```
| version (1) | proposal_id (32) | approved_height (8) | signal_pct (1) | threshold (1) | foundation_flag (1) |
   = 44 bytes total
```

The validator reconstructs the token from the payload, looks up the proposal in chain state, verifies it actually passed the threshold at `approved_height`, and only then allows the spend.

### 5.5 Push `GV_GOVERNANCE_ACTIVATION` to a realistic height

**Current value**: 5000 (in ~3-4 days from audit time, **way too soon** to ship a fork).
**Recommended value**: bundle activation height with V6 fork height. Probably block 25,000 - 50,000 (4-9 months from now).

This requires **a node release that pushes the constant** before block 5000 hits. If not done in time, the constant fires at block 5000 and **does nothing** (because the rules aren't wired) — embarrassing but not dangerous, since the consensus enforcement doesn't exist yet anyway.

---

## 6. Open questions

These must be answered before each phase of implementation.

### Q1. The private key question
> Does anyone hold the private key for `ADDR_GOLD_VAULT`?

This determines:
- Whether the vault is currently safe by code (no key) or by trust (Foundation holds key).
- How urgent the Phase II Phase B switch (Safe → Reality Module) really is.
- What the honest narrative is in the BTCTalk ANN.

**Action**: NeoB to verify and document privately. Do not write the answer in this memo.

### Q2. Who are the 7 (or 5) initial Safe signers?
- Phase A multisig signers must be publicly identifiable.
- Geographic distribution preferred.
- Conflict-of-interest avoidance: no single firm/family/jurisdiction can dominate.
- Realistic count: with only ~24 miners and 1 month live, finding 6 is hard. Start with 3-of-5 if needed.

**Action**: NeoB to identify candidates privately and contact them one by one. Do not solicit publicly.

### Q3. Who runs the bot?
- The official bot runs on the Foundation's infrastructure for v1.
- After Phase II launches, document how anyone can run a competing bot (provide the source code, RPC examples, Reality.eth question template).
- A second public bot operator (independent of the Foundation) would significantly strengthen decentralization within ~3 months of Phase II launch.

### Q4. What happens to the Foundation veto?
- `proposals.h:89` — the Foundation veto expires automatically at block 263,106 (~5 years from genesis).
- During Epoch 0-1, the Foundation can effectively contribute +10% to any GV3 vote.
- **Decision needed**: should the Foundation veto apply to Phase II proposals? If yes, it changes the Reality.eth question template to include the foundation flag.

### Q5. Should proposals require a fee or a stake?
- Without friction, anyone can spam proposals.
- Options:
  - Charge a creation fee (e.g. 1 SOST burned)
  - Require the proposer to lock SOST collateral (refunded if proposal passes, slashed if it fails)
  - Foundation gatekeeping (centralized, bad)
- Recommendation: **1 SOST burn per proposal**. Cheap enough not to gatekeep, expensive enough to deter trivial spam.

### Q6. How does the Reality.eth question reference a SOST proposal?
- The question text needs to encode `proposal_id`, threshold, and block height in a parseable way.
- Template: `"Did SOST proposal 0x{proposal_id} pass with at least {threshold}% miner signaling by block {block_height}? See https://sostcore.com/gv/{proposal_id} for details."`
- The dashboard URL gives reviewers a clickable verification link.

### Q7. Bot funding model
- Bonds + gas: ~0.5 ETH float at any time, refilled from foundation funds initially.
- After Phase II is mature, the bot's bond reclaims (which produce a small profit per unchallenged answer) cover gas costs.
- For the first year, expect to spend ~0.1-0.5 ETH/month on bot operations.

---

## 7. Code touchpoints (verified line numbers)

### To modify NOW (no fork)

| File | Lines | Change |
|---|---|---|
| `src/sost-node.cpp` | 2316-2317 | Replace dummy versions with real `g_blocks[j].header.version` |
| `src/sost-miner.cpp` | (around 700) | Add `--signal-bits` CLI flag and OR into header version |
| `src/sost-node.cpp` | new code | Add 5 new RPCs (`gv_propose`, `gv_list_proposals`, `gv_get_proposal`, `gv_signal_status`, `gv_check_activation`) |
| `include/sost/gv_proposal_store.h` | NEW | Side-DB for proposals (SQLite or JSON file) |
| `src/gv_proposal_store.cpp` | NEW | Implementation |
| `src/sost-node.cpp` | new P2P handler | New message type `MSG_GV_PROPOSAL` for proposal gossip |

Estimated effort: **200-400 LOC + tests + a few days of integration work**. Achievable in 1-2 weeks.

### To modify in NEXT FORK (consensus-critical)

| File | Lines | Change |
|---|---|---|
| `include/sost/consensus_constants.h` | 36 | Push `GV_GOVERNANCE_ACTIVATION` to V6 activation height |
| `src/tx_validation.cpp` | new code | Wire `classify_gv_spend()` into the tx validation pipeline |
| `src/block_validation.cpp` | new code | Track `GVMonthlyTracker` in chain state, reset per window |
| `include/sost/transaction.h` | new tx_type | `TX_TYPE_GV_PROPOSAL = 0x04` |
| `src/transaction.cpp` | new serializers | Serialize/deserialize `GVProposal` and `GVApprovalToken` payloads |
| `include/sost/chain_state.h` | new state | `gv_proposal_state` map |
| `tests/test_gv_consensus.cpp` | NEW | Integration tests for consensus enforcement |

Estimated effort: **400-800 LOC + tests + 30 days testnet**. Bundle with V6 (signature-bound PoW) for one coordinated fork.

### Ethereum side (NEW repo, not in sost-core)

| Repo | Component | LOC estimate |
|---|---|---|
| `sost-vault-contracts` | Gnosis Safe deployment scripts (forge/hardhat) | ~50 (config files) |
| `sost-vault-contracts` | Zodiac Reality Module deployment | ~100 |
| `sost-vault-contracts` | TimelockController + tests | ~200 |
| `sost-vault-contracts` | End-to-end deployment runbook | docs only |
| `sost-gv-bot` | Python bot relayer | ~400 |
| `sost-gv-dashboard` | Public web dashboard | ~600 (frontend + backend) |

Estimated total: **~1500 LOC** new code, mostly in TypeScript/Solidity/Python. None of it lives in `sost-core`.

---

## 8. Implementation timeline (realistic)

### Sprint 1 — Weeks 1-2 (immediate, no fork)
- Fix `handle_getproposals` dummy versions bug
- Add miner `--signal-bits` flag
- Stand up Gnosis Safe 5-of-7 (or 3-of-5) on Ethereum mainnet
- Identify and onboard the signers
- Write the bot relayer (basic version, single SOST node read)
- Build the dashboard (read-only, no proposal creation yet)

### Sprint 2 — Weeks 3-4
- Implement `gv_propose`, `gv_list_proposals`, `gv_get_proposal` RPCs
- Implement `gv_proposal_store` side-DB
- Add P2P gossip for proposals
- First end-to-end test: create proposal in SOST, miner signals, bot reads, posts to Reality.eth, Safe receives execution trigger (testnet)

### Sprint 3 — Weeks 5-6
- Deploy Zodiac Reality Module on the production Safe
- Connect Reality.eth to production
- First **soft-governance** mainnet test: proposal → signal → bot → Reality.eth → Safe
- Publish transparency report template

### Sprint 4 — Weeks 7-8
- Migrate Safe control: signers vote to install Zodiac as sole executor (Phase II Phase B)
- Public announcement: "Foundation no longer has executive control over the gold vault"
- Document the runbook for community bot operators

### Sprint 5+ — Months 3-6
- Real OTC purchases routed through the Phase II flow
- Monthly transparency reports
- Monitor bot reliability, signer behavior, dispute rate
- Iterate based on real-world friction

### Fork V6 — Month 6-9 (if conditions met)
- Bundle GV consensus enforcement with signature-bound PoW
- Push `GV_GOVERNANCE_ACTIVATION`, wire `classify_gv_spend()`
- Activate as a single coordinated fork at a planned height
- After activation, Phase II governance is enforced by consensus, not just by social commitment

---

## 9. Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| The private key for `ADDR_GOLD_VAULT` is held by a single person and is lost or compromised | Catastrophic | Unknown until Q1 answered | Confirm key custody NOW; if Foundation holds it, move to multisig immediately |
| Bot operator goes offline → vault frozen | Medium | Medium | Document community bot operation; encourage at least 2 independent bots |
| Reality.eth deprecated or hacked | High | Low | Reality.eth has been live since 2018; high integration risk concentration but acceptable given lack of alternatives |
| Signers collude in Phase A multisig | High | Low | Public identities; reputation cost; transparency reports; 30-day timelock |
| Phase II ships and nobody proposes anything | Low | High | Initial proposals come from the Foundation as "test runs"; dashboard shows zero activity is OK |
| Hard fork V6 fails to coordinate | Medium | Low | Long lead time (4 weeks announcement); only ~24-30 miners to coordinate; canonical client distribution |
| Migration of Safe control to Zodiac is botched (signers can't be removed) | Catastrophic if unrecoverable | Low | Test on Sepolia testnet first; have OpenZeppelin auditor review the transaction; document recovery |

---

## 10. The narrative for the BTCTalk ANN (when ready)

> **SOST Gold Vault Governance — Phase II**
>
> The SOST Gold Vault is a constitutional 25% allocation of every block reward, hardcoded into the consensus rules. Today, it is custodied via a 5-of-7 multisig on Ethereum (`0x...`), with seven publicly identified signers and a 30-day timelock on all withdrawals.
>
> **In Q3 2026, executive control of the Vault transitions from human signers to on-chain governance.** A Zodiac Reality Module is installed on the Safe. From that block onwards, the only way to move funds from the Vault is for SOST miners to vote in favor of a specific proposal with at least 75% threshold (rising to 95% after Epoch 2). The seven signers become observers, retaining only veto power against bot misbehavior — they cannot initiate or approve withdrawals.
>
> **In a future protocol fork (V6), the consensus rules of the SOST chain itself enforce these governance decisions.** Any block containing a Gold Vault spend that does not match a passed GV3 proposal is rejected by every honest node. At that point, the Vault is governed not by social trust, but by cryptographic verification.
>
> **In a future Phase III, the SOST Foundation establishes a physical gold custody arrangement** in a Swiss or London vault, and the tokenized gold (XAUT, PAXG) held in the Safe is gradually replaced by audit reports from a real custodian. SOST exits the smart-contract dependency entirely.
>
> The Foundation will lose control of the Vault on a publicly announced date. There is no "trust us" — only "verify us, then verify the protocol, then verify the gold."

This is the position of strength to hold. **It is technically true, defensible, and unique among gold-backed crypto projects.**

---

## 11. Maintenance

This document must be re-read and updated:
- After every change to `gold_vault_governance.h`, `tx_validation.cpp`, or `consensus_constants.h`
- After each Phase II sprint completion
- Before any public statement about vault governance
- Whenever an audit point in §1 ("Audit findings") is invalidated by code changes
- Every 3 months minimum

If this document falls out of sync with the codebase by more than 6 months, **rerun the audit** (§1) before trusting any of the line numbers or claims.

---

## Appendix A — Quick verification commands

To re-run the audit yourself:

```bash
# 1. Verify the rules engine still passes
cd build && ./test-gold-vault

# 2. Verify classify_gv_spend is still dead in src/
grep -rn classify_gv_spend src/  # should return nothing

# 3. Verify the dummy versions bug still exists
grep -A1 "Current blocks all version=1" src/sost-node.cpp

# 4. Verify no production use of GVProposal
grep -rn "GVProposal\|GVApprovalToken" src/  # should return nothing

# 5. Verify the constitutional addresses haven't moved
grep -A2 "Constitutional addresses" include/sost/params.h
```

If any of these checks change, **the line numbers in this memo are out of date** — re-verify before using them.

— End of memo —
