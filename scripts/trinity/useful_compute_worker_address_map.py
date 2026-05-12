#!/usr/bin/env python3
"""Trinity / Useful Compute — Worker Address Map helper v0.1.

A small CLI that lets operators create and validate a mapping between
``worker_id_hash`` values and SOST payout addresses.

Schema
------
``trinity-worker-address-map/v0.1``:

    {
      "schema": "trinity-worker-address-map/v0.1",
      "workers": [
        {
          "worker_id_hash": "<16-hex>",
          "payout_address": "sost1...",
          "label": "optional human label"
        }
      ]
    }

Hard invariants
---------------
- Does NOT generate addresses.
- Does NOT touch any wallet, key store, RPC endpoint or network.
- Does NOT sign anything.
- ``create-template`` only writes placeholder strings the operator
  must replace manually.
- ``validate`` enforces:
    * the v0.1 schema string
    * unique ``worker_id_hash`` entries
    * unique ``payout_address`` entries (one address per worker)
    * sost1 prefix + bech32-charset body (basic regex, NOT a full
      bech32 checksum — that lives in the wallet sprint).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_MAP = "trinity-worker-address-map/v0.1"

# sost1 + bech32 charset (no [1bio]), 20..80 chars body.
# We deliberately do NOT verify the bech32 checksum in v0.1.
_ADDRESS_RE = re.compile(r"^sost1[023456789acdefghjklmnpqrstuvwxyz]{20,80}$")
_WORKER_HASH_RE = re.compile(r"^[0-9a-f]{16}$")


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def validate_address(addr: str) -> Optional[str]:
    if not isinstance(addr, str):
        return "payout_address must be a string"
    if not _ADDRESS_RE.match(addr):
        return f"payout_address has wrong format: {addr!r}"
    return None


def validate_map(obj: Any) -> List[str]:
    """Return a list of human-readable problems. Empty list means
    the map is well-formed."""
    problems: List[str] = []
    if not isinstance(obj, dict):
        problems.append("address map must be a JSON object")
        return problems
    if obj.get("schema") != SCHEMA_MAP:
        problems.append(
            f"wrong schema: {obj.get('schema')!r}; "
            f"expected {SCHEMA_MAP!r}"
        )
    workers = obj.get("workers")
    if not isinstance(workers, list):
        problems.append("workers must be a list")
        return problems
    seen_hashes: Dict[str, int] = {}
    seen_addresses: Dict[str, int] = {}
    for i, w in enumerate(workers):
        if not isinstance(w, dict):
            problems.append(f"workers[{i}] must be an object")
            continue
        wh = w.get("worker_id_hash", "")
        if not (isinstance(wh, str) and _WORKER_HASH_RE.match(wh)):
            problems.append(
                f"workers[{i}].worker_id_hash wrong format: {wh!r}"
            )
        else:
            if wh in seen_hashes:
                problems.append(
                    f"workers[{i}].worker_id_hash duplicate of "
                    f"workers[{seen_hashes[wh]}]"
                )
            else:
                seen_hashes[wh] = i

        addr = w.get("payout_address", "")
        problem = validate_address(addr)
        if problem is not None:
            problems.append(f"workers[{i}]: {problem}")
        else:
            if addr in seen_addresses:
                problems.append(
                    f"workers[{i}].payout_address duplicate of "
                    f"workers[{seen_addresses[addr]}]"
                )
            else:
                seen_addresses[addr] = i

        label = w.get("label")
        if label is not None and not (
            isinstance(label, str) and 0 < len(label) <= 128
        ):
            problems.append(f"workers[{i}].label wrong format")
        allowed = {"worker_id_hash", "payout_address", "label"}
        extra = set(w.keys()) - allowed
        if extra:
            problems.append(
                f"workers[{i}] has unknown fields: {sorted(extra)}"
            )

    # Top-level extra keys.
    allowed_top = {"schema", "workers"}
    extra_top = set(obj.keys()) - allowed_top
    if extra_top:
        problems.append(
            f"address map has unknown top-level fields: "
            f"{sorted(extra_top)}"
        )
    return problems


def _cmd_create_template(args: argparse.Namespace) -> int:
    n = int(args.entries)
    if n < 1 or n > 1024:
        print(
            "[worker_address_map] entries must be in [1, 1024]",
            file=sys.stderr,
        )
        return 2
    template_workers: List[Dict[str, Any]] = []
    for i in range(n):
        template_workers.append({
            "worker_id_hash": f"{'0' * 15}{i % 16:x}"[:16],
            "payout_address": (
                "sost1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            ),
            "label": f"placeholder-worker-{i}",
        })
    obj = {"schema": SCHEMA_MAP, "workers": template_workers}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        canonical_dumps(obj) + "\n", encoding="utf-8",
    )
    print(
        f"[worker_address_map] wrote template with {n} placeholder "
        f"entries to {out_path}. Replace worker_id_hash and "
        f"payout_address values before use."
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(
            f"[worker_address_map] file not found: {path}",
            file=sys.stderr,
        )
        return 2
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"[worker_address_map] invalid JSON: {exc}",
            file=sys.stderr,
        )
        return 2
    problems = validate_map(obj)
    if problems:
        for p in problems:
            print(f"[worker_address_map] {p}", file=sys.stderr)
        return 2
    workers = obj["workers"]
    print(
        f"[worker_address_map] OK — {len(workers)} entries, "
        f"all sost1 addresses well-formed (no checksum check in v0.1)."
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_worker_address_map",
        description=(
            "Trinity worker address map helper v0.1. Creates and "
            "validates v0.1 mapping files. NEVER generates addresses, "
            "NEVER touches a wallet, NEVER signs."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_t = sub.add_parser(
        "create-template",
        help="Write a JSON template with placeholder entries",
    )
    p_t.add_argument("--out", required=True)
    p_t.add_argument("--entries", type=int, default=3)
    p_t.set_defaults(func=_cmd_create_template)

    p_v = sub.add_parser(
        "validate",
        help="Validate a worker address map file",
    )
    p_v.add_argument("--path", required=True)
    p_v.set_defaults(func=_cmd_validate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
