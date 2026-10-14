// Unit test of the persistent address book (include/sost/p2p_addrbook.h), the exact code
// sost-node.cpp uses for peers.txt (P1/P2), outbound candidate selection (P3), the VERS
// extension (P4) and the bootstrap plan (P5/P6).
#include "sost/p2p_addrbook.h"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>

using namespace sost;

static int pass_n = 0, fail_n = 0;
static void CK(bool c, const char* m) { if (c) pass_n++; else { fail_n++; printf("FAIL: %s\n", m); } }

static std::string tmpdir() {
    char t[] = "/tmp/d1_addrbook_XXXXXX";
    char* d = mkdtemp(t);
    return d ? std::string(d) : std::string("/tmp");
}
static std::string slurp(const std::string& p) {
    FILE* f = fopen(p.c_str(), "r"); if (!f) return "";
    std::string s; char b[4096]; size_t n; while ((n = fread(b, 1, sizeof(b), f)) > 0) s.append(b, n);
    fclose(f); return s;
}

int main() {
    const int64_t T = 1760000000;
    std::string dir = tmpdir();
    std::string path = dir + "/peers.txt";

    // ---- parse_ipv4_hostport / subnet16
    CK(parse_ipv4_hostport("1.2.3.4:19333", nullptr, nullptr), "ipv4 literal ok");
    CK(!parse_ipv4_hostport("seed-eu.sostcore.com:19333", nullptr, nullptr), "hostname refused");
    CK(!parse_ipv4_hostport("1.2.3.4", nullptr, nullptr), "no port refused");
    CK(!parse_ipv4_hostport("1.2.3.4:0", nullptr, nullptr), "port 0 refused");
    CK(!parse_ipv4_hostport("1.2.3.4:65536", nullptr, nullptr), "port 65536 refused");
    CK(!parse_ipv4_hostport("01.2.3.4:1", nullptr, nullptr), "non-canonical ip refused");
    CK(!parse_ipv4_hostport("1.2.3.4:12a", nullptr, nullptr), "junk port refused");
    CK(subnet16_of("203.0.113.9:19333") == "203.0", "subnet16 of ip:port");
    CK(subnet16_of("198.51.100.7") == "198.51", "subnet16 of ip");
    CK(subnet16_of("seed.sostcore.com:19333") == "", "subnet16 of hostname empty");

    // ---- P1: only resolved IPv4 literals enter the book
    AddrBook b;
    CK(!b.mark_success("seed-eu.sostcore.com:19333", PeerSource::DNS, T), "hostname never stored");
    CK(b.mark_success("212.132.108.244:19333", PeerSource::DNS, T), "resolved seed IP stored");
    CK(!b.mark_success("212.132.108.244:19333", PeerSource::DNS, T + 5), "refresh is not new");
    CK(b.size() == 1, "dedupe");

    // ---- persistence round trip (mode 600, atomic)
    b.mark_success("203.0.113.5:19333", PeerSource::GOSSIP, T + 10);
    b.mark_failure("203.0.113.5:19333", T + 20);
    CK(b.save_file(path), "save ok");
    struct stat st; stat(path.c_str(), &st);
    CK((st.st_mode & 0777) == 0600, "mode 600");
    CK(access((path + ".tmp").c_str(), F_OK) != 0, "no tmp left behind");
    AddrBook r; std::vector<std::string> legacy;
    CK(r.load_file(path, &legacy), "load ok");
    CK(r.size() == 2 && legacy.empty(), "round trip size");
    {
        bool okf = false;
        for (auto& e : r.entries()) if (e.addr == "203.0.113.5:19333")
            okf = e.fails == 1 && e.first_fail == T + 20 && e.last_success == T + 10 && e.source == PeerSource::GOSSIP;
        CK(okf, "round trip keeps counters and source");
    }
    CK(r.by_recency()[0] == "203.0.113.5:19333", "most recent success first");

    // ---- downgrade compatibility: an OLD binary's loader (rfind(':') + atoi) still gets host:port
    {
        std::string text = slurp(path); size_t okc = 0, lines = 0, pos = 0;
        while (pos < text.size()) {
            size_t nl = text.find('\n', pos); std::string ln = text.substr(pos, nl - pos); pos = nl + 1;
            if (ln.find(':') == std::string::npos) continue;   // old loader skips colon-less lines
            ++lines; auto c = ln.rfind(':');
            std::string host = ln.substr(0, c); int port = atoi(ln.substr(c + 1).c_str());
            if (parse_ipv4_hostport(host + ":" + std::to_string(port), nullptr, nullptr)) ++okc;
        }
        CK(lines == 2 && okc == 2, "old loader parses v2 lines as host:port");
        CK(text.rfind("#", 0) == 0 && text.substr(0, text.find('\n')).find(':') == std::string::npos,
           "header line has no ':' (old loader ignores it)");
    }

    // ---- legacy peers.txt (hostnames + IPs + junk)
    {
        FILE* f = fopen(path.c_str(), "w");
        fprintf(f, "seed-eu.sostcore.com:19333\n9.9.9.9:19333\nnocolon\n\nbad\x01host:1\n# comment\n8.8.4.4:19444\n");
        fclose(f);
        AddrBook l; std::vector<std::string> lh;
        l.load_file(path, &lh);
        CK(l.size() == 2, "legacy: 2 IP entries kept");
        CK(lh.size() == 1 && lh[0] == "seed-eu.sostcore.com:19333", "legacy: hostname returned to dial once");
        bool src_ok = true; for (auto& e : l.entries()) if (e.source != PeerSource::STORE) src_ok = false;
        CK(src_ok, "legacy IP lines tagged store");
    }

    // ---- bounded: 300 successes -> 256; stalest evicted
    {
        AddrBook c;
        for (int i = 0; i < 300; i++) {
            char a[32]; snprintf(a, sizeof(a), "100.%d.%d.1:19333", i / 200, i % 200 + 1);
            c.mark_success(a, PeerSource::GOSSIP, T + i);
        }
        CK(c.size() == AddrBook::MAX, "bounded at 256");
        CK(!c.contains("100.0.1.1:19333"), "oldest evicted");
        CK(c.contains("100.1.100.1:19333"), "newest kept");
    }

    // ---- empty book never wipes a good file
    {
        AddrBook g; g.mark_success("5.6.7.8:19333", PeerSource::STORE, T); g.save_file(path);
        AddrBook e; CK(!e.save_file(path), "empty save refused");
        AddrBook chk; chk.load_file(path, nullptr); CK(chk.size() == 1, "file intact after empty save");
    }

    // ---- 14-day expiry + back-off
    {
        AddrBook x;
        x.mark_success("1.1.1.1:19333", PeerSource::STORE, T);
        x.mark_success("2.2.2.2:19333", PeerSource::STORE, T);
        x.mark_failure("1.1.1.1:19333", T + 100);
        CK(!x.backoff_ok("1.1.1.1:19333", T + 130), "back-off 60 s after 1st failure");
        CK(x.backoff_ok("1.1.1.1:19333", T + 161), "back-off elapsed");
        x.mark_failure("1.1.1.1:19333", T + 200);
        CK(!x.backoff_ok("1.1.1.1:19333", T + 300), "back-off doubles (120 s)");
        CK(x.backoff_ok("1.1.1.1:19333", T + 321), "doubled back-off elapsed");
        CK(x.expire(T + 100 + 14 * 86400 - 1) == 0, "not expired before 14 d");
        CK(x.expire(T + 100 + 14 * 86400) == 1, "expired after 14 d of failures");
        CK(x.contains("2.2.2.2:19333") && !x.contains("1.1.1.1:19333"), "healthy entry kept");
        x.mark_failure("2.2.2.2:19333", T + 10);
        x.mark_success("2.2.2.2:19333", PeerSource::STORE, T + 20);
        CK(x.expire(T + 30 * 86400) == 0, "success resets the failure streak");
    }

    // ---- P3 selection: /16 diversity, exclusion, back-off
    {
        AddrBook bk;
        std::vector<std::string> cands = {"10.1.0.1:1", "10.1.0.2:1", "10.1.0.3:1", "10.2.0.1:1", "10.3.0.1:1", "10.3.0.2:1"};
        std::map<std::string, int> per16; per16["10.1"] = 1;          // already 1 outbound in 10.1
        auto pk = select_outbound_candidates(cands, {}, bk, per16, T, 3, true, 2);
        CK(pk.size() == 3 && pk[0] == "10.2.0.1:1" && pk[1] == "10.3.0.1:1" && pk[2] == "10.1.0.1:1",
           "new /16s first, then fill under the cap");
        auto pk2 = select_outbound_candidates(cands, {}, bk, per16, T, 10, true, 2);
        int in101 = 0; for (auto& a : pk2) if (subnet16_of(a) == "10.1") in101++;
        CK(in101 == 1, "per-/16 cap 2 (1 existing + 1 new)");
        auto pk3 = select_outbound_candidates(cands, {"10.2.0.1:1"}, bk, {}, T, 10, true, 2);
        CK(std::find(pk3.begin(), pk3.end(), "10.2.0.1:1") == pk3.end(), "excluded address skipped");
        bk.mark_success("10.3.0.1:1", PeerSource::STORE, T); bk.mark_failure("10.3.0.1:1", T);
        auto pk4 = select_outbound_candidates(cands, {}, bk, {}, T + 1, 10, true, 2);
        CK(std::find(pk4.begin(), pk4.end(), "10.3.0.1:1") == pk4.end(), "address in back-off skipped");
        auto pk5 = select_outbound_candidates(cands, {}, AddrBook(), {}, T, 10, false, 2);
        CK(pk5.size() == cands.size(), "diversity off (devnet loopback lab): all candidates");
    }

    // ---- P4 VERS extension: round trip, legacy 41-byte VERS, old-node view
    {
        uint8_t v[VERS_EXT_LEN]; memset(v, 0xAB, sizeof(v)); v[40] = 0x01;
        write_vers_ext(v, 19333, 0x1122334455667788ull);
        VersExt e = parse_vers_ext(v, sizeof(v));
        CK(e.present && e.listen_port == 19333 && e.nonce == 0x1122334455667788ull, "VERS ext round trip");
        CK((v[40] & 0x01) == 0x01, "CAP_ADDR bit preserved for old nodes");
        CK(!parse_vers_ext(v, VERS_LEGACY_LEN).present, "41-byte legacy VERS -> no ext");
        uint8_t w[VERS_EXT_LEN] = {0}; w[40] = 0x01;
        CK(!parse_vers_ext(w, VERS_EXT_LEN).present, "51 bytes without CAP_LISTEN -> no ext");
    }

    // ---- P5/P6 bootstrap plan
    {
        std::vector<std::string> conn = {"9.9.9.9:19333"}, add = {"7.7.7.7:19333"}, store = {"1.1.1.1:19333"},
            sf = {"2.2.2.2:19333"}, dns = {"seed.sostcore.com:19333"}, fb = {"3.3.3.3:19333"};
        auto p1 = bootstrap_plan({}, add, store, sf, dns, fb, false);
        CK(p1.size() == 5 && p1[0].source == PeerSource::ADDNODE && p1[1].source == PeerSource::STORE &&
           p1[2].source == PeerSource::SEEDSFILE && p1[3].source == PeerSource::DNS && p1[4].source == PeerSource::FALLBACK,
           "addnode keeps discovery: addnode, store, seeds.txt, dns, fallback");
        auto p2 = bootstrap_plan(conn, add, store, sf, dns, fb, false);
        CK(p2.size() == 2 && p2[0].source == PeerSource::CONNECT && p2[1].source == PeerSource::ADDNODE,
           "--connect stays exclusive");
        auto p3 = bootstrap_plan({}, add, store, sf, dns, fb, true);
        CK(p3.size() == 1 && p3[0].source == PeerSource::ADDNODE, "--noseed: only explicit peers");
        auto p4 = bootstrap_plan({}, {}, {}, {}, dns, fb, false);
        CK(p4.size() == 2 && p4.back().hostport == "3.3.3.3:19333", "fallback IPs follow DNS seeds");
        auto p5 = bootstrap_plan({}, {"1.1.1.1:19333"}, store, {}, {}, {}, false);
        CK(p5.size() == 1, "dedupe across sources");
    }

    // ---- source names round trip
    {
        bool ok = true;
        for (int i = 1; i <= 8; i++) { auto s = (PeerSource)i; if (peer_source_from_name(peer_source_name(s)) != s) ok = false; }
        CK(ok && peer_source_from_name("zz") == PeerSource::UNKNOWN, "source names");
    }

    remove(path.c_str()); rmdir(dir.c_str());
    printf("D1 address-book unit: %d passed, %d failed\n", pass_n, fail_n);
    return fail_n ? 1 : 0;
}
