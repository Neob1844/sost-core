# Release Distribution Mirror — Runbook
Goal: multiple independent transports for the SAME cryptographic source of truth, so the
binaries can be obtained + verified even if main GitHub is unavailable.

## One source of truth, many transports
The canonical manifest is `docs/v30000/SHA256SUMS.txt` (node/miner/cli SHA-256). ANY mirror
is trusted ONLY insofar as a downloaded file matches that manifest. Mirrors never need to be
trusted themselves — the hashes are the trust anchor.

## Mirrors you can stand up (no consensus change)
- **Second git host:** push the repo + release assets to a second forge (GitLab/Codeberg/self-hosted).
- **Static HTTP:** host sost-node/sost-miner/sost-cli + SHA256SUMS.txt on an independent domain/CDN.
- **IPFS:**  `ipfs add sost-node sost-miner sost-cli SHA256SUMS.txt`  → publish the CIDs. Anyone: `ipfs get <cid>`.
- **Torrent/magnet:** create a torrent of the release dir; publish the magnet link.

## Operator verification (ALWAYS, regardless of transport)
    sha256sum -c SHA256SUMS.txt        # must print: sost-node: OK / sost-miner: OK / sost-cli: OK
    # if a single byte differs → STOP, do not run it.

## Download + verify from several mirrors (scripted)
`scripts/release/fetch-and-verify.sh` takes any number of mirrors (`--mirror <https base URL>`,
repeatable, or `--mirrors-file release/MIRRORS.txt`). It authenticates `SHA256SUMS` with the
release public key first, then accepts each file only if its sha256 matches; a mirror that is
down or serves a bad copy is skipped. This is how a user gets a verified release with
sostcore.com unreachable:

    scripts/release/fetch-and-verify.sh --tag <tag> --out ./rel --backend openssl \
        --pubkey keys/sost-release.pem --mirror https://github.com/Neob1844/sost-core/releases/download/<tag> \
        --mirror https://<independent mirror>/sost/<tag>

`release/MIRRORS.txt` lists only publication points that exist (today the GitHub release
assets); add an independent mirror there once it is operated. Accepted forms: static HTTPS on
another domain, an IPFS gateway URL for the release CID, a second forge's release assets, or
`file://` for offline media. Plain `http://` is refused.

## (Future, optional) authenticity on top of integrity
Sign SHA256SUMS.txt (minisign/GPG) with an OFFLINE key and publish the PUBLIC key on ≥2
independent hosts. Then operators verify the signature before trusting the manifest.
Tooling: scripts/release/make-sha256sums.sh, scripts/sign-release.sh (minisign/gpg/openssl),
scripts/verify-release.sh, scripts/release/fetch-and-verify.sh — see docs/RELEASE_SIGNING.md.
