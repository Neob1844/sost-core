# Trinity External Worker Trial Pack v0.1

**Sprint:** 5.37 (Part A of combined sprint 5.37-5.39)
**Status:** additive · audit-only · zero hash / payment / consensus changes
**Depends on:** Sprint 5.35 (Friendly Worker Onboarding) · 5.34 (Materials Cache) · 5.32 (Materials Engine Backend) · 5.12 (cross-worker replay contract)

---

## 1. Why it exists

Sprint 5.35 made it possible to *document* a new worker host
(read-only JSON bundle, no secrets). It did not give that worker
host an actual, runnable trial. A friend who wants to help run
Trinity needs a small, self-contained pack that:

- Contains one canonical request to run.
- Tells them which Sprint 5.32 backend will pick it up.
- Tells them exactly which `compute_output_sha256` they should
  reach if their host is deterministic-correct.
- Carries no secret material: distributing the pack is safe.

Sprint 5.37 ships that pack.

---

## 2. What the pack contains

```
<out-dir>/
    PACK_MANIFEST.json            ← schema-validated, hashes every file
    README_WORKER_TRIAL.md        ← human-readable run instructions
    worker_config.json            ← suggested worker CLI args + safety flags
    sample_request.json           ← the request to run
    expected_result_hashes.json   ← expected compute_output_sha256
```

- `PACK_MANIFEST.json` follows
  `trinity-worker-trial-pack-manifest/v0.1` and contains:
  `pack_id` (`twtp-<16hex>`), `worker_id`, `worker_id_hash`,
  `pinned_time`, `repo_commit`, `repo_tag`, `request_basename`,
  `request_sha256`, `expected_compute_output_sha256`, `files[]`
  (each with name + size_bytes + sha256), `safety_status` (six
  const-true flags), `notes`.
- `expected_result_hashes.json` follows
  `trinity-worker-trial-pack-expected/v0.1` and carries the
  expected `compute_output_sha256` plus an at-a-glance materials
  summary (`top_ranked_material`, `top_ranked_score`,
  `known_materials`, `materials_project_cache_*`).
- `worker_config.json` follows
  `trinity-worker-trial-pack-config/v0.1` and is the recipient's
  pinned configuration: preferred backend
  (`local_materials_engine_v01`), an address-map template with a
  `<PAYOUT_ADDRESS_FOR_<worker_id>>` placeholder (the schema
  rejects any real `sost1+40hex` value), and six const-true safety
  flags.

---

## 3. Safety contract

Static tests assert all of the following:

- The pack contains **NO** real SOST address (`sost1+40hex`).
- The pack contains **NO** 64-hex blob that is not bound to a
  named hash field (sha256, cache_sha256,
  compute_output_sha256, etc.). Any unbound 64-hex blob would be
  shaped like a private key.
- The pack contains **NO** absolute `/tmp/` paths from the
  operator's build directory.
- All six safety flags are const-true at both the script source
  and the schema level:
  - `no_wallet_required`
  - `no_private_key_required`
  - `no_seed_phrase_required`
  - `no_broadcast_capability`
  - `no_network_in_worker_process`
  - `pack_carries_no_secrets`
- The pack builder imports ONLY `useful_compute_backends` (to
  compute the expected hash). All other sibling imports are
  rejected by the static safety test.

---

## 4. Determinism

`build_trial_pack(worker_id, pinned_time, out_dir, request_fixture,
repo_commit, repo_tag)` is deterministic: same inputs always
produce the same pack bytes. Tests assert byte-identical files
across two independent invocations and identical `pack_id` +
`expected_compute_output_sha256`.

The expected hash is computed by invoking
`useful_compute_backends._materials_engine_v01` over the request,
canonicalising `backend_result.output_obj` with sorted keys + UTF-8
+ no whitespace, and sha-256ing the resulting bytes — exactly the
same pipeline that the worker uses to produce
`compute_output_sha256`. So if the recipient's worker runs the
same request against the same materials cache, they MUST get the
same hash.

---

## 5. Recipient workflow

The README that ships in the pack tells the recipient:

1. Clone `sost-core` at the pinned `repo_commit`.
2. Drop the pack alongside.
3. Run:

       python3 scripts/trinity/useful_compute_worker.py \
           --mode local-dry-run \
           --request <pack>/sample_request.json \
           --out-dir <pack>/worker_out \
           --worker-id <their-worker-id> \
           --pinned-time <pack's pinned_time>

4. Open the resulting `TRINITY_USEFUL_COMPUTE_RESULT_*.json` and
   confirm `compute_output_sha256` equals
   `expected_compute_output_sha256` from the pack.

If the two hashes match, their host satisfies the Sprint 5.12
cross-worker replay contract. If they differ, the recipient's
environment is drifting (different Python version, different
locale, edited materials cache, …) and the operator must not add
them to a real queue until they investigate.

---

## 6. Non-goals for v0.1

- The pack does **not** activate any payment. The operator
  replaces the placeholder payout address out-of-band after the
  recipient passes the trial.
- The pack does **not** open the network from the worker
  process (`no_network_in_worker_process = True`).
- The pack does **not** ship a wallet, key, seed, or signing
  material.
- The pack does **not** ship an executable shell script. All
  recipient commands live in the README.
