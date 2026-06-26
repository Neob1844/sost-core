🛡️ **PoPC Redesigned — One Native Bond, Gold as a Boost**

We've simplified Proof of Personal Custody (PoPC). What used to be two models is now **one SOST-native protocol**.

**The change in one line:**
👉 One bond, posted in SOST — the only collateral, the only thing that can be slashed. Gold becomes a *reward boost*, never collateral.

**Why?**
Security that can be slashed must live where the protocol can slash it. When the bond was gold on Ethereum, punishing a cheater needed an off-chain watcher / oracle / key — a trusted middleman. That's exactly what PoPC is supposed to avoid.

Putting the bond in SOST gives us:
✅ No external chain as the root of security
✅ Maximum decentralization — nobody holds a key over your bond
✅ Maximum automation — lock → audit → reward → slash, all under SOST consensus

**How rewards work now**

Base reward (native SOST bond), by lock time:
`1mo → 1% · 3mo → 4% · 6mo → 9% · 9mo → 14% · 12mo → 20%`

Gold Boost (on top of base, if you also hold verified gold):
`0–30d → +0% · 31–90d → +10% · 91+d → +20%`
(cap +20%, technical max +25%)

🔹 Gold stays in *your* wallet, never seized. Withdraw it → you just drop back to the base reward. No penalty.

**Example:** 12-month bond = 20% base. With gold 91+ days → 20% × 1.20 = **24%**.

**Coinbase split** stays the same headline numbers — the old 25% Gold Vault slice is repurposed as a dedicated **Gold Boost Reserve**, so boosts never dilute the base pool:
`50% miner · 25% PoPC Base Pool · 25% Gold Boost Reserve`

ℹ️ This is a design/docs update — no consensus change on its own, ships **off by default**.

📄 Full detail → whitepaper §6 at sostcore.com
🌐 sostcore.com · ✉️ sost@sostcore.com

*SOST — Sovereign Stock Token. MIT-licensed. No admin keys. No bridges in the root of security.*
