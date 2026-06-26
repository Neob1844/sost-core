# X / Twitter thread — PoPC redesign

---

**1/**
We've redesigned PoPC (Proof of Personal Custody).

Two models → one.

Now there's a single bond, posted in $SOST — the only collateral, the only thing slashable. Gold becomes a reward boost, never collateral. 🧵

---

**2/**
The principle:

Security that can be slashed must live where the protocol can slash it.

When the bond was gold on Ethereum, punishing a cheater needed an off-chain watcher / oracle / key — a trusted middleman. That's exactly what PoPC is meant to remove.

---

**3/**
Anchoring the bond in SOST gives us:

✅ No external chain as the root of security
✅ Max decentralization — nobody holds a key over your bond
✅ Max automation — lock → audit → reward → slash, all under SOST consensus

---

**4/**
Base reward (native SOST bond), by lock duration:

1mo → 1%
3mo → 4%
6mo → 9%
9mo → 14%
12mo → 20%

---

**5/**
Gold Boost — on top of the base reward, if you also hold verified gold:

0–30d → +0%
31–90d → +10%
91+d → +20%

Cap +20% (technical max +25%). Recommended lock: 90 days.

---

**6/**
Gold stays in YOUR wallet. Never seized.

Withdraw it, or if verification is briefly unavailable → you simply drop back to the base reward. No penalty, no slash.

Example: 12-mo bond = 20% base. + gold 91+ days = 20% × 1.20 = 24%.

Eligibility: gold worth ≥ max(25% of the bond value, 0.25 PAXG/XAUT). Dust doesn't count.

---

**7/**
The Gold Boost is paid from the PoPC Pool (capped, surplus-only) so it can never dilute the base reward. The Metals Reserve stays untouched. Coinbase split unchanged:

50% miner · 25% Metals Reserve · 25% PoPC Pool (base + optional boost)

---

**8/**
This is a design/docs update — no consensus change on its own, ships off by default.

Full detail in the whitepaper §6 👇
🌐 sostcore.com

$SOST — Sovereign Stock Token. MIT. No admin keys. No bridges in the root of security.
