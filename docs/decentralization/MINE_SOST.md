# MINE SOST

A simple, honest path for a brand-new miner. Follow the steps top to bottom and
you will have a node syncing, a wallet, and a miner producing blocks the network
accepts.

SOST mining uses **ConvergenceX / SbPoW Phase 2** — a memory-hard, CPU-oriented
proof of work. It is deliberately memory-hard so that there is no early ASIC or
GPU advantage: ordinary multi-core CPUs with enough RAM compete on equal terms.

> **Read this first — honesty up front.**
> This guide does **not** promise that mining SOST is profitable. It gives you the
> verifiable inputs (block reward, reward split, observed resource usage) and the
> real commands. Electricity prices, hardware, and network difficulty vary enormously,
> and there is no committed market price. **Calculate your own economics before you
> commit hardware or power.** Nobody here is telling you that you will earn money.

---

## 0. What you need

- A 64-bit Linux machine (these binaries are built and tested on Linux / WSL2).
- A multi-core CPU. More cores = more parallel nonce search.
- **RAM: see Section 4 — this is the single most important requirement.** SbPoW is
  memory-hard and will use several GB per worker.
- A stable network connection so your node can stay synced with peers.
- Patience for the initial chain sync before you start mining.

---

## 1. Download the official v30000 release

Get the three binaries — `sost-node`, `sost-miner`, `sost-cli` — plus the genesis
file, from the official release page:

**https://github.com/Neob1844/sost-core/releases/tag/v30000**

Download (example — adjust names to the exact asset names on the release page):

```bash
mkdir -p ~/sost && cd ~/sost

# the three binaries + the genesis file come from the v30000 release assets
# (download them from the release page link above into ~/sost)
```

Only use binaries from that official release tag. Do not run a binary you were sent
privately, and do not skip the verification in the next step.

---

## 2. Verify the SHA256 BEFORE you run anything

The published SHA256 of the `sost-miner` binary for v30000 is:

```
eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951
```

Verify your downloaded miner matches, byte for byte:

```bash
cd ~/sost
sha256sum sost-miner
# compare the printed hash against the one above — they MUST be identical
```

Or check it automatically:

```bash
echo "eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951  sost-miner" | sha256sum -c -
# expect:  sost-miner: OK
```

The release page also publishes a `SHA256SUMS` file covering `sost-node` and
`sost-cli` — verify those the same way:

```bash
sha256sum -c SHA256SUMS
```

**If a hash does not match, stop.** Do not run the binary. Re-download from the
official release and verify again.

Make the binaries executable:

```bash
chmod +x sost-node sost-miner sost-cli
```

---

## 3. Build from source instead (optional)

If you prefer to build rather than trust a binary, the node refuses to run on
mainnet unless it was compiled consensus-capable. The build flags are **mandatory**:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    -DSOST_ENABLE_PHASE2_SBPOW=ON \
    -DSOST_TESTNET_FORKS=OFF
cmake --build build -j"$(nproc)" sost-node sost-miner sost-cli
```

Confirm the Phase 2 verification path is in the binary:

```bash
strings build/sost-node | grep -c 'POW-SIG/v11'   # must be > 0
```

A node built with `SOST_ENABLE_PHASE2_SBPOW=OFF` will silently reject every block
and stall — it will **not** mine.

---

## 4. Real hardware requirements (RAM is the one that matters)

SbPoW / ConvergenceX is memory-hard by design. From the implementation, a block's
proof of work operates over an **8 GB working set per block**: a **4 GB dataset**
(regenerated per block) plus a **4 GB scratchpad**. The code logs this directly, e.g.
`[DATASET] regenerated ... size=4096 MB`.

What that means in practice:

- **Plan for several GB of RAM per concurrent worker.** SbPoW is memory-hard — the
  exact resident footprint depends on your build, your thread count, and how the
  dataset/scratchpad are shared between threads. **Measure it on your own hardware**
  with `top`/`htop` while the miner runs, and size your machine from what you observe,
  not from a number someone quoted you.
- Running more `--threads` than your RAM can back will push the machine into swap and
  **slow you down**, not speed you up. Watch for swap thrashing.
- A machine with only a few GB of RAM is not a good fit for SOST mining.

There is no fabricated "minimum RAM" figure here on purpose: run it, watch the real
numbers, and decide.

---

## 5. Create your RPC password (private, never on the command line)

The node and miner talk over RPC with HTTP Basic auth. Put the password in a
mode-600 file so it never appears in `ps` or your shell history:

```bash
mkdir -p ~/.sost && umask 077
openssl rand -base64 30 > ~/.sost/rpc.pass
chmod 600 ~/.sost/rpc.pass
```

Pick any username you like (used below as `myuser`).

---

## 6. Start your local node and let it sync

The miner mines against your **own local node**. Start the node first and connect it
to the official seed so it discovers peers and downloads the chain:

```bash
cd ~/sost
./sost-node \
  --genesis genesis_block.json \
  --chain chain.json \
  --connect seed.sostcore.com:19333 \
  --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass \
  --profile mainnet \
  --p2p-enc on
```

Defaults you should know:

- **P2P port: 19333** (`--port` to change)
- **RPC port: 18232** (`--rpc-port` to change) — bound to `127.0.0.1` only unless you
  explicitly pass `--rpc-public`. Leave it local.
- `--connect` can be given more than once to add additional peers.

**Wait for the node to finish syncing to the network tip before you start mining.**
Mining on a node that is still catching up just produces blocks that lose the race.
Check progress with:

```bash
./sost-cli --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass getblockcount
```

Compare the number against the height shown on the explorer (Section 10).

---

## 7. Create a wallet and a mining key

Your mining reward address is derived from the **signing key** that signs each block,
so you need a wallet with a labelled key, and you point the miner at that label.

```bash
cd ~/sost

# create the wallet
./sost-cli --wallet wallet.json newwallet

# create a key with a label you choose — here "miner"
./sost-cli --wallet wallet.json getnewaddress "miner"

# protect the wallet file
chmod 600 wallet.json
```

`getnewaddress "miner"` prints the address and stores a key labelled `miner`. You
will pass that same label to the miner as `--mining-key-label`.

> Since SbPoW went live (block #7,100) the payout address is bound to the signing
> key. Use `--wallet` + `--mining-key-label` — **not** `--address` alone, which is the
> obsolete pre-SbPoW path and will not give you valid Phase 2 blocks or jackpot
> eligibility.

---

## 8. Start the miner — with `--realtime` (CRITICAL)

```bash
cd ~/sost
./sost-miner \
  --wallet wallet.json \
  --mining-key-label "miner" \
  --genesis genesis_block.json \
  --rpc 127.0.0.1:18232 \
  --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass \
  --blocks 999999 \
  --threads 4 \
  --profile mainnet \
  --realtime
```

### `--realtime` is MANDATORY

> **Without `--realtime` the miner stamps every block with `prev_time + 600s`
> (simulation time). The node rejects those blocks as `timestamp too far in the
> future`, and your chain stalls. You will mine and submit and nothing will be
> accepted. ALWAYS pass `--realtime` on a real network.**

### The miner flags (from `sost-miner --help`)

| Flag | Meaning |
|------|---------|
| `--wallet <path>` | Wallet JSON holding your SbPoW signing key |
| `--mining-key-label <label>` | Which wallet key label signs your blocks (must exist in the wallet) |
| `--rpc <host:port>` | Your local node's RPC endpoint (default node RPC is `127.0.0.1:18232`) |
| `--rpc-user <u>` | RPC Basic auth user — must match the node's `--rpc-user` |
| `--rpc-pass-file <path>` | RPC pass read from a PRIVATE (mode 600) file — preferred over `--rpc-pass` |
| `--threads <n>` | Parallel nonce-search threads (default 1). Threads share one scratchpad. |
| `--realtime` | Use real wall-clock timestamps. **REQUIRED on mainnet (see above).** |
| `--profile mainnet\|testnet\|dev` | Network profile — use `mainnet` |
| `--blocks <n>` | How many blocks to mine before exiting (use a large number to keep going) |
| `--genesis <path>` | Genesis JSON |

Set `--threads` to what your **RAM** (not just your core count) can support — see
Section 4. Credentials: use `--rpc-pass-file` (or `--rpc-pass-fd`), never the plain
`--rpc-pass`, which is visible to any local user in `ps`.

The miner works by pulling a block template from your node (`getblocktemplate`),
searching for a valid SbPoW solution, signing it, and submitting it
(`submitblock`). On success you will see a line like:

```
[BLOCK 30421] <hash> nonce=... extra=... <ms>ms txs=...
  sub=... fees=... miner=... gold=... popc=...
  -> submitted to node OK (... txs)
```

`-> submitted to node OK` means your node accepted the block. `-> node REJECTED
block` means it did not — see troubleshooting.

---

## 9. The reward (and why you must do your own math)

- **Block subsidy is about 7.851 SOST per block** at the current emission stage.
- Since **block #25,000 the subsidy is split 50% to the miner / 50% to DTD**, so the
  miner's portion of a block is roughly **half** of the subsidy, plus any transaction
  fees in that block.
- **Coinbase maturity is 1,000 confirmations.** A reward you just mined cannot be
  spent until 1,000 more blocks are built on top of it. Until then your wallet shows
  it as `Immature`.

That is the full set of inputs the protocol gives you. It does **not** include a
price, an exchange rate, or an earnings figure, because those are not protocol facts.
**Your profit or loss is (your block share × how many blocks you actually win) minus
your electricity and hardware costs** — all of which depend on your difficulty share,
your power price, and the market. Work it out yourself before committing.

---

## 10. Verify your blocks were accepted

Three independent ways to confirm your mining is landing on the real chain:

**A. The miner's own log** — look for `-> submitted to node OK` after each
`[BLOCK ...]` line. A `-> node REJECTED block` line means it was not accepted.

**B. Your node, via `sost-cli`:**

```bash
# height should keep rising and track the network
./sost-cli --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass getblockcount

# the current best tip hash — should match the explorer's latest block
./sost-cli --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass getbestblockhash
```

Then confirm your wallet is receiving coinbase rewards (mature + immature):

```bash
./sost-cli --wallet wallet.json --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass listaddresses
```

Freshly mined rewards appear as **Immature** until 1,000 confirmations.

**C. The public explorer:**

**https://sostcore.com/sost-explorer.html**

Find a block at a height you mined and confirm its hash matches your node's
`getbestblockhash` (and the coinbase pays your mining address). If it is on the
explorer, the whole network accepted it — that is the definitive confirmation.

---

## 11. Troubleshooting

**`timestamp too far in future` / chain stalls / nothing is accepted**
You forgot `--realtime`. Add it. This is the single most common mistake. Without it
every block you submit is rejected.

**`FATAL: binary is not consensus-capable on mainnet`**
Your `sost-node` was built with `SOST_ENABLE_PHASE2_SBPOW=OFF`. Rebuild with the
mandatory flags in Section 3, or use the official release binary (and verify its
hash).

**RPC 401 / "credentials still wrong"**
The miner's `--rpc-user` / `--rpc-pass-file` must match the **node's** `--rpc-user` /
`--rpc-pass-file`. This is a per-node RPC password, not a SOST-wide password. Make
sure both processes read the same `~/.sost/rpc.pass` and use the same username.

**`--mining-key-label requires --wallet` / "label not found"**
`--wallet` and `--mining-key-label` must be used together, and the label must exist
in the wallet. Create it with `sost-cli --wallet wallet.json getnewaddress "miner"`,
then pass `--mining-key-label "miner"`.

**`[RPC] Waiting for node...` / "Connection lost"**
Your node isn't reachable at the `--rpc` address. Check the node is running, that the
RPC port is right (default **18232**), and that you did not accidentally bind it
somewhere else.

**Machine swapping / mining got slower when I added threads**
You exceeded the RAM your machine can back (Section 4). SbPoW is memory-hard —
reduce `--threads` until the working set fits in RAM and swap stops.

**My blocks say `OK` but a competing block wins ("race lost, advancing")**
Normal — other miners are solving the same height. As long as your node stays synced
and you keep `--realtime`, you keep competing for the next block.

**The miner mines but the node never catches the network tip**
Make sure the node finished its initial sync before you started mining, and that
`--connect seed.sostcore.com:19333` (or another good peer) is reachable.

---

## 12. Quick reference — full copy/paste

```bash
# 1. verify (binaries from github.com/Neob1844/sost-core/releases/tag/v30000)
cd ~/sost
echo "eec96efb02bde61cae150f51b3cedb46e55a5dd5e903496a278e90257aa64951  sost-miner" | sha256sum -c -
chmod +x sost-node sost-miner sost-cli

# 2. private RPC password
mkdir -p ~/.sost && umask 077
openssl rand -base64 30 > ~/.sost/rpc.pass && chmod 600 ~/.sost/rpc.pass

# 3. node (let it fully sync)
./sost-node --genesis genesis_block.json --chain chain.json \
  --connect seed.sostcore.com:19333 \
  --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass \
  --profile mainnet --p2p-enc on

# 4. wallet + mining key (in another shell)
./sost-cli --wallet wallet.json newwallet
./sost-cli --wallet wallet.json getnewaddress "miner"
chmod 600 wallet.json

# 5. miner — note --realtime is MANDATORY
./sost-miner --wallet wallet.json --mining-key-label "miner" \
  --genesis genesis_block.json \
  --rpc 127.0.0.1:18232 --rpc-user myuser --rpc-pass-file ~/.sost/rpc.pass \
  --blocks 999999 --threads 4 --profile mainnet --realtime
```

Explorer: https://sostcore.com/sost-explorer.html

Welcome, and mine honestly.
