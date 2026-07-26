#pragma once
// =============================================================================
// V15 (J) live wiring — reserve discovery from the live UTXO set.
// Bridges the chainstate UTXO set to the pure jackpot core (jackpot.h). This is
// the ONLY consensus source of the Historical Jackpot reserve set: every honest
// node derives the identical set from chainstate alone. No wallet, no index as
// authority, no external service, no unordered iteration — the UTXO set is a
// std::map (ordered) and we additionally sort by the canonical (height, txid,
// vout) key so the result is bit-identical everywhere.
// =============================================================================
#include <vector>
#include <algorithm>
#include "sost/jackpot.h"
#include "sost/utxo_set.h"   // UtxoSet; brings OutPoint/UTXOEntry via tx_validation.h

namespace sost::jackpot {

// Discover the Historical Jackpot reserve UTXOs (spec §5b): Gold Vault / PoPC
// coinbase outputs at their constitutional addresses, plus any prior jackpot
// change output (which re-enters as an OUT_COINBASE_GOLD at the reserve sink).
// Returned sorted oldest-first (height, txid, vout) — the exact order the
// canonical selection consumes.
inline std::vector<ReserveUtxo> discover_reserve_utxos(const UtxoSet& utxos,
                                                       const PubKeyHash& gold_pkh,
                                                       const PubKeyHash& popc_pkh) {
    std::vector<ReserveUtxo> out;
    for (const auto& kv : utxos.GetMap()) {
        const UTXOEntry& e = kv.second;
        if (!is_reserve_output(e.type, e.pubkey_hash, gold_pkh, popc_pkh)) continue;
        ReserveUtxo u;
        u.height = e.height;
        u.txid   = kv.first.txid;   // Hash256 == Bytes32 (same 32-byte array)
        u.vout   = kv.first.index;
        u.amount = e.amount;
        out.push_back(u);
    }
    std::sort(out.begin(), out.end(), reserve_utxo_less);
    return out;
}

// Live reserve balance = sum of the discovered reserve UTXO amounts. This IS the
// `reserve_before` fed to hist_jackpot_apply on a jackpot block (spec §3: the
// reserve is whatever the constitutional addresses hold, not a stored counter).
inline int64_t reserve_balance(const std::vector<ReserveUtxo>& reserve) {
    int64_t s = 0;
    for (const auto& u : reserve) s += u.amount;
    return s;
}

} // namespace sost::jackpot
