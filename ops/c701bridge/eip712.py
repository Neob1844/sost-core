"""EIP-712 messages of SOSTBridge.sol (domain "SOST Automated Bridge", version "1")."""
from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from eth_abi import encode as abi_encode

DOMAIN_NAME = "SOST Automated Bridge"
DOMAIN_VERSION = "1"

DOMAIN_FIELDS = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
MINT_FIELDS = [
    {"name": "requestId", "type": "bytes32"},
    {"name": "recipient", "type": "address"},
    {"name": "amount", "type": "uint256"},
    {"name": "depositTxid", "type": "bytes32"},
    {"name": "depositVout", "type": "uint32"},
    {"name": "bridgeVault", "type": "bytes32"},
    {"name": "sostBlockHash", "type": "bytes32"},
    {"name": "sostBlockHeight", "type": "uint64"},
    {"name": "confirmations", "type": "uint32"},
    {"name": "feeXaut", "type": "uint256"},
    {"name": "priceHash", "type": "bytes32"},
    {"name": "expiry", "type": "uint64"},
    {"name": "nonce", "type": "uint256"},
]
PRICE_FIELDS = [
    {"name": "xautEur8", "type": "uint256"},
    {"name": "sostEur8", "type": "uint256"},
    {"name": "methodology", "type": "bytes32"},
    {"name": "observedAt", "type": "uint64"},
    {"name": "quoteId", "type": "bytes32"},
]
PRICE_TYPEHASH = keccak(text="PriceQuote(uint256 xautEur8,uint256 sostEur8,bytes32 methodology,uint64 observedAt,bytes32 quoteId)")


def _typed(primary, fields, msg, chain_id, contract):
    return {
        "types": {"EIP712Domain": DOMAIN_FIELDS, primary: fields},
        "primaryType": primary,
        "domain": {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": chain_id, "verifyingContract": contract},
        "message": msg,
    }


def price_struct_hash(q: dict) -> bytes:
    return keccak(abi_encode(["bytes32", "uint256", "uint256", "bytes32", "uint64", "bytes32"],
                             [PRICE_TYPEHASH, q["xautEur8"], q["sostEur8"], q["methodology"], q["observedAt"], q["quoteId"]]))


def sign_mint(a: dict, chain_id: int, contract: str, key) -> bytes:
    sm = Account.sign_message(encode_typed_data(full_message=_typed("MintAuthorization", MINT_FIELDS, a, chain_id, contract)), key)
    return sm.signature


def sign_price(q: dict, chain_id: int, contract: str, key) -> bytes:
    sm = Account.sign_message(encode_typed_data(full_message=_typed("PriceQuote", PRICE_FIELDS, q, chain_id, contract)), key)
    return sm.signature


def recover_mint(a: dict, chain_id: int, contract: str, sig: bytes) -> str:
    return Account.recover_message(encode_typed_data(full_message=_typed("MintAuthorization", MINT_FIELDS, a, chain_id, contract)), signature=sig)


def deposit_id(txid_hex: str, vout: int) -> bytes:
    """keccak256(abi.encodePacked("SOST-C701-DEPOSIT-V1", txid, uint32 vout)) — SOSTBridge.depositIdOf."""
    return keccak(b"SOST-C701-DEPOSIT-V1" + bytes.fromhex(txid_hex) + vout.to_bytes(4, "big"))


def request_id(chain_id: int, contract: str, recipient: str, amount: int, vault_hash: bytes, salt: bytes) -> bytes:
    """Public, recomputable commitment carried in the deposit capsule."""
    return keccak(abi_encode(["string", "uint256", "address", "address", "uint256", "bytes32", "bytes32"],
                             ["SOST-C701-REQUEST-V1", chain_id, contract, recipient, amount, vault_hash, salt]))
