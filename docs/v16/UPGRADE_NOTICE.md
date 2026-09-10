# DRAFT — Mandatory Network Upgrade Notice (do NOT publish until release = READY)

Publish on: sostcore.com, X, Telegram (t.me/SOSTProtocolOfficial), BitcoinTalk.
Contact: sost@sostcore.com · logo: http://sostcore.com/sost-logo.png
(Do not include any personal email or handle in the public post.)

---

## 📣 SOST — MANDATORY NETWORK UPGRADE (V16 · DTD Jackpot V2)

**All node operators and miners must update.**

- **Update window:** after block **#29,900** and before block **#30,000**.
- **Activation:** block **#30,000** (automatic — no command or restart at the height).
- **First DTD Jackpot V2 draw:** block **#30,186**.

### What it does
From #30,000 the **DTD Jackpot** becomes an **independent draw**. The regular
DTD reward is **unchanged**. To be eligible for the DTD Jackpot a miner must:

- contribute real Proof-of-Work (≥ 3 signed blocks in the last 5,000), **and**
- run a node: bind a node key to the mining key and keep it heartbeating.

Your **odds are proportional to your Proof-of-Work** (linear weight). Creating extra
addresses or extra nodes does **not** increase your odds. There is no cooldown and no
anti-dominance on the jackpot — it rewards contributed security + node participation.
Payout economics are unchanged (100 SOST base, up to 500 with rollover, paid from the
existing reserve — no new emission).

### What you must do
1. Have the new software ready **now**.
2. Between #29,900 and #29,999: stop your node, update to the V16 release, verify the
   published SHA256, restart. **Miners: run with `--realtime`.**
3. Do nothing at #30,000 — V2 activates by height automatically.

A node left on the old version after #30,000 **will fork off the network.**

Full instructions: sostcore.com → docs/v16 Operator Guide.
Release notes + verified binary hashes: (link at release).

---

### Release-day checklist (internal — before publishing the notice)
```
[ ] freeze consensus commit on feat/historical-jackpot-v2-30000
[ ] reintroduce V16 into main via revert-of-reverts OR clean cherry-pick (NOT a naive merge)
[ ] build final: sost-node, sost-miner, sost-cli  (-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF)
[ ] record: NODE VERSION / CONSENSUS COMMIT / SHA256(node,miner,cli)
[ ] confirm ALL green: unit, devnet paid-E2E, reorg, reindex, restart, upgrade V15->V16
[ ] publish binaries + hashes; THEN publish this notice
```
