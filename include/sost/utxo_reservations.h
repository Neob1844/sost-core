// utxo_reservations.h — local reservation ledger for watch-only `sost-cli buildtx`.
//
// buildtx writes an UNSIGNED transaction; nothing reaches the node until it is
// signed offline and broadcast. Until then the node cannot know those inputs are
// taken, so a second build from the same address would pick them again. buildtx
// therefore records the outpoints of every build it writes in a small JSON ledger
// and excludes them from later builds until one of these happens:
//   - the reservation expires (expires_at, set from --reservation-ttl),
//   - none of its outpoints is still an unspent output of the address (the tx,
//     or a conflicting one, confirmed — the coins are gone either way),
//   - the user clears it explicitly (--clear-reservations).
// Coins spent by a tx already in the node mempool are excluded separately (node
// RPC getmempoolspends), so a reservation is only needed for the window between
// build and broadcast.
//
// Wallet/CLI tooling only. No consensus or node policy depends on this file.
#pragma once

#include <cstdint>
#include <set>
#include <string>
#include <vector>

namespace sost::resv {

inline constexpr const char* kFormat = "sost-buildtx-reservations-v1";
inline constexpr int64_t kDefaultTtlSeconds = 24 * 3600;

// "txid_hex:vout" — lowercase hex txid.
std::string outpoint_key(const std::string& txid_hex, uint32_t vout);

struct Reservation {
    std::string from;                   // source address of the build
    std::string file;                   // the unsigned tx file it was written to
    std::string build_id;               // txid of the unsigned build (informational)
    int64_t     created_at{0};          // unix seconds
    int64_t     expires_at{0};          // unix seconds
    std::vector<std::string> outpoints; // outpoint_key()s
};

struct Ledger {
    std::vector<Reservation> items;
};

// Missing file -> empty ledger, true. Any unreadable / malformed content -> false
// (fail closed: never silently forget reservations).
bool load(const std::string& path, Ledger& out, std::string* err = nullptr);

// Atomic replace (write <path>.tmp, fsync, rename). Mode 0600.
bool save(const std::string& path, const Ledger& l, std::string* err = nullptr);

std::string to_json(const Ledger& l);
bool from_json(const std::string& text, Ledger& out, std::string* err = nullptr);

// Drop expired entries (any address), and entries of `from` none of whose
// outpoints is in `live_utxos` (the address's current confirmed UTXO keys).
// Returns the number of entries removed.
size_t prune(Ledger& l, int64_t now, const std::string& from, const std::set<std::string>& live_utxos);

// Outpoints of `from` reserved by unexpired entries.
std::set<std::string> reserved_for(const Ledger& l, const std::string& from, int64_t now);

// Remove every entry of `from`. Returns the number removed.
size_t clear_from(Ledger& l, const std::string& from);

} // namespace sost::resv
