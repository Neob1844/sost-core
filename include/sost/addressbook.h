// addressbook.h — SOST Trusted Address Book (wallet-layer, no consensus)
#pragma once
#include <string>
#include <vector>
#include <map>
#include <cstdint>

namespace sost {

enum class TrustLevel : int {
    BLOCKED  = -1,
    UNKNOWN  =  0,   // not in address book
    NEW      =  1,
    KNOWN    =  2,
    TRUSTED  =  3,
};

inline const char* TrustLevelStr(TrustLevel tl) {
    switch (tl) {
        case TrustLevel::BLOCKED: return "blocked";
        case TrustLevel::NEW:     return "new";
        case TrustLevel::KNOWN:   return "known";
        case TrustLevel::TRUSTED: return "trusted";
        default:                  return "unknown";
    }
}

inline TrustLevel TrustLevelFromStr(const std::string& s) {
    if (s == "blocked") return TrustLevel::BLOCKED;
    if (s == "new")     return TrustLevel::NEW;
    if (s == "known")   return TrustLevel::KNOWN;
    if (s == "trusted") return TrustLevel::TRUSTED;
    return TrustLevel::UNKNOWN;
}

struct AddressEntry {
    std::string  address;
    std::string  label;
    TrustLevel   trust{TrustLevel::NEW};
    int64_t      added_time{0};    // unix timestamp
    std::string  notes;
};

class AddressBook {
public:
    // Add or update an address
    void Add(const std::string& address, const std::string& label,
             TrustLevel trust, int64_t time = 0, const std::string& notes = "");

    // Remove an address
    bool Remove(const std::string& address);

    // Look up trust level (UNKNOWN if not found)
    TrustLevel Check(const std::string& address) const;

    // Get full entry (nullptr if not found)
    const AddressEntry* Get(const std::string& address) const;

    // List all entries
    const std::vector<AddressEntry>& Entries() const { return entries_; }
    size_t Size() const { return entries_.size(); }

    // Persistence (simple JSON)
    bool Save(const std::string& path, std::string* err = nullptr) const;
    bool Load(const std::string& path, std::string* err = nullptr);

private:
    std::vector<AddressEntry> entries_;
    std::map<std::string, size_t> index_;  // address → entries_ index

    void RebuildIndex();
};

} // namespace sost
