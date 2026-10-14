# RUN AN INDEPENDENT SOST NODE

This guide is for a **third party** who wants to run their own SOST full node,
validate the chain independently, and **not depend on sostcore.com** for
anything except optional bootstrap convenience. If you follow it exactly you
will: install the `v30000` release, cryptographically verify it, sync, discover
peers, confirm you are on the canonical chain, and — by default — expose **no
RPC at all**.

**Security posture: deny-by-default.** The node ships closed. RPC binds to
`127.0.0.1` only, state-changing methods require authentication, and nothing is
reachable from the network until you deliberately open it. This guide never
asks you to expose a secret, an RPC password, or any wallet/admin method. If a
step feels like it is loosening security, re-read it — you almost certainly do
not need to.

---

## 0. What you are running

Three binaries ship in the release:

| Binary      | Purpose                                                      |
|-------------|-------------------------------------------------------------|
| `sost-node` | The full node: validates and relays blocks over P2P.        |
| `sost-miner`| Produces blocks. **You do not need this to run a node.**    |
| `sost-cli`  | Command-line client for talking to a node's RPC.            |

A node alone validates the entire chain. You only need `sost-miner` if you
intend to mine, and `sost-cli` only if you turn RPC on.

Key network parameters (defaults, mainnet):

- **P2P port:** `19333`
- **RPC port:** `18232` (bound to `127.0.0.1` by default — not the network)
- **Network profile:** `mainnet` (the default)

---

## 1. Install and verify (SHA256)

### 1.1 Download the release

Get the three binaries and the checksum manifest from the official release tag:

> https://github.com/Neob1844/sost-core/releases/tag/v30000

Download `sost-node`, `sost-miner`, `sost-cli`, and `SHA256SUMS`.

### 1.2 Verify ALL THREE binaries before running anything

Never run a binary you have not checksum-verified. From the directory where you
downloaded them:

```bash
# Verify every file listed in the manifest in one shot:
sha256sum -c SHA256SUMS
#   sost-node: OK
#   sost-miner: OK
#   sost-cli: OK
```

The published `sost-node` SHA256 is:

```
78fefb67a15615f3df1b0a4f498239ccba07ba47ce6e333d13d5d2afdcecbb56
```

Confirm it independently:

```bash
sha256sum sost-node
# must print exactly:
# 78fefb67a15615f3df1b0a4f498239ccba07ba47ce6e333d13d5d2afdcecbb56  sost-node
```

If any line is not `OK` (or the hash differs by a single character), **stop** —
do not run the binary. Re-download, and if it still fails, do not proceed.

```bash
chmod +x sost-node sost-miner sost-cli
```

### 1.3 (If you build from source instead)

If you compile rather than use the release binaries, the node **must** be built
with Phase 2 SbPoW verification enabled or it will refuse to run on mainnet:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON
cmake --build build -j"$(nproc)" sost-node sost-miner sost-cli

# Sanity check the binary actually contains the verification code path:
strings build/sost-node | grep -c 'POW-SIG/v11'   # must be > 0
```

A mainnet node compiled without this flag fails loudly at startup with a FATAL
"binary is not consensus-capable" message — by design.

---

## 2. First run and initial sync

The simplest possible start — explicit mainnet profile, everything else at its
safe defaults:

```bash
./sost-node --profile mainnet
```

On first launch the node will:

1. Print its banner (`=== SOST Node v0.4.0 ===`) and the active profile.
2. Bootstrap P2P: with no `--connect` given, it tries the default DNS seeds
   (see §3) and reports which connected.
3. Report `[RPC] Listening on 127.0.0.1:18232 ... (auth=ON)` — note **127.0.0.1**,
   not the network.
4. Begin downloading and **validating** blocks until it reaches the chain tip.

By default the node uses fast sync. To force a full ConvergenceX re-verification
of every block (slower, maximum paranoia), add `--full-verify` (equivalently
`--no-fast-sync`).

Useful flags for the data it keeps:

```bash
./sost-node --profile mainnet \
  --chain   /var/lib/sost/chain.json \
  --wallet  /var/lib/sost/wallet.json
```

`--chain` is the chain file it loads and auto-saves to; `--wallet` is only
relevant if you later use wallet features. Neither opens any network surface.

Leave it running until the height stops advancing and matches the network (see
§4). To replay and print the UTXO-set root and height **without** opening P2P or
RPC at all — a good offline integrity check — use `--dry-run-replay`:

```bash
./sost-node --profile mainnet --chain /var/lib/sost/chain.json --dry-run-replay
```

---

## 3. Peer discovery (and not depending on sostcore.com)

> The behaviour below is the one on branch `feat/v40k-p2p` (P1–P7 of
> `docs/v40000/DECENTRALIZATION_ACTION_PLAN_40000.md`). Released binaries up to
> v16.x do NOT have it: their `peers.txt` keeps the dialed hostnames, gossip is
> only used after losing every peer, and there is no `--addnode`.

### 3.1 Automatic (default)

With no `--connect`, the node bootstraps in this order and stops the automatic
sources once 3 peers are connected:

1. `--addnode` peers (always dialed, see 3.2);
2. the **address book** `peers.txt` next to `--chain` (most recently successful first);
3. `seeds.txt` next to `--chain` (one `host` or `host:port` per line, operator-supplied);
4. the default DNS seeds `seed-eu`, `seed-apac`, `seed-us`, `seed` `.sostcore.com`;
5. compiled-in fallback IPv4 literals (`FALLBACK_SEED_IPS`, empty until independent
   seed operators with evidence exist — none are invented).

After that the node keeps discovering peers while it is connected: every 30 s, while
it has fewer than **8 outbound** peers, it dials up to 2 new addresses from its address
book, from addresses learned by gossip, and from inbound peers' advertised listen
addresses, with at most **2 outbound peers per /16** and an exponential retry back-off.
The seeds are a convenience for first contact, **not** an authority on the chain.

**Address book (`peers.txt`, mode 600).** It holds the *resolved* `ip:port` of peers that
completed a handshake with this node — never the hostname that was dialed, so a node
that first connected through `seed-eu.sostcore.com` can redial its peers even if
sostcore.com DNS disappears. At most 256 entries; an entry that has failed for 14 days
is dropped; a gossiped address is written only after this node completed a handshake
with it. Format: `ip:port last_success last_attempt fails first_fail source`. An older
binary reading this file still gets `ip:port` from each line, and the new binary reads
an old one-address-per-line file (hostname lines are dialed once and not kept).

**Self-advertisement.** The version message carries the node's listen port. A peer that
connects to you learns `your_ip:listen_port`, verifies it with its own short "feeler"
connection, and only then stores and gossips it. If your public address is not the one
peers see (NAT, multiple addresses), pass `--externalip <ipv4>`. Old nodes ignore the
extra bytes.

### 3.2 `--addnode` (add peers, keep discovery) vs `--connect` (only these peers)

```bash
# Add peers you trust; the address book, seeds.txt, DNS seeds, fallback IPs and
# gossip all stay active. --addnode may be repeated; the node keeps them connected.
./sost-node --profile mainnet \
  --addnode 203.0.113.10:19333 \
  --addnode 198.51.100.22:19333

# Connect ONLY to these peers (exclusive): no address book / seeds.txt / DNS seeds at
# boot and no outbound discovery. Use for labs or a node behind your own gateway.
./sost-node --profile mainnet --connect 203.0.113.10:19333
```

If you ever see `[P2P] WARNING: no stored peer, seeds.txt entry, default seed or fallback
IP reachable`, one working `--addnode` peer is the fix; the node learns the rest by gossip
and remembers it in `peers.txt`.

### 3.3 Where your peers came from

`getpeerinfo` reports, per peer, `source` (connect / addnode / store / seedsfile / dns /
fallback / gossip / inbound), `subnet16` (only the first two octets, like the masked
`addr`), the advertised `listen_port` and whether it is a short `feeler` connection.
`getaddrbookinfo` returns counts only: address-book entries, failing entries, distinct
/16s, entries by source, gossip candidates, pending feelers, outbound/inbound and the
outbound target. No full address is exposed over RPC.

Optional P2P link encryption is available via `--p2p-enc off|on|required`
(default `off`); set it consistently with the peers you connect to.

---

## 4. Confirm you are on the canonical chain

Your node validates every block itself, so "canonical" means "the valid chain
with the most work" — which your node determines locally. To *sanity-check*
that your local view agrees with the rest of the network, compare your tip
against independent sources (other peers, and — only as one data point — the
public explorer).

If RPC is off (the default), you can read status without any auth by sending a
plain HTTP GET to the local RPC port, which returns `getinfo`:

```bash
# Localhost only — this is the default bind, no credentials needed:
curl -s http://127.0.0.1:18232/        # -> getinfo JSON (height, tip, peers)
```

Or, with `sost-cli` pointed at your local node:

```bash
./sost-cli getblockcount         # your current height
./sost-cli getbestblockhash      # hash of your tip
./sost-cli getpeerinfo           # who you are connected to
```

To confirm agreement:

1. Note your `getblockcount` and `getbestblockhash`.
2. Check the same height's hash against **more than one** independent peer, and
   optionally against the public explorer.
3. If the **best block hash at the same height matches**, you are on the
   canonical chain. If it differs, you are either still syncing (let it catch
   up) or you have found a fork — in which case trust **your own validation**:
   the node only ever follows blocks that pass all consensus rules.

The explorer is a convenience cross-check, not the source of truth. Your node
reaching the same tip through its own validation **is** the confirmation.

---

## 5. RPC: keep it OFF / localhost by default (deny-by-default)

### 5.1 The default is already safe — leave it that way

Out of the box:

- RPC **binds to `127.0.0.1` only**. Nothing on the network can reach it.
- **Read-only** methods (e.g. `getblockcount`, `getinfo`, `getpeerinfo`,
  `getbestblockhash`) are auth-exempt — handy for your own local scripts.
- **Every state-changing / wallet / admin method requires Basic Auth**, and
  because no `--rpc-user` / `--rpc-pass` is set by default, those methods are
  simply **rejected with 401**. There is no admin surface until you create one.

For a pure validating node, **do nothing** — do not set a password, do not open
a port. This is the recommended configuration. You do not need RPC exposed to
run a node or to contribute to the network.

### 5.2 Flags you should NOT use unless you fully understand them

- `--rpc-public` — binds RPC to `0.0.0.0` (all interfaces). **Avoid.** It puts
  the RPC port directly on the network. If you need remote read access, use a
  reverse proxy instead (§5.3), not this flag.
- `--rpc-noauth` — disables authentication entirely. **Never** use this on a
  reachable node; it would let anyone call state-changing methods.
- `--rpc-pass <p>` — passes the password on the command line, where it lands in
  `argv` and process listings. Prefer `--rpc-pass-file` (§5.3).

### 5.3 IF you must expose read-only RPC: do it safely

Only expose RPC if you have a real reason (e.g. you run a dashboard on another
host). Then follow all of these:

1. **Keep the node itself bound to localhost.** Do **not** use `--rpc-public`.
   Put a reverse proxy (nginx/Caddy) in front of `127.0.0.1:18232`.

2. **Expose only read-only methods.** Have the proxy allow-list exactly the
   non-mutating methods and reject everything else. The read-only set the node
   treats as auth-exempt includes (not exhaustive):
   `getinfo`, `getblockcount`, `getblockhash`, `getblock`, `getbestblockhash`,
   `getmempoolinfo`, `getrawmempool`, `getrawtransaction`, `getpeerinfo`,
   `validateaddress`, `gettxout`, `getaddressbalance`, `getsupplyinfo`,
   `geteligibleminers`, `getlotteryaudit`, `gethistoricaljackpotstatus`.
   These are pure reads: they never mutate state and never reveal credentials.

3. **Never proxy wallet or admin methods.** Anything that signs, sends, moves
   funds, or changes node state must not be reachable from outside. Keep those
   local-only.

4. **If you need authenticated methods at all, keep the credential off the
   command line.** Put the password in a private, mode-600 file and load it with
   `--rpc-pass-file`:

   ```bash
   umask 077
   printf '%s' 'a-long-random-password' > /etc/sost/rpc.pass
   chmod 600 /etc/sost/rpc.pass            # owner-only
   ./sost-node --profile mainnet \
     --rpc-user sost \
     --rpc-pass-file /etc/sost/rpc.pass
   ```

   **Never** print this password, commit it, bake it into a container image,
   send it over an unencrypted channel, or hand it to a client that logs URLs.
   Rotate it if it is ever exposed.

5. **Terminate TLS at the proxy** and apply rate limiting / IP allow-listing
   there. The node's RPC speaks plain HTTP and sets a permissive CORS header; it
   is designed to sit *behind* a proxy, never directly on the internet.

Minimal nginx sketch (read-only, localhost upstream, method allow-listing is
done by your app/proxy logic):

```nginx
server {
    listen 443 ssl;
    server_name node.example.org;
    # ... your TLS certs ...
    location /rpc {
        # Only forward to the node bound on loopback:
        proxy_pass http://127.0.0.1:18232/;
        # Enforce read-only at this layer (allow-list methods in your app),
        # apply auth/rate-limit here, and NEVER forward wallet/admin calls.
    }
}
```

---

## 6. Operating independently of sostcore.com

A correctly run node does **not** need sostcore.com to function:

- **Validation is local.** Your node checks every block against consensus rules
  itself. If the website and explorer go down, your node keeps validating,
  relaying, and advancing exactly as before.
- **Peers, not a website, are the network.** Even the DNS seeds are only a
  first-contact convenience; after bootstrap you stay connected via peer
  exchange. You can bootstrap entirely from `--connect` peers you choose (§3.2)
  and never touch the sostcore.com seeds.
- **The explorer is a cross-check, not an authority (§4).** If your tip
  disagrees with the explorer, trust your node's own validation. "Canonical" is
  the valid most-work chain your node computes — not whatever any website says.
- **No phone-home, no secret needed.** Running a node requires no account, no
  key given to a third party, and no credential shared with anyone. Everything
  in this guide keeps secrets on your machine.

**Want to help decentralize?** Run with a stable, reachable P2P port (`19333`),
keep the node up, and — optionally — let others `--connect` to you. You do not
need to expose RPC to be a useful peer.

---

## 7. Quick reference

```bash
# Verify (do this first, every time)
sha256sum -c SHA256SUMS

# Minimal, safe, independent node (no RPC exposed):
./sost-node --profile mainnet

# Bootstrap without the sostcore.com seeds:
./sost-node --profile mainnet --connect <host:port> --connect <host:port>

# Local status (no auth, localhost only):
curl -s http://127.0.0.1:18232/
./sost-cli getblockcount
./sost-cli getbestblockhash
./sost-cli getpeerinfo

# Offline integrity replay (no P2P, no RPC):
./sost-node --profile mainnet --chain <path> --dry-run-replay

# Full help / all flags:
./sost-node --help
```

**Defaults recap:** RPC on `127.0.0.1:18232`, auth required for anything that
changes state, no admin surface until you create one. Leave it that way unless
you have a concrete reason — and even then, read-only, behind a proxy, secrets
on disk at mode 600, wallet/admin methods never exposed.
