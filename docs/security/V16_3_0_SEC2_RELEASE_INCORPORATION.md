# sec2 — incorporation into the existing v16.3.0 release (no overwrite, no tag move)

**Do NOT execute without owner authorization.** This adds ONE asset (`sost-node-sec2`) to the
existing GitHub v16.3.0 release. The original assets (`sost-node`, `sost-node-sec1`,
`sost-miner`, `sost-cli`) and the `v16.3.0` tag stay exactly as published.

## Asset to add
| file | sha256 | note |
|---|---|---|
| `sost-node-sec2` | `5b50a448f3e319ef6137da61093750bd6d286cc508ff69fe994cf3532c4fa157` | NEW (sec1 + RPC hardening) |
| `SHA256SUMS.v16.3.0-sec2` | — | manifest (in repo: `docs/v16/`) |
| `sost-miner` | `2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2` | UNCHANGED — do not re-upload |
| `sost-cli` | `489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07` | UNCHANGED — do not re-upload |

## Build the asset (reproducible)
From branch `release/v16.3.0-sec1-rpc`, with a build dir named EXACTLY `build` INSIDE the source
tree (so `-ffile-prefix-map=<src>=/sost` normalizes both source and build paths):
```
cmake -S <src> -B <src>/build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build <src>/build --target sost-node -j
sha256sum <src>/build/sost-node   # MUST equal 5b50a448…
```
(Verified deterministic: two clean builds → identical hash; miner/cli reproduce v16.3.0 byte-for-byte.)

## Publish steps (GitHub release, manual)
1. Confirm the built `sost-node` hash == `5b50a448…`. If not, STOP (wrong build dir name/location).
2. Rename the artifact to `sost-node-sec2`.
3. On the EXISTING v16.3.0 release: *Edit release → add files* → upload `sost-node-sec2` and
   `SHA256SUMS.v16.3.0-sec2`. Do NOT delete/replace any existing asset. Do NOT retag.
4. Append to the release notes: sec2 is an urgent security revision (two unauthenticated RPC
   DoS fixed); node-only; miner/cli unchanged; sec2 supersedes sec1.

## Downloader verification procedure
```
# in an empty directory, with sost-node-sec2 and SHA256SUMS.v16.3.0-sec2 present:
sha256sum -c SHA256SUMS.v16.3.0-sec2      # -> sost-node-sec2: OK
# miner/cli unchanged from v16.3.0 — keep the ones you already verified.
```
