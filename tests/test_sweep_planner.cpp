// Sweep planner tests — the plan must be right before anything is signed.
#include "sost/sweep.h"
#include "sost/tx_validation.h"
#include "sost/consensus_constants.h"
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <string>

using namespace sost;
using namespace sost::sweep;

static int g_pass=0,g_fail=0;
#define TEST(m,c) do{ if(c){++g_pass;} else {printf("  *** FAIL: %s [%d]\n",m,__LINE__);++g_fail;} }while(0)

static Utxo mk(int i, int64_t amt, int64_t h, bool mature=true){
    Utxo u; char b[80]; snprintf(b,sizeof b,"%064x", i);
    u.txid=b; u.vout=(uint32_t)(i%3); u.amount=amt; u.height=h;
    u.coinbase=true; u.mature=mature; u.spendable=mature; return u;
}

int main(){
    const auto L = default_limits();

    printf("== the cap is derived from the mempool's own estimator ==\n");
    {
        size_t cap = max_inputs_per_batch(L);
        printf("  limits: %d bytes / %u inputs, margin %d -> cap %zu inputs (%zu bytes)\n",
               L.max_tx_bytes_standard, L.max_inputs_standard, L.byte_margin, cap, policy_size(cap,1));
        TEST("cap is below the policy input limit", cap < (size_t)L.max_inputs_standard);
        TEST("a batch at the cap fits under the byte limit minus margin",
             policy_size(cap,1) <= (size_t)(L.max_tx_bytes_standard - L.byte_margin));
        TEST("one more input would break the budget",
             policy_size(cap+1,1) > (size_t)(L.max_tx_bytes_standard - L.byte_margin));
        // The planner must agree with the real estimator exactly, not approximately.
        Transaction t; t.inputs.resize(cap); t.outputs.resize(1);
        TEST("policy_size == EstimateTxSerializedSize", policy_size(cap,1)==EstimateTxSerializedSize(t));
        TEST("and it is under the hard policy limit too",
             policy_size(cap,1) < (size_t)MAX_TX_BYTES_STANDARD);
    }

    printf("== maturity and the journal are hard filters ==\n");
    {
        std::vector<Utxo> all;
        for (int i=0;i<10;i++) all.push_back(mk(i, 100000, 100+i, i%2==0));   // half immature
        auto sp = filter_spendable(all, {});
        TEST("immature UTXOs never enter a plan", sp.size()==5);
        std::vector<std::string> consumed = { sp[0].key(), sp[2].key() };
        auto sp2 = filter_spendable(all, consumed);
        TEST("outpoints the journal already spent are excluded", sp2.size()==3);
        for (const auto& u : sp2) {
            TEST("no excluded outpoint survives", u.key()!=consumed[0] && u.key()!=consumed[1]);
        }
    }

    printf("== packing: deterministic, complete, no double-spend ==\n");
    {
        const int N = 2058;                      // the live mining address
        std::vector<Utxo> all;
        for (int i=0;i<N;i++) all.push_back(mk(i, 392550432, 1000+i));
        auto sp = filter_spendable(all, {});
        auto plan = plan_batches(sp, L);
        size_t cap = max_inputs_per_batch(L);
        printf("  %d spendable -> %zu batches of at most %zu inputs\n", N, plan.size(), cap);
        TEST("batch count matches the cap", plan.size()==(size_t)((N+cap-1)/cap));

        std::set<std::string> seen; size_t total_inputs=0; bool sizes_ok=true, fees_ok=true;
        for (const auto& b : plan) {
            total_inputs += b.inputs.size();
            for (const auto& u : b.inputs) {
                if (!seen.insert(u.key()).second) { printf("  *** duplicate input %s\n", u.key().c_str()); ++g_fail; }
            }
            if (b.est_bytes > (size_t)MAX_TX_BYTES_STANDARD) sizes_ok=false;
            if (b.inputs.size() > (size_t)MAX_INPUTS_STANDARD) sizes_ok=false;
            if (b.fee < (int64_t)b.est_bytes) fees_ok=false;          // min relay fee is 1 stock/byte
            if (b.to_destination != b.total_in - b.fee) fees_ok=false;
        }
        TEST("every spendable UTXO is planned exactly once", total_inputs==sp.size() && seen.size()==sp.size());
        TEST("every batch is inside BOTH policy limits", sizes_ok);
        TEST("every batch pays at least the minimum relay fee, and change is exact", fees_ok);

        // The last batch is the short one; its size must be computed from ITS
        // own input count, not inherited from the cap.
        const auto& last = plan.back();
        TEST("the short final batch is sized on its own inputs",
             last.est_bytes == policy_size(last.inputs.size(),1) && last.inputs.size() <= cap);
        TEST("and it is genuinely shorter here", last.inputs.size() == (size_t)(N % cap));

        // Same input, same plan — a plan has to be reviewable and diffable.
        auto plan2 = plan_batches(sp, L);
        bool identical = plan.size()==plan2.size();
        for (size_t i=0;identical && i<plan.size();++i){
            if (plan[i].inputs.size()!=plan2[i].inputs.size() || plan[i].fee!=plan2[i].fee) identical=false;
            for (size_t k=0;identical && k<plan[i].inputs.size();++k)
                if (plan[i].inputs[k].key()!=plan2[i].inputs[k].key()) identical=false;
        }
        TEST("the plan is deterministic", identical);

        int64_t swept=0, fees=0;
        for (const auto& b : plan){ swept += b.to_destination; fees += b.fee; }
        printf("  total swept %lld stocks, fees %lld stocks (%.8f SOST)\n",
               (long long)swept, (long long)fees, fees/1e8);
        TEST("nothing is lost: in == out + fees",
             swept + fees == (int64_t)sp.size()*392550432LL);
    }

    printf("== journal: survives a restart, and a corrupt file is NOT 'nothing spent' ==\n");
    {
        const std::string path = "/tmp/sost_sweep_journal_test.json";
        std::remove(path.c_str());
        Journal j; j.destination="sost1dest"; j.source_address="sost1src";
        JournalEntry e; e.batch_index=0; e.txid="deadbeef"; e.confirmed_height=27500;
        e.confirmed_block_hash="00aa"; e.total_in=1000; e.fee=64;
        e.consumed={"aa:0","bb:1"};
        j.entries.push_back(e);
        std::string err;
        TEST("journal saves", journal_save(path, j, &err));

        Journal back;
        TEST("journal reloads", journal_load(path, back, &err));
        TEST("round-trips exactly",
             back.destination==j.destination && back.entries.size()==1 &&
             back.entries[0].txid=="deadbeef" && back.entries[0].confirmed_height==27500 &&
             back.entries[0].consumed.size()==2 && back.entries[0].consumed[1]=="bb:1");

        auto ck = consumed_keys(back);
        TEST("consumed outpoints are recovered", ck.size()==2);

        // A truncated or corrupt journal must FAIL LOUDLY. Reading it as an empty
        // journal would re-plan outpoints that are already spent and pay twice.
        { FILE* f=fopen(path.c_str(),"w"); fputs("{\"entries\": [ {\"txid\": \"aa", f); fclose(f); }
        Journal bad; std::string berr;
        TEST("a corrupt journal is refused, not read as empty", !journal_load(path, bad, &berr));
        TEST("and says why", berr.rfind("corrupt journal",0)==0);
        std::remove(path.c_str());

        Journal missing; std::string merr;
        TEST("a missing journal is distinguishable from a corrupt one",
             !journal_load("/tmp/sost_no_such_journal.json", missing, &merr) && merr=="no_journal");
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
