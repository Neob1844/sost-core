# V30000 — Offline Release Signing Runbook

Goal: produce an **authenticity** signature over `docs/v30000/SHA256SUMS.txt`
without a private key ever touching an online machine (server, WSL, CI, GitHub).

The **private key stays OFFLINE** (air-gapped box or encrypted USB). Only the
**public key** and the **detached signature** ever come back online.

----------------------------------------------------------------------
OPTION A — minisign (recommended: tiny, modern Ed25519)
----------------------------------------------------------------------
On your OFFLINE machine:

    # install minisign (Debian/Ubuntu: apt install minisign; or the static binary)
    # generate the keypair ONCE (prompts for a passphrase — use a strong one):
    minisign -G -p sost-release.pub -s sost-release.key
    #   sost-release.pub  -> PUBLIC  (publish)
    #   sost-release.key  -> PRIVATE (keep OFFLINE, encrypted; NEVER copy online)

    # FIRST verify the manifest matches YOUR independently downloaded binaries:
    sha256sum -c SHA256SUMS.txt
    #   sost-node: OK / sost-miner: OK / sost-cli: OK

    # sign (detached):
    minisign -S -s sost-release.key -m SHA256SUMS.txt -x SHA256SUMS.txt.minisig

Bring back ONLY:  sost-release.pub  +  SHA256SUMS.txt.minisig

----------------------------------------------------------------------
OPTION B — GPG (if you already keep a GPG identity offline)
----------------------------------------------------------------------
On your OFFLINE machine:

    gpg --full-generate-key                 # Ed25519/RSA4096; set an expiry
    gpg --armor --export <KEYID> > sost-release.asc          # PUBLIC
    sha256sum -c SHA256SUMS.txt                              # verify first
    gpg --armor --detach-sign -u <KEYID> -o SHA256SUMS.txt.asc SHA256SUMS.txt

Bring back ONLY:  sost-release.asc  +  SHA256SUMS.txt.asc
(The secret key and its revocation certificate stay OFFLINE.)

----------------------------------------------------------------------
THEN (online, done for you once you hand back the public material):
----------------------------------------------------------------------
  * publish the public key at  keys/sost-release.pub  (and /asc for gpg)
    and at  https://sostcore.com/keys/sost-release.pub
  * publish the detached signature next to the manifest and on the release
  * anyone verifies with:
        scripts/verify-release.sh --minisign docs/v30000/SHA256SUMS.txt keys/sost-release.pub --check-sums
        scripts/verify-release.sh --gpg      docs/v30000/SHA256SUMS.txt keys/sost-release.asc --check-sums

Honesty labels (do not overclaim):
  TOOLING READY            = yes (scripts/sign-release.sh, verify-release.sh)
  MANIFEST CREATED         = yes (docs/v30000/SHA256SUMS.txt)
  PUBLIC KEY PUBLISHED     = only after the .pub/.asc is installed above
  V30000 MANIFEST SIGNED   = only after a real detached signature exists
  OFFLINE CUSTODY COMPLETE = only if the private key was generated and kept
                             off-line and never online — NEVER claim otherwise
