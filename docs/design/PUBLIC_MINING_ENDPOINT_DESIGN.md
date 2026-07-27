# Public Mining Endpoint — Security Design (DESIGN ONLY, NOT IMPLEMENTED)

Status: **DESIGN — do NOT implement on production without a cold security review.**
Author: CTO/consensus. Goal: let anyone mine SOST by pointing a miner at
`sostcore.com` WITHOUT running their own full node — turning a multi-hour setup
into two commands, and ending the network's dependence on a single operator's
machine. This is the structural cure for "only one miner"; but it converts the
node (our most stable asset) into a public attack surface, so the security
design is the hard part and must come first.

## 1. The barrier this removes
To mine SOST today a person must run + sync their OWN full node, because:
- `getlotterystate` / `getblockcount` are **no-auth reads** (already public via
  the proxy) — a miner CAN fetch work.
- **`submitblock` requires node auth** — the public proxy (`sost-rpc-proxy.py`)
  only injects credentials for `sendrawtransaction`, so a remote miner **cannot
  submit the block it finds**. Hence everyone needs their own node.
Result: 180+ "updated miners" that never sustained a node → the single-miner
fragility. Removing the submit barrier (safely) is the unlock.

## 2. What is safe vs what is NOT
- **Consensus-safe:** an invalid block submitted to `submitblock` is rejected by
  full validation — you cannot corrupt the chain by submitting bad blocks. Valid
  blocks submitted by strangers are GOOD (that is the whole point).
- **NOT automatically safe:** availability. An open `submitblock`/`getblocktemplate`
  endpoint is a **DoS surface**. On a 3.8 GB / 2-core node, unbounded requests
  (each `getblocktemplate` builds a template; each `submitblock` runs full block
  validation incl. the memory/PoW checks) can saturate CPU/RAM and take the node
  down. **The node is the one piece that has stayed solid — it must not become
  the soft target.** "Consensus validates it" answers correctness, not liveness.

## 3. Threat model (must all be handled)
1. **Request flood / DoS** on getblocktemplate/submitblock → node CPU/RAM
   exhaustion → chain stalls (worse than the operational stalls we have now).
2. **Expensive-validation abuse:** submitblock triggers full PoW/witness
   validation; a stream of almost-valid blocks is a CPU amplification attack.
3. **Sensitive-RPC exposure:** must NOT widen access to admin/wallet/write
   methods. Only the exact mining triple may pass; everything else stays gated.
4. **Method smuggling:** a crafted body must not slip a second method past the
   gate (the proxy already canonicalizes to one method — preserve that).
5. **Amplification / reflection** via the CORS `*` origin.
6. **Resource starvation of the co-located node** (see §5 limits).

## 4. Minimal exposed surface
Expose ONLY, via the gateway, the mining triple:
- `getlotterystate` (read; already public)
- `getblocktemplate` (read-ish; bounded cost)
- `submitblock` (write; **gateway injects node auth**, like sendrawtransaction)
Everything else stays as today: reads no-auth, all admin/wallet/write BLOCKED.
`submitblock` joins the gateway's `BROADCAST_METHODS`-style auth-injection set so
the node still enforces its own gate; no node RPC credentials are ever exposed to
the public.

## 5. Required protections (the actual work — none optional)
- **Rate limiting (per-IP + global):** e.g. getblocktemplate ≤ N/s per IP,
  submitblock ≤ M/s per IP, with a global ceiling sized to the node's headroom.
  Reject with 429, cheaply, before touching the node.
- **Connection + body caps:** max concurrent conns, max body size, short
  timeouts; drop slow-loris.
- **A dedicated front (nginx/limit_req or a hardened gateway):** do the rate
  limiting in front of the node, not inside it, so floods die before reaching the
  expensive path.
- **Node resource isolation:** the node runs under systemd with `CPUWeight`/
  `MemoryMax` so even a partial flood cannot OOM/starve it; the gateway is a
  separate unit that can be killed without touching the node.
- **Capacity test:** measure how many concurrent miners a 3.8 GB node sustains
  before getblockcount latency degrades. If the answer is "few", the endpoint
  needs a bigger node (≥8 GB) BEFORE going public — do not ship it onto the
  current 3.8 GB box.
- **Kill switch:** one command to disable the public mining endpoint instantly
  (revert to node-only) if abuse appears, WITHOUT restarting the node.
- **Observability:** per-method request counters + node latency alerting, so
  abuse is visible early (the explorer's "RPC errors" is a lagging signal).

## 6. Abuse response
- Endpoint saturating the node → kill switch (§5) → node returns to health; miners
  fall back to their own nodes; chain unaffected.
- Persistent abuser → per-IP ban at the front.
- The node NEVER depends on the endpoint: mining locally (operator + any
  self-hosted miner) keeps working if the public endpoint is off.

## 7. Phased rollout gate (do not skip)
1. Design review (this doc) — cold, not at 2 a.m.
2. Stand up the hardened gateway on a **staging/≥8 GB node**, never first on
   production.
3. Load-test: simulate 10/50/100 miners; confirm node latency stays healthy and
   the kill switch works.
4. Only then, on a node with adequate RAM, enable publicly with rate limits.
5. Publish a "Mine SOST in 2 minutes" guide (miner + wallet + `--rpc sostcore.com`
   + the 8 GB-RAM caveat) ONLY after 1–4 pass.
Ship nothing to the current 3.8 GB production node until it has headroom or is
replaced/upgraded.

## 8. Why it is worth doing (cold argument)
180+ people tried to mine and hit the node-setup wall — that is **latent demand,
not disinterest**. Removing the wall (safely) is plausibly what turns SOST from
"one operator holds it up" into "many miners, self-healing". That is a strong
reason to design it right, and an equally strong reason NOT to bolt it onto the
production node in a hurry.
