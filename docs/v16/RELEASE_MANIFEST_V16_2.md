# SOST V16.2.0 — Release Manifest

**V16.2.0 is not a fork.** It activates nothing, changes no consensus rule and
moves no height. V16.1.0 and V16.2.0 nodes follow the same chain, accept each
other's blocks and compute the same DTD draws. The V16 activation at **#30,000**
and the first DTD Jackpot V2 at **#30,186** are unchanged and still owner-locked.

What this release is about: **no credential this protocol asks an operator to
handle needs to sit in `argv` or on a screen any more.**

| | |
|---|---|
| Version | `v16.2.0` |
| Tag | `v16.2.0` |
| Final commit | `8f6b9ddf4df857d1cfb9ef8b6aeec566be93a14e` |
| Previous release | `v16.1.0` (`25915c74…`) — binaries kept, see rollback |
| Consensus | **unchanged from V16.1.0** (measured, not asserted) |
| Activation height | 30,000 (unchanged) |
| First V2 jackpot | 30,186 (unchanged) |

## v16.2.3 — the last hand-rolled parsers

`v16.2.3` ships **only a new `sost-cli`** for the third time; `sost-node` and
`sost-miner` keep the same hashes they had in v16.2.0. It converts the two
paths left over from v16.2.1:

* **`cancel-tx` / `bump-fee`** rebuilt the original transaction by scanning the
  raw response. `"fee"` was searched from offset 0 (any earlier field of that
  name won), a vin was delimited by the first `}` (one nested object truncated
  the list — and every dropped vin is a `prev_value` missing from `total_in`,
  which is what `total_in - new_fee` returns to the wallet), and fields were
  read with `std::stoll` on the raw C string, which throws and aborts on a null
  or quoted value.
* **`capsule-decrypt`** counted `payload_hex` matches in order, guessing which
  vout each belonged to, and read a truncated reply as "no capsule here".

The CLI now has **zero substring-scanned RPC answers**.
`tests/audit_v162_rbf.sh` covers it with 10 assertions, including the
nested-object vin that used to truncate the list.

```
b253e4a9c352ea4b8557eec78d57e1c7619ab267af228c3e8f24bf8d7b69b897  sost-node   (unchanged since v16.2.0)
2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  sost-miner  (unchanged since v16.2.0)
489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  sost-cli    (v16.2.3)
```

## v16.2.1 — the CLI follow-up

`v16.2.1` (commit `84f93015`) ships **only a new `sost-cli`**. `sost-node` and
`sost-miner` are **byte-identical** to v16.2.0, verified by hash, so a node or a
miner already running v16.2.0 does not restart for this release and loses no
mining time. Consensus is unchanged for the third release running.

What it fixes, all of it in the CLI's RPC layer:

* `rpc_call` could not read a large answer. It stopped as soon as a buffer
  happened to end with `}` whenever it did not find a literal
  `Content-Length: ` header — and header names are case-insensitive, and the
  public RPC gateway answers with `Transfer-Encoding: chunked` and no
  Content-Length at all. Every UTXO object ends in `}`, so a large
  `getaddressutxos` was cut at a chunk boundary and surfaced as `bad_json`.
  Fixed: case-insensitive header, chunked decoding, read-to-close, and a socket
  timeout bounding all three.
* `send` bypassed `rpc_call` entirely — its own socket, one `read()` into a
  4 KB buffer, and "accepted" decided by finding `"result":"` anywhere in the
  reply. That decision marks the wallet's coins spent.
* Balances, UTXO import, broadcast, sendmany, bump-fee, the mempool check and
  the chain height were all parsed by substring search. `query_chain_height`
  called `std::stoll` on whatever followed `"blocks":` — which throws and
  aborts on a non-numeric body, and that height decides coinbase maturity.

All of them now go through `sost::json`: **23 call sites, zero remaining
`"result"` substring searches**. A broadcast counts as accepted only when the
JSON-RPC result IS a string txid. When an answer cannot be read, the wallet
leaves the inputs unspent and says "not confirmed" rather than "rejected",
pointing the operator at `getrawmempool` before they build another transaction.
The CLI also gained `--rpc-pass-file` / `--rpc-pass-fd`.

Hashes: `docs/v16/SHA256SUMS`. The v16.2.0 list is kept as
`SHA256SUMS_V16_2_0`, and v16.1.0 as `SHA256SUMS_V16_1`.

## Official binary hashes (v16.2.0)

```
b253e4a9c352ea4b8557eec78d57e1c7619ab267af228c3e8f24bf8d7b69b897  sost-node
2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  sost-miner
212e37d8f925afd4d4e1f9971a86bd49120be2978e09ec1cf77b713ebc0812c5  sost-cli
```

`docs/v16/SHA256SUMS` carries the same list with its verification notes.
`docs/v16/SHA256SUMS_V16_1` keeps the V16.1.0 list, because that is what a
rollback binary verifies against.

## Official build environment

Unchanged from V16.1.0:

| | |
|---|---|
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 5.15.167.4-microsoft-standard-WSL2 |
| Arch | x86_64 |
| Compiler | g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0 |
| Linker | GNU ld (GNU Binutils for Ubuntu) 2.38 |
| CMake | 3.22.1 |
| libc | GNU libc 2.35 (Ubuntu GLIBC 2.35-0ubuntu3.15) |

```bash
cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF \
      -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-miner sost-cli -j"$(nproc)"
```

```
PATH-INDEPENDENT BUILD        = YES   (measured: rel-v162-a and /tmp/rel-v162-b
                                       produced byte-identical binaries)
CROSS-MACHINE REPRODUCIBILITY = NOT PROVEN
```

One practical note learned in this release: the **build directory name** is part
of what gets embedded. `-ffile-prefix-map` normalises the *source* path, so the
same commit reproduces from any source directory, but building into `build-v162`
instead of `build` yields different bytes. Use `-B build` to reproduce the
published hashes.

## What changed

Nothing in the consensus path. In the operator path:

* **`src/secret_input.cpp`** — one reader behind every secret: terminal with echo
  off (and a refusal if echo cannot be disabled), an open descriptor, or a
  mode-600 file owned by the caller. A group- or world-readable file is refused
  rather than read with a warning; a multi-line file is refused because neither
  reading the first line nor keeping the newline can be what the operator meant.
  No error message ever echoes what it rejected.
* **miner** — `--rpc-pass-fd`, `--rpc-pass-file`, `--wallet-passphrase-file`.
  `--rpc-pass` still works and says out loud that it is visible in `ps`. The
  sources are mutually exclusive and resolved before anything else runs. An HTTP
  401 on submit now says what it means instead of looking like a rejected block.
* **node** — `--node-key-file` (heartbeat key) and `--rpc-pass-file`, so a
  systemd unit can name a path instead of expanding a password into `ExecStart`.
* **cli** — `createnodebind` / `nodeheartbeat` take `--node-key-file` or
  `--node-key-fd`; `wallet-export` / `wallet-import` prompt with echo off and
  accept `--passphrase-fd`.
* Encrypted (v2) wallets are fully supported end to end, and **v1 wallets keep
  working with no conversion and no deadline**.
* Earlier in this cycle, also shipped here: a hardened strict JSON reader,
  `listunspent` that queries the chain instead of a stale cache, and
  `sost-cli sweep-plan` — a planner only; it signs and broadcasts nothing.

## Validation — what was actually run

| check | result |
|---|---|
| unit suite (release worktree, release flags) | **119/119** |
| devnet E2E, 8 harnesses (V16 jackpot V2 paid / rollover / autohb / V15 payout, reorg, mempool, rollover) | **89 assertions, 0 failures** |
| `tests/run_v162_equivalence.sh` — v16.1.0 node vs v16.2.0 node on one devnet | both accept each other's blocks; **61/61 heights hash identically**; lottery audit identical at all 60 |
| `tests/run_v162_historical_replay.sh` — **the real production chain**, offline, on the exact release binary | both releases load to **height 27,544**, no rejections, **959 sampled heights identical**, tip block identical, **959 lottery audits identical** |
| `tests/test_v16_mainnet_calendar.cpp` | **28/28** — the published calendar pinned to the compiled constants |
| `tests/test_secret_input.cpp` | **19/19** |
| encrypted wallet, end to end | mines, and the **mining identity and payout address are unchanged** by encryption |
| RPC credentials, end to end | node and miner authenticate with the password in **neither process's `argv`**; a wrong password stops submission and leaves the chain where it was |
| node key, end to end | argv hex, `--node-key-file` and `--node-key-fd` produce a **byte-identical** NODE_BIND (176 B) and heartbeat (175 B) |

## Rollback

Nothing in V16.2.0 changes the on-disk chain format, so a rollback is the old
binary and nothing else. The V16.1.0 binaries are preserved in two independent
worktrees and verified against `docs/v16/SHA256SUMS_V16_1`:

```bash
# node (VPS)
systemctl stop sost-node
install -m 0755 /opt/sost/build/sost-node.v161.<timestamp> /opt/sost/build/sost-node
systemctl start sost-node
PID=$(systemctl show sost-node -p MainPID --value)
sha256sum "$(readlink -f /proc/$PID/exe)"   # must be b94c2650a93bfad…

# miner (WSL)
install -m 0755 build/sost-miner.v161.<timestamp> build/sost-miner
# then relaunch with the same command line as always
```

**One caveat, and only one:** a wallet encrypted with V16.2.0 (`version: 2`)
cannot be read by a V16.1.0 binary. If you encrypted a wallet and then roll back,
point the old binary at the v1 file you kept. This is why the guide says to keep
the v1 file until the encrypted one has mined a block.

There is no chain surgery, no reindex and no state migration in either direction.

## Upgrade window

**After #29,900 and before #30,000** — node and miner, both. Technically
V16.2.0 is consensus-identical to V16.1.0 and could be installed at any height;
the window exists for coordination, so the whole network crosses the activation
running the same code. Get the binaries and check their hashes *before* the
window opens; inside it, only stop, install, restart.

The deadline itself belongs to the V15 → V16 change: **any node still on V15
after #30,000 diverges.** See `docs/v16/QUICK_UPGRADE_5MIN.md` for that path and
`docs/v16/UPGRADE_V16_2.md` for this release.
