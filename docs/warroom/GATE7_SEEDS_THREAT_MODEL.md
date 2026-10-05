# Gate 7 — seeds.txt threat model

**seeds.txt is TRUSTED LOCAL OPERATOR CONFIGURATION, not data received from peers.**
It is read only from `<datadir>/seeds.txt` (the directory of the operator's `--chain` path),
exactly like bitcoind's `addnode=`. It is never fetched, never written by the node, and never
overwritten from the network. Verified against `load_extra_seeds()` (src/sost-node.cpp):

| Property | Enforcement | Verdict |
|----------|-------------|---------|
| Local file only, operator-owned | `config_dir_of(chain_path)+"/seeds.txt"`; `fopen("r")` only | PASS |
| No automatic remote overwrite | node never writes seeds.txt (only peers.txt, a separate cache) | PASS |
| Max number of entries | loop bounded `out.size()<64` | PASS (≤64) |
| Max line length | `char line[256]`, fgets-bounded | PASS (≤255 bytes) |
| Hostname length bound | inherited from the 256-byte line bound | PASS |
| Invalid lines ignored safely | blank / `#` comment skipped; control-char lines rejected | PASS |
| Port validation | `port>0 && port<65536`, else default 19333 | PASS |
| No command injection / no shell | parsed with fgets + string ops; passed to getaddrinfo(), never a shell | PASS |
| No SSRF screen needed | operator-trusted: an operator listing an internal host is intentional | N/A (by design) |

seeds.txt entries are dialed as operator-trusted sources and therefore BYPASS the
gossip SSRF/DNS screen (`gossip_target_ok`) — that screen applies only to addresses a
*peer* gossips to us (ADDR), never to operator config. This separation is the core of the
D2 trust model: **operator config is trusted; peer gossip is not.**
