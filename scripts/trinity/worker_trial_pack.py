#!/usr/bin/env python3
"""Trinity External Worker Trial Pack v0.1 (Sprint 5.37).

Generates a portable, distributable, read-only trial-pack
directory that a *second* machine or person can run as a Trinity
Useful Compute worker, with NO wallet, NO private key, NO seed
phrase, NO broadcast capability, and NO network in the worker
process itself.

The pack lets the external worker run one deterministic request
(against the Sprint 5.32 ``local_materials_engine_v01`` backend by
default) and verify their ``compute_output_sha256`` matches the
expected value that the pack ships pre-baked. That cross-host
equality is the Sprint 5.12 replay contract; the trial pack is
the friendly on-ramp for proving a new worker host satisfies it.

Hard invariants v0.1 (enforced by static tests):
    - The trial-pack directory contains NO secret material:
      no 64-hex blob, no BIP39 mnemonic, no real sost1 address.
    - No network. No DNS lookup. No child process. No shell. No
      eval / exec.
    - No wallet creation, no key generation, no signing, no
      broadcasting.
    - Address-map entries are template placeholders only
      (``<PAYOUT_ADDRESS_FOR_<worker_id>>``).
    - Deterministic for fixed inputs: same (worker_id,
      pinned_time, request_fixture, repo_commit, repo_tag) ALWAYS
      produce identical pack bytes.

Usage:
    python3 scripts/trinity/worker_trial_pack.py \\
        --worker-id worker-D \\
        --pinned-time 2026-05-18T00:00:00+00:00 \\
        --out-dir /var/lib/trinity/trial-packs/worker-D \\
        --request-fixture tests/trinity/fixtures/useful_compute/\\
request_scientific_intake.json \\
        --repo-commit  <commit-sha> \\
        --repo-tag     <tag>

Output files written under ``--out-dir``:
    PACK_MANIFEST.json
    README_WORKER_TRIAL.md
    worker_config.json
    sample_request.json
    expected_result_hashes.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_MANIFEST = "trinity-worker-trial-pack-manifest/v0.1"
SCHEMA_EXPECTED = "trinity-worker-trial-pack-expected/v0.1"
SCHEMA_WORKER_CONFIG = "trinity-worker-trial-pack-config/v0.1"

# The pack ships a fixed set of files; the manifest hashes every
# one of them so the recipient can verify the pack is intact.
PACK_FILES = (
    "README_WORKER_TRIAL.md",
    "worker_config.json",
    "sample_request.json",
    "expected_result_hashes.json",
)

# Pack-level safety flags. All const-True; never operator-settable.
PACK_SAFETY_FLAGS = (
    "no_wallet_required",
    "no_private_key_required",
    "no_seed_phrase_required",
    "no_broadcast_capability",
    "no_network_in_worker_process",
    "pack_carries_no_secrets",
)


class TrialPackError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_text(s: str) -> str:
    return _sha256_bytes(s.encode("utf-8"))


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _validate_worker_id(worker_id: str) -> None:
    if not isinstance(worker_id, str):
        raise TrialPackError("worker-id must be a string")
    if not (1 <= len(worker_id) <= 64):
        raise TrialPackError(
            "worker-id length must be 1..64; got " + str(len(worker_id))
        )
    for ch in worker_id:
        if not (ch.isalnum() or ch in "-_."):
            raise TrialPackError(
                "worker-id may only contain [A-Za-z0-9._-]; "
                "found " + repr(ch)
            )


def _validate_commit(repo_commit: str) -> None:
    if not isinstance(repo_commit, str) or not (7 <= len(repo_commit) <= 64):
        raise TrialPackError(
            "repo-commit length must be 7..64; got "
            + repr(repo_commit)
        )
    for ch in repo_commit:
        if ch not in "0123456789abcdef":
            raise TrialPackError(
                "repo-commit must be lowercase hex; found "
                + repr(ch)
            )


def _validate_tag(repo_tag: str) -> None:
    if not isinstance(repo_tag, str) or not (1 <= len(repo_tag) <= 64):
        raise TrialPackError(
            "repo-tag length must be 1..64; got " + repr(repo_tag)
        )
    for ch in repo_tag:
        if not (ch.isalnum() or ch in "-_./"):
            raise TrialPackError(
                "repo-tag may only contain [A-Za-z0-9._/-]; found "
                + repr(ch)
            )


# ---------------------------------------------------------------------------
# Request loading
# ---------------------------------------------------------------------------


def _load_request(request_fixture: Path) -> Dict[str, Any]:
    if not request_fixture.is_file():
        raise TrialPackError(
            "request-fixture not readable: " + str(request_fixture)
        )
    try:
        with open(request_fixture, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise TrialPackError(
            "request-fixture not valid JSON: " + str(exc)
        )
    if not isinstance(obj, dict):
        raise TrialPackError("request-fixture root must be an object")
    return obj


# ---------------------------------------------------------------------------
# Expected hash computation (operator-side, deterministic)
# ---------------------------------------------------------------------------
#
# The pack generator runs ONCE on the operator's host to compute
# the canonical compute_output_sha256 the recipient should reach.
# We import the backend module directly. This is operator-side
# behaviour; the resulting pack JSON contains NO live import
# surface, only the resulting hash and metadata.
#
# NOTE: this is the ONLY place this script touches sibling modules.
# A static safety test enforces no other sibling import paths.


def _compute_expected_hashes(
    request_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the materials_engine backend once over the request and
    return the canonical {compute_output_sha256, backend_name,
    backend_kind, materials_engine_summary}. The result is exactly
    what an external worker should produce.

    Uses the public ``select_backend`` + ``run_backend`` entry
    points so the bytes match the worker pipeline byte-for-byte.
    """
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import useful_compute_backends as _backends  # type: ignore
    except ImportError as exc:
        raise TrialPackError(
            "cannot import useful_compute_backends: " + str(exc)
        )
    task_type = request_obj.get("task_type")
    if not isinstance(task_type, str) or not task_type:
        raise TrialPackError(
            "request missing task_type for trial pack"
        )
    rid = request_obj.get("request_id", "") or ""
    input_sha = request_obj.get("input_bundle_sha256", "") or ""
    # Reproduce the worker's seed64 derivation byte-for-byte.
    seed_blob = _canonical_dumps({
        "rid": rid, "sha": input_sha,
    }).encode("utf-8")
    seed64 = int.from_bytes(
        hashlib.sha256(seed_blob).digest()[:8], "big",
    )
    try:
        spec = _backends.select_backend(
            task_type=task_type,
            backend_name="local_materials_engine_v01",
            allow_experimental=False,
        )
        backend_result = _backends.run_backend(
            spec,
            request=request_obj,
            deterministic_seed=seed64,
            input_bundle_bytes=None,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise TrialPackError(
            "materials_engine backend raised on the trial request: "
            + repr(exc)
        )
    output_obj = getattr(backend_result, "output_obj", None)
    if not isinstance(output_obj, dict):
        raise TrialPackError("backend result missing output_obj dict")
    output_blob = _canonical_dumps(output_obj)
    compute_output_sha256 = _sha256_text(output_blob)
    spec_obj = getattr(backend_result, "spec", None)
    backend_name = str(getattr(spec_obj, "name", "")) if spec_obj else ""
    backend_kind = str(getattr(spec_obj, "kind", "")) if spec_obj else ""
    expected = {
        "schema": SCHEMA_EXPECTED,
        "backend_name":   backend_name,
        "backend_kind":   backend_kind,
        "compute_output_sha256": compute_output_sha256,
        "top_ranked_material":   output_obj.get(
            "top_ranked_material", ""
        ),
        "top_ranked_score":      output_obj.get(
            "top_ranked_score", 0.0
        ),
        "known_materials":       list(
            output_obj.get("known_materials", []) or []
        ),
        "materials_project_cache_used":
            bool(output_obj.get("materials_project_cache_used", False)),
        "materials_project_cache_version":
            str(output_obj.get(
                "materials_project_cache_version", "missing",
            )),
        "materials_project_cache_sha256":
            str(output_obj.get(
                "materials_project_cache_sha256", "0" * 64,
            )),
        "materials_project_cache_hit_count":
            len(output_obj.get(
                "materials_project_cache_hits", [],
            ) or []),
        "materials_project_cache_miss_count":
            len(output_obj.get(
                "materials_project_cache_misses", [],
            ) or []),
    }
    return expected


# ---------------------------------------------------------------------------
# README + worker_config templates
# ---------------------------------------------------------------------------


def _build_worker_config(
    worker_id: str,
    pinned_time: str,
    repo_commit: str,
    repo_tag: str,
    request_basename: str,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA_WORKER_CONFIG,
        "worker_id": worker_id,
        "worker_id_hash": _sha16(worker_id),
        "pinned_time": pinned_time,
        "repo_commit": repo_commit,
        "repo_tag": repo_tag,
        "preferred_backend": "local_materials_engine_v01",
        "supported_backends": [
            "local_materials_engine_v01",
            "placeholder_scientific_intake",
        ],
        "sample_request_basename": request_basename,
        "expected_hashes_basename": "expected_result_hashes.json",
        "address_map_template": {
            "schema": "trinity-worker-address-map/v0.1",
            "workers": [
                {
                    "worker_id_hash": _sha16(worker_id),
                    "payout_address":
                        "<PAYOUT_ADDRESS_FOR_" + worker_id + ">",
                    "label": worker_id,
                },
            ],
            "_template_notice": (
                "Replace <PAYOUT_ADDRESS_FOR_*> out-of-band. The "
                "trial pack never carries a real address."
            ),
        },
        "safety_status": {flag: True for flag in PACK_SAFETY_FLAGS},
        "notes": [
            "Trial-pack worker runs are LOCAL-DRY-RUN only.",
            "Worker process must NOT have a wallet on disk.",
            "Worker process must NOT have network egress credentials.",
        ],
    }


def _build_readme(
    worker_id: str,
    pinned_time: str,
    repo_commit: str,
    repo_tag: str,
    expected_hashes: Dict[str, Any],
) -> str:
    lines: List[str] = []
    a = lines.append
    a("# Trinity External Worker Trial Pack")
    a("")
    a("**Worker id:** `" + worker_id + "`  ")
    a("**Pinned time:** `" + pinned_time + "`  ")
    a("**Repo commit:** `" + repo_commit + "`  ")
    a("**Repo tag:** `" + repo_tag + "`  ")
    a("**Backend:** `local_materials_engine_v01` (Sprint 5.32 real_backend)  ")
    a("")
    a("This pack lets you run ONE deterministic Trinity Useful "
      "Compute request on a fresh worker host and verify your "
      "output matches the operator's expected hash. No wallet, "
      "no private key, no broadcast surface.")
    a("")
    a("## Files in this pack")
    a("")
    a("- `PACK_MANIFEST.json` — pack identity + per-file sha256")
    a("- `README_WORKER_TRIAL.md` — this file")
    a("- `worker_config.json` — pinned worker configuration")
    a("- `sample_request.json` — the request to run")
    a("- `expected_result_hashes.json` — expected output hash")
    a("")
    a("## Safety contract")
    a("")
    a("- NO wallet required")
    a("- NO private key required")
    a("- NO seed phrase required")
    a("- NO broadcast capability")
    a("- NO network in the worker process")
    a("- Pack carries NO secrets")
    a("")
    a("## How to run")
    a("")
    a("1. Clone the SOST repo at commit `" + repo_commit + "`:")
    a("")
    a("       git clone <repo-url>")
    a("       cd sost-core")
    a("       git checkout " + repo_commit)
    a("")
    a("2. Place this pack alongside the repo, e.g. `/var/trinity/trial-pack/`.")
    a("")
    a("3. Run the worker against the pack's sample request:")
    a("")
    a("       python3 scripts/trinity/useful_compute_worker.py \\")
    a("           --mode local-dry-run \\")
    a("           --request <PACK>/sample_request.json \\")
    a("           --out-dir <PACK>/worker_out \\")
    a("           --worker-id " + worker_id + " \\")
    a("           --pinned-time " + pinned_time)
    a("")
    a("4. Find your worker result JSON under `<PACK>/worker_out/"
      "TRINITY_USEFUL_COMPUTE_RESULT_<request_id>_<worker>.json`.")
    a("")
    a("5. Verify your `compute_output_sha256` matches:")
    a("")
    a("       expected_compute_output_sha256 = `"
      + str(expected_hashes.get("compute_output_sha256", "")) + "`")
    a("")
    a("   You can compute yours with:")
    a("")
    a("       python3 -c \"import json,sys;"
      "r=json.load(open(sys.argv[1]));"
      "print(r['compute_output_sha256'])\" \\")
    a("           <PACK>/worker_out/TRINITY_USEFUL_COMPUTE_RESULT_*.json")
    a("")
    a("   The two strings MUST be identical. If they differ, "
      "your worker is producing different bytes for the same "
      "request — your environment is drifting from the canonical "
      "Trinity deterministic contract.")
    a("")
    a("## What this proves")
    a("")
    a("If your `compute_output_sha256` equals the expected value, "
      "your host honours the Sprint 5.12 cross-worker replay "
      "contract. Once that is true, the operator can add your "
      "worker to a real queue and your results will validate "
      "against other workers byte-for-byte.")
    a("")
    a("## What this does NOT do")
    a("")
    a("- It does NOT pay you. The pack contains a placeholder "
      "`<PAYOUT_ADDRESS_FOR_" + worker_id + ">`; the operator "
      "replaces it out-of-band only after you pass the trial.")
    a("- It does NOT open the network. No DNS lookup, no socket.")
    a("- It does NOT broadcast. No chain-cli, no send-raw-transaction.")
    a("- It does NOT sign anything.")
    a("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Pack builder
# ---------------------------------------------------------------------------


def build_trial_pack(
    *,
    worker_id: str,
    pinned_time: str,
    out_dir: Path,
    request_fixture: Path,
    repo_commit: str,
    repo_tag: str,
) -> Dict[str, Any]:
    _validate_worker_id(worker_id)
    _validate_commit(repo_commit)
    _validate_tag(repo_tag)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Load + materialise the sample request.
    request_obj = _load_request(Path(request_fixture))
    sample_request_text = _canonical_dumps(request_obj) + "\n"

    # 2) Compute expected hash.
    expected = _compute_expected_hashes(request_obj)

    # 3) Build worker_config.
    config = _build_worker_config(
        worker_id=worker_id,
        pinned_time=pinned_time,
        repo_commit=repo_commit,
        repo_tag=repo_tag,
        request_basename="sample_request.json",
    )
    config_text = _canonical_dumps(config) + "\n"
    expected_text = _canonical_dumps(expected) + "\n"

    # 4) README.
    readme_text = _build_readme(
        worker_id=worker_id,
        pinned_time=pinned_time,
        repo_commit=repo_commit,
        repo_tag=repo_tag,
        expected_hashes=expected,
    )

    # 5) Per-file write + sha256.
    file_contents: Dict[str, str] = {
        "README_WORKER_TRIAL.md":      readme_text,
        "worker_config.json":          config_text,
        "sample_request.json":         sample_request_text,
        "expected_result_hashes.json": expected_text,
    }

    files_manifest: List[Dict[str, Any]] = []
    for name in PACK_FILES:
        text = file_contents[name]
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        files_manifest.append({
            "name": name,
            "size_bytes": len(text.encode("utf-8")),
            "sha256": _sha256_text(text),
        })

    # 6) Pack manifest (the last thing written; never references
    # itself in its own sha256 chain).
    pack_id = "twtp-" + _sha16(_canonical_dumps({
        "worker_id":      worker_id,
        "pinned_time":    pinned_time,
        "repo_commit":    repo_commit,
        "repo_tag":       repo_tag,
        "request_sha256": _sha256_text(sample_request_text),
    }))
    manifest: Dict[str, Any] = {
        "schema":             SCHEMA_MANIFEST,
        "pack_id":            pack_id,
        "worker_id":          worker_id,
        "worker_id_hash":     _sha16(worker_id),
        "pinned_time":        pinned_time,
        "repo_commit":        repo_commit,
        "repo_tag":           repo_tag,
        "request_basename":   "sample_request.json",
        "request_sha256":     _sha256_text(sample_request_text),
        "expected_compute_output_sha256":
            expected["compute_output_sha256"],
        "files":              files_manifest,
        "safety_status":      {f: True for f in PACK_SAFETY_FLAGS},
        "notes": [
            "Pack is read-only; recipient must NOT edit any "
            "file inside the pack before running the trial.",
            "Pack distribution is safe; contains zero secret "
            "material.",
        ],
    }
    manifest_text = _canonical_dumps(manifest) + "\n"
    (out_dir / "PACK_MANIFEST.json").write_text(
        manifest_text, encoding="utf-8",
    )
    manifest["_manifest_text_sha256"] = _sha256_text(manifest_text)
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="worker_trial_pack",
        description=(
            "Trinity External Worker Trial Pack v0.1. Generates a "
            "deterministic read-only trial pack directory a new "
            "worker host can use to prove cross-host replay "
            "equality. NEVER touches a wallet, NEVER signs, "
            "NEVER broadcasts."
        ),
    )
    p.add_argument("--worker-id", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pinned-time", default=None)
    p.add_argument("--request-fixture", required=True)
    p.add_argument("--repo-commit", required=True)
    p.add_argument("--repo-tag", required=True)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()
    try:
        manifest = build_trial_pack(
            worker_id=args.worker_id,
            pinned_time=pinned,
            out_dir=Path(args.out_dir),
            request_fixture=Path(args.request_fixture),
            repo_commit=args.repo_commit,
            repo_tag=args.repo_tag,
        )
    except TrialPackError as exc:
        print("[worker_trial_pack] error: " + str(exc), file=sys.stderr)
        return 2

    print(
        "[worker_trial_pack] pack_id=" + manifest["pack_id"]
        + " worker_id=" + manifest["worker_id"]
        + " expected_compute_output_sha256="
        + manifest["expected_compute_output_sha256"]
        + " out_dir=" + str(Path(args.out_dir))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
