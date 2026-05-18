# V13 RC1 Public Artifact Metadata

**Public manifest:** `website/api/v13_rc1_artifact_manifest.json`
**Public SHA256SUMS:** `website/api/v13_rc1_SHA256SUMS.txt`
**Public SHA256SUMS signature (NEW, v269):** `website/api/v13_rc1_SHA256SUMS.asc` — OpenPGP ASCII-armored detached signature, sha256 `5e83889bb95d21404c3ae4faedfeb8c04729343fc88b03f5a9e608dd7c228779`
**Release status (NEW, v269):** `signed_metadata_only` — the SHA256SUMS file is now SIGNED, but binaries are NOT yet uploaded
**Source bundle:** `v13-rc1-artifact-bundle-v01` (operator-local; binaries are NOT committed to this repository)
**Companion docs:** `V13_RC1_SIGNING_AND_PUBLICATION_CHECKLIST.md`, `V13_RC1_ARTIFACT_BUNDLE.md`, `V13_BINARY_PREFLIGHT.md`, `V13_RELEASE_CANDIDATE.md`, `V13_MINER_OPERATOR_CHECKLIST.md`

**SOST release key (V13 RC1):**

| Field | Value |
|---|---|
| `uid` | `SOST Release (V13 RC1 release signing key) <sost@sostcore.com>` |
| `primary_fingerprint`        | `41B1A46E626064AB524CB99EB6B9E2852AE41A04` |
| `signing_subkey_fingerprint` | `E2FCC898520842F0192EF7A46422CC120F51DCEA` |
| `key_id`                     | `B6B9E2852AE41A04` |

The release key is **dedicated to release signing**. It is NOT a wallet key, NOT a mining key, NOT an SbPoW key. Anyone announcing a different fingerprint as "SOST release key" is impersonating the operator — verify against the BitcoinTalk announcement thread.

---

## 1. What this is

`website/api/v13_rc1_artifact_manifest.json` and `website/api/v13_rc1_SHA256SUMS.txt` are the **public, safe metadata** describing the V13 RC1 release-candidate artifact bundle. They let any reviewer:

- See exactly which binaries (`sost-node`, `sost-miner`, `sost-cli`) make up the V13 RC1 build, their byte sizes, and their SHA-256 hashes.
- See the bundle id, the recorded `min_commit`, the deterministic tarball's basename + sha256.
- Verify byte-for-byte that any binary they later download (from a separate manual publication step) is exactly the binary the operator built locally for V13 RC1.

These files are **published before** the operator signs anything or uploads any binary. They are the audit surface, not the release surface.

---

## 2. What this is NOT

| Item | Why it is not here |
|---|---|
| The compiled binaries themselves | The repository is not a binary distribution channel. Binaries are produced locally per `V13_BINARY_PREFLIGHT.md` and published through a separate, manual operator step (GitHub release / mirror / IPFS — operator's choice). |
| A signature over `SHA256SUMS` | Signing is an explicit manual operator action. When (and if) the operator signs `SHA256SUMS` with the release key, a corresponding `*.sig` file will appear alongside it on the publication surface. This step is **NOT** automated. |
| A release upload | No script in the V13 RC1 chain has any network / upload primitive. |
| A wallet, private key, seed phrase | Nothing here touches any signing or wallet material. |
| A broadcast capability | No transaction is built, signed, or sent. |
| An automated download endpoint | Operators download binaries from whatever public distribution channel the release announcement points to; the manifest only lists the SHA-256 to verify against. |

---

## 3. How to verify once binaries are downloaded

The verification flow is intentionally simple and offline:

```bash
# 1. Download binaries from the operator's published release surface.
#    (Wherever the BitcoinTalk announcement / website link points.)
mkdir -p v13-rc1 && cd v13-rc1
# ... place sost-node, sost-miner, sost-cli here ...

# 2. Download the public SHA256SUMS (or copy from this repo /api/).
curl -fSsL -o SHA256SUMS https://sostcore.com/api/v13_rc1_SHA256SUMS.txt

# 3. Re-hash and compare.
sha256sum -c SHA256SUMS
# expected: every line ends with '  OK'
```

The SHA256SUMS file is now **signed**. The full offline verification flow is:

```bash
# 4. Download the operator-signed detached signature.
curl -fSsL -o SHA256SUMS.asc https://sostcore.com/api/v13_rc1_SHA256SUMS.asc

# 5. Import the SOST release public key (announced on the BitcoinTalk
#    thread and published on sostcore.com — it is NOT the same as any
#    wallet, mining or SbPoW key).
gpg --recv-keys 41B1A46E626064AB524CB99EB6B9E2852AE41A04
# (or import from a file published next to the announcement)

# 6. Verify the signature.
gpg --verify SHA256SUMS.asc SHA256SUMS
# expected:
#   gpg: Good signature from "SOST Release (V13 RC1 release signing key) <sost@sostcore.com>"
#   Primary key fingerprint: 41B1 A46E 6260 64AB 524C  B99E B6B9 E285 2AE4 1A04

# 7. Independently hash the signature file itself and compare to
#    the value in the public manifest (signature.sha256):
sha256sum SHA256SUMS.asc
# expected: 5e83889bb95d21404c3ae4faedfeb8c04729343fc88b03f5a9e608dd7c228779
```

A `gpg: WARNING: This key is not certified with a trusted signature!` line is expected on a fresh keyring — it means you have imported the key but have not personally signed it as trusted in your local web-of-trust. The `Good signature` line is what matters; the `WARNING` only says you have not yet locally trusted the key.

The public manifest file additionally exposes the SHA-256 of the deterministic tarball (`v13-rc1-artifact-bundle-v13rc1bundle-<id>.tar.gz`). If the operator publishes that tarball, reviewers can verify the whole bundle in one step:

```bash
sha256sum v13-rc1-artifact-bundle-v13rc1bundle-fe3b041de40a3f62.tar.gz
# compare to manifest.tarball.sha256
```

---

## 4. Why a separate public manifest, not just the in-repo `MANIFEST.json`

The in-repo bundle MANIFEST.json (under `config/v13_release_candidate.json` and the various `v13_*` JSONs) is operator-side metadata. It is rich and contains some fields that are only meaningful inside the operator's tree (e.g. `repo_root_basename`, `preflight_was_ready`, `no_copy_binaries_mode`). The public manifest is a deliberate subset:

- **Kept**: `bundle_id`, `pinned_time`, `rc_id`, `activation_height`, `min_commit`, `binaries[]`, `sha256sums_basename`, `reports[]`, `configs[]`, `tarball`, `safety_flags`, `release_status`.
- **Omitted**: `repo_root_basename` (operator-local), `no_copy_binaries_mode` (internal flag), `preflight_was_ready` (internal — the bundle itself was only built because the preflight reported it ready; mirroring this in public adds no audit value).

The `release_status` field on the public manifest is the load-bearing signal:

| `release_status` value | What it means |
|---|---|
| `metadata_only_not_signed_not_uploaded` | (Historical, website-v268.) Metadata was published; the operator had NOT yet signed `SHA256SUMS` and had NOT yet uploaded binaries to any public distribution surface. |
| `signed_metadata_only` | **Current state (website-v269).** The `SHA256SUMS.asc` detached OpenPGP signature is published alongside `SHA256SUMS`, signed with the SOST release key (primary fingerprint `41B1A46E626064AB524CB99EB6B9E2852AE41A04`, signing subkey `E2FCC898520842F0192EF7A46422CC120F51DCEA`). Binaries are still NOT on a public distribution surface from the operator. Anyone now downloading future V13 RC1 binaries from the operator's eventual release surface can already verify them locally with `sha256sum -c SHA256SUMS && gpg --verify SHA256SUMS.asc SHA256SUMS`. |
| `signed_and_published` | (Future.) Operator has signed `SHA256SUMS` (already true) AND uploaded binaries to a publication channel AND posted the release announcement linking the two. |

The transition from `metadata_only_not_signed_not_uploaded` to `signed_metadata_only` (which landed in website-v269) was an explicit manual operator action: the operator ran `gpg --detach-sign --armor SHA256SUMS` on the secure host that holds the SOST release key. No automated agent ever touched the release key. The next transition (`signed_metadata_only` → `signed_and_published`) is similarly a manual operator action — it requires the operator to upload the binaries to a public distribution channel and announce the release.

---

## 5. Safety contract

The public files honour the same const-true safety block the bundle generator produced internally:

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

And the two public files:

- contain **NO** absolute paths from the operator's temporary
  or installation directories
- contain **NO** binary ELF content
- contain **NO** private key, mnemonic, seed phrase, or signing material
- carry only the SHA-256 hashes the operator's local bundle already computed

These properties are checked statically during the publish commit.

---

## 6. Pointers

- Operator-local bundle generator: `scripts/trinity/v13_rc1_artifact_bundle.py` + `docs/V13_RC1_ARTIFACT_BUNDLE.md`.
- Operator-local preflight: `scripts/trinity/v13_binary_preflight.py` + `docs/V13_BINARY_PREFLIGHT.md`.
- V13 RC1 release-candidate manifest (RC stage, not binary): `config/v13_release_candidate.json`, `website/api/v13_release_candidate.json`, `docs/V13_RELEASE_CANDIDATE.md`.
- V13 activation plan: `docs/V13_ACTIVATION_PLAN.md`, `docs/V13_READINESS_GATES.md`.
- Miner / operator checklist: `docs/V13_MINER_OPERATOR_CHECKLIST.md`.

If you want to reproduce the binaries from source instead of trusting a downloaded copy, run the build sequence in `docs/V13_BINARY_PREFLIGHT.md` and run the preflight script. The SHA-256 you compute locally must match the SHA-256 in `website/api/v13_rc1_SHA256SUMS.txt`.
