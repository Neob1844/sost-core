Synthetic fixtures in the exact JSON shapes printed by src/sost-node.cpp (handle_gettransaction,
handle_gettxout, handle_getaddressutxos). Not captured from mainnet; no real addresses or txids.
Amounts are unquoted 8-decimal JSON numbers: parse with Decimal, never float.
