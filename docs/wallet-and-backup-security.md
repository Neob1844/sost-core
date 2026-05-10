# SOST Wallet & Backup Security

Single source of truth for "why does my balance look like 0 spendable?",
"can I recover my wallet?", "should I run two miners with the same address?",
and other questions that come up the first week a new miner joins SOST.

This document is canonical. Other pages (the whitepaper reader, the
miner setup guide, FAQ entries, the BTCTalk ANN thread) link here rather
than duplicate the answer.

---

## TL;DR

| Concept           | What it means                                                       |
|-------------------|---------------------------------------------------------------------|
| SOST coins        | Live on-chain forever, public and permanent                         |
| Private keys      | Live ONLY in your local encrypted wallet file                       |
| Recovery          | The 12-word BIP39 phrase regenerates the keys                       |
| Responsibility    | Your keys, your coins. Your loss if you lose them                   |

> **Your keys, your coins. Your loss if you lose them.**

---

## 1. What's stored on-chain vs locally

### On-chain (the SOST blockchain)

Stored permanently on every node and indestructible while the network
exists:

- **Blocks**: hash, parent hash, timestamp, miner address, merkle root
- **Transactions**: sender, receiver, amount, fees, signatures
- **UTXOs**: every unspent output and the address that owns it
- **Coinbase rewards**: which address received which block reward
- **Lottery payouts**: which address won which DTD lottery
- **PoPC commitments**: bond UTXOs and their lock heights
- **Gold Vault state**: governance ledger entries

Anyone running a SOST node can read all of this. It is public.

### Local only (your wallet file)

Stored exclusively on your machine:

- **Private keys** — sign transactions and blocks. Critical.
- **The 12-word BIP39 seed** (only when the wallet was created with
  `sost-cli hd create`; not present in CLI wallets created with plain
  `newwallet`)
- **Address labels** — `default`, `phase2-miner`, … cosmetic
- **Local UTXO index cache**

If you lose the file AND the 12 words, **you cannot move your SOST
anymore**. The SOST themselves remain in the chain forever, just
unreachable.

#### Three storage layers, three encryption models

There is no single answer to "is my wallet encrypted?" — SOST has three
distinct files and they behave differently. Mixing them up is the most
common cause of accidental key exposure:

| File                                        | Encryption                                | Where it should live                                  |
|---------------------------------------------|-------------------------------------------|-------------------------------------------------------|
| CLI **active** wallet (e.g. `wallet.json`)  | **None** — plain JSON                     | Local disk only. **Never upload to cloud / share.**   |
| CLI **encrypted backup** (`*.enc`)          | scrypt N=32768 + AES-256-GCM              | Anywhere — USB, cloud, email, all safe                |
| Web wallet entry in browser `localStorage`  | PBKDF2 100k + AES-256-GCM under password  | The browser holds it; the **Download Encrypted Backup** button exports the same encrypted JSON, also cloud-safe |

Why the CLI active wallet is plaintext: the miner and RPC need to sign
blocks and transactions without prompting for a password every time. A
prompt would block 24/7 mining. The encrypted backup format
(`wallet-export --encrypted`) and the web wallet's encrypted
localStorage are the layers that protect keys at rest; the active CLI
wallet trades that protection for unattended operation. Only run the
CLI miner on a machine you physically control and where you trust the
disk is yours alone.

### Bank vault analogy

```
+-------------------------------------------------------------+
|  THE CHAIN  =  an indestructible glass vault                |
|                everyone sees what's inside                  |
|                your N SOST are visible to all               |
|                                                             |
|  YOUR KEY   =  the only key to that vault                   |
|                you keep it in your pocket                   |
|                if you lose it the vault stays sealed        |
|                forever — even though everyone still sees    |
|                your SOST inside                             |
+-------------------------------------------------------------+
```

This is the cost of being your own bank. In the legacy financial system
you trust the bank to keep your records. In SOST you keep them yourself.

---

## 2. Why aren't private keys stored automatically?

Three reasons:

1. **The chain is public.** Putting private keys on-chain would publish
   them to every node. Anyone could move your SOST instantly.
2. **Chain bloat.** Storing wallet state for every user would push the
   chain into terabytes territory. Lightweight nodes and bootstrap
   downloads would become impractical.
3. **Trustless decentralisation.** A core PoW-blockchain principle is
   that you don't have to trust a third party. If a foundation could
   "recover" your wallet, it could also seize it, censor it, or be
   coerced. SOST avoids that by design.

---

## 3. Backup strategy — two layers

### Layer 1 — The 12 BIP39 words on paper

Your master backup. Generated when you ran `sost-cli hd create`.

Keep them written on paper, in order, in a secure physical location. Not
digital, not photographed, not typed into a website you don't fully
control.

With these 12 words you can regenerate every HD-derived private key from
scratch on any device. Even if your hardware is destroyed, your SOST are
recoverable.

### Layer 2 — Wallet file backup

A convenience layer on top of the 12 words. **What you copy depends
on which wallet you're backing up:**

**CLI wallet** (`wallet.json`, `phase2-miner-wallet.json`, …) — the
active file is plain JSON, so a raw copy is **not safe to upload to
cloud or share**. For an off-site copy, export an encrypted snapshot
first:

```bash
# Encrypted export (cloud-safe). Prompts for a passphrase you invent
# now; remember it — it cannot be recovered. KDF: scrypt N=32768.
# Cipher: AES-256-GCM.
./sost-cli --wallet wallet.json wallet-export \
    --encrypted --output wallet-backup-$(date +%Y%m%d).enc
```

The `.enc` is what you upload to USB, Drive, email, or anywhere else.
**Never upload the raw `wallet.json`** — it contains the private keys
in plaintext. Restore later with `wallet-import --encrypted`; see
section 9.

For an in-house copy on a machine you fully control (USB in a drawer,
another machine on your LAN), copying the raw `wallet.json` is fine
and faster:

```bash
cp wallet.json /path/to/usb/wallet-backup-$(date +%Y%m%d).json
chmod 600 /path/to/usb/wallet-backup-*.json
```

**Web wallet** (`sost-wallet.html`) — use the **Download Encrypted
Backup** button on the seed screen (and again from Settings). That
file is already PBKDF2 + AES-256-GCM encrypted with your wallet
password and is safe for cloud / email / USB without further wrapping.

Recovery from either is faster than the 12-word path (~1 minute vs
30–60 minutes), and preserves labels and the local UTXO index cache.

---

## 4. How to recover a wallet

### Fast path (you have a wallet JSON backup)

```bash
# 1. Copy the backup to the new machine
cp wallet-backup-20260509.json ~/SOST/sostcore/sost-core/build/wallet.json
chmod 600 wallet.json

# 2. Verify the address list is what you expect
./sost-cli --wallet wallet.json listaddresses

# 3. Relaunch the miner with the same flags as before
./sost-miner --wallet wallet.json --mining-key-label phase2-miner ...
```

Web wallet equivalent: open `sostcore.com/sost-wallet.html` →
**Import** → Upload encrypted backup → enter password.

Total time: about 1 minute.

### Deep path (you only have the 12 words)

```bash
# 1. Get the sost-cli binary on the new machine.

# 2. Create an empty wallet shell.
./sost-cli --wallet wallet.json newwallet

# 3. Restore from seed phrase. The CLI prompts for the 12 words.
./sost-cli --wallet wallet.json hd restore

# 4. Recreate any labels you used.
./sost-cli --wallet wallet.json getnewaddress phase2-miner
# repeat for each label you had

# 5. Confirm the address shows the same as before.
./sost-cli --wallet wallet.json listaddresses

# 6. Sync UTXOs from the node (the wallet picks up your coinbase /
#    incoming transfers automatically when you query info or send).
./sost-cli --wallet wallet.json info
```

Web wallet equivalent: **Import** → "From 12-word seed phrase" → paste
the words → set a new password.

Total time: 30–60 minutes including any chain rescan. The result is
identical — the same address, the same SOST balance — because BIP44
derivation is deterministic.

---

## 5. The 1000-block coinbase maturity rule

When you mine a block the reward (coinbase) is **immature** for 1000
confirmations (~7 days at the 600-second target).

This is a standard PoW protection: if a deep reorg invalidates a recent
block, its reward becomes invalid too. The maturity period prevents
users from spending coins that might disappear.

Symptom you will see:

```
SPENDABLE:  0 SOST
IMMATURE:  31.40400000 SOST  (4 coinbase UTXOs)
```

Cure: time. Each new block adds 1 confirmation. After 1000 blocks on
top of yours, the SOST become spendable.

---

## 6. Mining with the same address from multiple machines

Common assumption: "if I run two miners pointing to the same wallet
label, my hashrate adds up."

Actual behaviour: it does not add up cleanly. Both miners build very
similar block templates (same coinbase address, same prev hash, same
timestamp window) and explore overlapping nonce space. Whichever miner
finds a valid nonce first wins; the other miner's recent work for that
template is discarded once the next block lands. The exact amount of
overlap depends on how far apart the two miners' nonce search starts
and how the timestamps drift, so the loss varies — what is reliable is
that **two solo miners on the same label are not equivalent to one
miner with double the hashrate**. There is no SOST stratum/pool today
that coordinates nonce ranges between them.

### Recommended approach: one address per machine, consolidate later

```bash
# On machine 1
./sost-cli --wallet wallet.json getnewaddress miner-rig-1
./sost-miner --wallet wallet.json --mining-key-label miner-rig-1 ...

# On machine 2
./sost-cli --wallet wallet.json getnewaddress miner-rig-2
./sost-miner --wallet wallet.json --mining-key-label miner-rig-2 ...

# Periodically consolidate the two streams into one address
./sost-cli --wallet wallet.json --from-label miner-rig-2 \
    send sost1<consolidation-address> <amount>
```

This way each machine owns its own address and explores nonce space
without colliding. When a stratum-style pool ships in the future, it
will distribute disjoint nonce ranges to many workers signing under one
shared payout address; that is the only architecture in which "same
address, many machines" cleanly adds hashrate.

---

## 7. Common questions

**Q: I lost my computer. Are my SOST gone?**
No. Your SOST are in the chain. If you have either the 12-word seed
phrase OR a wallet JSON backup, you can recover them on any machine.

**Q: I lost both the 12 words and the wallet file.**
Your SOST are unreachable. They remain in the chain forever, visible to
everyone, but no one can spend them. This is permanent.

**Q: Someone saw my 12 words.**
They can move your SOST to their wallet. Immediately:

1. Generate a new wallet (`sost-cli newwallet` + `hd create`).
2. Send your entire balance to the new address before the attacker
   does.
3. Discard the compromised wallet forever.

**Q: My wallet JSON is on Google Drive. Is that safe?**
Depends on which JSON. If it is the CLI active wallet
(`wallet.json` / `phase2-miner-wallet.json`), **no — that file is
plain JSON and contains the private keys readable by anyone who
downloads it.** Delete it from cloud and replace with an encrypted
export (`wallet-export --encrypted` → `.enc`).

If it is a `.enc` file (CLI `wallet-export --encrypted`) or a web
wallet **Download Encrypted Backup** export, yes — both are AES-256-
GCM encrypted under a key derived from your passphrase / password
(scrypt or PBKDF2). With a strong passphrase (20+ random chars) the
file is computationally infeasible to crack. With a weak one
("password123") it can be brute-forced. Use a password manager and a
long random passphrase.

**Q: Can the SOST developers recover my wallet?**
No. They have no privileged access. If they could, the system wouldn't
be trustless.

**Q: What if the SOST project itself stops being maintained?**
Your private key still works. Anyone running a SOST-compatible node can
submit a transaction signed by your key. As long as any node exists
somewhere, your SOST can still move.

---

## 8. Best-practices checklist

Before starting to mine seriously:

- [ ] Generated a wallet with `sost-cli hd create`
- [ ] Wrote the 12 words on physical paper, in order, double-checked
- [ ] Stored the paper somewhere physically secure (locked drawer, safe)
- [ ] Made a backup copy of the wallet JSON onto a USB or another machine
- [ ] Set the wallet password to 20+ random characters (managed by a
      password manager)
- [ ] Confirmed the address on the explorer (`sostcore.com/sost-explorer.html`)
- [ ] Configured NTP (`chronyc`) so block timestamps are valid
- [ ] Read the 1000-block coinbase maturity rule (don't expect a
      spendable balance immediately)

If all eight are checked, you are ready to mine safely.

---

## 9. Encrypted backup — commands cheat sheet

The CLI ships three commands for moving keys around. Verified in
`src/sost-cli.cpp`:

```bash
# Export an encrypted backup. Prompts for a passphrase you invent NOW,
# repeated for confirmation. Min 8 chars. KDF: scrypt N=32768, r=8, p=1.
# Cipher: AES-256-GCM. Output is the .enc file, cloud-safe.
./sost-cli --wallet wallet.json wallet-export \
    --encrypted --output wallet-backup-$(date +%Y%m%d).enc

# Import an encrypted backup into a fresh active wallet (the destination
# wallet must already exist — create it first with newwallet, then run
# wallet-import). Prompts for the passphrase used at export.
./sost-cli --wallet /tmp/restored.json newwallet
./sost-cli --wallet /tmp/restored.json wallet-import \
    --encrypted --input wallet-backup-20260510.enc

# Print one private key from the active wallet (DANGER — the key is
# already plaintext on disk; this just prints it to your terminal).
./sost-cli --wallet wallet.json dumpprivkey sost1...
```

There are **three different secrets** in this system; do not mix them
up:

| Secret                                   | Where it lives                | Who creates it             | Recoverable?               |
|------------------------------------------|-------------------------------|----------------------------|----------------------------|
| The 12-word BIP39 seed                   | Paper, in your hand           | The CLI / web wallet at HD wallet creation | No — written **once** at creation, never shown again |
| The `.enc` backup passphrase             | Your head, then on paper      | **You invent it** at `wallet-export` time | No — if you forget it, the `.enc` is unrecoverable |
| The web wallet password                  | Your head                     | **You invent it** at wallet creation       | No — wraps the entire web-wallet localStorage entry |

The `.enc` passphrase and the 12-word seed are independent. You can
write both on the same paper (label them) but they are not the same
thing: the seed reconstructs HD-derived keys mathematically; the
passphrase decrypts a snapshot of all keys (HD-derived AND non-HD).

---

## 10. The CLI mining label is freeform

There is no fixed list of valid mining labels and no "phase2-miner"
prefix requirement. Verified in `src/sost-cli.cpp:1269` and
`src/wallet.cpp:84`: `getnewaddress <label>` takes the label as a
plain string with no validation, and `find_key_by_label` is a direct
string compare.

The only rule: the label you pass to `getnewaddress <label>` must be
**character-for-character identical** to the one you pass to
`--mining-key-label <label>` when launching the miner against the
same wallet. Pick whatever you remember — `phase2-miner`,
`home-rig`, `node-3`, `bedroom-laptop`, anything.

Two example flows, with different labels, both produce a valid
mining setup:

```bash
# Example A — label "phase2-miner"
./sost-cli --wallet phase2-miner-wallet.json newwallet
./sost-cli --wallet phase2-miner-wallet.json getnewaddress phase2-miner
./sost-miner --wallet phase2-miner-wallet.json \
             --mining-key-label phase2-miner [...]

# Example B — label "home-rig"
./sost-cli --wallet home-rig-wallet.json newwallet
./sost-cli --wallet home-rig-wallet.json getnewaddress home-rig
./sost-miner --wallet home-rig-wallet.json \
             --mining-key-label home-rig [...]
```

The miner echoes the chosen label at startup so you can confirm:

```
SbPoW signing key: label='<your-label>'
Miner address: sost1...   (derived from wallet key)
```

---

## 11. HD seed vs `getnewaddress` — recovery semantics

Two CLI commands generate a key, but they have **different recovery
guarantees**, and confusing them is the most common way to lose
seed-based recovery on a mining wallet:

| Command                              | What it generates                                    | Label         | Recoverable from 12 words?         |
|--------------------------------------|------------------------------------------------------|---------------|------------------------------------|
| `sost-cli hd create`                 | One address derived from a fresh BIP39 12-word seed | `hd-seed`     | **Yes** — `hd restore` regenerates it byte-for-byte |
| `sost-cli getnewaddress <label>`     | One address from a fresh **random** secp256k1 key    | `<label>`     | **No** — the random key is NOT derived from any seed; it only lives inside `wallet.json` |

If you create an HD wallet and **then** run `getnewaddress
phase2-miner` and mine to that label, the mined coinbase rewards land
on a non-HD address. The 12 words on paper will not recover them.
Your only backup for that address is the `wallet.json` file itself
(or its `.enc` export). Lose both → lose those SOST.

To keep "12 words → full recovery" as your safety net, **mine to the
HD-derived address directly**:

```bash
./sost-cli --wallet wallet.json hd create
# (write the 12 words on paper exactly once when they print)

./sost-cli --wallet wallet.json listaddresses
# look for the entry tagged [hd-seed]; that is the address you mine to

./sost-miner --wallet wallet.json \
             --mining-key-label hd-seed [...]
```

The `hd-seed` label is just a string — you can keep it, or generate
a new HD wallet with whatever label you prefer if you ever rebuild.
What matters is that the address you pick to mine to was
**derived from the seed**, not generated random by `getnewaddress`.

The web wallet (`sost-wallet.html`) avoids this trap entirely: each
wallet has exactly one address, derived from the displayed 12 words.
There is no equivalent of `getnewaddress` that would add a non-HD
key.

---

## 12. Local cache vs chain truth

When you run:

```
$ ./sost-cli --wallet wallet.json info
  Balance:   11.989... SOST   (chain truth)
$ ./sost-cli --wallet wallet.json listaddresses
  sost1...   1548.510... SOST   (chain truth)
```

— or when `wallet-import --encrypted` reports
`Balance: 11.98...` after a fresh import — you can see two different
numbers and they are both correct. This is expected behaviour, not a
bug, and **it does not affect what you can spend**. Explanation:

- The CLI wallet keeps a small **local UTXO index cache** that only
  holds UTXOs the wallet has signed for or imported explicitly. It is
  not auto-populated with coinbase rewards from the wallet's own
  mining-key — those land on the node's UTXO set directly.
- The display fix in commit `995d61c` made `info` and
  `listaddresses` query `getaddressutxos` from the node and tag the
  result `(chain truth)` so the headline number always matches the
  explorer.
- `send` calls `sync_wallet_utxos_from_node` before signing, so the
  spendable set used for any outgoing transaction is the chain
  truth, not the cache. You can always spend the real on-chain
  balance.
- `wallet-export --encrypted` snapshots the **private keys** plus the
  current local cache. The keys give full control of every UTXO at
  every address they own, present and future. The cache figure
  inside the `.enc` is just an offline snapshot from the moment of
  export — not a cap on what the keys can recover.

So: a `.enc` whose import shows a small `Balance:` is still the right
backup. Verify by running `listaddresses` after import; the
`(chain truth)` line is the one that matches the chain.

If the `Balance:` line in `info` lags too far behind chain truth and
you want to refresh the cache, the way is to rebuild it implicitly
by running `send` (the sync happens before signing). A standalone
`wallet rescan` command is not part of the CLI today.

---

## 13. Transaction and block limits

Hard ceilings, enforced by the consensus rules. A block that violates
any of these is rejected by every node on the network:

| Limit                                              | Constant                          | Value          |
|----------------------------------------------------|-----------------------------------|----------------|
| Max transaction size                               | `MAX_TX_BYTES_CONSENSUS`          | **100 KB**     |
| Max block size                                     | `MAX_BLOCK_BYTES_CONSENSUS`       | **1 MB**       |
| Max transactions per block                         | `MAX_BLOCK_TXS_CONSENSUS`         | **65 536**     |

Soft (policy) ceilings, enforced by the local mempool and the miner's
template builder. A transaction that violates a policy ceiling is
**not relayed** by peer nodes and is **not picked up** by the miner
template, but a hand-crafted block carrying it is still consensus-
valid as long as it stays under the hard ceilings:

| Limit                                              | Constant                          | Value          |
|----------------------------------------------------|-----------------------------------|----------------|
| Standard transaction size (mempool relay limit)    | `MAX_TX_BYTES_STANDARD`           | **16 KB**      |
| Default transactions per block (miner template)    | `MAX_BLOCK_TX_COUNT`              | **4 096**      |
| Target block spacing                               | `TARGET_SPACING`                  | **600 s**      |

(File references: `include/sost/tx_validation.h`,
`include/sost/consensus_constants.h`, `include/sost/block_validation.h`,
`include/sost/mempool.h`, `include/sost/params.h`.)

Practical throughput, given a 600-second block:

| Transaction shape                                   | Typical bytes | TX/block (1 MB) | TX/hour |
|-----------------------------------------------------|---------------|-----------------|---------|
| Simple payment, 1–2 inputs, 2 outputs, no capsule   | ~250–400 B    | 2 500 – 4 000   | 15 000 – 24 000 |
| Payment with small capsule (Open Note ≤80 B)        | ~500–700 B    | 1 400 – 2 000   | 8 400 – 12 000  |
| Heavy capsule send (39 inputs + capsule)            | ~5 850 B      | ~170            | ~1 020          |
| Transaction at the 16 KB policy limit               | ~16 000 B     | 62              | 372             |

What happens at congestion: the mempool holds the surplus until later
blocks pick it up. The miner template orders candidates by fee rate
(stocks per byte) and includes the highest-paying subset that fits
under the size and count caps. Low-fee transactions wait — they do
not vanish. The wallet's auto-split logic exists precisely so a
single payment that would build to over 16 KB is split into smaller
chunks that pass the relay filter; you have already seen this in
practice when sending a capsule payment that fans out to N siblings
in the same block.

The web wallet does not need to know any of these numbers explicitly
— the fee-pass converging loop and the auto-split helper handle the
limits automatically. They are documented here so you can recognise
the symptoms when they appear (e.g. a `tx size 22369 > standard
limit 16000` rejection).

---

## Implementation note

The web wallet (`sostcore.com/sost-wallet.html`) gates the seed-phrase
reveal behind a red warning panel and refuses to leave the
"Your Seed Phrase" screen until the user explicitly checks
*"I have written all 12 words on physical paper, in order, and verified
them"*. The exact strings live in `website/sost-wallet.html`
(`#seedRevealGate`, `#seedWrittenAck`, `revealSeed()`,
`confirmSeedSaved()`).

This document is the textual source of truth for the wording. If the
wallet UI or the FAQ section diverges, update them to match this file
rather than the other way around.
