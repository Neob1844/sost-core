// p2p_addrbook.h — persistent, bounded peer address book (P2P only, never consensus).
//
// Replaces the old "snapshot of the currently connected outbound peers" peers.txt with a
// real address book:
//
//   * P1  entries are RESOLVED IPv4 literals ("a.b.c.d:port", taken from getpeername() of a
//         handshake-complete connection), never the hostname that was dialed. A node that
//         bootstrapped from seed-*.sostcore.com can therefore redial its peers after the
//         sostcore.com DNS records disappear.
//   * P2  bounded (ADDRBOOK_MAX = 256); an address enters the book only after a successful
//         VERS handshake (gossip-learned addresses are NEVER persisted raw); each entry keeps
//         last-success / last-attempt / failure counters; an entry that has been failing for
//         14 days is expired; at the cap the stalest entry is evicted.
//   * P3  candidate selection for outbound-target maintenance with /16 diversity: at most
//         `per16_cap` outbound peers per /16, unrepresented /16s first, exponential retry
//         back-off per address.
//
// File format (peers.txt next to --chain, mode 600, atomic tmp+fsync+rename):
//   # sost addrbook v2 (addr last_success last_attempt fails first_fail source)
//   1.2.3.4:19333 1760000000 1760000000 0 0 store
// An old binary reading this file sees "host:port <ignored>" — rfind(':') plus atoi() still
// yields the right host and port, so a downgrade keeps working. A legacy file (one
// "host:port" per line, possibly hostnames) is read by the new loader: IPv4 literals become
// book entries, hostnames are returned separately as legacy entries to dial once.
//
// Pure (no globals, no I/O except the explicit load/save helpers) so it is unit-testable.
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <string>
#include <vector>
#include <arpa/inet.h>
#include <sys/stat.h>
#include <unistd.h>

namespace sost {

// Where a peer / address came from. Exposed by getpeerinfo ("source") and stored in the book.
enum class PeerSource : uint8_t {
    UNKNOWN = 0, CONNECT, ADDNODE, STORE, SEEDSFILE, DNS, FALLBACK, GOSSIP, INBOUND
};

inline const char* peer_source_name(PeerSource s) {
    switch (s) {
        case PeerSource::CONNECT:   return "connect";
        case PeerSource::ADDNODE:   return "addnode";
        case PeerSource::STORE:     return "store";
        case PeerSource::SEEDSFILE: return "seedsfile";
        case PeerSource::DNS:       return "dns";
        case PeerSource::FALLBACK:  return "fallback";
        case PeerSource::GOSSIP:    return "gossip";
        case PeerSource::INBOUND:   return "inbound";
        default:                    return "unknown";
    }
}

inline PeerSource peer_source_from_name(const std::string& n) {
    static const PeerSource all[] = {PeerSource::CONNECT, PeerSource::ADDNODE, PeerSource::STORE,
        PeerSource::SEEDSFILE, PeerSource::DNS, PeerSource::FALLBACK, PeerSource::GOSSIP,
        PeerSource::INBOUND};
    for (auto s : all) if (n == peer_source_name(s)) return s;
    return PeerSource::UNKNOWN;
}

// "a.b.c.d:port" with a strict IPv4 literal and port 1..65535.
inline bool parse_ipv4_hostport(const std::string& s, std::string* ip_out, int* port_out) {
    auto c = s.rfind(':');
    if (c == std::string::npos || c == 0 || c + 1 >= s.size() || s.size() > 21) return false;
    std::string ip = s.substr(0, c), ps = s.substr(c + 1);
    for (char ch : ps) if (ch < '0' || ch > '9') return false;
    if (ps.size() > 5) return false;
    int port = atoi(ps.c_str());
    if (port < 1 || port > 65535) return false;
    struct in_addr a;
    if (inet_pton(AF_INET, ip.c_str(), &a) != 1) return false;
    char canon[INET_ADDRSTRLEN];
    if (!inet_ntop(AF_INET, &a, canon, sizeof(canon)) || ip != canon) return false;  // no "01.2.3.4"
    if (ip_out) *ip_out = ip;
    if (port_out) *port_out = port;
    return true;
}

// "/16" group of an IPv4 address or "ip:port" ("a.b"); "" if not an IPv4 literal.
inline std::string subnet16_of(const std::string& addr) {
    std::string ip = addr;
    auto c = addr.rfind(':');
    if (c != std::string::npos) ip = addr.substr(0, c);
    struct in_addr a;
    if (inet_pton(AF_INET, ip.c_str(), &a) != 1) return "";
    uint32_t v = ntohl(a.s_addr);
    return std::to_string((v >> 24) & 0xFF) + "." + std::to_string((v >> 16) & 0xFF);
}

struct AddrBookEntry {
    std::string addr;              // canonical "a.b.c.d:port"
    int64_t     last_success = 0;  // unix time of the last completed handshake
    int64_t     last_attempt = 0;  // unix time of the last dial attempt
    uint32_t    fails = 0;         // consecutive failed attempts since last_success
    int64_t     first_fail = 0;    // time of the first failure of the current failing streak
    PeerSource  source = PeerSource::UNKNOWN;  // how we first learned it
};

class AddrBook {
public:
    static constexpr size_t  MAX = 256;
    static constexpr int64_t EXPIRE_SECS = 14 * 86400;   // failing for 14 days -> dropped
    static constexpr int64_t BACKOFF_BASE = 60;          // retry back-off: 60 s * 2^fails
    static constexpr int64_t BACKOFF_MAX = 3600;         // capped at 1 h

    size_t size() const { return entries_.size(); }
    const std::vector<AddrBookEntry>& entries() const { return entries_; }
    bool contains(const std::string& addr) const { return find(addr) >= 0; }

    // A handshake with `addr` completed. Inserts (evicting the stalest entry at the cap) or
    // refreshes. Returns true if the entry is new. Non-IPv4-literal input is refused.
    bool mark_success(const std::string& addr, PeerSource src, int64_t now) {
        if (!parse_ipv4_hostport(addr, nullptr, nullptr)) return false;
        int i = find(addr);
        if (i >= 0) {
            auto& e = entries_[i];
            e.last_success = now; e.last_attempt = now; e.fails = 0; e.first_fail = 0;
            if (e.source == PeerSource::UNKNOWN) e.source = src;
            return false;
        }
        if (entries_.size() >= MAX) evict_one();
        AddrBookEntry e; e.addr = addr; e.last_success = now; e.last_attempt = now; e.source = src;
        entries_.push_back(e);
        return true;
    }

    void mark_attempt(const std::string& addr, int64_t now) {
        int i = find(addr); if (i >= 0) entries_[i].last_attempt = now;
    }

    void mark_failure(const std::string& addr, int64_t now) {
        int i = find(addr); if (i < 0) return;
        auto& e = entries_[i];
        e.last_attempt = now;
        if (e.fails == 0) e.first_fail = now;
        if (e.fails < 1000000) e.fails++;
    }

    // Drop entries that have been failing for EXPIRE_SECS. Returns the number removed.
    size_t expire(int64_t now) {
        size_t before = entries_.size();
        entries_.erase(std::remove_if(entries_.begin(), entries_.end(), [&](const AddrBookEntry& e) {
            return e.fails > 0 && e.first_fail > 0 && now - e.first_fail >= EXPIRE_SECS;
        }), entries_.end());
        return before - entries_.size();
    }

    // Is `addr` allowed to be redialed now (exponential back-off after failures)?
    bool backoff_ok(const std::string& addr, int64_t now) const {
        int i = find(addr); if (i < 0) return true;
        const auto& e = entries_[i];
        if (e.fails == 0) return true;
        int64_t wait = BACKOFF_BASE;
        for (uint32_t k = 1; k < e.fails && wait < BACKOFF_MAX; ++k) wait *= 2;
        if (wait > BACKOFF_MAX) wait = BACKOFF_MAX;
        return now - e.last_attempt >= wait;
    }

    // Book entries, most recently successful first (deterministic tie-break on addr).
    std::vector<std::string> by_recency() const {
        std::vector<AddrBookEntry> v = entries_;
        std::sort(v.begin(), v.end(), [](const AddrBookEntry& a, const AddrBookEntry& b) {
            if (a.last_success != b.last_success) return a.last_success > b.last_success;
            return a.addr < b.addr;
        });
        std::vector<std::string> out; out.reserve(v.size());
        for (auto& e : v) out.push_back(e.addr);
        return out;
    }

    // ---- text (de)serialization ----
    std::string serialize() const {
        std::string s = "# sost addrbook v2 (addr last_success last_attempt fails first_fail source)\n";
        for (const auto& e : entries_) {
            char buf[160];
            snprintf(buf, sizeof(buf), "%s %lld %lld %u %lld %s\n", e.addr.c_str(),
                     (long long)e.last_success, (long long)e.last_attempt, e.fails,
                     (long long)e.first_fail, peer_source_name(e.source));
            s += buf;
        }
        return s;
    }

    // Parse v2 lines and legacy "host:port" lines. IPv4 literals become entries; legacy
    // hostname lines are appended to *legacy_hosts (bounded, validated) and not kept.
    void parse(const std::string& text, std::vector<std::string>* legacy_hosts) {
        entries_.clear();
        size_t pos = 0;
        while (pos < text.size()) {
            size_t nl = text.find('\n', pos);
            std::string ln = text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
            pos = (nl == std::string::npos) ? text.size() : nl + 1;
            while (!ln.empty() && (ln.back() == '\r' || ln.back() == ' ' || ln.back() == '\t')) ln.pop_back();
            if (ln.empty() || ln[0] == '#') continue;
            bool ctl = false;
            for (char c : ln) if ((unsigned char)c < 32 && c != '\t') { ctl = true; break; }
            if (ctl || ln.size() > 200) continue;
            std::vector<std::string> f;
            {
                size_t p = 0;
                while (p < ln.size()) {
                    size_t q = ln.find_first_of(" \t", p);
                    std::string t = ln.substr(p, q == std::string::npos ? std::string::npos : q - p);
                    if (!t.empty()) f.push_back(t);
                    if (q == std::string::npos) break;
                    p = q + 1;
                }
            }
            if (f.empty()) continue;
            if (!parse_ipv4_hostport(f[0], nullptr, nullptr)) {
                // legacy hostname:port entry (old peers.txt) — dial once, never re-persisted
                auto c = f[0].rfind(':');
                if (legacy_hosts && f.size() == 1 && c != std::string::npos && c > 0 && c + 1 < f[0].size()
                    && legacy_hosts->size() < 64) {
                    int port = atoi(f[0].substr(c + 1).c_str());
                    if (port > 0 && port < 65536) legacy_hosts->push_back(f[0]);
                }
                continue;
            }
            if (find(f[0]) >= 0 || entries_.size() >= MAX) continue;
            AddrBookEntry e; e.addr = f[0];
            if (f.size() >= 6) {
                e.last_success = atoll(f[1].c_str()); e.last_attempt = atoll(f[2].c_str());
                long long fl = atoll(f[3].c_str()); e.fails = (fl < 0) ? 0u : (uint32_t)std::min<long long>(fl, 1000000);
                e.first_fail = atoll(f[4].c_str()); e.source = peer_source_from_name(f[5]);
                if (e.last_success < 0) e.last_success = 0;
                if (e.last_attempt < 0) e.last_attempt = 0;
                if (e.first_fail < 0) e.first_fail = 0;
            } else {
                e.source = PeerSource::STORE;   // legacy IP line: a peer we were connected to
            }
            entries_.push_back(e);
        }
    }

    // Atomic, durable save (tmp + fflush + fsync + rename, mode 600). Never wipes a good
    // file with an empty book. Returns true on success.
    bool save_file(const std::string& path) const {
        if (entries_.empty()) return false;
        std::string tmp = path + ".tmp";
        FILE* fp = fopen(tmp.c_str(), "w");
        if (!fp) return false;
        std::string s = serialize();
        bool werr = fwrite(s.data(), 1, s.size(), fp) != s.size();
        if (fflush(fp) != 0) werr = true;
        if (!werr && fsync(fileno(fp)) != 0) werr = true;
        fclose(fp);
        if (werr) { unlink(tmp.c_str()); return false; }
        chmod(tmp.c_str(), 0600);
        return rename(tmp.c_str(), path.c_str()) == 0;
    }

    bool load_file(const std::string& path, std::vector<std::string>* legacy_hosts) {
        FILE* fp = fopen(path.c_str(), "r");
        if (!fp) return false;
        std::string text; char buf[4096]; size_t n;
        while ((n = fread(buf, 1, sizeof(buf), fp)) > 0 && text.size() < (1u << 20)) text.append(buf, n);
        fclose(fp);
        parse(text, legacy_hosts);
        return true;
    }

private:
    std::vector<AddrBookEntry> entries_;

    int find(const std::string& addr) const {
        for (size_t i = 0; i < entries_.size(); ++i) if (entries_[i].addr == addr) return (int)i;
        return -1;
    }
    void evict_one() {
        if (entries_.empty()) return;
        // stalest = most failures first, then oldest last_success, then addr (deterministic)
        size_t w = 0;
        for (size_t i = 1; i < entries_.size(); ++i) {
            const auto& a = entries_[i]; const auto& b = entries_[w];
            if (a.fails != b.fails) { if (a.fails > b.fails) w = i; continue; }
            if (a.last_success != b.last_success) { if (a.last_success < b.last_success) w = i; continue; }
            if (a.addr > b.addr) w = i;
        }
        entries_.erase(entries_.begin() + w);
    }
};

// ---- P3: outbound target maintenance -----------------------------------------------------
// Pick up to `max_pick` dial targets from `candidates` (in preference order), skipping:
//   * anything in `exclude` (already connected / being dialed / ourselves),
//   * addresses whose back-off has not elapsed (book),
//   * when enforce_diversity: candidates whose /16 already has `per16_cap` outbound peers
//     (counted in `outbound_per16`, updated as we pick).
// Candidates from a /16 with no outbound peer at all are taken before the rest.
inline std::vector<std::string> select_outbound_candidates(
    const std::vector<std::string>& candidates, const std::set<std::string>& exclude,
    const AddrBook& book, std::map<std::string, int> outbound_per16, int64_t now,
    size_t max_pick, bool enforce_diversity, int per16_cap = 2)
{
    std::vector<std::string> out;
    std::set<std::string> seen;
    for (int pass = 0; pass < 2 && out.size() < max_pick; ++pass) {
        for (const auto& c : candidates) {
            if (out.size() >= max_pick) break;
            if (seen.count(c) || exclude.count(c)) continue;
            if (!book.backoff_ok(c, now)) continue;
            std::string g = subnet16_of(c);
            int have = g.empty() ? 0 : outbound_per16[g];
            if (enforce_diversity) {
                if (!g.empty() && have >= per16_cap) continue;
                if (pass == 0 && have > 0) continue;        // first pass: new /16s only
            } else if (pass == 1) {
                break;                                       // single pass suffices
            }
            seen.insert(c);
            out.push_back(c);
            if (!g.empty()) outbound_per16[g] = have + 1;
        }
    }
    return out;
}

// ---- P4: VERS extension (backward compatible) ---------------------------------------------
// Legacy VERS = 41 bytes: height i64 | genesis 32 | capability u8. New nodes append
//   listen_port u16 LE (0 = not accepting inbound) | node_nonce u64 LE (self-connection check)
// = 51 bytes. Old nodes read only bytes 0..40 and ignore the rest; new nodes treat a 41-byte
// VERS as listen_port = 0 / nonce = 0 (unknown).
static constexpr uint8_t CAP_LISTEN = 0x02;   // VERS capability bit: listen port appended
static constexpr size_t  VERS_LEGACY_LEN = 41;
static constexpr size_t  VERS_EXT_LEN = 51;

struct VersExt { uint16_t listen_port = 0; uint64_t nonce = 0; bool present = false; };

inline VersExt parse_vers_ext(const uint8_t* p, size_t n) {
    VersExt v;
    if (n < VERS_EXT_LEN) return v;
    if (!(p[40] & CAP_LISTEN)) return v;
    v.listen_port = (uint16_t)(p[41] | (p[42] << 8));
    uint64_t x = 0;
    for (int i = 7; i >= 0; --i) x = (x << 8) | p[43 + i];
    v.nonce = x;
    v.present = true;
    return v;
}

inline void write_vers_ext(uint8_t* p /* >= 51 bytes, bytes 0..40 already set */,
                           uint16_t listen_port, uint64_t nonce) {
    p[40] |= CAP_LISTEN;
    p[41] = (uint8_t)(listen_port & 0xFF); p[42] = (uint8_t)(listen_port >> 8);
    for (int i = 0; i < 8; ++i) p[43 + i] = (uint8_t)(nonce >> (8 * i));
}

// ---- P5/P6: bootstrap plan ----------------------------------------------------------------
// Ordered list of (source, "host:port") a node with no --connect dials at boot. --addnode
// entries are always included (they never disable discovery); store -> seeds.txt -> DNS
// seeds -> compiled-in fallback IPs follow. With --connect the plan is the connect list only
// (exclusive) plus the addnode list. With --noseed DNS seeds and fallback IPs are omitted.
struct BootTarget { PeerSource source; std::string hostport; };

inline std::vector<BootTarget> bootstrap_plan(
    const std::vector<std::string>& connect, const std::vector<std::string>& addnode,
    const std::vector<std::string>& store, const std::vector<std::string>& seedsfile,
    const std::vector<std::string>& dns_seeds, const std::vector<std::string>& fallback_ips,
    bool noseed)
{
    std::vector<BootTarget> out;
    std::set<std::string> seen;
    auto add = [&](PeerSource s, const std::vector<std::string>& v) {
        for (const auto& a : v) if (!a.empty() && seen.insert(a).second) out.push_back({s, a});
    };
    if (!connect.empty()) { add(PeerSource::CONNECT, connect); add(PeerSource::ADDNODE, addnode); return out; }
    add(PeerSource::ADDNODE, addnode);
    if (noseed) return out;
    add(PeerSource::STORE, store);
    add(PeerSource::SEEDSFILE, seedsfile);
    add(PeerSource::DNS, dns_seeds);
    add(PeerSource::FALLBACK, fallback_ips);
    return out;
}

// Ordered list of (source, "host:port") the node redials when it has NO peer left. The same
// exclusivity as bootstrap_plan holds on every reconnect: with --connect only the connect list
// plus the addnode list, never the address book (peers.txt), gossiped addresses, seeds.txt, DNS
// seeds or fallback IPs. Without --connect: connect(empty), addnode, store, gossip, then the
// seed sources unless --noseed.
inline std::vector<BootTarget> reconnect_plan(
    const std::vector<std::string>& connect, const std::vector<std::string>& addnode,
    const std::vector<std::string>& store, const std::vector<std::string>& gossip,
    const std::vector<std::string>& seedsfile, const std::vector<std::string>& dns_seeds,
    const std::vector<std::string>& fallback_ips, bool noseed)
{
    std::vector<BootTarget> out;
    auto add = [&](PeerSource s, const std::vector<std::string>& v) {
        for (const auto& a : v) if (!a.empty()) out.push_back({s, a});
    };
    add(PeerSource::CONNECT, connect);
    add(PeerSource::ADDNODE, addnode);
    if (!connect.empty()) return out;
    add(PeerSource::STORE, store);
    add(PeerSource::GOSSIP, gossip);
    if (noseed) return out;
    add(PeerSource::SEEDSFILE, seedsfile);
    add(PeerSource::DNS, dns_seeds);
    add(PeerSource::FALLBACK, fallback_ips);
    return out;
}

} // namespace sost
