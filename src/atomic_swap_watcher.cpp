// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// Atomic Swap — local non-custodial watcher / auto-pilot (OTC-2). Pure,
// non-custodial, non-consensus. See include/sost/atomic_swap_watcher.h.

#include "sost/atomic_swap_watcher.h"
#include "sost/crypto.h"   // sha256 for preimage verification
#include <sstream>

namespace sost {
namespace atomic_swap {

const char* WatchSideName(WatchSide s) {
    return s == WatchSide::Claimant ? "claimant" : "refunder";
}

const char* WatchActionName(WatchAction a) {
    switch (a) {
        case WatchAction::Wait:   return "wait";
        case WatchAction::Claim:  return "claim";
        case WatchAction::Refund: return "refund";
        case WatchAction::Done:   return "done";
    }
    return "?";
}

WatchAction DecideWatchAction(const WatchedSwap& s,
                              int64_t current_sost_height,
                              bool lock_unspent) {
    // The LOCK is gone or already spent → nothing left to watch.
    if (s.sost_spent || !lock_unspent) return WatchAction::Done;

    if (s.side == WatchSide::Claimant) {
        // We can claim only while the preimage is known AND we are strictly
        // before the refund window opens (R22). After that the claim window is
        // closed; the refunder will recover, so we just wait/stop.
        if (s.have_preimage && current_sost_height < s.sost_refund_height)
            return WatchAction::Claim;
        return WatchAction::Wait;
    }

    // Refunder: recover our own lock once the refund window has opened (R24).
    if (current_sost_height >= s.sost_refund_height)
        return WatchAction::Refund;
    return WatchAction::Wait;
}

bool IngestRevealedPreimage(WatchedSwap& s, const std::array<uint8_t, 32>& preimage) {
    Bytes32 computed = sha256(preimage.data(), preimage.size());
    for (int i = 0; i < 32; ++i)
        if (computed[i] != s.hashlock[i]) return false;  // does not unlock this swap
    s.preimage = preimage;
    s.have_preimage = true;
    return true;
}

// -----------------------------------------------------------------------------
// Hex helpers (lowercase, no reversal) for deterministic persistence.
// -----------------------------------------------------------------------------
namespace {
std::string ToHex(const uint8_t* d, size_t n) {
    static const char* H = "0123456789abcdef";
    std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s.push_back(H[d[i] >> 4]); s.push_back(H[d[i] & 0xF]); }
    return s;
}
template <size_t N>
std::string ToHex(const std::array<uint8_t, N>& a) { return ToHex(a.data(), N); }

int HexNibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
template <size_t N>
bool FromHex(const std::string& s, std::array<uint8_t, N>& out) {
    if (s.size() != N * 2) return false;
    for (size_t i = 0; i < N; ++i) {
        int hi = HexNibble(s[2 * i]), lo = HexNibble(s[2 * i + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return true;
}
}  // namespace

std::string SerializeWatchedSwap(const WatchedSwap& s) {
    // Pipe-delimited, fixed field order. swap_id must not contain '|' or '\n'.
    std::ostringstream o;
    o << s.swap_id << '|'
      << WatchSideName(s.side) << '|'
      << ToHex(s.sost_lock_txid) << '|'
      << s.sost_lock_vout << '|'
      << ToHex(s.hashlock) << '|'
      << s.sost_refund_height << '|'
      << ToHex(s.claim_pkh) << '|'
      << ToHex(s.refund_pkh) << '|'
      << (s.have_preimage ? 1 : 0) << '|'
      << ToHex(s.preimage) << '|'
      << (s.sost_spent ? 1 : 0);
    return o.str();
}

bool ParseWatchedSwap(const std::string& line, WatchedSwap& out) {
    std::vector<std::string> f;
    std::string cur;
    for (char c : line) {
        if (c == '|') { f.push_back(cur); cur.clear(); }
        else cur.push_back(c);
    }
    f.push_back(cur);
    if (f.size() != 11) return false;

    WatchedSwap s;
    s.swap_id = f[0];
    if (s.swap_id.empty() || s.swap_id.find('\n') != std::string::npos) return false;
    if (f[1] == "claimant") s.side = WatchSide::Claimant;
    else if (f[1] == "refunder") s.side = WatchSide::Refunder;
    else return false;
    if (!FromHex(f[2], s.sost_lock_txid)) return false;
    try { s.sost_lock_vout = static_cast<uint32_t>(std::stoul(f[3])); }
    catch (...) { return false; }
    if (!FromHex(f[4], s.hashlock)) return false;
    try { s.sost_refund_height = std::stoll(f[5]); }
    catch (...) { return false; }
    if (!FromHex(f[6], s.claim_pkh)) return false;
    if (!FromHex(f[7], s.refund_pkh)) return false;
    if (f[8] != "0" && f[8] != "1") return false;
    s.have_preimage = (f[8] == "1");
    if (!FromHex(f[9], s.preimage)) return false;
    if (f[10] != "0" && f[10] != "1") return false;
    s.sost_spent = (f[10] == "1");

    out = s;
    return true;
}

std::string SerializeWatchlist(const std::vector<WatchedSwap>& v) {
    std::string out;
    for (const auto& s : v) { out += SerializeWatchedSwap(s); out.push_back('\n'); }
    return out;
}

bool ParseWatchlist(const std::string& text, std::vector<WatchedSwap>& out) {
    out.clear();
    std::istringstream in(text);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        WatchedSwap s;
        if (!ParseWatchedSwap(line, s)) return false;
        out.push_back(s);
    }
    return true;
}

}  // namespace atomic_swap
}  // namespace sost
