# Atomic Swap V14.7 — Coordinated relay re-activation (block 18,000)

## Summary

The atomic-swap HTLC **consensus** rules have been live since **V14.5 / block 16,000**
(`atomic_swap_htlc_active_at`, unchanged). What was missing was the **relay/mempool
policy** exemption (PR #63): `ValidateTransactionPolicy` ran the capsule check on every
payload-bearing output, so HTLC outputs (`OUT_HTLC_LOCK` / `OUT_HTLC_CLAIM_WITNESS`)
were rejected on `sendrawtransaction` with `bad capsule` and could never be broadcast,
relayed or mined — even though they were valid in a block.

PR #63 fixed that, but its first deploy was **ungated**: it took effect the moment a node
ran the new binary. Updated nodes began building `txs=N` templates carrying the HTLC while
un-updated nodes stayed `txs=1` — an **asymmetric-mempool** condition that degraded the
updated miners (for ~134 blocks only the dominant, un-updated miner produced accepted
blocks). That is why the deploy was rolled back and PR #63 frozen.

## The fix, re-applied as a coordinated flag-day (V14.7)

- **New milestone `V14_7_HEIGHT`** (mainnet **18,000** / testnet 40) in `include/sost/params.h`.
- **New gate** `atomic_swap_relay_active_at()` + `ATOMIC_SWAP_RELAY_ACTIVATION_HEIGHT = V14_7_HEIGHT`
  in `include/sost/atomic_swap.h`, **decoupled** from the consensus gate
  `atomic_swap_htlc_active_at` (still `V14_5_HEIGHT` / 16,000, **unchanged**).
- `src/tx_validation.cpp`: the PR #63 capsule exemption now keys off
  `atomic_swap_relay_active_at` (the **only** policy-path use; consensus-path uses stay on 16,000).

Below block 18,000 every node keeps rejecting HTLC in the mempool, so no HTLC enters a
template and every block stays `txs=1` — **mining is unaffected**. At 18,000 all upgraded
nodes flip together, eliminating the asymmetry that caused the earlier disruption.

**This is a POLICY gate, not a new consensus rule.** Block validity is byte-identical, so a
non-upgraded node does **not** fork off the chain. The mandatory coordinated recompile+restart
is to keep every node's mempool homogeneous (all `txs=1` → all `txs=N` in lockstep) and so
that every miner can relay/mine swap transactions.

## Verification

- Clean `sost-node` build with mandatory flags (`-DSOST_ENABLE_PHASE2_SBPOW=ON
  -DSOST_TESTNET_FORKS=OFF`, Release).
- Tests pass: `tx-validation`, `capsule`, `v14-h3-h4`, all `atomic-swap*` / `htlc*`.

## Recommended before the 18,000 window (CTO note)

Gating synchronizes **when** `txs=N` behavior begins but does not by itself prove `txs=N`
blocks are safe. Run the regtest reproduction of a `txs=N` HTLC block (mine + propagate,
pre-fix vs post-fix) before block 18,000 — there is ample runway. Also recommended: a
**local node on the founder's miner** to remove tunnel latency.

## Build & activation

```bash
cd /opt/sost && git pull
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"
# restart NODE and MINER in the window: after block 17,900, before block 18,000
```

## Miner coordination

- Publish binary + SHA-256; post the announcement below on BitcoinTalk + Telegram + the site banners.
- Reach the known high-hashrate miners directly — every one matters.
- Recompile/restart window: after block 17,900, before 18,000.
- Rollback: because this is a policy gate, reverting is safe (raise `V14_7_HEIGHT`, recompile,
  re-announce) with no fork risk to the chain.

---

## BitcoinTalk announcement (DRAFT — publish after dev approves + release binary + SHA-256)

```
[center][img]http://sostcore.com/sost-logo.png[/img]

[size=15pt][b][color=#d9a441]V14.7 — MANDATORY NODE & MINER UPDATE[/color][/b][/size]
[size=12pt][b]Atomic Swap re-activates at BLOCK 18,000[/b][/size]
[b]Recompile + restart window: after block 17,900, before block 18,000[/b][/center]

[hr]

[b]WHAT THIS IS[/b]
The SOST Atomic Swap (cross-chain HTLC — SOST <-> ETH, BSC/BNB, and later BTC) is being
switched back on under a coordinated activation at [b]block 18,000[/b] (milestone V14.7).
Every node and miner must run the updated binary before the chain reaches 18,000.

[b]WHAT YOU MUST DO[/b]
[list=1]
[li]git pull the latest sost-core (main).[/li]
[li]Recompile: [code]cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release && cmake --build build --target sost-node sost-miner sost-cli -j$(nproc)[/code][/li]
[li]Restart your NODE and your MINER.[/li]
[li]Do it AFTER block 17,900 and BEFORE block 18,000.[/li]
[/list]

[b]Until block 18,000 nothing changes[/b] — mining and consensus are unaffected, and no funds
are or were ever at risk. From 18,000, all updated nodes flip together and begin relaying/mining
swap transactions in lockstep.

[hr]

[b][color=#d9a441]FORENSIC NOTE — full transparency[/color][/b]

The atomic-swap fix is localized and tested. When we first implemented it — updating the binaries
and restarting node and miner — even though we believed it did not touch consensus, an operational
anomaly appeared: for roughly 134 blocks the dominant miner, through no fault of its own, kept
mining with its blocks accepted normally, while the other miners who had updated saw their blocks
effectively rejected.

Anomalies of this kind are not easy to detect and typically surface precisely when you are pushing
an improvement or a bug fix. This is nobody's fault — no miner is responsible for it. In a protocol
built on trial, error, detection, diagnosis and fix, this is simply part of the process.

Root cause and remedy are now understood: the fix requires a [b]joint, synchronized update and
restart of all of us — operators and miners together[/b]. That is exactly why it is being done as
the V14.7 coordinated flag-day at block 18,000, instead of an ad-hoc deploy. Below 18,000 every node
keeps rejecting swap transactions in its mempool, so no block carries them and mining stays
untouched; at 18,000 the whole network switches at once, so the asymmetry that caused the earlier
disruption cannot happen again.

[hr]

[b]WHY THIS MATTERS[/b]
The atomic swap is an essential tool for the protocol to work well: it lets coins be swapped across
different blockchains (ETH, BSC, BTC, and more) with full security. That is not a simple task — it
requires real testing and trials by the founder, above all on mainnet, because that experience can
only be gained on mainnet and not on testnet.

[b]The swap remains founder-testing / DO NOT USE for third parties[/b] until it is announced as
validated. Any public use before that is at your own risk.

[hr]

[b]Technical note (for node operators):[/b] this V14.7 change is at the relay/mempool policy layer,
not a new consensus rule — a node that does not update will [i]not[/i] be forked off the chain.
However, you must update to relay and mine swap transactions and to keep the network's mempools
consistent. Announcements: this thread, [url=http://sostcore.com]sostcore.com[/url], and Telegram
[url=https://t.me/SOSTProtocolOfficial]t.me/SOSTProtocolOfficial[/url].
[/center]
```
