#include "sost/node.h"
#include <cstdio>
using namespace sost;
static int pass=0,fail=0;
#define T(n,c) do{if(c){pass++;printf("  PASS: %s\n",n);}else{fail++;printf("  FAIL: %s\n",n);}}while(0)
int main(){
    printf("SOST Chunk 7 Tests - Node\n=========================\n");
    Node node(Profile::DEV);
    T("initial height=-1",node.height()==-1);
    Wallet w; w.generate_key();
    auto mr=node.mine_next(w);
    T("mined block 0",mr.found);
    T("height=0",node.height()==0);
    T("wallet credited",w.balance()>0);
    auto mr2=node.mine_next(w);
    T("mined block 1",mr2.found);
    T("height=1",node.height()==1);
    T("balance increased",w.balance()>mr.block.subsidy_stocks);
    auto info=node.info_json();
    T("info has height",info.find("height")!=std::string::npos);
    auto bj=node.block_json(0);
    T("block json has nonce",bj.find("nonce")!=std::string::npos);
    T("block json has subsidy",bj.find("subsidy")!=std::string::npos);
    auto bj_bad=node.block_json(999);
    T("bad height returns error",bj_bad.find("error")!=std::string::npos);
    auto st=node.state();
    T("state has 2 blocks",st.blocks.size()==2);
    T("state metas match",st.metas.size()==2);
    printf("\n=========================\nResults: %d passed, %d failed\n",pass,fail);
    return fail>0?1:0;
}
