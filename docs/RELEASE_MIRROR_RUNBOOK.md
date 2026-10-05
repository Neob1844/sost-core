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

## (Future, optional) authenticity on top of integrity
Sign SHA256SUMS.txt (minisign/GPG) with an OFFLINE key and publish the PUBLIC key on ≥2
independent hosts. Then operators verify the signature before trusting the manifest.
(See the deferred release-signing tooling: scripts/sign-release.sh, verify-release.sh.)
