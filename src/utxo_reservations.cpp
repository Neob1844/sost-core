// utxo_reservations.cpp — see include/sost/utxo_reservations.h
#include "sost/utxo_reservations.h"
#include "sost/json_rpc.h"

#include <cstdio>
#include <fcntl.h>
#include <fstream>
#include <iterator>
#include <sys/stat.h>
#include <unistd.h>

namespace sost::resv {

std::string outpoint_key(const std::string& txid_hex, uint32_t vout) {
    return txid_hex + ":" + std::to_string(vout);
}

static std::string esc(const std::string& s) {
    std::string o;
    for (char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += c; }
        else if ((unsigned char)c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", (unsigned)(unsigned char)c); o += b; }
        else o += c;
    }
    return o;
}

static bool valid_key(const std::string& k) {
    auto c = k.find(':');
    if (c != 64 || k.size() < 66 || k.size() > 75) return false;
    for (size_t i = 0; i < 64; ++i) {
        char x = k[i];
        if (!((x >= '0' && x <= '9') || (x >= 'a' && x <= 'f'))) return false;
    }
    for (size_t i = 65; i < k.size(); ++i) if (k[i] < '0' || k[i] > '9') return false;
    return true;
}

std::string to_json(const Ledger& l) {
    std::string j = "{\n  \"format\": \"" + std::string(kFormat) + "\",\n  \"reservations\": [";
    for (size_t i = 0; i < l.items.size(); ++i) {
        const auto& r = l.items[i];
        j += i ? ",\n    {" : "\n    {";
        j += "\"from\": \"" + esc(r.from) + "\", \"file\": \"" + esc(r.file) + "\", \"build_id\": \"" + esc(r.build_id)
           + "\", \"created_at\": " + std::to_string(r.created_at) + ", \"expires_at\": " + std::to_string(r.expires_at)
           + ", \"outpoints\": [";
        for (size_t k = 0; k < r.outpoints.size(); ++k) j += (k ? ", \"" : "\"") + esc(r.outpoints[k]) + "\"";
        j += "]}";
    }
    j += l.items.empty() ? "]\n}\n" : "\n  ]\n}\n";
    return j;
}

bool from_json(const std::string& text, Ledger& out, std::string* err) {
    auto fail = [&](const char* m) { if (err) *err = m; return false; };
    json::Value d; std::string perr;
    if (!json::parse(text, d, &perr) || !d.is_obj()) return fail("reservation file is not valid JSON");
    std::string fmt;
    if (!d.get_str("format", fmt) || fmt != kFormat) return fail("reservation file has an unknown format");
    const json::Value* rs = d.find("reservations");
    if (!rs || !rs->is_arr()) return fail("reservation file has no reservation list");
    Ledger l;
    for (const auto& e : rs->a) {
        Reservation r;
        const json::Value* ops = e.find("outpoints");
        if (!e.get_str("from", r.from) || !e.get_int("created_at", r.created_at) || !e.get_int("expires_at", r.expires_at)
            || !ops || !ops->is_arr())
            return fail("reservation file has an incomplete entry");
        e.get_str("file", r.file);
        e.get_str("build_id", r.build_id);
        for (const auto& o : ops->a) {
            if (o.type != json::Value::T::Str || !valid_key(o.s)) return fail("reservation file has a malformed outpoint");
            r.outpoints.push_back(o.s);
        }
        l.items.push_back(std::move(r));
    }
    out = std::move(l);
    return true;
}

bool load(const std::string& path, Ledger& out, std::string* err) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        struct stat st;
        if (::stat(path.c_str(), &st) != 0) { out = Ledger{}; return true; }   // no file yet: nothing reserved
        if (err) *err = "cannot read reservation file " + path;
        return false;
    }
    std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (text.size() > 16u * 1024u * 1024u) { if (err) *err = "reservation file is too large"; return false; }
    std::string e;
    if (!from_json(text, out, &e)) { if (err) *err = e + " (" + path + ")"; return false; }
    return true;
}

bool save(const std::string& path, const Ledger& l, std::string* err) {
    const std::string tmp = path + ".tmp";
    const std::string j = to_json(l);
    int fd = ::open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) { if (err) *err = "cannot write " + tmp; return false; }
    size_t off = 0;
    while (off < j.size()) {
        ssize_t w = ::write(fd, j.data() + off, j.size() - off);
        if (w <= 0) { ::close(fd); ::unlink(tmp.c_str()); if (err) *err = "write failed: " + tmp; return false; }
        off += (size_t)w;
    }
    if (::fsync(fd) != 0) { ::close(fd); ::unlink(tmp.c_str()); if (err) *err = "fsync failed: " + tmp; return false; }
    ::close(fd);
    if (::rename(tmp.c_str(), path.c_str()) != 0) { ::unlink(tmp.c_str()); if (err) *err = "cannot replace " + path; return false; }
    return true;
}

size_t prune(Ledger& l, int64_t now, const std::string& from, const std::set<std::string>& live_utxos) {
    size_t before = l.items.size();
    std::vector<Reservation> keep;
    for (auto& r : l.items) {
        if (r.expires_at <= now) continue;
        if (r.from == from) {
            bool any_live = false;
            for (const auto& o : r.outpoints) if (live_utxos.count(o)) { any_live = true; break; }
            if (!any_live) continue;
        }
        keep.push_back(std::move(r));
    }
    l.items = std::move(keep);
    return before - l.items.size();
}

std::set<std::string> reserved_for(const Ledger& l, const std::string& from, int64_t now) {
    std::set<std::string> s;
    for (const auto& r : l.items)
        if (r.from == from && r.expires_at > now) s.insert(r.outpoints.begin(), r.outpoints.end());
    return s;
}

size_t clear_from(Ledger& l, const std::string& from) {
    size_t before = l.items.size();
    std::vector<Reservation> keep;
    for (auto& r : l.items) if (r.from != from) keep.push_back(std::move(r));
    l.items = std::move(keep);
    return before - l.items.size();
}

} // namespace sost::resv
