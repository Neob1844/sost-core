# Trinity Useful Compute — Real Signed Payment Draft v0.1

Sprint **5.17** of the Trinity Useful Compute stack. This is the first
sprint where Trinity scripts touch a real wallet to produce a real
SOST transaction signature. **It does not, and never will, broadcast.**

## What changed vs Sprint 5.16

| Aspect | 5.16 | 5.17 |
| --- | --- | --- |
| Draft schema | `v0.1` | `v0.2` |
| Modes | `--unsigned-only` (default) + `--dry-sign` | `--unsigned-only` + `--dry-sign` + **`--real-sign`** |
| `--dry-sign` `signed_tx_hex` | `DRYSIGN_PLACEHOLDER_…_V01` | unchanged |
| `--real-sign` `signed_tx_hex` | n/a | real bytes from `sost-cli createtx` |
| `txid_if_signed` (real-sign) | n/a | real 32-byte hex |
| Real signing path | none | `useful_compute_real_signer.py` → `sost-cli createtx` |
| Subprocess in `useful_compute_payment_draft.py` | none | still none — delegated |
| `safety_status.automatic_payout` | n/a | locked `const: false` |
| Broadcast | NEVER | NEVER |
| Auto-payout | NEVER | NEVER |

## Four artefact types in the workflow

The full path from a useful-compute result to a paid worker has four
distinct artefacts. Each is a JSON file you can diff, replay and
discard. **No artefact in this list touches the chain.**

1. **Payment proposal** — Sprint 5.15. Consolidates accepted
   governance batches under a budget. `useful_compute_reward_batch_v1`.
2. **Unsigned draft** — Sprint 5.16 `--unsigned-only`. Reviewable
   list of outputs. No wallet touched.
3. **Dry-sign draft** — Sprint 5.16 `--dry-sign`. Verifies the
   wallet file exists, records `dry_signed=true`, writes a
   placeholder `signed_tx_hex` string. No keys loaded.
4. **Real-signed draft (NEW)** — Sprint 5.17 `--real-sign`. Calls
   `sost-cli createtx` once per eligible payable item and records
   the real signed hex + txid. One draft file per output.
   **Still NOT broadcast.**

The next, *separate*, human-driven sprint takes a real-signed draft
and broadcasts it via `sendrawtransaction`. That sprint does not
exist yet.

## How `--real-sign` works

```
useful_compute_payment_draft.py --real-sign
       │
       ▼ importlib loads, never inlines subprocess
useful_compute_real_signer.py
       │
       │ subprocess.run(["sost-cli", "--wallet", W,
       │   "--from-label", L, "createtx", ADDR, AMOUNT],
       │   shell=False, timeout=60s)
       ▼
sost-cli createtx (C++ binary)
       │
       │ RPC read-only: chain height, listunspent
       │ wallet: ECDSA sign each input (BIP143-simplified sighash)
       │ NO broadcast
       ▼
stdout:
   Inputs:  N
   Outputs: N
   Size:    N bytes
   Fee:     X SOST (Y stocks = Z bytes x R rate)
   Raw hex: <hex>
   Txid:    <hex>
```

The Python wrapper parses that stdout, builds a v0.2 draft per
output, and writes one JSON per output to `--out-dir`.

## CLI invocation

```bash
python3 scripts/trinity/useful_compute_payment_draft.py \
    --mode local-dry-run \
    --proposal /path/to/TRINITY_USEFUL_COMPUTE_PAYMENT_PROPOSAL_<id>.json \
    --out-dir   /tmp/uc-payment-real-sign \
    --real-sign \
    --wallet     /path/to/wallet.json \
    --from-label test-payer \
    --max-total-stocks 1000000 \
    --require-confirmation-token I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST \
    --pinned-time 2026-05-12T00:00:00+00:00 \
    --sost-cli-bin /usr/local/bin/sost-cli \
    --sost-cli-timeout 60
```

Every flag below is required for `--real-sign`:

| Flag | Why |
| --- | --- |
| `--wallet` | path the wallet binary opens; never parsed in Python |
| `--from-label` or `--from-address` | selects the source key on multi-key wallets |
| `--max-total-stocks` | hard cap on the *sum* of outputs across all drafts |
| `--require-confirmation-token I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST` | exact token; substrings or near-matches are refused |

Any of these flags will refuse the run with exit code 2:

| Flag | Reason |
| --- | --- |
| `--broadcast` | banned at pre-argparse scan |
| `--send` | banned at pre-argparse scan |
| `--payout-now` | banned at pre-argparse scan |
| `--auto-pay` | banned at pre-argparse scan |
| `--sendrawtransaction` | banned at pre-argparse scan |
| `--export-private-key` | banned at pre-argparse scan |

`--real-sign` is mutually exclusive with `--unsigned-only` and
`--dry-sign`.

## Safety boundaries

| Surface | Where it is enforced |
| --- | --- |
| `subprocess` lives only in `useful_compute_real_signer.py` | static test `test_payment_draft_safety.py` |
| Only `sost-cli` is invoked | runtime check + static test `test_payment_draft_real_sign_safety.py` |
| Only the `createtx` subcommand is allowed | `_ALLOWED_SUBCOMMANDS = ("createtx",)` + runtime scan + static test |
| `shell=False` | runtime + static test |
| Forbidden argv tokens denied | `_FORBIDDEN_ARGV_TOKENS` tuple + runtime scan |
| No HTTP / TCP / WebSocket imports | static tests on both modules |
| No private-key tokens | static tests on both modules |
| No `sendrawtransaction` RPC | static test on real-signer module |
| Schema locks `no_broadcast`, `human_review_required`, `private_keys_exported=false`, `requires_separate_broadcast`, `automatic_payout=false` | `useful_compute_payment_draft.schema.json` |
| `signed_tx_hex` is bytes, not a placeholder, when `signing_mode = real_sign_local` | functional test |
| `--max-total-stocks` enforced before any wallet call | functional test |
| Proposal with `unresolved` / `deferred` / `rejected` items refuses to sign | functional test |
| Empty proposal refuses to invoke the wallet at all | functional test |

## Threat model — what this sprint protects against

| Threat | Mitigation |
| --- | --- |
| Accidental broadcast | `useful_compute_real_signer.py` never calls a broadcast method; CLI's `send` subcommand is not in `_ALLOWED_SUBCOMMANDS`. |
| Argv smuggling (`--broadcast`, `--auto-pay`, …) | Pre-argparse scan in `useful_compute_payment_draft.py` + runtime allowlist scan in `useful_compute_real_signer.py`. |
| Wrong wallet signed | `wallet_fingerprint_hash` (sha16 of file bytes) is recorded in every draft. Operator compares before broadcasting. |
| Wrong source key | `signer_label_or_address_hash` (sha16 of label or address) is recorded in every draft. |
| Oversize payout | `--max-total-stocks` enforced before any `sost-cli` call. |
| Drift across runs | Each draft's `draft_id` is `sha16(canonical(mode + proposal_id + pinned_time + output + txid + max_total_stocks))`. Identical inputs produce identical `draft_id`. |
| `signed_tx_hex` smuggling via stdout | Strict regex parse of `Raw hex:` / `Txid:` / `Fee:` lines; rejection if any pattern missing. |
| Hung CLI | `--sost-cli-timeout` defaults to 60s; `subprocess.run` raises on timeout and the Python wrapper turns it into a `ValueError`. |
| Stale UTXOs from a prior `createtx` | `sost-cli` calls `mark_tx_inputs_spent` after every successful build; warned in the draft. |

## Threat model — what this sprint does NOT protect against

- Address-map corruption: if Sprint 5.15 wrote the wrong
  `payout_address` for a worker, this sprint signs it faithfully.
  Mitigation: review the proposal before passing it to `--real-sign`.
- A compromised `sost-cli` binary: real signing trusts the local
  binary. Distribute and verify it like any other consensus binary.
- Operator with the wrong wallet file: `wallet_fingerprint_hash` is
  for audit, not authentication.
- Replay: the same signed tx can be broadcast twice if the operator
  manually re-runs the broadcast step.

## Review checklist (before broadcasting any real-signed draft)

1. `schema == "trinity-useful-compute-payment-draft/v0.2"`
2. `signing_mode == "real_sign_local"`
3. `real_signed == true`
4. `safety_status.no_broadcast == true` and `automatic_payout == false`
5. `outputs.length == 1` and the recipient matches the proposal
6. `total_payment_stocks` ≤ `--max-total-stocks` you passed
7. `wallet_fingerprint_hash` matches the wallet you authorised
8. `signer_label_or_address_hash` matches the source key you intended
9. `txid_if_signed` decodes to the same tx as `signed_tx_hex`
10. Warnings list reviewed and understood

If all 10 checks pass, the draft is ready for the *next* sprint to
actually broadcast it. **Sprint 5.17 stops here.**

## Files touched in this sprint

| File | Change |
| --- | --- |
| `schemas/trinity/useful_compute_payment_draft.schema.json` | bumped to v0.2 with new fields and `automatic_payout` const |
| `scripts/trinity/useful_compute_payment_draft.py` | added `--real-sign`, delegates via importlib |
| `scripts/trinity/useful_compute_real_signer.py` | NEW — only Trinity script with `subprocess.run` |
| `tests/trinity/test_payment_draft_safety.py` | bumped to v0.2 assertions |
| `tests/trinity/test_payment_draft_real_sign_safety.py` | NEW |
| `tests/trinity/test_useful_compute_payment_draft.py` | unchanged (v0.1 path still works) |
| `tests/trinity/test_useful_compute_payment_draft_schema.py` | bumped to v0.2 with `signing_mode` and `automatic_payout` |
| `tests/trinity/test_useful_compute_payment_draft_real_sign.py` | NEW |
| `tests/trinity/test_payment_draft_web_real_sign.py` | NEW |
| `website/trinity-useful-compute.html` | v0.2 draft panel + SIGNED-BUT-NOT-BROADCAST banner |
| `website/api/explorer_version.json` | v236 |
| `docs/TRINITY_USEFUL_COMPUTE_REAL_SIGNED_PAYMENT_V01.md` | this document |

## What is still deferred

- **Broadcast.** No script in any Trinity sprint sends a tx.
- **`signed_outputs[]` aggregation.** Sprint 5.17 produces one draft
  per output. A future sprint may consolidate them under one capsule.
- **`selected_utxos[]` introspection.** v0.2 stores `inputs_count`
  via warnings, not the txid/vout list. Decoding `signed_tx_hex`
  for full UTXO breakdown is deferred.
- **Capsule attachment to the chain tx.** `sost-cli` supports
  `--capsule-mode`, but the v0.2 draft does not yet pass it through.
- **HSM / hardware-wallet integration.** Out of scope.
