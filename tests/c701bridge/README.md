# C701 bridge engine tests (development only)

    python3 -m pytest -q tests/c701bridge            # engine unit tests (fixture-backed SOST RPC, MockEth)
    (cd contracts/bridge && forge test)              # Solidity suite
    (cd contracts/bridge && forge build) && python3 tests/c701bridge/e2e_anvil.py   # real bytecode on a local Anvil

The E2E starts its own Anvil on 127.0.0.1:8557 (chainId 31337), refuses a busy port, refuses any
other chain id, and stops Anvil on exit. Keys are Anvil's public development keys: TEST ONLY.
