# Gold Vault Signal — Design (PLANNED / NOT ACTIVE)

**Status: PLANNED / NOT ACTIVE.** Design document only. No voting is live, no funds
move, no consensus rule is added, nothing is deployed. This describes a **visual,
wallet-signed signalling system in the explorer** by which SOST holders can approve
**strictly-limited** Gold Vault reserve operations.

> One line: *Gold Vault Signal lets SOST holders signal approval for strictly limited
> reserve operations using signed wallet votes.*

> **Binding status (2026 update):** this signal is a **NON-BINDING temperature check
> only**. It must not be presented as binding governance. **Binding weighted voting is
> not implemented** and requires **snapshot-balance support** (`getbalanceatheight` /
> indexer) that does not exist yet — without it, vote weight by SOST held cannot be
> computed. In the governance model the founder/guardian has a **time-boxed, reasoned
> safety VETO, not spending power** (a guardian set of 2-of-3 / 3-of-5 is recommended
> over a single key), and approval is **holder-weighted, not miner-block voting**.
> Canonical rules: [`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md).

Related: [`TOKENIZED_GOLD_RESERVE_SAFE_DESIGN.md`](TOKENIZED_GOLD_RESERVE_SAFE_DESIGN.md),
[`GOLD_ACCUMULATION_AUCTION_PROGRAM.md`](GOLD_ACCUMULATION_AUCTION_PROGRAM.md) (Gold
Reserve Forge), [`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md).

---

## 1. What it is (and is not)

A section of the **explorer** where holders vote with their SOST wallet on a small,
fixed menu of reserve operations. Voting is by **wallet signature**, weighted by SOST
held at a **snapshot** block.

- **Not mining-based.** Mining a block — even 90% of blocks — grants **zero** extra
  voting power. Hashrate does not vote. A dominant miner cannot capture the vault.
- **Not a free-for-all DAO.** The Signal can only approve operations inside strict,
  pre-defined safety rails (§4). It never grants open spending power.
- **Not live and not consensus** (at first). Phase 1–3 are **off-chain signed**
  signalling read/verified by the explorer; consensus enforcement is a later phase.

```
1 SOST at snapshot = 1 vote     ·     1 wallet = 1 signed vote
vote by wallet signature        ·     NOT by mining / hashrate / coinbase
```

---

## 2. How a holder votes

The user sees only buttons in the explorer:

```
Gold Vault Signal — Proposal GV-001
Convert up to 100 SOST into PAXG → verified Tokenized Gold Safe
Your voting power: 1,250 SOST
[ Vote YES ]   [ Vote NO ]
```

Under the hood the wallet signs a short message (the user never types commands):

```
GVOTE:GV-001:YES        (or :NO)
```

CLI equivalent (for power users / verification):
```
sost-cli signmessage "sost1..." "GVOTE:GV-001:YES"   → signature
sost-cli verifymessage "sost1..." "<sig>" "GVOTE:GV-001:YES"   → true/false
```

**One wallet = one vote.** If an address signs again, the **last valid vote before
close replaces** the previous one. A signature proves *this address voted*; its weight
is looked up from the snapshot.

---

## 3. Vote weight & snapshot

Weight = the SOST balance the address held at a fixed **snapshot** block:

```
snapshot_height = voting_start_height − 1
```

Taking the snapshot at the block **before** voting opens means nobody can see the
proposal and then buy/shuffle SOST in the same block to manipulate the weight. Buying
more SOST *after* the snapshot does not change the vote for that proposal.

```
wallet A held 10,000 SOST at snapshot → weight 10,000
wallet B held    100 SOST at snapshot → weight    100
```

**Votable supply** (the quorum denominator) excludes SOST that must not count:
the Gold Vault's own balance, genesis/burn addresses, and (where identifiable) the
PoPC pool — so quorum is measured against real, movable holder supply.

---

## 4. What can be voted on (strictly limited)

The Signal exposes **only** these proposal types — never arbitrary calls:

1. **Convert** up to the cap of Gold-Vault SOST into PAXG/XAUT (a Forge window).
2. **Move** PAXG/XAUT from the Safe to **another verified Safe**.
3. **Emergency migration** to a verified **emergency** Safe.

Every proposal is bounded by the reserve safety rails (already in the Safe & Forge
designs):

```
only PAXG / XAUT            no AMM
only verified allowlisted   no CEX destination
  Safe destinations         no personal wallet
weekly outflow cap          no unknown contract
timelock                    emergency stop (guardian)
Protocol Registry entry
```

So the vote never decides "do anything" — only "yes/no" **inside safe rails**.

---

## 5. Thresholds (simple)

### Normal proposal (small movements)
```
voting window : 24 h
quorum        : ≥ 10% of votable SOST participates
approval      : ≥ 60% YES (weighted)
weekly cap    : ≤ 1% of the Safe's tokenized gold
timelock      : 24 h
destination   : allowlisted only
```

### Emergency proposal (issuer/custody risk, urgent migration)
```
voting window : 6 h
quorum        : ≥ 20% of votable SOST
approval      : ≥ 90% YES (weighted)
amount        : may move up to 100% — but ONLY to a verified emergency Safe
timelock      : 6 h
reason        : mandatory
```

Worked example (normal):
```
votable SOST = 100,000  →  quorum 10% = 10,000
votes: A 10,000 YES · B 2,000 YES · C 1,000 NO
participation = 13,000 (≥ 10,000 ✓)   YES = 12,000/13,000 = 92.3% (≥ 60% ✓)
→ passes → 24 h timelock → execute to allowlisted Safe → Registry entry
```

---

## 6. Proposal lifecycle (states)

```
Draft → Voting Open → Voting Passed → Timelock → Executed
                    ↘ Voting Failed
                    ↘ Cancelled
   (Emergency track runs the same states on the 6 h / 90% path)
```

Full flow: publish proposal (with snapshot & window) → holders sign YES/NO →
explorer verifies signatures + snapshot weights → if quorum + approval + cap +
allowlisted destination all pass → timelock opens → (no emergency-stop veto) →
Safe executes → Protocol Registry entry published.

---

## 7. The off-chain-first architecture (and the cross-chain reality)

The vote happens on the **SOST chain** (signatures over SOST balances); the gold sits
in an **Ethereum Safe**. Bridging "the vote said yes" to "the Safe moves" is the hard
part, so we phase it:

- **Phase 1–3 (off-chain signalling):** the explorer collects the signed votes,
  verifies each signature + snapshot weight, computes the result, and **publishes** it.
  The Safe's 3/5 signers execute an operation **only if** its Signal passed — with the
  Safe's own timelock + destination allowlist + guardian veto as the enforced
  backstops. This is a *trusted-signers-honour-the-result* model, made safe by those
  backstops (a signer cannot send to a non-allowlisted address regardless of any vote).
- **Later (trust-minimised):** relay the result to a Zodiac module on the Safe via an
  optimistic oracle (Reality.eth / SafeSnap), so the Safe acts on the vote without a
  trusted relayer. (The Safe design already anticipates Reality.eth.)

Signalling is honest about what it is at each phase: early on it is **advisory +
publicly verifiable**, not yet self-executing consensus.

---

## 8. Security considerations & open questions

- **Snapshot, not live balance** — prevents "buy → vote → sell" and same-block
  manipulation. (Load-bearing; do not use live balances.)
- **Whale capture (open question).** Pure `1 SOST = 1 vote` lets a pre-existing large
  holder — or an exchange voting with customer coins — dominate. Recommended hardening
  to decide before any real vote: a **per-wallet voting-weight cap** (e.g. ≤ 5% of
  votable power) and/or excluding known exchange hot wallets. The base design is
  simple; the cap is the single most effective anti-capture lever.
- **Emergency quorum vs. reserve freeze.** A high emergency bar (20% quorum / 90% YES)
  resists capture but could be *unreachable* during real apathy, freezing the reserve
  when it is most needed. Mitigation: pair it with a **guardian fast-path** (the
  guardian can act, not only veto, on a genuine, documented emergency) as a backstop.
- **Sybil.** Weight is by SOST, not by address count, so splitting across many wallets
  gains nothing (weight is conserved) — unless a per-wallet cap is added, in which case
  a whale could split to dodge the cap; if the cap is adopted, pair it with a small
  minimum-stake-per-vote or identity-light measure.
- **Destination allowlist is the ultimate backstop** — even a captured vote cannot send
  gold anywhere but a pre-approved Safe/redemption/emergency address.

---

## 9. Phased build

```
Phase 1 — Visual dashboard (no voting): show mock/planned proposals, rules,
          voting power display, "how it will work". Nothing is signed.   ← this PR
Phase 2 — Real signing: connect wallet, sign GVOTE message, store + verify
          signatures, compute snapshot-weighted result.
Phase 3 — Registry: publish results, export JSON, link Forge Proofs.
Phase 4 — Automation: timelock, Safe execution checklist / oracle binding.
```

Home: the **explorer** (production). This document's companion Phase-1 preview renders
on the public Gold & Metals Reserve page as a static, non-interactive mock.

---

## 10. Ownership & framing (unchanged)

The tokenized gold belongs to the **protocol's Tokenized Gold Reserve**, custodied in a
Safe multisig. It gives **no individual redemption right** to holders, miners or
buyers. Buying SOST in a Forge window buys **SOST**, not a share of the gold. The Gold
Vault Signal only decides — within safe rails — how the *protocol's* reserve moves.

**Not** a peg · **not** gold-backed SOST · **not** a dividend/yield/equity · **not** a
claim on gold · **no** new SOST minted · **NOT ACTIVE**.
