#include "sost/node.h"
#include <cstdio>
#include <sstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cstring>
namespace sost {

Node::Node(Profile prof) : prof_(prof) {
    ACTIVE_PROFILE = prof; // Set global for MAGIC derivation
    cs_.tip_height = -1; cs_.total_work = 0; cs_.tip_hash.fill(0);
}

bool Node::accept_block(const Block& blk) {
    std::lock_guard<std::mutex> lk(mu_);
    int64_t now = blk.timestamp + 7200;
    auto vr = verify_block(blk, cs_.metas, now, prof_, true);
    if (!vr.ok) { printf("[NODE] reject %lld: %s\n",(long long)blk.height,vr.reason.c_str()); return false; }
    cs_.blocks.push_back(blk); cs_.metas.push_back(to_meta(blk));
    cs_.tip_hash = blk.block_id; cs_.tip_height = blk.height;
    return true;
}

Block Node::get_block(int64_t h) const {
    std::lock_guard<std::mutex> lk(mu_); if(h<0||h>=(int64_t)cs_.blocks.size()) return Block{}; return cs_.blocks[h];
}

int64_t Node::height() const { std::lock_guard<std::mutex> lk(mu_); return cs_.tip_height; }
Bytes32 Node::tip() const { std::lock_guard<std::mutex> lk(mu_); return cs_.tip_hash; }
ChainState Node::state() const { std::lock_guard<std::mutex> lk(mu_); return cs_; }

MineResult Node::mine_next(Wallet& w, uint32_t max_nonce) {
    std::lock_guard<std::mutex> lk(mu_);
    int64_t h = (int64_t)cs_.metas.size();
    Bytes32 prev = (h==0)?ZERO_HASH():cs_.tip_hash;
    Bytes32 mrkl{}; mrkl.fill(0x11);
    int64_t ts = (h==0)?GENESIS_TIME:cs_.blocks.back().timestamp+TARGET_SPACING;
    uint32_t diff = asert_next_difficulty(cs_.metas, h);
    mu_.unlock();
    auto mr = mine_block(cs_.metas, prev, mrkl, ts, diff, max_nonce, prof_);
    mu_.lock();
    if (mr.found) {
        auto vr = verify_block(mr.block, cs_.metas, ts, prof_, true);
        if (vr.ok) {
            cs_.blocks.push_back(mr.block); cs_.metas.push_back(to_meta(mr.block));
            cs_.tip_hash = mr.block.block_id; cs_.tip_height = mr.block.height;
            w.credit_coinbase(h, mr.block.subsidy_stockshis, mr.block.block_id);
            printf("[NODE] block %lld mined id=%s nonce=%u\n",(long long)h,hex(mr.block.block_id).substr(0,16).c_str(),mr.block.nonce);
        } else { mr.found=false; mr.error=vr.reason; }
    }
    return mr;
}

int Node::mine_loop(int32_t count, Wallet& w, uint32_t max_nonce) {
    for(int32_t i=0;count==0||i<count;++i) {
        auto mr = mine_next(w, max_nonce);
        if(!mr.found) { printf("[NODE] fail: %s\n",mr.error.c_str()); return 1; }
    }
    return 0;
}

std::string Node::info_json() const {
    std::lock_guard<std::mutex> lk(mu_);
    std::ostringstream s;
    s<<"{\"height\":"<<cs_.tip_height<<",\"tip\":\""<<hex(cs_.tip_hash).substr(0,16)<<"...\",\"blocks\":"<<cs_.blocks.size()<<"}\n";
    return s.str();
}

std::string Node::block_json(int64_t h) const {
    std::lock_guard<std::mutex> lk(mu_);
    if(h<0||h>=(int64_t)cs_.blocks.size()) return "{\"error\":\"not found\"}";
    auto& b=cs_.blocks[h]; auto sp=coinbase_split(b.subsidy_stockshis);
    std::ostringstream s;
    s<<"{\"height\":"<<b.height<<",\"id\":\""<<hex(b.block_id)<<"\",\"nonce\":"<<b.nonce
     <<",\"subsidy\":"<<b.subsidy_stockshis<<",\"miner\":"<<sp.miner
     <<",\"gold_vault\":"<<sp.gold_vault<<",\"popc_pool\":"<<sp.popc_pool
     <<",\"metric\":"<<b.stability_metric<<"}";
    return s.str();
}

static std::string handle_rpc(Node& n, Wallet& w, const std::string& path) {
    if(path=="/info"||path=="/") return n.info_json();
    if(path.rfind("/block/",0)==0) return n.block_json(std::stoll(path.substr(7)));
    if(path=="/wallet/balance") { std::ostringstream s; s<<"{\"balance\":"<<w.balance()<<",\"address\":\""<<w.default_address()<<"\"}"; return s.str(); }
    if(path=="/wallet/utxos") {
        auto us=w.utxos(); std::ostringstream s; s<<"{\"count\":"<<us.size()<<",\"utxos\":[";
        for(size_t i=0;i<us.size();++i){if(i)s<<",";s<<"{\"amount\":"<<us[i].amount<<",\"h\":"<<us[i].height<<"}";} s<<"]}"; return s.str();
    }
    return "{\"error\":\"unknown\"}";
}

int run_rpc_server(Node& node, Wallet& wallet, int port) {
    int srv=socket(AF_INET,SOCK_STREAM,0); if(srv<0){perror("socket");return 1;}
    int opt=1; setsockopt(srv,SOL_SOCKET,SO_REUSEADDR,&opt,sizeof(opt));
    struct sockaddr_in addr{}; addr.sin_family=AF_INET; addr.sin_addr.s_addr=INADDR_ANY; addr.sin_port=htons(port);
    if(bind(srv,(struct sockaddr*)&addr,sizeof(addr))<0){perror("bind");return 1;}
    listen(srv,5); printf("[RPC] port %d\n",port);
    while(true){
        int cl=accept(srv,nullptr,nullptr); if(cl<0)continue;
        char buf[4096]{}; read(cl,buf,sizeof(buf)-1);
        std::string req(buf),path="/";
        auto sp=req.find(' '); if(sp!=std::string::npos){auto s2=req.find(' ',sp+1);if(s2!=std::string::npos)path=req.substr(sp+1,s2-sp-1);}
        auto body=handle_rpc(node,wallet,path);
        std::string resp="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: "+std::to_string(body.size())+"\r\n\r\n"+body;
        write(cl,resp.c_str(),resp.size()); close(cl);
    }
    return 0;
}
} // namespace sost