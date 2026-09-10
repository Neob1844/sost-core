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

### Operational safeguards (freeze → monitor → release-day)
These are process rules, **not** protocol changes. Consensus is frozen.

1. **Feature branch frozen de facto.** From now, nothing lands on
   `feat/historical-jackpot-v2-30000` except a fix for a **critical bug**. No "minor"
   change may touch already-validated code. Any fix re-runs the FULL suite before it
   is accepted.
2. **Clean-room build on release day.** Build from the tag, then do a **second clean
   build in a fresh checkout** and confirm the binaries/hashes match. If they are not
   byte-for-byte reproducible, document exactly the **compiler, its version, and the
   build environment** alongside the published hashes.
3. **Abort plan before #30,000.** If a critical problem appears during the
   #29,900–#29,999 window, **stop the rollout and publish a correction before the chain
   crosses #30,000.** Once V16 activates at #30,000, "go back to V15" is **not** a normal
   downgrade — treat pre-activation as the only safe abort point.
4. **Announce early.** The 100-block window is short (~16–17 h at current cadence).
   Publish the BitcoinTalk/Telegram notice and the guides **well before #29,900** so
   operators know exactly what to do, even though they execute the switch only inside
   the window.

### Release-day checklist (internal — before publishing the notice)
```
[ ] feature branch frozen; only a critical-bug fix may land (full suite re-run if it does)
[ ] freeze consensus commit on feat/historical-jackpot-v2-30000
[ ] reintroduce V16 into main via revert-of-reverts OR clean cherry-pick (NOT a naive merge)
[ ] verify HIST_JACKPOT_V2_HEIGHT == 30000  (mainnet)
[ ] confirm ALL green: unit, devnet paid-E2E, rollover->cap, reorg, reindex, restart, upgrade V15->V16, auto-heartbeat
[ ] create the FINAL release tag
[ ] build final FROM THE TAG: sost-node, sost-miner, sost-cli  (-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF)
[ ] SECOND clean build in a fresh checkout; confirm hashes match (else document toolchain+env)
[ ] record: NODE VERSION / CONSENSUS COMMIT+TAG / SHA256(node,miner,cli)  (finals REPLACE the RC hashes)
[ ] publish binaries + FINAL hashes + source commit/tag; publish QUICK_UPGRADE_5MIN
[ ] publish this notice (BitcoinTalk/Telegram) WELL BEFORE #29,900
[ ] abort point: any critical issue in #29,900–#29,999 -> halt + fix BEFORE #30,000
```
