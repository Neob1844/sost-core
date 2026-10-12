"""SOST-side scan of the Bridge Vault and full bridge reconciliation.

A sufficient vault balance alone is NOT proof of correct accounting. The indexer reconciles every
deposit id, mint, burn and release separately and reports BALANCED / PENDING / CRITICAL with exact
reasons. It never repairs anything silently; on CRITICAL it can stop new mint authorisation.

Ledger (all amounts in stocks):
  A confirmed native deposits      B deposits awaiting confirmations
  C minted wSOST                   D burned wSOST
  E burns awaiting native release  F completed native releases
  G Bridge Vault balance           H wSOST totalSupply
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from eth_utils import keccak

from .common import (to_stocks, fmt_sost, parse_open_note, parse_wsost_recipient, parse_release,
                     deposit_id, is_sost_address)
from .sostchain import iter_canonical_txs

BALANCED, PENDING, CRITICAL = "BALANCED", "PENDING", "CRITICAL"


@dataclass
class VaultDeposit:
    txid: str
    vout: int
    deposit_id: bytes
    amount: int
    recipient: str
    height: int
    block_hash: str
    confirmations: int


@dataclass
class VaultRelease:
    txid: str
    burn_id: bytes
    dest: str
    amount: int
    fee: int
    height: int
    confirmations: int


@dataclass
class VaultScan:
    tip: int
    vault_balance: int = 0
    deposits: List[VaultDeposit] = field(default_factory=list)
    unattributed: List[dict] = field(default_factory=list)     # paid to the vault without a valid capsule
    releases: List[VaultRelease] = field(default_factory=list)
    unexplained_spends: List[dict] = field(default_factory=list)


def scan_vault(rpc, vault: str, start_height: int) -> VaultScan:
    """Walk canonical blocks [start, tip] and classify every movement of the Bridge Vault."""
    if not is_sost_address(vault):
        raise ValueError("bad vault address")
    tip = rpc.getblockcount()
    s = VaultScan(tip=tip)
    for h, bh, tx in iter_canonical_txs(rpc, start_height, tip):
        vin = tx.get("vin", []) or []
        vout = tx.get("vout", []) or []
        conf = tip - h + 1
        in_vault = sum(to_stocks(i.get("amount", 0)) for i in vin if i.get("address") == vault)
        from_vault = in_vault > 0
        out_vault = 0
        for idx, o in enumerate(vout):
            if o.get("address") == vault:
                amt = to_stocks(o.get("amount", 0))
                out_vault += amt
                if from_vault:
                    continue                                  # change back to the vault
                rcpt = parse_wsost_recipient(parse_open_note(o.get("payload_hex")))
                if rcpt:
                    s.deposits.append(VaultDeposit(tx["txid"], idx, deposit_id(tx["txid"], idx), amt, rcpt, h, bh, conf))
                else:
                    s.unattributed.append({"txid": tx["txid"], "vout": idx, "amount": amt, "height": h})
        s.vault_balance += out_vault - in_vault
        if from_vault:
            total_in = sum(to_stocks(i.get("amount", 0)) for i in vin)
            total_out = sum(to_stocks(o.get("amount", 0)) for o in vout)
            rel = None
            for o in vout:
                if o.get("address") == vault:
                    continue
                bid = parse_release(parse_open_note(o.get("payload_hex")))
                if bid is not None:
                    if rel is not None:
                        rel = "multi"
                        break
                    rel = VaultRelease(tx["txid"], bid, o.get("address"), to_stocks(o.get("amount", 0)),
                                       total_in - total_out, h, conf)
            if isinstance(rel, VaultRelease):
                s.releases.append(rel)
            else:
                s.unexplained_spends.append({"txid": tx["txid"], "height": h, "amount": in_vault,
                                             "why": "multiple release capsules" if rel == "multi" else "vault spend without a release capsule"})
    return s


@dataclass
class Reconciliation:
    status: str
    reasons: List[str]
    warnings: List[str]
    ledger: Dict[str, int]
    detail: Dict[str, list]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, default=lambda b: "0x" + b.hex() if isinstance(b, bytes) else str(b))


def reconcile(scan: VaultScan, eth, min_conf: int, release_fee_allowance: int) -> Reconciliation:
    reasons: List[str] = []
    warnings: List[str] = []
    mints = eth.mint_events()
    burns = eth.burn_events()
    supply = eth.total_supply()

    confirmed = [d for d in scan.deposits if d.confirmations >= min_conf]
    pending = [d for d in scan.deposits if d.confirmations < min_conf]
    dep_by_id: Dict[bytes, VaultDeposit] = {}
    for d in scan.deposits:
        if d.deposit_id in dep_by_id:
            reasons.append(f"duplicate deposit id 0x{d.deposit_id.hex()}")
        dep_by_id[d.deposit_id] = d

    # --- mints <-> deposits
    minted_ids: Dict[bytes, int] = {}
    for m in mints:
        minted_ids[m.deposit_id] = minted_ids.get(m.deposit_id, 0) + 1
        d = dep_by_id.get(m.deposit_id)
        if d is None:
            reasons.append(f"mint without a canonical deposit 0x{m.deposit_id.hex()} ({fmt_sost(m.amount)} wSOST)")
            continue
        if d.confirmations < min_conf:
            reasons.append(f"mint of deposit 0x{m.deposit_id.hex()} that is no longer buried by {min_conf} confirmations (reorg?)")
        if m.amount != d.amount:
            reasons.append(f"mint amount mismatch for 0x{m.deposit_id.hex()}: minted {m.amount}, deposited {d.amount}")
        if m.recipient.lower() != d.recipient.lower():
            reasons.append(f"mint recipient mismatch for 0x{m.deposit_id.hex()}")
        if m.sost_block_hash and m.sost_block_hash != bytes.fromhex(d.block_hash):
            reasons.append(f"mint references a block hash that is not canonical for 0x{m.deposit_id.hex()}")
    for k, n in minted_ids.items():
        if n > 1:
            reasons.append(f"deposit 0x{k.hex()} minted {n} times")
    unminted_confirmed = [d for d in confirmed if d.deposit_id not in minted_ids]

    # --- burns <-> releases
    burn_by_id = {b.burn_id: b for b in burns}
    released: Dict[bytes, int] = {}
    for r in scan.releases:
        released[r.burn_id] = released.get(r.burn_id, 0) + 1
        b = burn_by_id.get(r.burn_id)
        if b is None:
            reasons.append(f"native release without a wSOST burn: tx {r.txid}")
            continue
        if r.amount != b.amount - release_fee_allowance:
            reasons.append(f"release amount mismatch for burn 0x{r.burn_id.hex()}: released {r.amount}, expected {b.amount - release_fee_allowance}")
        if r.dest != b.sost_address:
            reasons.append(f"release destination substituted for burn 0x{r.burn_id.hex()}")
        if r.fee > release_fee_allowance:
            warnings.append(f"release {r.txid} paid fee {r.fee} above the allowance {release_fee_allowance}")
    for k, n in released.items():
        if n > 1:
            reasons.append(f"burn 0x{k.hex()} released {n} times")
    awaiting = [b for b in burns if b.burn_id not in released]
    for u in scan.unexplained_spends:
        reasons.append(f"unexplained Bridge Vault spend {u['txid']}: {u['why']}")
    for u in scan.unattributed:
        warnings.append(f"payment to the vault without a valid WSOST capsule: {u['txid']}:{u['vout']} ({fmt_sost(u['amount'])} SOST) — not mintable, manual review")

    C = sum(m.amount for m in mints)
    D = sum(b.amount for b in burns)
    if C - D != supply:
        reasons.append(f"wSOST totalSupply {supply} != minted {C} - burned {D}")

    pending_amt = sum(d.amount for d in pending)
    confirmed_backing = scan.vault_balance - pending_amt
    owed = supply + sum(b.amount for b in awaiting) + sum(d.amount for d in unminted_confirmed)
    if confirmed_backing < owed:
        reasons.append(f"backing deficit: confirmed vault backing {confirmed_backing} < owed {owed} (supply {supply} + awaiting releases + unminted deposits)")
    if supply > confirmed_backing:
        reasons.append(f"wSOST totalSupply {supply} exceeds confirmed native backing {confirmed_backing}")

    ledger = {
        "A_confirmed_deposits": sum(d.amount for d in confirmed),
        "B_pending_deposits": pending_amt,
        "C_minted": C,
        "D_burned": D,
        "E_burns_awaiting_release": sum(b.amount for b in awaiting),
        "F_completed_releases": sum(r.amount for r in scan.releases),
        "G_vault_balance": scan.vault_balance,
        "H_total_supply": supply,
        "confirmed_backing": confirmed_backing,
        "owed": owed,
        "surplus": confirmed_backing - owed,
        "tip": scan.tip,
    }
    if reasons:
        status = CRITICAL
    elif pending or unminted_confirmed or awaiting:
        status = PENDING
    else:
        status = BALANCED
    detail = {
        "pending_deposits": [d.txid + ":" + str(d.vout) for d in pending],
        "unminted_confirmed": [d.txid + ":" + str(d.vout) for d in unminted_confirmed],
        "burns_awaiting_release": ["0x" + b.burn_id.hex() for b in awaiting],
    }
    return Reconciliation(status, reasons, warnings, ledger, detail)


def enforce_safety(rec: Reconciliation, eth, pauser: Optional[str] = None) -> bool:
    """On CRITICAL, stop NEW mints (transfers and burns continue). Returns True if a pause was issued."""
    if rec.status != CRITICAL:
        return False
    if not eth.is_mint_paused():
        eth.pause_mint(pauser) if pauser is not None else eth.pause_mint()
        return True
    return False
