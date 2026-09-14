# Security policy

SOST is an experimental Layer-1 blockchain: ConvergenceX proof-of-work, nodes,
miners, transactions, wallet, explorer, DTD and DTD Jackpot, atomic swap, and
generic capsule proof anchoring. It is MIT-licensed and provided without
warranty.

## Reporting a vulnerability

Report privately to **sost@sostcore.com**, or through the contact form at
<https://sostcore.com/sost-contact.html>. Do not open a public issue for a
vulnerability that is not already public.

Please include:

- what is affected (node, miner, wallet, explorer, RPC, a specific consensus
  rule or a specific release);
- the version or commit you tested;
- a minimal reproduction, and the impact you believe it has;
- whether it is already public anywhere.

We will acknowledge the report and tell you what we intend to do about it. There
is no bug-bounty programme.

## Scope

In scope:

- consensus and block validation (`src/`), including the ConvergenceX
  proof-of-work path and the cASERT difficulty controller;
- the node, its P2P handling, its mempool and its RPC surface;
- the reference miner;
- wallet key handling, signing, and the capsule (proof-anchoring) path;
- the atomic-swap implementation;
- the public web surface: explorer, wallet page and the site under
  `website/`.

Out of scope:

- the value, liquidity or listing status of the token;
- third-party services the site merely links to;
- reports produced solely by an automated scanner with no demonstrated impact.

## What SOST does not claim

The consensus code has **not** been audited by an independent security firm. It
was deployed directly on mainnet and is being tested in public. Mining, running
a node, and any market activity are undertaken at the participant's own risk.

Only install binaries from the official repository and verify the published
SHA-256 hashes before running them.
