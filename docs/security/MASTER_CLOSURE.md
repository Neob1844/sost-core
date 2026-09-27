# SOST — MASTER CLOSURE (DONE / TESTING / BLOCKED) + continuation checkpoint

Deadline snapshot: real mainnet height **28,142** (2026-09-27) → **~1,758 blocks to #29,900** (~12 d),
~1,858 to #30,000 (V16 activation, OWNER-LOCKED). Nothing published/deployed/merged-to-main.
Peers in all adversarial tests are a **protocol-accurate Python simulator**, NOT independent real nodes.

## Branches (dev, on GitHub)
| branch | commit | content |
|---|---|---|
| `release/v16.3.0-sec1-rpc` (sec2) | 19186bab | sec1 hardening + RPC dispatch/parser fixes (node-only) |
| `fix/rpc-crash-hardening` | eb2dd5b9 | the two RPC DoS fixes (isolated) |
| `fix/rpc-proxy-interim-mitigation` | 52612101 | public-gateway param-shape validation (interim) |
| `fix/ibd-mining-gate` | 7ad9aba0 | stale-tip mining gate v2 (node+miner) |
| `feat/p2p-headers-first-ibd` | 796b0094 | P2P convergence + fast-sync (frozen) |
| `integration/sec2-p2p-ibd` | e0c8a57d(+) | INTEGRATED candidate (sec2+P2P+ibd-gate) |
| `test/security-gauntlet` | b29b4898 | gauntlet harnesses (cASERT/D/E) |
| `feat/wallet-coin-selection` | 62b34f7b | coin-selection AUDIT+DESIGN (impl deferred) |
| `feat/btc-atomic-swap-complete` | 12b81dca | BTC atomic swap code-complete (regtest pending) |

## DONE (verified, reproducible)
- **sec2 node** `5b50a448` (miner/cli `2ef9d0a7`/`489f4374` == v16.3.0). ctest 119/119; both RPC DoS
  fixed (getblockhash abort, getblock OOM); mainnet-profile compiles; reorg/payout E2E pass.
- **Integrated candidate** node `c0c21da0`/miner `5a29cad4`/cli `489f4374`. Merge: 1 orphan-store
  conflict resolved (sec1 quota + P2P dedup guard combined); ibd-gate 0 conflicts.
- **Full mainnet sync** genesis→tip **28,077 in 25m06s** on the integrated binary; tip hash + h=1/12000/
  20000/25000 match public RPC; emission at #25000 correct (50% miner split). *(Sync source was an
  already-synced local peer; chain content is real, hash-verified.)*
- **cASERT bit-exact:** 14,896 vectors, 0 divergences (active regime, recompiled vs integrated source).
- **66 historical exceptions:** 66/66 hashes match the live mainnet chain (positive); a corrupted
  replay-exception hash (5150) makes sync STALL at 5149 with a **bits_q consensus mismatch (NOT
  PoW-invalid)** — proving the guard is exact-hash-gated, the exception is necessary, and the reject
  path is isolated. (Param table →5038, replay table →5410.)
- **Gauntlet:** RPC fuzz, block-reception fuzz, 200-peer adversarial lab (RSS flat, 0 crash, 0 unfair
  ban), reorg E2E, jackpot_v2 9/0, ASan+UBSan 0, **TSan 0 races** (mining+P2P+reorg+RPC concurrent),
  CPU-DoS (141 req/s RSS flat), durability (corrupt/truncated/empty chain → fail-safe).
- **IBD mining gate v2:** attacker-independent (checkpoint-height, not peer-announced); 5/5 tests
  (liar/colluding→mines; genesis→refuses; solo→mines).
- **ENOSPC/write-fail:** code audit — `f.good()` gates the rename (no partial promoted); real
  partial-write reproduction (isolated SIGXFSZ) → real chain.json byte-intact, restart recovers.
- **V16 literal mainnet-height predicates:** 30000=activation (NOT jackpot), 30186=first V2 jackpot,
  NODE_BIND/heartbeat on-chain gate = h>=30000 (rejected at BOTH mempool and ConnectBlock before);
  cadence 288 (30474 next).
- **ConvergenceX header audit:** PoW needs the full transcript → NOT header-verifiable → headers-first
  stays OUT of the candidate; chain selection = highest VERIFIED work.

## TESTING (partial coverage — explicitly NOT PASS)
- **Exact ENOSPC:** covered the *interrupted/failed write* path (SIGXFSZ + open-fail + f.good() audit),
  NOT a byte-exact `ENOSPC` on a real full volume (needs a disposable size-capped FS / privileges).
  No corruption in any case tested; the fsync gap below is the real residual.
- **Power-loss durability:** save does `flush+close+rename` with **NO fsync** of the file or directory.
  Process-crash-safe (proven 5/5 SIGKILL). Power/OS-loss could lose the *most recent* save (recoverable
  by re-sync; atomic rename still guarantees a consistent file → no corruption). FIX (proposed, not
  coded, needs its own test): fsync(tmp fd) before rename + fsync(dir) after.
- **V16 full mainnet transition:** the literal-height *predicates* are verified; the full state machine
  (NODE_BIND/heartbeat/eligibility/no-winner/rollover/reorg/valid+invalid payout) is exercised by
  `run_v16_devnet_jackpot_v2` (9/0) + rollover/autohb tests at SCALED devnet heights (same code path).
  Reaching literal 30000 by mining is a ~1 h run; a height override is forbidden.

## BLOCKED — owner authorization (sec2 = urgent, independent of the integrated candidate)
- **A. Proxy mitigation** (lowest-scope, with verify+rollback) — prepared, lab-verified, NOT applied.
- **B. Publish `sost-node-sec2`** on the v16.3.0 release (no tag move, no asset overwrite) — prepared.
- **C. STRATO reversible swap** (backup+health-checks+rollback) — plan complete, NOT executed.
- ⚠️ **RISK STANDING:** the two RPC DoS are unauthenticated and reachable via the public gateway;
  **STRATO is NOT protected until at least A is authorized.** This is the top operational priority.

## BLOCKED — external / third-party
- **Seed DNS records:** `seed-eu/us/apac.sostcore.com` and `seed.sostcore.com` DO NOT RESOLVE; only
  `sostcore.com`→STRATO resolves. New-operator bootstrap therefore depends on STRATO or `--connect`.
  Fix requires the owner to populate the seed DNS A-records (owner DNS action) AND/OR code below.
- **Independent security audit** (atomic swap + node) — package to be prepared (Fase 7).
- **Three independent external operators + 2 independent miners** for the 24 h decentralization test.
- **Exchange acceptance / listing.**

## RESIDUAL RISKS / FINDINGS
1. **Decentralization NOT yet achieved:** no peer persistence (no peers.json/addrman) + seed DNS not
   resolving → bootstrap depends on STRATO. Needed: (a) owner DNS seed records [external]; (b) peer
   persistence to disk [code, not done]; (c) resolvable community seeds / anchor peers [code+ops].
2. **Save durability:** no fsync (power-loss can drop the latest save; no corruption).
3. **Mining after persistent save failure:** node keeps mining in memory; recent unsaved blocks lost on
   crash (recoverable via re-sync; no consensus harm). Proposed policy: halt getblocktemplate after K
   save failures (local-triggered, not peer-exploitable) — implement+test on a branch.
4. **IBD gate:** a node synced above the checkpoint but below the tip mines soon-orphaned blocks
   (non-catastrophic; min-chainwork floor = release-time tightening).

## CONTINUATION CHECKPOINT (next-session tasks, NOT started / partial — do NOT repeat DONE items)
- **Fase 3 coin selection** (`feat/wallet-coin-selection`): audit+design DONE; IMPLEMENT the unified
  selector (BnB + effective-value + waste + safe fallback, stocks/byte fee, change/dust/insufficient,
  strict --from, exclude immature coinbase + Gold-Vault/PoPC locks), preserve monetary invariants,
  test CLI/PSBT/web + ANTES/DESPUÉS benchmark. **Next action:** unify the ≥4 duplicate selectors in
  src/wallet.cpp (lines ~358/608/716/813).
- **Fase 4 Explorer/PoPC** (`feat/explorer-drilldown-wallet-popc` / `feat/explorer-circulating-supply-…`):
  balance drill-downs, cursor-paginated READ-ONLY history RPC (strict limits, keep off public gateway),
  classify balance categories honestly (no same-owner transfers as income), retire misleading PoPC
  localStorage "registration" UI, keep historical data + consensus intact.
- **Fase 5 Bretton Woods:** single-source `1 SOST = 31.1034768/35 mg gold` (=0.888670765…mg),
  explicit "reference only, no backing/reserve/redemption/price guarantee"; sweep web/Explorer/charts/docs.
- **Fase 6 installers/exchange package + BOOTSTRAP FIX:** Win/Linux reproducible install, SHA-256/SBOM,
  exchange integration folder (RPC/deposits/withdrawals/confirmations/reorg), automated integrator
  test-bench; **implement peer persistence + resolvable-seed strategy so a clean machine bootstraps
  WITHOUT STRATO**; prepare the 24 h protocol (mark real run BLOCKED-EXTERNAL).
- **Fase 7 atomic swap** (`feat/btc-atomic-swap-complete`): audit; run SOST/BTC on real bitcoind REGTEST
  (fund/sign/claim/refund/bad-preimage/malicious-counterparty/reorg/coordinator-crash/recovery); refresh
  threat model; prepare external-audit package; BTC mainnet stays OFF, no real funds.

## Recommended deployment order (Fase 8; each separate, each with its own rollback)
1. **sec2** (urgent, node-only) — after authorization A→B→C.
2. **Integrated node+miner** candidate — after its own release gate (post-sec2).
3. **Wallet** (coin selection).
4. **Explorer/web** (incl. Bretton Woods).
5. **Third-party integration tools.**
6. **BTC atomic swap** — audit + authorization gated.
Keep per-component regression suites; do NOT bundle into one deployment.
