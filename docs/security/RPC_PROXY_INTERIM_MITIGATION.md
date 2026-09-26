# Interim mitigation — public RPC gateway param validation (pre-sec2)

**Purpose:** reduce exposure of the two pre-existing RPC DoS defects (see
`RPC_CRASH_HARDENING.md` / `V16_3_0_SEC2_COMBINED.md`) DURING the window before the sec2 node
is deployed. Config/infra change to the public gateway only — **no node binary, no consensus,
no tag change.** NOT applied to production by this branch (prepared + lab-tested only).

## Why nginx alone cannot mitigate
Both exploits use tiny payloads: defect 1 (`getblockhash ["str"]`) is a single call; defect 2
(`getblock [[[[1]]]]`) is well under the 16 KB body cap and needs only 2–4 calls to OOM. The
10 r/s / burst-5 limit does not stop either. Removing the methods from public exposure would
break the block explorer (it calls both). So the mitigation must be **param-shape validation**.

## The mitigation (`ops/sost-rpc-proxy.py`)
`bad_public_params(method, params)` validates the shape of the two crash-prone anonymous reads
and the gateway returns HTTP 400 (`-32602 invalid parameters`) before forwarding:
- `getblockhash`: exactly one integer (or integer-string).
- `getblock`: first param a 64-char hex string.
Everything else is unchanged. Valid explorer calls (`getblockhash [<int>]`,
`getblock ["<64hex>"]`) pass through untouched.

## Lab verification (proxy in front of the ORIGINAL, UNFIXED sec1 node)
```
getblockhash ["str"]  -> 400 {"code":-32602,"invalid parameters"}   node ALIVE
getblock [[[[1]]]]    -> 400 {"code":-32602,"invalid parameters"}   node ALIVE (RSS unchanged)
getblockhash [5]      -> 200  real block hash
getblock ["<hash>"]   -> 200  {"height":5}
```
The unpatched node survived both culprit inputs because the gateway rejected them; valid
calls still work. This confirms the gateway patch protects production **without** the node swap
and **without** breaking the explorer.

## Deployment (execute ONLY on owner authorization; lower risk than the node swap)
1. Back up the current `ops/sost-rpc-proxy.py` on STRATO.
2. Replace it with this branch's version (constants `NODE_URL`/`RPC_ENV`/`LISTEN` unchanged).
3. `systemctl restart sost-rpc-proxy`; confirm it comes up (journald `[rpc-proxy]` lines).
4. Verify: the two culprit inputs return 400 through `/rpc`; explorer still renders blocks.
5. Rollback = restore the backup + restart. No node/chain state involved.
Remove this mitigation once the sec2 node is deployed (the node then handles the inputs safely).
