# Trinity Sprint Release Runner v0.1

**Sprint:** 5.40
**Status:** additive · read-only · zero hash / payment / consensus changes
**Depends on:** all prior Trinity sprints (consumes their artifacts; modifies none)

---

## 1. Why it exists

Cutting a sprint release used to look like this in the
operator's terminal:

```
git checkout main
git pull --ff-only
git merge --no-ff feature/branch
python3 -m pytest tests/trinity/ -q
git push origin main
git tag -a sprint-N -m "..."
git push origin sprint-N
```

Each step is small. The compound is easy to typo. A missed
`pull --ff-only`, a typo in the tag name, a stale local main, a
half-completed merge — any of these can rot a release.

Sprint 5.40 ships a **preflight verifier**. It does NOT perform
the release. It only confirms the local state is plausibly ready
to release. The operator still runs the destructive verbs
(`push`, `merge`, `tag`) by hand.

---

## 2. CLI

```
python3 scripts/trinity/sprint_release_runner.py verify \
    --repo-root /opt/sost \
    --sprint-id sprint-5.40 \
    --branch trinity/sprint-release-runner-v01 \
    --base-ref main \
    --out-json /var/lib/trinity/release/TRINITY_SPRINT_RELEASE_REPORT_<id>.json \
    --out-md   /var/lib/trinity/release/TRINITY_SPRINT_RELEASE_REPORT_<id>.md \
    --pinned-time 2026-05-18T00:10:00+00:00
    [--pytest-target tests/trinity/]
    [--demo-root    /tmp/trinity-5-37-39-final-v3]
    [--require-clean-tracked-tree]
    [--allow-untracked]
```

Exit codes:

| code | meaning |
|---:|---|
| `0` | report written; `ready_to_release = true` |
| `1` | report written; `ready_to_release = false` (warnings recorded) |
| `2` | usage / setup error (bad repo-root, etc.) |

---

## 3. What it inspects

| input | how it's read | mutates? |
|---|---|---|
| current branch | `git rev-parse --abbrev-ref HEAD` | no |
| HEAD commit | `git rev-parse HEAD` | no |
| base ref commit | `git rev-parse <base-ref>` | no |
| tracked dirty | `git status --porcelain` | no |
| untracked files | `git status --porcelain` | no |
| changed files vs base | `git diff --numstat <base>..HEAD` | no |
| commits ahead | `git log --pretty=%H %s <base>..HEAD` | no |
| pytest | `python -m pytest <target> -q --tb=no` | no |
| demo artifacts | recursive walk for `*.json`, match on `schema` field | no |

All git invocations use argv-list form. The runner refuses any
git verb outside the read-only allow-list
(`rev-parse`, `status`, `diff`, `log`, `branch`, `ls-files`,
`rev-list`). `shell=True` is never set and is forbidden in source.

---

## 4. Artifact discovery (by schema content, not filename)

Operators rename demo files routinely. The runner ignores file
names; it identifies artifacts by their `schema` field:

| schema | artifact_type |
|---|---|
| `trinity-task-queue-autopilot-report/v0.1` | `autopilot_report` |
| `trinity-task-queue-dashboard/v0.1` | `dashboard` |
| `trinity-daily-report/v0.1` | `daily_report` |
| `trinity-worker-trial-pack-manifest/v0.1` | `trial_pack_manifest` |

Anything else is silently ignored. The walk is symlink-safe
(only files whose resolved path stays inside `--demo-root` are
considered) and capped at 100 entries to keep the report bounded.

---

## 5. Output

`trinity-sprint-release-report/v0.1` JSON + a Markdown rendering.
Top-level fields include:

- `report_id` (`tsr-<16hex>`)
- `sprint_id`, `branch`, `current_branch`, `branch_match`
- `head_commit` (40-hex), `head_commit_short`, `base_commit`
- `repo_root_basename`
- `tree_status`: `{tracked_dirty, untracked_count, untracked_allowed}`
- `changed_files[]` (`{path, status, additions, deletions}`, capped 200)
- `additions_total`, `deletions_total`, `changed_files_count`
- `commits_ahead[]` (`{sha_short, subject}`, capped 50)
- `pytest`: `{ran, target, returncode, passed, failed, skipped, errors, summary}`
- `demo_artifacts[]` (`{artifact_type, path_basename, schema, summary}`)
- `warnings[]`
- `ready_to_release` (bool)
- `safety_status` (ok / warning / failed)
- `safety_flags`: 7 const-true flags

The Markdown report contains 9 sections (Branch, Commits, Tree
status, Changed files, Tests, Demo artifacts, Warnings, Safety
flags) and never leaks absolute `/tmp/` paths.

---

## 6. Safety contract

Static tests assert:

- No `shell=True`, `os.system`, `os.popen`, `eval`, `exec`.
- No network primitive (`requests`, `urllib`, `httpx`, `aiohttp`,
  `socket.socket`, `http.client`).
- No GitHub API surface (`api.github.com`, `GITHUB_TOKEN`,
  `X-GitHub-`, `PyGithub`).
- No wallet / signing / broadcast tokens.
- No LLM client imports.
- No string-form `subprocess.run("...")`; argv lists only.
- No destructive git argv literals: `"push"`, `"merge"`, `"tag"`,
  `"reset"`, `"checkout"`, `"rm"`, `"clean"`, `"commit"`, `"add"`,
  `"stash"`.
- An `ALLOWED_GIT_VERBS` constant exists in source listing all
  seven read-only verbs.
- The runner imports NO sibling Trinity module.
- All seven `safety_flags` are const-true at script AND schema level.

---

## 7. What this is NOT

- It is NOT a release tool. It does not push, merge, or tag.
- It is NOT a CI surrogate. It runs pytest locally; CI still
  runs whatever CI runs.
- It is NOT a daemon. Single-shot bounded invocation.
- It is NOT GitHub-aware. No API calls; no token reading.
- It is NOT a wallet, signer, or broadcaster.

The release-cut sequence after a green report still belongs to
the operator's hands.
