# wSOST bridge, Gold Reserve V2 and governance — Stage 1 architecture

Status: **Stage 1 — local / devnet engineering only.** Branch `feat/wsost-gold-reserve-v2`.
Nothing here is deployed to Ethereum mainnet or testnet, no production key exists, no real funds
move, and SOST consensus, node, miner and CLI are unchanged. Public status of every component
remains RESEARCH (see `website/sost-wsost-gold-vault.html`).

## Constitutional invariants

1. **1 wSOST = 1 native SOST locked** in the Bridge Vault. `wSOST.totalSupply` never exceeds the
   confirmed native backing; the indexer proves it, and more (see accounting).
2. **Native SOST is never burned.** Only wSOST is burned, to request a release. Native SOST is
   released, never destroyed.
3. **Gold never mints wSOST.** Gold Reserve V2 has no path into WSOST.
4. **No arbitrary gold withdrawal.** There is no `withdraw(address)` and no function with a free
   destination parameter in Gold Reserve V2 or its Quarantine Vault.
5. **Five ledgers never combined:** native SOST · Bridge-locked SOST · wSOST · Gold Reserve V2 ·
   historical Gold Vault + PoPC (frozen since #25,000, committed to the DTD Jackpot).

## Components

| Component | File | Role |
|---|---|---|
| WSOST | `contracts/wsost/src/WSOST.sol` | ERC-20 (8 decimals). Mint only with ≥ threshold EIP-712 observer attestations; unique deposit id; daily and exposure caps; mint pause independent from transfers; burn-for-release; timelocked configuration; no owner mint, no confiscation, no proxy |
| SigLib | `contracts/wsost/src/SigLib.sol` | ECDSA recovery with low-s and v∈{27,28} |
| ReserveBase | `contracts/wsost/src/ReserveBase.sol` | Guardian approvals per action id, successor registry by runtime code hash, frozen proposal hash, 2/3-of-full-census check, timelocked final migration |
| GoldReserveVault | `contracts/wsost/src/GoldReserveVault.sol` | Contributions (XAUT enabled, PAXG gated), pause 2/5 (moves nothing), unpause 4/5, critical rescue 4/5 + delay → fixed Quarantine Vault only |
| QuarantineVault | `contracts/wsost/src/QuarantineVault.sol` | Temporary custody; no deposit, no withdraw; leaves only by the governed migration path |
| sostbridge | `ops/sostbridge/` | Python: capsule parsing, SOST RPC + in-memory chain with reorgs, observer, relayer helpers, ledger/reconciliation, release signer abstraction, governance indexer |
| CLIs | `ops/bridge-observer.py`, `ops/bridge-indexer.py`, `ops/governance-indexer.py` | Operator entry points (devnet) |

## Wrap (deposit → mint)

```
Juan:  sost-cli send <BRIDGE_VAULT> 500 --capsule-mode open-note --capsule-text "WSOST:0x<recipient>"
          (capsule = SCPv1 open note, active since #7,350 — no consensus change)
observers (3): independently re-verify on their own node
          tx canonical · pays the vault · amount · recipient capsule · not a vault self-spend ·
          >= min_confirmations (30, provisional) · deposit id not used · bridge not CRITICAL
       → sign EIP-712 Deposit{depositId, recipient, amount, bridgeVault, sostBlockHash,
                               sostBlockHeight, confirmations=min_confirmations, bridgeVersion}
relayer: collects >= 2 identical statements, checks the block is still canonical, calls mint()
WSOST:  verifies version, vault, confirmations, caps, unused id, sorted distinct observer signatures
```

- **Deposit id** = `keccak256("SOST-WSOST-DEPOSIT-V1" || txid || vout_be32)`. A deposit mints once.
- **Domain separation**: EIP-712 domain = name "SOST wSOST Bridge", version "1", chainId,
  verifying contract; the struct carries `bridgeVersion` and `bridgeVault`. Replays across chains,
  deployments or bridge versions fail.
- The statement attests "buried by at least `min_confirmations`", so every honest observer signs an
  identical message regardless of when it looked.
- **Relayer ≠ signer.** A relayer holds no authority; with no signatures `mint` reverts.

## Unwrap (burn → release)

```
holder:  WSOST.burn(amount, "sost1…")  → BurnedForRelease(burnId, from, amount, sostAddress, nonce)
release: ReleaseProcessor → ReleaseSigner.execute_release(burnId, dest, amount − fee_allowance)
         native tx carries the capsule WSOST-RELEASE:0x<burnId> (exactly 80 bytes)
journal: burn id recorded BEFORE signing — a crash or a mempool-invisible release cannot cause a
         second release; the chain check refuses burns already released
```

Signer abstraction: `ColdSingleSigner` (Stage 1, single dedicated vault wallet, capped pilot) →
`NativeMultisigSigner` (target; requires a future explicit consensus upgrade — see
NATIVE_MULTISIG_FUTURE.md). Deposits, attestations and accounting do not change when the signer does.

**Known limitation:** `sost-cli createtx` (sign without broadcast) does not accept a capsule today,
so a fully air-gapped signature of a release needs a future CLI feature. Stage 1 signs and submits
with `sost-cli send` from the vault wallet on the signing machine. The CLI was not modified.

## Accounting (bridge indexer)

| | Ledger | Source |
|---|---|---|
| A | confirmed native deposits | SOST chain |
| B | deposits awaiting confirmations | SOST chain |
| C | minted wSOST | `Minted` events |
| D | burned wSOST | `BurnedForRelease` events |
| E | burns awaiting native release | D without a matching release |
| F | completed native releases | SOST chain (release capsules) |
| G | Bridge Vault balance | SOST chain (all outputs to − inputs from the vault) |
| H | wSOST totalSupply | contract |

CRITICAL (with an exact reason) when any of: `C − D ≠ H`; a mint without a canonical deposit; a
mint whose amount, recipient or block hash differs from the deposit; a deposit minted twice; a
release without a burn; a release whose amount ≠ burn − allowance or whose destination differs; a
burn released twice; any vault spend without a release capsule; confirmed backing < supply +
awaiting releases + unminted confirmed deposits. Otherwise PENDING while anything is in flight,
else BALANCED. `confirmed_backing ≥ totalSupply` is necessary but never treated as sufficient.

On CRITICAL the safety layer calls `pauseMint()` (any observer may) and observers refuse new
attestations. Transfers and burns keep working. Nothing is repaired silently.

## Gold Reserve V2

```
contribute(asset, amount)      enabled assets only (XAUT; PAXG gated off), permanent, no claim
pause()                        2-of-5, stops contributions and migration execution, moves nothing
unpause()                      4-of-5
queueRescue / executeRescue    4-of-5 + rescue delay → the fixed Quarantine Vault only
registerSuccessor(vault,hash)  4-of-5, vault must be a contract with exactly that runtime code hash
queueMigration(proposal,result) 4-of-5 on (proposalHash, tallyHash) + result.yes ≥ ceil(2/3 census)
                               + registered successor = proposal.successorVault/codehash
                               + proposal.timelock ≥ minimum
executeMigration(proposal)     after the timelock; re-checks the successor's code at execution
```

**Enforced on Ethereum:** guardian thresholds, the frozen proposal hash, the 2/3-of-full-census
arithmetic on the submitted counts, the timelock, the successor's registered code hash, no EOA, no
free destination. **Verified off-chain:** that the submitted counts are the canonical SOST tally —
Ethereum cannot read SOST. Guardians attest it with `tallyHash`; anyone can recount with
`ops/governance-indexer.py`. A guardian majority ignoring a valid vote would be publicly provable,
not technically impossible; that is why destination rules live in the contract.

Successor code hashes include constructor immutables, so a successor is approved per deployed
instance after review.

## Governance (SOST side)

- Census: identities eligible at the snapshot (`EligibilityRules`: ≥3 SbPoW blocks in 2,016,
  active NODE_BIND bound at or before the snapshot with a minimum age, heartbeat participation).
  Explicit governance rules, derived from — not identical to — Jackpot V2. Frozen at the snapshot.
- Vote: self-transfer from the identity, every input from that identity, open-note capsule
  `SOSTGOV1|<proposal>|S<snapshot>|YES|NO|ABSTAIN` (28 of 80 bytes), confirmed in (snapshot, close].
- Last valid vote before the close wins; the history is kept. One identity, one vote.
- `required_yes = ceil(2/3 × census)`; ABSTAIN is never YES.
- States: OPEN → CLOSED_FINALITY_PENDING → FINAL_PASS | FINAL_FAIL after the finality depth.
- The proposal hash is computed identically in Python and Solidity (checked in the E2E).

## Naming note (G-rules)

The public website's historical "Metals Reserve Constitution" uses labels G1–G7/G10, while
`docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md` uses G1–G5 for the (inactive) spend gates of the
historical Gold Vault. They are different lists under the same letters. This bridge work does not
reuse either label set and does not rename any protocol concept.

## Tests

- Solidity (Foundry): `contracts/wsost/test` — `cd contracts/wsost && forge test --offline`.
- Python: `python3 -m pytest -q tests/bridge`.
- Local E2E: `python3 tests/bridge/e2e_devnet_anvil.py` (real SOST DEVNET_FAST node, miner and CLI
  plus Anvil; disposable keys) — 44/44, see `E2E_STAGE1_RESULT.md`. Capsules are only valid from
  #7,350 in every profile, so the capsule flow runs on the real contract with an in-memory SOST side
  until a devnet chain passes that height.
