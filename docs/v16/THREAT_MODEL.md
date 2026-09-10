# V16 — DTD Jackpot V2 · Threat Model (living document)

Activation **#30,000** (owner-locked). DTD-normal untouched. NODE = eligibility
gate; PoW = linear weight; no jackpot cooldown; no jackpot anti-dominance.

Status legend:
- **TESTED** — mitigation implemented AND covered by a passing unit test.
- **DESIGN** — mitigation fixed by the design; enforced by tested pure logic.
- **OPEN** — to be enforced at the ConnectBlock/DisconnectBlock + mempool wiring
  (next increment); listed here so the wiring is written against it, not blindly.

Fail-safe: any finding that could split consensus / create SOST / spend the
reserve wrongly / make selection non-deterministic / allow replay-double-heartbeat
/ cause severe DoS is escalated as **BLOCKER = / SEVERITY = / CAUSE = / FIX = /
TEST =** and fixed before #30,000 — never silently patched.

---

### A. NODE_BIND replay
- SEVERITY: medium
- EXPLOIT: rebroadcast an old NODE_BIND to reactivate a stale/compromised node key.
- CONSENSUS IMPACT: wrong active binding.
- MITIGATION: per-miner **strictly-increasing `bind_seq`**; a bind with seq ≤ the
  miner's max accepted is ignored by `jv2_derive_bind_state`. Message binds seq, so
  it cannot be re-used for a different seq.
- TEST: `bind_seq replay/stale ignored`, `NODE_BIND seq mismatch vs signed message`. **TESTED**

### B. heartbeat replay (cross-epoch)
- SEVERITY: medium
- EXPLOIT: replay an epoch-e heartbeat as epoch e+1.
- CONSENSUS IMPACT: fabricated participation history.
- MITIGATION: `epoch_idx` + `tip_ref_hash` are signed; a heartbeat is valid only if
  `epoch_idx == epoch_of(inclusion_height)` AND `tip_ref_hash` matches that epoch —
  so it cannot count for any other epoch.
- TEST: `wrong-epoch heartbeat rejected`, `bad tip_ref rejected`. **TESTED**

### C. duplicate heartbeat (same epoch)
- SEVERITY: low
- EXPLOIT: submit many heartbeats for one epoch to inflate the count.
- CONSENSUS IMPACT: none on weight (heartbeat never adds weight); could pad chain.
- MITIGATION: eligibility counts **distinct epochs per mining_pkh** (`std::set`),
  so duplicates give zero benefit. Mempool must also drop the 2nd per (miner,epoch) — **OPEN** (mempool).
- TEST: `miner2 dedup: 2 records same epoch -> 1`. **TESTED (consensus count)** / OPEN (mempool policy)

### D. future heartbeat pre-signing
- SEVERITY: medium
- EXPLOIT: pre-sign heartbeats for future epochs to look live without following the chain.
- CONSENSUS IMPACT: fake liveness.
- MITIGATION: `tip_ref_hash` = hash of `epoch_start(e)-1`, unknown until that block
  exists; a heartbeat referencing a future epoch fails `epoch_of(inclusion)` and/or
  tip_ref. No pre-signing possible.
- TEST: `wrong-epoch heartbeat rejected`. **TESTED**

### E. heartbeat from a stale fork
- SEVERITY: medium
- EXPLOIT: include a heartbeat whose tip_ref is from an orphaned fork.
- CONSENSUS IMPACT: divergence if validators disagree on tip_ref.
- MITIGATION: tip_ref is checked against the **canonical block hash** at
  `epoch_start(e)-1` on the connecting chain; a stale-fork tip_ref mismatches and is rejected.
- TEST: `bad tip_ref rejected` (unit) — full canonical-lookup path is **OPEN** (ConnectBlock).

### F. reorg around an epoch boundary
- SEVERITY: high
- EXPLOIT: reorg that moves a heartbeat across an epoch edge.
- CONSENSUS IMPACT: orphaned/duplicated participation state.
- MITIGATION: state is a record list; `undo_*` pops exactly; queries recompute from
  the list, so post-reorg state == fresh recompute of the new chain. Boundary math
  frozen (epoch e = [A+e·288, A+(e+1)·288−1], completed strictly before H).
- TEST: `incremental state == fresh from-chain recompute`, boundary tests
  `#30,287/#30,288/#30,575/#30,576`. **TESTED (pure)** / OPEN (ConnectBlock undo wiring).

### G. reorg around a jackpot height
- SEVERITY: high
- EXPLOIT: reorg re-selects a different winner or double-pays.
- CONSENSUS IMPACT: fund safety.
- MITIGATION: winner is a pure function of (canonical entropy, eligible set, height);
  recomputed on the connecting chain. Payout reuses the V15 rollover/reserve machinery
  (supply-neutral, one winner). Wiring = **OPEN** (ConnectBlock), to reuse `hist_jackpot_apply`.
- TEST: winner determinism + 0/1-eligible (pure). **TESTED (pure)** / OPEN (block path).

### H. node-key theft / rotation
- SEVERITY: medium
- EXPLOIT: attacker steals a node key.
- CONSENSUS IMPACT: attacker heartbeats as the victim (no weight gain; weight is PoW).
- MITIGATION: owner rotates via a new NODE_BIND (higher seq) signed by the **mining
  key** (root authority); no admin/authority. Old key stays owned (not reusable by others).
- TEST: `rotation -> active key n2`, `undo rotation`, `m2 cannot claim rotated-away n1`. **TESTED**

### I. one node key bound to multiple miners
- SEVERITY: medium
- EXPLOIT: share one node key across miners to pass the gate cheaply.
- CONSENSUS IMPACT: gate bypass.
- MITIGATION: **global uniqueness** — a node_pubkey belongs to exactly one mining_pkh
  (first claimant, by canonical order); later cross-owner binds rejected.
- TEST: `first claimant owns the node key`, `second miner claiming same node key rejected`,
  `node key owned by m1 not acceptable for m2`. **TESTED**

### J. one miner spawning many node keys
- SEVERITY: low
- EXPLOIT: register many node keys to multiply chances.
- CONSENSUS IMPACT: none — node keys are a gate, never weight; only one active binding
  per miner; weight stays PoW-linear.
- TEST: `weight == pow regardless of node participation`, node-Sybil invariance. **TESTED**

### K. mempool heartbeat spam / L. zero-value tx spam
- SEVERITY: medium (DoS)
- EXPLOIT: flood 0-value heartbeats/binds to bloat mempool.
- CONSENSUS IMPACT: none to state; resource exhaustion.
- MITIGATION (planned, **OPEN** — mempool policy): (1) reject a heartbeat that is not
  currently-valid (activation, epoch, tip_ref, active binding); (2) at most one
  accepted heartbeat per (mining_pkh, epoch) and one pending bind per miner; (3)
  require a minimum fee OR bind-must-reference a mining_pkh with ≥1 SbPoW block
  (real prior work) — anti-spam anchor. **Decision needed: fee policy vs work-anchor.**
- TEST: pending mempool tests. **OPEN**

### M. block-size amplification
- SEVERITY: low
- EXPLOIT: pack a block with node txs.
- CONSENSUS IMPACT: chain growth.
- MITIGATION: measured real sizes NODE_BIND=138B, HEARTBEAT=137B; at 5,000
  participants ≈ 2.4 KB/block avg amortized. Cap per-block node-tx count in policy — **OPEN**.
- TEST: byte measurement `NODE_BIND=138B / HEARTBEAT=137B`. **TESTED (size)** / OPEN (per-block cap).

### N/O. weighted-selection & cumulative-weight integer overflow
- SEVERITY: high
- EXPLOIT: craft weights to overflow the draw.
- CONSENSUS IMPACT: non-determinism / wrong winner.
- MITIGATION: integer-only; window ≤ 5000 ⇒ total_weight ≤ 5000 (int64 headroom huge);
  `roll = read_u64_le(seed) % total`; cumulative in uint64. No floats anywhere.
- TEST: `total weight helper`, draw determinism, linear weight. **TESTED**

### P/Q. eligible-address ordering ambiguity / iteration-order divergence
- SEVERITY: critical
- EXPLOIT: rely on map/RPC/db iteration order so nodes disagree on the winner.
- CONSENSUS IMPACT: chain split.
- MITIGATION: **canonical order = raw mining_pkh bytes ascending** before the draw;
  no unordered iteration feeds selection.
- TEST: `winner identical across all input orderings` (all permutations). **TESTED**

### R. jackpot seed manipulation
- SEVERITY: high
- EXPLOIT: grind entropy to steer the winner.
- CONSENSUS IMPACT: unfair selection.
- MITIGATION: seed = `sha256("SOST_HIST_JACKPOT" || canonical recent block hashes ||
  height)` — domain-separated from DTD; entropy is committed chain history (same
  family the DTD selector uses). Grinding requires real PoW on the entropy blocks.
- TEST: `seed differs by height`, `seed reproducible`. **TESTED (seed)** / entropy-source wiring OPEN (ConnectBlock).

### S. miner withholding around a jackpot height
- SEVERITY: medium
- EXPLOIT: withhold a block to alter the eligible set/entropy.
- CONSENSUS IMPACT: marginal selection influence (same class as V15 DTD; the whale
  already influences by producing most blocks — that IS the proportional design).
- MITIGATION: entropy spans a window of recent hashes; weight already reflects real
  work; no cooldown/anti-dominance to game. Documented as accepted (proportional).
- TEST: analysis; monitor in devnet. **DESIGN**

### T. 0 / 1 eligible
- SEVERITY: high (fund safety)
- MITIGATION: 0 eligible ⇒ winner index −1 ⇒ **rollover** (reserve preserved), never a
  forced PoW-only fallback; 1 eligible ⇒ that miner wins (100% weight).
- TEST: `0 eligible -> -1 (rollover)`, `1 eligible -> index 0 wins`. **TESTED**

### U. rollover 100→500
- SEVERITY: medium
- MITIGATION: reuse V15 `hist_jackpot_apply` (base 100, cap 500, reserve-limited,
  supply-neutral). No change to economics.
- TEST: V15 jackpot suite 108/108 (rollover/cap). **TESTED (V15 core)** / V2 wiring OPEN.

### V. activation edge #29,999 / #30,000
- SEVERITY: critical
- MITIGATION: `node_participation_active_at(h) = h ≥ 30000`; below → node txs rejected
  (byte-identical historical replay). `is_hist_jackpot_v2_height` picks V2 rules only
  at jackpot heights ≥ 30000.
- TEST: `#29,999 NODE_BIND rejected`, `#30,000 accepted`; block-level guard in
  ConnectBlock **OPEN**. **TESTED (pure guard)** / OPEN (block path).

### W. first V2 jackpot #30,186
- SEVERITY: high
- MITIGATION: last V15 jackpot #29,898; first V2 #30,186 (bootstrap 0/0 but NODE_BIND
  mandatory); ramp 1/1→2/2→3/3→3/4 permanent at #31,338.
- TEST: bootstrap schedule + `#30,186 NOT bound -> ineligible`. **TESTED**

---

## Open items to resolve at the ConnectBlock/mempool wiring (next increment)
1. ConnectBlock accepts NODE_BIND/HEARTBEAT only at h≥30000 (mirror htlc_ok/jackpot_ok),
   handling 0-input/0-output protocol txs without touching the UTXO set.
2. Apply/undo NodeState in ConnectBlock/DisconnectBlock; reorg reindex parity test.
3. Canonical tip_ref + entropy lookups from the connecting chain.
4. **Fee / anti-spam policy decision**: minimum fee vs "bind requires ≥1 SbPoW block"
   work-anchor (recommended: work-anchor for bind + 1-per-(miner,epoch) accept cap for
   heartbeats + per-block node-tx cap). Consensus validity vs mempool policy separated.
5. Wire V2 eligibility+weight+seed into the jackpot payout path (reuse hist_jackpot_apply).
