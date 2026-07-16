# ADR-007 — Opt-in wallet migration with legacy/PQ/hybrid coexistence

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

- **Status:** Provisional
- **Date:** 2026-07-02
- **Author:** NeoB

## Context

If a post-quantum spend type is ever activated (a separate future consensus
proposal — ADR-005), wallets must move users from legacy ECDSA addresses
(alg_id `0x00`) to PQ (`0x01`) or hybrid (`0x02`) addresses. The signature threat
model shapes the urgency: an adversary can collect public keys revealed on-chain
now and forge signatures later once a quantum computer exists (Shor recovers the
private key from the revealed public key). Funds at **revealed** pubkeys
(spent-from / reused addresses) are the exposed set; funds at **unrevealed**
pubkeys (never-spent, only the hash on-chain) are less exposed until spend time —
though the spend itself reveals the pubkey and a mempool front-running window
opens at that moment.

Migration must not break users who cannot or will not act: hardware wallets on
old firmware, exchange custody, and — critically — **dormant or lost coins whose
owners are absent**. A forced or automatic migration is therefore unacceptable.

## Decision

**Opt-in migration** with **legacy / PQ / hybrid coexistence**:

1. **Coexistence.** Legacy (`0x00`), PQ (`0x01`), and hybrid (`0x02`) addresses
   all remain spendable side by side; no address type is retired by fiat.
2. **User-initiated.** Migration is an explicit user action (move funds to a new
   PQ/hybrid address), never automatic.
3. **Clear warnings.** The wallet explains that spending from a legacy address
   reveals its public key (increasing long-run quantum exposure) and guides the
   user toward PQ/hybrid where activated.
4. **RPC/explorer labelling.** RPC responses and the explorer label each output's
   alg_id / scheme (legacy vs PQ vs hybrid) so users and integrators can see what
   they hold and what they are sending to — labelling must stay accurate
   (ADR-006).
5. **Protection against sending to incompatible clients.** The wallet guards
   against sending PQ/hybrid outputs to clients that cannot parse or spend them
   (capability signalling / address-format checks), to avoid stranding funds with
   a counterparty that cannot handle the new witness (ADR-003).

### Open problem: dormant / lost coins

Coins at addresses whose owners are absent (dormant, lost keys) **cannot be
migrated by their owners.** No wallet strategy solves this: only the key holder
can move funds to a PQ/hybrid address, and by definition they are not acting.
This is an acknowledged **open problem**, not something this ADR resolves.
Consensus-level responses (e.g. any form of forced sweeping) are out of scope and
are not proposed here.

## Alternatives considered

1. **Forced / automatic migration** (protocol sweeps legacy outputs into PQ
   form). **Rejected.** It breaks users who cannot act in time — dormant-coin
   holders, hardware wallets on old firmware, exchanges with cold custody — and
   it is a heavy, contentious consensus intervention. Automatic migration of
   funds a user did not authorise is fundamentally at odds with self-custody.
2. **Deprecate legacy addresses on a deadline.** Rejected: same breakage as
   forced migration for the dormant/absent set, plus it invents a date, which the
   V3 rules forbid.
3. **PQ-only new addresses, no hybrid option.** Rejected as the default: hybrid
   (ADR-002) is the safer transition mode; users should be able to choose hybrid
   during the migration window.

## Pros

- Respects self-custody: no funds move without the owner's action.
- No breakage for hardware-wallet, exchange, or dormant-coin users.
- Clear labelling and incompatible-client protection reduce foot-guns and
  stranded funds.
- Hybrid coexistence lets cautious users hold defence-in-depth during transition.

## Risks

- Opt-in means slow adoption: many revealed-pubkey legacy outputs may remain
  un-migrated, staying exposed under the signature threat model.
- The dormant/lost-coin exposure is unresolved and unresolvable at the wallet
  layer — an honest, standing limitation.
- Incompatible-client protection depends on reliable capability signalling; gaps
  could still strand funds if a counterparty misreports support.
- Spending to migrate reveals the pubkey and opens a mempool front-running window
  at spend time — timing/UX guidance needed if/when activated.

## Consensus impact

**NONE now — wallet/UX strategy only, activates nothing.** The migration flow
presupposes a PQ spend type that is not active (`PQ_ACTIVATION_HEIGHT =
INT64_MAX`). Any protocol behaviour it references would be a separate future
consensus proposal (ADR-005); the rejected forced-migration alternative would be
a consensus change and is explicitly not proposed.

## Notes

- Coexistence relies on the alg_id registry (ADR-001) and the versioned witness
  (ADR-003); labelling accuracy relies on the docs/claims discipline (ADR-006).
- ML-KEM (FIPS 203) is a KEM, not a signature scheme, and plays no role in spend
  migration.
- Prior iteration: docs/PQ_MIGRATION_V2.md (PR #37), superseded by V3.
