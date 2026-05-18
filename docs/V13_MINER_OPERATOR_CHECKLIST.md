# V13 Miner + Operator Checklist

**Target:** miners and node operators running SOST mainnet through block 12,000.
**RC:** `v13-rc1` (`release_status = signed_metadata_only` — binaries not yet uploaded)
**Companion docs:** `V13_PUBLIC_SCOPE_UPDATE.md` (READ THIS FIRST), `V13_RELEASE_CANDIDATE.md`, `V13_ACTIVATION_PLAN.md`, `V13_READINESS_GATES.md`, `V13_DTD_FLIP_12100_AUTOMATIC.md`

If you only read one thing, read this checklist. Run through every box before block 12,000 lands. If you only read TWO things, read `docs/V13_PUBLIC_SCOPE_UPDATE.md` first — it tells you what V13 will and will NOT do (PoPC, Escrow, Gold Vault governance are V14, not V13).

---

## A. Binary

```
[ ] My sost-node + sost-miner binaries are built from the V13 release
    tag (rc: v13-rc1 / released: vN).

[ ] The commit I compiled matches the published min_commit:
        e87fb78b3c7a1609ee6cdb4dc237feacf9ff4e2a
    (run `git rev-parse HEAD` inside the cloned repo before building).

[ ] I rebuilt cleanly:
        cd build
        cmake .. -DCMAKE_BUILD_TYPE=Release
        make -j$(nproc) sost-node sost-miner sost-cli

[ ] Both node and miner restart on the new binary. The node prints
    its version and the miner prints its mining identity.
```

---

## B. Chain height

```
[ ] I know my current chain height. Example:
        curl -s --user USER:PASS \
            -d '{"method":"getblockcount","params":[],"id":1}' \
            http://127.0.0.1:18232

[ ] I know how many blocks remain to V13_HEIGHT (12000). At a target
    spacing of 600 s, that is roughly:
        (12000 - current_height) * 10 minutes

[ ] My node has the latest tip from peers before block 12,000.
```

---

## C. NTP (MANDATORY post-V13)

This is the single most operationally important V13 change. Get this
wrong and your candidate blocks will be silently rejected by every
validator starting at block 12,000.

```
[ ] My system clock is within 10 s of true time. After block 12,000,
    a clock more than 10 s ahead of real time makes my candidate
    blocks rejected (future-drift cap drops from 60 s to 10 s).

[ ] Verify NTP service is active:

        timedatectl

    Expected output MUST include:
        System clock synchronized: yes
                      NTP service: active

    If "NTP service: inactive", enable it once:

        sudo timedatectl set-ntp true

    Then re-run timedatectl and confirm both lines are green.

[ ] Optional but recommended — use chrony for tighter sync:

        sudo apt install chrony
        chronyc tracking | head -5

    The "System time" line should be within a few milliseconds of
    true time, never seconds ahead.

[ ] If my clock is BEHIND true time, that's fine — only ahead-of-true-time
    is rejected by the future-drift gate. Behind-time may slow my mining
    until the cASERT cascade catches up but it will NOT be rejected.

[ ] I have tested NTP at least once before the V13 deadline. I have
    NOT discovered the 10-second rule the hard way at block 12,001
    after losing my first three candidates.
```

---

## D. Wallet + mining key (no change vs SbPoW)

```
[ ] If I mine, I am already running with --wallet + --mining-key-label
    (mandatory since SbPoW activated at block 7,100). V13 introduces
    NO new wallet migration.

[ ] My wallet.json file permissions are tight (chmod 600 wallet.json).

[ ] I have NOT exported my private key. The mining key stays on the
    mining host.

[ ] I have NOT shared mining key material with any pool operator.
    Pool topologies that delegate work without sharing the key are
    not viable under SbPoW; that did not change in V13.
```

---

## E. Beacon Phase II-A (optional)

```
[ ] If I want to surface operator-signed notices at startup, place a
    properly-signed notices.json file under <datadir>/notices.json.

[ ] The notice signature is verified against the BEACON_PUBKEY_HEX
    constant hardcoded in the binary. The node does NOT fetch
    notices.json from the network.

[ ] Beacon Phase II-A MAY inform. It MAY NOT restart, MAY NOT block,
    MAY NOT change consensus, MAY NOT execute commands.
```

---

## F. Fallback V14 items — do NOT expect at block 12,000

```
[ ] I understand that PoPC Model A + B is GATED. It activates at
    block 12,000 only if all seven readiness gates close in time.
    Otherwise it slides to V14 (block 15,000) — or stays inactive.

[ ] I understand that Beacon Phase II-B (expiration / threshold sig /
    mirror / revocation / severity) is gated. Slides to V14 if not
    ready.

[ ] I understand that Beacon Phase III (P2P gossip of notices) is
    gated. Slides to V14 if not ready.

[ ] I understand that Memory-Lock per-instance (the second anti-pool
    mechanism besides SbPoW) is gated. Slides to V14 if not ready.

[ ] I am NOT building any tooling on top of those four items assuming
    they ship at block 12,000.
```

---

## G. After block 12,000 — troubleshooting rejected blocks

If your mined blocks start getting rejected after V13_HEIGHT, walk
this list in order:

```
1. Clock too far ahead of true time (> 10 s).
   Symptom: validator log says "REJECTED future-drift".
   Fix:     synchronise NTP. Wait for the chain to advance one block,
            re-test.

2. Still running an old binary.
   Symptom: my own node accepts my block but every other peer
            rejects it.
   Fix:     verify `git rev-parse HEAD` matches min_commit and that
            `cmake / make` ran clean. Restart sost-node + sost-miner.

3. Outdated cASERT profile assumption.
   Symptom: validator log says "profile_index N exceeds active
            ceiling at height X".
   Fix:     a fresh V13 binary lifts the ceiling from H20 to H35.
            Pre-V13 binaries cap at H20 and will reject any block
            declaring H21-H35. Upgrade.

4. Outdated DTD cooldown assumption.
   Symptom: my address mined a recent block + lottery prize but I
            am still being treated as eligible (or vice versa).
   Fix:     V13 raises the cooldown from 5 to 6 blocks. Recent-winner
            exclusion lasts one extra block post-V13.
```

If none of the above explains the rejection, post the validator log
extract on the BitcoinTalk thread. Do NOT post private keys, wallet
files, or anything wallet-shaped.

---

## H. DTD lottery decision at block 12,100

```
[ ] I will read the operator's announcement at block 12,100 (~100
    blocks after V13 stabilises) about whether the DTD lottery
    stays or is disabled.

[ ] I understand the two options:
        OPTION A — keep DTD lottery at 1-of-3 permanent.
        OPTION B — disable DTD lottery; rewards go through the
                   original PoPC + Useful Compute path only.

[ ] I will give input on the BitcoinTalk thread before the operator
    closes the decision.
```

---

## I. What does NOT change

```
[ ] My 50/25/25 coinbase split is unchanged.
[ ] My emission schedule is unchanged (epoch 0 reward, decay, hard
    cap 4,669,201 SOST).
[ ] My SbPoW signing contract is unchanged.
[ ] My ConvergenceX dataset, scratchpad and per-block program are
    unchanged.
[ ] Useful Compute rewards are STILL POSTPONED (post #133 invariant
    unchanged). The infrastructure remains dry-run; block 12,000
    will NOT activate Useful Compute rewards.
```

---

## J. Quick run of the V13 RC + readiness checks

```bash
# Confirm the release candidate package is internally consistent.
python3 scripts/trinity/v13_release_candidate_check.py \
    --repo-root /opt/sost \
    --out-json  /tmp/sost-v13-rc/report.json \
    --out-md    /tmp/sost-v13-rc/report.md \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
# Expected: rc_ready=true, safety_status in {ok, warning}.

# Confirm V13 readiness against the live tree.
python3 scripts/trinity/v13_readiness_check.py \
    --repo-root /opt/sost \
    --out-json  /tmp/sost-v13-readiness/report.json \
    --out-md    /tmp/sost-v13-readiness/report.md \
    --pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
# Expected: v13_ready_for_confirmed_items=true,
#           overall_decision=v13_confirmed_items_ready_gated_items_fallback_to_v15.
```

Both checks are read-only. They never push, never merge, never tag, never sign, never broadcast, never open the network, never touch the GitHub API, never use subprocess. Run them as many times as you want.

---

## K. Where to ask for help

- BitcoinTalk thread (primary forum).
- Operator's Telegram channel (announced from this thread first).
- For technical bug reports: include log extract, height, OS, binary commit, and clock skew measurement. Do NOT include wallet or key material.
