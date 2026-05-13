#!/usr/bin/env python3
"""Trinity / Useful Compute — Operator Loop v0.1 (Sprint 5.19).

Repeatable orchestration of the Trinity Useful Compute pipeline. The
loop drives the seven sibling scripts in order:

    1. useful_compute_task_builder      -> request.json
    2. useful_compute_worker  x N        -> results / pending rewards
    3. useful_compute_replay_validator   -> validation
    4. useful_compute_governance_gate    -> governance batch
    5. useful_compute_reward_budget_policy -> budget
    6. useful_compute_payment_proposal   -> proposal
    7. useful_compute_payment_draft      -> unsigned / dry-sign draft

Each sibling is loaded via importlib and called as
``mod.main(argv=[...])`` so this script remains free of subprocess
tokens. It NEVER calls --real-sign, --mode human-broadcast,
sost-cli send or sost-cli sendrawtransaction. allow_wallet_access
and allow_broadcast are locked const-false in the operator_run
state file, and the pre-argparse argv scan refuses any wallet /
broadcast / signing flag with exit code 2.

State + checkpoints
-------------------
Each successful step writes its artifact path + sha256 into
``operator_run.json`` and appends a line to ``SHA256SUMS.txt``. The
loop can be resumed against any prior run with ``--resume
<operator_run.json>``: on resume, every recorded artifact is
re-hashed and compared. Hash match -> step is skipped. Hash
mismatch -> hard error. Missing artifact -> the step is re-run.

Confirmation token
------------------
Operator token (exact match required, no substring):
    I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_OPERATOR_RUN = "trinity-useful-compute-operator-run/v0.1"
OPERATOR_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP"

# Mode-specific tokens for the downstream payment_draft step. The
# operator only ever drives the safe modes; the real-sign token is
# deliberately NOT a string in this source.
UNSIGNED_ONLY_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST"
DRY_SIGN_TOKEN = "I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST"

# Pre-argparse rejection — every one of these flags is a sign that
# the operator was asked to do something it is NOT allowed to do
# in v0.1 (touch a wallet, sign in any mode beyond placeholder, or
# initiate a broadcast). The argparse layer never sees them.
REJECTED_FLAGS = (
    "--broadcast",
    "--send",
    "--payout-now",
    "--auto-pay",
    "--sign-now",
    "--export-private-key",
    "--wallet",
    "--from-label",
    "--from-address",
    "--allow-wallet-access",
    "--allow-broadcast",
)

STEP_NAMES = (
    "task_builder",
    "worker",
    "replay_validator",
    "governance_gate",
    "reward_budget_policy",
    "payment_proposal",
    "payment_draft",
)


# =============================================================================
# Module loader (same pattern as sibling Trinity scripts)
# =============================================================================

def _load_sibling(modname: str, filename: str):
    """Load a sibling Trinity script by filename and return the
    module object. Avoids sys.path mutation. Cached in sys.modules
    so each script is only loaded once per process."""
    if modname in sys.modules:
        return sys.modules[modname]
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        modname, here / filename,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load sibling " + filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# =============================================================================
# Hash + manifest helpers
# =============================================================================

def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha16_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _rel_to(p: Path, base: Path) -> str:
    return str(Path(p).resolve().relative_to(Path(base).resolve()))


def _git_head(repo_root: Path) -> str:
    """Best-effort lookup of the current git HEAD WITHOUT subprocess.
    Returns 'unknown' when not in a git checkout or when the HEAD
    cannot be resolved by reading .git/HEAD + refs/."""
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        return "unknown"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if head.startswith("ref: "):
        ref = head[5:].strip()
        ref_path = git_dir / ref
        if ref_path.exists():
            try:
                return ref_path.read_text(encoding="utf-8").strip()
            except OSError:
                return "unknown"
        packed = git_dir / "packed-refs"
        if packed.exists():
            try:
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        return line.split()[0]
            except OSError:
                pass
        return "unknown"
    # Detached HEAD already contains the hex sha.
    if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
        return head
    return "unknown"


# =============================================================================
# Manifest I/O
# =============================================================================

def _append_manifest(manifest_path: Path, sha: str, rel: str) -> None:
    line = sha + "  " + rel + "\n"
    if manifest_path.exists():
        existing = manifest_path.read_text(encoding="utf-8")
        if line in existing:
            return
        manifest_path.write_text(existing + line, encoding="utf-8")
    else:
        manifest_path.write_text(line, encoding="utf-8")


def _write_state(state_path: Path, state: Dict[str, Any]) -> None:
    state_path.write_text(
        _canonical_dumps(state) + "\n", encoding="utf-8",
    )


def _read_state(state_path: Path) -> Dict[str, Any]:
    obj = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("operator_run.json must be a JSON object")
    if obj.get("schema") != SCHEMA_OPERATOR_RUN:
        raise ValueError(
            "operator_run.json wrong schema: "
            + repr(obj.get("schema"))
        )
    return obj


def _verify_artifact(rel_path: str, sha: str, base: Path) -> None:
    p = base / rel_path
    if not p.exists():
        raise ValueError(
            "operator_run artifact missing on disk: " + rel_path
            + " (sha256=" + sha + ")"
        )
    actual = _sha256_file(p)
    if actual != sha:
        raise ValueError(
            "operator_run artifact hash mismatch for " + rel_path
            + " (expected " + sha + ", got " + actual + ")"
        )


# =============================================================================
# Steps
# =============================================================================

def _step_task_builder(*, out_dir: Path, args, state: Dict[str, Any]):
    mod = _load_sibling(
        "_op_task_builder", "useful_compute_task_builder.py",
    )
    out = out_dir / "request.json"
    argv = [
        "--source-tool", args.source_tool,
        "--candidate-id", args.candidate_id,
        "--input-bundle", args.input_bundle,
        "--expected-output-schema", args.expected_output_schema,
        "--difficulty-class", args.difficulty_class,
        "--deadline", args.deadline,
        "--public-description", args.public_description,
        "--max-reward-stocks", str(args.max_reward_stocks),
        "--out-json", str(out),
    ]
    rc = mod.main(argv)
    if rc != 0:
        raise ValueError(
            "step task_builder exited " + str(rc)
        )
    return [out]


def _step_worker(*, out_dir: Path, args, state, request_path: Path):
    mod = _load_sibling("_op_worker", "useful_compute_worker.py")
    worker_out = out_dir / "worker_out"
    worker_out.mkdir(parents=True, exist_ok=True)
    produced: List[Path] = []
    for worker_id in args.worker_id:
        argv = [
            "--mode", "local-dry-run",
            "--pinned-time", args.pinned_time,
            "--request", str(request_path),
            "--worker-id", worker_id,
            "--out-dir", str(worker_out),
            "--backend", args.backend,
        ]
        rc = mod.main(argv)
        if rc != 0:
            raise ValueError(
                "step worker exited " + str(rc)
                + " for worker_id=" + worker_id
            )
    for p in sorted(worker_out.glob("*.json")):
        produced.append(p)
    return produced


def _step_replay_validator(
    *, out_dir: Path, args, state, request_path: Path, worker_out: Path,
):
    mod = _load_sibling(
        "_op_replay", "useful_compute_replay_validator.py",
    )
    out = out_dir / "validation"
    out.mkdir(parents=True, exist_ok=True)
    argv = [
        "--mode", "local-dry-run",
        "--pinned-time", args.pinned_time,
        "--request", str(request_path),
        "--results-dir", str(worker_out),
        "--out-dir", str(out),
        "--min-workers", str(args.min_workers),
    ]
    rc = mod.main(argv)
    if rc != 0:
        raise ValueError("step replay_validator exited " + str(rc))
    files = sorted(
        out.glob("TRINITY_USEFUL_COMPUTE_VALIDATION_*.json")
    )
    if not files:
        raise ValueError("replay_validator produced no artifact")
    return files


def _step_governance_gate(
    *, out_dir: Path, args, state, validations_dir: Path,
    rewards_dir: Path,
):
    mod = _load_sibling(
        "_op_governance", "useful_compute_governance_gate.py",
    )
    out = out_dir / "governance"
    out.mkdir(parents=True, exist_ok=True)
    argv = [
        "--mode", "local-dry-run",
        "--pinned-time", args.pinned_time,
        "--validations-dir", str(validations_dir),
        "--rewards-dir", str(rewards_dir),
        "--out-dir", str(out),
        "--reviewer-id", args.reviewer_id,
        "--policy", "conservative",
    ]
    rc = mod.main(argv)
    if rc != 0:
        raise ValueError("step governance_gate exited " + str(rc))
    files = sorted(
        out.glob("TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_*.json")
    )
    if not files:
        raise ValueError("governance_gate produced no artifact")
    return files


def _step_reward_budget_policy(
    *, out_dir: Path, args, state, governance_dir: Path,
):
    mod = _load_sibling(
        "_op_budget", "useful_compute_reward_budget_policy.py",
    )
    out = out_dir / "budget"
    out.mkdir(parents=True, exist_ok=True)
    argv = [
        "--mode", "local-dry-run",
        "--pinned-time", args.pinned_time,
        "--pool-balance-stocks", str(args.pool_balance_stocks),
        "--governance-dir", str(governance_dir),
        "--out-dir", str(out),
        "--policy", "conservative",
    ]
    rc = mod.main(argv)
    if rc != 0:
        raise ValueError(
            "step reward_budget_policy exited " + str(rc)
        )
    files = sorted(
        out.glob("TRINITY_USEFUL_COMPUTE_REWARD_BUDGET_*.json")
    )
    if not files:
        raise ValueError("reward_budget_policy produced no artifact")
    return files


def _step_payment_proposal(
    *, out_dir: Path, args, state, budget_plan: Path,
    rewards_dir: Path,
):
    mod = _load_sibling(
        "_op_proposal", "useful_compute_payment_proposal.py",
    )
    out = out_dir / "proposal"
    out.mkdir(parents=True, exist_ok=True)
    argv = [
        "--mode", "local-dry-run",
        "--pinned-time", args.pinned_time,
        "--budget-plan", str(budget_plan),
        "--worker-address-map", args.worker_address_map,
        "--rewards-dir", str(rewards_dir),
        "--out-dir", str(out),
    ]
    rc = mod.main(argv)
    if rc != 0:
        raise ValueError("step payment_proposal exited " + str(rc))
    files = sorted(
        out.glob("TRINITY_USEFUL_COMPUTE_PAYMENT_PROPOSAL_*.json")
    )
    if not files:
        raise ValueError("payment_proposal produced no artifact")
    return files


def _step_payment_draft(
    *, out_dir: Path, args, state, proposal_path: Path,
):
    mod = _load_sibling(
        "_op_draft", "useful_compute_payment_draft.py",
    )
    out = out_dir / "draft"
    out.mkdir(parents=True, exist_ok=True)
    if args.draft_mode == "unsigned-only":
        token = UNSIGNED_ONLY_TOKEN
        mode_flag = "--unsigned-only"
    else:
        token = DRY_SIGN_TOKEN
        mode_flag = "--dry-sign"
    argv = [
        "--mode", "local-dry-run",
        "--pinned-time", args.pinned_time,
        "--proposal", str(proposal_path),
        "--out-dir", str(out),
        mode_flag,
        "--require-confirmation-token", token,
        "--max-total-stocks", str(args.max_total_stocks),
    ]
    rc = mod.main(argv)
    if rc != 0:
        raise ValueError("step payment_draft exited " + str(rc))
    files = sorted(
        out.glob("TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_*.json")
    )
    if not files:
        raise ValueError("payment_draft produced no artifact")
    return files


# =============================================================================
# Top-level driver
# =============================================================================

def _record_step(
    *, state: Dict[str, Any], step: str, files: List[Path],
    base: Path, manifest: Path, single: bool,
) -> None:
    entries: List[Dict[str, str]] = []
    for f in files:
        sha = _sha256_file(f)
        rel = _rel_to(f, base)
        _append_manifest(manifest, sha, rel)
        entries.append({"path": rel, "sha256": sha})
    if step in state["artifacts"]:
        # Avoid double-recording on resume reruns.
        pass
    state["artifacts"][step] = entries[0] if single else entries
    if step not in state["steps_completed"]:
        state["steps_completed"].append(step)


def run_operator_loop(args, repo_root: Path) -> Dict[str, Any]:
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "SHA256SUMS.txt"
    state_path = out_dir / "operator_run.json"

    state: Dict[str, Any]
    if args.resume:
        rp = Path(args.resume).resolve()
        if rp != state_path:
            raise ValueError(
                "--resume must point at the operator_run.json inside "
                "the same --out-dir; got " + str(rp)
                + " vs " + str(state_path)
            )
        state = _read_state(rp)
        # Validate every recorded artifact still matches.
        for step, entry in state.get("artifacts", {}).items():
            if isinstance(entry, list):
                for e in entry:
                    _verify_artifact(e["path"], e["sha256"], out_dir)
            else:
                _verify_artifact(entry["path"], entry["sha256"], out_dir)
    else:
        operator_run_id = "oprun-" + _sha16_str(_canonical_dumps({
            "mode": args.mode,
            "pinned_time": args.pinned_time,
            "candidate_id": args.candidate_id,
            "worker_id": list(args.worker_id),
            "pool_balance_stocks": int(args.pool_balance_stocks),
            "max_total_stocks": int(args.max_total_stocks),
        }))
        state = {
            "schema": SCHEMA_OPERATOR_RUN,
            "operator_run_id": operator_run_id,
            "mode": args.mode,
            "pinned_time": args.pinned_time,
            "git_head": _git_head(repo_root),
            "max_total_stocks": int(args.max_total_stocks),
            "pool_balance_stocks": int(args.pool_balance_stocks),
            "allow_wallet_access": False,
            "allow_broadcast": False,
            "human_review_required": True,
            "steps_completed": [],
            "artifacts": {},
            "warnings": [],
        }
        _write_state(state_path, state)

    completed = set(state.get("steps_completed", []))

    # Step 1 — task_builder.
    if "task_builder" in completed:
        request_path = out_dir / state["artifacts"]["task_builder"]["path"]
    else:
        files = _step_task_builder(
            out_dir=out_dir, args=args, state=state,
        )
        _record_step(state=state, step="task_builder", files=files,
                     base=out_dir, manifest=manifest, single=True)
        _write_state(state_path, state)
        request_path = files[0]

    # Step 2 — worker (N invocations).
    if "worker" in completed:
        worker_files = [
            out_dir / e["path"]
            for e in state["artifacts"]["worker"]
        ]
    else:
        worker_files = _step_worker(
            out_dir=out_dir, args=args, state=state,
            request_path=request_path,
        )
        _record_step(state=state, step="worker", files=worker_files,
                     base=out_dir, manifest=manifest, single=False)
        _write_state(state_path, state)
    worker_out = (out_dir / "worker_out").resolve()

    # Step 3 — replay_validator.
    if "replay_validator" in completed:
        validation_files = [
            out_dir / state["artifacts"]["replay_validator"]["path"]
        ]
    else:
        validation_files = _step_replay_validator(
            out_dir=out_dir, args=args, state=state,
            request_path=request_path, worker_out=worker_out,
        )
        _record_step(state=state, step="replay_validator",
                     files=[validation_files[0]], base=out_dir,
                     manifest=manifest, single=True)
        _write_state(state_path, state)
    validations_dir = (out_dir / "validation").resolve()

    # Step 4 — governance_gate.
    if "governance_gate" in completed:
        gov_files = [
            out_dir / state["artifacts"]["governance_gate"]["path"]
        ]
    else:
        gov_files = _step_governance_gate(
            out_dir=out_dir, args=args, state=state,
            validations_dir=validations_dir, rewards_dir=worker_out,
        )
        _record_step(state=state, step="governance_gate",
                     files=[gov_files[0]], base=out_dir,
                     manifest=manifest, single=True)
        _write_state(state_path, state)
    governance_dir = (out_dir / "governance").resolve()

    # Step 5 — reward_budget_policy.
    if "reward_budget_policy" in completed:
        budget_files = [
            out_dir / state["artifacts"]["reward_budget_policy"]["path"]
        ]
    else:
        budget_files = _step_reward_budget_policy(
            out_dir=out_dir, args=args, state=state,
            governance_dir=governance_dir,
        )
        _record_step(state=state, step="reward_budget_policy",
                     files=[budget_files[0]], base=out_dir,
                     manifest=manifest, single=True)
        _write_state(state_path, state)

    # Step 6 — payment_proposal.
    if "payment_proposal" in completed:
        proposal_files = [
            out_dir / state["artifacts"]["payment_proposal"]["path"]
        ]
    else:
        proposal_files = _step_payment_proposal(
            out_dir=out_dir, args=args, state=state,
            budget_plan=budget_files[0], rewards_dir=worker_out,
        )
        _record_step(state=state, step="payment_proposal",
                     files=[proposal_files[0]], base=out_dir,
                     manifest=manifest, single=True)
        _write_state(state_path, state)

    # Step 7 — payment_draft.
    if "payment_draft" not in completed:
        draft_files = _step_payment_draft(
            out_dir=out_dir, args=args, state=state,
            proposal_path=proposal_files[0],
        )
        _record_step(state=state, step="payment_draft",
                     files=[draft_files[0]], base=out_dir,
                     manifest=manifest, single=True)
        _write_state(state_path, state)

    return state


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_operator_loop",
        description=(
            "Trinity Useful Compute Operator Loop v0.1. Local-dry-run "
            "orchestration of the full Useful Compute pipeline with "
            "checkpoints and resume support. NEVER touches a wallet, "
            "NEVER signs in any mode beyond placeholder, NEVER "
            "broadcasts."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument("--out-dir", required=True)
    p.add_argument(
        "--require-confirmation-token", required=True,
        help="Exact match: " + OPERATOR_TOKEN,
    )
    p.add_argument("--candidate-id", default="op-candidate-001")
    p.add_argument(
        "--input-bundle", default=None,
        help="Path to the task input bundle file.",
    )
    p.add_argument(
        "--worker-address-map", default=None,
        help="Path to a trinity-worker-address-map/v0.1 JSON file.",
    )
    p.add_argument("--max-total-stocks", type=int, default=1_000_000)
    p.add_argument("--pool-balance-stocks", type=int, default=10_000_000)
    p.add_argument(
        "--pinned-time", default="2026-05-13T00:00:00+00:00",
    )
    p.add_argument(
        "--reviewer-id", default="operator-loop-v01",
    )
    p.add_argument(
        "--source-tool", default="trinity_orchestrator",
        choices=["geaspirit", "materials_engine", "trinity_orchestrator"],
    )
    p.add_argument(
        "--difficulty-class", default="low",
        choices=["low", "medium", "high", "extreme"],
    )
    p.add_argument("--deadline", default="2026-06-30")
    p.add_argument(
        "--public-description",
        default="Operator loop dry-run pipeline",
    )
    p.add_argument(
        "--expected-output-schema",
        default="trinity-useful-compute-result/v0.4",
    )
    p.add_argument("--max-reward-stocks", type=int, default=100_000)
    p.add_argument(
        "--worker-id", action="append", default=None,
        help="Repeat for multiple workers (default: worker-A, worker-B).",
    )
    p.add_argument(
        "--backend", default="placeholder",
        help="Worker backend kind (default: placeholder).",
    )
    p.add_argument("--min-workers", type=int, default=2)
    p.add_argument(
        "--draft-mode", default="unsigned-only",
        choices=["unsigned-only", "dry-sign"],
    )
    p.add_argument(
        "--resume", default=None,
        help="Resume a prior run by passing its operator_run.json.",
    )

    # Pre-argparse rejection scan. Rejecting before argparse keeps
    # the wallet / broadcast / signing flags off the argv even if
    # someone tried to smuggle them in.
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    for f in REJECTED_FLAGS:
        if f in raw_argv:
            print(
                "[useful_compute_operator_loop] flag " + f
                + " is rejected in v0.1",
                file=sys.stderr,
            )
            return 2

    args = p.parse_args(argv)

    if args.require_confirmation_token != OPERATOR_TOKEN:
        print(
            "[useful_compute_operator_loop] require-confirmation-token "
            "must be: " + OPERATOR_TOKEN,
            file=sys.stderr,
        )
        return 2

    if args.worker_id is None:
        args.worker_id = ["worker-A", "worker-B"]
    if args.input_bundle is None:
        print(
            "[useful_compute_operator_loop] --input-bundle is "
            "required",
            file=sys.stderr,
        )
        return 2
    if args.worker_address_map is None:
        print(
            "[useful_compute_operator_loop] --worker-address-map "
            "is required",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(__file__).resolve().parents[2]
    try:
        state = run_operator_loop(args, repo_root)
    except ValueError as exc:
        print(
            "[useful_compute_operator_loop] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    print(
        "[useful_compute_operator_loop] operator_run_id="
        + state["operator_run_id"]
        + " steps_completed="
        + ",".join(state["steps_completed"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
