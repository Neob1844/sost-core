# "SOST in 2 Minutes" — V15 · content specification

Status: **specification only. No video has been produced.** This exists because
`sost-intro.mp4` was withdrawn from the public Watch chooser on 2026-09-02: it described a
protocol that no longer exists, and there is no source project to edit — only the rendered MP4.
The replacement has to be authored from scratch, and this is the list of what it may say.

Every claim below was checked against the live site and the repository on 2026-09-02 and is
marked **CURRENT**, **STALE** or **VERIFY**. Nothing here is written from memory.

## Why the old film was withdrawn

| Screen in the old film | Problem |
|---|---|
| `OTC / P2P Atomic Swaps` — "V14 PREVIEW", "gates still closed" | STALE — V14 label, and the gate state has moved |
| `Swap SOST with` — "DESIGNED PAIRS (V14)" | STALE — V14 label |
| `SOST DEX` under "PROOF OF PERSONAL CUSTODY — PoPC" | STALE — the PoPC DEX was reframed |
| `50% MINER / 25% GOLD FUNDING VAULT / 25% POPC POOL` | STALE — V15 replaced this with DTD |
| `Observable, not a peg` — "25% of every block routed to the Gold Funding Vault" | STALE — same reason |
| `DTD LOTTERY` — "active since block 7,100, permanent cadence since 12,100" | STALE — superseded cadence |

The site itself already carries the correction: *"Update — no longer active: at V15 (block
#25,000) the Gold Funding Vault / PoPC gold-emission plan has been temporarily replaced by the
DTD."* The film never got that update.

## What the new film may say

| Claim | Status | Verified against |
|---|---|---|
| Native Layer 1 Proof-of-Work | CURRENT | index.html |
| ConvergenceX — memory-hard PoW | CURRENT | index.html, casert-spec.html |
| V15 activation at block **25,000** | CURRENT | live site, 8 occurrences |
| Hard cap 4,669,201 SOST | CURRENT | sost-tokenomics.html |
| Target spacing 10 minutes | CURRENT | index.html |
| DTD — 1-of-3 cadence, deterministic | CURRENT | index.html, sost-mechanisms.mp4 |
| DTD recency gate — 5,000 normal | CURRENT | docs/V15_DTD_RECENCY_GATE.md |
| Atomic Swap DEX | CURRENT | index.html, sost-dex.html |
| No ICO · no premine · no VC allocation · no dev tax | CURRENT | index.html — but see note |
| Fair launch by construction | CURRENT | index.html |
| Gold Funding Vault / PoPC Pool emission | **STALE — DO NOT USE** | superseded at V15 |
| Any "V14" label | **STALE — DO NOT USE** | — |
| PoPC as a DEX | **STALE — DO NOT USE** | reframed to PoPC Bond Staking |
| BTC leg of the Atomic Swap | **VERIFY** | BTC is gated OFF; state it only if still true at production time |
| Gold / Metals Reserve | **VERIFY** | staged and not active; check the page before claiming anything |
| Jackpot heights and first-jackpot block | **VERIFY** | check the explorer's live figures, not a remembered number |

Note on "no ICO / no premine": true and worth saying, but it is a claim about launch history, so
it should be phrased as history and not as an ongoing property.

## Production notes learned the hard way

1. **Keep the source project.** The current films cannot be corrected because only the render
   exists. A one-line factual change now costs a full re-authoring.
2. **Put block heights in one place.** Both films bake activation heights into pixels. Heights
   move. Either avoid them, or accept that the film has a shelf life and say so on the card.
3. **Use the current mark.** `sost-logo.png`, 107,602 bytes, superellipse, with the pulsing red
   glow the site uses on a 2.4-second cycle.
4. **Shorter is safer.** The old film is 1:58 and spends six screens on economics that changed.
   The fewer specific numbers a film carries, the longer it stays true.
