// libFuzzer harness for the strict JSON reader.
//
// The reader sits on the path that decides which UTXOs a transaction spends, so
// the property under test is not "it parses our node's replies" — it is "it
// never misbehaves on input it did not expect". Any crash, read/write out of
// bounds, integer UB, unbounded allocation or hang is a finding.
//
// Build:  clang++ -std=c++17 -O1 -g -fsanitize=fuzzer,address,undefined \
//                 -I include tests/fuzz/fuzz_json_rpc.cpp src/json_rpc.cpp -o fuzz_json
#include "sost/json_rpc.h"
#include <cstdint>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    std::string in((const char*)data, size);

    // 1) raw document
    sost::json::Value v;
    std::string err;
    if (sost::json::parse(in, v, &err)) {
        // A successful parse must produce a coherent tree: walk it so any
        // corrupt internal state is touched, not merely constructed.
        struct W { static size_t walk(const sost::json::Value& n, int d) {
            if (d > sost::json::MAX_DEPTH + 2) return 0;   // the parser must have stopped us long before
            size_t n_nodes = 1;
            if (n.is_arr()) for (const auto& c : n.a) n_nodes += walk(c, d+1);
            if (n.is_obj()) for (const auto& kv : n.o) n_nodes += walk(kv.second, d+1);
            return n_nodes; } };
        volatile size_t sink = W::walk(v, 0);
        (void)sink;
    }

    // 2) as a JSON-RPC envelope
    sost::json::Value res;
    std::string e2;
    (void)sost::json::rpc_result(in, res, &e2);

    // 3) as an HTTP response (status-line handling is where a 401 must never
    //    become an empty body)
    std::string body;
    std::string e3;
    (void)sost::json::http_body(in, body, &e3);

    return 0;
}
