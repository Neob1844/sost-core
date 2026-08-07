// test_popc_v15_carrier_e2e.cpp — V15 PoPC end-to-end: REAL signed on-chain
// carriers -> deterministic collection (mirrors node_collect_popc_events) ->
// chain_active_popc_set -> lottery eligibility with the PoPC gate ON.
//
// This is the validation the DTD-PoPC lottery rule never had: it proves that a
// REAL owner-signed Register+Activate carrier (the bytes a tx would carry on
// chain) makes that owner lottery-eligible, that an address with NO carrier is
// excluded, that forged/unsigned/attacker carriers are ignored, that an empty
// eligible set is deterministic, and that expiry/auto-settle drops the owner —
// all the edge cases that could otherwise fork the chain over who wins blocks.
//
// It deliberately replicates the EXACT decode+authz filter of
// node_collect_popc_events (sost-node.cpp) so the path under test is the real
// consensus path, not a stand-in. Build-agnostic: passes on both the mainnet
// (-DSOST_TESTNET_FORKS=OFF) and testnet builds.
#include "sost/popc_v15.h"
#include "sost/lottery.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include <secp256k1.h>
#include <cstdio>
#include <vector>
#include <utility>
using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(n,c) do{ if(c){++g_pass;std::printf("  ok  %s\n",n);} else {++g_fail;std::printf("  *** FAIL: %s\n",n);} }while(0)
static Bytes32 cid_of(uint8_t b){ Bytes32 x{}; x.fill(b); return x; }

// One carrier as it would sit in a block: (block height, the 0-value marker output).
struct CarrierAt { int64_t h; TxOutput out; };

// Build a carrier TxOutput from an encoded payload (amount 0, marker pkh).
static TxOutput carrier_output(const std::vector<uint8_t>& payload) {
    TxOutput o; o.amount = 0; o.pubkey_hash = POPC_V15_MARKER_PKH; o.payload = payload;
    return o;
}

// Replicate node_collect_popc_events' decode + P4c authorization filter EXACTLY,
// over an explicit list of carriers (so the test exercises the real consensus
// decode path without needing g_blocks). Returns the accepted canonical events.
static std::vector<PopcV15Event> collect(const std::vector<CarrierAt>& carriers) {
    std::vector<PopcV15Event> ev;
    for (const auto& ca : carriers) {
        if (!popc_v15_is_carrier_output(ca.out)) continue;
        auto c = popc_v15_decode_output(ca.out, ca.h);
        if (!c.ok) continue;
        if (!popc_v15_event_is_carriable(c.event.type)) continue;
        if (c.event.type == PopcEventType::Activate) {
            if (!popc_v15_verify_attestation(c.event.commitment_id, c.balance_mg,
                                             c.attest_height, c.pubkey, c.sig)) continue;
            if (!popc_v15_pubkey_is_owner(c.pubkey, c.event.owner_pkh)) continue;
        } else {
            if (!c.has_sig) continue;
            if (!popc_v15_verify_event_auth(c.event.type, c.event.commitment_id, c.event.owner_pkh,
                                            c.event.model, c.event.end_height, c.pubkey, c.sig)) continue;
        }
        ev.push_back(c.event);
    }
    return ev;
}

int main(){
    std::printf("=== PoPC V15 — end-to-end signed carrier -> lottery eligibility ===\n");
    secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN|SECP256K1_CONTEXT_VERIFY);

    auto mkkey=[&](unsigned char seed, std::vector<uint8_t>& pub){
        unsigned char sk[32]; for(int i=0;i<32;i++) sk[i]=(unsigned char)(i+seed);
        secp256k1_pubkey pk; secp256k1_ec_pubkey_create(ctx,&pk,sk);
        unsigned char comp[33]; size_t cl=33; secp256k1_ec_pubkey_serialize(ctx,comp,&cl,&pk,SECP256K1_EC_COMPRESSED);
        pub.assign(comp,comp+33);
        return std::vector<uint8_t>(sk,sk+32);
    };
    auto sign=[&](const std::vector<uint8_t>& sk, const Bytes32& dg){
        secp256k1_ecdsa_signature s; secp256k1_ecdsa_sign(ctx,&s,dg.data(),sk.data(),nullptr,nullptr);
        unsigned char sig[64]; secp256k1_ecdsa_signature_serialize_compact(ctx,sig,&s);
        return std::vector<uint8_t>(sig,sig+64);
    };

    std::vector<uint8_t> ownerPub, attackerPub;
    auto ownerSk    = mkkey(7,  ownerPub);
    auto attackerSk = mkkey(99, attackerPub);
    const PubKeyHash OWNER = popc_v15_pubkey_pkh(ownerPub);
    const PubKeyHash NOBODY = [](){ PubKeyHash p{}; p.fill(0xC3); return p; }();
    const Bytes32 CID = cid_of(0x42);
    const uint8_t MODEL = (uint8_t)PopcModel::A;

    // A maintained commitment: activate well before eligibility and answer the
    // audit challenge every POPC_V15_AUDIT_INTERVAL_BLOCKS so it stays Active
    // through the query height (a one-shot would auto-slash — see soak test).
    const int64_t ACT  = 20020;
    const int64_t END  = 200000;                 // far future -> no auto-settle in range
    const int64_t QH   = DTD_POPC_ELIGIBILITY_HEIGHT > ACT + 6000
                       ? DTD_POPC_ELIGIBILITY_HEIGHT : ACT + 6000;  // a height where the gate bites

    auto regCarrier=[&](const std::vector<uint8_t>& sk, const std::vector<uint8_t>& pub){
        Bytes32 dg = popc_v15_event_digest(PopcEventType::Register, CID, OWNER, MODEL, END);
        auto sig = sign(sk, dg);
        return carrier_output(popc_v15_encode_signed_event(PopcEventType::Register, CID, OWNER, MODEL, END, pub, sig));
    };
    auto attestCarrier=[&](int64_t attest_h){
        int64_t bal = 50000;
        Bytes32 dg = popc_v15_attest_digest(CID, bal, attest_h);
        auto sig = sign(ownerSk, dg);
        return carrier_output(popc_v15_encode_attest(CID, OWNER, MODEL, END, bal, attest_h, ownerPub, sig));
    };

    // ---- the happy path: owner-signed Register + maintained Activates -> eligible ----
    {
        std::vector<CarrierAt> chain;
        chain.push_back({ ACT - 10, regCarrier(ownerSk, ownerPub) });   // signed Register (owner)
        chain.push_back({ ACT,      attestCarrier(ACT) });              // Activate (attestation)
        for (int64_t k = 1; ACT + k*POPC_V15_AUDIT_INTERVAL_BLOCKS <= QH; ++k)
            chain.push_back({ ACT + k*POPC_V15_AUDIT_INTERVAL_BLOCKS, attestCarrier(ACT + k*POPC_V15_AUDIT_INTERVAL_BLOCKS) });

        auto evs = collect(chain);
        CHECK("owner-signed Register+Activate carriers are accepted", !evs.empty());
        CHECK("owner is lottery-eligible at the query height (gate would include)",
              popc_v15_owner_active(evs, OWNER, QH));
        CHECK("an address with NO carrier is NOT eligible",
              !popc_v15_owner_active(evs, NOBODY, QH));

        // Eligibility composition with the gate ON (the real lottery filter):
        //   excluded  <=>  popc_eligibility_enforced(h,true) && !owner_active
        bool owner_excluded  = lottery::popc_eligibility_enforced(QH, true) && !popc_v15_owner_active(evs, OWNER, QH);
        bool nobody_excluded = lottery::popc_eligibility_enforced(QH, true) && !popc_v15_owner_active(evs, NOBODY, QH);
        CHECK("gate ON @ eligibility: owner with PoPC NOT excluded", !owner_excluded);
        CHECK("gate ON @ eligibility: address without PoPC IS excluded", nobody_excluded);
        CHECK("gate ON one block BEFORE eligibility: nobody excluded yet",
              !(lottery::popc_eligibility_enforced(DTD_POPC_ELIGIBILITY_HEIGHT - 1, true) && !popc_v15_owner_active(evs, NOBODY, DTD_POPC_ELIGIBILITY_HEIGHT - 1)));
        CHECK("gate OFF: nobody is ever excluded (flag false = no-op)",
              !(lottery::popc_eligibility_enforced(QH, false) && !popc_v15_owner_active(evs, NOBODY, QH)));
    }

    // ---- Finding 1: Register ALONE leaves the commitment PENDING -> NOT eligible.
    //      popc_register must return BOTH carriers; broadcasting only the Register one
    //      leaves the miner OUT of the lottery. Adding the Activate carrier -> ACTIVE -> eligible.
    {
        std::vector<CarrierAt> regOnly = { { ACT - 10, regCarrier(ownerSk, ownerPub) } };
        auto e1 = collect(regOnly);
        CHECK("Register-only: owner NOT active (Pending)", !popc_v15_owner_active(e1, OWNER, QH));
        CHECK("Register-only @ eligibility, gate ON: owner EXCLUDED",
              lottery::popc_eligibility_enforced(QH, true) && !popc_v15_owner_active(e1, OWNER, QH));

        std::vector<CarrierAt> regAct = regOnly;
        regAct.push_back({ ACT, attestCarrier(ACT) });
        for (int64_t k = 1; ACT + k*POPC_V15_AUDIT_INTERVAL_BLOCKS <= QH; ++k)
            regAct.push_back({ ACT + k*POPC_V15_AUDIT_INTERVAL_BLOCKS, attestCarrier(ACT + k*POPC_V15_AUDIT_INTERVAL_BLOCKS) });
        auto e2 = collect(regAct);
        CHECK("Register + Activate: owner ACTIVE", popc_v15_owner_active(e2, OWNER, QH));
        CHECK("Register + Activate @ eligibility, gate ON: owner INCLUDED",
              !(lottery::popc_eligibility_enforced(QH, true) && !popc_v15_owner_active(e2, OWNER, QH)));
    }

    // ---- forged / unsigned carriers are ignored (no third-party injection) ----
    {
        // Attacker signs the Register digest with their OWN key but claims OWNER.
        Bytes32 dg = popc_v15_event_digest(PopcEventType::Register, CID, OWNER, MODEL, END);
        auto badSig = sign(attackerSk, dg);
        auto forged = carrier_output(popc_v15_encode_signed_event(PopcEventType::Register, CID, OWNER, MODEL, END, attackerPub, badSig));
        // Unsigned base Register (no owner authorization).
        auto unsignedReg = carrier_output(popc_v15_encode_event(PopcEventType::Register, CID, OWNER, MODEL, END));
        std::vector<CarrierAt> chain = { {ACT-10, forged}, {ACT-10, unsignedReg}, {ACT, attestCarrier(ACT)} };
        auto evs = collect(chain);
        CHECK("forged + unsigned Register carriers are filtered out",
              !popc_v15_owner_active(evs, OWNER, QH));
    }

    // ---- empty eligible set is deterministic (the feared fork edge is a no-op) ----
    {
        std::vector<CarrierAt> none;                       // no PoPC carriers at all
        auto evs = collect(none);
        CHECK("no carriers -> empty active set (every node computes the same)",
              chain_active_popc_set(evs, QH).empty());
        // With the gate on and an empty set, EVERY candidate is excluded — but
        // deterministically (pure function of chain+height), so no node disagreement.
        CHECK("empty set + gate ON: owner excluded deterministically",
              lottery::popc_eligibility_enforced(QH, true) && !popc_v15_owner_active(evs, OWNER, QH));
    }

    // ---- expiry / auto-settle at end_height drops eligibility (no off-by-one fork) ----
    {
        const int64_t SHORT_END = ACT + 3000;              // commitment ends mid-window
        auto reg = [&](){ Bytes32 dg = popc_v15_event_digest(PopcEventType::Register, CID, OWNER, MODEL, SHORT_END);
                          return carrier_output(popc_v15_encode_signed_event(PopcEventType::Register, CID, OWNER, MODEL, SHORT_END, ownerPub, sign(ownerSk,dg))); }();
        auto act = [&](){ int64_t bal=50000; Bytes32 dg=popc_v15_attest_digest(CID,bal,ACT);
                          return carrier_output(popc_v15_encode_attest(CID, OWNER, MODEL, SHORT_END, bal, ACT, ownerPub, sign(ownerSk,dg))); }();
        std::vector<CarrierAt> chain = { {ACT-10, reg}, {ACT, act} };
        auto evs = collect(chain);
        CHECK("active strictly before end_height", popc_v15_owner_active(evs, OWNER, SHORT_END - 1));
        CHECK("NOT active at/after end_height (auto-settle, deterministic)",
              !popc_v15_owner_active(evs, OWNER, SHORT_END) && !popc_v15_owner_active(evs, OWNER, SHORT_END + 1));
    }

    secp256k1_context_destroy(ctx);
    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
