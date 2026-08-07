// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// test_bitcoin_backend.cpp — unit tests for the optional Bitcoin JSON-RPC
// backend. NO network, NO bitcoind: a mock transport returns canned JSON.
// Verifies the fail-closed guarantees and the JSON-RPC request/response
// handling for every method.

#include "sost/bitcoin_backend.h"

#include <cstdio>
#include <string>

using namespace sost::atomic_swap::btc;

static int g_fail = 0;
#define CHECK(cond, msg) do { \
    if (!(cond)) { std::printf("FAIL: %s\n", msg); ++g_fail; } \
    else         { std::printf("ok:   %s\n", msg); } \
} while (0)

// A mock transport that returns a response keyed on the method embedded in the
// request body. Records the last body so tests can assert request shape.
struct MockRpc {
    std::string last_body;
    std::string reply_for(const std::string& body) {
        last_body = body;
        auto has = [&](const char* m) { return body.find(std::string("\"method\":\"") + m + "\"") != std::string::npos; };
        if (has("sendrawtransaction")) {
            // Echo a fixed 64-hex txid.
            return "{\"result\":\"" + std::string(64, 'a') + "\",\"error\":null,\"id\":\"sost-swap\"}";
        }
        if (has("getblockcount")) {
            return "{\"result\":812345,\"error\":null,\"id\":\"sost-swap\"}";
        }
        if (has("estimatesmartfee")) {
            // 0.00002 BTC/kvB = 2000 sat/kvB = 2 sat/vB.
            return "{\"result\":{\"feerate\":0.00002000,\"blocks\":6},\"error\":null}";
        }
        if (has("getrawtransaction")) {
            if (body.find(",true]") != std::string::npos) {
                // verbose status query
                if (body.find("confirmedtx") != std::string::npos)
                    return "{\"result\":{\"txid\":\"x\",\"confirmations\":7},\"error\":null}";
                if (body.find("mempooltx") != std::string::npos)
                    return "{\"result\":{\"txid\":\"x\"},\"error\":null}";
                if (body.find("missingtx") != std::string::npos)
                    return "{\"result\":null,\"error\":{\"code\":-5,\"message\":\"No such mempool or blockchain transaction\"}}";
            } else {
                return "{\"result\":\"deadbeef\",\"error\":null}";
            }
        }
        if (has("listunspent")) {
            return "{\"result\":["
                   "{\"txid\":\"" + std::string(64,'1') + "\",\"vout\":0,\"amount\":0.50000000,\"confirmations\":10,\"scriptPubKey\":\"0014abcd\"},"
                   "{\"txid\":\"" + std::string(64,'2') + "\",\"vout\":3,\"amount\":1.25000000,\"confirmations\":100}"
                   "],\"error\":null}";
        }
        if (has("errmethod")) {
            return "{\"result\":null,\"error\":{\"code\":-32601,\"message\":\"boom\"}}";
        }
        return "";  // transport failure
    }
};

static BtcHttpTransport make_mock(MockRpc* m) {
    return [m](const std::string&, int, const std::string&, const std::string& body) {
        return m->reply_for(body);
    };
}

int main() {
    std::printf("=== test_bitcoin_backend ===\n");

    // --- Fail-closed guarantees -------------------------------------------
    {
        NullBitcoinBackend nb;
        CHECK(!nb.IsConfigured(), "null backend not configured");
        CHECK(!nb.BroadcastRawTransaction("00").ok, "null broadcast fails closed");
        CHECK(!nb.GetBlockHeight().ok, "null height fails closed");
        CHECK(!nb.ListUnspent(1, "").ok, "null listunspent fails closed");
    }
    {
        // runtime gate OFF → factory returns Null even with full creds.
        BitcoinRpcConfig c; c.host="127.0.0.1"; c.port=8332; c.user="u"; c.pass="p";
        c.runtime_enabled = false;
        auto be = MakeBitcoinBackend(c);
        CHECK(!be->IsConfigured(), "gate OFF → Null backend");
        CHECK(be->Name() == "null", "gate OFF → name null");
    }
    {
        // gate ON but incomplete creds → Null.
        BitcoinRpcConfig c; c.runtime_enabled = true; c.host="127.0.0.1"; /* no port/user/pass */
        auto be = MakeBitcoinBackend(c);
        CHECK(!be->IsConfigured(), "gate ON + incomplete creds → Null backend");
    }
    {
        BitcoinRpcConfig c; c.host="h"; c.port=1; c.user="u"; c.pass="p"; c.runtime_enabled=true;
        CHECK(c.IsUsable(), "full creds + gate ON → usable");
        c.runtime_enabled=false;
        CHECK(!c.IsUsable(), "gate OFF → not usable");
    }

    // --- Live backend with mock transport ---------------------------------
    MockRpc mock;
    BitcoinRpcConfig cfg; cfg.host="127.0.0.1"; cfg.port=18443; cfg.user="u"; cfg.pass="p";
    cfg.runtime_enabled = true; cfg.network = "regtest";
    auto be = MakeBitcoinBackend(cfg, make_mock(&mock));
    CHECK(be->IsConfigured(), "mock backend configured");
    CHECK(be->Name() == "bitcoind-rpc", "mock backend name");
    CHECK(be->Network() == "regtest", "mock backend network");

    // broadcast
    {
        auto r = be->BroadcastRawTransaction("0200000000");
        CHECK(r.ok, "broadcast ok");
        CHECK(r.txid == std::string(64,'a'), "broadcast returns txid");
        CHECK(mock.last_body.find("\"jsonrpc\":\"1.0\"") != std::string::npos, "uses JSON-RPC 1.0");
        CHECK(mock.last_body.find("sendrawtransaction") != std::string::npos, "broadcast method name");
    }
    // height
    {
        auto r = be->GetBlockHeight();
        CHECK(r.ok && r.height == 812345, "getblockcount → height");
    }
    // fee
    {
        auto r = be->EstimateFeeRate(6);
        CHECK(r.ok && r.sat_per_vbyte == 2, "estimatesmartfee → 2 sat/vB");
    }
    // raw tx (non-verbose)
    {
        auto r = be->GetRawTransaction(std::string(64,'d'));
        CHECK(r.ok && r.raw_tx_hex == "deadbeef", "getrawtransaction hex");
    }
    // status: confirmed / mempool / not-found
    {
        auto r = be->GetTransactionStatus("confirmedtx");
        CHECK(r.ok && r.state == BtcTxState::Confirmed && r.confirmations == 7, "status confirmed");
        auto m = be->GetTransactionStatus("mempooltx");
        CHECK(m.ok && m.state == BtcTxState::InMempool && m.confirmations == 0, "status mempool");
        auto nf = be->GetTransactionStatus("missingtx");
        CHECK(nf.ok && nf.state == BtcTxState::NotFound, "status not-found (query ok)");
    }
    // listunspent → sats
    {
        auto r = be->ListUnspent(1, "");
        CHECK(r.ok && r.utxos.size() == 2, "listunspent parses 2 utxos");
        if (r.utxos.size() == 2) {
            CHECK(r.utxos[0].amount_sats == 50000000, "utxo0 amount = 0.5 BTC in sats");
            CHECK(r.utxos[0].vout == 0, "utxo0 vout");
            CHECK(r.utxos[1].amount_sats == 125000000, "utxo1 amount = 1.25 BTC in sats");
            CHECK(r.utxos[1].vout == 3, "utxo1 vout");
        }
    }
    // rpc error surfaces (use a concrete backend for the test-only raw call)
    {
        BitcoindRpcBackend rpc(cfg, make_mock(&mock));
        auto raw = rpc.CallRawForTest("errmethod", "[]");
        CHECK(raw.find("boom") != std::string::npos, "raw error passthrough");
    }
    // transport failure → fail closed
    {
        auto be2 = MakeBitcoinBackend(cfg, [](const std::string&,int,const std::string&,const std::string&){ return std::string(); });
        auto r = be2->GetBlockHeight();
        CHECK(!r.ok, "transport failure → fail closed");
    }

    std::printf("=== %s ===\n", g_fail == 0 ? "ALL PASS" : "FAILURES");
    return g_fail == 0 ? 0 : 1;
}
