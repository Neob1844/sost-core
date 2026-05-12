"""Trinity Autonomy keeps the geo dossier disclaimers intact and
never produces public-claim language in summary / lessons / bundle
outputs."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from conftest import requires_real_council


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
OBJECTIVES_DIR = REPO_ROOT / "config" / "trinity" / "objectives"


_REQUIRED_GEO_DISCLAIMERS = (
    "autonomous AOI proposal",
    "remote proxy evidence only",
    "no field validation",
    "no drilling evidence",
    "no confirmed mineralization",
    "not a mineral reserve claim",
    "requires geological review before any public claim",
)

_PUBLIC_CLAIM_TOKENS_PROHIBITED_OUTSIDE_DISCLAIMER = (
    r"\bconfirmed\s+deposit\b",
    r"\bdiscovered\s+ore\b",
    r"\bmineral\s+reserves\s+confirmed\b",
    r"\bdrilling\s+confirmed\b",
)


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def orch_mod():
    return _load(
        "trinity_orch_pubclaims",
        SCRIPTS_DIR / "trinity_orchestrator.py",
    )


@requires_real_council
def test_geo_disclaimers_survive_full_run(tmp_path, orch_mod):
    orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=tmp_path, count=25,
    )
    geo_md = (tmp_path / "geo" /
              "TRINITY_GEO_DOSSIER_global_phase1.md").read_text(
                  encoding="utf-8"
              )
    for phrase in _REQUIRED_GEO_DISCLAIMERS:
        assert phrase.lower() in geo_md.lower(), (
            f"geo dossier MD lost disclaimer {phrase!r}"
        )


@requires_real_council
def test_summary_md_has_no_prohibited_claim_tokens(tmp_path, orch_mod):
    r = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=tmp_path, count=25,
    )
    md = Path(r["paths"]["summary"]).read_text(encoding="utf-8")
    for pattern in _PUBLIC_CLAIM_TOKENS_PROHIBITED_OUTSIDE_DISCLAIMER:
        assert re.search(pattern, md, re.IGNORECASE) is None, (
            f"summary MD contains prohibited claim token: {pattern}"
        )


@requires_real_council
def test_bundle_carries_disclaimers(tmp_path, orch_mod):
    r = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=tmp_path, count=25,
    )
    bundle = json.loads(
        Path(r["paths"]["bundle"]).read_text(encoding="utf-8")
    )
    assert "no automatic payout" in bundle["disclaimers"]
    assert "no on-chain registration" in bundle["disclaimers"]
    assert "council acts as critic; humans review final claims" \
        in bundle["disclaimers"]
