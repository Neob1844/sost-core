// Sweep planner — see include/sost/sweep.h.
#include "sost/sweep.h"

#include "sost/consensus_constants.h"
#include "sost/tx_validation.h"
#include "sost/transaction.h"
#include "sost/json_rpc.h"

#include <algorithm>
#include <fstream>
#include <sstream>

namespace sost::sweep {

PlanLimits default_limits() {
    PlanLimits L;
    L.max_tx_bytes_standard      = MAX_TX_BYTES_STANDARD;
    L.max_inputs_standard        = MAX_INPUTS_STANDARD;
    L.fee_rate_stocks_per_byte   = 1;      // policy minimum relay fee
    L.byte_margin                = 256;    // headroom: never sit on the limit
    return L;
}

size_t policy_size(size_t n_in, size_t n_out) {
    // Build a structurally identical transaction and ask the REAL estimator —
    // the one ValidateTransactionPolicy calls. Reimplementing the formula here
    // would let the planner and the mempool drift apart silently.
    Transaction t;
    t.inputs.resize(n_in);
    t.outputs.resize(n_out);          // payload-free outputs
    return EstimateTxSerializedSize(t);
}

size_t max_inputs_per_batch(const PlanLimits& L) {
    const size_t budget = (size_t)std::max(0, L.max_tx_bytes_standard - L.byte_margin);
    size_t best = 0;
    // Walk up to the input-count limit and stop at the last count that fits.
    for (size_t n = 1; n <= (size_t)L.max_inputs_standard; ++n) {
        if (policy_size(n, 1) <= budget) best = n; else break;
    }
    return best;
}

std::vector<Utxo> filter_spendable(const std::vector<Utxo>& all,
                                   const std::vector<std::string>& consumed_keys_in) {
    std::vector<std::string> consumed = consumed_keys_in;
    std::sort(consumed.begin(), consumed.end());
    std::vector<Utxo> out;
    out.reserve(all.size());
    for (const auto& u : all) {
        if (!u.mature || !u.spendable) continue;          // maturity is a hard filter
        if (std::binary_search(consumed.begin(), consumed.end(), u.key())) continue;
        out.push_back(u);
    }
    return out;
}

std::vector<Batch> plan_batches(std::vector<Utxo> spendable, const PlanLimits& L) {
    // Deterministic order: the same chain state must always produce the same
    // plan, so two runs can be diffed and a plan can be reviewed before use.
    std::sort(spendable.begin(), spendable.end(), [](const Utxo& a, const Utxo& b){
        if (a.txid != b.txid) return a.txid < b.txid;
        return a.vout < b.vout;
    });

    const size_t cap = max_inputs_per_batch(L);
    std::vector<Batch> out;
    if (cap == 0) return out;

    for (size_t i = 0; i < spendable.size(); i += cap) {
        Batch b;
        const size_t end = std::min(i + cap, spendable.size());
        for (size_t k = i; k < end; ++k) {
            b.inputs.push_back(spendable[k]);
            b.total_in += spendable[k].amount;
        }
        // Size and fee come from THIS batch's own shape, not from the cap.
        b.est_bytes = policy_size(b.inputs.size(), 1);
        b.fee = (int64_t)b.est_bytes * L.fee_rate_stocks_per_byte;
        // Pay for the size the tx will actually have; policy compares fee against
        // the estimate, so matching it exactly is enough, but round up a little
        // rather than land on the boundary.
        b.fee += 64;
        b.to_destination = b.total_in - b.fee;
        out.push_back(std::move(b));
    }
    return out;
}

// ---------------------------------------------------------------------------
// Journal
// ---------------------------------------------------------------------------
std::vector<std::string> consumed_keys(const Journal& j) {
    std::vector<std::string> out;
    for (const auto& e : j.entries)
        for (const auto& k : e.consumed) out.push_back(k);
    return out;
}

static std::string esc(const std::string& s) {
    std::string o;
    for (char c : s) {
        switch (c) {
            case '"':  o += "\\\""; break;
            case '\\': o += "\\\\"; break;
            case '\n': o += "\\n";  break;
            case '\r': o += "\\r";  break;
            case '\t': o += "\\t";  break;
            default:
                if ((unsigned char)c < 0x20) { char b[8]; snprintf(b,sizeof b,"\\u%04x",c); o += b; }
                else o += c;
        }
    }
    return o;
}

bool journal_save(const std::string& path, const Journal& j, std::string* err) {
    std::ostringstream s;
    s << "{\n  \"destination\": \"" << esc(j.destination) << "\",\n"
      << "  \"source_address\": \"" << esc(j.source_address) << "\",\n"
      << "  \"entries\": [\n";
    for (size_t i = 0; i < j.entries.size(); ++i) {
        const auto& e = j.entries[i];
        s << "    {\"batch_index\": " << e.batch_index
          << ", \"txid\": \"" << esc(e.txid) << "\""
          << ", \"confirmed_height\": " << e.confirmed_height
          << ", \"confirmed_block_hash\": \"" << esc(e.confirmed_block_hash) << "\""
          << ", \"total_in\": " << e.total_in
          << ", \"fee\": " << e.fee
          << ", \"consumed\": [";
        for (size_t k = 0; k < e.consumed.size(); ++k) {
            if (k) s << ",";
            s << "\"" << esc(e.consumed[k]) << "\"";
        }
        s << "]}" << (i + 1 < j.entries.size() ? "," : "") << "\n";
    }
    s << "  ]\n}\n";

    // Write beside the target and rename: a half-written journal is worse than
    // no journal, because it would under-report what was already spent.
    const std::string tmp = path + ".tmp";
    { std::ofstream f(tmp, std::ios::trunc);
      if (!f) { if (err) *err = "cannot open " + tmp; return false; }
      f << s.str();
      if (!f) { if (err) *err = "write failed"; return false; } }
    if (std::rename(tmp.c_str(), path.c_str()) != 0) {
        if (err) *err = "rename failed";
        return false;
    }
    return true;
}

bool journal_load(const std::string& path, Journal& out, std::string* err) {
    std::ifstream f(path);
    if (!f) { if (err) *err = "no_journal"; return false; }
    std::stringstream ss; ss << f.rdbuf();
    json::Value doc;
    std::string perr;
    if (!json::parse(ss.str(), doc, &perr)) {
        if (err) *err = "corrupt journal: " + perr;   // never treated as "nothing spent"
        return false;
    }
    if (!doc.is_obj()) { if (err) *err = "journal is not an object"; return false; }
    doc.get_str("destination", out.destination);
    doc.get_str("source_address", out.source_address);
    const json::Value* arr = doc.find("entries");
    if (!arr || !arr->is_arr()) { if (err) *err = "journal has no entries array"; return false; }
    for (const auto& e : arr->a) {
        JournalEntry je;
        int64_t bi = 0;
        if (e.get_int("batch_index", bi)) je.batch_index = (int)bi;
        e.get_str("txid", je.txid);
        e.get_int("confirmed_height", je.confirmed_height);
        e.get_str("confirmed_block_hash", je.confirmed_block_hash);
        e.get_int("total_in", je.total_in);
        e.get_int("fee", je.fee);
        const json::Value* c = e.find("consumed");
        if (c && c->is_arr())
            for (const auto& k : c->a)
                if (k.type == json::Value::T::Str) je.consumed.push_back(k.s);
        out.entries.push_back(std::move(je));
    }
    return true;
}

} // namespace sost::sweep
