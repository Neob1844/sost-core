# V13 Release Candidate — Operator Note

**RC id:** `v13-rc1`
**Pinned time:** 2026-05-18T13:00:00+00:00
**Source of truth:** `config/v13_release_candidate.json`
**Public mirror:** `website/api/v13_release_candidate.json`
**Companion docs:** `docs/V13_PUBLIC_SCOPE_UPDATE.md` (NEW — operator + community scope update), `docs/V13_ACTIVATION_PLAN.md`, `docs/V13_READINESS_GATES.md`, `docs/V13_MINER_OPERATOR_CHECKLIST.md`, `docs/V13_DTD_FLIP_12100_AUTOMATIC.md`, `docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md`, `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md`, `docs/V13_BEACON_II_B_III_GAPS.md`

---

## 0. Public scope update (2026-05-18)

The operator-and-community version of V13 scope is in **`docs/V13_PUBLIC_SCOPE_UPDATE.md`**. That document supersedes any earlier statement that implied a wider V13 scope. Highlights:

- V13 confirmed at block 12,000: cASERT E7-H35, DTD cooldown 5 → 6, drift cap 60s → 10s (NTP mandatory), Beacon Phase II-A.
- V13 target-if-ready: Beacon Phase II-B, Beacon Phase III.
- **Deferred to V14 / block 15,000**: PoPC + Escrow automatic lifecycle, Gold Vault governance (90% block-based signaling, 67-block window, Transitional Guardian, auto-disconnect at block 25,000), Memory-Lock per-instance (no longer planned at all — see §2).
- DTD flip at block 12,100: verified automatic (`docs/V13_DTD_FLIP_12100_AUTOMATIC.md`).
- RC1 metadata: `release_status = signed_metadata_only`. Binaries not yet uploaded.

Read `docs/V13_PUBLIC_SCOPE_UPDATE.md` end-to-end before mining V13.

---

## 1. What activates at block 12,000

The V13 hardfork ships four CONFIRMED items at block 12000 (heights expressed in protocol blocks, not commits):

```
1. All cASERT equalizer profiles E7-H35 active
   - Helper:    effective_profile_ceiling_at(height) in include/sost/params.h
   - Validator: validator_profile_ceiling_at(height) in src/sost-node.cpp
   - Constant:  CASERT_MAX_ACTIVE_PROFILE_V13 = 35

2. DTD lottery cooldown 5 -> 6 blocks
   - Helper:   lottery_exclusion_window_at(height) in include/sost/params.h
   - Reason:   deterministic 2-firing exclusion under permanent 1-of-3
               cadence regardless of (height mod 3).

3. Future-timestamp drift cap 60 s -> 10 s
   - Helper:   max_future_drift_at(height) in include/sost/params.h
   - Reason:   removes 50 s of timestamp-gaming margin on staged-relief
               and same-block Slingshot tiers.

4. Beacon Phase II-A (local notices, file-only, signed)
   - Gate:     BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT
   - Pubkey:   BEACON_PUBKEY_HEX hardcoded in include/sost/beacon.h
   - Transport: file-local <datadir>/notices.json — no P2P, no HTTP.
```

These four are wired in code at the V13 readiness commit and pass the
V13 readiness check.

---

## 2. What falls back to V14 (block 15,000)

Gated items behind readiness gates. After the 2026-05-18 gap analysis
(see `docs/V13_PUBLIC_SCOPE_UPDATE.md`), the realistic split is:

```
DEFERRED TO V14 (high confidence — gates not close to closing):
- popc_model_a_b              PoPC Model A + B (full automated lifecycle)
- sostescrow_eth_bridge       SOSTEscrow + Ethereum event listener
- gold_vault_governance       Spend-side governance (90% / 67-block /
                              Transitional Guardian / auto-disconnect)

TARGET FOR V13 IF READY, OTHERWISE V14:
- beacon_phase_ii_b           Beacon Phase II-B
- beacon_phase_iii            Beacon Phase III (P2P gossip)

NOT SCHEDULED FOR ANY FORK (rejected):
- memory_lock_per_instance    Memory-Lock per-instance (anti-pool) —
                              numerical analysis shows it penalises
                              small miners proportionally more than
                              large rigs (the opposite of intent).
                              SbPoW remains the protocol's only
                              anti-pool defense.
```

**PoPC is not half-shipped.** Either every PoPC readiness gate (a–g in
`V13_READINESS_GATES.md`) passes and PoPC activates at block 12,000, or
PoPC stays inactive in V13 and slides to V14. There is no middle
position: a half-validated PoPC will not enter consensus. Today, five
of nine PoPC consensus-readiness gates are RED (see
`docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md`); V14 is the realistic
target.

**Gold Vault governance is not half-shipped.** Five of six gates are
RED today (see `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md`); V14 is the
realistic target. The accumulation side (25 % per block) is unaffected
and continues unchanged at consensus level since genesis.

---

## 3. NTP synchronisation is MANDATORY post-V13

The future-timestamp drift cap drops from 60 s to 10 s at block 12,000.
A host whose clock is more than 10 s ahead of true time will produce
candidate blocks that validators reject.

**Action:** before block 12,000, every miner host must run NTP (chrony,
ntpd, timedatectl) and verify the clock skew. The 60 s tolerance of
pre-V13 is gone.

---

## 4. DTD lottery decision at block 12,100

The DTD lottery was not in the original SOST design. It was added in
V11 Phase 2 as a redistribution mechanism while PoPC and Useful Compute
reached production. At block 12,100 — ~100 blocks after V13 stabilises —
the operator will open a community decision in the BitcoinTalk thread:

```
OPTION A — Keep the DTD lottery at 1-of-3 blocks permanent.
  Cooldown stays at 6 (V13). Continues as supplementary redistribution
  in parallel with PoPC (once PoPC is live).

OPTION B — Disable the DTD lottery.
  Protocol returns to clean 50/25/25 split on every block. Extra-
  coinbase rewards stay on the original path: PoPC contracts +
  Useful Compute (when each activates).
```

The decision is community-driven, not unilateral.

---

## 5. Beacon is a loudspeaker, not a remote control

Beacon Phase II-A (V13 confirmed) carries operator-signed notices to
miners and node operators. The validator and a static safety lint
together enforce five hard guarantees on every Beacon phase:

```
- Beacon MAY inform an operator.
- Beacon MAY NOT restart a node or miner.
- Beacon MAY NOT block any block or transaction.
- Beacon MAY NOT change consensus rules.
- Beacon MAY NOT execute commands on the host.
```

If you have a notices.json file under `<datadir>/notices.json` signed
by the hardcoded operator pubkey, the node and miner will surface a
banner at startup. The node never opens the network to obtain
notices in Phase II-A.

---

## 6. Miner / node upgrade sequence

```
Step 1. Pull the V13 release tag (this is rc1; the released tag will
        be vN, with the same min_commit advertised below).
Step 2. Verify your build commit equals the published min_commit:
            e87fb78b3c7a1609ee6cdb4dc237feacf9ff4e2a
Step 3. Run NTP and verify your clock is not >10 s ahead of true time.
Step 4. Restart sost-node and sost-miner on the new binary BEFORE
        block 12,000.
Step 5. If you mine, keep using --wallet + --mining-key-label exactly
        as you have since SbPoW activated at block 7,100. No wallet
        migration is required by V13.
Step 6. Optional: place a signed notices.json under <datadir>/notices.json
        if you want to surface Beacon Phase II-A notices on startup.
```

---

## 7. What V13 does NOT do

- Does NOT change the SbPoW signing contract (active since block 7,100).
- Does NOT introduce a new wallet format.
- Does NOT change the coinbase split (50% miner / 25% Gold Vault / 25% PoPC Pool).
- Does NOT activate Useful Compute rewards (post #133 invariant unchanged).
- Does NOT open any network endpoint on the node beyond what was already there.
- Does NOT modify the block reward emission schedule.

---

## 8. Risk if you do nothing

If your node + miner are still on a pre-V13 binary at block 12,000:

- Your blocks may include profiles or timestamps that V13 nodes will
  reject. Your node may fork from the V13 chain.
- You will not see Beacon Phase II-A notices.
- You will miss the validator + controller cASERT profile expansion
  to H21-H35 — your miner cannot declare those profiles even if the
  rest of the network has moved.

In short: upgrade before block 12,000 or risk being on the wrong fork.

---

## 9. Reference

See `docs/V13_ACTIVATION_PLAN.md` for the full activation plan, and
`docs/V13_READINESS_GATES.md` for the per-gate readiness checklist.
Run the V13 readiness check locally if you want to see the current
state of confirmed-item wiring and gated-item gates:

```
python3 scripts/trinity/v13_readiness_check.py \
    --repo-root /opt/sost \
    --out-json /tmp/sost-v13-readiness/report.json \
    --out-md   /tmp/sost-v13-readiness/report.md \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
```

Run the V13 release-candidate check to verify this RC package itself:

```
python3 scripts/trinity/v13_release_candidate_check.py \
    --repo-root /opt/sost \
    --out-json /tmp/sost-v13-rc/report.json \
    --out-md   /tmp/sost-v13-rc/report.md \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
```
