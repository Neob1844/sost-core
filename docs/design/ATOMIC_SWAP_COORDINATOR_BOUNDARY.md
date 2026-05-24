# Atomic Swap — Coordinator Boundary (Phase 4C-0)

**Branch:** `feat/atomic-swap-htlc-v13-candidate`
**Status:** boundary specification (no code in this commit).
**Gate:** `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (sentinel OFF).

This document defines what the cross-chain atomic-swap coordinator **is**
and, more importantly, what it **must never be**. The coordinator is a
wallet-side state machine that helps the user follow the correct sequence
of swap steps. It is NOT a custodian, NOT a server, NOT an authority. The
SOST chain has no view into BTC or Ethereum at consensus time; the
coordinator runs entirely in the user's local wallet (or in a public web
client). Its outputs are advisory.

---

## Hard invariants — the coordinator MUST NOT

1. **Custody no funds.** Ever. The coordinator never holds a private key,
   never controls a wallet's funds, never moves SOST/BTC/ETH/USDT/USDC/
   BNB/PAXG/XAUT on behalf of a user.
2. **Sign no transaction automatically.** Every signing step is initiated
   by the user, via the user's wallet, with the user's keys, on the user's
   device.
3. **Broadcast no transaction automatically.** Every broadcast is
   initiated by the user. The coordinator may prepare an unsigned tx and
   ask the user to confirm + sign + broadcast, but never bypasses that
   loop.
4. **Talk to no SOST consensus path.** The coordinator's chain
   observations are read-only and feed only the user's UI. SOST consensus
   rules (R17-R24) never call into the coordinator.
5. **Touch no PoPC DEX surface.** PoPC DEX and OTC atomic swap are
   separate flows. The coordinator handles the OTC P2P atomic-swap flow
   only and does not modify, read, or interfere with PoPC contracts,
   SOSTEscrow.sol, position market, reward-right trades, Gold Vault
   governance, PoPC Model A/B, or PoPC settlement logic.
6. **Run no server-side authority.** There is no centralized coordinator
   instance with privileged knowledge of swaps. Two parties may share a
   relayed `swapId` for convenience, but the coordinator binary running
   in each user's wallet is independent and equal.
7. **Hold no external-chain state inside SOST consensus.** All chain
   observation (BTC mempool / Bitcoin block height; Ethereum mempool /
   block number; ERC-20 events) lives in the wallet UI, never in
   `tx_validation.cpp`, `mempool.cpp`, or `block_validation.cpp`.

---

## State machine (the public contract of the coordinator)

The coordinator is a pure state machine. Each swap progresses through
the states below. Transitions happen as the result of explicit user
actions (sign, broadcast) and/or passive chain observations (mempool /
block).

```
                    +-----------------+
                    | OfferCreated    |
                    +-----------------+
                            |
                            | user reviews + signs the SOST-side LOCK tx
                            v
                    +---------------------+
                    | SostLockPrepared    |   (unsigned tx ready)
                    +---------------------+
                            |
                            | user broadcasts SOST LOCK via wallet
                            v
                    +-------------------+
                    | SostLockBroadcast |
                    +-------------------+
                            |
                            | coordinator observes counterparty LOCK on BTC/EVM
                            v
                    +----------------------------+
                    | CounterpartyLockObserved   |
                    +----------------------------+
                            |
                            | user is ready to claim with preimage
                            v
                    +-------------+
                    | ClaimReady  |
                    +-------------+
                            |
                            | user broadcasts CLAIM on counterparty chain
                            | (reveals preimage)
                            v
                    +---------+
                    | Claimed |
                    +---------+

                    Timeout fork — at any point:

                            | refund_height reached
                            v
                    +-------------+
                    | RefundReady |
                    +-------------+
                            |
                            | user broadcasts REFUND
                            v
                    +----------+
                    | Refunded |
                    +----------+

                    Sad paths:

                    +---------+         +--------+
                    | Expired |         | Failed |
                    +---------+         +--------+
                       |                    |
                       | both refund        | unrecoverable error
                       | windows passed     | (e.g. wallet crash mid-flow)
                       | with no claim      |
                       | broadcast          |
```

### State definitions

  - **OfferCreated** — the user has filled the offer form. No transactions
    exist on any chain.
  - **SostLockPrepared** — the coordinator has built the unsigned
    SOST-side HTLC_LOCK transaction (via `HandleCreateHtlcLockRpc`). The
    user has not yet signed.
  - **SostLockBroadcast** — the user has signed and broadcast the
    SOST-side LOCK. The coordinator polls the SOST mempool / chain via
    the existing RPC (`getrawmempool`, `getrawtransaction`,
    `gethtlcstatus`) until the LOCK utxo is confirmed.
  - **CounterpartyLockObserved** — the coordinator has independently
    observed the counterparty LOCK on BTC or EVM (via a user-provided
    txid + a public block explorer or the user's own node). The
    coordinator does NOT trust the counterparty's claim; it requires
    cryptographic confirmation (the BTC P2WSH address matches the
    expected `sha256(redeemScript)`; the EVM `LockCreated` event matches
    the expected `swapId`).
  - **ClaimReady** — both LOCKs confirmed; the user holds the preimage;
    the BTC / EVM refund window is still open.
  - **Claimed** — the user has broadcast the counterparty-chain CLAIM,
    revealing the preimage. The coordinator now passively waits for the
    counterparty (or anyone) to claim the SOST side using the same
    preimage; once SOST CLAIM is broadcast the swap is complete.
  - **RefundReady** — the SOST `refund_height` has been reached. The
    coordinator now allows the user to build and broadcast a SOST
    REFUND.
  - **Refunded** — the user's SOST has been recovered via REFUND.
  - **Expired** — both sides' refund windows passed with no CLAIM. Both
    parties should now refund their respective sides independently.
  - **Failed** — unrecoverable error (e.g. wallet lost mid-flow,
    counterparty chain observation unavailable, etc.). The coordinator
    instructs the user to manually refund whichever side they locked.

### Transition triggers

  - **User action triggers:** sign, broadcast, supply preimage,
    abort.
  - **Passive observation triggers:** SOST mempool / chain (via RPC),
    counterparty chain (via user-supplied txid + user-supplied explorer
    URL).
  - **Time triggers:** refund_height reached (computed from current
    chain height + comparison with LOCK payload).

The coordinator NEVER advances state on observation alone for any action
that moves funds. Funds-moving transitions (LOCK broadcast, CLAIM
broadcast, REFUND broadcast) require explicit user action.

---

## Recovery / refund-first design

The coordinator's recovery model is: **always favour refund**. If a
swap is in any ambiguous state past the refund window, the coordinator's
default UI suggestion is "refund and try again", not "wait and hope".

This biases the user toward fund safety over swap completion. A swap
that abandons mid-way and refunds is a small UX loss; a swap that hangs
in an ambiguous state and the user loses funds is a hard fail.

Specifically:

  - If the counterparty LOCK is not observed within a defined window
    (e.g. 30 minutes past expected propagation time), the coordinator
    surfaces a clear "no counterparty LOCK observed — recommend
    abandoning swap and refunding your SOST when refund_height arrives"
    notice.
  - If the user's CLAIM broadcast on the counterparty chain fails for
    any reason (RBF dropped, mempool eviction, etc.), the coordinator
    treats the swap as Failed and recommends refund.
  - If chain observation is unavailable (no explorer URL configured, no
    local node), the coordinator does NOT auto-advance; it shows
    "observation paused — re-check manually before refund_height
    arrives".

---

## What the coordinator depends on (and what it does not)

**Depends on (read-only):**

  - SOST node RPC (for `gethtlcstatus`, `getrawtransaction`,
    `getrawmempool`).
  - User-supplied counterparty txids.
  - User-supplied chain explorer URLs (Etherscan, Mempool.space, etc.) —
    user-controlled, never hardcoded URLs.

**Does NOT depend on:**

  - SOST consensus internals beyond the public RPC.
  - Any centralized SOST coordinator service.
  - Any hosted oracle / API service.
  - Any built-in chain client (no in-process BTC / Ethereum light
    client). The user supplies their own block-explorer URL or runs
    their own node.

---

## Why this is implemented later, not in Phase 4C-0

The coordinator state machine is the LAST piece of the swap stack
because it depends on the previous phases:

  - The SOST side LOCK / CLAIM / REFUND RPC is the source of state for
    the SOST half (DONE this branch, Phase 3C-1).
  - The BTC redeemScript builder is needed to compute the expected P2WSH
    address for observation (DONE this branch, Phase 4A-0).
  - The BTC signing path is needed for the user to broadcast CLAIM /
    REFUND (PENDING, Phase 4A-1).
  - The EVM contract is needed for the EVM half of the swap (PENDING,
    Phase 4B-1).

Once Phase 4A-1 + 4B-1 land, the coordinator state machine is a small
C++ class (or wallet-side TypeScript) that consumes the above
primitives. The shape is fixed by this document; the implementation
is straightforward.

---

## Activation gating

The coordinator binary, when shipped, will refuse to operate while
`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT == INT64_MAX`. Same pattern as the
existing wallet/RPC/CLI helpers: gate-check first, then state-machine
progression.

When the gate flips to `V14_HEIGHT`, the coordinator becomes usable,
but only as a UI helper. The cryptography (HTLC on both chains) does
the actual safety work. The coordinator just keeps the user moving
through the steps in the right order.
