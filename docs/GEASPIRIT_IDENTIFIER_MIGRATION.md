# The `geaspirit` identifier — why renaming it is not cosmetic

**Status: DEFERRED.** A rename was attempted on 2026-08-09 as part of the
SOST/GeaSpirit separation and was reverted the same day. This records what went
wrong so nobody retries it as a find-and-replace.

## What was tried

Rename the internal Trinity track identifier `geaspirit` to `geospatial` across
`scripts/trinity/`, `tests/trinity/`, `config/trinity/` and `schemas/trinity/`
— 64 occurrences in 22 files, plus renaming
`config/trinity/objectives/geaspirit.json` to `geospatial.json`.

It looked safe. The consensus audit had already established that none of this
reaches `sost-node`, `sost-miner` or `sost-cli`: zero matches in the 57 C++
sources, and zero matches in `strings` across all 16 compiled binaries. That
part still holds — **this is not a consensus concern**.

## What broke

The full Trinity suite went from 5 pre-existing failures to 14. Two distinct
causes, both outside `sost-core`:

### 1. The identifier is an input to a deterministic hash

`materials-engine-private/src/multi_ai_review/hypothesis_schema.py:93`

```python
def hypothesis_hash(self) -> str:
    key = f"{self.project}|{self.type}|{self.subject}|{self.claim}".lower().strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
```

`project` is the track name. Changing `geaspirit` to `geospatial` changes the
hash of **every hypothesis ever recorded under that track**. Trinity pins this:
`test_pipeline_byte_identical_across_runs` and
`test_pipeline_seed_change_changes_bundle` both failed, because the bundles
stopped reproducing against previously generated output.

Reproducibility is the point of those bundles. Silently invalidating historical
hashes to tidy up a name is a bad trade.

### 2. A whitelist in a separate private repository

`materials-engine-private/src/multi_ai_review/hypothesis_schema.py:13`

```python
PROJECTS: Tuple[str, ...] = (
    "materials", "geaspirit", "sost", "useful_compute", "generic",
)
```

`materials-engine-private` is its own git repository. Any renamed value is
rejected at construction time with `ValueError: invalid project: 'geospatial'`,
which is what took down `test_geo_discovery_v01`, `test_geo_materials_bridge`
and `test_no_public_claims`.

So the rename is a **coordinated two-repository change**, not a local cleanup.

## Verification of the revert

`git reset --hard` on the rename branch, then:

```
tests/trinity/test_geo_discovery_v01.py
tests/trinity/test_geo_materials_bridge.py
tests/trinity/test_no_public_claims.py
    -> 35 passed
```

Back to the 5 pre-existing failures (`test_task_builder_reader_metadata` ×2,
`test_v13_dtd_flip_audit` ×3), which are unrelated and predate this work.

## The compatible strategy, if it is ever wanted

**Not implemented. Proposal only.**

Keep `geaspirit` as the frozen storage identifier and add `geospatial` as a
display alias. Historical hashes stay valid because the hashed value never
changes.

1. **Storage identifier stays `geaspirit`** — forever, for anything that has
   been hashed, serialized or written to a bundle. Treat it as a legacy
   constant, like a database enum value that outlived its name.

2. **Add an alias layer** in `hypothesis_schema.py`:
   ```python
   PROJECTS = ("materials", "geaspirit", "sost", "useful_compute", "generic")
   PROJECT_ALIASES = {"geospatial": "geaspirit"}   # accepted on input
   PROJECT_DISPLAY = {"geaspirit": "Geospatial"}   # shown in output
   ```
   Normalize on input, so both spellings are accepted; hash the canonical
   (legacy) value only.

3. **Rename the display layer only** — reports, dashboards, docs, page copy.
   Those are not hashed.

4. **Version it if the storage name must really change.** Introduce
   `hypothesis_hash_v2` alongside v1, tag each record with the version that
   produced it, and never re-hash old records. This is the only honest way to
   move the stored identifier, and it costs a schema migration.

5. **Land both repositories together**, with the full Trinity suite green
   before and after.

## Scope note

This is separate from — and not required by — the SOST/GeaSpirit separation.
Phases 1 and 2 removed every public reference in both directions without
touching this identifier. It is internal naming in an off-chain research
harness that no user sees. Deferring it costs nothing.

Consensus impact: **none**, confirmed by source and binary audit.
Requires coordinated node upgrade: **no**.
Safe to defer past V15: **yes**.
