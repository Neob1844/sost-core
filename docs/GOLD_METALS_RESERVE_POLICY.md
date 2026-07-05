# Protocol Strategic Reserve — Governance Policy

**Status:** read-only policy document (**planned / NOT ACTIVE**). It describes what
the reserve **is today** and how governed use is **designed to work in the future**.
It activates nothing, moves no funds, sells nothing, and changes no consensus rule.

**One-line summary:** The protocol accumulates SOST on-chain today. **No reserve
spending is active.** No SOST from the reserve is being sold or moved. No tokenized
gold has been acquired. SOST is **not** gold-backed and gives **no** claim to gold.

---

## 0. Naming — one reserve, two compartments

What has been called the "Gold Vault" is, more precisely, one **Protocol Strategic
Reserve** with two clearly separated compartments. Being explicit up front avoids
the fair criticism *"you said gold vault, then spent it on listings."*

```
Protocol Strategic Reserve  (the SOST the protocol accumulates on-chain)
├─ Gold Accumulation Reserve            — minimum 50%
└─ Growth / Listing / Compliance Reserve — maximum 50%
```

- **Gold Accumulation Reserve — minimum 50%.** Earmarked for a **future** metal
  reserve (**PAXG / XAUT** only). Its future measure is **grams of
  protocol-held gold** — a treasury metric, **not a peg and not a redemption claim.**
  There is **no** individual claim on gold, **no** "1 SOST = 1 gram", and SOST is
  **not** gold-backed.
- **Growth / Listing / Compliance Reserve — maximum 50%.** Earmarked for a **future**
  set of ecosystem costs: compliance, MiCA/legal, audits, infrastructure,
  aggregators, serious listings, initial liquidity and security. Rationale: **the
  founder should not have to personally fund every listing, legal, infrastructure or
  compliance cost** for the protocol to survive and grow.

The split is a **floor/ceiling policy**, not a physical partition: gold ≥ 50%, growth
≤ 50%. Nothing is partitioned or moved today.

---

## 1. Current state (what is and is not active)

| Component | State | Enforced by |
|---|---|---|
| **On-chain SOST accumulation** | **ACTIVE** since genesis | Consensus (coinbase rules CB5/CB6) |
| **Any reserve spending (either compartment)** | **NOT ACTIVE / LOCKED** | Deferred — activation height `INT64_MAX` on mainnet |
| **Gold Accumulation — tokenized gold acquired** | **NONE** | Off-chain; nothing bought, no Safe created |
| **PAXG / XAUT held** | **0 / pending** | — |
| **Growth / Listing / Compliance spending** | **NOT ACTIVE** | No SOST sold or paid out from the reserve |
| **Weighted holder voting** | **NOT ACTIVE** | Requires snapshot-balance support (see §4) |
| **Public Protocol Registry of operations** | **PREPARED (empty)** | No operations executed yet |

- The reserve address is fixed at consensus level:
  `sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d`.
- Every valid block pays exactly 25% of the block subsidy (`q = reward // 4`) into
  that reserve. A block that does not is rejected. This accumulation is the **only**
  live part of the reserve system.
- The **spend** side is scaffolding + audit only. The classifier and Slice-1
  validator helpers exist and are unit-tested, but on mainnet they are wired behind
  `GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX`, so consensus behaviour is identical to
  having no spend rule at all. **Nothing can be spent from the reserve today — the
  spend path is disabled at the consensus level, not merely by policy.**

---

## 2. Economic reality — potential capital, not liquid capital

The reserve is denominated in **SOST**. Until SOST has an external market price and
liquidity, the reserve is **potential capital, not immediately spendable capital**:
converting reserve SOST into either gold (PAXG/XAUT) or fiat (to pay a provider)
requires selling SOST, which is only possible — and only responsible — once a market
exists that can absorb it.

Therefore the natural sequence is:

```
1. Growth / liquidity work unlocks a real SOST market.
2. The reserve then becomes usable capital.
3. Gold accumulation becomes meaningful once conversion can happen
   without damaging the market.
```

Growth/liquidity is the **first** unlock; gold accumulation is chronologically the
**second** step, not the first. Buying gold before liquidity exists would mean
selling SOST into a market that cannot support it.

---

## 3. Governance model (design, not active)

When — and only when — a market, legal structure and snapshot support all exist, any
reserve operation (gold **or** growth) would require **all** of the following. This
is **holder** governance, **not** miner-block voting.

**Normal operation:**

| Rule | Value |
|---|---|
| Vote weight | **Weighted by SOST held** at a snapshot height (see §4) |
| Quorum | **≥ 15%** of votable SOST |
| Approval | **≥ 51% YES** (weighted) |
| Weekly cap | **≤ 1%** of the relevant reserve compartment |
| Destination | **Allowlisted** only (verified Safe / verified provider) |
| Timelock | **72h** before execution |
| Public registry | **Mandatory** — every operation published |
| Founder / guardian | **Time-boxed, reasoned safety VETO during the timelock** |

**Emergency operation** (e.g. moving gold between Safes): quorum ≥ 25%, **≥ 90% YES**
weighted, allowlisted emergency destination, guardian veto active, public registry.

**The founder / guardian role — veto, not spending power:**

- The founder/guardian can **block** a dangerous execution (unverified destination,
  legal risk, oracle mismatch, hack/phishing, price error). Each veto is **public,
  reasoned and time-boxed**.
- The founder/guardian **cannot approve a spend, cannot spend unilaterally, and
  cannot move the reserve alone.** It is a **negative** power only.
- Recommended control is a **guardian set (2-of-3 or 3-of-5)**, not a single founder
  key — the founder may be **one** guardian, never the only control. This avoids both
  a single point of failure (a lost key must not freeze the reserve forever) and the
  optics of unilateral control.

**The mother rule:**

```
Nothing leaves the reserve on a single key.
Not the founder. Not a whale. Not a simple majority alone.
It leaves only with: weighted holder approval + allowlisted destination
+ weekly cap + timelock + public registry + no guardian veto.
```

---

## 4. Voting status — non-binding signal today

- **Binding weighted voting is NOT implemented.** Real weighted voting requires
  **snapshot-balance support** — a way to read how much SOST each wallet held at the
  snapshot height (a `getbalanceatheight` / indexer capability that does **not** exist
  yet). Without it, votes cannot be weighted correctly, so no binding vote is possible.
- The existing wallet **`GVOTE:` signal is a NON-BINDING temperature check only.** A
  holder can sign `GVOTE:GV-001:YES/NO` with their SOST key to express an opinion; it
  produces a signed JSON receipt and **executes nothing**. It must **not** be
  presented as binding governance.
- Building a governance system that cannot execute anything would be theatre; the
  binding layer waits until snapshot support and a real market exist.

---

## 5. Consensus enforcement layer (G1–G5, all deferred)

Underneath the holder-governance design sits the consensus-level scaffolding. On
mainnet these are all deferred (disabled). They are the *enforcement* mechanism a
future activation would use; the *decision* mechanism is holder voting (§3).

- **G1 — Purpose whitelist.** A spend may only go to a pre-committed destination.
- **G2 — Dual whitelist cross-check.** The destination list is committed in two
  independent places that must agree byte-for-byte; any mismatch fails closed.
- **G3a — Per-spend cap.** No single spend may exceed a fixed fraction of the balance.
- **G3b — Accumulated cap / rate-limit.** A minimum number of blocks must pass between
  spends. **This is the current technical blocker** (needs a
  `gold_vault_last_spend_height` schema field, landing in a separate tested commit).
- **G4 — Approval signaling.** Approval is being redesigned toward **holder-weighted
  voting** (§3), superseding the earlier miner-block-signaling sketch. **No
  miner-block voting.**
- **G5 — Transitional Guardian veto.** A strictly temporary, signed veto that can only
  **block**, never force. Silence = accept. Auto-disconnects forever at a hardcoded
  height and can never be re-enabled.

Until G3b is wired and cross-validated, and snapshot support exists, **no responsible
activation is possible.** The helpers are unit-tested; they are simply not called by
consensus yet.

---

## 6. Custody design (for the Gold Accumulation Reserve, when active)

- **Tokenized Gold Reserve** — will live on **Ethereum mainnet** as a **Safe multisig
  (3/5)** with a **timelock**, a **destination whitelist**, and a **public dashboard**.
  No single key should be able to move reserve assets: multi-authorised **and**
  time-delayed **and** destination-constrained.
- **Asset policy:** **PAXG primary** (Paxos; NY-regulated, redeemable, monthly
  attestations), **XAUT secondary/optional** (liquidity diversification). **PAXG and
  XAUT only** — no other gold instrument and no physical gold custody in this phase.
- **Why Ethereum mainnet?** PAXG/XAUT are ERC-20 tokens native to Ethereum with their
  deepest liquidity and redemption there, and Safe custody/audit tooling is most
  battle-tested there. A sealed, rarely-moving reserve makes mainnet gas immaterial.
- **Why not a direct SOST/PAXG or SOST/XAUT AMM pair?** SOST is its own L1, not an
  ERC-20. A native AMM pair would require wrapping SOST via a bridge, and bridges are
  the single largest source of losses in crypto. So SOST/PAXG and SOST/XAUT are
  **conversion rails (OTC / Atomic Swap)**, not a vault and not a live AMM.

---

## 7. Public Protocol Registry (prepared, empty)

Every future reserve operation will be published with: SOST txid, EVM txid, token
received (PAXG/XAUT), amount, price/reference used, Safe address, resulting balance,
grams-equivalent (for gold), compartment (gold / growth), and notes/status.

**No reserve operations have been executed yet.**

---

## 8. What will not happen before activation

No SOST will be sold or moved from either compartment until **all** of the following
are true: a real SOST market/liquidity exists, snapshot-balance support is available,
weighted holder voting is live, per-spend + accumulated caps set, a destination
allowlist committed, a 72h timelock in place, the guardian veto framework in place,
the Ethereum Safe created (for gold), legal/compliance cleared (incl. MiCA
considerations), and an operational runbook published. Until then: **accumulation
only.**

**What SOST is not:** not gold, not gold-backed, not "1 SOST = 1 gram", no redemption
right, no guaranteed return. "Grams of protocol-held gold" is a future treasury
metric, **not a peg or a claim.**
