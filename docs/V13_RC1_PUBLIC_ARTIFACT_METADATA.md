# V13 RC1 Public Artifact Metadata

**Public manifest:** `website/api/v13_rc1_artifact_manifest.json`
**Public SHA256SUMS:** `website/api/v13_rc1_SHA256SUMS.txt`
**Source bundle:** `v13-rc1-artifact-bundle-v01` (operator-local; binaries are NOT committed to this repository)
**Companion docs:** `V13_RC1_ARTIFACT_BUNDLE.md`, `V13_BINARY_PREFLIGHT.md`, `V13_RELEASE_CANDIDATE.md`, `V13_MINER_OPERATOR_CHECKLIST.md`

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

If the operator later publishes a signature, the same flow adds:

```bash
# 4. Download the operator-signed signature.
curl -fSsL -o SHA256SUMS.sig <wherever-the-operator-publishes-the-signature>

# 5. Verify the signature against the operator's release public key
#    (the operator publishes the release pubkey separately, e.g. on
#    BitcoinTalk + sostcore.com — it is NOT the same as any wallet
#    or mining key).
# (Operator chooses the signing scheme; see the release announcement
#  for the exact verify command.)
```

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
| `metadata_only_not_signed_not_uploaded` | Current state. Metadata is published; the operator has NOT yet signed `SHA256SUMS` and has NOT yet uploaded binaries to any public distribution surface. Anyone reading the manifest knows they should NOT install a binary from a third party claiming to be V13 RC1 — wait for the operator's signed release. |
| `signed_metadata_only` | (Future) A `*.sig` file is published alongside `SHA256SUMS` but binaries are still not on a public distribution surface from the operator. |
| `signed_and_published` | (Future) Operator has signed `SHA256SUMS`, uploaded binaries to a publication channel, and posted the release announcement linking the two. |

The transition from `metadata_only_not_signed_not_uploaded` to anything else is **always** a manual operator action, never an automated agent action.

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
