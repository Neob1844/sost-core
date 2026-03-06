// sost-rpc.cpp — SOST JSON-RPC Daemon v0.3 (with UtxoSet + Mempool)
//
// Bitcoin-compatible JSON-RPC for exchange integration (TradeOgre, etc.)
//
// Supported methods:
//   getblockcount             → chain height
//   getblockhash <height>     → block hash at height
//   getblock <hash>           → block info
//   getbalance                → wallet balance
//   getnewaddress [label]     → generate new address
//   listunspent               → list unspent outputs
//   validateaddress <addr>    → check address validity
//   sendrawtransaction <hex>  → validate + add to mempool
//   gettxout <txid> <vout>    → get UTXO from set
//   getinfo                   → node/wallet summary
//   getmempoolinfo            → mempool stats
//   getrawmempool             → list mempool txids
//   getrawtransaction <txid>  → get tx from mempool

#include "sost/wallet.h"
#include "sost/address.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/types.h"
#include "sost/utxo_set.h"
#include "sost/mempool.h"
#include "sost/tx_validation.h"
#include "sost/emission.h"

#include <fstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>
#include <map>
#include <functional>
#include <ctime>

using namespace sost;

// === Globals ===
static Wallet   g_wallet;
static UtxoSet  g_utxo_set;
static Mempool  g_mempool;
static std::string g_wallet_path = "wallet.json";
static Hash256  g_genesis_hash{};
static int64_t  g_chain_height = 0;

struct StoredBlock {
    Hash256 block_id, prev_hash, merkle_root;
    int64_t timestamp; uint32_t bits_q; uint64_t nonce;
    int64_t height, subsidy;
};
static std::vector<StoredBlock> g_blocks;

// === Helpers ===
static std::string to_hex(const uint8_t* d, size_t len) {
    static const char* hx = "0123456789abcdef";
    std::string s; s.reserve(len*2);
    for (size_t i=0;i<len;++i){s+=hx[d[i]>>4];s+=hx[d[i]&0xF];}
    return s;
}
static bool hex_to_bytes(const std::string& h, uint8_t* out, size_t len) {
    if(h.size()!=len*2) return false;
    auto hv=[](char c)->int{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return 10+c-'a';if(c>='A'&&c<='F')return 10+c-'A';return -1;};
    for(size_t i=0;i<len;++i){int hi=hv(h[i*2]),lo=hv(h[i*2+1]);if(hi<0||lo<0)return false;out[i]=(uint8_t)((hi<<4)|lo);}
    return true;
}
static std::string format_sost(int64_t stocks) {
    char buf[64]; bool neg=stocks<0; int64_t a=neg?-stocks:stocks;
    snprintf(buf,sizeof(buf),"%s%lld.%08lld",neg?"-":"",(long long)(a/sost::STOCKS_PER_SOST),(long long)(a%sost::STOCKS_PER_SOST));
    return std::string(buf);
}
static std::string json_escape(const std::string& s) {
    std::string o; for(char c:s){if(c=='"')o+="\\\"";else if(c=='\\')o+="\\\\";else if(c=='\n')o+="\\n";else o+=c;} return o;
}

// === JSON parser ===
static std::string json_get_string(const std::string& json, const std::string& key) {
    std::string needle="\""+key+"\""; auto pos=json.find(needle); if(pos==std::string::npos)return"";
    pos=json.find(':',pos+needle.size()); if(pos==std::string::npos)return""; pos++;
    while(pos<json.size()&&(json[pos]==' '||json[pos]=='\t'))pos++;
    if(pos>=json.size())return"";
    if(json[pos]=='"'){auto end=json.find('"',pos+1);if(end==std::string::npos)return"";return json.substr(pos+1,end-pos-1);}
    auto end=json.find_first_of(",}] \t\n\r",pos);if(end==std::string::npos)end=json.size();return json.substr(pos,end-pos);
}
static std::vector<std::string> json_get_params(const std::string& json) {
    std::vector<std::string> r; auto pos=json.find("\"params\""); if(pos==std::string::npos)return r;
    pos=json.find('[',pos); if(pos==std::string::npos)return r;
    auto end=json.find(']',pos); if(end==std::string::npos)return r;
    std::string inner=json.substr(pos+1,end-pos-1); size_t i=0;
    while(i<inner.size()){
        while(i<inner.size()&&(inner[i]==' '||inner[i]==','||inner[i]=='\t'||inner[i]=='\n'))i++;
        if(i>=inner.size())break;
        if(inner[i]=='"'){auto q=inner.find('"',i+1);if(q==std::string::npos)break;r.push_back(inner.substr(i+1,q-i-1));i=q+1;}
        else{auto p=inner.find_first_of(",] \t\n\r",i);if(p==std::string::npos)p=inner.size();r.push_back(inner.substr(i,p-i));i=p;}
    }
    return r;
}

// === RPC builders ===
static std::string rpc_result(const std::string& id, const std::string& r) {
    return "{\"jsonrpc\":\"2.0\",\"id\":"+id+",\"result\":"+r+"}";
}
static std::string rpc_error(const std::string& id, int code, const std::string& msg) {
    return "{\"jsonrpc\":\"2.0\",\"id\":"+id+",\"error\":{\"code\":"+std::to_string(code)+",\"message\":\""+json_escape(msg)+"\"}}";
}

// === RPC handlers ===
static std::string handle_getblockcount(const std::string& id, const std::vector<std::string>&) {
    return rpc_result(id, std::to_string(g_chain_height));
}
static std::string handle_getblockhash(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing height");
    int64_t h=std::stoll(p[0]);
    if(h<0||h>=(int64_t)g_blocks.size()) return rpc_error(id,-8,"Block height out of range");
    return rpc_result(id,"\""+to_hex(g_blocks[h].block_id.data(),32)+"\"");
}
static std::string handle_getblock(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing blockhash");
    for(const auto& b:g_blocks){
        if(to_hex(b.block_id.data(),32)==p[0]){
            std::ostringstream s;
            s<<"{\"hash\":\""<<to_hex(b.block_id.data(),32)<<"\",\"height\":"<<b.height
             <<",\"previousblockhash\":\""<<to_hex(b.prev_hash.data(),32)
             <<"\",\"merkleroot\":\""<<to_hex(b.merkle_root.data(),32)
             <<"\",\"time\":"<<b.timestamp<<",\"bits_q\":"<<b.bits_q
             <<",\"nonce\":"<<b.nonce<<",\"subsidy\":"<<b.subsidy<<"}";
            return rpc_result(id,s.str());
        }
    }
    return rpc_error(id,-5,"Block not found");
}
static std::string handle_getinfo(const std::string& id, const std::vector<std::string>&) {
    std::ostringstream s;
    s<<"{\"version\":\"0.3.0\",\"protocolversion\":1,\"blocks\":"<<g_chain_height
     <<",\"connections\":0,\"difficulty\":"<<(g_blocks.empty()?0:g_blocks.back().bits_q)
     <<",\"testnet\":false,\"balance\":\""<<format_sost(g_wallet.balance())
     <<"\",\"keypoolsize\":"<<g_wallet.num_keys()
     <<",\"mempool_size\":"<<g_mempool.Size()
     <<",\"utxo_count\":"<<g_utxo_set.Size()<<"}";
    return rpc_result(id,s.str());
}
static std::string handle_getbalance(const std::string& id, const std::vector<std::string>&) {
    double bal=(double)g_wallet.balance()/(double)sost::STOCKS_PER_SOST;
    char buf[64]; snprintf(buf,sizeof(buf),"%.8f",bal);
    return rpc_result(id,std::string(buf));
}
static std::string handle_getnewaddress(const std::string& id, const std::vector<std::string>& p) {
    std::string label; if(!p.empty()) label=p[0];
    auto key=g_wallet.generate_key(label);
    std::string err; g_wallet.save(g_wallet_path,&err);
    return rpc_result(id,"\""+key.address+"\"");
}
static std::string handle_validateaddress(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing address");
    bool valid=address_valid(p[0]); bool mine=g_wallet.has_address(p[0]);
    std::ostringstream s;
    s<<"{\"isvalid\":"<<(valid?"true":"false")<<",\"address\":\""<<json_escape(p[0])
     <<"\",\"ismine\":"<<(mine?"true":"false");
    if(mine){auto k=g_wallet.find_key(p[0]);if(k){s<<",\"pubkey\":\""<<to_hex(k->pubkey.data(),33)<<"\"";if(!k->label.empty())s<<",\"label\":\""<<json_escape(k->label)<<"\"";}}
    s<<"}"; return rpc_result(id,s.str());
}
static std::string handle_listunspent(const std::string& id, const std::vector<std::string>&) {
    auto utxos=g_wallet.list_unspent(); std::ostringstream s; s<<"[";
    for(size_t i=0;i<utxos.size();++i){
        if(i)s<<","; const auto& u=utxos[i];
        s<<"{\"txid\":\""<<to_hex(u.txid.data(),32)<<"\",\"vout\":"<<u.vout
         <<",\"address\":\""<<address_encode(u.pkh)<<"\",\"amount\":"<<format_sost(u.amount)
         <<",\"confirmations\":"<<(g_chain_height-u.height+1)<<",\"spendable\":true}";
    }
    s<<"]"; return rpc_result(id,s.str());
}
static std::string handle_gettxout(const std::string& id, const std::vector<std::string>& p) {
    if(p.size()<2) return rpc_error(id,-1,"missing txid and vout");
    Hash256 txid{}; if(!hex_to_bytes(p[0],txid.data(),32)) return rpc_error(id,-8,"invalid txid");
    OutPoint op; op.txid=txid; op.index=(uint32_t)std::stoul(p[1]);
    auto entry=g_utxo_set.GetUTXO(op); if(!entry) return rpc_result(id,"null");
    std::ostringstream s;
    s<<"{\"bestblock\":\""<<to_hex(g_genesis_hash.data(),32)<<"\",\"confirmations\":"<<(g_chain_height-entry->height+1)
     <<",\"value\":"<<format_sost(entry->amount)<<",\"address\":\""<<address_encode(entry->pubkey_hash)
     <<"\",\"type\":"<<(int)entry->type<<",\"coinbase\":"<<(entry->is_coinbase?"true":"false")<<"}";
    return rpc_result(id,s.str());
}
static std::string handle_sendrawtransaction(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing hex tx");
    std::string hex_str=p[0]; if(hex_str.size()%2!=0) return rpc_error(id,-22,"odd hex length");
    std::vector<Byte> raw; raw.reserve(hex_str.size()/2);
    for(size_t i=0;i<hex_str.size();i+=2){uint8_t b;if(!hex_to_bytes(hex_str.substr(i,2),&b,1))return rpc_error(id,-22,"invalid hex");raw.push_back(b);}
    Transaction tx; std::string err;
    if(!Transaction::Deserialize(raw,tx,&err)) return rpc_error(id,-22,"TX decode: "+err);
    Hash256 txid; if(!tx.ComputeTxId(txid,&err)) return rpc_error(id,-25,"TX reject: "+err);
    TxValidationContext ctx; ctx.genesis_hash=g_genesis_hash; ctx.spend_height=g_chain_height+1;
    int64_t now=(int64_t)time(nullptr);
    auto result=g_mempool.AcceptToMempool(tx,g_utxo_set,ctx,now);
    if(!result.accepted){
        printf("[RPC] sendrawtx REJECTED: %s\n",result.reason.c_str());
        return rpc_error(id,-25,result.reason);
    }
    printf("[RPC] sendrawtx ACCEPTED: %s fee=%lld\n",to_hex(txid.data(),32).c_str(),(long long)result.fee);
    return rpc_result(id,"\""+to_hex(txid.data(),32)+"\"");
}
static std::string handle_getmempoolinfo(const std::string& id, const std::vector<std::string>&) {
    std::ostringstream s;
    s<<"{\"size\":"<<g_mempool.Size()<<",\"bytes\":"<<g_mempool.TotalSize()
     <<",\"total_fees\":"<<g_mempool.TotalFees()<<",\"maxsize\":"<<g_mempool.MaxEntries()<<"}";
    return rpc_result(id,s.str());
}
static std::string handle_getrawmempool(const std::string& id, const std::vector<std::string>&) {
    auto tmpl=g_mempool.BuildBlockTemplate(); std::ostringstream s; s<<"[";
    for(size_t i=0;i<tmpl.txids.size();++i){if(i)s<<",";s<<"\""<<to_hex(tmpl.txids[i].data(),32)<<"\"";}
    s<<"]"; return rpc_result(id,s.str());
}
static std::string handle_getrawtransaction(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing txid");
    Hash256 txid{}; if(!hex_to_bytes(p[0],txid.data(),32)) return rpc_error(id,-8,"invalid txid");
    const MempoolEntry* entry=g_mempool.GetEntry(txid); if(!entry) return rpc_error(id,-5,"Not in mempool");
    std::vector<Byte> raw; std::string err;
    if(!entry->tx.Serialize(raw,&err)) return rpc_error(id,-1,"serialize: "+err);
    bool verbose=(p.size()>1&&p[1]!="0"&&p[1]!="false");
    if(!verbose) return rpc_result(id,"\""+to_hex(raw.data(),raw.size())+"\"");
    std::ostringstream s;
    s<<"{\"txid\":\""<<to_hex(txid.data(),32)<<"\",\"size\":"<<raw.size()<<",\"fee\":"<<entry->fee<<",\"vin\":[";
    for(size_t i=0;i<entry->tx.inputs.size();++i){if(i)s<<",";const auto&in=entry->tx.inputs[i];s<<"{\"txid\":\""<<to_hex(in.prev_txid.data(),32)<<"\",\"vout\":"<<in.prev_index<<"}";}
    s<<"],\"vout\":[";
    for(size_t i=0;i<entry->tx.outputs.size();++i){if(i)s<<",";const auto&o=entry->tx.outputs[i];s<<"{\"value\":"<<format_sost(o.amount)<<",\"n\":"<<i<<",\"address\":\""<<address_encode(o.pubkey_hash)<<"\"}";}
    s<<"]}"; return rpc_result(id,s.str());
}

// estimatefee (standalone: always returns minimum relay)
static std::string handle_estimatefee(const std::string& id, const std::vector<std::string>&) {
    const int64_t MIN_FEE = 1000;
    std::ostringstream s;
    s<<"{\"fee_per_byte\":"<<MIN_FEE
     <<",\"fee_for_typical_tx\":"<<(MIN_FEE*250)
     <<",\"basis\":\"minimum_relay\"}";
    return rpc_result(id,s.str());
}

// === Dispatch ===
using RpcHandler=std::function<std::string(const std::string&,const std::vector<std::string>&)>;
static std::map<std::string,RpcHandler> g_handlers={
    {"getblockcount",handle_getblockcount},{"getblockhash",handle_getblockhash},{"getblock",handle_getblock},
    {"getinfo",handle_getinfo},{"getbalance",handle_getbalance},{"getnewaddress",handle_getnewaddress},
    {"validateaddress",handle_validateaddress},{"listunspent",handle_listunspent},{"gettxout",handle_gettxout},
    {"sendrawtransaction",handle_sendrawtransaction},{"getmempoolinfo",handle_getmempoolinfo},
    {"getrawmempool",handle_getrawmempool},{"getrawtransaction",handle_getrawtransaction},
    {"estimatefee",handle_estimatefee},
};
static std::string dispatch_rpc(const std::string& req) {
    std::string method=json_get_string(req,"method"),id_raw=json_get_string(req,"id");
    std::string id=id_raw.empty()?"null":id_raw;
    if(!id_raw.empty()&&id_raw[0]>='0'&&id_raw[0]<='9')id=id_raw;
    else if(id_raw!="null"&&!id_raw.empty())id="\""+id_raw+"\"";
    if(method.empty()) return rpc_error(id,-32600,"missing method");
    auto it=g_handlers.find(method); if(it==g_handlers.end()) return rpc_error(id,-32601,"Method not found: "+method);
    return it->second(id,json_get_params(req));
}

// === HTTP server ===
static void handle_connection(int fd) {
    char buf[65536]{}; ssize_t n=read(fd,buf,sizeof(buf)-1); if(n<=0){close(fd);return;}
    std::string req(buf,n),body;
    auto bp=req.find("\r\n\r\n"); body=(bp!=std::string::npos)?req.substr(bp+4):req;
    if(req.substr(0,3)=="GET"){
        auto result=dispatch_rpc("{\"method\":\"getinfo\",\"id\":1}");
        std::string resp="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: "+std::to_string(result.size())+"\r\n\r\n"+result;
        write(fd,resp.c_str(),resp.size());close(fd);return;
    }
    if(req.substr(0,7)=="OPTIONS"){
        std::string resp="HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: POST,GET,OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type,Authorization\r\nContent-Length: 0\r\n\r\n";
        write(fd,resp.c_str(),resp.size());close(fd);return;
    }
    auto result=dispatch_rpc(body);
    std::string resp="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: "+std::to_string(result.size())+"\r\n\r\n"+result;
    write(fd,resp.c_str(),resp.size());close(fd);
}

// === Genesis loader ===
static int64_t jint(const std::string& j,const std::string& k){
    std::string n="\""+k+"\"";auto p=j.find(n);if(p==std::string::npos)return-1;p=j.find(':',p+n.size());if(p==std::string::npos)return-1;p++;while(p<j.size()&&j[p]==' ')p++;return std::stoll(j.substr(p));
}
static std::string jstr(const std::string& j,const std::string& k){
    std::string n="\""+k+"\"";auto p=j.find(n);if(p==std::string::npos)return"";p=j.find('"',p+n.size()+1);if(p==std::string::npos)return"";auto e=j.find('"',p+1);if(e==std::string::npos)return"";return j.substr(p+1,e-p-1);
}
static bool load_genesis(const std::string& path) {
    std::ifstream f(path); if(!f)return false;
    std::string json((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
    std::string bid=jstr(json,"block_id"); if(bid.size()!=64)return false;
    StoredBlock g; g.block_id=from_hex(bid); g.prev_hash=from_hex(jstr(json,"prev_hash"));
    g.merkle_root=from_hex(jstr(json,"merkle_root")); g.timestamp=jint(json,"timestamp");
    g.bits_q=(uint32_t)jint(json,"bits_q"); g.nonce=(uint64_t)jint(json,"nonce"); g.height=0;
    g.subsidy=jint(json,"subsidy_stocks");
    g_genesis_hash=g.block_id; g_blocks.push_back(g); g_chain_height=0;

    // Init UTXO set
    int64_t miner_amt=jint(json,"miner"),gold_amt=jint(json,"gold_vault"),popc_amt=jint(json,"popc_pool");
    if(miner_amt<=0||gold_amt<=0||popc_amt<=0){auto sp=coinbase_split(g.subsidy);miner_amt=sp.miner;gold_amt=sp.gold_vault;popc_amt=sp.popc_pool;}
    struct{const char*addr;int64_t amt;uint8_t type;}cb[3]={
        {ADDR_MINER_FOUNDER,miner_amt,OUT_COINBASE_MINER},
        {ADDR_GOLD_VAULT,gold_amt,OUT_COINBASE_GOLD},
        {ADDR_POPC_POOL,popc_amt,OUT_COINBASE_POPC},
    };
    for(int i=0;i<3;++i){
        PubKeyHash pkh{}; address_decode(cb[i].addr,pkh);
        OutPoint op; op.txid=g_genesis_hash; op.index=(uint32_t)i;
        UTXOEntry e; e.amount=cb[i].amt; e.type=cb[i].type; e.pubkey_hash=pkh; e.height=0; e.is_coinbase=true;
        std::string err; g_utxo_set.AddUTXO(op,e,&err);
    }
    printf("UTXO set: %zu entries, %s SOST\n",g_utxo_set.Size(),format_sost(miner_amt+gold_amt+popc_amt).c_str());
    return true;
}

// === Chain loader ===
static bool load_chain(const std::string& path) {
    std::ifstream f(path); if(!f) return false;
    std::string json((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
    int64_t ch=jint(json,"chain_height"); if(ch<0) return false;
    size_t search=json.find("\"blocks\""); if(search==std::string::npos) return false;
    search=json.find('[',search); if(search==std::string::npos) return false;
    while(true){
        auto bs=json.find('{',search); if(bs==std::string::npos) break;
        auto be=json.find('}',bs); if(be==std::string::npos) break;
        std::string bj=json.substr(bs,be-bs+1); search=be+1;
        std::string bid=jstr(bj,"block_id"); if(bid.size()!=64) continue;
        int64_t height=jint(bj,"height"); if(height==0) continue;
        StoredBlock sb;
        sb.block_id=from_hex(bid); sb.prev_hash=from_hex(jstr(bj,"prev_hash"));
        sb.merkle_root={}; sb.merkle_root.fill(0x11);
        sb.timestamp=jint(bj,"timestamp"); sb.bits_q=(uint32_t)jint(bj,"bits_q");
        sb.nonce=(uint64_t)jint(bj,"nonce"); sb.height=height;
        sb.subsidy=jint(bj,"subsidy");
        g_blocks.push_back(sb);
        int64_t m_amt=jint(bj,"miner"),g_amt=jint(bj,"gold_vault"),p_amt=jint(bj,"popc_pool");
        struct{const char*a;int64_t v;uint8_t t;}cb[3]={
            {ADDR_MINER_FOUNDER,m_amt,OUT_COINBASE_MINER},
            {ADDR_GOLD_VAULT,g_amt,OUT_COINBASE_GOLD},
            {ADDR_POPC_POOL,p_amt,OUT_COINBASE_POPC},
        };
        for(int i=0;i<3;++i){
            PubKeyHash pkh{}; address_decode(cb[i].a,pkh);
            OutPoint op; op.txid=sb.block_id; op.index=(uint32_t)i;
            UTXOEntry e; e.amount=cb[i].v; e.type=cb[i].t;
            e.pubkey_hash=pkh; e.height=height; e.is_coinbase=true;
            std::string err; g_utxo_set.AddUTXO(op,e,&err);
        }
    }
    g_chain_height=ch;
    printf("Chain loaded: %zu blocks, height=%lld, UTXOs=%zu\n",
           g_blocks.size(),(long long)g_chain_height,g_utxo_set.Size());
    return true;
}

// === main ===
int main(int argc,char**argv){
    int port=18232; std::string genesis_path="genesis_block.json";
    for(int i=1;i<argc;++i){
        if(!strcmp(argv[i],"--wallet")&&i+1<argc)g_wallet_path=argv[++i];
        else if(!strcmp(argv[i],"--port")&&i+1<argc)port=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--genesis")&&i+1<argc)genesis_path=argv[++i];
        else if(!strcmp(argv[i],"--test-height")&&i+1<argc) g_chain_height=atoi(argv[++i]);
	else if(!strcmp(argv[i],"--chain")&&i+1<argc) ;// handled below
        else if(!strcmp(argv[i],"--help")||!strcmp(argv[i],"-h")){
            printf("SOST RPC Daemon v0.3\n  --wallet <path>\n  --port <port>\n  --genesis <path>\n  --test-height <n>\n");return 0;
        }
    }
    printf("=== SOST RPC Daemon v0.3 ===\n");
    if(!load_genesis(genesis_path)){fprintf(stderr,"Error: cannot load genesis\n");return 1;}
    for(int i=1;i<argc;++i) if(!strcmp(argv[i],"--test-height")&&i+1<argc) g_chain_height=atoi(argv[i+1]);
    // Load chain if provided
    for(int i=1;i<argc;++i) if(!strcmp(argv[i],"--chain")&&i+1<argc){ load_chain(argv[i+1]); break; }
    printf("Genesis: %s (height=%lld)\n",to_hex(g_genesis_hash.data(),32).c_str(),(long long)g_chain_height);
    std::string err;
    if(!g_wallet.load(g_wallet_path,&err)){fprintf(stderr,"Error: %s\nUse sost-cli newwallet first.\n",err.c_str());return 1;}
    printf("Wallet: %zu keys, %s SOST\n",g_wallet.num_keys(),format_sost(g_wallet.balance()).c_str());
    printf("Mempool: %zu txs | UTXO set: %zu entries\n\n",g_mempool.Size(),g_utxo_set.Size());
    int srv=socket(AF_INET,SOCK_STREAM,0); if(srv<0){perror("socket");return 1;}
    int opt=1; setsockopt(srv,SOL_SOCKET,SO_REUSEADDR,&opt,sizeof(opt));
    struct sockaddr_in addr{}; addr.sin_family=AF_INET; addr.sin_addr.s_addr=INADDR_ANY; addr.sin_port=htons(port);
    if(bind(srv,(struct sockaddr*)&addr,sizeof(addr))<0){perror("bind");return 1;}
    listen(srv,10);
    printf("RPC on port %d — 13 methods available\n",port);
    printf("Test: curl http://localhost:%d/\n\n",port);
    while(true){int cl=accept(srv,nullptr,nullptr);if(cl<0)continue;handle_connection(cl);}
    close(srv); return 0;
}




