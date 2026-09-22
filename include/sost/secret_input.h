#pragma once
// ============================================================================
// Reading a secret without leaving it somewhere it can be read back.
//
// A passphrase must never reach argv (visible in `ps`, in /proc/PID/cmdline and
// in any monitoring that captures command lines), an environment variable
// (inherited by children, visible in /proc/PID/environ), a config file, a shell
// history or a log. That leaves two acceptable sources:
//
//   * an interactive terminal with echo switched off;
//   * a file descriptor the caller already opened — a pipe from a password
//     manager, or a here-doc — passed by NUMBER, so the secret itself is never
//     an argument.
//
// The buffer is wiped when the Secret goes out of scope. That is hygiene, not
// a guarantee: once a process holds a key in memory, anyone who already owns
// the machine can read it. Encryption at rest protects the FILE; it does not
// protect a running miner on a compromised host.
// ============================================================================
#include <string>

namespace sost {

class Secret {
public:
    Secret() = default;
    explicit Secret(std::string v) : v_(std::move(v)) {}
    ~Secret() { wipe(); }
    Secret(const Secret&) = delete;
    Secret& operator=(const Secret&) = delete;
    Secret(Secret&& o) noexcept : v_(std::move(o.v_)) { o.v_.clear(); }
    Secret& operator=(Secret&& o) noexcept { wipe(); v_ = std::move(o.v_); o.v_.clear(); return *this; }

    const std::string& str() const { return v_; }
    bool empty() const { return v_.empty(); }
    void wipe();

private:
    std::string v_;
};

// Prompt on the controlling terminal with echo disabled. Fails (returns false)
// when stdin is not a terminal — so a script cannot silently get an empty
// passphrase and a confusing decryption error.
bool read_secret_tty(const std::string& prompt, Secret& out, std::string* err);

// Read a secret from an already-open file descriptor, up to the first newline.
// The caller passes the NUMBER; the secret never appears in the command line.
bool read_secret_fd(int fd, Secret& out, std::string* err);

// Read a secret from a file that must be private: the call FAILS if the file is
// group- or world-readable, or is not owned by the caller. A key whose file
// anyone can read is not protected by being in a file rather than in argv, so
// the permission check is part of the contract rather than advice.
//
// Trailing whitespace and a single trailing newline are stripped; the rest is
// returned verbatim.
bool read_secret_file(const std::string& path, Secret& out, std::string* err);

// Is this wallet file the encrypted (v2) format? Returns false for v1 or for a
// file that cannot be read as a wallet at all (reason in `err`).
bool wallet_file_is_encrypted(const std::string& path, bool& encrypted, std::string* err);

} // namespace sost
