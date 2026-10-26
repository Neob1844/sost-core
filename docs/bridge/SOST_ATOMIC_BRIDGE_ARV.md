# SOST Atomic Bridge — Atomic Reserve Vault (ARV)

Target architecture · design + audit · 2026-10-26

STATUS: RESEARCH / DEVELOPMENT · NOT ACTIVE · NOT MAINNET DEPLOYED · NOT AUDITED · NOT YET PROVEN

This document sets the **target architecture** of the SOST bridge between native SOST and wSOST
on Ethereum. The architecture is called the **SOST Atomic Bridge**. Its mechanism is the
**Atomic Reserve Vault (ARV)**.

The lock/mint design in `C701_AUTOMATED_BRIDGE_SPEC.md` ("Automated Bridge V2") is no longer the
target. It stays in the repository for three uses:

* as the **conventional reference model**, kept for comparison;
* as the **existing prototype**;
* as a **source of components** for ARV (section 9).

Nothing here changes consensus, deploys a contract or moves funds.

---

## 1. Decision

| Role | What |
|---|---|
| OUR TARGET | SOST Atomic Bridge = Atomic Reserve Vault |
| REFERENCE | conventional lock → mint / burn → release bridge (C701/C703) |
| EXISTING PROTOTYPE | C701/C703 contracts, engine and tests (component source) |
| RESEARCH COMPARISON | Atomiq, THORChain, Chainflip, other bridge families |

The ARV design has these properties:

* **No mint per operation.** wSOST is preissued once and immobilized in the Ethereum Atomic Vault.
* **No burn on the return.** Returned wSOST goes back to the immobilized inventory.
* **Native SOST is never burned.**
* **Atomic swaps, both directions,** using the native SOST HTLC (active on mainnet since #16,000)
  and an Ethereum HTLC with the same `sha256` hashlock.
* **No liquidity pool, and no human approval per operation.**
* **Gold Access Key unchanged and separate.** XAUT goes 100% to Gold Reserve V2 and is not
  part of the 1:1 backing.

## 2. Accounting (premint model)

`totalSupply(wSOST)` includes the immobilized inventory, so it is **not** the quantity to compare
with the reserve. The contract and the engine track:

| Quantity | Meaning |
|---|---|
| TOTAL_PREMINTED_wSOST | fixed at deployment (no minter afterwards) |
| IMMOBILIZED_wSOST | free inventory held by the Atomic Vault |
| PENDING_wSOST | wSOST inside entry or exit HTLCs of the vault |
| CIRCULATING_wSOST | TOTAL − IMMOBILIZED − PENDING |
| BACKING_NATIVE_SOST | confirmed reserve UTXOs |
| PENDING_NATIVE_SOST | user entry HTLCs claimable by the reserve; reserve exit HTLCs |

The invariants:

* **Always:** `CIRCULATING_wSOST <= BACKING_NATIVE_SOST + claimable PENDING_NATIVE_SOST`.
* **At rest, after every completed operation:** `CIRCULATING_wSOST == BACKING_NATIVE_SOST`, a
  backing ratio of 100%.

The 990,000 immobilized wSOST in the example below count neither as backed nor as circulating.

Example: 1,000,000 preminted wSOST, 990,000 immobilized and 10,000 circulating, against a native
reserve of 10,000 SOST. The backing ratio is 10,000 / 10,000 = 100%.

**Premint size (audit note).** A preminted inventory is a target in itself: whoever can release
it holds a bound on the damage. Inventory should be sized to the exposure caps and topped up in
tranches, not issued all at once. The 1,000,000 figure is illustrative.

## 3. Entry — SOST → wSOST (1,000 SOST)

**Parameters.** SOST blocks are about 10 minutes. The timeouts below are proposed values.

* `T_user`: the user's SOST HTLC refunds at `+288` blocks (about 48 h).
* `T_vault`: the vault's Ethereum HTLC refunds after about 12 h.
* `T_user` must exceed `T_vault` plus the confirmation wait plus a safety margin.

**Steps.**

1. **Request (Ethereum).** The user's wallet generates a secret `s` locally and computes
   `H = sha256(s)`. The user opens an entry request bound to `H`, the amount, the Ethereum
   recipient and an expiry. In the same transaction the user **escrows the Gold Access Key in
   XAUT** inside the vault contract. If the user does not have enough XAUT, the operation fails
   here, before any SOST is locked.
2. **Lock SOST (SOST).** The user creates `OUT_HTLC_LOCK` with:
   * `hashlock = H`;
   * `claim_pkh` = the reserve claim key;
   * `refund_pkh` = the user;
   * `refund_height = now + 288`.
3. **Verify.** The engine waits for 30 confirmations. It checks the amount, the hashlock, the
   claim key, the refund height and single use.
4. **Release inventory into an HTLC (Ethereum).** On the engine's authorization, the vault moves
   1,000 wSOST from IMMOBILIZED to PENDING, in an HTLC with:
   * hashlock `H`;
   * beneficiary = the user's address, which is fixed;
   * refund back to the inventory after `T_vault`.
5. **Claim wSOST (Ethereum).** The user calls `claim(s)`. Because the beneficiary is fixed, anyone
   holding `s` may submit this call. It atomically moves:
   * 1,000 wSOST from PENDING to the user;
   * the escrowed XAUT to Gold Reserve V2.

   The claim publishes `s`.
6. **Claim SOST (SOST).** The engine claims the user's HTLC with `s`. The claim pays into the
   native reserve: a single cold key before V17, `OUT_MULTISIG` 3-of-5 from V17 on.

**After the entry:**

| | before | after |
|---|---|---|
| SOST reserve | 10,000 | 11,000 |
| wSOST circulating | 10,000 | 11,000 |
| wSOST in vault | 990,000 | 989,000 |
| backing | 100% | 100% |

No mint happens. No XAUT is part of the backing.

**Why the entry still needs verification.** Step 4 must not happen for a SOST lock that does not
exist. Otherwise a user would receive wSOST for nothing, because the user knows `s`. The
Ethereum vault therefore needs to know that the SOST HTLC is real and final. Today that knowledge
comes from the engine's authorization, which can be a threshold of keys: the prototype already
supports 2-of-3 authorizers. Later it could come from a SOST light client on Ethereum
(section 7).

ARV turns "mint authority" into "release-from-inventory authority". Damage from a compromised
verifier is bounded by the inventory and the caps; it is not removed.

## 4. Exit — wSOST → SOST (500 wSOST)

**Parameters.**

* `T_user'`: the user's Ethereum HTLC refunds after about 48 h.
* `T_res`: the reserve's SOST HTLC refunds at `+72` blocks (about 12 h).

**Steps.**

1. **Lock wSOST (Ethereum).** The user generates `s'` and `H' = sha256(s')`. The user locks
   500 wSOST in the vault's exit HTLC with:
   * beneficiary = the vault inventory, which is fixed;
   * refund to the user after `T_user'`.

   No XAUT is charged on the return.
2. **Verify.** The engine waits for Ethereum finality, about 2 epochs.
3. **Fund the SOST HTLC (SOST).** The reserve funds `OUT_HTLC_LOCK` with:
   * 500 SOST minus the SOST network fee;
   * `hashlock = H'`;
   * `claim_pkh` = the user;
   * `refund_height = now + 72`, refunding to the reserve.
4. **Claim SOST (SOST).** The user claims the SOST with `s'`, and that reveals `s'`.
5. **Settle (Ethereum).** Anyone with `s'` (the engine, a watchtower or the user) calls `claim(s')`
   on the exit HTLC. The 500 wSOST return from PENDING to IMMOBILIZED. No burn.

**After the exit:**

| | before | after |
|---|---|---|
| SOST reserve | 10,000 | 9,500 |
| wSOST circulating | 10,000 | 9,500 |
| wSOST in vault | 990,000 | 990,500 |
| backing | 100% | 100% |

SOST does not need to verify an Ethereum burn. What it needs is a reserve signer that funds the
SOST HTLC only after it sees a final Ethereum exit lock. That decision is made off-chain, and it
is the custody problem (section 6).

## 5. Failure and refund paths

| Case | Outcome |
|---|---|
| Not enough XAUT | fails at step 1 (escrow); nothing locked on SOST |
| Vault never releases (engine down, reserve paused) | user refunds the SOST at `T_user`; XAUT escrow returns after expiry |
| User never claims wSOST | vault HTLC refunds to inventory at `T_vault` (anyone may trigger); user refunds SOST at `T_user`; XAUT escrow returns |
| User claims wSOST, engine fails to claim SOST before `T_user` | **under-backing risk**: the user could refund the SOST and keep the wSOST. Mitigated by margin and redundant claimers, but the SOST claim needs the claim key (no keyless claim on SOST today) |
| Exit: reserve never funds | user refunds wSOST at `T_user'` |
| Exit: user never claims SOST | reserve refunds at `T_res`; user refunds wSOST at `T_user'` |
| Exit: user claims SOST late | anyone settles the wSOST with `s'` before `T_user'` (permissionless on Ethereum) |
| Same secret replayed | each hashlock and swap id is single-use in the vault; engine rejects a reused `H` |
| Reorg of the SOST lock after step 4 | the vault HTLC cannot be cancelled without breaking atomicity, so the protection is depth (30 confirmations) plus a security hold. Residual risk bounded by depth |
| Concurrent exits | each exit uses distinct reserve UTXOs; the engine serializes reserve spending |
| Reserve insufficient | cannot happen while the invariant holds; the engine refuses to fund, and the user refunds |

**Audit finding — a secret revealed in a reverted transaction.** If the XAUT payment were taken
inside `claim(s)` and the claim reverted, `s` would still be public on-chain. The reserve could
then claim the user's SOST although the user received nothing. This is why the Gold Access Key
is escrowed at step 1 and the claim is made unconditional (fixed beneficiary, no other
precondition).

**Never both.** Within one swap, a user cannot end with both wSOST and a SOST refund **if** the
reserve claims in time. Section 6 explains why that "if" is the open point.

## 6. The central problem — who controls the native SOST reserve?

An atomic swap coordinates the exchange. It does **not** decide who controls the SOST afterwards.

**What exists today and at V17** (read from `include/sost/transaction.h` and
`docs/v40000/NATIVE_MULTISIG_SPEC_40000.md`):

* **Native HTLC.** `OUT_HTLC_LOCK` is active since #16,000. Its fields are a `sha256` hashlock,
  an absolute `refund_height`, and **single-key** `claim_pkh` and `refund_pkh`.
* **V17 multisig.** `OUT_MULTISIG` arrives at #40,000 as M-of-N with N ≤ 15 and no script engine.
  * A multisig **may fund** an HTLC.
  * An HTLC claim **may pay to** `OUT_MULTISIG`.
  * A multisig **cannot be the claimant or refund key** of an HTLC.
  * A timelocked recovery path is out of scope.

**What follows from that:**

* **Custody in flight.** Every entry claim is signed by a single claim key, and the claimer chooses
  the outputs of the claim transaction. A stolen claim key can redirect in-flight entries.
* **Liveness.** Only the claim-key holder can claim, so watchtowers cannot do it for the reserve.
* **Custody at rest.** A 3-of-5 reserve reduces single-key risk. Three signers can still move the
  whole reserve anywhere.
* **Exit decisions.** The SOST chain cannot see Ethereum, so the reserve signers decide off-chain
  when to fund an exit HTLC.

**Conclusion: with current and V17 primitives, arbitrary withdrawal by the reserve signers is NOT
impossible.**

The missing primitives below are a research list. None of them is authorized.

| # | Primitive | Effect |
|---|---|---|
| P1 | destination-committed HTLC: claim output fixed at lock time (for example the reserve MSH), claim valid with the preimage alone | removes the in-flight hot key; makes the entry claim permissionless (watchtowers) and closes the liveness gap |
| P2 | HTLC with a multisig claimant or refund key | lets the reserve own the HTLC legs directly |
| P3 | reserve vault with delayed spending + recovery path (in the spirit of Bitcoin's OP_VAULT proposal) | makes an unauthorized withdrawal slow, public and recoverable |
| P4 | covenant: reserve UTXOs spendable only into exit HTLCs whose refund returns to the reserve, plus rate limits | bounds what signers can do per period |
| P5 | SOST consensus able to verify Ethereum state (light client or proof) | the only family that makes "release only against a real Ethereum exit lock" a rule instead of a decision |

**Status: NATIVE_CUSTODY_SOLVED = NO. CONSENSUS_CHANGE_REQUIRED = YES** for a non-discretionary
reserve: P1 to P4 are consensus changes, and P5 is a large research item. No consensus change is
made or proposed for activation here.

## 7. Cross-chain proofs — new role

ARV does not need Ethereum to verify every SOST block in order to exchange. The entry release
(step 4) is still the place where a proof would replace the verifier.

The SOST PoW has a compact form. ConvergenceX has a compact transcript proof (`verify_cx_proof`,
about 10–20 ms natively, with the 4 GB dataset recomputed O(1) per witness), so a SOST light
client on Ethereum is **not ruled out**. However, reproducing that verification and the cASERT
difficulty rules in the EVM has not been measured, and its gas cost is unknown.

This is the comparison with Atomiq. Atomiq verifies Bitcoin double-SHA256 headers on-chain, which
is cheap.

Other uses of proofs, all research:

* reserve verification and public audit;
* settlement verification;
* reorg detection;
* recovery;
* reducing the trust in the step-4 authorizer.

## 8. Comparison with existing systems

Sources:

* <https://docs.atomiq.exchange/overview/core-primitives/utxo-controlled-vault>
* <https://docs.atomiq.exchange/overview/core-primitives/bitcoin-light-client>
* <https://docs.chainflip.io/protocol/protocol-overview>
* <https://docs.thorchain.org/technical-documentation/technology/bifrost-tss-and-vaults>

| | Atomiq | THORChain | Chainflip | SOST Atomic Bridge (target) |
|---|---|---|---|---|
| Native-chain verification | on-chain Bitcoin light client (PoW, difficulty, most-work fork choice); headers submitted permissionlessly | validators witness (Bifröst), supermajority | every validator witnesses | engine authorization today; SOST light client = research |
| Vault control | smart-chain vault releases only against verified Bitcoin transactions; UTXO chaining serializes withdrawals | TSS vaults (docs: Asgard 27-of-40), bonded RUNE | aggregate key, FROST threshold 100 of 150 | Ethereum vault contract + native reserve (single cold key → V17 3-of-5) |
| Liquidity | LP liquidity in the vault | liquidity pools (AMM) | JIT AMM, balances on the State Chain | **none**: preissued inventory, 1:1 |
| Validator network | no (watchtowers submit proofs) | yes | yes | no |
| What moves | destination-chain liquidity | native assets via pools | native assets via vaults | inventory wSOST ↔ native SOST |

* **Similarities with Atomiq:** a UTXO-native chain, a vault, atomic settlement, withdrawals tied
  to UTXO state, and less reliance on custodial signers.
* **Differences:** Atomiq verifies Bitcoin PoW on the smart chain and releases LP liquidity. The
  SOST design uses preissued wSOST and native 1:1 reserve accounting, and has no SOST light client
  yet.

We do not claim the SOST design is more advanced. Nor do we claim it is novel: related concepts
such as UTXO-controlled vaults already exist.

The SOST design aims to avoid a separate validator coordination network for every conversion. It
is not claimed to be more secure than one.

## 9. Audit of C701/C703 components

| Component | Class | Note |
|---|---|---|
| `GoldAccessKey.sol` (fee math, ceil, cap 250, min 100 EUR) | REUSE_AS_IS | |
| `GoldReserveV2.sol`, `ReserveBase.sol`, `QuarantineVault.sol` | REUSE_AS_IS | XAUT destination, guardians, no arbitrary withdrawal |
| `SigLib.sol` (low-S ECDSA) | REUSE_AS_IS | |
| `WSOST.sol` | ADAPT_FOR_ARV | mint once to the vault at deployment, then no minter; remove `burn` |
| `SOSTBridge.sol`: EIP-712 domain, threshold authorizers, nonces, price quotes, caps, pause, config timelock | ADAPT_FOR_ARV | becomes the Atomic Vault |
| `SOSTBridge.sol`: `mint`, `burnForRelease`, `recordRelease`, `revokeDeposit` | REFERENCE_ONLY | replaced by entry/exit HTLC legs with fixed beneficiaries and permissionless claim/refund |
| `contracts/atomic-swap/AtomicSwapHTLCv2.sol` (main, undeployed) | ADAPT_FOR_ARV | same `sha256` + timeout primitive; needs fixed-destination, anyone-can-claim legs |
| `ops/c701bridge/sost.py` (RPC), `eip712.py`, `fee.py`, `pricing.py` | REUSE_AS_IS | |
| `ops/c701bridge/engine.py`: confirmations, reorg hold, single use, append log, reconcile | ADAPT_FOR_ARV | scan `OUT_HTLC_LOCK` instead of capsule deposits; reconcile CIRCULATING vs BACKING |
| capsule `C701:0x…` deposit binding | REFERENCE_ONLY | the hashlock and request binding replace it |
| state machine | ADAPT_FOR_ARV | REQUEST → SOST_HTLC_LOCKED → CONFIRMED → VAULT_HTLC_READY → CLAIMED → RESERVE_CLAIMED → COMPLETED; EXPIRED / REFUND_ELIGIBLE / REFUNDED / SECURITY_HOLD |
| tests: fee, price, signature, pause, caps | REUSE_AS_IS | |
| tests: mint/burn accounting | REFERENCE_ONLY | ARV needs inventory invariants |
| `C701_AUTOMATED_BRIDGE_SPEC.md` | REFERENCE_ONLY | conventional model |
| web demo dashboard | ADAPT_FOR_ARV | done 2026-10-26 (demo only) |
| federated observers, Gold → wSOST desk | OBSOLETE | already historical |

## 10. Proof of concept (testnet / devnet only) — NOT STARTED

The native HTLC exists on the testnet and devnet profiles (`V14_5_HEIGHT` 30 / 11). The PoC uses
100 fictitious preminted wSOST on a local EVM chain.

| Test | Requirement |
|---|---|
| A | 100 SOST → 100 existing wSOST, no manual step |
| B | 100 wSOST → 100 SOST |
| C | counterparty disappears, both sides refund |
| D | timelock ordering |
| E | engine stops mid-swap |
| F | same secret replay |
| G | concurrent swaps |
| H | reserve insufficient |
| I | reorg |
| J | attempted arbitrary reserve withdrawal |
| decisive | 500 SOST → 500 wSOST → 500 SOST with 1:1 kept |

**Success requires all of:**

* no human approval per swap;
* no double spend and no double claim;
* safe refunds;
* 1:1 accounting;
* **no arbitrary reserve withdrawal**.

**Expected result of test J with today's primitives: FAIL.** The signers of the reserve can
withdraw. Test J can only pass with P1–P5.

Until then: ATOMIC_RESERVE_VAULT = RESEARCH_ONLY.

## 11. Gold Access Key

Unchanged:

* 0.10% of the operation value, minimum 0.50 EUR, maximum 250 EUR;
* minimum operation 100 EUR equivalent;
* 100% goes to Gold Reserve V2, escrowed at entry step 1 and paid at claim;
* nothing on the return.

XAUT does not back wSOST. It is not part of the 1:1 ratio and it is not liquidity. Real
operations also stay blocked by the valuation gate: SOST has no approved SOST/EUR methodology.
