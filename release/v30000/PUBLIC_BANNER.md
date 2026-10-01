# V30000 public upgrade banner / notice (ready to publish on GO — not yet deployed)

## Explorer / website banner (operator-facing)
> **SOST V30000 — HARD FORK AT BLOCK #30,000 — UPDATE REQUIRED**
> All operators must update **node + miner + cli** before #30,000 (this is NOT a cli-only
> release). Activation is automatic by height; no manual step at the block.
> Official binaries + SHA256 + guide: <release link>.
> SHA256 — node `78fefb67…cbb56` · miner `eec96efb…64951` · cli `c8ae00b9…2691b`.
> Verify with `sha256sum -c` before installing.

## DEX / Tokenization notice (already live on the gated pages, pre-#30000 copy)
> IMPLEMENTED & VALIDATED · ACTIVATES AT BLOCK #30,000 · NOT YET ACTIVE ON MAINNET ·
> PUBLIC ACCESS RESTRICTED · CONTROLLED DEVELOPER ACCESS · EXPERIMENTAL PROTOCOL ·
> PENDING MAINNET VALIDATION AND REGULATORY READINESS.
> (auto-switches to "LIVE AT PROTOCOL LEVEL / MAINNET — CONTROLLED DEVELOPER ACCESS / …"
> once height ≥ 30000.) *Technical availability does not constitute regulatory authorization.*

## Correction vs the stale v16.2.x notice
The current public page says "only sost-cli changed; node & miner byte-identical." That is
TRUE for v16.2.x but FALSE for V30000: node, miner AND cli all change. The published notice
must be replaced with the above on go-live.
