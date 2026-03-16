// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// sost-node.cpp — SOST Full Node v0.3.2
//
// Full node: P2P + JSON-RPC + chain sync + tx relay
//
// CHANGES v0.3.2 (critical fix):
// - FIX: Transaction persistence — chain.json now stores ALL txs per block
//        load_chain() replays full UTXO connect on restart
// - FIX: Auto-save chain.json after every accepted block (no data loss on crash)
// - FIX: p2p_send_block includes transactions for full peer sync
//
// CHANGES v0.3.1 (bug-fix release):
// - FIX #1: ACTIVE_PROFILE now set to MAINNET at startup (was DEV default)
//           + added --profile mainnet|testnet|dev CLI flag
// - FIX #2: Chain load validates tip continuity with genesis
// - FIX #3: Defensive height check on block acceptance
//
// v0.3 features preserved:
// - REAL PoW verification for ConvergenceX blocks
// - RPC Basic Auth (fail-closed by default)
// - getblocktemplate enforces 500KB max block tx bytes (excluding coinbase)
// - relay/mempool min fee handled by tx_validation policy

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
#include "sost/subsidy.h"
#include "sost/merkle.h"
#include "sost/serialize.h"
#include "sost/pow/convergencex.h"
#include "sost/block_validation.h"
#include "sost/sostcompact.h"
#include "sost/checkpoints.h"

#include <fstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
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

// P2P encryption (X25519 + ChaCha20-Poly1305)
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/kdf.h>

using namespace sost;

// =============================================================================
// Globals
// =============================================================================

static Wallet       g_wallet;
static UtxoSet      g_utxo_set;
static Mempool      g_mempool;
static std::string  g_wallet_path = "wallet.json";
static std::string  g_chain_path  = "";            // v0.3.2: for auto-save after block acceptance
static Hash256      g_genesis_hash{};
static int64_t      g_chain_height = 0;
static std::mutex   g_chain_mu;

// RPC auth (fail-closed by default)
static std::string g_rpc_user = "";
static std::string g_rpc_pass = "";
static bool        g_rpc_auth_required = true;
static bool        g_rpc_public = false; // default: bind to 127.0.0.1 only

// Block record
struct StoredBlock {
    Hash256 block_id, prev_hash, merkle_root;
    Hash256 commit, checkpoints_root;
    int64_t timestamp;
    uint32_t bits_q;
    uint32_t nonce;
    uint32_t extra_nonce;
    int64_t height;
    int64_t subsidy;
    int64_t miner_reward, gold_vault_reward, popc_pool_reward;
    uint64_t stability_metric;
    std::string x_bytes_hex;     // CX solution vector (hex)
    std::string final_state_hex; // Final hash state (hex)
    std::vector<std::string> tx_hexes;  // ALL serialized txs (coinbase + transfers)
};
static std::vector<StoredBlock> g_blocks;

// P2P state
static const uint32_t P2P_MAGIC = 0x534F5354; // "SOST"
static const int P2P_PORT_DEFAULT = 19333;
static const int RPC_PORT_DEFAULT = 18232;
static std::atomic<bool> g_running{true};

// P2P encryption mode
enum class P2PEncMode { OFF, ON, REQUIRED };
static P2PEncMode g_p2p_enc = P2PEncMode::ON;

// P2PMsg defined early for use by encryption functions
struct P2PMsg {
    char cmd[5];
    std::vector<uint8_t> payload;
};

// Per-peer encryption state
struct PeerCrypto {
    bool encrypted{false};
    uint8_t send_key[32]{};
    uint8_t recv_key[32]{};
    uint64_t send_nonce{0};
    uint64_t recv_nonce{0};
};

static bool chacha20_poly1305_encrypt(const uint8_t key[32], uint64_t nonce_counter,
    const uint8_t* plaintext, size_t plen, uint8_t* out, uint8_t tag[16]) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if(!ctx) return false;
    uint8_t nonce[12]{};
    memcpy(nonce+4, &nonce_counter, 8); // little-endian nonce
    int ok=1;
    ok &= EVP_EncryptInit_ex(ctx, EVP_chacha20_poly1305(), nullptr, key, nonce);
    int outl=0;
    ok &= EVP_EncryptUpdate(ctx, out, &outl, plaintext, (int)plen);
    int finl=0;
    ok &= EVP_EncryptFinal_ex(ctx, out+outl, &finl);
    ok &= EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_GET_TAG, 16, tag);
    EVP_CIPHER_CTX_free(ctx);
    return ok==1;
}

static bool chacha20_poly1305_decrypt(const uint8_t key[32], uint64_t nonce_counter,
    const uint8_t* ciphertext, size_t clen, const uint8_t tag[16], uint8_t* out) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if(!ctx) return false;
    uint8_t nonce[12]{};
    memcpy(nonce+4, &nonce_counter, 8);
    int ok=1;
    ok &= EVP_DecryptInit_ex(ctx, EVP_chacha20_poly1305(), nullptr, key, nonce);
    ok &= EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_TAG, 16, (void*)tag);
    int outl=0;
    ok &= EVP_DecryptUpdate(ctx, out, &outl, ciphertext, (int)clen);
    int finl=0;
    ok &= EVP_DecryptFinal_ex(ctx, out+outl, &finl);
    EVP_CIPHER_CTX_free(ctx);
    return ok==1;
}

// X25519 key exchange
static bool x25519_keygen(uint8_t privkey[32], uint8_t pubkey[32]) {
    EVP_PKEY* pkey = nullptr;
    EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new_id(EVP_PKEY_X25519, nullptr);
    if(!ctx) return false;
    bool ok = EVP_PKEY_keygen_init(ctx)==1 && EVP_PKEY_keygen(ctx, &pkey)==1;
    if(ok){
        size_t len=32;
        ok &= EVP_PKEY_get_raw_private_key(pkey, privkey, &len)==1;
        len=32;
        ok &= EVP_PKEY_get_raw_public_key(pkey, pubkey, &len)==1;
    }
    EVP_PKEY_free(pkey);
    EVP_PKEY_CTX_free(ctx);
    return ok;
}

static bool x25519_derive(const uint8_t our_priv[32], const uint8_t their_pub[32], uint8_t shared[32]) {
    EVP_PKEY* our_key = EVP_PKEY_new_raw_private_key(EVP_PKEY_X25519, nullptr, our_priv, 32);
    EVP_PKEY* their_key = EVP_PKEY_new_raw_public_key(EVP_PKEY_X25519, nullptr, their_pub, 32);
    if(!our_key || !their_key){ EVP_PKEY_free(our_key); EVP_PKEY_free(their_key); return false; }
    EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new(our_key, nullptr);
    bool ok = ctx && EVP_PKEY_derive_init(ctx)==1 && EVP_PKEY_derive_set_peer(ctx, their_key)==1;
    if(ok){
        size_t len=32;
        ok = EVP_PKEY_derive(ctx, shared, &len)==1 && len==32;
    }
    EVP_PKEY_CTX_free(ctx);
    EVP_PKEY_free(our_key);
    EVP_PKEY_free(their_key);
    return ok;
}

// Derive send/recv keys from shared secret using HKDF-SHA256
static void derive_session_keys(const uint8_t shared[32], bool is_initiator,
    uint8_t send_key[32], uint8_t recv_key[32]) {
    // Simple key derivation: SHA256(shared || "sost-p2p-send" || role_byte)
    // and SHA256(shared || "sost-p2p-recv" || role_byte)
    uint8_t buf[64];
    memcpy(buf, shared, 32);
    // Initiator sends with key A, receives with key B
    // Responder sends with key B, receives with key A
    const char* label_a = "sost-p2p-key-a";
    const char* label_b = "sost-p2p-key-b";
    unsigned int md_len=32;
    EVP_MD_CTX* mdctx = EVP_MD_CTX_new();
    // Key A
    EVP_DigestInit_ex(mdctx, EVP_sha256(), nullptr);
    EVP_DigestUpdate(mdctx, shared, 32);
    EVP_DigestUpdate(mdctx, label_a, strlen(label_a));
    uint8_t key_a[32]; EVP_DigestFinal_ex(mdctx, key_a, &md_len);
    // Key B
    EVP_DigestInit_ex(mdctx, EVP_sha256(), nullptr);
    EVP_DigestUpdate(mdctx, shared, 32);
    EVP_DigestUpdate(mdctx, label_b, strlen(label_b));
    uint8_t key_b[32]; EVP_DigestFinal_ex(mdctx, key_b, &md_len);
    EVP_MD_CTX_free(mdctx);

    if(is_initiator){
        memcpy(send_key, key_a, 32);
        memcpy(recv_key, key_b, 32);
    } else {
        memcpy(send_key, key_b, 32);
        memcpy(recv_key, key_a, 32);
    }
}

// p2p_send_encrypted and p2p_recv_encrypted defined after P2P protocol section

// Forward declaration — defined in P2P section, used by RPC handlers too
static bool write_exact(int fd, const void* buf, size_t len);

struct Peer {
    int fd;
    std::string addr;
    int64_t their_height;
    bool version_sent;
    bool version_acked;
    bool outbound;
    time_t last_seen;
    int ban_score;         // misbehavior score, ban at >= 100
};
static std::vector<Peer> g_peers;
static std::mutex g_peers_mu;

// Checkpoints: known block_id at specific heights (hex → height)
// Prevents deep reorgs past a checkpoint and validates chain integrity.
struct ChainCheckpoint {
    int64_t height;
    const char* block_hash;  // hex
};
static const ChainCheckpoint g_checkpoints[] = {
    // Genesis is validated separately via load_genesis()
    // Add mainnet checkpoints here after launch:
    // { 1000, "abcdef..." },
    // { 5000, "123456..." },
};
static const size_t g_num_checkpoints = sizeof(g_checkpoints) / sizeof(g_checkpoints[0]);

// Maximum reorganization depth. Any alternative chain diverging more than
// 500 blocks (~3.5 days) from the current tip is rejected. Combined with
// ConvergenceX memory-hard requirements, cASERT progressive hardening,
// and 1000-block coinbase maturity, this provides robust protection
// against deep reorganization attacks.
static const int64_t MAX_REORG_DEPTH = 500;

// Fast sync: skip expensive ConvergenceX recomputation for trusted historical blocks.
// Structural, semantic, and economic validation (header, timestamp, cASERT bitsQ, commit<=target,
// coinbase, UTXO) ALWAYS runs. Only the expensive CX recompute is conditionally skipped.
// Trust requires exact hard checkpoint match OR assumevalid anchor on active chain.
// --full-verify forces full CX recomputation for all blocks.
static bool g_full_verify_mode = false;

// DoS/ban tracking
static const int BAN_THRESHOLD = 100;
static const int BAN_DURATION  = 86400;  // 24 hours
static const size_t MAX_P2P_MSG_SIZE = 4 * 1024 * 1024;  // 4MB max message
static const int MAX_INBOUND_PEERS = 64;
static const int MAX_PEERS_PER_IP  = 4;
static std::map<std::string, time_t> g_banned;  // IP → ban expiry
static std::mutex g_ban_mu;

// TX-INDEX: txid → {block_height, tx_position_in_block}
struct TxIndexEntry {
    int64_t block_height;
    uint32_t tx_pos;
};
static std::map<Hash256, TxIndexEntry> g_tx_index;

static std::string peer_ip(const std::string& addr) {
    auto colon = addr.rfind(':');
    return (colon != std::string::npos) ? addr.substr(0, colon) : addr;
}

static bool is_banned(const std::string& ip) {
    std::lock_guard<std::mutex> lk(g_ban_mu);
    auto it = g_banned.find(ip);
    if (it == g_banned.end()) return false;
    if (time(nullptr) >= it->second) {
        g_banned.erase(it);
        return false;
    }
    return true;
}

static void ban_peer(int fd, const std::string& addr, const char* reason) {
    std::string ip = peer_ip(addr);
    {
        std::lock_guard<std::mutex> lk(g_ban_mu);
        g_banned[ip] = time(nullptr) + BAN_DURATION;
    }
    printf("[P2P] BANNED %s: %s (24h)\n", addr.c_str(), reason);
    close(fd);
}

// Add misbehavior score to a peer; returns true if peer was banned
static bool add_misbehavior(int fd, const std::string& addr, int points, const char* reason) {
    int new_score = 0;
    {
        std::lock_guard<std::mutex> lk(g_peers_mu);
        for (auto& p : g_peers) {
            if (p.fd == fd) {
                p.ban_score += points;
                new_score = p.ban_score;
                break;
            }
        }
    }
    if (new_score >= BAN_THRESHOLD) {
        ban_peer(fd, addr, reason);
        return true;
    }
    printf("[P2P] Misbehavior +%d (%s) from %s [score=%d/%d]\n",
           points, reason, addr.c_str(), new_score, BAN_THRESHOLD);
    return false;
}

// =============================================================================
// Helpers
// =============================================================================

static std::string to_hex(const uint8_t* d, size_t len) {
    static const char* hx = "0123456789abcdef";
    std::string s; s.reserve(len*2);
    for(size_t i=0;i<len;++i){ s+=hx[d[i]>>4]; s+=hx[d[i]&0xF]; }
    return s;
}

static bool hex_to_bytes(const std::string& h, uint8_t* out, size_t len) {
    if(h.size()!=len*2) return false;
    auto hv=[](char c)->int{
        if(c>='0'&&c<='9')return c-'0';
        if(c>='a'&&c<='f')return 10+c-'a';
        if(c>='A'&&c<='F')return 10+c-'A';
        return -1;
    };
    for(size_t i=0;i<len;++i){
        int hi=hv(h[i*2]),lo=hv(h[i*2+1]);
        if(hi<0||lo<0) return false;
        out[i]=(uint8_t)((hi<<4)|lo);
    }
    return true;
}

static std::string format_sost(int64_t stocks) {
    char buf[64];
    bool neg=stocks<0;
    int64_t a=neg?-stocks:stocks;
    snprintf(buf,sizeof(buf),"%s%lld.%08lld",neg?"-":"",
            (long long)(a/sost::STOCKS_PER_SOST),
            (long long)(a%sost::STOCKS_PER_SOST));
    return buf;
}

static std::string json_escape(const std::string& s) {
    std::string o;
    for(char c:s){
        if(c=='"') o+="\\\"";
        else if(c=='\\') o+="\\\\";
        else if(c=='\n') o+="\\n";
        else o+=c;
    }
    return o;
}

// =============================================================================
// JSON parser (very small, sufficient for this node)
// =============================================================================

static std::string json_get_string(const std::string& json, const std::string& key) {
    std::string needle="\""+key+"\"";
    auto pos=json.find(needle);
    if(pos==std::string::npos) return "";
    pos=json.find(':',pos+needle.size());
    if(pos==std::string::npos) return "";
    pos++;
    while(pos<json.size()&&(json[pos]==' '||json[pos]=='\t')) pos++;
    if(pos>=json.size()) return "";
    if(json[pos]=='"'){
        auto end=json.find('"',pos+1);
        if(end==std::string::npos) return "";
        return json.substr(pos+1,end-pos-1);
    }
    auto end=json.find_first_of(",}] \t\n\r",pos);
    if(end==std::string::npos) end=json.size();
    return json.substr(pos,end-pos);
}

static std::vector<std::string> json_get_params(const std::string& json) {
    std::vector<std::string> r;
    auto pos=json.find("\"params\"");
    if(pos==std::string::npos) return r;
    pos=json.find('[',pos);
    if(pos==std::string::npos) return r;

    size_t depth=1; size_t end=pos+1; bool in_str=false;
    while(end<json.size()&&depth>0){
        char c=json[end];
        if(in_str){
            if(c=='"'&&json[end-1]!='\\') in_str=false;
        } else {
            if(c=='"') in_str=true;
            else if(c=='['||c=='{') depth++;
            else if(c==']'||c=='}') depth--;
        }
        if(depth>0) end++;
    }
    if(depth!=0) return r;

    std::string inner=json.substr(pos+1,end-pos-1);
    size_t i=0;
    while(i<inner.size()){
        while(i<inner.size()&&(inner[i]==' '||inner[i]==','||inner[i]=='\t'||inner[i]=='\n')) i++;
        if(i>=inner.size()) break;

        if(inner[i]=='"'){
            size_t q=i+1;
            while(q<inner.size()){
                if(inner[q]=='"'&&(q==0||inner[q-1]!='\\')) break;
                q++;
            }
            if(q>=inner.size()) break;
            std::string val=inner.substr(i+1,q-i-1);
            std::string unesc;
            for(size_t k=0;k<val.size();k++){
                if(val[k]=='\\'&&k+1<val.size()&&val[k+1]=='"'){ unesc+='"'; k++; }
                else unesc+=val[k];
            }
            r.push_back(unesc);
            i=q+1;
        } else {
            auto p=inner.find_first_of(",] \t\n\r",i);
            if(p==std::string::npos) p=inner.size();
            r.push_back(inner.substr(i,p-i));
            i=p;
        }
    }
    return r;
}

static int64_t jint(const std::string& j,const std::string& k){
    std::string n="\""+k+"\"";
    auto p=j.find(n); if(p==std::string::npos) return -1;
    p=j.find(':',p+n.size()); if(p==std::string::npos) return -1;
    p++;
    while(p<j.size()&&(j[p]==' '||j[p]=='\t')) p++;
    try { return std::stoll(j.substr(p)); }
    catch(...) { printf("[JSON] stoll failed for key '%s' val='%.40s'\n", k.c_str(), j.substr(p,40).c_str()); fflush(stdout); return -1; }
}
// For uint64 fields that may exceed INT64_MAX (dataset_value, program_output, residuals)
static uint64_t juint(const std::string& j,const std::string& k){
    std::string n="\""+k+"\"";
    auto p=j.find(n); if(p==std::string::npos) return 0;
    p=j.find(':',p+n.size()); if(p==std::string::npos) return 0;
    p++;
    while(p<j.size()&&(j[p]==' '||j[p]=='\t')) p++;
    try { return std::stoull(j.substr(p)); }
    catch(...) { printf("[JSON] stoull failed for key '%s' val='%.40s'\n", k.c_str(), j.substr(p,40).c_str()); fflush(stdout); return 0; }
}

static std::string jstr(const std::string& j,const std::string& k){
    std::string n="\""+k+"\"";
    auto p=j.find(n); if(p==std::string::npos) return "";
    p=j.find('"',p+n.size()+1); if(p==std::string::npos) return "";
    auto e=j.find('"',p+1); if(e==std::string::npos) return "";
    return j.substr(p+1,e-p-1);
}

// Parse "transactions":[ "hex", "hex", ... ] from block JSON
static std::vector<std::string> json_get_tx_hexes(const std::string& block_json) {
    std::vector<std::string> out;
    auto tx_pos = block_json.find("\"transactions\"");
    if(tx_pos==std::string::npos) return out;

    auto arr_start = block_json.find('[', tx_pos);
    auto arr_end = block_json.find(']', arr_start);
    if(arr_start==std::string::npos || arr_end==std::string::npos) return out;

    std::string arr = block_json.substr(arr_start+1, arr_end-arr_start-1);
    size_t p=0;
    while(p<arr.size()){
        auto q1=arr.find('"',p); if(q1==std::string::npos) break;
        auto q2=arr.find('"',q1+1); if(q2==std::string::npos) break;
        std::string tx_hex=arr.substr(q1+1,q2-q1-1);
        p=q2+1;
        if(!tx_hex.empty()) out.push_back(tx_hex);
    }
    return out;
}

// Forward declarations
static void p2p_broadcast_tx(const std::string& hex_str);
static bool process_block(const std::string& block_json);
static bool save_chain_internal(const std::string& path);  // v0.3.2: no-lock save
static bool decode_tx_hex(const std::string& tx_hex, std::vector<Byte>& out_raw);

// =============================================================================
// RPC Basic Auth (Base64 decode)
// =============================================================================
static inline bool is_b64(unsigned char c) { return (isalnum(c) || c=='+' || c=='/'); }

static std::string base64_decode(const std::string& encoded) {
    static const std::string b64="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    int in_len=(int)encoded.size();
    int i=0,j=0,in_=0;
    unsigned char a4[4],a3[3];
    std::string ret; ret.reserve((encoded.size()*3)/4);

    while(in_len-- && encoded[in_]!='=' && is_b64((unsigned char)encoded[in_])) {
        a4[i++]=(unsigned char)encoded[in_]; in_++;
        if(i==4){
            for(i=0;i<4;i++) a4[i]=(unsigned char)b64.find(a4[i]);
            a3[0]=(unsigned char)((a4[0]<<2)+((a4[1]&0x30)>>4));
            a3[1]=(unsigned char)(((a4[1]&0x0F)<<4)+((a4[2]&0x3C)>>2));
            a3[2]=(unsigned char)(((a4[2]&0x03)<<6)+a4[3]);
            for(i=0;i<3;i++) ret.push_back((char)a3[i]);
            i=0;
        }
    }
    if(i){
        for(j=i;j<4;j++) a4[j]=0;
        for(j=0;j<4;j++) a4[j]=(unsigned char)b64.find(a4[j]);
        a3[0]=(unsigned char)((a4[0]<<2)+((a4[1]&0x30)>>4));
        a3[1]=(unsigned char)(((a4[1]&0x0F)<<4)+((a4[2]&0x3C)>>2));
        a3[2]=(unsigned char)(((a4[2]&0x03)<<6)+a4[3]);
        for(j=0;j<i-1;j++) ret.push_back((char)a3[j]);
    }
    return ret;
}

static std::string trim(const std::string& s) {
    size_t a=0; while(a<s.size()&&(s[a]==' '||s[a]=='\t'||s[a]=='\r'||s[a]=='\n')) a++;
    size_t b=s.size(); while(b>a&&(s[b-1]==' '||s[b-1]=='\t'||s[b-1]=='\r'||s[b-1]=='\n')) b--;
    return s.substr(a,b-a);
}

static bool rpc_check_basic_auth(const std::string& req) {
    if(!g_rpc_auth_required) return true;
    if(g_rpc_user.empty() || g_rpc_pass.empty()) return false;

    auto p=req.find("Authorization:");
    if(p==std::string::npos) return false;
    auto e=req.find("\r\n",p);
    if(e==std::string::npos) e=req.find('\n',p);
    if(e==std::string::npos) return false;

    std::string line=req.substr(p,e-p);
    auto b=line.find("Basic ");
    if(b==std::string::npos) return false;
    std::string b64=trim(line.substr(b+6));
    std::string decoded=base64_decode(b64);
    return decoded==(g_rpc_user+":"+g_rpc_pass);
}

static void rpc_reply_401(int fd) {
    const char* body = "{\"jsonrpc\":\"2.0\",\"id\":null,\"error\":{\"code\":-401,\"message\":\"Authentication required\"}}";
    int blen = (int)strlen(body);
    std::string resp =
        "HTTP/1.1 401 Unauthorized\r\n"
        "WWW-Authenticate: Basic realm=\"sost\"\r\n"
        "Content-Type: application/json\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Access-Control-Allow-Methods: POST,GET,OPTIONS\r\n"
        "Access-Control-Allow-Headers: Content-Type,Authorization\r\n"
        "Content-Length: " + std::to_string(blen) + "\r\n"
        "Connection: close\r\n\r\n" + body;
    write_exact(fd, resp.c_str(), resp.size());
}

// =============================================================================
// ConvergenceX header builder (mirror of miner)
// =============================================================================
static void build_hc72(uint8_t out[72],
                       const Bytes32& prev, const Bytes32& mrkl,
                       uint32_t ts, uint32_t bits) {
    std::memcpy(out, prev.data(), 32);
    std::memcpy(out + 32, mrkl.data(), 32);
    write_u32_le(out + 64, ts);
    write_u32_le(out + 68, bits);
}

static std::vector<uint8_t> build_full_header_bytes(
    const uint8_t hc72[72],
    const Bytes32& checkpoints_root,
    uint32_t nonce_u32,
    uint32_t extra_u32)
{
    std::vector<uint8_t> buf;
    buf.reserve(10 + 4 + 72 + 32 + 4 + 4);
    append_magic(buf);
    append(buf, "HDR2", 4);
    append(buf, hc72, 72);
    append(buf, checkpoints_root);
    append_u32_le(buf, nonce_u32);
    append_u32_le(buf, extra_u32);
    return buf;
}

// =============================================================================
// RPC (condensed)
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
             <<",\"nonce\":"<<b.nonce<<",\"extra_nonce\":"<<b.extra_nonce
             <<",\"subsidy\":"<<b.subsidy
             <<",\"commit\":\""<<to_hex(b.commit.data(),32)<<"\""
             <<",\"checkpoints_root\":\""<<to_hex(b.checkpoints_root.data(),32)<<"\""
             <<",\"stability_metric\":"<<b.stability_metric
             <<",\"miner_reward\":"<<b.miner_reward
             <<",\"gold_vault_reward\":"<<b.gold_vault_reward
             <<",\"popc_pool_reward\":"<<b.popc_pool_reward
             <<",\"tx_count\":"<<b.tx_hexes.size();
            // Extract miner address from coinbase tx, or from UTXO set for genesis
            if(!b.tx_hexes.empty()){
                std::vector<Byte> cbraw; std::string cberr;
                if(decode_tx_hex(b.tx_hexes[0],cbraw)){
                    Transaction cbtx;
                    if(Transaction::Deserialize(cbraw,cbtx,&cberr)&&!cbtx.outputs.empty()){
                        s<<",\"miner_address\":\""<<address_encode(cbtx.outputs[0].pubkey_hash)<<"\"";
                    }
                }
                // Include txids
                s<<",\"txids\":[";
                for(size_t ti=0;ti<b.tx_hexes.size();++ti){
                    std::vector<Byte> traw; std::string terr;
                    if(decode_tx_hex(b.tx_hexes[ti],traw)){
                        Transaction ttx;
                        if(Transaction::Deserialize(traw,ttx,&terr)){
                            Hash256 tid; if(ttx.ComputeTxId(tid,&terr)){
                                if(ti>0)s<<",";
                                s<<"\""<<to_hex(tid.data(),32)<<"\"";
                            }
                        }
                    }
                }
                s<<"]";
            } else {
                // Genesis block has no tx_hexes — look up miner from UTXO set
                OutPoint op; op.txid=b.block_id; op.index=0;
                auto entry=g_utxo_set.GetUTXO(op);
                if(entry){
                    s<<",\"miner_address\":\""<<address_encode(entry->pubkey_hash)<<"\"";
                }
                s<<",\"txids\":[\""<<to_hex(b.block_id.data(),32)<<"\"]";
            }
            std::vector<BlockMeta> meta;
            for(size_t j=0;j<=size_t(b.height)&&j<g_blocks.size();++j){
                BlockMeta bm; bm.block_id=g_blocks[j].block_id;
                bm.height=g_blocks[j].height; bm.time=g_blocks[j].timestamp;
                bm.powDiffQ=g_blocks[j].bits_q; meta.push_back(bm);
            }
            auto cd=casert_compute(meta,b.height+1);
            s<<",\"casert_mode\":\""<<casert_profile_name(cd.profile_index)
             <<"\",\"casert_signal\":"<<cd.lag<<"}";
            return rpc_result(id,s.str());
        }
    }
    return rpc_error(id,-5,"Block not found");
}

static std::string handle_getinfo(const std::string& id, const std::vector<std::string>&) {
    size_t peers_count;
    { std::lock_guard<std::mutex> lk(g_peers_mu); peers_count=g_peers.size(); }

    // Show which profile is active so operator can verify at a glance
    const char* profile_str = "unknown";
    if(ACTIVE_PROFILE == Profile::MAINNET) profile_str = "mainnet";
    else if(ACTIVE_PROFILE == Profile::TESTNET) profile_str = "testnet";
    else if(ACTIVE_PROFILE == Profile::DEV) profile_str = "dev";

    std::ostringstream s;
    s<<"{\"version\":\"0.3.2\",\"protocolversion\":1,\"blocks\":"<<g_chain_height
     <<",\"connections\":"<<peers_count
     <<",\"difficulty\":"<<(g_blocks.empty()?0:g_blocks.back().bits_q)
     <<",\"profile\":\""<<profile_str<<"\""
     <<",\"testnet\":"<<(ACTIVE_PROFILE==Profile::TESTNET?"true":"false")
     <<",\"balance\":\""<<format_sost(g_wallet.balance(g_chain_height))
     <<"\",\"keypoolsize\":"<<g_wallet.num_keys()
     <<",\"mempool_size\":"<<g_mempool.Size()
     <<",\"utxo_count\":"<<g_utxo_set.Size()<<"}";
    return rpc_result(id,s.str());
}

static std::string handle_getbalance(const std::string& id, const std::vector<std::string>&) {
    int64_t total=g_wallet.balance(g_chain_height);
    int64_t locked=g_wallet.locked_balance(g_chain_height);
    int64_t avail=total-locked;
    std::ostringstream s;
    s<<"{\"total\":"<<format_sost(total)
     <<",\"available\":"<<format_sost(avail)
     <<",\"locked\":"<<format_sost(locked)<<"}";
    return rpc_result(id,s.str());
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
    auto utxos=g_wallet.list_unspent(g_chain_height); std::ostringstream s; s<<"[";
    for(size_t i=0;i<utxos.size();++i){
        if(i)s<<","; const auto& u=utxos[i];
        bool isLocked=(u.output_type==0x10||u.output_type==0x11)&&(uint64_t)g_chain_height<u.lock_until;
        s<<"{\"txid\":\""<<to_hex(u.txid.data(),32)<<"\",\"vout\":"<<u.vout
         <<",\"address\":\""<<address_encode(u.pkh)<<"\",\"amount\":"<<format_sost(u.amount)
         <<",\"confirmations\":"<<(g_chain_height-u.height+1)<<",\"spendable\":"<<(isLocked?"false":"true");
        if(u.output_type==0x10)s<<",\"type\":\"bond\",\"lock_until\":"<<u.lock_until;
        else if(u.output_type==0x11)s<<",\"type\":\"escrow\",\"lock_until\":"<<u.lock_until;
        s<<"}";
    }
    s<<"]"; return rpc_result(id,s.str());
}

static std::string handle_gettxout(const std::string& id, const std::vector<std::string>& p) {
    if(p.size()<2) return rpc_error(id,-1,"missing txid and vout");
    Hash256 txid{}; if(!hex_to_bytes(p[0],txid.data(),32)) return rpc_error(id,-8,"invalid txid");
    OutPoint op; op.txid=txid; op.index=(uint32_t)std::stoul(p[1]);
    auto entry=g_utxo_set.GetUTXO(op); if(!entry) return rpc_result(id,"null");
    std::ostringstream s;
    s<<"{\"bestblock\":\""<<to_hex(g_blocks.back().block_id.data(),32)
     <<"\",\"confirmations\":"<<(g_chain_height-entry->height+1)
     <<",\"value\":"<<format_sost(entry->amount)<<",\"address\":\""<<address_encode(entry->pubkey_hash)
     <<"\",\"type\":"<<(int)entry->type<<",\"coinbase\":"<<(entry->is_coinbase?"true":"false")<<"}";
    return rpc_result(id,s.str());
}

static std::string handle_sendrawtransaction(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing hex tx");
    std::string hex_str=p[0];
    if(hex_str.size()%2!=0) return rpc_error(id,-22,"odd hex length");

    std::vector<Byte> raw; raw.reserve(hex_str.size()/2);
    for(size_t i=0;i<hex_str.size();i+=2){
        uint8_t b; if(!hex_to_bytes(hex_str.substr(i,2),&b,1)) return rpc_error(id,-22,"invalid hex");
        raw.push_back(b);
    }

    Transaction tx; std::string err;
    if(!Transaction::Deserialize(raw,tx,&err)) return rpc_error(id,-22,"TX decode: "+err);

    Hash256 txid; if(!tx.ComputeTxId(txid,&err)) return rpc_error(id,-25,"TX reject: "+err);

    TxValidationContext ctx; ctx.genesis_hash=g_genesis_hash; ctx.spend_height=g_chain_height+1;

    int64_t now=(int64_t)time(nullptr);
    auto result=g_mempool.AcceptToMempool(tx,g_utxo_set,ctx,now);
    if(!result.accepted){
        return rpc_error(id,-25,result.reason);
    }

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
    auto tmpl=g_mempool.BuildBlockTemplate();
    std::ostringstream s; s<<"[";
    for(size_t i=0;i<tmpl.txids.size();++i){
        if(i)s<<",";
        s<<"\""<<to_hex(tmpl.txids[i].data(),32)<<"\"";
    }
    s<<"]"; return rpc_result(id,s.str());
}

static std::string handle_getrawtransaction(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing txid");
    Hash256 txid{}; if(!hex_to_bytes(p[0],txid.data(),32)) return rpc_error(id,-8,"invalid txid");
    const MempoolEntry* entry=g_mempool.GetEntry(txid);
    if(!entry) return rpc_error(id,-5,"Not in mempool");
    std::vector<Byte> raw; std::string err;
    if(!entry->tx.Serialize(raw,&err)) return rpc_error(id,-1,"serialize: "+err);
    bool verbose=(p.size()>1&&p[1]!="0"&&p[1]!="false");
    if(!verbose) return rpc_result(id,"\""+to_hex(raw.data(),raw.size())+"\"");
    std::ostringstream s;
    s<<"{\"txid\":\""<<to_hex(txid.data(),32)<<"\",\"size\":"<<raw.size()
     <<",\"fee\":"<<entry->fee<<",\"vin\":[";
    for(size_t i=0;i<entry->tx.inputs.size();++i){
        if(i)s<<",";
        const auto& in=entry->tx.inputs[i];
        s<<"{\"txid\":\""<<to_hex(in.prev_txid.data(),32)<<"\",\"vout\":"<<in.prev_index<<"}";
    }
    s<<"],\"vout\":[";
    for(size_t i=0;i<entry->tx.outputs.size();++i){
        if(i)s<<",";
        const auto& o=entry->tx.outputs[i];
        s<<"{\"value\":"<<format_sost(o.amount)<<",\"n\":"<<i<<",\"address\":\""<<address_encode(o.pubkey_hash)<<"\"}";
    }
    s<<"]}";
    return rpc_result(id,s.str());
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

static std::string handle_submitblock(const std::string& id, const std::vector<std::string>& p) {
    printf("[SUBMITBLOCK] Received block submission (params=%zu)\n", p.size()); fflush(stdout);
    if(p.empty()) { printf("[SUBMITBLOCK] REJECTED: missing block JSON\n"); fflush(stdout); return rpc_error(id,-1,"missing block JSON"); }
    if(process_block(p[0])) { printf("[SUBMITBLOCK] ACCEPTED\n"); fflush(stdout); return rpc_result(id,"true"); }
    printf("[SUBMITBLOCK] REJECTED by process_block\n"); fflush(stdout);
    return rpc_error(id,-25,"Block rejected");
}

// 500KB tx bytes in template (coinbase excluded here)
static constexpr size_t NODE_MAX_BLOCK_TX_BYTES = 500 * 1024;

static std::string handle_getblocktemplate(const std::string& id, const std::vector<std::string>&) {
    auto tmpl = g_mempool.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, NODE_MAX_BLOCK_TX_BYTES);
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
      << ",\"max_block_tx_bytes\":" << NODE_MAX_BLOCK_TX_BYTES
      << ",\"mempool_size\":" << g_mempool.Size() << "}";
    return rpc_result(id, s.str());
}

// TX-INDEX: gettransaction — returns full transaction JSON from confirmed blocks
static std::string handle_gettransaction(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing txid");
    Hash256 txid{}; if(!hex_to_bytes(p[0],txid.data(),32)) return rpc_error(id,-8,"invalid txid");

    // Check mempool first
    const MempoolEntry* mentry=g_mempool.GetEntry(txid);
    if(mentry){
        std::ostringstream s;
        s<<"{\"txid\":\""<<to_hex(txid.data(),32)<<"\",\"block_height\":-1,\"confirmations\":0";
        s<<",\"in_mempool\":true";
        s<<",\"vin\":[";
        for(size_t i=0;i<mentry->tx.inputs.size();++i){
            if(i)s<<",";
            const auto&in=mentry->tx.inputs[i];
            std::string in_addr;
            int64_t in_amt=0;
            OutPoint op{in.prev_txid,in.prev_index};
            auto utxo=g_utxo_set.GetUTXO(op);
            if(utxo){in_addr=address_encode(utxo->pubkey_hash);in_amt=utxo->amount;}
            s<<"{\"prev_txid\":\""<<to_hex(in.prev_txid.data(),32)
             <<"\",\"index\":"<<in.prev_index
             <<",\"address\":\""<<in_addr<<"\",\"amount\":"<<format_sost(in_amt)<<"}";
        }
        s<<"],\"vout\":[";
        for(size_t i=0;i<mentry->tx.outputs.size();++i){
            if(i)s<<",";
            const auto&o=mentry->tx.outputs[i];
            s<<"{\"address\":\""<<address_encode(o.pubkey_hash)
             <<"\",\"amount\":"<<format_sost(o.amount)
             <<",\"type\":"<<(int)o.type<<"}";
        }
        s<<"],\"fee\":"<<mentry->fee<<"}";
        return rpc_result(id,s.str());
    }

    // Check tx-index for confirmed transactions
    auto it=g_tx_index.find(txid);
    if(it==g_tx_index.end()) return rpc_error(id,-5,"Transaction not found");

    int64_t bh=it->second.block_height;
    uint32_t tpos=it->second.tx_pos;
    if(bh<0||bh>=(int64_t)g_blocks.size()) return rpc_error(id,-5,"Block not available");
    const auto& blk=g_blocks[bh];
    if(tpos>=blk.tx_hexes.size()) return rpc_error(id,-5,"TX position out of range");

    // Deserialize the transaction
    std::vector<Byte> raw;
    if(!decode_tx_hex(blk.tx_hexes[tpos],raw)) return rpc_error(id,-1,"cannot decode tx hex");
    Transaction tx; std::string derr;
    if(!Transaction::Deserialize(raw,tx,&derr)) return rpc_error(id,-1,"tx deserialize: "+derr);

    // Compute fee for standard txs (not coinbase)
    int64_t fee=0;
    if(tx.tx_type==TX_TYPE_STANDARD){
        // Sum input amounts from tx-index lookup of previous outputs
        int64_t sum_in=0,sum_out=0;
        for(const auto&o:tx.outputs) sum_out+=o.amount;
        // Try to compute from the block's UTXO state... simplify: fee = sum_in - sum_out
        // For confirmed txs, compute from the UTXO entries at the time (we can look up each input's source block)
        for(const auto&in:tx.inputs){
            auto iit=g_tx_index.find(in.prev_txid);
            if(iit!=g_tx_index.end()){
                int64_t ibh=iit->second.block_height;
                uint32_t itpos=iit->second.tx_pos;
                if(ibh<(int64_t)g_blocks.size()&&itpos<g_blocks[ibh].tx_hexes.size()){
                    std::vector<Byte> iraw;
                    if(decode_tx_hex(g_blocks[ibh].tx_hexes[itpos],iraw)){
                        Transaction itx; std::string ie;
                        if(Transaction::Deserialize(iraw,itx,&ie)&&in.prev_index<itx.outputs.size()){
                            sum_in+=itx.outputs[in.prev_index].amount;
                        }
                    }
                }
            }
        }
        fee=sum_in-sum_out;
        if(fee<0) fee=0;
    }

    std::ostringstream s;
    s<<"{\"txid\":\""<<to_hex(txid.data(),32)<<"\",\"block_height\":"<<bh
     <<",\"tx_position\":"<<tpos
     <<",\"confirmations\":"<<(g_chain_height-bh+1)
     <<",\"in_mempool\":false";
    s<<",\"vin\":[";
    for(size_t i=0;i<tx.inputs.size();++i){
        if(i)s<<",";
        const auto&in=tx.inputs[i];
        std::string in_addr;
        int64_t in_amt=0;
        // Look up the source output
        auto iit=g_tx_index.find(in.prev_txid);
        if(iit!=g_tx_index.end()){
            int64_t ibh=iit->second.block_height;
            uint32_t itpos=iit->second.tx_pos;
            if(ibh<(int64_t)g_blocks.size()&&itpos<g_blocks[ibh].tx_hexes.size()){
                std::vector<Byte> iraw;
                if(decode_tx_hex(g_blocks[ibh].tx_hexes[itpos],iraw)){
                    Transaction itx; std::string ie;
                    if(Transaction::Deserialize(iraw,itx,&ie)&&in.prev_index<itx.outputs.size()){
                        in_addr=address_encode(itx.outputs[in.prev_index].pubkey_hash);
                        in_amt=itx.outputs[in.prev_index].amount;
                    }
                }
            }
        }
        s<<"{\"prev_txid\":\""<<to_hex(in.prev_txid.data(),32)
         <<"\",\"index\":"<<in.prev_index
         <<",\"address\":\""<<in_addr<<"\",\"amount\":"<<format_sost(in_amt)<<"}";
    }
    s<<"],\"vout\":[";
    for(size_t i=0;i<tx.outputs.size();++i){
        if(i)s<<",";
        const auto&o=tx.outputs[i];
        s<<"{\"address\":\""<<address_encode(o.pubkey_hash)
         <<"\",\"amount\":"<<format_sost(o.amount)
         <<",\"type\":"<<(int)o.type<<"}";
    }
    s<<"],\"fee\":"<<fee<<"}";
    return rpc_result(id,s.str());
}

// ESTIMATEFEE: analyze last 10 blocks + mempool for fee recommendation
static std::string handle_estimatefee(const std::string& id, const std::vector<std::string>&) {
    const int64_t MIN_FEE = 1000; // relay minimum in stocks/byte
    const int LOOKBACK = 10;

    // Analyze fees in last LOOKBACK blocks
    int64_t total_fee_rate = 0;
    int fee_samples = 0;

    int64_t start = std::max((int64_t)1, g_chain_height - LOOKBACK + 1);
    for(int64_t h=start; h<=g_chain_height && h<(int64_t)g_blocks.size(); ++h){
        const auto& blk=g_blocks[h];
        // Only look at standard txs (skip coinbase at index 0)
        for(size_t t=1; t<blk.tx_hexes.size(); ++t){
            std::vector<Byte> raw;
            if(!decode_tx_hex(blk.tx_hexes[t],raw)) continue;
            Transaction tx; std::string derr;
            if(!Transaction::Deserialize(raw,tx,&derr)) continue;

            int64_t sum_in=0,sum_out=0;
            for(const auto&in:tx.inputs){
                auto iit=g_tx_index.find(in.prev_txid);
                if(iit!=g_tx_index.end()){
                    int64_t ibh=iit->second.block_height;
                    uint32_t itpos=iit->second.tx_pos;
                    if(ibh<(int64_t)g_blocks.size()&&itpos<g_blocks[ibh].tx_hexes.size()){
                        std::vector<Byte> iraw;
                        if(decode_tx_hex(g_blocks[ibh].tx_hexes[itpos],iraw)){
                            Transaction itx; std::string ie;
                            if(Transaction::Deserialize(iraw,itx,&ie)&&in.prev_index<itx.outputs.size()){
                                sum_in+=itx.outputs[in.prev_index].amount;
                            }
                        }
                    }
                }
            }
            for(const auto&o:tx.outputs) sum_out+=o.amount;
            int64_t fee=sum_in-sum_out;
            if(fee>0 && raw.size()>0){
                total_fee_rate += fee / (int64_t)raw.size();
                fee_samples++;
            }
        }
    }

    int64_t fee_per_byte = MIN_FEE;
    std::string basis = "minimum_relay";
    if(fee_samples>0){
        fee_per_byte = std::max(MIN_FEE, total_fee_rate / fee_samples);
        basis = "block_analysis";
    }

    // Also check mempool
    int64_t mp_total_rate=0; int mp_samples=0;
    auto tmpl=g_mempool.BuildBlockTemplate();
    for(size_t i=0;i<tmpl.txs.size();++i){
        if(tmpl.txids.size()>i){
            const MempoolEntry* me=g_mempool.GetEntry(tmpl.txids[i]);
            if(me && me->size>0){
                mp_total_rate += me->fee / (int64_t)me->size;
                mp_samples++;
            }
        }
    }
    if(mp_samples>0){
        int64_t mp_rate = mp_total_rate / mp_samples;
        if(mp_rate > fee_per_byte){
            fee_per_byte = mp_rate;
            basis = "mempool_analysis";
        }
    }

    // Typical tx ~250 bytes
    int64_t typical_fee = fee_per_byte * 250;

    std::ostringstream s;
    s<<"{\"fee_per_byte\":"<<fee_per_byte
     <<",\"fee_for_typical_tx\":"<<typical_fee
     <<",\"basis\":\""<<basis<<"\"}";
    return rpc_result(id,s.str());
}

// GETADDRESSBALANCE: return balance for any address (used by web wallet)
static std::string handle_getaddressbalance(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing address");
    std::string addr = p[0];
    if(!address_valid(addr)) return rpc_error(id,-8,"invalid address");

    PubKeyHash pkh{};
    address_decode(addr, pkh);

    int64_t total = 0;
    int utxo_count = 0;
    const auto& umap = g_utxo_set.GetMap();
    for(const auto& kv : umap){
        if(kv.second.pubkey_hash == pkh){
            total += kv.second.amount;
            utxo_count++;
        }
    }

    std::ostringstream s;
    s<<"{\"address\":\""<<json_escape(addr)<<"\",\"balance\":"<<format_sost(total)
     <<",\"balance_stocks\":"<<total<<",\"utxo_count\":"<<utxo_count<<"}";
    return rpc_result(id,s.str());
}

static std::string handle_getaddressinfo(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing address");
    std::string addr = p[0];

    bool valid = address_valid(addr);
    bool mine = g_wallet.has_address(addr);

    PubKeyHash pkh{};
    address_decode(addr, pkh);

    int64_t total = 0;
    int utxo_count = 0;
    std::ostringstream utxo_arr;
    utxo_arr << "[";

    const auto& umap = g_utxo_set.GetMap();
    bool first = true;
    for (const auto& kv : umap) {
        const auto& op = kv.first;
        const auto& entry = kv.second;
        if (entry.pubkey_hash != pkh) continue;

        if (!first) utxo_arr << ",";
        first = false;

        utxo_arr << "{\"txid\":\"" << to_hex(op.txid.data(), 32)
                 << "\",\"vout\":" << op.index
                 << ",\"amount\":" << format_sost(entry.amount)
                 << ",\"height\":" << entry.height
                 << ",\"type\":" << (int)entry.type
                 << ",\"coinbase\":" << (entry.is_coinbase ? "true" : "false")
                 << "}";

        total += entry.amount;
        utxo_count++;
    }
    utxo_arr << "]";

    std::ostringstream s;
    s << "{\"address\":\"" << json_escape(addr) << "\""
      << ",\"isvalid\":" << (valid ? "true" : "false")
      << ",\"ismine\":" << (mine ? "true" : "false")
      << ",\"balance\":" << format_sost(total)
      << ",\"utxo_count\":" << utxo_count
      << ",\"utxos\":" << utxo_arr.str()
      << "}";
    return rpc_result(id, s.str());
}

static std::string handle_listbonds(const std::string& id, const std::vector<std::string>&) {
    auto bonds=g_wallet.list_bonds(g_chain_height);
    std::ostringstream s; s<<"[";
    for(size_t i=0;i<bonds.size();++i){
        if(i)s<<","; const auto& u=bonds[i];
        bool locked=(g_chain_height>=0&&(uint64_t)g_chain_height<u.lock_until);
        s<<"{\"txid\":\""<<to_hex(u.txid.data(),32)<<"\",\"vout\":"<<u.vout
         <<",\"type\":"<<(u.output_type==0x10?"\"bond\"":"\"escrow\"")
         <<",\"amount\":"<<format_sost(u.amount)
         <<",\"lock_until\":"<<u.lock_until
         <<",\"status\":\""<<(locked?"locked":"unlocked")<<"\"";
        if(u.output_type==0x11)
            s<<",\"beneficiary\":\""<<address_encode(u.beneficiary)<<"\"";
        if(locked&&g_chain_height>=0)
            s<<",\"blocks_remaining\":"<<(u.lock_until-(uint64_t)g_chain_height);
        s<<"}";
    }
    s<<"]"; return rpc_result(id,s.str());
}

// Dispatch
using RpcHandler=std::function<std::string(const std::string&,const std::vector<std::string>&)>;
static std::map<std::string,RpcHandler> g_handlers={
    {"getblockcount",handle_getblockcount},
    {"getblockhash",handle_getblockhash},
    {"getblock",handle_getblock},
    {"getinfo",handle_getinfo},
    {"getbalance",handle_getbalance},
    {"getnewaddress",handle_getnewaddress},
    {"validateaddress",handle_validateaddress},
    {"listunspent",handle_listunspent},
    {"gettxout",handle_gettxout},
    {"sendrawtransaction",handle_sendrawtransaction},
    {"getmempoolinfo",handle_getmempoolinfo},
    {"getrawmempool",handle_getrawmempool},
    {"getrawtransaction",handle_getrawtransaction},
    {"getpeerinfo",handle_getpeerinfo},
    {"submitblock",handle_submitblock},
    {"getblocktemplate",handle_getblocktemplate},
    {"getaddressinfo",handle_getaddressinfo},
    {"gettransaction",handle_gettransaction},
    {"estimatefee",handle_estimatefee},
    {"getaddressbalance",handle_getaddressbalance},
    {"listbonds",handle_listbonds},
};

static std::string dispatch_rpc(const std::string& req) {
    std::string method=json_get_string(req,"method"),id_raw=json_get_string(req,"id");
    std::string id=id_raw.empty()?"null":id_raw;
    if(!id_raw.empty()&&id_raw[0]>='0'&&id_raw[0]<='9') id=id_raw;
    else if(id_raw!="null"&&!id_raw.empty()) id="\""+id_raw+"\"";

    if(method.empty()) return rpc_error(id,-32600,"missing method");
    auto it=g_handlers.find(method);
    if(it==g_handlers.end()) return rpc_error(id,-32601,"Method not found: "+method);
    return it->second(id,json_get_params(req));
}

// =============================================================================
// P2P Protocol
// =============================================================================

// P2PMsg defined earlier (near encryption section)

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

static bool write_exact(int fd, const void* buf, size_t len) {
    size_t sent=0;
    const uint8_t* p=static_cast<const uint8_t*>(buf);
    while(sent<len){
        ssize_t n=write(fd,p+sent,len-sent);
        if(n<=0) return false;
        sent+=n;
    }
    return true;
}

static bool p2p_send(int fd, const char* cmd, const uint8_t* payload, size_t len) {
    uint8_t hdr[12];
    write_u32(hdr, P2P_MAGIC);
    memcpy(hdr+4, cmd, 4);
    write_u32(hdr+8, (uint32_t)len);
    if(!write_exact(fd, hdr, 12)) return false;
    if(len>0 && !write_exact(fd, payload, len)) return false;
    return true;
}

static bool p2p_recv(int fd, P2PMsg& msg) {
    uint8_t hdr[12];
    if(!read_exact(fd, hdr, 12)) return false;
    uint32_t magic=read_u32(hdr);
    if(magic!=P2P_MAGIC) return false;
    memcpy(msg.cmd, hdr+4, 4); msg.cmd[4]=0;
    uint32_t len=read_u32(hdr+8);
    if(len>MAX_P2P_MSG_SIZE) return false;
    msg.payload.resize(len);
    if(len>0 && !read_exact(fd, msg.payload.data(), len)) return false;
    return true;
}

// Encrypted p2p send/recv (X25519 + ChaCha20-Poly1305)
static bool p2p_send_encrypted(int fd, PeerCrypto& crypto, const char* cmd,
    const uint8_t* payload, size_t len) {
    if(!crypto.encrypted) return false;
    size_t plen = 4 + len;
    std::vector<uint8_t> plain(plen);
    memcpy(plain.data(), cmd, 4);
    if(len>0) memcpy(plain.data()+4, payload, len);

    std::vector<uint8_t> cipher(plen);
    uint8_t tag[16];
    if(!chacha20_poly1305_encrypt(crypto.send_key, crypto.send_nonce++,
        plain.data(), plen, cipher.data(), tag)) return false;

    uint8_t hdr[12];
    write_u32(hdr, P2P_MAGIC);
    memcpy(hdr+4, "ENCR", 4);
    write_u32(hdr+8, (uint32_t)(plen + 16));
    if(!write_exact(fd, hdr, 12)) return false;
    if(!write_exact(fd, cipher.data(), plen)) return false;
    if(!write_exact(fd, tag, 16)) return false;
    return true;
}

static bool p2p_recv_encrypted(int fd, PeerCrypto& crypto, P2PMsg& msg) {
    uint8_t hdr[12];
    if(!read_exact(fd, hdr, 12)) return false;
    uint32_t magic=read_u32(hdr);
    if(magic!=P2P_MAGIC) return false;

    char cmd[5]; memcpy(cmd, hdr+4, 4); cmd[4]=0;
    uint32_t len=read_u32(hdr+8);

    if(strcmp(cmd,"ENCR")!=0){
        if(len>MAX_P2P_MSG_SIZE) return false;
        msg.payload.resize(len);
        memcpy(msg.cmd, cmd, 5);
        if(len>0 && !read_exact(fd, msg.payload.data(), len)) return false;
        return true;
    }

    if(len < 20 || len > MAX_P2P_MSG_SIZE) return false;
    uint32_t clen = len - 16;
    std::vector<uint8_t> cipher(clen);
    uint8_t tag[16];
    if(!read_exact(fd, cipher.data(), clen)) return false;
    if(!read_exact(fd, tag, 16)) return false;

    std::vector<uint8_t> plain(clen);
    if(!chacha20_poly1305_decrypt(crypto.recv_key, crypto.recv_nonce++,
        cipher.data(), clen, tag, plain.data())) return false;

    memcpy(msg.cmd, plain.data(), 4); msg.cmd[4]=0;
    msg.payload.assign(plain.begin()+4, plain.end());
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
     <<"\",\"commit\":\""<<to_hex(b.commit.data(),32)
     <<"\",\"checkpoints_root\":\""<<to_hex(b.checkpoints_root.data(),32)
     <<"\",\"height\":"<<b.height
     <<",\"timestamp\":"<<b.timestamp
     <<",\"bits_q\":"<<b.bits_q
     <<",\"nonce\":"<<b.nonce
     <<",\"extra_nonce\":"<<b.extra_nonce
     <<",\"subsidy\":"<<b.subsidy
     <<",\"miner\":"<<b.miner_reward
     <<",\"gold_vault\":"<<b.gold_vault_reward
     <<",\"popc_pool\":"<<b.popc_pool_reward
     <<",\"stability_metric\":"<<b.stability_metric;

    // Include transactions for full block sync (v0.3.2)
    if (!b.tx_hexes.empty()) {
        s << ",\"transactions\":[";
        for (size_t t = 0; t < b.tx_hexes.size(); ++t) {
            if (t) s << ",";
            s << "\"" << b.tx_hexes[t] << "\"";
        }
        s << "]";
    }

    s << "}";
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

// =============================================================================
// Block processing (FULL validation + PoW)
// =============================================================================

static bool decode_tx_hex(const std::string& tx_hex, std::vector<Byte>& out_raw) {
    if(tx_hex.empty() || (tx_hex.size()%2)!=0) return false;
    out_raw.clear();
    out_raw.reserve(tx_hex.size()/2);
    for(size_t i=0;i<tx_hex.size();i+=2){
        uint8_t b;
        if(!hex_to_bytes(tx_hex.substr(i,2), &b, 1)) return false;
        out_raw.push_back(b);
    }
    return true;
}

static bool compute_fee_for_tx(const Transaction& tx, const IUtxoView& view, int64_t& out_fee, std::string* err) {
    __int128 sum_in=0;
    for(size_t i=0;i<tx.inputs.size();++i){
        OutPoint op{tx.inputs[i].prev_txid, tx.inputs[i].prev_index};
        auto utxo=view.GetUTXO(op);
        if(!utxo.has_value()){
            if(err) *err="fee: missing utxo for input["+std::to_string(i)+"]";
            return false;
        }
        sum_in += (__int128)utxo->amount;
    }
    __int128 sum_out=0;
    for(const auto& o:tx.outputs) sum_out += (__int128)o.amount;
    __int128 fee=sum_in - sum_out;
    if(fee < 0 || fee > (__int128)SUPPLY_MAX_STOCKS){
        if(err) *err="fee: invalid computed fee";
        return false;
    }
    out_fee=(int64_t)fee;
    return true;
}

static bool process_block(const std::string& block_json) {
    std::lock_guard<std::mutex> lk(g_chain_mu);

    // Required fields
    std::string bid = jstr(block_json,"block_id");
    std::string prev = jstr(block_json,"prev_hash");
    std::string mrkl = jstr(block_json,"merkle_root");
    std::string commit_hex = jstr(block_json,"commit");
    std::string croot_hex  = jstr(block_json,"checkpoints_root");

    if(bid.size()!=64 || prev.size()!=64 || mrkl.size()!=64 || commit_hex.size()!=64 || croot_hex.size()!=64){
        printf("[BLOCK] REJECTED: missing/invalid required hex fields\n");
        return false;
    }

    int64_t height = jint(block_json,"height");
    int64_t ts64   = jint(block_json,"timestamp");
    uint32_t bits_q= (uint32_t)jint(block_json,"bits_q");
    uint32_t nonce = (uint32_t)jint(block_json,"nonce");
    uint32_t extra = (uint32_t)jint(block_json,"extra_nonce");
    int64_t subsidy= jint(block_json,"subsidy");
    int64_t miner_r= jint(block_json,"miner");
    int64_t gold_r = jint(block_json,"gold_vault");
    int64_t popc_r = jint(block_json,"popc_pool");
    uint64_t stb   = juint(block_json,"stability_metric");
    std::string x_bytes_hex = jstr(block_json,"x_bytes");
    std::string final_state_hex = jstr(block_json,"final_state");

    // Parse checkpoint_leaves array (for CX proof verification)
    std::vector<Bytes32> checkpoint_leaves_vec;
    {
        // Simple JSON array parser for checkpoint_leaves
        auto cl_start = block_json.find("\"checkpoint_leaves\"");
        if (cl_start != std::string::npos) {
            auto arr_start = block_json.find('[', cl_start);
            auto arr_end = block_json.find(']', arr_start);
            if (arr_start != std::string::npos && arr_end != std::string::npos) {
                std::string arr = block_json.substr(arr_start + 1, arr_end - arr_start - 1);
                size_t pos = 0;
                while (pos < arr.size()) {
                    auto q1 = arr.find('"', pos);
                    if (q1 == std::string::npos) break;
                    auto q2 = arr.find('"', q1 + 1);
                    if (q2 == std::string::npos) break;
                    std::string leaf_hex = arr.substr(q1 + 1, q2 - q1 - 1);
                    if (leaf_hex.size() == 64)
                        checkpoint_leaves_vec.push_back(from_hex(leaf_hex));
                    pos = q2 + 1;
                }
            }
        }
    }

    if(height != (int64_t)g_blocks.size()){
        printf("[BLOCK] REJECTED: height %lld != expected %zu\n",(long long)height,g_blocks.size());
        return false;
    }

    // Chain link
    Hash256 prev_h = from_hex(prev);
    if(!g_blocks.empty() && prev_h != g_blocks.back().block_id){
        printf("[BLOCK] REJECTED: prev_hash mismatch\n");
        return false;
    }

    // Timestamp rules
    if(!g_blocks.empty() && ts64 <= g_blocks.back().timestamp){
        printf("[BLOCK] REJECTED: timestamp not increasing\n");
        return false;
    }
    int64_t now_ts=(int64_t)time(nullptr);
    if(ts64 > now_ts + MAX_FUTURE_DRIFT){
        printf("[BLOCK] REJECTED: timestamp too far in future\n");
        return false;
    }

    // Difficulty must match cASERT bitsQ
    std::vector<BlockMeta> chain_meta;
    chain_meta.reserve(g_blocks.size());
    for(const auto& b:g_blocks){
        BlockMeta bm; bm.block_id=b.block_id; bm.height=b.height; bm.time=b.timestamp; bm.powDiffQ=b.bits_q;
        chain_meta.push_back(bm);
    }
    uint32_t expected_diff = casert_next_bitsq(chain_meta, height);
    if(bits_q != expected_diff){
        printf("[BLOCK] REJECTED: bits_q mismatch (got=%u expected=%u)\n",bits_q,expected_diff);
        return false;
    }

    // Decode txs (coinbase included)
    std::vector<std::string> tx_hexes = json_get_tx_hexes(block_json);
    if(tx_hexes.empty()){
        printf("[BLOCK] REJECTED: missing transactions[] (must include coinbase)\n");
        return false;
    }

    std::vector<Transaction> txs;
    txs.reserve(tx_hexes.size());
    for(const auto& hx : tx_hexes){
        std::vector<Byte> raw;
        if(!decode_tx_hex(hx, raw)){
            printf("[BLOCK] REJECTED: bad tx hex in transactions[]\n");
            return false;
        }
        Transaction tx; std::string derr;
        if(!Transaction::Deserialize(raw, tx, &derr)){
            printf("[BLOCK] REJECTED: tx deserialize failed: %s\n", derr.c_str());
            return false;
        }
        txs.push_back(std::move(tx));
    }

    // Validate merkle root from txs
    Hash256 computed_mrkl{}; std::string merr;
    if(!ComputeMerkleRootFromTxs(txs, computed_mrkl, &merr)){
        printf("[BLOCK] REJECTED: merkle compute failed: %s\n", merr.c_str());
        return false;
    }
    Hash256 mrkl_h = from_hex(mrkl);
    if(computed_mrkl != mrkl_h){
        printf("[BLOCK] REJECTED: merkle_root mismatch\n");
        printf("  got:      %s\n", to_hex(mrkl_h.data(),32).c_str());
        printf("  computed: %s\n", to_hex(computed_mrkl.data(),32).c_str());
        return false;
    }

    // Coinbase consensus validation: subsidy + total_fees must match outputs split.
    if(txs[0].tx_type != TX_TYPE_COINBASE){
        printf("[BLOCK] REJECTED: txs[0] must be coinbase\n");
        return false;
    }

    // Compute total fees from standard txs using current UTXO view (pre-state)
    int64_t total_fees = 0;
    TxValidationContext vctx;
    vctx.genesis_hash = g_genesis_hash;
    vctx.spend_height = height; // coinbase maturity uses spend_height - utxo.height

    for(size_t i=1;i<txs.size();++i){
        if(txs[i].tx_type != TX_TYPE_STANDARD){
            printf("[BLOCK] REJECTED: non-standard tx at index %zu\n", i);
            return false;
        }
        auto cres = ValidateTransactionConsensus(txs[i], g_utxo_set, vctx);
        if(!cres.ok){
            printf("[BLOCK] REJECTED: tx consensus fail: %s\n", cres.message.c_str());
            return false;
        }
        auto pres = ValidateTransactionPolicy(txs[i], g_utxo_set, vctx);
        if(!pres.ok){
            printf("[BLOCK] REJECTED: tx policy fail: %s\n", pres.message.c_str());
            return false;
        }
        int64_t fee_i=0; std::string ferr;
        if(!compute_fee_for_tx(txs[i], g_utxo_set, fee_i, &ferr)){
            printf("[BLOCK] REJECTED: cannot compute fee: %s\n", ferr.c_str());
            return false;
        }
        total_fees += fee_i;
        if(total_fees < 0 || total_fees > SUPPLY_MAX_STOCKS){
            printf("[BLOCK] REJECTED: fee overflow\n");
            return false;
        }
    }

    // Subsidy must match schedule
    int64_t expected_sub = sost_subsidy_stocks(height);
    if(subsidy != expected_sub){
        printf("[BLOCK] REJECTED: subsidy mismatch (got=%lld expected=%lld)\n",
               (long long)subsidy,(long long)expected_sub);
        return false;
    }

    // Validate coinbase amounts/destinations against subsidy+fees
    PubKeyHash gold_pkh{}, popc_pkh{};
    address_decode(ADDR_GOLD_VAULT, gold_pkh);
    address_decode(ADDR_POPC_POOL, popc_pkh);
    auto cbr = ValidateCoinbaseConsensus(txs[0], height, subsidy, total_fees, gold_pkh, popc_pkh);
    if(!cbr.ok){
        printf("[BLOCK] REJECTED: coinbase invalid: %s\n", cbr.message.c_str());
        return false;
    }

    // Also check JSON claimed split matches real coinbase outputs (hardening)
    if((int64_t)txs[0].outputs.size()!=3){
        printf("[BLOCK] REJECTED: coinbase outputs != 3\n");
        return false;
    }
    if(txs[0].outputs[0].amount!=miner_r || txs[0].outputs[1].amount!=gold_r || txs[0].outputs[2].amount!=popc_r){
        printf("[BLOCK] REJECTED: JSON rewards mismatch vs coinbase tx outputs\n");
        return false;
    }

    // Recompute block_id and verify PoW
    Bytes32 prev32 = prev_h;
    Bytes32 mrkl32 = computed_mrkl;
    Bytes32 commit32 = from_hex(commit_hex);
    Bytes32 croot32  = from_hex(croot_hex);

    uint8_t hc72[72];
    build_hc72(hc72, prev32, mrkl32, (uint32_t)ts64, bits_q);
    auto full_hdr = build_full_header_bytes(hc72, croot32, nonce, extra);
    Bytes32 computed_bid = compute_block_id(full_hdr.data(), full_hdr.size(), commit32);

    Bytes32 provided_bid = from_hex(bid);
    if(computed_bid != provided_bid){
        printf("[BLOCK] REJECTED: block_id mismatch (computed != provided)\n");
        printf("  provided: %s\n", to_hex(provided_bid.data(),32).c_str());
        printf("  computed: %s\n", to_hex(computed_bid.data(),32).c_str());
        // Diagnostic: show profile magic being used
        printf("  ACTIVE_PROFILE: %s (magic bytes in header)\n",
               ACTIVE_PROFILE==Profile::MAINNET?"MAINNET":
               ACTIVE_PROFILE==Profile::TESTNET?"TESTNET":"DEV");
        return false;
    }

    // ALWAYS verify commit <= target (cheap PoW inequality check).
    // This runs regardless of fast sync mode.
    if(!pow_meets_target(commit32, bits_q)){
        printf("[BLOCK] REJECTED: PoW invalid (commit !<= target)\n");
        return false;
    }

    // CONVERGENCEX TRANSCRIPT V2 VERIFICATION
    // Parse segments_root from block JSON
    std::string segments_root_hex = jstr(block_json, "segments_root");

    if (!x_bytes_hex.empty() && !final_state_hex.empty() && !segments_root_hex.empty()) {
        // Decode hex fields
        auto hex_decode = [](const std::string& h) -> std::vector<uint8_t> {
            std::vector<uint8_t> out; out.reserve(h.size()/2);
            auto hx = [](char c) -> uint8_t {
                if(c>='0'&&c<='9') return c-'0'; if(c>='a'&&c<='f') return 10+c-'a';
                if(c>='A'&&c<='F') return 10+c-'A'; return 0; };
            for(size_t i=0;i+1<h.size();i+=2) out.push_back((hx(h[i])<<4)|hx(h[i+1]));
            return out;
        };
        std::vector<uint8_t> x_bytes_raw = hex_decode(x_bytes_hex);
        Bytes32 fstate = from_hex(final_state_hex);
        Bytes32 sroot = from_hex(segments_root_hex);

        // Parse segment_proofs from JSON
        std::vector<SegmentProof> seg_proofs_vec;
        {
            auto sp_start = block_json.find("\"segment_proofs\"");
            if (sp_start != std::string::npos) {
                auto arr_s = block_json.find('[', sp_start);
                if (arr_s != std::string::npos) {
                    // Find the matching ] for the outer array (skip nested [] pairs)
                    size_t arr_e = arr_s + 1;
                    int depth = 1;
                    while (arr_e < block_json.size() && depth > 0) {
                        if (block_json[arr_e] == '[') depth++;
                        else if (block_json[arr_e] == ']') depth--;
                        if (depth > 0) arr_e++;
                    }
                    printf("[PARSE] segment_proofs array: pos %zu to %zu (%zu chars)\n", arr_s, arr_e, arr_e - arr_s);
                    fflush(stdout);
                    // Parse array of segment proof objects
                    size_t pos = arr_s + 1;
                    while (pos < arr_e) {
                        auto obj_s = block_json.find('{', pos);
                        if (obj_s == std::string::npos || obj_s >= arr_e) break;
                        // Find matching } (skip nested {})
                        size_t obj_e = obj_s + 1;
                        int od = 1;
                        while (obj_e < block_json.size() && od > 0) {
                            if (block_json[obj_e] == '{') od++;
                            else if (block_json[obj_e] == '}') od--;
                            if (od > 0) obj_e++;
                        }
                        if (od != 0) break;
                        std::string obj = block_json.substr(obj_s, obj_e - obj_s + 1);
                        SegmentProof sp;
                        sp.leaf.segment_index = (uint32_t)jint(obj, "si");
                        sp.leaf.round_start = (uint32_t)jint(obj, "rs");
                        sp.leaf.round_end = (uint32_t)jint(obj, "re");
                        sp.leaf.state_start = from_hex(jstr(obj, "ss"));
                        sp.leaf.state_end = from_hex(jstr(obj, "se"));
                        sp.leaf.x_start_hash = from_hex(jstr(obj, "xsh"));
                        sp.leaf.x_end_hash = from_hex(jstr(obj, "xeh"));
                        sp.leaf.residual_start = juint(obj, "rrs");
                        sp.leaf.residual_end = juint(obj, "rre");
                        // Parse merkle_path
                        auto mp_s = obj.find("\"mp\"");
                        if (mp_s != std::string::npos) {
                            auto mp_arr = obj.find('[', mp_s);
                            auto mp_end = obj.find(']', mp_arr);
                            if (mp_arr != std::string::npos && mp_end != std::string::npos) {
                                std::string mps = obj.substr(mp_arr+1, mp_end-mp_arr-1);
                                size_t mpos = 0;
                                while (mpos < mps.size()) {
                                    auto q1 = mps.find('"', mpos);
                                    if (q1 == std::string::npos) break;
                                    auto q2 = mps.find('"', q1+1);
                                    if (q2 == std::string::npos) break;
                                    std::string lh = mps.substr(q1+1, q2-q1-1);
                                    if (lh.size() == 64) sp.merkle_path.push_back(from_hex(lh));
                                    mpos = q2+1;
                                }
                            }
                        }
                        seg_proofs_vec.push_back(sp);
                        pos = obj_e + 1;
                    }
                }
            }
            printf("[PARSE] Parsed %zu segment_proofs\n", seg_proofs_vec.size()); fflush(stdout);
        }
        // Parse round_witnesses from JSON
        std::vector<RoundWitness> round_witnesses_vec;
        {
            auto rw_start = block_json.find("\"round_witnesses\"");
            if (rw_start != std::string::npos) {
                auto arr_s = block_json.find('[', rw_start);
                if (arr_s != std::string::npos) {
                    // Find matching ] for outer array (skip nested [])
                    size_t arr_e = arr_s + 1;
                    { int d2 = 1; while (arr_e < block_json.size() && d2 > 0) { if (block_json[arr_e]=='[') d2++; else if (block_json[arr_e]==']') d2--; if (d2>0) arr_e++; } }
                    printf("[PARSE] round_witnesses array: pos %zu to %zu (%zu chars)\n", arr_s, arr_e, arr_e - arr_s);
                    fflush(stdout);
                    size_t pos = arr_s + 1;
                    while (pos < arr_e) {
                        auto obj_s = block_json.find('{', pos);
                        if (obj_s == std::string::npos || obj_s >= arr_e) break;
                        // Find matching closing brace (skip nested {})
                        int depth = 0; size_t obj_e = obj_s;
                        for (size_t k = obj_s; k < block_json.size(); ++k) {
                            if (block_json[k] == '{') depth++;
                            if (block_json[k] == '}') { depth--; if (depth == 0) { obj_e = k; break; } }
                        }
                        std::string obj = block_json.substr(obj_s, obj_e - obj_s + 1);
                        RoundWitness rw;
                        rw.round_index = (uint32_t)jint(obj, "ri");
                        rw.state_before = from_hex(jstr(obj, "sb"));
                        rw.state_after = from_hex(jstr(obj, "sa"));
                        rw.dataset_value = juint(obj, "dv");
                        rw.program_output = juint(obj, "po");
                        // Decode x_before (128 hex chars = 32 int32)
                        std::string xb_hex = jstr(obj, "xb");
                        auto hxd = [](const std::string& h) -> std::vector<uint8_t> {
                            std::vector<uint8_t> o; auto hx=[](char c)->uint8_t{
                                if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return 10+c-'a';
                                if(c>='A'&&c<='F')return 10+c-'A';return 0;};
                            for(size_t i=0;i+1<h.size();i+=2)o.push_back((hx(h[i])<<4)|hx(h[i+1]));
                            return o;
                        };
                        auto xb_raw = hxd(xb_hex);
                        for (int k = 0; k < 32 && k*4+3 < (int)xb_raw.size(); ++k)
                            rw.x_before[k] = read_i32_le(xb_raw.data() + k*4);
                        std::string xa_hex = jstr(obj, "xa");
                        auto xa_raw = hxd(xa_hex);
                        for (int k = 0; k < 32 && k*4+3 < (int)xa_raw.size(); ++k)
                            rw.x_after[k] = read_i32_le(xa_raw.data() + k*4);
                        // Parse scratch_values and scratch_indices arrays
                        auto parse_i32_arr = [&](const std::string& key) -> std::array<int32_t,4> {
                            std::array<int32_t,4> a{};
                            auto ks = obj.find("\"" + key + "\"");
                            if (ks == std::string::npos) return a;
                            auto as = obj.find('[', ks); auto ae = obj.find(']', as);
                            if (as == std::string::npos || ae == std::string::npos) return a;
                            std::string arr = obj.substr(as+1, ae-as-1);
                            int idx = 0; size_t p = 0;
                            while (p < arr.size() && idx < 4) {
                                while (p < arr.size() && (arr[p]==' '||arr[p]==',')) p++;
                                if (p >= arr.size()) break;
                                a[idx++] = (int32_t)std::strtol(arr.c_str()+p, nullptr, 10);
                                while (p < arr.size() && arr[p]!=',') p++;
                            }
                            return a;
                        };
                        auto parse_u32_arr = [&](const std::string& key) -> std::array<uint32_t,4> {
                            std::array<uint32_t,4> a{};
                            auto ks = obj.find("\"" + key + "\"");
                            if (ks == std::string::npos) return a;
                            auto as = obj.find('[', ks); auto ae = obj.find(']', as);
                            if (as == std::string::npos || ae == std::string::npos) return a;
                            std::string arr = obj.substr(as+1, ae-as-1);
                            int idx = 0; size_t p = 0;
                            while (p < arr.size() && idx < 4) {
                                while (p < arr.size() && (arr[p]==' '||arr[p]==',')) p++;
                                if (p >= arr.size()) break;
                                a[idx++] = (uint32_t)std::strtoul(arr.c_str()+p, nullptr, 10);
                                while (p < arr.size() && arr[p]!=',') p++;
                            }
                            return a;
                        };
                        rw.scratch_values = parse_i32_arr("sv");
                        rw.scratch_indices = parse_u32_arr("si2");
                        round_witnesses_vec.push_back(rw);
                        pos = obj_e + 1;
                    }
                }
            }
        }
        printf("[BLOCK-V2] Parsed: x_bytes=%zu final_state=%s segments_root=%s cp_leaves=%zu seg_proofs=%zu rw=%zu\n",
                x_bytes_raw.size(), final_state_hex.substr(0,16).c_str(), segments_root_hex.substr(0,16).c_str(),
                checkpoint_leaves_vec.size(), seg_proofs_vec.size(), round_witnesses_vec.size());
        fflush(stdout);

        ConsensusParams cx_params = sost::get_consensus_params(sost::Profile::MAINNET, height);
        // Use the miner's declared stability profile (includes anti-stall decay)
        // The miner sends the exact params it used; we verify the proof with those params.
        // Security: a miner using easier params gets easier stability but still needs commit<=target.
        {
            int32_t declared_scale = (int32_t)jint(block_json, "stab_scale");
            int32_t declared_k = (int32_t)jint(block_json, "stab_k");
            int32_t declared_margin = (int32_t)jint(block_json, "stab_margin");
            int32_t declared_steps = (int32_t)jint(block_json, "stab_steps");
            int32_t declared_lr = (int32_t)jint(block_json, "stab_lr_shift");

            if (declared_scale > 0 && declared_k > 0 && declared_margin > 0 && declared_steps > 0) {
                // Validate: declared params must be within the E3-H6 range (not easier than E3)
                bool valid_profile = declared_scale >= 1 && declared_scale <= 4
                    && declared_k >= 3 && declared_k <= 7
                    && declared_margin >= 120 && declared_margin <= 240
                    && declared_steps >= 3 && declared_steps <= 7;
                if (!valid_profile) {
                    printf("[BLOCK] REJECTED: declared stability params out of valid range (scale=%d k=%d margin=%d steps=%d)\n",
                           declared_scale, declared_k, declared_margin, declared_steps);
                    fflush(stdout);
                    return false;
                }
                cx_params.stab_scale = declared_scale;
                cx_params.stab_k = declared_k;
                cx_params.stab_margin = declared_margin;
                cx_params.stab_steps = declared_steps;
                if (declared_lr > 0) cx_params.stab_lr_shift = declared_lr;
                printf("[BLOCK-V2] Using miner's declared profile: scale=%d k=%d margin=%d steps=%d lr=%d\n",
                       cx_params.stab_scale, cx_params.stab_k, cx_params.stab_margin, cx_params.stab_steps, cx_params.stab_lr_shift);
            } else {
                // Fallback: recompute from chain (for blocks without declared profile)
                std::vector<BlockMeta> meta;
                for (size_t j = 0; j < g_blocks.size(); ++j) {
                    BlockMeta bm; bm.block_id = g_blocks[j].block_id;
                    bm.height = g_blocks[j].height; bm.time = g_blocks[j].timestamp;
                    bm.powDiffQ = g_blocks[j].bits_q;
                    meta.push_back(bm);
                }
                auto cdec = sost::casert_compute(meta, height, 0);
                cx_params = sost::casert_apply_profile(cx_params, cdec);
                printf("[BLOCK-V2] Fallback cASERT: H=%d scale=%d k=%d margin=%d steps=%d\n",
                       cdec.profile_index, cx_params.stab_scale, cx_params.stab_k, cx_params.stab_margin, cx_params.stab_steps);
            }
            fflush(stdout);
        }

        if (height == 0) {
            // Genesis: verify commit binding + stability only (no challenges)
            // Verify checkpoint leaves
            if (checkpoint_leaves_vec.empty()) { printf("[BLOCK] REJECTED: missing checkpoint_leaves\n"); return false; }
            Bytes32 cp_root = merkle_root_16(checkpoint_leaves_vec);
            if (cp_root != croot32) { printf("[BLOCK] REJECTED: checkpoint merkle mismatch\n"); return false; }
            // Verify commit V2 (includes segments_root)
            Bytes32 prev_h; std::memcpy(prev_h.data(), hc72, 32);
            Bytes32 bk = compute_block_key(prev_h);
            std::vector<uint8_t> sbuf_v; append_magic(sbuf_v); append(sbuf_v,"SEED",4);
            append(sbuf_v, hc72, 72); append(sbuf_v, bk);
            append_u32_le(sbuf_v, nonce); append_u32_le(sbuf_v, extra);
            Bytes32 seed_v = sha256(sbuf_v);
            std::vector<uint8_t> cbuf_v; append_magic(cbuf_v); append(cbuf_v,"COMMIT",6);
            append(cbuf_v, hc72, 72); append(cbuf_v, seed_v); append(cbuf_v, fstate);
            append(cbuf_v, x_bytes_raw.data(), x_bytes_raw.size());
            append(cbuf_v, croot32); append(cbuf_v, sroot);
            append_u64_le(cbuf_v, stb);
            if (sha256(cbuf_v) != commit32) { printf("[BLOCK] REJECTED: commit V2 mismatch\n"); return false; }
            printf("[BLOCK] Genesis CX proof verified (commit V2 + checkpoint merkle)\n");
        } else {
            // Full Transcript V2 verification for non-genesis blocks
            if (!sost::verify_cx_proof(hc72, nonce, extra,
                    commit32, croot32, sroot, fstate,
                    x_bytes_raw.data(), x_bytes_raw.size(),
                    stb, checkpoint_leaves_vec,
                    seg_proofs_vec, round_witnesses_vec, cx_params)) {
                printf("[BLOCK] REJECTED: CX Transcript V2 verification failed\n");
                return false;
            }
            printf("[BLOCK] CX Transcript V2 verified\n");
        }
    } else if (height > 0) {
        printf("[BLOCK] REJECTED: missing CX proof data\n");
        return false;
    }

    // FAST SYNC DECISION:
    // Hard checkpoints and assumevalid anchors allow skipping expensive full CX recomputation
    // (100K rounds), but the lightweight proof verification above always runs.
    std::string bid_hex = to_hex(computed_bid.data(), 32);
    bool anchor_on_chain = false;
    if(sost::has_assumevalid_anchor() && sost::ASSUMEVALID_HEIGHT < g_blocks.size()){
        std::string chain_hash = to_hex(g_blocks[sost::ASSUMEVALID_HEIGHT].block_id.data(), 32);
        anchor_on_chain = (chain_hash == sost::ASSUMEVALID_BLOCK_HASH);
    }
    bool skip_cx = sost::can_skip_cx_recomputation(
        (uint32_t)height, bid_hex, anchor_on_chain, g_full_verify_mode);
    if(skip_cx){
        printf("[BLOCK] fast-sync height=%lld (lightweight CX proof passed, full recompute skipped)\n",
               (long long)height);
    }

    // Checkpoint validation: if this height has a checkpoint, block_id must match
    for(size_t ci=0; ci<g_num_checkpoints; ++ci){
        if(g_checkpoints[ci].height == height){
            Hash256 expected_cp = from_hex(g_checkpoints[ci].block_hash);
            if(computed_bid != expected_cp){
                printf("[BLOCK] REJECTED: checkpoint mismatch at height %lld\n",(long long)height);
                return false;
            }
            printf("[BLOCK] Checkpoint verified at height %lld\n",(long long)height);
            break;
        }
    }

    // Reorg depth limit: reject blocks that would require undoing more than MAX_REORG_DEPTH blocks
    // (Currently chain is append-only, but this guards against future reorg logic)
    if(height < g_chain_height - MAX_REORG_DEPTH){
        printf("[BLOCK] REJECTED: height %lld is beyond max reorg depth (%lld blocks behind tip %lld)\n",
               (long long)height, (long long)MAX_REORG_DEPTH, (long long)g_chain_height);
        return false;
    }

    // Reject blocks that would reorg past a checkpoint
    for(size_t ci=0; ci<g_num_checkpoints; ++ci){
        if(g_checkpoints[ci].height <= g_chain_height && height <= g_checkpoints[ci].height){
            printf("[BLOCK] REJECTED: would reorg past checkpoint at height %lld\n",
                   (long long)g_checkpoints[ci].height);
            return false;
        }
    }

    // Connect block to UTXO set atomically
    BlockUndo undo;
    std::string uerr;
    if(!g_utxo_set.ConnectBlock(txs, height, undo, &uerr)){
        printf("[BLOCK] REJECTED: UTXO ConnectBlock failed: %s\n", uerr.c_str());
        return false;
    }

    // Accept block: record
    StoredBlock sb;
    sb.block_id = computed_bid;
    sb.prev_hash = prev_h;
    sb.merkle_root = computed_mrkl;
    sb.commit = commit32;
    sb.checkpoints_root = croot32;
    sb.timestamp = ts64;
    sb.bits_q = bits_q;
    sb.nonce = nonce;
    sb.extra_nonce = extra;
    sb.height = height;
    sb.subsidy = subsidy;
    sb.miner_reward = miner_r;
    sb.gold_vault_reward = gold_r;
    sb.popc_pool_reward = popc_r;
    sb.stability_metric = stb;
    sb.x_bytes_hex = x_bytes_hex;
    sb.final_state_hex = final_state_hex;
    sb.tx_hexes = tx_hexes;  // PERSIST all transaction hex strings

    g_blocks.push_back(sb);
    g_chain_height = height;

    // TX-INDEX: index all transactions in this block
    for(size_t ti=0; ti<txs.size(); ++ti){
        Hash256 txid_i{}; txs[ti].ComputeTxId(txid_i, nullptr);
        g_tx_index[txid_i] = {height, (uint32_t)ti};
    }

    // Wallet bookkeeping (mark spends + add outputs owned by us)
    for(size_t ti=1; ti<txs.size(); ++ti){
        for(const auto& in:txs[ti].inputs){
            g_wallet.mark_spent(in.prev_txid, in.prev_index);
        }
    }
    for(const auto& tx:txs){
        Hash256 txid{}; tx.ComputeTxId(txid, nullptr);
        for(size_t oi=0; oi<tx.outputs.size(); ++oi){
            const auto& o = tx.outputs[oi];
            std::string addr = address_encode(o.pubkey_hash);
            if(g_wallet.has_address(addr)){
                WalletUTXO wu;
                wu.txid = txid;
                wu.vout = (uint32_t)oi;
                wu.amount = o.amount;
                wu.output_type = o.type;
                wu.pkh = o.pubkey_hash;
                wu.height = height;
                wu.spent = false;
                g_wallet.add_utxo(wu);
            }
        }
    }

    // Remove confirmed/conflicting txs from mempool
    if(txs.size()>1){
        std::vector<Transaction> stdtxs(txs.begin()+1, txs.end());
        size_t removed = g_mempool.RemoveForBlock(stdtxs);
        if(removed>0) printf("[BLOCK] Mempool: %zu txs removed\n", removed);
    }

    printf("[BLOCK] Height %lld accepted: %s (txs=%zu, fees=%lld, UTXOs=%zu)\n",
           (long long)height, bid.substr(0,16).c_str(), txs.size(), (long long)total_fees, g_utxo_set.Size());

    // v0.3.2: Auto-save chain immediately after every accepted block
    if (!g_chain_path.empty()) {
        if (!save_chain_internal(g_chain_path)) {
            printf("[BLOCK] WARNING: chain auto-save failed!\n");
        }
    }

    return true;
}

// Process received tx (P2P relay path)
static bool process_tx(const std::string& hex_str) {
    std::vector<Byte> raw;
    if(!decode_tx_hex(hex_str, raw)) return false;
    Transaction tx; std::string err;
    if(!Transaction::Deserialize(raw, tx, &err)) return false;

    TxValidationContext ctx; ctx.genesis_hash=g_genesis_hash; ctx.spend_height=g_chain_height+1;
    int64_t now=(int64_t)time(nullptr);
    auto result=g_mempool.AcceptToMempool(tx,g_utxo_set,ctx,now);
    if(!result.accepted) return false;

    Hash256 txid{}; tx.ComputeTxId(txid,nullptr);
    printf("[P2P] TX accepted: %s\n", to_hex(txid.data(),32).substr(0,16).c_str());
    return true;
}

// Adaptive p2p send: use encryption if established, else plaintext
static bool p2p_send_adaptive(int fd, PeerCrypto& crypto, const char* cmd,
    const uint8_t* payload, size_t len) {
    if(crypto.encrypted)
        return p2p_send_encrypted(fd, crypto, cmd, payload, len);
    return p2p_send(fd, cmd, payload, len);
}

// Handle one peer connection
static void handle_peer(int fd, const std::string& addr, bool outbound) {
    {
        std::lock_guard<std::mutex> lk(g_peers_mu);
        Peer p; p.fd=fd; p.addr=addr; p.their_height=-1;
        p.version_sent=false; p.version_acked=false;
        p.outbound=outbound; p.last_seen=time(nullptr); p.ban_score=0;
        g_peers.push_back(p);
    }
    printf("[P2P] Peer connected: %s (%s)\n",addr.c_str(),outbound?"outbound":"inbound");

    // P2P encryption handshake
    PeerCrypto crypto{};
    if(g_p2p_enc != P2PEncMode::OFF){
        uint8_t our_priv[32], our_pub[32];
        if(x25519_keygen(our_priv, our_pub)){
            // Send our ephemeral public key
            p2p_send(fd, "EKEY", our_pub, 32);

            // Wait for their key (with timeout)
            struct timeval ht; ht.tv_sec=10; ht.tv_usec=0;
            setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &ht, sizeof(ht));

            P2PMsg ekey_msg;
            if(p2p_recv(fd, ekey_msg) && !strcmp(ekey_msg.cmd,"EKEY") && ekey_msg.payload.size()==32){
                uint8_t shared[32];
                if(x25519_derive(our_priv, ekey_msg.payload.data(), shared)){
                    derive_session_keys(shared, outbound, crypto.send_key, crypto.recv_key);
                    crypto.encrypted = true;
                    printf("[P2P] %s: encryption established (X25519+ChaCha20)\n", addr.c_str());
                }
                // Zero shared secret
                OPENSSL_cleanse(shared, 32);
            } else if(g_p2p_enc == P2PEncMode::REQUIRED){
                printf("[P2P] %s: encryption required but peer doesn't support it, dropping\n", addr.c_str());
                OPENSSL_cleanse(our_priv, 32);
                close(fd);
                std::lock_guard<std::mutex> lk(g_peers_mu);
                g_peers.erase(std::remove_if(g_peers.begin(),g_peers.end(),
                    [fd](const Peer& p){return p.fd==fd;}),g_peers.end());
                return;
            } else {
                printf("[P2P] %s: peer doesn't support encryption, falling back to plaintext\n", addr.c_str());
            }
            OPENSSL_cleanse(our_priv, 32);
        }
    }

    p2p_send_version(fd);

    struct timeval tv; tv.tv_sec=30; tv.tv_usec=0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    while(g_running) {
        P2PMsg msg;
        bool recv_ok;
        if(crypto.encrypted){
            recv_ok = p2p_recv_encrypted(fd, crypto, msg);
        } else {
            recv_ok = p2p_recv(fd, msg);
        }
        if(!recv_ok) break;

        // Handle EKEY during session (late encryption handshake from peer)
        if(!strcmp(msg.cmd,"EKEY") && !crypto.encrypted && g_p2p_enc != P2PEncMode::OFF){
            if(msg.payload.size()==32){
                uint8_t our_priv[32], our_pub[32];
                if(x25519_keygen(our_priv, our_pub)){
                    p2p_send(fd, "EKEY", our_pub, 32);
                    uint8_t shared[32];
                    if(x25519_derive(our_priv, msg.payload.data(), shared)){
                        derive_session_keys(shared, false, crypto.send_key, crypto.recv_key);
                        crypto.encrypted = true;
                        printf("[P2P] %s: late encryption established\n", addr.c_str());
                    }
                    OPENSSL_cleanse(shared, 32);
                    OPENSSL_cleanse(our_priv, 32);
                }
            }
            continue;
        }

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
                p2p_send_adaptive(fd, crypto, "VACK", nullptr, 0);
                printf("[P2P] %s: version OK, their height=%lld\n",addr.c_str(),(long long)their_h);

                if(their_h > g_chain_height){
                    uint8_t buf[8];
                    write_i64(buf, g_chain_height+1);
                    p2p_send_adaptive(fd, crypto, "GETB", buf, 8);
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
                    // p2p_send_block uses plaintext framing; for encrypted mode
                    // we'd need to refactor. Keep block sends plaintext-framed for now.
                    p2p_send_block(fd, h);
                }
                p2p_send_adaptive(fd, crypto, "DONE", nullptr, 0);
            }
        }
        else if(!strcmp(msg.cmd,"BLCK")) {
            std::string block_json((char*)msg.payload.data(), msg.payload.size());
            if(!process_block(block_json)){
                if(add_misbehavior(fd, addr, 50, "invalid block")) break;
            }
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
            } else {
                if(add_misbehavior(fd, addr, 10, "invalid tx")) break;
            }
        }
        else if(!strcmp(msg.cmd,"PING")) {
            p2p_send_adaptive(fd, crypto, "PONG", nullptr, 0);
        }
        else if(!strcmp(msg.cmd,"PONG")) {
            // no-op, just update last_seen (already done above)
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
                p2p_send_adaptive(fd, crypto, "GETB", buf, 8);
                printf("[P2P] Batch done, requesting from %lld\n",(long long)(g_chain_height+1));
            } else {
                printf("[P2P] Sync complete, height=%lld\n",(long long)g_chain_height);
            }
        }
        else {
            if(add_misbehavior(fd, addr, 10, "unknown command")) break;
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
    std::ifstream f(path); if(!f) return false;
    std::string json((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());

    std::string bid=jstr(json,"block_id"); if(bid.size()!=64) return false;
    std::string prev=jstr(json,"prev_hash"); if(prev.size()!=64) return false;
    std::string mr=jstr(json,"merkle_root"); if(mr.size()!=64) return false;

    StoredBlock g{};
    g.block_id=from_hex(bid);
    g.prev_hash=from_hex(prev);
    g.merkle_root=from_hex(mr);
    g.commit = from_hex(jstr(json,"commit"));
    g.checkpoints_root = from_hex(jstr(json,"checkpoints_root"));
    g.timestamp=jint(json,"timestamp");
    g.bits_q=(uint32_t)jint(json,"bits_q");
    g.nonce=(uint32_t)jint(json,"nonce");
    g.extra_nonce=(uint32_t)jint(json,"extra_nonce");
    g.height=0;
    g.subsidy=jint(json,"subsidy_stocks");
    g.stability_metric=juint(json,"stability_metric");

    auto sp=coinbase_split(g.subsidy);
    g.miner_reward=sp.miner;
    g.gold_vault_reward=sp.gold_vault;
    g.popc_pool_reward=sp.popc_pool;

    g_genesis_hash=g.block_id;
    g_blocks.push_back(g);
    g_chain_height=0;

    // TX-INDEX: genesis block coinbase (block_id used as pseudo-txid)
    g_tx_index[g.block_id] = {0, 0};

    // Add genesis coinbase-like UTXOs
    struct{const char*addr;int64_t amt;uint8_t type;}cb[3]={
        {ADDR_MINER_FOUNDER,sp.miner,OUT_COINBASE_MINER},
        {ADDR_GOLD_VAULT,sp.gold_vault,OUT_COINBASE_GOLD},
        {ADDR_POPC_POOL,sp.popc_pool,OUT_COINBASE_POPC},
    };
    for(int i=0;i<3;++i){
        PubKeyHash pkh{}; address_decode(cb[i].addr,pkh);
        OutPoint op; op.txid=g_genesis_hash; op.index=(uint32_t)i;
        UTXOEntry e; e.amount=cb[i].amt; e.type=cb[i].type; e.pubkey_hash=pkh; e.height=0; e.is_coinbase=true;
        e.payload_len=0; e.payload.clear();
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

    // We need to parse block objects that may contain nested arrays (transactions)
    // so use brace-matching instead of simple find('}')
    while(true){
        auto bs=json.find('{',search); if(bs==std::string::npos) break;

        // Brace-match to find the end of this block object
        size_t depth=1; size_t be=bs+1;
        bool in_str=false;
        while(be<json.size() && depth>0){
            char c=json[be];
            if(in_str){
                if(c=='"' && json[be-1]!='\\') in_str=false;
            } else {
                if(c=='"') in_str=true;
                else if(c=='{' || c=='[') depth++;
                else if(c=='}' || c==']') depth--;
            }
            if(depth>0) be++;
        }
        if(depth!=0) break;

        std::string bj=json.substr(bs,be-bs+1); search=be+1;

        std::string bid=jstr(bj,"block_id"); if(bid.size()!=64) continue;
        int64_t height=jint(bj,"height"); if(height==0) continue;

        // FIX #2: Validate chain continuity
        if(height != (int64_t)g_blocks.size()){
            printf("[CHAIN-LOAD] Warning: height gap at %lld (expected %zu), skipping\n",
                   (long long)height, g_blocks.size());
            continue;
        }

        StoredBlock sb{};
        sb.block_id=from_hex(bid);
        sb.prev_hash=from_hex(jstr(bj,"prev_hash"));

        // FIX #2: Verify prev_hash links
        if(!g_blocks.empty() && sb.prev_hash != g_blocks.back().block_id){
            printf("[CHAIN-LOAD] ERROR: prev_hash mismatch at height %lld, aborting chain load\n",
                   (long long)height);
            break;
        }

        std::string mr=jstr(bj,"merkle_root");
        sb.merkle_root = mr.size()==64 ? from_hex(mr) : Hash256{};
        std::string cm=jstr(bj,"commit"); sb.commit = cm.size()==64 ? from_hex(cm) : Hash256{};
        std::string cr=jstr(bj,"checkpoints_root"); sb.checkpoints_root = cr.size()==64 ? from_hex(cr) : Hash256{};
        sb.timestamp=jint(bj,"timestamp");
        sb.bits_q=(uint32_t)jint(bj,"bits_q");
        sb.nonce=(uint32_t)jint(bj,"nonce");
        sb.extra_nonce=(uint32_t)jint(bj,"extra_nonce");
        sb.height=height;
        sb.subsidy=jint(bj,"subsidy");
        sb.miner_reward=jint(bj,"miner");
        sb.gold_vault_reward=jint(bj,"gold_vault");
        sb.popc_pool_reward=jint(bj,"popc_pool");
        sb.stability_metric=juint(bj,"stability_metric");

        // Parse transactions if present (v0.3.2+)
        sb.tx_hexes = json_get_tx_hexes(bj);

        if (!sb.tx_hexes.empty()) {
            // FULL REPLAY: deserialize all TXs and connect to UTXO set
            std::vector<Transaction> txs;
            txs.reserve(sb.tx_hexes.size());
            bool tx_ok = true;

            for (const auto& hx : sb.tx_hexes) {
                std::vector<Byte> raw;
                if (!decode_tx_hex(hx, raw)) {
                    printf("[CHAIN-LOAD] Warning: bad tx hex at height %lld, falling back to coinbase-only\n",
                           (long long)height);
                    tx_ok = false;
                    break;
                }
                Transaction tx; std::string derr;
                if (!Transaction::Deserialize(raw, tx, &derr)) {
                    printf("[CHAIN-LOAD] Warning: tx deserialize failed at height %lld: %s\n",
                           (long long)height, derr.c_str());
                    tx_ok = false;
                    break;
                }
                txs.push_back(std::move(tx));
            }

            if (tx_ok && !txs.empty()) {
                // Use ConnectBlock to atomically update UTXO set
                BlockUndo undo;
                std::string uerr;
                if (g_utxo_set.ConnectBlock(txs, height, undo, &uerr)) {
                    // Also register wallet UTXOs
                    for (size_t ti = 1; ti < txs.size(); ++ti) {
                        for (const auto& in : txs[ti].inputs) {
                            g_wallet.mark_spent(in.prev_txid, in.prev_index);
                        }
                    }
                    for (const auto& tx : txs) {
                        Hash256 txid{}; tx.ComputeTxId(txid, nullptr);
                        for (size_t oi = 0; oi < tx.outputs.size(); ++oi) {
                            const auto& o = tx.outputs[oi];
                            std::string addr = address_encode(o.pubkey_hash);
                            if (g_wallet.has_address(addr)) {
                                WalletUTXO wu;
                                wu.txid = txid;
                                wu.vout = (uint32_t)oi;
                                wu.amount = o.amount;
                                wu.output_type = o.type;
                                wu.pkh = o.pubkey_hash;
                                wu.height = height;
                                wu.spent = false;
                                g_wallet.add_utxo(wu);
                            }
                        }
                    }
                    // TX-INDEX: index all txs from this block
                    for(size_t ti=0; ti<txs.size(); ++ti){
                        Hash256 txid_i{}; txs[ti].ComputeTxId(txid_i, nullptr);
                        g_tx_index[txid_i] = {height, (uint32_t)ti};
                    }
                    g_blocks.push_back(sb);
                    continue;  // skip the legacy coinbase-only path below
                } else {
                    printf("[CHAIN-LOAD] Warning: ConnectBlock failed at height %lld: %s (falling back)\n",
                           (long long)height, uerr.c_str());
                }
            }
        }

        // LEGACY fallback: no transactions field → reconstruct coinbase only
        g_tx_index[sb.block_id] = {height, 0};  // TX-INDEX: pseudo-index
        g_blocks.push_back(sb);
        struct{const char*a;int64_t v;uint8_t t;}cb[3]={
            {ADDR_MINER_FOUNDER,sb.miner_reward,OUT_COINBASE_MINER},
            {ADDR_GOLD_VAULT,sb.gold_vault_reward,OUT_COINBASE_GOLD},
            {ADDR_POPC_POOL,sb.popc_pool_reward,OUT_COINBASE_POPC},
        };
        for(int i=0;i<3;++i){
            PubKeyHash pkh{}; address_decode(cb[i].a,pkh);
            OutPoint op; op.txid=sb.block_id; op.index=(uint32_t)i;
            UTXOEntry e; e.amount=cb[i].v; e.type=cb[i].t; e.pubkey_hash=pkh; e.height=height; e.is_coinbase=true;
            e.payload_len=0; e.payload.clear();
            std::string err; g_utxo_set.AddUTXO(op,e,&err);
        }
    }

    g_chain_height = (int64_t)g_blocks.size() - 1;
    if(g_chain_height != ch){
        printf("[CHAIN-LOAD] Warning: JSON claimed height=%lld but loaded %lld blocks (using %lld)\n",
               (long long)ch, (long long)g_blocks.size(), (long long)g_chain_height);
    }
    return true;
}

// =============================================================================
// RPC Server Thread
// =============================================================================

static bool rpc_is_readonly_method(const std::string& body_json) {
    std::string m = json_get_string(body_json, "method");
    if (m.empty()) return false;

    static const std::set<std::string> kReadOnly = {
        "getinfo",
        "getblockcount",
        "getblockhash",
        "getblock",
        "getbestblockhash",
        "getmempoolinfo",
        "getrawmempool",
        "getrawtransaction",
        "getpeerinfo",
        "validateaddress",
        "gettxout",
        "getblocktemplate",
        "getaddressinfo",
        "gettransaction",
        "estimatefee",
        "getaddressbalance",
        "listbonds"
    };
    return kReadOnly.count(m) > 0;
}

static void rpc_handle_connection(int fd) {
    char buf[65536]{};
    ssize_t total=0;

    while(total<(ssize_t)sizeof(buf)-1){
        ssize_t n=read(fd,buf+total,sizeof(buf)-1-total);
        if(n<=0) break;
        total+=n; buf[total]=0;
        if(strstr(buf,"\r\n\r\n")) break;
    }
    if(total<=0){ close(fd); return; }

    std::string req(buf,total);

    // OPTIONS (CORS preflight) — no auth needed
    if(req.rfind("OPTIONS", 0) == 0){
        std::string resp=
            "HTTP/1.1 204 No Content\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: POST,GET,OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type,Authorization\r\n"
            "Access-Control-Max-Age: 86400\r\n"
            "Content-Length: 0\r\n\r\n";
        write_exact(fd,resp.c_str(),resp.size());
        close(fd);
        return;
    }

    // GET → getinfo (no auth, for quick status / explorer)
    if(req.rfind("GET", 0) == 0){
        auto result = dispatch_rpc("{\"method\":\"getinfo\",\"id\":1}");
        std::string resp =
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Headers: Content-Type,Authorization\r\n"
            "Content-Length: " + std::to_string(result.size()) + "\r\n\r\n" + result;
        write_exact(fd,resp.c_str(),resp.size());
        close(fd);
        return;
    }

    // Parse body (POST)
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
    } else {
        body=req;
    }

    // Auth gating: read-only without auth, state-changing requires auth
    bool readonly = rpc_is_readonly_method(body);

    if (!readonly) {
        if(!rpc_check_basic_auth(req)){
            rpc_reply_401(fd);
            close(fd);
            return;
        }
    }

    auto result=dispatch_rpc(body);

    std::string resp =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Access-Control-Allow-Headers: Content-Type,Authorization\r\n"
        "Access-Control-Max-Age: 86400\r\n"
        "Content-Length: " + std::to_string(result.size()) + "\r\n\r\n" + result;

    write_exact(fd,resp.c_str(),resp.size());
    close(fd);
}

static void rpc_server_thread(int port) {
    int srv=socket(AF_INET,SOCK_STREAM,0); if(srv<0){perror("rpc socket");return;}
    int opt=1; setsockopt(srv,SOL_SOCKET,SO_REUSEADDR,&opt,sizeof(opt));
    struct sockaddr_in addr{}; addr.sin_family=AF_INET;
    addr.sin_addr.s_addr = g_rpc_public ? INADDR_ANY : htonl(INADDR_LOOPBACK);
    addr.sin_port=htons(port);
    if(bind(srv,(struct sockaddr*)&addr,sizeof(addr))<0){perror("rpc bind");close(srv);return;}
    listen(srv,128);
    printf("[RPC] Listening on %s:%d — %zu methods (auth=%s)\n",
           g_rpc_public ? "0.0.0.0" : "127.0.0.1", port, g_handlers.size(),
           g_rpc_auth_required ? "ON" : "OFF");
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

        // DoS: reject banned IPs
        if (is_banned(ip)) {
            close(cl);
            continue;
        }

        // DoS: limit inbound peers (total + per-IP)
        {
            std::lock_guard<std::mutex> lk(g_peers_mu);
            int inbound_count = 0;
            int ip_count = 0;
            for (const auto& p : g_peers) {
                if (!p.outbound) ++inbound_count;
                if (p.addr.find(std::string(ip) + ":") == 0) ++ip_count;
            }
            if (inbound_count >= MAX_INBOUND_PEERS || ip_count >= MAX_PEERS_PER_IP) {
                close(cl);
                continue;
            }
        }

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
// Save chain (node local)
// =============================================================================

// v0.3.2: Internal save — caller MUST already hold g_chain_mu
static bool save_chain_internal(const std::string& path) {
    std::ofstream f(path); if (!f) return false;
    f << "{\n  \"chain_height\": " << g_chain_height
      << ",\n  \"tip\": \"" << to_hex(g_blocks.back().block_id.data(),32)
      << "\",\n  \"blocks\": [\n";
    for (size_t i = 0; i < g_blocks.size(); ++i) {
        const auto& b = g_blocks[i];
        f << "    {\"block_id\":\"" << to_hex(b.block_id.data(),32)
          << "\",\"prev_hash\":\"" << to_hex(b.prev_hash.data(),32)
          << "\",\"merkle_root\":\"" << to_hex(b.merkle_root.data(),32)
          << "\",\"commit\":\"" << to_hex(b.commit.data(),32)
          << "\",\"checkpoints_root\":\"" << to_hex(b.checkpoints_root.data(),32)
          << "\",\"height\":" << b.height
          << ",\"timestamp\":" << b.timestamp
          << ",\"bits_q\":" << b.bits_q
          << ",\"nonce\":" << b.nonce
          << ",\"extra_nonce\":" << b.extra_nonce
          << ",\"subsidy\":" << b.subsidy
          << ",\"miner\":" << b.miner_reward
          << ",\"gold_vault\":" << b.gold_vault_reward
          << ",\"popc_pool\":" << b.popc_pool_reward
          << ",\"stability_metric\":" << b.stability_metric;

        // WRITE TRANSACTIONS (v0.3.2 — critical for TX persistence)
        if (!b.tx_hexes.empty()) {
            f << ",\"transactions\":[";
            for (size_t t = 0; t < b.tx_hexes.size(); ++t) {
                if (t) f << ",";
                f << "\"" << b.tx_hexes[t] << "\"";
            }
            f << "]";
        }

        f << "}" << (i + 1 < g_blocks.size() ? ",\n" : "\n");
    }
    f << "  ]\n}\n";
    return f.good();
}

// Public save — acquires lock, then delegates to internal
static bool save_chain(const std::string& path) {
    std::lock_guard<std::mutex> lk(g_chain_mu);
    return save_chain_internal(path);
}

// =============================================================================
// main
// =============================================================================
int main(int argc, char** argv) {
    // =========================================================================
    // FIX #1: Set ACTIVE_PROFILE BEFORE anything that touches magic bytes.
    // Default to MAINNET. Can be overridden with --profile.
    // =========================================================================
    Profile selected_profile = Profile::MAINNET;

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
        else if(!strcmp(argv[i],"--rpc-user")&&i+1<argc) g_rpc_user=argv[++i];
        else if(!strcmp(argv[i],"--rpc-pass")&&i+1<argc) g_rpc_pass=argv[++i];
        else if(!strcmp(argv[i],"--rpc-noauth")) g_rpc_auth_required=false;
        else if(!strcmp(argv[i],"--rpc-public")) g_rpc_public=true;
        else if(!strcmp(argv[i],"--profile")&&i+1<argc){
            std::string pv=argv[++i];
            if(pv=="mainnet") selected_profile=Profile::MAINNET;
            else if(pv=="testnet") selected_profile=Profile::TESTNET;
            else if(pv=="dev") selected_profile=Profile::DEV;
            else { fprintf(stderr,"Error: unknown profile '%s' (use mainnet|testnet|dev)\n",pv.c_str()); return 1; }
        }
        else if(!strcmp(argv[i],"--p2p-enc")&&i+1<argc){
            std::string ev=argv[++i];
            if(ev=="off") g_p2p_enc=P2PEncMode::OFF;
            else if(ev=="on") g_p2p_enc=P2PEncMode::ON;
            else if(ev=="required") g_p2p_enc=P2PEncMode::REQUIRED;
            else { fprintf(stderr,"Error: --p2p-enc must be off|on|required\n"); return 1; }
        }
        else if(!strcmp(argv[i],"--full-verify")){
            g_full_verify_mode = true;
        }
        else if(!strcmp(argv[i],"--no-fast-sync")){
            g_full_verify_mode = true;
        }
        else if(!strcmp(argv[i],"--help")||!strcmp(argv[i],"-h")){
            printf("SOST Node v0.4.0\n");
            printf("  --wallet <path>            Wallet file (default: wallet.json)\n");
            printf("  --genesis <path>           Genesis JSON\n");
            printf("  --chain <path>             Chain JSON to load/save\n");
            printf("  --port <n>                 P2P port (default: 19333)\n");
            printf("  --rpc-port <n>             RPC port (default: 18232)\n");
            printf("  --connect <host:port>      Connect to peer\n");
            printf("  --rpc-user <u>             RPC Basic Auth user (required by default)\n");
            printf("  --rpc-pass <p>             RPC Basic Auth pass (required by default)\n");
            printf("  --rpc-noauth               Disable RPC auth (NOT recommended)\n");
            printf("  --rpc-public               Bind RPC to 0.0.0.0 (default: 127.0.0.1)\n");
            printf("  --profile mainnet|testnet|dev  Network profile (default: mainnet)\n");
            printf("  --p2p-enc off|on|required      P2P encryption mode (default: on)\n");
            printf("  --full-verify              Force full ConvergenceX verification (no fast sync)\n");
            printf("  --no-fast-sync             Same as --full-verify\n");
            return 0;
        }
    }

    // FIX #1: Apply profile AFTER parsing all args, BEFORE any crypto/chain ops
    ACTIVE_PROFILE = selected_profile;

    // v0.3.2: Set global chain path for auto-save in process_block
    g_chain_path = chain_path;

    const char* profile_name =
        ACTIVE_PROFILE==Profile::MAINNET ? "MAINNET" :
        ACTIVE_PROFILE==Profile::TESTNET ? "TESTNET" : "DEV";

    const char* enc_str = g_p2p_enc==P2PEncMode::OFF?"off":g_p2p_enc==P2PEncMode::ON?"on":"required";
    printf("=== SOST Node v0.4.0 ===\n");
    printf("Profile: %s | P2P: %d | RPC: %d | RPC auth: %s | P2P enc: %s | Fast sync: %s\n\n",
           profile_name, p2p_port, rpc_port,
           g_rpc_auth_required ? "ON" : "OFF", enc_str,
           g_full_verify_mode ? "OFF (--full-verify)" : "ON");

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

    // Wallet rescan from UTXO set
    {
        int rescan_count = 0;
        const auto& umap = g_utxo_set.GetMap();
        for (const auto& kv : umap) {
            const auto& op = kv.first;
            const auto& entry = kv.second;
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
        std::string werr;
        if (!g_wallet.save(g_wallet_path, &werr))
            printf("Warning: wallet save failed: %s\n", werr.c_str());
    }

    printf("UTXO set: %zu entries | Mempool: %zu txs\n\n",g_utxo_set.Size(),g_mempool.Size());

    std::thread rpc_thread(rpc_server_thread, rpc_port);
    rpc_thread.detach();

    std::thread p2p_thread(p2p_server_thread, p2p_port);
    p2p_thread.detach();

    // Default seed node (VPS) — used when no --connect is specified
    if(connect_addrs.empty()){
        printf("[P2P] No --connect specified, using default seed: seed.sostcore.com:%d\n", P2P_PORT_DEFAULT);
        connect_peer("seed.sostcore.com", P2P_PORT_DEFAULT);
    }
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
