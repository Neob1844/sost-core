// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap BTC — swap state machine + persistable record (OTC-6)
// =============================================================================
//
// One BtcSwapRecord is the full, restart-recoverable state of ONE BTC HTLC leg
// of a cross-chain swap. It carries everything the wallet needs to resume after
// a crash WITHOUT re-broadcasting a tx it already sent (no double-spend):
//
//   - the immutable swap parameters (hashlock, redeem script, HTLC address,
//     refund height, destination addresses, fee)
//   - the on-chain facts learned so far (funding txid/vout/amount, claim txid,
//     refund txid, last observed confirmations)
//   - the discrete state in the lifecycle
//
// The transition function is PURE and idempotent: applying the same event twice
// is a no-op, and illegal transitions (claim-after-refund, refund-after-claim,
// anything out of a terminal state) are rejected. The economic decision "should
// I actually broadcast now?" is expressed as: a broadcast event only *changes*
// state out of the Redeemable/Refundable/… precondition state exactly once —
// so a retry after a network error finds the state already advanced and does
// NOT broadcast a second tx.
//
// Pure, non-consensus, no libwally, no network. Private keys are NEVER stored.
// =============================================================================
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace btc {

// Discrete lifecycle of one BTC HTLC leg. Hex strings, not raw bytes, so the
// record round-trips through the text watchlist without conversion churn.
enum class BtcSwapState : uint8_t {
    Created,          // record built; HTLC address derived; nothing on-chain
    FundingBroadcast, // funding(=lock) tx broadcast; awaiting confirmations
    Locked,           // funding tx reached min-confirmations; BTC is locked
    Redeemable,       // claimant: preimage known AND before timeout → may claim
    Redeeming,        // claim tx broadcast; awaiting confirmations
    Redeemed,         // claim confirmed  (TERMINAL, success)
    Refundable,       // funder: timeout reached AND still unspent → may refund
    Refunding,        // refund tx broadcast; awaiting confirmations
    Refunded,         // refund confirmed (TERMINAL)
    Failed            // aborted / unrecoverable error (TERMINAL)
};
const char* BtcSwapStateName(BtcSwapState s);
bool        IsBtcSwapTerminal(BtcSwapState s);

// Events that drive the state machine. Each corresponds to a concrete fact the
// watcher/orchestration layer observed or an action it is about to take.
enum class BtcSwapEvent : uint8_t {
    FundingBroadcast,   // we broadcast the funding tx
    FundingConfirmed,   // funding tx reached min-confirmations
    BecameRedeemable,   // claimant: preimage known and window open
    ClaimBroadcast,     // we broadcast the claim tx
    ClaimConfirmed,     // claim tx confirmed
    BecameRefundable,   // funder: timeout reached, still unspent
    RefundBroadcast,    // we broadcast the refund tx
    RefundConfirmed,    // refund tx confirmed
    Fail                // abort (network-independent error)
};
const char* BtcSwapEventName(BtcSwapEvent e);

// Our spend relationship to this HTLC (mirrors the SOST-side WatchSide).
enum class BtcParty : uint8_t { Claimant, Funder };
const char* BtcPartyName(BtcParty p);

// The full persistable record.
struct BtcSwapRecord {
    std::string  swap_id;                 // ties to the off-chain Offer / SOST leg
    BtcParty     party = BtcParty::Funder;
    std::string  network = "mainnet";     // mainnet|testnet|regtest

    // Immutable swap parameters (all hex where noted).
    std::string  hashlock_hex;            // 32-byte sha256(preimage), hex
    std::string  redeem_script_hex;       // BuildBtcHtlcRedeemScript output, hex
    std::string  htlc_address;            // bech32 P2WSH address the funding pays
    int64_t      lock_amount_sats = 0;    // amount locked in the HTLC output
    int64_t      refund_height = 0;       // CLTV height the refund branch opens
    std::string  claim_dest_addr;         // where a successful claim pays
    std::string  refund_dest_addr;        // where a refund pays
    int64_t      fee_sats = 0;            // fee for the spending (claim/refund) tx

    // Learned on-chain facts.
    std::string  funding_txid;            // hex (big-endian display form), the lock utxo
    uint32_t     funding_vout = 0;
    std::string  claim_txid;              // hex, set once we broadcast/observe a claim
    std::string  refund_txid;             // hex, set once we broadcast/observe a refund
    int64_t      last_confirmations = 0;  // last observed conf count on the relevant tx

    // Secret material (preimage only — NEVER a private key). Cleartext hex; the
    // store writes 0600. Before a claim this is a secret; after the claim it is
    // public on-chain anyway.
    bool         have_preimage = false;
    std::string  preimage_hex;

    BtcSwapState state = BtcSwapState::Created;
};

// Result of a transition attempt.
struct BtcTransition {
    bool         ok = false;      // the event was legal (or a no-op)
    bool         changed = false; // state actually advanced (false = idempotent no-op)
    std::string  error;           // set when ok==false
};

// Apply an event to the record's state, in place. Idempotent: re-applying an
// event whose effect already happened returns ok=true, changed=false and does
// NOT mutate. Illegal transitions (e.g. ClaimBroadcast after Refunded) return
// ok=false. `Fail` is always legal from a non-terminal state.
//
// The `changed` flag is the double-spend guard: broadcast only when changed.
BtcTransition ApplyBtcSwapEvent(BtcSwapRecord& r, BtcSwapEvent e);

// Ingest a revealed preimage (hex). Returns true iff sha256(bytes)==hashlock,
// setting have_preimage+preimage_hex. A non-matching preimage is ignored.
bool IngestBtcPreimage(BtcSwapRecord& r, const std::string& preimage_hex);

// -----------------------------------------------------------------------------
// Persistence — deterministic single-line "key=value;..." per record, matching
// the style of SerializeWatchedSwap. Pure string<->struct; no file I/O here
// (that lives in the recovery store, btc_watch.*).
// -----------------------------------------------------------------------------
std::string SerializeBtcSwapRecord(const BtcSwapRecord& r);
bool        ParseBtcSwapRecord(const std::string& line, BtcSwapRecord& out);
std::string SerializeBtcSwapList(const std::vector<BtcSwapRecord>& v);
bool        ParseBtcSwapList(const std::string& text, std::vector<BtcSwapRecord>& out);

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
