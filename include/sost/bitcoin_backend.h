// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap BTC — Bitcoin chain backend (broadcast + queries)
// =============================================================================
//
// The pure signing module (atomic_swap_btc_signing.*) builds and signs the raw
// BTC HTLC transactions but, by design, NEVER touches the network. This module
// is the thin, OPTIONAL layer that talks to a Bitcoin node (bitcoind /
// btcd-compatible JSON-RPC) so the wallet/CLI can:
//
//   - broadcast a signed raw tx                  (BroadcastRawTransaction)
//   - fetch a raw tx / its confirmation status   (GetRawTransaction, GetTransactionStatus)
//   - read the BTC chain tip height              (GetBlockHeight)
//   - estimate a fee rate                        (EstimateFeeRate)
//   - enumerate spendable UTXOs for funding      (ListUnspent)
//
// HARD RULES (fund-safety + Option-A guarantee):
//
//   1. This layer is NEVER reached from SOST consensus. It lives in the
//      wallet/OTC tooling only. The SOST node builds and runs with no bitcoind
//      present and no BTC_RPC_* set.
//
//   2. Fail-closed by default. `MakeBitcoinBackendFromEnv()` returns a
//      NullBitcoinBackend (every call ok=false "not configured") UNLESS BOTH:
//        (a) the runtime gate SOST_BTC_ATOMIC_SWAP_ENABLED=1, AND
//        (b) BTC_RPC_HOST/PORT/USER/PASS are all present.
//      With BTC OFF (the deployed Option A) there is no path to a live backend.
//
//   3. No credentials are ever hardcoded, logged, or persisted by this module.
//      They come from the environment (or an explicit BitcoinRpcConfig the
//      caller assembled) and stay in memory.
//
// TESTABILITY: BitcoindRpcBackend takes an injectable HTTP transport so the
// JSON-RPC request/response handling is unit-tested with canned responses and
// NO real network / NO bitcoind. The default transport is a raw-socket POST
// (same shape as src/tx_send.cpp's rpc_call).
// =============================================================================
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace btc {

// ---------------------------------------------------------------------------
// Result types — every call returns ok + error; never throws for I/O failure.
// ---------------------------------------------------------------------------

// On-chain state of a tx as seen by the backend.
enum class BtcTxState : uint8_t {
    Unknown,     // backend could not determine (RPC error / disabled)
    NotFound,    // node has never seen this txid
    InMempool,   // accepted, 0 confirmations
    Confirmed    // >= 1 confirmation
};
const char* BtcTxStateName(BtcTxState s);

struct BtcBroadcastResult {
    bool        ok = false;
    std::string error;
    std::string txid;   // the txid the node accepted (on ok)
};

struct BtcRawTxResult {
    bool        ok = false;
    std::string error;
    std::string raw_tx_hex;
};

struct BtcTxStatus {
    bool        ok = false;          // ok == the query itself succeeded
    std::string error;
    BtcTxState  state = BtcTxState::Unknown;
    int64_t     confirmations = 0;
    int64_t     block_height = -1;   // -1 if unconfirmed / unknown
};

struct BtcHeightResult {
    bool        ok = false;
    std::string error;
    int64_t     height = -1;
};

struct BtcFeeResult {
    bool        ok = false;
    std::string error;
    int64_t     sat_per_vbyte = 0;   // conservative floor applied by impl
};

// A spendable output the funder controls, as reported by the node.
struct BtcUtxo {
    std::string txid;
    uint32_t    vout = 0;
    int64_t     amount_sats = 0;
    std::string script_pubkey_hex;   // may be empty if the node omits it
    int64_t     confirmations = 0;
};

struct BtcListUnspentResult {
    bool                 ok = false;
    std::string          error;
    std::vector<BtcUtxo> utxos;
};

// ---------------------------------------------------------------------------
// Abstract backend
// ---------------------------------------------------------------------------

class BitcoinBackend {
public:
    virtual ~BitcoinBackend() = default;

    // Human-readable name for logs/dashboard ("bitcoind-rpc", "null").
    virtual std::string Name() const = 0;

    // True iff this backend is wired to a usable node. A NullBitcoinBackend
    // returns false. The dashboard/tooling must treat false as "BTC disabled".
    virtual bool IsConfigured() const = 0;

    // The BTC network this backend serves ("mainnet"|"testnet"|"regtest"|"").
    virtual std::string Network() const = 0;

    virtual BtcBroadcastResult   BroadcastRawTransaction(const std::string& raw_tx_hex) = 0;
    virtual BtcRawTxResult       GetRawTransaction(const std::string& txid) = 0;
    virtual BtcTxStatus          GetTransactionStatus(const std::string& txid) = 0;
    virtual BtcHeightResult      GetBlockHeight() = 0;
    virtual BtcFeeResult         EstimateFeeRate(int confirm_target_blocks) = 0;
    virtual BtcListUnspentResult ListUnspent(int min_confirmations,
                                             const std::string& address) = 0;
};

// ---------------------------------------------------------------------------
// NullBitcoinBackend — the fail-closed default. Every call ok=false.
// ---------------------------------------------------------------------------

class NullBitcoinBackend : public BitcoinBackend {
public:
    explicit NullBitcoinBackend(std::string reason = "BTC backend not configured")
        : reason_(std::move(reason)) {}

    std::string Name() const override { return "null"; }
    bool        IsConfigured() const override { return false; }
    std::string Network() const override { return ""; }

    BtcBroadcastResult   BroadcastRawTransaction(const std::string&) override { return fail_bc(); }
    BtcRawTxResult       GetRawTransaction(const std::string&) override { return fail_raw(); }
    BtcTxStatus          GetTransactionStatus(const std::string&) override { return fail_st(); }
    BtcHeightResult      GetBlockHeight() override { return fail_h(); }
    BtcFeeResult         EstimateFeeRate(int) override { return fail_fee(); }
    BtcListUnspentResult ListUnspent(int, const std::string&) override { return fail_lu(); }

private:
    std::string reason_;
    BtcBroadcastResult   fail_bc()  { BtcBroadcastResult r;   r.error = reason_; return r; }
    BtcRawTxResult       fail_raw() { BtcRawTxResult r;       r.error = reason_; return r; }
    BtcTxStatus          fail_st()  { BtcTxStatus r;          r.error = reason_; return r; }
    BtcHeightResult      fail_h()   { BtcHeightResult r;      r.error = reason_; return r; }
    BtcFeeResult         fail_fee() { BtcFeeResult r;         r.error = reason_; return r; }
    BtcListUnspentResult fail_lu()  { BtcListUnspentResult r; r.error = reason_; return r; }
};

// ---------------------------------------------------------------------------
// bitcoind JSON-RPC backend
// ---------------------------------------------------------------------------

struct BitcoinRpcConfig {
    std::string host;
    int         port = 0;
    std::string user;
    std::string pass;
    std::string network = "mainnet";      // "mainnet"|"testnet"|"regtest"
    int         min_confirmations = 1;    // confirmations to treat a tx "final"
    bool        runtime_enabled = false;  // SOST_BTC_ATOMIC_SWAP_ENABLED gate

    // Reads BTC_RPC_HOST / BTC_RPC_PORT / BTC_RPC_USER / BTC_RPC_PASSWORD /
    // BTC_NETWORK / BTC_CONFIRMATIONS and the runtime gate
    // SOST_BTC_ATOMIC_SWAP_ENABLED from the environment. Never logs values.
    static BitcoinRpcConfig FromEnv();

    // host+port+user+pass all present.
    bool HasCredentials() const;

    // HasCredentials() AND runtime_enabled. This is the single predicate that
    // decides whether a live backend may be constructed. Default = false.
    bool IsUsable() const;
};

// Injectable HTTP transport: perform ONE HTTP/1.1 POST of `json_body` to
// host:port with the given base64 Basic-Auth token, return the raw HTTP
// RESPONSE BODY (headers stripped), or "" on transport failure. The default
// transport (used when none is injected) is a raw-socket POST. Tests inject a
// lambda returning canned JSON so no socket is opened.
using BtcHttpTransport = std::function<std::string(const std::string& host,
                                                   int                port,
                                                   const std::string& auth_b64,
                                                   const std::string& json_body)>;

class BitcoindRpcBackend : public BitcoinBackend {
public:
    // If `transport` is empty, the real raw-socket transport is used.
    explicit BitcoindRpcBackend(BitcoinRpcConfig cfg, BtcHttpTransport transport = {});

    std::string Name() const override { return "bitcoind-rpc"; }
    bool        IsConfigured() const override { return cfg_.IsUsable(); }
    std::string Network() const override { return cfg_.network; }

    BtcBroadcastResult   BroadcastRawTransaction(const std::string& raw_tx_hex) override;
    BtcRawTxResult       GetRawTransaction(const std::string& txid) override;
    BtcTxStatus          GetTransactionStatus(const std::string& txid) override;
    BtcHeightResult      GetBlockHeight() override;
    BtcFeeResult         EstimateFeeRate(int confirm_target_blocks) override;
    BtcListUnspentResult ListUnspent(int min_confirmations,
                                     const std::string& address) override;

    // Exposed for unit tests: run a raw method/params and return the JSON body.
    std::string CallRawForTest(const std::string& method, const std::string& params_json);

private:
    BitcoinRpcConfig cfg_;
    BtcHttpTransport transport_;
    // Sends {"jsonrpc":"1.0","id":...,"method":...,"params":...}; returns the
    // response body. `ok` set false if transport failed or JSON has an error.
    std::string Rpc(const std::string& method, const std::string& params_json);
};

// The default raw-socket transport (declared for reuse/testing).
std::string DefaultBtcHttpTransport(const std::string& host,
                                    int                port,
                                    const std::string& auth_b64,
                                    const std::string& json_body);

// ---------------------------------------------------------------------------
// Factory — the ONLY sanctioned way tooling obtains a backend.
// ---------------------------------------------------------------------------
//
// Returns a live BitcoindRpcBackend iff BitcoinRpcConfig::FromEnv().IsUsable()
// (runtime gate ON + full credentials). Otherwise returns a NullBitcoinBackend
// carrying a human-readable reason. NEVER returns a half-configured live
// backend. This is what guarantees Option A (BTC OFF) has no live BTC path.
std::unique_ptr<BitcoinBackend> MakeBitcoinBackendFromEnv();

// Same, from an explicit config (for tests / callers that assemble their own).
std::unique_ptr<BitcoinBackend> MakeBitcoinBackend(const BitcoinRpcConfig& cfg,
                                                   BtcHttpTransport transport = {});

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
