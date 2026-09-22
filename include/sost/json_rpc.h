#pragma once
// ============================================================================
// Strict JSON reader for RPC responses.
//
// Why this exists: sost-cli parsed node responses by hand — find('{'),
// rfind(']'), substr — in four places, including the path that decides which
// UTXOs a transaction spends. That is how an auth-rejected query became
// "0 UTXOs" twice in this file's history (see the comments at sost-cli.cpp:334
// and :366). A wallet tool must never confuse "the node said no" with "you have
// nothing".
//
// Deliberately NOT a general JSON library and deliberately not a third-party
// one: this is the layer that reads money, so it is small enough to audit in
// one sitting and has no supply chain. It is strict on purpose — anything it
// does not fully understand is an error, never a silent default:
//
//   * no trailing content after the top-level value
//   * no NaN/Infinity, no comments, no single quotes, no trailing commas
//   * duplicate object keys rejected (a response that says "amount" twice is
//     not something to guess about)
//   * depth and length bounds, so a hostile or corrupted body cannot blow the
//     stack or allocate unboundedly
//   * integers kept exactly as int64 when they are integral; a value that does
//     not fit is an error rather than a silent double
//
// Consensus-neutral: used by the CLI and tools only. Nothing here touches block
// or transaction validation.
// ============================================================================
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace sost::json {

inline constexpr int    MAX_DEPTH      = 64;
inline constexpr size_t MAX_INPUT_SIZE = 64u * 1024u * 1024u;   // 64 MB

struct Value;
using Object = std::map<std::string, Value>;
using Array  = std::vector<Value>;

struct Value {
    enum class T { Null, Bool, Int, Real, Str, Arr, Obj };
    T           type{T::Null};
    bool        b{false};
    int64_t     i{0};
    double      d{0.0};
    std::string s;
    Array       a;
    Object      o;

    bool is_null() const { return type == T::Null; }
    bool is_obj()  const { return type == T::Obj;  }
    bool is_arr()  const { return type == T::Arr;  }

    // Lookups that never throw and never invent a value: `found` tells the
    // caller whether the field was there, so a missing amount is not a zero.
    const Value* find(const std::string& key) const {
        if (type != T::Obj) return nullptr;
        auto it = o.find(key);
        return it == o.end() ? nullptr : &it->second;
    }
    bool get_int(const std::string& key, int64_t& out) const {
        const Value* v = find(key);
        if (!v) return false;
        if (v->type == T::Int)  { out = v->i; return true; }
        return false;                       // a real/string amount is NOT an int
    }
    bool get_str(const std::string& key, std::string& out) const {
        const Value* v = find(key);
        if (!v || v->type != T::Str) return false;
        out = v->s; return true;
    }
    bool get_bool(const std::string& key, bool& out) const {
        const Value* v = find(key);
        if (!v || v->type != T::Bool) return false;
        out = v->b; return true;
    }
};

// Parse a complete JSON document. Returns false and fills `err` on ANY
// deviation. `err` is safe to show a user: it never echoes the payload.
bool parse(const std::string& text, Value& out, std::string* err = nullptr);

// Convenience for JSON-RPC bodies: extracts `result`, or reports the `error`
// object's message. Returns false when the body is not a valid JSON-RPC reply,
// when it carries an error, or when `result` is absent — each with a distinct
// message, so a caller can tell them apart.
bool rpc_result(const std::string& body, Value& result_out, std::string* err = nullptr);

// Strip an HTTP response down to its body. Returns false if the status line
// reports a non-2xx code, putting "http_<code>" in `err` — so 401 stops being
// indistinguishable from an empty result.
bool http_body(const std::string& response, std::string& body_out, std::string* err = nullptr);

} // namespace sost::json
