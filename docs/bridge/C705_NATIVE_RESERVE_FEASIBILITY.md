# C705 — SOST Atomic Bridge: native reserve consensus feasibility study

Research only · 2026-10-26

Ground rules for this study: nothing is implemented, V17 is not modified, consensus is not
changed, nothing is deployed and no funds move.

The study answers one question:

> What does SOST need so that a reserve output **cannot be spent arbitrarily by anyone** —
> no daemon, no guardians, no multisig — but **can** be spent by (A) a valid redemption, (B) a
> valid refund and (C) a defined recovery?

Short answer:

* **Two new SOST consensus primitives are enough.** HTLCs and V17 multisig are not needed for
  the reserve at all.
* **One Ethereum-side component (not a SOST consensus change) is also required:** a SOST light
  client contract.
* "100% trustless" is not achievable by any bridge. With these pieces there would be **no key, no
  multisig, no human approval and no admin**. What remains are the consensus assumptions of both
  chains, code correctness, one honest relayer or watcher, and a one-time bootstrap checkpoint.

Companion artefact: `research/arv/arv_model.py`, a bounded model check. Results are in §14.

---

## 0. The finding that changes the design

**A reserve that nobody controls can only react to events its own chain can verify.**

Hashed time-locked contracts (HTLCs) do not change this. In an HTLC swap, each side has an
agent who *decides* to lock only after seeing the other side's lock. A keyless reserve has no
agent. If anyone could make the reserve lock SOST under a hashlock of their choice, an attacker
would pick a hashlock whose secret they know and claim the SOST.

The same argument applies on Ethereum: if anyone could make the vault lock wSOST without proof
of a SOST deposit, anyone could collect wSOST.

Two consequences follow:

* **Exit (wSOST → SOST):** SOST consensus must verify an Ethereum fact — "these wSOST went back
  to the vault, owed to this SOST address".
* **Entry (SOST → wSOST):** the Ethereum vault must verify a SOST fact — "this deposit exists,
  is final, and has this amount and this recipient".

So the keyless Atomic Bridge is a **two-way light-client bridge** with a **preissued, immobilized
wSOST inventory** instead of minting. Atomicity no longer comes from hashlocks. It comes from
two rules:

* **Single arbiter per entry.** The Ethereum vault decides once whether an entry is RELEASED or
  CANCELLED. The two are mutually exclusive by timestamp.
* **Single use per exit.** An exit is irrevocable on Ethereum and payable exactly once on SOST.

HTLCs remain useful only for an optional peer-to-peer fast path, where market makers swap their
own funds through the separate Atomic Swap service. That fast path never touches the reserve.

The name stays: **SOST Atomic Bridge**. The premint and inventory accounting of the ARV design
are unchanged.

## 1. P1–P5 from the C704 audit — exact definitions and verdict

**P1 — destination-committed HTLC**

| Field | Content |
|---|---|
| PURPOSE | The claim output is fixed when the HTLC is locked, so anyone holding the secret can claim and nobody chooses the destination |
| CURRENT_SOST_LIMITATION | an `OUT_HTLC_LOCK` claim must be signed by the key whose hash is the payload field `claim_pkh`, and the claimer chooses the outputs |
| WHY_HTLC_IS_NOT_ENOUGH | the HTLC as defined requires a key |
| WHY_V17_MULTISIG_IS_NOT_ENOUGH | a multisig cannot be a claimant (spec D5) |
| CONSENSUS_CHANGE_REQUIRED | yes |
| SECURITY_PROPERTY | open execution, no in-flight custody |
| **VERDICT** | **NOT NEEDED** in the keyless design (no HTLC touches the reserve). Optional for the fast path |

**P2 — HTLC with a multisig claimant or refund key**

| Field | Content |
|---|---|
| PURPOSE | lets an M-of-N reserve own the HTLC legs |
| CURRENT_SOST_LIMITATION | spec D5 rejects it explicitly (R20 / S16 / R25) |
| WHY_HTLC_IS_NOT_ENOUGH | single-key fields only |
| WHY_V17_MULTISIG_IS_NOT_ENOUGH | it is excluded by design |
| CONSENSUS_CHANGE_REQUIRED | yes |
| SECURITY_PROPERTY | none that survives "M signers can still spend" |
| **VERDICT** | **REJECTED.** Multisig is not wanted, and it does not remove discretion |

**P3 — delayed-spend vault with a recovery path**

| Field | Content |
|---|---|
| PURPOSE | makes an unauthorized key spend slow, public and reversible by a recovery key |
| CURRENT_SOST_LIMITATION | no relative timelock, no vault opcode; V17 has no timelocked recovery (spec §1, out of scope) |
| WHY_HTLC_IS_NOT_ENOUGH | the HTLC has an absolute height and no clawback |
| WHY_V17_MULTISIG_IS_NOT_ENOUGH | no recovery path |
| CONSENSUS_CHANGE_REQUIRED | yes |
| SECURITY_PROPERTY | only mitigates a key holder |
| **VERDICT** | **NOT NEEDED.** With no key there is nothing to delay. Its useful part (a defined recovery) becomes the spend rules of P4 |

**P4 — restricted reserve output (covenant-like)**

| Field | Content |
|---|---|
| PURPOSE | a keyless output whose only spend paths are fixed by consensus |
| CURRENT_SOST_LIMITATION | every spendable SOST output is guarded by a pubkey hash; there is no keyless restricted output |
| WHY_HTLC_IS_NOT_ENOUGH | key-guarded |
| WHY_V17_MULTISIG_IS_NOT_ENOUGH | key-guarded (M keys) |
| CONSENSUS_CHANGE_REQUIRED | **yes** |
| SECURITY_PROPERTY | no arbitrary withdrawal by anyone |
| **VERDICT** | **REQUIRED → primitive N1** |

**P5 — SOST verifies Ethereum**

| Field | Content |
|---|---|
| PURPOSE | consensus accepts a proof that a vault event was finalized on Ethereum |
| CURRENT_SOST_LIMITATION | SOST has no notion of another chain |
| WHY_HTLC_IS_NOT_ENOUGH | a secret proves knowledge, not that wSOST returned (§0) |
| WHY_V17_MULTISIG_IS_NOT_ENOUGH | signers would be an oracle, which is discretion |
| CONSENSUS_CHANGE_REQUIRED | **yes** |
| SECURITY_PROPERTY | the reserve pays only against real exits and cancels |
| **VERDICT** | **REQUIRED → primitive N2** |

**MINIMUM_NEW_PRIMITIVES = 2**, both on SOST: N1 = P4 and N2 = P5. Ethereum also needs one new
contract component (§11), which is not a SOST consensus change.

## 2–3. The two primitives — specific, not a VM

### N1 · ARV outputs (two fixed-function output types, no pubkey, no script)

**`OUT_ARV_DEPOSIT`** — proposed type byte, not yet assigned.

Payload:
`eth_recipient(20) | eth_deadline(8, unix) | refund_pkh(20) | vault_id(20) | version(1)`

It can be spent **only** by the two transactions below. **Both also spend and recreate the reserve
singleton**, because the singleton holds the Ethereum light-client state that the proof is checked
against; SOST has no read-only reference inputs.

* `ARV_SWEEP`: carries a proof of `EntryReleased(depositId)` from the vault. The whole value goes
  into the reserve singleton.
* `ARV_REFUND`: carries a proof of `EntryCancelled(depositId)` from the vault. The value goes to
  `refund_pkh`, minus at most the published network fee.

`depositId = txid ‖ vout`. Because a UTXO can be spent once, **the deposit output is its own
nullifier**.

The Ethereum vault keys each entry by `entryKey = hash(depositId, amount, eth_recipient,
eth_deadline, vault_id)`. `cancel` is therefore bound to the real deposit fields, and an attacker
cannot cancel early with a fake deadline. `ARV_SWEEP` and `ARV_REFUND` check that the event's
`entryKey` matches the deposit payload exactly.

**`OUT_ARV_RESERVE`** — a singleton.

Payload:
`finalized_roots[R](32 each, ring of the last R finalized headers) | eth_finalized_slot(8) | sync_committee_root(32) | next_sync_committee_root(32) | next_exit_nonce(8) | vault_id(20) | params_hash(32)`

It is created once, by the activation rule, with a bootstrap checkpoint. After that it can only
be created by spending the previous `OUT_ARV_RESERVE` (lineage). This is the Atomiq UTXO-chaining
idea applied to SOST. Every spend must recreate exactly one reserve output as output 0. The
allowed spends are:

* `ARV_LC_UPDATE`: advances the Ethereum checkpoint and sync committee (N2 verifies it). The value
  is unchanged.
* `ARV_SWEEP`: absorbs proven deposits. Value goes up by their sum.
* `ARV_REFUND`: passes the reserve through unchanged while paying out a proven cancelled deposit.
* `ARV_RELEASE`: pays proven `ExitRequested(nonce, amount, sost_dest_pkh, max_fee)` events with
  nonces `next_exit_nonce … +m`, in order. Each payout goes exactly to `sost_dest_pkh`, for
  `amount − fee` with `fee ≤ max_fee`. Value goes down by the sum of amounts, and the nonce
  advances. **The sequential nonce is the nullifier.** There is no global set.

Common rules:

* **Binding checks.** The vault requires `deposit.vault_id == address(this)`. Every ARV spend
  requires `log.address == deposit.vault_id == reserve.vault_id`. N2 binds the Ethereum
  `genesis_validators_root` and fork domains, so a proof cannot be replayed from another chain or
  another contract. Without these checks a user could name a fake vault, get wSOST from the real
  one and refund through the fake one.
* **Exits that can always be paid.** The vault enforces a minimum exit above the SOST dust
  threshold, plus `max_fee < amount`. Otherwise one unpayable nonce would block every later one,
  because nonces are paid in order.
* **Fees.** The user sets `max_fee` and relayers will take it, so it is effectively the user's fee.
  Sweeps and refunds are paid from the relayer's own input; a small sweep fee comes out of the
  deposit, committed in the payload. The vault caps `eth_deadline` (for example at most 7 days).
* Extra non-ARV inputs and outputs are allowed only to pay fees and change of the relayer.
* There is **no other path**: no withdraw, no admin, no pause, no upgrade key.
* The rules live in C++ consensus code, like `OUT_HTLC_LOCK` today. Each output has fixed fields
  and a fixed spend path. **No virtual machine** is involved.

### N2 · `ETH_FINALITY_PROOF` — Ethereum light-client verification inside SOST consensus

* **Light-client updates.** Following the Ethereum light-client protocol (Altair sync committees,
  with the **Capella-or-later** header format, which carries `execution` and `execution_branch`;
  generalized indices are per fork, Deneb and Electra included), an update carries an attested
  header, a finalized header with its SSZ branch and a sync aggregate. The BLS12-381 aggregate
  signature must have at least 2/3 participation of the sync committee whose root is stored in the
  reserve. 2/3 is SOST's design threshold; the spec's own minimum is 1 participant. 2/3 of 512
  sampled keys is weaker than full Casper finality. Committee rotation happens every 256 epochs (about 27 h), using
  `next_sync_committee` with its branch.
* **Proof anchoring.** A proof may refer to any of the R finalized roots in the ring. Older blocks
  are reached by a `historical_summaries` / `block_roots` ancestry proof. This way a racing
  `ARV_LC_UPDATE` cannot make pending proofs invalid.
* **Event proofs.** A finalized beacon header links, through an SSZ branch, to the
  `execution_payload_header.receipts_root`. A Merkle-Patricia proof (RLP, keccak-256) then gives
  the receipt. The log must come from `vault_id` and carry the topic and fields of the event.
* **New consensus code needed:**
  * BLS12-381 pairing — for example the `blst` library, about 1–2 ms per verification;
  * SSZ hashing (sha256);
  * keccak-256;
  * RLP decoding;
  * Merkle-Patricia proof verification.
* **Size.** An event proof is a few KB. A committee rotation carries 512 × 48-byte keys, checked
  against the stored root.
* **Verdict.** This is bounded, deterministic and specific. It is **not** general computation.

## 4. Entry — 1,000 SOST → 1,000 existing wSOST (keyless)

| Question | Answer |
|---|---|
| Who creates the native output? | the user's wallet: `OUT_ARV_DEPOSIT` 1,000 SOST, recipient `0xUSER`, deadline `now + D` |
| Who can spend it? | **nobody by key.** Only `ARV_SWEEP` (proof of release) or `ARV_REFUND` (proof of cancel), submitted by anyone |
| Ethereum side | anyone relays the SOST deposit (§11) after k confirmations. The vault checks it, checks `block.timestamp < deadline` and the Gold Access Key, and moves 1,000 **existing** wSOST from inventory to `0xUSER`. The entry becomes RELEASED |
| Where does the UTXO end up? | anyone sweeps it into `OUT_ARV_RESERVE` with the proof of `EntryReleased` |
| Who can spend the reserve afterwards? | **nobody by key.** Only `ARV_RELEASE` against proven exits |
| Link to circulating wSOST | `reserve + released-but-unswept deposits == circulating wSOST + unpaid exits` (checked exactly, §14) |
| If the deposit is never released | after the deadline anyone calls `cancel(entryKey fields)` on Ethereum. No SOST proof is needed: the key binds every field, so a cancel for a deposit that does not exist matches nothing on SOST. Cancel is impossible if already released, and release is impossible after the deadline. Anyone then refunds with the proof. Refunds therefore do not depend on the Ethereum-side SOST relay being live |

The result is never "a daemon owns a private key": no key exists for these outputs.

## 5. Exit — 1,000 wSOST → 1,000 SOST

* **Ethereum.** The user calls `vault.exit(1000, sost1…, max_fee)`. The wSOST move to the
  immobilized inventory **immediately and irrevocably**. The vault emits
  `ExitRequested(nonce n, …)`. No XAUT is charged.
* **Native allocation.** Anyone relays the proof after Ethereum finality (2 epochs, about 13
  min). `ARV_RELEASE` pays 1,000 − fee to `sost1…` from the reserve, and `next_exit_nonce`
  becomes n+1.
* **Secret ordering and timelocks.** None are needed. There is no HTLC and no refund race: the
  user's side is already settled on Ethereum, and the SOST side is an obligation that consensus
  enforces.
* **Inventory return.** It happened at the first step.

The two forbidden outcomes:

* **"User keeps wSOST and recovers the original SOST."** Impossible. An entry is either RELEASED
  or CANCELLED, never both, and the deposit output can be consumed once (sweep **or** refund).
* **"Vault takes wSOST and the user never gets SOST."** Not permanent. Anyone, including the
  user, can relay the exit proof. The only failure mode is liveness: nobody relays and the user
  does not either.

## 6. Timelock safety

**Keyless design (D2).** The only deadline is the entry deadline `D`, enforced on Ethereum. There
is no cross-chain race, because Ethereum alone decides RELEASED or CANCELLED. `D` must allow a
normal entry to complete:

```
D  >=  k · 600 s · slow_factor   +   W_relay   +   M_outage
      (SOST confirmations, slow    (challenge     (relayer outage
       blocks)                      window of the  tolerance)
                                    SOST relay)
example  k = 30, slow_factor = 1.6 → 8 h;  W = 12 h;  M = 12 h   →   D = 32 h  (use 48 h)
```

If `D` is too short, the entry is refunded. That costs the user time, never money.

**HTLC variant (D1, only if an HTLC touches the reserve).** The race found in C704 closes
when this holds (closed-form worst case, arithmetic-checked in §14):

```
H_r  >=  h0 + (T_v + L) · f + m + k + 1          (all in SOST-block units of 600 s)
  T_v  vault HTLC deadline        L  max relay latency / outage
  f    max factor by which SOST blocks can be faster than target over the window
  m    blocks to include the claim     k  depth the claim must have before H_r (reorg safety)
example  T_v = 72, L = 36, f = 2, m = 6, k = 30   →   H_r − h0 >= 253 blocks
```

This is a closed-form worst case: the model's grid only checks the arithmetic, it is not a race
model. `m` and `f` are assumptions. Censorship of the claim by a dominant miner, a real risk at
about 90% of the hashrate, is not covered and pushes `m` up.

The **longer** deadline must sit on the SOST HTLC (the side whose secret is revealed second), by
at least `(T_v + L)(f − 1) + L + m + k + 1` blocks. Timeline:

```
t0 ──── deposit ──── k conf ──── vault locks ────────── T_v ──── +L ──── +m ──── +k ── H_r
        │                         │ user may claim ───────┘        claim seen, mined, buried
        └── user SOST HTLC (refund only after H_r) ────────────────────────────────────────┘
```

## 7. Reserve UTXO model

| State | Where it lives | Reached by |
|---|---|---|
| AVAILABLE | `OUT_ARV_RESERVE` value | `ARV_SWEEP` |
| RESERVED | (not needed: exits are paid when proven) | — |
| HTLC_PENDING | only in the D1 variant / fast path | — |
| CLAIMED (deposit swept) | deposit output spent by `ARV_SWEEP` | proof of `EntryReleased` |
| REFUNDED | deposit output spent by `ARV_REFUND` | proof of `EntryCancelled` |
| RECOVERY | the reserve **freezes**: no spend except `ARV_LC_UPDATE` | stale light client (§13 long-range risk) |

**Choice:** a combination of models.

* **Per-deposit outputs** handle the entries. They give single use for free, can be processed in
  parallel, and fragmentation is harmless because each one is swept once.
* **One chained reserve singleton** holds the aggregate. It gives serialized and ordered exits,
  and needs no global nullifier set.

Concurrency trade-offs:

* Two relayers spending the singleton in the same block conflict. One wins and the other
  rebuilds; this costs liveness only.
* Exits are batched (m per transaction), and chained spends are allowed within a block, so
  throughput is far above bridge demand.

## 8. V17 multisig — verified in code, not used

* `OUT_MULTISIG` is defined as 0x50, with M ≤ N ≤ 15 (`MAX_MULTISIG_N`). There is no script
  engine.
* The spec states: "a multisig cannot be the claimant or refund key of an HTLC", with rejections
  R20, S16 and R25 (`docs/v40000/NATIVE_MULTISIG_SPEC_40000.md` §7). It also says a timelocked
  recovery path is "out of scope (decided, not deferred)".
* Extending the HTLC to accept a multisig authority is possible (P2), but it keeps discretion with
  M signers.

**Conclusion: the keyless design does not use multisig anywhere in the reserve path.**
MULTISIG_EXTENSION_REQUIRED = NO.

## 9. Arbitrary-withdrawal test

**Setup.** The attacker controls every daemon, every relayer and every SOSTCore server. The
attacker has no valid redemption condition.

* **D0 (key reserve, including V17 3-of-5):** the attacker moves the reserve. **DESIGN FAIL.**
  The model checker finds `I4/I10 reserve SOST appropriated by a key holder`.
* **D2 (keyless):** no key exists. To move reserve SOST, the attacker must do one of these:
  1. actually return wSOST to the vault on Ethereum, which costs the SOST withdrawn;
  2. forge a finalized Ethereum event, which needs at least 2/3 of the 512-member sync
     committee to sign a false header;
  3. exploit a bug in N1 or N2.

  **Result: NO**, by design, under those assumptions.

**Indirect route — still open, and stated honestly.** The attacker obtains *unbacked* wSOST by
defeating the **entry** proof, then exits legitimately and drains the reserve at the expense of
the last holders. This can happen two ways:

* a SOST reorg deeper than k (`D2-deep` in the model breaks I1);
* an undetected fraud in the SOST relay on Ethereum.

While SOST hashrate is concentrated, a deep reorg is cheap for the dominant miner. The bridged
value must therefore stay below the cost of a k-block reorg. Mitigations:

* immutable caps and rate limits on the vault;
* larger k for larger deposits;
* the inventory size itself as a hard bound.

## 10. Third-party execution

Every action in D2 is **permissionless**:

* the light-client update;
* the SOST header relay;
* release, cancel, sweep, refund and exit payout.

Amount and destination are fixed by the deposit payload or by the Ethereum event. A relayer only
chooses a fee, capped by `max_fee`, which the user set. **Execution permission is open; ownership
permission does not exist.**

The user can always relay their own operation. The model checks that, from every reachable state,
permissionless relays alone make every user whole (I9).

## 11. Cross-chain proof options

| Option | Trust | Complexity | Cost | Consensus change | Security | Reorgs |
|---|---|---|---|---|---|---|
| A · HTLC secret only | a deciding counterparty | low | low | none | **cannot protect a keyless reserve (§0)** | timelocks |
| B · event proof alone | whoever supplies headers | medium | low | yes | needs C | — |
| C · Ethereum light client (sync committee; an optimistic bonded relay of Ethereum headers is a cheaper variant with a 1-of-N honest-watcher assumption) | >2/3 honest of 512 (no slashing for committee signatures) + bootstrap checkpoint | high, bounded | ms per proof on SOST nodes | **yes (N2)** | strongest practical on SOST | finalized headers only |
| D · external verifier | its keys | low | low | none | **key = discretion** | operator policy |
| E · hybrid (C for the reserve; Ethereum-side SOST relay for entries; HTLC fast path for market makers with their own funds) | C + SOST PoW majority + 1 honest watcher | high | — | N1 + N2 | **recommended** | k-depth + finality |

The light client was not assumed: §0 shows that the only alternative to C for a keyless reserve
is D, which is a key.

A succinct-proof (zk) verifier of Ethereum consensus is a variant of C. It would also need a new
verifier primitive in SOST.

**The Ethereum side needs a SOST light client contract.** It is *not* a SOST consensus change.

* **Design:** an optimistic header relay. Anyone posts SOST headers with a bond. Headers become
  final after a challenge window W unless a challenger proves one invalid. Fork choice is most
  cumulative work, and deposits must be k deep.
* **Fraud proof:** verifies one ConvergenceX transcript (`verify_cx_proof`, about 10–20 ms
  natively, no 4 GB dataset) and the cASERT difficulty on-chain, or through an interactive
  bisection if one verification exceeds the block gas limit.
* **Gas:** unmeasured. This is the largest engineering unknown.
* **Later:** a zk proof of SOST header validity.

## 12. Atomiq

| Topic | Atomiq | SOST |
|---|---|---|
| What it solves | the smart chain verifies Bitcoin on-chain (headers, double-SHA256 PoW, difficulty, most-work fork choice; anyone submits headers). Its UTXO-controlled vault releases liquidity only against verified Bitcoin transactions, serialized by UTXO chaining. **This is our entry direction** | not yet solved: our PoW (ConvergenceX + cASERT) is far costlier to verify in the EVM |
| What it does not solve, and does not need to | Bitcoin cannot verify the smart chain and has no covenants. Atomiq never holds a keyless BTC reserve: LPs keep their own Bitcoin keys and liquidity | **our exit direction** is a problem Atomiq does not face |
| Why SOST can go further | — | SOST can add N1 and N2 to its own consensus; Bitcoin cannot |
| What we adapt (justified) | — | (1) UTXO chaining for the reserve singleton: ordered exits, no nullifier set; (2) permissionless header and proof submission with watchtower incentives; (3) withdrawals bound to verified transactions instead of signers |
| What we do not copy | — | the LP liquidity model: our inventory is preissued wSOST, 1:1, not LP capital |

A closer precedent for SOST verifying Ethereum: bridges in which a chain's runtime verifies the
Ethereum sync committee, such as Snowbridge for Polkadot. Public analyses discuss the
sync-committee assumption.

## 13. Consensus change

Both primitives are a **hard fork**: old nodes reject unknown output and transaction types.

The minimal change:

* `OUT_ARV_DEPOSIT` and `OUT_ARV_RESERVE`;
* the tx types `ARV_SWEEP`, `ARV_REFUND`, `ARV_RELEASE` and `ARV_LC_UPDATE`;
* the verification code of N2;
* one activation rule that creates the reserve singleton with a published bootstrap checkpoint.

| Question | Answer |
|---|---|
| CAN_FIT_V17 | NO, realistically: a new cryptographic stack (BLS12-381, keccak, RLP, MPT) plus new output types, inside a frozen scope that already carries multisig, DTD-F1, the new economics, block-size and P2P work |
| SHOULD_FIT_V17 | NO |
| RISK_OF_ADDING_TO_V17 | HIGH: large new consensus surface, a dependency on Ethereum's fork schedule, an unmeasured Ethereum-side relay |
| BETTER_AS_V18 | YES, after a devnet PoC and an external review |

**Permanent coupling.** **Every** Ethereum hard fork needs a SOST release before it activates,
because the sync-committee signing domain depends on `fork_version`, and containers or generalized
indices may change as well. Otherwise the reserve freezes until SOST upgrades.

**Long-range risk.** Retired sync committees cannot be slashed. Catching up a stale light client
means trusting old committee keys. Keep the reserve's light client live, and treat a long freeze
as a case for a published checkpoint in a SOST release.

## 14. Security model — what is shown and how

**Bounded model check:** `research/arv/arv_model.py`.

* It explores every interleaving of these actions: deposit and exit by honest users **and by an
  attacker who holds funds**, confirmation, reorg of unconfirmed deposits, permissionless release
  / cancel / sweep / refund / in-order exit payout, the clock, and (D0) a key spend.
* I4/I10 is checked as "no party, the attacker included, ever holds more value than it brought".
* Default bounds: 2 users + attacker, 2 SOST each, premint 6, up to 2 deposits and 2 exits, 3 clock
  values. A larger run of D2 only: 1 user + attacker, 3 SOST each, premint 6, 3 deposits, 3 exits, 3 clock
  values (all designs at these bounds exceed the time budget).

Results:

```
D0  (reserve key / V17 M-of-N)   FAIL  — I4/I10 a party gained value, I1 broken
D2  (keyless N1 + N2)            PASS  — no safety violation, no liveness failure (58,467 states)
D2-deep (reorg deeper than k)    FAIL  — I1 broken, I3/I5 user keeps wSOST and the SOST
mutations of D2, each with ONE rule removed — every one is caught (the checker is not vacuous):
  release without k confirmations · cancel after release · replayed exit nonce · refund without
  a cancel proof · relayer chooses the payee            FAIL ×5
D1 HTLC timing (arithmetic check of the worst case)      PASS
D2 larger bounds (1 user + attacker, 3 SOST each, premint 6, 3 deposits, 3 exits)
                                 PASS  — no safety violation, no liveness failure (2,212,323 states)
```

**Not modelled:**

* fees and dust;
* forged light-client or relay proofs — N2 and the Ethereum-side relay are assumed sound;
* checkpoint staleness and front-running;
* censorship;
* inventory exhaustion beyond the premint.

`complete()` follows one greedy relay schedule. It shows that a completion exists, not that every
schedule completes.

| Invariant | Status |
|---|---|
| I1 circulating wSOST ≤ native reserve | **by design + model (exact equation)**, *assuming* no SOST reorg deeper than k and a sound relay |
| I2 one native unit cannot back two wSOST | **by design + model** (single-use outputs, conservation) |
| I3 no double claim | **by design + model** (deposit output consumed once; sequential exit nonce) |
| I4 no arbitrary reserve withdrawal | **by design + model** (an attacker with funds and the power to relay gains nothing; the free-payee mutation is caught); holds as long as N1 and N2 are correct and the sync committee is not >2/3 corrupt |
| I5 safe refund | **by design + model** (RELEASED xor CANCELLED, by timestamp) |
| I6 safe recovery | **partially.** In-protocol: timeouts, cancel and refund, permissionless relays, freeze on a stale light client. Extraordinary recovery (an Ethereum format change, a vault bug) **requires a SOST network upgrade**. No key can do it, and no key exists |
| I7 safe concurrent swaps | **model** (all interleavings within the bounds) |
| I8 reorg tolerance | **assumption** (k-depth on SOST, finality on Ethereum); the model shows the exact failure past k |
| I9 service disappearance steals nothing | **model** (completion by permissionless relays makes every user whole) |
| I10 no single operator can appropriate the reserve | **by design + model** |

A bounded model check is evidence, **not a proof** for all sizes. A formal proof (TLA+ or Coq)
and an external review remain to do.

## 15. Delivery

```
P1: destination-committed HTLC        — NOT NEEDED (optional fast path)
P2: HTLC with multisig claimant       — REJECTED (multisig not wanted; keeps discretion)
P3: delayed-spend vault + recovery key — NOT NEEDED (no key to delay)
P4: restricted keyless reserve output — REQUIRED  → N1 (OUT_ARV_DEPOSIT + OUT_ARV_RESERVE)
P5: SOST verifies Ethereum            — REQUIRED  → N2 (ETH_FINALITY_PROOF, sync-committee LC)
MINIMUM_NEW_PRIMITIVES:     2 on SOST (N1, N2) + 1 Ethereum contract component (SOST relay)
HTLC_EXTENSION_REQUIRED:    NO
MULTISIG_EXTENSION_REQUIRED: NO
NEW_OUTPUT_TYPE_REQUIRED:   YES (2 types)
COVENANT_LIKE_RULE_REQUIRED: YES (fixed spend paths, singleton lineage)
ETHEREUM_PROOF_REQUIRED:    YES
NATIVE_RESERVE_MODEL:  per-deposit keyless outputs + one chained keyless reserve singleton
ENTRY_MODEL:           ARV_DEPOSIT → relay to Ethereum → vault releases inventory (deadline) →
                       sweep with proof; or cancel → refund with proof
EXIT_MODEL:            vault.exit (wSOST to inventory, sequential nonce) → proof → ARV_RELEASE
TIMELOCK_MODEL:        one Ethereum deadline D (no cross-chain race); D1 bound if an HTLC is used
RECOVERY_MODEL:        no key; timeouts + refunds + open relays; freeze on stale LC; upgrade = SOST release
ARBITRARY_WITHDRAWAL_PREVENTED: YES for any key holder (by design, model-checked); indirect route via
                       a deep SOST reorg or relay fraud remains — bounded by caps
THIRD_PARTY_EXECUTION_POSSIBLE: YES (all actions permissionless; destinations fixed)
CROSS_CHAIN_TRUST_REMAINING: SOST PoW majority (entry) · Ethereum sync committee >2/3 honest (exit,
                       refund) · code correctness · ≥1 honest relayer/watcher · bootstrap checkpoints
CAN_IMPLEMENT_WITH_CURRENT_V17: NO
CONSENSUS_CHANGE_REQUIRED: YES (hard fork)
SHOULD_CHANGE_V17:     NO
OR_DEFER_TO_V18:       YES
SECURITY_INVARIANTS_PROVEN_BY_DESIGN: I1 I2 I3 I4 I5 I7 I9 I10 by design + bounded model (I1/I4
                       conditional on stated assumptions); I6 partial; I8 assumption; no formal proof yet
POC_CAN_START:         YES for a devnet PoC of N1 + N2 + vault with a stub SOST relay (models the
                       design that passes); NO for the earlier key-based PoC (known to fail test J)
MAINNET_CHANGED: NO
CONSENSUS_CHANGED: NO
```

### Remaining non-reserve trust (outside this study's scope)

* The Gold Access Key needs an XAUT/EUR price and an approved SOST/EUR valuation. That is an
  oracle. Keyless options are an immutable XAUT-per-SOST schedule or an on-chain TWAP; this is
  open.
* Gold Reserve V2 guardians are humans. They are not in the bridge path.
* The Ethereum vault must be immutable: no admin, no pause, immutable caps. A bug can only be
  addressed by a new deployment plus a SOST upgrade that names it.
