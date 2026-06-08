// test_popc_v15.cpp — V15 PoPC Model A/B pure base (P1).
// Unit tests only: commitment id, bond/term, lifecycle (expiry/audit/slash/settle),
// attestation sign→verify (Model A self-signed + Model B supervisor) and rejections,
// pubkey→owner binding, and the activation gate (mainnet deferred no-op).
#include "sost/popc_v15.h"
#include <secp256k1.h>
#include <cstdio>
#include <vector>
using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(n,c) do{ if(c){++g_pass;std::printf("  ok  %s\n",n);} else {++g_fail;std::printf("  *** FAIL: %s\n",n);} }while(0)

int main(){
    std::printf("=== PoPC V15 Model A/B — pure base (P1) ===\n");

    secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN|SECP256K1_CONTEXT_VERIFY);
    // owner (Model A) key
    unsigned char sk[32]; for(int i=0;i<32;i++) sk[i]=(unsigned char)(i+3);
    secp256k1_pubkey pk; secp256k1_ec_pubkey_create(ctx,&pk,sk);
    unsigned char comp[33]; size_t cl=33; secp256k1_ec_pubkey_serialize(ctx,comp,&cl,&pk,SECP256K1_EC_COMPRESSED);
    std::vector<uint8_t> ownerPub(comp,comp+cl);
    PubKeyHash ownerPkh = popc_v15_pubkey_pkh(ownerPub);
    // supervisor (Model B) key — different
    unsigned char sk2[32]; for(int i=0;i<32;i++) sk2[i]=(unsigned char)(200-i);
    secp256k1_pubkey pk2; secp256k1_ec_pubkey_create(ctx,&pk2,sk2);
    unsigned char comp2[33]; size_t cl2=33; secp256k1_ec_pubkey_serialize(ctx,comp2,&cl2,&pk2,SECP256K1_EC_COMPRESSED);
    std::vector<uint8_t> supPub(comp2,comp2+cl2);

    PopcV15Commitment c;
    c.model=(uint8_t)PopcModel::A; c.owner_pkh=ownerPkh; c.gold_token="PAXG";
    c.gold_amount_mg=311035; c.bond_stocks=POPC_V15_MIN_BOND_STOCKS;
    c.start_height=1000; c.end_height=1000+POPC_V15_MIN_TERM_BLOCKS; c.audit_interval=720;

    // commitment id — deterministic + binds fields
    { auto id1=popc_v15_commitment_id(c), id2=popc_v15_commitment_id(c);
      PopcV15Commitment d=c; d.gold_amount_mg+=1; auto id3=popc_v15_commitment_id(d);
      CHECK("commitment id deterministic", id1==id2);
      CHECK("commitment id binds fields",  !(id1==id3)); }

    // bond + term
    CHECK("min bond ok at floor",  popc_v15_min_bond_ok(POPC_V15_MIN_BOND_STOCKS)==true);
    CHECK("min bond rejects below", popc_v15_min_bond_ok(POPC_V15_MIN_BOND_STOCKS-1)==false);
    CHECK("term ok at minimum",     popc_v15_term_ok(c.start_height,c.end_height)==true);
    CHECK("term rejects too short", popc_v15_term_ok(1000,1000+10)==false);

    // expiry / audit schedule
    CHECK("not expired before end", popc_v15_is_expired(c,c.end_height-1)==false);
    CHECK("expired at end",         popc_v15_is_expired(c,c.end_height)==true);
    CHECK("audit due at start+interval", popc_v15_audit_due(c.start_height,c.audit_interval,c.start_height+c.audit_interval)==true);
    CHECK("audit not due off-interval",  popc_v15_audit_due(c.start_height,c.audit_interval,c.start_height+c.audit_interval+1)==false);
    CHECK("next audit strictly after h", popc_v15_next_audit(c.start_height,c.audit_interval,c.start_height+1)==c.start_height+c.audit_interval);

    // slash eligibility (challenge at audit_h, no response within grace)
    { int64_t ah=2000;
      CHECK("no challenge -> not slashable", popc_v15_slash_eligible(0,0,9999)==false);
      CHECK("answered in grace -> not slashable", popc_v15_slash_eligible(ah,ah+1,ah+POPC_V15_AUDIT_GRACE_BLOCKS+50)==false);
      CHECK("no response, within grace -> not yet", popc_v15_slash_eligible(ah,0,ah+POPC_V15_AUDIT_GRACE_BLOCKS)==false);
      CHECK("no response, past grace -> slashable", popc_v15_slash_eligible(ah,0,ah+POPC_V15_AUDIT_GRACE_BLOCKS+1)==true); }

    // settlement
    CHECK("settle eligible at end (active)", popc_v15_settle_eligible(PopcV15Status::Active,c,c.end_height)==true);
    CHECK("settle not eligible before end",  popc_v15_settle_eligible(PopcV15Status::Active,c,c.end_height-1)==false);
    CHECK("settle not eligible if slashed",   popc_v15_settle_eligible(PopcV15Status::Slashed,c,c.end_height)==false);

    // pubkey → owner binding (Model A self-attestation)
    CHECK("owner pubkey binds to owner pkh", popc_v15_pubkey_is_owner(ownerPub,ownerPkh)==true);
    CHECK("supervisor pubkey is NOT owner",  popc_v15_pubkey_is_owner(supPub,ownerPkh)==false);

    // attestation sign → verify
    Bytes32 cid=popc_v15_commitment_id(c);
    auto sign=[&](unsigned char* key, int64_t bal, int64_t h){
        Bytes32 dg=popc_v15_attest_digest(cid,bal,h);
        secp256k1_ecdsa_signature s; secp256k1_ecdsa_sign(ctx,&s,dg.data(),key,nullptr,nullptr);
        unsigned char out[64]; secp256k1_ecdsa_signature_serialize_compact(ctx,out,&s);
        return std::vector<uint8_t>(out,out+64);
    };
    { auto sig=sign(sk,311035,1720);
      CHECK("Model A: owner-signed attestation verifies", popc_v15_verify_attestation(cid,311035,1720,ownerPub,sig)==true);
      CHECK("wrong balance in verify -> fail", popc_v15_verify_attestation(cid,311036,1720,ownerPub,sig)==false);
      CHECK("wrong height in verify -> fail",  popc_v15_verify_attestation(cid,311035,1721,ownerPub,sig)==false);
      CHECK("wrong pubkey (supervisor) -> fail", popc_v15_verify_attestation(cid,311035,1720,supPub,sig)==false);
      auto bad=sig; bad[5]^=0xFF;
      CHECK("tampered signature -> fail", popc_v15_verify_attestation(cid,311035,1720,ownerPub,bad)==false); }
    { auto sig=sign(sk2,311035,1720);   // Model B: supervisor signs
      CHECK("Model B: supervisor-signed verifies vs supervisor key", popc_v15_verify_attestation(cid,311035,1720,supPub,sig)==true);
      CHECK("Model B sig does NOT verify vs owner key", popc_v15_verify_attestation(cid,311035,1720,ownerPub,sig)==false); }

    // activation gate (P1 is pure base — mainnet must be deferred)
#ifdef SOST_TESTNET_FORKS
    CHECK("testnet: active at V15_HEIGHT", popc_v15_active_at(V15_HEIGHT)==true);
    CHECK("testnet: inactive before V15", popc_v15_active_at(V15_HEIGHT-1)==false);
#else
    CHECK("mainnet: deferred at 20000",    popc_v15_active_at(20000)==false);
    CHECK("mainnet: deferred at INT64_MAX-1", popc_v15_active_at(INT64_MAX-1)==false);
#endif

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
