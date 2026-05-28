"""
Tiny file-based cache for connector responses.

Keyed by SHA-256 of (connector_name, canonical(query_args)). Values
are arbitrary JSON-able payloads with a TTL in seconds. Lives under
geaspirit/data/opportunity/cache/ — caller decides which connector
opts in.

Network connectors should use this so a re-run within the TTL window
doesn't re-hit Overpass / external endpoints unnecessarily.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .canonical import canonical_json


# Cache root relative to this file: geaspirit/geaspirit/opportunity/ →
# geaspirit/data/opportunity/cache/
_HERE = Path(__file__).resolve().parent
_CACHE_ROOT = _HERE.parent.parent / "data" / "opportunity" / "cache"


def _ensure_root() -> Path:
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return _CACHE_ROOT


def _key_for(connector: str, query_args: Any) -> str:
    blob = canonical_json({"c": connector, "q": query_args})
    return hashlib.sha256(blob).hexdigest()[:24]


def cache_get(connector: str, query_args: Any, ttl_seconds: int) -> Optional[Any]:
    """Return cached payload if present AND younger than ttl_seconds.
    None on miss or stale."""
    root = _ensure_root()
    path = root / f"{connector}_{_key_for(connector, query_args)}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            obj = json.load(fh)
        age = time.time() - obj.get("ts", 0)
        if age > ttl_seconds:
            return None
        return obj.get("payload")
    except Exception:
        # Corrupt cache entry — treat as miss; don't error out.
        return None


def cache_put(connector: str, query_args: Any, payload: Any) -> None:
    """Write payload to cache. Atomic via temp file + rename."""
    root = _ensure_root()
    path = root / f"{connector}_{_key_for(connector, query_args)}.json"
    tmp = path.with_suffix(".json.tmp")
    obj = {"ts": int(time.time()), "payload": payload}
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    tmp.replace(path)


def cache_path_for(connector: str, query_args: Any) -> Path:
    """For debugging: where would this query be cached?"""
    return _ensure_root() / f"{connector}_{_key_for(connector, query_args)}.json"
