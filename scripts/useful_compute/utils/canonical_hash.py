"""
Canonical JSON serialisation + SHA256 hashing.

The single source of truth for "make this output deterministic and bit-
exact across runs". All Heavy handlers funnel their result dict through
canonical_hash. The same hash MUST be produced for the same input on
two separate Python invocations on the same host AND on a clean venv.

Stdlib only. No 3rd-party JSON libs (orjson, ujson, etc.) — they are NOT
guaranteed bit-identical across versions.
"""

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Stable JSON encoding.

    Rules:
      - sort_keys=True (deterministic key order regardless of dict
        insertion order)
      - separators=(",", ":") (no whitespace, single-byte separators)
      - default=str (anything non-JSON-able coerces to str — sets are
        forbidden in hashed payloads anyway, this is just a safety net)
      - ensure_ascii=False → UTF-8 bytes are stable across Python 3.x
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )


def canonical_sha256(obj: Any) -> str:
    """SHA256 of canonical_json(obj) as a 64-char lower-case hex digest."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def canonical_short_id(obj: Any) -> str:
    """First 16 chars of canonical_sha256 — used for task_id."""
    return canonical_sha256(obj)[:16]
