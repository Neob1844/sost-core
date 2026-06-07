// test_gv_slice1_block_enforcement.cpp — V14 W1.
//
// Exercises the SHARED composite Slice 1 block-spend check
// (gv_slice1_check_block_spend) that is wired into BOTH the real node path
// (process_block, src/sost-node.cpp) and the orphan
// ValidateBlockTransactionsConsensus (src/block_validation.cpp). This is the
// logic W1 puts on the node's real block path; testing it here proves the
// six required scenarios without needing the static process_block.
//
// The whitelist is configured by B1 (single genesis-miner destination), the
// relative cap is sentinel-disabled (BPS == 0) and the absolute cap is
// 1,000 SOST. gv_slice1_check_block_spend does NOT look at height — callers
// gate it on gv_slice1_active_at() — so it is testable on the mainnet build.
#include "sost/gold_vault_slice1.h"
#include "sost/transaction.h"
#include <cstdio>
#include <array>
using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(name, cond) do { if (cond) { ++g_pass; std::printf("  ok  %s\n", name); } \
    else { ++g_fail; std::printf("  *** FAIL: %s\n", name); } } while (0)

// A vault input always resolves to the gold-vault pkh; a non-vault input to
// something else. The composite check only cares about the resolved pkh.
int main() {
    std::printf("=== Gold Vault Slice 1 — composite block-spend check (W1) ===\n");

    // B1 prerequisites
    CHECK("whitelist primary len == 1", GV_SLICE1_WHITELIST_PRIMARY_LEN == 1);
    CHECK("primary/mirror whitelists agree", gv_slice1_whitelists_agree());

    // Distinct pkhs derived from the (real) whitelisted destination so we never
    // accidentally collide with it.
    const PubKeyHash wl   = GV_SLICE1_WHITELIST_PRIMARY[0];   // whitelisted dest
    PubKeyHash gold = wl;  gold[0] = (Byte)(gold[0] ^ 0xFF);  // gold-vault pkh (!= wl)
    PubKeyHash bad  = wl;  bad[1]  = (Byte)(bad[1]  ^ 0xFF);  // non-whitelisted (!= wl, != gold)
    CHECK("gold != whitelisted dest", gold != wl);
    CHECK("bad  != whitelisted dest", bad  != wl);
    CHECK("gold != bad",              gold != bad);

    Hash256 vtxid{}; for (auto& b : vtxid) b = 0x11;
    auto lookupVault = [&](const Hash256&, uint32_t, PubKeyHash& out) { out = gold; return true; };
    auto lookupOther = [&](const Hash256&, uint32_t, PubKeyHash& out) { out = bad;  return true; };

    auto oneInOneOut = [&](const PubKeyHash& dest, int64_t amt) {
        Transaction t;
        TxInput in; in.prev_txid = vtxid; in.prev_index = 0; t.inputs.push_back(in);
        TxOutput o; o.amount = amt; o.pubkey_hash = dest; t.outputs.push_back(o);
        return t;
    };

    const int64_t CAP = GV_SLICE1_PER_SPEND_CAP_STOCKS;   // 1,000 SOST absolute cap

    // 1) A normal, non-vault tx is completely unconstrained.
    {
        auto t = oneInOneOut(bad, 999);
        CHECK("non-vault spend -> NotAVaultSpend (unaffected)",
              gv_slice1_check_block_spend(t, gold, lookupOther, 0) == GvSlice1Verdict::NotAVaultSpend);
    }

    // 2) Vault spend to a whitelisted destination, within the cap -> Ok.
    {
        auto t = oneInOneOut(wl, CAP - 1);
        CHECK("vault -> whitelist, within abs cap -> Ok",
              gv_slice1_check_block_spend(t, gold, lookupVault, SUPPLY_MAX_STOCKS) == GvSlice1Verdict::Ok);
    }

    // 3) Vault spend to a NON-whitelisted destination -> rejected (G1).
    {
        auto t = oneInOneOut(bad, 100);
        CHECK("vault -> non-whitelist -> DestNotAllowed",
              gv_slice1_check_block_spend(t, gold, lookupVault, SUPPLY_MAX_STOCKS) == GvSlice1Verdict::DestNotAllowed);
    }

    // 4) Exactly the 1,000-SOST absolute cap -> Ok (boundary).
    {
        auto t = oneInOneOut(wl, CAP);
        CHECK("vault -> whitelist, == abs cap (1000 SOST) -> Ok",
              gv_slice1_check_block_spend(t, gold, lookupVault, SUPPLY_MAX_STOCKS) == GvSlice1Verdict::Ok);
    }

    // 5) 1,000 SOST + 1 stock -> rejected by the absolute cap (G3a).
    {
        auto t = oneInOneOut(wl, CAP + 1);
        CHECK("vault -> whitelist, abs cap + 1 stock -> OverAbsCap",
              gv_slice1_check_block_spend(t, gold, lookupVault, SUPPLY_MAX_STOCKS) == GvSlice1Verdict::OverAbsCap);
    }

    // 6) Change back to the vault is treated as change; whitelisted external
    //    within the cap -> Ok.
    {
        Transaction t;
        TxInput in; in.prev_txid = vtxid; in.prev_index = 0; t.inputs.push_back(in);
        TxOutput chg; chg.amount = 500; chg.pubkey_hash = gold; t.outputs.push_back(chg); // change to vault
        TxOutput o;   o.amount   = CAP; o.pubkey_hash   = wl;   t.outputs.push_back(o);   // external, whitelisted
        CHECK("change-to-vault + whitelisted external within cap -> Ok",
              gv_slice1_check_block_spend(t, gold, lookupVault, SUPPLY_MAX_STOCKS) == GvSlice1Verdict::Ok);
    }

    // 7) Verdict reason strings are non-empty (used in block-reject logging).
    CHECK("reason(DestNotAllowed) non-empty",
          gv_slice1_verdict_reason(GvSlice1Verdict::DestNotAllowed)[0] != '\0');

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
