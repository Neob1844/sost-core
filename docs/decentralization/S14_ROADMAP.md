# S14 Roadmap — Restricted Developer Mode

> **Status: documentation only.** This file describes the current state of the
> S14 gate and the prerequisites that would have to be met before it could be
> reduced or removed. It changes no code, no configuration, and no consensus
> rule. **No artificial date is set.**

---

## 1. What S14 is (current state)

**S14 = RESTRICTED DEVELOPER MODE** — a protocol-level admin-authority gate.

- **Activation.** S14 activates with the `V30000` hardfork at block **#30,000**.
- **Scope of the gate.** While S14 is active, **every** native-asset /
  tokenization / SOST-layer-DEX operation must carry an input authorised by the
  admin key (`ADMIN_AUTHORITY_PKH`). Any such operation that is not so
  authorised is **rejected by consensus** with reject code
  `S14_RESTRICTED_DEV_MODE = 214`.
- **Fail-closed.** The gate is fail-closed: an all-zero authority
  (`ADMIN_AUTHORITY_PKH` unset / all zeros) **disables the gated feature set
  entirely** rather than opening it. There is no "open by default" state.
- **Public access is DISABLED.** There is **no** CLI, RPC, or browser bypass of
  the gate. The gated capabilities are not publicly usable while S14 is active.
- **Web dashboards.** The web dashboards that surface these capabilities
  additionally enforce server-side authentication (bcrypt over HTTPS). This is
  an operational layer on top of — not a substitute for — the consensus gate.
- **What this means.** S14 deliberately concentrates authority over the gated
  feature set in a single key during the restricted-developer phase. This is a
  **known, stated centralization** that exists **only for this phase**.

### What S14 does NOT affect

Ordinary SOST usage is completely unaffected by S14:

- ordinary SOST transfers
- mining
- DTD (Dynamic Transaction Difficulty)
- base consensus

These work normally for all users regardless of S14. S14 constrains **only**
the native-asset / tokenization / SOST-layer-DEX feature set.

### How the gate is lifted

The gate can be lifted **only** by a future height-gated release. There is no
runtime switch, no admin RPC toggle, and no configuration flag that opens public
access to the gated features — reducing or removing S14 requires a new release
activated at a future block height.

---

## 2. Lifting S14 is a governance + decentralization step — NOT a listing prerequisite

Lifting S14 is about **governance and decentralization** of the
tokenization / native-asset / SOST-layer-DEX feature set. It is **not** a
prerequisite for exchange listing or operation.

An exchange can list and operate SOST **as a native coin** — deposits,
withdrawals, trading, mining-sourced supply — **without any of the S14-gated
features**. The gated capabilities are a separate, optional layer; nothing about
listing or running SOST as a coin depends on them being open.

In short: **S14 removal is a decentralization milestone, not a listing
blocker.**

---

## 3. Prerequisites before S14 could be reduced or removed

The following are **prerequisites**, listed without date, order-of-completion
guarantee, or promise. All of them would need to be satisfied before reducing or
removing the gate would be responsible. **No artificial date is set**, and
nothing here commits to a timeline.

1. **Stable post-#30,000 operation.** The `V30000` hardfork must have activated
   and run cleanly for a sustained period.
2. **DEX browser end-to-end verified.** The SOST-layer-DEX browser flow must be
   verified end-to-end.
3. **A public testnet.** A public testnet exercising the gated features must
   exist.
4. **An external independent security audit.** An external, independent security
   audit of the gated feature set is required. **This audit is currently NOT
   completed, and no such audit presently exists.**
5. **Operational monitoring in place.** Monitoring for the gated feature set
   must be operational.
6. **Documented incident-response procedures.** Incident-response procedures
   must be documented.
7. **Regulatory review where applicable.** Tokenization capability raises
   jurisdiction-specific questions. **Technical availability is not regulatory
   authorization.** Regulatory review must be addressed where applicable.

---

## 4. Honesty statement

- The S14-gated features are **not publicly usable** while S14 is active. Public
  access is disabled, and there is no CLI/RPC/browser bypass.
- **No external security audit of the gated feature set exists** at this time.
- **No timeline, target date, or schedule is set or implied** for reducing or
  removing S14. No artificial date is set.
- This document describes current state and prerequisites only. It does not
  change S14, does not change any code or configuration, and does not set a
  date.
