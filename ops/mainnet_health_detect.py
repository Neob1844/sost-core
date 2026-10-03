#!/usr/bin/env python3
# mainnet_health_detect.py — pure-stdlib detection core for the SOST mainnet
# health monitor. It takes a *combined snapshot* (two or more observers of the
# SAME mainnet) and emits the labelled health conditions + an ALERT verdict.
#
# This module touches NO node, NO network and NO key. It is pure: snapshots in,
# findings out. That is deliberate — ops/mainnet-health-monitor.sh does the
# (read-only) data collection and hands the result here, and
# scripts/mainnet_health_monitor_test.sh feeds it *synthetic* snapshots to
# prove the labels fire correctly without touching any real node.
#
# Combined-snapshot schema (see the monitor for how it is built):
# {
#   "ts": "2026-..Z", "ts_epoch": 179..,
#   "thresholds": { "stall_secs":1800, "min_peers":1,
#                   "max_height_gap":2, "expected_version":null },
#   "observers": [
#     { "observer":"LOCAL",  "rpc_alive":true, "node_alive":true,
#       "height":29045, "tip_hash":"..", "chainwork":null,
#       "last_block_age_secs":123, "peers":2, "mempool":0,
#       "version":"0.3.2", "block_acceptance":"advancing",
#       "reachable":true, "error":null },
#     { "observer":"STRATO", ... }
#   ]
# }
#
# Conditions labelled: TIP_DIVERGENCE, HEIGHT_STALL, NODE_DOWN, PEER_DROP,
# RPC_FAILURE, CHAINWORK_DIVERGENCE, OLD_VERSION. ALERT is raised when two
# observers disagree, or when any observer is down / stalled.
#
# NEVER fabricates: a field that is null/unknown is skipped, not guessed.

import argparse
import json
import sys

DEFAULT_THRESHOLDS = {
    "stall_secs": 1800,       # 30 min (~3 block times at 10 min)
    "min_peers": 1,           # below this -> PEER_DROP
    "max_height_gap": 2,      # heights further apart than this -> divergence
    "expected_version": None, # if set, a mismatch -> OLD_VERSION
}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def detect(snapshot):
    """Return (conditions, alert) for a combined snapshot dict.

    conditions: list of {scope, observer, code, detail}
    alert:      bool
    """
    thr = dict(DEFAULT_THRESHOLDS)
    thr.update(snapshot.get("thresholds") or {})
    observers = snapshot.get("observers") or []
    conditions = []

    # ---- per-observer conditions -------------------------------------------
    for ob in observers:
        name = ob.get("observer", "?")

        reachable = ob.get("reachable")
        rpc_alive = ob.get("rpc_alive")
        node_alive = ob.get("node_alive")

        # An observer we could not reach at all, or whose RPC/node is down,
        # is NODE_DOWN. RPC_FAILURE is reported in addition when the transport
        # reached something but the RPC itself did not answer.
        down = (reachable is False) or (node_alive is False) or (rpc_alive is False)
        if down:
            detail = ob.get("error") or "node/rpc not answering"
            conditions.append({"scope": "observer", "observer": name,
                               "code": "NODE_DOWN", "detail": detail})
            if rpc_alive is False and reachable is not False:
                conditions.append({"scope": "observer", "observer": name,
                                   "code": "RPC_FAILURE",
                                   "detail": "transport up but RPC did not answer"})
            # A down observer gives no further usable fields; stop here for it.
            continue

        # HEIGHT_STALL — RPC up but the tip is older than the stall window.
        age = ob.get("last_block_age_secs")
        if _num(age) and age >= thr["stall_secs"]:
            conditions.append({"scope": "observer", "observer": name,
                               "code": "HEIGHT_STALL",
                               "detail": "tip age %ss >= %ss" % (int(age), thr["stall_secs"])})

        # PEER_DROP
        peers = ob.get("peers")
        if _num(peers) and peers < thr["min_peers"]:
            conditions.append({"scope": "observer", "observer": name,
                               "code": "PEER_DROP",
                               "detail": "%s peers < min %s" % (int(peers), thr["min_peers"])})

        # OLD_VERSION (only if an expected version is configured)
        exp = thr.get("expected_version")
        ver = ob.get("version")
        if exp and ver and ver != exp:
            conditions.append({"scope": "observer", "observer": name,
                               "code": "OLD_VERSION",
                               "detail": "version %s != expected %s" % (ver, exp)})

    # ---- cross-observer conditions (pairwise over reachable observers) -----
    live = [o for o in observers
            if o.get("reachable") is not False
            and o.get("rpc_alive") is not False
            and o.get("node_alive") is not False]

    for i in range(len(live)):
        for k in range(i + 1, len(live)):
            a, b = live[i], live[k]
            na, nb = a.get("observer", "A"), b.get("observer", "B")
            ha, hb = a.get("height"), b.get("height")
            ta, tb = a.get("tip_hash"), b.get("tip_hash")
            wa, wb = a.get("chainwork"), b.get("chainwork")

            # Same height, different tip hash -> genuine fork / divergence.
            if _num(ha) and _num(hb) and ha == hb and ta and tb and ta != tb:
                conditions.append({"scope": "cross", "observer": "%s|%s" % (na, nb),
                                   "code": "TIP_DIVERGENCE",
                                   "detail": "height %s but tips differ (%s.. vs %s..)"
                                             % (ha, str(ta)[:12], str(tb)[:12])})
            # Heights too far apart -> one observer is on a different/longer tip.
            elif _num(ha) and _num(hb) and abs(ha - hb) > thr["max_height_gap"]:
                conditions.append({"scope": "cross", "observer": "%s|%s" % (na, nb),
                                   "code": "TIP_DIVERGENCE",
                                   "detail": "height gap %s > %s (%s=%s, %s=%s)"
                                             % (abs(ha - hb), thr["max_height_gap"],
                                                na, ha, nb, hb)})

            # Chainwork divergence — only when both expose chainwork AND tips
            # differ (equal tips with unequal reported work would be a bug in
            # one node's accounting, still worth flagging).
            if wa and wb and wa != wb and ta != tb:
                conditions.append({"scope": "cross", "observer": "%s|%s" % (na, nb),
                                   "code": "CHAINWORK_DIVERGENCE",
                                   "detail": "chainwork differs (%s.. vs %s..)"
                                             % (str(wa)[:16], str(wb)[:16])})

    alert = len(conditions) > 0
    return conditions, alert


def render(snapshot, conditions, alert):
    lines = []
    lines.append("==================== SOST MAINNET HEALTH =====================")
    lines.append("sampled: %s" % snapshot.get("ts", "?"))
    thr = dict(DEFAULT_THRESHOLDS)
    thr.update(snapshot.get("thresholds") or {})
    lines.append("thresholds: stall>=%ss  min_peers=%s  max_height_gap=%s  expected_version=%s"
                 % (thr["stall_secs"], thr["min_peers"], thr["max_height_gap"],
                    thr.get("expected_version") or "(any)"))
    lines.append("--------------------------------------------------------------")
    hdr = "%-8s %-7s %-9s %-14s %-6s %-5s %-8s %-9s" % (
        "OBSERVER", "RPC", "HEIGHT", "TIP", "PEERS", "MEMP", "VERSION", "TIP_AGE")
    lines.append(hdr)
    for ob in snapshot.get("observers", []):
        rpc = "UP" if ob.get("rpc_alive") else ("DOWN" if ob.get("rpc_alive") is False else "?")
        if ob.get("reachable") is False:
            rpc = "UNREACH"
        tip = ob.get("tip_hash")
        tip = (str(tip)[:12] + "..") if tip else "n/a"
        age = ob.get("last_block_age_secs")
        age = ("%ss" % int(age)) if _num(age) else "n/a"
        lines.append("%-8s %-7s %-9s %-14s %-6s %-5s %-8s %-9s" % (
            ob.get("observer", "?"), rpc,
            ob.get("height") if _num(ob.get("height")) else "n/a",
            tip,
            ob.get("peers") if _num(ob.get("peers")) else "n/a",
            ob.get("mempool") if _num(ob.get("mempool")) else "n/a",
            ob.get("version") or "n/a",
            age))
    lines.append("--------------------------------------------------------------")
    if not conditions:
        lines.append("VERDICT: OK — observers agree, no conditions detected.")
    else:
        lines.append("VERDICT: ALERT — %d condition(s):" % len(conditions))
        for c in conditions:
            lines.append("  [%s] %-20s (%s) %s" % (
                c["scope"].upper(), c["code"], c["observer"], c["detail"]))
    lines.append("ALERT=%s" % ("YES" if alert else "NO"))
    lines.append("==============================================================")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="SOST mainnet health detection core (pure; no node access).")
    ap.add_argument("--snapshot", help="combined snapshot JSON file ('-' for stdin)", default="-")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of a table")
    args = ap.parse_args(argv)

    if args.snapshot == "-":
        data = sys.stdin.read()
    else:
        with open(args.snapshot, "r") as fh:
            data = fh.read()
    snapshot = json.loads(data)

    conditions, alert = detect(snapshot)

    if args.json:
        print(json.dumps({"ts": snapshot.get("ts"),
                          "alert": alert,
                          "conditions": conditions}, indent=2))
    else:
        print(render(snapshot, conditions, alert))

    # Exit code: 0 = OK, 1 = at least one condition (useful for cron/alerting).
    return 1 if alert else 0


if __name__ == "__main__":
    sys.exit(main())
