// OTC-5 — Atomic Swap canonical policy layer tests.
//
// Covers: canonical timeout ordering (safe + every unsafe mode) with
// human-readable deadlines; collision-resistant swapId derivation
// (determinism, input-binding / anti-squatting, and BIT-FOR-BIT parity with
// the Solidity AtomicSwapHTLC.computeSwapId); funding/confirmation
// classification; EVM claim preimage extraction (calldata + event, happy +
// adversarial); RPC-failure recovery policy; and the truthful asset matrix.

#include "sost/atomic_swap_policy.h"
#include "sost/crypto.h"

#include <cstdio>
#include <string>

using namespace sost::atomic_swap;
using namespace sost::atomic_swap::policy;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

static std::array<uint8_t,20> addr(uint8_t last) {
    std::array<uint8_t,20> a{}; a[19] = last; return a;
}
static sost::Bytes32 b32(uint8_t fill) {
    sost::Bytes32 b{}; for (auto& x : b) x = fill; return b;
}
static std::string hexof(const std::vector<uint8_t>& v) {
    static const char* H = "0123456789abcdef";
    std::string s; for (uint8_t x : v) { s.push_back(H[x>>4]); s.push_back(H[x&0xf]); }
    return s;
}

int main() {
    printf("\n== Atomic Swap Policy (OTC-5) ==\n\n");

    // =====================================================================
    // 1. Canonical timeout ordering
    // =====================================================================
    {
        // SAFE: T2=100 < T1=112, gap 12 >= margin 6.
        TimeoutPolicyInput in;
        in.initiator_refund_height = 112;
        in.responder_refund_height = 100;
        in.current_height = 50;
        in.safety_margin_min_blocks = 6;
        in.seconds_per_block = 10;
        auto r = EvaluateTimeoutOrder(in);
        TEST("TO1 safe ordering ok", r.ok && r.errors.empty());
        TEST("TO1b refund_gap computed", r.refund_gap == 12);
        TEST("TO1c human deadlines populated",
             !r.responder_deadline_human.empty() && !r.initiator_deadline_human.empty());
        TEST("TO1d summary says SAFE", r.summary_human.rfind("SAFE", 0) == 0);
        TEST("TO1e eta rendered (seconds_per_block>0)",
             r.responder_deadline_human.find("from now") != std::string::npos);
    }
    {
        // UNSAFE: T2 >= T1 (responder opens last).
        TimeoutPolicyInput in;
        in.initiator_refund_height = 100;
        in.responder_refund_height = 120;
        in.current_height = 50;
        auto r = EvaluateTimeoutOrder(in);
        bool has = false;
        for (auto& e : r.errors) if (e.find("TIMEOUT_ORDER_INVALID") != std::string::npos) has = true;
        TEST("TO2 reversed ordering rejected", !r.ok && has);
    }
    {
        // UNSAFE: gap below margin.
        TimeoutPolicyInput in;
        in.initiator_refund_height = 103;
        in.responder_refund_height = 100;
        in.current_height = 50;
        in.safety_margin_min_blocks = 6;
        auto r = EvaluateTimeoutOrder(in);
        bool has = false;
        for (auto& e : r.errors) if (e.find("TIMEOUT_MARGIN_TOO_SMALL") != std::string::npos) has = true;
        TEST("TO3 gap below margin rejected", !r.ok && has);
    }
    {
        // UNSAFE: responder deadline already passed at current tip.
        TimeoutPolicyInput in;
        in.initiator_refund_height = 200;
        in.responder_refund_height = 100;
        in.current_height = 150;   // >= T2
        in.safety_margin_min_blocks = 6;
        auto r = EvaluateTimeoutOrder(in);
        bool has = false;
        for (auto& e : r.errors) if (e.find("RESPONDER_DEADLINE_PASSED") != std::string::npos) has = true;
        TEST("TO4 responder deadline passed rejected", !r.ok && has);
    }
    {
        // WARNING (still ok): responder deadline near.
        TimeoutPolicyInput in;
        in.initiator_refund_height = 200;
        in.responder_refund_height = 100;
        in.current_height = 97;    // 3 blocks to T2 < margin 6
        in.safety_margin_min_blocks = 6;
        auto r = EvaluateTimeoutOrder(in);
        bool warned = false;
        for (auto& w : r.warnings) if (w.find("RESPONDER_DEADLINE_NEAR") != std::string::npos) warned = true;
        TEST("TO5 near-deadline warns but still ok", r.ok && warned);
    }
    {
        // Offer adapter mirrors the same verdict.
        Offer o;
        o.give = Asset::SOST; o.want = Asset::ETH;
        o.give_amount = 10; o.want_amount = 20;
        o.hashlock = b32(0xAB);
        o.initiator_refund_height = 130;
        o.responder_refund_height = 100;
        o.safety_margin_min_blocks = 6;
        auto r = EvaluateOfferTimeout(o, 50, 12);
        TEST("TO6 offer adapter safe", r.ok && r.refund_gap == 30);
    }

    // =====================================================================
    // 2. Collision-resistant swapId derivation
    // =====================================================================
    {
        auto locker = addr(1), claimer = addr(2), refunder = addr(3), token = addr(0);
        sost::Bytes32 hl = b32(0x11), nonce = b32(0x22);
        sost::Bytes32 id = DeriveSwapId(locker, claimer, refunder, token,
                                        1000000000000000000ULL, hl, 100, 1, nonce);

        // Determinism.
        sost::Bytes32 id2 = DeriveSwapId(locker, claimer, refunder, token,
                                         1000000000000000000ULL, hl, 100, 1, nonce);
        TEST("SID1 deterministic", ToHex(id) == ToHex(id2));

        // BIT-FOR-BIT parity with Solidity AtomicSwapHTLC.computeSwapId for the
        // SAME fixed vector (reference produced by the contract itself).
        const std::string SOLIDITY_REF =
            "ed55f61ec3d8cc1ff350f83b2ad3d272d1075a3dd4f2f8b2ef28cce0eb564573";
        TEST("SID2 parity with Solidity computeSwapId", ToHex(id) == SOLIDITY_REF);

        // Anti-squatting: every binding input flips the id.
        TEST("SID3a locker-bound",
             ToHex(id) != ToHex(DeriveSwapId(addr(9), claimer, refunder, token, 1000000000000000000ULL, hl, 100, 1, nonce)));
        TEST("SID3b claimer-bound",
             ToHex(id) != ToHex(DeriveSwapId(locker, addr(9), refunder, token, 1000000000000000000ULL, hl, 100, 1, nonce)));
        TEST("SID3c refunder-bound",
             ToHex(id) != ToHex(DeriveSwapId(locker, claimer, addr(9), token, 1000000000000000000ULL, hl, 100, 1, nonce)));
        TEST("SID3d token/asset-bound",
             ToHex(id) != ToHex(DeriveSwapId(locker, claimer, refunder, addr(7), 1000000000000000000ULL, hl, 100, 1, nonce)));
        TEST("SID3e amount-bound",
             ToHex(id) != ToHex(DeriveSwapId(locker, claimer, refunder, token, 999ULL, hl, 100, 1, nonce)));
        TEST("SID3f hashlock-bound",
             ToHex(id) != ToHex(DeriveSwapId(locker, claimer, refunder, token, 1000000000000000000ULL, b32(0x33), 100, 1, nonce)));
        TEST("SID3g refundTime-bound",
             ToHex(id) != ToHex(DeriveSwapId(locker, claimer, refunder, token, 1000000000000000000ULL, hl, 101, 1, nonce)));
        TEST("SID3h chainId-bound (Ethereum vs BNB)",
             ToHex(id) != ToHex(DeriveSwapId(locker, claimer, refunder, token, 1000000000000000000ULL, hl, 100, 56, nonce)));
        TEST("SID3i nonce-bound (the anti-front-run secret)",
             ToHex(id) != ToHex(DeriveSwapId(locker, claimer, refunder, token, 1000000000000000000ULL, hl, 100, 1, b32(0x44))));
    }

    // =====================================================================
    // 3. Funding / confirmation classification
    // =====================================================================
    {
        TEST("FC1 unseen", ClassifyFunding(false, false, 0, 3) == FundingStatus::Unseen);
        TEST("FC2 mempool 0-conf", ClassifyFunding(true, false, 0, 3) == FundingStatus::InMempool);
        TEST("FC3 mined but shallow", ClassifyFunding(true, true, 2, 3) == FundingStatus::Confirming);
        TEST("FC4 deep enough", ClassifyFunding(true, true, 3, 3) == FundingStatus::Confirmed);
        TEST("FC5 settled only when Confirmed",
             FundingIsSettled(FundingStatus::Confirmed) &&
             !FundingIsSettled(FundingStatus::InMempool) &&
             !FundingIsSettled(FundingStatus::Confirming));
        // min_confirmations < 1 is coerced to 1 (never accept 0-conf as settled).
        TEST("FC6 zero-min coerced (mempool still not settled)",
             ClassifyFunding(true, false, 0, 0) == FundingStatus::InMempool);
    }

    // =====================================================================
    // 4. EVM claim preimage extraction
    // =====================================================================
    {
        // Build a valid claim(bytes32,bytes32) calldata: selector + swapId + preimage.
        sost::Bytes32 preimage = b32(0xEE);
        sost::Bytes32 hl = sost::sha256(preimage.data(), preimage.size());
        sost::Bytes32 swapId = b32(0x77);
        std::vector<uint8_t> cd;
        cd.push_back(0x84); cd.push_back(0xcc); cd.push_back(0x9d); cd.push_back(0xfb);
        cd.insert(cd.end(), swapId.begin(), swapId.end());
        cd.insert(cd.end(), preimage.begin(), preimage.end());
        std::string cd_hex = "0x" + hexof(cd);

        auto e = ExtractPreimageFromEvmClaimCalldata(cd_hex, hl);
        TEST("PX1 valid calldata extracts preimage", e.ok && ToHex(e.preimage) == ToHex(preimage));

        // Wrong hashlock -> reject (guards against a bogus/attacker claim).
        auto e2 = ExtractPreimageFromEvmClaimCalldata(cd_hex, b32(0x00));
        TEST("PX2 mismatched hashlock rejected", !e2.ok);

        // Wrong selector -> reject.
        std::vector<uint8_t> bad = cd; bad[0] = 0x00;
        auto e3 = ExtractPreimageFromEvmClaimCalldata(hexof(bad), hl);
        TEST("PX3 wrong selector rejected", !e3.ok);

        // Truncated -> reject.
        auto e4 = ExtractPreimageFromEvmClaimCalldata("0x84cc9dfb1234", hl);
        TEST("PX4 truncated calldata rejected", !e4.ok);

        // Non-hex -> reject.
        auto e5 = ExtractPreimageFromEvmClaimCalldata("0xZZZZ", hl);
        TEST("PX5 non-hex rejected", !e5.ok);

        // Event data path: [preimage(32)][claimer(32)].
        std::vector<uint8_t> ev;
        ev.insert(ev.end(), preimage.begin(), preimage.end());
        for (int i = 0; i < 32; ++i) ev.push_back(i == 31 ? 0x02 : 0x00);   // claimer addr padded
        auto e6 = ExtractPreimageFromEvmClaimEventData("0x" + hexof(ev), hl);
        TEST("PX6 event-data extracts preimage", e6.ok && ToHex(e6.preimage) == ToHex(preimage));

        auto e7 = ExtractPreimageFromEvmClaimEventData("0x" + hexof(ev), b32(0x01));
        TEST("PX7 event-data mismatched hashlock rejected", !e7.ok);
    }

    // =====================================================================
    // 5. RPC-failure / recovery policy
    // =====================================================================
    {
        RpcHealthInput ok; // fresh, no failures
        TEST("RP1 healthy -> Proceed", DecideRpcRecovery(ok) == RpcRecovery::Proceed);

        RpcHealthInput transient; transient.consecutive_failures = 1;
        TEST("RP2 transient failure -> RetryBackoff",
             DecideRpcRecovery(transient) == RpcRecovery::RetryBackoff);

        RpcHealthInput many; many.consecutive_failures = 5; many.max_failures_before_halt = 5;
        TEST("RP3 too many failures -> HaltDoNotAct",
             DecideRpcRecovery(many) == RpcRecovery::HaltDoNotAct);

        RpcHealthInput staleAct;
        staleAct.seconds_since_last_success = 300; staleAct.max_stale_seconds = 120;
        staleAct.have_time_sensitive_action = true;
        TEST("RP4 stale view + time-sensitive action -> HaltDoNotAct (never act blindly)",
             DecideRpcRecovery(staleAct) == RpcRecovery::HaltDoNotAct);

        RpcHealthInput staleNoAct;
        staleNoAct.seconds_since_last_success = 300; staleNoAct.max_stale_seconds = 120;
        TEST("RP5 stale view, no pending action -> RetryBackoff",
             DecideRpcRecovery(staleNoAct) == RpcRecovery::RetryBackoff);

        RpcHealthInput oneFailAct; oneFailAct.consecutive_failures = 1;
        oneFailAct.have_time_sensitive_action = true;
        TEST("RP6 any failure + time-sensitive action -> HaltDoNotAct",
             DecideRpcRecovery(oneFailAct) == RpcRecovery::HaltDoNotAct);
    }

    // =====================================================================
    // 6. Truthful asset matrix
    // =====================================================================
    {
        // No EVM asset is over-claimed as Available (nothing audited/deployed/E2E).
        TEST("AM1 ETH testing",  EvmAssetStatusFor(Asset::ETH)  == EvmAssetStatus::Testing);
        TEST("AM2 BNB testing",  EvmAssetStatusFor(Asset::BNB)  == EvmAssetStatus::Testing);
        TEST("AM3 USDC testing (standard bool ERC-20)", EvmAssetStatusFor(Asset::USDC) == EvmAssetStatus::Testing);
        // The minimal-IERC20 + require(ok) contract REVERTS the lock for a no-bool token, so real
        // USDT is NOT supported and must not be advertised (regression guard for the over-claim fix).
        TEST("AM4 USDT disabled (no-bool token reverts at lock)",
             EvmAssetStatusFor(Asset::USDT) == EvmAssetStatus::Disabled);
        TEST("AM5 XAUT testing (standard bool ERC-20)", EvmAssetStatusFor(Asset::XAUT) == EvmAssetStatus::Testing);
        // Fee-on-transfer escrows less than nominal, so claim/refund revert → stuck. NOT supported.
        TEST("AM6 PAXG disabled (fee-on-transfer stuck-until-refund)",
             EvmAssetStatusFor(Asset::PAXG) == EvmAssetStatus::Disabled);
        TEST("AM7 BTC disabled in EVM path",
             EvmAssetStatusFor(Asset::BTC) == EvmAssetStatus::Disabled);
        bool none_available =
            EvmAssetStatusFor(Asset::ETH)  != EvmAssetStatus::Available &&
            EvmAssetStatusFor(Asset::USDT) != EvmAssetStatus::Available &&
            EvmAssetStatusFor(Asset::PAXG) != EvmAssetStatus::Available;
        TEST("AM8 nothing claimed Available (honest gate)", none_available);
        TEST("AM9 reasons non-empty",
             !EvmAssetStatusReason(Asset::USDT).empty() &&
             !EvmAssetStatusReason(Asset::PAXG).empty());
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
