// ============================================================================
// test_jackpot_v2 — V16 Historical Jackpot V2, PURE consensus core.
// Exercises include/sost/jackpot_v2.h: epoch/bootstrap math, NODE_BIND active
// derivation (effective at inclusion+1, seq replay, global uniqueness, rotation),
// heartbeat window counting, eligibility, linear weight, canonical ordering,
// domain-separated seed, deterministic integer weighted draw, Sybil/ordering
// invariance, 0/1-eligible edges. All heights use explicit A=30000, L=288 so the
// file asserts the exact mainnet bootstrap schedule regardless of build net.
// ============================================================================
#include "sost/jackpot_v2.h"
#include "sost/params.h"

#include <cstdio>
#include <vector>
#include <algorithm>

using namespace sost;
using namespace sost::jackpot_v2;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { ++g_pass; printf("  PASS: %s\n", msg); } \
    else      { ++g_fail; printf("  FAIL: %s\n", msg); } \
} while (0)

static PubKeyHash pkh(uint8_t b) { PubKeyHash p{}; p.fill(b); return p; }
static NodePubKey node(uint8_t b) { NodePubKey n{}; n.fill(b); return n; }

static JackpotV2Candidate cand(uint8_t b, int64_t pow, bool bound, int64_t hb, bool sbpow = true) {
    JackpotV2Candidate c;
    c.mining_pkh = pkh(b);
    c.sbpow_valid = sbpow;
    c.pow_blocks = pow;
    c.node_bound = bound;
    c.heartbeats_in_window = hb;
    return c;
}

// Mainnet-shape constants used explicitly (net-independent assertions).
static const int64_t A = 30000;    // V2 activation
static const int64_t L = 288;      // epoch length
static const int64_t FIRST_V2 = 30186;

// ---------------------------------------------------------------------------
static void test_epoch_and_bootstrap() {
    TEST("epoch0 completes at end of #30,287 -> 0 before #30,287",
         jv2_completed_epochs_before(A, L, 30287) == 0);
    TEST("epoch0 counted from #30,288",
         jv2_completed_epochs_before(A, L, 30288) == 1);
    TEST("#30,575 -> 1 completed", jv2_completed_epochs_before(A, L, 30575) == 1);
    TEST("#30,576 -> 2 completed", jv2_completed_epochs_before(A, L, 30576) == 2);
    TEST("#30,864 -> 3 completed", jv2_completed_epochs_before(A, L, 30864) == 3);

    struct { int64_t h, req, win; } exp[] = {
        {30186, 0, 0}, {30474, 1, 1}, {30762, 2, 2}, {31050, 3, 3}, {31338, 3, 4}, {31626, 3, 4},
    };
    for (auto& e : exp) {
        int64_t c = jv2_completed_epochs_before(A, L, e.h);
        char m[96];
        snprintf(m, sizeof m, "bootstrap #%lld -> HB %lld/%lld",
                 (long long)e.h, (long long)jv2_heartbeat_required(c), (long long)jv2_heartbeat_window(c));
        TEST(m, jv2_heartbeat_required(c) == e.req && jv2_heartbeat_window(c) == e.win);
    }
    TEST("first V2 jackpot is beyond activation and cadence-aligned in params",
         is_hist_jackpot_v2_height(HIST_JACKPOT_FIRST_HEIGHT) ==
         (HIST_JACKPOT_FIRST_HEIGHT >= HIST_JACKPOT_V2_HEIGHT));
}

// ---------------------------------------------------------------------------
static void test_node_bind() {
    // effective at inclusion_height + 1
    std::vector<NodeBindRecord> recs;
    recs.push_back({pkh(1), node(10), /*seq*/1, /*incl*/30100});
    TEST("bind NOT active at inclusion height", !jv2_is_node_bound_at(recs, pkh(1), 30100));
    TEST("bind active at inclusion+1",            jv2_is_node_bound_at(recs, pkh(1), 30101));

    // rotation: higher bind_seq replaces; active node key becomes the new one
    recs.push_back({pkh(1), node(11), 2, 30120});
    auto act = jv2_active_bindings_at(recs, 30200);
    TEST("rotation -> active node key is the higher-seq one", act[pkh(1)].node_pubkey == node(11));

    // replay / stale: a bind_seq <= max already accepted is ignored
    recs.push_back({pkh(1), node(12), 2, 30140}); // seq 2 again -> ignored (not strictly greater)
    recs.push_back({pkh(1), node(13), 1, 30160}); // seq 1 replay -> ignored
    auto act2 = jv2_active_bindings_at(recs, 30200);
    TEST("bind_seq replay/stale ignored -> active unchanged", act2[pkh(1)].node_pubkey == node(11));

    // global uniqueness: a node_pubkey belongs to exactly one mining_pkh
    std::vector<NodeBindRecord> u;
    u.push_back({pkh(1), node(50), 1, 30010});   // miner 1 claims node 50 first
    u.push_back({pkh(2), node(50), 1, 30020});   // miner 2 tries same node -> rejected
    auto au = jv2_active_bindings_at(u, 30100);
    TEST("first claimant owns the node key",      au.count(pkh(1)) == 1 && au[pkh(1)].node_pubkey == node(50));
    TEST("second miner claiming same node key rejected", au.count(pkh(2)) == 0);

    // rotation does not release ownership of the old key
    std::vector<NodeBindRecord> r2;
    r2.push_back({pkh(1), node(60), 1, 30010});
    r2.push_back({pkh(1), node(61), 2, 30020});  // miner1 rotates 60 -> 61
    r2.push_back({pkh(2), node(60), 1, 30030});  // miner2 tries old key 60 -> rejected
    auto ar = jv2_active_bindings_at(r2, 30100);
    TEST("rotated-away key still owned -> other miner rejected", ar.count(pkh(2)) == 0);

    // order independence: shuffle the input vector -> identical active set
    std::vector<NodeBindRecord> s = r2;
    std::reverse(s.begin(), s.end());
    auto as1 = jv2_active_bindings_at(r2, 30100);
    auto as2 = jv2_active_bindings_at(s,  30100);
    TEST("active binding derivation is input-order independent",
         as1[pkh(1)].node_pubkey == as2[pkh(1)].node_pubkey && as1.size() == as2.size());
}

// ---------------------------------------------------------------------------
static void test_heartbeats() {
    std::vector<HeartbeatRecord> hbs;
    // miner 1 heartbeats in epochs 0,1,2 ; miner 2 only epoch 2 (twice -> dedup)
    hbs.push_back({pkh(1), 0});
    hbs.push_back({pkh(1), 1});
    hbs.push_back({pkh(1), 2});
    hbs.push_back({pkh(2), 2});
    hbs.push_back({pkh(2), 2});
    // at #31,338: completed=4, window=4, range epochs [0,3]
    TEST("miner1 has 3 distinct epochs in window", jv2_heartbeats_in_window(hbs, pkh(1), A, L, 31338) == 3);
    TEST("miner2 dedup: 2 records same epoch -> 1", jv2_heartbeats_in_window(hbs, pkh(2), A, L, 31338) == 1);
    // at #30,186: window 0 -> count 0 for everyone
    TEST("bootstrap #30,186 window 0 -> count 0",  jv2_heartbeats_in_window(hbs, pkh(1), A, L, 30186) == 0);
}

// ---------------------------------------------------------------------------
static void test_eligibility() {
    // at #31,338 (permanent 3/4): required heartbeats = 3
    TEST("all conditions met -> eligible",
         jv2_is_eligible(cand(1, /*pow*/5, /*bound*/true, /*hb*/3), A, L, 31338));
    TEST("pow < 3 -> POW_TOO_LOW",
         (jv2_eligibility_reason(cand(1, 2, true, 3), A, L, 31338) & JV2_POW_TOO_LOW) != 0);
    TEST("pow == 3 -> eligible",
         jv2_is_eligible(cand(1, 3, true, 3), A, L, 31338));
    TEST("not node-bound -> NOT_NODE_BOUND",
         (jv2_eligibility_reason(cand(1, 5, false, 3), A, L, 31338) & JV2_NOT_NODE_BOUND) != 0);
    TEST("heartbeats short -> HEARTBEAT_SHORT",
         (jv2_eligibility_reason(cand(1, 5, true, 2), A, L, 31338) & JV2_HEARTBEAT_SHORT) != 0);
    TEST("no sbpow -> NO_SBPOW",
         (jv2_eligibility_reason(cand(1, 5, true, 3, /*sbpow*/false), A, L, 31338) & JV2_NO_SBPOW) != 0);
    // bootstrap #30,186: NODE_BIND still mandatory, heartbeats 0 required
    TEST("#30,186 bound + pow>=3 + hb 0 -> eligible",
         jv2_is_eligible(cand(1, 3, true, 0), A, L, FIRST_V2));
    TEST("#30,186 NOT bound -> ineligible even with pow (bind mandatory from first V2)",
         !jv2_is_eligible(cand(1, 100, false, 0), A, L, FIRST_V2));
}

// ---------------------------------------------------------------------------
static void test_weight_and_order() {
    std::vector<JackpotV2Candidate> cs = {
        cand(3, 5, true, 3), cand(1, 12, true, 3), cand(2, 3, true, 3),
        cand(9, 7, false, 3),          // not bound -> excluded
    };
    auto w = jv2_build_weighted_set(cs, A, L, 31338);
    TEST("only eligible are included (3 of 4)", w.size() == 3);
    TEST("linear weight == pow_blocks", w[0].weight + w[1].weight + w[2].weight == 20);
    TEST("canonical order = pkh ascending",
         w[0].pkh == pkh(1) && w[1].pkh == pkh(2) && w[2].pkh == pkh(3));
    TEST("total weight helper", jv2_total_weight(w) == 20);
}

// ---------------------------------------------------------------------------
static void test_sybil_invariance() {
    // one identity with 100 blocks
    std::vector<JackpotV2Candidate> single = { cand(1, 100, true, 3) };
    auto ws = jv2_build_weighted_set(single, A, L, 31338);
    int64_t t_single = jv2_total_weight(ws);

    // same 100 blocks split across 10 identities (10 each)
    std::vector<JackpotV2Candidate> split;
    for (uint8_t i = 0; i < 10; ++i) split.push_back(cand((uint8_t)(20 + i), 10, true, 3));
    auto wsp = jv2_build_weighted_set(split, A, L, 31338);
    int64_t t_split = jv2_total_weight(wsp);

    // and across 100 identities (1 each) — but pow<3 would exclude; so use 3 each x split test
    TEST("single(100) total == 100", t_single == 100);
    TEST("split 10x10 aggregate == 100 (Sybil-neutral)", t_split == 100);
    TEST("fragmenting does NOT increase aggregate weight", t_split == t_single);

    // node count never affects weight: same pow, more heartbeats/binding irrelevant to weight
    auto w_bound = jv2_build_weighted_set({ cand(1, 42, true, 3) }, A, L, 31338);
    TEST("weight == pow regardless of node participation", w_bound[0].weight == 42);
}

// ---------------------------------------------------------------------------
static void test_draw_determinism_and_order_invariance() {
    std::vector<Bytes32> ent(4);
    for (int i = 0; i < 4; ++i) ent[i].fill((uint8_t)(0xA0 + i));
    Bytes32 seed = jv2_seed(ent, 31338);

    std::vector<JackpotV2Candidate> base = {
        cand(1, 5, true, 3), cand(2, 12, true, 3), cand(3, 3, true, 3),
        cand(4, 8, true, 3), cand(5, 1, true, 3),
    };
    auto wbase = jv2_build_weighted_set(base, A, L, 31338);
    int64_t idx = jv2_select_winner_index(wbase, seed);
    TEST("winner index in range", idx >= 0 && idx < (int64_t)wbase.size());
    PubKeyHash winner = wbase[idx].pkh;

    // determinism: repeat
    TEST("draw is deterministic (repeat)", jv2_select_winner_index(wbase, seed) == idx);

    // ordering invariance: feed candidates in many shuffled orders -> same winner
    bool same = true;
    std::vector<JackpotV2Candidate> perm = base;
    std::sort(perm.begin(), perm.end(),
              [](const JackpotV2Candidate& a, const JackpotV2Candidate& b){ return a.mining_pkh < b.mining_pkh; });
    int count = 0;
    do {
        auto wp = jv2_build_weighted_set(perm, A, L, 31338);
        int64_t wi = jv2_select_winner_index(wp, seed);
        if (wp[wi].pkh != winner) { same = false; break; }
        ++count;
    } while (std::next_permutation(perm.begin(), perm.end(),
             [](const JackpotV2Candidate& a, const JackpotV2Candidate& b){ return a.mining_pkh < b.mining_pkh; })
             && count < 120);
    TEST("winner identical across all input orderings", same);

    // seed domain separation / height sensitivity
    TEST("seed differs by height", !(jv2_seed(ent, 31338) == jv2_seed(ent, 31626)));
    TEST("seed reproducible", jv2_seed(ent, 31338) == jv2_seed(ent, 31338));
}

// ---------------------------------------------------------------------------
static void test_edges() {
    std::vector<Bytes32> ent(1); ent[0].fill(0x11);
    Bytes32 seed = jv2_seed(ent, FIRST_V2);

    // 0 eligible -> -1 (rollover)
    std::vector<JackpotV2Candidate> none = { cand(1, 2, true, 0) /*pow too low*/ };
    auto w0 = jv2_build_weighted_set(none, A, L, FIRST_V2);
    TEST("0 eligible -> winner index -1 (rollover)", jv2_select_winner_index(w0, seed) == -1);

    // 1 eligible -> that one wins
    std::vector<JackpotV2Candidate> one = { cand(7, 4, true, 0) };
    auto w1 = jv2_build_weighted_set(one, A, L, FIRST_V2);
    int64_t wi = jv2_select_winner_index(w1, seed);
    TEST("1 eligible -> index 0 wins", wi == 0 && w1[wi].pkh == pkh(7));
}

// ---------------------------------------------------------------------------
int main() {
    printf("== test_jackpot_v2 (V16 pure consensus core) ==\n");
    test_epoch_and_bootstrap();
    test_node_bind();
    test_heartbeats();
    test_eligibility();
    test_weight_and_order();
    test_sybil_invariance();
    test_draw_determinism_and_order_invariance();
    test_edges();
    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
