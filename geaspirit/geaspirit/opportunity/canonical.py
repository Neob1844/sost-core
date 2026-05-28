"""
Deterministic JSON serialization for opportunity scorecards.

The whole point: any two machines running the same orchestrator over
the same evidence MUST produce byte-identical JSON bytes so the SHA-
256 of the canonical form is stable and can be anchored on chain via
the SOST Protocol Registry (same pattern as Trinity Kalgoorlie).

Rules
-----
* keys sorted alphabetically (json.dumps(sort_keys=True))
* compact separators (',', ':') — no whitespace
* ensure_ascii=False — UTF-8 bytes, not \\uXXXX escapes
* floats rounded to 6 decimal places before serialization
* tuples → lists (json has no tuple type)
* dataclasses → dict via field iteration (no asdict — recursive)
* nested dataclasses recursed
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any


_FLOAT_DECIMALS = 6


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses / tuples / floats into a form
    that json.dumps can serialise deterministically."""
    if dataclasses.is_dataclass(obj):
        # Use field iteration so frozen dataclasses work and so we
        # never accidentally include private attrs.
        out = {}
        for f in dataclasses.fields(obj):
            out[f.name] = _to_jsonable(getattr(obj, f.name))
        return out
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, bool):
        # bool is a subclass of int — branch first to keep True/False
        # not coerced to 1.0 by the float branch below.
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        # Round and normalise so 1.0 vs 1.00000001 don't change the hash
        # when they shouldn't. NaN/inf are NOT supported (json spec).
        if obj != obj:                        # NaN
            raise ValueError("NaN cannot be serialised canonically")
        if obj in (float("inf"), float("-inf")):
            raise ValueError("inf cannot be serialised canonically")
        return round(obj, _FLOAT_DECIMALS)
    # str, None, anything else — leave as-is (json.dumps handles or errors)
    return obj


def canonical_json(obj: Any) -> bytes:
    """Return the canonical UTF-8 byte representation of `obj`.

    The returned bytes are stable across Python versions and machines
    for the same logical input. SHA-256 those bytes to get the chain-
    anchor digest.
    """
    jsonable = _to_jsonable(obj)
    s = json.dumps(
        jsonable,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return s.encode("utf-8")


def sha256_of_canonical(obj: Any) -> str:
    """Convenience: SHA-256 hex digest of canonical_json(obj)."""
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def pretty_json(obj: Any, indent: int = 2) -> str:
    """Indented JSON for human reading. NOT what gets hashed."""
    return json.dumps(
        _to_jsonable(obj),
        sort_keys=True,
        ensure_ascii=False,
        indent=indent,
        allow_nan=False,
    )
