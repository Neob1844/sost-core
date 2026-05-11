#!/usr/bin/env python3
"""Trinity Autonomous Orchestrator v0.1.

Coordinates geaspirit, materials_engine and useful_compute under the
authority of the SOST AI council (with deterministic-heuristic
fallback).

What it does in one run
-----------------------
1. Loads the four canonical objectives from
   ``config/trinity/objectives/*.json``.
2. Invokes geaspirit + materials_engine pipelines in *dry-run* mode
   to produce candidate dossiers.
3. Builds a queue of candidate decisions (one option per accepted
   dossier candidate, capped by ``max_decisions_per_run``).
4. Asks ``sost_ai_orchestrator_adapter.decide_next_action`` which
   option to act on next.
5. For each selected option, if the candidate's score crosses the
   vertical threshold, emits a ``trinity-useful-compute-request/v0.1``
   manifest via ``useful_compute_task_builder`` — written to disk
   only, never broadcast.
6. Logs every decision (input hashes, selected option, council usage,
   pending reward forecast, errors, retries) to
   ``TRINITY_AUTONOMY_LEDGER.jsonl``.
7. Updates ``trinity_error_memory`` with any lessons learned.
8. Emits a final ``trinity-autonomy-proof-bundle/v0.1`` summary.

Hard invariants
---------------
- No network calls. No subprocesses. No wallet operations.
- ``registered=false`` and ``ready_to_register=false`` by default.
- Bundle is byte-identical across runs with the same seed and pinned
  time, provided the underlying geo / materials pipelines are.
- Refuses to retry a (vertical, task_signature) that already has a
  recorded lesson unless ``--allow-retry-known-failures`` is set.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_LEDGER  = "trinity-autonomy-ledger/v0.1"
SCHEMA_BUNDLE  = "trinity-autonomy-proof-bundle/v0.1"
SCHEMA_SUMMARY = "trinity-autonomy-summary/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

_REQUIRED_OBJECTIVES = (
    "geaspirit", "materials_engine", "useful_compute", "sost_ai",
)


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def load_objectives(objectives_dir: Path) -> Dict[str, Dict[str, Any]]:
    if not objectives_dir.exists():
        raise FileNotFoundError(
            f"objectives directory does not exist: {objectives_dir}"
        )
    out: Dict[str, Dict[str, Any]] = {}
    for name in _REQUIRED_OBJECTIVES:
        p = objectives_dir / f"{name}.json"
        if not p.exists():
            raise FileNotFoundError(
                f"missing objective config: {p}"
            )
        out[name] = json.loads(p.read_text(encoding="utf-8"))
    return out


def _objectives_hash(objectives: Dict[str, Dict[str, Any]]) -> str:
    return _sha256_hex(canonical_dumps(objectives).encode("utf-8"))


def _build_geo_candidates(
    out_dir: Path,
    count: int,
    seed: str,
    pinned_time: str,
) -> Dict[str, Any]:
    pipeline = _load(
        "trinity_orch_geo_pipeline",
        _SCRIPTS_DIR / "geo_discovery_pipeline.py",
    )
    return pipeline.run_pipeline(
        mode="offline-belts",
        commodity="copper_gold_critical_minerals",
        count=count,
        seed=seed,
        pinned_time=pinned_time,
        out_dir=out_dir,
    )


def _build_materials_candidates(
    out_dir: Path,
    count: int,
    seed: str,
    pinned_time: str,
) -> Dict[str, Any]:
    pipeline = _load(
        "trinity_orch_mat_pipeline",
        _SCRIPTS_DIR / "materials_discovery_pipeline.py",
    )
    return pipeline.run_pipeline(
        family="oxide_frontier",
        count=count,
        seed=seed,
        pinned_time=pinned_time,
        out_dir=out_dir,
    )


def _geo_options_from_dossier(
    dossier_path: Path,
    max_options: int,
) -> List[Dict[str, Any]]:
    d = json.loads(dossier_path.read_text(encoding="utf-8"))
    # v0.1 dossier uses the key "aois". Sort accepts by score desc.
    accepts = [a for a in d.get("aois", []) if a.get("decision") == "accept"]
    accepts.sort(
        key=lambda a: (-float(a.get("confidence", 0.0)),
                       a.get("aoi_id", "")),
    )
    out: List[Dict[str, Any]] = []
    for entry in accepts[:max_options]:
        # geo confidence is 0..1; multiply by 100 so score lives in
        # the same 0..100 space the orchestrator threshold expects.
        confidence = float(entry.get("confidence", 0.0))
        out.append({
            "vertical": "geaspirit",
            "objective": "discover-aoi",
            "candidate_id": entry.get("aoi_id", ""),
            "score": confidence * 100.0,
            "evidence_strength": float(entry.get("council_confidence", 0.0)),
            "novelty": 1.0 - float(entry.get("council_confidence", 0.0)),
            "decision": "accept",
        })
    return out


def _materials_options_from_dossier(
    dossier_path: Path,
    max_options: int,
) -> List[Dict[str, Any]]:
    d = json.loads(dossier_path.read_text(encoding="utf-8"))
    # v0.2 dossier uses the key "hypotheses". Accept-only with score
    # derived from council_confidence (0..1).
    accepts = [
        h for h in d.get("hypotheses", []) if h.get("decision") == "accept"
    ]
    accepts.sort(
        key=lambda h: (-float(h.get("council_confidence", 0.0)),
                       h.get("candidate_id", "")),
    )
    out: List[Dict[str, Any]] = []
    for entry in accepts[:max_options]:
        out.append({
            "vertical": "materials_engine",
            "objective": "discover-material",
            "candidate_id": entry.get("candidate_id", ""),
            "score": float(entry.get("council_confidence", 0.0)),
            "evidence_strength": float(
                entry.get("seed_frontier_proximity", 0.0)
            ),
            "novelty": float(entry.get("seed_novelty", 0.0)),
            "decision": "accept",
        })
    return out


def _emit_uc_request_if_eligible(
    *,
    out_dir: Path,
    builder_mod,
    option: Dict[str, Any],
    objectives: Dict[str, Dict[str, Any]],
    pinned_time: str,
) -> Optional[Dict[str, Any]]:
    vertical = option.get("vertical", "")
    obj = objectives.get(vertical)
    if obj is None:
        return None
    threshold = float(
        obj.get("thresholds", {}).get("min_score_for_uc_request", 0.0)
    )
    if vertical == "geaspirit":
        score = float(option.get("score", 0.0))  # 0..100
    else:
        score = float(option.get("score", 0.0))  # 0..1
    if score < threshold:
        return None

    candidate_id = option.get("candidate_id", "")
    input_blob = canonical_dumps({
        "vertical": vertical, "candidate_id": candidate_id,
        "objective": option.get("objective", ""),
        "score": score, "pinned_time": pinned_time,
    }).encode("utf-8")
    deadline = pinned_time  # v0.1: no future scheduling
    if vertical == "geaspirit":
        difficulty = "medium"
        expected_schema = "geo-followup-result/v0"
    else:
        difficulty = "high"
        expected_schema = "materials-dft-result/v0"

    req = builder_mod.build_request(
        source_tool=vertical,
        candidate_id=candidate_id,
        input_bundle_bytes=input_blob,
        expected_output_schema=expected_schema,
        difficulty_class=difficulty,
        max_reward_stocks=int(
            objectives["useful_compute"]["thresholds"]
            ["max_reward_stocks_per_task"]
        ),
        deadline=deadline,
        public_description=(
            f"Useful compute request for {vertical} candidate "
            f"{candidate_id}. Dry-run v0.1; not on-chain."
        ),
        manual_review_required=False,
    )
    req_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_REQUEST_{req['request_id']}.json"
    )
    req_path.write_text(canonical_dumps(req), encoding="utf-8")
    return req


def run_orchestrator(
    *,
    mode: str,
    seed: str,
    pinned_time: str,
    objectives_dir: Path,
    out_dir: Path,
    count: int,
    allow_retry_known_failures: bool = False,
) -> Dict[str, Any]:
    if mode != "dry-run":
        raise ValueError("v0.1 only supports --mode dry-run")
    out_dir.mkdir(parents=True, exist_ok=True)

    objectives = load_objectives(objectives_dir)
    objectives_hash = _objectives_hash(objectives)

    geo_dir = out_dir / "geo"
    mat_dir = out_dir / "materials"
    geo_dir.mkdir(parents=True, exist_ok=True)
    mat_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = out_dir / "TRINITY_AUTONOMY_LEDGER.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()
    error_mem_path = out_dir / "TRINITY_AUTONOMY_ERROR_LEDGER.jsonl"
    if error_mem_path.exists():
        error_mem_path.unlink()

    adapter_mod = _load(
        "trinity_orch_adapter",
        _SCRIPTS_DIR / "sost_ai_orchestrator_adapter.py",
    )
    builder_mod = _load(
        "trinity_orch_builder",
        _SCRIPTS_DIR / "useful_compute_task_builder.py",
    )
    error_mem_mod = _load(
        "trinity_orch_error_mem",
        _SCRIPTS_DIR / "trinity_error_memory.py",
    )
    reward_mod = _load(
        "trinity_orch_reward",
        _SCRIPTS_DIR / "useful_compute_reward_model.py",
    )

    decisions: List[Dict[str, Any]] = []
    uc_requests: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    deterministic_run_id = _sha16(canonical_dumps({
        "mode": mode, "seed": seed, "pinned_time": pinned_time,
        "objectives_hash": objectives_hash, "count": count,
    }))

    geo_result: Optional[Dict[str, Any]] = None
    mat_result: Optional[Dict[str, Any]] = None
    try:
        geo_result = _build_geo_candidates(
            geo_dir, count=count, seed=objectives["geaspirit"]["default_seed"],
            pinned_time=pinned_time,
        )
    except Exception as exc:
        errors.append({
            "vertical": "geaspirit",
            "kind": "compute_failed",
            "detail": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc(limit=4),
        })
        error_mem_mod.record_lesson(
            ledger_path=error_mem_path,
            vertical="geaspirit",
            task_inputs={"action": "geo_pipeline", "count": count},
            cause="compute_failed",
            detail=f"{type(exc).__name__}: {exc}",
            pinned_time=pinned_time,
        )

    try:
        mat_result = _build_materials_candidates(
            mat_dir, count=count,
            seed=objectives["materials_engine"]["default_seed"],
            pinned_time=pinned_time,
        )
    except Exception as exc:
        errors.append({
            "vertical": "materials_engine",
            "kind": "compute_failed",
            "detail": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc(limit=4),
        })
        error_mem_mod.record_lesson(
            ledger_path=error_mem_path,
            vertical="materials_engine",
            task_inputs={"action": "materials_pipeline", "count": count},
            cause="compute_failed",
            detail=f"{type(exc).__name__}: {exc}",
            pinned_time=pinned_time,
        )

    options: List[Dict[str, Any]] = []
    if geo_result is not None:
        options.extend(_geo_options_from_dossier(
            Path(geo_result["paths"]["dossier_json"]),
            max_options=int(
                objectives["geaspirit"]["thresholds"]
                ["max_uc_requests_per_run"]
            ),
        ))
    if mat_result is not None:
        options.extend(_materials_options_from_dossier(
            Path(mat_result["paths"]["dossier_json"]),
            max_options=int(
                objectives["materials_engine"]["thresholds"]
                ["max_uc_requests_per_run"]
            ),
        ))

    max_decisions = int(
        objectives["sost_ai"]["thresholds"]["max_decisions_per_run"]
    )
    remaining = list(options)
    decision_count = 0
    while remaining and decision_count < max_decisions:
        # Refuse to act on tasks whose signature has a recorded lesson.
        if not allow_retry_known_failures:
            filtered: List[Dict[str, Any]] = []
            for opt in remaining:
                prior = error_mem_mod.has_repeat_lesson(
                    error_mem_path, opt.get("vertical", ""),
                    {"candidate_id": opt.get("candidate_id", "")},
                )
                if prior is None:
                    filtered.append(opt)
            remaining = filtered
            if not remaining:
                break

        verdict = adapter_mod.decide_next_action(
            options=remaining, use_real_council=True,
        )
        sel = verdict["selected"]
        if sel is None:
            break

        uc = _emit_uc_request_if_eligible(
            out_dir=out_dir, builder_mod=builder_mod,
            option=sel, objectives=objectives, pinned_time=pinned_time,
        )
        forecast = None
        if uc is not None:
            uc_requests.append(uc)
            forecast = reward_mod.compute_pending_reward(
                task_id=uc["request_id"],
                worker_id="ORCHESTRATOR_FORECAST",
                benchmark_score=1.0,
                verified_compute_seconds=float(
                    uc["estimated_compute_cost"]["seconds"]
                ),
                difficulty_class=uc["estimated_compute_cost"]["tier"],
                result_validated=True,
                duplicate_result=False,
                max_reward_stocks=int(uc["max_reward_stocks"]),
            )

        decision = {
            "schema": SCHEMA_LEDGER,
            "deterministic_run_id": deterministic_run_id,
            "decision_index": decision_count,
            "pinned_time": pinned_time,
            "selected_option": sel,
            "council_used": verdict["council_used"],
            "council_path": verdict["council_path"],
            "reason": verdict["reason"],
            "uc_request_id": uc["request_id"] if uc else None,
            "pending_reward_forecast": forecast,
        }
        decisions.append(decision)
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_dumps(decision) + "\n")

        remaining = [
            o for o in remaining
            if o.get("candidate_id") != sel.get("candidate_id")
        ]
        decision_count += 1

    # Persist a consolidated list of uc_requests.
    uc_index_path = out_dir / "TRINITY_USEFUL_COMPUTE_REQUESTS.json"
    uc_index_path.write_text(canonical_dumps({
        "schema": "trinity-useful-compute-index/v0.1",
        "pinned_time": pinned_time,
        "count": len(uc_requests),
        "requests": uc_requests,
    }), encoding="utf-8")

    # Summary MD.
    summary_md_path = out_dir / "TRINITY_AUTONOMY_SUMMARY.md"
    summary_md_path.write_text(
        _render_summary_md(
            decisions=decisions, uc_requests=uc_requests,
            errors=errors, geo_result=geo_result, mat_result=mat_result,
            pinned_time=pinned_time, seed=seed, run_id=deterministic_run_id,
        ),
        encoding="utf-8",
    )

    # Error memory rolling MD.
    lessons = error_mem_mod.read_lessons(error_mem_path)
    lessons_md_path = out_dir / "TRINITY_AUTONOMY_LESSONS.md"
    lessons_md_path.write_text(
        error_mem_mod.render_lessons_md(lessons),
        encoding="utf-8",
    )

    # Final proof bundle.
    ledger_hash = _sha256_hex(
        ledger_path.read_bytes() if ledger_path.exists() else b""
    )
    objectives_hash_final = _objectives_hash(objectives)
    candidate_hashes = {
        "geo_dossier": _sha256_hex(
            Path(geo_result["paths"]["dossier_json"]).read_bytes()
        ) if geo_result is not None else None,
        "materials_dossier": _sha256_hex(
            Path(mat_result["paths"]["dossier_json"]).read_bytes()
        ) if mat_result is not None else None,
    }
    uc_index_hash = _sha256_hex(uc_index_path.read_bytes())
    reward_model_hash = _sha256_hex(
        (_SCRIPTS_DIR / "useful_compute_reward_model.py").read_bytes()
    )

    bundle = {
        "schema": SCHEMA_BUNDLE,
        "orchestrator_version": "v0.1",
        "deterministic_run_id": deterministic_run_id,
        "pinned_time": pinned_time,
        "seed": seed,
        "objectives_hash": objectives_hash_final,
        "ledger_hash": ledger_hash,
        "candidate_hashes": candidate_hashes,
        "uc_request_index_hash": uc_index_hash,
        "reward_model_hash": reward_model_hash,
        "decisions_count": len(decisions),
        "uc_requests_count": len(uc_requests),
        "errors_count": len(errors),
        "disclaimers": [
            "autonomous orchestrator output",
            "no on-chain registration",
            "no automatic payout",
            "rewards are pending only until result verification",
            "council acts as critic; humans review final claims",
        ],
        "safety_status": {
            "dry_run": True,
            "registered": False,
            "ready_to_register": False,
            "no_rewards_active": True,
            "no_paid_providers": True,
            "no_network_calls": True,
        },
    }
    bundle_path = out_dir / "TRINITY_AUTONOMY_PROOF_BUNDLE_v01.json"
    bundle_path.write_text(canonical_dumps(bundle), encoding="utf-8")

    return {
        "deterministic_run_id": deterministic_run_id,
        "decisions": decisions,
        "uc_requests": uc_requests,
        "errors": errors,
        "paths": {
            "ledger":  str(ledger_path),
            "summary": str(summary_md_path),
            "uc_index": str(uc_index_path),
            "bundle":  str(bundle_path),
            "lessons": str(lessons_md_path),
        },
        "shas": {
            "ledger":         ledger_hash,
            "uc_request_idx": uc_index_hash,
            "bundle":         _sha256_hex(bundle_path.read_bytes()),
            "objectives":     objectives_hash_final,
            "reward_model":   reward_model_hash,
        },
        "summary": {
            "decisions_count":   len(decisions),
            "uc_requests_count": len(uc_requests),
            "errors_count":      len(errors),
            "geo_ran":           geo_result is not None,
            "materials_ran":     mat_result is not None,
        },
    }


def _render_summary_md(
    *, decisions, uc_requests, errors, geo_result, mat_result,
    pinned_time, seed, run_id,
) -> str:
    lines = [
        "# TRINITY AUTONOMY SUMMARY",
        "",
        f"- schema: `{SCHEMA_SUMMARY}`",
        f"- deterministic_run_id: `{run_id}`",
        f"- seed: `{seed}`",
        f"- pinned_time: `{pinned_time}`",
        f"- decisions: {len(decisions)}",
        f"- useful compute requests: {len(uc_requests)}",
        f"- errors: {len(errors)}",
        "",
        "## Disclaimers",
        "",
        "- autonomous orchestrator output",
        "- no on-chain registration",
        "- no automatic payout",
        "- rewards are pending only until result verification",
        "- council acts as critic; humans review final claims",
        "",
        "## Verticals",
        "",
        f"- geaspirit pipeline ran: {geo_result is not None}",
        f"- materials_engine pipeline ran: {mat_result is not None}",
        "",
    ]
    if decisions:
        lines.append("## Decisions (chronological)")
        lines.append("")
        lines.append(
            "| # | vertical | candidate | council_used | uc_request | pending_stocks |"
        )
        lines.append("|---|---|---|---|---|---|")
        for d in decisions:
            opt = d.get("selected_option") or {}
            f = d.get("pending_reward_forecast") or {}
            lines.append(
                f"| {d['decision_index']} | "
                f"{opt.get('vertical','')} | "
                f"{opt.get('candidate_id','')} | "
                f"{d.get('council_used')} | "
                f"{d.get('uc_request_id','')} | "
                f"{f.get('pending_reward_stocks','')} |"
            )
        lines.append("")
    if errors:
        lines.append("## Errors")
        lines.append("")
        for e in errors:
            lines.append(
                f"- `{e.get('vertical','')}` "
                f"**{e.get('kind','')}** — {e.get('detail','')}"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="trinity_orchestrator",
        description="Trinity Autonomous Orchestrator v0.1 — dry-run only.",
    )
    p.add_argument("--mode", default="dry-run",
                   choices=["dry-run"],
                   help="v0.1 only supports dry-run")
    p.add_argument("--seed", default="trinity-autonomy-v0.1")
    p.add_argument("--pinned-time",
                   default="2026-05-11T00:00:00+00:00")
    p.add_argument("--objectives", required=False,
                   default=str(_REPO_ROOT / "config" / "trinity" / "objectives"))
    p.add_argument("--out-dir", default=str(Path.cwd()))
    p.add_argument("--count", type=int, default=25)
    p.add_argument(
        "--allow-retry-known-failures", action="store_true",
        help=(
            "If set, the planner will retry tasks whose signature "
            "matches a previously recorded lesson. Default: refuse."
        ),
    )
    args = p.parse_args(argv)

    result = run_orchestrator(
        mode=args.mode, seed=args.seed,
        pinned_time=args.pinned_time,
        objectives_dir=Path(args.objectives),
        out_dir=Path(args.out_dir),
        count=args.count,
        allow_retry_known_failures=args.allow_retry_known_failures,
    )

    print(
        f"[trinity_orchestrator] run_id={result['deterministic_run_id']}"
    )
    print(
        f"[trinity_orchestrator] decisions={result['summary']['decisions_count']}, "
        f"uc_requests={result['summary']['uc_requests_count']}, "
        f"errors={result['summary']['errors_count']}"
    )
    print(f"[trinity_orchestrator] geo_ran={result['summary']['geo_ran']}, "
          f"materials_ran={result['summary']['materials_ran']}")
    print(f"[trinity_orchestrator] SHAs:")
    for k, v in sorted(result["shas"].items()):
        print(f"  {k:>14}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
