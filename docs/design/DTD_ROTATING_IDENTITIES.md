# DTD rotating identities (audit findings F2/F3): design note

Status: **DEFERRED_FOR_SEPARATE_DESIGN.** Nothing here is implemented. V17 (#40,000) keeps the
normal DTD eligibility, cooldown, anti-dominance gate and amounts exactly as they are; the only DTD
change in V17 is DTD-F1 (seed from the PoW commit, `docs/v40000/DTD_F1_SEED_POW_COMMIT.md`).
Changing eligibility needs an owner decision on the economic goal and its own fork height.

## 1. Observation (mainnet, read-only)

Source: `dtd-audit` test (e), `data/test_e_sybil.txt`, chain copy plus public RPC.

* Window **#30,562 – #30,711** (and still visible at #30,812: 74 eligible).
* **74 identities**, each of which had mined before #30,001, mined **exactly one block** each in the
  window (74 of the 251 blocks between #30,562 and #30,812, 29.5 %, about 290 SOST of miner share).
* The anti-dominance gate (10 % of the 288-block window, armed from V16 only with ≥ 11 distinct
  miners) **armed at draw #30,589**. From #30,600 neither large miner (`sost17a8985bc…`,
  `sost1ad01a1ce…`, each ≥ 10 % of the window) was eligible.
* The 74 one-block identities collected **953.90 of 985.30 SOST of DTD paid since #30,562
  (96.8 %)**.
* Whether one operator controls them is not established. The pattern is exactly what the rules pay
  for: one block buys one equal ticket for up to 288 draws (282 after cooldown), worth about
  `282/E × DTD`; at E = 74 that is ≈ 15 SOST pre-V17 and ≈ 4.5 SOST in V17, per block mined.

## 2. Effect on the anti-dominance gate

The gate is a per-pkh percentage rule. It is defeated in both directions by address rotation:

* a large miner splits its coinbase across addresses that each stay under 10 %, so it is never
  excluded;
* small or rotated identities raise the distinct-miner count to ≥ 11, which **arms** the gate and
  excludes every honest miner that pays to one address and holds ≥ 10 % of the window.

So the gate either does nothing or is used against the miners it does not target. DTD-F1 removes
the free choice of the winner among the eligible set; it does not change who is eligible.

## 3. Alternatives (to be evaluated in a separate design)

| Option | Sybil cost per ticket | Effect on redistribution goal | Notes |
|---|---|---|---|
| **Persistent identity** (ticket tied to a long-lived key, e.g. the SbPoW key, with first-seen age) | cost of keeping one key mining over time | keeps uniform tickets for real participants | identities are free to create; needs a minimum age or work to bite |
| **Accumulated work** (ticket weight = blocks or work in the window, as Jackpot V2 already does) | fully Sybil-proof: splitting does not add weight | returns most DTD to large miners; conflicts with the "reward small miners" goal | the only option that is exactly split-invariant |
| **Capped / concave weight** (e.g. `min(blocks, c)` or `sqrt(blocks)`) | partial | middle ground | splitting still helps up to the cap; must be analysed against rotation |
| **Minimum age / minimum blocks** (≥ N blocks over M windows before a ticket counts) | N blocks per identity, spread over time | delays new honest miners | raises the price of each identity, does not remove the incentive |
| **NODE_BIND + heartbeat** (reuse Jackpot V2 participation: a bound node key and heartbeats in completed epochs) | one running node (or at least one signed heartbeat per epoch) per identity | rewards operating infrastructure | node keys are also free; bind cost and heartbeat availability set the price |
| **Weighted tickets by age × work** | combination | tunable | more parameters, more audit surface |
| **Sybil-resistant mechanisms** (stake/bond per ticket, e.g. a PoPC-style bond; or identity attestations) | capital per identity | changes who can participate | bonds introduce custody/slashing questions; attestations are not permissionless |
| **Rework or drop the 10 % gate** (arm only on miners with ≥ M blocks, or drop it together with work weighting) | — | removes the weaponisation | without a work-based ticket the gate cannot do what it was designed for |

## 4. Requirements for the separate design

1. State the economic goal numerically (share of DTD to miners below x % hashrate).
2. Show split-invariance or quantify the residual gain from splitting into k identities.
3. Show the gate cannot be armed by identities that cost less than the exclusion they cause.
4. Replay the full history and the #30,562 – #30,711 episode under the proposed rule.
5. Keep DTD-F1 (commit seed) and the Jackpot V2 rules independent of the change.
6. Its own activation height, devnet E2E, vectors and owner sign-off.

**DTD_ROTATING_IDENTITIES = DEFERRED_FOR_SEPARATE_DESIGN.**
