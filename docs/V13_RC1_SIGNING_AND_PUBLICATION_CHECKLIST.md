# V13 RC1 — Signing & Publication Checklist

**Checklist generator:** `scripts/trinity/v13_rc1_release_manual_checklist.py`
**Schema:** `schemas/trinity/v13_rc1_release_manual_checklist.schema.json` (`$id` = `trinity-v13-rc1-release-manual-checklist/v0.1`)
**Companion docs:** `V13_RC1_ARTIFACT_BUNDLE.md`, `V13_RC1_PUBLIC_ARTIFACT_METADATA.md`, `V13_BINARY_PREFLIGHT.md`, `V13_RELEASE_CANDIDATE.md`

This document describes the manual operator steps that transition the V13 RC1 release from `metadata_only_not_signed_not_uploaded` to `signed_and_published`. The companion script generates the same checklist as a JSON + Markdown report so the operator can tick it off in their own terminal, but **does not execute any of the steps**. Signing, uploading, GitHub API calls, and announcements remain explicit manual operator actions.

---

## 1. Where the boundary is

```
+--------------------+      +--------------------+      +-------------------+
| automation         |  ->  | manual operator    |  ->  | automation        |
| (bundle generator, |      | (sign + upload +   |      | (metadata bump +  |
|  metadata mirror,  |      |  announce)         |      |  website refresh) |
|  this checklist)   |      |                    |      |                   |
+--------------------+      +--------------------+      +-------------------+
   pre-signing                  signing window               post-signing
```

The automated side **never** holds the release key, **never** opens the network for the release upload, **never** posts the announcement. The script in this directory only:

1. Confirms the local bundle is intact.
2. Confirms the public website metadata is still at `metadata_only_not_signed_not_uploaded`.
3. Emits the operator's manual to-do list with copy-paste command templates and explicit warnings.

The transitions are operator-acknowledged:

```
metadata_only_not_signed_not_uploaded
    -> signed_metadata_only            (after operator signs SHA256SUMS)
    -> signed_and_published            (after operator uploads + announces)
```

---

## 2. Hard warnings (read these before anything else)

- **The release key MUST stay offline / on a secure host.** Never give it to any automated agent. The script in this branch refuses to invoke gpg / signify / minisign — that is intentional.
- **Never sign on an untrusted host.** Run step B (signing) only on the machine that already holds the release key. Do not export the key. Do not copy it.
- **Never upload unsigned binaries as a final release.** If you have to upload binaries before the signature is ready, keep the public manifest at `signed_metadata_only` (NOT `signed_and_published`) until the signature follows.
- **Never let a third party publish under your release identity.** Re-download every published URL from a different host and re-verify the SHA256SUMS + the signature before posting the announcement.
- **This checklist is documentation, not a script.** Do not pipe its Markdown into a shell. Read it, copy the commands you want, and run them yourself.

---

## 3. Stage A — pre-sign verification

| Step | What | Notes |
|---|---|---|
| **A1** | `sha256sum -c SHA256SUMS` inside `<bundle>/bin/` | independent re-hash of every binary against the bundle's recorded SHA-256 |
| **A2** | (optional) re-run `scripts/trinity/v13_binary_preflight.py` with `--require-binaries --run-tests --run-ctest --write-sha256sums` | confirms `ready_to_release: true` on the same tree the bundle was built from |
| **A3** | confirm release-key fingerprint on the SECURE host | the release key MUST be different from any wallet / mining / SbPoW key |

If any of these fails, stop. Do not sign.

---

## 4. Stage B — sign `SHA256SUMS`

This is the only step that touches the release key. Run it on the secure host that already holds the key. The script in this branch never invokes gpg / signify / minisign; the operator picks the tool.

| Step | Command template (operator pastes into their own shell) | Output |
|---|---|---|
| **B1** | `gpg --detach-sign --armor <bundle>/SHA256SUMS` | writes `SHA256SUMS.asc` next to `SHA256SUMS` |
| **B2** | `gpg --verify <bundle>/SHA256SUMS.asc <bundle>/SHA256SUMS` | confirms the signature verifies cleanly against the public release key |
| **B3** | `sha256sum <bundle>/SHA256SUMS.asc` | record the signature's own SHA-256 — needed for step D2 |

Output of stage B: a `SHA256SUMS.asc` file the operator can publish. The public release pubkey was already announced on the BitcoinTalk thread; reviewers will verify with it.

---

## 5. Stage C — upload release

The script never calls the GitHub API. The operator does. Two safe paths:

**Path 1 — `gh` CLI** (interactive, on the operator's own machine):

```bash
gh release create v13-rc1 --draft \
    --title 'SOST V13 RC1' \
    --notes-file <bundle>/MANIFEST.md

gh release upload v13-rc1 \
    <bundle>/bin/sost-node \
    <bundle>/bin/sost-miner \
    <bundle>/bin/sost-cli \
    <bundle>/SHA256SUMS \
    <bundle>/SHA256SUMS.asc
```

**Path 2 — GitHub web UI**:

Drag and drop the same five files onto a new release draft, then click Publish.

After upload (step **C3**), re-download every file from a different host and re-verify:

```bash
curl -fSsLO <release-url>/SHA256SUMS
curl -fSsLO <release-url>/SHA256SUMS.asc
gpg --verify SHA256SUMS.asc SHA256SUMS
# then re-hash binaries fetched from the URL and compare against SHA256SUMS
```

If any check fails, mark the release as `signed_metadata_only` (NOT `signed_and_published`) until the bytes are correct on the publication surface.

---

## 6. Stage D — update public metadata

This stage is back inside the automation surface, but every change is on a feature branch the operator pushes/merges/tags themselves. The script in this branch does NOT push/merge/tag.

| Step | What | File |
|---|---|---|
| **D1** | flip `release_status` to `signed_and_published` (or `signed_metadata_only` if only the signature is up so far) | `website/api/v13_rc1_artifact_manifest.json` |
| **D2** | add a `signature` block with `basename`, `sha256` (from B3) and `public_url` | same file |
| **D3** | bump explorer version `v268` → `v269` | `website/api/explorer_version.json` |
| **D4** | operator interactive release sequence (push + merge + tag + delete branch) | local terminal |

Suggested next tag: `website-v269` (consistent with the v265 / v266 / v267 / v268 chain).

---

## 7. Stage E — announce

Once the public URLs are stable and re-verified, post the announcement:

| Step | Where | What to include |
|---|---|---|
| **E1** | BitcoinTalk canonical thread | release URL, four SHA-256 hashes (three binaries + SHA256SUMS), signature URL, release-key fingerprint, verification command |
| **E2** | official Telegram channel | condensed version of E1; the channel is announced from the thread first to block impersonators |
| **E3** | sostcore.com explorer + protocol-spec + relevant pages | bundle with the next website bump |

The order matters: BitcoinTalk first, so the canonical source of truth lives in the operator's own thread; everything downstream points at it.

---

## 8. How the script helps

```bash
python3 scripts/trinity/v13_rc1_release_manual_checklist.py \
    --repo-root   /opt/sost \
    --bundle-dir  /tmp/sost-v13-rc1-artifact-bundle \
    --out-json    /tmp/sost-v13-rc1-release-checklist/checklist.json \
    --out-md      /tmp/sost-v13-rc1-release-checklist/checklist.md \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
```

Output:

- `checklist.json` — schema-locked, every safety flag const-true, every manual step has a string `command_template` that the operator must run themselves
- `checklist.md` — same content rendered as a tick-box list per stage (A → E)

Exit codes:

- `0` — bundle intact AND public metadata is still in the pre-signing state
- `1` — bundle has gaps OR public metadata is not in the pre-signing state; fix that first
- `2` — usage / setup error

Nothing the script does opens the network, invokes gpg, executes a subprocess, touches a wallet, or mutates git state.

---

## 9. Safety contract enforced by the script

```
no_private_key_access   true
no_signing_executed     true
no_release_upload       true
no_github_api           true
no_wallet_access        true
no_broadcast            true
no_network_required     true
no_subprocess           true
no_shell_true           true
no_ethereum_deploy      true
no_gpg_invocation       true
```

Eleven flags. All const-locked at the schema level. The static safety test refuses to let the script regress.

---

## 10. What this document is NOT

- Not a release tool. The operator releases.
- Not a signing tool. The operator signs on a secure host with the release key.
- Not a publication tool. The operator uploads to GitHub / mirror / IPFS.
- Not an announcement tool. The operator posts to BitcoinTalk + Telegram + web.
- Not a substitute for `V13_RC1_PUBLIC_ARTIFACT_METADATA.md`. That doc describes the *current* public surface; this one describes the *next* manual step.
