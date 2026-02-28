// address.cpp — SOST address encoding (sost1 + hex(pkh))
#include "sost/address.h"
#include <cstring>

namespace sost {

static const char HEX_CHARS[] = "0123456789abcdef";

static int hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + c - 'a';
    if (c >= 'A' && c <= 'F') return 10 + c - 'A';
    return -1;
}

std::string address_encode(const PubKeyHash& pkh) {
    std::string addr = "sost1";
    addr.reserve(45);
    for (int i = 0; i < 20; ++i) {
        addr += HEX_CHARS[pkh[i] >> 4];
        addr += HEX_CHARS[pkh[i] & 0x0F];
    }
    return addr;
}

bool address_decode(const std::string& addr, PubKeyHash& out_pkh) {
    if (addr.size() != 45) return false;
    if (addr.substr(0, 5) != "sost1") return false;

    for (int i = 0; i < 20; ++i) {
        int hi = hex_val(addr[5 + i * 2]);
        int lo = hex_val(addr[5 + i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out_pkh[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

bool address_valid(const std::string& addr) {
    PubKeyHash tmp{};
    return address_decode(addr, tmp);
}

std::string pubkey_to_address(const PubKey& pubkey) {
    PubKeyHash pkh = ComputePubKeyHash(pubkey);
    return address_encode(pkh);
}

} // namespace sost
