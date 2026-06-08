// popc15_carrier.cpp — testnet PoPC V15 carrier-payload generator (soak tooling).
//
// Produces the hex payload of an owner-authorized PoPC V15 carrier (Register /
// Activate / Renew / Suspend), to be broadcast with:
//     sost-cli send <your-own-address> 0.00000001 --popc-carrier <HEX>
//
// The carrier is signed by the OWNER key (the private key given here). owner_pkh =
// RIPEMD160(SHA256(pubkey)). For Activate, the attestation digest is signed; for
// the others, the event-authorization digest is signed. A --forge-owner override
// lets you deliberately build an UNAUTHORIZED carrier (owner_pkh != signer) to
// confirm the node rejects it.
//
// THIS IS TEST/OPS TOOLING — not consensus. It only assembles + signs bytes.
#include "sost/popc_v15.h"
#include "sost/crypto.h"
#include "sost/tx_signer.h"
#include <secp256k1.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static std::string hex(const std::vector<uint8_t>& v){ std::string s; static const char* H="0123456789abcdef";
    for(uint8_t b:v){ s+=H[b>>4]; s+=H[b&15]; } return s; }
static std::string hex32(const Bytes32& v){ return hex(std::vector<uint8_t>(v.begin(),v.end())); }
static std::string hex20(const PubKeyHash& v){ return hex(std::vector<uint8_t>(v.begin(),v.end())); }

static std::vector<uint8_t> unhex(const std::string& s){
    std::vector<uint8_t> v; if (s.size()%2) return v;
    auto nib=[](char c)->int{ if(c>='0'&&c<='9')return c-'0'; if(c>='a'&&c<='f')return c-'a'+10; if(c>='A'&&c<='F')return c-'A'+10; return -1; };
    for(size_t i=0;i<s.size();i+=2){ int hi=nib(s[i]),lo=nib(s[i+1]); if(hi<0||lo<0) return {}; v.push_back((uint8_t)((hi<<4)|lo)); }
    return v;
}
static std::string arg(int argc,char**argv,const std::string& k,const std::string& def=""){
    for(int i=1;i+1<argc;++i) if(k==argv[i]) return argv[i+1];
    return def;
}
static bool has(int argc,char**argv,const std::string& k){ for(int i=1;i<argc;++i) if(k==argv[i]) return true; return false; }

static void usage(){
    std::printf(
"popc15-carrier — PoPC V15 carrier-payload generator (testnet soak tooling)\n\n"
"Usage:\n"
"  popc15-carrier --event register|activate|renew|suspend --privkey <64hex> \\\n"
"                 [--commitment <64hex> | --commitment-auto] [--model A|B] --end <height> \\\n"
"                 [--balance <mg> --attest-height <h>]   (activate only) \\\n"
"                 [--forge-owner <40hex>]                (build an UNAUTHORIZED carrier)\n\n"
"Outputs the carrier payload hex; broadcast it with:\n"
"  sost-cli send <your-own-address> 0.00000001 --popc-carrier <HEX>\n");
}

int main(int argc,char**argv){
    if(argc<2 || has(argc,argv,"-h") || has(argc,argv,"--help")){ usage(); return argc<2?1:0; }

    std::string evs = arg(argc,argv,"--event");
    PopcEventType type;
    if      (evs=="register") type=PopcEventType::Register;
    else if (evs=="activate") type=PopcEventType::Activate;
    else if (evs=="renew")    type=PopcEventType::Renew;
    else if (evs=="suspend")  type=PopcEventType::Suspend;
    else { std::fprintf(stderr,"error: --event must be register|activate|renew|suspend\n"); return 1; }

    auto sk = unhex(arg(argc,argv,"--privkey"));
    if (sk.size()!=32){ std::fprintf(stderr,"error: --privkey must be 64 hex chars (32 bytes)\n"); return 1; }
    uint8_t model = (arg(argc,argv,"--model","A")=="B") ? (uint8_t)PopcModel::B : (uint8_t)PopcModel::A;
    int64_t end_height = std::strtoll(arg(argc,argv,"--end","0").c_str(),nullptr,10);
    if (end_height<=0){ std::fprintf(stderr,"error: --end <height> required (>0)\n"); return 1; }

    // Derive the compressed pubkey + owner pkh from the private key.
    secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN);
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_create(ctx,&pk,sk.data())){ std::fprintf(stderr,"error: invalid private key\n"); return 1; }
    unsigned char comp[33]; size_t cl=33;
    secp256k1_ec_pubkey_serialize(ctx,comp,&cl,&pk,SECP256K1_EC_COMPRESSED);
    std::vector<uint8_t> pub(comp,comp+33);
    PubKeyHash owner = popc_v15_pubkey_pkh(pub);
    if (has(argc,argv,"--forge-owner")){
        auto f = unhex(arg(argc,argv,"--forge-owner"));
        if (f.size()!=20){ std::fprintf(stderr,"error: --forge-owner must be 40 hex chars (20 bytes)\n"); return 1; }
        for (int i=0;i<20;++i) owner[(size_t)i]=f[(size_t)i];   // owner_pkh != signer -> node MUST reject
    }

    // commitment id
    Bytes32 cid{};
    if (has(argc,argv,"--commitment")){
        auto c = unhex(arg(argc,argv,"--commitment"));
        if (c.size()!=32){ std::fprintf(stderr,"error: --commitment must be 64 hex chars\n"); return 1; }
        for (int i=0;i<32;++i) cid[(size_t)i]=c[(size_t)i];
    } else { // deterministic: sha256(owner_pkh || end_le)
        std::vector<uint8_t> m(owner.begin(),owner.end());
        for (int i=0;i<8;++i) m.push_back((uint8_t)((end_height>>(8*i))&0xff));
        cid = sha256(m.data(), m.size());
    }

    auto signDigest=[&](const Bytes32& dg){
        secp256k1_ecdsa_signature s; secp256k1_ecdsa_sign(ctx,&s,dg.data(),sk.data(),nullptr,nullptr);
        unsigned char sig[64]; secp256k1_ecdsa_signature_serialize_compact(ctx,sig,&s);
        return std::vector<uint8_t>(sig,sig+64);
    };

    std::vector<uint8_t> payload;
    bool selfVerify=false;
    if (type==PopcEventType::Activate){
        int64_t balance = std::strtoll(arg(argc,argv,"--balance","0").c_str(),nullptr,10);
        int64_t ah      = std::strtoll(arg(argc,argv,"--attest-height","0").c_str(),nullptr,10);
        if (ah<=0){ std::fprintf(stderr,"error: activate needs --attest-height <h> (and --balance <mg>)\n"); return 1; }
        Bytes32 dg = popc_v15_attest_digest(cid, balance, ah);
        auto sig = signDigest(dg);
        payload = popc_v15_encode_attest(cid, owner, model, end_height, balance, ah, pub, sig);
        selfVerify = popc_v15_verify_attestation(cid, balance, ah, pub, sig) &&
                     (has(argc,argv,"--forge-owner") ? true : popc_v15_pubkey_is_owner(pub, owner));
    } else {
        Bytes32 dg = popc_v15_event_digest(type, cid, owner, model, end_height);
        auto sig = signDigest(dg);
        payload = popc_v15_encode_signed_event(type, cid, owner, model, end_height, pub, sig);
        selfVerify = popc_v15_verify_event_auth(type, cid, owner, model, end_height, pub, sig);
    }

    std::printf("event           : %s\n", evs.c_str());
    std::printf("model           : %s\n", model==(uint8_t)PopcModel::B?"B":"A");
    std::printf("owner_pkh       : %s%s\n", hex20(owner).c_str(), has(argc,argv,"--forge-owner")?"  (FORGED — node must REJECT)":"");
    std::printf("commitment_id   : %s\n", hex32(cid).c_str());
    std::printf("end_height      : %lld\n", (long long)end_height);
    std::printf("authorized      : %s\n", selfVerify?"yes (owner signature verifies)":"NO (unauthorized — expect rejection)");
    std::printf("payload (%zu B) : %s\n", payload.size(), hex(payload).c_str());
    std::printf("\nbroadcast with:\n  sost-cli send <YOUR-OWN-ADDRESS> 0.00000001 --popc-carrier %s\n", hex(payload).c_str());
    return 0;
}
