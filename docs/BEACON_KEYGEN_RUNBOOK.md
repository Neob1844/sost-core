# Beacon keygen runbook — V13 operator keys

**Last updated:** 2026-05-23  
**Audience:** SOST operator generating the V13 Beacon operator keys
for the first time.  
**Outcome:** 6 secp256k1 keypairs (1 II-A single-sig + 5 II-B
threshold) generated on the operator machine with the network
disconnected, private keys encrypted with AES-256 + passphrase, public
keys ready to paste back into the install commit.

## What this runbook does NOT do

- Does not generate any key automatically. Every command is run by
  the operator on their own machine.
- Does not handle private keys. The runbook produces 6 `.pem` files
  encrypted with AES-256 and 6 hex pubkeys + 6 SHA-256 fingerprints.
  Only the pubkeys + fingerprints are ever paste-back material.
- Does not push, merge, tag, or deploy anything.

## Preconditions (verify BEFORE you start)

Run these checks on the operator machine (WSL on
DESKTOP-CR2TMLU is the documented target; any Linux works):

```bash
# OpenSSL is installed
openssl version
# expected: OpenSSL 3.x or higher

# The keygen script is the AES-256 version
grep -c "aes256" scripts/beacon-keygen.sh
# expected: 1 or more

# /dev/shm exists and is writable (the script aborts otherwise)
test -d /dev/shm && test -w /dev/shm && echo OK
# expected: OK

# The 6 placeholders are still in src/beacon.cpp (read-only check)
grep -n "BEACON_PUBKEY_HEX =" src/beacon.cpp
grep -n "key [0-4] .*placeholder\|generator point" src/beacon.cpp | head -6
# expected: 1 line for II-A, 5 lines for II-B placeholders

# The II-B threshold sentinel is OFF (INT64_MAX)
grep -n "BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT" include/sost/params.h
# expected: ...= INT64_MAX
```

If any check fails, stop and report. Do not proceed with keygen.

## Pre-flight checklist (machine hygiene)

Before generating any key on the operator machine:

- [ ] Close every application not needed for keygen (browsers,
      IDEs, code agents, chat clients, screen recorders).
- [ ] Decide the 6 passphrases in advance. Each one:
      - >= 20 characters, ideally a 6-8 word diceware phrase
      - distinct from the other 5 passphrases
      - written to a password manager **and** a paper backup
      - stored physically separate from where the .pem will live
- [ ] Prepare the USB sticks:
      - 1 USB stick for the II-A private key
      - 2 USB sticks for the 5 II-B private keys (split: e.g.
        keys 0/1/2 on stick A, keys 3/4 on stick B, or any other
        distribution that puts them in **different physical
        locations**)
      - 1 spare USB stick for the second backup of all 6 .pem files
      - All USB sticks are encrypted (BitLocker, VeraCrypt, LUKS).
- [ ] Disconnect the network:
      - WiFi OFF
      - Ethernet cable UNPLUGGED (if applicable)
      - Verify with `ping -c 1 8.8.8.8` -> should fail.
- [ ] Open a fresh terminal in WSL (no shared history with the agent).

## Keygen — 6 invocations

All commands are run inside WSL on the operator machine.

```bash
# Create a working directory in your home, NOT inside the repo
mkdir -p ~/sost-beacon-keys-v13
chmod 700 ~/sost-beacon-keys-v13
cd ~/sost-beacon-keys-v13

# Set the path to the keygen script
KEYGEN=~/SOST/sostcore/sost-core/scripts/beacon-keygen.sh

# Verify the script is executable
ls -la "$KEYGEN"
# expected: -rwxr-xr-x ...
```

### Key 1 of 6 — II-A single-sig

```bash
"$KEYGEN" ./beacon-iia-priv.pem ./beacon-iia-pub.pem
```

Output you should see (in order):

```
Generating secp256k1 keypair. You will be prompted for a passphrase
THREE times: (1) set, (2) confirm, (3) read to derive public key.
...
read EC key
writing EC key
Enter PEM pass phrase:                # <-- prompt 1: type passphrase A
Verifying - Enter PEM pass phrase:    # <-- prompt 2: re-type passphrase A
read EC key
Enter PEM pass phrase:                # <-- prompt 3: re-type passphrase A

Beacon keypair generated:
  private key : ./beacon-iia-priv.pem  (mode 600, AES-256 ENCRYPTED — keep SECRET)
  public  key : ./beacon-iia-pub.pem   (commit this to repo)

Public key fingerprint (sha256 of uncompressed pubkey hex):
  <64 hex chars>                      # <-- COPY THIS, it is the II-A fingerprint

Uncompressed public key (hex, 65 bytes — embed in src/beacon.cpp
as BEACON_PUBKEY_HEX or as one entry of BEACON_THRESHOLD_PUBKEYS):
  04<128 hex chars>                   # <-- COPY THIS, it is the II-A pubkey
```

**Write down on paper (NOT in any file):**

```
II-A
  passphrase: <the words you used> (only on the paper backup, not anywhere digital)
  fingerprint: <64-hex>
  pubkey_hex:  04<128-hex>
```

### Keys 2-6 of 6 — II-B threshold (3-of-5)

Run the same command pattern 5 more times. Use a **different
passphrase** for each one.

```bash
"$KEYGEN" ./beacon-iib-0-priv.pem ./beacon-iib-0-pub.pem
# Enter passphrase B (twice + read)
# Record fingerprint + pubkey_hex on paper as "II-B key 0"

"$KEYGEN" ./beacon-iib-1-priv.pem ./beacon-iib-1-pub.pem
# Enter passphrase C
# Record fingerprint + pubkey_hex as "II-B key 1"

"$KEYGEN" ./beacon-iib-2-priv.pem ./beacon-iib-2-pub.pem
# Enter passphrase D
# Record fingerprint + pubkey_hex as "II-B key 2"

"$KEYGEN" ./beacon-iib-3-priv.pem ./beacon-iib-3-pub.pem
# Enter passphrase E
# Record fingerprint + pubkey_hex as "II-B key 3"

"$KEYGEN" ./beacon-iib-4-priv.pem ./beacon-iib-4-pub.pem
# Enter passphrase F
# Record fingerprint + pubkey_hex as "II-B key 4"
```

After all 6 keys are generated, list the directory:

```bash
ls -la ~/sost-beacon-keys-v13
# expected: 12 files total
#   6 *-priv.pem  (mode 600, AES-256 encrypted)
#   6 *-pub.pem   (mode 644, plaintext public)
```

Verify each .pem is actually encrypted:

```bash
for f in ~/sost-beacon-keys-v13/*-priv.pem; do
  echo "--- $f ---"
  grep -c "ENCRYPTED\|Proc-Type: 4,ENCRYPTED" "$f"
done
# expected: each file shows >= 1
```

If any file shows 0, that .pem is NOT encrypted — STOP and regenerate
that key.

## Move private keys to encrypted USB (and wipe locally)

```bash
# Mount your encrypted USB (BitLocker / VeraCrypt / LUKS) and assume
# it is at /mnt/usb-a (adjust to your mountpoint).

cp ~/sost-beacon-keys-v13/beacon-iia-priv.pem      /mnt/usb-a/
cp ~/sost-beacon-keys-v13/beacon-iib-0-priv.pem    /mnt/usb-a/
cp ~/sost-beacon-keys-v13/beacon-iib-1-priv.pem    /mnt/usb-a/
cp ~/sost-beacon-keys-v13/beacon-iib-2-priv.pem    /mnt/usb-a/
# (split the rest to a second USB at a different location)

cp ~/sost-beacon-keys-v13/beacon-iib-3-priv.pem    /mnt/usb-b/
cp ~/sost-beacon-keys-v13/beacon-iib-4-priv.pem    /mnt/usb-b/

# Optional but recommended: full backup of all 6 on a third USB,
# stored in yet another location.
cp ~/sost-beacon-keys-v13/*-priv.pem               /mnt/usb-backup/

# Verify the copies exist on the USB(s)
ls -la /mnt/usb-a /mnt/usb-b /mnt/usb-backup

# NOW wipe the local copies of the private keys
shred -u ~/sost-beacon-keys-v13/*-priv.pem

# The public keys can stay on disk — they are public.
ls ~/sost-beacon-keys-v13
# expected: only 6 *-pub.pem files
```

Unmount + physically disconnect the USB sticks. Store them in their
respective locations.

## Reconnect the network

Only after all 6 private keys are on encrypted USB(s) and wiped
locally:

```bash
# Reconnect WiFi or plug the cable back in.
# Verify network is back
ping -c 1 8.8.8.8
# expected: success
```

## Paste-back format — exactly what to send to the install agent

When you return to the assistant chat, paste **only** the block below.
Replace each `<placeholder>` with the actual hex (no quotes, no
backticks, no extra whitespace). Include the dash separators.

```
=== BEACON V13 OPERATOR PUBLIC KEYS — bootstrap custody ===

II-A
  pubkey_hex:  04<128 hex chars>
  fingerprint: <64 hex chars>

II-B key 0
  pubkey_hex:  04<128 hex chars>
  fingerprint: <64 hex chars>

II-B key 1
  pubkey_hex:  04<128 hex chars>
  fingerprint: <64 hex chars>

II-B key 2
  pubkey_hex:  04<128 hex chars>
  fingerprint: <64 hex chars>

II-B key 3
  pubkey_hex:  04<128 hex chars>
  fingerprint: <64 hex chars>

II-B key 4
  pubkey_hex:  04<128 hex chars>
  fingerprint: <64 hex chars>

=== END ===
```

**Hard rules for the paste-back:**

- **Each pubkey_hex** is exactly **130 hex characters** (the literal
  prefix `04` + 128 hex chars).
- **Each fingerprint** is exactly **64 hex characters** (SHA-256).
- **All 6 pubkeys MUST be distinct.** If any two are identical, stop
  and regenerate (the install will reject duplicates).
- **NEVER paste**:
  - the content of any `.pem` file
  - any passphrase
  - any output from `openssl ec -in <file> -text` that includes the
    `priv:` block

## What the install commit will do (when you paste back)

1. Substitute the 6 placeholders in `src/beacon.cpp` with the
   real pubkeys, preserving the same `"04"` + 64 + 64 chunk layout.
2. Verify each substituted pubkey: 130 chars, starts with `04`, is
   distinct from the other 5.
3. Recompute SHA-256 of each pubkey on the install side and compare
   to the fingerprint you pasted. Any mismatch aborts the install.
4. Update the comments next to each pubkey from
   `// placeholder, fail-closed` to
   `// V13 bootstrap custody — fingerprint <sha256>`.
   The comments will **not** claim distributed custody (that is
   reserved for after the operator distributes 4 of 5 II-B keys to
   independent custodians — see `docs/BEACON_CUSTODY_STATUS.md`).
5. Update `docs/BEACON_CUSTODY_STATUS.md` with the 6 fingerprints
   under the bootstrap section.
6. Run the Beacon test suite + Trinity.
7. Commit as `beacon: install V13 operator public keys`.

No push, no merge — the operator does the release ceremony manually.

## Disaster recovery

| Scenario | Action |
|---|---|
| You lost a passphrase | That `.pem` is a brick. Regenerate **only that key** (one new keygen invocation), distribute the new pubkey + fingerprint, and update `BEACON_CUSTODY_STATUS.md`. If it was the II-A key, the legacy single-sig channel is rotated. If it was an II-B key, the threshold scheme can survive 1 lost key (3-of-5 still works with 4) but a future rotation is required to restore full 5-of-5 redundancy. |
| You lost a `.pem` file (USB destroyed) | Same as above — regenerate that one key. |
| You lost the paper backup of pubkeys + fingerprints | The pubkeys can be re-derived from the corresponding `.pem` (you still need the passphrase). The fingerprints can be re-derived from the pubkeys. Use `openssl ec -in <file> -pubout` + `awk` + `sha256sum`. |
| You suspect a `.pem` was exposed (USB lost in transit) | Treat the corresponding key as compromised. Regenerate, distribute new pubkey, and publish a revocation notice using the existing II-A key (if not the one compromised) or a threshold-signed II-B notice. |
| The `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT` sentinel is lowered before custody is distributed | Revert the sentinel back to `INT64_MAX` in a fast follow-up commit. The II-B threshold path is silently disabled again. |

## Hard rules to repeat to yourself

- The 6 private keys NEVER touch: the repo, GitHub, any chat, any
  email, any unencrypted disk that is not RAM tmpfs.
- The 6 passphrases NEVER touch: any file on the operator machine,
  any chat, any email.
- Paste-back: pubkeys + fingerprints only. 12 lines total.
- The first time you generate the keys is the only time the
  unencrypted private keys ever exist on the machine, and they exist
  only in `/dev/shm` (RAM tmpfs). The script wipes them on exit.
