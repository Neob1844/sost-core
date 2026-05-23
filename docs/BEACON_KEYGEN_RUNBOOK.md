# Beacon keygen runbook — V13 operator key (II-A only)

**Last updated:** 2026-05-23  
**Audience:** SOST operator generating the V13 Beacon II-A operator
key. **One key only.**  
**Outcome:** 1 secp256k1 keypair (II-A single-sig) generated on the
operator machine with the network disconnected, private key encrypted
with AES-256 + passphrase, public key ready to paste back into the
install commit.

## Why only 1 key (and not 6)

V13 deliberately ships with Beacon Phase II-B (the 3-of-5 threshold
path) **dormant**:

- `include/sost/params.h:857` —
  `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT = INT64_MAX` (sentinel).
- While the sentinel holds, `src/beacon.cpp:is_active()` REJECTS
  every threshold-claimed notice BEFORE the threshold verifier runs,
  regardless of signature validity.
- The 5 placeholder pubkeys at `src/beacon.cpp:48-65` therefore
  never get evaluated against real signatures — they exist only so
  the code shape is final and a future activation does not require
  a code refactor.

The operator generates **only** the II-A key today. The 5 II-B keys
are generated and installed later, when 5 independent custodians are
identified and the operator decides to lower the sentinel.

What runs in V13 with the II-A key installed:

| Phase | Status | What it does |
|---|---|---|
| Phase II-A (single-sig, the key you generate today) | **ACTIVE** | Operator signs advisory notices; nodes verify against the installed II-A pubkey. |
| Phase II-B (3-of-5 threshold) | **DORMANT (sentinel)** | Code present, placeholders in place, no real keys, no notices accepted. |
| Phase III (P2P gossip) | **ACTIVE** | Nodes relay valid II-A notices peer-to-peer. The full 7-check pipeline (size cap, parse, sig verify, network match, expiry, dedup LRU, per-peer rate limit) runs. |

What this runbook does NOT do:

- Does not generate any key automatically. Every command is run by
  the operator on their own machine.
- Does not handle the private key. The runbook produces 1 `.pem`
  file encrypted with AES-256 and 1 hex pubkey + 1 SHA-256
  fingerprint. Only the pubkey + fingerprint are ever paste-back
  material.
- Does not push, merge, tag, or deploy anything.

## Verified preconditions (already confirmed)

The following were verified at runbook commit time and do not need
to be re-checked unless the source tree changes:

| Check | Status |
|---|---|
| `scripts/beacon-keygen.sh` uses AES-256 + `/dev/shm` + `shred` | ✓ |
| `src/beacon.cpp:29` `BEACON_PUBKEY_HEX` is placeholder | ✓ |
| `src/beacon.cpp:47-65` 5 II-B placeholders intact | ✓ |
| `include/sost/params.h:857` `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT = INT64_MAX` | ✓ |
| `sost-core` library builds clean with placeholders | ✓ |
| Beacon test group passes (II-A + II-B + III + scaffold) | ✓ 4/4 |

If anything below the line changes — for example, the build stops
compiling, or the Beacon tests start failing — STOP and report.
Do not generate the key.

## Quick sanity checks on the operator machine (≤ 1 minute)

Run these on WSL (or any Linux box) before starting the keygen
session:

```bash
# OpenSSL is installed and modern enough
openssl version
# expected: OpenSSL 3.x or higher (1.1.x also works)

# The keygen script is the AES-256 version
grep -c "aes256" scripts/beacon-keygen.sh
# expected: 1 or more

# /dev/shm exists and is writable (the script aborts otherwise)
test -d /dev/shm && test -w /dev/shm && echo OK
# expected: OK
```

If any check fails, fix it before continuing.

## Pre-flight checklist (machine hygiene)

Before generating the II-A key on the operator machine:

- [ ] Close every application not needed for keygen (browsers,
      IDEs, code agents, chat clients, screen recorders).
- [ ] Decide ONE strong passphrase for the II-A key:
      - ≥ 20 characters, ideally a 6-8 word diceware phrase
      - written to a password manager **and** a paper backup
      - stored physically separate from where the .pem will live
- [ ] Prepare 2 encrypted USB sticks:
      - 1 USB stick for the live II-A private key
      - 1 spare USB stick for the second backup (different physical
        location)
      - Both encrypted with BitLocker / VeraCrypt / LUKS
- [ ] Disconnect the network:
      - WiFi OFF
      - Ethernet cable UNPLUGGED (if applicable)
      - Verify with `ping -c 1 8.8.8.8` → should fail
- [ ] Open a fresh terminal in WSL (no shared history with the agent).

## Keygen — 1 invocation

All commands run inside WSL on the operator machine.

```bash
# Create a working directory in your home, NOT inside the repo
mkdir -p ~/sost-beacon-keys-v13
chmod 700 ~/sost-beacon-keys-v13
cd ~/sost-beacon-keys-v13

# Set the path to the keygen script (adjust to your local repo path)
KEYGEN=~/SOST/sostcore/sost-core/scripts/beacon-keygen.sh

# Verify the script is executable
ls -la "$KEYGEN"
# expected: -rwxr-xr-x ...

# Generate the II-A keypair (the ONLY key for this session)
"$KEYGEN" ./beacon-iia-priv.pem ./beacon-iia-pub.pem
```

Output you should see (in order):

```
Generating secp256k1 keypair. You will be prompted for a passphrase
THREE times: (1) set, (2) confirm, (3) read to derive public key.
...
read EC key
writing EC key
Enter PEM pass phrase:                # ← prompt 1: type passphrase
Verifying - Enter PEM pass phrase:    # ← prompt 2: re-type
read EC key
Enter PEM pass phrase:                # ← prompt 3: re-type once more

Beacon keypair generated:
  private key : ./beacon-iia-priv.pem  (mode 600, AES-256 ENCRYPTED — keep SECRET)
  public  key : ./beacon-iia-pub.pem   (commit this to repo)

Public key fingerprint (sha256 of uncompressed pubkey hex):
  <64 hex chars>                      # ← COPY THIS

Uncompressed public key (hex, 65 bytes — embed in src/beacon.cpp
as BEACON_PUBKEY_HEX or as one entry of BEACON_THRESHOLD_PUBKEYS):
  04<128 hex chars>                   # ← COPY THIS
```

**Write down on paper (NOT in any file):**

```
II-A
  fingerprint: <64 hex chars>
  pubkey_hex:  04<128 hex chars>
```

Verify the .pem is actually encrypted:

```bash
grep -c "ENCRYPTED\|Proc-Type: 4,ENCRYPTED" ./beacon-iia-priv.pem
# expected: ≥ 1
```

If 0, the .pem is NOT encrypted — STOP and regenerate.

## Move the private key to encrypted USB(s) and wipe locally

```bash
# Mount your primary encrypted USB at /mnt/usb-a (adjust to your mountpoint)
cp ~/sost-beacon-keys-v13/beacon-iia-priv.pem /mnt/usb-a/

# Mount your backup encrypted USB at /mnt/usb-backup
cp ~/sost-beacon-keys-v13/beacon-iia-priv.pem /mnt/usb-backup/

# Verify the copies exist
ls -la /mnt/usb-a /mnt/usb-backup

# Wipe the local copy of the private key
shred -u ~/sost-beacon-keys-v13/beacon-iia-priv.pem

# The public key can stay on disk — it is public.
ls ~/sost-beacon-keys-v13
# expected: only beacon-iia-pub.pem
```

Unmount + physically disconnect the USB sticks. Store them in two
different physical locations.

## Reconnect the network

Only after the .pem is on both encrypted USB sticks and wiped
locally:

```bash
# Reconnect WiFi or plug the cable back in
ping -c 1 8.8.8.8
# expected: success
```

## Paste-back format — exactly what to send to the install agent

When you return to the assistant chat, paste **only** the block
below. Replace each `<placeholder>` with the actual hex from the
paper (no quotes, no backticks, no extra whitespace).

```
=== BEACON V13 OPERATOR PUBLIC KEY (II-A) — bootstrap custody ===

II-A
  pubkey_hex:  04<128 hex chars>
  fingerprint: <64 hex chars>

=== END ===
```

**Hard rules for the paste-back:**

- `pubkey_hex` is exactly **130 hex characters** (the literal prefix
  `04` + 128 hex chars).
- `fingerprint` is exactly **64 hex characters** (SHA-256).
- **NEVER paste**:
  - the content of any `.pem` file
  - the passphrase
  - any output from `openssl ec -in <file> -text` that includes the
    `priv:` block

## What the install commit will do (when you paste back)

1. Substitute the placeholder at `src/beacon.cpp:29`
   (`BEACON_PUBKEY_HEX`) with the real II-A pubkey, preserving the
   same `"04"` + 64 + 64 chunk layout.
2. Verify the substituted pubkey: 130 chars, starts with `04`.
3. Recompute SHA-256 of the pubkey on the install side and compare
   to the fingerprint you pasted. Mismatch → install aborts.
4. Update the comment next to the pubkey from `// placeholder,
   fail-closed` to `// V13 operator II-A key (single-sig advisory
   path) — fingerprint <sha256>`.
5. The 5 II-B placeholders at `src/beacon.cpp:48-65` are **left
   untouched** — they remain syntactically valid fail-closed points
   while II-B sentinel keeps that path dormant.
6. `docs/BEACON_CUSTODY_STATUS.md` is updated with the II-A
   fingerprint under the active section. The II-B section continues
   to say "5 II-B keys not yet generated, sentinel `INT64_MAX`".
7. Run the Beacon test suite + Trinity.
8. Commit as `beacon: install V13 operator II-A public key`.

No push, no merge — the operator does the release ceremony manually.

## Future: when II-B is to be activated (not part of this session)

If at some point in the future you have identified 5 independent
custodians and want to activate the 3-of-5 threshold path, the
procedure is parallel to the II-A flow:

1. Generate 5 II-B keypairs offline (5 separate keypairs, 5
   distinct passphrases, distributed to 5 custodians on encrypted
   USB sticks).
2. Paste back the 5 pubkeys + 5 fingerprints in the same format
   used for II-A (one block per key, labelled `II-B key 0` through
   `II-B key 4`).
3. The install agent substitutes the 5 placeholders at
   `src/beacon.cpp:48-65` with the real pubkeys.
4. In a follow-up commit, change `include/sost/params.h:857`:
   ```diff
   - inline constexpr int64_t BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT = INT64_MAX;
   + inline constexpr int64_t BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT = <future_height>;
   ```
5. Rebuild, redeploy, announce in a II-A signed advisory notice.

**No fork is required**, because Beacon is advisory-only and never
affects consensus, block validation, or canonical-chain decisions.
The activation is purely a code change + rebuild.

## Disaster recovery

| Scenario | Action |
|---|---|
| You lost the passphrase | The `.pem` is a brick. Regenerate the II-A key (one new keygen invocation), distribute the new pubkey + fingerprint, update `BEACON_CUSTODY_STATUS.md`. The legacy single-sig channel is rotated. |
| You lost the `.pem` file (both USBs destroyed) | Same as above — regenerate. |
| You lost the paper backup of pubkey + fingerprint | The pubkey can be re-derived from the `.pem` (you still need the passphrase). The fingerprint can be re-derived from the pubkey. Use `openssl ec -in <file> -pubout` + `awk` + `sha256sum`. |
| You suspect the `.pem` was exposed (USB lost in transit) | Treat the II-A key as compromised. Regenerate, distribute new pubkey, publish a revocation notice using the new key. |
| You accidentally pasted the .pem content into chat | The key is compromised. Regenerate immediately. The passphrase is not enough — a determined attacker with the encrypted .pem and time can attempt offline passphrase cracking. |

## Hard rules to repeat to yourself

- The II-A private key NEVER touches: the repo, GitHub, any chat,
  any email, any unencrypted disk that is not RAM tmpfs.
- The passphrase NEVER touches: any file on the operator machine,
  any chat, any email.
- Paste-back: pubkey + fingerprint only. 2 lines of hex.
- The first time you generate the key is the only time the
  unencrypted private key ever exists on the machine, and it
  exists only in `/dev/shm` (RAM tmpfs). The script wipes it on
  exit.
- II-B placeholders are left untouched. They are dormant by sentinel.
  Do NOT regenerate or install them in this session.
