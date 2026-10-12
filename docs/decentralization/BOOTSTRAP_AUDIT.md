# SOST Bootstrap & Peer-Discovery Dependency Audit

**Status:** AUDIT ONLY — no code or configuration was changed by this document.
**Scope:** How a SOST node finds its first peers and stays connected (bootstrap +
peer discovery), the single points of failure in that path, and *proposals only*
for improvements to be considered **after block #30,000** (pre-#30000 freeze is in
effect — nothing here is to be applied now).

**Audited tree:** `main` @ `de5f1597`
**Primary evidence file:** `src/sost-node.cpp`
**Headers checked:** `include/sost/*.h`
**Method:** direct `grep`/read of the real source — every claim below cites the
code location it came from. Where a claimed feature could not be found, that is
stated explicitly rather than assumed.

---

## 1. What the code actually does

### 1.1 P2P port
- `static const int P2P_PORT_DEFAULT = 19333;` — `src/sost-node.cpp:273`.
- Used as the default for seed dials (`:9541`), for `--connect` addresses with no
  explicit port (`:9560`), for reconnect (`:9591`), and documented in `--help`
  (`:9289`). A single fixed default port for the whole network.

### 1.2 DNS seeds (the primary bootstrap path)
- `DEFAULT_SEEDS[]` — `src/sost-node.cpp:9530-9535`:
  - `seed-eu.sostcore.com`
  - `seed-apac.sostcore.com`
  - `seed-us.sostcore.com`
  - `seed.sostcore.com`  — comment: *"backward-compatible alias (currently -> EU)"*
- Logic (`:9529-9552`): only used when `--connect` is **not** supplied
  (`if(connect_addrs.empty())`). It tries the seeds in order and stops once
  `WANT = 3` connect. Seeds that don't resolve "fail closed and are skipped"
  (degrades to EU-only until the APAC/US records + nodes exist). If **zero**
  seeds are reachable it prints a WARNING and the node has no peers unless
  `--connect` is passed.

- **KEY FINDING (confirmed):** all four seed hostnames are sub-domains of the
  **same parent domain `sostcore.com`**, which is project-controlled. The three
  "regional" names (eu/apac/us) give geographic *node* diversity but **not**
  naming/trust diversity: they share one DNS zone, one registrar, and one
  registrant. A compromise, lapse, hijack, or takedown of `sostcore.com` (or its
  authoritative DNS) disables *all four* seed names at once. The regional split
  is a load/availability improvement, **not** an independence improvement.

### 1.3 Hardcoded peers / static fallback IPs
- **None found.** There is no array of literal fallback IP addresses compiled
  into the binary. The only compiled-in bootstrap data is the four
  `sostcore.com` DNS names above. If DNS resolution fails for all of them, there
  is no hardcoded IP to fall back to — the operator must supply `--connect`.

### 1.4 Manual bootstrap (`--connect`)
- `connect_addrs` is populated **only** from the `--connect` CLI flag
  (`src/sost-node.cpp:9204`). When present, it *replaces* the DNS-seed path
  (the seed block is guarded by `connect_addrs.empty()`).
- Accepts `host:port` or bare `host` (defaults to 19333) — `:9553-9563`.

### 1.5 Persistent peer database / peers file
- **NOT located in the audited code.** Greps for `peers.dat`, `peers.json`,
  `addrman`, `addr_db`, `save_peers`/`load_peers`, `persist…peer`, `known_peers`,
  `peerdb`, and file-I/O (`fopen`/`ofstream`/`ifstream`) tied to peers all
  returned nothing in `src/sost-node.cpp` or `include/sost/*.h`.
- The only on-disk state saved in the main loop is the **chain**
  (`save_chain(chain_path)`, `:9598`) and the **PoPC registry**
  (`g_popc_registry.save(...)`, `:9599`). No peer address set is written to disk
  or read back at startup.
- `g_known_blocks` (`:459-472`) is an in-memory FIFO of block IDs (for relay
  dedup), **not** peer addresses — it is unrelated to peer persistence.
- **Honesty note on the "persistent peer storage + automatic redial" claim:**
  *Persistent peer storage* is **not** evidenced in the audited code — claimed
  but unverified here; no file is written or loaded. *Automatic redial* exists
  but in a **narrow form only** (see 1.7): it redials the `--connect` list, not
  discovered peers, and does nothing for a DNS-seed-only node.

### 1.6 Address relay / gossip (ADDR / GETADDR)
- **No peer-address gossip exists.** The complete P2P command set handled in
  `handle_peer` (`src/sost-node.cpp:7831-8949`) is:
  `EKEY` (encryption handshake), `VERS`/`VACK` (version),
  `GETB`/`BLCK`/`DONE` (block sync), `TXXX` (tx relay),
  `PING`/`PONG` (keepalive), `BCNN` (Beacon advisory notice).
- There is **no `ADDR` and no `GETADDR` message.** Nodes never tell each other
  about *other* peers. `VERS` carries only `{their_height (8B), genesis_hash
  (32B)}` (`:8062-8075`) — no address payload. `BCNN` is the Beacon Phase III
  **advisory** notice (`:8349+`), explicitly walled off from consensus and not a
  peer-address message.
- **Consequence:** the comment at `:9526-9528` ("Peer exchange grows the mesh
  from whatever connects") describes an intent that the current code does **not**
  implement — there is no peer-exchange mechanism. The mesh does **not** grow
  beyond (a) nodes that dial the seeds/`--connect` and (b) inbound connections
  those produce. A fresh node's reachable peer set is exactly what the seeds (or
  `--connect`) hand it; it cannot discover the wider network.

### 1.7 Connection maintenance / redial
- Main loop every 30 s (`:9574-9597`): PINGs live peers, saves chain + PoPC.
- **Auto-reconnect** (`:9584-9596`) fires **only** when
  `g_peers.empty() && !connect_addrs.empty()` — i.e. a node that was started
  with `--connect`. It redials the `--connect` addresses.
- A node bootstrapped purely from DNS seeds has `connect_addrs` empty, so if it
  loses **all** peers it will **not** redial the seeds — it simply sits
  peerless until restarted. Discovered/inbound peers are never re-dialed either.
- Inbound peers: `MAX_INBOUND_PEERS = 32`, `MAX_PEERS_PER_IP = 2`
  (`:480-481`); ban/misbehavior scoring exists (`:582-611`). None of this
  records addresses for later reconnection.

### 1.8 Reliance on the sostcore.com / VPS infrastructure
- The DNS names, and (per the decentralization review) the primary
  infrastructure node, are project-operated — the main seed resolves to one VPS
  (Germany). The backward-compat alias `seed.sostcore.com` currently points to
  the EU seed, so the "4 seeds" collapse toward a small number of
  project-operated endpoints in practice.
- `sostcore.com` is also referenced elsewhere in the node for user-facing text
  (e.g. `:9427`), but the bootstrap-critical dependency is specifically the DNS
  zone + the hosts the seed names resolve to.

---

## 2. BOOTSTRAP SINGLE POINTS

- **Single DNS domain:** all four seed names live under one project-controlled
  domain (`sostcore.com`) — one registrar + one DNS zone can take down every
  seed at once (`src/sost-node.cpp:9530-9535`).
- **No hardcoded fallback IPs:** if DNS fails for all four names, a default node
  has no compiled-in peer to reach and needs manual `--connect` (`:9529-9552`).
- **No persistent peer store:** nothing is saved/loaded from disk, so every
  restart re-bootstraps from scratch via the same seeds (no peer file found in
  audited code).
- **No address gossip (ADDR/GETADDR):** nodes cannot learn peers from each
  other; the reachable set is only what the seeds/`--connect` provide
  (`handle_peer` command set, `:7831-8949`).
- **Seed-only nodes never redial:** auto-reconnect covers `--connect` nodes
  only; a DNS-seeded node that loses all peers stays peerless until restart
  (`:9584-9596`).
- **Operator concentration:** the seed hosts (and the primary node) are
  project-operated on one VPS region; `seed.sostcore.com` aliases to EU, so
  effective seed diversity is lower than the four names suggest.
- **Single fixed P2P port (19333):** a network-level block of one port isolates
  default nodes (`:273`).

---

## 3. POST-#30000 PROPOSALS (proposals only — DO NOT APPLY NOW)

> All of the following are **P2P/operational** in nature and would be designed to
> have **no consensus, mining, or PoPC impact**; none is to be implemented during
> the pre-#30000 freeze. Listed for later evaluation.

1. **Multiple INDEPENDENT DNS seeds on different domains + registrars.**
   Add seed hostnames under 2-3 *distinct* parent domains held at *different*
   registrars (and ideally different DNS providers), so no single zone/registrar
   compromise disables bootstrap. The existing `sostcore.com` names stay as one
   of several, not the only, trust root.

2. **Third-party / community seed operators.**
   Invite independent operators to run seed nodes under domains they control and
   list them in `DEFAULT_SEEDS`. Reduces the "all seeds are project-operated on
   one VPS" concentration; publish an operator policy so the list is auditable.

3. **Hardcoded fallback peer IPs.**
   Compile in a small, curated list of stable fallback node IPs (geographically
   spread, mixed operators) tried when *all* DNS resolution fails — the
   last-resort path that today does not exist. Keep it small and refreshed per
   release.

4. **Persistent peer database ("addr store") + redial of discovered peers.**
   Actually implement what is currently only claimed: write successfully
   connected peer addresses to disk (e.g. a `peers`/`addr` file under the data
   dir) and load them at startup, so restarts don't depend on seeds. Extend the
   30 s maintenance loop to redial from this store even when `--connect` was not
   given (closing the "seed-only node never redials" gap at `:9584`).

5. **Address relay / gossip hardening (ADDR / GETADDR).**
   Add a minimal, rate-limited, anti-spoofing peer-exchange protocol so the mesh
   can actually "grow from whatever connects" (the stated intent at `:9526`).
   Must include: bounded ADDR payloads, misbehavior scoring reuse (`:593`),
   per-IP caps (reuse `MAX_PEERS_PER_IP`), and no self-poisoning (don't relay
   unroutable/banned addresses). Pairs with (4) to populate the addr store.

6. **Diversify seed resolution (DNSSEC / fixed-seed + eclipse resistance).**
   Consider DNSSEC on seed zones, and bucketed outbound selection (spread
   connections across IP ranges) to raise the cost of an eclipse attack now that
   discovery would no longer be a single funnel.

7. **Configurable / documented alternate P2P port fallback.**
   Optional secondary listen/dial port so a block of 19333 alone cannot isolate
   default nodes. Lower priority; only if operational evidence warrants it.

8. **Seed health + decentralization monitoring.**
   Operational (non-code): track per-seed reachability and the fraction of the
   network reachable only via project-operated infra, so progress on the above
   is measurable rather than assumed.

---

## 4. Honesty statement

This audit reports only what the source at `de5f1597` shows. Confirmed in code:
the four same-domain DNS seeds, the single default port, the absence of
hardcoded fallback IPs, the absence of any ADDR/GETADDR peer gossip, and the
narrow `--connect`-only auto-reconnect. **Not** evidenced in code and therefore
**not** claimed as present: a persistent peer-address store/file, redial of
discovered (non-`--connect`) peers, and any working peer-exchange that grows the
mesh beyond the seeds. No decentralization property is asserted beyond what the
code demonstrates.
