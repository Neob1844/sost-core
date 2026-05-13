# Trinity Useful Compute — Human Broadcast Guard v0.1

Sprint **5.18** of the Trinity Useful Compute stack. This is the
**first** sprint that is allowed to broadcast a SOST transaction.
Every prior Trinity sprint refuses broadcast outright; this one only
broadcasts after a human operator has cleared every gate by hand.

## Position in the pipeline

```
[5.6 task]  →  [5.7 worker]  →  [5.8 replay]  →  [5.9 governance]
                                      ↓
                       [5.14 budget]  →  [5.15 proposal]
                                      ↓
              [5.16 unsigned/dry draft]  →  [5.17 real-signed draft]
                                      ↓
                       [5.18 HUMAN BROADCAST GUARD]   ← this sprint
                                      ↓
                              node mempool  →  chain
```

## What this sprint adds

1. A new CLI subcommand `sost-cli sendrawtransaction <hex>` — a
   thin wrapper around the existing `sendrawtransaction` RPC.
   Does NOT touch the wallet, does NOT sign, does NOT mark UTXOs
   spent. ~50 lines in `src/sost-cli.cpp`.
2. A new Python script `scripts/trinity/useful_compute_broadcast_guard.py`
   — the only Trinity script in the entire stack that is allowed
   to broadcast a transaction. The guard:
   - Loads a Sprint 5.17 real-signed draft.
   - Validates every safety flag on the draft.
   - In `--mode local-dry-run` (default): emits a receipt with
     `broadcast_performed = false`. No subprocess.
   - In `--mode human-broadcast`: requires the exact confirmation
     token `I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION`,
     invokes `sost-cli sendrawtransaction <signed_tx_hex>` via
     `subprocess.run(..., shell=False, timeout=...)` and records
     the node's txid in the receipt.
3. A new schema `trinity-useful-compute-broadcast-receipt/v0.1`
   with seven const-locked safety flags (`human_broadcast_only`,
   `requires_manual_confirmation`, `no_private_keys`,
   `no_wallet_access`, `no_signing`, `no_automatic_payout`,
   `single_transaction_only`).
4. A new web console panel that loads a receipt JSON from disk and
   renders the result. No `fetch`, no wallet inputs, no signing
   buttons.

## CLI invocation

### Dry-run (default)

```bash
python3 scripts/trinity/useful_compute_broadcast_guard.py \
  --mode local-dry-run \
  --draft /tmp/uc-payment-real-sign/TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_<id>.json \
  --out-dir /tmp/uc-broadcast-receipts \
  --max-total-stocks 1000000
```

No wallet binary is invoked. The receipt has
`broadcast_performed = false` and `txid_broadcast = null`. This
mode is for offline review of the draft + the validation pipeline.

### Human-triggered broadcast

```bash
python3 scripts/trinity/useful_compute_broadcast_guard.py \
  --mode human-broadcast \
  --draft /tmp/uc-payment-real-sign/TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_<id>.json \
  --out-dir /tmp/uc-broadcast-receipts \
  --max-total-stocks 1000000 \
  --require-confirmation-token I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION \
  --sost-cli-bin /usr/local/bin/sost-cli \
  --sost-cli-timeout 60
```

Requires:

| Flag | Why |
| --- | --- |
| `--require-confirmation-token` | exact match; substrings refused |
| `--max-total-stocks` | hard cap before any subprocess call |
| `--sost-cli-bin` | path to the rebuilt sost-cli (Sprint 5.18) |
| `--draft` | a Sprint 5.17 v0.2 draft with `real_signed = true` |

Any of these argv flags abort with rc=2 BEFORE argparse:
`--auto-pay`, `--send`, `--payout-now`, `--export-private-key`,
`--sign-now`.

## Draft validation matrix

A draft is **refused** before any broadcast attempt if any of:

| Check | Failure reason |
| --- | --- |
| `schema != "trinity-useful-compute-payment-draft/v0.2"` | wrong schema |
| `draft_id` does not match `^draft-[0-9a-f]{16}$` | wrong format |
| `real_signed != true` | nothing to broadcast |
| `signing_mode != "real_sign_local"` | wrong mode |
| `signing_scope` not in `{full_proposal, single_payable_item_subset}` | unknown scope |
| `signed_tx_hex` empty / not hex / odd length | not a valid raw tx |
| `txid_if_signed` not 64-lowercase-hex | wrong txid format |
| `capsule_attached != false` | future-format draft, refuse v0.1 |
| `safety_status.no_broadcast != true` on source draft | wrong source |
| `safety_status.automatic_payout != false` | wrong source |
| `safety_status.human_review_required != true` | wrong source |
| `safety_status.private_keys_exported != false` | wrong source |
| `safety_status.requires_separate_broadcast != true` | wrong source |
| `total_payment_stocks > --max-total-stocks` | cap exceeded |
| (broadcast mode) txid from node != `txid_if_signed` from draft | mismatch |

Every check runs before the subprocess. The cap and the txid-match
check are deliberately conservative — a mismatch indicates either a
tampered draft or a buggy CLI build, and either way the receipt
should not record the broadcast as clean.

## Receipt fields

```json
{
  "schema": "trinity-useful-compute-broadcast-receipt/v0.1",
  "receipt_id": "rcpt-<16 hex>",
  "source_draft_id": "draft-<16 hex>",
  "txid_if_signed": "<64 hex>",
  "txid_broadcast": "<64 hex> | null",
  "signed_tx_hex_sha256": "<64 hex>",
  "broadcast_performed": true | false,
  "broadcast_mode": "local-dry-run" | "human-broadcast",
  "confirmation_token_hash": "<64 hex> | null",
  "total_payment_stocks": 0,
  "max_total_stocks": 0,
  "pinned_time": "2026-05-13T00:00:00+00:00",
  "sost_cli_bin_hash": "<16 hex> | null",
  "safety_status": {
    "human_broadcast_only":          true,
    "requires_manual_confirmation":  true,
    "no_private_keys":               true,
    "no_wallet_access":              true,
    "no_signing":                    true,
    "no_automatic_payout":           true,
    "single_transaction_only":       true
  }
}
```

All seven `safety_status` flags are locked `const: true` in the
schema. A reviewer can tell at a glance whether anyone has tried
to tamper with the receipt.

`receipt_id` is `sha16(canonical(mode + source_draft_id +
txid_if_signed + txid_broadcast + broadcast_performed +
pinned_time + max_total_stocks))`. Two runs that produce the same
broadcast outcome produce byte-identical receipts.

## Hard safety boundaries

- No wallet path. No private key. No seed phrase. No mnemonic.
  No passphrase. No signing function. Static safety tests verify
  none of these tokens exist in the broadcast-guard source.
- Only the `sost-cli` binary is spawned. Only the
  `sendrawtransaction` subcommand is in the allowlist. The
  runtime guard rejects every other subcommand and every flag in
  `_FORBIDDEN_ARGV_TOKENS`.
- `subprocess.run(..., shell=False, ...)` is the only process
  primitive. `Popen`, `call`, `check_call`, `check_output` and
  `os.system` are statically banned.
- No HTTP / TCP / WebSocket imports. The CLI itself talks JSON-RPC
  to the local node; Python does not.
- `--mode local-dry-run` never invokes a subprocess at all.

## What this sprint does NOT do

- It does NOT broadcast more than one draft per invocation. There
  is no batch flag and no loop. If you want to broadcast three
  drafts, you run the guard three times.
- It does NOT sign anything. The signed hex was produced in Sprint
  5.17 and must already exist in the draft.
- It does NOT pay anything automatically. There is no scheduler,
  no cron, no daemon mode in this sprint.
- It does NOT verify that the txid from the node matches the
  txid_if_signed by re-deriving from the hex; it only checks
  string equality of the two values. A real "rederive" check is a
  future hardening sprint.
- It does NOT replace `sost-cli` for general broadcasts. Use it
  for Trinity Useful Compute payments only.

## Files touched

| File | Change |
| --- | --- |
| `src/sost-cli.cpp` | NEW subcommand `sendrawtransaction <hex>` |
| `scripts/trinity/useful_compute_broadcast_guard.py` | NEW |
| `schemas/trinity/useful_compute_broadcast_receipt.schema.json` | NEW v0.1 |
| `tests/trinity/test_useful_compute_broadcast_guard.py` | NEW |
| `tests/trinity/test_useful_compute_broadcast_guard_schema.py` | NEW |
| `tests/trinity/test_broadcast_guard_safety.py` | NEW |
| `tests/trinity/test_broadcast_guard_web_console.py` | NEW |
| `website/trinity-useful-compute.html` | NEW "Human Broadcast Guard" panel |
| `website/api/explorer_version.json` | v238 |
| `docs/TRINITY_USEFUL_COMPUTE_HUMAN_BROADCAST_GUARD_V01.md` | this document |
