// sost-node.cpp — SOST Full Node v0.2
//
// Combines: P2P networking + JSON-RPC + chain sync + tx relay
//
// P2P Protocol (TCP, little-endian):
//   [4 bytes MAGIC] [4 bytes cmd] [4 bytes payload_len] [payload...]
//
// Commands:
//   "VERS" - version handshake: height(8) + tip_hash(32)
//   "VACK" - version ack
//   "GETB" - getblocks: from_height(8)
//   "BLCK" - block data: block JSON
//   "TXXX" - transaction: raw tx hex
//   "PING" - keepalive
//   "PONG" - keepalive response
//   "GETM" - get mempool txids
//   "MPTX" - mempool txids list
//
// Usage:
//   sost-node --genesis genesis_block.json --chain chain.json --port 19333
//   sost-node --genesis genesis_block.json --connect 1.2.3.4:19333

#include "sost/wallet.h"
#include "sost/address.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/types.h"
#include "sost/utxo_set.h"
#include "sost/mempool.h"
#include "sost/tx_validation.h"
#include "sost/emission.h"
#include "sost/pow/casert.h"

#include <fstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>
#include <map>
#include <set>
#include <mutex>
#include <functional>
#include <ctime>
#include <atomic>
#include <thread>
#include <chrono>

using namespace sost;

// =============================================================================
// Globals
// =============================================================================

static Wallet       g_wallet;
static UtxoSet      g_utxo_set;
static Mempool      g_mempool;
static std::string  g_wallet_path = "wallet.json";
static Hash256      g_genesis_hash{};
static int64_t      g_chain_height = 0;
static std::mutex   g_chain_mu;

struct StoredBlock {
    Hash256 block_id, prev_hash, merkle_root;
    int64_t timestamp; uint32_t bits_q; uint64_t nonce;
    int64_t height, subsidy;
    int64_t miner_reward, gold_vault_reward, popc_pool_reward;
};
static std::vector<StoredBlock> g_blocks;

// P2P state
static const uint32_t P2P_MAGIC = 0x534F5354; // "SOST"
static const int P2P_PORT_DEFAULT = 19333;
static const int RPC_PORT_DEFAULT = 18232;
static std::atomic<bool> g_running{true};

struct Peer {
    int fd;
    std::string addr;
    int64_t their_height;
    bool version_sent;
    bool version_acked;
    bool outbound;
    time_t last_seen;
};
static std::vector<Peer> g_peers;
static std::mutex g_peers_mu;

// =============================================================================
// Helpers (shared with RPC)
// =============================================================================

static std::string to_hex(const uint8_t* d, size_t len) {
    static const char* hx = "0123456789abcdef";
    std::string s; s.reserve(len*2);
    for(size_t i=0;i<len;++i){s+=hx[d[i]>>4];s+=hx[d[i]&0xF];}
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
    return buf;
}
static std::string json_escape(const std::string& s) {
    std::string o; for(char c:s){if(c=='"')o+="\\\"";else if(c=='\\')o+="\\\\";else if(c=='\n')o+="\\n";else o+=c;} return o;
}

// =============================================================================
// JSON parser
// =============================================================================

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
        if(inner[i]=='"'){
            size_t q=i+1;
            while(q<inner.size()){if(inner[q]=='"'&&(q==0||inner[q-1]!='\\'))break;q++;}
            if(q>=inner.size())break;
            std::string val=inner.substr(i+1,q-i-1);
            std::string unesc; for(size_t k=0;k<val.size();k++){if(val[k]=='\\'&&k+1<val.size()&&val[k+1]=='"'){unesc+='"';k++;}else unesc+=val[k];}
            r.push_back(unesc);i=q+1;
        }
        else{auto p=inner.find_first_of(",] \t\n\r",i);if(p==std::string::npos)p=inner.size();r.push_back(inner.substr(i,p-i));i=p;}
    }
    return r;
}
static int64_t jint(const std::string& j,const std::string& k){
    std::string n="\""+k+"\"";auto p=j.find(n);if(p==std::string::npos)return-1;p=j.find(':',p+n.size());if(p==std::string::npos)return-1;p++;while(p<j.size()&&j[p]==' ')p++;return std::stoll(j.substr(p));
}
static std::string jstr(const std::string& j,const std::string& k){
    std::string n="\""+k+"\"";auto p=j.find(n);if(p==std::string::npos)return"";p=j.find('"',p+n.size()+1);if(p==std::string::npos)return"";auto e=j.find('"',p+1);if(e==std::string::npos)return"";return j.substr(p+1,e-p-1);
}

// Forward declarations
static void p2p_broadcast_tx(const std::string& hex_str);
static bool process_block(const std::string& block_json);

// =============================================================================
// RPC (reuse from sost-rpc.cpp, condensed)
// =============================================================================

static std::string rpc_result(const std::string& id, const std::string& r) {
    return "{\"jsonrpc\":\"2.0\",\"id\":"+id+",\"result\":"+r+"}";
}
static std::string rpc_error(const std::string& id, int code, const std::string& msg) {
    return "{\"jsonrpc\":\"2.0\",\"id\":"+id+",\"error\":{\"code\":"+std::to_string(code)+",\"message\":\""+json_escape(msg)+"\"}}";
}

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
             <<",\"nonce\":"<<b.nonce<<",\"subsidy\":"<<b.subsidy;
            // Compute cASERT mode for this block
            std::vector<BlockMeta> meta;
            for(size_t j=0;j<=size_t(b.height)&&j<g_blocks.size();++j){
                BlockMeta bm; bm.block_id=g_blocks[j].block_id;
                bm.height=g_blocks[j].height; bm.time=g_blocks[j].timestamp;
                bm.powDiffQ=g_blocks[j].bits_q; meta.push_back(bm);
            }
            auto cd=casert_mode_from_chain(meta,b.height+1);
            s<<",\"casert_mode\":\""<<casert_mode_str(cd.mode)
             <<"\",\"casert_signal\":"<<cd.signal_s<<"}";
            return rpc_result(id,s.str());
        }
    }
    return rpc_error(id,-5,"Block not found");
}
static std::string handle_getinfo(const std::string& id, const std::vector<std::string>&) {
    size_t peers_count;
    {std::lock_guard<std::mutex> lk(g_peers_mu); peers_count=g_peers.size();}
    std::ostringstream s;
    s<<"{\"version\":\"0.5.0\",\"protocolversion\":1,\"blocks\":"<<g_chain_height
     <<",\"connections\":"<<peers_count
     <<",\"difficulty\":"<<(g_blocks.empty()?0:g_blocks.back().bits_q)
     <<",\"testnet\":false,\"balance\":\""<<format_sost(g_wallet.balance())
     <<"\",\"keypoolsize\":"<<g_wallet.num_keys()
     <<",\"mempool_size\":"<<g_mempool.Size()
     <<",\"utxo_count\":"<<g_utxo_set.Size()<<"}";
    return rpc_result(id,s.str());
}
static std::string handle_getbalance(const std::string& id, const std::vector<std::string>&) {
    double bal=(double)g_wallet.balance()/(double)sost::STOCKS_PER_SOST;
    char buf[64]; snprintf(buf,sizeof(buf),"%.8f",bal);
    return rpc_result(id,buf);
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
     <<"\",\"ismine\":"<<(mine?"true":"false")<<"}";
    return rpc_result(id,s.str());
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
    p2p_broadcast_tx(hex_str);
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
static std::string handle_getpeerinfo(const std::string& id, const std::vector<std::string>&) {
    std::lock_guard<std::mutex> lk(g_peers_mu);
    std::ostringstream s; s<<"[";
    for(size_t i=0;i<g_peers.size();++i){
        if(i)s<<",";
        s<<"{\"addr\":\""<<g_peers[i].addr<<"\",\"height\":"<<g_peers[i].their_height
         <<",\"inbound\":"<<(!g_peers[i].outbound?"true":"false")<<"}";
    }
    s<<"]"; return rpc_result(id,s.str());
}

static std::string handle_getaddressinfo(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing address");
    if(!address_valid(p[0])) return rpc_error(id,-5,"invalid address");
    PubKeyHash target_pkh{}; address_decode(p[0],target_pkh);
    const auto& umap=g_utxo_set.GetMap();
    int64_t balance=0; int utxo_count=0;
    std::ostringstream utxos; utxos<<"[";
    for(const auto& [op,entry]:umap){
        if(entry.pubkey_hash==target_pkh){
            if(utxo_count)utxos<<",";
            utxos<<"{\"txid\":\""<<to_hex(op.txid.data(),32)<<"\",\"vout\":"<<op.index
                 <<",\"amount\":"<<format_sost(entry.amount)<<",\"height\":"<<entry.height
                 <<",\"coinbase\":"<<(entry.is_coinbase?"true":"false")<<"}";
            balance+=entry.amount; utxo_count++;
        }
    }
    utxos<<"]";
    bool mine=g_wallet.has_address(p[0]);
    std::ostringstream s;
    s<<"{\"address\":\""<<p[0]<<"\",\"balance\":"<<format_sost(balance)
     <<",\"utxo_count\":"<<utxo_count<<",\"ismine\":"<<(mine?"true":"false")
     <<",\"utxos\":"<<utxos.str()<<"}";
    return rpc_result(id,s.str());
}

static std::string handle_submitblock(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing block JSON");
    if(process_block(p[0])) return rpc_result(id,"true");
    return rpc_error(id,-25,"Block rejected");
}

static std::string handle_getblocktemplate(const std::string& id, const std::vector<std::string>&) {
    auto tmpl = g_mempool.BuildBlockTemplate();
    std::ostringstream s;
    s << "{\"transactions\":[";
    for (size_t i = 0; i < tmpl.txs.size(); ++i) {
        if (i) s << ",";
        std::vector<Byte> raw;
        std::string err;
        if (tmpl.txs[i].Serialize(raw, &err)) {
            s << "\"" << to_hex(raw.data(), raw.size()) << "\"";
        }
    }
    s << "],\"total_fees\":" << tmpl.total_fees
      << ",\"count\":" << tmpl.txs.size()
      << ",\"mempool_size\":" << g_mempool.Size() << "}";
    return rpc_result(id, s.str());
}

// Dispatch
using RpcHandler=std::function<std::string(const std::string&,const std::vector<std::string>&)>;
static std::map<std::string,RpcHandler> g_handlers={
    {"getblockcount",handle_getblockcount},{"getblockhash",handle_getblockhash},{"getblock",handle_getblock},
    {"getinfo",handle_getinfo},{"getbalance",handle_getbalance},{"getnewaddress",handle_getnewaddress},
    {"validateaddress",handle_validateaddress},{"listunspent",handle_listunspent},{"gettxout",handle_gettxout},
    {"sendrawtransaction",handle_sendrawtransaction},{"getmempoolinfo",handle_getmempoolinfo},
    {"getrawmempool",handle_getrawmempool},{"getrawtransaction",handle_getrawtransaction},
    {"getpeerinfo",handle_getpeerinfo},{"getaddressinfo",handle_getaddressinfo},
    {"submitblock",handle_submitblock},
    {"getblocktemplate",handle_getblocktemplate},
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

// =============================================================================
// P2P Protocol
// =============================================================================

struct P2PMsg {
    char cmd[5];
    std::vector<uint8_t> payload;
};

static void write_u32(uint8_t* p, uint32_t v) {
    p[0]=v&0xFF; p[1]=(v>>8)&0xFF; p[2]=(v>>16)&0xFF; p[3]=(v>>24)&0xFF;
}
static uint32_t read_u32(const uint8_t* p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void write_i64(uint8_t* p, int64_t v) {
    for(int i=0;i<8;++i) p[i]=(uint8_t)((v>>(i*8))&0xFF);
}
static int64_t read_i64(const uint8_t* p) {
    int64_t v=0; for(int i=0;i<8;++i) v|=((int64_t)p[i]<<(i*8)); return v;
}

static bool read_exact(int fd, uint8_t* buf, size_t len) {
    size_t got=0;
    while(got<len){
        ssize_t n=read(fd,buf+got,len-got);
        if(n<=0) return false;
        got+=n;
    }
    return true;
}

static bool p2p_send(int fd, const char* cmd, const uint8_t* payload, size_t len) {
    uint8_t hdr[12];
    write_u32(hdr, P2P_MAGIC);
    memcpy(hdr+4, cmd, 4);
    write_u32(hdr+8, (uint32_t)len);
    if(write(fd, hdr, 12)!=12) return false;
    if(len>0 && write(fd, payload, len)!=(ssize_t)len) return false;
    return true;
}

static bool p2p_recv(int fd, P2PMsg& msg) {
    uint8_t hdr[12];
    if(!read_exact(fd, hdr, 12)) return false;
    uint32_t magic=read_u32(hdr);
    if(magic!=P2P_MAGIC) return false;
    memcpy(msg.cmd, hdr+4, 4); msg.cmd[4]=0;
    uint32_t len=read_u32(hdr+8);
    if(len>10*1024*1024) return false;
    msg.payload.resize(len);
    if(len>0 && !read_exact(fd, msg.payload.data(), len)) return false;
    return true;
}

static void p2p_send_version(int fd) {
    uint8_t buf[40];
    write_i64(buf, g_chain_height);
    memcpy(buf+8, g_genesis_hash.data(), 32);
    p2p_send(fd, "VERS", buf, 40);
}

static void p2p_send_block(int fd, int64_t h) {
    std::lock_guard<std::mutex> lk(g_chain_mu);
    if(h<0||h>=(int64_t)g_blocks.size()) return;
    const auto& b=g_blocks[h];
    std::ostringstream s;
    s<<"{\"block_id\":\""<<to_hex(b.block_id.data(),32)
     <<"\",\"prev_hash\":\""<<to_hex(b.prev_hash.data(),32)
     <<"\",\"merkle_root\":\""<<to_hex(b.merkle_root.data(),32)
     <<"\",\"height\":"<<b.height
     <<",\"timestamp\":"<<b.timestamp
     <<",\"bits_q\":"<<b.bits_q
     <<",\"nonce\":"<<b.nonce
     <<",\"subsidy\":"<<b.subsidy
     <<",\"miner\":"<<b.miner_reward
     <<",\"gold_vault\":"<<b.gold_vault_reward
     <<",\"popc_pool\":"<<b.popc_pool_reward<<"}";
    std::string js=s.str();
    p2p_send(fd, "BLCK", (const uint8_t*)js.data(), js.size());
}

static void p2p_broadcast_tx(const std::string& hex_str) {
    std::lock_guard<std::mutex> lk(g_peers_mu);
    for(auto& p:g_peers){
        if(p.version_acked){
            p2p_send(p.fd, "TXXX", (const uint8_t*)hex_str.data(), hex_str.size());
        }
    }
}

// Process received block (with standard transaction support)
static bool process_block(const std::string& block_json) {
    std::string bid=jstr(block_json,"block_id"); if(bid.size()!=64) return false;
    int64_t height=jint(block_json,"height");

    std::lock_guard<std::mutex> lk(g_chain_mu);
    if(height<(int64_t)g_blocks.size()) return false;
    if(height!=(int64_t)g_blocks.size()) return false;

    StoredBlock sb;
    sb.block_id=from_hex(bid); sb.prev_hash=from_hex(jstr(block_json,"prev_hash"));
    sb.merkle_root=from_hex(jstr(block_json,"merkle_root"));
    sb.timestamp=jint(block_json,"timestamp"); sb.bits_q=(uint32_t)jint(block_json,"bits_q");
    sb.nonce=(uint64_t)jint(block_json,"nonce"); sb.height=height;
    sb.subsidy=jint(block_json,"subsidy");
    sb.miner_reward=jint(block_json,"miner");
    sb.gold_vault_reward=jint(block_json,"gold_vault");
    sb.popc_pool_reward=jint(block_json,"popc_pool");

    if(g_blocks.size()>0 && sb.prev_hash!=g_blocks.back().block_id) return false;

    g_blocks.push_back(sb);
    g_chain_height=height;

    // 1. Añadir UTXOs de coinbase
    struct{const char*a;int64_t v;uint8_t t;}cb[3]={
        {ADDR_MINER_FOUNDER,sb.miner_reward,OUT_COINBASE_MINER},
        {ADDR_GOLD_VAULT,sb.gold_vault_reward,OUT_COINBASE_GOLD},
        {ADDR_POPC_POOL,sb.popc_pool_reward,OUT_COINBASE_POPC},
    };
    for(int i=0;i<3;++i){
        PubKeyHash pkh{}; address_decode(cb[i].a,pkh);
        OutPoint op; op.txid=sb.block_id; op.index=(uint32_t)i;
        UTXOEntry e; e.amount=cb[i].v; e.type=cb[i].t;
        e.pubkey_hash=pkh; e.height=height; e.is_coinbase=true;
        std::string err; g_utxo_set.AddUTXO(op,e,&err);
        // Actualizar wallet si la dirección es nuestra
        std::string addr=address_encode(pkh);
        if(g_wallet.has_address(addr)){
            WalletUTXO wu; wu.txid=op.txid; wu.vout=op.index;
            wu.amount=e.amount; wu.output_type=e.type;
            wu.pkh=pkh; wu.height=height; wu.spent=false;
            g_wallet.add_utxo(wu);
        }
    }

    // 2. Procesar transacciones estándar del bloque
    size_t tx_count = 0;
    auto tx_pos = block_json.find("\"transactions\"");
    if (tx_pos != std::string::npos) {
        auto arr_start = block_json.find('[', tx_pos);
        auto arr_end = block_json.find(']', arr_start);
        if (arr_start != std::string::npos && arr_end != std::string::npos) {
            std::string arr = block_json.substr(arr_start + 1, arr_end - arr_start - 1);
            size_t p = 0;
            std::vector<Transaction> block_std_txs;

            while (p < arr.size()) {
                auto q1 = arr.find('"', p);
                if (q1 == std::string::npos) break;
                auto q2 = arr.find('"', q1 + 1);
                if (q2 == std::string::npos) break;
                std::string tx_hex = arr.substr(q1 + 1, q2 - q1 - 1);
                p = q2 + 1;

                if (tx_hex.empty() || tx_hex.size() % 2 != 0) continue;

                std::vector<Byte> raw;
                raw.reserve(tx_hex.size() / 2);
                bool hex_ok = true;
                for (size_t i = 0; i < tx_hex.size(); i += 2) {
                    uint8_t b;
                    if (!hex_to_bytes(tx_hex.substr(i, 2), &b, 1)) { hex_ok = false; break; }
                    raw.push_back(b);
                }
                if (!hex_ok) continue;

                Transaction tx;
                std::string err;
                if (!Transaction::Deserialize(raw, tx, &err)) {
                    printf("[BLOCK] WARNING: skip malformed tx: %s\n", err.c_str());
                    continue;
                }
                if (tx.tx_type == TX_TYPE_COINBASE) continue;

                block_std_txs.push_back(tx);
            }

            for (const auto& tx : block_std_txs) {
                Hash256 txid{};
                std::string err;
                if (!tx.ComputeTxId(txid, &err)) {
                    printf("[BLOCK] WARNING: cannot compute txid: %s\n", err.c_str());
                    continue;
                }

                // Gastar inputs
                for (const auto& txin : tx.inputs) {
                    OutPoint op{txin.prev_txid, txin.prev_index};
                    g_utxo_set.SpendUTXO(op, nullptr, nullptr);
                    g_wallet.mark_spent(txin.prev_txid, txin.prev_index);
                }

                // Crear outputs
                for (size_t i = 0; i < tx.outputs.size(); ++i) {
                    const auto& txout = tx.outputs[i];
                    OutPoint op{txid, (uint32_t)i};
                    UTXOEntry entry;
                    entry.amount = txout.amount;
                    entry.type = txout.type;
                    entry.pubkey_hash = txout.pubkey_hash;
                    entry.height = height;
                    entry.is_coinbase = false;
                    std::string aerr;
                    g_utxo_set.AddUTXO(op, entry, &aerr);

                    std::string addr = address_encode(txout.pubkey_hash);
                    if (g_wallet.has_address(addr)) {
                        WalletUTXO wu;
                        wu.txid = txid;
                        wu.vout = (uint32_t)i;
                        wu.amount = txout.amount;
                        wu.output_type = txout.type;
                        wu.pkh = txout.pubkey_hash;
                        wu.height = height;
                        wu.spent = false;
                        g_wallet.add_utxo(wu);
                    }
                }

                tx_count++;
                printf("[BLOCK] TX confirmed: %s\n",
                       to_hex(txid.data(), 32).substr(0, 16).c_str());
            }

            // 3. Limpiar mempool
            if (!block_std_txs.empty()) {
                size_t removed = g_mempool.RemoveForBlock(block_std_txs);
                if (removed > 0)
                    printf("[BLOCK] Mempool: %zu txs removed\n", removed);
            }
        }
    }

    printf("[BLOCK] Height %lld accepted: %s (%zu std txs, UTXOs: %zu)\n",
           (long long)height, bid.substr(0, 16).c_str(),
           tx_count, g_utxo_set.Size());
    return true;
}

// Process received tx
static bool process_tx(const std::string& hex_str) {
    std::vector<Byte> raw; raw.reserve(hex_str.size()/2);
    for(size_t i=0;i<hex_str.size();i+=2){
        uint8_t b; if(!hex_to_bytes(hex_str.substr(i,2),&b,1)) return false;
        raw.push_back(b);
    }
    Transaction tx; std::string err;
    if(!Transaction::Deserialize(raw,tx,&err)) return false;
    Hash256 txid; if(!tx.ComputeTxId(txid,&err)) return false;
    TxValidationContext ctx; ctx.genesis_hash=g_genesis_hash; ctx.spend_height=g_chain_height+1;
    int64_t now=(int64_t)time(nullptr);
    auto result=g_mempool.AcceptToMempool(tx,g_utxo_set,ctx,now);
    if(!result.accepted) return false;
    printf("[P2P] TX accepted: %s\n",to_hex(txid.data(),32).substr(0,16).c_str());
    return true;
}

// Handle one peer connection
static void handle_peer(int fd, const std::string& addr, bool outbound) {
    {
        std::lock_guard<std::mutex> lk(g_peers_mu);
        Peer p; p.fd=fd; p.addr=addr; p.their_height=-1;
        p.version_sent=false; p.version_acked=false;
        p.outbound=outbound; p.last_seen=time(nullptr);
        g_peers.push_back(p);
    }
    printf("[P2P] Peer connected: %s (%s)\n",addr.c_str(),outbound?"outbound":"inbound");

    p2p_send_version(fd);

    struct timeval tv; tv.tv_sec=30; tv.tv_usec=0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    while(g_running) {
        P2PMsg msg;
        if(!p2p_recv(fd, msg)) break;

        {
            std::lock_guard<std::mutex> lk(g_peers_mu);
            for(auto& p:g_peers) if(p.fd==fd) { p.last_seen=time(nullptr); break; }
        }

        if(!strcmp(msg.cmd,"VERS")) {
            if(msg.payload.size()>=40){
                int64_t their_h=read_i64(msg.payload.data());
                Hash256 their_genesis;
                memcpy(their_genesis.data(), msg.payload.data()+8, 32);
                if(their_genesis!=g_genesis_hash){
                    printf("[P2P] %s: genesis mismatch, disconnecting\n",addr.c_str());
                    break;
                }
                {
                    std::lock_guard<std::mutex> lk(g_peers_mu);
                    for(auto& p:g_peers) if(p.fd==fd){p.their_height=their_h;p.version_acked=true;break;}
                }
                p2p_send(fd, "VACK", nullptr, 0);
                printf("[P2P] %s: version OK, their height=%lld\n",addr.c_str(),(long long)their_h);

                if(their_h > g_chain_height){
                    uint8_t buf[8];
                    write_i64(buf, g_chain_height+1);
                    p2p_send(fd, "GETB", buf, 8);
                    printf("[P2P] Requesting blocks from %lld\n",(long long)(g_chain_height+1));
                }
            }
        }
        else if(!strcmp(msg.cmd,"VACK")) {
            std::lock_guard<std::mutex> lk(g_peers_mu);
            for(auto& p:g_peers) if(p.fd==fd){p.version_acked=true;break;}
        }
        else if(!strcmp(msg.cmd,"GETB")) {
            if(msg.payload.size()>=8){
                int64_t from_h=read_i64(msg.payload.data());
                for(int64_t h=from_h;h<=g_chain_height && h<from_h+500;++h){
                    p2p_send_block(fd, h);
                }
                p2p_send(fd, "DONE", nullptr, 0);
            }
        }
        else if(!strcmp(msg.cmd,"BLCK")) {
            std::string block_json((char*)msg.payload.data(), msg.payload.size());
            process_block(block_json);
        }
        else if(!strcmp(msg.cmd,"TXXX")) {
            std::string hex_str((char*)msg.payload.data(), msg.payload.size());
            if(process_tx(hex_str)){
                std::lock_guard<std::mutex> lk(g_peers_mu);
                for(auto& p:g_peers){
                    if(p.fd!=fd && p.version_acked){
                        p2p_send(p.fd, "TXXX", msg.payload.data(), msg.payload.size());
                    }
                }
            }
        }
        else if(!strcmp(msg.cmd,"PING")) {
            p2p_send(fd, "PONG", nullptr, 0);
        }
        else if(!strcmp(msg.cmd,"DONE")) {
            int64_t their_h=-1;
            {
                std::lock_guard<std::mutex> lk(g_peers_mu);
                for(auto& p:g_peers) if(p.fd==fd){their_h=p.their_height;break;}
            }
            if(g_chain_height<their_h){
                uint8_t buf[8];
                write_i64(buf, g_chain_height+1);
                p2p_send(fd, "GETB", buf, 8);
                printf("[P2P] Batch done, requesting from %lld\n",(long long)(g_chain_height+1));
            } else {
                printf("[P2P] Sync complete, height=%lld\n",(long long)g_chain_height);
            }
        }
    }

    close(fd);
    {
        std::lock_guard<std::mutex> lk(g_peers_mu);
        g_peers.erase(std::remove_if(g_peers.begin(),g_peers.end(),
            [fd](const Peer& p){return p.fd==fd;}),g_peers.end());
    }
    printf("[P2P] Peer disconnected: %s\n",addr.c_str());
}

// =============================================================================
// Loaders
// =============================================================================

static bool load_genesis(const std::string& path) {
    std::ifstream f(path); if(!f)return false;
    std::string json((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
    std::string bid=jstr(json,"block_id"); if(bid.size()!=64)return false;
    StoredBlock g; g.block_id=from_hex(bid); g.prev_hash=from_hex(jstr(json,"prev_hash"));
    g.merkle_root=from_hex(jstr(json,"merkle_root")); g.timestamp=jint(json,"timestamp");
    g.bits_q=(uint32_t)jint(json,"bits_q"); g.nonce=(uint64_t)jint(json,"nonce"); g.height=0;
    g.subsidy=jint(json,"subsidy_stocks");
    auto sp=coinbase_split(g.subsidy);
    g.miner_reward=sp.miner; g.gold_vault_reward=sp.gold_vault; g.popc_pool_reward=sp.popc_pool;
    g_genesis_hash=g.block_id; g_blocks.push_back(g); g_chain_height=0;
    struct{const char*addr;int64_t amt;uint8_t type;}cb[3]={
        {ADDR_MINER_FOUNDER,sp.miner,OUT_COINBASE_MINER},
        {ADDR_GOLD_VAULT,sp.gold_vault,OUT_COINBASE_GOLD},
        {ADDR_POPC_POOL,sp.popc_pool,OUT_COINBASE_POPC},
    };
    for(int i=0;i<3;++i){
        PubKeyHash pkh{}; address_decode(cb[i].addr,pkh);
        OutPoint op; op.txid=g_genesis_hash; op.index=(uint32_t)i;
        UTXOEntry e; e.amount=cb[i].amt; e.type=cb[i].type; e.pubkey_hash=pkh; e.height=0; e.is_coinbase=true;
        std::string err; g_utxo_set.AddUTXO(op,e,&err);
    }
    return true;
}

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
        std::string mr=jstr(bj,"merkle_root");
        if(mr.size()==64) sb.merkle_root=from_hex(mr);
        else { sb.merkle_root={}; sb.merkle_root.fill(0x11); }
        sb.timestamp=jint(bj,"timestamp"); sb.bits_q=(uint32_t)jint(bj,"bits_q");
        sb.nonce=(uint64_t)jint(bj,"nonce"); sb.height=height;
        sb.subsidy=jint(bj,"subsidy");
        sb.miner_reward=jint(bj,"miner"); sb.gold_vault_reward=jint(bj,"gold_vault"); sb.popc_pool_reward=jint(bj,"popc_pool");
        g_blocks.push_back(sb);
        struct{const char*a;int64_t v;uint8_t t;}cb[3]={
            {ADDR_MINER_FOUNDER,sb.miner_reward,OUT_COINBASE_MINER},
            {ADDR_GOLD_VAULT,sb.gold_vault_reward,OUT_COINBASE_GOLD},
            {ADDR_POPC_POOL,sb.popc_pool_reward,OUT_COINBASE_POPC},
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
    return true;
}

// =============================================================================
// RPC Server Thread
// =============================================================================

static void rpc_handle_connection(int fd) {
    char buf[65536]{};
    ssize_t total=0;
    while(total<(ssize_t)sizeof(buf)-1){
        ssize_t n=read(fd,buf+total,sizeof(buf)-1-total);
        if(n<=0) break;
        total+=n; buf[total]=0;
        if(strstr(buf,"\r\n\r\n")) break;
    }
    if(total<=0){close(fd);return;}
    std::string req(buf,total);
    if(req.substr(0,3)=="GET"){
        auto result=dispatch_rpc("{\"method\":\"getinfo\",\"id\":1}");
        std::string resp="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Headers: Content-Type\r\nContent-Length: "+std::to_string(result.size())+"\r\n\r\n"+result;
        write(fd,resp.c_str(),resp.size());close(fd);return;
    }
    if(req.substr(0,7)=="OPTIONS"){
        std::string resp="HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: POST,GET,OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type,Authorization\r\nAccess-Control-Max-Age: 86400\r\nContent-Length: 0\r\n\r\n";
        write(fd,resp.c_str(),resp.size());close(fd);return;
    }
    std::string body;
    auto bp=req.find("\r\n\r\n");
    if(bp!=std::string::npos){
        body=req.substr(bp+4);
        int content_len=0;
        auto cl=req.find("Content-Length:");
        if(cl==std::string::npos) cl=req.find("content-length:");
        if(cl!=std::string::npos) content_len=atoi(req.c_str()+cl+15);
        while((int)body.size()<content_len){
            char tmp[4096];
            ssize_t n=read(fd,tmp,std::min((int)sizeof(tmp),content_len-(int)body.size()));
            if(n<=0) break;
            body.append(tmp,n);
        }
    } else { body=req; }
    auto result=dispatch_rpc(body);
    std::string resp="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Headers: Content-Type\r\nAccess-Control-Max-Age: 86400\r\nContent-Length: "+std::to_string(result.size())+"\r\n\r\n"+result;
    write(fd,resp.c_str(),resp.size());close(fd);
}

static void rpc_server_thread(int port) {
    int srv=socket(AF_INET,SOCK_STREAM,0); if(srv<0){perror("rpc socket");return;}
    int opt=1; setsockopt(srv,SOL_SOCKET,SO_REUSEADDR,&opt,sizeof(opt));
    struct sockaddr_in addr{}; addr.sin_family=AF_INET; addr.sin_addr.s_addr=INADDR_ANY; addr.sin_port=htons(port);
    if(bind(srv,(struct sockaddr*)&addr,sizeof(addr))<0){perror("rpc bind");close(srv);return;}
    listen(srv,128);
    printf("[RPC] Listening on port %d — 17 methods\n",port);
    while(g_running){
        int cl=accept(srv,nullptr,nullptr);
        if(cl<0) continue;
        std::thread([cl](){rpc_handle_connection(cl);}).detach();
    }
    close(srv);
}

// =============================================================================
// P2P Server Thread
// =============================================================================

static void p2p_server_thread(int port) {
    int srv=socket(AF_INET,SOCK_STREAM,0); if(srv<0){perror("p2p socket");return;}
    int opt=1; setsockopt(srv,SOL_SOCKET,SO_REUSEADDR,&opt,sizeof(opt));
    struct sockaddr_in addr{}; addr.sin_family=AF_INET; addr.sin_addr.s_addr=INADDR_ANY; addr.sin_port=htons(port);
    if(bind(srv,(struct sockaddr*)&addr,sizeof(addr))<0){perror("p2p bind");close(srv);return;}
    listen(srv,128);
    printf("[P2P] Listening on port %d\n",port);
    while(g_running){
        struct sockaddr_in cl_addr{};
        socklen_t cl_len=sizeof(cl_addr);
        int cl=accept(srv,(struct sockaddr*)&cl_addr,&cl_len);
        if(cl<0) continue;
        char ip[64]; inet_ntop(AF_INET,&cl_addr.sin_addr,ip,sizeof(ip));
        std::string peer_addr=std::string(ip)+":"+std::to_string(ntohs(cl_addr.sin_port));
        std::thread([cl,peer_addr](){handle_peer(cl,peer_addr,false);}).detach();
    }
    close(srv);
}

static void connect_peer(const std::string& host, int port) {
    struct addrinfo hints{}, *res;
    hints.ai_family=AF_INET; hints.ai_socktype=SOCK_STREAM;
    std::string port_str=std::to_string(port);
    if(getaddrinfo(host.c_str(),port_str.c_str(),&hints,&res)!=0){
        printf("[P2P] Cannot resolve %s\n",host.c_str()); return;
    }
    int fd=socket(res->ai_family,res->ai_socktype,res->ai_protocol);
    if(fd<0){freeaddrinfo(res);return;}
    if(connect(fd,res->ai_addr,res->ai_addrlen)<0){
        printf("[P2P] Cannot connect to %s:%d\n",host.c_str(),port);
        close(fd); freeaddrinfo(res); return;
    }
    freeaddrinfo(res);
    std::string addr=host+":"+std::to_string(port);
    std::thread([fd,addr](){handle_peer(fd,addr,true);}).detach();
}

// =============================================================================
// Save chain
// =============================================================================

static bool save_chain(const std::string& path) {
    std::lock_guard<std::mutex> lk(g_chain_mu);
    std::ofstream f(path); if (!f) return false;
    f << "{\n  \"chain_height\": " << g_chain_height
      << ",\n  \"tip\": \"" << to_hex(g_blocks.back().block_id.data(),32)
      << "\",\n  \"blocks\": [\n";
    for (size_t i = 0; i < g_blocks.size(); ++i) {
        const auto& b = g_blocks[i];
        f << "    {\"block_id\":\"" << to_hex(b.block_id.data(),32)
          << "\",\"prev_hash\":\"" << to_hex(b.prev_hash.data(),32)
          << "\",\"merkle_root\":\"" << to_hex(b.merkle_root.data(),32)
          << "\",\"height\":" << b.height << ",\"timestamp\":" << b.timestamp
          << ",\"bits_q\":" << b.bits_q << ",\"nonce\":" << b.nonce
          << ",\"subsidy\":" << b.subsidy
          << ",\"miner\":" << b.miner_reward << ",\"gold_vault\":" << b.gold_vault_reward
          << ",\"popc_pool\":" << b.popc_pool_reward
          << ",\"stability_metric\":0}"
          << (i + 1 < g_blocks.size() ? ",\n" : "\n");
    }
    f << "  ]\n}\n";
    return f.good();
}

// =============================================================================
// main
// =============================================================================

int main(int argc, char** argv) {
    int rpc_port=RPC_PORT_DEFAULT;
    int p2p_port=P2P_PORT_DEFAULT;
    std::string genesis_path="genesis_block.json";
    std::string chain_path="";
    std::vector<std::string> connect_addrs;

    for(int i=1;i<argc;++i){
        if(!strcmp(argv[i],"--wallet")&&i+1<argc) g_wallet_path=argv[++i];
        else if(!strcmp(argv[i],"--rpc-port")&&i+1<argc) rpc_port=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--port")&&i+1<argc) p2p_port=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--genesis")&&i+1<argc) genesis_path=argv[++i];
        else if(!strcmp(argv[i],"--chain")&&i+1<argc) chain_path=argv[++i];
        else if(!strcmp(argv[i],"--connect")&&i+1<argc) connect_addrs.push_back(argv[++i]);
        else if(!strcmp(argv[i],"--help")||!strcmp(argv[i],"-h")){
            printf("SOST Node v0.2\n");
            printf("  --wallet <path>      Wallet file (default: wallet.json)\n");
            printf("  --genesis <path>     Genesis JSON\n");
            printf("  --chain <path>       Chain JSON to load\n");
            printf("  --port <n>           P2P port (default: 19333)\n");
            printf("  --rpc-port <n>       RPC port (default: 18232)\n");
            printf("  --connect <host:port> Connect to peer\n");
            return 0;
        }
    }

    printf("=== SOST Node v0.2 ===\n");
    printf("P2P: %d | RPC: %d\n\n",p2p_port,rpc_port);

    if(!load_genesis(genesis_path)){fprintf(stderr,"Error: cannot load genesis\n");return 1;}
    printf("Genesis: %s\n",to_hex(g_genesis_hash.data(),32).c_str());

    if(!chain_path.empty()){
        if(load_chain(chain_path)){
            printf("Chain: %zu blocks, height=%lld, UTXOs=%zu\n",
                   g_blocks.size(),(long long)g_chain_height,g_utxo_set.Size());
        } else {
            printf("Warning: failed to load chain from %s\n",chain_path.c_str());
        }
    }

    std::string err;
    if(!g_wallet.load(g_wallet_path,&err)){
        printf("Warning: %s (run sost-cli newwallet)\n",err.c_str());
    } else {
        printf("Wallet: %zu keys\n",g_wallet.num_keys());
    }
    // === Wallet UTXO rescan ===
    {
        int rescan_count = 0;
        const auto& umap = g_utxo_set.GetMap();
        for (const auto& [op, entry] : umap) {
            std::string addr = address_encode(entry.pubkey_hash);
            if (g_wallet.has_address(addr)) {
                WalletUTXO wu;
                wu.txid = op.txid;
                wu.vout = op.index;
                wu.amount = entry.amount;
                wu.output_type = entry.type;
                wu.pkh = entry.pubkey_hash;
                wu.height = entry.height;
                wu.spent = false;
                g_wallet.add_utxo(wu);
                rescan_count++;
            }
        }
        printf("Wallet rescan: %d UTXOs registered (balance: %s SOST)\n",
               rescan_count, format_sost(g_wallet.balance()).c_str());
        // Persistir UTXOs al disco para que sost-cli los vea
        std::string werr;
        if (!g_wallet.save(g_wallet_path, &werr))
            printf("Warning: wallet save failed: %s\n", werr.c_str());
    }

    printf("UTXO set: %zu entries | Mempool: %zu txs\n\n",g_utxo_set.Size(),g_mempool.Size());

    std::thread rpc_thread(rpc_server_thread, rpc_port);
    rpc_thread.detach();

    std::thread p2p_thread(p2p_server_thread, p2p_port);
    p2p_thread.detach();

    for(const auto& a:connect_addrs){
        auto colon=a.rfind(':');
        if(colon!=std::string::npos){
            std::string host=a.substr(0,colon);
            int port=atoi(a.substr(colon+1).c_str());
            connect_peer(host, port);
        } else {
            connect_peer(a, P2P_PORT_DEFAULT);
        }
    }

    printf("Node running. Ctrl+C to stop.\n\n");
    while(g_running){
        std::this_thread::sleep_for(std::chrono::seconds(30));
        {
            std::lock_guard<std::mutex> lk(g_peers_mu);
            for(auto& p:g_peers){
                if(p.version_acked) p2p_send(p.fd,"PING",nullptr,0);
            }
        }
        if(!chain_path.empty()) save_chain(chain_path);
    }

    return 0;
}
