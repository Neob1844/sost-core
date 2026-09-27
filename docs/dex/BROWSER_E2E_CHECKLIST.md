# SOST DEX — Real-Wallet Browser E2E Checklist (SOST+MetaMask, SOST+Xverse)

**Status of the automated run: BLOCKED-ENVIRONMENT.** The sandbox has no browser extensions
and no persistent relay (RLIMIT_FSIZE kills background servers), so these flows **cannot be
marked PASS from here**. The wallet adapters (`dex-wallets.js`) and the gating logic are unit-
tested with mock providers (16/16, DOM-verified), but a mock provider is not proof a real
wallet signs. This document is the reproducible procedure to run on a real machine; **do not
record PASS for any row until it is executed with the real extension installed.**

## Preconditions
- Node + miner built with `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF` (devnet:
  add `-DSOST_DEVNET_FORKS=ON`).
- A funded SOST devnet/regtest node reachable by the SOST sign-request bridge.
- EVM: a testnet (or anvil) with the `AtomicSwapHTLC` contract deployed; MetaMask on that network.
- BTC: bitcoind regtest; Xverse (or UniSat) with a funded regtest address + PSBT signing.
- The DEX page served over http(s) (not file://) so extension injection + EIP-6963 work.

## Capability gate (must hold before any swap is enabled)
The Swap CTA must stay disabled unless ALL are true (this is what `WM.swapReady(pair)` checks):
1. SOST wallet connected (bridge, no seed exposure).
2. Counterparty wallet connected (MetaMask for EVM pairs, Xverse for BTC pairs).
3. Counterparty wallet on the CORRECT network/chainId for the pair.
4. Sufficient balances on both legs for amount + fees.
5. The counterparty wallet is HTLC/PSBT-capable — **not merely able to send** (a wallet that can
   only send BTC but cannot `signPsbt` must be treated as incompatible).
6. A valid, unexpired quote/price is present.

## Part A — SOST + MetaMask (EVM leg)
| # | Step | Expected | Result |
|---|---|---|---|
| A1 | Open DEX, click Connect → SOST | Bridge connect; address shown; NO seed/priv-key prompt | ☐ |
| A2 | Connect → MetaMask (EIP-6963 discovery) | MetaMask popup; account + chainId captured | ☐ |
| A3 | Wrong EVM network selected | CTA blocked, reason "wrong network"; no swap allowed | ☐ |
| A4 | Switch MetaMask to correct chainId | CTA re-enables (if other gates pass) | ☐ |
| A5 | Insufficient balance on either leg | CTA blocked, reason "insufficient balance" | ☐ |
| A6 | Change MetaMask account mid-session | UI updates; stale approval invalidated | ☐ |
| A7 | Execute swap; sign the EVM `lockNative`/`lockERC20` in MetaMask | tx broadcast; Activity shows the real txid | ☐ |
| A8 | Watcher bridges preimage; SOST leg claims | Both legs settle; Activity 10-step lifecycle from real events | ☐ |
| A9 | Reject the MetaMask signature | Swap aborts cleanly; no partial state; refund path documented | ☐ |
| A10 | Quote expires before signing | CTA blocks; requires fresh quote | ☐ |

## Part B — SOST + Xverse (BTC leg)
| # | Step | Expected | Result |
|---|---|---|---|
| B1 | Connect → SOST bridge | as A1 | ☐ |
| B2 | Connect → Xverse | BTC address + public key captured | ☐ |
| B3 | Verify PSBT capability | `signPsbt` present; a send-only wallet is rejected as incompatible | ☐ |
| B4 | Build BTC HTLC (P2WSH, BIP-199) lock | funding PSBT presented to Xverse | ☐ |
| B5 | Sign PSBT in Xverse | signed tx broadcast to regtest; txid in Activity | ☐ |
| B6 | Counterparty SOST HTLC lock | SOST HTLC_LOCK confirmed | ☐ |
| B7 | Claim reveals preimage; watcher bridges to BTC claim | both legs settle; preimage matches (sha256) | ☐ |
| B8 | Refund path: let timelock expire without claim | refund spendable after timeout; R24 pre-timeout refund rejected | ☐ |
| B9 | Xverse rejects PSBT sign | swap aborts; funds remain under user control | ☐ |

## Part C — resilience (run on both A and B)
| # | Scenario | Expected | Result |
|---|---|---|---|
| C1 | Relay restart mid-swap | state re-derived from chain; no double-spend, no lost swap | ☐ |
| C2 | Coordinator restart mid-swap | resumes from persisted state (proven in lab via coord_gate) | ☐ |
| C3 | Watcher disconnect/reconnect | preimage still bridged once available; no stuck swap | ☐ |
| C4 | Reorg on either chain | confirmations re-counted; premature settle prevented | ☐ |
| C5 | Refund after full expiry | initiator recovers funds; counterparty cannot claim post-timeout | ☐ |

## Sign-off
- Tester, machine, wallet versions, chain heights: ______________________
- Every ☐ must be ✅ (with the real extension) before the corresponding matrix cell moves from
  BLOCKED-ENVIRONMENT to TESTED. Lab-verified components (adapters, gating, coordinator recovery,
  atomic-swap primitives) are cited in `docs/v15/CROSS_CHAIN_SWAP_RESULTS.md`; they do NOT by
  themselves satisfy these real-wallet rows.
