# Trinity dossier — AOI `kalgoorlie`

- **Schema**: `trinity-dossier/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source scorecard**: `scorecard_kalgoorlie.json` (sha256 `836b677c14a73ee3…`)
- **Source scorecard SHA-256 (full)**: `836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246`
- **Features available / total**: 0 / 5
- **Fallback mode**: `True`
- **Publishability**: `needs_human_review`

## Honesty matrix (verbatim from source scorecard)

- **Tier**: Tier 1 — Remote proxy evidence only
- **Environment**: semi_arid
- **Adjusted confidence**: 0.0

> **Source recommendation**: Field validation with local geophysics required before any geological interpretation. These are statistical anomalies, not geological conclusions.

**Acknowledged blind spots from the source:**
- Direct imaging of buried ore bodies at depth
- Reliable detection through dense vegetation (C-band limitation)
- Detection through thick homogeneous overburden (>2-3m in most soils)
- Differentiation of mineralised vs non-mineralised similar material
- Replacement of field geophysics (ERT, GPR, gravity, magnetics)
- Quantitative depth estimation without calibration data

## Reviews

### 1. kalgoorlie: AOI-level priority assessment (fallback mode)

- **Subject**: `aoi:kalgoorlie`
- **Type**: `aoi_priority`
- **Hypothesis hash**: `abb3423914c731a4`
- **Council decision**: `hold` (confidence 0.55)
- **Next step (council)**: needs more evidence before promotion
- **Strongest argument**: validator verdict=partially_supported (level=local_report_supported)

**Claim:** AOI kalgoorlie is currently in Tier 1 — Remote proxy evidence only. No per-target ranking is available in this scorecard; the dossier records the honesty-matrix limits and recommends explicit data uplift before any geological interpretation.

**Why it might be true:** Field validation with local geophysics required before any geological interpretation. These are statistical anomalies, not geological conclusions.

**Evidence needed:**
- Process additional Geaspirit feature layers for this AOI
- Compute per-target ranking once layers are available
- Re-run `aoi_to_dossier.py` after the layer uplift
- Source-acknowledged limit: Direct imaging of buried ore bodies at depth
- Source-acknowledged limit: Reliable detection through dense vegetation (C-band limitation)
- Source-acknowledged limit: Detection through thick homogeneous overburden (>2-3m in most soils)
- Source-acknowledged limit: Differentiation of mineralised vs non-mineralised similar material
- Source-acknowledged limit: Replacement of field geophysics (ERT, GPR, gravity, magnetics)

**Validation path:**
- `geaspirit_layer_review`
- `data_completeness_assessment`

**Council opinions:**

| Member | Verdict | Confidence | Rationale |
| --- | --- | --- | --- |
| `validator_member` | `agree` | 0.55 | validator verdict=partially_supported (level=local_report_supported) |
| `local_knowledge` | `insufficient` | 0.00 | no local doc mentions 'aoi:kalgoorlie' |
| `mock_ai` | `abstain` | 0.40 | mock: insufficient signal for a strong call |

---

## Summary

- **Reviews emitted**: 1
- **Decision tally**:
    - `hold`: 1

## Operator actions

- Inspect the per-review next_step strings; only promote a target after independent geological field validation.
- Optionally register the dossier hash as a SOST capsule with `sost-cli send --capsule-mode doc-ref-open --capsule-locator <https-url-of-dossier> --recipient-pubkey <self>`. The hash to register is printed below.

## Integrity

- **Canonical JSON SHA-256**: `d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf`
- The hash above is computed over the canonical (sorted, no-spaces, ASCII) JSON serialisation of the dossier object. Re-running the script with the same scorecard input will produce a different hash if the `generated_at_utc` field changes; pass `--pinned-time` to fix it.

## Capsule registration (manual, optional)

If the operator chooses to register this dossier on chain as proof of priority, the SHA-256 above is the locator content. Two natural carriers in SOST are:

1. `OPEN_NOTE_INLINE` — short label fitting in 80 bytes, for example: `trinity-dossier kalgoorlie sha256:<first16hex>`.
2. `DOC_REF_OPEN` — full URL pointing at the dossier file (commit hash on a public mirror or hosted JSON), with the SHA-256 stored in the capsule's hash field.

The script does not broadcast. The dossier is not a geological conclusion; it is a council-reviewed plan based on remote-proxy evidence with explicit limits.
