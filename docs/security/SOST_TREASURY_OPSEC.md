# SOST Treasury Operations Security

## Context
SOST has three constitutional addresses receiving coinbase rewards:
- **Miner** (50%): sost1059d...3df33
- **Gold Vault** (25%): sost11a9c...bb4d
- **PoPC Pool** (25%): sost1d876...a30f

These addresses accumulate significant value over time. Their security is
paramount to the protocol's integrity.

## Current State

| Aspect | Status | Risk |
|--------|--------|------|
| Key storage | Single private key per address | HIGH |
| Signing | Online hot wallet | HIGH |
| Backup | Manual file copy | MEDIUM |
| Multi-party auth | NOT IMPLEMENTED | HIGH |
| Withdrawal limits | NONE | HIGH |
| Audit trail | NONE | MEDIUM |

## Recommended Architecture

### Hot / Warm / Cold Split

```
COLD (offline, air-gapped)
  └── Master treasury keys
  └── Used for: large transfers, policy changes
  └── Access: 2+ signers physically present
  └── Hardware: dedicated laptop, never connected to internet

WARM (online, restricted)
  └── Operational wallet with daily spending limit
  └── Used for: routine operations, small transfers
  └── Access: single authorized operator
  └── Hardware: hardened server, localhost RPC only

HOT (online, automated)
  └── Minimal funds for automated operations
  └── Used for: mining reward collection only
  └── Access: automated scripts
  └── Hardware: node server
```

### Operational Procedures

#### Before Any Treasury Transfer

1. Verify destination address on separate device
2. Confirm amount matches intended transfer
3. Check fee is reasonable (not abnormally high)
4. If amount > 100 SOST: require second operator review
5. If destination is new: 24h cool-down before execution
6. Log the operation: who, when, how much, where, why

#### Emergency Procedures

1. **Key compromise suspected**: Move all funds to new cold wallet immediately
2. **Node compromise**: Shut down, audit, rebuild from verified source
3. **Operator unavailable**: Secondary keyholder activates backup plan
4. **Blockchain reorg**: Wait for deep confirmation (100+ blocks)

### Backup Rotation

| Backup Type | Frequency | Storage | Retention |
|-------------|-----------|---------|-----------|
| Cold wallet file | After each key generation | 2+ physical locations | Permanent |
| Warm wallet file | Weekly | Encrypted remote backup | 90 days rolling |
| Hot wallet file | Daily | Encrypted local backup | 30 days rolling |
| Configuration | After changes | Version controlled | Permanent |

### Future: Multisig Treasury

When PSBT + multisig support is implemented:

```
Gold Vault: 2-of-3 multisig
  Key A: Founder (cold storage)
  Key B: Foundation officer (cold storage)
  Key C: Emergency backup (safe deposit)

PoPC Pool: 2-of-3 multisig
  Key A: Protocol lead (cold storage)
  Key B: Operations lead (cold storage)
  Key C: Emergency backup (safe deposit)
```

This eliminates single-point-of-failure for treasury keys.

## Honest Limitations

- **No multisig yet**: Single-key control is the current reality
- **No timelock**: Withdrawals execute immediately once signed
- **No on-chain governance**: Treasury policy is off-chain trust-based
- **Institutional grade requires**: PSBT, multisig, HSM support — all future work
