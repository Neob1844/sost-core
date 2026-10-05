// p2p_addr_filter.h — pure, testable predicate for screening GOSSIPED peer addresses.
//
// D1/D2 peer autonomy: addresses a peer gossips to us (via ADDR) are untrusted. Before we
// ever resolve or dial one on a public network we require it to be a routable public IPv4
// literal. This closes (a) blind SSRF / internal-port probing and (b) DNS abuse (no
// getaddrinfo on an attacker-supplied hostname). Operator-trusted sources (--connect,
// seeds.txt, DEFAULT_SEEDS, the persisted peer store) bypass this and are never screened.
//
// Pure (no globals) so it is unit-testable in isolation. `allow_private` is wired to
// "profile == DEV" by the caller, so the loopback devnet lab keeps working while mainnet /
// testnet are screened.
#pragma once
#include <string>
#include <cstdint>
#include <arpa/inet.h>

namespace sost {

inline bool p2p_gossip_target_ok(const std::string& host, bool allow_private){
    if(allow_private) return true;                               // devnet lab (127.0.0.x)
    struct in_addr a;
    if(inet_pton(AF_INET, host.c_str(), &a) != 1) return false;  // must be an IPv4 literal (no DNS on gossip)
    uint32_t ip = ntohl(a.s_addr);
    uint8_t o1=(uint8_t)((ip>>24)&0xFF), o2=(uint8_t)((ip>>16)&0xFF);
    if(o1==0 || o1==127 || o1>=224) return false;                // this-host / loopback / multicast+reserved(240+)
    if(o1==10) return false;                                     // 10.0.0.0/8
    if(o1==172 && o2>=16 && o2<=31) return false;                // 172.16.0.0/12
    if(o1==192 && o2==168) return false;                         // 192.168.0.0/16
    if(o1==169 && o2==254) return false;                         // 169.254.0.0/16 (link-local / cloud metadata)
    if(o1==100 && o2>=64 && o2<=127) return false;               // 100.64.0.0/10 (CGNAT)
    return true;                                                 // routable public IPv4
}

} // namespace sost
