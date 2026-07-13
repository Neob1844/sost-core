// test_popc_v15_carrier.cpp — V15 PoPC P3: on-chain carriers + pure decoder.
// Encodes/decodes the deterministic carrier (0-value marker output) for each
// event, rejects malformed/wrong-version/wrong-domain/wrong-length, and proves
// the Activate carrier carries a verifiable attestation. No node wiring.
#include "sost/popc_v15.h"
#include "sost/transaction.h"
#include <secp256k1.h>
#include <cstdio>
#include <vector>
using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(n,c) do{ if(c){++g_pass;std::printf("  ok  %s\n",n);} else {++g_fail;std::printf("  *** FAIL: %s\n",n);} }while(0)

static Bytes32 id(uint8_t b){ Bytes32 x{}; x.fill(b); return x; }
static PubKeyHash own(uint8_t b){ PubKeyHash p{}; p.fill(b); return p; }
static TxOutput carrier(const std::vector<uint8_t>& payload){ TxOutput o; o.amount=0; o.pubkey_hash=POPC_V15_MARKER_PKH; o.payload=payload; return o; }

int main(){
#ifndef SOST_TESTNET_FORKS
    // V15 final-decentralization fork RETIRES PoPC on mainnet: the PoPC V15
    // subsystem never auto-activates (popc_v15_active_at == false at every
    // height). This suite exercises the live subsystem only on the testnet
    // profile; on mainnet it verifies the retirement invariant and exits green.
    // See docs/V15_FINAL_DECENTRALIZATION_SPEC.md.
    if (sost::popc_v15_active_at(sost::V15_HEIGHT) ||
        sost::popc_v15_active_at(sost::V15_HEIGHT + 100000)) {
        printf("FAIL: PoPC must be inactive (retired) on mainnet under the V15 fork\n");
        return 1;
    }
    printf("[mainnet] PoPC retired by the V15 fork - subsystem is testnet-only. OK\n");
    return 0;
#endif
    std::printf("=== PoPC V15 P3 — on-chain carriers + decoder ===\n");
    const Bytes32 CID=id(0x11); const PubKeyHash OWN=own(0x22);
    const int64_t BH=5000;

    // non-attest carriers round-trip for every event type
    PopcEventType types[]={PopcEventType::Register,PopcEventType::Renew,PopcEventType::Suspend,
                           PopcEventType::Slash,PopcEventType::Settle,PopcEventType::Expire};
    for(auto t:types){
        auto pl=popc_v15_encode_event(t,CID,OWN,(uint8_t)PopcModel::A,9000);
        auto c=popc_v15_decode_carrier(pl,BH);
        bool okc = c.ok && c.event.type==t && c.event.commitment_id==CID && c.event.owner_pkh==OWN
                   && c.event.model==(uint8_t)PopcModel::A && c.event.end_height==9000 && c.event.height==BH && !c.has_attest;
        char nm[64]; std::snprintf(nm,64,"event type %d round-trips",(int)t); CHECK(nm, okc);
    }

    // Model B preserved
    { auto c=popc_v15_decode_carrier(popc_v15_encode_event(PopcEventType::Register,CID,OWN,(uint8_t)PopcModel::B,9000),BH);
      CHECK("Model B model byte preserved", c.ok && c.event.model==(uint8_t)PopcModel::B); }

    // carrier output recognition
    { auto o=carrier(popc_v15_encode_event(PopcEventType::Register,CID,OWN,0,9000));
      CHECK("carrier output recognised", popc_v15_is_carrier_output(o));
      auto d=popc_v15_decode_output(o,BH); CHECK("decode_output ok", d.ok && d.event.commitment_id==CID);
      TxOutput normal; normal.amount=100; normal.pubkey_hash=own(0x99);
      CHECK("normal output NOT a carrier", !popc_v15_is_carrier_output(normal));
      TxOutput zeroOther; zeroOther.amount=0; zeroOther.pubkey_hash=own(0x99); zeroOther.payload=popc_v15_encode_event(PopcEventType::Register,CID,OWN,0,9000);
      CHECK("0-value to wrong pkh NOT a carrier", !popc_v15_is_carrier_output(zeroOther)); }

    // malformed payloads → ok=false
    { CHECK("too short -> reject", !popc_v15_decode_carrier(std::vector<uint8_t>(10,0),BH).ok);
      auto p=popc_v15_encode_event(PopcEventType::Register,CID,OWN,0,9000); p[0]^=0xFF;
      CHECK("wrong magic -> reject", !popc_v15_decode_carrier(p,BH).ok);
      p=popc_v15_encode_event(PopcEventType::Register,CID,OWN,0,9000); p[4]=2;
      CHECK("wrong version -> reject", !popc_v15_decode_carrier(p,BH).ok);
      p=popc_v15_encode_event(PopcEventType::Register,CID,OWN,0,9000); p[5]=99;
      CHECK("unknown event type -> reject", !popc_v15_decode_carrier(p,BH).ok);
      p=popc_v15_encode_event(PopcEventType::Register,CID,OWN,0,9000); p[6]=7;
      CHECK("invalid model -> reject", !popc_v15_decode_carrier(p,BH).ok);
      p=popc_v15_encode_event(PopcEventType::Register,CID,OWN,0,9000); p.push_back(0);
      CHECK("non-attest with extra bytes -> reject", !popc_v15_decode_carrier(p,BH).ok); }

    // Activate (attestation) carrier: encode → decode → verify the signed claim
    {
        secp256k1_context* ctx=secp256k1_context_create(SECP256K1_CONTEXT_SIGN|SECP256K1_CONTEXT_VERIFY);
        unsigned char sk[32]; for(int i=0;i<32;i++) sk[i]=(unsigned char)(i+9);
        secp256k1_pubkey pk; secp256k1_ec_pubkey_create(ctx,&pk,sk);
        unsigned char comp[33]; size_t cl=33; secp256k1_ec_pubkey_serialize(ctx,comp,&cl,&pk,SECP256K1_EC_COMPRESSED);
        std::vector<uint8_t> pub(comp,comp+33);
        int64_t bal=311035, ah=4800;
        Bytes32 dg=popc_v15_attest_digest(CID,bal,ah);
        secp256k1_ecdsa_signature s; secp256k1_ecdsa_sign(ctx,&s,dg.data(),sk,nullptr,nullptr);
        unsigned char sig[64]; secp256k1_ecdsa_signature_serialize_compact(ctx,sig,&s);
        std::vector<uint8_t> sigv(sig,sig+64);

        auto pl=popc_v15_encode_attest(CID,OWN,(uint8_t)PopcModel::A,9000,bal,ah,pub,sigv);
        CHECK("attest payload length == 180", pl.size()==POPC_V15_CARRIER_ATTEST_LEN);
        auto c=popc_v15_decode_carrier(pl,BH);
        CHECK("attest decodes ok", c.ok && c.has_attest && c.event.type==PopcEventType::Activate);
        CHECK("attest fields", c.balance_mg==bal && c.attest_height==ah && c.pubkey.size()==33 && c.sig.size()==64);
        CHECK("decoded attest signature VERIFIES",
              popc_v15_verify_attestation(c.event.commitment_id, c.balance_mg, c.attest_height, c.pubkey, c.sig)==true);
        CHECK("attest verify fails on tampered balance",
              popc_v15_verify_attestation(c.event.commitment_id, c.balance_mg+1, c.attest_height, c.pubkey, c.sig)==false);
        // truncated attest -> reject
        auto bad=pl; bad.resize(120);
        CHECK("truncated attest -> reject", !popc_v15_decode_carrier(bad,BH).ok);
        // Activate at exactly base length (no attest body) -> reject
        auto base=popc_v15_encode_event(PopcEventType::Activate,CID,OWN,0,9000);
        CHECK("Activate without attest body -> reject", !popc_v15_decode_carrier(base,BH).ok);
    }

    // gating: P3 decode is pure; V15 ACTIVATED — live from V15_HEIGHT on both profiles.
    CHECK("popc_v15 active at V15_HEIGHT", popc_v15_active_at(V15_HEIGHT)==true);

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
