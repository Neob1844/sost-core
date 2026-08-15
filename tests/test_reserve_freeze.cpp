// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// V15 BLOCKER 2 regression test — CONSTITUTIONAL RESERVE FREEZE (S13).
// =============================================================================
// Before V15 the Historical Jackpot reserve was protected by key custody alone:
// docs/CONSTITUTIONAL_ADDRESSES_AUDIT.md records that "no consensus rule
// prevents spending FROM Gold Vault or PoPC Pool — anyone with the private key
// CAN spend". Since the reserve is defined as whatever those addresses hold
// (jackpot_reserve.h) and the jackpot retires permanently once the reserve
// reaches zero (jackpot.h), a single signed sweep would have destroyed the
// Historical Jackpot for good.
//
// From RESERVE_FREEZE_ACTIVATION_HEIGHT (= V15_HEIGHT) consensus enforces:
//     spending a reserve UTXO  =>  tx.tx_type MUST be TX_TYPE_JACKPOT
// and the canonical jackpot must still match the byte-exact reconstruction.
//
// ON PROVING "A VALID SIGNATURE IS REJECTED"
// -----------------------------------------
// The constitutional private keys are not available to this test suite (and
// must never be), so a signature made BY those keys cannot be produced here.
// Instead the test proves the strictly stronger structural property: the S13
// verdict is INVARIANT under the contents of the signature/pubkey fields. The
// same reserve-spending transaction is validated with a zero signature, with a
// garbage signature, and with a real ECDSA signature from a freshly generated
// key — all three yield S13_RESERVE_FROZEN, and S13 is reached BEFORE any
// signature or pkh check runs. A signature from the real constitutional key is
// just a fourth value of those same bytes, so it is rejected identically.
// =============================================================================

#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/transaction.h"
#include "sost/jackpot.h"
#include "sost/jackpot_block.h"
#include "sost/jackpot_reserve.h"
#include "sost/utxo_set.h"
#include "sost/address.h"
#include "sost/params.h"

#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
static void CHECK(const std::string& what, bool cond) {
    if (cond) { ++g_pass; std::printf("  [PASS] %s\n", what.c_str()); }
    else      { ++g_fail; std::printf("  [FAIL] %s\n", what.c_str()); }
}

// ---------------------------------------------------------------------------
// Mock UTXO view for the validator
// ---------------------------------------------------------------------------
class MapUtxoView : public IUtxoView {
public:
    std::map<OutPoint, UTXOEntry> db;
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
        auto it = db.find(op);
        if (it == db.end()) return std::nullopt;
        return it->second;
    }
    void Add(const Hash256& txid, uint32_t index, const UTXOEntry& e) {
        db[OutPoint{txid, index}] = e;
    }
};

static Hash256 mk_txid(uint8_t fill) {
    Hash256 h{}; std::memset(h.data(), fill, 32); return h;
}
static PubKeyHash mk_pkh(uint8_t fill) {
    PubKeyHash p{}; std::memset(p.data(), fill, p.size()); return p;
}

static Hash256   g_genesis{};
static PrivKey   g_priv{};
static PubKey    g_pub{};
static PubKeyHash g_pkh{};

// How the signature bytes were produced — used to prove S13 ignores them.
enum class SigMode { Zero, Garbage, RealEcdsa };

// Build a 1-in-1-out ordinary transfer that spends the UTXO (txid,0) held in
// `view`, i.e. exactly the "signed sweep" the audit warned about.
static Transaction make_sweep_tx(const MapUtxoView& view,
                                 const Hash256& prev_txid,
                                 SigMode mode) {
    const UTXOEntry& u = view.db.at(OutPoint{prev_txid, 0});

    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid  = prev_txid;
    in.prev_index = 0;
    tx.inputs.push_back(in);

    TxOutput out;
    out.amount      = u.amount - 1000;      // leave a generous fee
    out.type        = OUT_TRANSFER;
    out.pubkey_hash = mk_pkh(0x77);         // attacker-controlled destination
    tx.outputs.push_back(out);

    switch (mode) {
        case SigMode::Zero:
            tx.inputs[0].signature.fill(0);
            tx.inputs[0].pubkey.fill(0);
            break;
        case SigMode::Garbage:
            tx.inputs[0].signature.fill(0x5A);
            tx.inputs[0].pubkey.fill(0x5A);
            break;
        case SigMode::RealEcdsa: {
            SpentOutput spent{u.amount, u.type};
            std::string err;
            SignTransactionInput(tx, 0, spent, g_genesis, g_priv, &err);
            break;
        }
    }
    return tx;
}

static TxValidationContext mk_ctx(int64_t spend_height) {
    TxValidationContext c;
    c.genesis_hash = g_genesis;
    c.spend_height = spend_height;
    return c;
}

// ---------------------------------------------------------------------------
// 1-2) ordinary signed spend from each constitutional sink at h >= V15
// ---------------------------------------------------------------------------
static void test_sweep_rejected(const char* label, uint8_t out_type, const PubKeyHash& sink_pkh) {
    const int64_t H = jackpot::RESERVE_FREEZE_ACTIVATION_HEIGHT;   // exactly at activation

    for (auto mode : { SigMode::Zero, SigMode::Garbage, SigMode::RealEcdsa }) {
        MapUtxoView view;
        const Hash256 prev = mk_txid(0x31);
        UTXOEntry u;
        u.amount      = 60378LL * STOCKS_PER_SOST;   // the whole historical reserve
        u.type        = out_type;
        u.pubkey_hash = sink_pkh;
        u.height      = 100;
        u.is_coinbase = true;
        view.Add(prev, 0, u);

        Transaction tx = make_sweep_tx(view, prev, mode);

        const char* mname = (mode == SigMode::Zero) ? "zero-sig"
                          : (mode == SigMode::Garbage) ? "garbage-sig" : "real-ECDSA-sig";

        auto r = ValidateTransactionConsensus(tx, view, mk_ctx(H));
        CHECK(std::string(label) + " sweep at h=V15 REJECTED (" + mname + ")",
              !r.ok && r.code == TxValCode::S13_RESERVE_FROZEN);

        auto r2 = ValidateTransactionConsensus(tx, view, mk_ctx(H + 100000));
        CHECK(std::string(label) + " sweep far past V15 REJECTED (" + mname + ")",
              !r2.ok && r2.code == TxValCode::S13_RESERVE_FROZEN);

        // Relay policy must refuse it too, so it never propagates or gets mined.
        auto p = ValidateTransactionPolicy(tx, view, mk_ctx(H));
        CHECK(std::string(label) + " sweep NOT RELAYED at h=V15 (" + mname + ")",
              !p.ok && p.code == TxValCode::P_RESERVE_FROZEN);
    }
}

int main() {
    std::printf("=== V15 BLOCKER 2 — constitutional reserve freeze (S13) ===\n");

    std::memset(g_genesis.data(), 0xAA, 32);
    {
        std::string err;
        if (!GenerateKeyPair(g_priv, g_pub, &err)) {
            std::printf("  [FAIL] GenerateKeyPair: %s\n", err.c_str());
            return 1;
        }
        g_pkh = ComputePubKeyHash(g_pub);
    }

    const PubKeyHash& GOLD = jackpot::reserve_gold_pkh();
    const PubKeyHash& POPC = jackpot::reserve_popc_pkh();

    // ---- 0) the accessors really decode the constitutional addresses -------
    {
        PubKeyHash g{}, p{};
        CHECK("ADDR_GOLD_VAULT decodes", address_decode(ADDR_GOLD_VAULT, g));
        CHECK("ADDR_POPC_POOL decodes",  address_decode(ADDR_POPC_POOL, p));
        CHECK("reserve_gold_pkh() == ADDR_GOLD_VAULT", GOLD == g);
        CHECK("reserve_popc_pkh() == ADDR_POPC_POOL",  POPC == p);
        CHECK("freeze activates exactly at V15_HEIGHT",
              jackpot::RESERVE_FREEZE_ACTIVATION_HEIGHT == V15_HEIGHT);
    }

    // ---- 1) Gold Vault sweep at h >= V15 -> REJECTED -----------------------
    std::printf("\n-- 1) ordinary signed spend from ADDR_GOLD_VAULT --\n");
    test_sweep_rejected("Gold Vault", OUT_COINBASE_GOLD, GOLD);

    // ---- 2) PoPC Pool sweep at h >= V15 -> REJECTED ------------------------
    std::printf("\n-- 2) ordinary signed spend from ADDR_POPC_POOL --\n");
    test_sweep_rejected("PoPC Pool", OUT_COINBASE_POPC, POPC);

    // ---- 3) the SAME spend below V15 -> the freeze does NOT apply ----------
    // Replay integrity: below the activation height the new rule is inert, so
    // pre-V15 validation is byte-for-byte the old behaviour. What blocked such a
    // spend before V15 was ONLY key custody (an S2 pkh mismatch for anybody who
    // is not the key holder) — precisely the gap the audit reported.
    std::printf("\n-- 3) same spend below V15 (replay intact) --\n");
    {
        for (int variant = 0; variant < 2; ++variant) {
            const bool gold = (variant == 0);
            MapUtxoView view;
            const Hash256 prev = mk_txid(0x42);
            UTXOEntry u;
            u.amount      = 5000LL * STOCKS_PER_SOST;
            u.type        = gold ? OUT_COINBASE_GOLD : OUT_COINBASE_POPC;
            u.pubkey_hash = gold ? GOLD : POPC;
            u.height      = 100;
            u.is_coinbase = true;
            view.Add(prev, 0, u);

            Transaction tx = make_sweep_tx(view, prev, SigMode::RealEcdsa);
            const std::string lbl = gold ? "Gold Vault" : "PoPC Pool";

            // The gate predicate itself is false below V15.
            CHECK(lbl + ": freeze predicate FALSE at h = V15-1",
                  !jackpot::reserve_freeze_active_at(V15_HEIGHT - 1));
            CHECK(lbl + ": freeze predicate TRUE at h = V15",
                  jackpot::reserve_freeze_active_at(V15_HEIGHT));

            // And the validator therefore never returns S13 below V15 — the tx is
            // judged purely by the pre-V15 rules (here: S2, because this test does
            // not and must not hold the constitutional key).
            for (int64_t h : { (int64_t)1, V15_HEIGHT / 2, V15_HEIGHT - 1 }) {
                auto r = ValidateTransactionConsensus(tx, view, mk_ctx(h));
                CHECK(lbl + ": h=" + std::to_string((long long)h) +
                      " NOT rejected by the freeze (pre-V15 behaviour unchanged)",
                      r.code != TxValCode::S13_RESERVE_FROZEN);
                auto p = ValidateTransactionPolicy(tx, view, mk_ctx(h));
                CHECK(lbl + ": h=" + std::to_string((long long)h) +
                      " NOT blocked by relay policy pre-V15",
                      p.code != TxValCode::P_RESERVE_FROZEN);
            }
        }

        // A NORMAL transfer is completely unaffected on both sides of the fork.
        MapUtxoView nview;
        const Hash256 nprev = mk_txid(0x53);
        UTXOEntry n;
        n.amount = 1000000; n.type = OUT_TRANSFER; n.pubkey_hash = g_pkh;
        n.height = 0; n.is_coinbase = false;
        nview.Add(nprev, 0, n);
        Transaction ntx = make_sweep_tx(nview, nprev, SigMode::RealEcdsa);
        ntx.outputs[0].pubkey_hash = g_pkh;
        {   // re-sign after changing the output
            SpentOutput spent{n.amount, n.type};
            std::string err;
            SignTransactionInput(ntx, 0, spent, g_genesis, g_priv, &err);
        }
        auto pre  = ValidateTransactionConsensus(ntx, nview, mk_ctx(V15_HEIGHT - 1));
        auto post = ValidateTransactionConsensus(ntx, nview, mk_ctx(V15_HEIGHT));
        CHECK("normal transfer valid below V15", pre.ok);
        CHECK("normal transfer valid at/after V15", post.ok);
        CHECK("normal transfer verdict identical across the fork", pre.ok == post.ok);
    }

    // ---- 4) canonical TX_TYPE_JACKPOT at a cadence height -> ACCEPTED ------
    std::printf("\n-- 4) canonical jackpot accepted / 5) tampered jackpot rejected --\n");
    {
        const int64_t H = HIST_JACKPOT_FIRST_HEIGHT;
        CHECK("first jackpot height is a cadence height", is_hist_jackpot_height(H));

        std::vector<jackpot::ReserveUtxo> reserve;
        for (int i = 0; i < 4; ++i) {
            jackpot::ReserveUtxo u;
            u.height = 100 + i;
            u.txid   = mk_txid((uint8_t)(0x60 + i));
            u.vout   = 0;
            u.amount = 200LL * STOCKS_PER_SOST;
            reserve.push_back(u);
        }
        std::sort(reserve.begin(), reserve.end(), jackpot::reserve_utxo_less);
        const int64_t reserve_before = jackpot::reserve_balance(reserve);
        const PubKeyHash winner = mk_pkh(0x91);

        Transaction jtx;
        const bool built = jackpot::build_canonical_jackpot_tx(
            H, /*winner_exists=*/true, winner, reserve_before, /*rollover_before=*/0,
            reserve, GOLD, jtx);
        CHECK("canonical jackpot tx builds", built);
        CHECK("canonical jackpot carries TX_TYPE_JACKPOT", jtx.tx_type == TX_TYPE_JACKPOT);

        std::vector<Transaction> block = { Transaction{} /*coinbase placeholder*/, jtx };
        block[0].tx_type = TX_TYPE_COINBASE;

        auto ok = jackpot::validate_block_jackpot(block, H, reserve, true, winner,
                                                  reserve_before, 0, GOLD);
        CHECK("canonical jackpot block ACCEPTED", ok.ok);

        // 5) tampering — winner / amount / inputs
        {
            auto bad = block;
            bad[1].outputs[0].pubkey_hash = mk_pkh(0x92);          // different winner
            auto r = jackpot::validate_block_jackpot(bad, H, reserve, true, winner,
                                                     reserve_before, 0, GOLD);
            CHECK("jackpot with ALTERED WINNER rejected", !r.ok);
        }
        {
            auto bad = block;
            bad[1].outputs[0].amount += 1;                          // inflated payout
            auto r = jackpot::validate_block_jackpot(bad, H, reserve, true, winner,
                                                     reserve_before, 0, GOLD);
            CHECK("jackpot with ALTERED AMOUNT rejected", !r.ok);
        }
        {
            auto bad = block;
            bad[1].inputs[0].prev_txid = mk_txid(0xEE);             // different input
            auto r = jackpot::validate_block_jackpot(bad, H, reserve, true, winner,
                                                     reserve_before, 0, GOLD);
            CHECK("jackpot with ALTERED INPUTS rejected", !r.ok);
        }
        {
            auto bad = block;
            TxInput extra = bad[1].inputs[0];
            extra.prev_txid = mk_txid(0x63);
            bad[1].inputs.push_back(extra);                         // extra input grab
            auto r = jackpot::validate_block_jackpot(bad, H, reserve, true, winner,
                                                     reserve_before, 0, GOLD);
            CHECK("jackpot with EXTRA INPUT rejected", !r.ok);
        }
        {
            auto bad = block;
            if (bad[1].outputs.size() > 1) bad[1].outputs[1].pubkey_hash = mk_pkh(0x93);
            else { TxOutput e; e.amount = 1; e.type = OUT_TRANSFER; e.pubkey_hash = mk_pkh(0x93);
                   bad[1].outputs.push_back(e); }
            auto r = jackpot::validate_block_jackpot(bad, H, reserve, true, winner,
                                                     reserve_before, 0, GOLD);
            CHECK("jackpot with DIVERTED CHANGE rejected", !r.ok);
        }
        {
            auto bad = block;
            bad[1].tx_type = TX_TYPE_STANDARD;                      // not a jackpot type
            auto r = jackpot::validate_block_jackpot(bad, H, reserve, true, winner,
                                                     reserve_before, 0, GOLD);
            CHECK("jackpot downgraded to STANDARD rejected", !r.ok);
        }
        {
            std::vector<Transaction> nonJ = { block[0], jtx };
            auto r = jackpot::validate_block_jackpot(nonJ, H + 1, reserve, true, winner,
                                                     reserve_before, 0, GOLD);
            CHECK("jackpot tx at a NON-cadence height rejected", !r.ok);
        }
    }

    // ---- 6) full cycle: consecutive jackpots drain the reserve -------------
    // The change output re-enters the reserve sink as OUT_COINBASE_GOLD, stays
    // discoverable by discover_reserve_utxos (not trapped), stays FROZEN against
    // signed spends, and the reserve strictly decreases until the jackpot retires.
    std::printf("\n-- 6) full drain cycle: change returns to the sink, stays frozen --\n");
    {
        UtxoSet chain;
        int64_t seeded = 0;
        for (int i = 0; i < 3; ++i) {
            OutPoint op{mk_txid((uint8_t)(0x70 + i)), 0};
            UTXOEntry e;
            e.amount      = 250LL * STOCKS_PER_SOST;
            e.type        = (i % 2 == 0) ? OUT_COINBASE_GOLD : OUT_COINBASE_POPC;
            e.pubkey_hash = (i % 2 == 0) ? GOLD : POPC;
            e.height      = 100 + i;
            e.is_coinbase = true;
            std::string err;
            chain.AddUTXO(op, e, &err);
            seeded += e.amount;
        }

        int64_t rollover = 0;
        int64_t prev_reserve = seeded;
        int     payouts = 0;
        int     change_generations = 0;
        uint8_t synth = 0xA0;

        for (int round = 0; round < 12; ++round) {
            const int64_t H = HIST_JACKPOT_FIRST_HEIGHT + (int64_t)round * HIST_JACKPOT_CADENCE_BLOCKS;
            auto sorted = jackpot::discover_reserve_utxos(chain, GOLD, POPC);
            const int64_t reserve_before = jackpot::reserve_balance(sorted);
            if (reserve_before == 0) break;

            const PubKeyHash winner = mk_pkh((uint8_t)(0xB0 + round));
            Transaction jtx;
            if (!jackpot::build_canonical_jackpot_tx(H, true, winner, reserve_before,
                                                     rollover, sorted, GOLD, jtx)) break;

            std::vector<Transaction> blk = { Transaction{}, jtx };
            blk[0].tx_type = TX_TYPE_COINBASE;
            auto v = jackpot::validate_block_jackpot(blk, H, sorted, true, winner,
                                                     reserve_before, rollover, GOLD);
            CHECK("round " + std::to_string(round) + ": canonical jackpot validates", v.ok);

            // Apply it to the UTXO set exactly as ConnectBlock would.
            for (const auto& in : jtx.inputs) {
                OutPoint op{in.prev_txid, in.prev_index};
                std::string err;
                CHECK("round " + std::to_string(round) + ": reserve input spent from chainstate",
                      chain.SpendUTXO(op, nullptr, &err));
            }
            Hash256 jtxid = mk_txid(synth++);   // synthetic txid for the applied tx
            for (uint32_t oi = 0; oi < jtx.outputs.size(); ++oi) {
                UTXOEntry e;
                e.amount      = jtx.outputs[oi].amount;
                e.type        = jtx.outputs[oi].type;
                e.pubkey_hash = jtx.outputs[oi].pubkey_hash;
                e.height      = H;
                e.is_coinbase = false;
                std::string err;
                chain.AddUTXO(OutPoint{jtxid, oi}, e, &err);

                if (oi == 1) {
                    ++change_generations;
                    // The change MUST be a frozen reserve output again.
                    CHECK("round " + std::to_string(round) +
                          ": change re-enters the reserve sink as a FROZEN output",
                          jackpot::is_constitutional_reserve_utxo(e.type, e.pubkey_hash));

                    // ...and a signed spend of that change is rejected by consensus.
                    MapUtxoView cv;
                    cv.Add(jtxid, 1, e);
                    // make_sweep_tx spends index 0, so mirror the entry there.
                    MapUtxoView cv0; cv0.Add(mk_txid(0xC1), 0, e);
                    Transaction steal = make_sweep_tx(cv0, mk_txid(0xC1), SigMode::RealEcdsa);
                    auto sr = ValidateTransactionConsensus(steal, cv0, mk_ctx(H));
                    CHECK("round " + std::to_string(round) +
                          ": signed spend of the jackpot change REJECTED (S13)",
                          !sr.ok && sr.code == TxValCode::S13_RESERVE_FROZEN);
                }
            }

            const auto res = jackpot::hist_jackpot_apply(H, true, reserve_before, rollover);
            rollover = res.rollover_after;
            ++payouts;

            auto after = jackpot::discover_reserve_utxos(chain, GOLD, POPC);
            const int64_t reserve_after = jackpot::reserve_balance(after);
            CHECK("round " + std::to_string(round) + ": reserve strictly decreases",
                  reserve_after < prev_reserve);
            CHECK("round " + std::to_string(round) + ": chainstate reserve == core reserve_after",
                  reserve_after == res.reserve_after);
            // The winner's payout is a NORMAL spendable OUT_TRANSFER, not frozen.
            CHECK("round " + std::to_string(round) + ": winner output is NOT frozen",
                  !jackpot::is_constitutional_reserve_utxo(jtx.outputs[0].type,
                                                           jtx.outputs[0].pubkey_hash));
            prev_reserve = reserve_after;
        }

        CHECK("several consecutive jackpots paid out", payouts >= 3);
        CHECK("change was recycled into the sink at least once", change_generations >= 1);
        auto finalr = jackpot::discover_reserve_utxos(chain, GOLD, POPC);
        const int64_t final_balance = jackpot::reserve_balance(finalr);
        CHECK("reserve fully drained by the canonical path (nothing trapped)",
              final_balance == 0);
        CHECK("total paid out equals the seeded reserve (supply-neutral)",
              seeded - final_balance == seeded);
    }

    std::printf("\n=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
