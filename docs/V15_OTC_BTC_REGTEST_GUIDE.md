# OTC-3a — BTC HTLC Signing on regtest (libwally backend)

**Status:** review/regtest only. **OFF by default.** This guide describes the
opt-in `-DSOST_BTC_HTLC_SIGNING=ON` build that turns the BTC HTLC signing
backend from inert stubs into the real libwally implementation, and how to
drive a SOST↔BTC atomic swap on a **Bitcoin regtest** node.

> **Safety invariants (unchanged by anything here):**
> - `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` — the SOST HTLC consensus
>   gate stays OFF. Nothing in OTC-3a flips it.
> - The default build (`SOST_BTC_HTLC_SIGNING` unset/OFF) is **byte-identical**:
>   it links no libwally and every BTC signing function returns `ok=false`
>   (`disabled_result()`).
> - This backend is for **regtest / test vectors only**. Do **not** point it at
>   Bitcoin mainnet and do **not** broadcast outside regtest.
> - No EVM, no mainnet activation, no VPS changes.

---

## 1. What the flag does

`-DSOST_BTC_HTLC_SIGNING=ON`:

1. Defines `SOST_BTC_HTLC_SIGNING_ENABLED=1` (API surface) and
   `SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY=1` (real backend bodies).
2. Builds the **vendored** `vendor/libwally-core` (release_1.5.3) in isolation
   via `ExternalProject`, producing `libwallycore.a` + libwally's own
   `libsecp256k1.a`, and links them into `sost-core`. libwally's bundled
   secp256k1 is kept isolated so it never collides with SOST's **system**
   `secp256k1` (used for consensus SbPoW).
3. Activates the real implementations of: `BuildBtcHtlcRedeemScript`
   (always real), BIP-143 segwit-v0 sighash, Low-R/Low-S ECDSA signing,
   P2WSH witness assembly (claim + refund), `EncodeP2WSHAddress`, and
   `SignBtcHtlcClaim` / `SignBtcHtlcRefund`.

The default OFF build keeps all of the above as stubs returning `ok=false`.

---

## 2. Vendoring libwally-core (one-time)

The build expects `vendor/libwally-core` to contain the GPG-verified
`release_1.5.3` tree (see `docs/design/ATOMIC_SWAP_LIBWALLY_VENDOR_CEREMONY.md`
for provenance: tag `release_1.5.3`, commit
`000137393a436d55a18971ca93a2d20a54d55437`, maintainer key
`129EE55E90E6E7BB5ED3530DFD9FCBA3C53CED20`).

The vendor ceremony disables libwally's own CMake build by prefixing its build
files with `_` (`_CMakeLists.txt`, `src/_CMakeLists.txt`, `_cmake/`) so the
pristine tree never auto-builds. **You do not need to rename them by hand** —
when `SOST_BTC_HTLC_SIGNING=ON`, the SOST CMake restores those names
idempotently at configure time. If `vendor/libwally-core` is absent entirely,
the configure step fails fast with a pointer back to this guide.

> The 24 MB vendored tree is **not** committed to the repo by default (the OFF
> build never needs it). Obtain it per the ceremony doc before an ON build.

---

## 3. Build (ON) and run the BTC vector tests

```bash
cmake -S . -B build-otc3a -DSOST_BTC_HTLC_SIGNING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-otc3a -j"$(nproc)"
cd build-otc3a && ctest        # full suite green, BTC tests run the real backend
```

Targeted checks:

```bash
./build-otc3a/test-atomic-swap-btc-signing       # ON: 80 pass (incl. BIP-143 vectors)
./build-otc3a/test-atomic-swap-btc-script        # redeemscript byte layout
./build-otc3a/test-atomic-swap-btc-test-vectors  # BIP-173/350 + determinism
```

For comparison, the default OFF build runs the same `test-atomic-swap-btc-signing`
binary with **45** assertions, all checking that every backend function is
cleanly disabled (`ok=false`).

The signing happy-path vectors are anchored to the **BIP-143 native P2WSH**
test vector (privkey `b8f28a77…84c4580c` → compressed pubkey `036d5c20…14685f8`),
so a passing ON run is a known-answer test against the Bitcoin spec.

---

## 4. The HTLC primitives (SOST-side API)

All functions live in `sost::atomic_swap` (`include/sost/atomic_swap_btc.h`,
`include/sost/atomic_swap_btc_signing.h`):

| Step | Function | Notes |
|---|---|---|
| Redeem script | `BuildBtcHtlcRedeemScript(hashlock, refund_height, claim_pubkey, refund_pubkey)` | `OP_IF OP_SHA256 <H> OP_EQUALVERIFY <claim_pk> OP_CHECKSIG OP_ELSE <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <refund_pk> OP_CHECKSIG OP_ENDIF` |
| Witness program | `BtcHtlcWitnessProgram(redeem_script)` | `sha256(redeem_script)` |
| P2WSH address | `EncodeP2WSHAddress(witness_program, network)` | `network ∈ {mainnet, testnet, regtest}` → `bc/tb/bcrt` |
| Claim spend | `SignBtcHtlcClaim(lock_txid, lock_vout, lock_amount_sats, redeem_script, preimage, claim_privkey, claim_destination_addr, fee_sats, network)` | preimage path; returns `{ok, error, raw_tx_hex}` |
| Refund spend | `SignBtcHtlcRefund(lock_txid, lock_vout, lock_amount_sats, redeem_script, refund_height, refund_privkey, refund_destination_addr, fee_sats, network)` | CLTV path; sets `nLockTime` ≥ `refund_height` and a non-final input sequence |

The claim witness stack is `[sig+SIGHASH_ALL, preimage, 0x01(truthy→OP_IF), redeem_script]`;
the refund witness is `[sig+SIGHASH_ALL, <empty>(falsy→OP_ELSE), redeem_script]`.

The same `hashlock = sha256(preimage)` is shared with the SOST-side
`OUT_HTLC_LOCK` (OTC-1), which is how the two legs are bound.

---

## 5. End-to-end on Bitcoin regtest

Start regtest:

```bash
bitcoind -regtest -daemon -fallbackfee=0.0001 -txindex=1
bitcoin-cli -regtest createwallet swap
ADDR=$(bitcoin-cli -regtest getnewaddress)
bitcoin-cli -regtest generatetoaddress 101 "$ADDR"   # mature a coinbase
```

Swap roles: the **maker** (knows the secret) and the **taker**. Each side has a
keypair; derive compressed pubkeys with `DeriveBtcCompressedPubkey(privkey)`.

1. **Construct the lock.** Both sides agree on `hashlock = sha256(secret)`, the
   `refund_height` (a regtest block height comfortably after funding), and the
   two pubkeys. Build `redeem_script` and the P2WSH `bcrt1…` address.
2. **Fund the HTLC.** Send the agreed amount to the P2WSH address:
   ```bash
   LOCK_ADDR=bcrt1...          # from EncodeP2WSHAddress(..., "regtest")
   TXID=$(bitcoin-cli -regtest sendtoaddress "$LOCK_ADDR" 0.5)
   bitcoin-cli -regtest generatetoaddress 1 "$ADDR"
   VOUT=$(bitcoin-cli -regtest gettxout "$TXID" 0 >/dev/null && echo 0 || echo 1)
   ```
   Record `lock_amount_sats` (the exact output value) and `lock_vout`.
3. **Claim (taker, with the secret).** Build the signed claim tx and broadcast:
   ```bash
   # raw_tx_hex = SignBtcHtlcClaim(TXID, VOUT, lock_amount_sats, redeem_script,
   #                               preimage, claim_privkey, dest_addr, fee, "regtest")
   bitcoin-cli -regtest sendrawtransaction <raw_tx_hex>
   bitcoin-cli -regtest generatetoaddress 1 "$ADDR"
   ```
   The claim **reveals the preimage on-chain** in the witness.
4. **Refund (maker, if no claim before timeout).** Mine past `refund_height`,
   then build the refund tx (it carries `nLockTime ≥ refund_height` and a
   non-final sequence so CLTV passes):
   ```bash
   bitcoin-cli -regtest generatetoaddress 20 "$ADDR"
   # raw_tx_hex = SignBtcHtlcRefund(TXID, VOUT, lock_amount_sats, redeem_script,
   #                                refund_height, refund_privkey, dest_addr, fee, "regtest")
   bitcoin-cli -regtest sendrawtransaction <raw_tx_hex>
   ```
   A refund attempted before `refund_height` is rejected by the network
   (`non-final` / CLTV), which the builder’s locktime/sequence settings make
   verifiable in a regtest dry run.

---

## 6. Extracting the revealed preimage (cross-chain link)

When the BTC claim confirms, the preimage sits in the spending tx witness:

```bash
bitcoin-cli -regtest getrawtransaction <claim_txid> 2 \
  | jq -r '.vin[0].txinwitness[1]'      # witness item [1] = 32-byte preimage
```

That preimage is the secret the counterparty needs to unlock the **SOST** leg.
Feed it to the OTC-2 watcher, which verifies `sha256(preimage) == hashlock`
(`IngestRevealedPreimage`) and then auto-claims the SOST `OUT_HTLC_LOCK` via the
OTC-1 builders. On the SOST side, once that claim confirms, the OTC-2.5
`gethtlcstatus` RPC reports `status: claimed` and echoes the same
`revealed_preimage` — closing the loop symmetrically.

So the full SOST↔BTC regtest cycle is:

```
maker locks BTC (P2WSH) ── taker claims BTC with secret ── preimage on BTC chain
        │                                                          │
        └── maker also locks SOST (OUT_HTLC_LOCK) ◄── watcher reads preimage ──┘
                         │
                         └── watcher claims SOST leg (OTC-1 CLAIM) → gethtlcstatus: claimed
```

---

## 7. What is still NOT done (deferred past OTC-3a)

- **`SignBtcHtlcLockFunding`** remains a pure stub (funding a P2WSH from an
  arbitrary UTXO is left to `bitcoin-cli sendtoaddress` on regtest).
- **EVM leg** (`AtomicSwapHTLC.sol`) — OTC-3b.
- **External cryptographic review** + adversarial fee/locktime review before any
  consideration of flipping `SOST_BTC_HTLC_SIGNING` on outside a lab, and well
  before any discussion of `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`.
- Mainnet BTC and real broadcast remain out of scope.
