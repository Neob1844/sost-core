# SOST Release Signing

**Status:** tooling added (`scripts/sign-release.sh`, `scripts/verify-release.sh`).
No real release key is created, stored, or shipped by this change.
**Scope:** adds cryptographic **authenticity** on top of the existing
`SHA256SUMS` **integrity** files. No consensus, binary, or RC change.

---

## 1. Why both SHA256SUMS *and* a signature

| Property | Provided by | Answers |
|---|---|---|
| **Integrity** | `SHA256SUMS` (+ `sha256sum -c`) | "Did these bytes arrive unchanged?" |
| **Authenticity** | detached signature over `SHA256SUMS` | "Did the SOST owner actually release these bytes?" |

A `SHA256SUMS` file alone is only as trustworthy as the channel it came from:
anyone who can replace the binaries can also replace `SHA256SUMS`. Signing
`SHA256SUMS` with a key the public already trusts closes that gap — tamper with
any binary and the hash breaks; tamper with `SHA256SUMS` and the signature
breaks. We sign the **sums file**, not each binary, so one signature covers the
whole release and the existing `SHA256SUMS` workflow is unchanged.

---

## 2. Key custody — the hard rules

- The **private release key is the owner's and lives OFFLINE** — encrypted USB
  / air-gapped machine. This mirrors the Beacon key custody model already in
  use (`docs/BEACON_CUSTODY_STATUS.md`).
- The private key **must never** appear in: this repo, the VPS, any log, any CI
  job, any environment dump, or GitHub. `scripts/sign-release.sh` reads the key
  path **at runtime only** (argument / `SIGN_KEY` env) and never copies, prints,
  or transmits it.
- The **public** key MAY and SHOULD be published (repo + web). It is not secret.

---

## 3. Preferred backend: minisign (Ed25519)

`minisign` is tiny, has no keyring state, and produces a one-line public key
that is easy to publish and pin.

### One-time key generation (owner, on the OFFLINE machine only)

```sh
# Run this ONLY on the air-gapped machine. The secret key stays there.
minisign -G -p sost-release.pub -s sost-release.key
#   sost-release.pub  -> PUBLIC, publish it (repo keys/ + web)
#   sost-release.key  -> SECRET, never leaves the offline machine (encrypted)
```

> This repository does **not** run the keygen and ships **no** key. The command
> above is documentation for the owner.

### Sign a release (owner)

```sh
scripts/sign-release.sh --minisign docs/v16/SHA256SUMS_v16.2.3 /media/usb/sost-release.key
# -> docs/v16/SHA256SUMS_v16.2.3.minisig
```

### Verify (anyone)

```sh
scripts/verify-release.sh --minisign docs/v16/SHA256SUMS_v16.2.3 keys/sost-release.pub --check-sums
```

---

## 4. Fallback backend: GPG

```sh
# Sign (secret key from the owner's offline keyring; -u pins the identity)
scripts/sign-release.sh --gpg docs/v16/SHA256SUMS_v16.2.3 <key-id-or-fingerprint>
# -> docs/v16/SHA256SUMS_v16.2.3.asc

# Verify (standalone public key, no keyring pollution — the script uses a temp GNUPGHOME)
scripts/verify-release.sh --gpg docs/v16/SHA256SUMS_v16.2.3 keys/sost-release.asc --check-sums
```

---

## 5. Where the PUBLIC key lives (placeholder paths)

Publish the public key in BOTH places and document the fingerprint:

- **Repo:** `keys/sost-release.pub` (minisign) and/or `keys/sost-release.asc` (gpg)
- **Web:** `https://sostcore.com/keys/sost-release.pub`

> These paths are **placeholders** — the real public key is installed by the
> owner. Pin the public-key fingerprint in the release notes so a verifier can
> confirm the key itself out-of-band (the same way the Beacon pubkey fingerprint
> `bbb560e3…` is pinned in `docs/BEACON_CUSTODY_STATUS.md`).

---

## 6. Release checklist (operator)

1. Build the release binaries (unchanged process).
2. Generate `SHA256SUMS` (unchanged process).
3. On the OFFLINE machine: `sign-release.sh --minisign SHA256SUMS <seckey>`.
4. Publish `SHA256SUMS` **and** `SHA256SUMS.minisig` together.
5. Ensure `keys/sost-release.pub` (repo + web) matches the pinned fingerprint.
6. Smoke-test: `verify-release.sh --minisign SHA256SUMS keys/sost-release.pub --check-sums`.

---

## 7. What this does NOT change

- No consensus rule, no binary, no RC artifact.
- `SHA256SUMS` files already published stay valid; signatures are **additive**.
- Existing `SHA256SUMS`-only verification keeps working for anyone who does not
  yet have the public key.
