# V15 OTC — Founder Test Runbook (Atomic Swap HTLC)

> **FOUNDER-ONLY · UNAUDITED · DO NOT USE PUBLICLY.** This feature is technically active
> but has had **no external audit**. Real swaps can cause **permanent loss of funds**. Do
> not announce "safe to use" until an audit is complete. This runbook is a safe,
> reproducible test procedure — it does **not** execute anything by itself.

**Status (verified at ~block 16,080):**
- **V14.5 ACTIVE** on mainnet — HTLC LOCK + CLAIM + REFUND accepted on the block path
  (activation `V14_5_HEIGHT = 16000`, consensus fix commit `3272b1f5`, 2026-06-28).
- **Node ready** — running a post-fix binary (built after 2026-06-28), synced, HTLC RPCs
  present. **No node restart or recompile is required to test.**
- **EVM leg contract NOT deployed** — `AtomicSwapHTLC.sol` is not deployed on any mainnet
  EVM chain. The full cross-chain leg therefore requires deploying it (testnet first).
- **SOST↔BTC = OFF** (deferred to V15, ~block 20,000). Do not test BTC.

**The key insight — you can test on mainnet TODAY without the EVM contract:**
a **self-swap** locks a tiny amount of SOST in an HTLC where **both `claim_pkh` and
`refund_pkh` are YOUR OWN addresses**. No counterparty, no theft risk: worst case you
wait for the timeout and REFUND your own funds back. This exercises the real mainnet SOST
HTLC end-to-end without any EVM contract and without trusting anyone.

Units: **1 SOST = 100,000,000 stocks**. `*_pkh` = 40 hex. `hashlock`/`preimage` = 64 hex.

---

## Test order (do them in this order — do NOT skip ahead)

```
Stage 0  OFFLINE            zero risk        prove the logic (tests + coordinator rehearsal)
Stage 1  REFUND-FIRST       safest live      lock → do NOT reveal secret → wait → refund → Refunded
Stage 2  HAPPY-PATH         live             lock → claim with secret → Claimed
Stage 3  CROSS-CHAIN EVM    advanced         only after 0–2, EVM testnet first, contract deploy required
```

Stages 1–2 run first on **regtest** (throwaway node), then as a **mainnet self-swap**
with a **tiny** amount and **both legs your own addresses**.

---

## Rules (non-negotiable)

- **Use `otc-coordinator`** to create sessions; it enforces the timelock discipline
  **T1 (SOST refund) > T2 (EVM refund)**, margin ≥ 6 blocks. **Never set timelocks by hand.**
- **Never reveal the secret** (`preimage`) until you have **seen the counterparty's LOCK
  confirmed** on its chain. On a self-swap there is no counterparty, so this is moot — but
  keep the habit.
- **Never execute a mainnet swap automatically** — every mainnet step is manual and
  reviewed with `decodehtlc` before broadcast.
- **Never paste a private key into chat, a ticket, a doc or a shared shell.** Keep keys
  local to your machine only.
- Do **not** touch consensus, the node, the Gold Vault or PoPC to run this.
- **Refund-first, always.** Prove you can get funds back before you risk the claim path.

---

## Stage 0 — OFFLINE validation (zero risk, do this first)

No funds move, no mainnet. Proves the consensus rules and the coordinator work.

```bash
cd ~/SOST/sostcore/sost-core
# consensus + atomic-swap module tests (use any already-built mainnet build dir)
( cd build && ctest -R atomic-swap --output-on-failure )

# end-to-end coordinator rehearsal (offer → lock → claim → Completed, plus refund + negatives)
BUILD=build bash scripts/otc_rehearsal_sost_local.sh
```
Expect `100% tests passed` and the phases `Completed` / `Refunded` / `TIMEOUT_ORDER_INVALID`.

---

## Generate the secret + hashlock (initiator only)

```bash
SECRET=$(openssl rand -hex 32)                                   # keep PRIVATE
HASHLOCK=$(python3 -c "import hashlib,sys;print(hashlib.sha256(bytes.fromhex(sys.argv[1])).hexdigest())" "$SECRET")
echo "HASHLOCK (public, goes in the LOCK): $HASHLOCK"
# Do NOT echo SECRET anywhere shared. Anyone who sees it on-chain can complete the other leg.
```

---

## SOST-side CLI reference (exact signatures — verified against `src/atomic_swap_helpers.cpp`)

Every `create*/claim*/refund*` returns an **unsigned** tx (`{"raw_tx_hex":"…"}`); sign with
`sost-signtx`, then broadcast with `sendrawtransaction`.

```bash
# LOCK (10 params): spend one of your UTXOs into an HTLC output
sost-cli createhtlclock <prev_txid> <prev_vout> <prev_amount> <prev_pkh> \
                        <hashlock> <refund_height> <claim_pkh> <refund_pkh> \
                        <lock_amount> <fee>

# CLAIM (7 params): reveal the preimage, before refund_height
sost-cli claimhtlc <lock_txid> <lock_vout> <lock_amount> <preimage> \
                   <claim_destination_pkh> <marker_dust_amount> <fee>

# REFUND (5 params): recover your funds, at/after refund_height
sost-cli refundhtlc <lock_txid> <lock_vout> <lock_amount> <refund_destination_pkh> <fee>

# INSPECT an unsigned tx BEFORE broadcasting (verify hashlock / refund_height / pkhs)
sost-cli decodehtlc <raw_tx_hex>

# STATE (read-only)
sost-cli gethtlcstatus <lock_txid> <lock_vout>   # Unknown|Locked|Expired|Claimed|Refunded
sost-cli listhtlclocks

# SIGN then BROADCAST
sost-signtx <unsigned_hex> <privkey_hex32> <spent_amount_stocks> <spent_type> [input_index=0]
#   spent_type: 0  = normal UTXO input (the input that FUNDS the LOCK)
#               18 = OUT_HTLC_LOCK (0x12) — the UTXO a CLAIM or REFUND spends
sost-cli sendrawtransaction <signed_hex>
```

Signing per step: LOCK → `... <prev_amount> 0` · CLAIM → `... <lock_amount> 18` · REFUND → `... <lock_amount> 18`.

---

## Stage 1 — REFUND-FIRST (the safest live test)

Prove you can always get funds back **before** you ever rely on the claim path.

**1a. On regtest first** (throwaway node; the mainnet binary/constant is unchanged):
```bash
cmake -S . -B build-regtest -DSOST_TESTNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-regtest --target sost-node sost-cli sost-signtx -j$(nproc)
# start the regtest node, mine past the HTLC activation height, then run the sequence below.
```

**1b. The refund sequence** (regtest, then a mainnet self-swap with a tiny amount):
```
1. refund_height = current_height + ~30      # short, so you don't wait days (~10 min/block)
2. createhtlclock ... claim_pkh=<YOURS> refund_pkh=<YOURS> ...   # both legs yours
3. decodehtlc <raw>        # VERIFY hashlock / refund_height / pkhs before broadcast
4. sost-signtx <raw> <privkey> <prev_amount> 0  →  sendrawtransaction
5. gethtlcstatus <lock_txid> 0   → Locked
6. Do NOT reveal the secret. Try refundhtlc BEFORE refund_height → it MUST FAIL (rule R24).
7. Wait until height ≥ refund_height, then refundhtlc → sign (type 18) → sendrawtransaction
8. gethtlcstatus → Refunded   ✅ funds are back
```
Confirming that **REFUND before the timeout FAILS** is a core safety guarantee — verify it.

---

## Stage 2 — HAPPY-PATH / CLAIM (after Stage 1 passes)

```
1. createhtlclock ... claim_pkh=<YOURS> refund_pkh=<YOURS> ...   # self-swap on mainnet
2. decodehtlc → verify → sign (type 0) → sendrawtransaction → gethtlcstatus = Locked
3. claimhtlc <lock_txid> 0 <lock_amount> <SECRET> <claim_dest_pkh=YOURS> <dust> <fee>
4. sign the claim (type 18) → sendrawtransaction
5. gethtlcstatus → Claimed, and revealed_preimage == your SECRET   ✅ atomic swap works
```
Also verify a **wrong preimage CLAIM FAILS** (rule R21). On mainnet keep the amount tiny
(e.g. ~1 SOST) and both legs your own addresses.

---

## Stage 3 — CROSS-CHAIN SOST ↔ EVM (advanced; only after 0–2)

The EVM contract is **not deployed** yet, so this starts on an **EVM testnet** (Anvil/Sepolia
or BNB testnet). Use `otc-coordinator` to bind the two legs and enforce **T1 > T2**.

```bash
# Deploy the EVM HTLC (once per network) — testnet first
cd contracts/atomic-swap && forge install foundry-rs/forge-std && forge build
forge create src/AtomicSwapHTLC.sol:AtomicSwapHTLC --rpc-url $RPC --private-key $PK --broadcast
# → record the deployed address as $HTLC

# Coordinator session (enforces T1 SOST > T2 EVM, margin ≥ 6)
otc-coordinator create swap.json --role Initiator --cp ETH --give SOST --want ETH \
  --give-amount <stocks> --want-amount <wei> --hashlock <64hex> --secret <64hex> \
  --t1 <sost_refund_height> --t2 <evm_refund_block>
otc-coordinator inspect swap.json                    # redacts the secret
otc-coordinator next swap.json --height <current>    # tells you the safe next action

# EVM leg (native ETH/BNB — NOT a freezable token)
cast send $HTLC "lockNative(bytes32,bytes32,uint256,address,address)" \
  $SWAPID $HASHLOCK $T2 $CLAIMER $REFUNDER --value <tiny> --rpc-url $RPC --private-key $LOCKER_PK
cast send $HTLC "claim(bytes32,bytes32)" $SWAPID $SECRET --rpc-url $RPC --private-key $ANY_PK
cast send $HTLC "refund(bytes32)" $SWAPID --rpc-url $RPC --private-key $ANY_PK   # after T2
```

**Reference rehearsals:** `scripts/otc_rehearsal_evm_anvil.sh`, and guides
`docs/V15_OTC_E2E_SWAP_GUIDE.md`, `docs/V15_OTC_EVM_TESTNET_GUIDE.md`.

### Mainnet cross-chain template (founder-only, last)
- **Native ETH or BNB only, minuscule amount.**
- **Do NOT use USDT / USDC / PAXG / XAUT** for these first tests: the issuer (Tether /
  Circle / Paxos) can **freeze** the escrowed tokens mid-swap, breaking atomicity at the
  asset level — not a code bug, an asset-level risk. Lock a freezable token only after the
  flow is proven and never as the first-mover leg.
- Deploy the EVM contract on the real chain first, verify it, then run one tiny swap.

---

## GO / NO-GO checklist (before ANY live step)

- [ ] Stage 0 (offline) passed — `100% tests passed` + coordinator `Completed`/`Refunded`.
- [ ] Node synced, height > 16,000, HTLC RPCs answer (`listhtlclocks` returns).
- [ ] Amount is **tiny**; on mainnet **both legs are your own addresses** (self-swap).
- [ ] `refund_height` is short and sane; verified with `decodehtlc` before broadcast.
- [ ] REFUND-before-timeout **fails** (R24); wrong-preimage CLAIM **fails** (R21) — confirmed.
- [ ] `otc-coordinator` shows **T1 > T2** (margin ≥ 6) for any cross-chain swap.
- [ ] No private key was pasted anywhere shared.
- [ ] BTC not touched (V15, off).
- [ ] Not announcing "safe to use" — feature is unaudited.

If any box is unchecked → **NO-GO**.

---

## How funds are lost (avoid every one of these)

| Failure | Cause | Prevention |
|---|---|---|
| **Premature secret reveal** | Revealing `preimage` before the counterparty's LOCK is confirmed | Never reveal until you see their LOCK on-chain (moot on a self-swap) |
| **Inverted timelocks (T2 ≥ T1)** | Responder refund opens after yours → you can be stranded | Use `otc-coordinator` (it rejects this); never set by hand |
| **Claim too late** | `refund_height` passes before your CLAIM confirms (R22) | Claim early; leave a 1–2 block confirmation buffer |
| **Wrong hashlock** | `sha256(preimage)` differs between legs | Compute once, use identically; `decodehtlc` to verify |
| **Issuer token freeze** | USDT/USDC/PAXG/XAUT frozen mid-swap | Test with native ETH/BNB; never lock a freezable token first |
| **Wrong signing type/key** | Signing a CLAIM/REFUND with type 0, or wrong key | LOCK input = type 0; CLAIM/REFUND = type 18; key must match the pkh |
| **Reorg confusion** | Acting on an unconfirmed leg | Wait ≥ 3 confirmations before advancing to the next leg |

**The safety net:** in a self-swap, if anything goes wrong you **always** recover via REFUND
after the timeout. The worst case is waiting, not loss.

---

## What to verify before going to mainnet cross-chain

1. Stages 0–2 all green (offline, regtest refund, regtest+mainnet self-swap claim).
2. EVM contract deployed and verified on the chosen network; you can `lockNative` / `claim`
   / `refund` on **testnet** cleanly.
3. `otc-coordinator next` gives sane guidance at every height; T1 > T2 confirmed.
4. Amounts are tiny; native asset only; both-your-addresses where possible.
5. A written recovery plan: which REFUND you run, at which height, if a leg stalls.

---

## Troubleshooting

- **"Atomic Swap HTLC is disabled until protocol activation"** → below activation height
  (regtest: mine more; mainnet: already active > 16,000).
- **CLAIM rejected** → preimage mismatch (R21) or past `refund_height` (R22).
- **REFUND rejected** → not yet at `refund_height` (R24); wait.
- **Funds seem stuck** → in a self-swap you always recover with REFUND after the timeout.
- State any time: `gethtlcstatus` / `listhtlclocks`.

Related: `docs/ATOMIC_SWAP_FOUNDER_TEST_GUIDE.md`, `docs/ATOMIC_SWAP_CLI_GUIDE.md`,
`docs/V15_OTC_E2E_SWAP_GUIDE.md`, `docs/V15_OTC_EVM_TESTNET_GUIDE.md`,
`docs/ATOMIC_SWAP_V14_MINER_DISCLOSURE.md`.
