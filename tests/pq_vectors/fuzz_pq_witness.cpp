// SOST Post-Quantum Migration V3 — libFuzzer target for the witness parser.
//
// STANDALONE / OPTIONAL. NOT part of the node build. It only runs if a fuzzing
// toolchain is available. The parser must NEVER crash, over-read, or allocate
// unboundedly on ANY input — it must always return one of the enumerated
// PqParseCode values. Build (clang):
//
//   clang++ -std=c++17 -g -O1 -fsanitize=fuzzer,address,undefined \
//       -I prototype/pq tests/pq_vectors/fuzz_pq_witness.cpp -o /tmp/fuzz_pq
//   /tmp/fuzz_pq -max_total_time=60
//
// If clang / libFuzzer is not present this file is simply not built — it is not
// wired into CMake and cannot affect mainnet consensus.
//
// Author: NeoB.
#include <cstdint>
#include <cstddef>
#include "pq_witness.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    sost::pq_proto::Bytes in(data, data + size);
    sost::pq_proto::PqWitness w;
    // Must always return deterministically; must never crash / OOM / over-read.
    volatile auto rc = sost::pq_proto::parse_witness(in, w);
    (void)rc;
    return 0;
}
