# V6 Hard Fork — Signature-Bound PoW (Non-Outsourceable Puzzle)

**Status**: Design draft — NOT for implementation. Reserve weapon for the day pool centralization becomes a measurable problem.
**Author / context**: Drafted as a contingency design while SOST is still in early mainnet (block ~4400). Do NOT discuss publicly. Keep in `docs/internal/`.
**Target version**: ConvergenceX v3.0 / SOST protocol fork V6.
**Estimated implementation effort**: ~200-400 LOC across 5-6 files + test suite. ~2-4 weeks of focused work for one engineer who already knows the codebase.

---

## 1. Threat model

### What we are defending against

A **mining pool operator** that aggregates the hashrate of many independent participants into a single block-finding entity, redistributing rewards proportional to "shares" submitted.

Specific failure modes we want to prevent or make economically unattractive:

1. **Hashrate concentration** — a single pool controls >25% of network hashrate, becoming a censorship vector and a 51% precursor.
2. **Coinbase address concentration** — the pool's payout flow makes one address (or a small rotating set) dominant in coinbase rewards, undermining the "many independent miners" property that SOST's PoPC + gold-backing narrative rests on.
3. **Out-of-band coordination** — the pool operator can refuse to include certain transactions (censorship), prioritize their own, or sell blockspace privately, eroding the censorship-resistance guarantee.
4. **Single point of regulatory attack** — pools are legal entities or identifiable operators. A single subpoena collapses 30%+ of network hashrate. SOST's "post-fiat infrastructure" thesis is incompatible with this.

### What we are NOT defending against

- **Solo miners with large hashrate**. A single honest miner running 100 machines is fine. Anti-pool defenses must not penalize them.
- **Miners that share hardware** (e.g. someone runs sost-miner on their friend's PC). That's fine.
- **Cooperative protocols where each participant retains key sovereignty** (e.g. P2Pool-style decentralized pools where each miner signs their own block). These are pool-shaped but not pool-functional, and our defense should leave them untouched.
- **Statistical clustering** (e.g. miners in the same datacenter). Geographic or ISP centralization is a separate, network-layer problem.

### Why heuristic detection is the wrong answer

Any defense based on "detect address X has >Y% of recent coinbase rewards and penalize it" creates:

- **False positives** against legitimate large solo miners.
- **Trivial evasion** by rotating coinbase addresses.
- **Self-DoS surfaces** (an attacker can sabotage you by forcing rewards to your address).
- **Subjective protocol rules** (the protocol decides what patterns are "good"), which is philosophically incompatible with SOST.

We want a **structural** defense: a property that makes pool operation mathematically incompatible with the consensus rules, not a heuristic that flags suspicious behavior.

---

## 2. Approach: signature-bound PoW

### The idea in one sentence

Modify the PoW victory predicate so that finding a valid block requires a **signature over the PoW commitment with the private key of the miner**, and require that the **coinbase pays to the address derived from that same public key**. A pool operator must therefore either give every worker the pool's private key (suicide — any worker can steal blocks) or do all signing centrally (becoming a bottleneck and defeating distribution).

### Academic precedent

This design is grounded in the line of work on *non-outsourceable puzzles*:

- Miller, A., Kosba, A., Katz, J., Shi, E. — *Nonoutsourceable Scratch-Off Puzzles to Discourage Bitcoin Mining Coalitions* (CCS 2015).
- Several altcoins have explored variants (notably some early proposals around Permacoin and related schemes).

None of the deployed PoW chains today uses this defense at the consensus layer. SOST would be the **first major PoW chain with structural pool resistance**. This is consistent with SOST's positioning as opinionated, post-fiat infrastructure.

### Why this defeats every existing pool model

Consider the three actual pool designs in production today:

| Pool model | What we break |
|---|---|
| **PPS / PPLNS over Stratum** (ckpool, NOMP, ViaBTC). Operator has one key, distributes work to thousands of workers. | Workers submit nonces but cannot produce a valid signature without the operator's privkey. The operator has to sign every candidate centrally → workers become useless, the operator IS the miner. |
| **P2Pool-style decentralized pools**. Each miner has their own key, shares are aggregated via a side chain. | Already compatible. Each peer signs their own blocks. We do not break this — and that is desirable, because P2Pool-shaped systems preserve key sovereignty. |
| **Cloud / hosted mining** (NiceHash, MiningRigRentals). The buyer rents hashrate; the seller runs the miner. | Buyer gives seller a coinbase address. After the fork, the buyer must also give the seller the **private key** corresponding to that address — which means the seller can steal everything. Economic model collapses. |

The first model (the dominant one in BTC) and the third model (the dominant one in altcoin marketplaces) are both broken. The middle model is preserved. This is the desired outcome.

---

## 3. Concrete protocol changes

### 3.1 Current state (V5, block ~4400+)

#### Block header (96 bytes, `include/sost/block.h:43`)
```
version (4) || prev_hash (32) || merkle_root (32) || timestamp (8)
            || bits_q (4) || nonce (8) || height (8)
```

#### PoW header_core (`hc72`, 72 bytes, fed into ConvergenceX)
```
prev_hash (32) || merkle_root (32) || ts_u32 (4 LE) || bits_q (4 LE)
```
Built by `BlockHeaderToCore72` in `block.h:131` and `build_hc72` in `sost-miner.cpp:98`.

#### Full header bytes for block_id computation (`sost-miner.cpp:81`)
```
MAGIC || "HDR2" (4) || hc72 (72) || checkpoints_root (32) || nonce (4) || extra (4)
```

#### Win predicate (`sost-miner.cpp:828`)
```cpp
if (res.is_stable && pow_meets_target(res.commit, bits_q)) {
    // BLOCK FOUND
}
```

`res.commit` is a 32-byte hash output from the ConvergenceX attempt — the "PoW result" that gets compared to the difficulty target.

#### Coinbase reward (`sost-miner.cpp:146`)
The coinbase already binds the reward output to `miner_pkh` (a 20-byte PubKeyHash):
```cpp
TxOutput out_miner;
out_miner.amount       = split.miner;
out_miner.type         = OUT_COINBASE_MINER;
out_miner.pubkey_hash  = miner_pkh;   // <-- bound here
```
This is the lever we exploit: V5 already requires `miner_pkh` to be present. V6 will require it to **match the public key that signed the PoW commitment**.

---

### 3.2 New state (V6)

#### New consensus rule

> A block at height `h ≥ V6_ACTIVATION_HEIGHT` is valid if and only if:
> 1. The existing V5 rules pass (CASERT bits, stability filter, ConvergenceX correctness, transaction validity).
> 2. The block contains a `miner_pubkey` field (33 bytes, secp256k1 compressed) and a `pow_signature` field (64 bytes, ECDSA secp256k1 over `commit`).
> 3. `verify_ecdsa(miner_pubkey, message=commit, signature=pow_signature) == true`.
> 4. `pow_meets_target(SHA256(commit || pow_signature), bits_q) == true`.
>    *Note: this replaces the V5 predicate `pow_meets_target(commit, bits_q)`.*
> 5. `coinbase.outputs[0].type == OUT_COINBASE_MINER`.
> 6. `coinbase.outputs[0].pubkey_hash == HASH160(miner_pubkey)`.
> 7. *(Optional, recommended)* `pow_signature` is in low-S canonical form (BIP-62) to prevent malleability.

Rules 2-4 force the miner to **possess the private key** in order to find a block.
Rules 5-6 force the miner to **receive the reward at the address derived from that same key**, closing the loophole where a pool could sign with one key but pay out elsewhere.

#### Header format change

The 96-byte V5 header is unchanged. The new 97 bytes (`miner_pubkey` + presence flag) are placed in a new optional trailer that only exists for `version ≥ 2`:

```
V6 BlockHeader (193 bytes):
  version (4)          = 2  // bumped
  prev_hash (32)
  merkle_root (32)
  timestamp (8)
  bits_q (4)
  nonce (8)
  height (8)
  miner_pubkey (33)    // NEW — secp256k1 compressed
  pow_signature (64)   // NEW — ECDSA over commit
                       ─────
                       193 bytes
```

Why bump the version: trivially identifies pre-fork vs post-fork blocks for nodes during the grace period; SPV proofs and explorers can switch parsers based on `version`.

#### PoW attempt loop change

In `convergencex_attempt` (`src/pow/convergencex.cpp:285`), after computing `commit`, two extra steps:

```cpp
// V6: sign the commit with miner's privkey
Bytes64 sig = ecdsa_sign_low_s(g_miner_privkey, commit);

// V6: new effective hash binds commit + sig together
Bytes32 effective = sha256_concat(commit, sig);

// Existing target check, but against `effective` instead of `commit`
if (res.is_stable && pow_meets_target(effective, bits_q)) {
    res.pow_signature = sig;
    return res;  // BLOCK FOUND
}
```

Note: the `is_stable` check is **unchanged**. CASERT stability semantics are orthogonal to this defense.

#### Verification path change

In `sost-node.cpp::process_block` (called by `submitblock`, line 1137), after the existing PoW verification:

```cpp
// V6: verify miner_pubkey + signature
if (block.header.version >= 2) {
    if (!ecdsa_verify_low_s(block.header.miner_pubkey,
                             res.commit,
                             block.header.pow_signature)) {
        return reject(block, "V6: bad pow_signature");
    }
    Bytes32 effective = sha256_concat(res.commit, block.header.pow_signature);
    if (!pow_meets_target(effective, block.header.bits_q)) {
        return reject(block, "V6: effective hash above target");
    }
    PubKeyHash expected_pkh = hash160(block.header.miner_pubkey);
    if (block.txs[0].outputs[0].pubkey_hash != expected_pkh) {
        return reject(block, "V6: coinbase mismatch with miner_pubkey");
    }
}
```

#### Difficulty re-targeting

CASERT BitQ + Equalizer are **untouched**. The new effective-hash predicate has the same statistical distribution as the old commit-only predicate (signatures are pseudorandom uniform), so the difficulty curve does not change. **No CASERT recalibration is needed at fork time.**

---

## 4. Migration plan

### 4.1 Activation strategy

**Hard fork at block `V6_ACTIVATION_HEIGHT`** (to be determined ~6 weeks before activation, based on observed block rate at the time).

Phased rollout:

| Phase | Window | Behavior |
|---|---|---|
| **Announcement** | 4 weeks before activation | New miner binary published; validators notified; explorer + dashboards updated |
| **Soft transition** | 1000 blocks before activation | Both V5-style and V6-style blocks accepted; V6 binaries produce V6 blocks, old binaries still work |
| **Activation height** | block `V6_ACTIVATION_HEIGHT` | Strict: only V6 blocks accepted from this height onwards |
| **Sunset** | activation + 144 blocks | Old miners that haven't upgraded are forked off the canonical chain |

The 1000-block grace period (~7 days at 10-min target) is enough for solo miners to recompile and redeploy without coordination panic.

### 4.2 Backwards compatibility

**None.** This is a hard fork. Old miner binaries cannot produce valid post-fork blocks. Old node binaries will reject post-fork blocks.

This is acceptable because:
- The V5 → V6 transition is **planned, not emergency** (we deploy this when pools become a measurable problem, not preemptively).
- The change is small and rebuilds are quick (`make -j$(nproc)` on the existing repo).
- We control the canonical client.

### 4.3 Wallet / address compatibility

User-facing addresses are **unchanged**. SOST addresses are already `HASH160(pubkey)` (Bitcoin-style). Any existing wallet UTXO is spendable post-fork without modification.

The only constraint is on **mining**: a miner must possess the private key whose pubkey hash matches the address they want to receive coinbase to. This is already true for any sane setup — the user runs `sost-miner --address sost1...` with an address derived from a key they control. The change is that the miner must now also have **online access** to that private key, not just the address.

This rules out one V5 pattern: mining to a "cold" address whose private key lives offline in a hardware wallet. Post-V6, mining requires a hot key. We accept this tradeoff because:
- The hot key is only used for mining, not for spending.
- A miner can use a dedicated key separated from their long-term storage.
- Coinbase outputs are subject to coinbase maturity (`COINBASE_MATURITY` blocks) — by the time funds are spendable, the miner can have moved them to a cold address anyway.

### 4.4 Rollback plan

If the fork goes catastrophically wrong (consensus split, signature scheme bug discovered post-deployment, etc.), the rollback is to publish a hotfix client that disables the V6 rules at a specific height and re-org back to the last known-good V5 state. This is painful but possible because we control the canonical client and the network is small enough to coordinate via direct comms.

We **must** dry-run V6 on testnet for at least 30 days before mainnet activation. Skipping this is unacceptable.

---

## 5. Open questions

These are unresolved at the time of writing. Each must be answered before V6 implementation begins.

### Q1. Signature scheme: ECDSA or Schnorr?

ECDSA secp256k1 is already used elsewhere in the codebase (transaction signatures). It works, it's audited, and verification is fast. **Default choice: ECDSA**.

Schnorr (BIP-340) has nicer properties (linearity, smaller batch verification) but adds a second crypto primitive to the consensus layer. **Reject for V6**, keep for a future V7+ if Schnorr migration happens chain-wide.

### Q2. Sign the commit, or sign something larger?

Signing only the 32-byte `commit` is the minimum. Some non-outsourceable puzzle papers recommend signing `(header_core || nonce || extra_nonce || commit)` to bind the signature even more tightly to the block context.

**Recommendation**: sign the full message `H(header_core || nonce || extra_nonce || commit)` to prevent replay across blocks and to guard against any subtle attack where an adversary swaps parts of a header but reuses a signature.

### Q3. What about hardware wallets / threshold signatures?

A sufficiently advanced pool could implement V6-compatible mining via a threshold ECDSA scheme: the privkey is split among N parties, no single party can produce a signature alone, and signing requires online cooperation of all (or t-of-N). This in theory restores pool-like operation.

**In practice, no production threshold-ECDSA stack exists for this use case today**, and the per-signature latency (multi-round protocol) would be far too high for mining (you'd need a signature per attempt at >100 attempts/sec). This is a theoretical concern, not a practical one.

If this becomes a real attack vector in the future, the response is V7: switch to a signature scheme that is provably hard to thresholdify (e.g. a scheme with non-linear key aggregation).

### Q4. Should the signature be over the *attempt* (per nonce) or only over the *winning attempt*?

Two options:

**(a) Sign every attempt**: every nonce in the search loop is signed and contributes to the effective hash. This is the strongest defense — even at high hashrates, the signing cost is a hard floor. But it adds ~50-200 µs per attempt (ECDSA sign cost on commodity CPUs), which at SOST's current ~30 att/s per miner is negligible (<1% overhead) but at higher rates becomes a bottleneck.

**(b) Sign only when a candidate passes the target**: the miner runs the normal loop, and only signs the rare candidate that passes the difficulty target. The signature is then included in the block. This is computationally cheap but **breaks the defense partially**: a pool can run many workers searching for target hits, and the operator only needs to sign the (rare) winning candidate. Pool delegation is partially restored.

**Recommendation**: **option (a) — sign every attempt**. The bottleneck argument is real but acceptable for SOST's design point (CPU-friendly, not optimized for raw hashrate). It also adds incidental ASIC resistance (an ASIC must include ECDSA hardware that doesn't accelerate the rest of CX, raising cost).

### Q5. Coinbase address vs miner pubkey decoupling

Some users might want to mine with key K1 but receive rewards at address A2 (controlled by a different key K2) — for example, a miner using a hot key for the actual mining process while routing rewards directly to a cold storage address.

**Recommendation**: do not allow this in V6. Rule 6 above is strict: `coinbase.outputs[0].pubkey_hash == HASH160(miner_pubkey)`. Allowing decoupling would re-enable pool delegation: a pool could give workers throwaway mining keys and a single shared coinbase address.

If users want to consolidate to cold storage, they can do so via a normal post-maturity transfer transaction. The friction is acceptable.

### Q6. Edge case: multi-output coinbase (gold vault, PoPC pool)

The current coinbase has three outputs: `OUT_COINBASE_MINER`, `OUT_COINBASE_GOLD`, `OUT_COINBASE_POPC` (`sost-miner.cpp:163-177`). Only the first one needs to bind to `miner_pubkey`. The other two pay to fixed governance addresses and are unaffected.

Rule 5 above is specifically `coinbase.outputs[0]` — the miner output. The other outputs continue to be validated by existing logic.

### Q7. Genesis miner_pubkey for the V6 activation block

The block at exactly `V6_ACTIVATION_HEIGHT` is mined under V6 rules. The miner of that block must use a real key. There is no special case — whoever wins block `V6_ACTIVATION_HEIGHT` is just the first V6 miner. Easy.

---

## 6. Code touchpoints (to be modified)

This is the concrete file-by-file change list. Use it as a starting checklist when implementation day arrives. **Line numbers are accurate as of the date this memo is written; verify before editing.**

| File | Lines | Change |
|---|---|---|
| `include/sost/block.h` | 36-86 | Bump `BLOCK_HEADER_VERSION` to 2; add `miner_pubkey` and `pow_signature` fields; update `BLOCK_HEADER_SIZE`; update serializer/deserializer to handle both v1 and v2 |
| `include/sost/pow/convergencex.h` | 84-93 | Add `Bytes64 pow_signature` to `CXAttemptResult` |
| `src/pow/convergencex.cpp` | 285-330 | After computing `commit`, sign with miner privkey; compute `effective = SHA256(commit || sig)`; replace target check input |
| `src/pow/convergencex.cpp` | 845+ | Same change in the witness-replay path |
| `src/sost-miner.cpp` | 75-77 | Load miner privkey alongside `g_miner_address` and `g_miner_pkh`. New CLI flag `--privkey` or read from a keystore file |
| `src/sost-miner.cpp` | 81-96 | Update `build_full_header_bytes` to include `miner_pubkey` and `pow_signature` after the activation height |
| `src/sost-miner.cpp` | 828 | Predicate stays `is_stable && pow_meets_target(...)` but the input changes from `commit` to `effective` |
| `src/sost-node.cpp` | 1137-1146 | `handle_submitblock` → `process_block` adds the V6 verification block from §3.2 above |
| `src/sost-node.cpp` | 1148-1188 | `handle_getblocktemplate` returns `version: 2` and tells the miner the activation height |
| `include/sost/block_validation.h` | (entire) | Update validation rules; add helper `verify_v6_pow_signature(BlockHeader&, Bytes32 commit)` |
| `include/sost/consensus_constants.h` | (new constant) | `inline constexpr int64_t V6_ACTIVATION_HEIGHT = ???;` |
| `tests/test_v6_pow.cpp` | (new) | Round-trip tests: sign/verify, valid/invalid signatures, target check, coinbase binding, version bump, fork boundary, activation behavior |

### New helper functions to add

In `include/sost/crypto.h` (or similar):

```cpp
// V6 helpers
Bytes64 ecdsa_sign_low_s(const PrivKey& sk, const Bytes32& msg);
bool    ecdsa_verify_low_s(const PubKey33& pk, const Bytes32& msg, const Bytes64& sig);
PubKey33 derive_compressed_pubkey(const PrivKey& sk);
PubKeyHash hash160(const PubKey33& pk);  // already exists somewhere — reuse
```

These already exist in some form for transaction signing in the wallet/tx code. The V6 work mostly **wires existing primitives into the consensus layer**, not new cryptography. That is a good sign — minimal new attack surface.

---

## 7. Risk assessment

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Subtle bug in signature verification path causes consensus split | Low | Catastrophic | 30-day testnet dry-run; fuzz the verifier; cross-check with reference implementation |
| ECDSA implementation bug (timing leak, RNG bug) leaks privkey | Low | High | Use the same ECDSA primitive already used elsewhere in the codebase; constant-time signing; deterministic nonce per RFC 6979 |
| Network-wide coordination failure during fork | Medium | Medium | 4-week public announcement; 1000-block soft transition; canonical client distribution |
| Threshold-ECDSA pool emerges within 12 months of V6 | Very low | Medium | Document V7 plan (alternative signature scheme); monitor literature |
| Miners refuse to upgrade because of "cold key" loss of convenience | Low | Low | Document the maturity-window workaround; provide example scripts for hot/cold key separation |
| Performance regression at high hashrate (>1000 att/s) | Low (no SOST miner is there yet) | Low | Profile signing cost; if real, switch to "sign only on target hit" (option Q4-b) as fallback |

---

## 8. When to actually deploy this

Trigger conditions (any one is sufficient):

1. **A single coinbase address receives >25% of rewards** sustained over 2000+ consecutive blocks.
2. **A pool service publicly advertises SOST mining** (URL, fee schedule, payout method).
3. **The unique miners count plateaus or declines** for 3+ consecutive months while hashrate grows — implying consolidation into pools rather than new independent miners.
4. **Active research from a third party** demonstrating SOST pool feasibility with working code.

Until at least one of these triggers fires, **V6 is on the shelf**. Don't ship a hard fork without a real reason — it spends political capital and signals weakness.

The right posture is: *we have this designed, reviewed, tested, and ready to deploy in 4 weeks. We don't need to deploy it today.*

---

## 9. What this memo deliberately does NOT cover

These are intentionally out of scope. If V6 implementation begins, each becomes its own document:

- **Detailed test vectors** (signature inputs, expected outputs)
- **Wire protocol changes for P2P block propagation** (probably none — it's just a bigger header)
- **SPV / light client implications** (need to verify that our SPV proof format handles the larger header gracefully)
- **Communication plan to the community** (when, how, what wording — handled separately at deployment time)
- **Economic analysis** (does forking cost us miners short-term? data-driven, not theoretical)
- **Coordination with exchanges** (if SOST is listed by then, give them lead time)
- **Wallet integration** (hot key handling, key rotation UX in the official wallet)

---

## 10. Maintenance of this document

This memo should be **re-read and updated** every 6 months while it sits unused. Specifically:

1. Re-verify all line numbers and file paths against the current codebase.
2. Re-read the open questions in §5 — your answer may change as the project evolves.
3. Re-check the deployment trigger conditions in §8 against actual chain state.
4. If significant CASERT or ConvergenceX changes happen between now and V6, propagate them here.

If this document falls out of sync with the codebase by more than 12 months, **rewrite it from scratch** rather than patching it. The cost of stale assumptions in a consensus-layer hard fork is severe.

---

## Appendix B — Pending decision: Gold Vault hardening (added during V6 design review)

**Status**: Design accepted, NOT yet implemented. To be bundled into the V6 hard fork alongside signature-bound PoW and the GV1-GV4 wiring described in the separate Phase II memo. Final code to be written before the V6 release candidate.

### The problem this solves

The original GV1-GV4 design had a critical weakness: **GV3 ("any spend with ≥95% miner approval") is a democratic backdoor**. With ~24 active miners and the top 3 producing ~70% of the hashrate combined, a colluding supermajority could vote to drain the vault to a miner-controlled address. The 95% threshold is necessary but not sufficient — democracy can vote to rob itself, especially in small networks vulnerable to sybil/coercion attacks.

### Design principle

> **The Gold Vault must be able to change form, but not purpose.**

The vault is a **reserve engine**, not a **treasury**. Its outputs must always serve the constitutional purpose (gold reserve operations) and never become arbitrary spending. Miners can vote on HOW the reserve is managed (which custodian, which token, when to migrate), but never on WHAT the vault is for.

### The five-defense model

Every Gold Vault spend must satisfy ALL of the following at consensus level. No vote, no matter how unanimous, can override any of them.

#### Defense 1 — Purpose restriction (semantic)
The vault can only be used for operations classified as gold reserve operations. Any other purpose is rejected, regardless of voting outcome.

#### Defense 2 — Two separate destination whitelists (structural)

Two distinct sets of constitutional addresses, hardcoded in `consensus_constants.h`:

```cpp
// Normal gold-reserve operations (GV1). Used for routine gold purchases,
// rebalancing between gold-backed tokens, etc. These addresses MUST be
// publicly known, auditable, and serve a reserve function.
inline constexpr const char* GV_ALLOWED_RESERVE_DESTINATIONS[] = {
    "sost1<otc_conversion_addr>",       // OTC desk → fiat → gold tokens
    // future: "sost1<phase3_custody_addr>",  // physical gold custodian
    // future: "sost1<paxg_xaut_swap_addr>",  // wrapper migration
};

// Emergency-only destinations (GV3). Initially empty or near-empty.
// Adding entries requires a hard fork. Reserved for genuine emergencies
// (e.g., a custodian compromise that requires an unplanned reserve
// migration). NEVER for general spending.
inline constexpr const char* GV_ALLOWED_EMERGENCY_DESTINATIONS[] = {
    // intentionally empty at V6 launch
};
```

A spend whose destination is not in EITHER whitelist is rejected at consensus, regardless of vote count. **This kills the colluding-miners-drain-vault attack structurally.**

#### Defense 3 — Hard cap per spend
No single transaction can move more than 2% of the current vault balance. Enforced at consensus level. This applies to BOTH GV1 (normal) and GV3 (emergency) spends.

```cpp
inline constexpr int32_t GV_HARD_MAX_SPEND_BPS = 200;  // 2.00% per spend
```

#### Defense 4 — Rate limiting (asymmetric for GV1 vs GV3)

**For GV1 (gold purchases — routine operations):**
- No fixed cooldown between spends (avoid throttling legitimate DCA-style buying)
- BUT: aggregate cap of **5% per 30-day window** across all GV1 spends combined
- Allows multiple small purchases (e.g. 5× weekly purchases of 1% each)

**For GV3 (emergency migration — non-routine):**
- Hard cooldown of **30 days (4,320 blocks)** between any two GV3 spends
- Plus the 2% per-spend cap from Defense 3

```cpp
inline constexpr int32_t GV_GV1_AGGREGATE_CAP_BPS = 500;   // 5% per window
inline constexpr int64_t GV_GV1_AGGREGATE_WINDOW  = 4320;  // ~30 days
inline constexpr int64_t GV_GV3_COOLDOWN_BLOCKS   = 4320;  // ~30 days minimum
```

#### Defense 5 — Supermajority signaling for non-routine
GV3 spends still require ≥95% miner signaling over a 288-block window. Maintained from the original design, but now as one of FIVE conditions, not the only one.

### What this eliminates from the original design

- **GV2 (operational small spends ≤10% monthly without vote)** — eliminated entirely. It was a backdoor that didn't add value under the new model. Any operational need can be funded via GV3 with miner approval, or via the rate-limited GV1 if it's gold-related.
- **Burn address as a destination** — explicitly forbidden. The total SOST supply is small (4.67M cap, currently <1% emitted). Burning vault SOST permanently destroys protocol-backing capacity. The vault preserves and transforms value; it never destroys it.
- **Single mixed whitelist** — replaced by two semantically distinct whitelists.
- **"Cualquier gasto con 95%"** — eliminated. The vote is now a NECESSARY but not SUFFICIENT condition.

### Final classification logic (pseudo-code)

```cpp
GVSpendType classify_gv_spend_v6(
    int64_t  vault_balance,
    int64_t  spend_amount,
    PubKeyHash dest_addr,
    bool     has_gold_purchase_marker,
    const GVApprovalToken* approval_token,
    const GVRateTracker& rate_tracker,
    int64_t  current_height)
{
    // Defense 3: hard cap per spend (applies to ALL spends)
    int64_t max_per_spend = (vault_balance * GV_HARD_MAX_SPEND_BPS) / 10000;
    if (spend_amount > max_per_spend) return REJECTED;

    if (has_gold_purchase_marker) {
        // GV1 candidate

        // Defense 2A: must be in reserve whitelist
        if (!is_in_reserve_whitelist(dest_addr)) return REJECTED;

        // Defense 4 (GV1 variant): aggregate cap per window
        int64_t window_aggregate_cap =
            (vault_balance * GV_GV1_AGGREGATE_CAP_BPS) / 10000;
        if (rate_tracker.gv1_spent_in_window(current_height) + spend_amount
            > window_aggregate_cap) return REJECTED;

        // Defense 1 implicit (gold purchase = reserve purpose)
        return GOLD_PURCHASE;
    }

    if (approval_token != nullptr) {
        // GV3 candidate

        // Defense 2B: must be in emergency whitelist
        if (!is_in_emergency_whitelist(dest_addr)) return REJECTED;

        // Defense 5: supermajority signaling
        if (approval_token->signal_pct < 95) return REJECTED;
        if (approval_token->threshold_required != 95) return REJECTED;

        // Defense 4 (GV3 variant): hard cooldown
        if (current_height - rate_tracker.last_gv3_height
            < GV_GV3_COOLDOWN_BLOCKS) return REJECTED;

        return REQUIRES_APPROVAL;
    }

    // Defense 1: any spend without gold marker AND without approval token
    // is by definition not a reserve operation
    return REJECTED;
}
```

Note: the function never returns `OPERATIONAL_SMALL`. That entire branch is gone.

### Open implementation questions (resolved at code-write time, not now)

1. **What is the exact OTC conversion address for the initial reserve whitelist?** Must be decided before the V6 release candidate. NeoB to provide. Should be a SOST address that is publicly committed to the reserve operation flow and operationally separated from any personal wallet.

2. **Should the emergency whitelist be empty at launch?** Recommended yes. Adding an emergency destination later requires its own hard fork, which is the appropriate friction. Better to need an emergency fork than to have a populated emergency whitelist that someone tries to abuse.

3. **`GVRateTracker` chain state**: needs to be persisted alongside UTXO set and rebuilt during reindex. Tracks `gv1_spent_in_window` (sliding window) and `last_gv3_height`.

4. **How are reserve whitelist additions verified?** A future hard fork that adds a new reserve destination should include a documented justification in the commit message and in the announcement post. The address itself is the audit unit — anyone can check what's in `GV_ALLOWED_RESERVE_DESTINATIONS` by reading the source.

5. **Audit trail**: every rejected spend should emit a clear validation error code (e.g. `GV_R1_DESTINATION_NOT_WHITELISTED`, `GV_R2_HARD_CAP_EXCEEDED`, `GV_R3_AGGREGATE_CAP_EXCEEDED`, `GV_R4_COOLDOWN_NOT_ELAPSED`, `GV_R5_INSUFFICIENT_SIGNALING`) so node operators can trace exactly why something failed.

### Communication for the V6 ANN

The corresponding Q&A in the BTCTalk announcement should describe the five defenses without revealing all the technical details. Recommended phrasing:

> **Q: What can the Gold Vault be used for?**
> A: After V6 activates, the Gold Vault is constrained by FIVE independent consensus-level defenses, all of which must hold simultaneously for any spend to be valid:
>
> 1. **Purpose restriction** — the vault can only be used for gold reserve operations. Any other purpose is rejected at consensus, regardless of voting outcome.
> 2. **Destination whitelists** — the vault can only send to a small set of constitutional addresses hardcoded in the protocol source code, organized into two categories: normal reserve destinations (gold purchases, rebalancing) and emergency reserve destinations (initially empty). Adding any new destination requires a hard fork. No miner vote, no matter how unanimous, can authorize a transfer to any address outside these whitelists — including any miner-controlled wallet.
> 3. **Hard per-spend cap** — no single transaction can move more than 2% of the current vault balance.
> 4. **Aggregate rate limit** — routine gold purchases are capped at 5% of the vault balance per ~30-day window combined. Emergency spends additionally require a hard 30-day cooldown between transactions.
> 5. **Supermajority approval for non-routine spends** — emergency spends require ≥95% miner signaling over a 288-block window.
>
> The vault has no burn route. Vault SOST is never destroyed under any conditions. The supply is too small to permit destruction; the vault preserves and transforms value, never removes it.
>
> **The Gold Vault must be able to change form, but not purpose.** Even a hostile 100% colluding cabal of miners cannot drain the vault to a wallet they control — the destination whitelists make that mathematically impossible at consensus level. The vault is structurally single-purpose.

### Deferred until V6 implementation phase

- Exact constants (caps, windows, cooldowns) — values in this memo are recommendations; final values to be tuned during V6 testnet.
- Address formats and encodings for `GV_ALLOWED_RESERVE_DESTINATIONS`.
- New error code definitions in `tx_validation.h`.
- Test vectors covering each of the five defenses individually + combinations.
- Migration story for the GVMonthlyTracker → GVRateTracker rename in chain state.

### Calibration notes (do NOT treat as final values)

These three constants need empirical tuning during testnet. Treat them as starting points, not dogma:

1. **`GV_HARD_MAX_SPEND_BPS = 200` (2% per spend)** — reasonable baseline. May need to tighten (1%) if vault grows large enough that 2% is itself a meaningful absolute amount, or loosen (3-5%) if operational gold purchases need to be larger to be efficient. Decision deferred until vault has at least 6 months of operational data.

2. **`GV_GV1_AGGREGATE_CAP_BPS = 500` (5% per 30-day window)** — needs operational testing. The risk is that an overly rigid limit makes legitimate DCA-style buying clunky (small frequent purchases are healthier for averaging than rare large ones). If the OTC desk reports being throttled by this in practice, the cap can be raised to 7-10% in a follow-up fork — but only via the same hard-fork process that adds whitelist entries.

3. **`OTC conversion address` in `GV_ALLOWED_RESERVE_DESTINATIONS`** — this is the most operationally critical entry. The address itself is constitutional infrastructure: it must have hardened operational security independent of the consensus protection. The whitelist protects the destination at consensus level, but does NOT substitute for security of whatever system controls the address. **A whitelist guarantees that funds can only flow TO a specific address; it does not guarantee what happens AFTER they arrive.** This is an unavoidable trust assumption for any on-chain → off-chain bridge involving real-world assets. The mitigation is operational hygiene (key management, monitoring, fast incident response) plus public auditability of every flow through the address.

### Governance trap to remember

A strong destination whitelist protects WHERE funds can go, not what happens to them once they arrive. If the operational system behind a whitelisted address is compromised, consensus does not save the vault. The whitelist closes the protocol-level attack surface; it cannot close the operational-level attack surface. The two layers are independent and both must be defended separately.

This is why the emergency whitelist starts EMPTY: it is better to require an emergency hard fork to add a recovery destination (slow, public, deliberate) than to have a populated emergency whitelist that someone tries to abuse by social engineering.

### Non-decision: this is approved direction

This design is **approved** as the V6 Gold Vault model. Implementation is deferred to the V6 code-write phase but the principles are locked in:

- ✅ Two separate whitelists (reserve + emergency)
- ✅ Per-spend hard cap
- ✅ Asymmetric rate limits (GV1 aggregate, GV3 cooldown)
- ✅ GV2 eliminated
- ✅ Burn destination forbidden, no exceptions
- ✅ GV3 95% signaling retained as one of five defenses, not the only one
- ✅ Adding any whitelist entry requires a hard fork, never a vote

The five-defense model is the V6 baseline. Any future loosening or tightening must itself go through a hard fork with its own design review.

---

## Appendix A — One-page summary (for future you)

> SOST V6 is a hard fork that adds **signature-bound PoW**: every winning block must include `miner_pubkey` (33 bytes) and `pow_signature` (64 bytes ECDSA over the PoW commitment), and the coinbase miner output must pay to `HASH160(miner_pubkey)`. This makes mining-pool delegation structurally impossible: a pool operator has to either share their private key with workers (suicide) or sign every attempt centrally (defeating distribution). CASERT and ConvergenceX are unchanged. The fork is ~200-400 LOC across 5-6 files and requires 30 days of testnet plus 1000 blocks of soft-transition grace period. Trigger conditions for deployment are documented in §8. Do not deploy preemptively.

— End of memo —

---

## Appendix C — Anti-stall threshold change (block 10,000 consensus)

**Decision (2026-04-19):** Raise anti-stall activation from 60 minutes (3600s) to 90 minutes (5400s) at block 10,000.

**Rationale:** The anti-stall sweep (360 simulations across 72 parameter combinations × 5 seeds) showed:

| Activation | %Time in AS | Score | Verdict |
|-----------|------------|-------|---------|
| 30 min | 27-41% | 110 | RED — network lives in anti-stall |
| 60 min (current) | 8-18% | 75 | GREEN/YELLOW |
| **90 min** | **3-8%** | **68** | **GREEN** |
| 120 min | 1.5-3.6% | 61 | GREEN |

90 minutes is the optimal balance: low anti-stall time without excessive tail risk. 120 min scores slightly better but increases P99 block time.

**Why not implement now:** The miner lag-adjust feature (implemented alongside this memo) covers most cases where anti-stall would have activated — the miner now restarts search within 30 seconds when the node profile changes, rather than waiting 60 minutes. The consensus change to 90 min is a safety net refinement, not urgent.

**Implementation for block 10,000:**
```cpp
inline constexpr int64_t CASERT_VT_ANTISTALL_FLOOR = 5400;  // 90 min (was 3600)

// In casert.cpp anti-stall section:
int64_t t_act = (next_height >= VT_FORK_HEIGHT)
    ? CASERT_VT_ANTISTALL_FLOOR
    : CASERT_ANTISTALL_FLOOR_V5;
```

This is a consensus change — all nodes and miners must upgrade before block 10,000.
