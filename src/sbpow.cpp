// sbpow.cpp — V11 Phase 2 component C: Signature-bound Proof of Work
//
// Spec: docs/V11_SPEC.md §3
// Status: SKELETON — every entry point returns a sentinel and is gated
// behind a static_assert-style runtime guard so any accidental call
// from production code fails loudly during integration.
//
// Real implementation lands together with the activation of
// V11_PHASE2_HEIGHT, after gates G3.1-G3.4 in V11_SPEC.md §6.
#include "sost/sbpow.h"

#include <cstdio>
#include <cstdlib>

namespace sost::sbpow {

namespace {
[[noreturn]] void phase2_not_implemented(const char* fn) {
    std::fprintf(stderr,
        "FATAL: sost::sbpow::%s called before V11 Phase 2 implementation. "
        "This is a skeleton — wire the real code before activating "
        "V11_PHASE2_HEIGHT.\n", fn);
    std::abort();
}
} // namespace

Bytes32 derive_seed_v11(
    const uint8_t* /*header_core*/, size_t /*header_core_len*/,
    const Bytes32& /*block_key*/,
    uint32_t /*nonce*/, uint32_t /*extra_nonce*/,
    const MinerPubkey& /*miner_pubkey*/)
{
    phase2_not_implemented("derive_seed_v11");
}

Bytes32 build_sig_message(const Bytes32& /*commit*/, int64_t /*height*/) {
    phase2_not_implemented("build_sig_message");
}

bool sign(const std::array<uint8_t, 32>& /*privkey*/,
          const Bytes32& /*sig_message*/,
          MinerSignature& /*out*/)
{
    phase2_not_implemented("sign");
}

bool verify(const MinerPubkey& /*pubkey*/,
            const Bytes32& /*sig_message*/,
            const MinerSignature& /*signature*/)
{
    phase2_not_implemented("verify");
}

bool validate(const HeaderV2Ext& /*ext*/, const ValidationContext& /*ctx*/) {
    phase2_not_implemented("validate");
}

} // namespace sost::sbpow
