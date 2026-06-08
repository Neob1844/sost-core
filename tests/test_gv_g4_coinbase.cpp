// test_gv_g4_coinbase.cpp — V14/V15 W2.
//
// The G4 coinbase approval marker (GV_G4_APPROVAL_PKH, 0-value) must be:
//   * REJECTED before gv_g4_active_at(height) — replay byte-identical;
//   * ACCEPTED as exactly one extra trailing output once active (testnet build);
//   * never two markers, never amount>0, never with a wrong pkh, only as last.
// W2 only RECOGNIZES the marker; the 67-block 61/67 tally is W3.
//
// Post-activation cases run only on the testnet build (-DSOST_TESTNET_FORKS),
// where gv_g4_active_at becomes true at V15_HEIGHT (300). On the mainnet build
// gv_g4_active_at is always false (INT64_MAX), so the marker is always rejected.
#include "sost/tx_validation.h"
#include "sost/gv_g4.h"
#include "sost/transaction.h"
#include "sost/params.h"
#include <cstdio>
using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(name, cond) do { if (cond) { ++g_pass; std::printf("  ok  %s\n", name); } \
    else { ++g_fail; std::printf("  *** FAIL: %s\n", name); } } while (0)

static PubKeyHash pkh(uint8_t b) { PubKeyHash p; p.fill(b); return p; }

// A canonical pre-Phase-2 coinbase: 3 outputs MINER/GOLD/POPC with the 50/25/25 split.
static Transaction make_cb(int64_t height, int64_t subsidy, int64_t fees,
                           const PubKeyHash& gold, const PubKeyHash& popc) {
    Transaction tx; tx.version = 1; tx.tx_type = TX_TYPE_COINBASE;
    TxInput in; in.prev_index = 0xFFFFFFFFu;
    for (int i = 0; i < 8; ++i) in.signature[i] = (Byte)((height >> (8 * i)) & 0xFF);
    tx.inputs.push_back(in);
    int64_t total = subsidy + fees, q = total / 4;
    TxOutput o0; o0.type = OUT_COINBASE_MINER; o0.amount = total - q - q;        tx.outputs.push_back(o0);
    TxOutput o1; o1.type = OUT_COINBASE_GOLD;  o1.amount = q; o1.pubkey_hash = gold; tx.outputs.push_back(o1);
    TxOutput o2; o2.type = OUT_COINBASE_POPC;  o2.amount = q; o2.pubkey_hash = popc; tx.outputs.push_back(o2);
    return tx;
}
static TxOutput marker_out(int64_t amount, const PubKeyHash& p) {
    TxOutput m; m.amount = amount; m.pubkey_hash = p; return m;
}

int main() {
    std::printf("=== Gold Vault G4 — coinbase approval marker (W2) ===\n");
    const PubKeyHash GOLD = pkh(0xAA), POPC = pkh(0xBB);
    const int64_t SUB = 1000000, FEES = 0;

    // A valid 3-output coinbase is always accepted (no marker).
    {
        auto cb = make_cb(400, SUB, FEES, GOLD, POPC);
        auto r = ValidateCoinbaseConsensus(cb, 400, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("valid 3-output coinbase (no marker) -> OK", r.ok);
    }

    // PRE-ACTIVATION: a coinbase carrying the marker must be rejected. On the
    // mainnet build this holds at every height; on the testnet build use a height
    // below V15_HEIGHT so gv_g4_active_at is false.
    {
#ifdef SOST_TESTNET_FORKS
        const int64_t H = V15_HEIGHT - 50;   // pre-activation on testnet
#else
        const int64_t H = 400;               // mainnet: always pre-activation
#endif
        CHECK("test height is pre-activation", gv_g4_active_at(H) == false);
        auto cb = make_cb(H, SUB, FEES, GOLD, POPC);
        cb.outputs.push_back(marker_out(0, GV_G4_APPROVAL_PKH));
        auto r = ValidateCoinbaseConsensus(cb, H, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("pre-activation: coinbase + marker -> REJECTED", !r.ok);
    }

#ifdef SOST_TESTNET_FORKS
    // POST-ACTIVATION (testnet build, height >= V15_HEIGHT).
    const int64_t H = V15_HEIGHT + 100;
    CHECK("test height is post-activation (G4 active)", gv_g4_active_at(H) == true);

    {   // valid coinbase + one trailing 0-value marker -> OK
        auto cb = make_cb(H, SUB, FEES, GOLD, POPC);
        cb.outputs.push_back(marker_out(0, GV_G4_APPROVAL_PKH));
        auto r = ValidateCoinbaseConsensus(cb, H, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("post-activation: coinbase + valid marker -> OK", r.ok);
    }
    {   // coinbase WITHOUT marker still OK post-activation
        auto cb = make_cb(H, SUB, FEES, GOLD, POPC);
        auto r = ValidateCoinbaseConsensus(cb, H, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("post-activation: coinbase without marker -> OK", r.ok);
    }
    {   // marker with amount > 0 -> rejected (not recognized as a marker; 4th real output)
        auto cb = make_cb(H, SUB, FEES, GOLD, POPC);
        cb.outputs.push_back(marker_out(1, GV_G4_APPROVAL_PKH));
        auto r = ValidateCoinbaseConsensus(cb, H, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("post-activation: marker amount>0 -> REJECTED", !r.ok);
    }
    {   // extra output to a WRONG pkh -> rejected (shape)
        auto cb = make_cb(H, SUB, FEES, GOLD, POPC);
        cb.outputs.push_back(marker_out(0, pkh(0xCC)));
        auto r = ValidateCoinbaseConsensus(cb, H, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("post-activation: 0-value to wrong pkh -> REJECTED", !r.ok);
    }
    {   // two markers -> rejected
        auto cb = make_cb(H, SUB, FEES, GOLD, POPC);
        cb.outputs.push_back(marker_out(0, GV_G4_APPROVAL_PKH));
        cb.outputs.push_back(marker_out(0, GV_G4_APPROVAL_PKH));
        auto r = ValidateCoinbaseConsensus(cb, H, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("post-activation: two markers -> REJECTED", !r.ok);
    }
    {   // marker NOT last (a real output after it) -> rejected
        auto cb = make_cb(H, SUB, FEES, GOLD, POPC);
        TxOutput extra; extra.type = OUT_COINBASE_MINER; extra.amount = 1;
        cb.outputs.insert(cb.outputs.end() - 1, marker_out(0, GV_G4_APPROVAL_PKH));
        auto r = ValidateCoinbaseConsensus(cb, H, SUB, FEES, GOLD, POPC, nullptr);
        CHECK("post-activation: marker not last -> REJECTED", !r.ok);
    }
#else
    std::printf("  [mainnet build: post-activation cases run on the testnet build]\n");
    // Mainnet stays a no-op: gv_g4_active_at is false at the V15 target height too.
    CHECK("mainnet: gv_g4 deferred at V15_HEIGHT (20000)", gv_g4_active_at(20000) == false);
#endif

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
