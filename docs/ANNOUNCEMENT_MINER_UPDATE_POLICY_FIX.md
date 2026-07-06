# SOST — Miner & Node Update Announcement (Atomic Swap policy fix)

Ready-to-post copy for **BitcoinTalk (BBCode)**, **X/Twitter**, and **Telegram**.
The fix is **policy-only** (relay/mempool), consensus is byte-identical → **no fork, no coordinated window**.

---

## 1) BitcoinTalk — BBCode (paste as-is)

```bbcode
[center][b][size=14pt]⚙ SOST NODE & MINER UPDATE — Atomic Swap Policy Fix[/size][/b]
[i]Policy-only change · consensus byte-identical · NO fork · please recompile & restart[/i][/center]

[hr]

[b]TL;DR[/b] — A bug in the SOST Atomic Swap has been found and fixed. It is a [b]relay/mempool policy[/b] fix, [b]not[/b] a consensus change: old and new binaries agree on which blocks are valid, so there is [b]no fork and no coordinated upgrade window[/b]. Please recompile and restart your node & miner so atomic-swap transactions can be relayed and mined across the whole network.

[b]What happened[/b]
SOST Atomic Swap HTLC transactions were valid at consensus (a block containing one is accepted by every node), but the node's relay/mempool policy rejected them — a leftover check treated the HTLC output's typed payload as a "capsule" and failed on its magic bytes. Result: HTLC LOCK/CLAIM transactions could not be broadcast, relayed or mined, even though they were consensus-valid. It was discovered during the founder's first real mainnet self-swap.

[b]The fix[/b]
The relay/mining policy now exempts HTLC outputs (OUT_HTLC_LOCK / OUT_HTLC_CLAIM_WITNESS) from the capsule check, mirroring what consensus already does.
[list]
[li][b]Policy-only[/b] — block/consensus validation is byte-identical.[/li]
[li][b]No fork risk[/b] — updated and non-updated nodes accept exactly the same blocks.[/li]
[li][b]No coordinated window[/b] — update any time; nothing breaks if some miners update before others.[/li]
[li]Fully tested — atomic-swap, capsule and tx-validation suites all green; real capsules still validated.[/li]
[/list]

[b]Why update[/b]
Until you update, your node will not relay or mine atomic-swap transactions. The more of the network updates — especially larger miners — the sooner atomic swaps work reliably for everyone. Not updating does [b]not[/b] stop you from mining normal blocks; it only means your blocks won't include swap transactions.

[b]How to update[/b]
[code]# 1) BUILD the new binary (flags are MANDATORY):
cd sost-core
git checkout main && git pull origin main
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-cli sost-miner sost-signtx -j$(nproc)

# 2) RESTART your NODE:
#    systemd:  sudo systemctl restart sost-node
#    manual:   stop the old sost-node, then start ./build/sost-node

# 3) RESTART your MINER:
#    stop the old sost-miner, then relaunch ./build/sost-miner with your usual args[/code]

[b]⚠ Important[/b]
[list]
[li][b]-DSOST_TESTNET_FORKS=OFF is required[/b] (=ON throws you off mainnet).[/li]
[li]The same binary carries the existing V15 schedule (PoPC 20,000 / 25,000) unchanged. Gold Vault & Gold Boost remain OFF.[/li]
[/list]

[b]Atomic Swap status[/b]
The atomic swap is still in [b]founder testing[/b] and is [b]not[/b] for public use yet — please do not use it until we officially announce it is safe. We expect it ready for public use in a few days, once the network has updated.

[b]Links[/b]
Explorer: https://sostcore.com/sost-explorer.html
Source: https://github.com/Neob1844/sost-core
Contact: sost@sostcore.com · Telegram: https://t.me/SOSTProtocolOfficial

[i]This is a routine node/miner maintenance update — no consensus rules changed.[/i]
```

---

## 2) X / Twitter — thread (3 posts)

**Post 1/3**
```
⚙ SOST node & miner update

We found and fixed a bug in the SOST Atomic Swap: HTLC transactions were valid at consensus but rejected by the node's mempool policy — so swaps couldn't be relayed or mined.

The fix is POLICY-ONLY. Consensus is byte-identical → NO fork, update any time. 🧵
```

**Post 2/3**
```
Please recompile & restart your node + miner so atomic swaps work network-wide:

git pull →
cmake … -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF →
build (node/cli/miner/signtx) →
restart node + miner

Full step-by-step on the explorer banner:
https://sostcore.com/sost-explorer.html
```

**Post 3/3**
```
Not updating does NOT stop you mining — old & new binaries accept the same blocks. Updating just lets your blocks carry swap txs.

The atomic swap stays in founder testing — do NOT use it yet. We expect it public-ready in a few days, once the network updates.

Source: https://github.com/Neob1844/sost-core
```

---

## 3) Telegram (paste to t.me/SOSTProtocolOfficial)

```
⚙ SOST — Node & Miner Update (please recompile)

We found and fixed a bug in the SOST Atomic Swap. HTLC transactions were valid at consensus but were rejected by the node's relay/mempool policy, so swaps could not be broadcast or mined.

✅ The fix is POLICY-ONLY — block/consensus validation is byte-identical, so there is NO fork risk and NO coordinated window. You can update at any time; nothing breaks if some update before others.

Please recompile and restart your node & miner so atomic-swap transactions can be relayed and mined across the whole network:

1) BUILD:
cd sost-core
git checkout main && git pull origin main
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-cli sost-miner sost-signtx -j$(nproc)

2) RESTART NODE:
• systemd: sudo systemctl restart sost-node
• manual:  stop old sost-node, start ./build/sost-node

3) RESTART MINER:
stop old sost-miner, relaunch ./build/sost-miner with your usual args

⚠ -DSOST_TESTNET_FORKS=OFF is required (=ON throws you off mainnet).
PoPC V15 (20,000 / 25,000), Gold Vault & Gold Boost unchanged.

ℹ Not updating does NOT stop you from mining normal blocks — it only means your blocks won't include swap transactions. Everyone keeps mining; all nodes accept the same blocks.

The atomic swap is still in founder testing — please do NOT use it yet. We expect it public-ready in a few days.

🔎 Explorer: https://sostcore.com/sost-explorer.html
💻 Source: https://github.com/Neob1844/sost-core
✉ Questions: sost@sostcore.com
```

---

### Notes for the poster
- The build snapshot is the current `main` tip (includes PR #63, the HTLC policy fix). No block-height deadline — it is a policy update, safe to deploy at any time.
- Do **not** publish any $/SOST figure. Keep the atomic swap framed as founder-testing until officially cleared.
- Official channel for public posts: `t.me/SOSTProtocolOfficial`. Person-of-contact handle (if needed on a form): `@NeoB1844`.
