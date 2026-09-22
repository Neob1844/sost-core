# SOST V16.2.0 — upgrade guide for miners and node operators

**Short version.** If you are already running **V16.1.0**, this upgrade changes
**no consensus rule** — it is about keeping your passwords and keys out of
places where other local accounts can read them. If you are still on **V15**,
this is the **mandatory** upgrade and it must be in place **before block
#30,000**.

Your coins, your keys, your wallet file and your payout address are
**untouched** by this upgrade. There is nothing to convert, nothing to move and
nothing to re-register. Encrypting your wallet is **optional** and always will
be.

**Update window: after block #29,900 and before block #30,000** — on your node
**and** your miner. V16.2.0 is consensus-identical to V16.1.0, so the window is
coordination, not a technical constraint: the point is that the whole network
crosses the activation running the same code. Download, build and verify the
hashes *before* the window opens, so inside it you only stop, install, restart.

```text
BEFORE #29,900     get the binaries, verify SHA256 — do NOT switch yet
#29,900 -> #30,000 THE WINDOW (~16-17 h): stop, install, restart. Node AND miner.
AT #30,000         V16 activates by itself — you do nothing
AFTER #30,000      optional: NODE_BIND, if you want the DTD Jackpot

V15            -> MUST upgrade before #30,000 (a V15 node diverges after it)
V16.0 / V16.1  -> same consensus as V16.2.0; upgrade in the window anyway, so
                  everyone is on one build when the rules change
```

---

## 0 · Get the binaries (no compiler needed)

The official binaries are published with the release, so compiling is optional:

```bash
mkdir -p ~/sost-v162 && cd ~/sost-v162
for f in sost-node sost-miner sost-cli SHA256SUMS; do
  curl -fsSL -O "https://github.com/Neob1844/sost-core/releases/download/v16.2.0/$f"
done
sha256sum -c SHA256SUMS      # must print: sost-node: OK / sost-miner: OK / sost-cli: OK
chmod +x sost-node sost-miner sost-cli
```

If `sha256sum -c` does not print OK for all three, **stop and do not run them**.
They are built for Linux x86_64 (Ubuntu 22.04 toolchain, glibc 2.35). If your
system cannot run them, build from source as described below — the hashes will
differ on a different toolchain, and that alone is not evidence of tampering.

The previous release is downloadable too, at
`https://github.com/Neob1844/sost-core/releases/tag/v16.1.0`, so a rollback does
not depend on you having kept a copy.

---

## 1 · What actually changed

| | V16.1.0 | V16.2.0 |
|---|---|---|
| consensus rules | V16 at #30,000 | **identical — proven, see below** |
| wallet format | v1 plaintext | v1 **and** v2 encrypted, your choice |
| RPC password | `--rpc-pass <p>` only | also `--rpc-pass-fd` / `--rpc-pass-file` |
| node key | `--node-key <hex>` | also `--node-key-file` |
| `wallet-export` | passphrase echoed on screen | echo off, or `--passphrase-fd` |
| a wrong RPC password | looked like a rejected block | says so, in plain words |

"Identical" is not an assertion here. `tests/run_v162_equivalence.sh` runs a
V16.1.0 node and a V16.2.0 node on the same devnet: each accepts every block the
other produces, all 61 heights hash the same on both, and the DTD lottery audit
matches at every height. The V16 activation calendar itself
(`tests/test_v16_mainnet_calendar.cpp`) is pinned by 28 assertions against the
compiled constants — #29,898 last V15 jackpot, #30,000 activation, #30,186
first V2 jackpot, #31,338 the permanent 3-of-4 heartbeat rule.

---

## 2 · Upgrade — the whole thing

Same command you already use, with a new binary. Nothing about your setup
changes.

Build in a **worktree from the tag**, so your working tree and your running
binaries are untouched — and name the build directory `build`, because the
published hashes only reproduce from a directory with that name.

```bash
# 1. get the release, in its own worktree
cd /path/to/sost-core
git fetch --all --tags --prune
git worktree add ../sost-v162 v16.2.0
cd ../sost-v162
git describe --tags --exact-match          # must print v16.2.0

# 2. build
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF \
      -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"

# 3. verify BEFORE you install anything
for b in sost-node sost-miner sost-cli; do
  mine=$(sha256sum "build/$b" | awk '{print $1}')
  published=$(awk -v b="$b" '$2 == b {print $1}' docs/v16/SHA256SUMS)
  [ "$mine" = "$published" ] && echo "OK       $b" || echo "DIFFERS  $b  ($mine)"
done
```

**Why the directory name matters.** The source path is normalised out of the
binary (`-ffile-prefix-map`), which is why the same commit reproduces from any
source directory — that is measured, twice, for this release. The *build*
directory name is not normalised, so `-B build-v162` yields different bytes
from the same source. Use `-B build`.

**If a hash does not match, stop.** A mismatch usually means a different
compiler or flags, not a tampered file — but you cannot tell the two apart from
the outside, so treat it as a reason to ask before running the binary.

```bash
# 4. install, keeping the old binaries (from your normal tree)
cd /path/to/sost-core
cp build/sost-miner "build/sost-miner.v161.$(date -u +%Y%m%d-%H%M%S)"
cp build/sost-cli   "build/sost-cli.v161.$(date -u +%Y%m%d-%H%M%S)"
install -m 0755 ../sost-v162/build/sost-miner build/sost-miner
install -m 0755 ../sost-v162/build/sost-cli   build/sost-cli

# 5. restart the miner with EXACTLY the flags you used before
```

The node side is the same three steps (`sost-node`), then
`systemctl restart sost-node`. Verify the binary that is **running**, not the
one on disk:

```bash
PID=$(systemctl show sost-node -p MainPID --value)
sha256sum "$(readlink -f /proc/$PID/exe)"
```

---

## 3 · The RPC password — read this once

**The RPC password is the password of the node you connect to.** It is not a
SOST-wide password, there is no network-wide account, and nobody can give you
"the SOST RPC password". If you run your own node, *you* choose it. If you mine
against someone else's node, they tell you theirs.

A node without `--rpc-noauth` requires it for anything that changes state —
**submitting blocks included**. Read-only queries (`getblockcount`,
`getblockhash`, …) are deliberately open, which is why a wrong password lets a
miner start and follow the chain, and only fails when it finally submits. From
V16.2.0 the miner says exactly that instead of printing a generic rejection.

### Set it up locally, without putting it in a command line

```bash
# on the machine that runs the NODE
install -d -m 0700 /etc/sost
umask 077
printf '%s\n' 'pon-aqui-tu-contrasena-larga' > /etc/sost/rpc.pass
chmod 600 /etc/sost/rpc.pass
```

The value above is a placeholder — use a long random string of your own, e.g.
`openssl rand -base64 30`. Then:

```bash
# node (systemd ExecStart, or your own launcher)
sost-node --profile mainnet --genesis genesis_block.json --chain chain.json \
          --rpc-user mi-usuario --rpc-pass-file /etc/sost/rpc.pass --p2p-enc on

# miner, same machine
sost-miner --wallet ~/sost-keys/mi-cartera.json \
           --mining-key-label "mi-etiqueta" \
           --genesis genesis_block.json \
           --rpc 127.0.0.1:18232 --rpc-user mi-usuario \
           --rpc-pass-file /etc/sost/rpc.pass \
           --blocks 999999 --profile mainnet --threads 8
```

or, if the password lives in a keyring / password manager and you never want it
on disk at all:

```bash
sost-miner ... --rpc-pass-fd 3 3< <(mi-gestor-de-claves leer sost/rpc)
```

Rules the binaries enforce for you:

- a secret file must be **mode 600 and owned by you** — a file group- or
  world-readable is refused, not read with a warning;
- it must hold the secret on **one line and nothing else**;
- `--rpc-pass`, `--rpc-pass-fd` and `--rpc-pass-file` are **mutually
  exclusive**, so an old `--rpc-pass` left in a script cannot quietly win;
- `--rpc-pass` still works and now warns that it is visible in `ps`.

---

## 4 · Encrypting your wallet — optional

A v1 (plaintext) wallet keeps working exactly as before, with no conversion and
no deadline. The miner loads it, warns once that its private keys are readable
by anything that can read the file, and mines.

If you do want it encrypted (scrypt N=32768 + AES-256-GCM):

```bash
sost-cli --wallet ~/sost-keys/mi-cartera.json wallet-export \
         --encrypted --output ~/sost-keys/mi-cartera.v2.json
# passphrase typed twice, with the terminal NOT echoing it

sost-miner --wallet ~/sost-keys/mi-cartera.v2.json \
           --mining-key-label "mi-etiqueta" --wallet-passphrase-fd 3 3< /ruta/al/fichero \
           ... # the rest exactly as before
```

**Keep the v1 file until you have proven the v2 one mines a block.** The
passphrase cannot be recovered: lose it and the keys in that file are gone.
`wallet-import --encrypted --input <file>` goes back the other way.

Your **mining identity and payout address do not change** when you encrypt: it
is the same keys in a different container. SbPoW still signs with the key
selected by `--mining-key-label`, and jackpot eligibility and any NODE_BIND you
already published stay valid.

---

## 5 · If you bind a node for the DTD Jackpot

Only relevant after #30,000, and only if you want to enter the jackpot draw. The
node private key can now stay out of `ps`:

```bash
umask 077
openssl rand -hex 32 > ~/.sost/node.key       # SAVE THIS — it is your node identity
chmod 600 ~/.sost/node.key

sost-cli --wallet ~/sost-keys/mi-cartera.json \
         --mining-key-label "mi-etiqueta" \
         createnodebind 1 --node-key-file ~/.sost/node.key
# -> raw tx hex; broadcast it with sendrawtransaction

# and on the node, so it heartbeats by itself:
sost-node ... --node-key-file ~/.sost/node.key
```

The old positional form (`createnodebind 1 <hex>`) still works and warns. Both
forms produce a byte-identical transaction.

---

## 6 · Rolling back

Nothing in V16.2.0 changes the on-disk chain format, so a rollback is just the
old binary:

```bash
systemctl stop sost-node
install -m 0755 build/sost-node.v161.<timestamp> build/sost-node
systemctl start sost-node
```

For the miner, stop it and start it again with the backup binary. Your wallet
file is not touched by either version — **except** that a v2 (encrypted) wallet
cannot be read by a pre-V16.2 binary. If you encrypted your wallet and then roll
back, point the old binary at the v1 file you kept.

---

## 7 · Quick checklist

- [ ] binaries built and hashes compared against `docs/v16/SHA256SUMS`
- [ ] old binaries kept, with a timestamp in the name
- [ ] node restarted; `/proc/<pid>/exe` hashes to the published value
- [ ] miner restarted with the same wallet, label and address as before
- [ ] `getblockcount` advancing and matching the network
- [ ] a block submitted and accepted (no `RPC AUTHENTICATION REJECTED`)
- [ ] if you use one: the secret file is `600`, single-line, owned by you
