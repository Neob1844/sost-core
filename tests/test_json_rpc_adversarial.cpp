// Adversarial corpus for the strict JSON reader.
//
// The unit tests say it reads correct input correctly. This file says it FAILS
// SAFELY on input it never expected — which is the property that matters for a
// reader sitting on the path that decides which UTXOs get spent.
//
// Deterministic on purpose (fixed seed, fixed iteration count): a wallet tool
// must be re-verifiable byte for byte by anyone, and an open-ended fuzz session
// is not. Build it under sanitizers to make the assertions real:
//   clang++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=undefined \
//           -I include tests/test_json_rpc_adversarial.cpp src/json_rpc.cpp -o t
//
// The contract under test, for EVERY input: parse() either returns true with a
// coherent tree, or returns false with an error string. It never crashes, never
// reads out of bounds, never overflows, never hangs, never allocates without
// bound, and never half-fills the output.
#include "sost/json_rpc.h"
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>

using namespace sost::json;

static int g_pass = 0, g_fail = 0;
#define TEST(m,c) do{ if(c){++g_pass;} else {printf("  *** FAIL: %s [%d]\n",m,__LINE__);++g_fail;} }while(0)

// Deterministic PRNG — no <random> so the corpus is identical on every platform.
static uint64_t rng_state = 0x50571C0FFEEULL;
static uint64_t rnd() {
    rng_state ^= rng_state << 13; rng_state ^= rng_state >> 7; rng_state ^= rng_state << 17;
    return rng_state;
}

// Run one input through every entry point. Returns false only if an invariant
// broke; a rejected parse is a PASS.
static bool run_one(const std::string& in) {
    Value v; std::string err;
    bool ok = parse(in, v, &err);
    if (!ok && err.empty()) return false;              // a refusal must say why
    if (ok) {
        // Walk it: a tree that parsed must be traversable without surprises.
        struct W { static size_t walk(const Value& n, int d, bool& bad) {
            if (d > MAX_DEPTH + 2) { bad = true; return 0; }   // the depth bound must have stopped us
            size_t c = 1;
            if (n.is_arr()) for (const auto& x : n.a) c += walk(x, d + 1, bad);
            if (n.is_obj()) for (const auto& kv : n.o) c += walk(kv.second, d + 1, bad);
            return c; } };
        bool bad = false;
        (void)W::walk(v, 0, bad);
        if (bad) return false;
    }
    Value r; std::string e2;
    (void)rpc_result(in, r, &e2);
    std::string body; std::string e3;
    (void)http_body(in, body, &e3);
    return true;
}

int main() {
    // ---- seed corpus: the shapes a node reply actually takes -----------------
    std::vector<std::string> seeds = {
        R"({"jsonrpc":"2.0","id":1,"result":[{"txid":"ab","vout":0,"amount_stocks":392550432,"height":27263,"coinbase":true,"mature":false,"spendable":false,"output_type":1}]})",
        R"({"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"unauthorized"}})",
        "HTTP/1.1 401 Unauthorized\r\nContent-Length: 7\r\n\r\n{\"e\":1}",
        "HTTP/1.1 200 OK\r\n\r\n{\"result\":[]}",
        "HTTP/1.1 500 Internal Server Error\r\n\r\n",
        R"({"s":"😀A\\\/\b\f\n\r\t"})",
        "[9223372036854775807,-9223372036854775808,1e308,0.1]",
        R"({"a":1,"a":2})",
        "", "null", "[]", "{}", "\"x\"", "0",
    };
    { std::string deep; for (int i=0;i<MAX_DEPTH+10;i++) deep += '[';
      for (int i=0;i<MAX_DEPTH+10;i++) deep += ']'; seeds.push_back(deep); }

    printf("== seed corpus ==\n");
    { bool all=true; for (const auto& s : seeds) if (!run_one(s)) all=false;
      TEST("every seed handled without breaking an invariant", all); }

    // ---- a realistic large reply, and every truncation of it ----------------
    printf("== large reply + truncation at every byte ==\n");
    std::string big = "{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":[";
    for (int k = 0; k < 400; ++k) {
        if (k) big += ',';
        big += "{\"txid\":\"aabbccdd\",\"vout\":" + std::to_string(k % 4)
             + ",\"amount_stocks\":392550432,\"height\":" + std::to_string(20000 + k)
             + ",\"coinbase\":true,\"mature\":" + ((k % 3) ? "true" : "false") + "}";
    }
    big += "]}";
    {
        Value r; std::string err;
        TEST("the complete reply parses", rpc_result(big, r, &err) && r.is_arr() && r.a.size() == 400);
        // Truncation is what a dropped connection looks like. Not one prefix may
        // parse as a shorter-but-valid reply: that is how a partial transfer
        // becomes a wrong UTXO set.
        int handled = 0, accepted = 0;
        for (size_t n = 1; n < big.size(); ++n) {
            std::string pre = big.substr(0, n);
            if (run_one(pre)) ++handled;
            Value rv; std::string e;
            if (rpc_result(pre, rv, &e)) ++accepted;
        }
        TEST("every truncation handled safely", handled == (int)big.size() - 1);
        TEST("no truncation is accepted as a result", accepted == 0);
    }

    // ---- byte mutations of the seeds (deterministic) ------------------------
    printf("== 200,000 deterministic mutations ==\n");
    {
        int broke = 0;
        for (int it = 0; it < 200000; ++it) {
            std::string s = seeds[rnd() % seeds.size()];
            if (s.empty()) s = "{}";
            int ops = 1 + (int)(rnd() % 4);
            for (int o = 0; o < ops; ++o) {
                if (s.empty()) break;
                size_t at = (size_t)(rnd() % s.size());
                switch (rnd() % 3) {
                    case 0: s[at] = (char)(rnd() % 256); break;              // flip
                    case 1: s.insert(at, 1, (char)(rnd() % 256)); break;     // insert
                    case 2: s.erase(at, 1); break;                           // delete
                }
            }
            if (!run_one(s)) ++broke;
        }
        TEST("no mutation broke an invariant", broke == 0);
    }

    // ---- explicit memory / range bounds -------------------------------------
    printf("== bounds: memory and integers ==\n");
    {
        std::string over(MAX_INPUT_SIZE + 1, 'a');
        std::string err; Value v;
        TEST("input over MAX_INPUT_SIZE refused before parsing", !parse(over, v, &err) && err == "input too large");
    }
    {   // a very long string and a very wide array, both inside the limits
        std::string longstr = "{\"s\":\"" + std::string(2 * 1024 * 1024, 'x') + "\"}";
        Value v; TEST("2 MB string value parses", parse(longstr, v));
        std::string wide = "["; for (int i = 0; i < 100000; ++i) { if (i) wide += ','; wide += "1"; }
        wide += "]";
        Value w; TEST("100k-element array parses", parse(wide, w) && w.a.size() == 100000);
    }
    {   // many duplicate keys must be refused, not silently collapsed
        std::string dup = "{"; for (int i = 0; i < 1000; ++i) { if (i) dup += ','; dup += "\"k\":1"; }
        dup += "}";
        Value v; TEST("repeated duplicate keys refused", !parse(dup, v));
    }
    {   // integers at and beyond the int64 edge
        Value v;
        TEST("int64 min parses exactly", parse("[-9223372036854775808]", v) && v.a[0].type == Value::T::Int);
        TEST("int64 max+1 refused", !parse("[9223372036854775808]", v));
        TEST("huge exponent refused as non-finite", !parse("[1e400]", v));
        TEST("amount as string is not an int", parse(R"({"amount_stocks":"392550432"})", v)
             && [&]{ int64_t a = 0; return !v.get_int("amount_stocks", a); }());
    }
    {   // HTTP framing: a status line must never be mistaken for a body
        std::string body, err;
        TEST("headers without body: 200 gives empty body",
             http_body("HTTP/1.1 200 OK\r\n\r\n", body, &err) && body.empty());
        Value empty_res;
        TEST("empty body is not a valid result",
             !rpc_result(body, empty_res, &err));
        err.clear();
        TEST("403 reported as http_403", !http_body("HTTP/1.1 403 Forbidden\r\n\r\n{}", body, &err) && err == "http_403");
        err.clear();
        TEST("garbled status refused", !http_body("HTTP/1.1\r\n\r\n{}", body, &err));
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
