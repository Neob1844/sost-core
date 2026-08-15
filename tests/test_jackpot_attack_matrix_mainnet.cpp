// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// V15 jackpot attack matrix — MAINNET-PARAMETER edition.
// =============================================================================
// WHY THIS FILE EXISTS
// --------------------
// The 17-case valid-PoW attack matrix (tests/run_v15_devnet_attacks.sh) can only
// run under DEVNET_FAST: the adversarial mutations are compiled `#ifdef
// SOST_DEVNET_FORKS` into sost-miner, and the harness needs a first jackpot at
// height 24 rather than 25290. That is a legitimate harness, but it means the
// matrix has NEVER been executed against MAINNET consensus constants — and a
// MAINNET-vs-DEVNET parameter difference is exactly what hid V15 BLOCKER 1 (the
// DTD-PoPC gate).
//
// This test closes that specific gap at the layer that actually decides: the
// canonical reconstruction in jackpot_block.h::validate_block_jackpot, which is
// the sole authorization for the keyless TX_TYPE_JACKPOT reserve spend and the
// function every node-level rejection ultimately comes from. Every mutation the
// devnet miner can perform is replayed here against MAINNET heights (V15 25000,
// first jackpot 25290, cadence 288) and must be rejected.
//
// SCOPE — stated honestly. This is a CONSENSUS-DECISION matrix, not an
// end-to-end node/miner matrix. It does not mine PoW, does not call submitblock
// and does not assert node state atomicity; that remains the devnet harness's
// job. What it does prove is that the accept/reject verdict for every mutation
// is identical under mainnet constants.
// =============================================================================

#include "sost/jackpot.h"
#include "sost/jackpot_block.h"
#include "sost/jackpot_reserve.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/address.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
static void CHECK(const std::string& what, bool cond) {
    if (cond) { ++g_pass; std::printf("  [PASS] %s\n", what.c_str()); }
    else      { ++g_fail; std::printf("  [FAIL] %s\n", what.c_str()); }
}

static Bytes32 mk_id(uint8_t f) { Bytes32 b{}; std::memset(b.data(), f, 32); return b; }
static PubKeyHash mk_pkh(uint8_t f) { PubKeyHash p{}; std::memset(p.data(), f, p.size()); return p; }

int main() {
    std::printf("=== V15 jackpot attack matrix — MAINNET parameters ===\n");

#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS)
    std::printf("  [SKIP] not a MAINNET-parameter build — this matrix only asserts under\n");
    std::printf("         mainnet consensus constants (that is its entire purpose).\n");
    std::printf("=== Results: SKIPPED (wrong profile) ===\n");
    return 0;
#else
    static_assert(V15_HEIGHT == 25000, "MAINNET params required (V15_HEIGHT == 25000).");
    static_assert(HIST_JACKPOT_FIRST_HEIGHT == 25290, "MAINNET params required (first jackpot 25290).");
    static_assert(HIST_JACKPOT_CADENCE_BLOCKS == 288, "MAINNET params required (cadence 288).");
    CHECK("mainnet constants: V15=25000, firstJ=25290, cadence=288",
          V15_HEIGHT == 25000 && HIST_JACKPOT_FIRST_HEIGHT == 25290 &&
          HIST_JACKPOT_CADENCE_BLOCKS == 288);

    const PubKeyHash& GOLD = jackpot::reserve_gold_pkh();

    // --- canonical pre-block state at the FIRST mainnet jackpot height -------
    const int64_t H = HIST_JACKPOT_FIRST_HEIGHT;                 // 25290
    const PubKeyHash WINNER      = mk_pkh(0x91);
    const PubKeyHash CUR_MINER   = mk_pkh(0x55);                 // the block's own miner

    std::vector<jackpot::ReserveUtxo> reserve;
    for (int i = 0; i < 5; ++i) {
        jackpot::ReserveUtxo u;
        u.height = 1000 + i;
        u.txid   = mk_id((uint8_t)(0x10 + i));
        u.vout   = (uint32_t)i;
        u.amount = 60LL * STOCKS_PER_SOST;    // 5 x 60 = 300 SOST; base prize 100 -> real change
        reserve.push_back(u);
    }
    std::sort(reserve.begin(), reserve.end(), jackpot::reserve_utxo_less);
    const int64_t RESERVE_BEFORE = jackpot::reserve_balance(reserve);
    const int64_t ROLLOVER = 0;

    Transaction canonical;
    CHECK("canonical mainnet jackpot builds at h=25290",
          jackpot::build_canonical_jackpot_tx(H, true, WINNER, RESERVE_BEFORE, ROLLOVER,
                                              reserve, GOLD, canonical));
    CHECK("canonical jackpot has a positive change output (matrix is meaningful)",
          canonical.outputs.size() == 2 && canonical.outputs[1].amount > 0);

    Transaction coinbase;
    coinbase.version = 1;
    coinbase.tx_type = TX_TYPE_COINBASE;
    { TxOutput o; o.amount = 1; o.type = OUT_COINBASE_MINER; o.pubkey_hash = CUR_MINER;
      coinbase.outputs.push_back(o); }

    const std::vector<Transaction> HONEST = { coinbase, canonical };

    auto verdict = [&](const std::vector<Transaction>& txs, int64_t h) {
        return jackpot::validate_block_jackpot(txs, h, reserve, /*winner_exists=*/true, WINNER,
                                               RESERVE_BEFORE, ROLLOVER, GOLD);
    };

    // ---- the HONEST block must be accepted --------------------------------
    CHECK("A00 honest canonical block ACCEPTED", verdict(HONEST, H).ok);

    // ---- the 17-case mutation matrix, replayed at mainnet heights ----------
    struct Case { const char* id; std::vector<Transaction> txs; };
    std::vector<Case> cases;
    auto add = [&](const char* id, std::vector<Transaction> txs) { cases.push_back({id, std::move(txs)}); };

    { auto t = HONEST; t[1].outputs[0].pubkey_hash[0] ^= 0xFF;             add("A01 wrong-winner", t); }
    { auto t = HONEST; t[1].outputs[0].pubkey_hash = CUR_MINER;            add("A02 winner-self (anti self-payout)", t); }
    { auto t = HONEST; t[1].outputs[0].amount += 1;                        add("A04 payout-plus", t); }
    { auto t = HONEST; t[1].outputs[0].amount -= 1;                        add("A05 payout-minus", t); }
    { auto t = HONEST; t[1].outputs[0].amount = 0;                         add("A06 payout-zero", t); }
    { auto t = HONEST; std::reverse(t[1].inputs.begin(), t[1].inputs.end()); add("A08 reverse-inputs", t); }
    { auto t = HONEST; t[1].inputs.pop_back();                             add("A09 remove-input", t); }
    { auto t = HONEST; t[1].inputs.push_back(t[1].inputs.back());          add("A10 dup-input", t); }
    { auto t = HONEST; TxInput fk{}; fk.prev_txid.fill(0xAB); fk.prev_index = 0;
      t[1].inputs.push_back(fk);                                           add("B04 foreign-input", t); }
    { auto t = HONEST; t[1].outputs.push_back(t[1].outputs[0]);            add("A19 extra-output", t); }
    { auto t = HONEST; t[1].outputs.erase(t[1].outputs.begin());           add("A20 remove-winner-output", t); }
    { auto t = HONEST; t.push_back(t[1]); std::swap(t[1], t[2]);           add("A21 move-jackpot (not at index 1)", t); }
    { auto t = HONEST; t.insert(t.begin() + 2, t[1]);                      add("A22 dup-jackpot", t); }
    { auto t = HONEST; t.erase(t.begin() + 1);                             add("A23 remove-jackpot", t); }
    { auto t = HONEST; t[0].outputs[0].pubkey_hash[0] ^= 0xFF;
      t[1].outputs[0].pubkey_hash = t[0].outputs[0].pubkey_hash;           add("A26 coinbase-mutate (J retained)", t); }
    { auto t = HONEST; t[1].inputs[0].prev_index += 1;                     add("B-idx input-index-bump", t); }
    { auto t = HONEST; t[1].inputs[0].prev_txid[0] ^= 0xFF;                add("B-txid input-txid-flip", t); }
    { auto t = HONEST; t[1].outputs[0].amount = 0x7fffffffffffffffLL;      add("payout-intmax", t); }
    { auto t = HONEST; size_t n = t[1].inputs.size();
      for (size_t k = 0; k < n; ++k) t[1].inputs.push_back(t[1].inputs[k]);
                                                                           add("dup-all-inputs (bulk double-spend)", t); }
    // Change-output mutations (matrix rows 1/2/3/4) — reachable here because the
    // fixture deliberately produces a positive canonical change.
    { auto t = HONEST; t[1].outputs[1].amount += 1;                        add("C1 wrong change amount", t); }
    { auto t = HONEST; t[1].outputs[1].pubkey_hash = mk_pkh(0x77);         add("C2 change diverted off the sink", t); }
    { auto t = HONEST; t[1].outputs[1].type = OUT_TRANSFER;                add("C2b change made ordinarily spendable", t); }
    { auto t = HONEST; t[1].outputs.pop_back();                            add("C4 missing required change", t); }
    { auto t = HONEST; t[1].tx_type = TX_TYPE_STANDARD;                    add("type-downgrade to STANDARD", t); }
    { auto t = HONEST; t[1].version += 1;                                  add("version bump", t); }

    for (const auto& c : cases) {
        auto r = verdict(c.txs, H);
        CHECK(std::string(c.id) + " REJECTED at mainnet h=25290", !r.ok);
    }

    // ---- height-dimension cases (M02 / M03 analogues) ----------------------
    // M02: a perfectly canonical jackpot replayed at a NON-cadence height.
    for (int64_t off : { (int64_t)1, (int64_t)2, (int64_t)143, (int64_t)287 }) {
        auto r = verdict(HONEST, H + off);
        CHECK("M02 canonical J at non-cadence height " + std::to_string((long long)(H + off)) +
              " REJECTED", !r.ok);
        CHECK("M02 that height really is NOT a jackpot height", !is_hist_jackpot_height(H + off));
    }
    // M03: a STALE jackpot (built for h=25290) replayed at the NEXT cadence height,
    // where the canonical reconstruction differs because the reserve has moved on.
    {
        const int64_t H2 = H + HIST_JACKPOT_CADENCE_BLOCKS;    // 25578
        CHECK("M03 next cadence height is a jackpot height", is_hist_jackpot_height(H2));
        std::vector<jackpot::ReserveUtxo> reserve2;            // reserve after the first payout
        for (size_t i = 2; i < reserve.size(); ++i) reserve2.push_back(reserve[i]);
        const int64_t RB2 = jackpot::reserve_balance(reserve2);
        auto r = jackpot::validate_block_jackpot(HONEST, H2, reserve2, true, WINNER, RB2, 0, GOLD);
        CHECK("M03 stale jackpot replayed at a later event REJECTED", !r.ok);
    }
    // Below the first jackpot height nothing may carry a jackpot tx at all.
    {
        auto r = verdict(HONEST, V15_HEIGHT);
        CHECK("jackpot tx at V15_HEIGHT (pre-first-jackpot) REJECTED", !r.ok);
        auto r2 = verdict(HONEST, V15_HEIGHT - 1);
        CHECK("jackpot tx below V15_HEIGHT REJECTED", !r2.ok);
    }
    // No eligible winner -> no jackpot tx may be present.
    {
        auto r = jackpot::validate_block_jackpot(HONEST, H, reserve, /*winner_exists=*/false,
                                                 WINNER, RESERVE_BEFORE, ROLLOVER, GOLD);
        CHECK("jackpot tx present with NO eligible winner REJECTED", !r.ok);
    }
    // Empty reserve -> no jackpot tx may be present, and the honest block is txs=1.
    {
        std::vector<jackpot::ReserveUtxo> empty;
        auto r = jackpot::validate_block_jackpot(HONEST, H, empty, true, WINNER, 0, ROLLOVER, GOLD);
        CHECK("jackpot tx present with an EXHAUSTED reserve REJECTED", !r.ok);
        std::vector<Transaction> cb_only = { coinbase };
        auto r2 = jackpot::validate_block_jackpot(cb_only, H, empty, true, WINNER, 0, ROLLOVER, GOLD);
        CHECK("coinbase-only block at a jackpot height with an empty reserve ACCEPTED", r2.ok);
    }

    // ---- the honest block is STILL accepted after the whole matrix ---------
    CHECK("A00 honest canonical block still ACCEPTED after the matrix", verdict(HONEST, H).ok);

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
#endif
}
