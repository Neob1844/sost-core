#!/usr/bin/env python3
"""check_decentralization_gates.py — read-only measurement of the #40,000
decentralization gates that can be measured from one node.

What it measures (see docs/v40000/DECENTRALIZATION_ACTION_PLAN_40000.md):

  * peers      getpeerinfo: total / outbound / inbound / handshake-complete,
               distinct /16 networks, the largest /16 share, and — only when
               a local mapping file is given — distinct ASNs, hosting
               providers and regions among the peers.
  * producers  getblockhash + getblock over the last N blocks: distinct
               producer addresses, top-1 share, and the G7 thresholds.
  * seeds      the compiled-in DEFAULT_SEEDS (parsed from src/sost-node.cpp)
               plus an optional seed registry file: how many seeds are
               independent of the project domain / operator / ASN (G4).

What it does NOT measure, and never claims:

  * Operator independence. A peer IP, an ASN or a producer address is not
    an operator. The peer view is one node's view only. The script reports
    lower-level facts; the gates that need operator evidence (G4, G6) are
    only evaluated from a registry file a human has filled with evidence.
  * Anything over the network other than the given node's JSON-RPC.

Read-only: it calls getblockcount, getblockhash, getblock and getpeerinfo
only. It writes nothing except the optional --json-out report. Credentials
come from --rpc-user plus --rpc-pass-file (a mode-600 file) or from the
SOST_RPC_USER / SOST_RPC_PASS environment; they are never printed.

getpeerinfo masks the last two octets of each peer IP (src/sost-node.cpp
mask_addr), so the /16 network is the finest resolution available, and an
ASN mapping can only be matched at /16 granularity.

Stdlib only. Exit code 0 = report produced; with --strict, exit 1 when any
evaluated gate is not met; exit 2 on usage / RPC errors.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import stat
import sys
import urllib.request
from collections import Counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

PROJECT_DOMAIN = "sostcore.com"

# Thresholds (docs/v40000/DECENTRALIZATION_GATES_40000.md).
G4_MIN_INDEPENDENT_SEEDS = 3
G6_MIN_ASNS = 3
G6_MIN_REGIONS = 3
G7_WINDOW = 2016
G7_MIN_PRODUCERS = 5
G7_MAX_TOP_SHARE = 0.50
PEER_MIN_OUTBOUND = 3
PEER_MIN_DISTINCT_16 = 3

RpcCall = Callable[..., Any]


# --------------------------------------------------------------------- RPC

class RpcError(Exception):
    pass


def make_rpc(url: str, user: str, password: str, timeout: int = 30) -> RpcCall:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()

    def call(method: str, *params: Any) -> Any:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": list(params)}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "Authorization": "Basic " + token})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001 — report and stop, never retry blindly
            raise RpcError(f"{method}: {type(e).__name__}") from None
        if resp.get("error"):
            raise RpcError(f"{method}: {resp['error']}")
        return resp.get("result")

    return call


def read_password_file(path: str) -> str:
    st = os.stat(path)
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RpcError(f"{path}: password file must not be group/world accessible (chmod 600)")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ------------------------------------------------------------------- peers

_ADDR_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(?:xxx|\d{1,3})\.(?:xxx|\d{1,3})(?::\d+)?$")


def net16_of(addr: str) -> Optional[str]:
    """'203.0.xxx.xxx:19333' or '203.0.113.7:19333' -> '203.0.0.0/16'.
    Returns None for hostnames or anything that is not an IPv4 form."""
    m = _ADDR_RE.match(addr.strip())
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a > 255 or b > 255:
        return None
    return f"{a}.{b}.0.0/16"


def load_asn_map(entries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for e in entries:
        net = ipaddress.ip_network(str(e["prefix"]), strict=False)
        if net.version != 4:
            continue
        out.append({"net": net, "asn": e.get("asn"), "provider": e.get("provider"),
                    "region": e.get("region")})
    return out


def match_asn(net16: str, asn_map: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match a /16 against the mapping. Returns the entry, None if unmapped,
    or {'ambiguous': True} when overlapping entries disagree on the ASN
    (possible because only the /16 is visible)."""
    n = ipaddress.ip_network(net16)
    hits = [e for e in asn_map if e["net"].overlaps(n)]
    if not hits:
        return None
    if len({e["asn"] for e in hits}) > 1:
        return {"ambiguous": True}
    return hits[0]


def measure_peers(peerinfo: Sequence[Dict[str, Any]],
                  asn_map: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    peers = list(peerinfo or [])
    outbound = [p for p in peers if p.get("direction") == "outbound"]
    acked = [p for p in peers if p.get("version_acked")]
    nets = [net16_of(str(p.get("addr", ""))) for p in peers]
    ip_nets = [n for n in nets if n]
    c16 = Counter(ip_nets)
    res: Dict[str, Any] = {
        "total": len(peers),
        "outbound": len(outbound),
        "inbound": len(peers) - len(outbound),
        "version_acked": len(acked),
        "non_ip_addrs": len(nets) - len(ip_nets),
        "distinct_16": len(c16),
        "largest_16_share": (max(c16.values()) / len(ip_nets)) if ip_nets else None,
        "nets_16": dict(sorted(c16.items())),
    }
    if asn_map is not None:
        asns, providers, regions = set(), set(), set()
        unmapped = ambiguous = 0
        for n in ip_nets:
            m = match_asn(n, asn_map)
            if m is None:
                unmapped += 1
            elif m.get("ambiguous"):
                ambiguous += 1
            else:
                asns.add(m["asn"])
                if m.get("provider"):
                    providers.add(m["provider"])
                if m.get("region"):
                    regions.add(m["region"])
        res.update({"distinct_asns": len(asns), "distinct_providers": len(providers),
                    "distinct_regions": len(regions), "unmapped": unmapped,
                    "ambiguous": ambiguous, "asns": sorted(asns, key=str),
                    "providers": sorted(providers), "regions": sorted(regions)})
    return res


def fetch_peers(call: RpcCall) -> List[Dict[str, Any]]:
    r = call("getpeerinfo")
    return r if isinstance(r, list) else []


# --------------------------------------------------------------- producers

def producer_of(block: Dict[str, Any]) -> str:
    return str(block.get("miner_address") or block.get("miner_pubkey") or "UNKNOWN")


def measure_producers(blocks: Sequence[Dict[str, Any]],
                      merge: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """blocks: getblock results (any order). merge maps address -> entity label
    so the operator can group addresses known to belong to one miner."""
    merge = merge or {}
    prods = [merge.get(producer_of(b), producer_of(b)) for b in blocks]
    c = Counter(prods)
    n = len(prods)
    top_addr, top_n = (c.most_common(1)[0] if c else (None, 0))
    heights = [int(b["height"]) for b in blocks if "height" in b]
    return {
        "blocks": n,
        "from_height": min(heights) if heights else None,
        "to_height": max(heights) if heights else None,
        "distinct_producers": len(c),
        "top_producer": top_addr,
        "top_share": (top_n / n) if n else None,
        "unknown_producer_blocks": c.get("UNKNOWN", 0),
        "counts": dict(c.most_common()),
    }


def fetch_blocks(call: RpcCall, last: int) -> List[Dict[str, Any]]:
    tip = int(call("getblockcount"))
    start = max(0, tip - last + 1)
    out = []
    for h in range(start, tip + 1):
        bh = call("getblockhash", h)
        out.append(call("getblock", bh))
    return out


# ------------------------------------------------------------------- seeds

_SEEDS_BLOCK_RE = re.compile(r"DEFAULT_SEEDS\[\]\s*=\s*\{(.*?)\};", re.S)
_STR_RE = re.compile(r'"([^"]+)"')


def parse_default_seeds(source_text: str) -> List[str]:
    m = _SEEDS_BLOCK_RE.search(source_text)
    if not m:
        return []
    body = "\n".join(line.split("//", 1)[0] for line in m.group(1).splitlines())
    return _STR_RE.findall(body)


def under_project_domain(host: str) -> bool:
    h = host.lower().rstrip(".")
    return h == PROJECT_DOMAIN or h.endswith("." + PROJECT_DOMAIN)


def measure_seeds(default_seeds: Sequence[str],
                  registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """registry = {"project": {"operator": "...", "asns": [..]},
                   "seeds": [{"host","operator","asn","region","evidence"}]}
    A seed counts as independent only if ALL hold: host not under the project
    domain, operator different from the project and from every other counted
    seed, ASN not a project ASN and not already counted, and a non-empty
    'evidence' field (a signed challenge / reachability record)."""
    res: Dict[str, Any] = {
        "default_seeds": list(default_seeds),
        "default_seeds_project_domain": sum(1 for s in default_seeds if under_project_domain(s)),
        "default_seeds_other_domain": sum(1 for s in default_seeds if not under_project_domain(s)),
    }
    if registry is None:
        res["independent_seeds"] = None
        return res
    proj = registry.get("project", {})
    proj_op = str(proj.get("operator", "")).strip().lower()
    proj_asns = {str(a) for a in proj.get("asns", [])}
    ops, asns, regions = set(), set(), set()
    counted, rejected = [], []
    for s in registry.get("seeds", []):
        host = str(s.get("host", ""))
        op = str(s.get("operator", "")).strip().lower()
        asn = str(s.get("asn", "")).strip()
        why = None
        if not host:
            why = "no host"
        elif under_project_domain(host.rsplit(":", 1)[0]):
            why = "project domain"
        elif not op or op == proj_op:
            why = "project or unknown operator"
        elif op in ops:
            why = "operator already counted"
        elif not asn or asn in proj_asns:
            why = "project or unknown ASN"
        elif asn in asns:
            why = "ASN already counted"
        elif not str(s.get("evidence", "")).strip():
            why = "no evidence"
        if why:
            rejected.append({"host": host, "reason": why})
            continue
        ops.add(op)
        asns.add(asn)
        if s.get("region"):
            regions.add(str(s["region"]))
        counted.append(host)
    res.update({"independent_seeds": len(counted), "independent_hosts": counted,
                "independent_regions": len(regions), "rejected": rejected})
    return res


# ------------------------------------------------------------------- gates

def evaluate(peers: Optional[Dict[str, Any]], prods: Optional[Dict[str, Any]],
             seeds: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, Dict[str, Any]] = {}

    def put(name: str, met: Optional[bool], detail: str) -> None:
        g[name] = {"met": met, "status": "NOT_MEASURED" if met is None else
                   ("MET" if met else "NOT_MET"), "detail": detail}

    if peers is not None:
        put("PEER_CONNECTIVITY",
            peers["outbound"] >= PEER_MIN_OUTBOUND and peers["distinct_16"] >= PEER_MIN_DISTINCT_16,
            f"outbound={peers['outbound']} (>= {PEER_MIN_OUTBOUND}), "
            f"distinct /16={peers['distinct_16']} (>= {PEER_MIN_DISTINCT_16}); one node's view only")
        if "distinct_asns" in peers:
            put("G6_PEER_VIEW_ASN_REGION",
                peers["distinct_asns"] >= G6_MIN_ASNS and peers["distinct_regions"] >= G6_MIN_REGIONS,
                f"ASNs={peers['distinct_asns']} (>= {G6_MIN_ASNS}), regions={peers['distinct_regions']} "
                f"(>= {G6_MIN_REGIONS}), unmapped={peers['unmapped']}, ambiguous={peers['ambiguous']}; "
                "necessary, NOT sufficient: G6 also needs a verified operator registry")
        else:
            put("G6_PEER_VIEW_ASN_REGION", None, "no --asn-map given")
    if prods is not None:
        if prods["blocks"] < G7_WINDOW:
            put("G7_PRODUCERS", None,
                f"window {prods['blocks']} < {G7_WINDOW} blocks; distinct={prods['distinct_producers']}, "
                f"top share={prods['top_share']}")
        else:
            put("G7_PRODUCERS",
                prods["distinct_producers"] >= G7_MIN_PRODUCERS and prods["top_share"] < G7_MAX_TOP_SHARE,
                f"distinct={prods['distinct_producers']} (>= {G7_MIN_PRODUCERS}), "
                f"top share={prods['top_share']:.3f} (< {G7_MAX_TOP_SHARE}); addresses, not entities; "
                "one 2016 window only — G7 needs every window over 30 days")
    if seeds is not None:
        if seeds.get("independent_seeds") is None:
            put("G4_INDEPENDENT_SEEDS", False if seeds["default_seeds_other_domain"] == 0 else None,
                f"compiled-in seeds outside {PROJECT_DOMAIN}: {seeds['default_seeds_other_domain']}; "
                "no --seed-registry given (independence needs evidence)")
        else:
            put("G4_INDEPENDENT_SEEDS", seeds["independent_seeds"] >= G4_MIN_INDEPENDENT_SEEDS,
                f"independent seeds with evidence={seeds['independent_seeds']} (>= {G4_MIN_INDEPENDENT_SEEDS}); "
                "14-day >= 99% reachability is measured separately")
    return g


def summarize(gates: Dict[str, Dict[str, Any]]) -> str:
    measured = [v for v in gates.values() if v["met"] is not None]
    if not measured:
        return "NOT_MEASURED"
    if any(v["met"] is None for v in gates.values()):
        return "NO" if any(not v["met"] for v in measured) else "INCOMPLETE"
    return "YES" if all(v["met"] for v in measured) else "NO"


# --------------------------------------------------------------------- CLI

def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run(args: argparse.Namespace, call: Optional[RpcCall] = None) -> Dict[str, Any]:
    peers = prods = seeds = None
    asn_map = load_asn_map(_load_json(args.asn_map)) if args.asn_map else None
    merge = _load_json(args.merge) if args.merge else None

    if args.fixture_dir:
        pi = os.path.join(args.fixture_dir, "getpeerinfo.json")
        bl = os.path.join(args.fixture_dir, "blocks.json")
        if os.path.exists(pi):
            peers = measure_peers(_load_json(pi), asn_map)
        if os.path.exists(bl):
            blocks = _load_json(bl)
            prods = measure_producers(blocks[-args.last:] if args.last else blocks, merge)
    elif call is not None:
        if not args.skip_peers:
            peers = measure_peers(fetch_peers(call), asn_map)
        if args.last:
            prods = measure_producers(fetch_blocks(call, args.last), merge)

    if args.source:
        with open(args.source, "r", encoding="utf-8", errors="replace") as f:
            ds = parse_default_seeds(f.read())
        seeds = measure_seeds(ds, _load_json(args.seed_registry) if args.seed_registry else None)

    gates = evaluate(peers, prods, seeds)
    return {"peers": peers, "producers": prods, "seeds": seeds, "gates": gates,
            "DECENTRALIZATION_GATES_MET_MEASURABLE_SUBSET": summarize(gates),
            "note": "Measures one node's view and on-chain addresses. Not evidence of "
                    "independent operators. G1-G3, G5, G8, G9 need the procedures in "
                    "docs/v40000/DECENTRALIZATION_GATES_40000.md."}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rpc-url", default="http://127.0.0.1:18232")
    p.add_argument("--rpc-user", default=os.environ.get("SOST_RPC_USER", ""))
    p.add_argument("--rpc-pass-file", help="mode-600 file holding the RPC password")
    p.add_argument("--last", type=int, default=G7_WINDOW, help="blocks for producer stats (0 = skip)")
    p.add_argument("--skip-peers", action="store_true")
    p.add_argument("--asn-map", help="JSON list of {prefix, asn, provider, region}")
    p.add_argument("--merge", help="JSON object address -> entity label")
    p.add_argument("--source", help="path to src/sost-node.cpp (parse DEFAULT_SEEDS)")
    p.add_argument("--seed-registry", help="JSON seed registry with evidence")
    p.add_argument("--fixture-dir", help="offline mode: getpeerinfo.json / blocks.json")
    p.add_argument("--json-out")
    p.add_argument("--strict", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    call = None
    try:
        if not args.fixture_dir and (not args.skip_peers or args.last):
            pw = os.environ.get("SOST_RPC_PASS", "")
            if args.rpc_pass_file:
                pw = read_password_file(args.rpc_pass_file)
            call = make_rpc(args.rpc_url, args.rpc_user, pw)
        report = run(args, call)
    except (RpcError, OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    for name, v in sorted(report["gates"].items()):
        print(f"{name:26s} {v['status']:13s} {v['detail']}")
    print(f"MEASURABLE SUBSET: {report['DECENTRALIZATION_GATES_MET_MEASURABLE_SUBSET']}")
    if args.strict and any(v["met"] is False for v in report["gates"].values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
