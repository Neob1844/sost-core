# Trinity Combined Sprint 5.34-5.36: Materials Cache + Worker Onboarding + Dashboard Surfacing

**Sprints rolled into one branch:** 5.34 / 5.35 / 5.36
**Status:** local · cache-only · no LLM · no network · no wallet / no secrets
**Depends on:** Sprint 5.32 (Materials Engine) · 5.31 (Classifier) · 5.30 (Reader Metadata) · 5.33 (Result Surfacing) · 5.28 (Queue Dashboard)

---

## 1. Why one branch

Three small, mutually compatible improvements that all touch the
materials_engine / dashboard surface. Doing them on one branch
keeps the schema-extension surface coherent (the dashboard now
shows all of: top material, cache hits, worker count) and avoids
three rounds of "merge → tag → re-run E2E demo".

| Part | Sprint | What |
|------|--------|------|
| A    | 5.34   | Materials Project-style local cache + hash-bound provenance in materials_engine result |
| B    | 5.35   | Friendly worker onboarding bundle (read-only, no secrets) |
| C    | 5.36   | Dashboard surfacing: cache hits/misses + workers seen |

---

## 2. Part A — Materials Project Cache v0.1

### Data file

`data/trinity/materials_project_cache_v01.json`

Self-contained, hand-curated reference dataset. v0.1 ships two
records (CeO2 / ceria, PrOx / praseodymia) each with:

- `material_id` matching `^trinity-mpc-[a-z0-9-]+-v[0-9]+$`
- `formula_pretty`, `aliases` (case-insensitive lookup)
- `source = "cached_materials_project_style_reference"` (enum-locked)
- `source_url_text` (text only; the loader NEVER fetches it)
- `source_retrieved_at = "manual_curated_v0.1"`
- `properties`: formation_energy_per_atom, band_gap, density,
  energy_above_hull, oxygen_storage_capacity_reference, notes
- `property_hash_sha256` (sha256 of canonical(properties))
- `record_sha256` (sha256 of canonical(record minus record_sha256))

The file itself carries a `cache_sha256` over its canonical body
(excluding the cache_sha256 field). Any tampering — change a
single byte of a property — fails verification at load time.

### Loader contract

`scripts/trinity/useful_compute_backends.py` gains:

- `_load_materials_project_cache()` — lazy, idempotent, called
  once. Searches `data/trinity/` then `config/trinity/`. Verifies
  every hash. **On failure** (missing file, invalid JSON, hash
  mismatch) returns a sentinel cache (records=[], load_error
  set) so the worker never crashes on a bad cache.
- `_verify_cache_hashes()` — recomputes cache_sha256,
  record_sha256, property_hash_sha256 from canonical form; raises
  ValueError on first mismatch.
- `_resolve_material_in_cache(label)` — case-insensitive alias
  lookup; returns None on miss.
- `materials_project_cache_info()` — read-only descriptor for
  tests + dashboard introspection.

### Backend integration

Inside `_materials_engine_v01`, after the ranking is built, the
backend consults the cache for every candidate material and
attaches FIVE new fields **inside the hashed output_obj**:

```json
{
  "materials_project_cache_used":   true,
  "materials_project_cache_version": "v0.1",
  "materials_project_cache_sha256":  "25b9209b...",
  "materials_project_cache_hits": [
    {"query": "CeO2", "material_id": "trinity-mpc-ceria-v01",
     "record_sha256": "...", "property_hash_sha256": "..."},
    {"query": "PrOx", "material_id": "trinity-mpc-prox-v01",
     ...}
  ],
  "materials_project_cache_misses": []
}
```

The cache fields go **inside** `output_obj` (so the per-record
hash anchors land in `compute_output_sha256`). Cross-worker
equality is preserved because the cache file is byte-identical
across hosts: same alias index, same hits, same hashes.

The summary projection (Sprint 5.33) gains five corresponding
roll-up fields: `materials_project_cache_used`,
`materials_project_cache_version`,
`materials_project_cache_sha256`,
`materials_project_cache_hit_count`,
`materials_project_cache_miss_count`.

---

## 3. Part B — Friendly Worker Onboarding v0.1

### Script

`scripts/trinity/worker_onboarding.py` generates a deterministic
read-only JSON bundle for any new worker host.

### Bundle contract

`schemas/trinity/worker_onboarding_bundle.schema.json`
($id `trinity-worker-onboarding-bundle/v0.1`)

```json
{
  "schema":          "trinity-worker-onboarding-bundle/v0.1",
  "bundle_id":       "twob-<16hex>",
  "worker_id":       "worker-C",
  "worker_id_hash":  "<sha16 of worker_id>",
  "pinned_time":     "...",
  "repo_root_basename": "sost-core",
  "supported_backends": [
    {"name": "placeholder",                kind: "placeholder",  experimental: false, note: ...},
    {"name": "local_materials_engine_v01", kind: "real_backend", experimental: false, note: ...},
    ...
  ],
  "required_commands": [
    {"name": "useful_compute_worker", script: "...", purpose: "...",
     example_argv: [...],
     "requires_wallet": false, "requires_private_key": false,
     "requires_network": false},
    ...
  ],
  "sample_paths": {...},
  "address_map_template": {
    "schema":  "trinity-worker-address-map/v0.1",
    "workers": [
      {"worker_id_hash": "<sha16>",
       "payout_address": "<PAYOUT_ADDRESS_FOR_worker-C>",
       "label":          "worker-C"}
    ],
    "_template_notice": "..."
  },
  "safety_checklist": [...],
  "safety_status": {
    "no_wallet_required":           true,
    "no_private_key_required":      true,
    "no_seed_phrase_required":      true,
    "no_broadcast_capability":      true,
    "no_network_in_worker_process": true,
    "bundle_carries_no_secrets":    true
  },
  "notes": [...]
}
```

### Hard rules (all enforced by tests + schema)

- `payout_address` MUST match `^<PAYOUT_ADDRESS_FOR_[A-Za-z0-9._-]+>$`
  — i.e., a placeholder. The schema rejects real `sost1+40hex`
  values.
- Every safety_status flag is `const: true`.
- Every `required_commands[*]` declares
  `requires_wallet=false` + `requires_private_key=false` +
  `requires_network=false` (also `const: false` in the schema).
- The script does NOT create keys, mnemonics, wallets, or
  signatures. Static safety test rejects every wallet/sign/broadcast
  token + every network/shell/LLM primitive.

### What the operator does

1. `python3 scripts/trinity/worker_onboarding.py --worker-id worker-C --out-json /var/lib/trinity/onboarding/worker-C.json --pinned-time …`
2. Distribute the bundle file to the new worker host (it's safe to
   email — no secrets inside).
3. Out-of-band, replace `<PAYOUT_ADDRESS_FOR_worker-C>` with the
   real SOST address in the operator's own address-map file.

---

## 4. Part C — Dashboard surfacing

`task_queue_dashboard.py::_per_item_audit` gains a per-item pass
that walks `worker_out/TRINITY_USEFUL_COMPUTE_RESULT_*.json` and
produces FOUR new optional fields on each `latest_items[*]`:

```json
{
  "materials_project_cache_hits":   2,
  "materials_project_cache_misses": 0,
  "workers_seen":                   2,
  "worker_ids_truncated":           ["worker-A", "worker-B"]
}
```

HTML `render_html` gains TWO new columns (between the existing
`materials_engine` cell and `operator_run`):

```
materials_cache → "2 hits (0 misses)"  — painted #7dd3fc
workers         → "2 (worker-A, worker-B)"
```

Same Sprint 5.28 privacy contracts: no JS, no external assets,
no absolute paths, `html.escape` on every text insertion.

---

## 5. Tests added

| File | Tests | Topic |
|------|-------|-------|
| `tests/trinity/test_materials_project_cache.py`        | 18 | resolver, cache integrity, engine integration, tamper detection |
| `tests/trinity/test_materials_project_cache_schema.py` | 13 | schema valid, patterns, const locks, no real SOST addresses |
| `tests/trinity/test_materials_project_cache_safety.py` | 6  | backends no-new-forbidden-tokens, cache loader present, data file no-private-key blobs, no SOST address, source notice says local |
| `tests/trinity/test_worker_onboarding.py`              | 19 | bundle_id pattern, worker_id_hash sha16, determinism, validation, invalid worker_id rejected (parametrised), safety_status all True, address-map placeholder pattern, no SOST address, no 64-hex blob, required_commands flags, CLI roundtrip |
| `tests/trinity/test_worker_onboarding_safety.py`       | 6  | source has no forbidden tokens, no sibling-module imports, declares v0.1 schema, SUPPORTED_BACKENDS present, safety flags hardcoded True, defensive helper not re-introduced |

Plus three pre-existing schemas extended additively:

- `useful_compute_backends.py` — registry unchanged, but
  `materials_engine_result.schema.json` gains 5 cache fields + the
  required-set test updated.
- `materials_engine_summary.schema.json` gains 5 cache surfacing
  fields (optional).
- `task_queue_dashboard.schema.json` gains 4 surfacing fields per
  `latest_items[*]` (optional).

Total: **62 new tests + 3 schema extensions + 1 required-set
test update**.

---

## 6. Non-goals for v0.1

- **No live Materials Project API call.** Cache-only. v0.2 may
  add a separate, sandbox-isolated fetcher with explicit operator
  confirmation; v0.1 reads JSON from disk and refuses to fetch.
- **No new wallet / key / address material.** The onboarding
  bundle contains placeholders. The cache contains zero SOST
  addresses (static test enforced).
- **No new RPC, no new endpoint, no new daemon.** Pure file IO.
- **No new task_type / source_tool enums.** Auto-routing rules
  from Sprint 5.32 are unchanged.
- **No new backend.** `local_materials_engine_v01` got smarter
  (cache provenance), not replaced.
- **No DFT, no quantum, no real simulation.** Same disclaimer
  surface as Sprint 5.32.

---

## 7. Manual demo

```bash
# Reuse the Sprint 5.31 classifier-derived request.
INTAKE=$(ls /tmp/trinity-5-29-final-intake/out/TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json | head -1)

# Queue + run-once (the auto-router still picks materials_engine,
# now augmented with cache provenance).
python3 scripts/trinity/task_queue.py init   --queue-dir /tmp/trinity-5-34-q
python3 scripts/trinity/task_queue.py enqueue --queue-dir /tmp/trinity-5-34-q \
    --request-json /tmp/trinity-5-31-classifier/request.json \
    --worker-address-map tests/trinity/fixtures/useful_compute/address_map.json \
    --governor-policy config/trinity_autonomy_governor.example.json \
    --pinned-time 2026-05-18T00:00:00+00:00
python3 scripts/trinity/task_queue.py run-once --queue-dir /tmp/trinity-5-34-q

# Generate the dashboard.
python3 scripts/trinity/task_queue_dashboard.py \
    --queue-dir /tmp/trinity-5-34-q \
    --out-dir   /tmp/trinity-5-34-dash \
    --pinned-time 2026-05-18T00:00:00+00:00

# Generate an onboarding bundle for a future worker-C.
python3 scripts/trinity/worker_onboarding.py \
    --worker-id worker-C \
    --out-json /tmp/trinity-5-34-onboarding-worker-C.json \
    --pinned-time 2026-05-18T00:00:00+00:00
```

Expected:

- **Worker result** carries `materials_project_cache_used=true`,
  `cache_sha256=25b9209b…`, 2 hits (CeO2 + PrOx) with their
  record_sha256s.
- **Both workers** still report identical `compute_output_sha256`
  (cross-worker contract preserved).
- **Operator run** roll-up unchanged from Sprint 5.33 (cache info
  flows through summary).
- **Dashboard JSON**: `latest_items[0]` has
  `materials_project_cache_hits=2`, `workers_seen=2`,
  `worker_ids_truncated=["worker-A","worker-B"]`.
- **Dashboard HTML**: new `materials_cache` and `workers` columns
  show "2 hits (0 misses)" and "2 (worker-A, worker-B)".
- **Onboarding bundle**: validates against schema, contains
  `<PAYOUT_ADDRESS_FOR_worker-C>` placeholder, every safety flag
  True, no real SOST address, no 64-hex private-key blob.

---

## 8. Traceability

- Schemas extended additively (no `$id` bumps for the existing
  3); 2 new schemas (`materials_project_cache.schema.json`,
  `worker_onboarding_bundle.schema.json`).
- New data file: `data/trinity/materials_project_cache_v01.json`,
  pinned `cache_sha256` makes any future drift detectable at load
  time.
- Pre-existing artifacts on disk still validate (the cache fields
  in the result schema ARE in `required` — but the only producer
  of materials_engine_result has been Sprint 5.32+ which would be
  updated in lockstep on the same host).
- Pure scripts + schemas + data + docs + tests. Zero `src/`,
  zero consensus, zero wallet / payment / broadcast changes.
