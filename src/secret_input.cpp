#include "sost/secret_input.h"
#include "sost/json_rpc.h"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <sys/stat.h>
#include <sys/types.h>
#include <termios.h>
#include <unistd.h>

namespace sost {

void Secret::wipe() {
    if (v_.empty()) return;
    // volatile write so the compiler cannot elide the clearing
    volatile char* p = const_cast<volatile char*>(v_.data());
    for (size_t i = 0; i < v_.size(); ++i) p[i] = 0;
    v_.clear();
}

bool read_secret_tty(const std::string& prompt, Secret& out, std::string* err) {
    if (!isatty(STDIN_FILENO)) {
        if (err) *err = "stdin is not a terminal — pass the secret on an open descriptor "
                        "(the --...-fd form) or in a mode-600 file (--...-file), never on "
                        "the command line";
        return false;
    }
    struct termios old{};
    if (tcgetattr(STDIN_FILENO, &old) != 0) { if (err) *err = "tcgetattr failed"; return false; }
    struct termios quiet = old;
    quiet.c_lflag &= ~(tcflag_t)ECHO;
    if (tcsetattr(STDIN_FILENO, TCSAFLUSH, &quiet) != 0) {
        if (err) *err = "cannot disable terminal echo — refusing to read a passphrase that would be visible";
        return false;
    }
    fputs(prompt.c_str(), stderr);
    fflush(stderr);
    std::string line;
    bool ok = (bool)std::getline(std::cin, line);
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &old);
    fputs("\n", stderr);
    if (!ok) { if (err) *err = "no input"; return false; }
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty()) { if (err) *err = "empty passphrase"; return false; }
    out = Secret(std::move(line));
    return true;
}

bool read_secret_fd(int fd, Secret& out, std::string* err) {
    std::string buf;
    char c;
    ssize_t n;
    while ((n = ::read(fd, &c, 1)) == 1) {
        if (c == '\n') break;
        if (c == '\r') continue;
        buf.push_back(c);
        if (buf.size() > 4096) { if (err) *err = "passphrase too long"; return false; }
    }
    if (n < 0) { if (err) *err = "read error on descriptor"; return false; }
    if (buf.empty()) { if (err) *err = "empty passphrase on descriptor"; return false; }
    out = Secret(std::move(buf));
    return true;
}

bool read_secret_file(const std::string& path, Secret& out, std::string* err) {
    struct stat st{};
    if (::stat(path.c_str(), &st) != 0) { if (err) *err = "cannot stat " + path; return false; }
    if (!S_ISREG(st.st_mode)) { if (err) *err = path + " is not a regular file"; return false; }
    if (st.st_mode & (S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH)) {
        if (err) *err = path + " is readable by group or others — refusing to read a secret from it "
                               "(chmod 600 and make sure it is owned by the account running this process)";
        return false;
    }
    if (st.st_uid != ::geteuid() && ::geteuid() != 0) {
        if (err) *err = path + " is not owned by this account";
        return false;
    }
    std::ifstream f(path);
    if (!f) { if (err) *err = "cannot open " + path; return false; }
    std::string data((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    while (!data.empty() && (data.back() == '\n' || data.back() == '\r' ||
                             data.back() == ' '  || data.back() == '\t')) data.pop_back();
    if (data.empty()) { if (err) *err = path + " is empty"; return false; }
    // An interior newline means the file holds more than the secret (a comment,
    // a second key, a stray blank line). Taking the first line would silently
    // use a different credential than the operator believes is in the file, and
    // keeping the newline makes it a credential no prompt can ever reproduce.
    // Both are worse than saying so.
    if (data.find('\n') != std::string::npos || data.find('\r') != std::string::npos) {
        if (err) *err = path + " must contain the secret on a single line and nothing else";
        return false;
    }
    out = Secret(std::move(data));
    return true;
}

bool wallet_file_is_encrypted(const std::string& path, bool& encrypted, std::string* err) {
    std::ifstream f(path);
    if (!f) { if (err) *err = "cannot open " + path; return false; }
    std::stringstream ss; ss << f.rdbuf();
    json::Value doc;
    std::string perr;
    if (!json::parse(ss.str(), doc, &perr)) {
        if (err) *err = "wallet is not readable JSON: " + perr;
        return false;
    }
    int64_t ver = 0;
    if (!doc.get_int("version", ver)) { if (err) *err = "wallet has no integer version field"; return false; }
    encrypted = (ver == 2);
    return true;
}

} // namespace sost
