# SOST DEX V2 — lab relay

`dex_lab_relay.py` is a **localhost-only** bridge so `website/sost-dex-v2.html` can start a
laboratory swap and observe its REAL state (to COMPLETED or REFUNDED) against SOST devnet +
Bitcoin regtest + Anvil. TEST MODE — never real funds, never mainnet.

## Security model (deliberate)
- Fixed, tiny endpoint set (`/api/health`, `POST /api/swap/start`, `GET /api/swap/<id>`). **No
  endpoint executes a command built from client input.** The orchestration is a FIXED argv-array
  subprocess of an already-tested harness — never a shell string from the browser.
- **State is never trusted from a file or the browser.** Every milestone is re-derived by querying
  the actual nodes (txid confirmations + amount/address checks). A bogus txid does not verify.
- The browser sends **no private keys or seeds**; lab signing keys are server-side TEST fixtures.
- Binds `127.0.0.1` only.

## Run
```
DEX_LAB_BTC_CLI="/path/bitcoin-cli -regtest -datadir=<dd> -rpcuser=rt -rpcpassword=rt -rpcport=18443" \
DEX_LAB_SOST_RPC=http://127.0.0.1:18296/ \
DEX_LAB_ANVIL_RPC=http://127.0.0.1:8545/ \
DEX_LAB_HARNESS=/abs/path/xswap_sost_btc_coordinated.sh \
python3 dex_lab_relay.py            # http://127.0.0.1:8781
```

## Verified
`relay_verify_test.py <funding_txid> <claim_txid>` proves the on-chain verification logic against a
live regtest: real txids resolve to their actual confirmations, a **bogus txid is rejected**, and
`derive_state` computes the correct milestone from verified facts. (Run in foreground.)

## Note on this sandbox
The relay serves correctly in the foreground. In THIS build sandbox, long-lived background
processes are killed by a low `RLIMIT_FSIZE` (SIGXFSZ) imposed on background tasks — a sandbox
limit, not a defect of the relay; a normal operator machine runs it persistently without that cap.
The dashboard client degrades gracefully to "lab relay not running" when the relay is absent.
