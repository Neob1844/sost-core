# V15 — DTD Recency Eligibility Gate (consensus addition)

**Status:** implemented + tested, gated at `V15_HEIGHT` (mainnet **#25,000**). Pre-V15 replay is
byte-identical (window == 0). Bundled into the V15 activation per founder decision.

## Rule
A DTD lottery candidate must have mined at least one block within a **recency window**, in addition to the
existing gates (recent-winner cooldown, SbPoW-activity, anti-dominance, uniform keyless selection):

| Block type | Recency window | Meaning |
|---|---|---|
| Normal DTD draw | **5,000 blocks** | must have mined ≥1 block in the last 5,000 |
| DTD Jackpot block | **2,016 blocks** (~2 weeks) | stricter — must have mined ≥1 block in the last 2,016 |

The jackpot window is stricter and governs jackpot blocks (the single DTD winner of a jackpot block receives
both the normal DTD share and the jackpot). Dormant addresses drop out of eligibility until they mine again.

## Implementation
- `include/sost/params.h`: `DTD_RECENCY_WINDOW = 5000`, `DTD_JACKPOT_RECENCY_WINDOW = 2016`,
  `dtd_recency_window_at(height)` → 0 for `height < V15_HEIGHT`, else 2016 on jackpot heights / 5000 otherwise.
- `src/lottery.cpp`: one filter inside `compute_lottery_eligibility_set` — `last_mined_height < height - window ⇒ excluded`.
  Because the window is derived from `height` **inside** the shared eligibility builder, all five call sites
  (miner template + every validator/jackpot path) use one predicate → guaranteed miner↔validator parity.
- Height-anchored → pre-25,000 replay byte-identical; the existing sbpow/cooldown/anti-dominance gates are unchanged.

## Tests
- `tests/test_dtd_recency.cpp` (target `test-dtd-recency`): 13/13 PASS — helper values, pre-V15 no-op,
  normal 5,000 exclusion, jackpot 2,016 exclusion.
- No regression: test-lottery-eligibility 77/77, test-jackpot 108/108, test-coinbase-phase2 76/76,
  test-lottery-frequency 79/79, test-lottery-rollover 53/53, test-v13-lottery-cooldown-fork 24/24,
  test-popc-v15-eligibility 5/5.

## Release binaries (SOST_ENABLE_PHASE2_SBPOW=ON, SOST_TESTNET_FORKS=OFF)
- sost-node  sha256 `100645eea36a00a2d29b6d4b535766a0136ea8a0ebf77c0b2c77c11b4227d6b5`
- sost-miner sha256 `c9e53f1444bb85ce59ad2634478fbbb39165acefaca9bda339dc6b824687d9c1`
(rebuild locally with the mandatory flags; hashes are per-toolchain — verify against a reproducible build before wide distribution.)

## ⚠️ Coordinated upgrade REQUIRED (consensus)
This changes which DTD winners are valid at ≥ #25,000. **Every node and miner MUST run a binary containing
this rule before block #25,000**, or the network will split (some accept a DTD winner others reject).
At time of writing mainnet height ≈ 23,186 → ~1,800 blocks (~12–13 days) of runway. The ~90% dominant miner
must upgrade too. Do NOT deploy piecemeal.
