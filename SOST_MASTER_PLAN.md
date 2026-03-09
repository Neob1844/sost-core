# SOST Protocol — Master Plan & Handoff Document
## CTO Briefing — March 5, 2026

---

## 1. CURRENT STATE (what works today)

### Infrastructure
- **VPS:** Strato VC 2-4, Ubuntu 24.04, IP `212.132.108.244`, 4GB RAM + 4GB swap, 120GB disk
- **Node:** sost-node v0.3.2 running as systemd service, auto-restart, 24/7
- **Explorer:** `https://explorer.sostcore.com` — live, SSL, reads blockchain data in real-time
- **P2P:** port 19333 open, tested between local PC and VPS, version handshake + block sync works
- **Website:** `sostcore.com` — already deployed on Strato hosting
- **Mining:** works from local PC via RPC to local node, blocks propagate to VPS via P2P

### Security (implemented today)
- SSH: key-only authentication (ed25519), password login disabled
- Firewall: UFW active — ports 22, 80, 443, 19333 only
- Fail2ban: active, blocks brute force
- RPC: strong credentials (`NeoB_1_248` / long pass), NOT exposed in explorer HTML
- Explorer: read-only RPC calls without authentication, no credentials visible to public
- Nginx: `limit_except POST OPTIONS { deny all; }` blocks GET scanners on /rpc
- Git: wallet.json purged from history with `git filter-repo`, `.gitignore` updated

### Blockchain
- Genesis: 2026-03-13 00:00:00 UTC
- Current height: ~777 blocks
- Emission: 7.8510 SOST per block, 50/25/25 split (miner/gold/popc)
- cASERT: L1-L5 with thresholds 5/20/50/75 (matches params.h)

### Code Repository
- GitHub: `github.com/Neob1844/sost-core` (PRIVATE)
- Clean: no private keys, no binaries, no wallet files in repo/history

---

## 2. CRITICAL: REGENESIS (must do before public launch)

### Why
Private keys for the 3 constitutional addresses (founder, gold vault, PoPC pool) were exposed in a chat session. Although the repo is private and the network has no external participants, these keys must be considered compromised.

### New Constitutional Wallets (already created, stored offline)
- **Founder/Miner V2:** `sost13a22c277b5d5cbdc17ecc6c7bc33a9755b88d429`
- **Gold Vault V2:** `sost1505a886a372a34e0044e3953ea2c8c0f0d7a4724`
- **PoPC Pool V2:** `sost144cc82d3c711b5a9322640c66b94a520497ac40d`
- Wallet files: `~/SOST/secrets/` (chmod 600, NOT in git)
- Backup: `C:\Users\ferna\Desktop\SOST_SECRETS_BACKUP\` → must be moved to USB

### Regenesis Steps
1. Update `include/sost/params.h` with the 3 new V2 addresses
2. Optionally update `GENESIS_TIME` to new date (e.g., launch day)
3. Generate new `genesis_block.json` (using genesis generation tool/script)
4. Delete old `chain.json` on all machines (local + VPS)
5. Recompile `sost-node`, `sost-miner`, `sost-cli` (local + VPS)
6. Start fresh chain from block 0
7. Verify: coinbase splits go to V2 addresses
8. Update explorer on VPS with new chain data
9. Tag release: `v1.0.0-mainnet`

### Files to modify
- `include/sost/params.h` — ADDR_MINER_FOUNDER, ADDR_GOLD_VAULT, ADDR_POPC_POOL
- `genesis_block.json` — regenerate
- `chain.json` — delete and start fresh
- VPS: `/opt/sost/` — recompile and redeploy
- VPS: `/var/www/explorer/index.html` — update if addresses are hardcoded in JS

---

## 3. SECURITY HARDENING (beyond what's done)

### Wallet Security
- [ ] **Wallet encryption:** AES-256-GCM + scrypt/argon2 key derivation from passphrase
- [ ] **Separate hot/cold wallets:** node uses hot wallet (1-2 keys), institutional keys stay offline
- [ ] **Watch-only mode:** node can track addresses without holding private keys
- [ ] **Never store institutional keys on VPS** — only hot wallet for operations

### RPC Security
- [ ] **Rate limiting in nginx:** prevent abuse of public RPC endpoint
```nginx
limit_req_zone $binary_remote_addr zone=rpc:10m rate=10r/s;
location /rpc {
    limit_req zone=rpc burst=20 nodelay;
    # ... rest of config
}
```
- [ ] **Separate read-only vs admin RPC:** read methods public, write methods require auth
- [ ] **Bind RPC to localhost only:** already done (127.0.0.1:18232), nginx proxies it

### P2P Security
- [ ] **DoS protection / peer banning:** rate-limit connections per IP, ban invalid block/tx senders
- [ ] **Misbehavior scoring:** track bad peer behavior, auto-disconnect at threshold
- [ ] **Max peers limit:** cap inbound connections (e.g., 125 like Bitcoin)
- [x] **P2P encryption (default on):** X25519 + ChaCha20-Poly1305 (Noise-lite protocol)
  - Add `--p2p-enc off|on|required` flag
  - EKEY handshake → derive shared secret → encrypt all messages
  - File to modify: `src/sost-node.cpp` (p2p_send/p2p_recv + handle_peer)

### Chain Security
- [ ] **Checkpoints:** hardcode known block hashes at key heights to prevent long-range attacks
- [ ] **Reorg depth limit:** reject reorganizations deeper than 100 blocks
- [ ] **PoW verification on submitblock:** already implemented, verify it's airtight
- [ ] **write_exact() fix:** replace `write()` with loop-based `write_exact()` in P2P send (prevents partial writes on large BLCK messages). File: `src/sost-node.cpp`

### Infrastructure Security
- [ ] **Regular backups:** automated chain.json + wallet backup to secure location
- [ ] **Log monitoring:** health check script (height, peers, mempool) with alerts
- [ ] **System updates:** `apt upgrade` schedule
- [ ] **VPS snapshots:** periodic Strato snapshots before major changes

---

## 4. P2P NETWORK HARDENING

### Seeds (critical for launch)
- [ ] **Hardcoded seeds:** add VPS IP `212.132.108.244:19333` as default seed in `src/sost-node.cpp`
- [ ] **DNS seed:** create `seed.sostcore.com` A record pointing to VPS IP
- [ ] **Multiple seeds:** add 1-2 more VPS nodes for redundancy (cheap: $5/month each)

### Sync Testing Checklist (must pass before launch)
1. [ ] Fresh node connects to seed → handshake OK
2. [ ] Fresh node completes IBD (full chain download) → reaches tip
3. [ ] Remote miner mines block → all peers receive within seconds
4. [ ] TX created on one node → appears in mempool of other nodes (relay)
5. [ ] Invalid block/TX sent → peer gets penalized/banned

### P2P Protocol Improvements
- [ ] **getaddr/addr messages:** peer discovery beyond hardcoded seeds
- [ ] **Peer rotation:** periodically try new peers, don't rely on one connection
- [ ] **Connection timeout tuning:** current 30s recv timeout may need adjustment

---

## 5. GITHUB & BRANDING

### Organization Migration
- [ ] Create GitHub organization: `SOST-Protocol`
- [ ] Transfer `sost-core` repo to organization
- [ ] Result: `github.com/SOST-Protocol/sost-core` (old URLs auto-redirect)
- [ ] Add organization profile, logo, description
- [ ] Free for public repos

### Repository Cleanup
- [ ] Fix README versions: node v0.3.2, miner v0.5, cli v1.3, explorer v4.2
- [ ] Fix Quick Start: add `--rpc-user`/`--rpc-pass`, correct CLI commands
- [ ] Update Security Status section
- [ ] Add CONTRIBUTING.md, SECURITY.md (vulnerability disclosure)
- [ ] Tag release `v1.0.0` with compiled binaries + SHA256 hashes
- [ ] Add GitHub Actions CI (optional: auto-build on push)

### Commit Hygiene
- [ ] Use `Neob` as author (not real name) in git config
- [ ] Use GitHub noreply email: `Neob1844@users.noreply.github.com`
- [ ] Never commit secrets, wallets, binaries, or `.env` files

---

## 6. EXPLORER IMPROVEMENTS

### Current: v4.2 (functional)
- Dashboard with height, supply, balances, hashrate, difficulty
- Block detail with cASERT panel
- TX flow visualization
- Gold Reserve + PoPC charts
- Emission curve
- Chain timing

### Improvements
- [ ] **Hide USER/PASS input fields entirely** (since no auth needed for reads)
- [ ] **Auto-refresh indicator:** show last update timestamp
- [ ] **Mobile responsive testing:** verify on phone screens
- [ ] **Rich block detail:** show full decoded transactions in block view
- [ ] **Address page:** TX history (requires tx-index, Phase 3)
- [ ] **Network stats:** peer count, geographic distribution
- [ ] **Version indicator:** show node version in footer

### SSL Certificate
- ✅ Already installed (Let's Encrypt, auto-renewal via certbot timer)
- Verify: `certbot certificates`

---

## 7. WALLET ECOSYSTEM

### Phase 1 — Web Wallet (`wallet.sostcore.com`)
- Browser-based, no download required
- Key generation in browser using `noble-secp256k1` JS library
- sost1 address derivation in JavaScript (RIPEMD160(SHA256(pubkey)))
- UTXO query via public RPC (getaddressinfo, listunspent)
- TX construction + client-side signing (private key never leaves browser)
- Broadcast via sendrawtransaction RPC
- Balance display + QR code for receive address
- Export/import private keys (encrypted download)
- **2FA for transactions:** require TOTP code (Google Authenticator / Authy) before signing
- Hosted on VPS as static HTML (like explorer), cost: 0€

### Phase 2 — Desktop Wallet (Electrum-style)
- Electron or Qt framework, cross-platform (Windows, macOS, Linux)
- Connects to SOST node via RPC (own node or public)
- Multi-address management (HD-style from single seed)
- TX history + CSV export for accounting
- Offline signing (create unsigned TX → sign on air-gapped machine)
- **2FA integration:** TOTP required before broadcast
- Address book + labeled contacts
- Auto-update mechanism

### Phase 3 — Mobile App (`SOST Wallet` — iOS + Android)
- React Native or Flutter (single codebase, both platforms)
- Full wallet: generate keys, send/receive, view balance, TX history
- QR code scanner for receiving addresses
- Push notifications for incoming transactions
- Biometric auth (fingerprint / face) + PIN + optional TOTP 2FA
- Connect to public RPC or user's own node
- Publish on App Store + Google Play
- Cost: development time only (publishing fees ~$25 Google, $99/year Apple)

### Phase 4 — Browser Extension Wallet
- Chrome + Firefox extension (Manifest V3)
- Like MetaMask but for SOST (sost1 addresses, UTXO model)
- Encrypted keystore in browser storage
- Website integration API: `window.sost.requestPayment()` for merchants
- Transaction approval popup (user confirms before signing)
- One-click payments on websites that accept SOST

### Phase 5 — MetaMask Snap
- SOST is UTXO/Bitcoin-like with sost1 addresses → NOT directly MetaMask compatible
- MetaMask Snap: custom plugin that manages sost1 keys, signs UTXO TXs, talks to RPC
- Gives access to millions of existing MetaMask users
- Only pursue when SOST has user traction and community demand
- Development: Snap SDK, key derivation, TX signing, RPC bridge
- Submit to MetaMask Snap Directory for public listing

---

## 7b. TWO-FACTOR AUTHENTICATION (2FA)

### Strategy
SOST uses UTXO model (like Bitcoin) — there is no "account" on-chain to protect with 2FA. The 2FA protects the **wallet application**, not the blockchain itself. This is the same approach Bitcoin wallets use.

### Level 1 — Wallet Application 2FA (priority, implement with web wallet)
- **TOTP (Time-based One-Time Password):** compatible with Google Authenticator, Authy, Microsoft Authenticator
- User sets up 2FA when creating wallet → scans QR code with authenticator app
- Before signing any transaction, wallet requires 6-digit TOTP code
- Implementation: `otpauth://` URI generation + TOTP verification in JavaScript (library: `otplib`)
- Secret stored encrypted in wallet file, never on server
- Recovery codes generated at setup (offline backup)

### Level 2 — Passphrase + 2FA (cold storage protection)
- Wallet file encrypted with AES-256-GCM + scrypt key derivation
- To open wallet: passphrase (something you know) + 2FA code (something you have)
- This is equivalent to "2FA" without needing protocol changes

### Level 3 — On-chain Multisig (future, requires protocol change)
- New output type: `OUT_MULTISIG_2OF3`
- Requires 2 of 3 signatures to spend (e.g., user key + phone key + backup key)
- True on-chain security — even if one key is stolen, funds are safe
- Significant development effort, target for Phase 4+
- Alternative: MuSig2 (Schnorr-based, more compact)

### Level 4 — Hardware Security (long-term)
- Ledger/Trezor app for SOST
- Private key never leaves hardware device
- Physical button press required to sign
- Combined with TOTP for maximum security

### What NOT to do
- Do NOT build a custom SMS-based 2FA (expensive, insecure, SIM-swap attacks)
- Do NOT require email verification (adds server dependency, privacy concern)
- Use standard TOTP — it's free, offline, and battle-tested

---

## 7c. ENCRYPTION EVERYWHERE (maximize security)

### Principle: encrypt everything that can be encrypted

| Layer | What | How | Status |
|-------|------|-----|--------|
| Wallet at rest | wallet.json private keys | AES-256-GCM + scrypt/argon2 + passphrase | TODO |
| Wallet backup | exported wallet files | AES-256-GCM encrypted ZIP / GPG | TODO |
| P2P transport | all peer-to-peer messages | X25519 + ChaCha20-Poly1305 (Noise-lite) | TODO |
| RPC transport | browser ↔ node | HTTPS/TLS (already via nginx + certbot) | ✅ DONE |
| Chain data at rest | chain.json on VPS disk | Full-disk encryption (LUKS) or encrypted partition | OPTIONAL |
| SSH transport | admin ↔ VPS | SSH ed25519 key-only (already done) | ✅ DONE |
| Git transport | push/pull to GitHub | SSH or HTTPS with PAT | ✅ DONE |
| Backup transport | wallet files to USB | Encrypted USB (BitLocker/LUKS) or GPG | TODO |
| Seed phrases | wallet recovery words | Never stored digitally — paper/metal only | POLICY |

### Wallet Encryption (AES-256-GCM) — Implementation Plan
Current wallet.json stores privkeys in plaintext:
```json
{"privkey": "2de3ce69..."}  ← UNACCEPTABLE for production
```
Target format:
```json
{
  "version": 2,
  "encryption": "aes-256-gcm",
  "kdf": "scrypt",
  "kdf_params": {"N": 262144, "r": 8, "p": 1},
  "salt": "<hex>",
  "iv": "<hex>",
  "ciphertext": "<hex>",
  "tag": "<hex>"
}
```
- User provides passphrase → scrypt derives 256-bit key → AES-256-GCM encrypts all key material
- To unlock: passphrase + scrypt → decrypt → keys in memory only (never written to disk decrypted)
- Files to modify: `src/wallet.cpp`, `include/sost/wallet.h`
- Dependencies: OpenSSL (already linked for libsecp256k1)

### P2P Encryption (X25519 + ChaCha20-Poly1305) — Implementation Plan
Current P2P sends all messages in plaintext (VERS, BLCK, TXXX visible to anyone sniffing):
```
[MAGIC:4][CMD:4][LEN:4][PAYLOAD:N]  ← plaintext
```
Target: encrypted transport after handshake:
```
Handshake: EKEY(32 bytes pubkey) → X25519 shared secret → HKDF → session keys
Transport: [MAGIC:4]["ENC1":4][LEN:4][CTR:8][CIPHERTEXT+TAG:N+16]
```
- Flag: `--p2p-enc off|on|required`
- Backward compatible: unencrypted peers still work if mode=`on` (not `required`)
- File to modify: `src/sost-node.cpp` (p2p_send, p2p_recv, handle_peer)
- Dependencies: OpenSSL EVP (X25519, HKDF-SHA256, ChaCha20-Poly1305)

### RPC Encryption
- Already done: HTTPS via nginx + Let's Encrypt ✅
- Internal RPC (127.0.0.1:18232) is localhost-only, no encryption needed
- External access only through nginx HTTPS proxy

---

## 7d. PAYLOAD EXPANSION (consensus change — do with regenesis)

### Current limitation
- `payload_len` is `uint8_t` → max 255 bytes (rule R13 in tx_validation.cpp)
- Policy limit: `MAX_PAYLOAD_STANDARD` (likely smaller)

### Proposed change: expand to 512 bytes
- Change `payload_len` from `uint8_t` to `uint16_t` in serialization format
- Update R13 consensus rule: `if (out.payload.size() > 512)`
- Update `MAX_PAYLOAD_STANDARD` policy constant
- Update `EstimateTxSerializedSize()` to account for 2-byte length field
- Update `CompactSizeLen` usage if payload_len uses CompactSize encoding

### Files to modify
- `include/sost/transaction.h` — TxOutput struct, payload_len type
- `src/tx_validation.cpp` — R13 rule (255 → 512)
- `include/sost/tx_validation.h` — MAX_PAYLOAD_STANDARD constant
- `src/transaction.cpp` — Serialize/Deserialize (payload_len encoding)
- Whitepaper — update payload specification

### Why 512 bytes
- 255 is tight for future capsule data, metadata, or OP_RETURN-style messages
- 512 gives 2x headroom without bloating transactions significantly
- Bitcoin OP_RETURN: 80 bytes. Ethereum calldata: unlimited but costly. 512 is generous for a UTXO chain.
- Can always increase later with another consensus upgrade, but better to do it now with regenesis

---

## 8. NODE & MINER IMPROVEMENTS

### High Priority
- [ ] **estimatefee RPC:** estimate optimal fee based on recent blocks
- [ ] **TX index (txindex):** full transaction index for historical lookups by txid
- [ ] **getblock verbose mode:** return full decoded transactions in block response
- [ ] **Pruning mode:** option to discard old block data, keep UTXO set + headers

### Mining
- [ ] **Mining guide (MINING.md):** step-by-step for external miners
- [ ] **Pool protocol (Stratum):** for pool mining support (post-launch)
- [ ] **VPS mining note:** 4GB RAM VPS cannot mine (needs 4GB scratchpad + OS), need 8GB+ or swap

---

## 9. LAUNCH CONTENT

### Announcements
- [ ] **BitcoinTalk [ANN] thread:** specs, links, mining guide, explorer
- [ ] **Reddit posts:** r/CryptoCurrency, r/CryptoMining, r/altcoin
- [ ] **Whitepaper PDF:** host on `sostcore.com/whitepaper.pdf` and GitHub releases

### Exchange Listings (post-launch)
- [ ] FreiExchange (free, PoW-focused)
- [ ] SafeTrade (low-cost, community)
- [ ] Exbitron / Finexbox (secondary)
- [ ] CoinGecko / CoinMarketCap tracking (once listed on 1+ exchange)

---

## 10. LONG-TERM VISION

### Gold Reserve Infrastructure (Phase 5)
- Custody partner: XAUT (Tether Gold) vs PAXG (Paxos Gold)
- Automated vault SOST → gold token conversion
- On-chain audit trail
- Reserve dashboard in explorer
- PoPC activation and distribution

### Future Development
- Mobile wallet (React Native / Flutter)
- Hardware wallet support (Ledger/Trezor app)
- Multi-metal tokenization (silver, platinum, palladium)
- Atomic swaps with BTC (HTLC)
- Lightning-style L2 payment channels

---

## 11. INFRASTRUCTURE MAP

```
LOCAL PC (WSL)
├── ~/SOST/sostcore/sost-core/    — development repo
├── ~/SOST/secrets/                — institutional wallets V2 (NEVER in git)
├── sost-node                      — local node (connects to VPS P2P)
├── sost-miner                     — mines locally, submits to local node
└── SSH key: C:\Users\ferna\.ssh\id_ed25519

VPS (212.132.108.244)
├── /opt/sost/                     — compiled binaries + chain data
├── /var/www/explorer/index.html   — public explorer
├── /etc/nginx/sites-available/sost — nginx config (SSL + /rpc proxy)
├── /etc/systemd/system/sost-node.service — auto-start node
├── sost-node: port 19333 (P2P), 18232 (RPC localhost)
├── nginx: port 80 → 443 (HTTPS), /rpc → 127.0.0.1:18232
└── Certbot: auto-renewal SSL for explorer.sostcore.com

STRATO
├── sostcore.com — main website (Strato hosting)
├── explorer.sostcore.com — DNS A record → 212.132.108.244
└── SFTP: su978586 @ 5019225769.ssh.w2.strato.hosting

GITHUB
└── github.com/Neob1844/sost-core (PRIVATE) → migrate to SOST-Protocol org
```

---

## 12. CREDENTIALS & ACCESS (do NOT share)

| Service | User | Notes |
|---------|------|-------|
| VPS SSH | root | key-only (id_ed25519), password disabled |
| Node RPC | NeoB_1_248 | strong pass, not in explorer HTML |
| Strato SFTP | su978586 | for explorer uploads to Strato hosting |
| GitHub | Neob1844 | use PAT for HTTPS push |

---

## 13. KNOWN ISSUES

1. **Chain desync local↔VPS:** local chain.json has 429 blocks, VPS has 776. After regenesis both start from 0 — problem goes away.
2. **VPS cannot mine:** 4GB RAM insufficient for 4GB scratchpad. Swap works but very slow. Mine from PC only, propagate via P2P.
3. **Explorer shows old data in non-incognito:** browser cache issue. Add cache-busting headers in nginx:
```nginx
location / {
    add_header Cache-Control "no-cache, must-revalidate";
    try_files $uri $uri/ /index.html;
}
```
4. **Whitepaper v3.6 says L3-L6 with 21/51/101 thresholds:** code actually uses L1-L5 with 5/20/50/75. Whitepaper needs correction to match code.

---

## 14. EXECUTION ORDER (no dates, do when ready)

### Block A — Regenesis (do first)
1. Update params.h with V2 addresses
2. Expand payload_len to uint16_t (512 bytes max) — consensus change
3. Generate new genesis
4. Recompile everything (local + VPS)
5. Start fresh chain
6. Verify explorer shows new chain
7. Mine 10+ blocks to confirm everything works

### Block B — Security & Encryption
8. Wallet encryption AES-256-GCM + scrypt (wallet.cpp)
9. Rate limiting on /rpc (nginx)
10. DoS/banning in P2P
11. write_exact() fix
12. Checkpoints + reorg limit
13. P2P encryption X25519 + ChaCha20-Poly1305 (sost-node.cpp)
14. Encrypted wallet backup export

### Block C — Network Ready
15. Hardcoded seeds in binary
16. DNS seed setup
17. Full P2P test (5-point checklist)
18. Mining guide published

### Block D — Public Launch
19. GitHub organization + repo transfer
20. README cleanup + tag v1.0.0
21. BitcoinTalk ANN + Reddit
22. Whitepaper PDF on website (corrected to match code: L1-L5, payload 512)
23. Monitor first external connections

### Block E — Post-Launch
24. Web wallet with TOTP 2FA (wallet.sostcore.com)
25. Exchange listings
26. TX index + estimatefee
27. Desktop wallet with 2FA + offline signing
28. Gold reserve infrastructure

### Block F — Growth
29. Mobile app (React Native / Flutter) — iOS + Android
30. Browser extension wallet (Chrome + Firefox)
31. MetaMask Snap (when community demands it)
32. On-chain multisig (protocol upgrade)
33. Hardware wallet support (Ledger/Trezor)

---

*SOST Protocol — Immutable by Design*
*sostcore.com*
