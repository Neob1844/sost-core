"""SOST Atomic Bridge (ARV) — bounded model check of the native-reserve designs (C705).

Research only. Nothing here is consensus code. It enumerates every interleaving of user,
relayer, attacker and clock actions up to small bounds and checks the security invariants.

Designs:
  D0  reserve held by a key (today's primitives, or V17 M-of-N): the key holder can spend.
  D2  keyless reserve: ARV_DEPOSIT / ARV_RESERVE outputs with fixed spend paths, released
      only against proofs of Ethereum vault events (and the vault releases only against a
      proof of a confirmed SOST deposit). Every relay is permissionless.
  D2-deep  D2 with an attacker able to reorganize a confirmed SOST deposit (deeper than k):
      shows which invariant depends on the SOST PoW majority.

Timing check (HTLC variant, D1): exhaustive search of the entry race between the vault's
Ethereum HTLC deadline and the user's SOST HTLC refund height.

Run:  python3 research/arv/arv_model.py        (exit code 0 = every expected result holds)
      python3 research/arv/arv_model.py 1 2 6 3 2 2   (other bounds)

Not modelled: fees and dust, inventory exhaustion beyond PREMINT, forged light-client or relay
proofs (assumed sound), proof staleness / front-running of checkpoints, censorship. complete()
follows ONE greedy relay schedule: it shows a completion exists, not that every schedule completes.
"""
from __future__ import annotations

import itertools
import sys
from collections import deque
from dataclasses import dataclass, replace

USERS = 2          # honest users; party index USERS is the attacker, who also holds funds and acts
SOST0 = 2          # native SOST of each party at the start (attacker included)
PREMINT = 6        # preissued wSOST, all immobilized at the start (= total SOST of all parties)
MAX_DEPOSITS = 2
MAX_EXITS = 2
TMAX = 2           # Ethereum clock ticks (deadline = deposit time + 1)

# Entry states. Ethereum side: REQ (unknown/requested), REL (released), CAN (cancelled).
# SOST side: PEND (deposit output unspent), SWEPT (merged into the reserve), REFD (refunded), GONE (reorged out).


@dataclass(frozen=True)
class Entry:
    user: int
    amount: int
    deadline: int
    confirmed: bool = False
    eth: str = "REQ"
    sost: str = "PEND"


@dataclass(frozen=True)
class Exit:
    user: int
    amount: int
    paid: bool = False


@dataclass(frozen=True)
class S:
    t: int
    sost: tuple          # native SOST per user (+ index USERS = attacker)
    wsost: tuple         # circulating wSOST per user (+ attacker)
    inv: int             # immobilized inventory
    deposits_pending: int  # value of PEND deposit outputs (keyless, not yet swept/refunded)
    reserve: int         # value of the ARV_RESERVE singleton
    entries: tuple
    exits: tuple


def parties():
    return range(USERS + 1)


def init():
    return S(0, (SOST0,) * (USERS + 1), (0,) * (USERS + 1), PREMINT, 0, 0, (), ())


def setv(tup, i, v):
    lst = list(tup)
    lst[i] = v
    return tuple(lst)


def successors(s: S, design: str):
    out = []
    # --- users ---
    for u in parties():                      # honest users and the attacker deposit / exit alike
        for a in (1, 2):
            if s.sost[u] >= a and len(s.entries) < MAX_DEPOSITS:              # deposit to ARV_DEPOSIT
                e = Entry(u, a, s.t + 1)
                out.append(("deposit", replace(s, sost=setv(s.sost, u, s.sost[u] - a),
                                               deposits_pending=s.deposits_pending + a, entries=s.entries + (e,))))
            if s.wsost[u] >= a and len(s.exits) < MAX_EXITS:                  # exit on Ethereum: wSOST -> inventory
                out.append(("exit", replace(s, wsost=setv(s.wsost, u, s.wsost[u] - a), inv=s.inv + a,
                                            exits=s.exits + (Exit(u, a),))))
    # --- chain events / clock ---
    if s.t < TMAX:
        out.append(("tick", replace(s, t=s.t + 1)))
    for i, e in enumerate(s.entries):
        if e.sost == "PEND" and not e.confirmed:
            out.append(("confirm", replace(s, entries=setv(s.entries, i, replace(e, confirmed=True)))))
        reorgable = e.sost == "PEND" and (not e.confirmed or design == "D2-deep")
        if reorgable:                                                         # deposit disappears from SOST
            out.append(("reorg", replace(s, sost=setv(s.sost, e.user, s.sost[e.user] + e.amount),
                                         deposits_pending=s.deposits_pending - e.amount,
                                         entries=setv(s.entries, i, replace(e, sost="GONE", confirmed=False)))))
    # --- permissionless relays (anyone; guards are consensus / contract rules) ---
    for i, e in enumerate(s.entries):
        # Ethereum: release inventory against a proof of a CONFIRMED deposit, before the deadline
        if e.eth == "REQ" and (e.confirmed or design == "M-noconfirm") and s.t < e.deadline and s.inv >= e.amount:
            out.append(("release", replace(s, inv=s.inv - e.amount, wsost=setv(s.wsost, e.user, s.wsost[e.user] + e.amount),
                                           entries=setv(s.entries, i, replace(e, eth="REL")))))
        # Ethereum: anyone cancels after the deadline if not released
        if (e.eth == "REQ" or (design == "M-cancel-after-release" and e.eth == "REL")) and s.t >= e.deadline:
            out.append(("cancel", replace(s, entries=setv(s.entries, i, replace(e, eth="CAN")))))
        # SOST: sweep a deposit into the reserve against a proof of EntryReleased
        if e.eth == "REL" and e.sost == "PEND":
            out.append(("sweep", replace(s, deposits_pending=s.deposits_pending - e.amount, reserve=s.reserve + e.amount,
                                         entries=setv(s.entries, i, replace(e, sost="SWEPT")))))
        # SOST: refund a deposit to its committed refund address against a proof of EntryCancelled
        if (e.eth == "CAN" or design == "M-refund-no-proof") and e.sost == "PEND":
            out.append(("refund", replace(s, deposits_pending=s.deposits_pending - e.amount,
                                          sost=setv(s.sost, e.user, s.sost[e.user] + e.amount),
                                          entries=setv(s.entries, i, replace(e, sost="REFD")))))
    first_unpaid = next((j for j, x in enumerate(s.exits) if not x.paid), None)
    for j, x in enumerate(s.exits):
        # SOST: pay a proven ExitRequested from the reserve; nonces strictly in order, each once
        in_order = j == first_unpaid or design in ("M-replay-exit", "M-free-dest")
        if (not x.paid or design == "M-replay-exit") and in_order and s.reserve >= x.amount:
            dests = [x.user] + ([USERS] if design == "M-free-dest" else [])   # mutation: relayer picks the payee
            for d in dests:
                out.append(("pay_exit", replace(s, reserve=s.reserve - x.amount, sost=setv(s.sost, d, s.sost[d] + x.amount),
                                                exits=setv(s.exits, j, replace(x, paid=True)))))
    # --- attacker ---
    if design == "D0" and s.reserve > 0:   # attacker holds the reserve key (daemon, or M of N signers)
        out.append(("key_spend", replace(s, reserve=s.reserve - 1, sost=setv(s.sost, USERS, s.sost[USERS] + 1))))
    return out


def circulating(s):
    return sum(s.wsost)


def owed_entries(s):
    # deposits whose fate is still open on SOST but which back nothing on Ethereum yet
    return sum(e.amount for e in s.entries if e.sost == "PEND" and e.eth != "REL")


def unpaid_exits(s):
    return sum(x.amount for x in s.exits if not x.paid)


def invariants(s, design):
    bad = []
    if s.inv + circulating(s) != PREMINT:
        bad.append("wSOST conservation: inventory + circulating != premint")
    if sum(s.sost) + s.deposits_pending + s.reserve != SOST0 * (USERS + 1):
        bad.append("SOST conservation")
    # I1: circulating wSOST is fully backed by native SOST held under the ARV rules
    backing = s.reserve + sum(e.amount for e in s.entries if e.sost == "PEND" and e.eth == "REL")
    if circulating(s) > backing:
        bad.append("I1 circulating > backing")
    # exact accounting (stronger than I1): reserve + released-unswept == circulating + unpaid exits
    if backing != circulating(s) + unpaid_exits(s):
        bad.append("I1/I2 exact accounting broken")
    for e in s.entries:
        if e.eth == "REL" and e.sost in ("REFD", "GONE"):
            bad.append("I3/I5 user kept wSOST and recovered the SOST")
        if e.sost == "SWEPT" and e.eth != "REL":
            bad.append("sweep without release")
    # I4/I10: no party (the attacker included) ever holds more value than it brought.
    # value = SOST + wSOST + its open deposits not yet released + its unpaid exits
    for p in parties():
        v = s.sost[p] + s.wsost[p]
        v += sum(e.amount for e in s.entries if e.user == p and e.sost == "PEND" and e.eth != "REL")
        v += sum(x.amount for x in s.exits if x.user == p and not x.paid)
        if v > SOST0:
            bad.append("I4/I10 a party gained value (appropriation)")
            break
    return bad


def complete(s, design):
    """Service disappearance test (I9): from s, only permissionless relays and the clock act.
    Returns the final state after driving every open item to its end."""
    changed = True
    while changed:
        changed = False
        for name, n in successors(s, design):
            if name in ("tick", "release", "cancel", "sweep", "refund", "pay_exit"):   # no new confirmations, no user actions
                s, changed = n, True
                break
        if not changed and any(e.eth == "REQ" and s.t < e.deadline for e in s.entries):
            s, changed = replace(s, t=s.t + 1), True    # the clock keeps running after the bound
    return s


def user_whole(s):
    # every party ends with exactly its starting value, counted 1:1 in SOST + wSOST
    return all(s.sost[u] + s.wsost[u] == SOST0 for u in parties())


def explore(design):
    start = init()
    seen, q = {start}, deque([start])
    violations, liveness_fail = [], []
    while q:
        s = q.popleft()
        for msg in invariants(s, design):
            violations.append((msg, s))
        f = complete(s, design)
        if invariants(f, design) or not user_whole(f):
            liveness_fail.append(s)
        for _, n in successors(s, design):
            if n not in seen:
                seen.add(n)
                q.append(n)
    return len(seen), violations, liveness_fail


# ---------------------------------------------------------------------------------------
# D1 timing (closed form; the grid below is an ARITHMETIC check of the worst case, not a race model;
# m and f are assumptions — claim censorship by a dominant miner is not modelled): entry HTLC race (block units, 1 block = 600 s at target)
#   user claims wSOST at Ethereum time tc <= T_v (vault HTLC deadline), revealing s;
#   any relayer sees it after <= L blocks-of-time, the SOST claim is mined within m blocks and
#   must be k deep before the SOST refund height H_r. SOST blocks may arrive up to f times
#   faster than target. Unsafe if the user can refund the SOST while keeping the wSOST.
# ---------------------------------------------------------------------------------------
def d1_unsafe(H_r, T_v, L, m, k, f):
    # worst case: claim at the last moment, slowest relay, fastest SOST blocks
    for tc in range(T_v + 1):
        for lat in range(L + 1):
            height_when_seen = (tc + lat) * f          # heights elapsed (fast blocks)
            buried = height_when_seen + m + k
            if buried >= H_r:
                return True
    return False


def d1_bound(T_v, L, m, k, f):
    return (T_v + L) * f + m + k + 1


def main():
    ok = True
    # M-*: D2 with ONE rule removed — the checker must catch every one (non-vacuity)
    expect = {"D0": "FAIL", "D2": "PASS", "D2-deep": "FAIL", "M-noconfirm": "FAIL", "M-cancel-after-release": "FAIL",
              "M-replay-exit": "FAIL", "M-refund-no-proof": "FAIL", "M-free-dest": "FAIL"}
    for d in expect:
        n, viol, live = explore(d)
        kinds = sorted({v[0] for v in viol})
        result = "PASS" if not viol and not live else "FAIL"
        print(f"{d:8} states={n:7}  safety={'none' if not viol else kinds}  liveness_fail={len(live)}  -> {result} (expected {expect[d]})")
        ok &= result == expect[d]
        if d == "D2-deep":
            ok &= any("I1" in k or "I3/I5" in k for k in kinds)
        if d in ("D0", "M-free-dest"):
            ok &= any("I4/I10" in k for k in kinds)
    # D1 timing: the closed-form bound must be exactly the safety threshold over a grid
    grid_ok = True
    for T_v, L, m, k, f in itertools.product(range(1, 6), range(0, 4), range(0, 3), (1, 3), (1, 2)):
        b = d1_bound(T_v, L, m, k, f)
        if d1_unsafe(b, T_v, L, m, k, f) or not d1_unsafe(b - 1, T_v, L, m, k, f):
            grid_ok = False
            print("D1 bound mismatch", T_v, L, m, k, f, b)
    print(f"D1 timing (arithmetic check): H_r >= (T_v + L) * f + m + k + 1 is the worst-case threshold -> {'PASS' if grid_ok else 'FAIL'}")
    ok &= grid_ok
    print("ALL EXPECTED RESULTS HOLD" if ok else "UNEXPECTED RESULT")
    return 0 if ok else 1


if __name__ == "__main__":
    # optional larger bounds: arv_model.py USERS SOST0 PREMINT MAX_DEPOSITS MAX_EXITS TMAX
    if len(sys.argv) == 7:
        USERS, SOST0, PREMINT, MAX_DEPOSITS, MAX_EXITS, TMAX = map(int, sys.argv[1:])
    print(f"bounds: users={USERS}+attacker sost0={SOST0} premint={PREMINT} deposits<={MAX_DEPOSITS} exits<={MAX_EXITS} tmax={TMAX}")
    sys.exit(main())
