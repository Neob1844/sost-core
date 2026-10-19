"""In-memory stand-in for the SOSTBridge contract state (unit tests only).

It applies the same acceptance rules the contract applies (signature recovery against the
authorizer set, expiry, deposit/request/nonce single-use, revoke guard, exact fee) so that engine
tests are meaningful; the real contract is exercised separately on a local Anvil (e2e_anvil.py).
"""
from __future__ import annotations

from .eip712 import deposit_id, recover_mint
from . import fee as feemod


class MockEth:
    def __init__(self, chain_id, bridge, authorizers, now):
        self.chain_id, self.bridge, self.authorizers, self.now = chain_id, bridge, set(authorizers), now
        self.used, self.revoked, self.final_revokes = set(), set(), set()
        self.requests, self.nonces = set(), set()
        self.supply = self.burned = self.released = 0
        self.recorded = {}
        self.burns = {}
        self.paused = False
        self.reserve_xaut = 0
        self.balances = {}

    # views used by the engine
    def deposit_used(self, did): return did in self.used
    def deposit_revoked(self, did): return did in self.revoked
    def revoke_final(self, did): return did in self.final_revokes
    def total_supply(self): return self.supply
    def burned_unreleased(self): return self.burned - self.released
    def release_recorded(self, rid): return rid in self.recorded
    def pause_mint(self, why): self.paused = True

    # contract-equivalent entry points
    def mint(self, bundle):
        a = {k: (bytes.fromhex(v[2:]) if isinstance(v, str) and v.startswith("0x") and k != "recipient" else v)
             for k, v in bundle["authorization"].items()}
        q = bundle["quote"]
        if self.paused: raise RuntimeError("MintIsPaused")
        if self.now() > a["expiry"]: raise RuntimeError("Expired")
        did = deposit_id(a["depositTxid"].hex(), a["depositVout"])
        if did in self.used: raise RuntimeError("DepositAlreadyUsed")
        if a["requestId"] in self.requests: raise RuntimeError("RequestAlreadyUsed")
        if a["nonce"] in self.nonces: raise RuntimeError("NonceAlreadyUsed")
        if feemod.fee_xaut_for_amount(a["amount"], q["sostEur8"], q["xautEur8"]) != a["feeXaut"]: raise RuntimeError("FeeMismatch")
        signer = recover_mint(a, self.chain_id, self.bridge, bytes.fromhex(bundle["authSigs"][0][2:]))
        if signer not in self.authorizers: raise RuntimeError("BadSignatures")
        self.used.add(did); self.requests.add(a["requestId"]); self.nonces.add(a["nonce"])
        self.supply += a["amount"]; self.reserve_xaut += a["feeXaut"]
        self.balances[a["recipient"]] = self.balances.get(a["recipient"], 0) + a["amount"]
        return did

    def revoke(self, txid, vout, final=True):
        did = deposit_id(txid, vout)
        if did in self.used: raise RuntimeError("DepositAlreadyUsed")
        self.used.add(did); self.revoked.add(did)
        if final: self.final_revokes.add(did)

    def burn(self, holder, amount, sost_address):
        if self.balances.get(holder, 0) < amount: raise RuntimeError("InsufficientBalance")
        self.balances[holder] -= amount; self.supply -= amount; self.burned += amount
        rid = "0x%064x" % (len(self.burns) + 1)
        self.burns[rid] = (holder, amount, sost_address)
        return rid

    def record_release(self, rid, sost_txid):
        if rid in self.recorded: raise RuntimeError("AlreadyReleased")
        self.recorded[rid] = sost_txid; self.released += self.burns[rid][1]
