# Feature Audit — March 2026

**Date:** 2026-03-25
**22/22 CTest targets pass**

## Feature Tracking Matrix

| # | Feature | Code | Tests | Web-Sec | Whitepaper | README | BTCTalk | CLAUDE.md |
|---|---------|------|-------|---------|------------|--------|---------|-----------|
| 1 | AES-256-GCM wallet encryption | wallet.cpp | chunk1/2 | Y | Y | Y | Y | Y |
| 2 | secp256k1 + LOW-S | tx_signer.cpp | test_tx_signer | Y | Y | Y | Y | Y |
| 3 | HD Wallet BIP39 | hd_wallet.cpp | test_hd_wallet | Y | Y | Y | Y | Y |
| 4 | SOST-PSBT offline signing | psbt.cpp | test_psbt | Y | Y | Y | Y | Y |
| 5 | Multisig OP_CHECKMULTISIG | script.cpp | test_multisig | Y | Y | Y | Y | Y |
| 6 | Trusted address book | addressbook.cpp | test_addressbook | Y | Y | Y | Y | Y |
| 7 | Treasury safety profile | wallet_policy.cpp | test_wallet_policy | Y | Y | Y | Y | Y |
| 8 | RBF replace-by-fee | mempool.cpp | test_rbf | Y | Y | Y | Y | Y |
| 9 | CPFP child-pays-for-parent | mempool.cpp | test_cpfp | Y | Y | Y | Y | Y |
| 10 | ConvergenceX PoW | convergencex.cpp | test_transcript_v2 | Y | Y | Y | Y | Y |
| 11 | cASERT V2 (24h/12.5%) | casert.cpp | test_casert | Y | Y | Y | Y | Y |
| 12 | Capsule Protocol v1 | capsule.cpp | test_capsule_codec | Y | Y | Y | Y | Y |
| 13 | P2P encryption X25519 | sost-node.cpp | — | Y | Y | Y | Y | Y |
| 14 | P2P ban system | node.cpp | — | Y | Y | Y | Y | Y |
| 15 | RPC auth | sost-node.cpp | — | Y | Y | Y | Y | Y |
| 16 | Coinbase maturity 1000 | params.h | — | Y | Y | Y | Y | Y |
| 17 | Checkpoints + reorg 500 | checkpoints.cpp | test_checkpoints | Y | Y | Y | Y | Y |
| 18 | Dynamic fee calculation | sost-cli.cpp | — | Y | Y | Y | Y | Y |
| 19 | Auth gateway TOTP | auth/gateway.py | auth/test_auth | — | — | — | — | — |
| 20 | Emission smooth exponential | emission.cpp | — | Y | Y | Y | Y | Y |
| 21 | UTXO set + reorg | utxo_set.cpp | test_utxo_set | — | Y | Y | Y | — |
| 22 | Merkle tree | merkle.cpp | test_merkle_block | — | Y | — | Y | Y |
| 23 | Build hardening (6 flags) | CMakeLists.txt | — | Y | — | Y | Y | Y |

## Gaps Identified and Fixed (This Audit)

1. **README:** Added HD Wallet, PSBT, Multisig, Address Book, Treasury Policy, RBF, CPFP, Build Hardening, Capsule Protocol, cASERT V2 to Security Status table
2. **BTCTalk:** Updated cASERT to V2 parameters, added Capsule Protocol, fixed test count (22/22)
3. **Whitepaper:** Added Network Security Layer (P2P encryption, ban system, build hardening), Capsule Protocol v1 section
4. **Website sost-security.html:** Added cASERT V1/V2 parameter comparison table
5. **Auth gateway TOTP:** Intentionally not in public docs (internal operational tool)

## Web Wallet Feature Checklist

| Feature | Implemented | Tab/Section |
|---------|------------|-------------|
| Dashboard | Y | view-dashboard |
| Send | Y | view-send |
| Receive | Y | view-receive |
| Generate | Y | view-generate |
| Import | Y | view-import |
| Backup | Y | view-backup |
| Address Book | Y | view-addressbook |
| Security Guide (score) | Y | view-secguide |
| PSBT | Y | view-psbt |
| Multisig | Y | view-multisig |
| 2FA (TOTP) | Y | view-totp |
| Settings (treasury policy) | Y | view-settings |
| Pre-send confirmation | Y | in send flow |
| First-time send warning | Y | in send flow |
| Auto-lock | Y | in settings |
