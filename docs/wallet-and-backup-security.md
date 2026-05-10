# SOST Wallet & Backup Security / Seguridad de Wallet y Backups

Single source of truth for "why does my balance look like 0 spendable?",
"can I recover my wallet?", "should I run two miners with the same address?",
and other questions that come up the first week a new miner joins SOST.

This document is canonical. Other pages (the whitepaper reader, the
miner setup guide, FAQ entries, the BTCTalk ANN thread) link here rather
than duplicate the answer.

---

## TL;DR

| Concept           | Spanish                                                   | English                                                       |
|-------------------|-----------------------------------------------------------|---------------------------------------------------------------|
| SOST coins        | Viven SIEMPRE en la cadena, públicas y permanentes        | Live on-chain forever, public and permanent                   |
| Private keys      | Viven SOLO en tu wallet local cifrado                     | Live ONLY in your local encrypted wallet file                 |
| Recovery          | Las 12 palabras BIP39 regeneran las claves                | The 12-word BIP39 phrase regenerates the keys                 |
| Responsibility    | Tú custodias las claves. Tú pierdes si las pierdes        | Your keys, your coins. Your loss if you lose them             |

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

Stored exclusively on your machine, encrypted with **AES-256-GCM** under
your wallet password (web wallet) or kept inside the JSON file the CLI
manages (e.g. `wallet.json` / `phase2-miner-wallet.json`):

- **Private keys** — sign transactions and blocks. Critical.
- **The 12-word BIP39 seed** (when generated via `sost-cli hd create`)
- **Address labels** — `default`, `phase2-miner`, … cosmetic
- **Local UTXO index cache**

If you lose the file AND the 12 words, **you cannot move your SOST
anymore**. The SOST themselves remain in the chain forever, just
unreachable.

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

### Layer 2 — Backup of the wallet JSON

A convenience layer on top of the 12 words. The file is encrypted (web
wallet uses AES-256-GCM under your password; CLI wallets are JSON the
CLI re-loads).

- Faster recovery (~1 minute vs 30–60 minutes from seed)
- Preserves labels and any local indexing state
- Encrypted backups are safe to upload to cloud storage

```bash
# Quick backup to a USB or another machine
cp wallet.json /path/to/usb/wallet-backup-$(date +%Y%m%d).json
chmod 600 /path/to/usb/wallet-backup-*.json

# Or to a remote machine via scp
scp wallet.json user@backup-server:/secure/path/wallet-backup-$(date +%Y%m%d).json
```

If you use the web wallet (`sost-wallet.html`), use the **Download
Encrypted Backup** button on the seed screen (and again from Settings).
That file is the encrypted JSON — same idea.

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

**Q: My encrypted wallet JSON is on Google Drive. Is that safe?**
The file is AES-256-GCM encrypted with your wallet password. With a
strong password (20+ random chars) the file is computationally infeasible
to crack. With a weak password ("password123") it can be brute-forced.
Use a password manager and a long random password.

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

## Sección en español (resumen rápido)

### Qué hay en la cadena vs en tu equipo

**En la cadena (público y permanente)**: bloques, transacciones, UTXOs,
recompensas de minado, lotterías, gold vault. Cualquier nodo lo puede
leer. Tus SOST están aquí.

**Solo en tu wallet local**: claves privadas, frase semilla cifrada,
labels, derivación HD. Si pierdes el archivo Y las 12 palabras no podrás
mover tus SOST nunca más.

### Por qué no se guardan claves en la cadena

Si las claves estuvieran en la cadena, todos las verían y cualquiera
podría mover tus SOST. Sería un sistema sin sentido. La cadena guarda lo
público. Las claves son responsabilidad del usuario.

### Cómo recuperar la wallet

**Vía rápida (con backup del wallet JSON)**: copiar el archivo a otro
equipo y lanzar el CLI. ~1 min.

**Vía profunda (solo con las 12 palabras)**:

```bash
./sost-cli --wallet wallet.json newwallet
./sost-cli --wallet wallet.json hd restore   # te pide las 12 palabras
./sost-cli --wallet wallet.json getnewaddress phase2-miner
./sost-cli --wallet wallet.json info
```

~30-60 min. La dirección regenerada es idéntica a la original (BIP44
determinístico).

### Madurez de coinbase: 1000 bloques

Cuando mineas un bloque, los SOST son **inmaduros** durante 1000
confirmaciones (~7 días). Tu saldo aparece como `IMMATURE` y
`SPENDABLE: 0` durante ese tiempo. Es protección anti-reorg estándar
PoW. Solo hay que esperar.

### Minar con la misma address en varias máquinas

Dos miners con la misma label construyen templates muy similares y
exploran rangos de nonce solapados. **No suma hashrate de forma limpia**:
parte del trabajo de la segunda máquina se descarta cuando llega el
siguiente bloque. Lo recomendado es **una label/address por máquina** y
consolidar después con `sost-cli send`. Cuando exista un stratum/pool
oficial de SOST, una única dirección compartida sí podrá sumar hashrate
porque el pool reparte rangos de nonce disjuntos.

### Tus claves, tus monedas

Si pierdes las 12 palabras Y el wallet JSON, tus SOST quedan
inalcanzables para siempre. Apunta las palabras en papel, guárdalas
físicamente seguras, y haz copias del wallet cifrado en otro disco/USB.

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
