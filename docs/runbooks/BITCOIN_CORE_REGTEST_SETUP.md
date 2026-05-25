# Bitcoin Core install (verified) — for the SOST regtest harness

This runbook explains how to install Bitcoin Core officially-signed
binaries on a SOST dev machine so that
`tests/harnesses/sost_btc_regtest.py` can run its full bitcoind-
dependent test suite instead of SKIPping.

It is **non-automated on purpose**. Bitcoin Core is the most security-
critical binary on a SOST dev box, and a silent install via a script
nobody read is the failure mode this runbook exists to prevent. Every
step that touches the network is one command you type after reading
the comment that explains it.

The harness itself NEVER auto-downloads bitcoin-core. If the binaries
are not on PATH, the harness SKIPs the bitcoind-dependent tests
cleanly and points back to this document.

## What the SOST harness needs

- `bitcoind`     >= 0.21 (segwit-v0 P2WSH + BIP-141 / BIP-143 RPC support).
  Newer is fine. The harness does not depend on any post-0.21
  taproot feature.
- `bitcoin-cli`  matching `bitcoind`'s major version.
- Both binaries on `$PATH` for the user that runs `pytest`.

The harness never starts a node on `mainnet`, `testnet`, or `signet`.
It only spawns `-regtest` in a private temporary datadir under
`/tmp`. The fixture explicitly sets `listen=0 dnsseed=0 upnp=0
natpmp=0 discover=0` so the spawned node has zero outbound network
surface even on a misconfigured host.

## What this runbook explicitly does NOT do

- **No `apt-get install bitcoind`** without checking the package
  source first. Ubuntu/Debian repositories sometimes do not carry the
  upstream Bitcoin Core package; the version they do carry can be
  several years stale.

- **No `snap install bitcoin-core`**. Snap distribution of Bitcoin
  Core is not maintained by the Core project.

- **No "trust this random PPA"** workflow. Third-party PPAs have been
  the vector for prior Bitcoin user compromises. Do not enable
  unknown PPAs on a dev box that also holds SOST keys.

- **No "curl | bash"** anywhere. If a step needs network access, it
  downloads a file and then verifies that file before executing it.

## Recommended source: bitcoincore.org tarball + Guix signatures

This is the path the Bitcoin Core project itself recommends for
operators who want reproducible-build verifiable binaries:

```
https://bitcoincore.org/en/download/
```

The release artefacts that you will download are:

```
bitcoin-<VERSION>-x86_64-linux-gnu.tar.gz       # binaries
SHA256SUMS                                       # checksums file
SHA256SUMS.asc                                   # detached GPG signature(s) over SHA256SUMS
```

`VERSION` is a string like `27.1` or `28.0`; pick the most recent
release the project marks as stable on the download page.

## Step-by-step verification

All commands below assume you are running them yourself in a terminal
and reading each output before typing the next. `$VERSION` is the
release number you chose above; `$WORKDIR` is a scratch directory you
will clean up afterwards.

### 1. Pick a release and a scratch directory

```bash
VERSION="27.1"     # or whatever the current stable release is
WORKDIR="$HOME/bitcoin-verify-${VERSION}"
mkdir -p "$WORKDIR"
cd "$WORKDIR"
```

### 2. Download tarball, checksums, and signatures

Only after reading the URLs out loud to yourself (typo squatting is a
real attack vector on this domain). Use `curl --proto '=https'
--tlsv1.2 --fail` so a redirect to a non-TLS endpoint cannot silently
substitute a payload.

```bash
BASE="https://bitcoincore.org/bin/bitcoin-core-${VERSION}"

curl --proto '=https' --tlsv1.2 --fail -LO \
    "${BASE}/bitcoin-${VERSION}-x86_64-linux-gnu.tar.gz"

curl --proto '=https' --tlsv1.2 --fail -LO \
    "${BASE}/SHA256SUMS"

curl --proto '=https' --tlsv1.2 --fail -LO \
    "${BASE}/SHA256SUMS.asc"
```

### 3. Verify the SHA256 checksum of the tarball

```bash
sha256sum --ignore-missing --check SHA256SUMS
```

Expected output line:

```
bitcoin-<VERSION>-x86_64-linux-gnu.tar.gz: OK
```

If you see `FAILED` or `WARNING: 1 listed file could not be read`,
**STOP**. Do not proceed. Re-download, or pick a different mirror,
and ask for a second opinion on the channel.

### 4. Verify the GPG signature(s) over SHA256SUMS

Bitcoin Core release shipments are signed by multiple Guix
contributors. Their public keys live in the project's `guix.sigs`
repository:

```
https://github.com/bitcoin-core/guix.sigs
```

There is a maintained KEYS file:

```
https://github.com/bitcoin/bitcoin/blob/master/contrib/builder-keys/keys.txt
```

Import the keys into your local GPG keyring:

```bash
# Either fetch the KEYS file and import every key listed:
curl --proto '=https' --tlsv1.2 --fail -L \
    https://raw.githubusercontent.com/bitcoin/bitcoin/master/contrib/builder-keys/keys.txt \
    -o keys.txt
# (open keys.txt, read it, then:)
while read -r fpr name; do
    [ -z "$fpr" ] && continue
    case "$fpr" in \#*) continue ;; esac
    gpg --keyserver hkps://keys.openpgp.org --recv-keys "$fpr" || true
done < keys.txt
```

Then verify:

```bash
gpg --verify SHA256SUMS.asc SHA256SUMS
```

Expected output: at least one `Good signature from "<builder name>"`
line for a key whose fingerprint you can match against the
`keys.txt` you read above. Multiple Good signatures are better.

If you only see `Can't check signature: No public key`, your local
keyring does not have the corresponding builder key — go back to the
`recv-keys` step and import it before proceeding.

### 5. Extract and install LOCALLY (no system overwrite)

```bash
tar -xzf "bitcoin-${VERSION}-x86_64-linux-gnu.tar.gz"
# Install into ~/.local/bin so the install never overwrites a system
# package, never needs sudo, and is trivial to revert (delete two
# files).
install -m 0755 "bitcoin-${VERSION}/bin/bitcoind"     "$HOME/.local/bin/bitcoind"
install -m 0755 "bitcoin-${VERSION}/bin/bitcoin-cli"  "$HOME/.local/bin/bitcoin-cli"
```

Make sure `~/.local/bin` is on your shell's `$PATH`. If it is not,
add this line to your shell rc (`~/.bashrc` or `~/.zshrc`) once:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then `source` the rc or open a new terminal.

### 6. Confirm the installed binaries

```bash
which bitcoind     # should print ~/.local/bin/bitcoind
which bitcoin-cli  # should print ~/.local/bin/bitcoin-cli
bitcoind     --version | head -1
bitcoin-cli  --version | head -1
```

Both `--version` lines must report the `$VERSION` you verified above.

### 7. (Optional) Verify the regtest harness now lights up

```bash
cd <your sost-core checkout>
python3 -m pytest tests/harnesses/sost_btc_regtest.py -v
```

Expected (Phase C.11 surface):

```
test_bitcoind_detection_runs                              PASSED
test_conf_template_includes_safety_flags                  PASSED
test_redeem_script_python_mirrors_cpp_layout              PASSED
test_p2wsh_script_pubkey_shape                            PASSED
test_encode_script_num_minimal_invariants                 PASSED
test_regtest_node_spawns_and_responds                     PASSED
test_regtest_can_mine_blocks                              PASSED
test_regtest_wallet_has_balance                           PASSED
test_regtest_can_decode_segwit_address                    PASSED
test_decodescript_returns_bcrt1q_for_sost_htlc            PASSED
test_fund_htlc_and_locate_outpoint                        PASSED
test_testmempoolaccept_recognises_a_wallet_self_spend     PASSED
test_btc_regtest_htlc_happy_path_claim                    SKIPPED  (Phase C.12)
test_btc_regtest_htlc_happy_path_refund                   SKIPPED  (Phase C.12)
```

The two SKIPs at the end are intentional. They cover the broadcast
of a SOST-signed CLAIM/REFUND tx, which requires Phase C.12 work on
the SOST signer side (a small `tools/btc_regtest_signer` binary or
the gated CLI surface). The runbook is complete once the 12 tests
above PASS and the 2 final ones SKIP with the C.12 message.

### 8. Cleanup

Once `bitcoind --version` works, the scratch directory can be deleted:

```bash
rm -rf "$WORKDIR"
```

The harness datadir is created and deleted inside `/tmp` by the
fixture itself for every test run, so there is nothing else to clean
up.

## Safety reminders

- **Never** enable `txindex=1`, `server=1`, or `rpcallowip=...` on a
  bitcoind that you start outside this regtest harness, unless you
  understand exactly what each of those flags exposes. The harness
  configures only `server=1` and only on a kernel-allocated local
  port that is closed on teardown.

- **Never** point this `bitcoind` at a mainnet datadir. The harness
  always builds the conf file fresh in a tempdir; do not be
  "helpful" by copying a real wallet into that tempdir.

- **Never** flip `SOST_BTC_HTLC_SIGNING=ON` on the production SOST
  build recipe just because the regtest harness now lights up.
  Production builds keep the flag OFF until external cryptographic
  audit on `src/atomic_swap_btc_signing.cpp` has signed off AND the
  separate operator opt-in for `IsBtcHtlcSigningEnabled()` lands.
  Until then, every SOST mainnet binary refuses every BTC-side
  signing call regardless of how the regtest harness behaves.

- **Never** flip `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` away from
  `INT64_MAX`. That is a single-purpose, single-commit, single-
  announcement change with its own pre-deploy checklist
  (`docs/release/ATOMIC_SWAP_PRE_DEPLOY_CHECKLIST.md`). Nothing in
  the regtest harness, in this runbook, or in C.11 work touches
  that gate.
