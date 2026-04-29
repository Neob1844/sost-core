# SOST Node — systemd deployment

This directory contains the canonical systemd setup for `sost-node`. It exists
because a misconfigured deploy left a node running with empty RPC credentials,
which caused every authenticated RPC call (including the operator's own miner
`submitblock`) to be rejected with HTTP 401 — silently. The files here make
that mistake hard to repeat.

## Files

- `sost-node.service.template` — systemd unit. Reads RPC credentials from
  `/etc/sost/rpc.env` so they never appear in the unit or in `ps -ef`.
- `install-sost-node.sh` — one-shot installer / repairer. Generates random
  RPC credentials if `/etc/sost/rpc.env` is missing, copies the unit into
  `/etc/systemd/system/`, reloads systemd, and (re)starts the service.
  Idempotent: re-running on a working host keeps the existing credentials.
- `healthcheck.sh` — quick verifier. Prints PASS / FAIL for each invariant:
  unit installed, env file present and 600, credentials non-empty in env,
  service active, RPC port listening, authenticated `sendrawtransaction`
  reaches the dispatcher (i.e. does NOT come back as 401).

## Setup on a fresh VPS

```
sudo ./deploy/systemd/install-sost-node.sh
```

That's it. The script:

1. Creates `/etc/sost/` with mode 700 if missing.
2. If `/etc/sost/rpc.env` is missing or empty, generates two 40-char hex
   tokens via `openssl rand -hex 20` and writes them as `RPC_USER` and
   `RPC_PASS`. The file is `chmod 600`, owned by `root:root`.
3. Copies `sost-node.service.template` to `/etc/systemd/system/sost-node.service`.
4. Runs `systemctl daemon-reload && systemctl enable --now sost-node`.
5. Waits 3 seconds and runs `healthcheck.sh` to confirm everything is up.

After install, **export the same credentials to your miner host**. From WSL
or wherever you run `sost-miner`, copy them out of the VPS once:

```
ssh root@<VPS_IP> 'cat /etc/sost/rpc.env'
```

…and use those exact values for `--rpc-user` / `--rpc-pass` on the miner.
The miner credentials must match the node credentials byte-for-byte.

## Running the healthcheck on a live node

```
sudo ./deploy/systemd/healthcheck.sh
```

The script returns exit code `0` only when every invariant passes. Wire it
into a periodic cron / systemd-timer if you want to be alerted as soon as
the credentials drift again:

```
sudo crontab -e
# every 5 minutes, log + alert on failure
*/5 * * * * /opt/sost/deploy/systemd/healthcheck.sh >> /var/log/sost-healthcheck.log 2>&1
```

## The bug this directory exists to prevent

A unit shaped like this:

```
ExecStart=/opt/sost/build/sost-node --rpc-user ${RPC_USER} --rpc-pass ${RPC_PASS} --profile mainnet
```

…requires `${RPC_USER}` and `${RPC_PASS}` to come from somewhere systemd
can resolve. Two failure modes:

- **No `EnvironmentFile=` directive.** systemd substitutes empty strings.
  The process line in `ps -ef` becomes `--rpc-user --rpc-pass --profile`,
  the argument parser consumes `--rpc-pass` as the value of `--rpc-user`,
  and the auth state ends up empty.
- **`EnvironmentFile=` points at a file that does not exist.** Same result.

In both cases the node still boots, lectures (`getinfo`, `getblock`) work
because they are in the read-only allowlist, but every authenticated call
returns 401. The miner submits blocks that the node refuses; `journalctl
-u sost-node` shows `[BLOCK] REJECTED: ... Authentication required`. The
node from the network's point of view looks fine because peers gossip
blocks via P2P (which does not go through RPC auth).

The healthcheck script catches this by issuing a real `sendrawtransaction`
with an obviously invalid hex payload. A working node returns a JSON error
like `"TX decode failed"` (auth passed; payload rejected). A broken node
returns 401. The two are unambiguous.

## Updating the node binary

```
cd /opt/sost
git pull --ff-only origin main
cd build
make -j$(nproc)
sudo systemctl restart sost-node
sudo /opt/sost/deploy/systemd/healthcheck.sh
```

If the healthcheck fails after a restart, do **not** assume it's a code
issue — it's almost always a credentials regression. Check `/etc/sost/rpc.env`,
`systemctl cat sost-node`, and the actual ExecStart in `ps -ef`.
