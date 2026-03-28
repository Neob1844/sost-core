# SOST Secrets Security Guide

**Author:** NeoB
**Date:** 2026-03-28
**Classification:** INTERNAL — do not publish

---

## Rule #1: NEVER leave private keys in plaintext on disk

Private keys must be encrypted at rest. The only time a key should exist in plaintext is during active use, in a temporary directory that is destroyed immediately after.

---

## Current Secret Files

| File | Contains | Location | Format |
|------|----------|----------|--------|
| secrets/founder_v2.json | Founder wallet (pre-regenesis) | WSL only | JSON plaintext |
| secrets/gold_vault_v2.json | Gold Vault wallet (pre-regenesis) | WSL only | JSON plaintext |
| secrets/popc_pool_v2.json | PoPC Pool wallet (pre-regenesis) | WSL only | JSON plaintext |
| secrets/regenesis/miner.json | Active miner wallet | WSL only | JSON plaintext |
| secrets/regenesis/gold_vault.json | **ACTIVE Gold Vault private key** | WSL only | JSON plaintext |
| secrets/regenesis/popc_pool.json | **ACTIVE PoPC Pool private key** | WSL only | JSON plaintext |

**CRITICAL:** `gold_vault.json` and `popc_pool.json` control the constitutional treasury addresses. Loss or compromise of these keys is catastrophic.

---

## Step 1: Encrypt All Secrets (DO THIS NOW)

```bash
bash scripts/encrypt_secrets.sh
```

This will:
1. Ask for a strong password (min 8 chars)
2. Encrypt each .json file with AES-256-CBC + PBKDF2 (100,000 iterations)
3. Verify the encryption works (decrypt test)
4. Destroy the plaintext originals with `shred` (3-pass overwrite)

After encryption, only `.json.enc` files remain. The plaintext is gone.

## Step 2: When You Need the Keys

```bash
bash scripts/decrypt_secrets.sh                  # decrypt to /tmp/sost_secrets/
bash scripts/decrypt_secrets.sh --auto-cleanup   # auto-destroy after 5 minutes
```

## Step 3: Backup to Encrypted USB (Rule 3-2-1)

### Create Encrypted USB

```bash
# 1. Insert USB drive (appears as /dev/sdX — verify with lsblk)
# 2. Format with LUKS encryption
sudo cryptsetup luksFormat /dev/sdX1
# Enter a DIFFERENT password than the .enc files (defense in depth)

# 3. Open and mount
sudo cryptsetup open /dev/sdX1 sost_backup
sudo mkfs.ext4 /dev/mapper/sost_backup
sudo mount /dev/mapper/sost_backup /mnt/sost_backup

# 4. Copy encrypted secrets
sudo cp ~/SOST/secrets/*.enc /mnt/sost_backup/
sudo cp ~/SOST/secrets/regenesis/*.enc /mnt/sost_backup/

# 5. Unmount and close
sudo umount /mnt/sost_backup
sudo cryptsetup close sost_backup
```

### Rule 3-2-1 Backup Strategy

| Copy | Location | Medium | Protection |
|------|----------|--------|------------|
| 1 | WSL (PC principal) | SSD | AES-256-CBC .enc files |
| 2 | USB #1 (en casa) | USB drive | LUKS + AES-256-CBC |
| 3 | USB #2 (ubicación remota) | USB drive | LUKS + AES-256-CBC |

**Double encryption:** Each USB has LUKS disk encryption + the files themselves are AES encrypted. An attacker would need BOTH passwords.

---

## Step 4: Recovery Procedure

```bash
# 1. Connect USB
sudo cryptsetup open /dev/sdX1 sost_backup
sudo mount /dev/mapper/sost_backup /mnt/sost_backup

# 2. Copy encrypted files back
cp /mnt/sost_backup/*.enc ~/SOST/secrets/
cp /mnt/sost_backup/*.enc ~/SOST/secrets/regenesis/

# 3. Decrypt
bash scripts/decrypt_secrets.sh

# 4. Use the keys (import into wallet, sign transactions, etc.)

# 5. When done, destroy temporary plaintext
shred -vfz /tmp/sost_secrets/*.json && rm -rf /tmp/sost_secrets/

# 6. Unmount USB
sudo umount /mnt/sost_backup
sudo cryptsetup close sost_backup
```

---

## Multisig Plan (Post Height 2000)

### Timeline
- Current height: ~1805
- Multisig activation: height 2000
- Blocks remaining: ~195
- Time remaining: ~195 × 10 min = ~32.5 hours ≈ 1.4 days
- **Estimated activation: ~March 29, 2026**

### Procedure for Gold Vault Multisig Migration

1. **Generate 3 keypairs:**
   ```bash
   # Key 1: WSL (this machine)
   ./sost-cli getnewaddress gold_vault_multisig_1

   # Key 2: On air-gapped USB (different machine)
   ./sost-cli getnewaddress gold_vault_multisig_2

   # Key 3: Paper wallet or separate device
   ./sost-cli getnewaddress gold_vault_multisig_3
   ```

2. **Create 2-of-3 multisig address:**
   ```bash
   ./sost-cli createmultisig 2 '["pubkey1","pubkey2","pubkey3"]'
   # Returns: sost3... address + redeemScript
   ```

3. **Migrate Gold Vault funds:**
   - Create TX from current Gold Vault (sost11a9c...) to new multisig (sost3...)
   - Sign with current single key
   - Broadcast

4. **Update miner configuration:**
   - Change the Gold Vault output address in the miner to the new sost3... address
   - This requires a code change in params.h → hard fork

5. **Same process for PoPC Pool**

### Security After Multisig
- To move Gold Vault funds: need 2 of 3 keys, signed on 2 different devices
- Single key compromise = no theft possible
- Lost key = still have 2 remaining keys (can move funds and generate new set)

---

## What NEVER to Do

- ❌ Never email private keys
- ❌ Never paste keys in chat/messaging apps
- ❌ Never store keys in cloud storage (Google Drive, Dropbox, etc.)
- ❌ Never commit keys to any git repository
- ❌ Never leave plaintext keys on VPS
- ❌ Never use the same password for LUKS and .enc files
- ❌ Never share the encryption password digitally

---

## Document History
- 2026-03-28: Initial version — NeoB
