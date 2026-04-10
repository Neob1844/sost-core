// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// sost-miner.cpp — SOST Block Miner v0.5
//
// Miner ConvergenceX with:
//   - Real coinbase tx
//   - Real merkle root
//   - Mempool tx inclusion via getblocktemplate RPC
//   - Submits FULL block to node (including commit/checkpoints_root/extra_nonce/txs)
//   - Supports RPC Basic Auth

#include "sost/types.h"
#include "sost/params.h"
#include "sost/pow/convergencex.h"
#include "sost/pow/casert.h"
#include "sost/pow/scratchpad.h"
#include "sost/sostcompact.h"
#include "sost/serialize.h"
#include "sost/emission.h"
#include "sost/subsidy.h"
#include "sost/block_validation.h"
#include "sost/transaction.h"
#include "sost/merkle.h"
#include "sost/address.h"

#include <fstream>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <atomic>
#include <thread>
#include <chrono>
#include <ctime>
#include <string>
#include <vector>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>

using namespace sost;

// =============================================================================
// Chain state
// =============================================================================
static std::vector<BlockMeta> g_chain;
static Bytes32 g_tip_hash;

struct MinedBlock {
    Bytes32  block_id, prev_hash, merkle_root, commit, checkpoints_root, segments_root;
    int64_t  height, timestamp, subsidy;
    uint32_t bits_q, nonce, extra_nonce;
    uint64_t stability_metric;
    int64_t  miner_reward, gold_vault_reward, popc_pool_reward;
    // Mining profile (actual params used, including any anti-stall decay)
    int32_t stab_scale, stab_k, stab_margin, stab_steps, stab_lr_shift;
    int32_t profile_index{0}; // committed to block hash
    std::vector<uint8_t> x_bytes;
    Bytes32 final_state;
    std::vector<Bytes32> checkpoint_leaves;
    std::vector<SegmentProof> segment_proofs;
    std::vector<RoundWitness> round_witnesses;
};
static std::vector<MinedBlock> g_mined_blocks;

// RPC mode
static std::string g_rpc_url = "";
static std::string g_rpc_user = "";
static std::string g_rpc_pass = "";

// Miner payout address
static std::string g_miner_address = "";
static PubKeyHash  g_miner_pkh{};

// =============================================================================
// Full header builder (same as genesis.cpp / node.cpp)
// =============================================================================
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

static void build_hc72(uint8_t out[72],
                       const Bytes32& prev, const Bytes32& mrkl,
                       uint32_t ts, uint32_t bits) {
    std::memcpy(out, prev.data(), 32);
    std::memcpy(out + 32, mrkl.data(), 32);
    write_u32_le(out + 64, ts);
    write_u32_le(out + 68, bits);
}

// =============================================================================
// Hex helper
// =============================================================================
static std::string to_hex_str(const uint8_t* d, size_t len) {
    static const char* hx = "0123456789abcdef";
    std::string s; s.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) { s += hx[d[i] >> 4]; s += hx[d[i] & 0xF]; }
    return s;
}

// =============================================================================
// Base64 encode (Basic Auth)
// =============================================================================
static std::string base64_encode(const std::string& in) {
    static const char* b64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    int val=0, valb=-6;
    for(unsigned char c : in){
        val = (val<<8) + c;
        valb += 8;
        while(valb>=0){
            out.push_back(b64[(val>>valb)&0x3F]);
            valb -= 6;
        }
    }
    if(valb>-6) out.push_back(b64[((val<<8)>>(valb+8))&0x3F]);
    while(out.size()%4) out.push_back('=');
    return out;
}

static std::string rpc_auth_header() {
    if(g_rpc_user.empty() && g_rpc_pass.empty()) return "";
    std::string token = base64_encode(g_rpc_user + ":" + g_rpc_pass);
    return "Authorization: Basic " + token + "\r\n";
}

// =============================================================================
// Coinbase transaction builder
// =============================================================================
static Transaction build_coinbase_tx(int64_t height, int64_t total_reward, const CoinbaseSplit& split,
                                     const PubKeyHash& miner_pkh) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;

    TxInput cin;
    cin.prev_txid.fill(0);
    cin.prev_index = 0xFFFFFFFF;
    cin.signature.fill(0);
    cin.pubkey.fill(0);
    for (int i = 0; i < 8; ++i)
        cin.signature[i] = (uint8_t)((height >> (i * 8)) & 0xFF);
    tx.inputs.push_back(cin);

    TxOutput out_miner;
    out_miner.amount = split.miner;
    out_miner.type = OUT_COINBASE_MINER;
    out_miner.pubkey_hash = miner_pkh;
    tx.outputs.push_back(out_miner);

    TxOutput out_gold;
    out_gold.amount = split.gold_vault;
    out_gold.type = OUT_COINBASE_GOLD;
    address_decode(ADDR_GOLD_VAULT, out_gold.pubkey_hash);
    tx.outputs.push_back(out_gold);

    TxOutput out_popc;
    out_popc.amount = split.popc_pool;
    out_popc.type = OUT_COINBASE_POPC;
    address_decode(ADDR_POPC_POOL, out_popc.pubkey_hash);
    tx.outputs.push_back(out_popc);

    return tx;
}

// =============================================================================
// JSON helpers (very small)
// =============================================================================
static std::string jstr(const std::string& j, const std::string& k) {
    std::string n = "\"" + k + "\"";
    auto p = j.find(n); if (p == std::string::npos) return "";
    p = j.find('"', p + n.size() + 1); if (p == std::string::npos) return "";
    auto e = j.find('"', p + 1); if (e == std::string::npos) return "";
    return j.substr(p + 1, e - p - 1);
}
static int64_t jint(const std::string& j, const std::string& k) {
    std::string n = "\"" + k + "\"";
    auto p = j.find(n); if (p == std::string::npos) return -1;
    p = j.find(':', p + n.size()); if (p == std::string::npos) return -1;
    p++; while (p < j.size() && j[p] == ' ') p++;
    return std::stoll(j.substr(p));
}

// =============================================================================
// Genesis loader
// =============================================================================
static bool load_genesis(const std::string& path) {
    std::ifstream f(path); if (!f) return false;
    std::string json((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    std::string bid = jstr(json, "block_id"); if (bid.size() != 64) return false;

    BlockMeta gm;
    gm.block_id = from_hex(bid);
    gm.height = 0;
    gm.time = jint(json, "timestamp");
    gm.powDiffQ = (uint32_t)jint(json, "bits_q");
    g_chain.push_back(gm);
    g_tip_hash = gm.block_id;

    MinedBlock gb{};
    gb.block_id = gm.block_id;
    gb.prev_hash = from_hex(jstr(json, "prev_hash"));
    gb.merkle_root = from_hex(jstr(json, "merkle_root"));
    gb.commit = from_hex(jstr(json, "commit"));
    gb.checkpoints_root = from_hex(jstr(json, "checkpoints_root"));
    gb.height = 0; gb.timestamp = gm.time; gb.bits_q = gm.powDiffQ;
    gb.nonce = (uint32_t)jint(json, "nonce");
    gb.extra_nonce = (uint32_t)jint(json, "extra_nonce");
    gb.stability_metric = (uint64_t)jint(json, "stability_metric");
    gb.subsidy = jint(json, "subsidy_stocks");
    auto sp = coinbase_split(gb.subsidy);
    gb.miner_reward = sp.miner; gb.gold_vault_reward = sp.gold_vault; gb.popc_pool_reward = sp.popc_pool;
    g_mined_blocks.push_back(gb);
    return true;
}

// =============================================================================
// Chain saver
// =============================================================================
static bool save_chain(const std::string& path) {
    std::string tmp = path + ".tmp";
    std::ofstream f(tmp); if (!f) return false;
    f << "{\n  \"chain_height\": " << (int64_t)(g_chain.size() - 1)
      << ",\n  \"tip\": \"" << hex(g_tip_hash) << "\",\n  \"blocks\": [\n";
    for (size_t i = 0; i < g_mined_blocks.size(); ++i) {
        const auto& b = g_mined_blocks[i];
        f << "    {\"block_id\":\"" << hex(b.block_id) << "\",\"prev_hash\":\"" << hex(b.prev_hash)
          << "\",\"merkle_root\":\"" << hex(b.merkle_root)
          << "\",\"commit\":\"" << hex(b.commit)
          << "\",\"checkpoints_root\":\"" << hex(b.checkpoints_root)
          << "\",\"height\":" << b.height << ",\"timestamp\":" << b.timestamp
          << ",\"bits_q\":" << b.bits_q << ",\"nonce\":" << b.nonce
          << ",\"extra_nonce\":" << b.extra_nonce << ",\"subsidy\":" << b.subsidy
          << ",\"miner\":" << b.miner_reward << ",\"gold_vault\":" << b.gold_vault_reward
          << ",\"popc_pool\":" << b.popc_pool_reward
          << ",\"stability_metric\":" << b.stability_metric << "}"
          << (i + 1 < g_mined_blocks.size() ? ",\n" : "\n");
    }
    f << "  ]\n}\n";
    f.flush();
    if (!f.good()) return false;
    f.close();
    return std::rename(tmp.c_str(), path.c_str()) == 0;
}

// =============================================================================
// RPC: generic call to node — returns HTTP response body
// =============================================================================
static std::string rpc_call(const std::string& method, const std::string& params = "[]") {
    if (g_rpc_url.empty()) return "";
    std::string host = "127.0.0.1";
    int port = 18232;
    auto colon = g_rpc_url.find(':');
    if (colon != std::string::npos) {
        host = g_rpc_url.substr(0, colon);
        port = atoi(g_rpc_url.substr(colon + 1).c_str());
    }
    std::string body = "{\"method\":\"" + method + "\",\"params\":" + params + ",\"id\":1}";
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return "";
    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    struct hostent* he = gethostbyname(host.c_str());
    if (!he) { close(fd); return ""; }
    memcpy(&addr.sin_addr, he->h_addr_list[0], he->h_length);
    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) { close(fd); return ""; }

    std::string req = "POST / HTTP/1.1\r\nHost: " + host + "\r\nContent-Type: application/json\r\n"
        + rpc_auth_header()
        + "Content-Length: " + std::to_string(body.size()) + "\r\n\r\n" + body;

    write(fd, req.c_str(), req.size());

    std::string response;
    char rbuf[8192];
    struct timeval tv; tv.tv_sec = 5; tv.tv_usec = 0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    while (true) {
        ssize_t n = read(fd, rbuf, sizeof(rbuf) - 1);
        if (n <= 0) break;
        rbuf[n] = 0;
        response.append(rbuf, n);
        auto hdr_end = response.find("\r\n\r\n");
        if (hdr_end != std::string::npos) {
            auto cl_pos = response.find("Content-Length:");
            if (cl_pos == std::string::npos) cl_pos = response.find("content-length:");
            if (cl_pos != std::string::npos) {
                int cl = atoi(response.c_str() + cl_pos + 15);
                if ((int)(response.size() - hdr_end - 4) >= cl) break;
            } else break;
        }
    }
    close(fd);
    auto bp = response.find("\r\n\r\n");
    if (bp == std::string::npos) return "";
    return response.substr(bp + 4);
}

// =============================================================================
// Fetch block template from node (mempool txs + fees)
// =============================================================================
struct BlockTemplateResult {
    std::vector<std::vector<uint8_t>> tx_raws;
    std::vector<std::string> tx_hexes;
    int64_t total_fees;
    int count;
};

static int hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + c - 'a';
    if (c >= 'A' && c <= 'F') return 10 + c - 'A';
    return -1;
}
static bool hex_to_raw(const std::string& h, std::vector<uint8_t>& out) {
    if (h.size() % 2 != 0) return false;
    out.clear();
    out.reserve(h.size() / 2);
    for (size_t i = 0; i < h.size(); i += 2) {
        int hi = hex_val(h[i]), lo = hex_val(h[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back((uint8_t)((hi << 4) | lo));
    }
    return true;
}

static BlockTemplateResult fetch_block_template() {
    BlockTemplateResult result;
    result.total_fees = 0;
    result.count = 0;

    std::string resp = rpc_call("getblocktemplate");
    if (resp.empty()) return result;

    int64_t fees_val = jint(resp, "total_fees");
    result.total_fees = (fees_val > 0) ? fees_val : 0;

    auto tx_pos = resp.find("\"transactions\"");
    if (tx_pos == std::string::npos) return result;
    auto arr_start = resp.find('[', tx_pos);
    auto arr_end = resp.find(']', arr_start);
    if (arr_start == std::string::npos || arr_end == std::string::npos) return result;

    std::string arr = resp.substr(arr_start + 1, arr_end - arr_start - 1);
    size_t p = 0;
    while (p < arr.size()) {
        auto q1 = arr.find('"', p);
        if (q1 == std::string::npos) break;
        auto q2 = arr.find('"', q1 + 1);
        if (q2 == std::string::npos) break;
        std::string tx_hex = arr.substr(q1 + 1, q2 - q1 - 1);
        p = q2 + 1;

        if (tx_hex.empty() || tx_hex.size() % 2 != 0) continue;

        std::vector<uint8_t> raw;
        if (hex_to_raw(tx_hex, raw) && !raw.empty()) {
            result.tx_raws.push_back(raw);
            result.tx_hexes.push_back(tx_hex);
        }
    }
    result.count = (int)result.tx_raws.size();
    return result;
}

// =============================================================================
// RPC: submit FULL block to node
// =============================================================================
// Return values: 1 = accepted, 0 = rejected by node, -1 = connection failed
static int rpc_submit_block_full(
    const MinedBlock& mb,
    const std::vector<std::string>& tx_hexes_including_coinbase)
{
    if (g_rpc_url.empty()) return 0;

    std::string host = "127.0.0.1";
    int port = 18232;
    auto colon = g_rpc_url.find(':');
    if (colon != std::string::npos) {
        host = g_rpc_url.substr(0, colon);
        port = atoi(g_rpc_url.substr(colon + 1).c_str());
    }

    // Build block JSON for node (must match node parser)
    std::string bj = "{\"block_id\":\"" + hex(mb.block_id)
        + "\",\"prev_hash\":\"" + hex(mb.prev_hash)
        + "\",\"merkle_root\":\"" + hex(mb.merkle_root)
        + "\",\"commit\":\"" + hex(mb.commit)
        + "\",\"checkpoints_root\":\"" + hex(mb.checkpoints_root)
        + "\",\"height\":" + std::to_string(mb.height)
        + ",\"timestamp\":" + std::to_string(mb.timestamp)
        + ",\"bits_q\":" + std::to_string(mb.bits_q)
        + ",\"nonce\":" + std::to_string(mb.nonce)
        + ",\"extra_nonce\":" + std::to_string(mb.extra_nonce)
        + ",\"subsidy\":" + std::to_string(mb.subsidy)
        + ",\"miner\":" + std::to_string(mb.miner_reward)
        + ",\"gold_vault\":" + std::to_string(mb.gold_vault_reward)
        + ",\"popc_pool\":" + std::to_string(mb.popc_pool_reward)
        + ",\"stability_metric\":" + std::to_string(mb.stability_metric)
        + ",\"stab_scale\":" + std::to_string(mb.stab_scale)
        + ",\"stab_k\":" + std::to_string(mb.stab_k)
        + ",\"stab_margin\":" + std::to_string(mb.stab_margin)
        + ",\"stab_steps\":" + std::to_string(mb.stab_steps)
        + ",\"stab_lr_shift\":" + std::to_string(mb.stab_lr_shift)
        + ",\"profile_index\":" + std::to_string(mb.profile_index)
        + ",\"x_bytes\":\"" + to_hex_str(mb.x_bytes.data(), mb.x_bytes.size()) + "\""
        + ",\"final_state\":\"" + hex(mb.final_state) + "\""
        + ",\"segments_root\":\"" + hex(mb.segments_root) + "\"";

    // Checkpoint leaves
    bj += ",\"checkpoint_leaves\":[";
    for (size_t i = 0; i < mb.checkpoint_leaves.size(); ++i) {
        if (i) bj += ",";
        bj += "\"" + hex(mb.checkpoint_leaves[i]) + "\"";
    }
    bj += "]";

    // Segment proofs (Transcript V2)
    bj += ",\"segment_proofs\":[";
    for (size_t i = 0; i < mb.segment_proofs.size(); ++i) {
        if (i) bj += ",";
        const auto& sp = mb.segment_proofs[i];
        bj += "{\"si\":" + std::to_string(sp.leaf.segment_index)
            + ",\"rs\":" + std::to_string(sp.leaf.round_start)
            + ",\"re\":" + std::to_string(sp.leaf.round_end)
            + ",\"ss\":\"" + hex(sp.leaf.state_start) + "\""
            + ",\"se\":\"" + hex(sp.leaf.state_end) + "\""
            + ",\"xsh\":\"" + hex(sp.leaf.x_start_hash) + "\""
            + ",\"xeh\":\"" + hex(sp.leaf.x_end_hash) + "\""
            + ",\"rrs\":" + std::to_string(sp.leaf.residual_start)
            + ",\"rre\":" + std::to_string(sp.leaf.residual_end)
            + ",\"mp\":[";
        for (size_t j = 0; j < sp.merkle_path.size(); ++j) {
            if (j) bj += ",";
            bj += "\"" + hex(sp.merkle_path[j]) + "\"";
        }
        bj += "]}";
    }
    bj += "]";

    // Round witnesses (Transcript V2)
    bj += ",\"round_witnesses\":[";
    for (size_t i = 0; i < mb.round_witnesses.size(); ++i) {
        if (i) bj += ",";
        const auto& rw = mb.round_witnesses[i];
        bj += "{\"ri\":" + std::to_string(rw.round_index)
            + ",\"xb\":\""; for (int k = 0; k < 32; ++k) { uint8_t b[4]; write_i32_le(b, rw.x_before[k]); bj += to_hex_str(b, 4); }
        bj += "\",\"xa\":\""; for (int k = 0; k < 32; ++k) { uint8_t b[4]; write_i32_le(b, rw.x_after[k]); bj += to_hex_str(b, 4); }
        bj += "\",\"sb\":\"" + hex(rw.state_before) + "\""
            + ",\"sa\":\"" + hex(rw.state_after) + "\""
            + ",\"sv\":[" + std::to_string(rw.scratch_values[0]) + "," + std::to_string(rw.scratch_values[1])
            + "," + std::to_string(rw.scratch_values[2]) + "," + std::to_string(rw.scratch_values[3]) + "]"
            + ",\"si2\":[" + std::to_string(rw.scratch_indices[0]) + "," + std::to_string(rw.scratch_indices[1])
            + "," + std::to_string(rw.scratch_indices[2]) + "," + std::to_string(rw.scratch_indices[3]) + "]"
            + ",\"dv\":" + std::to_string(rw.dataset_value)
            + ",\"po\":" + std::to_string(rw.program_output)
            + "}";
    }
    bj += "]";

    bj += ",\"transactions\":[";
    for(size_t i=0;i<tx_hexes_including_coinbase.size();++i){
        if(i) bj += ",";
        bj += "\"" + tx_hexes_including_coinbase[i] + "\"";
    }
    bj += "]}";

    // Escape JSON for RPC param string
    std::string escaped;
    escaped.reserve(bj.size()*2);
    for (char c : bj) { if (c == '"') escaped += "\\\""; else escaped += c; }

    std::string body = "{\"method\":\"submitblock\",\"params\":[\"" + escaped + "\"],\"id\":1}";

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1; // connection failed

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);

    struct hostent* he = gethostbyname(host.c_str());
    if (!he) { close(fd); return -1; }
    memcpy(&addr.sin_addr, he->h_addr_list[0], he->h_length);

    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) { close(fd); return -1; }

    std::string req = "POST / HTTP/1.1\r\nHost: " + host
        + "\r\nContent-Type: application/json\r\n"
        + rpc_auth_header()
        + "Content-Length: " + std::to_string(body.size()) + "\r\n\r\n" + body;

    write(fd, req.c_str(), req.size());

    char rbuf[4096]{};
    ssize_t nr = read(fd, rbuf, sizeof(rbuf) - 1);
    close(fd);

    if (nr <= 0) return -1; // connection lost during read
    return std::string(rbuf).find("\"result\":true") != std::string::npos ? 1 : 0;
}

// =============================================================================
// Chain loader
// =============================================================================
static bool load_chain(const std::string& path) {
    std::ifstream f(path); if (!f) return false;
    std::string json((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    int64_t ch = jint(json, "chain_height"); if (ch < 0) return false;
    size_t search = json.find("\"blocks\""); if (search == std::string::npos) return false;
    search = json.find('[', search); if (search == std::string::npos) return false;

    while (true) {
        auto bs = json.find('{', search); if (bs == std::string::npos) break;
        auto be = json.find('}', bs); if (be == std::string::npos) break;
        std::string bj = json.substr(bs, be - bs + 1); search = be + 1;
        std::string bid = jstr(bj, "block_id"); if (bid.size() != 64) continue;
        int64_t height = jint(bj, "height"); if (height == 0) continue;

        BlockMeta bm;
        bm.block_id = from_hex(bid); bm.height = height;
        bm.time = jint(bj, "timestamp"); bm.powDiffQ = (uint32_t)jint(bj, "bits_q");
        g_chain.push_back(bm);

        MinedBlock mb{};
        mb.block_id = bm.block_id;
        mb.prev_hash = from_hex(jstr(bj, "prev_hash"));
        std::string mr = jstr(bj, "merkle_root");
        mb.merkle_root = mr.size() == 64 ? from_hex(mr) : Bytes32{};
        std::string cm = jstr(bj, "commit");
        mb.commit = cm.size()==64 ? from_hex(cm) : Bytes32{};
        std::string cr = jstr(bj, "checkpoints_root");
        mb.checkpoints_root = cr.size()==64 ? from_hex(cr) : Bytes32{};
        mb.height = height; mb.timestamp = bm.time; mb.bits_q = bm.powDiffQ;
        mb.nonce = (uint32_t)jint(bj, "nonce");
        mb.extra_nonce = (uint32_t)jint(bj, "extra_nonce");
        mb.subsidy = jint(bj, "subsidy");
        mb.miner_reward = jint(bj, "miner");
        mb.gold_vault_reward = jint(bj, "gold_vault");
        mb.popc_pool_reward = jint(bj, "popc_pool");
        mb.stability_metric = (uint64_t)jint(bj, "stability_metric");
        g_mined_blocks.push_back(mb);

        g_tip_hash = bm.block_id;
    }

    printf("Chain loaded: %zu blocks, height=%lld\n", g_chain.size(), (long long)(g_chain.size()-1));
    return true;
}

// =============================================================================
// Block monitor — background thread that detects new blocks instantly
// =============================================================================
static std::atomic<bool> g_chain_advanced{false};
static std::atomic<int64_t> g_monitor_height{0};
static std::atomic<bool> g_monitor_running{false};

static void start_block_monitor(int64_t mining_height) {
    g_chain_advanced = false;
    g_monitor_height = mining_height;
    if (g_monitor_running || g_rpc_url.empty()) return;
    g_monitor_running = true;
    std::thread([]{
        while (g_monitor_running) {
            std::this_thread::sleep_for(std::chrono::seconds(2));
            if (!g_monitor_running) break;
            std::string resp = rpc_call("getblockcount");
            if (!resp.empty()) {
                auto rp = resp.find("\"result\":");
                if (rp != std::string::npos) {
                    int64_t node_h = atoll(resp.c_str() + rp + 9);
                    if (node_h >= g_monitor_height) {
                        g_chain_advanced = true;
                    }
                }
            }
        }
    }).detach();
}

static void stop_block_monitor() {
    g_monitor_running = false;
}

// =============================================================================
// Mine one block
// =============================================================================
static bool mine_one_block(Profile prof, uint32_t max_nonce, bool sim_time) {
    int64_t h = (int64_t)g_chain.size();
    int32_t epoch = (int32_t)(h / BLOCKS_PER_EPOCH);

    uint32_t bits_q = casert_next_bitsq(g_chain, h);
    // When mining with RPC, always use the node's difficulty (authoritative)
    // Local cASERT calculation can diverge if g_chain has pad entries from REJECTED recovery
    if (!g_rpc_url.empty()) {
        std::string info = rpc_call("getinfo");
        if (!info.empty()) {
            auto dp = info.find("\"next_difficulty\":");
            if (dp != std::string::npos) {
                uint32_t node_diff = (uint32_t)atoll(info.c_str() + dp + 18);
                if (node_diff > 0 && node_diff != bits_q) {
                    printf("[MINING] Local bitsQ=%u, node says %u — using node difficulty\n",
                           bits_q, node_diff);
                    bits_q = node_diff;
                }
            }
        }
    }
    ConsensusParams params = get_consensus_params(prof, h);
    auto cdec = casert_compute(g_chain, h, std::time(nullptr));
    params = casert_apply_profile(params, cdec);

    Bytes32 skey = epoch_scratch_key(epoch, &g_chain);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);
    Bytes32 bk = compute_block_key(g_tip_hash);

    int64_t ts;
    if (sim_time) ts = g_chain.back().time + TARGET_SPACING;
    else ts = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();

    int64_t subsidy = sost_subsidy_stocks(h);

    // Fetch mempool txs from node (RPC mode)
    int64_t total_fees = 0;
    std::vector<Transaction> mempool_txs;
    std::vector<std::string> mempool_tx_hexes;
    if (!g_rpc_url.empty()) {
        auto tmpl = fetch_block_template();
        if (tmpl.count > 0) {
            total_fees = tmpl.total_fees;
            for (size_t ti = 0; ti < tmpl.tx_raws.size(); ++ti) {
                Transaction tx;
                std::string derr;
                if (Transaction::Deserialize(tmpl.tx_raws[ti], tx, &derr)) {
                    mempool_txs.push_back(tx);
                    mempool_tx_hexes.push_back(tmpl.tx_hexes[ti]);
                } else {
                    printf("[MINER] WARNING: skip bad mempool tx: %s\n", derr.c_str());
                }
            }
            if (!mempool_txs.empty())
                printf("[MINER] Template: %zu txs, fees=%lld stocks\n", mempool_txs.size(), (long long)total_fees);
        }
    }

    // Coinbase = subsidy + fees, split 50/25/25
    int64_t total_reward = subsidy + total_fees;
    auto split = coinbase_split(total_reward);
    Transaction coinbase_tx = build_coinbase_tx(h, total_reward, split, g_miner_pkh);

    std::vector<Transaction> block_txs;
    block_txs.push_back(coinbase_tx);
    for (const auto& mtx : mempool_txs) block_txs.push_back(mtx);

    Hash256 mrkl;
    std::string merr;
    if (!ComputeMerkleRootFromTxs(block_txs, mrkl, &merr)) {
        printf("[ERROR] merkle root failed: %s\n", merr.c_str());
        return false;
    }

    printf("[MINING] h=%lld diff=%u sub=%lld fees=%lld merkle=%s txs=%zu\n",
           (long long)h, bits_q, (long long)subsidy, (long long)total_fees,
           hex(mrkl).substr(0, 16).c_str(), block_txs.size());

    uint8_t hc72[72];
    build_hc72(hc72, g_tip_hash, mrkl, (uint32_t)ts, bits_q);

    auto t0 = std::chrono::steady_clock::now();
    auto ts_last_update = t0;
    uint32_t extra_nonce = 0;
    bool found = false;

    // Pre-serialize coinbase for submitblock (we update if extra_nonce changes, but we keep same tx here)
    std::vector<Byte> cb_raw;
    std::string cb_ser_err;
    coinbase_tx.Serialize(cb_raw, &cb_ser_err);
    std::string coinbase_hex = to_hex_str(cb_raw.data(), cb_raw.size());

    // Diagnostic counters
    uint32_t diag_stable = 0, diag_target = 0, diag_total = 0;

    printf("[DIAG] Mining h=%lld prev=%s bitsQ=%u (%.4f) profile: scale=%d k=%d margin=%d steps=%d\n",
           (long long)h, hex(g_tip_hash).substr(0,16).c_str(), bits_q, bits_q/65536.0,
           params.stab_scale, params.stab_k, params.stab_margin, params.stab_steps);
    fflush(stdout);

    // Start background monitor that checks for new blocks every 2s
    start_block_monitor(h);

    while (!found) {
        for (uint32_t nonce = 0; nonce <= max_nonce; ++nonce) {
            if ((nonce % 1000) == 0 && nonce > 0) {
                if (diag_total > 0 && (diag_total % 1000) == 0) {
                    printf("\n[DIAG] nonce=%u stable=%u/1000 target=%u/1000 (total: %u stable, %u target)\n",
                           nonce + extra_nonce * max_nonce, diag_stable, diag_target,
                           diag_stable, diag_target);
                    fflush(stdout);
                    diag_stable = 0; diag_target = 0; diag_total = 0;
                }
            }
            // Instant abort: background thread detected chain advanced
            if (g_chain_advanced) {
                printf("\n[MINING] New block detected! Aborting mining of %lld\n", (long long)h);
                fflush(stdout);
                stop_block_monitor();
                // Fetch current state from node
                std::string info_check = rpc_call("getinfo");
                std::string best = rpc_call("getbestblockhash");
                if (!info_check.empty()) {
                    auto bp2 = info_check.find("\"blocks\":");
                    int64_t cur_h = (bp2 != std::string::npos) ? atoll(info_check.c_str() + bp2 + 9) : h;
                    auto rp2 = best.find("\"result\":\"");
                    if (rp2 != std::string::npos) {
                        std::string th = best.substr(rp2 + 10, 64);
                        if (th.size() == 64) {
                            Bytes32 nt{};
                            for (int i2=0;i2<32;++i2){unsigned int by;sscanf(th.c_str()+i2*2,"%02x",&by);nt[i2]=(uint8_t)by;}
                            g_tip_hash = nt;
                        }
                    }
                    auto dp2 = info_check.find("\"next_difficulty\":");
                    uint32_t nd = 0;
                    if (dp2 != std::string::npos) nd = (uint32_t)atoll(info_check.c_str() + dp2 + 18);
                    while ((int64_t)g_chain.size() - 1 < cur_h) {
                        BlockMeta pad{}; pad.height=(int64_t)g_chain.size(); pad.time=(int64_t)time(nullptr);
                        pad.powDiffQ = nd > 0 ? nd : bits_q; g_chain.push_back(pad);
                    }
                }
                return false; // restart at new height
            }

            // Refresh timestamp periodically
            if ((nonce % 5000) == 0 && nonce > 0) {
                printf("\r  nonce=%u extra=%u", nonce, extra_nonce); fflush(stdout);
                if (!sim_time) {
                    auto now_check = std::chrono::steady_clock::now();
                    auto since_update = std::chrono::duration_cast<std::chrono::seconds>(now_check - ts_last_update).count();
                    if (since_update >= 30) {
                        ts = std::chrono::duration_cast<std::chrono::seconds>(
                            std::chrono::system_clock::now().time_since_epoch()).count();
                        build_hc72(hc72, g_tip_hash, mrkl, (uint32_t)ts, bits_q);
                        ts_last_update = now_check;
                    }
                }
            }

            auto res = convergencex_attempt(
                scratch.data(), scratch.size(), bk,
                nonce, extra_nonce,
                params, hc72, epoch);

            diag_total++;
            if (res.is_stable) diag_stable++;
            if (pow_meets_target(res.commit, bits_q)) diag_target++;

            if (res.is_stable && pow_meets_target(res.commit, bits_q)) {
                auto t1 = std::chrono::steady_clock::now();
                auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();

                auto full_hdr = build_full_header_bytes(hc72, res.checkpoints_root, nonce, extra_nonce);
                Bytes32 block_id = compute_block_id(full_hdr.data(), full_hdr.size(), res.commit);

                printf("\r[BLOCK %lld] %s nonce=%u extra=%u %lldms txs=%zu\n",
                       (long long)h, hex(block_id).substr(0, 16).c_str(),
                       nonce, extra_nonce, (long long)elapsed, block_txs.size());
                printf("  sub=%lld fees=%lld miner=%lld gold=%lld popc=%lld\n",
                       (long long)subsidy, (long long)total_fees,
                       (long long)split.miner, (long long)split.gold_vault, (long long)split.popc_pool);

                // Generate Transcript V2 witnesses (replays challenged rounds)
                printf("  Generating Transcript V2 witnesses...\n");
                generate_transcript_witnesses(res, scratch.data(), scratch.size(),
                    bk, nonce, extra_nonce, params, hc72, epoch);
                printf("  %zu segment proofs, %zu round witnesses\n",
                       res.segment_proofs.size(), res.round_witnesses.size());

                MinedBlock mb{};
                mb.block_id = block_id;
                mb.prev_hash = g_tip_hash;
                mb.merkle_root = mrkl;
                mb.commit = res.commit;
                mb.checkpoints_root = res.checkpoints_root;
                mb.segments_root = res.segments_root;
                mb.height = h; mb.timestamp = ts; mb.bits_q = bits_q;
                mb.nonce = nonce; mb.extra_nonce = extra_nonce;
                mb.stability_metric = res.stability_metric;
                mb.stab_scale = params.stab_scale;
                mb.stab_k = params.stab_k;
                mb.stab_margin = params.stab_margin;
                mb.stab_steps = params.stab_steps;
                mb.stab_lr_shift = params.stab_lr_shift;
                mb.profile_index = params.stab_profile_index;
                mb.x_bytes = res.x_bytes;
                mb.final_state = res.final_state;
                mb.checkpoint_leaves = res.checkpoint_leaves;
                mb.segment_proofs = res.segment_proofs;
                mb.round_witnesses = res.round_witnesses;
                mb.subsidy = subsidy;
                mb.miner_reward = split.miner;
                mb.gold_vault_reward = split.gold_vault;
                mb.popc_pool_reward = split.popc_pool;

                // Submit to node FIRST — only advance local chain if accepted
                bool node_accepted = false;
                if (!g_rpc_url.empty()) {
                    std::vector<std::string> all_hexes;
                    all_hexes.reserve(1 + mempool_tx_hexes.size());
                    all_hexes.push_back(coinbase_hex);
                    for(const auto& hx : mempool_tx_hexes) all_hexes.push_back(hx);

                    int submit_rc = rpc_submit_block_full(mb, all_hexes);
                    if (submit_rc == 1) {
                        printf("  -> submitted to node OK (%zu txs)\n", all_hexes.size());
                        node_accepted = true;
                    } else if (submit_rc == -1) {
                        // Connection lost — pause mining until reconnected
                        printf("[RPC] Connection lost — pausing mining until reconnected\n");
                        int attempt = 0;
                        while (true) {
                            attempt++;
                            printf("[RPC] Waiting for node... (attempt %d)\n", attempt);
                            fflush(stdout);
                            sleep(30);
                            // Try to reach the node
                            std::string info = rpc_call("getinfo");
                            if (!info.empty()) {
                                printf("[RPC] Reconnected to node!\n");
                                auto bp = info.find("\"blocks\":");
                                if (bp != std::string::npos) {
                                    int64_t nh = atoll(info.c_str() + bp + 9);
                                    if (nh > (int64_t)g_chain.size() - 1) {
                                        printf("[RPC] Node height %lld > local %zu — chain advanced while disconnected\n",
                                               (long long)nh, g_chain.size() - 1);
                                    }
                                    // Update tip hash from node
                                    std::string best = rpc_call("getbestblockhash");
                                    auto rp = best.find("\"result\":\"");
                                    if (rp != std::string::npos) {
                                        std::string tip_hex = best.substr(rp + 10, 64);
                                        if (tip_hex.size() == 64) {
                                            Bytes32 new_tip{};
                                            for (int i = 0; i < 32; ++i) {
                                                unsigned int byte;
                                                sscanf(tip_hex.c_str() + i * 2, "%02x", &byte);
                                                new_tip[i] = (uint8_t)byte;
                                            }
                                            g_tip_hash = new_tip;
                                            printf("[RPC] Updated tip to %s\n", tip_hex.substr(0, 16).c_str());
                                        }
                                    }
                                    // Get difficulty from node
                                    uint32_t node_diff = 0;
                                    auto dp = info.find("\"next_difficulty\":");
                                    if (dp != std::string::npos) node_diff = (uint32_t)atoll(info.c_str() + dp + 18);
                                    else { auto dp2 = info.find("\"difficulty\":"); if (dp2 != std::string::npos) node_diff = (uint32_t)atoll(info.c_str() + dp2 + 13); }
                                    // Pad chain to match node
                                    while ((int64_t)g_chain.size() - 1 < nh) {
                                        BlockMeta pad{};
                                        pad.height = (int64_t)g_chain.size();
                                        pad.time = (int64_t)time(nullptr);
                                        pad.powDiffQ = node_diff > 0 ? node_diff : GENESIS_BITSQ;
                                        g_chain.push_back(pad);
                                    }
                                }
                                break;
                            }
                        }
                        // After reconnect: return false so main loop retries with fresh state
                        printf("[RPC] Resuming mining from height %lld with fresh state\n",
                               (long long)h);
                        return false; // will be retried by outer loop
                    } else {
                        // Block rejected — query node for current state
                        std::string info = rpc_call("getinfo");
                        std::string best = rpc_call("getbestblockhash");
                        if (!info.empty()) {
                            auto bp = info.find("\"blocks\":");
                            int64_t node_height = (bp != std::string::npos) ? atoll(info.c_str() + bp + 9) : -1;

                            // Get tip hash from getbestblockhash
                            auto rp = best.find("\"result\":\"");
                            if (rp != std::string::npos) {
                                std::string tip_hex = best.substr(rp + 10, 64);
                                if (tip_hex.size() == 64) {
                                    Bytes32 new_tip{};
                                    for (int i = 0; i < 32; ++i) {
                                        unsigned int byte;
                                        sscanf(tip_hex.c_str() + i * 2, "%02x", &byte);
                                        new_tip[i] = (uint8_t)byte;
                                    }
                                    g_tip_hash = new_tip;
                                    printf("  -> Updated tip to %s\n", tip_hex.substr(0, 16).c_str());
                                }
                            }

                            if (node_height >= h) {
                                printf("  -> NODE REJECTED — chain at height %lld (we tried %lld). Advancing.\n",
                                       (long long)node_height, (long long)h);
                                // Get next_difficulty from node for accurate cASERT
                                uint32_t node_diff = bits_q;
                                auto dp = info.find("\"next_difficulty\":");
                                if (dp != std::string::npos) {
                                    node_diff = (uint32_t)atoll(info.c_str() + dp + 18);
                                } else {
                                    auto dp2 = info.find("\"difficulty\":");
                                    if (dp2 != std::string::npos)
                                        node_diff = (uint32_t)atoll(info.c_str() + dp2 + 13);
                                }
                                // Pad local chain to match node height with real difficulty
                                while ((int64_t)g_chain.size() - 1 < node_height) {
                                    BlockMeta pad{};
                                    pad.height = (int64_t)g_chain.size();
                                    pad.time = (int64_t)time(nullptr);
                                    pad.powDiffQ = node_diff;
                                    g_chain.push_back(pad);
                                }
                                return false; // restart mining at new height
                            }
                        }
                        printf("  -> NODE REJECTED BLOCK — will retry same height\n");
                        continue;
                    }
                } else {
                    // No RPC — local-only mode, always accept
                    node_accepted = true;
                }

                if (node_accepted) {
                    // Only now add to local chain
                    BlockMeta meta;
                    meta.block_id = block_id;
                    meta.height = h;
                    meta.time = ts;
                    meta.powDiffQ = bits_q;
                    g_chain.push_back(meta);
                    g_tip_hash = block_id;
                    g_mined_blocks.push_back(mb);
                }

                found = true;
                stop_block_monitor();
                break;
            }
        }

        if (!found) {
            extra_nonce++;
            if (sim_time) {
                ts++;
            } else {
                ts = std::chrono::duration_cast<std::chrono::seconds>(
                    std::chrono::system_clock::now().time_since_epoch()).count();
                ts_last_update = std::chrono::steady_clock::now();
            }
            build_hc72(hc72, g_tip_hash, mrkl, (uint32_t)ts, bits_q);
            if (extra_nonce > 1000) {
                printf("\n[FATAL] exhausted 1000 extra_nonce loops\n");
                return false;
            }
        }
    }
    return true;
}

// =============================================================================
// main
// =============================================================================
int main(int argc, char** argv) {
    ACTIVE_PROFILE = Profile::MAINNET;

    int num_blocks = 5;
    uint32_t max_nonce = 0xFFFFFFFF; // unlimited by default
    Profile prof = Profile::MAINNET;
    bool sim_time = false;
    std::string genesis_path = "genesis_block.json";
    std::string chain_path = "chain.json";

    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--blocks") && i + 1 < argc) num_blocks = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-nonce") && i + 1 < argc) max_nonce = (uint32_t)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--genesis") && i + 1 < argc) genesis_path = argv[++i];
        else if (!strcmp(argv[i], "--chain") && i + 1 < argc) chain_path = argv[++i];
        else if (!strcmp(argv[i], "--realtime")) sim_time = false;
        else if (!strcmp(argv[i], "--rpc") && i + 1 < argc) g_rpc_url = argv[++i];
        else if (!strcmp(argv[i], "--rpc-user") && i + 1 < argc) g_rpc_user = argv[++i];
        else if (!strcmp(argv[i], "--rpc-pass") && i + 1 < argc) g_rpc_pass = argv[++i];
        else if (!strcmp(argv[i], "--address") && i + 1 < argc) g_miner_address = argv[++i];
        else if (!strcmp(argv[i], "--profile") && i + 1 < argc) {
            ++i;
            if (!strcmp(argv[i], "testnet")) prof = Profile::TESTNET;
            else if (!strcmp(argv[i], "dev")) prof = Profile::DEV;
        }
        else if (!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) {
            printf("SOST Miner v0.6\n");
            printf("  --address <sost1..> REQUIRED: your wallet address to receive mining rewards\n");
            printf("  --blocks <n>       Blocks to mine (default: 5)\n");
            printf("  --max-nonce <n>    Max nonce per extra_nonce cycle (default: unlimited)\n");
            printf("  --genesis <path>   Genesis JSON\n");
            printf("  --chain <path>     Chain file (default: chain.json)\n");
            printf("  --rpc <host:port>  Submit blocks to node via RPC\n");
            printf("  --rpc-user <u>     RPC Basic Auth user\n");
            printf("  --rpc-pass <p>     RPC Basic Auth pass\n");
            printf("  --profile <p>      mainnet|testnet|dev\n");
            printf("  --realtime         Real timestamps\n");
            return 0;
        }
    }

    // Validate --address (REQUIRED)
    if (g_miner_address.empty()) {
        fprintf(stderr, "ERROR: --address required. Use your wallet address to receive mining rewards.\n");
        fprintf(stderr, "  Example: --address sost1your40hexcharaddresshere1234567890ab\n");
        return 1;
    }
    if (!address_valid(g_miner_address)) {
        fprintf(stderr, "ERROR: invalid address '%s'. Must be sost1 + 40 hex chars.\n", g_miner_address.c_str());
        return 1;
    }
    if (!address_decode(g_miner_address, g_miner_pkh)) {
        fprintf(stderr, "ERROR: failed to decode address '%s'.\n", g_miner_address.c_str());
        return 1;
    }

    printf("=== SOST Miner v0.6 (FULL submitblock) ===\n");
    printf("Miner address: %s\n", g_miner_address.c_str());
    printf("Profile: %s | Blocks: %d%s\n\n",
           prof == Profile::MAINNET ? "mainnet" : (prof == Profile::TESTNET ? "testnet" : "dev"),
           num_blocks,
           g_rpc_url.empty() ? "" : (" | RPC: " + g_rpc_url).c_str());

    if (!load_genesis(genesis_path)) {
        fprintf(stderr, "Error: cannot load genesis\n"); return 1;
    }
    printf("Genesis: %s\n\n", hex(g_tip_hash).c_str());

    // Load existing chain to continue mining
    {
        std::ifstream test(chain_path);
        if (test.good()) {
            test.close();
            load_chain(chain_path);
            printf("Continuing from height %lld, tip=%s\n\n",
                   (long long)(g_chain.size()-1), hex(g_tip_hash).substr(0,16).c_str());
        }
    }

    int mined = 0;
    for (int i = 0; i < num_blocks; ++i) {
        if (!mine_one_block(prof, max_nonce, sim_time)) {
            // mine_one_block returns false on: RPC reconnect (retry same height)
            // or extra_nonce exhaustion (stop)
            if (!g_rpc_url.empty()) { --i; continue; } // retry same block after reconnect
            else break; // standalone mode: stop
        }
        mined++;
        if (g_rpc_url.empty()) save_chain(chain_path);
    }

    printf("\n=== Done: %d blocks mined, height=%lld ===\n",
           mined, (long long)(g_chain.size() - 1));
    printf("Tip: %s\n", hex(g_tip_hash).c_str());
    if (!g_rpc_url.empty())
        printf("Mode: RPC -> blocks submitted to node at %s\n", g_rpc_url.c_str());
    else
        printf("Mode: standalone -> chain saved to %s\n", chain_path.c_str());
    return 0;
}
