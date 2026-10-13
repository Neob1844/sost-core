# Stage 2 — Sepolia deployment and real E2E (2026-10-13)

**Label: TESTNET (Ethereum Sepolia, chainId 11155111) + SOST capsule-fast DEVNET. Not a mainnet validation.**
Test tokens only. No Ethereum mainnet. No SOST mainnet. No production keys.
The Bridge Vault signer is the Stage 2 single cold key (ColdSingleSigner path). Native multisig is not implemented.

## Deployer and funding

- Disposable testnet deployer `0xB6C433C46B4F7Cd95A524B1a4c8A19fa9b51835D`. The key never leaves the owner machine and is never committed.
- Funding: 0.05 SepoliaETH, tx `0x0a3da10b16071de14754cfbb4a56476f599bbf81e560f0dd1882fa3efe29edbf` (block 11,903,926, status 1).
  Verified on two RPCs (publicnode, 1rpc.io).
- The test observers (3), guardians (5) and the swap counterparty (Alice) are fresh test keys generated for this run.
  Their public addresses are in `sepolia/deployment.json`.

## Contracts (new deployments; the superseded PoPC SOSTEscrow is not reused)

| Contract | Address | Tx | Block | Gas used | Runtime bytes / keccak256 |
|---|---|---|---|---|---|
| WSOST | `0x4F71ef1D4878225eBd711216A75451F0bfF946C0` | `0x10d081b7…eb7b` | 11,904,101 | 15,095,931 | 8,821 / `0x457cccc1…eb97` |
| QuarantineVault | `0x8ef5A156cA578e779655085dc9655C79b61ee1A0` | `0x5e4c96fa…4a37` | 11,904,103 | 9,760,465 | 5,304 / `0x3e6c0b79…b857` |
| GoldReserveVault | `0x3cDaaD6a606a4ab77EBCd5DB421fbd1f8792534B` | `0xe2738182…5e16` | 11,904,104 | 13,907,788 | 7,987 / `0xd02743e4…5711` |
| AtomicSwapHTLCv2 | `0x395295622fDE4702BA199e4898F85B9d85175794` | `0x28fbbc94…7032` | 11,904,105 | 9,742,661 | 6,166 / `0x0aab418f…7167` |

- Compiler: solc `0.8.24+commit.e11b9ed9`, optimizer on, 200 runs. Build tool: forge 1.5.1.
- Effective gas price was about 0.001 gwei. Full tx hashes, constructor arguments and code hashes are in `sepolia/deployment.json`.
- AtomicSwapHTLCv2 runtime equals the compiled artifact byte for byte. The other contracts carry immutables.
- Constructor arguments:
  - WSOST: bridgeVault = keccak256 of the devnet Bridge Vault address. Admin is the deployer. 3 observers, threshold 2, 30 confirmations, exposure cap 100,000 wSOST, daily mint cap 50,000 wSOST.
  - QuarantineVault: 5 guardians; registered assets Mock XAUT and Mock PAXG; minTimelock 3,600 s.
  - GoldReserveVault: the same guardians and the QuarantineVault above. Mock XAUT is enabled and Mock PAXG is gated. minTimelock 3,600 s, rescueDelay 600 s.
  - AtomicSwapHTLCv2: no constructor arguments.

### Finding: forge under-estimates contract creation on current Sepolia

`forge script` estimates gas in its local EVM:
- WSOST: about 2.9 M locally, while the Sepolia node (reth 2.7) reports **15.2 M**.
- The node's charge for state creation is several times the local figure.

Two forge broadcasts ran out of gas and cost about 0.0000085 ETH:
- `0x9b1b300e…61e9`: limit 2,911,642.
- `0x6485843d…aaeb`: limit 5,599,312.

The same applies to a plain ETH transfer to a new account: a 21,000-gas transfer reverted (`0x6a082175…afcb`).

`tests/bridge/sepolia_stage2_deploy.py` deploys with the same constructors and uses node-side `eth_estimateGas` for every tx, with a margin and the EIP-7825 cap. All EVM test scripts now estimate with the node.

Public RPCs are load-balanced and can lag by a block. The scripts therefore keep a local nonce and wait until reads reflect the receipt's block.

## Wrap / unwrap / reconciliation (`run_capsule_fast_devnet.py` → `e2e_real_capsule.py --deployment`)

SOST side: a fresh capsule-fast devnet. The boundary checks ran again:
- #299 rejects the capsule tx with R14.
- #300 accepts the same signed bytes.
- A real reorg of a bridge deposit makes the relayer pre-flight and the observers refuse the stale statement.

| Step | Result |
|---|---|
| deposit 100 SOST + `WSOST:<eth recipient>` capsule, signed offline with an encrypted v2 wallet | PASS |
| PENDING before 30 confirmations, observers refuse | PASS |
| 2-of-3 observer attestations from the real node; relayer pre-flight canonical | PASS |
| wrong recipient with valid signatures → mint reverts; stale block hash → pre-flight refuses | PASS |
| **mint 100 wSOST on Sepolia** (`0x7cfe9ab7…d63a`, gas 609,281) | PASS |
| duplicate mint reverts | PASS |
| reconciliation BALANCED after wrap | PASS |
| **burn 40 wSOST on Sepolia** (`0xb9d8976e…6ef9`, gas 609,235) | burn executed; the in-line `totalSupply()==60` check read a lagging RPC backend and reported FAIL (fixed: reads now wait for the receipt's block) |
| release 40 SOST − 0.001 fee allowance, built watch-only, signed offline by the vault wallet, journal blocks a second release | PASS |
| **final reconciliation** | **BALANCED** |

That run: 32/33. The only FAIL is the stale read described above. The final state proves the burn: totalSupply 60, totalBurned 40, burnNonce 1.

Final accounting (the "gross" and "backing" figures are different numbers and are reported separately):

| | stocks | SOST / wSOST |
|---|---|---|
| A confirmed deposits | 10,000,000,000 | 100 |
| C minted | 10,000,000,000 | 100 |
| D burned | 4,000,000,000 | 40 |
| F completed releases (to the user, net of the fee allowance) | 3,999,900,000 | 39.999 |
| **G gross vault UTXO balance** | 6,000,097,050 | **60.00097050** |
| **owed = economic backing required** (supply + awaiting releases + unminted deposits) | 6,000,000,000 | **60** |
| surplus = unused part of the 0.001 release-fee allowance (the vault paid a 0.0000295 network fee) | 97,050 | 0.00097050 |
| **H wSOST totalSupply** (read on chain afterwards: minted 100, burned 40, burnNonce 1, mintPaused false) | 6,000,000,000 | **60** |

The CRITICAL drill (an unbacked mint by two compromised observers → mint pause) was **not** run on the shared Sepolia contract, because it would leave permanent unbacked supply and a paused mint. It passes on Anvil (CAPSULE_FAST_DEVNET.md).

## Atomic swap: SOST devnet HTLC ↔ wSOST AtomicSwapHTLCv2 on Sepolia (`e2e_swap_sost_wsost.py --deployment`)

The roles:
- Bob (the deployer) holds the bridge-minted wSOST from the wrap above.
- Alice is a fresh EVM test key, funded with 0.0005 test ETH for gas.
- The SOST side is a fresh capsule-fast devnet.

Final run: **28/28 PASS**.

Claim path:
- Alice locks 10 SOST. Bob verifies the lock with `gethtlcstatus`, then locks 9.95 wSOST on Sepolia with the same hashlock.
- Alice claims on Sepolia, which reveals the secret. Bob claims the SOST with it (+9.999).
- The node rejects a wrong preimage (R21), a claim by the wrong key (S2) and a replay (S1).

Refund path:
- Each side's early refund is rejected: SOST with R24 (`spend_height 236 < refund_height 293`), and Sepolia with `NOT_YET`.
- Each side then refunds after its timeout.
- The HTLC escrow ends empty.

After every phase:
- The Bridge Vault, wSOST totalSupply, totalMinted, totalBurned, burnNonce and mintPaused are **unchanged**.
- The Gold Reserve and the QuarantineVault hold 0 Mock XAUT, 0 Mock PAXG and 0 ETH.

The swap does **not** mint wSOST, does **not** burn native SOST, does **not** touch the Bridge Vault, and does **not** modify the GoldReserveVault. It only exchanges assets that already exist.

The previous run (`sepolia/run-swap-run2-timing-fail.log`) had one test-timing FAIL:
- The refund height was set 12 blocks ahead.
- The fast devnet passed it while the Sepolia transactions were confirming.
- The "early" refund reached the node at tip 130 with refund_height 129, so accepting it was correct.

The test now checks the early refund right after the lock, with a 60-block margin on Sepolia.

## Gas measured on Sepolia

| Operation | Gas used |
|---|---|
| WSOST deployment | 15,095,931 |
| QuarantineVault deployment | 9,760,465 |
| GoldReserveVault deployment | 13,907,788 |
| AtomicSwapHTLCv2 deployment | 9,742,661 |
| mint (wrap 100, 2 signatures) | 609,281 |
| burn (unwrap 40) | 609,235 |
| approve (wSOST → HTLC) | 128,082 – 128,094 |
| swap fund (lockERC20) | 928,020 – 928,056 |
| swap claim (claimERC20) | 69,288 – 162,937 (the higher figure is a first claim by a fresh account) |
| swap refund (refundERC20) | 64,308 |
| ETH transfer to a new account | 204,600 |

Sepolia ETH:
- Start: 0.05.
- Deployer end: 0.049435481593400456 (nonce 20).
- Total out: 0.000564518 ETH. Of that, 0.0005 was sent to the test counterparty, which still holds 0.000499768. Gas paid by the deployer: about 0.0000645 ETH.
- The effective gas price was about 0.001 gwei. At mainnet gas prices the same gas would cost orders of magnitude more; mainnet cost needs its own estimate.

## Still open (unchanged)

- Deep-fork P2P sync (CAPSULE_FAST_DEVNET.md): OPEN.
- `buildtx` cannot see mempool spends: OPEN (safe RBF reject).
- Native multisig for the Bridge Vault: design only, NOT AUTHORIZED.
- External review before any mainnet recommendation.

MAINNET_RECOMMENDATION: **DO NOT DEPLOY**.
