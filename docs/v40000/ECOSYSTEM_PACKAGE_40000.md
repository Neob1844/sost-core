# ECOSYSTEM PACKAGE — #40,000 horizon

**Scope.** This document classifies each ecosystem component by whether it needs a
SOST consensus fork, gives its current status, and lists what still has to happen.
It deploys nothing and activates nothing. Baseline: `release/v40000-prep`
`bc8a45d9`.

**Ledger rules.** `docs/bridge/ARCHITECTURE.md` defines five separate ledgers, and
they are never combined:

1. native SOST
2. bridge-locked SOST
3. wSOST
4. Gold Reserve V2
5. the historical Gold Vault + PoPC reserve

The rules that follow from this:

* The **historical Gold Vault + PoPC reserve is frozen** for the existing
  Historical Jackpot. It held 66,474.29 SOST at height 30,428 (see
  ECONOMICS_80_15_5.md) and drains only through `TX_TYPE_JACKPOT`.
* It is never wSOST backing.
* It is never reopened.
* It is never counted toward any other reserve.
* **Gold Reserve V2** is a new, separate, external reserve. It is not wSOST
  backing, and gold never mints wSOST.
* **wSOST**: 1 wSOST corresponds to 1 native SOST locked in the Bridge Vault. It
  is an informational wrapper accounting rule. It does not create any claim on
  gold or on the historical reserve.
* Native SOST is never burned. OUT_BURN 0x20 is RESERVED/INACTIVE: it is rejected
  by R11 on creation and by S12 on spend.

## Summary table

| Component | Needs SOST fork? | Class | Status | Blocking gates |
|---|---|---|---|---|
| wSOST (Ethereum L1 ERC-20) | **No** | ETHEREUM_EXTERNAL | Sepolia test deployment + devnet; mainnet: DO NOT DEPLOY | external audit, legal L1–L10, entity |
| SOST Bridge (capsule deposit, observer attestations, release) | **No** for the pilot (single-key cold vault + existing capsules); **Yes** for a native multisig vault | ETHEREUM_EXTERNAL + WALLET_CLI | devnet + Sepolia E2E; capped operator pilot design | native multisig (CONSENSUS_FORK), G4/G6 independence, audit, legal |
| Proof of Reserves | No | ETHEREUM_EXTERNAL + WEB_UI | indexer reconciliation (BALANCED/PENDING/CRITICAL, auto `pauseMint`) in tests; no public feed | public feed, independent re-computation |
| Gold Reserve V2 (`GoldReserveVault`, `ReserveBase`) | No | ETHEREUM_EXTERNAL | Sepolia with Mock XAUT; no funds; PAXG gated off | audit, legal L4–L7/L10, custody |
| QuarantineVault | No | ETHEREUM_EXTERNAL | Sepolia test | as Gold Reserve V2 |
| AtomicSwapHTLCv2 | No (SOST-side HTLC is consensus-active since #16,000) | ETHEREUM_EXTERNAL | code complete; Sepolia test instance only; canonical config has null addresses | external review, wallet signer |
| Native Asset Passport (Asset Registry v2) | No (capsule `doc_ref`, live since #7,350) | WEB_UI | web tool live; mainnet anchoring pending authorization | anchoring authorization |
| SOST Asset Market / native assets | **Yes** | CONSENSUS_FORK | code present but mainnet `NATIVE_ASSETS_ACTIVATION_HEIGHT = INT64_MAX`; S14 admin gate | see V40000_CONSENSUS_SCOPE §B (NOT READY) |
| Governance / voting tooling | No (open-note capsules + NODE_BIND census) | WALLET_CLI + WEB_UI | research, advisory (Phase A) | maturity criteria before any binding use |
| Offline signing (`buildtx` / `signtx`) | No | WALLET_CLI | **implemented** in `bc8a45d9` | `buildtx` cannot see mempool spends (fails safe) |
| Multisig custody | **Yes** | CONSENSUS_FORK (+ WALLET_CLI) | design only | V40000_CONSENSUS_SCOPE §A |

## Components

### wSOST — Ethereum L1 wrapper

**Fork needed: no.**
- Deposits use `sost-cli send <BRIDGE_VAULT> … --capsule-mode open-note --capsule-text "WSOST:0x<recipient>"`. That is the SCPv1 capsule, already active since #7,350.
- Releases carry the capsule `WSOST-RELEASE:0x<burnId>`.

**Status:**
- `contracts/wsost/src/WSOST.sol` (26 tests).
- Stage 1 devnet: E2E 44/44.
- Stage 2 Sepolia (`docs/bridge/STAGE2_SEPOLIA_RESULT.md`, chainId 11155111): WSOST `0x4F71ef1D4878225eBd711216A75451F0bfF946C0`.
- Wrap/unwrap scored 32/33. The one fail was a stale RPC read; the final state was BALANCED.
- Recorded verdict: **MAINNET_RECOMMENDATION: DO NOT DEPLOY**.

**Contract properties:** no owner mint, no confiscation, no proxy; daily and exposure caps; 2-day admin timelock.

**Dependencies:**
- Bridge Vault address on mainnet: none exists yet. Sepolia uses the devnet vault hash.
- Observers.

**Remaining gates:**
- External audit.
- Legal decisions L1–L10 (`docs/bridge/LEGAL_DECISIONS.md`).
- Entity and jurisdiction.
- An independent observer set (DECENTRALIZATION G6).

### SOST Bridge

**Fork needed: no** for a capped single-key operator pilot (`ColdSingleSigner`). The pilot is "not trustless and not decentralized".

**Yes** for the intended 3-of-5 native multisig vault: that needs OUT_MULTISIG, which does not exist today.

**Status:** devnet and Sepolia E2E (observers 2-of-3 EIP-712 attestations after 30 confirmations).

**Remaining gates:**
- Native multisig consensus (#40,000 target, design not ready; see scope doc).
- A rotation and migration runbook: pause mint → reconcile → publish policy → move funds with `WSOST-MIGRATE` → prove reserves → 2-day timelock → resume.
- Zero key/machine overlap between vault signers and observers.

**Known P2P issue (non-consensus):** in the capsule-fast devnet, nodes that diverged 2 blocks deep did not converge. GETB is by height and orphan parents are not requested (`docs/bridge/CAPSULE_FAST_DEVNET.md`). This is NODE_HARDENING and must be fixed before relying on bridge confirmations.

### Proof of Reserves

**Fork needed: no.** It reconciles locked native SOST (vault UTXOs) against wSOST supply.

**Status:** the indexer A–H checks and automatic `pauseMint` on CRITICAL exist inside the E2E suites. There is no public feed.

**Gates:**
- A public, independently re-computable feed (anyone can run the indexer against their own node).
- It must never include historical reserve funds or Gold Reserve V2 as wSOST backing.

### Gold Reserve V2

**Fork needed: no.** It is an Ethereum vault (`GoldReserveVault.sol`, `ReserveBase.sol`, 26 tests).

**Status:**
- Sepolia `0x3cDaaD6a606a4ab77EBCd5DB421fbd1f8792534B` with Mock XAUT.
- "NO GOLD RESERVE V2 FUNDS YET".
- PAXG gated off; Gold→wSOST desk gated off.

**Guardian thresholds:**
- Pause 2/5.
- Unpause 4/5.
- Rescue 4/5 plus a delay, and only to the fixed QuarantineVault.
- Migration needs a ≥ 2/3 census, a timelock, and a registered successor code hash.

**Separation:** Gold Reserve V2 is separate from wSOST backing and from the frozen historical Gold Vault.

**Gates:** audit, legal L4–L7/L10, real custody.

### QuarantineVault

**Fork needed: no.**

**Status:** Sepolia `0x8ef5A156cA578e779655085dc9655C79b61ee1A0`. It is the only rescue destination.

**Gates:** same as Gold Reserve V2.

### AtomicSwapHTLCv2

**Fork needed: no.** The SOST-side HTLC (`OUT_HTLC_LOCK`, CLAIM/REFUND tx types) has been consensus-active since #16,000.

**Status:**
- Code complete; 14 tests, plus the WsostAtomicSwap fuzz/invariant tests.
- Anvil E2E 27/27; Sepolia 28/28.
- Sepolia test instance: `0x395295622fDE4702BA199e4898F85B9d85175794`.
- The canonical `contracts/atomic-swap/deploy/htlc-v2-config.json` still has null addresses, consistent with "not deployed".

**Gates:** external review, wallet signer.

**Limitation:** an HTLC cannot pay to a multisig claimant in the first multisig version (open question).

### Native Asset Passport

**Fork needed: no.** It anchors a manifest hash through a capsule `doc_ref` (live since #7,350).

**Status:**
- Web tool `website/js/asset-passport-v2.js`; tests 77/77.
- `legal_classification` is always "NOT DETERMINED BY SOST".
- Mainnet anchoring awaits authorization.

**Gap:**
- The native-asset `AssetDef.manifest_hash` is documented as the Passport manifest hash, but no test links the two.
- `docs/ASSET_REGISTRY_V2.md` still says the native UTXO asset layer is "not built". The code exists but is dormant, so the doc is stale.

### SOST Asset Market (native assets)

**Fork needed: yes.** Mainnet activation is `INT64_MAX`, and the S14 admin gate (reject code 214) can only be lifted by a future height-gated release.

**Status:** NOT ACTIVATION READY (V40000_CONSENSUS_SCOPE §B). Web gate flags `DEX_PUBLIC_ENABLED`, `TOKENIZATION_PUBLIC_ENABLED` and `MAINNET_VALIDATED` are all false.

**Gates:** everything in §B, plus an external audit and regulatory review.

### Governance / voting tooling

**Fork needed: no.**
- Votes are open-note capsules: `SOSTGOV1|<proposal>|S<snapshot>|YES|NO|ABSTAIN`.
- The census comes from NODE_BIND/heartbeat identities, one identity one vote, with a ceil(2/3) threshold.
- Guardians verify the tally off-chain.

**Status:** research, advisory first (`ops/governance-indexer.py`, `tests/bridge/test_governance.py`).

**Gates:**
- Maturity criteria before any binding use.
- Sybil resistance of the census. Today NODE_BIND identities are not proof of independent operators (DECENTRALIZATION G6).

### Offline signing

**Fork needed: no.**

**Status: implemented** in `bc8a45d9`:
- `buildtx` is online and watch-only, and writes `sost-unsigned-tx-v1`.
- `signtx` is offline and checks format, network, genesis, inputs, duplicates, fee and output types.
- Tests: byte-equivalence 36/36, devnet E2E 22/22, suite 120/120.

**Missing for multisig:** `combinetx`, `verifytx`, `finalizetx`, `createmultisig`, and the `sost-psst-v1` format.

**Stale docs:** `docs/bridge/CLI_CAPSULE_OFFLINE_DESIGN.md` and `ARCHITECTURE.md` still say "not implemented".

### Multisig custody

**Fork needed: yes.** Here is why:
- There is no multisig output type: 0x50 is unassigned, and the legacy `OUT_SCRIPT_HASH` 0x30 collides with `OUT_NODE_PROTOCOL`.
- `TxInput` carries a single signature.
- Addresses accept only `sost1`.
- R11 and S9 reject unknown output types.
- No sigcheck limit exists.

**Status:** design only (`docs/design/NATIVE_MULTISIG_40000.md` on `design/native-multisig-40000`, "IMPLEMENTATION NOT AUTHORIZED").

**Gates:** see V40000_CONSENSUS_SCOPE §A.

## Package conclusion

Everything except **native multisig** and **native assets** can proceed **without a SOST fork**. Those other items are Ethereum contracts, CLI tooling, web pages and operational work. Their real blockers are external audit, legal decisions, and operator independence, not the #40,000 height.
