# Trinity Useful Compute Signed Payment Draft v0.1

## Where this layer sits

Trinity's Useful Compute pipeline now has five distinct "review
artefacts" between an honest worker submission and any actual SOST
transaction:

```
worker result + reward
    -> replay validation              (Sprint 5.8)
    -> governance batch               (Sprint 5.9)
    -> reward budget plan             (Sprint 5.14)
    -> payment proposal               (Sprint 5.15)
    -> [ payment draft  ← THIS LAYER ]
    -> ( future ) governance-signed payment
    -> ( future ) operator broadcast
```

Each artefact is canonical JSON, deterministic from its inputs, and
**none of them moves SOST**. v0.16 of the pipeline adds the **payment
draft**: the first artefact that *can* touch a wallet, but only behind
two explicit gates.

## What a payment draft is (and is not)

The draft is a single JSON file that says, item by item:

- which `payout_address` would receive how many `amount_stocks`
  (and `amount_sost`),
- which `request_id` and `worker_result_ids` justify each output,
- the `total_payment_stocks` of the whole batch,
- the `capsule_summary` copied verbatim from the source proposal,
- a list of `warnings` (dust filter, mode notes, etc),
- an unsigned/signed tx hex pair (both null in v0.1 unsigned; the
  signed slot carries a placeholder string in dry-sign),
- a `safety_status` with the four locked invariants (no_broadcast,
  human_review_required, private_keys_exported=false,
  requires_separate_broadcast) and the two mode-typed flags
  (`dry_sign_only`, `wallet_access_used`).

The draft is **not** a transaction. It does not call any RPC, it
does not call `sendrawtransaction`, it does not export a private
key, it does not broadcast. v0.1 of the layer is the safest possible
"yes, I would pay this" record before any wallet sprint lands.

## Two modes, two confirmation tokens

| Mode | Default | Wallet touched | Token required |
|---|---|---|---|
| `--unsigned-only` | yes | NO | `I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST` |
| `--dry-sign`     | no  | yes (path exists check) | `I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST` |

A bare invocation (no token, no mode flag) refuses to produce a
draft. Passing the wrong token also refuses. The tokens are
verbatim string matches; substring matches are NOT accepted.

`--dry-sign` additionally requires `--wallet <path>` and either
`--from-label <label>` or `--from-address <addr>`. The script
verifies the wallet file exists. **It does NOT load keys, NOT
extract a private key, NOT sign anything in v0.1.** A future
sprint will replace the placeholder signing block with a real
wallet-driven flow under explicit human review.

## Differences between proposal, draft, signed draft and broadcast

| Layer | What it produces | Wallet | Signing | Broadcast |
|---|---|---|---|---|
| Proposal (5.15) | `payable_items` mapped to addresses | NO | NO | NO |
| Draft (5.16) - unsigned-only | outputs[], no tx hex | NO | NO | NO |
| Draft (5.16) - dry-sign | outputs[] + placeholder signed_tx_hex | yes (path check) | NO (v0.1) | NO |
| Signed payment (future) | real signed tx hex | yes (load keys) | YES | NO |
| Operator broadcast (future) | tx accepted by mempool | yes | already done | YES (human-driven) |

Each step strictly downstream of the previous one. The further
right, the more dangerous; v0.1 stops at the second-leftmost
column.

## Reviewing a draft before signing

When the future signing sprint lands, the human reviewer should
walk through the draft in this order:

1. **`source_proposal_id` matches the proposal I approved.**
   Re-load the source proposal independently and compare
   `payable_items` to the draft's `outputs[]`.
2. **`total_payment_stocks` is within budget.** Re-load the source
   budget independently and confirm the total does not exceed the
   per-day / per-epoch cap.
3. **Each `payout_address` is correct.** Cross-check against the
   worker address map. Look for typos in bech32 characters.
4. **`warnings[]` is empty or fully understood.** Dust filter
   triggered? OK if expected. Dry-sign warning? Make sure that is
   intentional.
5. **`safety_status` carries `no_broadcast=true`,
   `human_review_required=true`, `private_keys_exported=false`,
   `requires_separate_broadcast=true`.** All four are schema
   constants; if they are missing or false, the file is invalid.
6. **`capsule_summary` text is honest.** Will be the public anchor
   when the Proof Registry sprint publishes it.

Only after every step is green should the signing sprint be
invoked.

## How a future broadcast would work (sketch)

This sprint does NOT implement the next step. Sketch only:

1. A new script reads the draft + the real wallet.
2. It loads the wallet keys behind a separate confirmation flow.
3. It builds an actual signed tx using the existing SOST wallet
   builder (no new tx format introduced).
4. It writes the signed tx to disk; still does NOT broadcast.
5. A separate `--broadcast` step, also gated by a token, sends the
   tx to a SOST RPC endpoint.
6. The Proof Registry sprint anchors the capsule_summary on-chain
   after the tx confirms.

Each of those five steps will live in its own dedicated layer.

## CLI surface

```
python3 scripts/trinity/useful_compute_payment_draft.py \
  --mode local-dry-run \
  --proposal <TRINITY_USEFUL_COMPUTE_PAYMENT_PROPOSAL_<id>.json> \
  --out-dir <dir> \
  --unsigned-only \
  --max-total-stocks 1000000 \
  --require-confirmation-token \
    I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST
```

Hard rejects (all return rc=2):

- `--mode` ≠ `local-dry-run`
- `--broadcast` / `--send` / `--payout-now` / `--auto-pay`
  / `--sendrawtransaction` / `--export-private-key`
- wrong confirmation token (mode-specific)
- `--unsigned-only` combined with `--wallet` / `--from-label`
  / `--from-address`
- `--dry-sign` without `--wallet` or without `--from-label` /
  `--from-address`
- `--max-total-stocks` exceeded by the source proposal

## Web miner console

`website/trinity-useful-compute.html` (badge v1.0) gains a new
"Signed Payment Draft" card. It is a read-only loader: choose a
draft JSON, see totals, outputs table, safety badges, warnings
and tx hex placeholders. The page never asks for a wallet, a
seed, a private key, an RPC password, or a signature. The page
never calls `fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource`,
or `navigator.sendBeacon`. All rendering uses `textContent`.

The card carries a danger strip: **"This page does not sign or
broadcast payments. The draft is a review artefact. Real signing
happens locally via a separate wallet sprint. Broadcast happens
in yet another explicit human-driven sprint after that."**

## Risks

- **Wrong address map.** Caught upstream by the proposal layer
  (Sprint 5.15) but the draft inherits the addresses verbatim. A
  human reviewer must still confirm them before any signing.
- **Inflated max-total-stocks cap.** If the operator passes a cap
  larger than they intended, the draft will pass through.
  Mitigation: the signing sprint must independently re-derive the
  cap from the budget plan.
- **Dust thresholds.** v0.1 hard-codes 546 stocks as the dust
  threshold. Outputs below that are skipped + warned. A future
  sprint may make this configurable per policy.
- **Fee / change not estimated.** v0.1 records
  `total_fee_stocks_estimated=0` and `change_stocks_estimated=0`
  because the script does not query the chain. The signing sprint
  must compute real fee + change before producing a real signed
  tx; ignoring the draft's zero values for those fields is
  required behaviour for the next layer.
- **Wallet path side-channel.** Passing the wallet path on the CLI
  in `--dry-sign` mode exposes the path to shell history.
  Mitigation: v0.1 does not load keys; only existence is checked.
  A future sprint should accept the wallet via a more guarded
  channel.
- **Placeholder signed_tx_hex.** The string
  `DRYSIGN_PLACEHOLDER_NO_REAL_SIGNING_IN_V01` MUST NEVER be
  forwarded to a real broadcaster. The signing sprint must reject
  it explicitly.

## Reference run

With the same three-honest-workers pipeline (alice / bob / carol,
governance approves 45000/worker × 3 = 135000, budget plan keeps
70% primary share = 94500), the unsigned-only draft is:

```
draft_id                 draft-ed3391733ff866fc
source_proposal_id       prop-016602fa8acd6584
total_outputs            3
total_payment_stocks     94,500
total_fee_stocks_est.    0   (not computed in v0.1)
change_stocks_est.       0   (not computed in v0.1)
unsigned_only            True
dry_signed               False
wallet_access_used       False
private_keys_exported    False
warnings                 0
outputs:
  alice -> sost1qaaa... 31,500 stocks
  bob   -> sost1qccc... 31,500 stocks
  carol -> sost1qddd... 31,500 stocks
```

In `--dry-sign` mode with a placeholder wallet file the same draft
becomes:

```
dry_signed               True
wallet_access_used       True
private_keys_exported    False
signed_tx_hex            DRYSIGN_PLACEHOLDER_NO_REAL_SIGNING_IN_V01
warnings (2):
  - dry-sign mode: signed_tx_hex is a placeholder string...
  - dry-sign --from-label='test-from' recorded for audit; not used.
```

Both drafts produce identical `outputs[]` and totals. Only the
safety metadata + the signed_tx_hex differ.
