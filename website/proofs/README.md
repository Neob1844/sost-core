# SOST public proofs

This folder holds **public cryptographic commitments**. Each commitment is a small
JSON file of hashes and aggregate metadata.

## What a commitment proves
- **Integrity + temporal precedence**: that a sealed dataset existed, unchanged,
  with exactly these fingerprints, at a stated time (and, once anchored on the
  SOST chain, at a verifiable block timestamp).

## What a commitment does NOT contain or prove
- It contains **no** private data: no raw records, no identifiers, no Merkle
  leaves and no inclusion proofs.
- It proves nothing about the *content* of the sealed dataset — only that the
  dataset it fingerprints has not changed since it was sealed.

## How anchoring works

A file is hashed with SHA-256, the hash is written into a SOST capsule, and the
capsule is confirmed in a block. From then on the block timestamp is a public,
immutable lower bound on when that exact file existed. The chain never sees the
file itself, only its hash.

This is a general-purpose blockchain utility: it works the same way for a
document, a software release, an audit record or any other digital artefact.
