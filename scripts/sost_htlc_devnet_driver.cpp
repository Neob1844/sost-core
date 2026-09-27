// SOST-side HTLC driver (OTC-1): build → sign → serialize an OUT_HTLC_LOCK lock,
// its preimage CLAIM, and its timeout REFUND, using the REAL project builders
// (atomic_swap_helpers) + the REAL signer (tx_signer). Prints signed raw-tx hex
// to broadcast via the node's sendrawtransaction. DEVNET/LAB ONLY.
#include "sost/atomic_swap_helpers.h"
#include "sost/tx_signer.h"
#include "sost/transaction.h"
#include "sost/crypto.h"
#include <array>
#include <vector>
#include <string>
#include <cstdio>
#include <cstring>
#include <cstdlib>
using namespace sost;
using namespace sost::atomic_swap;

static std::vector<uint8_t> unhex(const std::string& h){ std::vector<uint8_t> o; for(size_t i=0;i+1<h.size();i+=2)o.push_back((uint8_t)strtol(h.substr(i,2).c_str(),0,16)); return o; }
static std::string hex(const uint8_t* b,size_t n){ std::string s; char t[3]; for(size_t i=0;i<n;i++){snprintf(t,3,"%02x",b[i]);s+=t;} return s; }
template<size_t N> static std::array<uint8_t,N> arr(const std::string& h){ auto v=unhex(h); std::array<uint8_t,N> a{}; for(size_t i=0;i<N&&i<v.size();i++)a[i]=v[i]; return a; }
static Hash256 h256(const std::string& h){ Hash256 x{}; auto v=unhex(h); for(size_t i=0;i<32&&i<v.size();i++)x[i]=v[i]; return x; }

static bool sign0(Transaction& tx, int64_t amt, uint8_t type, const Hash256& gen, const std::array<uint8_t,32>& priv){
  SpentOutput sp; sp.amount=amt; sp.type=type;
  std::string err;
  if(!SignTransactionInput(tx,0,sp,gen,priv,&err)){ fprintf(stderr,"sign: %s\n",err.c_str()); return false; }
  return true;
}
static int emit(const Transaction& tx){
  std::vector<uint8_t> raw; std::string err;
  if(!tx.Serialize(raw,&err)){ fprintf(stderr,"serialize: %s\n",err.c_str()); return 1; }
  printf("%s\n", hex(raw.data(),raw.size()).c_str()); return 0;
}

int main(int argc,char**argv){
  if(argc<2){ fprintf(stderr,"usage: mode ...\n"); return 2; }
  std::string mode=argv[1];
  if(mode=="pkh"){ // pkh <privkey>  -> the 20-byte pkh of that key
    auto priv=arr<32>(argv[2]); PubKey pub{}; std::string err;
    if(!DerivePublicKey(priv,pub,&err)){ fprintf(stderr,"derive: %s\n",err.c_str()); return 1; }
    auto pkh=ComputePubKeyHash(pub);
    printf("%s\n", hex(pkh.data(),20).c_str()); return 0;
  }
  if(mode=="lock"){
    // lock <prev_txid> <prev_vout> <prev_amt> <prev_type> <privkey> <hashlock> <refund_h> <claim_pkh> <refund_pkh> <lock_amt> <fee> <genesis>
    auto ptx=h256(argv[2]); uint32_t pv=atoi(argv[3]); int64_t pamt=atoll(argv[4]); uint8_t ptype=(uint8_t)atoi(argv[5]);
    auto priv=arr<32>(argv[6]); auto hl=arr<32>(argv[7]); uint64_t rh=strtoull(argv[8],0,10);
    auto cpkh=arr<20>(argv[9]); auto rpkh=arr<20>(argv[10]); int64_t la=atoll(argv[11]); int64_t fee=atoll(argv[12]);
    auto gen=h256(argv[13]);
    PubKey pub{}; std::string e; if(!DerivePublicKey(priv,pub,&e)){fprintf(stderr,"derive:%s\n",e.c_str());return 1;}
    auto prev_pkh=ComputePubKeyHash(pub);
    auto r=BuildHtlcLockTx(ptx,pv,pamt,prev_pkh,hl,rh,cpkh,rpkh,la,fee);
    if(!r.ok){ fprintf(stderr,"BuildHtlcLockTx: %s\n",r.error.c_str()); return 1; }
    Transaction tx=r.tx;
    if(!sign0(tx,pamt,ptype,gen,priv)) return 1;
    return emit(tx);
  }
  if(mode=="claim"){
    // claim <lock_txid> <lock_vout> <lock_amt> <preimage> <claim_dest_pkh> <marker_dust> <fee> <claim_privkey> <genesis>
    auto ltx=h256(argv[2]); uint32_t lv=atoi(argv[3]); int64_t la=atoll(argv[4]); auto pre=arr<32>(argv[5]);
    auto dpkh=arr<20>(argv[6]); int64_t dust=atoll(argv[7]); int64_t fee=atoll(argv[8]); auto priv=arr<32>(argv[9]);
    auto gen=h256(argv[10]);
    auto r=BuildHtlcClaimTx(ltx,lv,la,pre,dpkh,dust,fee);
    if(!r.ok){ fprintf(stderr,"BuildHtlcClaimTx: %s\n",r.error.c_str()); return 1; }
    Transaction tx=r.tx;
    if(!sign0(tx,la,OUT_HTLC_LOCK,gen,priv)) return 1;   // spends the OUT_HTLC_LOCK utxo
    return emit(tx);
  }
  if(mode=="refund"){
    // refund <lock_txid> <lock_vout> <lock_amt> <refund_dest_pkh> <fee> <refund_privkey> <genesis>
    auto ltx=h256(argv[2]); uint32_t lv=atoi(argv[3]); int64_t la=atoll(argv[4]); auto dpkh=arr<20>(argv[5]);
    int64_t fee=atoll(argv[6]); auto priv=arr<32>(argv[7]); auto gen=h256(argv[8]);
    auto r=BuildHtlcRefundTx(ltx,lv,la,dpkh,fee);
    if(!r.ok){ fprintf(stderr,"BuildHtlcRefundTx: %s\n",r.error.c_str()); return 1; }
    Transaction tx=r.tx;
    if(!sign0(tx,la,OUT_HTLC_LOCK,gen,priv)) return 1;
    return emit(tx);
  }
  fprintf(stderr,"unknown mode %s\n",mode.c_str()); return 2;
}
