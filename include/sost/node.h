#pragma once
#include "block.h"
#include "wallet.h"
#include "miner.h"
#include <vector>
#include <string>
#include <functional>
#include <mutex>
namespace sost {

struct ChainState {
    std::vector<Block> blocks;
    std::vector<BlockMeta> metas;
    Bytes32 tip_hash;
    int64_t tip_height;
    int64_t total_work;
};

struct PeerInfo {
    std::string addr;
    int64_t tip_height;
    bool connected;
};

class Node {
public:
    Node(Profile prof);
    // Chain
    bool accept_block(const Block& blk);
    Block get_block(int64_t h) const;
    int64_t height() const;
    Bytes32 tip() const;
    ChainState state() const;
    // Mining
    MineResult mine_next(Wallet& w, uint32_t max_nonce=500000);
    int mine_loop(int32_t count, Wallet& w, uint32_t max_nonce=500000);
    // Info
    std::string info_json() const;
    std::string block_json(int64_t h) const;
private:
    Profile prof_;
    ChainState cs_;
    mutable std::mutex mu_;
};

// Simple HTTP RPC server (single-threaded)
int run_rpc_server(Node& node, Wallet& wallet, int port);

} // namespace sost
