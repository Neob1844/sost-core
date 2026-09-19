# SOST V16 — DTD Jackpot V2 — Release Notes (DRAFT)

**Type:** mandatory consensus upgrade (hard fork).
**Activation height:** **#30,000** (mainnet). Auto-activates by height — no manual step.
**First DTD Jackpot V2 draw:** **#30,186** (the first cadence jackpot at/after activation).
**Operator update window:** after **#29,900** and before **#30,000**.

> Pre-#30,000 the V16 binary is **byte-identical to V15** (all V16 artifacts are
> rejected below the activation height). From #30,000 the V2 rules apply. A node
> still running the old V15 binary after #30,000 will diverge from the network —
> **validating nodes and miners must upgrade.**

## What changes at #30,000

- **DTD-normal is 100% UNCHANGED** (eligibility, cadence, cooldown, anti-dominance,
  payout, seed). It keeps paying its frequent per-block winner exactly as today.
- The **DTD Jackpot becomes an independent draw** with its own winner. The
  DTD-normal winner and the DTD Jackpot winner may be the **same or
  different** addresses — both are valid.
- **Eligibility for the DTD Jackpot V2** (ALL required):
  1. valid SbPoW mining identity;
  2. **≥ 3 SbPoW blocks in the last 5,000 blocks** (real PoW contribution);
  3. an **active NODE_BIND** (a node key cryptographically bound to the mining key);
  4. **node heartbeats** — bootstrapped after activation and reaching the permanent
     rule of **3 of the last 4 epochs** (epoch = 288 blocks). Ramp:
     #30,186 = bind only (0/0) → 1/1 → 2/2 → 3/3 → **3/4 from #31,338**.
- **Weight = number of SbPoW blocks in the window (LINEAR)** — the only Sybil-neutral
  weighting: splitting the same work across many addresses does **not** increase your
  total weight; running more nodes never adds weight (node = eligibility gate only).
  Splitting can only ever LOSE weight: an identity below the 3-blocks-per-5,000 minimum
  is not eligible at all and contributes 0, and every identity needs its own NODE_BIND
  and its own heartbeats. See the Errata at the end of this file.
- **No jackpot cooldown. No jackpot anti-dominance.** The jackpot is a probabilistic
  reward proportional to contributed security + node participation.
- **Independent, domain-separated seed** (`SOST_HIST_JACKPOT`) — the jackpot draw is
  separate from and independent of the DTD-normal draw.
- **Payout economics UNCHANGED:** base 100 SOST, cap 500 (rollover), spent from the
  existing DTD reserve (supply-neutral, no new emission); miner 50% / DTD 50%
  and Gold/PoPC new-emission = 0% are untouched. If there are **0 eligible**
  participants at a jackpot height, it **rolls over** (no winner, funds preserved).

## New on-chain / interfaces (only valid from #30,000)

- **Tx types:** `TX_TYPE_NODE_BIND` (0x20), `TX_TYPE_NODE_HEARTBEAT` (0x21). Both are
  0-value protocol txs carrying a single **`OUT_NODE_PROTOCOL` (0x30) non-spendable**
  output (never enters the UTXO set). Full wire size: NODE_BIND 176 B, HEARTBEAT 175 B.
- **RPC:** `getjackpotv2audit <height>`, `checkhistoricaljackpoteligibility <address>`.
- **CLI:** `sost-cli createnodebind <bind_seq> <node_privkey_hex>`,
  `sost-cli nodeheartbeat <node_privkey_hex> <epoch_idx> <tip_ref_hex>`.

## Honest scope

Node participation is verified as **"Verified node participation"** — a bound node key
that follows the chain and signs periodic heartbeats. It is **not** a proof of an
independent physical machine, unique geography, or 24/7 serving. Extra nodes never
add weight, so faking additional nodes gains nothing.

## Validation summary (this release)

- Pure consensus core + tx layer + node-state: unit tests green (V2 core 46/46,
  node-participation 73/73), V15 jackpot 108/108, mempool 25/25, tx 15/15, utxo 21/21.
- Devnet end-to-end: **PAID V2 jackpot** (node-gated + PoW-weighted winner paid from
  reserve; unbound miner excluded; DTD-normal independent) — PASS; rollover — PASS.
- Regressions with V16 present but inactive: payout / reorg / reindex / restart — PASS.
- **V15→V16 upgrade** across activation (V15 chain loads byte-identically in V16 and
  crosses the activation automatically) — PASS.

## Errata — published announcement, not the protocol

The long-form BitcoinTalk announcement carried an anti-Sybil example reading
`100 identities x 1 block each = total weight 100`. That is **wrong against this
release**, and the correction is that the protocol is STRICTER than advertised,
never looser:

```
  1 identity  x 100 blocks -> 1 eligible   -> total weight 100
 10 identities x  10 blocks -> 10 eligible -> total weight 100
100 identities x   1 block  -> 0 eligible  -> total weight   0   <-- announcement said 100
```

`jv2_build_weighted_set()` (`src/jackpot_v2.cpp:93-109`) drops every candidate that
fails `jv2_eligibility_reason()`, and one block is below `JACKPOT_V2_MIN_BLOCKS = 3`
(`src/jackpot_v2.cpp:83`), so such identities carry no weight at all. `tests/
test_jackpot_v2.cpp:178` already noted this and covers only the 1x100 and 10x10 cases.

No consensus code changed for this: the binaries and the tag `v16.0.0-jackpot-v2`
stay frozen, and the hashes in `docs/v16/SHA256SUMS` remain the ones to verify.
