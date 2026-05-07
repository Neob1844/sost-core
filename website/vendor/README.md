# website/vendor — pinned third-party JS

The Beacon explorer banner verifies signed network notices in the browser.
Verification uses a **vendored**, version-pinned, hash-pinned copy of
`@noble/secp256k1`. **Never load from a CDN at runtime.**

## What's here

| File | Upstream | Version | Source URL | Purpose |
|---|---|---|---|---|
| `noble-secp256k1-2.2.3.js` | `@noble/secp256k1` | 2.2.3 | `https://cdn.jsdelivr.net/npm/@noble/secp256k1@2.2.3/index.js` | secp256k1 ECDSA verification (used by `website/js/beacon.js`) |

Pinned content hashes: see `HASHES.txt`.

## Verification

```bash
cd <repo-root>/website/vendor
sha256sum -c HASHES.txt
```

Output must be `OK` for every line. Any drift means either the file was
tampered or the pin needs an explicit, reviewed bump.

## Re-fetching (only when intentionally upgrading)

`scripts/beacon-vendor-fetch.sh` downloads from the upstream URL and refuses
to overwrite the existing file unless the new download matches the pinned
hash. Bumping a version is therefore a deliberate two-step:

1. Delete the old vendored file.
2. Run `scripts/beacon-vendor-fetch.sh` with the new version (edits required
   in the script itself — the version is hardcoded for auditability).
3. Update `HASHES.txt` with the new hash.

This intentionally makes "silently bumping noble" impossible.

## Why vendor instead of `import` from CDN

If the explorer fetched `@noble/secp256k1` from jsdelivr/unpkg at page load:

- A CDN compromise would let an attacker replace the verification routine
  with one that returns `true` for any signature — bypassing the entire
  Beacon trust model.
- A CDN outage would silently disable signature checking (at best, no
  banners; at worst, fail-open if the integration is sloppy).
- Subresource Integrity (SRI) on the script tag would help, but ESM
  `import` does not support SRI today.

Vendoring + hash-pinning + an explicit re-fetch ritual closes all three.
