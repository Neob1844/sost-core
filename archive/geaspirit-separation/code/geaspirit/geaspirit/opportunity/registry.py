"""
Protocol Registry capsule helper for opportunity scorecards and
campaigns.

A *capsule* is a short, single-line string we can hand to ``sost-cli``
to anchor an opportunity artefact on the SOST chain via the Protocol
Registry. The chain stores the capsule body verbatim; what makes it
load-bearing is the embedded SHA-256 of the canonical JSON, which any
auditor can re-compute from a published copy of the same artefact.

Capsule shape (deliberately ASCII, no leading whitespace, ``key=value``
pairs separated by single spaces):

    GEASPIRIT_OPPORTUNITY_SCORECARD_V1 sha256=<64hex> aoi=<aoi_name|redacted> \
        class=<opportunity_class> grade=<class_grade> commercial=<int> \
        schema=<schema_version> not_resource_estimate=true

    GEASPIRIT_OPPORTUNITY_CAMPAIGN_V1 sha256=<64hex> name=<campaign_name> \
        count=<aoi_count> schema=<schema_version> \
        not_resource_estimate=true

Rules
-----
* the embedded hash is the SHA-256 of the canonical JSON of the input
  file as-loaded — re-encoding may change byte ordering, do not re-
  serialise before hashing.
* AOI names containing spaces or punctuation are bracketed so the
  capsule remains parseable; ``redact_aoi=True`` collapses the name
  to the literal string ``redacted``.
* the helper NEVER touches the network or the chain; it only prints
  the capsule body + a suggested ``sost-cli`` invocation. The operator
  decides when to submit.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


SCORECARD_CAPSULE_PREFIX = "GEASPIRIT_OPPORTUNITY_SCORECARD_V1"
CAMPAIGN_CAPSULE_PREFIX  = "GEASPIRIT_OPPORTUNITY_CAMPAIGN_V1"

# Anything outside [A-Za-z0-9_./-] gets bracketed so the capsule remains
# trivially tokenisable.
_SAFE = re.compile(r"^[A-Za-z0-9_./-]+$")


def _safe_str(value: str) -> str:
    if not value:
        return "unknown"
    if _SAFE.match(value):
        return value
    # Bracket form: square brackets are not part of base64/hex and not
    # in standard hex/sha256 alphabets — easy to strip on the consuming
    # end. We also collapse internal whitespace to single spaces inside
    # the bracket to keep the capsule one-line-safe.
    flat = re.sub(r"\s+", " ", value.strip())
    return f"[{flat}]"


def sha256_hex_of_file(path: Path) -> str:
    """SHA-256 of the file's bytes verbatim."""
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


# ─── input detection ───────────────────────────────────────────────

def _looks_like_scorecard(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and obj.get("schema_version") == "opportunity_scorecard.v1"
        and "opportunity_class" in obj
        and "subscores" in obj
    )


def _looks_like_campaign_summary(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and obj.get("schema_version", "").startswith("opportunity_campaign")
        and "aoi_count" in obj
    )


# ─── capsule construction ──────────────────────────────────────────

def build_scorecard_capsule(
    canonical_path: Path,
    *,
    redact_aoi: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """Return ``(capsule_body, parsed_payload)`` for a scorecard
    canonical JSON. The capsule body is the literal string to paste
    on chain; the parsed payload is the loaded JSON dict (useful for
    operator-side display)."""
    canonical_path = Path(canonical_path)
    payload = json.loads(canonical_path.read_bytes())
    if not _looks_like_scorecard(payload):
        raise ValueError(
            f"{canonical_path} does not look like an opportunity scorecard "
            f"(expected schema_version='opportunity_scorecard.v1', got "
            f"{payload.get('schema_version')!r})"
        )
    sha = sha256_hex_of_file(canonical_path)
    aoi_name = "redacted" if redact_aoi else payload["aoi"]["name"]
    body = (
        f"{SCORECARD_CAPSULE_PREFIX} "
        f"sha256={sha} "
        f"aoi={_safe_str(aoi_name)} "
        f"class={_safe_str(payload['opportunity_class'])} "
        f"grade={_safe_str(payload['class_grade'])} "
        f"commercial={int(payload['subscores']['commercial'])} "
        f"schema={_safe_str(payload['schema_version'])} "
        f"not_resource_estimate=true"
    )
    return body, payload


def build_campaign_capsule(
    canonical_path: Path,
    *,
    redact_name: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    canonical_path = Path(canonical_path)
    payload = json.loads(canonical_path.read_bytes())
    if not _looks_like_campaign_summary(payload):
        raise ValueError(
            f"{canonical_path} does not look like a campaign summary "
            f"(expected schema_version starting with 'opportunity_campaign')"
        )
    sha = sha256_hex_of_file(canonical_path)
    name = "redacted" if redact_name else payload.get("campaign_name", "")
    body = (
        f"{CAMPAIGN_CAPSULE_PREFIX} "
        f"sha256={sha} "
        f"name={_safe_str(name)} "
        f"count={int(payload.get('aoi_count', 0))} "
        f"schema={_safe_str(payload['schema_version'])} "
        f"not_resource_estimate=true"
    )
    return body, payload


# ─── unified entry point ───────────────────────────────────────────

def build_capsule(
    canonical_path: Path,
    *,
    redact: bool = False,
) -> Tuple[str, str, Dict[str, Any]]:
    """Detect the input kind (scorecard vs campaign) and emit the
    appropriate capsule. Returns ``(kind, capsule_body, payload)``."""
    canonical_path = Path(canonical_path)
    payload = json.loads(canonical_path.read_bytes())
    if _looks_like_scorecard(payload):
        body, _ = build_scorecard_capsule(canonical_path, redact_aoi=redact)
        return "scorecard", body, payload
    if _looks_like_campaign_summary(payload):
        body, _ = build_campaign_capsule(canonical_path, redact_name=redact)
        return "campaign", body, payload
    raise ValueError(
        f"{canonical_path} is neither an opportunity scorecard nor a "
        f"campaign summary (schema_version="
        f"{payload.get('schema_version')!r})"
    )


def suggested_sost_cli_command(capsule_body: str) -> str:
    """The exact one-liner the operator would run to anchor this
    capsule. We DO NOT execute it ourselves."""
    # Use single quotes; capsule body is ASCII by construction.
    return (
        "sost-cli registry-note "
        f"--body '{capsule_body}'"
    )
