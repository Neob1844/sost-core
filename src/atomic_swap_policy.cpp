// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// OTC-5 — canonical cross-chain atomic-swap policy layer (pure).
// See include/sost/atomic_swap_policy.h for the API contract and invariants.

#include "sost/atomic_swap_policy.h"
#include "sost/crypto.h"     // sost::sha256

#include <cstdio>
#include <cstring>

namespace sost {
namespace atomic_swap {
namespace policy {

// ---------------------------------------------------------------------------
// Local hex helpers (no external dep).
// ---------------------------------------------------------------------------
namespace {
constexpr char HEXD[] = "0123456789abcdef";

int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

// Strip an optional leading "0x"/"0X" and lowercase-parse hex into bytes.
// Returns false on any non-hex char or odd length.
bool parse_hex(const std::string& in, std::vector<uint8_t>& out) {
    size_t start = 0;
    if (in.size() >= 2 && in[0] == '0' && (in[1] == 'x' || in[1] == 'X')) start = 2;
    if ((in.size() - start) % 2 != 0) return false;
    out.clear();
    out.reserve((in.size() - start) / 2);
    for (size_t i = start; i < in.size(); i += 2) {
        int hi = hexval(in[i]), lo = hexval(in[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back((uint8_t)((hi << 4) | lo));
    }
    return true;
}

// Append a uint64 as a 32-byte big-endian (uint256) field.
void push_u256_be(std::vector<uint8_t>& v, uint64_t x) {
    uint8_t buf[32];
    std::memset(buf, 0, sizeof(buf));
    for (int i = 0; i < 8; ++i) buf[31 - i] = (uint8_t)((x >> (8 * i)) & 0xff);
    v.insert(v.end(), buf, buf + 32);
}

bool hashlock_matches(const Bytes32& hl, const Bytes32& preimage) {
    Bytes32 h = sost::sha256(preimage.data(), preimage.size());
    for (int i = 0; i < 32; ++i) if (h[i] != hl[i]) return false;
    return true;
}

// Format a block-delta as an approximate human duration.
std::string humanize_eta(int64_t blocks_ahead, int64_t seconds_per_block) {
    if (seconds_per_block <= 0) return "";
    if (blocks_ahead <= 0) return " (already open)";
    int64_t secs = blocks_ahead * seconds_per_block;
    char buf[64];
    if (secs < 90) { std::snprintf(buf, sizeof(buf), " (~%llds from now)", (long long)secs); }
    else if (secs < 5400) { std::snprintf(buf, sizeof(buf), " (~%lldm from now)", (long long)(secs / 60)); }
    else if (secs < 172800) { std::snprintf(buf, sizeof(buf), " (~%.1fh from now)", secs / 3600.0); }
    else { std::snprintf(buf, sizeof(buf), " (~%.1fd from now)", secs / 86400.0); }
    return std::string(buf);
}
}  // namespace

std::string ToHex(const Bytes32& b) {
    std::string s; s.reserve(64);
    for (uint8_t x : b) { s.push_back(HEXD[x >> 4]); s.push_back(HEXD[x & 0xf]); }
    return s;
}

// ---------------------------------------------------------------------------
// 1. Canonical timeout-ordering policy
// ---------------------------------------------------------------------------
TimeoutPolicyResult EvaluateTimeoutOrder(const TimeoutPolicyInput& in) {
    TimeoutPolicyResult r;
    const int64_t T1 = in.initiator_refund_height;
    const int64_t T2 = in.responder_refund_height;
    r.refund_gap = T1 - T2;

    if (T1 <= 0 || T2 <= 0) {
        r.errors.push_back("both refund heights must be > 0 (T1=" +
                           std::to_string(T1) + ", T2=" + std::to_string(T2) + ")");
    }
    if (in.safety_margin_min_blocks < 0) {
        r.errors.push_back("safety_margin_min_blocks must be >= 0");
    }

    // Core ordering rule: responder (T2) opens FIRST, initiator (T1) LAST.
    if (T1 > 0 && T2 > 0) {
        if (T2 >= T1) {
            r.errors.push_back(
                "TIMEOUT_ORDER_INVALID: responder_refund_height (" + std::to_string(T2) +
                ") must be < initiator_refund_height (" + std::to_string(T1) +
                ") — the responder's refund must open first");
        } else if (r.refund_gap < in.safety_margin_min_blocks) {
            r.errors.push_back(
                "TIMEOUT_MARGIN_TOO_SMALL: refund gap " + std::to_string(r.refund_gap) +
                " < safety_margin_min_blocks " + std::to_string(in.safety_margin_min_blocks));
        }
    }

    // Future-relative caution: if the responder window has already opened at
    // the current tip, entering the swap is unsafe (the margin is gone).
    if (in.current_height > 0 && T2 > 0 && in.current_height >= T2) {
        r.errors.push_back(
            "RESPONDER_DEADLINE_PASSED: current height " + std::to_string(in.current_height) +
            " >= responder_refund_height " + std::to_string(T2) +
            " — the safety margin is already gone; do NOT lock");
    } else if (in.current_height > 0 && T2 > 0 &&
               (T2 - in.current_height) < in.safety_margin_min_blocks) {
        r.warnings.push_back(
            "RESPONDER_DEADLINE_NEAR: only " + std::to_string(T2 - in.current_height) +
            " blocks until the responder refund window opens");
    }

    // Human-readable deadline lines (always populated).
    r.responder_deadline_human =
        "Responder refund opens at height " + std::to_string(T2) +
        humanize_eta(in.current_height > 0 ? T2 - in.current_height : 0, in.seconds_per_block);
    r.initiator_deadline_human =
        "Initiator/SOST refund opens at height " + std::to_string(T1) +
        humanize_eta(in.current_height > 0 ? T1 - in.current_height : 0, in.seconds_per_block);

    r.ok = r.errors.empty();
    r.summary_human = r.ok
        ? ("SAFE: T2(" + std::to_string(T2) + ") < T1(" + std::to_string(T1) +
           "), gap " + std::to_string(r.refund_gap) + " >= margin " +
           std::to_string(in.safety_margin_min_blocks))
        : ("UNSAFE: " + r.errors.front());
    return r;
}

TimeoutPolicyResult EvaluateOfferTimeout(const Offer& o, int64_t current_height,
                                         int64_t seconds_per_block) {
    TimeoutPolicyInput in;
    in.initiator_refund_height = o.initiator_refund_height;
    in.responder_refund_height = o.responder_refund_height;
    in.current_height          = current_height;
    in.safety_margin_min_blocks = o.safety_margin_min_blocks;
    in.seconds_per_block       = seconds_per_block;
    return EvaluateTimeoutOrder(in);
}

// ---------------------------------------------------------------------------
// 2. Collision-resistant swapId derivation
// ---------------------------------------------------------------------------
Bytes32 DeriveSwapId(
    const std::array<uint8_t, 20>& locker,
    const std::array<uint8_t, 20>& claimer,
    const std::array<uint8_t, 20>& refunder,
    const std::array<uint8_t, 20>& token,
    uint64_t amount,
    const Bytes32& hashlock,
    uint64_t refund_time,
    uint64_t chain_id,
    const Bytes32& nonce) {
    // Exactly mirror AtomicSwapHTLC.computeSwapId's abi.encodePacked layout.
    static const char DOMAIN[] = "SOST-ATOMIC-SWAP-ID-v1";  // 22 bytes, no NUL
    std::vector<uint8_t> buf;
    buf.reserve(22 + 20 * 4 + 32 * 5);
    buf.insert(buf.end(), DOMAIN, DOMAIN + 22);
    buf.insert(buf.end(), locker.begin(), locker.end());
    buf.insert(buf.end(), claimer.begin(), claimer.end());
    buf.insert(buf.end(), refunder.begin(), refunder.end());
    buf.insert(buf.end(), token.begin(), token.end());
    push_u256_be(buf, amount);
    buf.insert(buf.end(), hashlock.begin(), hashlock.end());
    push_u256_be(buf, refund_time);
    push_u256_be(buf, chain_id);
    buf.insert(buf.end(), nonce.begin(), nonce.end());
    return sost::sha256(buf.data(), buf.size());
}

// ---------------------------------------------------------------------------
// 3. Funding / confirmation classification
// ---------------------------------------------------------------------------
const char* FundingStatusName(FundingStatus s) {
    switch (s) {
        case FundingStatus::Unseen:     return "Unseen";
        case FundingStatus::InMempool:  return "InMempool";
        case FundingStatus::Confirming: return "Confirming";
        case FundingStatus::Confirmed:  return "Confirmed";
    }
    return "Unseen";
}

FundingStatus ClassifyFunding(bool seen_in_mempool,
                              bool included_in_block,
                              int64_t current_confirmations,
                              int64_t min_confirmations) {
    if (min_confirmations < 1) min_confirmations = 1;
    if (included_in_block) {
        if (current_confirmations >= min_confirmations) return FundingStatus::Confirmed;
        return FundingStatus::Confirming;
    }
    if (seen_in_mempool) return FundingStatus::InMempool;
    return FundingStatus::Unseen;
}

bool FundingIsSettled(FundingStatus s) { return s == FundingStatus::Confirmed; }

// ---------------------------------------------------------------------------
// 4. Preimage extraction from an EVM claim
// ---------------------------------------------------------------------------
namespace {
PreimageExtraction fail_extract(const std::string& msg) {
    PreimageExtraction e; e.ok = false; e.error = msg; return e;
}
PreimageExtraction finish_extract(const std::vector<uint8_t>& bytes, size_t offset,
                                  const Bytes32& expected_hashlock) {
    if (offset + 32 > bytes.size()) return fail_extract("input too short for a 32-byte preimage");
    Bytes32 pre{};
    for (int i = 0; i < 32; ++i) pre[i] = bytes[offset + i];
    if (!hashlock_matches(expected_hashlock, pre))
        return fail_extract("extracted preimage does not match expected hashlock (sha256 mismatch)");
    PreimageExtraction ok; ok.ok = true; ok.preimage = pre; return ok;
}
// claim(bytes32,bytes32) selector.
constexpr uint8_t CLAIM_SELECTOR[4] = {0x84, 0xcc, 0x9d, 0xfb};
}  // namespace

PreimageExtraction ExtractPreimageFromEvmClaimCalldata(
    const std::string& calldata_hex, const Bytes32& expected_hashlock) {
    std::vector<uint8_t> b;
    if (!parse_hex(calldata_hex, b)) return fail_extract("calldata is not valid hex");
    // [selector(4)][swapId(32)][preimage(32)] = 68 bytes.
    if (b.size() != 68) return fail_extract("claim calldata must be exactly 68 bytes (got " +
                                            std::to_string(b.size()) + ")");
    for (int i = 0; i < 4; ++i)
        if (b[i] != CLAIM_SELECTOR[i]) return fail_extract("selector is not claim(bytes32,bytes32) 0x84cc9dfb");
    return finish_extract(b, 4 + 32, expected_hashlock);   // preimage is the 2nd arg
}

PreimageExtraction ExtractPreimageFromEvmClaimEventData(
    const std::string& event_data_hex, const Bytes32& expected_hashlock) {
    std::vector<uint8_t> b;
    if (!parse_hex(event_data_hex, b)) return fail_extract("event data is not valid hex");
    // Claimed(bytes32 indexed swapId, bytes32 preimage, address claimer):
    // non-indexed data = [preimage(32)][claimer(32, left-padded)] = 64 bytes.
    if (b.size() < 32) return fail_extract("event data too short for a 32-byte preimage");
    return finish_extract(b, 0, expected_hashlock);        // preimage is first
}

// ---------------------------------------------------------------------------
// 5. RPC-failure / recovery policy
// ---------------------------------------------------------------------------
const char* RpcRecoveryName(RpcRecovery r) {
    switch (r) {
        case RpcRecovery::Proceed:      return "Proceed";
        case RpcRecovery::RetryBackoff: return "RetryBackoff";
        case RpcRecovery::HaltDoNotAct: return "HaltDoNotAct";
    }
    return "HaltDoNotAct";
}

RpcRecovery DecideRpcRecovery(const RpcHealthInput& in) {
    const bool stale = in.max_stale_seconds > 0 &&
                       in.seconds_since_last_success > in.max_stale_seconds;

    // A time-sensitive action off a stale/unavailable view is the dangerous
    // case: NEVER act blindly. Halt and surface to the operator.
    if (in.have_time_sensitive_action && (stale || in.consecutive_failures > 0)) {
        return RpcRecovery::HaltDoNotAct;
    }
    // Too many failures — stop retrying blindly, escalate.
    if (in.consecutive_failures >= in.max_failures_before_halt) {
        return RpcRecovery::HaltDoNotAct;
    }
    // A stale view with no pending action is not immediately dangerous, but we
    // still must not treat it as fresh — back off and refresh.
    if (stale || in.consecutive_failures > 0) {
        return RpcRecovery::RetryBackoff;
    }
    return RpcRecovery::Proceed;
}

// ---------------------------------------------------------------------------
// 6. Truthful per-asset EVM support matrix
// ---------------------------------------------------------------------------
//
// Ground truth as of HEAD (verified against contracts/atomic-swap/src/AtomicSwapHTLC.sol
// + its Foundry suite — the code, NOT an older summary):
//   - The AtomicSwapHTLC contract uses a MINIMAL IERC20 interface with `require(ok)` on the
//     boolean return (AtomicSwapHTLC.sol ~53, ~194, ~229). It does NOT use OpenZeppelin
//     SafeERC20 and does NOT do balance-delta accounting. Therefore:
//       * native ETH/BNB and standard bool-returning ERC-20 (USDC, XAUT) work → Testing;
//       * a NO-BOOL token (real USDT) makes `bool ok = transferFrom(...)` revert on the empty
//         return-data ABI-decode → the LOCK itself reverts (Foundry
//         test_lockERC20_rejectsNoReturnERC20) → NOT supported → Disabled;
//       * a FEE-ON-TRANSFER token (PAXG) LOCKS with the nominal amount but the contract only
//         holds amount-fee, so the CLAIM/REFUND transfer of the nominal amount reverts →
//         funds stuck until refund (Foundry
//         test_lockERC20_feeOnTransferTokenIsUnsupported_lockSucceedsClaimFails) → Disabled.
//   - Nothing is externally audited, deployed to a live network, or E2E-verified on-chain, so
//     the HONEST ceiling for the SUPPORTED legs is Testing (never Available). The contract
//     FAILS CLOSED on the unsupported tokens (no theft), but they must NOT be advertised.
const char* EvmAssetStatusName(EvmAssetStatus s) {
    switch (s) {
        case EvmAssetStatus::Disabled:  return "DISABLED";
        case EvmAssetStatus::Testing:   return "TESTING";
        case EvmAssetStatus::Available: return "AVAILABLE";
    }
    return "DISABLED";
}

EvmAssetStatus EvmAssetStatusFor(Asset a) {
    switch (a) {
        case Asset::SOST:
            // SOST is the native consensus leg, not an EVM asset. Report
            // Testing to reflect the swap-as-a-whole gate (V14.5 founder-only).
            return EvmAssetStatus::Testing;
        case Asset::ETH:
        case Asset::BNB:
            // Native path: mechanically complete + unit-tested; not deployed/E2E.
            return EvmAssetStatus::Testing;
        case Asset::USDC:
        case Asset::XAUT:
            // Standard bool-returning ERC-20 via the minimal IERC20 + require(ok) path;
            // mechanically works, unaudited/undeployed → Testing.
            return EvmAssetStatus::Testing;
        case Asset::USDT:
            // No-bool-return token: the LOCK reverts (require(ok) on empty return-data).
            // The contract does NOT tolerate it. NOT supported.
            return EvmAssetStatus::Disabled;
        case Asset::PAXG:
            // Fee-on-transfer token: LOCK succeeds with the nominal amount but the contract
            // holds less, so CLAIM/REFUND revert → funds stuck. NOT safely supported.
            return EvmAssetStatus::Disabled;
        case Asset::BTC:
            // BTC is NOT the EVM workstream — BTC HTLC signing stays OFF.
            return EvmAssetStatus::Disabled;
    }
    return EvmAssetStatus::Disabled;
}

std::string EvmAssetStatusReason(Asset a) {
    switch (a) {
        case Asset::SOST:
            return "SOST is the native consensus leg (HTLC gated at V14.5, founder-only); "
                   "not an EVM-side asset.";
        case Asset::ETH:
            return "Native ETH via lockNative/claim/refund. Mechanically complete and "
                   "unit-tested; NOT audited, deployed, or E2E-verified on-chain.";
        case Asset::BNB:
            return "Native BNB (same contract on BNB Chain). Mechanically complete and "
                   "unit-tested; NOT audited, deployed, or E2E-verified on-chain.";
        case Asset::USDC:
            return "Standard bool-returning ERC-20 via the minimal IERC20 + require(ok) path. "
                   "Unaudited/undeployed. ISSUER_FREEZE_RISK: Circle can freeze escrowed funds.";
        case Asset::USDT:
            return "NOT SUPPORTED by the current contract: real USDT does not return a bool, so "
                   "`require(ok)` reverts on the empty return-data — the LOCK itself reverts "
                   "(Foundry test_lockERC20_rejectsNoReturnERC20). Do not offer until the contract "
                   "adopts a SafeERC20-style no-bool-tolerant path.";
        case Asset::XAUT:
            return "Standard bool-returning ERC-20 gold token via the minimal IERC20 + require(ok) "
                   "path. Unaudited/undeployed. ISSUER_FREEZE_RISK: TG Commodities can freeze funds.";
        case Asset::PAXG:
            return "NOT SUPPORTED by the current contract: fee-on-transfer means the LOCK escrows "
                   "less than the nominal amount, so the CLAIM/REFUND transfer of the nominal amount "
                   "reverts and funds are stuck until refund (Foundry "
                   "test_lockERC20_feeOnTransferTokenIsUnsupported_lockSucceedsClaimFails). Do not "
                   "offer until the contract adopts balance-delta accounting.";
        case Asset::BTC:
            return "BTC HTLC signing is a separate workstream and stays OFF in the EVM path.";
    }
    return "unknown asset";
}

}  // namespace policy
}  // namespace atomic_swap
}  // namespace sost
