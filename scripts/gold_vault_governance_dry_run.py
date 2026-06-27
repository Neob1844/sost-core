#!/usr/bin/env python3
# =============================================================================
# gold_vault_governance_dry_run.py — Gold Vault spend-governance SIMULATOR.
#
# ┌───────────────────────────────────────────────────────────────────────┐
# │  FOUNDER-ONLY MAINNET PILOT — DO NOT USE. Not externally audited.       │
# │  Public users: DRY-RUN ONLY. Public execution is DISABLED. This script  │
# │  NEVER signs, NEVER broadcasts, NEVER moves funds, NEVER activates       │
# │  governance. Gold Vault spending is NOT enabled on mainnet (all gates    │
# │  are INT64_MAX). It only reads a proposal JSON and prints a verdict.     │
# └───────────────────────────────────────────────────────────────────────┘
#
# Answers "would this Gold Vault spend pass the founder-only capped pilot
# governance?" by running the SAME rules the consensus helpers encode
# (gold_vault_slice1.h G1/G2/G3a, gv_g4.h, gv_g5.h) PLUS the tighter pilot
# rails (founder signature, 1 SOST per-spend, 10 SOST cumulative). Prints
# APPROVED or REJECTED with per-rule reasons.
#
# Usage:
#   python3 scripts/gold_vault_governance_dry_run.py scripts/fixtures/gv_valid.json
#   python3 scripts/gold_vault_governance_dry_run.py -  < proposal.json
# Exit code: 0 = APPROVED, 2 = REJECTED, 1 = bad input.
# =============================================================================
import sys, json, argparse

# ---- Canonical rule parameters (MUST mirror the C++ headers) ----------------
# G1/G2 whitelist — the single legal destination = the genesis/founder miner PKH
# (GV_SLICE1_WHITELIST_PRIMARY in gold_vault_slice1.h). CONFIRM this is the
# foundation/founder-controlled address before ANY future activation.
WHITELIST = {"059d1ef8639bcf47ec35e9299c17dc0452c3df33"}
# G3a absolute per-spend cap (GV_SLICE1_PER_SPEND_CAP_STOCKS = 1000 SOST).
ABS_CAP_SOST = 1000
REL_CAP_BPS = 0                       # G3a relative cap (0 = off)
RATE_LIMIT_BLOCKS = 144              # G3b timelock (intended; header sentinel 0/unwired)
G4_WINDOW, G4_THRESHOLD_PCT, G4_FOUNDATION_PCT = 67, 90, 10
G5_GRACE_BLOCKS, G5_AUTO_DISCONNECT_HEIGHT = 10, 100000

# ---- FOUNDER-ONLY PILOT rails (tighter than consensus G3a) -------------------
# These are the pilot limits. The CUMULATIVE cap is NOT yet enforceable on-chain
# (G3b is not wired — needs StoredBlock.gold_vault_last_spend_height), so it is a
# DOCUMENTED TARGET enforced here in the dry-run + operationally, until G3b lands.
PILOT_PER_SPEND_CAP_SOST   = 1       # max 1 SOST per pilot spend
PILOT_CUMULATIVE_CAP_SOST  = 10      # max 10 SOST total pilot outflow


def _ceil_pct(window, pct):
    return 0 if (window <= 0 or pct <= 0) else (window * pct + 99) // 100

G4_FLOOR = _ceil_pct(G4_WINDOW, G4_THRESHOLD_PCT)              # 61
G4_FOUNDATION_WEIGHT = _ceil_pct(G4_WINDOW, G4_FOUNDATION_PCT)  # 7


def evaluate(p):
    """Return (approved: bool, checks: list[(rule, ok, detail)])."""
    checks = []
    amt = p.get("amount_sost", 0)

    # P0 — founder-only authorization (pilot): the proposal must be signed by the
    # founder/foundation. (In consensus, only the holder of the vault key can spend;
    # here we model the explicit founder authorization the pilot requires.)
    p0 = bool(p.get("signed_by_founder", False))
    checks.append(("P0 founder-signed", p0,
                   "founder/foundation authorization present" if p0
                   else "NOT signed by founder/foundation (public execution disabled)"))

    # G1 — destination whitelist
    dest = str(p.get("destination_pkh", "")).lower()
    g1 = dest in WHITELIST
    checks.append(("G1 whitelist", g1,
                   "destination in whitelist" if g1 else f"destination {dest or '<none>'} NOT in whitelist"))

    # G2 — dual whitelist agreement (fail-closed on mismatch)
    g2 = bool(p.get("whitelists_agree", True))
    checks.append(("G2 dual-whitelist", g2,
                   "primary/mirror agree" if g2 else "primary/mirror DISAGREE (fail-closed)"))

    # P1 — pilot per-spend cap (1 SOST), tighter than G3a's 1000.
    p1 = amt <= PILOT_PER_SPEND_CAP_SOST
    checks.append(("P1 pilot per-spend cap", p1,
                   f"{amt} <= {PILOT_PER_SPEND_CAP_SOST} SOST" if p1
                   else f"{amt} > {PILOT_PER_SPEND_CAP_SOST} SOST pilot cap"))

    # P2 — pilot CUMULATIVE cap (10 SOST). NOT YET consensus-enforced (G3b unwired)
    # — documented target enforced here + operationally until G3b lands.
    prior = p.get("prior_pilot_outflow_sost", 0)
    p2 = (prior + amt) <= PILOT_CUMULATIVE_CAP_SOST
    checks.append(("P2 pilot cumulative cap", p2,
                   f"{prior}+{amt} <= {PILOT_CUMULATIVE_CAP_SOST} SOST" if p2
                   else f"{prior}+{amt} > {PILOT_CUMULATIVE_CAP_SOST} SOST cumulative (NOTE: not yet on-chain — G3b unwired)"))

    # G3a — consensus per-spend cap (absolute, and relative if enabled)
    g3a = amt <= ABS_CAP_SOST
    detail = f"{amt} <= {ABS_CAP_SOST} SOST" if g3a else f"{amt} > {ABS_CAP_SOST} SOST abs cap"
    if g3a and REL_CAP_BPS > 0:
        rel_cap = p.get("vault_balance_sost", 0) * REL_CAP_BPS / 10000
        if amt > rel_cap:
            g3a, detail = False, f"{amt} > {rel_cap} SOST relative cap"
    checks.append(("G3a per-spend cap", g3a, detail))

    # G3b — rate-limit / timelock (consensus: NOT wired yet)
    since = p.get("blocks_since_last_spend", 0)
    g3b = since >= RATE_LIMIT_BLOCKS
    checks.append(("G3b timelock", g3b,
                   f"{since} >= {RATE_LIMIT_BLOCKS} blocks" if g3b
                   else f"only {since} blocks since last spend (< {RATE_LIMIT_BLOCKS}) (NOTE: not yet on-chain)"))

    # G4 — miner signaling window
    yes = p.get("miner_yes", 0)
    eff = min(G4_WINDOW, yes + (G4_FOUNDATION_WEIGHT if p.get("foundation_signaled") else 0))
    g4 = 0 <= yes <= G4_WINDOW and eff >= G4_FLOOR
    checks.append(("G4 miner signaling", g4,
                   f"effective {eff}/{G4_WINDOW} >= floor {G4_FLOOR}" if g4
                   else f"effective {eff}/{G4_WINDOW} < floor {G4_FLOOR}"))

    # G5 — Guardian veto (silence = accept)
    height = p.get("height", 0)
    g5_active = height < G5_AUTO_DISCONNECT_HEIGHT
    vetoed = bool(p.get("veto_present")) and g5_active
    g5 = not vetoed
    checks.append(("G5 guardian veto", g5,
                   "no valid veto (silence = accept)" if g5
                   else ("VETOED by Guardian" if g5_active else "veto ignored (Guardian auto-disconnected)")))

    return all(ok for _, ok, _ in checks), checks


def main():
    ap = argparse.ArgumentParser(description="Gold Vault governance dry-run (no signing, no broadcast, no funds moved)")
    ap.add_argument("proposal", help="proposal JSON file, or - for stdin")
    args = ap.parse_args()
    try:
        raw = sys.stdin.read() if args.proposal == "-" else open(args.proposal, encoding="utf-8").read()
        p = json.loads(raw)
    except Exception as e:
        print(f"bad input: {e}", file=sys.stderr); return 1

    print("==== FOUNDER-ONLY MAINNET PILOT — DO NOT USE · public execution DISABLED · DRY-RUN ONLY ====")
    approved, checks = evaluate(p)
    print(f"== Gold Vault governance dry-run: {p.get('name', args.proposal)} ==")
    for rule, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {rule:<24} {detail}")
    print(f"== VERDICT: {'APPROVED' if approved else 'REJECTED'} ==")
    print("(simulation only — nothing signed, nothing broadcast, no funds moved, mainnet untouched)")
    return 0 if approved else 2


if __name__ == "__main__":
    sys.exit(main())
