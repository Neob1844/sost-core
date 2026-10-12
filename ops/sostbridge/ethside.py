"""Ethereum side of the bridge: a minimal read/write view of WSOST.

`Web3WSOST` drives the real contract (Anvil in Stage 1). `FakeWSOST` mirrors the contract's
rules in Python for fast deterministic tests (same EIP-712 digest, same threshold rule).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from eth_utils import keccak

from .eip712 import DepositMsg, recover_deposit_signer


@dataclass
class MintEvent:
    deposit_id: bytes
    recipient: str
    amount: int
    sost_block_hash: bytes
    sost_block_height: int


@dataclass
class BurnEvent:
    burn_id: bytes
    sender: str
    amount: int
    sost_address: str
    nonce: int


class FakeWSOST:
    def __init__(self, observers: List[str], threshold: int, vault: bytes, chain_id: int = 31337,
                 address: str = "0x00000000000000000000000000000000000B51D9", min_conf: int = 30,
                 exposure_cap: int = 10**18, daily_cap: int = 10**18):
        self.observers = {o.lower() for o in observers}
        self.threshold, self.vault, self.chain_id, self.address = threshold, vault, chain_id, address
        self.min_conf, self.exposure_cap, self.daily_cap = min_conf, exposure_cap, daily_cap
        self.used: Dict[bytes, bool] = {}
        self.balances: Dict[str, int] = {}
        self.supply = 0
        self.mints: List[MintEvent] = []
        self.burns: List[BurnEvent] = []
        self.mint_paused = False
        self._nonce = 0

    # view
    def deposit_used(self, deposit_id: bytes) -> bool:
        return self.used.get(deposit_id, False)

    def total_supply(self) -> int:
        return self.supply

    def mint_events(self) -> List[MintEvent]:
        return list(self.mints)

    def burn_events(self) -> List[BurnEvent]:
        return list(self.burns)

    def is_mint_paused(self) -> bool:
        return self.mint_paused

    # write
    def mint(self, msg: DepositMsg, sigs: List[bytes]):
        if self.mint_paused:
            raise RuntimeError("MintIsPaused")
        if msg.bridgeVault != self.vault or msg.bridgeVersion != 1:
            raise RuntimeError("BadVault/Version")
        if msg.confirmations < self.min_conf:
            raise RuntimeError("NotEnoughConfirmations")
        if self.used.get(msg.depositId):
            raise RuntimeError("DepositAlreadyUsed")
        if self.supply + msg.amount > self.exposure_cap:
            raise RuntimeError("ExposureCapExceeded")
        last = 0
        for s in sigs:
            a = recover_deposit_signer(msg, s, self.chain_id, self.address)
            if int(a, 16) <= last or a.lower() not in self.observers:
                raise RuntimeError("BadSignatures")
            last = int(a, 16)
        if len(sigs) < self.threshold:
            raise RuntimeError("BadSignatures")
        self.used[msg.depositId] = True
        self.supply += msg.amount
        self.balances[msg.recipient] = self.balances.get(msg.recipient, 0) + msg.amount
        self.mints.append(MintEvent(msg.depositId, msg.recipient, msg.amount, msg.sostBlockHash, msg.sostBlockHeight))

    def force_mint_unbacked(self, recipient: str, amount: int, deposit_id: bytes):
        """Test hook: models two compromised observers minting a fake deposit."""
        self.used[deposit_id] = True
        self.supply += amount
        self.mints.append(MintEvent(deposit_id, recipient, amount, b"\x00" * 32, 0))

    def burn(self, sender: str, amount: int, sost_address: str) -> bytes:
        if self.balances.get(sender, 0) < amount or amount <= 0:
            raise RuntimeError("InsufficientBalance")
        self.balances[sender] -= amount
        self.supply -= amount
        self._nonce += 1
        bid = keccak(b"fake-burn" + self._nonce.to_bytes(8, "big"))
        self.burns.append(BurnEvent(bid, sender, amount, sost_address, self._nonce))
        return bid

    def pause_mint(self, by: str = ""):
        self.mint_paused = True


class Web3WSOST:
    """Real WSOST contract via web3.py (local Anvil only in Stage 1)."""

    def __init__(self, w3, address: str, abi: list, from_block: int = 0):
        self.w3, self.address = w3, address
        self.c = w3.eth.contract(address=address, abi=abi)
        self.from_block = from_block
        self.chain_id = w3.eth.chain_id

    @staticmethod
    def load_abi(out_dir: str) -> list:
        with open(os.path.join(out_dir, "WSOST.sol", "WSOST.json")) as f:
            return json.load(f)["abi"]

    def deposit_used(self, deposit_id: bytes) -> bool:
        return bool(self.c.functions.depositUsed(deposit_id).call())

    def total_supply(self) -> int:
        return int(self.c.functions.totalSupply().call())

    def is_mint_paused(self) -> bool:
        return bool(self.c.functions.mintPaused().call())

    def mint_events(self) -> List[MintEvent]:
        logs = self.c.events.Minted().get_logs(from_block=self.from_block)
        return [MintEvent(bytes(l.args.depositId), l.args.recipient, int(l.args.amount),
                          bytes(l.args.sostBlockHash), int(l.args.sostBlockHeight)) for l in logs]

    def burn_events(self) -> List[BurnEvent]:
        logs = self.c.events.BurnedForRelease().get_logs(from_block=self.from_block)
        return [BurnEvent(bytes(l.args.burnId), l.args["from"], int(l.args.amount), l.args.sostAddress, int(l.args.nonce))
                for l in logs]

    def mint(self, msg: DepositMsg, sigs: List[bytes], sender: str):
        tx = self.c.functions.mint(msg.as_tuple(), sigs).transact({"from": sender})
        return self.w3.eth.wait_for_transaction_receipt(tx)

    def pause_mint(self, by: str):
        tx = self.c.functions.pauseMint().transact({"from": by})
        return self.w3.eth.wait_for_transaction_receipt(tx)
