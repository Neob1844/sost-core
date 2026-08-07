# DEVNET_FAST — isolated fast-mine development chain (design + SbPoW audit)

Status: **SPEC + audit complete (2026-08-04).** Not yet implemented. This is the
prerequisite for the V15 real-node runtime suite (acceptance / atomicity /
disconnect / reorg / restart / reindex over a mined chain). Branch
`feat/v15-jackpot-explorer-card`.

## 1. SbPoW 4 GB-per-block audit — DECISION GATE (PART 2–3)

**Question:** is regenerating ~4 GB per block a cache bug or intended?

**Answer: INTENDED. Not a bug.** Code evidence (`src/pow/convergencex.cpp`):
- `CXDataset::generate(block_prev_hash)` sets `seed_hash = block_prev_hash` and fills
  512M×uint64 = 4 GB (lines 44–64). The dataset seed **is the previous block hash**
  (`compute_dataset_seed`, lines 25–30).
- `is_valid_for(prev_hash)` hits only when `seed_hash == prev_hash` (lines 66–68). In a
  growing chain every block has a new prev_hash, so the cache legitimately cannot reuse
  across blocks — that per-block binding is the ASIC-resistance property. "Fixing reuse"
  would weaken consensus security. Do NOT touch it.

**Who pays the 4 GB:**
| Path | Function | Cost |
|---|---|---|
| Miner nonce search | `convergencex_attempt` (line 306) | builds 4 GB |
| Miner winning-block witness | `generate_transcript_witnesses` (line 896) | builds 4 GB |
| **Node block validation** | `verify_cx_proof` (line 740, called `sost-node.cpp:6016`) | **O(1) `compute_single_dataset_value` — no 4 GB** |

So the ~0.43 blk/s bottleneck is **miner-side** dataset construction; the validator is
already efficient. Combined with cASERT targeting 600 s of *real* time per block and the
Phase2 time-hard gate, there is **no cache fix** that makes the normal testnet reach
V15=12500 quickly. An isolated fast chain with trivial difficulty is genuinely required.

## 2. What already exists (big head-start)

Network identity is a **runtime `Profile`** axis, ORTHOGONAL to the compile-time
`SOST_TESTNET_FORKS` schedule axis. And a third profile already exists:
- `enum class Profile { DEV=0, TESTNET=1, MAINNET=2 }` (`params.h:20`).
- Distinct `MAGIC_DEV[10]` bytes (`params.h:29`) → **P2P network isolation already present**.
- `magic_for_profile()` / `MAGIC_STR_BYTES()` already switch on it (`params.h:33–43`).
- `sost-node`/`sost-miner` already accept `--profile dev`.

So PART 5's "unique network magic / chain identity" is **already built** for DEV. What is
missing is the fast *schedule* + trivial *PoW* + isolated *ports/datadir* + guards/tests.

## 3. Remaining build plan (concrete touch-points)

1. **DEV fast schedule.** The schedule is currently a 2-way compile switch
   (`#ifdef SOST_TESTNET_FORKS`). Add a DEV branch (or a runtime schedule table keyed by
   Profile) with low, coherent heights, e.g. Phase2=10 < V13=20 < DTD gate=25 < V15=30 <
   first J=36 (draw-aligned %3==0) < eligibility=50, cadence=12. Must preserve ordering
   invariants and reuse the existing `static_assert` pattern per network. Mainnet/testnet
   values unchanged.
2. **Trivial DEV PoW.** Add a dev-only easy target so `convergencex_attempt` finds a valid
   nonce in a few tries AND skips the 4 GB bulk build (use `compute_single_dataset_value`
   O(1) for the handful of lookups). Must still require a real nonce/hash relation and
   validate via the SAME `verify_cx_proof` path (no `if devnet return true`). Gate strictly
   to `Profile::DEV`.
3. **Relaxed temporal gates for DEV only** (spacing / MTP / future-drift) so blocks need not
   wait real minutes; harness assigns monotonically increasing timestamps. Never disable
   timestamp validation globally.
4. **Isolated ports/datadir.** `P2P_PORT_DEFAULT=19333`, `RPC_PORT_DEFAULT=18232`
   (`sost-node.cpp:245–246`) — add DEV defaults (e.g. 19555/18555) + a DEV datadir.
5. **Guards.** Compile-time: dev-fast PoW support only in dev/test builds. Runtime: abort on
   `MAINNET|TESTNET + fast rules`; allow only `Profile::DEV`. Hard failure, not a warning.
6. **Isolation tests (mandatory, PART 11):** mainnet/testnet reject DEV genesis/blocks; DEV
   rejects mainnet/testnet identity; DEV magic/datadir/ports differ; a fast-PoW block is
   invalid under normal validation; mainnet binary cannot activate fast rules by accident.
7. **Harness:** `tests/run_v15_devnet.sh` (extend the existing `run_v15_local_testnet.sh`)
   pointed at `--profile dev`, running the full PHASE C+ jackpot suite.

## 4. Then: the two-tier evidence (PART 27–28)

- **DEVNET functional soak** — fast: many blocks, many J events, reorgs, restarts, rollover
  cap, reserve reuse. Proves correctness quickly.
- **Normal testnet realism soak** — slow (~8.5 h+): real SbPoW, real timing, stability. Run
  under nohup/systemd; report RUNNING; never PASS before first J.

Do not mark V15 mainnet-ready from DEVNET alone.
