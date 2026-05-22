# V13 Public Scope Update

**Date:** 2026-05-18.
**Activation block:** 12,000 (~3,000 blocks remaining from this writing).
**Fallback hardfork:** V14 at block 15,000 (proposed final hardfork in this cycle, not guaranteed; replaces the earlier "V15" label).
**RC artifact:** `v13-rc1`, signed `SHA256SUMS` published (`release_status = signed_metadata_only`); binaries not yet uploaded.

This document is the **operator-and-community version** of what V13 will do at block 12,000 and what it will not. It supersedes any earlier statement that implied a wider V13 scope.

The honest summary: V13 is on track for a focused, defensible delivery. Some of the items that were originally aspirational for V13 — PoPC + Escrow automatic lifecycle, Gold Vault governance, the second anti-pool mechanism — are explicitly **deferred to V14** because shipping them half-implemented at block 12,000 would be worse than waiting.

---

## 1. Where we are right now

V13 RC1 is on the public surface:

- The release-candidate manifest, the preflight report, the bundle MANIFEST, the deterministic tarball, and the per-binary SHA-256 hashes are all published.
- `SHA256SUMS` has been signed off-line on the secure host that holds the SOST release key. The detached ASCII-armored signature `SHA256SUMS.asc` is at `/api/v13_rc1_SHA256SUMS.asc`, sha256 `5e83889bb95d21404c3ae4faedfeb8c04729343fc88b03f5a9e608dd7c228779`.
- `release_status = signed_metadata_only`. **The binaries themselves are not yet uploaded to a public distribution channel.** Once the operator uploads them, `release_status` will move to `signed_and_published` in a follow-up website bump.

The SOST release key is dedicated to release signing. It is **not** a wallet key, **not** a mining key, **not** an SbPoW key. Verify any future V13 binary against:

| Field | Value |
|---|---|
| `primary_fingerprint`        | `41B1A46E626064AB524CB99EB6B9E2852AE41A04` |
| `signing_subkey_fingerprint` | `E2FCC898520842F0192EF7A46422CC120F51DCEA` |
| `key_id`                     | `B6B9E2852AE41A04` |

Anyone announcing a different fingerprint as the SOST release key is impersonating the operator.

---

## 2. What V13 ships at block 12,000 (confirmed, wired in code)

These four items are in the V13 binary today and have validator-level test coverage:

1. **All cASERT equalizer profiles E7-H35 active.** The equalizer ceiling rises from H20 to H35 via `effective_profile_ceiling_at(height)` and `validator_profile_ceiling_at(height)` in `include/sost/params.h`. Closes the equalizer calibration that began at V6.

2. **DTD lottery cooldown 5 → 6 blocks.** `lottery_exclusion_window_at(height)` returns `6` for `height >= V13_HEIGHT` and `5` below it. Tightens the exclusion under the permanent 1-of-3 cadence.

3. **Future-timestamp drift cap 60 s → 30 s.** `max_future_drift_at(height)` returns `30` for `height >= V13_HEIGHT`. **NTP synchronisation is strongly recommended from block 12,000.** A host whose system clock is more than 30 s ahead of true time will produce candidate blocks that every validator rejects.

4. **Beacon Phase II-A.** `BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT`. The node loads operator-signed advisory notices from `<datadir>/notices.json` only. No P2P, no HTTP from C++ code, no command execution. The miner prints a banner. The five hard Beacon invariants apply (MAY inform, MAY NOT restart, MAY NOT block, MAY NOT change consensus, MAY NOT execute commands).

Plus the supporting infrastructure that landed in the RC1 chain: readiness gates, RC manifest, binary preflight, artifact bundle, public artifact metadata, and the manual signing + publication checklist.

---

## 3. What V13 may also ship (target, not guaranteed)

These two items are realistic for V13 if the operator can close the remaining gaps before the RC freeze; otherwise they defer cleanly to V14 / block 15,000:

- **Beacon Phase II-B.** Adds expiration-by-height (already present), severity levels (already present), plus N-of-M threshold signatures on critical notices, optional revocation, and a secondary publication channel (mirror). The five hard Beacon invariants do not change. Realistic close: 1–2 sprints if the operator can produce the M threshold keys offline.
- **Beacon Phase III.** Adds peer-to-peer gossip of verified notices, with size cap (4 KB), 32-notice dedup ring buffer, and per-peer rate limit (8 notices/peer/min). Scaffold dormant today at `BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX`. The five hard Beacon invariants do not change. Realistic close: 2–3 sprints, and depends on the underlying P2P gossip primitive being available.

If either Phase is not ready by the V13 RC freeze, it defers to V14 without any consensus impact — Phase II-A continues to operate alone, exactly as it does in the V13-confirmed scope above. No regression, no rework.

The full audit is in `docs/V13_BEACON_II_B_III_GAPS.md` with file:line evidence.

---

## 4. What is deferred to V14 / block 15,000

Four items that were originally listed as V13 targets have moved to V14 after the most recent gap analysis. **This is a deliberate scope contraction, not abandonment.** The reason is the same in every case: shipping half-implemented consensus changes is worse than waiting one fork.

- **PoPC Model A + B automatic lifecycle.** Today PoPC is application-layer — there is no `POPC_ACTIVATION_HEIGHT` consensus gate, no automatic audit scheduler, no auto-slash, no auto-settlement, no end-to-end lifecycle test, and the Solidity escrow contract `contracts/SOSTEscrow.sol` exists in source but is not deployed to Ethereum. PoPC remains accumulation-only at consensus (25 % per block to the PoPC Pool address since genesis) — that part keeps working as it always has. The full nine-gate audit is in `docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md`.

- **SOSTEscrow + Ethereum bridge + event listener.** The Ethereum escrow contract needs to be deployed (to Sepolia first for an end-to-end test, then to mainnet), and the SOST side needs a deterministic, reorg-safe bridge that translates `GoldDeposited` events into SOST state mutations. This is multi-sprint work and is gated on the PoPC consensus gate being design-final.

- **Gold Vault governance.** The accumulation side (25 % per block to the gold vault address) has been consensus-enforced since genesis and is unchanged. The spend-side governance — purpose restriction, dual whitelists, per-spend cap, rate limit, 90 % block-based miner signaling over a 67-block window (~12 h), Transitional Guardian with 10-block pronouncement window, auto-disconnect at consensus level (hard cap block 25,000) — defers to V14. Five of six gates are RED today. The full audit is in `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md`.

- **Memory-Lock per-instance (second anti-pool mechanism).** Originally proposed to force the 4 GB ConvergenceX dataset to be per-thread rather than shared, on the theory that this would penalise hashrate concentration. Numerical analysis of realistic hardware budgets shows the mechanism penalises small miners proportionally **more** than large rigs — the opposite of the intended effect. **Memory-Lock is therefore not in V13 scope, and is not currently planned for V14 either.** SbPoW (signature-bound PoW, active since block 7,100) remains the protocol's primary anti-pool defense.

These deferrals do not regress any current behaviour. The accumulation side of every Vault and Pool continues to work as it always has, and SbPoW continues to make traditional mining pools unworkable.

---

## 5. The DTD flip at block 12,100 (verified automatic)

100 blocks after V13 activates, the V11 Phase 2 lottery cadence transitions from bootstrap (`2-of-3 blocks fire`) to permanent (`1-of-3 blocks fire`). This is **not a separate fork constant**. It is implicit in `is_lottery_block(height, V11_PHASE2_HEIGHT)` in `include/sost/lottery.h:126`, which switches branches when `(height - 7100) >= 5000`.

The flip has been **verified automatic** — no operator action, no node restart, no miner restart, no Beacon notice, no RPC call, no config flag is required at block 12,100. Both miner and validator route through the same single pure function, and the miner has no parallel cadence logic (it reads `lottery_triggered` from the node's RPC response).

Six audit gates were checked and are all GREEN on `main`:

| # | Gate | Evidence |
|---|---|---|
| G1 | Constants pinned | `V11_PHASE2_HEIGHT=7100`, `LOTTERY_HIGH_FREQ_WINDOW=5000`, `V13_HEIGHT=12000` |
| G2 | `is_lottery_block` defined inline | `include/sost/lottery.h:126` |
| G3 | No literal-numeric call sites | 4 src/ call sites all use the named constant or a variable |
| G4 | Miner has no shadow cadence math | `src/sost-miner.cpp` consumes RPC `lottery_triggered` only |
| G5 | V13 cooldown helper decoupled | `lottery_exclusion_window_at` does not call `is_lottery_block` |
| G6 | Python math sanity | re-implementation agrees with the firing pattern at h ∈ [12,095, 12,110] |

Full details in `docs/V13_DTD_FLIP_12100_AUTOMATIC.md` (companion tag: `v13-dtd-flip-12100-verification-v01`).

After the flip, the community decides between Option A (keep DTD at 1-of-3) and Option B (disable DTD) on the BitcoinTalk thread. This decision is community-driven and orthogonal to V13 — it is not part of the V13 fork itself.

---

## 6. NTP — what every miner must do before block 12,000

This is the single most operationally important V13 change. From block 12,000 onward, any candidate block timestamped more than **10 seconds** ahead of true time will be rejected by every validator.

Verify on each mining host:

```bash
timedatectl
```

You should see:

```
   System clock synchronized: yes
                 NTP service: active
```

If NTP service is inactive, activate it once:

```bash
sudo timedatectl set-ntp true
```

Then re-check `timedatectl` and confirm both lines are green.

If you prefer `chrony` (more accurate than systemd-timesyncd), install it and verify with `chronyc tracking | head -5`. The number that matters is "System time": it should be within a few milliseconds of true time, never seconds ahead.

A clock that is **behind** true time is **fine**. The drift cap only rejects blocks timestamped in the future. Behind-time blocks may take a few extra cycles to converge under cASERT but are not rejected.

---

## 7. Miner operator checklist (short form)

**Upgrade window: blocks 11,900 → 11,999** (the 100 blocks immediately before activation, ~18 hours at the target block time). Do the work inside this window, NOT at block 12,000 — by then any candidate you mine on the pre-V13 binary or on a clock more than 30 s ahead of true time is already rejected.

Recommended sequence inside the window:

1. **Stop your miner.**
2. **Upgrade your binary to a V13-aware build** — once the release operator publishes the signed binaries (`release_status` moves from `signed_metadata_only` to `signed_and_published`), download from the announced URL, run `sha256sum -c SHA256SUMS` and `gpg --verify SHA256SUMS.asc SHA256SUMS` against the SOST release public key (primary fingerprint `41B1A46E626064AB524CB99EB6B9E2852AE41A04`).
3. **Configure NTP** (see §6). Both `timedatectl` output lines must be green.
4. **Restart miner with your existing `--wallet` + `--mining-key-label`** — V13 introduces no wallet migration. Pool topologies that delegate work without sharing the mining key remain unworkable, exactly as they were since SbPoW activated at block 7,100.
5. **(Optional) Drop a signed `notices.json` under `<datadir>/`** if you want to surface operator-signed Beacon advisory notices at startup.

After the swap:

6. **Do NOT expect** PoPC, the SOSTEscrow auto-bridge, or Gold Vault governance at block 12,000 — those are V14 scope.
7. **Watch block 12,000 land.** Your first post-activation candidates confirm everything is in order. If any get rejected, the most likely cause is NTP drift — re-run `timedatectl` and fix the clock; the next candidate will succeed.

After block 12,000:

- Watch for any rejected-block events. The most likely cause is NTP drift; fix the clock and the next attempt will succeed.
- Follow the BitcoinTalk thread for the DTD lottery decision (Option A vs Option B) opening at block 12,100.

The full miner checklist is in `docs/V13_MINER_OPERATOR_CHECKLIST.md`.

---

## 8. Short FAQ

**Q: Will PoPC activate at block 12,000?**
A: **No.** PoPC remains application-layer in V13 (accumulation only — the 25 % per block to the PoPC Pool address continues unchanged). The automatic lifecycle (audit daemon, auto-slash, auto-settlement, Ethereum bridge) defers to V14. This is documented in `docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md`.

**Q: Will Gold Vault governance activate at block 12,000?**
A: **No.** The accumulation side (25 % per block to the gold vault address) has been live since genesis and remains so. The spend-side governance (5-defense + Transitional Guardian + auto-disconnect at block 25,000) defers to V14. Documented in `docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md`.

**Q: What happens to the original V13 promise of PoPC at block 12,000?**
A: It was a target, not a guarantee. Five of nine PoPC gates and five of six Gold Vault gates are RED today. Shipping with half-implemented consensus rules is worse than waiting. V14 / block 15,000 is the explicit fallback; this is the same fallback the gap docs and the V13 RC manifest now use. The V14 label replaces the earlier "V15" label used in some pre-RC documents.

**Q: Is V13 still useful if PoPC is deferred?**
A: **Yes.** V13 is the stability + communication + signing fork: cASERT closure, DTD cooldown tightening, drift cap tightening, Beacon Phase II-A (advisory notices), and the published signed RC1 artifact metadata. V14 will be the custody + governance fork.

**Q: Why is Memory-Lock per-instance not in V13?**
A: Numerical analysis shows it would penalise small miners proportionally more than large rigs (small miners have less RAM headroom relative to threads), achieving the opposite of its intended anti-pool goal. SbPoW remains the protocol's only anti-pool defense.

**Q: Will I lose blocks because of NTP?**
A: Only if your clock is more than 10 seconds **ahead** of true time. Run `timedatectl` and `sudo timedatectl set-ntp true`. Behind-time clocks are not rejected; only future-time clocks are.

**Q: When can I download a V13 binary I can verify?**
A: When `release_status` in `/api/v13_rc1_artifact_manifest.json` moves to `signed_and_published`. Currently it is `signed_metadata_only`: the hashes are signed, the binaries are not yet uploaded.

**Q: Is the operator going to push V13 without telling anyone?**
A: No. V13 activation is height-anchored: block 12,000. Every node, every miner, every wallet upgrades on its own schedule against that height. The operator publishes the signed binaries; you verify them; you upgrade. There is no remote push, no auto-update, no consensus change triggered by a Beacon notice — that is part of the five hard Beacon invariants.

---

## 9. Closing note

V13 ships what it can defend. The four confirmed items (cASERT, DTD cooldown, drift cap, Beacon II-A) all have validator-level test coverage today and have been verified against the live `main` tree. The DTD flip at block 12,100 has been independently verified as automatic. The signed RC1 metadata is published.

The four items deferred to V14 are deferred for a single reason: they are not yet defensible at consensus level. PoPC needs a deterministic Ethereum bridge with reorg-safety, an audit scheduler, auto-slash, auto-settlement, and an end-to-end test. Gold Vault governance needs the spend-side classifier wired into the validator, the dual whitelists committed, the per-spend cap and rate limit decided, the Guardian role implemented with its 10-block grace and auto-disconnect at block 25,000, and the Heritage Reserve contract deployed on Ethereum. Memory-Lock per-instance is rejected outright because the math does not support its anti-pool claim.

Shipping less, well, beats shipping more, badly. V14 / block 15,000 will revisit the deferred items with concrete gates closed. Until then, the existing infrastructure — including SbPoW (which has kept pools genuinely unworkable since block 7,100), the 25 % per block accumulation to both the Gold Vault and the PoPC Pool, and operator-signed Beacon advisories — continues to operate exactly as it does today.

If anything in this document is unclear or contradicts something you have read elsewhere on `sostcore.com`, the BitcoinTalk thread, or in any other public channel, trust this document and the V13 RC1 public artifact metadata over any older statement. The whole point of publishing this scope update is to make the deferral explicit before block 12,000 — not after.

— NeoB
