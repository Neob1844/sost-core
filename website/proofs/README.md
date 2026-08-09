# SOST public proofs

This folder holds **public cryptographic commitments**. Each commitment is a small
JSON file of hashes and aggregate metadata.

## What a commitment proves
- **Integrity + temporal precedence**: that a sealed dataset existed, unchanged,
  with exactly these fingerprints, at a stated time (and, once anchored on the
  SOST chain, at a verifiable block timestamp).

## What a commitment does NOT contain or prove
- It contains **no coordinates, no individual scores, no target names, no Merkle
  leaves, no inclusion proofs, no keys and no credentials** — only hashes, counts
  and a general regional breakdown.
- It does **not** prove that any mineralisation exists.
- It is **not** a resource or reserve estimate.

## `ree-prospective-v04-20260616_commitment.json`

> **Historical / legacy research anchor.** This commitment was made by a
> third-party research operator in June 2026. It is preserved as an immutable
> historical record and is **not** a current integration or an ongoing
> relationship with any external platform. The commitment file and its anchor
> receipt are kept byte-for-byte intact: `commitment.json` hashes to the value
> committed on chain, so it is never edited. Any brand name still appearing
> inside those files is part of the sealed record itself, not a live reference.

Public commitment for a sealed REE prospective campaign (model E,
relative regional rank). The underlying campaign remains **unresolved**; its
targets stay private and encrypted. Prospective validation will follow the
published resolution protocol over a multi-year horizon. The single number that
matters publicly is the `merkle_root`; the full target set is not disclosed.
