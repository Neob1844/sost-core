"""Shared pytest configuration for tests/trinity.

Provides a single source of truth for the ``requires_real_council``
marker. Trinity v0.2 (materials track) and v0.1 (geo discovery)
default to invoking the real SOST AI free-tier council from
``materials-engine-private``. That repository is private and is NOT
checked in here, so tests that exercise the real council can only run
on hosts that have it available.

Production scripts must still fail loudly when the real council is
missing (this preserves the "no silent mock in production" invariant
the user asked for). The relaxation is test-only: tests decorated
with ``@requires_real_council`` are SKIPPED rather than failed when
``materials-engine-private`` is not reachable.

Discovery rule:
- Honour ``$TRINITY_MATERIALS_ENGINE_PATH`` first, then fall back to
  ``~/SOST/materials-engine-private``.
- Require that ``<root>/src/multi_ai_review`` is a directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _real_council_available() -> bool:
    me_env = os.environ.get("TRINITY_MATERIALS_ENGINE_PATH")
    candidates = []
    if me_env:
        candidates.append(Path(me_env))
    candidates.append(Path.home() / "SOST" / "materials-engine-private")
    for c in candidates:
        try:
            if c.exists() and (c / "src" / "multi_ai_review").is_dir():
                return True
        except OSError:
            continue
    return False


REAL_COUNCIL_AVAILABLE = _real_council_available()

requires_real_council = pytest.mark.skipif(
    not REAL_COUNCIL_AVAILABLE,
    reason=(
        "materials-engine-private not available on this host. "
        "Set TRINITY_MATERIALS_ENGINE_PATH or place the repo at "
        "~/SOST/materials-engine-private to run real-council tests."
    ),
)
