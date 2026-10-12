"""EIP-712 typed data for wSOST deposit attestations — byte-identical to WSOST.sol."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List

from eth_account import Account
from eth_account.messages import encode_typed_data

from .common import BRIDGE_VERSION

DOMAIN_NAME = "SOST wSOST Bridge"
DOMAIN_VERSION = "1"

DEPOSIT_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "Deposit": [
        {"name": "depositId", "type": "bytes32"},
        {"name": "recipient", "type": "address"},
        {"name": "amount", "type": "uint256"},
        {"name": "bridgeVault", "type": "bytes32"},
        {"name": "sostBlockHash", "type": "bytes32"},
        {"name": "sostBlockHeight", "type": "uint64"},
        {"name": "confirmations", "type": "uint32"},
        {"name": "bridgeVersion", "type": "uint32"},
    ],
}


@dataclass(frozen=True)
class DepositMsg:
    depositId: bytes
    recipient: str
    amount: int
    bridgeVault: bytes
    sostBlockHash: bytes
    sostBlockHeight: int
    confirmations: int
    bridgeVersion: int = BRIDGE_VERSION

    def as_tuple(self):
        return (self.depositId, self.recipient, self.amount, self.bridgeVault, self.sostBlockHash,
                self.sostBlockHeight, self.confirmations, self.bridgeVersion)

    def key(self):
        """Identity of the attested statement (all fields)."""
        return self.as_tuple()


def _full(msg: DepositMsg, chain_id: int, contract: str) -> dict:
    return {
        "types": DEPOSIT_TYPES,
        "primaryType": "Deposit",
        "domain": {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": chain_id, "verifyingContract": contract},
        "message": asdict(msg),
    }


def sign_deposit(private_key: bytes, msg: DepositMsg, chain_id: int, contract: str) -> bytes:
    signed = Account.sign_message(encode_typed_data(full_message=_full(msg, chain_id, contract)), private_key)
    return bytes(signed.signature)


def recover_deposit_signer(msg: DepositMsg, signature: bytes, chain_id: int, contract: str) -> str:
    return Account.recover_message(encode_typed_data(full_message=_full(msg, chain_id, contract)), signature=signature)


def order_signatures(pairs: List[tuple]) -> List[bytes]:
    """pairs of (signer_address, signature) -> signatures sorted by strictly increasing signer, distinct."""
    seen, out = set(), []
    for addr, sig in sorted(pairs, key=lambda p: int(p[0], 16)):
        if addr.lower() in seen:
            continue
        seen.add(addr.lower())
        out.append(sig)
    return out
