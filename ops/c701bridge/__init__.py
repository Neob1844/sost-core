"""C701 SOST Automated Bridge — off-chain verification engine prototype (DEVELOPMENT ONLY).

Nothing in this package touches SOST consensus, a production node, a production key or a public
chain. It reads SOST through the node's JSON-RPC (mocked fixtures in tests), issues EIP-712 mint
authorizations for the SOSTBridge contract, and keeps an idempotent SQLite ledger.
"""
