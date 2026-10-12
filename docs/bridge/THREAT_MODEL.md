# Threat model — wSOST bridge, Gold Reserve V2, governance (Stage 1)

Scope: the Stage 1 code on branch `feat/wsost-gold-reserve-v2` (contracts in `contracts/wsost`,
tooling in `ops/sostbridge`). Status labels: **MITIGATED** (code + test), **BOUNDED** (the risk exists
by design; caps / detection limit the damage), **ACCEPTED** (documented trust assumption),
**OPEN** (needs a later stage). Tests are named so they can be found with grep.

## Trust assumptions (stated plainly)

- Stage 1 / pilot is a **capped operator bridge**: a 2-of-3 operator quorum of observers and one
  cold single-key Bridge Vault. It is neither trustless nor decentralized.
- A threshold of observers CAN mint unbacked wSOST. The exposure cap and the daily cap bound it;
  the indexer detects it (CRITICAL) and stops new mints.
- The vault key holder CAN move native SOST out of the vault. The exposure cap bounds it; the
  indexer flags any vault spend without a release capsule as CRITICAL.
- Gold Reserve V2 guardians execute on Ethereum. SOST votes are verified off-chain; a guardian
  majority ignoring a vote is provable, not technically prevented. The contract still forbids any
  destination other than a registered successor or the fixed quarantine.
- XAUT/PAXG issuers can freeze or retire their tokens (external, ACCEPTED; rescue path exists).

## Bridge

| # | Threat | Status | Evidence |
|---|---|---|---|
| B1 | duplicate mint of one deposit | MITIGATED | `depositUsed`; `test_duplicateMint_reverts`, `test_sameDepositId_differentAmount_reverts`, py `test_duplicate_mint_rejected` |
| B2 | mint without a deposit | BOUNDED | needs ≥ threshold observers; detected: py `test_mint_without_deposit_is_critical_and_pauses` |
| B3 | amount / recipient mismatch | MITIGATED | signature over every field: `test_amountMismatch_reverts`, `test_recipientMismatch_reverts`; detected if forced: py `test_mint_amount_or_recipient_differs_from_deposit_is_critical` |
| B4 | stale attestation / stale block hash | MITIGATED | observer re-verifies; relayer `still_canonical`; `test_staleBlockHash_reverts`, py `test_reorg_after_threshold_stale_attestation_refused`, `test_stale_block_hash_forced_mint_is_flagged` |
| B5 | wrong chainId / contract / bridge version / vault | MITIGATED | EIP-712 domain + struct: `test_wrongChainId_reverts`, `test_wrongContract_replayFromOtherDeployment_reverts`, `test_wrongBridgeVersion_reverts`, `test_wrongVault_reverts` |
| B6 | one compromised observer | MITIGATED | `test_oneObserverOnly_cannotMint`, `test_nonObserverSignature_reverts` |
| B7 | two compromised observers | BOUNDED | `test_compromisedTwoObservers_canMint_butCapsBound` + CRITICAL detection |
| B8 | observer unavailable | MITIGATED | `test_unavailableObserver_twoOfThreeStillWork` |
| B9 | relayer abuse | MITIGATED | relayer has no authority: `test_relayerAlone_cannotMint` |
| B10 | signature malleability | MITIGATED | low-s / v check: `test_malleableHighS_rejected` |
| B11 | reorg before maturity (1, 2–5 blocks, disappear / reappear) | MITIGATED | py `test_one_block_reorg_removes_immature_deposit`, `test_reorg_2_to_5_blocks_deposit_reappears_once`, `test_deposit_disappears_before_maturity_then_reappears_on_branch` |
| B12 | deep reorg after mint | BOUNDED | 30 provisional confirmations; detected CRITICAL + pause: py `test_deep_reorg_after_mint_removes_deposit_critical` |
| B13 | duplicate burn / burn replay | MITIGATED | unique `burnId` per nonce; `test_burnRequiresValidSostAddress` |
| B14 | duplicate release | MITIGATED | journal before signing + chain check; detected: py `test_duplicate_release_is_critical`, `test_wrap500_unwrap200_balanced` |
| B15 | release without burn | MITIGATED (detection) | py `test_release_without_burn_is_critical`; E2E failure simulation |
| B16 | destination substitution / wrong release amount | MITIGATED (detection) | py `test_release_amount_and_destination_checked` |
| B17 | vault key theft / unexplained spend | BOUNDED | exposure cap; py `test_unexplained_vault_spend_is_critical` |
| B18 | daily cap / exposure cap exhaustion | MITIGATED | `test_dailyCap_andNextDay`, `test_exposureCap` |
| B19 | paused mint must not freeze holders | MITIGATED | `test_pauseMint_transfersAndBurnsStillWork` |
| B20 | admin parameter change without notice | MITIGATED | 2-day timelock, exact config: `test_configChange_needsTimelock`; minority threshold rejected |
| B21 | accounting deficit | MITIGATED (detection) | supply vs backing and C−D=H checks; E2E |
| B22 | float / rounding errors | MITIGATED | integer stocks, floats refused: py `test_amounts_exact`; 8 decimals on both sides |
| B23 | payments to the vault without a capsule | ACCEPTED | not mintable, warned for manual review: py `test_unattributed_payment_not_mintable` |
| B24 | fully offline release signing | OPEN | `createtx` has no capsule support today (CLI unchanged by design) |
| B25 | full REAL-chain capsule E2E on devnet | OPEN | capsules need height ≥ 7,350 in every profile; see E2E_STAGE1_RESULT.md |

## Gold Reserve V2

| # | Threat | Status | Evidence |
|---|---|---|---|
| G1 | arbitrary withdrawal | MITIGATED | no such function: `test_noArbitraryWithdrawal`, `test_quarantine_arbitraryWithdrawalBlocked` |
| G2 | arbitrary / unregistered successor | MITIGATED | `test_arbitrarySuccessor_notRegistered_rejected` |
| G3 | successor code mismatch | MITIGATED | `test_successorCodeHashMismatch_rejected`; re-checked at execution |
| G4 | destination EOA | MITIGATED | `test_destinationEOA_rejected` |
| G5 | unapproved / gated asset | MITIGATED | `test_paxgGatedOff`, `test_unregisteredAsset_rejected` |
| G6 | wrong / changed proposal | MITIGATED | `test_wrongProposal_resultForOtherHash_rejected`, `test_proposalHash_changesWithEveryMaterialField` |
| G7 | timelock bypass | MITIGATED | `test_migration_allFourKeys_pass`, `test_timelockShorterThanMinimum_rejected` |
| G8 | insufficient guardians | MITIGATED | `test_insufficientGuardians_fails`, pause/rescue thresholds |
| G9 | vote below 2/3 of the full census | MITIGATED (arithmetic) | `test_vote_7of12_fails_even_with_5of5_guardians`, `test_governancePassed_arithmetic`, impossible tallies rejected |
| G10 | forged tally submitted by guardians | ACCEPTED | off-chain verifiable (`tallyHash`, governance indexer) |
| G11 | pause moving funds | MITIGATED | `test_pause_oneGuardianFails_twoPass_movesNothing` |
| G12 | rescue to anywhere but quarantine | MITIGATED | no destination parameter: `test_rescue_onlyToQuarantine_needs4_andDelay` |
| G13 | approval reuse | MITIGATED | consumed action ids, nonces: `test_rescueApprovalCannotBeReused` |
| G14 | XAUT deprecation / freeze | MITIGATED / ACCEPTED | `test_xautDeprecation_rescueThenGovernedMigrationFromQuarantine`, `test_frozenToken_migrationRevertsCleanly` |
| G15 | guardian key loss | OPEN | guardian recovery (slow, assets cannot move) is a later-stage design |

## Governance

| # | Threat | Status | Evidence (tests/bridge/test_governance.py) |
|---|---|---|---|
| V1 | ineligible voter / Sybil after announcement | MITIGATED | census frozen, binding age: `test_census_freeze_rules`, `test_ineligible_and_malformed_and_wrong_fields_ignored` |
| V2 | vote not from the identity | MITIGATED | all inputs must spend from the identity |
| V3 | wrong proposal / snapshot / malformed | MITIGATED | same test |
| V4 | vote at snapshot or after close | MITIGATED | `test_vote_at_snapshot_or_after_close_not_counted` |
| V5 | vote change ambiguity | MITIGATED | `test_changed_vote_last_wins_history_kept`, `test_duplicate_same_vote_counted_once` |
| V6 | low-turnout capture | MITIGATED | 2/3 of the FULL census: `test_7_of_12_fails_even_if_all_voters_say_yes` |
| V7 | ABSTAIN lowering the bar | MITIGATED | `test_8_yes_4_abstain_passes_abstain_not_yes` |
| V8 | reorg around the close | MITIGATED | finality depth: `test_reorg_removing_final_vote_changes_result`, `test_finality_states` |
| V9 | one person, many identities | ACCEPTED / BOUNDED | NODE_BIND + PoW + binding age raise the cost; not proof of personhood |
| V10 | Python / Solidity proposal-hash divergence | MITIGATED | checked in the E2E against the deployed contract |
