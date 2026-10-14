// test_multisig_psst.cpp — offline multisig workflow (sost-psst-v1), NON-CONSENSUS.
//
// Usage: test-multisig-psst psst            library tests (ctest multisig-psst)
//        test-multisig-psst emit <dir>      writes policy35.json + tx.json for tests/cli/test_multisig_cli.sh
#include "sost/multisig_psst.h"
#include "sost/address.h"
#include "sost/params.h"
#include "sost/types.h"

#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::psst;

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { if (cond) { ++g_pass; } else { ++g_fail; \
    std::printf("  FAIL: %s  [%s:%d]\n", std::string(msg).c_str(), __FILE__, __LINE__); } } while (0)

static PrivKey priv(uint64_t n) { PrivKey k{}; for (int i = 0; i < 8; ++i) k[31 - i] = (Byte)(n >> (8 * i)); return k; }
static PubKey33 pub(uint64_t n) { PubKey p{}; DerivePublicKey(priv(n), p); return p; }
static const Hash256 GEN = from_hex("6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");

static Psst vault_spend(MsNetwork net, uint8_t m, const std::vector<uint64_t>& privs, int64_t amount = 10'000'000'000LL) {
    Policy pol; std::vector<PubKey33> ks; for (auto p : privs) ks.push_back(pub(p));
    MakePolicy(net, m, ks, pol);
    Input in; in.txid = from_hex("aa000000000000000000000000000000000000000000000000000000000000bb"); in.vout = 3;
    in.spent.amount = amount; in.spent.type = OUT_MULTISIG; in.spent.pubkey_hash = pol.msh;
    in.auth_kind = AUTH_MULTISIG; in.m = pol.m; in.keys = pol.keys;
    TxOutput pay; pay.amount = 1'000'000'000LL; pay.type = OUT_TRANSFER; pay.pubkey_hash = ComputePubKeyHash(pub(9));
    TxOutput ch; ch.amount = amount - 1'000'000'000LL - 50'000; ch.type = OUT_MULTISIG; ch.pubkey_hash = pol.msh;
    Psst p; std::string e;
    if (!Build(net, GEN, {in}, {pay, ch}, p, &e)) std::printf("build failed: %s\n", e.c_str());
    return p;
}

static void t_psst() {
    // ---- policy file round trip ----
    Policy pol; std::string e;
    CHECK(MakePolicy(MsNetwork::MAINNET, 3, {pub(1), pub(2), pub(3), pub(4), pub(5)}, pol, &e), "MakePolicy 3-of-5");
    CHECK(pol.address == "sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7", "policy address == spec vector");
    Policy back;
    CHECK(PolicyFromJson(PolicyToJson(pol), back, &e) && back.msh == pol.msh && back.keys == pol.keys, "policy JSON round trip");
    { std::string j = PolicyToJson(pol); auto at = j.find(pol.address); j[at + pol.address.size() - 1] = 'q';
      CHECK(!PolicyFromJson(j, back, &e), "policy file with altered address rejected"); }
    { Policy dup; CHECK(!MakePolicy(MsNetwork::MAINNET, 2, {pub(1), pub(1), pub(2)}, dup, &e), "createmultisig duplicate key refused"); }

    // ---- PSST round trip ----
    Psst p = vault_spend(MsNetwork::MAINNET, 3, {1, 2, 3, 4, 5});
    Psst q;
    CHECK(FromJson(ToJson(p), q, &e), "psst_round_trip: " + e);
    CHECK(ToJson(q) == ToJson(p), "psst JSON is canonical (round trip byte-identical)");
    CHECK(FinalSize(p) == 4 + 1 + 1 + 400 + 1 + 31 + 31 && FinalSigchecks(p) == 3, "FinalSize / FinalSigchecks of a 1-in 3-of-5 spend");

    // ---- independent signers ----
    Psst a = q, b = q, c = q, d = q;
    CHECK(Sign(a, {priv(1)}) == 1 && Sign(b, {priv(2)}) == 1 && Sign(c, {priv(5)}) == 1 && Sign(d, {priv(4)}) == 1, "4 independent signers add 1 sig each");
    CHECK(Sign(a, {priv(1)}) == 0, "re-signing with the same key adds nothing");
    CHECK(Sign(a, {priv(9)}) == 0, "a key outside the policy adds nothing");
    Psst ra; CHECK(FromJson(ToJson(a), ra, &e) && ra.inputs[0].sigs.size() == 1, "signed PSST round-trips with its signature");
    auto r1 = Verify(a, MULTISIG_HEIGHT);
    CHECK(!r1.complete && !r1.valid, "verifytx: 1 of 3 -> incomplete");

    // ---- combine ----
    Psst ab; CHECK(Combine({a, b}, ab, &e) && ab.inputs[0].sigs.size() == 2, "combine 2 files -> 2 sigs");
    CHECK(!Verify(ab, MULTISIG_HEIGHT).complete, "2 of 3 still incomplete");
    Psst abc; CHECK(Combine({a, b, c}, abc, &e), "combine 3 files: " + e);
    auto rep = Verify(abc, MULTISIG_HEIGHT);
    CHECK(rep.complete && rep.valid && rep.reason == "ok", "verifytx: 3 of 3 complete + consensus-valid: " + rep.reason);
    CHECK(rep.size == FinalSize(abc) && rep.fee == 50'000 && rep.sigchecks == 3, "report size/fee/sigchecks");
    // lowest key indexes are selected deterministically when more than M are present
    Psst all4; CHECK(Combine({a, b, c, d}, all4, &e) && all4.inputs[0].sigs.size() == 4, "combine 4 sigs");
    bool comp = false; Transaction t4 = Assemble(all4, &comp);
    std::vector<uint8_t> idx; for (const auto& s : t4.inputs[0].ms_sigs) idx.push_back(s.key_index);
    std::vector<uint8_t> want; for (const auto& kv : all4.inputs[0].sigs) { if (want.size() < 3) want.push_back(kv.first); }
    CHECK(comp && idx == want && idx.size() == 3, "combinetx_selects_lowest_indexes");
    CHECK(Verify(all4, MULTISIG_HEIGHT).valid, "4-signature PSST assembles to a valid M-sig tx");
    // a different subset gives a different txid but the same effect (D6)
    Psst bcd; Combine({b, c, d}, bcd, &e);
    CHECK(Verify(bcd, MULTISIG_HEIGHT).valid && Verify(bcd, MULTISIG_HEIGHT).txid != rep.txid, "other M-subset: valid, different txid");

    // ---- tampering ----
    {   // tampered unsigned_hex (output amount) -> fee mismatch / signature mismatch
        std::string j = ToJson(abc);
        std::string amt_le = "00ca9a3b00000000";   // 1,000,000,000 LE
        auto at = j.find(amt_le);
        CHECK(at != std::string::npos, "located payment amount in unsigned_hex");
        if (at != std::string::npos) { j.replace(at, amt_le.size(), "01ca9a3b00000000"); }
        Psst t; CHECK(!FromJson(j, t, &e), "tampered_unsigned_hex rejected: " + e);
    }
    {   // tampered declared spent amount (fee lie) without touching the template
        std::string j = ToJson(abc);
        auto at = j.find("\"amount\": 10000000000");
        j.replace(at, std::string("\"amount\": 10000000000").size(), "\"amount\": 10000000001");
        Psst t; CHECK(!FromJson(j, t, &e), "lying spent amount in the file rejected: " + e);
    }
    {   // a signature that does not belong to the template
        std::string j = ToJson(a);
        auto at = j.find("\"signatures\": {\"");
        auto s0 = j.find(": \"", at + 16) + 3;
        j[s0 + 10] = (j[s0 + 10] == 'a') ? 'b' : 'a';
        Psst t; CHECK(!FromJson(j, t, &e), "corrupted signature rejected on load: " + e);
    }
    {   // wrong chain_id for the declared network (signtx refuses)
        std::string j = ToJson(q);
        std::string m = HexStr(CHAIN_ID_MAINNET.data(), 32), tn = HexStr(CHAIN_ID_TESTNET.data(), 32);
        j.replace(j.find(m), m.size(), tn);
        Psst t; CHECK(!FromJson(j, t, &e) && e.find("chain_id") != std::string::npos, "wrong_chain_id_refused_by_signtx: " + e);
    }
    {   // mismatched policy in combinetx
        Psst other = vault_spend(MsNetwork::MAINNET, 2, {1, 2, 3, 4, 5});
        Sign(other, {priv(3)});
        Psst out; CHECK(!Combine({a, other}, out, &e), "mismatched_policy_in_combinetx rejected: " + e);
        Psst net2 = vault_spend(MsNetwork::DEVNET, 3, {1, 2, 3, 4, 5});
        CHECK(!Combine({a, net2}, out, &e), "combinetx across networks rejected: " + e);
    }
    {   // a testnet-signed signature never validates on mainnet (CHAIN_ID)
        Psst tn = vault_spend(MsNetwork::TESTNET, 3, {1, 2, 3, 4, 5});
        Sign(tn, {priv(1), priv(2), priv(3)});
        auto rt = Verify(tn, MULTISIG_HEIGHT);
        CHECK(rt.complete && rt.valid, "testnet PSST valid under its own CHAIN_ID");
        Psst forged = tn; forged.chain_id = CHAIN_ID_MAINNET; forged.net = MsNetwork::MAINNET;
        auto rf = Verify(forged, MULTISIG_HEIGHT);
        CHECK(rf.complete && !rf.valid, "same signatures relabelled mainnet are invalid (S18)");
    }
    // ---- funding (v2 single-sig inputs -> OUT_MULTISIG) ----
    {
        Input in; in.txid = from_hex("cc00000000000000000000000000000000000000000000000000000000000001"); in.vout = 0;
        in.spent.amount = 3'000'000'000LL; in.spent.type = OUT_TRANSFER; in.spent.pubkey_hash = ComputePubKeyHash(pub(7));
        TxOutput o; o.amount = 2'000'000'000LL; o.type = OUT_MULTISIG; o.pubkey_hash = pol.msh;
        TxOutput ch; ch.amount = 999'990'000LL; ch.type = OUT_TRANSFER; ch.pubkey_hash = in.spent.pubkey_hash;
        Psst f; CHECK(Build(MsNetwork::MAINNET, GEN, {in}, {o, ch}, f, &e), "build funding PSST");
        CHECK(Sign(f, {priv(8)}) == 0 && Sign(f, {priv(7)}) == 1, "only the owner key signs the single-sig input");
        auto rf = Verify(f, MULTISIG_HEIGHT);
        CHECK(rf.complete && rf.valid, "funding PSST valid: " + rf.reason);
        Psst f2; CHECK(FromJson(ToJson(f), f2, &e) && f2.inputs[0].single_signed, "signed single-sig input round-trips");
        // the builder refuses to put a multisig input on a non-0x50 output or vice versa
        Input bad = in; bad.auth_kind = AUTH_MULTISIG; bad.m = pol.m; bad.keys = pol.keys;
        Psst x; CHECK(!Build(MsNetwork::MAINNET, GEN, {bad}, {o}, x, &e), "builder: multisig input on OUT_TRANSFER refused");
        Input bad2 = in; bad2.spent.type = OUT_MULTISIG;
        CHECK(!Build(MsNetwork::MAINNET, GEN, {bad2}, {o}, x, &e), "builder: single-sig input on OUT_MULTISIG refused");
    }
    // ---- rotation: old 3-of-5 spends to a new 2-of-3 MSH ----
    {
        Policy np; MakePolicy(MsNetwork::MAINNET, 2, {pub(11), pub(12), pub(13)}, np);
        Psst r = vault_spend(MsNetwork::MAINNET, 3, {1, 2, 3, 4, 5});
        r.outputs = {}; TxOutput o; o.amount = 9'999'950'000LL; o.type = OUT_MULTISIG; o.pubkey_hash = np.msh; r.outputs.push_back(o);
        Sign(r, {priv(2), priv(4), priv(5)});
        auto rr = Verify(r, MULTISIG_HEIGHT);
        CHECK(rr.valid, "rotation PSST (old threshold signs, new MSH output) valid");
    }
}

static void emit(const std::string& dir) {
    Policy pol; MakePolicy(MsNetwork::MAINNET, 3, {pub(1), pub(2), pub(3), pub(4), pub(5)}, pol);
    std::ofstream(dir + "/policy35.json") << PolicyToJson(pol);
    std::ofstream(dir + "/tx.json") << ToJson(vault_spend(MsNetwork::MAINNET, 3, {1, 2, 3, 4, 5}));
    std::printf("emitted %s/policy35.json %s/tx.json\n", dir.c_str(), dir.c_str());
}

int main(int argc, char** argv) {
    std::string mode = argc > 1 ? argv[1] : "psst";
    if (mode == "emit" && argc > 2) { emit(argv[2]); return 0; }
    std::printf("=== multisig-psst ===\n");
    t_psst();
    std::printf("=== %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
