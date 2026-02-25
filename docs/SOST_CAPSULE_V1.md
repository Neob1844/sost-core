# SOST Capsule Protocol v1 (Draft)

## 0. Status

**Status:** Draft (implementation target for policy-level rollout)  
**Scope:** Optional `payload` usage for SOST transaction outputs (max 255 bytes per output)

This protocol defines a compact, deterministic way to attach:
- short notes
- off-chain document references
- structured instructions
- optional encrypted capsules

It does **not** change normal SOST transfers.

---

## 1. Objective

SOST Capsule Protocol v1 defines a standard, optional use of the transaction output `payload` field (max 255 bytes per output) to carry compact metadata and references.

The protocol is designed so that SOST remains:
- lightweight on-chain
- verifiable
- scalable
- usable for business/document workflows

A transaction may include:
- no capsule (`payload` empty), or
- one capsule payload in one output (recommended v1 policy)

---

## 2. Design Principles

### 2.1 Lightweight on-chain
Never store large files (PDF/image/audio) directly on-chain.

On-chain should contain only:
- hashes
- compact references
- small structured fields
- short notes (optional)

### 2.2 Optional privacy
Encryption is optional and only used when needed.

If no privacy is required:
- payload remains open and simple

### 2.3 Verifiable
Any off-chain document must be referenced by cryptographic hash.

The receiver verifies integrity by recomputing:
- file hash
- manifest hash (if used)

### 2.4 Deterministic binary layout
Capsule payloads use a strict binary layout:
- fixed header
- explicit lengths
- no JSON on-chain
- canonical field sizes

### 2.5 Backward-compatible behavior
Nodes that do not parse Capsule payloads may treat `payload` as opaque bytes.
Mempool policy may accept/reject unknown payloads.

Consensus remains minimal:
- only `payload <= 255 bytes` matters at consensus level (v1 recommendation)

### 2.6 Storage-neutral
SOST does not require a specific storage backend.

Off-chain storage can be:
- HTTPS (self-hosted or third-party)
- IPFS (optional)
- opaque backend ID (wallet/provider-managed)
- future storage backends

---

## 3. Architecture Model (Important)

## 3.1 SOST role: settlement + proof layer
SOST is used to:
- transfer value (SOST)
- anchor cryptographic proofs (hashes)
- carry compact metadata (payload capsule)

SOST is **not** a file hosting network.

## 3.2 Off-chain storage role
Large data lives off-chain:
- contracts
- invoices
- images
- audio
- archives
- manifests

The chain only proves:
- what was referenced
- when it was referenced
- whether it matches the expected hash

## 3.3 Responsibility model (costs and hosting)
**SOST network does not pay for user storage.**

The user (or service/provider) pays for:
- file hosting
- pinning/retention
- bandwidth
- backups

This keeps SOST lightweight and sustainable.

---

## 4. Operational Modes (User Experience)

## 4.1 Normal transfer (no document)
A user may send SOST without any payload.

Result:
- no capsule
- no encryption
- no off-chain upload
- normal fee only

## 4.2 Transfer + capsule (open)
A user sends SOST and adds:
- a short note, or
- a document reference

Wallet flow (automatic):
1. build capsule
2. estimate fee
3. sign tx
4. broadcast tx

## 4.3 Transfer + capsule (sealed/private)
A user sends SOST and attaches a private note or encrypted document reference.

Wallet flow (automatic):
1. generate document key (CEK)
2. encrypt file (or short note)
3. upload encrypted blob + manifest off-chain
4. compute hashes
5. build capsule payload
6. sign tx
7. broadcast tx

The receiver later:
1. sees tx
2. downloads off-chain content
3. verifies hashes
4. decrypts using their private key (via envelope in manifest)

---

## 5. Limits and Scope (v1)

## 5.1 Consensus limit
- `payload` per output: **0..255 bytes** (consensus)

## 5.2 Recommended v1 usage
- `OPEN_NOTE_INLINE`: up to **80 bytes** (policy recommendation)
- `SEALED_NOTE_INLINE`: small encrypted notes only
- `DOC_REF_*`: compact reference only (no file content)
- `TEMPLATE_FIELDS_*`: compact structured fields only

## 5.3 Off-chain required for large files
PDFs, images, audio, long documents:
- must be stored off-chain
- on-chain stores only hashes + locator

---

## 6. Enums (v1)

## 6.1 `capsule_type` (u8)
- `0x00` = NONE
- `0x01` = OPEN_NOTE_INLINE
- `0x02` = SEALED_NOTE_INLINE
- `0x03` = DOC_REF_OPEN
- `0x04` = DOC_REF_SEALED
- `0x05` = TEMPLATE_FIELDS_OPEN
- `0x06` = TEMPLATE_FIELDS_SEALED
- `0x07` = CERT_INSTRUCTION
- `0x08..0x7F` = reserved (SOST)
- `0x80..0xFF` = experimental/local

## 6.2 `template_id` (u8)
- `0x00` = NONE
- `0x01` = INVOICE_V1
- `0x02` = CONTRACT_REF_V1
- `0x03` = PAYMENT_RECEIPT_V1
- `0x04` = TRANSFER_INSTRUCTION_V1
- `0x05` = ESCROW_NOTE_V1
- `0x06` = COMPLIANCE_RECORD_V1
- `0x07` = WARRANTY_RECORD_V1
- `0x08` = SHIPMENT_RECORD_V1
- `0x09` = GOLD_CERT_NOTE_V1
- `0x0A` = CUSTOM_KV_V1
- `0x0B..0x7F` = reserved (SOST)
- `0x80..0xFF` = experimental/local

## 6.3 `flags` (u8, bitmask)
- bit0 (`0x01`) = ENCRYPTED
- bit1 (`0x02`) = COMPRESSED
- bit2 (`0x04`) = ACK_REQUIRED
- bit3 (`0x08`) = HAS_EXPIRES
- bit4 (`0x10`) = HAS_TEMPLATE
- bit5 (`0x20`) = MULTIPART_HINT
- bit6 (`0x40`) = RESERVED
- bit7 (`0x80`) = RESERVED

## 6.4 `locator_type` (u8)
- `0x00` = NONE
- `0x01` = HTTPS_PATH
- `0x02` = HTTPS_URL
- `0x03` = IPFS_CID
- `0x04` = OPAQUE_ID
- `0x05` = P2P_HINT
- `0x06..0xFF` = reserved

## 6.5 `hash_alg` (u8)
- `0x01` = SHA256
- `0x02` = BLAKE3 (future / policy)
- others reserved

## 6.6 `enc_alg` (u8)
- `0x00` = NONE
- `0x01` = ECIES_SECP256K1_AES256_GCM (proposed v1)
- `0x02` = X25519_AES256_GCM (future; requires extra key support)
- others reserved

---

## 7. Common Header (12 bytes)

All Capsule payloads start with the same 12-byte header.

### 7.1 Layout
- `offset 0`  / `2 bytes`  / `magic` = ASCII `"SC"` (`0x53 0x43`)
- `offset 2`  / `1 byte`   / `capsule_version` = `0x01`
- `offset 3`  / `1 byte`   / `capsule_type`
- `offset 4`  / `1 byte`   / `flags`
- `offset 5`  / `1 byte`   / `template_id`
- `offset 6`  / `1 byte`   / `locator_type`
- `offset 7`  / `1 byte`   / `hash_alg`
- `offset 8`  / `1 byte`   / `enc_alg`
- `offset 9`  / `1 byte`   / `body_len`
- `offset 10` / `2 bytes`  / `reserved` = `0x0000`

### 7.2 Rules
- `payload_total_size = 12 + body_len`
- `payload_total_size <= 255`
- `reserved` must be zero (policy)
- `body_len` must match actual body size exactly (policy)

---

## 8. Binary Layouts by Type

## 8.1 `OPEN_NOTE_INLINE` (`capsule_type = 0x01`)
**Use case:** short visible note / payment reference

### Body layout
- `0` / `1 byte` / `text_len`
- `1` / `N`      / UTF-8 bytes (`N = text_len`)

### Rules
- `flags.ENCRYPTED` must be `0`
- recommended `text_len <= 80` (policy)
- consensus only requires payload <= 255

---

## 8.2 `SEALED_NOTE_INLINE` (`capsule_type = 0x02`)
**Use case:** short private note

### Encryption (proposed v1)
- ECDH on secp256k1 (sender ephemeral key + receiver pubkey)
- AES-256-GCM for content
- `enc_alg = ECIES_SECP256K1_AES256_GCM`

### Body layout
- `0`      / `33` / `epk_compressed`
- `33`     / `12` / `nonce_gcm`
- `45`     / `1`  / `ct_len`
- `46`     / `N`  / `ciphertext`
- `46+N`   / `16` / `tag_gcm`

### Notes
- only suitable for short plaintexts (tight overhead)
- for larger private data, use `DOC_REF_SEALED`

---

## 8.3 `DOC_REF_OPEN` (`capsule_type = 0x03`)
**Use case:** public reference to off-chain file

### Body layout
- `0`  / `8`  / `capsule_id` (u64 LE)
- `8`  / `4`  / `file_size_bytes` (u32 LE)
- `12` / `32` / `file_hash`
- `44` / `32` / `manifest_hash` (zero if unused)
- `76` / `1`  / `locator_len`
- `77` / `N`  / `locator_ref`

### Examples of `locator_ref`
- IPFS CID
- HTTPS path (short)
- opaque backend ID

### Policy recommendations
- `locator_len <= 96`
- `file_hash != 0`
- `manifest_hash` may be zero for simple open refs

---

## 8.4 `DOC_REF_SEALED` (`capsule_type = 0x04`)
**Use case:** encrypted off-chain document with on-chain proof

### Body layout (same structure as `DOC_REF_OPEN`)
- `0`  / `8`  / `capsule_id`
- `8`  / `4`  / `file_size_bytes`
- `12` / `32` / `file_hash` (encrypted blob hash)
- `44` / `32` / `manifest_hash`
- `76` / `1`  / `locator_len`
- `77` / `N`  / `locator_ref`

### Required rules
- `flags.ENCRYPTED = 1`
- `enc_alg != NONE`
- encryption envelope details live in the off-chain manifest

---

## 8.5 `TEMPLATE_FIELDS_OPEN` (`capsule_type = 0x05`)
**Use case:** compact structured data (invoice/receipt/etc.) without repeated long text

### Body layout
- `0`  / `8`  / `capsule_id`
- `8`  / `1`  / `field_codec` (`0x01 = TLV_COMPACT`)
- `9`  / `1`  / `fields_len`
- `10` / `N`  / `fields_tlv`

### Required rules
- `template_id != NONE`
- `flags.HAS_TEMPLATE = 1`

### TLV example tags
- `0x01` = invoice_number
- `0x02` = due_date
- `0x03` = amount_minor
- `0x04` = currency
- `0x05` = doc_hash_short

---

## 8.6 `TEMPLATE_FIELDS_SEALED` (`capsule_type = 0x06`)
Same concept as `TEMPLATE_FIELDS_OPEN`, but private.

### Rules
- `flags.ENCRYPTED = 1`
- `enc_alg != NONE`

### v1 recommendation
If encrypted template fields do not fit inline:
- use `DOC_REF_SEALED` + `template_id`

---

## 8.7 `CERT_INSTRUCTION` (`capsule_type = 0x07`)
**Use case:** transferable certificate/instruction note (ecosystem-specific)

### Body layout
- `0`  / `1` / `cert_kind`
- `1`  / `1` / `instr_kind`
- `2`  / `8` / `cert_id` (u64 LE)
- `10` / `8` / `ref_value` (u64 LE)
- `18` / `4` / `expires_at` (u32 LE, 0 if none)
- `22` / `1` / `note_len`
- `23` / `N` / `short_note`

### Notes
- may be combined with `DOC_REF_*`
- useful for symbolic gold-linked instructions / proof notes / ecosystem flows

---

## 9. Off-chain Manifest (Recommended for `DOC_REF_*`)

The manifest is **not** stored on-chain.
Only `manifest_hash` is anchored on-chain.

## 9.1 Recommended manifest contents (off-chain)
Suggested fields (JSON or binary, outside consensus):
- `version`
- `file_name` (optional)
- `mime_type`
- `file_hash`
- `file_size`
- `chunking` info (if chunked)
- `encryption`:
  - `enc_alg`
  - `recipients[]`
  - `wrapped_key` / envelope
  - nonce/tag (if needed)
- `locators[]`
- `created_at`
- `sender_pub_hint` (optional)

## 9.2 Why manifest is off-chain
This keeps consensus simple and stable:
- backend can change (HTTPS/IPFS/other)
- on-chain format stays minimal
- only hashes are consensus-relevant

---

## 10. Wallet Automation Model (Recommended)

## 10.1 Default behavior (simple)
For v1, wallet should provide:
- **Send SOST only**
- **Send SOST + note**
- **Send SOST + document reference**

The wallet should automate:
- hashing
- encoding capsule
- fee estimation
- signing

## 10.2 Encrypted mode (future v1.1 / v2 rollout)
When privacy is enabled, wallet automates:
- CEK generation (new symmetric key per document)
- encryption
- envelope creation for recipient
- manifest generation
- upload
- capsule build
- tx signing

Users should not manually handle cryptographic details.

## 10.3 Storage backends (user-funded)
Wallet may support:
- default HTTPS backend
- user-owned HTTPS server
- IPFS (optional)
- local provider plugin / custom backend

**Important:** Storage costs are paid by the sender/user/service, not by SOST consensus.

---

## 11. On-chain vs Off-chain

## 11.1 On-chain (SOST)
- SOST value transfer
- capsule header
- hashes
- locator reference
- minimal metadata
- short note (if small enough)

## 11.2 Off-chain
- PDFs
- images
- audio
- long text/documents
- encrypted blobs
- manifests
- chunk maps

---

## 12. Security and Privacy (v1)

## 12.1 Privacy model
The chain does not hide:
- sender/receiver/value (normal chain transparency)

The chain may hide:
- note/document content (if encrypted capsule / encrypted blob)

## 12.2 Per-document encryption (recommended)
For private documents:
- generate a fresh CEK for each document
- encrypt document with AES-256-GCM
- wrap CEK for recipient via ECIES (secp256k1)
- store envelope in manifest

This avoids key reuse and improves safety.

## 12.3 Integrity checks (mandatory in wallet/client)
Before opening a document:
1. verify `manifest_hash`
2. verify `file_hash`
3. then decrypt/open

If hashes mismatch:
- reject content

---

## 13. Mempool Policy Rules (v1 Recommended)

These are **policy** rules unless explicitly marked consensus.

## 13.1 Standard Capsule acceptance
- Accept `capsule_type` only in `0x00..0x07` by default
- `payload_total <= 255` (**consensus**)
- If payload non-empty:
  - `magic == "SC"`
  - `capsule_version == 1`
  - `body_len` exact match
  - `reserved == 0`

## 13.2 Payload outputs per transaction
Recommended v1:
- max outputs with non-empty payload = **1**

Reason:
- simpler parsing
- lower spam risk
- predictable fee behavior

## 13.3 Per-type policy limits
- `OPEN_NOTE_INLINE`: `text_len <= 80`
- `DOC_REF_*`: `locator_len <= 96`
- `TEMPLATE_FIELDS_*`: `fields_len <= 128`
- `CERT_INSTRUCTION`: `note_len <= 64`

## 13.4 Fee policy
Fees should be based on transaction size in bytes.

Recommended:
- standard fee rate per byte
- optional payload weight multiplier (e.g. `2x`) for spam resistance

## 13.5 Dust policy
Payload does **not** exempt dust rules.

A transfer output with payload can still be dust and should be rejected by policy if below threshold.

## 13.6 Minimal DOC_REF checks
For `DOC_REF_*`:
- `hash_alg` must be supported
- `file_hash != 0`
- `locator_len > 0`
- `enc_alg != NONE` if sealed type

---

## 14. Examples

## 14.1 Example A: `OPEN_NOTE_INLINE`
**Use case:** visible payment reference

Plain text:
- `INV-2026-001`

On-chain:
- header (`SC`, v1, OPEN_NOTE_INLINE)
- body:
  - `text_len = 12`
  - bytes of `INV-2026-001`

No off-chain file required.

---

## 14.2 Example B: `DOC_REF_SEALED` (encrypted contract)
**Use case:** SOST transfer + private contract

On-chain capsule:
- `capsule_type = DOC_REF_SEALED`
- `flags = ENCRYPTED | HAS_TEMPLATE`
- `template_id = CONTRACT_REF_V1`
- `file_hash = SHA256(encrypted_blob)`
- `manifest_hash = SHA256(manifest)`
- `locator_type = HTTPS_PATH`
- `locator_ref = "/caps/2026/03/abc123.cap"`

Off-chain manifest:
- encryption envelope for recipient
- file metadata
- optional chunks
- optional alternate locators

Receiver flow:
1. sees tx
2. downloads manifest/blob
3. verifies hashes
4. unwraps CEK with private key
5. decrypts and opens contract

---

## 14.3 Example C: `TEMPLATE_FIELDS_OPEN` (compact invoice)
**Use case:** business metadata without large repeated text

On-chain:
- `template_id = INVOICE_V1`
- TLV fields:
  - invoice_number
  - due_date
  - amount_minor
  - currency
  - optional short doc hash

Advantage:
- very compact
- deterministic
- easy to parse

---

## 15. What v1 Does NOT Do

- It does **not** store large files on-chain
- It does **not** guarantee eternal availability of off-chain files
- It does **not** replace IPFS/HTTPS/storage providers
- It does **not** make SOST a general file-hosting chain

SOST anchors proofs and transfers value; storage remains external.

---

## 16. Tests (Required)

## 16.1 Codec / parser tests
1. valid header encode/decode roundtrip
2. reject `payload_total > 255`
3. reject mismatched `body_len`
4. reject invalid `magic` (policy)
5. reject unsupported `capsule_version`
6. reject non-zero `reserved`
7. reject invalid `locator_len`
8. `OPEN_NOTE_INLINE` empty and max cases
9. reject `DOC_REF_*` with zero `file_hash`
10. reject `TEMPLATE_FIELDS_*` with `template_id = NONE`

## 16.2 Crypto tests (when sealed is implemented)
1. SEALED note encrypt/decrypt OK
2. wrong recipient key fails
3. modified GCM tag fails
4. invalid ephemeral pubkey fails
5. modified nonce fails
6. manifest hash mismatch fails
7. file hash mismatch fails

## 16.3 Mempool policy tests
1. tx with no payload -> accept
2. tx with one valid capsule -> accept
3. tx with 2 payload outputs (if max=1) -> reject
4. fee too low for payload tx -> reject
5. dust output + payload -> reject
6. `OPEN_NOTE_INLINE` > 80 bytes -> reject
7. `DOC_REF_*` locator too long -> reject
8. experimental `capsule_type` -> reject (default policy)

---

## 17. Rollout Plan (CTO Recommendation)

## 17.1 Phase A (launch-safe)
Implement:
- Capsule parser/encoder
- `OPEN_NOTE_INLINE`
- `DOC_REF_OPEN`

No encrypted mode required yet.

## 17.2 Phase B (privacy)
Implement:
- `DOC_REF_SEALED`
- off-chain manifest encryption envelope
- optional `SEALED_NOTE_INLINE`

## 17.3 Phase C (ecosystem utilities)
Implement:
- templates (`INVOICE_V1`, `CONTRACT_REF_V1`, etc.)
- wallet UX for "Attach document"
- optional IPFS support + pinning integration

---

## 18. SOST Code Integration (Where to Implement)

## 18.1 `transaction.h/.cpp`
- `payload` already exists (raw bytes)
- add Capsule encode/decode helpers (non-consensus utility)
- keep base transaction serialization unchanged

## 18.2 `tx_validation.h/.cpp`
- consensus checks:
  - payload length <= 255
- policy checks:
  - Capsule structure validity
  - allowed types
  - per-type limits
  - optional strict mode

## 18.3 `mempool.h/.cpp`
- standardness policy for Capsule
- payload count per tx
- fee/byte policy
- dust policy
- reject non-standard capsule formats by default

## 18.4 Wallet (CLI/GUI)
- build Capsule payloads
- optional encryption (sealed modes)
- off-chain upload integration (HTTPS/IPFS/custom)
- verify hashes on receive/open
- automatic fee estimation

---

## 19. Final v1 Decision (Important)

To keep launch simple and reliable:

### Consensus (v1)
Keep consensus minimal:
- `payload <= 255 bytes`

### Policy (v1 standard)
Enable Capsule gradually:
1. `OPEN_NOTE_INLINE`
2. `DOC_REF_OPEN`

### Future policy/extensions
Later add:
- `DOC_REF_SEALED`
- template payloads
- full wallet automation for private document workflows

This keeps SOST:
- lightweight
- cheap
- useful
- extensible
- production-safe
