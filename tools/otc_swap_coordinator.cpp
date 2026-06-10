// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// otc-coordinator — operator tool for the OTC-4 end-to-end swap session
// =============================================================================
//
// A thin, NON-CUSTODIAL driver around sost::atomic_swap::session. It persists a
// swap to a local file, ingests observations the operator has verified
// on-chain, and prints the next safe action. It NEVER signs, broadcasts, holds
// a key, or contacts a chain — building/submitting the actual txs is the
// wallet's job (OTC-1 / OTC-3a / OTC-3b builders).
//
//   create   <file> --role R --cp C --give A --want A --give-amount N
//                    --want-amount N --hashlock HEX [--secret HEX] --t1 N --t2 N
//   inspect  <file>                      (read-only; secret redacted)
//   observe  <file> --event E [--preimage HEX]
//   next     <file> --height N
//
// Events: offer-published offer-accepted sost-locked cp-locked preimage
//         sost-claim cp-claim sost-refund cp-refund timeout failure corruption
//
// The session file stores the secret in cleartext when --secret is given (the
// initiator needs it across restarts); the file header flags this. Keep it
// local and protected; share only `inspect` output (redacted).
// =============================================================================

#include "sost/atomic_swap_session.h"
#include "sost/atomic_swap_orderbook.h"
#include "sost/crypto.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <array>

using namespace sost::atomic_swap;
using namespace sost::atomic_swap::session;

static const char* USAGE =
    "otc-coordinator — OTC-4 swap session driver (non-custodial)\n"
    "  create  <file> --role Initiator|Responder --cp BTC|ETH|BNB|ERC20\n"
    "                 --give ASSET --want ASSET --give-amount N --want-amount N\n"
    "                 --hashlock HEX64 [--secret HEX64] --t1 N --t2 N\n"
    "  inspect <file>\n"
    "  observe <file> --event EVENT [--preimage HEX64]\n"
    "  next    <file> --height N\n"
    "Events: offer-published offer-accepted sost-locked cp-locked preimage\n"
    "        sost-claim cp-claim sost-refund cp-refund timeout failure corruption\n";

static std::string arg(int argc, char** argv, const char* key, const std::string& def = "") {
    for (int i = 0; i < argc - 1; ++i) if (std::strcmp(argv[i], key) == 0) return argv[i + 1];
    return def;
}
static bool has(int argc, char** argv, const char* key) {
    for (int i = 0; i < argc; ++i) if (std::strcmp(argv[i], key) == 0) return true;
    return false;
}
static int hexv(char c){ if(c>='0'&&c<='9')return c-'0'; if(c>='a'&&c<='f')return c-'a'+10; if(c>='A'&&c<='F')return c-'A'+10; return -1; }
static bool parse_hex32(const std::string& s, std::array<uint8_t,32>& out){
    if (s.size()!=64) return false;
    for (int i=0;i<32;++i){ int hi=hexv(s[2*i]),lo=hexv(s[2*i+1]); if(hi<0||lo<0)return false; out[i]=(uint8_t)((hi<<4)|lo);} return true;
}
static bool read_file(const std::string& p, std::string& out){
    std::ifstream f(p); if(!f) return false; std::ostringstream ss; ss<<f.rdbuf(); out=ss.str(); return true;
}
static bool write_file(const std::string& p, const std::string& data){
    std::ofstream f(p, std::ios::trunc); if(!f) return false; f<<data; return (bool)f;
}

static void print_next(const Session& s, int64_t height) {
    NextStep n = DecideNextStep(s, height);
    std::printf("phase:       %s\n", SwapPhaseName(s.phase));
    std::printf("next action: %s%s\n", NextActionName(n.action), n.needs_confirmation ? "  [needs confirmation]" : "");
    std::printf("detail:      %s\n", n.detail.c_str());
    if (!n.recovery.empty()) std::printf("recovery:    %s\n", n.recovery.c_str());
    if (s.issuer_freeze_risk) std::printf("RISK:        issuer-freeze asset — atomicity NOT guaranteed.\n");
    for (const auto& w : s.warnings) std::printf("warning:     %s\n", w.c_str());
}

static int do_create(int argc, char** argv, const std::string& file) {
    Offer o;
    o.id = arg(argc, argv, "--id", "swap-otc4");
    std::string roleS = arg(argc, argv, "--role", "Initiator");
    Role role = (roleS == "Responder") ? Role::Responder : Role::Initiator;
    o.maker_role = Role::Initiator;
    CounterpartyChain cp = CounterpartyChain::BTC;
    if (!CounterpartyChainParse(arg(argc, argv, "--cp", "BTC"), cp)) { std::fprintf(stderr, "bad --cp\n"); return 1; }
    Asset give, want;
    if (!AssetParse(arg(argc, argv, "--give", "SOST"), give) ||
        !AssetParse(arg(argc, argv, "--want", "BTC"),  want)) { std::fprintf(stderr, "bad --give/--want asset\n"); return 1; }
    // Offer is in the MAKER's perspective. The maker is the Initiator; if this
    // operator is the taker, the maker's give/want are the reverse of ours.
    if (role == Role::Initiator) { o.give = give; o.want = want; }
    else                         { o.give = want; o.want = give; }
    try {
        o.give_amount = std::stoll(arg(argc, argv, "--give-amount", "0"));
        o.want_amount = std::stoll(arg(argc, argv, "--want-amount", "0"));
        o.initiator_refund_height = std::stoll(arg(argc, argv, "--t1", "0"));
        o.responder_refund_height = std::stoll(arg(argc, argv, "--t2", "0"));
    } catch (...) { std::fprintf(stderr, "bad numeric arg\n"); return 1; }
    if (!parse_hex32(arg(argc, argv, "--hashlock"), o.hashlock)) { std::fprintf(stderr, "bad --hashlock (need 64 hex)\n"); return 1; }

    std::array<uint8_t,32> secret{}; bool haveSecret = has(argc, argv, "--secret");
    if (haveSecret && !parse_hex32(arg(argc, argv, "--secret"), secret)) { std::fprintf(stderr, "bad --secret (need 64 hex)\n"); return 1; }

    SessionInit init = CreateSession(o, role, cp, haveSecret ? &secret : nullptr);
    if (!init.ok) {
        std::fprintf(stderr, "session rejected:\n");
        for (const auto& e : init.errors) std::fprintf(stderr, "  error: %s\n", e.c_str());
        return 1;
    }
    if (!write_file(file, SerializeSession(init.session, /*include_secret*/ true))) { std::fprintf(stderr, "write failed: %s\n", file.c_str()); return 1; }
    std::printf("created session -> %s\n", file.c_str());
    print_next(init.session, 0);
    return 0;
}

static bool load(const std::string& file, Session& s) {
    std::string txt;
    if (!read_file(file, txt)) { std::fprintf(stderr, "cannot read %s\n", file.c_str()); return false; }
    if (!ParseSession(txt, s)) { std::fprintf(stderr, "corrupted/invalid session file: %s\n", file.c_str()); return false; }
    return true;
}

static int do_inspect(const std::string& file) {
    Session s; if (!load(file, s)) return 1;
    std::printf("swap_id:     %s\n", s.swap_id.c_str());
    std::printf("role:        %s\n", s.role == Role::Initiator ? "Initiator" : "Responder");
    std::printf("cp_chain:    %s\n", CounterpartyChainName(s.cp_chain));
    std::printf("give/want:   %s %lld -> %s %lld\n", AssetName(s.give), (long long)s.give_amount, AssetName(s.want), (long long)s.want_amount);
    std::printf("T1/T2:       %lld / %lld (margin>=%lld)\n", (long long)s.initiator_refund_height, (long long)s.responder_refund_height, (long long)s.safety_margin_min_blocks);
    std::printf("have_secret: %s\n", s.have_secret ? "yes" : "no");
    print_next(s, 0);
    return 0;
}

static int do_observe(int argc, char** argv, const std::string& file) {
    Session s; if (!load(file, s)) return 1;
    std::string ev = arg(argc, argv, "--event");
    StepResult r;
    if (ev == "preimage") {
        std::array<uint8_t,32> p{};
        if (!parse_hex32(arg(argc, argv, "--preimage"), p)) { std::fprintf(stderr, "bad --preimage (need 64 hex)\n"); return 1; }
        r = IngestPreimage(s, p);
    } else {
        Observation o;
        if      (ev == "offer-published") o = Observation::OfferPublished;
        else if (ev == "offer-accepted")  o = Observation::OfferAccepted;
        else if (ev == "sost-locked")     o = Observation::SostLockConfirmed;
        else if (ev == "cp-locked")       o = Observation::CounterpartyLockConfirmed;
        else if (ev == "sost-claim")      o = Observation::SostClaimConfirmed;
        else if (ev == "cp-claim")        o = Observation::CounterpartyClaimConfirmed;
        else if (ev == "sost-refund")     o = Observation::SostRefundConfirmed;
        else if (ev == "cp-refund")       o = Observation::CounterpartyRefundConfirmed;
        else if (ev == "timeout")         o = Observation::TimeoutReached;
        else if (ev == "failure")         o = Observation::Failure;
        else if (ev == "corruption")      o = Observation::Corruption;
        else { std::fprintf(stderr, "unknown --event '%s'\n", ev.c_str()); return 1; }
        r = Ingest(s, o);
    }
    if (!r.ok) { std::fprintf(stderr, "rejected: %s (phase stays %s)\n", r.error.c_str(), SwapPhaseName(s.phase)); return 1; }
    if (!write_file(file, SerializeSession(s, /*include_secret*/ true))) { std::fprintf(stderr, "write failed\n"); return 1; }
    std::printf("observed %s -> %s\n", ev.c_str(), SwapPhaseName(s.phase));
    print_next(s, 0);
    return 0;
}

static int do_next(int argc, char** argv, const std::string& file) {
    Session s; if (!load(file, s)) return 1;
    int64_t h = 0; try { h = std::stoll(arg(argc, argv, "--height", "0")); } catch (...) {}
    print_next(s, h);
    return 0;
}

int main(int argc, char** argv) {
    if (argc < 3) { std::fprintf(stderr, "%s", USAGE); return 1; }
    std::string cmd = argv[1], file = argv[2];
    if (cmd == "create")  return do_create(argc, argv, file);
    if (cmd == "inspect") return do_inspect(file);
    if (cmd == "observe") return do_observe(argc, argv, file);
    if (cmd == "next")    return do_next(argc, argv, file);
    std::fprintf(stderr, "%s", USAGE);
    return 1;
}
