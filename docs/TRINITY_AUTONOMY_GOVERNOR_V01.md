# Trinity Autonomy Governor v0.1 (Sprint 5.23)

> Status: SHIPPED in branch `trinity/autonomy-governor-v01`. Not merged
> to `main` at the time of writing. Operates against the threat model
> in `SECURITY.md` (T01-T20).

## Why this exists

Trinity, by Sprint 5.22, can take a scientific intake document and walk
it all the way through worker → replay → governance → budget → proposal
→ payment draft. Every step is deterministic and auditable. **Nothing
autonomous touches money** — the two confirmation tokens
(`I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST` and
`I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION`) are typed
literally by a human for every transaction.

Before Trinity grows any autonomy at all — even something as harmless
as "Claude Code reads a PDF and proposes a benchmark" — we need a
**constitution**: a machine-checkable policy that tells the rest of
the codebase what an autonomous component *would* be allowed to do.
That is the Autonomy Governor.

The Governor v0.1 does **not** govern the operator loop at runtime
yet. It is shipped as a standalone evaluator with comprehensive tests.
Future sprints integrate it into the operator loop and the upcoming
Brain (Claude Code as a sandboxed `source_tool`), citing every cap and
allowlist back to the threats T01-T20 it mitigates.

## What it does

```
policy.json (constitution)
        +
proposed action + params
        ↓
+--------------------+
| autonomy_governor  |   pure function, no side effects
+--------------------+
        ↓
decision JSON (verdict, not execution)
        ↓
audit log (append-only) + future watchdog (separate process)
```

The Governor:

1. **Loads** a policy JSON file and pins its sha256 at boot
   (`boot_policy_sha256`).
2. **Recomputes** the policy sha256 at every decision
   (`policy_runtime_sha256`). If they differ, the decision is blocked
   with `policy_mutated_at_runtime`. This protects against T15 (log /
   proof tampering) and T13 (supply-chain compromise of the policy
   file).
3. **Checks** the kill switch (`/etc/trinity/HALT` by default). If
   the file exists, every action is blocked.
4. **Evaluates** the proposed action against the policy's caps,
   allowlists, and human-approval list.
5. **Emits** a deterministic decision JSON
   (`TRINITY_AUTONOMY_GOVERNOR_DECISION_<id>.json`) that cites the
   threats T01-T20 the action is relevant to.

The Governor **never** executes the action. v0.1 is observe-only. The
decision is a verdict, not an instruction.

## What it cannot do (by construction)

The static safety test
(`tests/trinity/test_autonomy_governor_safety.py`) fails CI if
`scripts/trinity/autonomy_governor.py` ever imports or calls any of:

- network libraries: `requests`, `urllib`, `httpx`, `aiohttp`, `socket`,
  `websockets`, `ftplib`
- shell / subprocess: `subprocess`, `os.system`, `os.popen`,
  `shell=True`
- dynamic code execution: `eval`, `exec`
- wallet / signing primitives: `private_key`, `seed_phrase`, `mnemonic`,
  `passphrase`, `ecdsa`, `secp256k1`
- broadcast / RPC clients: `sendrawtransaction(`, `broadcast(`,
  `sost-cli`
- sibling Trinity modules: `operator_loop`, `broadcast_guard`,
  `payment_draft`, `payment_proposal`, `reward_budget`,
  `useful_compute_worker`, `useful_compute_backends`,
  `useful_compute_task_builder`, `scientific_prompt_intake`

The Governor is intentionally narrow: it can read its policy file and
write decision JSONs to the operator-supplied `--out-dir`. Nothing
else.

## Relation to SECURITY.md (T01-T20)

Every decision carries a `threat_refs` field that maps the action to
the threats from the threat model. The default per-action mapping is:

| Action | Threats it touches |
| --- | --- |
| `create_request` | T01 (prompt injection), T05 (runaway cost), T09 (path leakage) |
| `launch_worker` | T02 (malicious worker), T03 (replay mismatch), T05 (runaway cost) |
| `call_rpc` | T12 (RPC credential leakage) |
| `real_sign` | T06 (wallet exposure), T07 (accidental broadcast), T08 (autonomous payment abuse) |
| `broadcast_signed_transaction` | T07, T08 |
| `wallet_access` | T06, T08, T11 (operator compromise) |
| `filesystem_read` | T09, T15 (log tampering) |
| `filesystem_write` | T09, T15 |
| `constitution_change` | T13 (supply chain), T15 |
| `register_new_source_tool` | T01, T13, T14 (dependency compromise) |

The Governor refuses **`real_sign`**, **`broadcast_signed_transaction`**,
**`wallet_access`**, **`constitution_change`** and
**`register_new_source_tool`** regardless of policy: these are in a
hardcoded `ALWAYS_REQUIRE_HUMAN_APPROVAL` set. A permissive policy
cannot bypass them.

## v0.1 hard invariants

These are enforced by the code and the tests; weakening any requires
a new sprint, a fresh review, and a new v0.x version of the schema.

| Invariant | Where enforced | Threats mitigated |
| --- | --- | --- |
| Only `mode = observe` ships | `_validate_policy_v01` rejects other modes at load | T08 (autonomous payment) |
| `caps_per_day.autonomous_sost_stocks == 0` | `_validate_policy_v01` rejects non-zero | T08 |
| Policy hash pinned at boot | `decide()` compares `boot_policy_sha256` vs `policy_runtime_sha256` | T13, T15 |
| Policy file not writable by Trinity | Deployment requirement (chown root / mode 0644) | T13, T16 (governance bypass) |
| Halt file blocks every action | `_check_halt` polled per decision | every threat (emergency stop) |
| Governor has no network | `test_autonomy_governor_safety` static grep | T05, T11, T20 |
| Governor has no shell / subprocess | same | T11 |
| Governor has no wallet / sign / broadcast | same | T06, T07, T08 |
| Governor has no eval / exec | same | T11, T14 |

## The future watchdog (out of scope for v0.1)

A separate process, `governor_watchdog.py`, will:

- Tail the audit log (`logs/governor/audit.log`).
- Post notifications to Telegram / Healthchecks when the Governor
  blocks something with `requires_human_approval=true` or when the
  halt file appears.
- Heartbeat to an external service so its silencing is observable
  (threat T20).

The watchdog will have **network access** but **no** wallet access,
**no** broadcast capability, and **no** write access to the policy or
the audit log. It is a strict observer.

**Out of scope for v0.1.** The watchdog is its own sprint.

## Deployment notes

When you put this into production:

1. `chown root:root config/trinity_autonomy_governor.json` and
   `chmod 0644` it. Trinity must not have write permission.
2. `mkdir -p /etc/trinity && chown root:root /etc/trinity`. Trinity
   must not be able to delete a halt file you create.
3. Set up `logs/governor/audit.log` with `chattr +a` (append-only on
   ext4 / xfs) once the runtime integration lands in a later sprint.
   v0.1 does not write an audit log; the decision JSON files in
   `--out-dir` are the audit trail today.
4. Do not symlink the policy file across volumes. The Governor
   computes sha256 over the file it actually reads; a symlink swap
   would be invisible to the runtime-mutation check.

## CLI examples

Allowed (a known `source_tool` under the cap):

```bash
python3 scripts/trinity/autonomy_governor.py \
    --policy config/trinity_autonomy_governor.example.json \
    --action create_request \
    --action-param source_tool=trinity_scientific_prompt_intake \
    --action-param estimated_worker_minutes=5 \
    --out-dir /tmp/governor-decisions \
    --pinned-time 2026-05-16T00:00:00+00:00
```

→ writes `TRINITY_AUTONOMY_GOVERNOR_DECISION_<id>.json` with
`"allowed": true, "blocked_reason": null, "threat_refs": ["T01", "T05", "T09"]`.

Blocked (requires-human action):

```bash
python3 scripts/trinity/autonomy_governor.py \
    --policy config/trinity_autonomy_governor.example.json \
    --action broadcast_signed_transaction \
    --action-param to_address=TEST_ADDR_B \
    --action-param amount_stocks=100 \
    --out-dir /tmp/governor-decisions \
    --pinned-time 2026-05-16T00:00:00+00:00
```

→ `"allowed": false, "blocked_reason": "requires_human_approval",
"requires_human_approval": true, "threat_refs": ["T07", "T08"]`.

Blocked (non-allowlisted RPC method):

```bash
python3 scripts/trinity/autonomy_governor.py \
    --policy config/trinity_autonomy_governor.example.json \
    --action call_rpc \
    --action-param rpc_method=dumpprivkey \
    --out-dir /tmp/governor-decisions \
    --pinned-time 2026-05-16T00:00:00+00:00
```

→ `"allowed": false, "blocked_reason": "rpc_method_not_in_allowlist",
"threat_refs": ["T12"]`.

## What v0.1 explicitly does NOT do

- ❌ Integrate with the operator loop. Future sprint.
- ❌ Read or write the audit log. Future sprint, append-only.
- ❌ Network heartbeats. The watchdog does this; the Governor never.
- ❌ Reach into a wallet or RPC. Both are forbidden by the static
  safety test.
- ❌ Allow `mode = propose` or `mode = execute_bounded`. Hardcoded
  reject. Each future mode is its own sprint.
- ❌ Allow `autonomous_sost_stocks != 0`. Hardcoded reject.

## What v0.2 will probably do

The roadmap below is informational, not a commitment:

- v0.2: `mode = propose` — Governor produces a queue of approval
  drafts; a human signs off in batch.
- v0.3: integration into `operator_loop` for real-time gating
  (still observe-only externally).
- v0.4: `mode = execute_bounded` for non-financial actions only.
- v0.5: watchdog process + audit-log append-only writes.

Each of these will land in its own branch, with its own threat-model
update if the surface widens.
