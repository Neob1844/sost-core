"""Bridge observer: independently verifies native SOST deposits and signs EIP-712 attestations.

An observer never mints. A relayer (any account, no authority) collects >= threshold attestations
for the SAME statement and submits them to WSOST.mint. Before signing, every field is re-verified
against the observer's own node: canonical block, vault, amount, recipient capsule, confirmations,
deposit not already used, and the bridge not in CRITICAL state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from eth_account import Account

from .common import to_stocks, parse_open_note, parse_wsost_recipient, vault_hash
from .eip712 import DepositMsg, sign_deposit, order_signatures
from .ledger import scan_vault, CRITICAL, VaultDeposit


@dataclass
class ObserverConfig:
    vault: str
    start_height: int
    min_confirmations: int = 30          # provisional pilot policy; never a protocol constant
    chain_id: int = 31337
    wsost: str = "0x0000000000000000000000000000000000000000"


@dataclass
class Attestation:
    msg: DepositMsg
    signer: str
    signature: bytes


class Observer:
    def __init__(self, name: str, private_key: bytes, rpc, cfg: ObserverConfig, eth, status_fn=None):
        self.name, self.key, self.rpc, self.cfg, self.eth = name, private_key, rpc, cfg, eth
        self.address = Account.from_key(private_key).address
        self.status_fn = status_fn                    # () -> current reconciliation status
        self.log: List[str] = []

    def candidates(self) -> List[VaultDeposit]:
        return scan_vault(self.rpc, self.cfg.vault, self.cfg.start_height).deposits

    def _refuse(self, why: str):
        self.log.append(why)
        return None

    def verify(self, d: VaultDeposit) -> Optional[DepositMsg]:
        """Re-check one deposit against the node right now; return the exact statement to sign."""
        if self.status_fn is not None and self.status_fn() == CRITICAL:
            return self._refuse("bridge CRITICAL: no new attestations")
        try:
            tx = self.rpc.gettransaction(d.txid)
        except Exception:
            return self._refuse(f"{d.txid}: deposit no longer found (reorg)")
        h = int(tx.get("block_height", -1))
        if h < 0:
            return self._refuse(f"{d.txid}: not confirmed")
        tip = self.rpc.getblockcount()
        canon = self.rpc.getblockhash(h)
        if h != d.height or canon != d.block_hash:
            return self._refuse(f"{d.txid}: block moved (reorg) — stale statement refused")
        conf = tip - h + 1
        if conf < self.cfg.min_confirmations:
            return self._refuse(f"{d.txid}: {conf} < {self.cfg.min_confirmations} confirmations")
        vout = tx.get("vout", [])
        if d.vout >= len(vout):
            return self._refuse(f"{d.txid}: vout missing")
        o = vout[d.vout]
        if o.get("address") != self.cfg.vault:
            return self._refuse(f"{d.txid}: not paid to the Bridge Vault")
        if to_stocks(o.get("amount", 0)) != d.amount:
            return self._refuse(f"{d.txid}: amount mismatch")
        rcpt = parse_wsost_recipient(parse_open_note(o.get("payload_hex")))
        if rcpt is None or rcpt != d.recipient:
            return self._refuse(f"{d.txid}: recipient capsule mismatch")
        if any(i.get("address") == self.cfg.vault for i in tx.get("vin", [])):
            return self._refuse(f"{d.txid}: vault self-spend is not a deposit")
        if self.eth.deposit_used(d.deposit_id):
            return self._refuse(f"{d.txid}: deposit already minted")
        return DepositMsg(depositId=d.deposit_id, recipient=d.recipient, amount=d.amount,
                          bridgeVault=vault_hash(self.cfg.vault), sostBlockHash=bytes.fromhex(d.block_hash),
                          sostBlockHeight=h, confirmations=self.cfg.min_confirmations)
        # The statement attests "buried by at least min_confirmations", so every honest observer
        # signs the identical message regardless of when it looked.

    def attest(self, d: VaultDeposit) -> Optional[Attestation]:
        msg = self.verify(d)
        if msg is None:
            return None
        sig = sign_deposit(self.key, msg, self.cfg.chain_id, self.cfg.wsost)
        return Attestation(msg, self.address, sig)


def collect(attestations: List[Optional[Attestation]], threshold: int):
    """Relayer helper: return (msg, signatures ordered by signer) once one identical statement has
    >= threshold distinct observer signatures; otherwise None. The relayer holds no authority."""
    by_stmt: Dict[tuple, List[Attestation]] = {}
    for a in attestations:
        if a is not None:
            by_stmt.setdefault(a.msg.key(), []).append(a)
    for same in by_stmt.values():
        if len({a.signer.lower() for a in same}) >= threshold:
            return same[0].msg, order_signatures([(a.signer, a.signature) for a in same])
    return None


def still_canonical(rpc, msg: DepositMsg) -> bool:
    """Relayer pre-flight: refuse to submit a statement whose block is no longer canonical
    (a reorg after the threshold was reached, before the mint was submitted)."""
    try:
        return rpc.getblockhash(int(msg.sostBlockHeight)) == msg.sostBlockHash.hex()
    except Exception:
        return False
