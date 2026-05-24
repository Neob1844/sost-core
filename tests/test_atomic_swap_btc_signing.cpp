// Phase 4A-1 — BTC signing backend disabled-stub tests.
//
// Verifies that with SOST_BTC_HTLC_SIGNING=OFF (default) the entire
// signing surface is inert: every function returns the disabled
// result, no transactions are produced, no addresses are derived, no
// private keys are touched. This is the safety guarantee while the
// real signing backend (vendored audited Bitcoin library) is not yet
// integrated.

#include "sost/atomic_swap_btc_signing.h"
#include "sost/atomic_swap.h"

#include <array>
#include <cstdio>
#include <cstdint>
#include <climits>
#include <string>

using namespace sost;
using namespace sost::atomic_swap::btc;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

int main() {
    printf("\n== Atomic Swap BTC Signing Phase 4A-1 — disabled-stub tests ==\n\n");
    printf("  IsBtcHtlcSigningEnabled() = %s\n",
           IsBtcHtlcSigningEnabled() ? "true" : "false");
    printf("  ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = %lld (must be INT64_MAX)\n\n",
           (long long)ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT);

    // T1. The build flag is OFF by default.
    TEST("T1 IsBtcHtlcSigningEnabled() returns false (default OFF)",
         IsBtcHtlcSigningEnabled() == false);

    // T2. The activation gate is independent and stays INT64_MAX. The
    //     two flags are not coupled — even if a future build flips the
    //     signing flag, the SOST consensus gate stays closed until the
    //     re-flip checklist is met.
    TEST("T2 SOST activation gate stays INT64_MAX",
         ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT == INT64_MAX);

    // -----------------------------------------------------------------
    // Stub behavior — every gated function returns disabled result.
    // -----------------------------------------------------------------

    Bytes32 fake_txid{};
    fake_txid.fill(0xAB);
    std::array<uint8_t, 32> fake_preimage{};
    std::array<uint8_t, 32> fake_privkey{};   // deliberately zero — never read
    std::vector<uint8_t> fake_redeem_script(113, 0x63);  // arbitrary bytes
    std::string addr = "bc1qworlds_smallest_address";
    std::string network = "testnet";

    // T3. SignBtcHtlcClaim
    {
        auto r = SignBtcHtlcClaim(
            fake_txid, 0, 100000,
            fake_redeem_script, fake_preimage, fake_privkey,
            addr, 1000, network);
        TEST("T3 SignBtcHtlcClaim returns ok=false",  r.ok == false);
        TEST("T3 SignBtcHtlcClaim error mentions 'disabled'",
             r.error.find("disabled") != std::string::npos);
        TEST("T3 SignBtcHtlcClaim raw_tx_hex empty",  r.raw_tx_hex.empty());
    }

    // T4. SignBtcHtlcRefund
    {
        auto r = SignBtcHtlcRefund(
            fake_txid, 0, 100000,
            fake_redeem_script, 15000, fake_privkey,
            addr, 1000, network);
        TEST("T4 SignBtcHtlcRefund returns ok=false", r.ok == false);
        TEST("T4 SignBtcHtlcRefund error mentions 'disabled'",
             r.error.find("disabled") != std::string::npos);
        TEST("T4 SignBtcHtlcRefund raw_tx_hex empty", r.raw_tx_hex.empty());
    }

    // T5. SignBtcHtlcLockFunding
    {
        auto r = SignBtcHtlcLockFunding(
            fake_txid, 0, 200000, fake_privkey, addr,
            fake_redeem_script, 100000, 1000, network);
        TEST("T5 SignBtcHtlcLockFunding returns ok=false", r.ok == false);
        TEST("T5 SignBtcHtlcLockFunding error mentions 'disabled'",
             r.error.find("disabled") != std::string::npos);
        TEST("T5 SignBtcHtlcLockFunding raw_tx_hex empty", r.raw_tx_hex.empty());
    }

    // T6. EncodeP2WSHAddress
    {
        std::array<uint8_t, 32> witness_program{};
        for (size_t i = 0; i < 32; ++i) witness_program[i] = static_cast<uint8_t>(i);
        auto r = EncodeP2WSHAddress(witness_program, network);
        TEST("T6 EncodeP2WSHAddress returns ok=false", r.ok == false);
        TEST("T6 EncodeP2WSHAddress error mentions 'disabled'",
             r.error.find("disabled") != std::string::npos);
        TEST("T6 EncodeP2WSHAddress address empty",   r.address.empty());
    }

    // -----------------------------------------------------------------
    // T7. Error message references the STOP REPORT doc — so a caller
    //     who hits the disabled error knows exactly where to read for
    //     the integration plan.
    // -----------------------------------------------------------------
    {
        auto r = SignBtcHtlcClaim(
            fake_txid, 0, 100000,
            fake_redeem_script, fake_preimage, fake_privkey,
            addr, 1000, network);
        TEST("T7 error references STOP REPORT doc path",
             r.error.find("ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md") != std::string::npos);
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
