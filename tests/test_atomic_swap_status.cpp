// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// OTC-2.5 — HTLC read-only status tests.
//
// Two layers, both pure / gate-agnostic:
//   1. ClassifyHtlcStatus — the decision core the node's gethtlcstatus RPC
//      calls once it has gathered the chain facts. Every branch is covered:
//      unknown / locked / expired / claimed / refunded, plus the explicit
//      "spent but unresolved" case and gate-independence (a read of chain
//      state is never a consensus action).
//   2. The node-status -> watcher pipeline: a gethtlcstatus result drives the
//      OTC-2 watcher to the correct auto-pilot action (Wait/Claim/Refund/Done)
//      and a revealed preimage from a CLAIM is ingested on real sha256 match.

#include "sost/atomic_swap_helpers.h"
#include "sost/atomic_swap_watcher.h"
#include "sost/transaction.h"   // TX_TYPE_HTLC_CLAIM / TX_TYPE_HTLC_REFUND
#include "sost/crypto.h"
#include <array>
#include <cstdio>

using namespace sost;
using namespace sost::atomic_swap;

static int g_fail = 0;
#define TEST(msg, cond) do { \
    if (!(cond)) { std::printf("  FAIL: %s\n", msg); ++g_fail; } \
    else { std::printf("  ok:   %s\n", msg); } \
} while (0)

// The node sets lock_unspent for the watcher from the resolved status.
static bool LockUnspentFromStatus(HtlcResolvedStatus st) {
    return st == HtlcResolvedStatus::Locked || st == HtlcResolvedStatus::Expired;
}

int main() {
    std::printf("[OTC-2.5 htlc status]\n");

    // ---- ClassifyHtlcStatus: every branch ----
    {
        // Not an HTLC lock at all -> Unknown (regardless of other facts).
        TEST("non-htlc outpoint -> unknown",
             ClassifyHtlcStatus(/*is_htlc*/false, /*present*/false, 100, 200, 0)
                 == HtlcResolvedStatus::Unknown);
        TEST("non-htlc but present -> unknown",
             ClassifyHtlcStatus(false, true, 100, 50, 0)
                 == HtlcResolvedStatus::Unknown);

        // Present lock, before the refund window -> Locked (claimable).
        TEST("present, height < refund -> locked",
             ClassifyHtlcStatus(true, true, 999, 1000, 0)
                 == HtlcResolvedStatus::Locked);
        // Present lock, at/after the refund window -> Expired (refundable).
        TEST("present, height == refund -> expired",
             ClassifyHtlcStatus(true, true, 1000, 1000, 0)
                 == HtlcResolvedStatus::Expired);
        TEST("present, height > refund -> expired",
             ClassifyHtlcStatus(true, true, 1500, 1000, 0)
                 == HtlcResolvedStatus::Expired);

        // Spent by a CLAIM / REFUND.
        TEST("spent by CLAIM -> claimed",
             ClassifyHtlcStatus(true, false, 1500, 1000, TX_TYPE_HTLC_CLAIM)
                 == HtlcResolvedStatus::Claimed);
        TEST("spent by REFUND -> refunded",
             ClassifyHtlcStatus(true, false, 1500, 1000, TX_TYPE_HTLC_REFUND)
                 == HtlcResolvedStatus::Refunded);
        // Spent but the spender wasn't resolved -> honest Unknown (no guess).
        TEST("spent, spender unresolved -> unknown",
             ClassifyHtlcStatus(true, false, 1500, 1000, 0)
                 == HtlcResolvedStatus::Unknown);
    }

    // ---- Status name strings (stable JSON vocabulary) ----
    {
        TEST("name locked",   std::string(HtlcResolvedStatusName(HtlcResolvedStatus::Locked))   == "locked");
        TEST("name expired",  std::string(HtlcResolvedStatusName(HtlcResolvedStatus::Expired))  == "expired");
        TEST("name claimed",  std::string(HtlcResolvedStatusName(HtlcResolvedStatus::Claimed))  == "claimed");
        TEST("name refunded", std::string(HtlcResolvedStatusName(HtlcResolvedStatus::Refunded)) == "refunded");
        TEST("name unknown",  std::string(HtlcResolvedStatusName(HtlcResolvedStatus::Unknown))  == "unknown");
    }

    // ---- Gate independence: a status read does NOT depend on the activation
    //      gate. On mainnet the gate is OFF (IsAtomicSwapHtlcEnabled()==false)
    //      yet the classifier still answers from the supplied facts. (In
    //      practice mainnet has zero HTLC locks, so is_htlc_lock is always
    //      false there and the answer is Unknown — but the function itself is
    //      gate-agnostic, which is the invariant we assert.)
    {
        TEST("classifier is gate-independent (no disabled refusal)",
             ClassifyHtlcStatus(true, true, 10, 20, 0) == HtlcResolvedStatus::Locked);
    }

    // ---- node-status -> watcher action pipeline ----
    {
        // Build a watched swap whose refund opens at height 1000.
        WatchedSwap s;
        s.swap_id = "swap-1";
        s.sost_refund_height = 1000;

        // REFUNDER watching its own lock.
        s.side = WatchSide::Refunder;

        // Node says "locked" at height 900 -> still unspent, before timeout -> Wait.
        {
            auto st = ClassifyHtlcStatus(true, true, 900, 1000, 0);
            TEST("refunder + node 'locked' -> Wait",
                 DecideWatchAction(s, 900, LockUnspentFromStatus(st)) == WatchAction::Wait);
        }
        // Node says "expired" at height 1000 -> unspent, timeout open -> Refund.
        {
            auto st = ClassifyHtlcStatus(true, true, 1000, 1000, 0);
            TEST("refunder + node 'expired' -> Refund",
                 DecideWatchAction(s, 1000, LockUnspentFromStatus(st)) == WatchAction::Refund);
        }
        // Node says "claimed" (lock spent) -> Done (counterparty took it).
        {
            auto st = ClassifyHtlcStatus(true, false, 1500, 1000, TX_TYPE_HTLC_CLAIM);
            TEST("refunder + node 'claimed' -> Done",
                 DecideWatchAction(s, 1500, LockUnspentFromStatus(st)) == WatchAction::Done);
        }
        // Node says "refunded" (lock spent) -> Done.
        {
            auto st = ClassifyHtlcStatus(true, false, 1500, 1000, TX_TYPE_HTLC_REFUND);
            TEST("refunder + node 'refunded' -> Done",
                 DecideWatchAction(s, 1500, LockUnspentFromStatus(st)) == WatchAction::Done);
        }

        // CLAIMANT watching a counterparty lock.
        WatchedSwap c;
        c.swap_id = "swap-2";
        c.side = WatchSide::Claimant;
        c.sost_refund_height = 1000;

        // No preimage yet, node 'locked' -> Wait.
        {
            auto st = ClassifyHtlcStatus(true, true, 500, 1000, 0);
            TEST("claimant, no preimage, node 'locked' -> Wait",
                 DecideWatchAction(c, 500, LockUnspentFromStatus(st)) == WatchAction::Wait);
        }

        // A counterparty CLAIM reveals the preimage on-chain; gethtlcstatus
        // surfaces it. The watcher ingests it (real sha256 check) and can now
        // claim within the window.
        std::array<uint8_t,32> secret; secret.fill(0x5A);
        Bytes32 hl = sha256(secret.data(), secret.size());
        for (int i = 0; i < 32; ++i) c.hashlock[i] = hl[i];

        std::array<uint8_t,32> wrong; wrong.fill(0x5B);
        TEST("watcher rejects wrong revealed preimage", !IngestRevealedPreimage(c, wrong));
        TEST("watcher accepts correct revealed preimage", IngestRevealedPreimage(c, secret));
        {
            auto st = ClassifyHtlcStatus(true, true, 600, 1000, 0); // still locked
            TEST("claimant, preimage ingested, node 'locked' -> Claim",
                 DecideWatchAction(c, 600, LockUnspentFromStatus(st)) == WatchAction::Claim);
        }
        // Once the lock is spent (node 'claimed') the claimant is Done.
        {
            auto st = ClassifyHtlcStatus(true, false, 600, 1000, TX_TYPE_HTLC_CLAIM);
            TEST("claimant, node 'claimed' -> Done",
                 DecideWatchAction(c, 600, LockUnspentFromStatus(st)) == WatchAction::Done);
        }
    }

    if (g_fail == 0) std::printf("ALL HTLC STATUS TESTS PASSED\n");
    else std::printf("%d HTLC STATUS TESTS FAILED\n", g_fail);
    return g_fail == 0 ? 0 : 1;
}
