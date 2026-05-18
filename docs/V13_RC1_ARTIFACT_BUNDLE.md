# V13 RC1 Local Artifact Bundle

**Bundle generator:** `scripts/trinity/v13_rc1_artifact_bundle.py`
**Manifest schema:** `schemas/trinity/v13_rc1_artifact_bundle_manifest.schema.json` (`$id` = `trinity-v13-rc1-artifact-bundle-manifest/v0.1`)
**Companion docs:** `V13_RELEASE_CANDIDATE.md`, `V13_MINER_OPERATOR_CHECKLIST.md`, `V13_BINARY_PREFLIGHT.md`, `V13_ACTIVATION_PLAN.md`, `V13_READINESS_GATES.md`

This document explains what the V13 RC1 local artefact bundle contains, how to verify it, and what is intentionally **not** included. The bundle is a reproducible, offline package the operator can copy to a USB stick, hand to a reviewer, or unpack on a fresh machine to confirm the V13 RC1 release-candidate state. It is **never** signed, **never** uploaded, **never** broadcast by the bundle generator itself.

---

## 1. What the bundle contains

```
<out-dir>/
    bin/
        sost-node           ← copy of the built binary
        sost-miner          ← copy of the built binary
        sost-cli            ← copy of the built binary
    SHA256SUMS              ← one line per binary, deterministic + sorted
    reports/
        preflight_report.json   ← copy of v13_binary_preflight report.json
        preflight_report.md     ← copy of v13_binary_preflight report.md
    config/
        v13_release_candidate.json
        v13_activation.json
        v13_binary_preflight.json
    MANIFEST.json           ← schema-locked top-level manifest
    MANIFEST.md             ← human-readable rendering of the manifest
    VERIFY_COMMANDS.md      ← step-by-step local-verification recipe
    [optional] v13-rc1-artifact-bundle-<bundle_id>.tar.gz
                             ← deterministic local tar.gz of the whole tree
```

Every file copied into the bundle is re-hashed with Python's `hashlib` and the hash is recorded inside `MANIFEST.json`. The generator refuses to proceed if any binary's hash disagrees with the corresponding line in the preflight `SHA256SUMS`, so the bundle can never carry binaries that were tampered with between the preflight and the bundle step.

---

## 2. What the bundle does NOT contain

| Item | Why it is not here |
|---|---|
| A signature over `SHA256SUMS` | Signing is an explicit manual operator step. The bundle generator does not hold any signing key and has no signing primitive. |
| A release upload to GitHub / S3 / IPFS | The bundle is local-only. There is no upload code path; the generator has no network primitive at all. |
| A wallet, a private key, a seed phrase | The bundle generator never opens, reads, copies, or asks for any wallet material. |
| A broadcast capability | No transaction is built, signed, or sent. |
| A consensus-level change | The bundle is downstream of the V13 readiness + RC manifest + binary preflight commits; it makes zero edits to `src/`, `include/sost/`, or any schema. |
| A modification to git state | The generator never invokes git. No push, no merge, no tag, no commit. |
| An Ethereum / L1 deploy | No web3 / etherscan / infura / alchemy import. |

---

## 3. How to verify the bundle locally

`VERIFY_COMMANDS.md` (inside the bundle) is the operator-facing version of this section. It contains the exact copy-paste commands; the same content is repeated here for completeness.

### 3.1 Re-hash every binary and compare against `SHA256SUMS`

```
cd <unpacked-bundle>
sha256sum -c SHA256SUMS
# expected: every line ends with '  OK'
```

### 3.2 Cross-check the manifest against the bundle tree

```python
import json, hashlib, pathlib
root = pathlib.Path(".")
m = json.loads((root / "MANIFEST.json").read_text())
def sha(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()
for b in m["binaries"]:
    p = root / "bin" / b["basename_under_bin"]
    assert sha(p) == b["sha256"], b["name"]
for r in m["reports"]:
    p = root / "reports" / r["basename_under_reports"]
    assert sha(p) == r["sha256"], r["name"]
for c in m["configs"]:
    p = root / "config" / c["basename_under_config"]
    assert sha(p) == c["sha256"], c["name"]
print("manifest cross-check OK")
```

### 3.3 Confirm every safety flag is const-true

```
python3 -c "import json,sys;m=json.load(open('MANIFEST.json'));
sys.exit(0 if all(v is True for v in m['safety_flags'].values()) else 1)"
```

### 3.4 (Optional) Verify the deterministic tarball

```
sha256sum v13-rc1-artifact-bundle-<bundle_id>.tar.gz
# compare with manifest["tarball"]["sha256"]
```

The tarball is built via Python's `tarfile` module with sorted membership, `uid=gid=0`, blank `uname/gname`, and `mtime=0`. Two runs over the same inputs produce byte-identical tar.gz files.

---

## 4. How to generate the bundle

```bash
# 1. Pre-requisite: binaries built into a known dir + a green preflight.
mkdir -p /opt/sost/build-v13-rc1 && cd /opt/sost/build-v13-rc1
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc) sost-node sost-miner sost-cli \
    test-casert test-casert-v11 \
    test-casert-v12-ceiling test-casert-v13-ceiling
cd /opt/sost

python3 scripts/trinity/v13_binary_preflight.py \
    --repo-root /opt/sost \
    --build-dir /opt/sost/build-v13-rc1 \
    --out-dir   /tmp/sost-v13-binary-preflight-release \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00) \
    --require-binaries --run-tests --run-ctest --write-sha256sums

# 2. Bundle.
python3 scripts/trinity/v13_rc1_artifact_bundle.py \
    --repo-root     /opt/sost \
    --build-dir     /opt/sost/build-v13-rc1 \
    --preflight-dir /tmp/sost-v13-binary-preflight-release \
    --out-dir       /tmp/sost-v13-rc1-artifact-bundle \
    --pinned-time   $(date -u +%Y-%m-%dT%H:%M:%S+00:00) \
    --require-preflight-ready \
    --write-tarball
```

Flags:

- `--require-preflight-ready` — refuse to bundle unless `preflight_report.ready_to_release == true`.
- `--no-copy-binaries` — produce the manifest and SHA256SUMS without copying the actual binaries (useful when you only want to publish the checksums).
- `--write-tarball` — also produce `<out-dir>/v13-rc1-artifact-bundle-<bundle_id>.tar.gz`, deterministic, local-only.

Exit codes: `0` (bundle clean), `1` (bundle refused — missing binary, SHA mismatch, preflight not ready), `2` (setup error).

---

## 5. What remains manual (NOT in v0.1)

| Step | Manual procedure |
|---|---|
| **Sign `SHA256SUMS`** | Operator uses a release key (separate from any wallet or mining key) to produce a detached signature next to `SHA256SUMS`. The bundle generator never holds the key. |
| **Upload binaries + signature** | Operator picks the publication surface (GitHub release page, mirror, IPFS pin, …). The bundle generator has no network primitive and no upload code path. |
| **Announce the release** | Operator posts to BitcoinTalk + the official Telegram channel + the SOST web. The bundle generator does not broadcast. |
| **Push / merge / tag** | The operator runs the interactive release sequence from their own SSH session. The bundle generator never mutates git state. |

---

## 6. Safety contract (enforced statically by tests)

The generator passes a static lint that forbids:

- `shell=True`, `os.system`, `os.popen`, `eval`, `exec`
- `requests`, `urllib`, `httpx`, `aiohttp`, `socket.socket`, `http.client`
- `api.github.com`, `GITHUB_TOKEN`, `X-GitHub-`, `PyGithub`
- `ecdsa`, `secp256k1`, `sign_tx`, `sendrawtransaction`, `broadcast`, `privkey`, `private_key_hex`
- `web3.`, `etherscan.io`, `infura.io`, `alchemy.com`, `ETHERSCAN_API_KEY`, `deploy_contract`, `send_transaction`
- `subprocess` (the generator must not shell out at all)
- The destructive git argv literals (`"push"`, `"merge"`, `"tag"`, `"reset"`, `"checkout"`, `"rm"`, `"clean"`, `"commit"`, `"add"`, `"stash"`)
- Any LLM client import (`anthropic`, `openai`, `langchain`, `transformers`, `llama_cpp`)

The manifest's `safety_flags` block is const-locked at the schema level:

```
no_wallet_access          true
no_private_key_access     true
no_signing                true
no_broadcast              true
no_release_upload         true
no_network_required       true
no_auto_restart           true
no_subprocess             true
no_shell_true             true
no_github_api             true
no_ethereum_deploy        true
```

---

## 7. Quick reference

```bash
# Smallest sensible invocation (full bundle, gated on preflight readiness):
python3 scripts/trinity/v13_rc1_artifact_bundle.py \
    --repo-root     /opt/sost \
    --build-dir     /opt/sost/build-v13-rc1 \
    --preflight-dir /tmp/sost-v13-binary-preflight-release \
    --out-dir       /tmp/sost-v13-rc1-artifact-bundle \
    --pinned-time   $(date -u +%Y-%m-%dT%H:%M:%S+00:00) \
    --require-preflight-ready --write-tarball
echo "bundle rc=$?"
cat /tmp/sost-v13-rc1-artifact-bundle/MANIFEST.md
```
