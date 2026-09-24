// libFuzzer harness for the transaction and block-header deserialisers.
//
// These parse attacker-controlled bytes straight off the P2P wire, so the
// property under test is: no input — however malformed, truncated, or with
// extreme counts/sizes — may crash, read out of bounds, overflow, or hang.
// A false return is fine; a sanitiser finding is a bug.
//
// Build:  clang++ -std=c++17 -O1 -g -fsanitize=fuzzer,address,undefined \
//                 -I include tests/fuzz/fuzz_tx_block.cpp \
//                 src/transaction.cpp src/block.cpp -o fuzz_txblock
#include "sost/transaction.h"
#include "sost/block.h"
#include <vector>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    std::vector<sost::Byte> buf(data, data + size);

    // 1. whole-transaction deserialiser (rejects trailing bytes)
    { sost::Transaction tx; std::string err;
      (void)sost::Transaction::Deserialize(buf, tx, &err); }

    // 2. transaction-at-offset (used by the block parser): sweep a few offsets
    for (size_t off : {size_t(0), size/4, size/2}) {
        size_t o = off; sost::Transaction tx; std::string err;
        (void)sost::Transaction::DeserializeFrom(buf, o, tx, &err);
    }

    // 3. block-header deserialiser
    { sost::BlockHeader hdr; std::string err;
      (void)sost::BlockHeader::DeserializeStandalone(buf, hdr, &err); }

    return 0;
}
