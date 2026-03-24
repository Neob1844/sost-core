// addressbook.cpp — SOST Trusted Address Book
#include "sost/addressbook.h"
#include <fstream>
#include <sstream>
#include <ctime>
#include <algorithm>

namespace sost {

void AddressBook::Add(const std::string& address, const std::string& label,
                      TrustLevel trust, int64_t time, const std::string& notes) {
    if (time == 0) time = (int64_t)std::time(nullptr);

    auto it = index_.find(address);
    if (it != index_.end()) {
        // Update existing
        auto& e = entries_[it->second];
        e.label = label;
        e.trust = trust;
        e.notes = notes;
        return;
    }

    AddressEntry entry;
    entry.address = address;
    entry.label = label;
    entry.trust = trust;
    entry.added_time = time;
    entry.notes = notes;

    index_[address] = entries_.size();
    entries_.push_back(std::move(entry));
}

bool AddressBook::Remove(const std::string& address) {
    auto it = index_.find(address);
    if (it == index_.end()) return false;

    size_t idx = it->second;
    entries_.erase(entries_.begin() + (ptrdiff_t)idx);
    RebuildIndex();
    return true;
}

TrustLevel AddressBook::Check(const std::string& address) const {
    auto it = index_.find(address);
    if (it == index_.end()) return TrustLevel::UNKNOWN;
    return entries_[it->second].trust;
}

const AddressEntry* AddressBook::Get(const std::string& address) const {
    auto it = index_.find(address);
    if (it == index_.end()) return nullptr;
    return &entries_[it->second];
}

void AddressBook::RebuildIndex() {
    index_.clear();
    for (size_t i = 0; i < entries_.size(); ++i) {
        index_[entries_[i].address] = i;
    }
}

// Simple JSON escape
static std::string json_escape(const std::string& s) {
    std::string r;
    r.reserve(s.size() + 8);
    for (char c : s) {
        if (c == '"') r += "\\\"";
        else if (c == '\\') r += "\\\\";
        else if (c == '\n') r += "\\n";
        else r += c;
    }
    return r;
}

bool AddressBook::Save(const std::string& path, std::string* err) const {
    std::ofstream f(path);
    if (!f.is_open()) {
        if (err) *err = "cannot open " + path + " for writing";
        return false;
    }

    f << "{\n  \"addresses\": [\n";
    for (size_t i = 0; i < entries_.size(); ++i) {
        const auto& e = entries_[i];
        f << "    {\n";
        f << "      \"address\": \"" << json_escape(e.address) << "\",\n";
        f << "      \"label\": \"" << json_escape(e.label) << "\",\n";
        f << "      \"trust_level\": \"" << TrustLevelStr(e.trust) << "\",\n";
        f << "      \"added\": " << e.added_time << ",\n";
        f << "      \"notes\": \"" << json_escape(e.notes) << "\"\n";
        f << "    }";
        if (i + 1 < entries_.size()) f << ",";
        f << "\n";
    }
    f << "  ]\n}\n";
    return true;
}

// Minimal JSON parser for address book format
static std::string extract_json_string(const std::string& line, const std::string& key) {
    auto pos = line.find("\"" + key + "\"");
    if (pos == std::string::npos) return "";
    pos = line.find(':', pos);
    if (pos == std::string::npos) return "";
    pos = line.find('"', pos + 1);
    if (pos == std::string::npos) return "";
    auto end = line.find('"', pos + 1);
    if (end == std::string::npos) return "";
    return line.substr(pos + 1, end - pos - 1);
}

static int64_t extract_json_int(const std::string& line, const std::string& key) {
    auto pos = line.find("\"" + key + "\"");
    if (pos == std::string::npos) return 0;
    pos = line.find(':', pos);
    if (pos == std::string::npos) return 0;
    // Skip whitespace
    pos++;
    while (pos < line.size() && (line[pos] == ' ' || line[pos] == '\t')) pos++;
    return std::strtoll(line.c_str() + pos, nullptr, 10);
}

bool AddressBook::Load(const std::string& path, std::string* err) {
    std::ifstream f(path);
    if (!f.is_open()) {
        // Not an error — file may not exist yet
        entries_.clear();
        index_.clear();
        return true;
    }

    entries_.clear();
    index_.clear();

    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());

    // Parse entries between { } blocks inside "addresses" array
    size_t pos = 0;
    while ((pos = content.find('{', pos + 1)) != std::string::npos) {
        auto end = content.find('}', pos);
        if (end == std::string::npos) break;

        std::string block = content.substr(pos, end - pos + 1);

        std::string addr = extract_json_string(block, "address");
        if (addr.empty()) continue;

        AddressEntry entry;
        entry.address = addr;
        entry.label = extract_json_string(block, "label");
        entry.trust = TrustLevelFromStr(extract_json_string(block, "trust_level"));
        entry.added_time = extract_json_int(block, "added");
        entry.notes = extract_json_string(block, "notes");

        index_[entry.address] = entries_.size();
        entries_.push_back(std::move(entry));
    }

    return true;
}

} // namespace sost
