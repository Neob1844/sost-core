# PSBT & Multisig — Implementation Assessment

**Date:** 2026-03-24

> **Superseded (2026-10-13).** The multisig parts of this assessment are replaced by
> `docs/v40000/NATIVE_MULTISIG_SPEC_40000.md` (native `OUT_MULTISIG = 0x50`, transaction
> version 2, no script engine) and `docs/v40000/MULTISIG_OPEN_DECISIONS_CLOSED.md`. The MuSig2
> statement below was wrong and is corrected in place.

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

**What could be done without consensus (corrected 2026-10-13):**
- ~~Threshold signing via MuSig2 produces a single standard ECDSA signature.~~ **Wrong.** MuSig2
  aggregates keys and produces one BIP-340 **Schnorr** signature (64 bytes, `R.x ‖ s`). SOST
  transaction inputs are verified with **ECDSA only** (`secp256k1_ecdsa_verify` in `VerifySighash`,
  `src/tx_signer.cpp`), so a MuSig2 signature cannot authorize a SOST input. Using it would itself
  require a consensus change (a Schnorr input type). In Bitcoin, MuSig2 works because Taproot
  (BIP-341) added Schnorr verification by soft fork.
- The only way to get an ordinary single-key ECDSA signature from several parties without a
  consensus change is **threshold ECDSA** (multi-round MPC such as GG18/GG20, CGGMP or DKLs). It is
  complex, interactive, hides the M-of-N structure from the chain and has a history of
  implementation vulnerabilities; it is not recommended for SOST custody.
- SOST therefore uses native consensus multisig instead (see the specification above).

**Recommendation:**
1. Implement PSBT first (pure wallet, no consensus)
2. ~~Implement MuSig2 threshold signing (no consensus)~~ — not possible without a consensus change (see above)
3. ~~Only add on-chain multisig opcodes~~ — superseded: native M-of-N multisig without a script engine (`docs/v40000/NATIVE_MULTISIG_SPEC_40000.md`)
