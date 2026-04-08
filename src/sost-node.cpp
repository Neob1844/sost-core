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
#include "sost/popc.h"
#include "sost/popc_tx_builder.h"
#include "sost/popc_model_b.h"
#include "sost/proposals.h"

#include <fstream>
#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
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
#include <unordered_set>
#include <deque>
#include <mutex>
#include <memory>
#include <functional>
#include <ctime>
#include <atomic>
#include <thread>
#include <chrono>
#include <csignal>
#include <stdexcept>
#include <iomanip>

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
static PoPCRegistry g_popc_registry;
static std::string  g_popc_registry_path = "popc_registry.json";
static EscrowRegistry g_escrow_registry;
static std::string    g_escrow_registry_path = "escrow_registry.json";
static int32_t      g_last_accepted_profile = 0; // last block's declared cASERT profile index
static std::recursive_mutex g_chain_mu; // recursive: process_block→try_reorganize→process_block
static bool g_in_reorg = false;        // guard against recursive reorg

// RPC auth (fail-closed by default)
static std::string g_rpc_user = "";
static std::string g_rpc_pass = "";
static bool        g_rpc_auth_required = true;
static bool        g_rpc_public = false; // default: bind to 127.0.0.1 only

// Block record — stores everything needed for P2P relay and chain.json persistence
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
    Bytes32 cumulative_work{};   // best chain = highest cumulative valid work
    // Transcript V2 proof data (for P2P relay — complete verification by remote nodes)
    std::string segments_root_hex;
    std::vector<std::string> checkpoint_leaves_hex;
    // Declared stability profile (miner's profile for CX verification)
    int32_t stab_scale{0}, stab_k{0}, stab_margin{0}, stab_steps{0}, stab_lr_shift{0};
    // Raw JSON for the full block (includes segment_proofs, round_witnesses, etc.)
    // Stored once on acceptance, used for P2P relay and chain.json persistence.
    // This avoids re-serializing complex nested proof structures.
    std::string raw_block_json;
};
static std::vector<StoredBlock> g_blocks;

// === REORG INFRASTRUCTURE ===
// best chain = highest cumulative valid work (NOT longest chain by height)
// BlockUndo stored per accepted block for chain reorganization
static std::vector<BlockUndo> g_block_undos;

// Block index entry: tracks every known block (active, fork, orphan)
enum class BlockStatus : uint8_t {
    ACTIVE = 0,    // on the main chain
    FORK = 1,      // valid parent known, but not on active chain
    ORPHAN = 2,    // parent NOT known locally
    INVALID = 3    // failed validation
};

struct BlockIndexEntry {
    Hash256 block_id;
    Hash256 prev_hash;
    int64_t height;
    uint32_t bits_q;
    Bytes32 block_work;        // work for this single block
    Bytes32 cumulative_work;   // total chainwork up to and including this block
    BlockStatus status;
    std::string raw_json;      // original JSON for re-validation during reorg
    bool has_undo{false};
};

// Block index: every known block by hash
static std::map<std::string, BlockIndexEntry> g_block_index; // hash_hex -> entry
static std::mutex g_block_index_mu;

// Orphan blocks: blocks whose parent is not yet known
// Key: prev_hash_hex (so we can re-process when parent arrives)
static std::multimap<std::string, std::string> g_orphans_by_prev; // prev_hash_hex -> block_hash_hex
static const size_t MAX_ORPHAN_BLOCKS = 200;
static const size_t MAX_FORK_INDEX_ENTRIES = 1000;

// Forward declarations for reorg
static bool try_reorganize(const std::string& fork_tip_hash);
static void cleanup_old_forks();
static void broadcast_block_to_peers(const StoredBlock& sb, int exclude_fd = -1);
static void process_orphans_for_parent(const std::string& parent_hash_hex);

// P2P state
static const uint32_t P2P_MAGIC = 0x534F5354; // "SOST"
static const int P2P_PORT_DEFAULT = 19333;
static const int RPC_PORT_DEFAULT = 18232;
static std::atomic<bool> g_running{true};

// P2P encryption mode
enum class P2PEncMode { OFF, ON, REQUIRED };
static P2PEncMode g_p2p_enc = P2PEncMode::OFF;

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
    std::shared_ptr<std::mutex> write_mu{std::make_shared<std::mutex>()}; // per-fd write serialization
};
static std::vector<Peer> g_peers;
static std::mutex g_peers_mu;

// Get per-fd write mutex (returns nullptr if peer not found)
static std::shared_ptr<std::mutex> get_peer_write_mu(int fd) {
    std::lock_guard<std::mutex> lk(g_peers_mu);
    for (auto& p : g_peers) {
        if (p.fd == fd) return p.write_mu;
    }
    return nullptr;
}

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
static bool g_verbose = false;  // --verbose: show CX-VERIFY and PARSE debug output

// Known blocks: blocks we've already accepted or stored as fork/orphan.
// Used to silently ignore re-broadcast of blocks we already know about.
// This prevents penalizing peers for normal relay behavior.
static std::unordered_set<std::string> g_known_blocks; // block_id hex
static std::deque<std::string> g_known_blocks_order;   // FIFO for pruning
static const size_t MAX_KNOWN_BLOCKS = 50000;
static std::mutex g_known_mu;

// Add block hash to known set with FIFO pruning
static void mark_block_known(const std::string& hash) {
    std::lock_guard<std::mutex> lk(g_known_mu);
    if (g_known_blocks.count(hash)) return;
    g_known_blocks.insert(hash);
    g_known_blocks_order.push_back(hash);
    while (g_known_blocks.size() > MAX_KNOWN_BLOCKS) {
        g_known_blocks.erase(g_known_blocks_order.front());
        g_known_blocks_order.pop_front();
    }
}

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

// Rate limiting per peer (blocks per minute)
struct PeerRateLimit {
    std::vector<time_t> block_timestamps; // timestamps of received blocks
    bool syncing{false};                  // true during initial sync (relaxed limits)
};
static std::map<int, PeerRateLimit> g_peer_rates; // fd -> rate state
static std::mutex g_rate_mu;
static const int STEADY_STATE_BLOCKS_PER_MIN = 50;
static const int SYNC_MODE_BLOCKS_PER_MIN = 5000;  // effectively unlimited during sync

static bool check_block_rate(int fd, bool is_syncing) {
    std::lock_guard<std::mutex> lk(g_rate_mu);
    auto& rl = g_peer_rates[fd];
    rl.syncing = is_syncing;
    time_t now = time(nullptr);
    // Remove entries older than 60 seconds
    while (!rl.block_timestamps.empty() && (now - rl.block_timestamps.front()) > 60)
        rl.block_timestamps.erase(rl.block_timestamps.begin());
    int limit = rl.syncing ? SYNC_MODE_BLOCKS_PER_MIN : STEADY_STATE_BLOCKS_PER_MIN;
    if ((int)rl.block_timestamps.size() >= limit) return false;
    rl.block_timestamps.push_back(now);
    return true;
}

static void cleanup_peer_rate(int fd) {
    std::lock_guard<std::mutex> lk(g_rate_mu);
    g_peer_rates.erase(fd);
}

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
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    return rpc_result(id, std::to_string(g_chain_height));
}

static std::string handle_getblockhash(const std::string& id, const std::vector<std::string>& p) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    if(p.empty()) return rpc_error(id,-1,"missing height");
    int64_t h=std::stoll(p[0]);
    if(h<0||h>=(int64_t)g_blocks.size()) return rpc_error(id,-8,"Block height out of range");
    return rpc_result(id,"\""+to_hex(g_blocks[h].block_id.data(),32)+"\"");
}

static std::string handle_getblock(const std::string& id, const std::vector<std::string>& p) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
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
            // Profile for THIS block (with anti-stall, using block's own timestamp)
            auto cd=casert_compute(meta,b.height,b.timestamp);
            // Base profile (no anti-stall) for reference
            auto cd_base=casert_compute(meta,b.height,0);
            s<<",\"casert_mode\":\""<<casert_profile_name(cd.profile_index)
             <<"\",\"casert_base\":\""<<casert_profile_name(cd_base.profile_index)
             <<"\",\"casert_signal\":"<<cd.lag<<"}";
            return rpc_result(id,s.str());
        }
    }
    return rpc_error(id,-5,"Block not found");
}

static std::string handle_getinfo(const std::string& id, const std::vector<std::string>&) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    size_t peers_count;
    { std::lock_guard<std::mutex> lk2(g_peers_mu); peers_count=g_peers.size(); }

    // Show which profile is active so operator can verify at a glance
    const char* profile_str = "unknown";
    if(ACTIVE_PROFILE == Profile::MAINNET) profile_str = "mainnet";
    else if(ACTIVE_PROFILE == Profile::TESTNET) profile_str = "testnet";
    else if(ACTIVE_PROFILE == Profile::DEV) profile_str = "dev";

    std::ostringstream s;
    // Compute next block difficulty + cASERT profile
    uint32_t next_diff = GENESIS_BITSQ;
    int32_t casert_profile_idx = 0;
    int32_t casert_lag = 0;
    if (!g_blocks.empty()) {
        std::vector<BlockMeta> meta;
        for (const auto& b : g_blocks) { BlockMeta bm; bm.block_id=b.block_id; bm.height=b.height; bm.time=b.timestamp; bm.powDiffQ=b.bits_q; meta.push_back(bm); }
        next_diff = sost::casert_next_bitsq(meta, (int64_t)g_blocks.size());
        // Compute live profile with current wall-clock time (includes anti-stall easing)
        auto dec = sost::casert_compute(meta, (int64_t)g_blocks.size(), std::time(nullptr));
        casert_profile_idx = dec.profile_index;
        casert_lag = dec.lag;
    }
    // Profile name from index
    static const char* PROF_NAMES[] = {"E4","E3","E2","E1","B0","H1","H2","H3","H4","H5","H6","H7","H8","H9","H10","H11","H12"};
    int prof_arr_idx = std::max(0, std::min(16, casert_profile_idx - CASERT_H_MIN));
    s<<"{\"version\":\"0.3.2\",\"protocolversion\":1,\"blocks\":"<<g_chain_height
     <<",\"connections\":"<<peers_count
     <<",\"difficulty\":"<<(g_blocks.empty()?0:g_blocks.back().bits_q)
     <<",\"next_difficulty\":"<<next_diff
     <<",\"casert_profile\":\""<<PROF_NAMES[prof_arr_idx]<<"\""
     <<",\"casert_profile_index\":"<<casert_profile_idx
     <<",\"casert_lag\":"<<casert_lag
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
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
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

    // -------------------------------------------------------------------------
    // Gold Vault policy protection (not consensus — policy only)
    // Detects and logs any TX that attempts to spend from the Gold Vault address.
    // Currently WARNING only — does not block acceptance.
    // To enable blocking: set a config flag and return rpc_error here instead.
    // -------------------------------------------------------------------------
    {
        PubKeyHash gold_vault_pkh{};
        address_decode(ADDR_GOLD_VAULT, gold_vault_pkh);
        for (const auto& txin : tx.inputs) {
            OutPoint op{txin.prev_txid, txin.prev_index};
            auto utxo = g_utxo_set.GetUTXO(op);
            if (utxo && utxo->pubkey_hash == gold_vault_pkh) {
                // Log a critical alert — Gold Vault is being spent
                printf("[GOLD-VAULT-ALERT] TX spending from Gold Vault detected! txid=%s amount=%lld stocks\n",
                       to_hex(txid.data(), 32).c_str(), (long long)utxo->amount);
                // NOTE: blocking can be enabled here later via a config flag,
                // e.g. return rpc_error(id,-403,"Gold Vault spend blocked by policy");
            }
        }
    }

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
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    auto tmpl = g_mempool.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, NODE_MAX_BLOCK_TX_BYTES);

    // Compute next block info
    int64_t next_height = g_chain_height + 1;
    std::string prev_hash = g_blocks.empty() ? std::string(64, '0') : to_hex(g_blocks.back().block_id.data(), 32);
    uint32_t next_bits = GENESIS_BITSQ;
    if (!g_blocks.empty()) {
        std::vector<BlockMeta> meta;
        for (const auto& b : g_blocks) { BlockMeta bm; bm.block_id=b.block_id; bm.height=b.height; bm.time=b.timestamp; bm.powDiffQ=b.bits_q; meta.push_back(bm); }
        next_bits = sost::casert_next_bitsq(meta, next_height);
    }
    int64_t curtime = (int64_t)time(nullptr);
    int64_t subsidy = sost_subsidy_stocks(next_height);

    std::ostringstream s;
    s << "{\"height\":" << next_height
      << ",\"previousblockhash\":\"" << prev_hash << "\""
      << ",\"bits\":" << next_bits
      << ",\"difficulty\":" << next_bits
      << ",\"curtime\":" << curtime
      << ",\"coinbasevalue\":" << subsidy
      << ",\"transactions\":[";
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
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
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

static std::string handle_getaddressutxos(const std::string& id, const std::vector<std::string>& p) {
    if(p.empty()) return rpc_error(id,-1,"missing address");
    std::string addr = p[0];
    if(!address_valid(addr)) return rpc_error(id,-8,"invalid address");

    PubKeyHash pkh{};
    address_decode(addr, pkh);

    std::ostringstream s;
    s << "[";
    bool first = true;
    const auto& umap = g_utxo_set.GetMap();
    for(const auto& kv : umap){
        if(kv.second.pubkey_hash == pkh){
            if(!first) s << ",";
            first = false;
            bool mature = !kv.second.is_coinbase ||
                          (g_chain_height - kv.second.height) >= COINBASE_MATURITY;
            bool isLocked = (kv.second.type==0x10||kv.second.type==0x11);  // bond/escrow types
            s << "{\"txid\":\"" << to_hex(kv.first.txid.data(),32)
              << "\",\"vout\":" << kv.first.index
              << ",\"amount\":" << format_sost(kv.second.amount)
              << ",\"amount_stocks\":" << kv.second.amount
              << ",\"height\":" << kv.second.height
              << ",\"confirmations\":" << (g_chain_height - kv.second.height + 1)
              << ",\"output_type\":" << (int)kv.second.type
              << ",\"coinbase\":" << (kv.second.is_coinbase ? "true" : "false")
              << ",\"mature\":" << (mature ? "true" : "false")
              << ",\"spendable\":" << (!isLocked && mature ? "true" : "false")
              << "}";
        }
    }
    s << "]";
    return rpc_result(id, s.str());
}

static std::string handle_getaddressinfo(const std::string& id, const std::vector<std::string>& p) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
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

// listtransfers: return blocks that contain non-coinbase transactions (transfers)
// Scans the entire chain once and returns transfer TXIDs with block heights.
// Efficient: only checks tx_hexes.size() > 1 per block (O(n) where n = chain height).
static std::string handle_listtransfers(const std::string& id, const std::vector<std::string>& p) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    int limit = 50;
    if (!p.empty()) { try { limit = std::stoi(p[0]); } catch(...) {} }
    if (limit < 1) limit = 1;
    if (limit > 200) limit = 200;

    std::ostringstream s;
    s << "[";
    int count = 0;
    // Scan from tip backwards
    for (int64_t h = g_chain_height; h >= 0 && count < limit; --h) {
        if (h >= (int64_t)g_blocks.size()) continue;
        const auto& blk = g_blocks[h];
        if (blk.tx_hexes.size() <= 1) continue; // only coinbase — skip

        // This block has transfers
        for (size_t t = 1; t < blk.tx_hexes.size() && count < limit; ++t) {
            // Decode TX to get basic info
            std::vector<Byte> raw;
            if (!decode_tx_hex(blk.tx_hexes[t], raw)) continue;
            Transaction tx; std::string err;
            if (!Transaction::Deserialize(raw, tx, &err)) continue;

            Hash256 txid;
            if (!tx.ComputeTxId(txid, &err)) continue;

            // Compute fee via tx-index
            int64_t sum_in = 0, sum_out = 0;
            for (const auto& o : tx.outputs) sum_out += o.amount;
            for (const auto& in : tx.inputs) {
                auto iit = g_tx_index.find(in.prev_txid);
                if (iit != g_tx_index.end()) {
                    int64_t ibh = iit->second.block_height;
                    uint32_t itpos = iit->second.tx_pos;
                    if (ibh < (int64_t)g_blocks.size() && itpos < g_blocks[ibh].tx_hexes.size()) {
                        std::vector<Byte> iraw;
                        if (decode_tx_hex(g_blocks[ibh].tx_hexes[itpos], iraw)) {
                            Transaction itx; std::string ie;
                            if (Transaction::Deserialize(iraw, itx, &ie) && in.prev_index < itx.outputs.size()) {
                                sum_in += itx.outputs[in.prev_index].amount;
                            }
                        }
                    }
                }
            }
            int64_t fee = sum_in > sum_out ? sum_in - sum_out : 0;

            if (count > 0) s << ",";
            s << "{\"txid\":\"" << to_hex(txid.data(), 32)
              << "\",\"height\":" << h
              << ",\"inputs\":" << tx.inputs.size()
              << ",\"outputs\":" << tx.outputs.size()
              << ",\"total_output\":" << sum_out
              << ",\"fee\":" << fee
              << ",\"size\":" << raw.size() << "}";
            count++;
        }
    }
    s << "]";
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

// =============================================================================
// PoPC RPC Handlers (application-layer, no consensus changes)
// =============================================================================

// Duration in blocks: approximately 30 days per month at 10 min/block
static int64_t popc_duration_to_blocks(uint16_t months) {
    // 144 blocks/day * 30 days/month * months
    return (int64_t)144 * 30 * (int64_t)months;
}

// load_popc_pricing
// Reads config/popc_pricing.json and returns sost_per_usd and gold_price_usd_per_oz.
// Falls back to defaults (sost_per_usd=1.0, gold_price=3000.0) if file is missing or malformed.
static void load_popc_pricing(double& sost_per_usd, double& gold_price_usd) {
    sost_per_usd  = 1.0;
    gold_price_usd = 3000.0;

    std::ifstream f("config/popc_pricing.json");
    if (!f.is_open()) return;

    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());

    // Extract sost_per_usd
    std::string sv = json_get_string(content, "sost_per_usd");
    if (!sv.empty()) {
        double v = std::strtod(sv.c_str(), nullptr);
        if (v > 0.0) sost_per_usd = v;
    }

    // Extract gold_price_usd_per_oz
    std::string gv = json_get_string(content, "gold_price_usd_per_oz");
    if (!gv.empty()) {
        double v = std::strtod(gv.c_str(), nullptr);
        if (v > 0.0) gold_price_usd = v;
    }
}

// handle_popc_register
// Params: [sost_address, eth_address, gold_token, gold_amount_mg, commitment_months]
static std::string handle_popc_register(const std::string& id, const std::vector<std::string>& p) {
    if (p.size() < 5) return rpc_error(id, -1, "usage: popc_register <sost_address> <eth_address> <gold_token> <gold_amount_mg> <commitment_months>");

    const std::string& sost_addr      = p[0];
    const std::string& eth_addr       = p[1];
    const std::string& gold_token     = p[2];
    int64_t gold_amount_mg            = (int64_t)std::stoll(p[3]);
    uint16_t commitment_months        = (uint16_t)std::stoul(p[4]);

    // Validate SOST address
    PubKeyHash user_pkh{};
    if (!address_decode(sost_addr, user_pkh))
        return rpc_error(id, -1, "invalid sost_address");

    // Validate gold token
    if (gold_token != "XAUT" && gold_token != "PAXG")
        return rpc_error(id, -1, "gold_token must be 'XAUT' or 'PAXG'");

    // Validate amount
    if (gold_amount_mg <= 0)
        return rpc_error(id, -1, "gold_amount_mg must be > 0");

    // Validate duration
    uint16_t reward_pct_bps = compute_reward_pct(commitment_months);
    if (reward_pct_bps == 0)
        return rpc_error(id, -1, "commitment_months must be 1, 3, 6, 9, or 12");

    // Compute commitment_id = SHA256(eth_address || sost_address || gold_token || commitment_months)
    Hash256 commitment_id{};
    {
        std::string canon = eth_addr + sost_addr + gold_token + std::to_string((int)commitment_months);
        unsigned int digest_len = 32;
        EVP_Digest(canon.data(), canon.size(),
                   commitment_id.data(), &digest_len,
                   EVP_sha256(), nullptr);
    }

    int64_t current_height;
    {
        std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
        current_height = g_chain_height;
    }

    // Load pricing from config/popc_pricing.json (with fallback defaults)
    double sost_per_usd   = 1.0;
    double gold_price_usd = 3000.0;
    load_popc_pricing(sost_per_usd, gold_price_usd);

    // --- Bond calculation (all integer arithmetic, no floats in final values) ---
    // Prices in micro-USD to preserve precision
    int64_t gold_price_micro = (int64_t)(gold_price_usd * 1000000.0); // e.g. 3000 * 1M = 3_000_000_000
    int64_t sost_price_micro = (int64_t)(sost_per_usd  * 1000000.0); // e.g. 1 * 1M = 1_000_000
    if (gold_price_micro <= 0) gold_price_micro = 3000000000LL;
    if (sost_price_micro <= 0) sost_price_micro = 1000000LL;

    // Gold value in micro-USD: (gold_mg * gold_price_per_oz_micro) / 31103
    // 1 troy oz = 31.103 g = 31103 mg
    int64_t gold_value_micro = (gold_amount_mg * gold_price_micro) / 31103;

    // Bond ratio for compute_bond_pct: (sost_price / gold_price) * 10000
    uint64_t ratio_bps = (uint64_t)((sost_price_micro * (int64_t)10000) / gold_price_micro);

    uint16_t bond_pct_bps = compute_bond_pct(ratio_bps);

    // Bond in micro-USD
    int64_t bond_micro = (gold_value_micro * (int64_t)bond_pct_bps) / 10000;

    // Bond in stocks: (bond_micro / sost_price_micro) * STOCKS_PER_SOST
    int64_t bond_sost_stocks = (bond_micro * (int64_t)STOCKS_PER_SOST) / sost_price_micro;
    if (bond_sost_stocks <= 0) bond_sost_stocks = 1; // minimum 1 stock

    // --- Anti-whale check ---
    uint16_t whale_mult = whale_tier_multiplier(gold_amount_mg);
    if (whale_mult == 0)
        return rpc_error(id, -1, "gold_amount_mg exceeds hard cap (>200 oz / 6,220,700 mg)");

    // --- Pool balance scan for PUR ---
    int64_t pool_balance = 0;
    {
        PubKeyHash popc_pkh_reg{};
        address_decode(ADDR_POPC_POOL, popc_pkh_reg);
        std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
        const auto& umap = g_utxo_set.GetMap();
        for (const auto& kv : umap) {
            if (kv.second.pubkey_hash == popc_pkh_reg)
                pool_balance += kv.second.amount;
        }
    }

    int32_t pur = compute_pur_bps(g_popc_registry.committed_rewards(), pool_balance);
    if (pur >= PUR_CLOSED_BPS)
        return rpc_error(id, -1, "Pool fully committed (PUR=100%). No new registrations accepted.");

    int32_t factor = compute_dynamic_factor_bps(pur);
    uint16_t dyn_rate = apply_dynamic_reward(reward_pct_bps, factor, POPC_REWARD_FLOOR_A_BPS);
    // Apply whale multiplier
    dyn_rate = (uint16_t)(((int64_t)dyn_rate * (int64_t)whale_mult) / 10000);
    if (dyn_rate < POPC_REWARD_FLOOR_A_BPS) dyn_rate = POPC_REWARD_FLOOR_A_BPS;

    // --- Reward calculation (using dynamic rate) ---
    int64_t reward_stocks = calculate_reward_stocks(bond_sost_stocks, dyn_rate);
    int64_t net_reward    = reward_stocks - (reward_stocks * (int64_t)POPC_PROTOCOL_FEE_BPS / 10000);
    int64_t total_return  = bond_sost_stocks + net_reward;

    // Gold value in USD (formatted as string, 2 decimal places)
    // gold_value_micro / 1_000_000 = USD
    char gold_usd_buf[64];
    snprintf(gold_usd_buf, sizeof(gold_usd_buf), "%lld.%02lld",
             (long long)(gold_value_micro / 1000000LL),
             (long long)((gold_value_micro % 1000000LL) / 10000LL));

    // Determine whale tier label
    const char* whale_tier_label = "T1_FULL";
    if (whale_mult == WHALE_MULT_T2) whale_tier_label = "T2_75PCT";
    else if (whale_mult == WHALE_MULT_T3) whale_tier_label = "T3_50PCT";

    // Store live prices in commitment (store dynamic rate in reward_pct_bps)
    PoPCCommitment c{};
    c.commitment_id        = commitment_id;
    c.user_pkh             = user_pkh;
    c.eth_wallet           = eth_addr;
    c.gold_token           = gold_token;
    c.gold_amount_mg       = gold_amount_mg;
    c.bond_sost_stocks     = bond_sost_stocks;
    c.duration_months      = commitment_months;
    c.start_height         = current_height;
    c.end_height           = current_height + popc_duration_to_blocks(commitment_months);
    c.bond_pct_bps         = bond_pct_bps;
    c.reward_pct_bps       = dyn_rate;
    c.status               = PoPCStatus::ACTIVE;
    c.sost_price_usd_micro = sost_price_micro;
    c.gold_price_usd_micro = gold_price_micro;

    std::string reg_err;
    if (!g_popc_registry.register_commitment(c, &reg_err))
        return rpc_error(id, -1, "register_commitment failed: " + reg_err);

    // Reserve committed rewards for PUR tracking
    g_popc_registry.add_committed(net_reward);

    // Save registry to disk
    std::string save_err;
    g_popc_registry.save(g_popc_registry_path, &save_err); // best-effort

    // Format commitment_id as hex
    char cid_hex[65]; cid_hex[64] = 0;
    static const char HEX[] = "0123456789abcdef";
    for (int i = 0; i < 32; ++i) {
        cid_hex[i*2]   = HEX[commitment_id[i] >> 4];
        cid_hex[i*2+1] = HEX[commitment_id[i] & 0x0F];
    }

    int32_t pur_pct         = pur / 100;
    int32_t factor_pct      = factor / 100;

    std::ostringstream s;
    s << "{"
      << "\"commitment_id\":\"" << cid_hex << "\""
      << ",\"declared_gold_mg\":" << gold_amount_mg
      << ",\"gold_value_usd\":\"" << gold_usd_buf << "\""
      << ",\"bond_percentage\":" << (int)bond_pct_bps
      << ",\"bond_required_sost\":\"" << format_sost(bond_sost_stocks) << "\""
      << ",\"base_reward_pct_bps\":" << (int)reward_pct_bps
      << ",\"pur_pct\":" << pur_pct
      << ",\"dynamic_factor_pct\":" << factor_pct
      << ",\"effective_rate_bps\":" << (int)dyn_rate
      << ",\"whale_tier\":\"" << whale_tier_label << "\""
      << ",\"expected_reward_sost\":\"" << format_sost(net_reward) << "\""
      << ",\"total_return_sost\":\"" << format_sost(total_return) << "\""
      << ",\"commitment_blocks\":" << popc_duration_to_blocks(commitment_months)
      << ",\"commitment_months\":" << (int)commitment_months
      << ",\"expires_at_height\":" << c.end_height;
    if (pur >= PUR_WARNING_BPS)
        s << ",\"warning\":\"Pool utilization above 80% — reward rate reduced\"";
    s << ",\"message\":\"Bond required before PoPC Pool releases reward. Operator verifies gold custody before release.\""
      << "}";
    return rpc_result(id, s.str());
}

// handle_popc_status
// Returns PoPC registry summary: active count, total bonded, PoPC Pool balance.
static std::string handle_popc_status(const std::string& id, const std::vector<std::string>&) {
    size_t active_count  = g_popc_registry.active_count();
    int64_t total_bonded = g_popc_registry.total_bonded_stocks();

    // Scan UTXO set for PoPC Pool balance
    PubKeyHash popc_pkh{};
    address_decode(ADDR_POPC_POOL, popc_pkh);

    int64_t pool_balance = 0;
    {
        std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
        const auto& umap = g_utxo_set.GetMap();
        for (const auto& kv : umap) {
            if (kv.second.pubkey_hash == popc_pkh) {
                pool_balance += kv.second.amount;
            }
        }
    }

    auto active = g_popc_registry.list_active();
    std::ostringstream arr;
    arr << "[";
    for (size_t i = 0; i < active.size(); ++i) {
        if (i) arr << ",";
        const auto& c = active[i];
        static const char HEX[] = "0123456789abcdef";
        char cid_hex[65]; cid_hex[64] = 0;
        for (int j = 0; j < 32; ++j) {
            cid_hex[j*2]   = HEX[c.commitment_id[j] >> 4];
            cid_hex[j*2+1] = HEX[c.commitment_id[j] & 0x0F];
        }
        arr << "{"
            << "\"commitment_id\":\"" << cid_hex << "\""
            << ",\"eth_address\":\"" << json_escape(c.eth_wallet) << "\""
            << ",\"gold_token\":\"" << json_escape(c.gold_token) << "\""
            << ",\"gold_amount_mg\":" << c.gold_amount_mg
            << ",\"bond\":\"" << format_sost(c.bond_sost_stocks) << "\""
            << ",\"duration_months\":" << (int)c.duration_months
            << ",\"start_height\":" << c.start_height
            << ",\"end_height\":" << c.end_height
            << "}";
    }
    arr << "]";

    int64_t committed_rwd = g_popc_registry.committed_rewards();
    int32_t pur_status    = compute_pur_bps(committed_rwd, pool_balance);
    int32_t dyn_factor    = compute_dynamic_factor_bps(pur_status);
    int32_t pur_pct       = pur_status / 100;
    int32_t factor_pct    = dyn_factor / 100;

    std::ostringstream s;
    s << "{"
      << "\"active_count\":" << active_count
      << ",\"total_bonded\":\"" << format_sost(total_bonded) << "\""
      << ",\"pool_balance\":\"" << format_sost(pool_balance) << "\""
      << ",\"committed_rewards\":\"" << format_sost(committed_rwd) << "\""
      << ",\"pur_pct\":" << pur_pct
      << ",\"dynamic_factor_pct\":" << factor_pct
      << ",\"commitments\":" << arr.str()
      << "}";
    return rpc_result(id, s.str());
}

// handle_popc_check
// Params: [eth_address]
// Returns instructions to run the Python-side Etherscan checker.
// Full Etherscan integration is Python-side, not C++.
static std::string handle_popc_check(const std::string& id, const std::vector<std::string>& p) {
    if (p.empty()) return rpc_error(id, -1, "usage: popc_check <eth_address>");
    const std::string& eth_addr = p[0];

    std::ostringstream s;
    s << "{"
      << "\"eth_address\":\"" << json_escape(eth_addr) << "\""
      << ",\"status\":\"MANUAL_CHECK_REQUIRED\""
      << ",\"message\":\"Run: python3 scripts/popc_etherscan_checker.py check " << json_escape(eth_addr) << "\""
      << "}";
    return rpc_result(id, s.str());
}

// handle_popc_release
// Params: [commitment_id_hex]
// Marks a completed commitment as COMPLETED and returns reward info.
static std::string handle_popc_release(const std::string& id, const std::vector<std::string>& p) {
    if (p.empty()) return rpc_error(id, -1, "usage: popc_release <commitment_id_hex>");

    const std::string& cid_hex = p[0];
    if (cid_hex.size() != 64) return rpc_error(id, -1, "commitment_id must be 64 hex chars");

    // Decode commitment_id from hex
    Hash256 commitment_id{};
    for (size_t i = 0; i < 32; ++i) {
        auto h = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return 10 + c - 'a';
            if (c >= 'A' && c <= 'F') return 10 + c - 'A';
            return -1;
        };
        int hi = h(cid_hex[i*2]);
        int lo = h(cid_hex[i*2+1]);
        if (hi < 0 || lo < 0) return rpc_error(id, -1, "invalid hex in commitment_id");
        commitment_id[i] = (uint8_t)((hi << 4) | lo);
    }

    int64_t current_height;
    {
        std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
        current_height = g_chain_height;
    }

    const PoPCCommitment* c = g_popc_registry.find(commitment_id);
    if (!c) return rpc_error(id, -1, "commitment_id not found");
    if (c->status != PoPCStatus::ACTIVE) return rpc_error(id, -1, "commitment is not ACTIVE");
    if (current_height < c->end_height)
        return rpc_error(id, -1, "commitment has not expired yet (end_height=" +
                         std::to_string(c->end_height) + ", current_height=" +
                         std::to_string(current_height) + ")");

    int64_t reward = calculate_reward_stocks(c->bond_sost_stocks, c->reward_pct_bps);
    int64_t net_reward_release = reward - (reward * (int64_t)POPC_PROTOCOL_FEE_BPS / 10000);

    // Mark as COMPLETED
    std::string comp_err;
    if (!g_popc_registry.complete(commitment_id, &comp_err))
        return rpc_error(id, -1, "complete failed: " + comp_err);

    // Release committed rewards from PUR tracking
    g_popc_registry.release_committed(net_reward_release);

    // Save registry
    g_popc_registry.save(g_popc_registry_path, nullptr);

    std::ostringstream s;
    s << "{"
      << "\"commitment_id\":\"" << json_escape(cid_hex) << "\""
      << ",\"status\":\"COMPLETED\""
      << ",\"bond\":\"" << format_sost(c->bond_sost_stocks) << "\""
      << ",\"reward_pct_bps\":" << (int)c->reward_pct_bps
      << ",\"reward_amount\":\"" << format_sost(net_reward_release) << "\""
      << ",\"instructions\":\"Broadcast a reward TX from the PoPC Pool to the user's SOST address using build_reward_tx()\""
      << "}";
    return rpc_result(id, s.str());
}

// handle_popc_slash
// Params: [commitment_id_hex, reason]
// Marks a commitment as SLASHED in the registry.
static std::string handle_popc_slash(const std::string& id, const std::vector<std::string>& p) {
    if (p.size() < 2) return rpc_error(id, -1, "usage: popc_slash <commitment_id_hex> <reason>");

    const std::string& cid_hex = p[0];
    const std::string& reason  = p[1];
    if (cid_hex.size() != 64) return rpc_error(id, -1, "commitment_id must be 64 hex chars");

    // Decode commitment_id from hex
    Hash256 commitment_id{};
    for (size_t i = 0; i < 32; ++i) {
        auto h = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return 10 + c - 'a';
            if (c >= 'A' && c <= 'F') return 10 + c - 'A';
            return -1;
        };
        int hi = h(cid_hex[i*2]);
        int lo = h(cid_hex[i*2+1]);
        if (hi < 0 || lo < 0) return rpc_error(id, -1, "invalid hex in commitment_id");
        commitment_id[i] = (uint8_t)((hi << 4) | lo);
    }

    const PoPCCommitment* c = g_popc_registry.find(commitment_id);
    if (!c) return rpc_error(id, -1, "commitment_id not found");
    if (c->status != PoPCStatus::ACTIVE) return rpc_error(id, -1, "commitment is not ACTIVE");

    // Capture reward amount before slash (for committed release)
    int64_t slash_reward = calculate_reward_stocks(c->bond_sost_stocks, c->reward_pct_bps);
    int64_t slash_net_reward = slash_reward - (slash_reward * (int64_t)POPC_PROTOCOL_FEE_BPS / 10000);

    std::string slash_err;
    if (!build_slash_marker(g_popc_registry, commitment_id, reason, &slash_err))
        return rpc_error(id, -1, "slash failed: " + slash_err);

    // Release committed rewards from PUR tracking (slashed rewards are not paid)
    g_popc_registry.release_committed(slash_net_reward);

    // Save registry
    g_popc_registry.save(g_popc_registry_path, nullptr);

    std::ostringstream s;
    s << "{"
      << "\"commitment_id\":\"" << json_escape(cid_hex) << "\""
      << ",\"status\":\"SLASHED\""
      << ",\"reason\":\"" << json_escape(reason) << "\""
      << ",\"note\":\"Bond UTXO can be recovered via build_bond_release_tx() after lock_until expires\""
      << "}";
    return rpc_result(id, s.str());
}

// =============================================================================
// Model B (Escrow) RPC Handlers
// =============================================================================

// handle_escrow_register
// Params: [sost_address, eth_escrow_address, gold_token, gold_amount_mg, commitment_months]
// Calculates immediate reward and registers the escrow commitment.
static std::string handle_escrow_register(const std::string& id, const std::vector<std::string>& p) {
    if (p.size() < 5) return rpc_error(id, -1, "usage: escrow_register <sost_address> <eth_escrow_address> <gold_token> <gold_amount_mg> <commitment_months>");

    const std::string& sost_addr        = p[0];
    const std::string& eth_escrow_addr  = p[1];
    const std::string& gold_token       = p[2];
    int64_t gold_amount_mg              = (int64_t)std::stoll(p[3]);
    uint16_t commitment_months          = (uint16_t)std::stoul(p[4]);

    // Validate SOST address
    PubKeyHash user_pkh{};
    if (!address_decode(sost_addr, user_pkh))
        return rpc_error(id, -1, "invalid sost_address");

    // Validate gold token
    if (gold_token != "XAUT" && gold_token != "PAXG")
        return rpc_error(id, -1, "gold_token must be 'XAUT' or 'PAXG'");

    // Validate amount
    if (gold_amount_mg <= 0)
        return rpc_error(id, -1, "gold_amount_mg must be > 0");

    // Validate duration — use ESCROW_REWARD_RATES (Model B, halved from Model A)
    static constexpr size_t ESCROW_RATES_N = sizeof(ESCROW_REWARD_RATES) / sizeof(ESCROW_REWARD_RATES[0]);
    static constexpr size_t POPC_DUR_N     = sizeof(POPC_DURATIONS) / sizeof(POPC_DURATIONS[0]);
    uint16_t base_reward_pct_bps = 0;
    for (size_t di = 0; di < POPC_DUR_N && di < ESCROW_RATES_N; ++di) {
        if (POPC_DURATIONS[di] == commitment_months) {
            base_reward_pct_bps = ESCROW_REWARD_RATES[di];
            break;
        }
    }
    if (base_reward_pct_bps == 0)
        return rpc_error(id, -1, "commitment_months must be 1, 3, 6, 9, or 12");

    // Anti-whale check
    uint16_t whale_mult_e = whale_tier_multiplier(gold_amount_mg);
    if (whale_mult_e == 0)
        return rpc_error(id, -1, "gold_amount_mg exceeds hard cap (>200 oz / 6,220,700 mg)");

    // Compute escrow_id = SHA256(eth_escrow_address || sost_address || gold_token || commitment_months)
    Hash256 escrow_id{};
    {
        std::string canon = eth_escrow_addr + sost_addr + gold_token + std::to_string((int)commitment_months);
        unsigned int digest_len = 32;
        EVP_Digest(canon.data(), canon.size(),
                   escrow_id.data(), &digest_len,
                   EVP_sha256(), nullptr);
    }

    int64_t current_height;
    {
        std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
        current_height = g_chain_height;
    }

    // Pool balance scan for PUR
    int64_t pool_balance_e = 0;
    {
        PubKeyHash popc_pkh_e{};
        address_decode(ADDR_POPC_POOL, popc_pkh_e);
        std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
        const auto& umap = g_utxo_set.GetMap();
        for (const auto& kv : umap) {
            if (kv.second.pubkey_hash == popc_pkh_e)
                pool_balance_e += kv.second.amount;
        }
    }

    int32_t pur_e = compute_pur_bps(g_popc_registry.committed_rewards(), pool_balance_e);
    if (pur_e >= PUR_CLOSED_BPS)
        return rpc_error(id, -1, "Pool fully committed (PUR=100%). No new registrations accepted.");

    int32_t factor_e = compute_dynamic_factor_bps(pur_e);
    uint16_t dyn_rate_e = apply_dynamic_reward(base_reward_pct_bps, factor_e, POPC_REWARD_FLOOR_B_BPS);
    // Apply whale multiplier
    dyn_rate_e = (uint16_t)(((int64_t)dyn_rate_e * (int64_t)whale_mult_e) / 10000);
    if (dyn_rate_e < POPC_REWARD_FLOOR_B_BPS) dyn_rate_e = POPC_REWARD_FLOOR_B_BPS;

    // Load pricing
    double sost_per_usd   = 1.0;
    double gold_price_usd = 3000.0;
    load_popc_pricing(sost_per_usd, gold_price_usd);

    // Gold value in micro-USD
    int64_t gold_price_micro = (int64_t)(gold_price_usd * 1000000.0);
    int64_t sost_price_micro = (int64_t)(sost_per_usd  * 1000000.0);
    if (gold_price_micro <= 0) gold_price_micro = 3000000000LL;
    if (sost_price_micro <= 0) sost_price_micro = 1000000LL;

    int64_t gold_value_micro = (gold_amount_mg * gold_price_micro) / 31103;

    // Gold value in stocks (for reward calculation using dynamic rate)
    int64_t gold_value_stocks = (gold_value_micro * (int64_t)STOCKS_PER_SOST) / sost_price_micro;

    // Calculate reward using dynamic rate (applied to gold_value_stocks)
    int64_t reward_stocks = (gold_value_stocks * (int64_t)dyn_rate_e) / 10000;
    int64_t net_reward    = reward_stocks - (reward_stocks * (int64_t)POPC_PROTOCOL_FEE_BPS / 10000);

    // Gold value USD formatted
    char gold_usd_buf[64];
    snprintf(gold_usd_buf, sizeof(gold_usd_buf), "%lld.%02lld",
             (long long)(gold_value_micro / 1000000LL),
             (long long)((gold_value_micro % 1000000LL) / 10000LL));

    // Determine whale tier label
    const char* whale_tier_label_e = "T1_FULL";
    if (whale_mult_e == WHALE_MULT_T2) whale_tier_label_e = "T2_75PCT";
    else if (whale_mult_e == WHALE_MULT_T3) whale_tier_label_e = "T3_50PCT";

    EscrowCommitment e{};
    e.escrow_id          = escrow_id;
    e.user_pkh           = user_pkh;
    e.eth_escrow_address = eth_escrow_addr;
    e.gold_token         = gold_token;
    e.gold_amount_mg     = gold_amount_mg;
    e.reward_stocks      = net_reward;
    e.duration_months    = commitment_months;
    e.start_height       = current_height;
    e.end_height         = current_height + popc_duration_to_blocks(commitment_months);
    e.status             = EscrowStatus::ACTIVE;

    std::string reg_err;
    if (!g_escrow_registry.register_escrow(e, &reg_err))
        return rpc_error(id, -1, "register_escrow failed: " + reg_err);

    // Reserve committed rewards for PUR tracking
    g_popc_registry.add_committed(net_reward);

    g_escrow_registry.save(g_escrow_registry_path, nullptr); // best-effort

    // Format escrow_id as hex
    char eid_hex[65]; eid_hex[64] = 0;
    static const char HEX_E[] = "0123456789abcdef";
    for (int i = 0; i < 32; ++i) {
        eid_hex[i*2]   = HEX_E[escrow_id[i] >> 4];
        eid_hex[i*2+1] = HEX_E[escrow_id[i] & 0x0F];
    }

    int32_t pur_pct_e    = pur_e / 100;
    int32_t factor_pct_e = factor_e / 100;

    std::ostringstream s;
    s << "{"
      << "\"escrow_id\":\"" << eid_hex << "\""
      << ",\"sost_address\":\"" << json_escape(sost_addr) << "\""
      << ",\"eth_escrow_address\":\"" << json_escape(eth_escrow_addr) << "\""
      << ",\"gold_token\":\"" << json_escape(gold_token) << "\""
      << ",\"gold_amount_mg\":" << gold_amount_mg
      << ",\"gold_value_usd\":\"" << gold_usd_buf << "\""
      << ",\"base_reward_pct_bps\":" << (int)base_reward_pct_bps
      << ",\"pur_pct\":" << pur_pct_e
      << ",\"dynamic_factor_pct\":" << factor_pct_e
      << ",\"effective_rate_bps\":" << (int)dyn_rate_e
      << ",\"whale_tier\":\"" << whale_tier_label_e << "\""
      << ",\"immediate_reward_sost\":\"" << format_sost(net_reward) << "\""
      << ",\"commitment_months\":" << (int)commitment_months
      << ",\"commitment_blocks\":" << popc_duration_to_blocks(commitment_months)
      << ",\"start_height\":" << current_height
      << ",\"end_height\":" << e.end_height
      << ",\"status\":\"ACTIVE\"";
    if (pur_e >= PUR_WARNING_BPS)
        s << ",\"warning\":\"Pool utilization above 80% — reward rate reduced\"";
    s << ",\"message\":\"Reward paid immediately. Gold held in Ethereum escrow contract until end_height.\""
      << "}";
    return rpc_result(id, s.str());
}

// handle_escrow_status
// Returns list of active escrow commitments and summary.
static std::string handle_escrow_status(const std::string& id, const std::vector<std::string>&) {
    size_t active_count = g_escrow_registry.active_count();
    auto active = g_escrow_registry.list_active();

    std::ostringstream arr;
    arr << "[";
    for (size_t i = 0; i < active.size(); ++i) {
        if (i) arr << ",";
        const auto& e = active[i];
        static const char HEX_E[] = "0123456789abcdef";
        char eid_hex[65]; eid_hex[64] = 0;
        for (int j = 0; j < 32; ++j) {
            eid_hex[j*2]   = HEX_E[e.escrow_id[j] >> 4];
            eid_hex[j*2+1] = HEX_E[e.escrow_id[j] & 0x0F];
        }
        arr << "{"
            << "\"escrow_id\":\"" << eid_hex << "\""
            << ",\"eth_escrow_address\":\"" << json_escape(e.eth_escrow_address) << "\""
            << ",\"gold_token\":\"" << json_escape(e.gold_token) << "\""
            << ",\"gold_amount_mg\":" << e.gold_amount_mg
            << ",\"reward_stocks\":\"" << format_sost(e.reward_stocks) << "\""
            << ",\"duration_months\":" << (int)e.duration_months
            << ",\"start_height\":" << e.start_height
            << ",\"end_height\":" << e.end_height
            << "}";
    }
    arr << "]";

    std::ostringstream s;
    s << "{"
      << "\"active_count\":" << active_count
      << ",\"escrows\":" << arr.str()
      << "}";
    return rpc_result(id, s.str());
}

// handle_escrow_verify
// Params: [eth_escrow_address]
// Placeholder — manual bridge to Etherscan (same pattern as popc_check).
static std::string handle_escrow_verify(const std::string& id, const std::vector<std::string>& p) {
    if (p.empty()) return rpc_error(id, -1, "usage: escrow_verify <eth_escrow_address>");
    const std::string& eth_addr = p[0];

    std::ostringstream s;
    s << "{"
      << "\"eth_escrow_address\":\"" << json_escape(eth_addr) << "\""
      << ",\"status\":\"MANUAL_CHECK_REQUIRED\""
      << ",\"message\":\"Run: python3 scripts/popc_etherscan_checker.py check " << json_escape(eth_addr) << "\""
      << ",\"note\":\"Verify that the Ethereum escrow contract holds the declared gold token balance.\""
      << "}";
    return rpc_result(id, s.str());
}

// handle_escrow_complete
// Params: [escrow_id_hex]
// Marks an escrow as COMPLETED when the timelock expires.
static std::string handle_escrow_complete(const std::string& id, const std::vector<std::string>& p) {
    if (p.empty()) return rpc_error(id, -1, "usage: escrow_complete <escrow_id_hex>");

    const std::string& eid_hex = p[0];
    if (eid_hex.size() != 64) return rpc_error(id, -1, "escrow_id must be 64 hex chars");

    // Decode escrow_id from hex
    Hash256 escrow_id{};
    for (size_t i = 0; i < 32; ++i) {
        auto h = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return 10 + c - 'a';
            if (c >= 'A' && c <= 'F') return 10 + c - 'A';
            return -1;
        };
        int hi = h(eid_hex[i*2]);
        int lo = h(eid_hex[i*2+1]);
        if (hi < 0 || lo < 0) return rpc_error(id, -1, "invalid hex in escrow_id");
        escrow_id[i] = (uint8_t)((hi << 4) | lo);
    }

    int64_t current_height;
    {
        std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
        current_height = g_chain_height;
    }

    const EscrowCommitment* e = g_escrow_registry.find(escrow_id);
    if (!e) return rpc_error(id, -1, "escrow_id not found");
    if (e->status != EscrowStatus::ACTIVE) return rpc_error(id, -1, "escrow is not ACTIVE");
    if (current_height < e->end_height)
        return rpc_error(id, -1, "escrow timelock has not expired yet (end_height=" +
                         std::to_string(e->end_height) + ", current_height=" +
                         std::to_string(current_height) + ")");

    int64_t escrow_reward_amount = e->reward_stocks;

    std::string comp_err;
    if (!g_escrow_registry.complete(escrow_id, &comp_err))
        return rpc_error(id, -1, "complete failed: " + comp_err);

    // Release committed rewards from PUR tracking
    g_popc_registry.release_committed(escrow_reward_amount);

    g_escrow_registry.save(g_escrow_registry_path, nullptr);

    std::ostringstream s;
    s << "{"
      << "\"escrow_id\":\"" << json_escape(eid_hex) << "\""
      << ",\"status\":\"COMPLETED\""
      << ",\"reward_paid\":\"" << format_sost(escrow_reward_amount) << "\""
      << ",\"note\":\"Escrow timelock expired. Gold can be released back to depositor.\""
      << "}";
    return rpc_result(id, s.str());
}

// handle_getproposals
// Returns all defined version-bit signaling proposals and their current status.
static std::string handle_getproposals(const std::string& id, const std::vector<std::string>&) {
    auto proposals = get_proposals();
    std::ostringstream s;
    s << "[";
    for (size_t i = 0; i < proposals.size(); ++i) {
        if (i) s << ",";
        const auto& p = proposals[i];
        // Count signals from recent blocks
        std::vector<uint32_t> versions;
        {
            std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
            int start = std::max(0, (int)g_blocks.size() - SIGNALING_WINDOW);
            for (int j = start; j < (int)g_blocks.size(); ++j)
                versions.push_back(1); // Current blocks all version=1, no signals yet
        }
        int32_t signal_count = count_version_signals(versions, p.bit);
        int32_t window = std::min((int32_t)versions.size(), SIGNALING_WINDOW);
        int32_t pct = window > 0 ? (signal_count * 100) / window : 0;

        s << "{\"bit\":" << (int)p.bit
          << ",\"name\":\"" << p.name << "\""
          << ",\"description\":\"" << p.description << "\""
          << ",\"status\":\"" << (p.status == ProposalStatus::DEFINED ? "defined" :
                                   p.status == ProposalStatus::ACTIVE ? "active" : "pending") << "\""
          << ",\"signal_count\":" << signal_count
          << ",\"window\":" << window
          << ",\"signal_pct\":" << pct
          << ",\"threshold\":" << SIGNALING_THRESHOLD_PCT
          << ",\"foundation_veto\":" << (p.foundation_veto ? "true" : "false")
          << ",\"foundation_support\":" << (p.foundation_support ? "true" : "false")
          << "}";
    }
    s << "]";
    return rpc_result(id, s.str());
}

static std::string handle_getsostprice(const std::string& id, const std::vector<std::string>&) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);

    // Read gold price from oracle cache file (written by sost_price_oracle.py cron)
    double gold_price = 3000.0; // fallback
    double xaut_price = 0.0, paxg_price = 0.0;
    {
        FILE* f = fopen("/opt/sost/data/current_price.json", "r");
        if (!f) f = fopen("/tmp/sost_gold_price_cache.json", "r");
        if (!f) f = fopen("data/current_price.json", "r");
        if (f) {
            char buf[4096];
            size_t n = fread(buf, 1, sizeof(buf)-1, f);
            fclose(f);
            buf[n] = '\0';
            std::string js(buf);
            // Parse from oracle output format
            auto gp = json_get_string(js, "gold_price_usd_per_oz");
            if (!gp.empty()) { try { gold_price = std::stod(gp); } catch(...) {} }
            auto xp = json_get_string(js, "xaut_price_usd");
            if (!xp.empty()) { try { xaut_price = std::stod(xp); } catch(...) {} }
            auto pp = json_get_string(js, "paxg_price_usd");
            if (!pp.empty()) { try { paxg_price = std::stod(pp); } catch(...) {} }
            // Also handle raw CoinGecko cache format (avg key)
            if (gold_price == 3000.0) {
                auto av = json_get_string(js, "avg");
                if (!av.empty()) { try { gold_price = std::stod(av); } catch(...) {} }
            }
            if (xaut_price == 0.0) {
                auto xv = json_get_string(js, "xaut");
                if (!xv.empty()) { try { xaut_price = std::stod(xv); } catch(...) {} }
            }
            if (paxg_price == 0.0) {
                auto pv = json_get_string(js, "paxg");
                if (!pv.empty()) { try { paxg_price = std::stod(pv); } catch(...) {} }
            }
        }
    }
    if (xaut_price == 0.0) xaut_price = gold_price;
    if (paxg_price == 0.0) paxg_price = gold_price;

    // Calculate circulating supply using epoch-decay formula
    // R0=7.85100863, Q=0.7788007830714049, EPOCH=131553
    double supply = 0.0;
    {
        const double R0 = 7.85100863;
        const double Q  = 0.7788007830714049;
        const int64_t EP = 131553;
        int64_t h = 0;
        while (h <= g_chain_height) {
            int64_t epoch = h / EP;
            double reward = R0;
            for (int64_t e = 0; e < epoch; ++e) reward *= Q;
            int64_t epoch_end = (epoch + 1) * EP - 1;
            if (epoch_end > g_chain_height) epoch_end = g_chain_height;
            supply += reward * (double)(epoch_end - h + 1);
            h = epoch_end + 1;
        }
    }

    // Foundation committed gold (immutable)
    const double FOUNDATION_XAUT_OZ = 0.6;
    const double FOUNDATION_PAXG_OZ = 0.6;
    const double gold_oz = FOUNDATION_XAUT_OZ + FOUNDATION_PAXG_OZ; // 1.2 oz total

    double total_gold_value = gold_oz * gold_price;
    double sost_price = supply > 0.0 ? total_gold_value / supply : 0.0;

    std::ostringstream s;
    s << std::fixed;
    s << "{"
      << "\"sost_price_usd\":"          << std::setprecision(6) << sost_price
      << ",\"gold_committed_oz\":"       << std::setprecision(1) << gold_oz
      << ",\"gold_price_usd_per_oz\":"   << std::setprecision(2) << gold_price
      << ",\"xaut_price_usd\":"          << std::setprecision(2) << xaut_price
      << ",\"paxg_price_usd\":"          << std::setprecision(2) << paxg_price
      << ",\"total_gold_value_usd\":"    << std::setprecision(2) << total_gold_value
      << ",\"total_sost_supply\":"       << std::setprecision(4) << supply
      << ",\"chain_height\":"            << g_chain_height
      << ",\"source\":\"popc_backed\""
      << ",\"note\":\"Reference price based on PoPC gold commitment. Not a market price.\""
      << ",\"disclaimer\":\"SOST is not listed on any exchange. This reference price reflects gold backing per token.\""
      << "}";
    return rpc_result(id, s.str());
}

// =========================================================================
// License RPC handlers
// =========================================================================

static std::string handle_license_verify(const std::string& id, const std::vector<std::string>& p) {
    if (p.empty()) return rpc_error(id, -1, "missing license_id or deposit_txid");
    std::string query = p[0];
    // Search for the deposit TX in the tx-index
    Hash256 txid{};
    if (!hex_to_bytes(query, txid.data(), 32))
        return rpc_error(id, -8, "invalid txid hex");
    auto it = g_tx_index.find(txid);
    if (it == g_tx_index.end())
        return rpc_result(id, "{\"valid\":false,\"status\":\"NOT_FOUND\",\"reason\":\"Deposit TX not found in chain\"}");
    int64_t bh = it->second.block_height;
    // Check if it's an ESCROW_LOCK
    if (bh >= (int64_t)g_blocks.size())
        return rpc_result(id, "{\"valid\":false,\"status\":\"INVALID\",\"reason\":\"Block not available\"}");
    uint32_t tpos = it->second.tx_pos;
    if (tpos >= g_blocks[bh].tx_hexes.size())
        return rpc_result(id, "{\"valid\":false,\"status\":\"INVALID\",\"reason\":\"TX position invalid\"}");
    std::vector<Byte> raw;
    if (!decode_tx_hex(g_blocks[bh].tx_hexes[tpos], raw))
        return rpc_result(id, "{\"valid\":false,\"status\":\"INVALID\",\"reason\":\"Cannot decode TX\"}");
    Transaction tx; std::string err;
    if (!Transaction::Deserialize(raw, tx, &err))
        return rpc_result(id, "{\"valid\":false,\"status\":\"INVALID\",\"reason\":\"Cannot deserialize TX\"}");
    // Find ESCROW_LOCK output
    bool has_escrow = false;
    int64_t lock_amount = 0;
    uint64_t lock_until = 0;
    for (const auto& o : tx.outputs) {
        if (o.type == OUT_ESCROW_LOCK) {
            has_escrow = true;
            lock_amount = o.amount;
            lock_until = ReadLockUntil(o.payload);
            break;
        }
    }
    if (!has_escrow)
        return rpc_result(id, "{\"valid\":false,\"status\":\"NOT_ESCROW\",\"reason\":\"TX does not contain ESCROW_LOCK output\"}");
    // Check if still locked
    bool active = (uint64_t)g_chain_height < lock_until;
    // Grace period: within LICENSE_GRACE_BLOCKS after unlock → still valid (auto-renewal window)
    bool in_grace = !active && ((uint64_t)g_chain_height < lock_until + 4320);
    std::string status = active ? "ACTIVE" : (in_grace ? "GRACE_PERIOD" : "EXPIRED");
    std::ostringstream s;
    s << "{\"valid\":" << (active || in_grace ? "true" : "false")
      << ",\"status\":\"" << status << "\""
      << ",\"deposit_stocks\":" << lock_amount
      << ",\"deposit_sost\":" << format_sost(lock_amount)
      << ",\"lock_height\":" << bh
      << ",\"unlock_height\":" << lock_until
      << ",\"grace_end\":" << (lock_until + 4320)
      << ",\"chain_height\":" << g_chain_height
      << ",\"auto_renewal\":\"If deposit not withdrawn by block " << (lock_until + 4320) << ", license auto-renews\""
      << ",\"type\":\"convergencex_operational\""
      << "}";
    return rpc_result(id, s.str());
}

static std::string handle_license_list(const std::string& id, const std::vector<std::string>&) {
    // Scan tx-index for ESCROW_LOCK transactions with sufficient amount
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    std::ostringstream s;
    s << "[";
    int count = 0;
    for (const auto& [txid_key, entry] : g_tx_index) {
        if (count >= 50) break;
        if (entry.block_height >= (int64_t)g_blocks.size()) continue;
        if (entry.tx_pos >= g_blocks[entry.block_height].tx_hexes.size()) continue;
        std::vector<Byte> raw;
        if (!decode_tx_hex(g_blocks[entry.block_height].tx_hexes[entry.tx_pos], raw)) continue;
        Transaction tx; std::string err;
        if (!Transaction::Deserialize(raw, tx, &err)) continue;
        for (const auto& o : tx.outputs) {
            if (o.type == OUT_ESCROW_LOCK && o.amount >= 100000000) { // min 1 SOST
                uint64_t lock_until = ReadLockUntil(o.payload);
                bool active = (uint64_t)g_chain_height < lock_until;
                bool in_grace = !active && ((uint64_t)g_chain_height < lock_until + 4320);
                if (active || in_grace) {
                    if (count > 0) s << ",";
                    s << "{\"txid\":\"" << to_hex(txid_key.data(), 32) << "\""
                      << ",\"amount\":" << format_sost(o.amount)
                      << ",\"lock_height\":" << entry.block_height
                      << ",\"unlock_height\":" << lock_until
                      << ",\"status\":\"" << (active ? "ACTIVE" : "GRACE_PERIOD") << "\""
                      << "}";
                    count++;
                }
                break;
            }
        }
    }
    s << "]";
    return rpc_result(id, s.str());
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
    {"getaddressutxos",handle_getaddressutxos},
    {"listbonds",handle_listbonds},
    {"listtransfers",handle_listtransfers},
    {"popc_register",handle_popc_register},
    {"popc_status",handle_popc_status},
    {"popc_check",handle_popc_check},
    {"popc_release",handle_popc_release},
    {"popc_slash",handle_popc_slash},
    {"escrow_register",handle_escrow_register},
    {"escrow_status",handle_escrow_status},
    {"escrow_verify",handle_escrow_verify},
    {"escrow_complete",handle_escrow_complete},
    {"getproposals",handle_getproposals},
    {"getsostprice",handle_getsostprice},
    {"license_verify",handle_license_verify},
    {"license_list",handle_license_list},
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
    int retries=0;
    while(got<len){
        ssize_t n=read(fd,buf+got,len-got);
        if(n<0){
            if(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR){
                if(++retries>50) return false; // ~5s with 100ms select
                // Wait up to 100ms for data (handles high-latency connections)
                fd_set fds; FD_ZERO(&fds); FD_SET(fd,&fds);
                struct timeval tv={0,100000}; // 100ms
                select(fd+1,&fds,nullptr,nullptr,&tv);
                continue;
            }
            return false;
        }
        if(n==0) return false; // connection closed
        got+=n;
        retries=0;
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
    // Decrypt with current nonce; only advance nonce on success
    uint64_t nonce_val = crypto.recv_nonce;
    if(!chacha20_poly1305_decrypt(crypto.recv_key, nonce_val,
        cipher.data(), clen, tag, plain.data())) return false;
    crypto.recv_nonce = nonce_val + 1;

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

// Forward declaration for encryption-aware send
static bool p2p_send_adaptive(int fd, PeerCrypto& crypto, const char* cmd,
    const uint8_t* payload, size_t len);

static void p2p_send_block(int fd, int64_t h, PeerCrypto* crypto = nullptr) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    if(h<0||h>=(int64_t)g_blocks.size()) return;
    const auto& b=g_blocks[h];
    // Use raw_block_json if available (contains complete Transcript V2 proof)
    if (!b.raw_block_json.empty()) {
        if (crypto && crypto->encrypted) {
            p2p_send_encrypted(fd, *crypto, "BLCK",
                (const uint8_t*)b.raw_block_json.data(), b.raw_block_json.size());
        } else {
            p2p_send(fd, "BLCK", (const uint8_t*)b.raw_block_json.data(), b.raw_block_json.size());
        }
        return;
    }
    // Fallback for genesis/legacy blocks without raw JSON
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
    if (!b.x_bytes_hex.size()) {} else { s<<",\"x_bytes\":\""<<b.x_bytes_hex<<"\""; }
    if (!b.final_state_hex.empty()) { s<<",\"final_state\":\""<<b.final_state_hex<<"\""; }
    if (!b.segments_root_hex.empty()) { s<<",\"segments_root\":\""<<b.segments_root_hex<<"\""; }
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
    if (crypto && crypto->encrypted) {
        p2p_send_encrypted(fd, *crypto, "BLCK", (const uint8_t*)js.data(), js.size());
    } else {
        p2p_send(fd, "BLCK", (const uint8_t*)js.data(), js.size());
    }
}

static void p2p_broadcast_tx(const std::string& hex_str) {
    std::lock_guard<std::mutex> lk(g_peers_mu);
    for(auto& p:g_peers){
        if(!p.version_acked) continue;
        // Skip syncing peers — same race condition as broadcast_block_to_peers
        if(p.their_height >= 0 && p.their_height < (int64_t)g_blocks.size() - 50)
            continue;
        {
            std::lock_guard<std::mutex> wlk(*p.write_mu);
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
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);

    // Required fields
    std::string bid = jstr(block_json,"block_id");
    std::string prev = jstr(block_json,"prev_hash");
    std::string mrkl = jstr(block_json,"merkle_root");
    std::string commit_hex = jstr(block_json,"commit");
    std::string croot_hex  = jstr(block_json,"checkpoints_root");

    // Debug: log every block near the 2500 boundary
    int64_t dbg_h = jint(block_json,"height");
    if(dbg_h >= 2498 && dbg_h <= 2505) {
        bool has_tx = block_json.find("\"transactions\"") != std::string::npos;
        printf("[P2PDBG] process_block h=%lld bid=%s has_tx=%d json_len=%zu chain_size=%zu\n",
               (long long)dbg_h, bid.substr(0,16).c_str(), (int)has_tx, block_json.size(), g_blocks.size());
    }

    if(bid.size()!=64 || prev.size()!=64 || mrkl.size()!=64 || commit_hex.size()!=64 || croot_hex.size()!=64){
        printf("[BLOCK] REJECTED: missing/invalid required hex fields\n");
        return false;
    }

    // Already known? Skip silently (normal relay behavior, NOT misbehavior)
    {
        std::lock_guard<std::mutex> lk2(g_known_mu);
        if (g_known_blocks.count(bid)) {
            return false; // silently ignore — not an error
        }
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

    Hash256 prev_h = from_hex(prev);

    // Fork-aware chain acceptance using cumulative work (NOT longest chain)
    bool extends_tip = (height == (int64_t)g_blocks.size()) &&
                       (g_blocks.empty() || prev_h == g_blocks.back().block_id);

    if (!extends_tip) {
        // This block doesn't extend our current tip — classify as fork or orphan
        printf("[FORK] Block h=%lld bid=%s does not extend tip (our height=%zu).\n",
               (long long)height, bid.substr(0,16).c_str(), g_blocks.size());
        fflush(stdout);

        // Check if parent is known (in active chain or block index)
        std::string prev_hex = to_hex(prev_h.data(), 32);
        bool parent_known = false;

        // Check active chain
        for (const auto& ab : g_blocks) {
            if (ab.block_id == prev_h) { parent_known = true; break; }
        }
        // Check block index (fork blocks)
        if (!parent_known) {
            std::lock_guard<std::mutex> lk(g_block_index_mu);
            parent_known = g_block_index.count(prev_hex) > 0;
        }

        if (!parent_known) {
            // ORPHAN: parent not known locally
            std::lock_guard<std::mutex> lk(g_block_index_mu);
            if (g_orphans_by_prev.size() < MAX_ORPHAN_BLOCKS) {
                BlockIndexEntry entry;
                entry.block_id = from_hex(bid);
                entry.prev_hash = prev_h;
                entry.height = height;
                entry.bits_q = bits_q;
                entry.block_work = compute_block_work(bits_q);
                entry.cumulative_work = {}; // unknown until parent found
                entry.status = BlockStatus::ORPHAN;
                entry.raw_json = block_json;
                g_block_index[bid] = entry;
                g_orphans_by_prev.insert({prev_hex, bid});
                mark_block_known(bid);
                printf("[ORPHAN] Block h=%lld stored (parent %s unknown). %zu orphans total.\n",
                       (long long)height, prev_hex.substr(0,16).c_str(), g_orphans_by_prev.size());
            }
            fflush(stdout);
            return false;
        }

        // FORK CANDIDATE: parent is known but block doesn't extend active tip
        {
            std::lock_guard<std::mutex> lk(g_block_index_mu);
            if (g_block_index.size() < MAX_FORK_INDEX_ENTRIES) {
                BlockIndexEntry entry;
                entry.block_id = from_hex(bid);
                entry.prev_hash = prev_h;
                entry.height = height;
                entry.bits_q = bits_q;
                entry.block_work = compute_block_work(bits_q);
                // Compute cumulative work: parent's cumulative_work + this block's work
                Bytes32 parent_cw{};
                // Look up parent's cumulative work
                auto pit = g_block_index.find(prev_hex);
                if (pit != g_block_index.end()) {
                    parent_cw = pit->second.cumulative_work;
                } else {
                    // Parent is on active chain — find it
                    for (const auto& ab : g_blocks) {
                        if (ab.block_id == prev_h) {
                            parent_cw = ab.cumulative_work;
                            break;
                        }
                    }
                }
                entry.cumulative_work = add_be256(parent_cw, entry.block_work);
                entry.status = BlockStatus::FORK;
                entry.raw_json = block_json;
                g_block_index[bid] = entry;
                mark_block_known(bid);

                // Check if this fork has MORE cumulative work than active tip
                Bytes32 active_tip_work = g_blocks.empty() ? Bytes32{} : g_blocks.back().cumulative_work;
                if (compare_chainwork(entry.cumulative_work, active_tip_work) > 0) {
                    printf("[FORK] Alternative chain has MORE cumulative work! "
                           "Fork tip h=%lld, active tip h=%lld. Attempting reorg.\n",
                           (long long)height, (long long)g_chain_height);
                    fflush(stdout);
                    // Release index lock before calling try_reorganize (it acquires chain_mu)
                    // try_reorganize uses its own locking
                    // NOTE: we already hold g_chain_mu from process_block(), so we call
                    // the internal reorg function directly
                    try { try_reorganize(bid); }
                    catch (const std::exception& e) { fprintf(stderr, "[ERROR] try_reorganize: %s\n", e.what()); }
                } else {
                    printf("[FORK] Fork stored but has LESS cumulative work (no reorg). "
                           "Fork work vs active: %s vs %s\n",
                           to_hex(entry.cumulative_work.data(),32).substr(0,16).c_str(),
                           to_hex(active_tip_work.data(),32).substr(0,16).c_str());
                }
            }
        }
        fflush(stdout);
        return false; // Don't add to main chain yet
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

    // FAST-SYNC: if block is under assumevalid, allow missing/empty transactions
    // This handles high-latency peers where block data arrives incomplete
    bool is_trusted_height = false;
    if(sost::has_assumevalid_anchor() && (uint32_t)height <= sost::get_assumevalid_height() && !g_full_verify_mode){
        is_trusted_height = true;
    }

    // Decode txs (coinbase included)
    std::vector<std::string> tx_hexes = json_get_tx_hexes(block_json);
    if(tx_hexes.empty()){
        if(is_trusted_height){
            // Trusted block with missing tx data — accept with header-only validation
            // Reconstruct minimal coinbase from block fields for UTXO accounting
            printf("[BLOCK] fast-sync height=%lld (trusted, tx data missing — header-only accept)\n",
                   (long long)height);
            StoredBlock sb{};
            sb.block_id=from_hex(bid); sb.prev_hash=from_hex(prev);
            sb.merkle_root=from_hex(mrkl); sb.commit=from_hex(commit_hex);
            sb.checkpoints_root=from_hex(croot_hex);
            sb.timestamp=ts64; sb.bits_q=bits_q; sb.nonce=nonce;
            sb.extra_nonce=extra; sb.height=height; sb.subsidy=subsidy;
            sb.miner_reward=jint(block_json,"miner");
            sb.gold_vault_reward=jint(block_json,"gold_vault");
            sb.popc_pool_reward=jint(block_json,"popc_pool");
            sb.stability_metric=juint(block_json,"stability_metric");
            sb.x_bytes_hex=jstr(block_json,"x_bytes");
            sb.final_state_hex=jstr(block_json,"final_state");
            sb.segments_root_hex=jstr(block_json,"segments_root");
            sb.raw_block_json=block_json;
            sb.cumulative_work = g_blocks.empty() ? Bytes32{} : g_blocks.back().cumulative_work;
            g_blocks.push_back(sb);
            g_chain_height = height;
            mark_block_known(bid);
            // Note: chain auto-saved when next normal block arrives
            return true;
        }
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
                    if(g_verbose) printf("[PARSE] segment_proofs array: pos %zu to %zu (%zu chars)\n", arr_s, arr_e, arr_e - arr_s);
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
            if(g_verbose) printf("[PARSE] Parsed %zu segment_proofs\n", seg_proofs_vec.size()); fflush(stdout);
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
                    if(g_verbose) printf("[PARSE] round_witnesses array: pos %zu to %zu (%zu chars)\n", arr_s, arr_e, arr_e - arr_s);
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
        if(g_verbose) printf("[BLOCK-V2] Parsed: x_bytes=%zu final_state=%s segments_root=%s cp_leaves=%zu seg_proofs=%zu rw=%zu\n",
                x_bytes_raw.size(), final_state_hex.substr(0,16).c_str(), segments_root_hex.substr(0,16).c_str(),
                checkpoint_leaves_vec.size(), seg_proofs_vec.size(), round_witnesses_vec.size());
        fflush(stdout);

        ConsensusParams cx_params = sost::get_consensus_params(sost::Profile::MAINNET, height);
        // CONSENSUS-CRITICAL: Profile verification
        // The commit now includes profile_index, so we must verify the miner
        // used exactly the correct profile. No more trusting free params.
        //
        // For trusted blocks (under assumevalid anchor), skip this check if
        // the block JSON doesn't contain profile_index (P2P fallback format).
        {
            // Check if this block is in the trusted range
            bool trusted_block = false;
            if(sost::has_assumevalid_anchor() && (uint32_t)height <= sost::get_assumevalid_height() && !g_full_verify_mode){
                trusted_block = true;
            }

            // 2. Read miner's declared profile_index
            int32_t declared_pi = (int32_t)jint(block_json, "profile_index");

            if (declared_pi == -1 && trusted_block) {
                // Profile index missing from P2P data but block is trusted — use B0 default
                printf("[BLOCK] fast-sync height=%lld: profile_index missing, trusted block (assuming B0)\n",
                       (long long)height);
                declared_pi = 0; // B0
                g_last_accepted_profile = declared_pi;
                CasertDecision dec_for_profile;
                dec_for_profile.profile_index = declared_pi;
                cx_params = sost::casert_apply_profile(cx_params, dec_for_profile);
            } else {
                // 1. Recompute base profile deterministically from chain history (no anti-stall)
                std::vector<BlockMeta> meta;
                meta.reserve(g_blocks.size());
                for (size_t j = 0; j < g_blocks.size(); ++j) {
                    BlockMeta bm; bm.block_id = g_blocks[j].block_id;
                    bm.height = g_blocks[j].height; bm.time = g_blocks[j].timestamp;
                    bm.powDiffQ = g_blocks[j].bits_q;
                    meta.push_back(bm);
                }
                auto base_dec = sost::casert_compute(meta, height, 0); // now_time=0 → no anti-stall
                int32_t base_profile = base_dec.profile_index;

                // 3. Validate: declared profile must be in [CASERT_H_MIN, base_profile]
                //    Anti-stall can only EASE (lower profile), never harden beyond base.
                if (declared_pi < CASERT_H_MIN || declared_pi > CASERT_H_MAX) {
                    printf("[BLOCK] REJECTED: profile_index %d out of bounds [%d, %d]\n",
                           declared_pi, CASERT_H_MIN, CASERT_H_MAX);
                    return false;
                }
                if (declared_pi > base_profile) {
                    printf("[BLOCK] REJECTED: profile_index %d exceeds base profile %d (can only ease, not harden beyond base)\n",
                           declared_pi, base_profile);
                    return false;
                }

                // 4. Store last accepted profile for getinfo reporting
                g_last_accepted_profile = declared_pi;

                // 5. Derive exact params from canonical table — no free params
                CasertDecision dec_for_profile;
                dec_for_profile.profile_index = declared_pi;
                cx_params = sost::casert_apply_profile(cx_params, dec_for_profile);
            }
            cx_params.verbose = g_verbose;

            if(g_verbose) printf("[BLOCK-V3] Profile: declared=%d (params: scale=%d k=%d margin=%d steps=%d)\n",
                   declared_pi, cx_params.stab_scale, cx_params.stab_k,
                   cx_params.stab_margin, cx_params.stab_steps);
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
            // V3: profile_index committed (genesis uses B0 = profile_index 0)
            int8_t genesis_pi = (int8_t)cx_params.stab_profile_index;
            cbuf_v.push_back((uint8_t)genesis_pi);
            if (sha256(cbuf_v) != commit32) { printf("[BLOCK] REJECTED: commit V3 mismatch\n"); return false; }
            printf("[BLOCK] Genesis CX proof verified (commit V3 + checkpoint merkle)\n");
        } else {
            // FAST SYNC DECISION: check BEFORE attempting CX proof verification
            // If this block is trusted (hard checkpoint or under assumevalid anchor),
            // skip CX proof verification entirely — the proof data may not be available
            // from peers that don't store raw_block_json for historical blocks.
            std::string bid_hex = to_hex(computed_bid.data(), 32);
            bool anchor_on_chain = false;
            // For initial sync, we trust the assumevalid anchor optimistically:
            // we don't yet have the anchor block on our chain, but we will verify it
            // when we reach that height. This is the same trust model as Bitcoin Core.
            if(sost::has_assumevalid_anchor() && (uint32_t)height <= sost::get_assumevalid_height()){
                anchor_on_chain = true; // optimistic trust during initial sync
            } else if(sost::has_assumevalid_anchor() && sost::get_assumevalid_height() < g_blocks.size()){
                std::string chain_hash = to_hex(g_blocks[sost::get_assumevalid_height()].block_id.data(), 32);
                anchor_on_chain = (chain_hash == sost::get_assumevalid_hash());
            }
            bool skip_cx = sost::can_skip_cx_recomputation(
                (uint32_t)height, bid_hex, anchor_on_chain, g_full_verify_mode);

            if(skip_cx){
                printf("[BLOCK] fast-sync height=%lld (trusted: checkpoint/assumevalid, CX proof skipped)\n",
                       (long long)height);
            } else {
                // Full Transcript V2 verification for non-trusted blocks
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
        }
    } else if (height > 0) {
        // Missing CX proof data — only acceptable for trusted blocks
        std::string bid_hex_nodata = to_hex(computed_bid.data(), 32);
        bool anchor_trust = false;
        if(sost::has_assumevalid_anchor() && (uint32_t)height <= sost::get_assumevalid_height()){
            anchor_trust = true;
        }
        bool skip_nodata = sost::can_skip_cx_recomputation(
            (uint32_t)height, bid_hex_nodata, anchor_trust, g_full_verify_mode);
        if(skip_nodata){
            printf("[BLOCK] fast-sync height=%lld (no CX data, trusted via checkpoint/assumevalid)\n",
                   (long long)height);
        } else {
            printf("[BLOCK] REJECTED: missing CX proof data (not in trusted range)\n");
            return false;
        }
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
    // Store Transcript V2 proof data and raw JSON for P2P relay
    sb.segments_root_hex = jstr(block_json, "segments_root");
    sb.stab_scale = (int32_t)jint(block_json, "stab_scale");
    sb.stab_k = (int32_t)jint(block_json, "stab_k");
    sb.stab_margin = (int32_t)jint(block_json, "stab_margin");
    sb.stab_steps = (int32_t)jint(block_json, "stab_steps");
    sb.stab_lr_shift = (int32_t)jint(block_json, "stab_lr_shift");
    sb.raw_block_json = block_json; // full JSON for relay

    // Compute cumulative chainwork: parent_work + this block's work
    // best chain = highest cumulative valid work
    Bytes32 this_block_work = compute_block_work(bits_q);
    Bytes32 parent_work = g_blocks.empty() ? Bytes32{} : g_blocks.back().cumulative_work;
    sb.cumulative_work = add_be256(parent_work, this_block_work);

    g_blocks.push_back(sb);
    g_block_undos.push_back(undo); // Store for reorg
    g_chain_height = height;

    // Update block index: mark as ACTIVE
    {
        std::lock_guard<std::mutex> lk(g_block_index_mu);
        BlockIndexEntry idx_entry;
        idx_entry.block_id = computed_bid;
        idx_entry.prev_hash = prev_h;
        idx_entry.height = height;
        idx_entry.bits_q = bits_q;
        idx_entry.block_work = this_block_work;
        idx_entry.cumulative_work = sb.cumulative_work;
        idx_entry.status = BlockStatus::ACTIVE;
        idx_entry.has_undo = true;
        g_block_index[bid] = idx_entry;
    }

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

    // Mark block as known (prevents re-processing on relay back from peers)
    mark_block_known(bid);

    // Show chainwork with significant bytes (skip leading zeros for readability)
    std::string cw_hex = to_hex(sb.cumulative_work.data(), 32);
    size_t cw_start = cw_hex.find_first_not_of('0');
    std::string cw_short = (cw_start == std::string::npos) ? "0" : cw_hex.substr(cw_start);
    printf("[BLOCK] Height %lld accepted: %s (txs=%zu, fees=%lld, UTXOs=%zu, chainwork=0x%s)\n",
           (long long)height, bid.substr(0,16).c_str(), txs.size(), (long long)total_fees,
           g_utxo_set.Size(), cw_short.c_str());

    // Clean up fork blocks that are now too old
    cleanup_old_forks();

    // v0.3.2: Auto-save chain immediately after every accepted block
    if (!g_chain_path.empty()) {
        if (!save_chain_internal(g_chain_path)) {
            printf("[BLOCK] WARNING: chain auto-save failed!\n");
        }
    }

    // P2P: broadcast accepted block to all connected peers
    try { broadcast_block_to_peers(sb); }
    catch (const std::exception& e) { fprintf(stderr, "[ERROR] broadcast_block_to_peers: %s\n", e.what()); }

    // Process orphan blocks that were waiting for this block as parent
    try { process_orphans_for_parent(bid); }
    catch (const std::exception& e) { fprintf(stderr, "[ERROR] process_orphans_for_parent: %s\n", e.what()); }

    return true;
}

// === REORG SUPPORT FUNCTIONS ===

static void cleanup_old_forks() {
    std::lock_guard<std::mutex> lk(g_block_index_mu);
    if (g_block_index.empty()) return;
    int64_t cutoff = g_chain_height - (int64_t)MAX_REORG_DEPTH;
    std::vector<std::string> to_remove;
    for (const auto& [hash, entry] : g_block_index) {
        if (entry.status != BlockStatus::ACTIVE && entry.height < cutoff) {
            to_remove.push_back(hash);
        }
    }
    for (const auto& h : to_remove) g_block_index.erase(h);

    // Also clean stale orphans
    std::vector<std::string> orphan_keys_to_remove;
    for (const auto& [prev, hash] : g_orphans_by_prev) {
        if (g_block_index.find(hash) == g_block_index.end()) {
            orphan_keys_to_remove.push_back(prev);
        }
    }
    for (const auto& k : orphan_keys_to_remove) g_orphans_by_prev.erase(k);

    if (!to_remove.empty())
        printf("[REORG] Cleaned %zu stale fork/orphan blocks (below height %lld)\n",
               to_remove.size(), (long long)cutoff);

    // g_known_blocks is now pruned via FIFO in mark_block_known() — no manual cap needed here
    {
    }
}

// === ATOMIC REORG: try_reorganize ===
// Reorganization is atomic: all-or-nothing. If any step fails,
// the original chain state is fully restored.
// Selection criterion: best chain = highest cumulative valid work.
static bool try_reorganize(const std::string& fork_tip_hash) {
    // Guard against recursive reorg (process_block→try_reorganize→process_block→try_reorganize)
    if (g_in_reorg) {
        printf("[REORG] Skipped: already in reorg\n");
        return false;
    }
    g_in_reorg = true;
    struct ReorgGuard { ~ReorgGuard(){ g_in_reorg = false; } } _rg;

    // NOTE: caller already holds g_chain_mu.
    // We acquire g_block_index_mu as needed.

    // Step 1: Walk the fork chain back through block_index to find fork point
    std::vector<BlockIndexEntry> fork_chain;
    {
        std::lock_guard<std::mutex> lk(g_block_index_mu);
        std::string current = fork_tip_hash;
        std::set<std::string> visited; // loop detection

        while (true) {
            auto it = g_block_index.find(current);
            if (it == g_block_index.end()) break; // hit unknown block or active chain
            if (visited.count(current)) break;    // loop prevention
            visited.insert(current);
            fork_chain.push_back(it->second);
            current = to_hex(it->second.prev_hash.data(), 32);
            // Stop if parent is on active chain
            bool on_active = false;
            for (const auto& ab : g_blocks) {
                if (to_hex(ab.block_id.data(), 32) == current) { on_active = true; break; }
            }
            if (on_active) break;
        }
    }
    std::reverse(fork_chain.begin(), fork_chain.end());

    if (fork_chain.empty()) {
        printf("[REORG] Cannot build fork chain from %s\n", fork_tip_hash.substr(0,16).c_str());
        return false;
    }

    // Step 2: Find the fork point (common ancestor on active chain)
    Hash256 fork_base_prev = fork_chain[0].prev_hash;
    int64_t fork_point = -1;
    for (int64_t h = g_chain_height; h >= 0; --h) {
        if (g_blocks[h].block_id == fork_base_prev) {
            fork_point = h;
            break;
        }
    }

    if (fork_point < 0) {
        printf("[REORG] Cannot find fork point on active chain\n");
        return false;
    }

    int64_t disconnect_count = g_chain_height - fork_point;
    int64_t connect_count = (int64_t)fork_chain.size();

    // Step 3: Verify limits
    if (disconnect_count > MAX_REORG_DEPTH) {
        printf("[REORG] Rejected: depth %lld exceeds REORG_LIMIT %lld\n",
               (long long)disconnect_count, (long long)MAX_REORG_DEPTH);
        return false;
    }

    // Reject reorg past a checkpoint
    for (size_t ci = 0; ci < g_num_checkpoints; ++ci) {
        if (g_checkpoints[ci].height > fork_point && g_checkpoints[ci].height <= g_chain_height) {
            printf("[REORG] Rejected: would reorg past checkpoint at height %lld\n",
                   (long long)g_checkpoints[ci].height);
            return false;
        }
    }

    // Step 4: Verify fork has MORE cumulative work (NOT just more height)
    Bytes32 fork_tip_work = fork_chain.back().cumulative_work;
    Bytes32 active_tip_work = g_blocks.back().cumulative_work;
    if (compare_chainwork(fork_tip_work, active_tip_work) <= 0) {
        printf("[REORG] Fork has equal or less cumulative work — no reorg. "
               "Active work=%s, candidate work=%s\n",
               to_hex(active_tip_work.data(),32).substr(0,16).c_str(),
               to_hex(fork_tip_work.data(),32).substr(0,16).c_str());
        return false;
    }

    printf("[REORG] Fork detected at height %lld\n", (long long)fork_point);
    printf("[REORG] Active work = %s, candidate work = %s\n",
           to_hex(active_tip_work.data(),32).substr(0,16).c_str(),
           to_hex(fork_tip_work.data(),32).substr(0,16).c_str());
    printf("[REORG] Disconnecting %lld blocks (h=%lld..%lld)\n",
           (long long)disconnect_count, (long long)(fork_point+1), (long long)g_chain_height);
    printf("[REORG] Connecting %lld blocks\n", (long long)connect_count);
    fflush(stdout);

    // Step 5: SNAPSHOT current state for atomic rollback
    // Save everything needed to restore on failure
    std::vector<StoredBlock> saved_blocks(g_blocks.begin() + fork_point + 1, g_blocks.end());
    std::vector<BlockUndo> saved_undos(g_block_undos.begin() + fork_point + 1, g_block_undos.end());
    int64_t saved_height = g_chain_height;
    // Save mempool state (txids) for potential restoration
    // (We don't deep-copy mempool; instead we re-add txs on failure)

    // Step 6: Disconnect phase — undo blocks from tip to fork point
    std::vector<StoredBlock> disconnected;
    std::vector<std::vector<Transaction>> disconnected_txs;

    for (int64_t h = g_chain_height; h > fork_point; --h) {
        if (h >= (int64_t)g_blocks.size() || h >= (int64_t)g_block_undos.size()) {
            printf("[REORG] ABORTED: missing undo data for height %lld\n", (long long)h);
            return false;
        }
        // Deserialize transactions
        std::vector<Transaction> txs;
        for (const auto& hex : g_blocks[h].tx_hexes) {
            std::vector<Byte> raw;
            if (decode_tx_hex(hex, raw)) {
                Transaction tx; std::string err;
                if (Transaction::Deserialize(raw, tx, &err)) txs.push_back(tx);
            }
        }
        std::string derr;
        if (!g_utxo_set.DisconnectBlock(txs, g_block_undos[h], &derr)) {
            printf("[REORG] ABORTED: DisconnectBlock failed at height %lld: %s\n", (long long)h, derr.c_str());
            printf("[REORG] Rolled back to original tip %s\n",
                   to_hex(g_blocks.back().block_id.data(),32).substr(0,16).c_str());
            // Blocks are still in g_blocks, UTXO state is inconsistent — try to reconnect
            // the blocks we just disconnected
            // (This shouldn't happen since DisconnectBlock uses recorded undo data)
            return false;
        }
        disconnected.push_back(g_blocks[h]);
        disconnected_txs.push_back(txs);
        printf("[REORG] Disconnected block h=%lld\n", (long long)h);
    }

    // Remove disconnected blocks
    g_blocks.resize(fork_point + 1);
    g_block_undos.resize(fork_point + 1);
    g_chain_height = fork_point;

    // Step 7: Connect phase — connect fork chain blocks
    // If any block fails, we MUST restore the original chain (atomic guarantee)
    size_t connected = 0;
    bool connect_success = true;

    for (size_t i = 0; i < fork_chain.size(); ++i) {
        if (!process_block(fork_chain[i].raw_json)) {
            printf("[REORG] ABORTED: block at height %lld failed validation\n",
                   (long long)fork_chain[i].height);
            connect_success = false;
            break;
        }
        connected++;
    }

    if (!connect_success) {
        // ROLLBACK: disconnect whatever we connected from the fork
        printf("[REORG] Rolling back %zu fork blocks...\n", connected);
        for (int64_t h = g_chain_height; h > fork_point; --h) {
            std::vector<Transaction> txs;
            for (const auto& hex : g_blocks[h].tx_hexes) {
                std::vector<Byte> raw;
                if (decode_tx_hex(hex, raw)) {
                    Transaction tx; std::string err;
                    if (Transaction::Deserialize(raw, tx, &err)) txs.push_back(tx);
                }
            }
            std::string derr;
            g_utxo_set.DisconnectBlock(txs, g_block_undos[h], &derr);
        }
        g_blocks.resize(fork_point + 1);
        g_block_undos.resize(fork_point + 1);
        g_chain_height = fork_point;

        // Reconnect original chain
        printf("[REORG] Restoring original chain (%zu blocks)...\n", saved_blocks.size());
        for (size_t ri = 0; ri < saved_blocks.size(); ++ri) {
            const auto& sb = saved_blocks[ri];
            // Deserialize txs
            std::vector<Transaction> txs;
            for (const auto& hex : sb.tx_hexes) {
                std::vector<Byte> raw;
                if (decode_tx_hex(hex, raw)) {
                    Transaction tx; std::string err;
                    if (Transaction::Deserialize(raw, tx, &err)) txs.push_back(tx);
                }
            }
            BlockUndo undo;
            std::string uerr;
            if (!g_utxo_set.ConnectBlock(txs, sb.height, undo, &uerr)) {
                printf("[REORG] CRITICAL: Cannot restore original block h=%lld: %s\n",
                       (long long)sb.height, uerr.c_str());
                // This should never happen — the original chain was valid
                break;
            }
            g_blocks.push_back(sb);
            g_block_undos.push_back(undo);
            g_chain_height = sb.height;
        }
        printf("[REORG] Rolled back to original tip %s at height %lld\n",
               to_hex(g_blocks.back().block_id.data(),32).substr(0,16).c_str(),
               (long long)g_chain_height);
        fflush(stdout);
        return false;
    }

    // Step 8: Mempool recovery — return valid non-coinbase txs from disconnected blocks
    int recovered = 0, conflicts = 0;
    // Collect all txids in the new branch to detect conflicts
    std::set<Hash256> new_branch_txids;
    for (int64_t h = fork_point + 1; h <= g_chain_height; ++h) {
        for (const auto& hex : g_blocks[h].tx_hexes) {
            std::vector<Byte> raw;
            if (decode_tx_hex(hex, raw)) {
                Transaction tx; std::string err;
                if (Transaction::Deserialize(raw, tx, &err)) {
                    Hash256 txid{}; tx.ComputeTxId(txid, nullptr);
                    new_branch_txids.insert(txid);
                }
            }
        }
    }

    for (const auto& dsb : disconnected) {
        for (size_t ti = 1; ti < dsb.tx_hexes.size(); ++ti) { // skip coinbase (idx 0)
            std::vector<Byte> raw;
            if (decode_tx_hex(dsb.tx_hexes[ti], raw)) {
                Transaction tx; std::string err;
                if (Transaction::Deserialize(raw, tx, &err)) {
                    Hash256 txid{}; tx.ComputeTxId(txid, nullptr);
                    // Skip if already in new branch
                    if (new_branch_txids.count(txid)) continue;
                    // Try to re-add to mempool with new UTXO state
                    TxValidationContext ctx; ctx.genesis_hash = g_genesis_hash;
                    ctx.spend_height = g_chain_height + 1;
                    auto mr = g_mempool.AcceptToMempool(tx, g_utxo_set, ctx, (int64_t)time(nullptr));
                    if (mr.accepted) recovered++;
                    else conflicts++;
                }
            }
        }
    }

    printf("[REORG] Success: new tip = %s at height %lld\n",
           to_hex(g_blocks.back().block_id.data(), 32).substr(0, 16).c_str(), (long long)g_chain_height);
    printf("[REORG] Recovered %d transactions to mempool (%d conflicts discarded)\n", recovered, conflicts);
    fflush(stdout);

    // Clean up: mark fork blocks as ACTIVE in index, remove from fork status
    {
        std::lock_guard<std::mutex> lk(g_block_index_mu);
        for (const auto& fc : fork_chain) {
            std::string h = to_hex(fc.block_id.data(), 32);
            auto it = g_block_index.find(h);
            if (it != g_block_index.end()) it->second.status = BlockStatus::ACTIVE;
        }
        // Mark old active blocks as FORK (they're no longer on main chain)
        for (const auto& dsb : disconnected) {
            std::string h = to_hex(dsb.block_id.data(), 32);
            auto it = g_block_index.find(h);
            if (it != g_block_index.end()) it->second.status = BlockStatus::FORK;
        }
    }

    return true;
}

// === P2P BLOCK BROADCAST ===
// After accepting a block, relay it to all connected peers (except the sender).
// Serializes block data from StoredBlock directly (caller holds g_chain_mu).
static void broadcast_block_to_peers(const StoredBlock& sb, int exclude_fd) {
    // Use the raw_block_json which contains the COMPLETE Transcript V2 proof
    const std::string& js = sb.raw_block_json;
    if (js.empty()) return;

    std::lock_guard<std::mutex> lk(g_peers_mu);
    int sent = 0;
    for (auto& p : g_peers) {
        if (p.fd == exclude_fd) continue;
        if (!p.version_acked) continue;
        // CRITICAL FIX: Do NOT broadcast to peers that are still syncing
        // (their_height far below ours). Broadcasting plaintext BLCKs into
        // an encrypted connection while the handle_peer thread is also writing
        // causes interleaved frames → corrupted TCP stream → silent block loss.
        // Syncing peers will get these blocks via the normal GETB flow.
        if (p.their_height >= 0 && p.their_height < (int64_t)g_blocks.size() - 50) {
            continue; // skip — peer is still syncing, will get blocks via GETB
        }
        {
            std::lock_guard<std::mutex> wlk(*p.write_mu); // serialize with handle_peer writes
            p2p_send(p.fd, "BLCK", (const uint8_t*)js.data(), js.size());
        }
        ++sent;
    }
    if (sent > 0) {
        printf("[P2P] Broadcasting block #%lld to %d peers\n", (long long)sb.height, sent);
        fflush(stdout);
    }
}

// === ORPHAN PROCESSING ===
// When a new block is accepted, check if any orphan blocks were waiting for it
static void process_orphans_for_parent(const std::string& parent_hash_hex) {
    std::vector<std::string> to_process;
    {
        std::lock_guard<std::mutex> lk(g_block_index_mu);
        auto range = g_orphans_by_prev.equal_range(parent_hash_hex);
        for (auto it = range.first; it != range.second; ++it) {
            to_process.push_back(it->second);
        }
        g_orphans_by_prev.erase(parent_hash_hex);
    }

    for (const auto& orphan_hash : to_process) {
        std::string raw_json;
        {
            std::lock_guard<std::mutex> lk(g_block_index_mu);
            auto it = g_block_index.find(orphan_hash);
            if (it != g_block_index.end() && it->second.status == BlockStatus::ORPHAN) {
                raw_json = it->second.raw_json;
                g_block_index.erase(it); // Remove from index before re-processing
            }
        }
        if (!raw_json.empty()) {
            printf("[ORPHAN] Re-processing orphan block %s (parent now available)\n",
                   orphan_hash.substr(0,16).c_str());
            process_block(raw_json);
        }
    }
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
                    printf("[SYNC] Peer %s has height %lld, we have %lld — requesting blocks %lld..%lld\n",
                           addr.c_str(), (long long)their_h, (long long)g_chain_height,
                           (long long)(g_chain_height+1), (long long)their_h);
                    uint8_t buf[8];
                    write_i64(buf, g_chain_height+1);
                    p2p_send_adaptive(fd, crypto, "GETB", buf, 8);
                }
            }
        }
        else if(!strcmp(msg.cmd,"VACK")) {
            int64_t their_h = -1;
            {
                std::lock_guard<std::mutex> lk(g_peers_mu);
                for(auto& p:g_peers) if(p.fd==fd){p.version_acked=true; their_h=p.their_height; break;}
            }
            // If peer has more blocks, initiate sync
            if(their_h > g_chain_height){
                printf("[SYNC] Peer %s has height %lld, we have %lld — requesting blocks %lld..%lld\n",
                       addr.c_str(), (long long)their_h, (long long)g_chain_height,
                       (long long)(g_chain_height+1), (long long)their_h);
                uint8_t buf[8];
                write_i64(buf, g_chain_height+1);
                p2p_send_adaptive(fd, crypto, "GETB", buf, 8);
            }
        }
        else if(!strcmp(msg.cmd,"GETB")) {
            if(msg.payload.size()>=8){
                int64_t from_h=read_i64(msg.payload.data());
                auto wmu = get_peer_write_mu(fd);
                if (wmu) {
                    std::lock_guard<std::mutex> wlk(*wmu); // block broadcasts while sending batch
                    for(int64_t h=from_h;h<=g_chain_height && h<from_h+500;++h){
                        p2p_send_block(fd, h, &crypto); // use encryption if available
                    }
                    p2p_send_adaptive(fd, crypto, "DONE", nullptr, 0);
                } else {
                    for(int64_t h=from_h;h<=g_chain_height && h<from_h+500;++h){
                        p2p_send_block(fd, h, &crypto);
                    }
                    p2p_send_adaptive(fd, crypto, "DONE", nullptr, 0);
                }
            }
        }
        else if(!strcmp(msg.cmd,"BLCK")) {
          try {
            // Rate limiting: check blocks per minute
            // Sync mode if EITHER side is far ahead (both directions need fast transfer)
            // Case 1: peer ahead of us → we're catching up from them
            // Case 2: we're ahead of peer → they're catching up, may relay blocks back
            bool is_syncing = false;
            {
                std::lock_guard<std::mutex> lk(g_peers_mu);
                for (auto& p : g_peers) {
                    if (p.fd == fd) {
                        is_syncing = (p.their_height < 0) || // handshake not complete
                                     (p.their_height > g_chain_height) || // peer ahead → still syncing
                                     (g_chain_height > p.their_height + 10);
                        break;
                    }
                }
            }
            if (!check_block_rate(fd, is_syncing)) {
                if (is_syncing) {
                    // In sync mode: NEVER penalize — just throttle silently
                    continue;
                }
                printf("[P2P] Rate limit exceeded from %s (mode=relay)\n", addr.c_str());
                if (add_misbehavior(fd, addr, 5, "block rate limit")) break;
                continue;
            }

            std::string block_json((char*)msg.payload.data(), msg.payload.size());

            // Check if block is already known BEFORE expensive validation
            // This is normal relay behavior — NOT misbehavior
            std::string blk_bid_check = jstr(block_json, "block_id");
            {
                std::lock_guard<std::mutex> lk3(g_known_mu);
                if (blk_bid_check.size() == 64 && g_known_blocks.count(blk_bid_check)) {
                    continue; // silently skip — normal relay, no penalty
                }
            }

            int64_t blk_height = jint(block_json, "height");
            auto t_start = std::chrono::steady_clock::now();
            if(!process_block(block_json)){
                // process_block returned false — determine severity
                // Only penalize for genuinely invalid blocks, NOT for forks with less work
                std::string blk_bid = jstr(block_json, "block_id");
                uint32_t blk_bitsq = (uint32_t)jint(block_json, "bits_q");

                // Check if this block was stored as fork/orphan (not an error)
                bool stored_as_fork = false;
                {
                    std::lock_guard<std::mutex> lk3(g_known_mu);
                    stored_as_fork = g_known_blocks.count(blk_bid) > 0;
                }

                if (stored_as_fork) {
                    // Block was valid but stored as fork/orphan — no penalty
                } else if (blk_bid.size() != 64) {
                    if (add_misbehavior(fd, addr, 25, "malformed block")) break;
                } else if (blk_bitsq == 0) {
                    if (add_misbehavior(fd, addr, 100, "zero difficulty")) break;
                } else {
                    // Genuinely invalid block during sync — stop syncing from this peer
                    printf("[SYNC] Block #%lld from %s failed validation — stopping sync\n",
                           (long long)blk_height, addr.c_str());
                    if (add_misbehavior(fd, addr, 10, "invalid block")) break;
                }
            } else {
                if (is_syncing) {
                    printf("[SYNC] Received block #%lld from %s\n", (long long)blk_height, addr.c_str());
                }
                auto t_end = std::chrono::steady_clock::now();
                auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(t_end - t_start).count();
                if (ms > 100) {
                    printf("[P2P] Warning: block processing took %lldms from %s\n", (long long)ms, addr.c_str());
                }
            }
          } catch (const std::exception& e) {
            fprintf(stderr, "[ERROR] BLCK handler exception from %s: %s\n", addr.c_str(), e.what());
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
            printf("[P2PDBG] DONE received from %s: our_height=%lld, their_height=%lld, blocks_size=%zu\n",
                   addr.c_str(), (long long)g_chain_height, (long long)their_h, g_blocks.size());
            if(g_chain_height<their_h){
                printf("[SYNC] Batch done from %s. Requesting blocks %lld..%lld\n",
                       addr.c_str(), (long long)(g_chain_height+1), (long long)their_h);
                uint8_t buf[8];
                write_i64(buf, g_chain_height+1);
                p2p_send_adaptive(fd, crypto, "GETB", buf, 8);
            } else {
                printf("[SYNC] Sync complete: height %lld\n",(long long)g_chain_height);
            }
        }
        else {
            if(add_misbehavior(fd, addr, 10, "unknown command")) break;
        }
    }

    close(fd);
    cleanup_peer_rate(fd);
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

    // Compute genesis cumulative chainwork
    g.cumulative_work = compute_block_work(g.bits_q);

    g_genesis_hash=g.block_id;
    g_blocks.push_back(g);
    g_chain_height=0;

    // Mark genesis as known
    mark_block_known(to_hex(g.block_id.data(),32));

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
        // Transcript V2 fields
        sb.x_bytes_hex=jstr(bj,"x_bytes");
        sb.final_state_hex=jstr(bj,"final_state");
        sb.segments_root_hex=jstr(bj,"segments_root");
        sb.stab_scale=(int32_t)jint(bj,"stab_scale");
        sb.stab_k=(int32_t)jint(bj,"stab_k");
        sb.stab_margin=(int32_t)jint(bj,"stab_margin");
        sb.stab_steps=(int32_t)jint(bj,"stab_steps");
        sb.stab_lr_shift=(int32_t)jint(bj,"stab_lr_shift");
        sb.raw_block_json=bj; // preserve full JSON for P2P relay

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
                    // Compute cumulative chainwork
                    Bytes32 bw = compute_block_work(sb.bits_q);
                    Bytes32 parent_cw = g_blocks.empty() ? Bytes32{} : g_blocks.back().cumulative_work;
                    sb.cumulative_work = add_be256(parent_cw, bw);
                    g_block_undos.push_back(undo); // Store undo for reorg support
                    g_blocks.push_back(sb);
                    mark_block_known(bid);
                    continue;  // skip the legacy coinbase-only path below
                } else {
                    printf("[CHAIN-LOAD] Warning: ConnectBlock failed at height %lld: %s (falling back)\n",
                           (long long)height, uerr.c_str());
                }
            }
        }

        // LEGACY fallback: no transactions field → reconstruct coinbase only
        g_tx_index[sb.block_id] = {height, 0};  // TX-INDEX: pseudo-index
        // Compute cumulative chainwork
        Bytes32 bw = compute_block_work(sb.bits_q);
        Bytes32 parent_cw = g_blocks.empty() ? Bytes32{} : g_blocks.back().cumulative_work;
        sb.cumulative_work = add_be256(parent_cw, bw);
        g_blocks.push_back(sb);
        mark_block_known(bid);
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
    // Log chainwork for tip (skip leading zeros for readability)
    if (!g_blocks.empty()) {
        std::string cw_hex = to_hex(g_blocks.back().cumulative_work.data(), 32);
        size_t cw_nz = cw_hex.find_first_not_of('0');
        std::string cw_short = (cw_nz == std::string::npos) ? "0" : cw_hex.substr(cw_nz);
        printf("[CHAIN-LOAD] Tip chainwork: 0x%s (height=%lld, work/block=0x%x)\n",
               cw_short.c_str(), (long long)g_chain_height,
               (unsigned)compute_block_work(g_blocks.back().bits_q)[31] |
               ((unsigned)compute_block_work(g_blocks.back().bits_q)[30] << 8) |
               ((unsigned)compute_block_work(g_blocks.back().bits_q)[29] << 16));
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
        // Set socket options for high-latency resilience
        {
            int flag=1;
            setsockopt(cl, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));
            struct timeval rtv={30,0}; // 30s recv timeout (handles 300ms+ ping)
            setsockopt(cl, SOL_SOCKET, SO_RCVTIMEO, &rtv, sizeof(rtv));
            struct timeval stv={30,0}; // 30s send timeout
            setsockopt(cl, SOL_SOCKET, SO_SNDTIMEO, &stv, sizeof(stv));
            int bufsize=262144; // 256KB socket buffer
            setsockopt(cl, SOL_SOCKET, SO_RCVBUF, &bufsize, sizeof(bufsize));
            setsockopt(cl, SOL_SOCKET, SO_SNDBUF, &bufsize, sizeof(bufsize));
        }
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

        // Eclipse attack detection: warn if all peers are in same /16
        {
            std::lock_guard<std::mutex> lk2(g_peers_mu);
            if (g_peers.size() >= 4) {
                std::set<std::string> subnets;
                for (const auto& p : g_peers) {
                    std::string pip = peer_ip(p.addr);
                    auto dot1 = pip.find('.');
                    if (dot1 != std::string::npos) {
                        auto dot2 = pip.find('.', dot1+1);
                        if (dot2 != std::string::npos)
                            subnets.insert(pip.substr(0, dot2));
                    }
                }
                if (subnets.size() == 1) {
                    printf("[P2P] Warning: all %zu peers in same /16 subnet (%s) — possible eclipse attack\n",
                           g_peers.size(), subnets.begin()->c_str());
                } else if (subnets.size() <= 2 && g_peers.size() >= 8) {
                    printf("[P2P] Warning: peer diversity low (%zu subnets for %zu peers)\n",
                           subnets.size(), g_peers.size());
                }
            }
        }
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
    if (g_blocks.empty()) return true; // nothing to save
    // Atomic write: write to .tmp then rename to avoid corruption on crash
    std::string tmp_path = path + ".tmp";
    std::ofstream f(tmp_path); if (!f) return false;
    f << "{\n  \"chain_height\": " << g_chain_height
      << ",\n  \"tip\": \"" << to_hex(g_blocks.back().block_id.data(),32)
      << "\",\n  \"blocks\": [\n";
    for (size_t i = 0; i < g_blocks.size(); ++i) {
        const auto& b = g_blocks[i];
        if (!b.raw_block_json.empty()) {
            // Write complete original JSON — preserves ALL Transcript V2 proof data
            // (checkpoint_leaves, segment_proofs, round_witnesses)
            f << "    " << b.raw_block_json;
        } else {
            // Fallback reconstruction for genesis/legacy blocks without raw JSON
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

            if (!b.x_bytes_hex.empty()) f << ",\"x_bytes\":\"" << b.x_bytes_hex << "\"";
            if (!b.final_state_hex.empty()) f << ",\"final_state\":\"" << b.final_state_hex << "\"";
            if (!b.segments_root_hex.empty()) f << ",\"segments_root\":\"" << b.segments_root_hex << "\"";
            if (b.stab_scale > 0) {
                f << ",\"stab_scale\":" << b.stab_scale
                  << ",\"stab_k\":" << b.stab_k
                  << ",\"stab_margin\":" << b.stab_margin
                  << ",\"stab_steps\":" << b.stab_steps;
                if (b.stab_lr_shift > 0) f << ",\"stab_lr_shift\":" << b.stab_lr_shift;
            }
            if (!b.tx_hexes.empty()) {
                f << ",\"transactions\":[";
                for (size_t t = 0; t < b.tx_hexes.size(); ++t) {
                    if (t) f << ",";
                    f << "\"" << b.tx_hexes[t] << "\"";
                }
                f << "]";
            }
            f << "}";
        }
        f << (i + 1 < g_blocks.size() ? ",\n" : "\n");
    }
    f << "  ]\n}\n";
    f.flush();
    if (!f.good()) return false;
    f.close();
    // Atomic rename: tmp → final (prevents corruption on crash mid-write)
    if (std::rename(tmp_path.c_str(), path.c_str()) != 0) {
        perror("[SAVE] rename failed");
        return false;
    }
    return true;
}

// Public save — acquires lock, then delegates to internal
static bool save_chain(const std::string& path) {
    std::lock_guard<std::recursive_mutex> lk(g_chain_mu);
    return save_chain_internal(path);
}

// =============================================================================
// Crash diagnostics — signal handler
// =============================================================================
static void crash_handler(int sig) {
    const char* name = "UNKNOWN";
    if (sig == SIGSEGV) name = "SIGSEGV";
    else if (sig == SIGABRT) name = "SIGABRT";
    else if (sig == SIGFPE)  name = "SIGFPE";
    time_t now = time(nullptr);
    std::string tip_hex = g_blocks.empty() ? "none" : to_hex(g_blocks.back().block_id.data(), 32);
    fprintf(stderr, "[CRASH] Signal %s (%d) at timestamp %lld. Chain height=%lld, tip=%s, blocks=%zu\n",
            name, sig, (long long)now, (long long)g_chain_height, tip_hex.c_str(), g_blocks.size());
    fflush(stderr);
    // Re-raise to get core dump
    signal(sig, SIG_DFL);
    raise(sig);
}

// =============================================================================
// main
// =============================================================================
int main(int argc, char** argv) {
    // Crash diagnostics
    signal(SIGSEGV, crash_handler);
    signal(SIGABRT, crash_handler);
    signal(SIGFPE,  crash_handler);
    setbuf(stdout, NULL); // unbuffered for crash visibility

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
        else if(!strcmp(argv[i],"--verbose")||!strcmp(argv[i],"-v")){
            g_verbose = true;
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
            printf("  --p2p-enc off|on|required      P2P encryption mode (default: off)\n");
            printf("  --full-verify              Force full ConvergenceX verification (no fast sync)\n");
            printf("  --no-fast-sync             Same as --full-verify\n");
            printf("  --verbose / -v             Show CX-VERIFY and PARSE debug output\n");
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
    // Load dynamic checkpoints (override hardcoded if file exists)
    sost::load_dynamic_checkpoints();

    printf("=== SOST Node v0.4.0 ===\n");
    printf("Profile: %s | P2P: %d | RPC: %d | RPC auth: %s | P2P enc: %s | Fast sync: %s\n",
           profile_name, p2p_port, rpc_port,
           g_rpc_auth_required ? "ON" : "OFF", enc_str,
           g_full_verify_mode ? "OFF (--full-verify)" : "ON");
    printf("Assumevalid: height=%u hash=%s\n\n",
           sost::get_assumevalid_height(),
           sost::get_assumevalid_hash().substr(0,16).c_str());

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

    // Load PoPC registry (optional — missing file is not an error)
    {
        std::string popc_err;
        if (!g_popc_registry.load(g_popc_registry_path, &popc_err)) {
            printf("Warning: PoPC registry load failed: %s\n", popc_err.c_str());
        } else {
            printf("PoPC registry: %zu active commitments\n", g_popc_registry.active_count());
        }
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
    try {
        while(g_running){
            std::this_thread::sleep_for(std::chrono::seconds(30));
            {
                std::lock_guard<std::mutex> lk(g_peers_mu);
                for(auto& p:g_peers){
                    // Skip syncing peers — writing PING while GETB handler
                    // is sending blocks corrupts the TCP stream (race condition)
                    if(p.their_height >= 0 && p.their_height < (int64_t)g_blocks.size() - 50)
                        continue;
                    if(p.version_acked) p2p_send(p.fd,"PING",nullptr,0);
                }
            }
            if(!chain_path.empty()) save_chain(chain_path);
            g_popc_registry.save(g_popc_registry_path, nullptr); // best-effort periodic save
        }
    } catch (const std::exception& e) {
        fprintf(stderr, "[CRASH] Main loop exception: %s (height=%lld)\n",
                e.what(), (long long)g_chain_height);
        throw;
    }

    return 0;
}
