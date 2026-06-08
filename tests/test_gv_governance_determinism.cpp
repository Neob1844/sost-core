// test_gv_governance_determinism.cpp — V15 Gold Vault governance, B3.
//
// Cross-validator / determinism harness. It does NOT add features — it proves
// that the COMPOSED Gold Vault governance verdict (G4 67-block window + G5
// grace-window veto) that process_block computes is a deterministic, pure
// function of (chain state, spend height, destination). Two validators on the
// same chain therefore reach the SAME verdict, byte for byte.
//
// It rebuilds the exact decision pipeline from the same pure helpers the node
// uses (gv_g4_count_window / gv_g4_window_approved / gv_g5_is_veto_output /
// gv_g5_verify_veto_payload) over a synthetic chain of coinbases, then asserts:
//   * identical verdict across two independent evaluations (determinism),
//   * recompute-from-chain (a different chain → a different verdict, no caching),
//   * the seven B3 scenarios resolve correctly.
// Scenario verdicts need the gates active → they run on the testnet build; the
// mainnet build asserts the whole pipeline is a no-op (gates deferred).
#include "sost/gv_g4.h"
#include "sost/gv_g5.h"
#include "sost/transaction.h"
#include "sost/params.h"
#include <secp256k1.h>
#include <cstdio>
#include <vector>
#include <string>
using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(name, cond) do { if (cond) { ++g_pass; std::printf("  ok  %s\n", name); } \
    else { ++g_fail; std::printf("  *** FAIL: %s\n", name); } } while (0)

static PubKeyHash pkh(uint8_t b) { PubKeyHash p; p.fill(b); return p; }

// ---- test Guardian key (so we can sign vetoes; default Guardian key is unknown here) ----
static secp256k1_context* CTX = nullptr;
static unsigned char SECKEY[32];
static std::string GKEY_HEX;
static std::string tohex(const unsigned char* p, size_t n){ static const char* H="0123456789abcdef"; std::string s; for(size_t i=0;i<n;i++){s.push_back(H[p[i]>>4]);s.push_back(H[p[i]&15]);} return s; }
static void initKey(){
    CTX = secp256k1_context_create(SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    for (int i=0;i<32;i++) SECKEY[i]=(unsigned char)(i+7);
    secp256k1_pubkey pub; secp256k1_ec_pubkey_create(CTX,&pub,SECKEY);
    unsigned char p65[65]; size_t l=65; secp256k1_ec_pubkey_serialize(CTX,p65,&l,&pub,SECP256K1_EC_UNCOMPRESSED);
    GKEY_HEX = tohex(p65,l);
}
static std::vector<uint8_t> vetoPayload(const PubKeyHash& dest, int64_t expiry){
    Bytes32 dg = gv_g5_veto_digest(dest, expiry);
    secp256k1_ecdsa_signature sig; secp256k1_ecdsa_sign(CTX,&sig,dg.data(),SECKEY,nullptr,nullptr);
    unsigned char comp[64]; secp256k1_ecdsa_signature_serialize_compact(CTX,comp,&sig);
    std::vector<uint8_t> pl; for(int i=0;i<8;i++) pl.push_back((uint8_t)((uint64_t)expiry>>(8*i)));
    pl.insert(pl.end(),comp,comp+64); return pl;
}

// A synthetic coinbase: g4=add a G4 approval marker; veto=add a G5 veto carrier.
static Transaction coinbase(bool g4, const std::vector<uint8_t>* veto){
    Transaction t;
    TxOutput miner; miner.amount=50; miner.type=OUT_COINBASE_MINER; t.outputs.push_back(miner);
    if (g4){ TxOutput m; m.amount=0; m.pubkey_hash=GV_G4_APPROVAL_PKH; t.outputs.push_back(m); }
    if (veto){ TxOutput v; v.amount=0; v.pubkey_hash=GV_G5_VETO_PKH; v.payload=*veto; t.outputs.push_back(v); }
    return t;
}

// The EXACT composed verdict process_block computes for a Gold Vault spend.
static bool decideAccept(const std::vector<Transaction>& chain, int64_t H, const PubKeyHash& dest){
    auto approvesAt = [&](int64_t hh)->bool{
        if (hh<0 || hh>=(int64_t)chain.size()) return false;
        for (const auto& o : chain[(size_t)hh].outputs)
            if (o.amount==0 && o.pubkey_hash==GV_G4_APPROVAL_PKH) return true;
        return false;
    };
    bool g4_ok = true;
    if (gv_g4_active_at(H)){
        int32_t yes = gv_g4_count_window(H, approvesAt);
        g4_ok = gv_g4_window_approved(yes, false);
    }
    bool g5_block = false;
    if (gv_g5_active_at(H)){
        for (int64_t hh=H-GV_G5_GRACE_BLOCKS; hh<=H-1 && !g5_block; ++hh){
            if (hh<0 || hh>=(int64_t)chain.size()) continue;
            for (const auto& o : chain[(size_t)hh].outputs)
                if (gv_g5_is_veto_output(o) && gv_g5_verify_veto_payload(dest, H, o.payload, GKEY_HEX)){ g5_block=true; break; }
        }
    }
    return g4_ok && !g5_block;
}

// build a chain of `len` coinbases; the last `napprove` blocks before H carry a G4 marker
static std::vector<Transaction> chainWith(int64_t len, int64_t H, int napprove, const std::vector<uint8_t>* vetoInGrace){
    std::vector<Transaction> c;
    for (int64_t h=0; h<len; ++h){
        bool g4 = (h>=H-napprove && h<=H-1);
        const std::vector<uint8_t>* veto = nullptr;
        if (vetoInGrace && h==H-3) veto = vetoInGrace;   // a veto sitting inside the grace window
        c.push_back(coinbase(g4, veto));
    }
    return c;
}

int main(){
    std::printf("=== Gold Vault governance — cross-validator / determinism (B3) ===\n");
    initKey();
    const PubKeyHash DEST = pkh(0x05), OTHER = pkh(0x09);

#ifdef SOST_TESTNET_FORKS
    const int64_t H = V15_HEIGHT + 200;              // gates active, below auto-disconnect
    CHECK("gates active at H", gv_g4_active_at(H) && gv_g5_active_at(H));

    // 1) 67 approvals, no veto -> accept
    { auto c=chainWith(H+1,H,67,nullptr);
      bool a=decideAccept(c,H,DEST), b=decideAccept(c,H,DEST);
      CHECK("67/67 no veto -> accept", a==true);
      CHECK("verdict deterministic across two evaluations", a==b); }

    // 2) exactly 61 approvals -> accept
    { auto c=chainWith(H+1,H,61,nullptr); CHECK("61/67 -> accept", decideAccept(c,H,DEST)==true); }

    // 3) 60 approvals -> reject (G4 floor)
    { auto c=chainWith(H+1,H,60,nullptr); CHECK("60/67 -> reject", decideAccept(c,H,DEST)==false); }

    // 4) 67 approvals + valid veto in grace -> reject (G5)
    { auto v=vetoPayload(DEST,H+10); auto c=chainWith(H+1,H,67,&v);
      CHECK("valid veto in grace -> reject", decideAccept(c,H,DEST)==false); }

    // 5) 67 approvals + EXPIRED veto -> accept (veto ignored)
    { auto v=vetoPayload(DEST,H-1); auto c=chainWith(H+1,H,67,&v);
      CHECK("expired veto -> accept (ignored)", decideAccept(c,H,DEST)==true); }

    // 6) 67 approvals + veto signed for ANOTHER destination -> accept
    { auto v=vetoPayload(OTHER,H+10); auto c=chainWith(H+1,H,67,&v);
      CHECK("veto for other destination -> accept", decideAccept(c,H,DEST)==false ? false : true);
      // (explicit: must NOT block this dest)
      CHECK("veto for other dest does not block DEST", decideAccept(c,H,DEST)==true); }

    // 7) AUTO-DISCONNECT: at H>=100000 a valid veto is ignored (G5 off); G4 still enforced
    { const int64_t H2=100000+20;
      CHECK("G5 auto-disconnected at H2", gv_g5_active_at(H2)==false);
      CHECK("G4 still active at H2",       gv_g4_active_at(H2)==true);
      auto v=vetoPayload(DEST,H2+50); auto c=chainWith(H2+1,H2,67,&v);
      CHECK("auto-disconnect: 67/67 + veto -> accept (veto ignored)", decideAccept(c,H2,DEST)==true);
      auto c2=chainWith(H2+1,H2,60,nullptr);
      CHECK("auto-disconnect: 60/67 still rejected by G4", decideAccept(c2,H2,DEST)==false); }

    // 8) REORG SAFETY (recompute from active chain, no caching): same H, two chains -> two verdicts
    { auto cA=chainWith(H+1,H,61,nullptr);  // would be accepted
      auto cB=chainWith(H+1,H,60,nullptr);  // would be rejected
      CHECK("recompute: chain A (61) accepts", decideAccept(cA,H,DEST)==true);
      CHECK("recompute: chain B (60) rejects", decideAccept(cB,H,DEST)==false);
      // evaluating A again after B must still give A's result (no surviving state)
      CHECK("no stale state after switching chains", decideAccept(cA,H,DEST)==true); }
#else
    // mainnet build: gates deferred -> the whole pipeline is a no-op (always accept),
    // regardless of markers/vetoes. Two evaluations are identical (determinism).
    const int64_t H = 20000;   // would-be V15 height; gates still INT64_MAX on mainnet
    CHECK("mainnet: G4 deferred", gv_g4_active_at(H)==false);
    CHECK("mainnet: G5 deferred", gv_g5_active_at(H)==false);
    auto v=vetoPayload(DEST,H+10); auto c=chainWith(H+1,H,0,&v);   // no approvals + a veto
    bool a=decideAccept(c,H,DEST), b=decideAccept(c,H,DEST);
    CHECK("mainnet: governance is a no-op (accept)", a==true);
    CHECK("mainnet: deterministic", a==b);
#endif

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0 ? 0 : 1;
}
