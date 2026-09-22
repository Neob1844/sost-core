// =============================================================================
// test_secret_input.cpp — the rules that keep a secret off the command line.
//
// These are the guarantees the wallet, the node key and the RPC password all
// lean on, so they are tested directly rather than through the binaries:
//   * a file that anyone else can read is REFUSED, not read anyway;
//   * a descriptor carries exactly one line, with the newline stripped;
//   * failure never returns a half-read secret;
//   * wipe() leaves nothing behind in the object.
// No terminal is involved: read_secret_tty() needs a tty by construction and is
// covered by the CLI-level tests instead.
// =============================================================================
#include "sost/secret_input.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

static int g_fail = 0;
static void check(bool cond, const char* what) {
    printf("  %-62s %s\n", what, cond ? "PASS" : "FAIL");
    if (!cond) g_fail++;
}

static std::string g_dir;

static std::string write_file(const char* name, const std::string& body, mode_t mode) {
    const std::string path = g_dir + "/" + name;
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) { printf("  cannot create %s\n", path.c_str()); exit(2); }
    fwrite(body.data(), 1, body.size(), f);
    fclose(f);
    if (chmod(path.c_str(), mode) != 0) { printf("  chmod failed\n"); exit(2); }
    return path;
}

int main() {
    char tmpl[] = "/tmp/sostsecret.XXXXXX";
    const char* d = mkdtemp(tmpl);
    if (!d) { printf("mkdtemp failed\n"); return 2; }
    g_dir = d;

    printf("=== secret files ===\n");
    {
        const std::string p = write_file("ok.key", "un-secreto-cualquiera\n", 0600);
        sost::Secret s; std::string err;
        const bool ok = sost::read_secret_file(p, s, &err);
        check(ok, "mode 600 file is accepted");
        check(s.str() == "un-secreto-cualquiera", "trailing newline is stripped");
        s.wipe();
        check(s.str().empty(), "wipe() empties the secret");
    }
    {
        const std::string p = write_file("group.key", "secreto\n", 0640);
        sost::Secret s; std::string err;
        const bool ok = sost::read_secret_file(p, s, &err);
        check(!ok, "mode 640 (group-readable) is REFUSED");
        check(s.str().empty(), "  ...and nothing is returned on refusal");
        check(err.find("secreto") == std::string::npos, "  ...and the error never echoes the content");
    }
    {
        const std::string p = write_file("world.key", "secreto\n", 0644);
        sost::Secret s; std::string err;
        check(!sost::read_secret_file(p, s, &err), "mode 644 (world-readable) is REFUSED");
    }
    {
        sost::Secret s; std::string err;
        check(!sost::read_secret_file(g_dir + "/no-existe", s, &err), "a missing file is an error, not an empty secret");
    }
    {
        // An empty file must not pass as a valid (empty) passphrase.
        const std::string p = write_file("empty.key", "", 0600);
        sost::Secret s; std::string err;
        check(!sost::read_secret_file(p, s, &err), "an empty file is rejected");
    }
    {
        // A file with more than one line is ambiguous: neither taking the first
        // line nor keeping the newline can be the operator's intent, so it is
        // refused rather than turned into a credential nobody can reproduce.
        const std::string p = write_file("twoline.key", "primera\nsegunda\n", 0600);
        sost::Secret s; std::string err;
        check(!sost::read_secret_file(p, s, &err), "a multi-line file is refused");
        check(s.str().empty(), "  ...and returns no secret");
        check(err.find("primera") == std::string::npos && err.find("segunda") == std::string::npos,
              "  ...and the error never echoes the content");
    }

    printf("=== secret descriptors ===\n");
    {
        const std::string p = write_file("fd.key", "por-descriptor\n", 0600);
        const int fd = open(p.c_str(), O_RDONLY);
        sost::Secret s; std::string err;
        const bool ok = sost::read_secret_fd(fd, s, &err);
        close(fd);
        check(ok && s.str() == "por-descriptor", "a descriptor carries the secret intact");
    }
    {
        // A pipe with no newline at all still yields the secret at EOF.
        int fds[2];
        if (pipe(fds) != 0) { printf("pipe failed\n"); return 2; }
        const char* msg = "sin-salto";
        if (write(fds[1], msg, strlen(msg)) < 0) { printf("write failed\n"); return 2; }
        close(fds[1]);
        sost::Secret s; std::string err;
        const bool ok = sost::read_secret_fd(fds[0], s, &err);
        close(fds[0]);
        check(ok && s.str() == "sin-salto", "a pipe without a trailing newline works");
    }
    {
        sost::Secret s; std::string err;
        check(!sost::read_secret_fd(777, s, &err), "a closed descriptor is an error");
    }
    {
        // CR is dropped so a file written on Windows does not carry a \r into
        // the passphrase and fail decryption for no visible reason.
        const std::string p = write_file("crlf.key", "windows\r\n", 0600);
        sost::Secret s; std::string err;
        check(sost::read_secret_file(p, s, &err) && s.str() == "windows", "CRLF is normalised");
    }

    printf("=== wallet format detection ===\n");
    {
        const std::string v2 = write_file("v2.json", "{\"version\":2,\"encrypted\":true,\"salt\":\"aa\"}", 0600);
        const std::string v1 = write_file("v1.json", "{\"version\":1,\"keys\":[]}", 0600);
        bool enc = false; std::string err;
        check(sost::wallet_file_is_encrypted(v2, enc, &err) && enc, "a v2 wallet is reported encrypted");
        check(sost::wallet_file_is_encrypted(v1, enc, &err) && !enc, "a v1 wallet is reported plaintext");
        check(!sost::wallet_file_is_encrypted(g_dir + "/no-existe", enc, &err), "a missing wallet is an error");
    }

    // Best-effort cleanup; the directory only ever held throwaway fixtures.
    const std::string rm = "rm -rf '" + g_dir + "'";
    if (system(rm.c_str()) != 0) { /* leaving a temp dir behind is not a failure */ }

    printf("\n%s\n", g_fail == 0 ? "ALL PASS" : "FAILURES");
    return g_fail == 0 ? 0 : 1;
}
