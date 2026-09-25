# How to incorporate the hardened node into the EXISTING v16.3.0 release
## Security revision "sec1" — no new version number, tag not moved, originals preserved

Goal: ship V1–V6 (+ P4 parser extraction) as an **identifiable security revision of v16.3.0**,
not a new version. `sost-miner` and `sost-cli` are unchanged (hashes still match), so only the
node gets a revised artifact. The published `v16.3.0` tag and its original binaries stay exactly
as they are — the revision is *added*, never substituted silently.

## Identity of the revision

| Field | Value |
|---|---|
| Public version (unchanged) | **v16.3.0** |
| Revision label | **sec1** |
| Source commit (node build) | **1a675744** (P4 parser extraction; V1–V6). Tests/docs land on top but do not change the node binary. |
| New `sost-node` SHA-256 | `d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213` |
| Original `sost-node` SHA-256 (kept) | `304d056d504960b4179543672f14bee28146788b985363a5e95d476cc6b1492e` |
| `sost-miner` / `sost-cli` | unchanged (`2ef9d0a7…` / `489f4374…`) |

## What NOT to do
- Do **not** move or re-create the `v16.3.0` git tag (it stays at `ec2bea2c`).
- Do **not** overwrite or delete the original release assets (`sost-node` 304d056d, `SHA256SUMS`).
- Do **not** bump the public version to v16.3.1.

## Recommended mechanism (Option A — augment the existing release)

1. **Merge** `feat/fork-store-hardening` → `main` (a normal merge commit; no history rewrite).
2. **Annotated tag** for traceability of the revision, clearly a revision *of* v16.3.0 — e.g.
   `v16.3.0-sec1` at the merge commit. This is a revision label, not a new minor version, and it
   leaves `v16.3.0` untouched.
3. On the **existing v16.3.0 GitHub release**, keep every original asset and **add**:
   - `sost-node-sec1`  (the hardened node, `d3212aea…`) — a *distinct filename* so the original
     `sost-node` (`304d056d…`) is still downloadable side-by-side.
   - `SHA256SUMS.sec1` (this repo's `docs/v16/SHA256SUMS.v16.3.0-sec1`).
   - Edit the release **body** to add a "🔒 Security revision sec1" section: new node hash, source
     commit `1a675744`, the six fixes, "miner & CLI unchanged", and the swap-node procedure.
4. **Traceability note in the release body:** the original `sost-node` (`304d056d`) remains the
   artifact of the initial v16.3.0 cut; `sost-node-sec1` (`d3212aea`) is the security-revised node.
   Operators verifying an already-downloaded original binary still match the original SHA-256.

### Alternative (Option B)
A separate release under tag `v16.3.0-sec1`, cross-linked from the v16.3.0 release. Cleaner asset
separation, two pages. Option A matches "one public v16.3.0 with an identifiable revision" better.

## Verification a downloader runs (either option)
```
sha256sum sost-node-sec1     # must equal d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213
```
Source rebuild (reproducible): build commit `1a675744` in a dir named `build`, Release, SBPOW=ON,
TESTNET_FORKS=OFF → same hash.

## Web / Explorer / BitcoinTalk (only after the revision is published)
Keep the version string **v16.3.0** everywhere; add a "security revision sec1" note and the new
node SHA-256. Bump the shared banner cache-bust (`?v=v478` → `v479`) so browsers refetch. Do not
announce a new version. The three-fixes list in the BitcoinTalk post gains the SIGPIPE availability
fix and the fork/orphan-store hardening; the node hash line shows both the original and sec1 hashes.

## Release-body text to add to the existing v16.3.0 release (point 7)

Prepend this block at the TOP of the v16.3.0 release description (original text kept below it):

```markdown
> ## 🔒 Security revision — sec1 (node-only, non-consensus)
> A hardened node is available as an **additional** asset on this release. It fixes an
> availability DoS (a peer closing a socket mid-write could kill the node via SIGPIPE) plus
> fork/orphan-store resource-exhaustion hardening. **No consensus rule changes**; activation is
> still automatic at #30,000 and the first DTD Jackpot V2 is still #30,186.
>
> - **New node:** [`sost-node-sec1`](https://github.com/Neob1844/sost-core/releases/download/v16.3.0/sost-node-sec1)
>   · SHA-256 `d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213`
>   · manifest [`SHA256SUMS.sec1`](https://github.com/Neob1844/sost-core/releases/download/v16.3.0/SHA256SUMS.sec1)
> - **Source of the revision:** tag [`v16.3.0-sec1`](https://github.com/Neob1844/sost-core/tree/v16.3.0-sec1)
> - **`sost-miner` and `sost-cli` are unchanged** (same SHA-256 as v16.3.0) — swap only the node.
> - The **original** `sost-node` (`304d056d…`) and `SHA256SUMS` remain on this release for
>   traceability. Verify and install `sost-node-sec1` per the operator guide.
```

The original `v16.3.0` tag, the original `sost-node` asset, and the original `SHA256SUMS` are
left byte-for-byte intact. The GitHub "Source code (zip/tar.gz)" attached to the `v16.3.0` tag
still contains the original source; to build the revised node, check out tag `v16.3.0-sec1`.
