// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// V15 BLOCKER 1 regression test — the MAINNET DTD is PERMISSIONLESS.
// =============================================================================
// WHY THIS FILE EXISTS
// --------------------
// The DTD-PoPC eligibility gate (DTD_POPC_GATE_CONSENSUS_ACTIVE) is a
// BUILD-PROFILE constant. The pre-existing attack matrix and jackpot harnesses
// run under DEVNET_FAST, where that constant has ALWAYS been false — so they
// were structurally incapable of detecting that the MAINNET branch shipped it
// as true. With it true, from DTD_POPC_ELIGIBILITY_HEIGHT (= V15_HEIGHT + 5000
// = 30000) every miner without an active on-chain PoPC commitment is filtered
// out of compute_lottery_eligibility_set(). Since V15 ships PoPC DEACTIVATED
// and the chain holds ZERO commitments, the eligibility set would be EMPTY from
// block 30000 forever, which means:
//   * the every-block DTD draw never has a winner  -> the 50 % emission share
//     rolls over perpetually instead of being redistributed to miners, and
//   * the Historical DTD Jackpot draws its winner from the SAME set, so the
//     ~60 378 SOST historical reserve would never be paid out.
//
// This test is COMPILED WITH MAINNET PARAMETERS (no SOST_DEVNET_FORKS, no
// SOST_TESTNET_FORKS) on purpose. Under any other profile it is inert and says
// so loudly — a green run under devnet/testnet proves NOTHING about mainnet.
//
// It also proves it is NOT vacuous: the counterfactual assertions show that with
// the gate forced ON and an empty chain-derived PoPC set (exactly today's
// mainnet state) every miner WOULD be excluded. Only the shipped mainnet value
// (false) keeps the DTD open.
// =============================================================================

#include "sost/lottery.h"
#include "sost/params.h"
#include "sost/popc_v15.h"
#include "sost/jackpot.h"

#include <cstdio>
#include <vector>
#include <functional>

using namespace sost;
using namespace sost::lottery;

static int g_pass = 0, g_fail = 0;
static void CHECK(const char* what, bool cond) {
    if (cond) { ++g_pass; std::printf("  [PASS] %s\n", what); }
    else      { ++g_fail; std::printf("  [FAIL] %s\n", what); }
}

static PubKeyHash mk_pkh(uint8_t seed) {
    PubKeyHash p{};
    for (size_t i = 0; i < p.size(); ++i) p[i] = (uint8_t)(seed + i);
    return p;
}

static bool contains_pkh(const std::vector<LotteryEligibilityEntry>& v, const PubKeyHash& p) {
    for (const auto& e : v) if (e.pkh == p) return true;
    return false;
}

// Build a mined-block history ending just below `height`, round-robin across
// `n_miners` distinct addresses so NO pkh reaches the 10 % V13 dominance
// threshold over the 288-block window (each takes ~288/n_miners blocks).
static std::vector<LotteryMinedBlockView> build_history(int64_t height,
                                                        const std::vector<PubKeyHash>& miners) {
    std::vector<LotteryMinedBlockView> blocks;
    const int64_t span = (int64_t)DTD_DOMINANCE_WINDOW * 3;   // well past the window
    const int64_t lo   = height - span;
    for (int64_t h = lo; h < height; ++h) {
        LotteryMinedBlockView b;
        b.height    = h;
        b.miner_pkh = miners[(size_t)((h - lo) % (int64_t)miners.size())];
        b.block_hash = Bytes32{};
        b.block_hash[0] = (uint8_t)(h & 0xFF);
        blocks.push_back(b);
    }
    return blocks;
}

int main() {
    std::printf("=== V15 BLOCKER 1 — MAINNET DTD permissionless (mainnet params) ===\n");

#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS)
    std::printf("  [SKIP] built with DEVNET/TESTNET forks — this test only asserts under\n");
    std::printf("         MAINNET parameters. Rebuild without SOST_DEVNET_FORKS /\n");
    std::printf("         SOST_TESTNET_FORKS to exercise the real release configuration.\n");
    std::printf("=== Results: SKIPPED (wrong profile) ===\n");
    return 0;
#else
    // ---- 0) pin that we really are on mainnet params -----------------------
    static_assert(V15_HEIGHT == 25000,
        "This test must be compiled with MAINNET params (V15_HEIGHT == 25000).");
    static_assert(DTD_POPC_ELIGIBILITY_HEIGHT == 30000,
        "This test must be compiled with MAINNET params (eligibility height == 30000).");
    static_assert(HIST_JACKPOT_FIRST_HEIGHT == 25290,
        "This test must be compiled with MAINNET params (first jackpot == 25290).");
    CHECK("mainnet params in effect (V15=25000, eligibility=30000)",
          V15_HEIGHT == 25000 && DTD_POPC_ELIGIBILITY_HEIGHT == 30000);

    // ---- 1) the shipped mainnet gate is INERT ------------------------------
    CHECK("MAINNET DTD_POPC_GATE_CONSENSUS_ACTIVE == false",
          DTD_POPC_GATE_CONSENSUS_ACTIVE == false);
    CHECK("gate not enforced at h=30000 with the shipped flag",
          !popc_eligibility_enforced(30000, DTD_POPC_GATE_CONSENSUS_ACTIVE));
    CHECK("gate not enforced at h=35000 with the shipped flag",
          !popc_eligibility_enforced(35000, DTD_POPC_GATE_CONSENSUS_ACTIVE));
    CHECK("gate not enforced at h=1000000 with the shipped flag",
          !popc_eligibility_enforced(1000000, DTD_POPC_GATE_CONSENSUS_ACTIVE));

    // ---- 2) reproduce TODAY'S mainnet PoPC state: ZERO commitments ---------
    // Wire a chain-derived event source that returns an EMPTY event set at every
    // height — this is exactly what node_collect_popc_events yields on mainnet
    // (popc_registry.json holds 0 commitments and no P4c carrier has ever been
    // mined). Without this the defensive `!g_popc_src -> eligible` branch would
    // mask the real behaviour and make the test vacuous.
    set_popc_event_source([](int64_t) { return std::vector<PopcV15Event>{}; });

    std::vector<PubKeyHash> miners;
    for (int i = 0; i < 36; ++i) miners.push_back(mk_pkh((uint8_t)(0x20 + i)));
    const PubKeyHash NO_BOND_MINER = miners[0];   // holds NO PoPC commitment

    // Sanity: this miner genuinely has no active canonical PoPC at these heights.
    CHECK("no-bond miner really has NO active canonical PoPC at h=30000",
          !popc_v15_owner_active(std::vector<PopcV15Event>{}, NO_BOND_MINER, 30000));

    // ---- 3) THE REGRESSION: eligible at and past the eligibility height ----
    for (int64_t h : { (int64_t)30000, (int64_t)30001, (int64_t)35000, (int64_t)60000 }) {
        auto blocks   = build_history(h, miners);
        auto eligible = compute_lottery_eligibility_set(blocks, h, NO_BOND_MINER, 0);
        char buf[160];
        std::snprintf(buf, sizeof(buf),
            "h=%lld: DTD eligibility set NON-EMPTY without any PoPC bond (%zu entries)",
            (long long)h, eligible.size());
        CHECK(buf, !eligible.empty());
        std::snprintf(buf, sizeof(buf),
            "h=%lld: the no-bond miner IS eligible for the DTD", (long long)h);
        CHECK(buf, contains_pkh(eligible, NO_BOND_MINER));
        std::snprintf(buf, sizeof(buf),
            "h=%lld: EVERY non-dominant miner is eligible (no bond filter at all)",
            (long long)h);
        bool all_in = true;
        for (const auto& m : miners) if (!contains_pkh(eligible, m)) all_in = false;
        CHECK(buf, all_in);
    }

    // ---- 4) the Historical Jackpot draws from the SAME set -----------------
    // Pick jackpot-cadence heights on BOTH sides of the eligibility height so the
    // reserve payout path is covered before and after the gate would have bitten.
    {
        const int64_t j_before = HIST_JACKPOT_FIRST_HEIGHT;                    // 25290
        int64_t j_after = HIST_JACKPOT_FIRST_HEIGHT;
        while (j_after < 30000) j_after += HIST_JACKPOT_CADENCE_BLOCKS;        // first cadence >= 30000
        CHECK("chosen pre-gate height is a jackpot height",  is_hist_jackpot_height(j_before));
        CHECK("chosen post-gate height is a jackpot height", is_hist_jackpot_height(j_after));
        CHECK("post-gate jackpot height is >= 30000", j_after >= 30000);

        for (int64_t h : { j_before, j_after }) {
            auto blocks   = build_history(h, miners);
            auto eligible = compute_lottery_eligibility_set(blocks, h, NO_BOND_MINER, 0);
            char buf[160];
            std::snprintf(buf, sizeof(buf),
                "jackpot height %lld has an eligible winner set (reserve CAN be paid)",
                (long long)h);
            CHECK(buf, !eligible.empty());

            // And the pure payout core then actually pays, i.e. the reserve is
            // returned to a miner instead of rolling over forever.
            const auto r = jackpot::hist_jackpot_apply(h, /*winner_exists=*/!eligible.empty(),
                                                       /*reserve_before=*/60378LL * STOCKS_PER_SOST,
                                                       /*rollover_before=*/0);
            std::snprintf(buf, sizeof(buf),
                "jackpot height %lld PAYS OUT (payout=%lld stocks)",
                (long long)h, (long long)r.payout);
            CHECK(buf, r.paid && r.payout > 0);
        }
    }

    // ---- 5) NOT VACUOUS: the counterfactual (gate forced ON) --------------
    // With the gate ON and zero commitments the set collapses to empty — this is
    // precisely the failure mode BLOCKER 1 describes. Proving it here means the
    // green result above is genuinely produced by the fix, not by an inert test.
    {
        const int64_t h = 30000;
        auto blocks = build_history(h, miners);
        CHECK("counterfactual: gate WOULD be enforced at h=30000 if flag were true",
              popc_eligibility_enforced(h, /*gate_active=*/true));
        bool would_exclude_everyone = true;
        for (const auto& m : miners) {
            if (!(popc_eligibility_enforced(h, true) && !has_active_canonical_popc(m, h)))
                would_exclude_everyone = false;
        }
        CHECK("counterfactual: with the gate ON every miner WOULD be excluded "
              "(empty DTD set -> perpetual rollover, jackpot never pays)",
              would_exclude_everyone);
        // The shipped configuration must NOT do that.
        auto eligible = compute_lottery_eligibility_set(blocks, h, NO_BOND_MINER, 0);
        CHECK("shipped configuration does NOT collapse the set", !eligible.empty());
    }

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
#endif
}
