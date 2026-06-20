# Atomic Swap — CLI usage guide (founder / private)

For SOST ↔ EVM (ETH/BNB/USDT/USDC/PAXG/XAUT) cross-chain atomic swaps via `sost-cli`, once the
HTLC gate is active (V14 / block 15,000). **SOST ↔ BTC is NOT active (V15).** The CLI builders
produce **unsigned** transactions; you sign + broadcast as a separate step. Active only at
height ≥ 15,000 — before that every builder prints the disabled message.

> Do NOT publicise this. The atomic swap is in founder testing and unaudited. Test with the
> SMALLEST possible amounts first. A wrong hashlock / timeout / pkh can lock funds until refund.

## 0. Concept (hash-time-locked, trustless)
You and a counterparty each lock funds on your own chain under the SAME hashlock `H = sha256(S)`,
with timeouts. You reveal the secret `S` to claim their side; that reveal lets them claim your
side. If anyone aborts, both refund after their timeout. No custodian.

Your side = SOST (this CLI). Their side = the EVM `AtomicSwapHTLC` contract (`contracts/atomic-swap/`).

## 1. The secret + hashlock (you, the initiator, generate it)
- Pick a random 32-byte secret `S` (keep it private until you claim).
- `H = sha256(S)` is the hashlock both locks use.
- (Use any secure RNG; record `S` and `H`. Never reuse a secret.)

## 2. SOST CLI commands (exact syntax — `sost-cli <cmd> ...`)
```
createhtlclock <prev_txid> <prev_vout> <prev_amount> <prev_pkh>
               <hashlock> <refund_height> <claim_pkh> <refund_pkh>
               <lock_amount> <fee>          -> unsigned HTLC LOCK tx (hex)

claimhtlc  <lock_txid> <lock_vout> <lock_amount> <preimage>
           <claim_dest_pkh> <marker_dust_amount> <fee>   -> unsigned CLAIM tx (hex)

refundhtlc <lock_txid> <lock_vout> <lock_amount>
           <refund_dest_pkh> <fee>          -> unsigned REFUND tx (hex)

decodehtlc <raw_tx_hex>                      -> decode/inspect any HTLC tx
gethtlcstatus <lock_txid> <lock_vout>        -> lock status from the node (read-only)
listhtlclocks                                -> all open HTLC locks on chain (read-only)
```
- `refund_height` = the block height after which YOU can refund your SOST lock. Set it LATER than
  the counterparty's EVM timeout (so you only refund if they never locked/claimed). The claimer
  must claim strictly BEFORE `refund_height` (rule R22); you can refund only at/after it (R24).
- `*_pkh` = 20-byte pubkey-hash hex of the relevant party. `hashlock`/`preimage` = 32-byte hex.

## 3. Happy-path flow (SOST → EVM example, small test amounts)
1. Generate `S`, compute `H = sha256(S)`.
2. **Lock SOST:** `sost-cli createhtlclock <your_utxo...> <H> <refund_height> <their_claim_pkh> <your_refund_pkh> <lock_amount> <fee>` → sign → broadcast (`sost-cli sendrawtransaction <signed_hex>`). Note the resulting `lock_txid`.
3. **Verify on chain:** `sost-cli gethtlcstatus <lock_txid> 0`.
4. **Counterparty locks EVM** in `AtomicSwapHTLC` with the SAME `H` and an EARLIER timeout. Confirm their lock on the EVM explorer (amount + hashlock match) before continuing.
5. **You claim the EVM side** by revealing `S` to the contract's `claim` (this publishes `S` on the EVM chain).
6. **Counterparty claims your SOST** using the now-public `S`: `claimhtlc <lock_txid> 0 <lock_amount> <S> <their_dest_pkh> <marker_dust> <fee>` → sign → broadcast.
7. Done. `gethtlcstatus` shows the lock spent by a CLAIM (preimage revealed).

## 4. Refund (recovery) — if the swap aborts
- **Your SOST lock:** only after `refund_height` passes: `refundhtlc <lock_txid> 0 <lock_amount> <your_refund_pkh> <fee>` → sign → broadcast. Rejected before timeout (R24).
- **Their EVM lock:** they call the contract's `refund` after their own timeout.
- Golden rule: set your `refund_height` LATER than their EVM timeout, so you never refund while they can still claim.

## 5. Safety checklist before each real swap
- [ ] Smallest viable amounts on the first swaps.
- [ ] `H` identical on both chains; `S` never revealed early.
- [ ] Your `refund_height` > their EVM timeout, with margin.
- [ ] Counterparty's lock confirmed (amount + hashlock) before you reveal `S`.
- [ ] `decodehtlc` your own unsigned tx to confirm fields before signing.
- [ ] `gethtlcstatus` / `listhtlclocks` to track state at each step.

## 6. Status / troubleshooting
- `gethtlcstatus <lock_txid> <vout>` — open / claimed (preimage) / refunded / spent.
- `listhtlclocks` — all open locks (sanity check yours appears).
- Builder prints "disabled until protocol activation" → height < 15,000 (gate not yet active).
