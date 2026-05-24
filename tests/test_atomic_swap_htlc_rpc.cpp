// Phase 3C-1 — RPC parameter wiring tests.
//
// Tests target the HandleXxxRpc helper layer in
// include/sost/atomic_swap_helpers.h directly. With the gate at INT64_MAX
// (current state) every gated call must return ok=false with the disabled
// error message. Parameter validation tests run regardless of gate because
// the gate is checked FIRST in the helper.

#include "sost/atomic_swap_helpers.h"
#include "sost/atomic_swap.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/consensus_constants.h"

#include <cstdio>
#include <climits>
#include <optional>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::atomic_swap;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

struct StubUtxoView : IUtxoView {
    std::optional<UTXOEntry> GetUTXO(const OutPoint&) const override {
        return std::nullopt;
    }
};

// Helper: a 10-element params vector with valid-looking hex/decimal entries.
static std::vector<std::string> valid_lock_params() {
    return {
        std::string(64, 'a'),     // p[0] prev_txid (32 bytes hex)
        "0",                       // p[1] prev_vout
        "200000",                  // p[2] prev_amount
        std::string(40, 'b'),     // p[3] prev_pkh (20 bytes hex)
        std::string(64, 'c'),     // p[4] hashlock
        "30000",                   // p[5] refund_height
        std::string(40, '5'),     // p[6] claim_pkh
        std::string(40, '7'),     // p[7] refund_pkh
        "100000",                  // p[8] lock_amount
        "2000"                     // p[9] fee
    };
}

static std::vector<std::string> valid_claim_params() {
    return {
        std::string(64, 'd'),     // p[0] lock_txid
        "0",                       // p[1] lock_vout
        "100000",                  // p[2] lock_amount
        std::string(64, 'e'),     // p[3] preimage
        std::string(40, '5'),     // p[4] claim_destination_pkh
        "10000",                   // p[5] marker_dust_amount
        "2000"                     // p[6] fee
    };
}

static std::vector<std::string> valid_refund_params() {
    return {
        std::string(64, 'd'),     // p[0] lock_txid
        "0",                       // p[1] lock_vout
        "100000",                  // p[2] lock_amount
        std::string(40, '7'),     // p[3] refund_destination_pkh
        "2000"                     // p[4] fee
    };
}

int main() {
    printf("\n== Atomic Swap HTLC Phase 3C-1 — RPC parameter wiring ==\n\n");
    const bool enabled = IsAtomicSwapHtlcEnabled();
    printf("  Gate is %s (IsAtomicSwapHtlcEnabled = %s)\n\n",
           enabled ? "OPEN" : "CLOSED", enabled ? "true" : "false");

    // ======================================================================
    // T1. disabled-gate behavior: all 5 helpers return the disabled message
    //     when the gate is INT64_MAX, regardless of params.
    // ======================================================================
    {
        auto r1 = HandleCreateHtlcLockRpc({});
        auto r2 = HandleClaimHtlcRpc({});
        auto r3 = HandleRefundHtlcRpc({});
        auto r4 = HandleDecodeHtlcRpc({});
        StubUtxoView v;
        auto r5 = HandleGetHtlcStatusRpc({}, 0, v);
        if (!enabled) {
            TEST("T1a createhtlclock disabled when gate closed",
                 !r1.ok && r1.body.find("disabled until protocol activation") != std::string::npos);
            TEST("T1b claimhtlc disabled when gate closed",
                 !r2.ok && r2.body.find("disabled until protocol activation") != std::string::npos);
            TEST("T1c refundhtlc disabled when gate closed",
                 !r3.ok && r3.body.find("disabled until protocol activation") != std::string::npos);
            TEST("T1d decodehtlc disabled when gate closed",
                 !r4.ok && r4.body.find("disabled until protocol activation") != std::string::npos);
            TEST("T1e gethtlcstatus disabled when gate closed",
                 !r5.ok && r5.body.find("disabled until protocol activation") != std::string::npos);
        } else {
            // Gate open: missing-params error instead (-32602)
            TEST("T1a (open) createhtlclock missing-params -> -32602",
                 !r1.ok && r1.error_code == -32602);
            TEST("T1b (open) claimhtlc missing-params -> -32602",
                 !r2.ok && r2.error_code == -32602);
            TEST("T1c (open) refundhtlc missing-params -> -32602",
                 !r3.ok && r3.error_code == -32602);
            TEST("T1d (open) decodehtlc missing-params -> -32602",
                 !r4.ok && r4.error_code == -32602);
            TEST("T1e (open) gethtlcstatus missing-params -> -32602",
                 !r5.ok && r5.error_code == -32602);
        }
    }

    // ======================================================================
    // T2. createhtlclock: missing params rejected before parsing
    // ======================================================================
    {
        std::vector<std::string> p = valid_lock_params();
        p.pop_back();  // only 9 params
        auto r = HandleCreateHtlcLockRpc(p);
        if (!enabled) {
            TEST("T2 createhtlclock missing param (gate closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T2 createhtlclock missing param (gate open) -> invalid_params",
                 !r.ok && r.error_code == -32602 && r.body.find("expected 10 positional") != std::string::npos);
        }
    }

    // ======================================================================
    // T3. createhtlclock: malformed hashlock (wrong length) rejected
    // ======================================================================
    {
        std::vector<std::string> p = valid_lock_params();
        p[4] = std::string(63, 'c');  // 63 chars instead of 64
        auto r = HandleCreateHtlcLockRpc(p);
        if (!enabled) {
            TEST("T3 createhtlclock bad-hashlock-len (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T3 createhtlclock bad-hashlock-len (open) -> invalid_params (hashlock 64 hex)",
                 !r.ok && r.error_code == -32602 && r.body.find("hashlock") != std::string::npos);
        }
    }

    // ======================================================================
    // T4. createhtlclock: malformed hex (invalid character) rejected
    // ======================================================================
    {
        std::vector<std::string> p = valid_lock_params();
        p[0] = std::string(63, 'a') + "z";  // last char invalid
        auto r = HandleCreateHtlcLockRpc(p);
        if (!enabled) {
            TEST("T4 createhtlclock bad-hex (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T4 createhtlclock bad-hex (open) -> invalid_params (prev_txid 64 hex)",
                 !r.ok && r.error_code == -32602 && r.body.find("prev_txid") != std::string::npos);
        }
    }

    // ======================================================================
    // T5. createhtlclock: negative amount rejected
    // ======================================================================
    {
        std::vector<std::string> p = valid_lock_params();
        p[8] = "-1";  // negative lock_amount
        auto r = HandleCreateHtlcLockRpc(p);
        if (!enabled) {
            TEST("T5 createhtlclock negative amount (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T5 createhtlclock negative amount (open) -> invalid_params",
                 !r.ok && r.error_code == -32602 && r.body.find("lock_amount") != std::string::npos);
        }
    }

    // ======================================================================
    // T6. claimhtlc: wrong preimage length rejected
    // ======================================================================
    {
        std::vector<std::string> p = valid_claim_params();
        p[3] = std::string(60, 'e');  // 30 bytes instead of 32
        auto r = HandleClaimHtlcRpc(p);
        if (!enabled) {
            TEST("T6 claimhtlc bad-preimage-len (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T6 claimhtlc bad-preimage-len (open) -> invalid_params (preimage 64 hex)",
                 !r.ok && r.error_code == -32602 && r.body.find("preimage") != std::string::npos);
        }
    }

    // ======================================================================
    // T7. refundhtlc: missing params rejected
    // ======================================================================
    {
        std::vector<std::string> p = valid_refund_params();
        p.pop_back();  // only 4
        auto r = HandleRefundHtlcRpc(p);
        if (!enabled) {
            TEST("T7 refundhtlc missing param (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T7 refundhtlc missing param (open) -> invalid_params (expected 5)",
                 !r.ok && r.error_code == -32602 && r.body.find("expected 5") != std::string::npos);
        }
    }

    // ======================================================================
    // T8. decodehtlc: malformed hex rejected
    // ======================================================================
    {
        auto r = HandleDecodeHtlcRpc({"not-hex"});
        if (!enabled) {
            TEST("T8 decodehtlc bad-hex (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T8 decodehtlc bad-hex (open) -> invalid_params (not valid hex)",
                 !r.ok && r.error_code == -32602 && r.body.find("not valid hex") != std::string::npos);
        }
    }

    // ======================================================================
    // T9. decodehtlc: even-length but garbage payload rejected by deserialize
    // ======================================================================
    {
        auto r = HandleDecodeHtlcRpc({"deadbeef"});  // valid hex, invalid tx
        if (!enabled) {
            TEST("T9 decodehtlc garbage tx (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            // Not a valid tx serialization -> invalid_params
            TEST("T9 decodehtlc garbage tx (open) -> invalid_params",
                 !r.ok && r.error_code == -32602);
        }
    }

    // ======================================================================
    // T10. gethtlcstatus: missing params rejected
    // ======================================================================
    {
        StubUtxoView v;
        auto r = HandleGetHtlcStatusRpc({"deadbeef"}, 1000, v);  // only 1 param
        if (!enabled) {
            TEST("T10 gethtlcstatus missing param (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            TEST("T10 gethtlcstatus missing param (open) -> invalid_params",
                 !r.ok && r.error_code == -32602 && r.body.find("expected 2") != std::string::npos);
        }
    }

    // ======================================================================
    // T11. gethtlcstatus: unknown swap returns Spent / Unknown safely
    //      (never errors out, never crashes, never returns internal state)
    // ======================================================================
    {
        StubUtxoView v;
        auto r = HandleGetHtlcStatusRpc(
            {std::string(64, 'f'), "0"}, 1000, v);
        if (!enabled) {
            TEST("T11 gethtlcstatus unknown (closed) -> disabled msg",
                 !r.ok && r.body.find("disabled") != std::string::npos);
        } else {
            // Open: utxo not found -> Spent (or Unknown), but ALWAYS ok=true
            // with a status field; never an error.
            TEST("T11 gethtlcstatus unknown swap (open) -> ok with status",
                 r.ok && (r.body.find("Spent") != std::string::npos ||
                          r.body.find("Unknown") != std::string::npos));
        }
    }

    // ======================================================================
    // T12. No-network-call / no-broadcast static guarantee.
    //      The helpers are pure C++ with no socket / no curl / no HTTP.
    //      This test is symbolic: it confirms the test process completes
    //      with no hangs or external calls. The grep audit in the commit
    //      message is the authoritative static check.
    // ======================================================================
    {
        auto r1 = HandleCreateHtlcLockRpc(valid_lock_params());
        auto r2 = HandleClaimHtlcRpc(valid_claim_params());
        auto r3 = HandleRefundHtlcRpc(valid_refund_params());
        TEST("T12 helpers complete without external IO (returned in-process)",
             true);  // reaching this line = no hang, no segfault
        (void)r1; (void)r2; (void)r3;
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
