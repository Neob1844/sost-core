// test_gv_slice1_activation.cpp — V14 Gold Vault Phase I, Slice 1 (B1) config.
//
// Verifies the ACTIVE configuration (independent of the mainnet/testnet gate
// height): the whitelist holds exactly the genesis/founder miner, the dual
// whitelist agrees, the absolute per-spend cap is 1,000 SOST, and the bytes
// hardcoded in gold_vault_slice1.{h,cpp} match the canonical address decode of
// ADDR_MINER_FOUNDER (catches any byte typo in the whitelist).
#include "sost/gold_vault_slice1.h"
#include "sost/consensus_constants.h"
#include "sost/params.h"
#include "sost/address.h"
#include "sost/tx_signer.h"   // PubKeyHash
#include <cstdio>

using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(name,cond) do{ if(cond){++g_pass; std::printf("  ok  %s\n",name);} \
  else{++g_fail; std::printf("  *** FAIL: %s\n",name);} }while(0)

int main() {
    std::printf("=== Gold Vault Slice 1 (B1) configuration ===\n");

    // Canonical genesis/founder miner pkh from the published constitutional address.
    PubKeyHash founder{};
    bool dec = address_decode(ADDR_MINER_FOUNDER, founder);
    CHECK("address_decode(ADDR_MINER_FOUNDER) succeeds", dec);

    // The hardcoded whitelist (header copy) MUST equal the decoded address.
    CHECK("whitelist[0] == decode(ADDR_MINER_FOUNDER) (no byte typo)",
          GV_SLICE1_WHITELIST_PRIMARY_LEN == 1 &&
          GV_SLICE1_WHITELIST_PRIMARY[0] == founder);

    // G2: primary and mirror whitelists agree (header vs separate .cpp copy).
    CHECK("gv_slice1_whitelists_agree() == true", gv_slice1_whitelists_agree());

    // G1: the genesis miner is allowed; anyone else is not.
    CHECK("destination_allowed(founder) == true",
          gv_slice1_destination_allowed(founder) == true);
    PubKeyHash other{}; for (auto& b : other) b = 0x7e;
    CHECK("destination_allowed(other) == false",
          gv_slice1_destination_allowed(other) == false);

    // G3a absolute cap = 1,000 SOST.
    const int64_t cap = 1000 * STOCKS_PER_SOST;
    CHECK("abs cap constant == 1,000 SOST",
          GV_SLICE1_PER_SPEND_CAP_STOCKS == cap);
    CHECK("amount == cap allowed",      gv_slice1_amount_within_abs_cap(cap) == true);
    CHECK("amount == cap-1 allowed",    gv_slice1_amount_within_abs_cap(cap-1) == true);
    CHECK("amount == cap+1 rejected",   gv_slice1_amount_within_abs_cap(cap+1) == false);
    CHECK("negative amount rejected",   gv_slice1_amount_within_abs_cap(-1) == false);

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0 ? 0 : 1;
}
