# PSBT & Multisig — Implementation Assessment

**Date:** 2026-03-24

## PSBT (Partially Signed Bitcoin Transactions)

**Status:** Designed but NOT implemented in this session.

**Why not now:**
- PSBT is a wallet-level serialization format (~1000+ LOC)
- No consensus change required
- Requires: key-value map format, role separation (creator/updater/signer/combiner/finalizer/extractor), serialization format for unsigned TX + metadata
- Dependencies: stable TX format, working HD wallet (now done), air-gapped signing workflow design

**Implementation plan when ready:**
1. `include/sost/psbt.h` — PSBT data structure (key-value maps per input/output)
2. `src/psbt.cpp` — Create/Update/Sign/Combine/Finalize/Extract
3. `sost-cli psbt create <to> <amount>` — Create unsigned PSBT
4. `sost-cli psbt sign <file>` — Sign with local keys
5. `sost-cli psbt finalize <file>` — Finalize and extract raw TX
6. `sost-cli psbt broadcast <file>` — Send finalized TX to node

**Effort:** ~2-3 days, no consensus risk

## Multisig

**Status:** NOT implementable without consensus changes.

**Why not now:**
- True multisig requires OP_CHECKMULTISIG or equivalent script opcode
- SOST currently has no script interpreter — output types are hardcoded (TRANSFER, COINBASE, BOND_LOCK, ESCROW_LOCK)
- Adding m-of-n validation IS a consensus change (new output type, new validation rules)
- Cannot be done as "wallet-layer only"

**What COULD be done without consensus:**
- **Threshold signing via MuSig2** — multiple signers produce a single standard ECDSA signature. Looks like a normal single-key TX on chain. No consensus change needed.
- This is the approach modern Bitcoin wallets use for Taproot-based multisig.

**Recommendation:**
1. Implement PSBT first (pure wallet, no consensus)
2. Implement MuSig2 threshold signing (no consensus)
3. Only add on-chain multisig opcodes when SOST needs a script upgrade
