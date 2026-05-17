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
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_REQUEST_ID_RE = re.compile(r"^uc-[0-9a-f]{16,64}$")


SCHEMA_OPERATOR_RUN = "trinity-useful-compute-operator-run/v0.1"
SCHEMA_REQUEST = "trinity-useful-compute-request/v0.1"
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
# External request import (Sprint 5.22)
# =============================================================================

def _validate_external_request(obj: Any) -> None:
    """Refuse the import if the JSON does not match the v0.1
    useful-compute request shape. The loop only needs the basics
    (schema id + request_id); downstream steps perform their own
    strict checks. Catching obvious mis-shapes here gives the
    operator a clean error before the run directory is mutated."""
    if not isinstance(obj, dict):
        raise ValueError(
            "imported request must be a JSON object"
        )
    if obj.get("schema") != SCHEMA_REQUEST:
        raise ValueError(
            "imported request wrong schema: "
            + repr(obj.get("schema"))
            + " (expected " + SCHEMA_REQUEST + ")"
        )
    rid = obj.get("request_id", "")
    if not (isinstance(rid, str) and _REQUEST_ID_RE.match(rid)):
        raise ValueError(
            "imported request_id wrong format: " + repr(rid)
        )
    # input_bundle_sha256 must be present and 64-hex; downstream
    # steps rely on it.
    ibs = obj.get("input_bundle_sha256", "")
    if not (isinstance(ibs, str)
            and re.match(r"^[0-9a-f]{64}$", ibs)):
        raise ValueError(
            "imported request input_bundle_sha256 must be 64 "
            "lowercase hex; got " + repr(ibs)
        )


def _import_existing_request(
    *, src: Path, run_request_path: Path,
) -> Tuple[str, str]:
    """Copy ``src`` to ``run_request_path`` and return
    (source_sha256, source_basename). Validates the JSON before
    writing so the run directory is never left with a half-imported
    request."""
    if not src.exists() or not src.is_file():
        raise ValueError(
            "--request-json file not found: " + str(src)
        )
    try:
        obj = json.loads(src.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "--request-json is not valid UTF-8 JSON: " + str(exc)
        )
    _validate_external_request(obj)
    # Source sha256 computed from the bytes on disk so the
    # state-file fingerprint matches the file the operator pointed
    # at, even if json.dumps would re-emit the keys in a different
    # order.
    source_sha = _sha256_file(src)
    run_request_path.parent.mkdir(parents=True, exist_ok=True)
    # Re-emit canonically so resume tamper detection always
    # compares against a deterministic file. The run-dir copy may
    # therefore differ byte-for-byte from the source (e.g. key
    # ordering) but always has the same content.
    run_request_path.write_text(
        _canonical_dumps(obj), encoding="utf-8",
    )
    return source_sha, src.name


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

# =============================================================================
# Sprint 5.24 — Autonomy Governor observe hook
# =============================================================================
#
# The hook is intentionally narrow. It loads autonomy_governor by the
# same _load_sibling helper every other Trinity script uses (importlib,
# no subprocess), pins the policy sha at boot, and asks for a verdict
# per step. The Governor's evaluate_decision() is a pure function — it
# only reads the policy file and writes the decision JSON. It does not
# open the network, run shell, or touch any wallet/sign/broadcast code.
#
# v0.1 enforcement rule: the operator_loop HARD-BLOCKS only on
#   - blocked_reason == "halt_file_present"            (kill switch)
#   - blocked_reason == "policy_mutated_at_runtime"    (T15/T13)
# Anything else is recorded as an audit artifact + appended to
# state["warnings"]. This keeps the pipeline observe-only and ensures
# 5.24 is a measurement layer, not an enforcement layer.

class _GovernorHook:
    """Per-run Governor wrapper. Lives only while run_operator_loop runs."""

    HARD_BLOCK_REASONS = ("halt_file_present", "policy_mutated_at_runtime")

    def __init__(self, policy_path, decisions_dir, pinned_time):
        self.policy_path = Path(policy_path).resolve()
        self.decisions_dir = Path(decisions_dir).resolve()
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.pinned_time = pinned_time
        self._mod = _load_sibling(
            "autonomy_governor", "autonomy_governor.py",
        )
        self.boot_policy_sha256, self._policy = self._mod.pin_policy(
            self.policy_path,
        )
        self.policy_basename = self.policy_path.name

    def evaluate(self, step_name):
        return self._mod.evaluate_decision(
            policy_path=self.policy_path,
            action="pipeline_step",
            action_params={"step_name": step_name},
            pinned_time=self.pinned_time,
            boot_policy_sha256=self.boot_policy_sha256,
            out_dir=self.decisions_dir,
        )


class GovernorHardBlock(Exception):
    """Raised by the operator_loop hook when the Governor returns one of
    the hard-block reasons (halt_file_present, policy_mutated_at_runtime).
    Caught by main() and turned into a non-zero exit."""

    def __init__(self, step_name, blocked_reason, decision_path):
        super().__init__(
            "Governor hard-blocked step '" + step_name
            + "' with reason '" + str(blocked_reason)
            + "' (decision at " + str(decision_path) + ")"
        )
        self.step_name = step_name
        self.blocked_reason = blocked_reason
        self.decision_path = decision_path


def _governor_call(hook, step_name, state, out_dir, manifest):
    """Invoke the Governor for one step and update state accordingly.

    No-op when hook is None (governor disabled).

    Returns nothing. Mutates state:
      - appends a {path, sha256} entry to state["artifacts"]
        ["governor_decisions"]
      - increments state["governor_decisions_count"]
      - appends a warning when the decision is allowed=false but the
        reason is not a hard-block (observe-only audit trail)

    Raises GovernorHardBlock when the reason is in HARD_BLOCK_REASONS.
    """
    if hook is None:
        return
    decision = hook.evaluate(step_name)
    decision_path = Path(decision.pop("_decision_path"))
    rel = _rel_to(decision_path, out_dir)
    sha = _sha256_file(decision_path)
    _append_manifest(manifest, sha, rel)
    artifacts = state.setdefault("artifacts", {})
    bucket = artifacts.setdefault("governor_decisions", [])
    bucket.append({"path": rel, "sha256": sha})
    state["governor_decisions_count"] = int(
        state.get("governor_decisions_count", 0)
    ) + 1

    if (not decision["allowed"]) and decision["blocked_reason"] in _GovernorHook.HARD_BLOCK_REASONS:
        raise GovernorHardBlock(
            step_name=step_name,
            blocked_reason=decision["blocked_reason"],
            decision_path=decision_path,
        )

    # Observe-only path: record a warning so it surfaces in operator_run.json
    # but do NOT stop the pipeline. Truncate at 512 chars to match the
    # schema's warnings.items.maxLength.
    if not decision["allowed"]:
        msg = (
            "[governor:observe] step=" + step_name
            + " blocked_reason=" + str(decision["blocked_reason"])
            + " requires_human_approval="
            + str(decision["requires_human_approval"])
            + " (audit-only in v0.1)"
        )
        state.setdefault("warnings", []).append(msg[:512])


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

    # Sprint 5.24 — Autonomy Governor observe hook bootstrap. When
    # --governor-policy is supplied the hook is built and the boot
    # policy sha256 is pinned for the lifetime of this run. When NOT
    # supplied, hook stays None and no Governor call ever happens —
    # behaviour identical to pre-5.24.
    governor_hook = None
    governor_enabled = bool(getattr(args, "governor_policy", None))
    if governor_enabled:
        decisions_dir = (
            Path(args.governor_decisions_dir).resolve()
            if getattr(args, "governor_decisions_dir", None)
            else (out_dir / "governor_decisions")
        )
        governor_hook = _GovernorHook(
            policy_path=args.governor_policy,
            decisions_dir=decisions_dir,
            pinned_time=args.pinned_time,
        )

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

        # Sprint 5.24 — when resuming a governor-enabled run, the
        # active policy file's sha256 must still match what was pinned
        # at the original boot. If it doesn't, refuse the resume.
        # When governor was DISABLED on the original run, just keep
        # the existing fields untouched.
        if governor_hook is not None:
            saved_sha = state.get("governor_policy_sha256")
            if saved_sha and saved_sha != governor_hook.boot_policy_sha256:
                raise ValueError(
                    "governor policy file sha256 changed since the "
                    "original run was started; refusing to resume. "
                    "Saved: " + saved_sha
                    + " · current: " + governor_hook.boot_policy_sha256
                )
            # Carry forward the original boot pin so all subsequent
            # decision JSONs cite the same boot policy sha256 that the
            # first decisions did.
            if saved_sha:
                governor_hook.boot_policy_sha256 = saved_sha
    else:
        # request_source toggles between two initial-step modes:
        #   "built"            -> the loop runs task_builder
        #   "existing_request" -> the loop imports an external
        #                         request.json via --request-json
        request_source = (
            "existing_request"
            if args.request_json is not None
            else "built"
        )
        source_request_sha: Optional[str] = None
        source_request_basename: Optional[str] = None
        if request_source == "existing_request":
            run_request_path = out_dir / "request.json"
            source_request_sha, source_request_basename = (
                _import_existing_request(
                    src=Path(args.request_json),
                    run_request_path=run_request_path,
                )
            )

        operator_run_id = "oprun-" + _sha16_str(_canonical_dumps({
            "mode": args.mode,
            "pinned_time": args.pinned_time,
            "candidate_id": args.candidate_id,
            "worker_id": list(args.worker_id),
            "pool_balance_stocks": int(args.pool_balance_stocks),
            "max_total_stocks": int(args.max_total_stocks),
            "request_source": request_source,
            "source_request_sha256": source_request_sha,
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
            # Sprint 5.24 — governor bookkeeping. These fields are
            # always present so the schema is uniform whether the
            # governor was enabled or not.
            "governor_enabled": bool(governor_enabled),
            "governor_policy_sha256": (
                governor_hook.boot_policy_sha256 if governor_hook else None
            ),
            "governor_policy_path_basename": (
                governor_hook.policy_basename if governor_hook else None
            ),
            "governor_decisions_count": 0,
            "request_source": request_source,
            "source_request_sha256": source_request_sha,
            "source_request_path_basename": source_request_basename,
            "steps_completed": [],
            "artifacts": {},
            "warnings": [],
        }

        # When importing an existing request, mark task_builder as
        # completed up-front with the copy in run/request.json.
        # Downstream steps (worker / replay / etc.) see the same
        # file layout as in the "built" path.
        if request_source == "existing_request":
            imported = out_dir / "request.json"
            _record_step(
                state=state, step="task_builder",
                files=[imported],
                base=out_dir, manifest=manifest, single=True,
            )

        _write_state(state_path, state)

    completed = set(state.get("steps_completed", []))

    # Step 1 — task_builder. Skipped automatically when an external
    # request was imported in the init block above (it was already
    # recorded as completed).
    if "task_builder" in completed:
        request_path = out_dir / state["artifacts"]["task_builder"]["path"]
    else:
        _governor_call(governor_hook, "task_builder", state, out_dir, manifest)
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
        _governor_call(governor_hook, "worker", state, out_dir, manifest)
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
        _governor_call(governor_hook, "replay_validator", state, out_dir, manifest)
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
        _governor_call(governor_hook, "governance_gate", state, out_dir, manifest)
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
        _governor_call(governor_hook, "reward_budget_policy", state, out_dir, manifest)
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
        _governor_call(governor_hook, "payment_proposal", state, out_dir, manifest)
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
        _governor_call(governor_hook, "payment_draft", state, out_dir, manifest)
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
        "--request-json", default=None,
        help="Path to an EXISTING trinity-useful-compute-request/"
             "v0.1 JSON manifest (typically produced by "
             "useful_compute_task_builder --from-scientific-intake "
             "in Sprint 5.21). When supplied, the operator loop "
             "skips its internal task_builder step and imports this "
             "request as the canonical run/request.json. Mutually "
             "exclusive with --input-bundle.",
    )
    p.add_argument(
        "--resume", default=None,
        help="Resume a prior run by passing its operator_run.json.",
    )

    # Sprint 5.24 — Autonomy Governor observe hook. When --governor-policy
    # is supplied, the loop loads scripts/trinity/autonomy_governor.py via
    # importlib (NO subprocess), pins the policy sha256 at boot, and asks
    # the Governor for a decision before each step. v0.1 is observe-only:
    # the loop only HARD-BLOCKS on halt_file_present or
    # policy_mutated_at_runtime; every other blocked_reason is recorded
    # as an audit artifact + a warning but does not stop the pipeline.
    p.add_argument(
        "--governor-policy", default=None,
        help="Path to a trinity-autonomy-governor-policy/v0.1 JSON. "
             "Enables the Governor observe hook. Without this flag the "
             "loop behaves exactly as before (no governor calls).",
    )
    p.add_argument(
        "--governor-decisions-dir", default=None,
        help="Directory where per-step Governor decision JSONs are "
             "written. Defaults to <out-dir>/governor_decisions/. Only "
             "consulted when --governor-policy is supplied.",
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
    if args.request_json is not None and args.input_bundle is not None:
        print(
            "[useful_compute_operator_loop] --request-json and "
            "--input-bundle are mutually exclusive (the request "
            "is either imported OR built from a bundle, not both)",
            file=sys.stderr,
        )
        return 2
    if args.request_json is None and args.input_bundle is None:
        print(
            "[useful_compute_operator_loop] either --request-json "
            "or --input-bundle is required",
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
    except GovernorHardBlock as exc:
        # Sprint 5.24 hard-block path: halt_file_present or
        # policy_mutated_at_runtime. The decision JSON is already on
        # disk and recorded in state["artifacts"]["governor_decisions"]
        # via _governor_call before the exception propagated.
        print(
            "[useful_compute_operator_loop] governor hard-block: "
            + str(exc),
            file=sys.stderr,
        )
        return 3
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
