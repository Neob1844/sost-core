# V13 RC1 Binary Preflight

**Preflight:** `v13-rc1-preflight-v01`
**RC:** `v13-rc1`
**Activation height:** block 12,000
**Source of truth:** `config/v13_binary_preflight.json`
**Companion docs:** `V13_RELEASE_CANDIDATE.md`, `V13_MINER_OPERATOR_CHECKLIST.md`, `V13_ACTIVATION_PLAN.md`, `V13_READINESS_GATES.md`

This document explains how to **build the V13 RC1 binaries on your own host** and how to **run the preflight checker** that verifies your local tree is in a state suitable for cutting a release candidate. The preflight does **NOT** build the binaries itself, does **NOT** sign anything, and does **NOT** publish or upload artefacts. Those remain explicit manual operator actions.

---

## 1. What the preflight is

`scripts/trinity/v13_binary_preflight.py` is a read-only Python CLI that, given a repo root and a build dir:

1. Reads `git HEAD` and the current branch (argv-only, allow-listed git verbs).
2. Loads `config/v13_binary_preflight.json` and verifies its schema.
3. Confirms that the two sibling configs exist:
   - `config/v13_activation.json`
   - `config/v13_release_candidate.json`
4. Re-runs **`v13_readiness_check.build_report()`** in-process and asserts `v13_ready_for_confirmed_items` is `true`.
5. Re-runs **`v13_release_candidate_check.build_report()`** in-process and asserts `rc_ready` is `true`.
6. For each required binary (`sost-node`, `sost-miner`, `sost-cli`), records whether it exists in the build dir, and if it exists, computes a SHA-256 with `hashlib`.
7. Optionally runs the full Trinity pytest suite (`--run-tests`).
8. Optionally runs an allow-listed short list of `ctest` names (`--run-ctest`).
9. Optionally writes a `SHA256SUMS` file (`--write-sha256sums`).
10. Emits a single `trinity-v13-binary-preflight-report/v0.1` JSON plus a Markdown rendering.

It uses `subprocess` ONLY for the read-only allow-list:

```
- git rev-parse / status / diff / log / branch / ls-files / rev-list
- python -m pytest <target>     (only when --run-tests is passed)
- ctest -R <name>                (only when --run-ctest is passed)
```

`shell=True` is forbidden in source. SHA-256 over binaries uses Python's `hashlib`, not a shelled `sha256sum`.

---

## 2. What the preflight is NOT

- It does **NOT** run `cmake` or `make`. The operator builds manually.
- It does **NOT** sign anything.
- It does **NOT** publish or upload any release artefact (no GitHub release, no S3, no IPFS, no pin).
- It does **NOT** touch a wallet, a private key, a seed phrase, or a signing identity.
- It does **NOT** broadcast any transaction.
- It does **NOT** open the network from the script itself.
- It does **NOT** mutate git state (no push, no merge, no tag, no commit, no add).

Those steps remain explicit manual operator actions and live outside this preflight.

---

## 3. How to build manually

```bash
# 1. Clean checkout on the V13 RC1 commit.
cd /opt/sost
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
#   expected: matches min_commit in config/v13_binary_preflight.json

# 2. Build in a dedicated dir so the preflight can target it cleanly.
mkdir -p build-v13-rc1 && cd build-v13-rc1
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc) sost-node sost-miner sost-cli

# 3. (Optional) Build the cASERT regression tests so the preflight
#    can invoke them with --run-ctest:
make -j$(nproc) test-casert test-casert-v11 \
    test-casert-v12-ceiling test-casert-v13-ceiling
```

The preflight does NOT run any of these commands for you. They are documented here so you can copy-paste them yourself.

---

## 4. How to run the preflight

### Minimal invocation (no binaries needed, no tests)

```bash
python3 scripts/trinity/v13_binary_preflight.py \
    --repo-root  /opt/sost \
    --build-dir  /opt/sost/build-v13-rc1 \
    --out-dir    /tmp/sost-v13-binary-preflight \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
```

Expected output: `ready_to_build=true`, `ready_to_release=false` (binaries not yet built), `safety_status=ok` or `warning` if your tree is dirty.

### Full invocation (binaries built, tests run, SHA256SUMS written)

```bash
python3 scripts/trinity/v13_binary_preflight.py \
    --repo-root        /opt/sost \
    --build-dir        /opt/sost/build-v13-rc1 \
    --out-dir          /tmp/sost-v13-binary-preflight \
    --pinned-time      $(date -u +%Y-%m-%dT%H:%M:%S+00:00) \
    --require-binaries \
    --run-tests \
    --run-ctest \
    --write-sha256sums
```

Expected output when everything is green:

- `ready_to_build=true`
- `ready_to_release=true`
- `safety_status=ok`
- `tmp/sost-v13-binary-preflight/SHA256SUMS` contains one line per built binary
- exit code `0`

If anything is red:

- `ready_to_release=false`
- exit code `1`
- The Markdown report's **Warnings** section names the failure(s).

Setup errors (bad `--repo-root`, missing config, schema mismatch) exit `2`.

---

## 5. How to interpret missing binaries vs failed tests

| Situation | Preflight behaviour |
|---|---|
| Build dir missing | All binaries marked `present=false`. `ready_to_release` is false; `ready_to_build` stays `true` (configs are still OK). |
| One binary missing | That binary entry has `present=false`. Without `--require-binaries`, this is a warning, not a failure. |
| One binary present but `--require-binaries` is set and another is missing | Warning is upgraded to a failure; exit `1`. |
| Tracked tree is dirty | Always a warning; `ready_to_build=false`. Binaries built from a dirty tree must NOT be tagged as a release. |
| `git HEAD` does not match `min_commit` | Warning; `ready_to_build=false`. Either rebase / pull onto the published `min_commit`, or update the config field on the same branch and re-run. |
| `v13_readiness_check` says confirmed items not wired | Warning; `ready_to_build=false`. The V13 wiring commits have not landed on this branch. |
| `v13_release_candidate_check` says `rc_ready=false` | Warning; `ready_to_build=false`. One or more RC manifest assertions failed (docs missing, public mirror mismatched, etc.). |
| `--run-tests` and pytest reports a failure | Warning; `ready_to_release=false`; exit `1`. |
| `--run-ctest` and any allow-listed ctest fails | Warning; `ready_to_release=false`; exit `1`. |
| `--run-ctest` and a required ctest is missing from the build dir | The test entry has `status=missing`. Build the missing target with the command in the warning text. |

---

## 6. What remains manual (NOT in the preflight, NOT in v0.1)

These steps will be added in later, **separate** sprints and are explicitly outside the V13 RC1 binary preflight v0.1 scope:

| Step | Manual procedure |
|---|---|
| **Sign release artefacts** | Operator generates a detached signature over `SHA256SUMS` with the operator-side release key (separate from any mining or wallet key). The preflight neither holds the key nor invokes the signer. |
| **Publish binaries** | Operator uploads the built binaries + signed `SHA256SUMS` to whichever distribution surface they choose (GitHub release, mirror, IPFS pin, …). The preflight has no network primitive and no upload code path. |
| **Announce release** | Operator posts the announcement to BitcoinTalk + the official Telegram channel + the SOST web. The preflight does not broadcast. |
| **Push / merge / tag** | The operator runs the interactive push/merge/tag sequence from their own SSH session. The preflight never mutates remote git state. |

In short: the preflight prepares a verifiable **local snapshot** of "is this tree releasable?" and stops there.

---

## 7. Files this preflight reads

```
- config/v13_binary_preflight.json            (self)
- config/v13_activation.json                  (sibling, via v13_readiness_check)
- config/v13_release_candidate.json           (sibling, via v13_release_candidate_check)
- website/api/v13_release_candidate.json      (public mirror, via v13_release_candidate_check)
- docs/V13_RELEASE_CANDIDATE.md               (via v13_release_candidate_check)
- docs/V13_MINER_OPERATOR_CHECKLIST.md        (via v13_release_candidate_check)
- docs/V13_ACTIVATION_PLAN.md                 (via v13_release_candidate_check)
- docs/V13_READINESS_GATES.md                 (via v13_release_candidate_check)
- include/sost/params.h                       (via v13_readiness_check + v13_release_candidate_check)
- include/sost/beacon.h                       (via v13_release_candidate_check)
- src/pow/casert.cpp / src/sost-node.cpp      (presence implied by readiness checker hits)
- <build-dir>/sost-node / sost-miner / sost-cli (only if present; never built by preflight)
```

It writes:

```
- <out-dir>/report.json
- <out-dir>/report.md
- <out-dir>/SHA256SUMS    (only when --write-sha256sums + at least one binary present)
```

Nothing else is created or modified.

---

## 8. Reference command (operator quick-card)

```bash
# Full preflight after a clean build, expecting rc1 release readiness:
python3 scripts/trinity/v13_binary_preflight.py \
    --repo-root        /opt/sost \
    --build-dir        /opt/sost/build-v13-rc1 \
    --out-dir          /tmp/sost-v13-binary-preflight \
    --pinned-time      $(date -u +%Y-%m-%dT%H:%M:%S+00:00) \
    --require-binaries \
    --run-tests \
    --run-ctest \
    --write-sha256sums
echo "preflight rc=$?"
cat /tmp/sost-v13-binary-preflight/report.md
```
