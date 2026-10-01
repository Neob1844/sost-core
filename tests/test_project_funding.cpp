// test_project_funding.cpp — PROJECT FUNDING modality (V30000).
//
// A crowdfunding campaign built ENTIRELY on the live HTLC primitive (no new
// consensus rule). Each contribution is an HTLC_LOCK:
//     claim_pkh  = PROJECT, hashlock = sha256(goal_secret)
//     refund_pkh = contributor_i, refund_height = DEADLINE
// Outcomes:
//   GOAL MET  -> campaign reveals goal_secret; PROJECT claims every contribution
//               (preimage) before DEADLINE -> funds released to the project.
//   GOAL UNMET-> after DEADLINE each contributor REFUNDs their own contribution.
// Safety (trust-minimised): project cannot claim with a wrong secret (R21) or
// after the deadline (R22); a contributor cannot rug-pull before the deadline (R24).
// Validated on the REAL consensus path (ValidateTransactionConsensus) + the block
// path (UtxoSet::ConnectBlock), exactly as the HTLC primitive itself is validated.
#include "sost/atomic_swap.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/utxo_set.h"
#include "sost/consensus_constants.h"
#include "sost/crypto.h"
#include <array>
#include <cstdio>
#include <cstring>
#include <optional>
#include <vector>
using namespace sost;
static int g_pass=0,g_fail=0;
#define TEST(m,c) do{ if(c){std::printf("  PASS: %s\n",m);++g_pass;} else {std::printf("  *** FAIL: %s [%d]\n",m,__LINE__);++g_fail;} }while(0)

static constexpr int64_t H = ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT;
static int64_t DEADLINE = 0;
static std::array<uint8_t,32> g_secret{};     // the "goal met" secret
static std::array<uint8_t,32> g_hashlock{};
static std::array<uint8_t,20> g_project{};     // claim_pkh (project)
static constexpr int N = 3;
static std::array<uint8_t,20> g_contrib[N];
static const int64_t AMT[N] = {100000, 250000, 400000}; // contributions (stocks)

static TxValidationContext MakeCtx(int64_t h){
    TxValidationContext c; c.genesis_hash.fill(0); c.spend_height=h;
    c.capsule_activation_height=CAPSULE_ACTIVATION_HEIGHT_MAINNET;
    c.bond_activation_height=BOND_ACTIVATION_HEIGHT_MAINNET;
    return c;
}
static Hash256 lockTxid(int i){ Hash256 t; t.fill((uint8_t)(0xC0+i)); return t; }
static void SeedContribution(UtxoSet& u,int i){
    UTXOEntry e; e.amount=AMT[i]; e.type=OUT_HTLC_LOCK; e.pubkey_hash.fill(0);
    WriteHtlcLockPayload(e.payload,g_hashlock,(uint64_t)DEADLINE,g_project,g_contrib[i]);
    e.payload_len=(uint16_t)e.payload.size(); e.height=100; e.is_coinbase=false;
    std::string err; u.AddUTXO(OutPoint{lockTxid(i),0},e,&err);
}
static Transaction MakeClaim(int i,const std::array<uint8_t,32>& preimage,const std::array<uint8_t,20>& dest){
    Transaction tx; tx.version=1; tx.tx_type=TX_TYPE_HTLC_CLAIM;
    TxInput in; in.prev_txid=lockTxid(i); in.prev_index=0; in.signature.fill(0x01); in.pubkey.fill(0x02); tx.inputs.push_back(in);
    TxOutput m; m.amount=10000; m.type=OUT_HTLC_CLAIM_WITNESS; m.pubkey_hash.fill(0); WriteHtlcClaimWitnessPayload(m.payload,preimage); tx.outputs.push_back(m);
    TxOutput o; o.amount=AMT[i]-20000; o.type=OUT_TRANSFER; o.pubkey_hash=dest; tx.outputs.push_back(o);
    return tx;
}
static Transaction MakeRefund(int i,const std::array<uint8_t,20>& dest){
    Transaction tx; tx.version=1; tx.tx_type=TX_TYPE_HTLC_REFUND;
    TxInput in; in.prev_txid=lockTxid(i); in.prev_index=0; in.signature.fill(0x01); in.pubkey.fill(0x02); tx.inputs.push_back(in);
    TxOutput o; o.amount=AMT[i]-10000; o.type=OUT_TRANSFER; o.pubkey_hash=dest; tx.outputs.push_back(o);
    return tx;
}
static Transaction Coinbase(int64_t h){
    Transaction tx; tx.version=1; tx.tx_type=TX_TYPE_COINBASE;
    TxInput cb; cb.prev_txid.fill(0); cb.prev_index=0xFFFFFFFF; cb.signature.fill(0);
    uint64_t hh=(uint64_t)h; std::memcpy(cb.signature.data(),&hh,8); cb.pubkey.fill(0); tx.inputs.push_back(cb);
    TxOutput o; o.amount=1000000; o.type=OUT_TRANSFER; o.pubkey_hash.fill(0x33); tx.outputs.push_back(o); return tx;
}
// a single-lock view for validation-path tests
struct OneLock: IUtxoView{ int idx;
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override{
        if(op.txid!=lockTxid(idx)||op.index!=0) return std::nullopt;
        UTXOEntry e; e.amount=AMT[idx]; e.type=OUT_HTLC_LOCK; e.pubkey_hash.fill(0);
        WriteHtlcLockPayload(e.payload,g_hashlock,(uint64_t)DEADLINE,g_project,g_contrib[idx]);
        e.payload_len=(uint16_t)e.payload.size(); e.height=100; e.is_coinbase=false; return e;
    }
};

int main(){
    std::printf("\n== PROJECT FUNDING (HTLC-based crowdfunding) ==\n\n");
    for(size_t i=0;i<g_secret.size();++i) g_secret[i]=(uint8_t)(i*7+1);
    { Bytes32 hl=sha256(g_secret.data(),g_secret.size()); std::copy(hl.begin(),hl.end(),g_hashlock.begin()); }
    g_project.fill(0x5A);
    for(int i=0;i<N;++i) g_contrib[i].fill((uint8_t)(0x90+i));
    DEADLINE = H + 1000;
    int64_t total=0; for(int i=0;i<N;++i) total+=AMT[i];
    std::printf("  HTLC gate H=%lld DEADLINE=%lld  contributions=%d total=%lld\n\n",(long long)H,(long long)DEADLINE,N,(long long)total);

    // ---- GOAL MET: project claims all contributions before the deadline ----
    std::printf("-- GOAL MET: project claims every contribution (preimage) --\n");
    {
        UtxoSet u; for(int i=0;i<N;++i) SeedContribution(u,i);
        std::vector<Transaction> block; block.push_back(Coinbase(H+10));
        for(int i=0;i<N;++i) block.push_back(MakeClaim(i,g_secret,g_project));
        BlockUndo undo; std::string err;
        bool ok=u.ConnectBlock(block,H+10,undo,&err);   // before DEADLINE
        TEST("campaign block of N claims ACCEPTED pre-deadline", ok);
        bool allGone=true; for(int i=0;i<N;++i) if(u.HasUTXO(OutPoint{lockTxid(i),0})) allGone=false;
        TEST("all contribution locks consumed (released to project)", allGone);
        if(!ok) std::printf("    err=%s\n",err.c_str());
    }
    // ---- GOAL UNMET: contributors refund after the deadline ----
    std::printf("\n-- GOAL UNMET: each contributor refunds after the deadline --\n");
    {
        UtxoSet u; for(int i=0;i<N;++i) SeedContribution(u,i);
        std::vector<Transaction> block; block.push_back(Coinbase(DEADLINE));
        for(int i=0;i<N;++i) block.push_back(MakeRefund(i,g_contrib[i]));
        BlockUndo undo; std::string err;
        bool ok=u.ConnectBlock(block,DEADLINE,undo,&err);  // at DEADLINE
        TEST("campaign block of N refunds ACCEPTED at/after deadline", ok);
        bool allGone=true; for(int i=0;i<N;++i) if(u.HasUTXO(OutPoint{lockTxid(i),0})) allGone=false;
        TEST("all contribution locks consumed (refunded to contributors)", allGone);
        if(!ok) std::printf("    err=%s\n",err.c_str());
    }
    // ---- SAFETY (validation path) ----
    std::printf("\n-- SAFETY: trust-minimised guarantees --\n");
    {
        OneLock v; v.idx=0;
        std::array<uint8_t,32> wrong{}; wrong[0]=0xFF;
        auto r=ValidateTransactionConsensus(MakeClaim(0,wrong,g_project),v,MakeCtx(H+10));
        TEST("project CANNOT claim with a wrong secret (R21)", !r.ok && r.code==TxValCode::R21_HTLC_CLAIM_PREIMAGE_MISMATCH);
    }
    {
        OneLock v; v.idx=0;
        auto r=ValidateTransactionConsensus(MakeClaim(0,g_secret,g_project),v,MakeCtx(DEADLINE));
        TEST("project CANNOT claim after the deadline (R22)", !r.ok && r.code==TxValCode::R22_HTLC_CLAIM_TIMEOUT);
    }
    {
        OneLock v; v.idx=0;
        auto r=ValidateTransactionConsensus(MakeRefund(0,g_contrib[0]),v,MakeCtx(DEADLINE-1));
        TEST("contributor CANNOT rug-pull before the deadline (R24)", !r.ok && r.code==TxValCode::R24_HTLC_REFUND_BEFORE_TIMEOUT);
    }
    {
        OneLock v; v.idx=0;
        auto r=ValidateTransactionConsensus(MakeClaim(0,g_secret,g_project),v,MakeCtx(H+10));
        TEST("correct-secret claim passes the preimage+timeout gates (R21/R22 clear)",
             r.code!=TxValCode::R21_HTLC_CLAIM_PREIMAGE_MISMATCH && r.code!=TxValCode::R22_HTLC_CLAIM_TIMEOUT);
    }
    std::printf("\n== Summary: %d passed, %d failed ==\n",g_pass,g_fail);
    return g_fail?1:0;
}
