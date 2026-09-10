# SOST V16 — Release Manifest (RC)

> **Status:** release-candidate. Mainnet is **untouched** (still V15). The FINAL,
> published hashes are produced on release day from the exact merge commit, after the
> feature is merged to `main` (revert-of-reverts) and `HIST_JACKPOT_V2_HEIGHT == 30000`
> is re-confirmed. The hashes below pin the current validated RC.

## Consensus
| Item | Value |
|---|---|
| Feature | DTD Jackpot V2 — independent, node-gated, PoW-linear-weighted draw |
| Activation height (mainnet) | **30,000** (OWNER-LOCKED) |
| First V2 jackpot draw | **30,186** |
| Node epoch length | 288 blocks (== jackpot cadence) |
| PoW eligibility/weight window | 5,000 blocks; minimum 3 SbPoW blocks |
| Weight | linear in SbPoW blocks in window (no sqrt/log/cap) |
| Payout | 100 base / 500 cap / rollover, from existing reserve (supply-neutral) |
| Seed | domain-separated (`SOST_HIST_JACKPOT`) |
| DTD-normal | UNCHANGED |
| Pre-#30,000 behaviour | byte-identical to V15 |

## RC binaries (mainnet flags: `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`)
| Binary | SHA256 |
|---|---|
| sost-node  | `8165feb8b39973963bbe89aa64d9c53ba7f8f0b009c11ca3a8d9a530c181afd3` |
| sost-miner | `f43cd5bbffd23bdb144bbdec8679cb67395e288fc8e70fcc4f2f8f7ffe1bbb67` |
| sost-cli   | `ab66e3bf97e88dfc73e3da5d02286b818fb70f6fea212c2fc7f4b5c21180c5e6` |

- Node version banner: **SOST Node v0.4.0** (Profile: MAINNET)
- Consensus commit: `4847df819eff377e9b5a4245b6c8ca9147fcb4ef`
- Branch: `feat/historical-jackpot-v2-30000`

## Validation (all PASS)
| Suite | Result |
|---|---|
| Unit — jackpot_v2 core | 46 / 46 |
| Unit — node participation | 73 / 73 |
| E2E — paid V2 jackpot (node-gated weighted; unbound excluded; reserve spent) | PASS |
| E2E — rollover → 500 cap (0 eligible; funds preserved) | PASS |
| E2E — V15 → V16 upgrade crossing (byte-identical load + auto-activate) | PASS |
| E2E — **native auto-heartbeat** (`--node-key`; bound node auto-eligible, wins paid V2) | PASS |

## New operator surface
- `sost-node --node-key <hex64>` — native per-epoch auto-heartbeat (opt-in).
- `sost-cli ... createnodebind <seq> <node_privkey_hex>` — bind a node key.
- `sost-cli ... nodeheartbeat <node_privkey_hex> <epoch> <tip_ref>` — manual fallback.
- RPC `checkhistoricaljackpoteligibility <address>` — eligibility + reasons.
- RPC `getjackpotv2audit <height>` — full eligible set, weights, pot/rollover, winner.

## Release-day checklist (NOT yet done — mainnet stays V15 until then)
1. Merge feature to `main` via revert-of-reverts (see UPGRADE_NOTICE.md).
2. Re-confirm `HIST_JACKPOT_V2_HEIGHT == 30000`; tag the release.
3. Rebuild from the tag; publish FINAL SHA256 (replacing these RC hashes).
4. Broadcast BitcoinTalk + Telegram (docs/v16/*.txt) before #29,900.
