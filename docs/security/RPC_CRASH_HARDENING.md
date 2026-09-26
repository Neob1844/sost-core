# RPC crash hardening — two pre-existing remote-DoS defects found by fuzzing

Branch: `fix/rpc-crash-hardening` (off `main`, NOT merged). Found while fuzzing the modified
P2P node; confirmed PRE-EXISTING on `main` (both reproduce on an unmodified base binary), so
they are unrelated to the P2P convergence work. Both are triggerable by a single
unauthenticated JSON-RPC call.

## Defect 1 — uncaught exception aborts the node
`{"method":"getblockhash","params":["str"],"id":1}` → `handle_getblockhash` calls
`std::stoll(p[0])` on a non-numeric string → throws `std::invalid_argument` → uncaught →
`std::terminate` → the whole node aborts. Several other handlers parse params with
`std::stoll/stoul/stod`, `from_hex`, or vector indexing that throw the same way.

**Fix:** wrap the handler invocation in `dispatch_rpc` in try/catch, returning a JSON-RPC
error (-32603) for any uncaught handler exception. Single-point, comprehensive, defensive —
valid calls unaffected, no consensus path touched.

## Defect 2 — malformed params OOM-kill the node (worse)
`{"method":"getblock","params":[[[[1]]]],"id":1}` → `json_get_params` tokenizer, on a nested
array/object, leaves the cursor ON a `]`/`}` (a delimiter), so `find_first_of` returns the
cursor position itself: the token is empty and the cursor never advances — an **infinite loop
appending "" to the params vector until the process OOMs** (~6 GB per call, measured; a few
calls drive RSS past 13 GB and the kernel OOM-kills the node; dmesg: "Out of memory: Killed
process sost-node, total-vm:41GB").

**Fix:** if the delimiter sits at the cursor (`p==i`), advance past it (`i++`) instead of
emitting a zero-length token and looping. Plus a defense-in-depth cap (`r.size()>256`) since
no RPC method takes anywhere near that many params.

## Verification (fixed binary)
- `getblockhash "str"` → clean RPC error, node alive.
- `getblock [[[[1]]]]` → "Block not found" error, **RSS flat at 9 MB** (was 6 GB → OOM).
- Fuzz: 300 malformed calls (garbage bodies, nested arrays/objects, huge hex, nulls, huge
  ints) → node responsive throughout, **RSS bounded at 9 MB**.
- Valid RPC unaffected: `getblockhash[2]`, `getblock[<hash>]` return correct results.
- Compiles clean in the mainnet profile; devnet reorg 9/0 and payout 9/0 E2E PASS.

## Exposure & status
These affect `main`/production. Whether reachable externally depends on which methods the
public RPC proxy exposes (the proxy allows only `sendrawtransaction` publicly and blocks admin
methods), but any local/authorised RPC client can crash the node, and Defect 2 is a severe
amplification (6 GB/call). Recommend landing before block 29,900 given the "stable, secure
node" priority. Branch only — no merge/publish/deploy without owner authorization. Kept
separate from the P2P convergence branch and from sec1.
