// Regtest driver for the SOST BTC HTLC (OTC-3a). Emits P2WSH address + redeem
// script, funds via the REAL SignBtcHtlcLockFunding, and signs claim/refund.
// Accepts txids in bitcoin-cli DISPLAY order and converts via the API helper
// (no manual byte reversal). REGTEST ONLY. Never mainnet, never a real broadcast.
#include "sost/atomic_swap_btc.h"
#include "sost/atomic_swap_btc_signing.h"
#include <openssl/sha.h>
#include <array>
#include <vector>
#include <string>
#include <cstdio>
#include <cstring>
#include <cstdint>
using namespace sost::atomic_swap::btc;

static std::vector<uint8_t> unhex(const std::string& h){
  std::vector<uint8_t> o; for(size_t i=0;i+1<h.size();i+=2){o.push_back((uint8_t)strtol(h.substr(i,2).c_str(),0,16));} return o;
}
static std::string hex(const std::vector<uint8_t>& b){ std::string s; char t[3]; for(auto c:b){snprintf(t,3,"%02x",c);s+=t;} return s; }
template<size_t N> static std::array<uint8_t,N> arr(const std::string& h){ auto v=unhex(h); std::array<uint8_t,N> a{}; for(size_t i=0;i<N&&i<v.size();i++)a[i]=v[i]; return a; }
// DISPLAY txid (bitcoin-cli order) -> Bytes32 (internal) via the API helper.
static bool disp_txid(const std::string& disp, std::array<uint8_t,32>& out){
  auto r = DisplayTxidToInternal(disp);
  if(!r.ok){ fprintf(stderr,"txid: %s\n", r.error.c_str()); return false; }
  for(int i=0;i<32;i++) out[i]=r.bytes[i];
  return true;
}

int main(int argc,char**argv){
  if(argc<2){fprintf(stderr,"usage: mode ...\n");return 2;}
  std::string mode=argv[1];
  if(mode=="addr"){
    // addr <preimage_hex> <refund_height> <claim_priv> <refund_priv> <network>
    auto preimage=arr<32>(argv[2]); int64_t rh=atoll(argv[3]);
    auto cpriv=arr<32>(argv[4]); auto rpriv=arr<32>(argv[5]); std::string net=argv[6];
    std::array<uint8_t,32> hashlock{}; SHA256(preimage.data(),32,hashlock.data());
    auto cpk=DeriveBtcCompressedPubkey(cpriv); auto rpk=DeriveBtcCompressedPubkey(rpriv);
    if(!cpk.ok||!rpk.ok){fprintf(stderr,"derive fail\n");return 1;}
    std::array<uint8_t,33> cpk33{},rpk33{}; for(int i=0;i<33;i++){cpk33[i]=cpk.bytes[i];rpk33[i]=rpk.bytes[i];}
    auto redeem=BuildBtcHtlcRedeemScript(hashlock,rh,cpk33,rpk33);
    auto wp=BtcHtlcWitnessProgram(redeem);
    std::array<uint8_t,32> wp32{}; for(int i=0;i<32;i++)wp32[i]=wp[i];
    auto ad=EncodeP2WSHAddress(wp32,net);
    if(!ad.ok){fprintf(stderr,"addr fail: %s\n",ad.error.c_str());return 1;}
    printf("ADDR=%s\n",ad.address.c_str());
    printf("REDEEM=%s\n",hex(redeem).c_str());
    printf("HASHLOCK=%s\n",hex(std::vector<uint8_t>(hashlock.begin(),hashlock.end())).c_str());
    return 0;
  }
  if(mode=="p2wpkh"){
    // p2wpkh <priv> <network> -> the funder's P2WPKH address (to fund with coins)
    auto priv=arr<32>(argv[2]); std::string net=argv[3];
    auto pk=DeriveBtcCompressedPubkey(priv);
    if(!pk.ok){fprintf(stderr,"derive fail\n");return 1;}
    // hash160(pubkey) -> P2WPKH witness program (20 bytes). Reuse EncodeP2WPKH if present;
    // otherwise emit via the address encoder path used by change outputs.
    auto ad=EncodeP2WPKHAddress(priv,net);
    if(!ad.ok){fprintf(stderr,"p2wpkh fail: %s\n",ad.error.c_str());return 1;}
    printf("P2WPKH=%s\n",ad.address.c_str());
    return 0;
  }
  if(mode=="fund"){
    // fund <prev_disp_txid> <prev_vout> <prev_amt> <funder_priv> <change_addr> <redeem_hex> <lock_amt> <fee> <net>
    std::array<uint8_t,32> ptx{}; if(!disp_txid(argv[2],ptx)) return 1;
    uint32_t pv=atoi(argv[3]); int64_t pamt=atoll(argv[4]);
    auto fpriv=arr<32>(argv[5]); std::string chg=argv[6];
    auto redeem=unhex(argv[7]); int64_t lock=atoll(argv[8]); int64_t fee=atoll(argv[9]); std::string net=argv[10];
    auto r=SignBtcHtlcLockFunding(ptx,pv,pamt,fpriv,chg,redeem,lock,fee,net);
    if(!r.ok){fprintf(stderr,"fund fail: %s\n",r.error.c_str());return 1;}
    printf("%s\n",r.raw_tx_hex.c_str()); return 0;
  }
  if(mode=="claim"){
    // claim <disp_txid> <vout> <amt> <redeem_hex> <preimage> <claim_priv> <dest> <fee> <net>
    std::array<uint8_t,32> txid{}; if(!disp_txid(argv[2],txid)) return 1;
    uint32_t vout=atoi(argv[3]); int64_t amt=atoll(argv[4]);
    auto redeem=unhex(argv[5]); auto preimage=arr<32>(argv[6]); auto cpriv=arr<32>(argv[7]);
    std::string dest=argv[8]; int64_t fee=atoll(argv[9]); std::string net=argv[10];
    auto r=SignBtcHtlcClaim(txid,vout,amt,redeem,preimage,cpriv,dest,fee,net);
    if(!r.ok){fprintf(stderr,"claim fail: %s\n",r.error.c_str());return 1;}
    printf("%s\n",r.raw_tx_hex.c_str()); return 0;
  }
  if(mode=="refund"){
    // refund <disp_txid> <vout> <amt> <redeem_hex> <refund_height> <refund_priv> <dest> <fee> <net>
    std::array<uint8_t,32> txid{}; if(!disp_txid(argv[2],txid)) return 1;
    uint32_t vout=atoi(argv[3]); int64_t amt=atoll(argv[4]);
    auto redeem=unhex(argv[5]); int64_t rh=atoll(argv[6]); auto rpriv=arr<32>(argv[7]);
    std::string dest=argv[8]; int64_t fee=atoll(argv[9]); std::string net=argv[10];
    auto r=SignBtcHtlcRefund(txid,vout,amt,redeem,rh,rpriv,dest,fee,net);
    if(!r.ok){fprintf(stderr,"refund fail: %s\n",r.error.c_str());return 1;}
    printf("%s\n",r.raw_tx_hex.c_str()); return 0;
  }
  if(mode=="txid"){
    // txid <raw_tx_hex> -> the DISPLAY txid (what bitcoin-cli shows), via API helpers
    auto t=ComputeBtcTxid(argv[2]);
    if(!t.ok){fprintf(stderr,"txid fail: %s\n",t.error.c_str());return 1;}
    std::array<uint8_t,32> it{}; for(int i=0;i<32;i++)it[i]=t.bytes[i];
    printf("%s\n", InternalTxidToDisplay(it).c_str()); return 0;
  }
  fprintf(stderr,"unknown mode %s\n",mode.c_str()); return 2;
}
