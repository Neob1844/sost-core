// test_popc_v15_authz.cpp — V15 PoPC P4c: carrier authorization.
//
// Closes the two holes found in the P4b review:
//   1. Register only declares (Pending); a valid Activate is required for Active.
//   2. Non-Activate carriers (Register/Renew/Suspend) must be signed by the OWNER
//      — a third party cannot inject events on a commitment they do not own; and
//      Slash/Settle are not carriable at all (derived deterministically).
#include "sost/popc_v15.h"
#include <secp256k1.h>
#include <cstdio>
#include <vector>
using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(n,c) do{ if(c){++g_pass;std::printf("  ok  %s\n",n);} else {++g_fail;std::printf("  *** FAIL: %s\n",n);} }while(0)
static Bytes32 id(uint8_t b){ Bytes32 x{}; x.fill(b); return x; }

int main(){
    std::printf("=== PoPC V15 P4c — carrier authorization ===\n");
    secp256k1_context* ctx=secp256k1_context_create(SECP256K1_CONTEXT_SIGN|SECP256K1_CONTEXT_VERIFY);

    // Owner key + a DIFFERENT (attacker) key.
    auto mkkey=[&](unsigned char seed, std::vector<uint8_t>& pub){
        unsigned char sk[32]; for(int i=0;i<32;i++) sk[i]=(unsigned char)(i+seed);
        secp256k1_pubkey pk; secp256k1_ec_pubkey_create(ctx,&pk,sk);
        unsigned char comp[33]; size_t cl=33; secp256k1_ec_pubkey_serialize(ctx,comp,&cl,&pk,SECP256K1_EC_COMPRESSED);
        pub.assign(comp,comp+33);
        std::vector<uint8_t> out(sk,sk+32); return out;
    };
    std::vector<uint8_t> ownerPub, attackerPub;
    auto ownerSk    = mkkey(7,  ownerPub);
    auto attackerSk = mkkey(99, attackerPub);
    PubKeyHash OWNER = popc_v15_pubkey_pkh(ownerPub);   // owner_pkh derived from the owner key
    const Bytes32 CID = id(0x42);
    const int64_t END = 50000;

    auto signWith=[&](const std::vector<uint8_t>& sk, const Bytes32& dg){
        secp256k1_ecdsa_signature s; secp256k1_ecdsa_sign(ctx,&s,dg.data(),sk.data(),nullptr,nullptr);
        unsigned char sig[64]; secp256k1_ecdsa_signature_serialize_compact(ctx,sig,&s);
        return std::vector<uint8_t>(sig,sig+64);
    };

    // ---- which events are carriable ----
    CHECK("Register carriable", popc_v15_event_is_carriable(PopcEventType::Register));
    CHECK("Activate carriable", popc_v15_event_is_carriable(PopcEventType::Activate));
    CHECK("Renew carriable",    popc_v15_event_is_carriable(PopcEventType::Renew));
    CHECK("Suspend carriable",  popc_v15_event_is_carriable(PopcEventType::Suspend));
    CHECK("Slash NOT carriable (derived only)",  !popc_v15_event_is_carriable(PopcEventType::Slash));
    CHECK("Settle NOT carriable (derived only)", !popc_v15_event_is_carriable(PopcEventType::Settle));
    CHECK("Expire NOT carriable",                !popc_v15_event_is_carriable(PopcEventType::Expire));

    // ---- owner authorization over a Register/Renew/Suspend digest ----
    {
        Bytes32 dg = popc_v15_event_digest(PopcEventType::Renew, CID, OWNER, (uint8_t)PopcModel::A, END);
        auto goodSig = signWith(ownerSk, dg);
        CHECK("owner signature authorizes Renew",
              popc_v15_verify_event_auth(PopcEventType::Renew, CID, OWNER, (uint8_t)PopcModel::A, END, ownerPub, goodSig));
        // attacker signs the SAME digest with their own key — pubkey is not the owner
        auto badSig = signWith(attackerSk, dg);
        CHECK("attacker key does NOT authorize (pubkey != owner)",
              !popc_v15_verify_event_auth(PopcEventType::Renew, CID, OWNER, (uint8_t)PopcModel::A, END, attackerPub, badSig));
        // owner sig but tampered field (end_height) -> digest mismatch -> reject
        CHECK("tampered end_height -> reject",
              !popc_v15_verify_event_auth(PopcEventType::Renew, CID, OWNER, (uint8_t)PopcModel::A, END+1, ownerPub, goodSig));
        // owner sig but different event type -> reject
        CHECK("wrong event type -> reject",
              !popc_v15_verify_event_auth(PopcEventType::Suspend, CID, OWNER, (uint8_t)PopcModel::A, END, ownerPub, goodSig));
        // empty / wrong-length sig -> reject
        CHECK("empty sig -> reject",
              !popc_v15_verify_event_auth(PopcEventType::Renew, CID, OWNER, (uint8_t)PopcModel::A, END, ownerPub, {}));
    }

    // ---- signed-event carrier: encode -> decode -> verify round-trip ----
    {
        Bytes32 dg = popc_v15_event_digest(PopcEventType::Register, CID, OWNER, (uint8_t)PopcModel::A, END);
        auto sig = signWith(ownerSk, dg);
        auto payload = popc_v15_encode_signed_event(PopcEventType::Register, CID, OWNER, (uint8_t)PopcModel::A, END, ownerPub, sig);
        CHECK("signed carrier length == 164", payload.size()==POPC_V15_CARRIER_SIGNED_LEN);
        auto c = popc_v15_decode_carrier(payload, 21000);
        CHECK("signed carrier decodes ok + has_sig", c.ok && c.has_sig && !c.has_attest);
        CHECK("decoded fields match", c.event.type==PopcEventType::Register && c.event.commitment_id==CID
              && c.event.owner_pkh==OWNER && c.event.end_height==END);
        CHECK("decoded signed carrier authorizes",
              popc_v15_verify_event_auth(c.event.type, c.event.commitment_id, c.event.owner_pkh,
                                         c.event.model, c.event.end_height, c.pubkey, c.sig));
        // an UNSIGNED base carrier decodes but carries no authorization
        auto base = popc_v15_encode_event(PopcEventType::Register, CID, OWNER, (uint8_t)PopcModel::A, END);
        auto cb = popc_v15_decode_carrier(base, 21000);
        CHECK("unsigned base carrier decodes but has_sig=false (node will reject)", cb.ok && !cb.has_sig);
    }

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
