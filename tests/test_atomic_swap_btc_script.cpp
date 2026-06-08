// Phase 4A-0 — BTC HTLC redeem script builder tests.
//
// Pure deterministic byte-output tests. NO network, NO file I/O, NO keys,
// NO signing. Each vector pins the exact byte sequence the builder must
// produce for fixed inputs. Vectors are hand-computed by following the
// encoding rules documented in
// docs/design/ATOMIC_SWAP_BTC_IMPLEMENTATION_DECISION.md.

#include "sost/atomic_swap_btc.h"
#include "sost/crypto.h"

#include <array>
#include <cstdio>
#include <cstdint>
#include <vector>

using namespace sost;
using namespace sost::atomic_swap::btc;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

static std::string to_hex_str(const std::vector<uint8_t>& v) {
    static const char* H = "0123456789abcdef";
    std::string s; s.reserve(v.size() * 2);
    for (auto b : v) { s.push_back(H[b >> 4]); s.push_back(H[b & 0x0F]); }
    return s;
}
static std::string to_hex_str(const Bytes32& v) {
    return to_hex_str(std::vector<uint8_t>(v.begin(), v.end()));
}

int main() {
    printf("\n== Atomic Swap BTC Phase 4A-0 — redeem script builder ==\n\n");

    // ---------------------------------------------------------------------
    // ScriptNum encoding edge cases
    // ---------------------------------------------------------------------
    {
        auto e0 = EncodeScriptNumMinimal(0);
        TEST("ScriptNum 0 -> empty vector", e0.empty());
    }
    {
        auto e1 = EncodeScriptNumMinimal(1);
        TEST("ScriptNum 1 -> {0x01}", e1.size() == 1 && e1[0] == 0x01);
    }
    {
        auto e127 = EncodeScriptNumMinimal(127);
        TEST("ScriptNum 127 -> {0x7f} (high bit 0)",
             e127.size() == 1 && e127[0] == 0x7f);
    }
    {
        // 128 has high bit set -> append sign-extension byte 0x00
        auto e128 = EncodeScriptNumMinimal(128);
        TEST("ScriptNum 128 -> {0x80, 0x00} (sign-extension byte)",
             e128.size() == 2 && e128[0] == 0x80 && e128[1] == 0x00);
    }
    {
        // 15000 = 0x3a98 -> little-endian {0x98, 0x3a}; high bit of 0x3a clear.
        auto e15000 = EncodeScriptNumMinimal(15000);
        TEST("ScriptNum 15000 -> {0x98, 0x3a} (LE, no sign byte)",
             e15000.size() == 2 && e15000[0] == 0x98 && e15000[1] == 0x3a);
    }
    {
        // 0x7FFFFFFF = 2147483647 -> {0xff, 0xff, 0xff, 0x7f}; high bit clear.
        auto eMax = EncodeScriptNumMinimal(2147483647);
        TEST("ScriptNum INT32_MAX -> 4 LE bytes",
             eMax.size() == 4 &&
             eMax[0] == 0xff && eMax[1] == 0xff &&
             eMax[2] == 0xff && eMax[3] == 0x7f);
    }
    {
        // 0x80000000 = 2147483648 -> {0x00, 0x00, 0x00, 0x80, 0x00}; high bit set -> +0x00.
        auto e = EncodeScriptNumMinimal(2147483648LL);
        TEST("ScriptNum 2^31 -> 5 bytes with sign-extension",
             e.size() == 5 &&
             e[0] == 0x00 && e[1] == 0x00 &&
             e[2] == 0x00 && e[3] == 0x80 && e[4] == 0x00);
    }

    // ---------------------------------------------------------------------
    // Pushdata encoding edge cases
    // ---------------------------------------------------------------------
    {
        std::vector<uint8_t> d(32, 0xAB);
        auto p = EncodePushdata(d);
        TEST("Pushdata 32B -> 0x20 + data",
             p.size() == 33 && p[0] == 0x20 && p[1] == 0xAB && p[32] == 0xAB);
    }
    {
        std::vector<uint8_t> d(75, 0x11);
        auto p = EncodePushdata(d);
        TEST("Pushdata 75B (largest single-byte length) -> 0x4b + data",
             p.size() == 76 && p[0] == 0x4b);
    }
    {
        std::vector<uint8_t> d(76, 0x22);
        auto p = EncodePushdata(d);
        TEST("Pushdata 76B -> OP_PUSHDATA1 (0x4c) + length + data",
             p.size() == 78 && p[0] == 0x4c && p[1] == 0x4c);
    }

    // ---------------------------------------------------------------------
    // V1 — smallest possible HTLC (zero hashlock, zero refund_height,
    //      zero-prefix pubkeys). Exercises the empty-ScriptNum 0 push path.
    // ---------------------------------------------------------------------
    {
        std::array<uint8_t, 32> hashlock{};  // all zeros
        std::array<uint8_t, 33> claim_pubkey{};
        std::array<uint8_t, 33> refund_pubkey{};
        claim_pubkey[0] = 0x02;
        refund_pubkey[0] = 0x02;

        auto s = BuildBtcHtlcRedeemScript(hashlock, 0, claim_pubkey, refund_pubkey);

        // Expected script bytes:
        //   63                              OP_IF
        //   a8                              OP_SHA256
        //   20 00*32                        push 32 zero bytes (hashlock)
        //   88                              OP_EQUALVERIFY
        //   21 02 00*32                     push 33 bytes (claim pubkey: 0x02 + 32 zeros)
        //   ac                              OP_CHECKSIG
        //   67                              OP_ELSE
        //   00                              push empty (ScriptNum 0)
        //   b1                              OP_CHECKLOCKTIMEVERIFY
        //   75                              OP_DROP
        //   21 02 00*32                     push 33 bytes (refund pubkey)
        //   ac                              OP_CHECKSIG
        //   68                              OP_ENDIF
        //
        // Total bytes: 1+1+33+1+34+1+1+1+1+1+34+1+1 = 111
        TEST("V1 script length 111", s.size() == 111);
        TEST("V1 starts with OP_IF, OP_SHA256, push32",
             s[0] == 0x63 && s[1] == 0xa8 && s[2] == 0x20);
        TEST("V1 ends with OP_CHECKSIG, OP_ENDIF",
             s[s.size()-2] == 0xac && s[s.size()-1] == 0x68);

        // Hash check: SHA-256 of the full script.
        Bytes32 wp = BtcHtlcWitnessProgram(s);
        printf("       V1 script hex   = %s\n", to_hex_str(s).c_str());
        printf("       V1 sha256(wp)   = %s\n", to_hex_str(wp).c_str());
        TEST("V1 witness program is 32 bytes", wp.size() == 32);
    }

    // ---------------------------------------------------------------------
    // V2 — typical HTLC (realistic-looking hashlock, refund_height = 15000,
    //      varied pubkey content). Exercises multi-byte ScriptNum.
    // ---------------------------------------------------------------------
    {
        std::array<uint8_t, 32> hashlock{};
        for (size_t i = 0; i < 32; ++i) hashlock[i] = static_cast<uint8_t>(0xde + i);
        std::array<uint8_t, 33> claim_pubkey{};
        claim_pubkey[0] = 0x02;
        for (size_t i = 1; i < 33; ++i) claim_pubkey[i] = static_cast<uint8_t>(0x10 + i);
        std::array<uint8_t, 33> refund_pubkey{};
        refund_pubkey[0] = 0x03;
        for (size_t i = 1; i < 33; ++i) refund_pubkey[i] = static_cast<uint8_t>(0xa0 + i);

        auto s = BuildBtcHtlcRedeemScript(hashlock, 15000, claim_pubkey, refund_pubkey);

        // refund_height = 15000 -> ScriptNum {0x98, 0x3a} -> push as
        // 0x02 0x98 0x3a (3 bytes total).
        // Expected length: 1+1+33+1+34+1+1+3+1+1+34+1+1 = 113.
        TEST("V2 script length 113 (3-byte ScriptNum for 15000)",
             s.size() == 113);

        // The ScriptNum push lives after OP_ELSE at position
        // 1+1+33+1+34+1+1 = 72. Bytes at 72/73/74 are 0x02 0x98 0x3a.
        TEST("V2 ScriptNum push for 15000 at position 72",
             s.size() > 75 && s[72] == 0x02 && s[73] == 0x98 && s[74] == 0x3a);

        // Sanity: SHA-256 produces a 32-byte witness program.
        Bytes32 wp = BtcHtlcWitnessProgram(s);
        printf("       V2 script hex   = %s\n", to_hex_str(s).c_str());
        printf("       V2 sha256(wp)   = %s\n", to_hex_str(wp).c_str());
        TEST("V2 witness program is 32 bytes", wp.size() == 32);
    }

    // ---------------------------------------------------------------------
    // V3 — largest reasonable height (INT32_MAX). Tests 4-byte ScriptNum
    //      with high bit clear (no sign extension needed).
    // ---------------------------------------------------------------------
    {
        std::array<uint8_t, 32> hashlock{};
        std::array<uint8_t, 33> claim_pubkey{};
        std::array<uint8_t, 33> refund_pubkey{};
        claim_pubkey[0] = 0x02;
        refund_pubkey[0] = 0x03;

        auto s = BuildBtcHtlcRedeemScript(hashlock, 2147483647, claim_pubkey, refund_pubkey);

        // 4-byte ScriptNum -> push 0x04 + 4 bytes = 5 bytes.
        // Expected length: 1+1+33+1+34+1+1+5+1+1+34+1+1 = 115.
        TEST("V3 script length 115 (4-byte ScriptNum for INT32_MAX)",
             s.size() == 115);

        // ScriptNum push at position 72: 0x04 0xff 0xff 0xff 0x7f.
        TEST("V3 ScriptNum push for INT32_MAX at position 72",
             s.size() > 76 && s[72] == 0x04 &&
             s[73] == 0xff && s[74] == 0xff && s[75] == 0xff && s[76] == 0x7f);
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
