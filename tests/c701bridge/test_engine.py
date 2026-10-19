"""C701 engine tests (development only). Run: python3 -m pytest -q tests/c701bridge
All keys below are TEST-ONLY constants with no value anywhere."""
import json
import os
import sys
from decimal import Decimal

import pytest
from eth_account import Account
from eth_utils import keccak, to_checksum_address

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ops"))

from c701bridge import engine as E  # noqa: E402
from c701bridge import fee as F  # noqa: E402
from c701bridge.eip712 import deposit_id, recover_mint  # noqa: E402
from c701bridge.mocketh import MockEth  # noqa: E402
from c701bridge.pricing import (Observation, PriceSigner, PriceUnavailable, SostValuation,  # noqa: E402
                                ValuationNotApproved, XautEurOracle)
from c701bridge.sost import (MockSostChain, SostRpc, build_open_note, capsule_for_request,  # noqa: E402
                             parse_open_note, release_capsule, request_id_from_capsule, to_stocks)

AUTH_KEY = "0x" + "11" * 32      # TEST ONLY
PRICE_KEY = "0x" + "22" * 32     # TEST ONLY
AUTH_ADDR = Account.from_key(AUTH_KEY).address
BRIDGE = to_checksum_address("0x" + "b1" * 20)
CHAIN = 31337
VAULT = "sost1" + "ab" * 20
USER_SOST = "sost1" + "cd" * 20
RECIPIENT = to_checksum_address("0x" + "e7" * 20)
XAUT8 = 371_313_000_000
METHOD = keccak(text="TEST-ONLY SOST/EUR methodology - NOT APPROVED")
FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Env:
    def __init__(self, valuation=None, sources=2):
        self.t = [1_800_000_000]
        self.chain = MockSostChain()
        self.chain.mine(5)
        self.eth = MockEth(CHAIN, BRIDGE, [AUTH_ADDR], lambda: self.t[0])
        self.obs = [Observation("srcA", XAUT8, self.t[0] - 60), Observation("srcB", XAUT8 + 10_000_000, self.t[0] - 30)][:sources]
        self.engine = E.Engine(":memory:", self.chain, self.eth, chain_id=CHAIN, bridge=BRIDGE, vault_address=VAULT,
                               authorizer_key=AUTH_KEY, price_signer=PriceSigner(PRICE_KEY, CHAIN, BRIDGE),
                               oracle=XautEurOracle(), valuation=valuation or SostValuation(METHOD, 100_000_000),
                               observations=lambda: [Observation(o.source, o.xaut_eur8, self.t[0] - 60) for o in self.obs],
                               now=lambda: self.t[0])
        self.n = 0

    def deposit(self, req, amount=None, to=VAULT, capsule=None, mine=True):
        self.n += 1
        txid = keccak(text=f"tx{self.n}").hex()
        cap = capsule if capsule is not None else req["capsule_hex"]
        self.chain.add_tx(txid, [{"address": to, "stocks": amount if amount is not None else req["amount_stocks"], "payload_hex": cap},
                                 {"address": USER_SOST, "stocks": 5 * 10**8}],
                          vin=[{"prev_txid": "aa" * 32, "index": 0, "address": USER_SOST, "stocks": 2_000 * 10**8}])
        if mine:
            self.chain.mine(1, include=[txid])
        return txid

    def to_confirmed(self, rid):
        self.engine.scan_vault()
        self.chain.mine(30)
        return self.engine.verify(rid)


# ---------------------------------------------------------------- fee math
def test_fee_table_20_rows():
    expected = [None, None, None, 135, 135, 135, 202, 270, 404, 539, 808, 1347, 2020, 2694, 4040, 6733, 13466, 13466, 13466, 13466]
    rows = F.example_table(XAUT8)
    assert len(rows) == 20
    assert [r["fee_xaut_units"] for r in rows] == expected
    assert [r["status"] for r in rows[:3]] == ["REJECTED_BELOW_MINIMUM"] * 3


def test_fee_integer_only_and_minimum():
    with pytest.raises(TypeError):
        F.fee_xaut(100.0, 1, XAUT8)
    with pytest.raises(F.BelowMinimumOperation):
        F.fee_xaut(100 * 10**8 - 1, 1, XAUT8)
    assert F.eur8("3713.13") == XAUT8
    with pytest.raises(TypeError):
        F.eur8(3713.13)
    assert F.fmt_xaut(13466) == "0.013466"


def test_fee_ceiling_property_exhaustive_sample():
    from fractions import Fraction
    import math
    for amount in [100 * 10**8, 123_456_789_01, 7_777_777_777_777, 10**15, 49_999 * 10**8 + 1]:
        exact = min(Fraction(50), max(Fraction(1, 2), Fraction(amount, 10**8) / 1000))
        assert F.fee_xaut_for_amount(amount, 10**8, XAUT8) == math.ceil(exact / Fraction(XAUT8, 10**8) * 10**6)


# ---------------------------------------------------------------- valuation / price gates
def test_no_valuation_blocks_every_request():
    env = Env(valuation=SostValuation(None, None))
    with pytest.raises(ValuationNotApproved):
        env.engine.create_request(RECIPIENT, 1_000 * 10**8)


def test_price_needs_two_fresh_agreeing_sources():
    env = Env(sources=1)
    with pytest.raises(PriceUnavailable):
        env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    o = XautEurOracle()
    now = 1_800_000_000
    with pytest.raises(PriceUnavailable):        # spread 5 %
        o.aggregate([Observation("a", XAUT8, now), Observation("b", XAUT8 * 105 // 100, now)], now)
    with pytest.raises(PriceUnavailable):        # stale
        o.aggregate([Observation("a", XAUT8, now - 3600), Observation("b", XAUT8, now - 3600)], now)
    with pytest.raises(PriceUnavailable):        # same source twice is ONE source
        o.aggregate([Observation("a", XAUT8, now), Observation("a", XAUT8, now)], now)


def test_request_validation():
    env = Env()
    with pytest.raises(F.BelowMinimumOperation):
        env.engine.create_request(RECIPIENT, 99 * 10**8)
    bad = "0x" + "E7" * 10 + "e7" * 10           # mixed case with wrong checksum
    with pytest.raises(ValueError):
        env.engine.create_request(bad, 1_000 * 10**8)
    with pytest.raises(ValueError):
        env.engine.create_request("0x" + "00" * 20, 1_000 * 10**8)


# ---------------------------------------------------------------- happy path
def test_happy_path_and_signature_recovers():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    assert env.engine.get(req["request_id"])["status"] == E.AWAITING_SOST
    env.deposit(req)
    env.engine.scan_vault()
    assert env.engine.verify(req["request_id"]) == E.VERIFYING            # 1 confirmation
    env.chain.mine(29)
    assert env.engine.verify(req["request_id"]) == E.DEPOSIT_CONFIRMED
    b = env.engine.authorize(req["request_id"])
    a = {k: (bytes.fromhex(v[2:]) if isinstance(v, str) and v.startswith("0x") and k != "recipient" else v)
         for k, v in b["authorization"].items()}
    assert recover_mint(a, CHAIN, BRIDGE, bytes.fromhex(b["authSigs"][0][2:])) == AUTH_ADDR
    assert a["amount"] == 1_000 * 10**8 and a["recipient"] == RECIPIENT and a["confirmations"] >= 30
    assert a["feeXaut"] == 270                                             # 1,000 EUR at the test fixture price
    env.engine.wallet_signing(req["request_id"])
    env.engine.mint_submitted(req["request_id"], "0xmint")
    env.eth.mint(b)
    assert env.engine.observe_mint(req["request_id"]) == E.COMPLETED
    assert env.eth.balances[RECIPIENT] == 1_000 * 10**8
    assert env.engine.reconcile()["status"] == "BALANCED"
    kinds = [r[0] for r in env.engine.db.execute("SELECT kind FROM log")]
    assert "request" in kinds and "state" in kinds and "reconcile" in kinds


def test_authorize_idempotent_and_replay_rejected():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.deposit(req)
    env.to_confirmed(req["request_id"])
    b1 = env.engine.authorize(req["request_id"])
    b2 = env.engine.authorize(req["request_id"])
    assert b1["authorization"]["nonce"] == b2["authorization"]["nonce"]
    env.eth.mint(b1)
    with pytest.raises(RuntimeError, match="DepositAlreadyUsed"):
        env.eth.mint(b1)
    assert env.eth.supply == 1_000 * 10**8


def test_tampered_authorization_rejected():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.deposit(req)
    env.to_confirmed(req["request_id"])
    b = env.engine.authorize(req["request_id"])
    b2 = json.loads(json.dumps(b))
    b2["authorization"]["recipient"] = to_checksum_address("0x" + "66" * 20)
    with pytest.raises(RuntimeError, match="BadSignatures"):
        env.eth.mint(b2)


# ---------------------------------------------------------------- failure matrix
def test_amount_mismatch_goes_to_recovery_then_refund_only_after_final_revoke():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    txid = env.deposit(req, amount=900 * 10**8)
    assert env.to_confirmed(req["request_id"]) == E.PENDING_RECOVERY
    assert env.engine.prepare_refund(req["request_id"])["ok"] is False      # not revoked yet
    env.eth.revoke(txid, 0, final=False)
    assert "finality" in env.engine.prepare_refund(req["request_id"])["next"]
    env.eth.final_revokes.add(deposit_id(txid, 0))
    r = env.engine.prepare_refund(req["request_id"])
    assert r["ok"] and r["instruction"]["to"] == USER_SOST
    assert r["instruction"]["amount_stocks"] == 900 * 10**8 - 10_000
    assert env.engine.get(req["request_id"])["status"] == E.REFUND_PREPARED


def test_cannot_keep_both_refund_and_wsost():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    txid = env.deposit(req)
    env.to_confirmed(req["request_id"])
    b = env.engine.authorize(req["request_id"])
    env.eth.revoke(txid, 0)                                                 # refund requested after an auth exists
    assert "expired" in env.engine.prepare_refund(req["request_id"])["next"]
    with pytest.raises(RuntimeError, match="DepositAlreadyUsed"):
        env.eth.mint(b)                                                     # the live auth is dead after revoke
    env.t[0] += 31 * 60
    assert env.engine.prepare_refund(req["request_id"])["ok"] is True
    # and the other order: once minted, revoke is impossible -> no refund
    env2 = Env()
    req2 = env2.engine.create_request(RECIPIENT, 1_000 * 10**8)
    tx2 = env2.deposit(req2)
    env2.to_confirmed(req2["request_id"])
    env2.eth.mint(env2.engine.authorize(req2["request_id"]))
    with pytest.raises(RuntimeError, match="DepositAlreadyUsed"):
        env2.eth.revoke(tx2, 0)


def test_deposit_without_capsule_is_unbound_and_never_minted():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.deposit(req, capsule="")
    env.engine.scan_vault()
    assert env.engine.get(req["request_id"])["status"] == E.AWAITING_SOST
    assert env.engine.db.execute("SELECT count(*) FROM log WHERE kind='unbound'").fetchone()[0] == 1
    env.engine.scan_vault()                                                 # idempotent logging
    assert env.engine.db.execute("SELECT count(*) FROM log WHERE kind='unbound'").fetchone()[0] == 1
    rep = env.engine.reconcile()
    assert rep["unbound_deposits"] == 1_000 * 10**8 and rep["status"] == "BALANCED"


def test_wrong_destination_not_detected_and_hint_explains():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    txid = env.deposit(req, to="sost1" + "ef" * 20)
    env.engine.scan_vault()
    assert env.engine.get(req["request_id"])["status"] == E.AWAITING_SOST
    assert env.engine.lookup_hint(req["request_id"], txid)["ok"] is False


def test_manual_hash_is_only_a_hint():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    assert env.engine.lookup_hint(req["request_id"], "nothex")["error"].startswith("invalid")
    assert "not found" in env.engine.lookup_hint(req["request_id"], "ff" * 32)["error"]
    txid = env.deposit(req)
    assert env.engine.lookup_hint(req["request_id"], txid)["ok"] is True
    assert env.engine.get(req["request_id"])["status"] == E.AWAITING_SOST   # a hint changes nothing


def test_capsule_for_other_request_cannot_be_reused():
    env = Env()
    r1 = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    r2 = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.deposit(r1)
    env.deposit(r1)                                                         # second deposit with r1's capsule
    env.engine.scan_vault()
    assert env.engine.get(r2["request_id"])["status"] == E.AWAITING_SOST
    bound = env.engine.db.execute("SELECT count(*) FROM requests WHERE deposit_id IS NOT NULL").fetchone()[0]
    assert bound == 1                                                       # duplicate deposit stays unbound -> recovery


def test_reorg_before_finality_is_harmless():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    txid = env.deposit(req)
    env.engine.scan_vault()
    env.chain.mine(4)
    env.engine.verify(req["request_id"])
    env.chain.reorg(5)                                                      # 5-deep reorg: deposit back to mempool
    assert env.engine.verify(req["request_id"]) == E.VERIFYING
    assert env.engine.get(req["request_id"])["block_hash"] is None
    env.chain.mine(1, include=[txid])
    env.chain.mine(30)
    assert env.engine.verify(req["request_id"]) == E.DEPOSIT_CONFIRMED


def test_deep_reorg_after_authorization_is_security_error_and_halts():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.deposit(req)
    env.to_confirmed(req["request_id"])
    env.engine.authorize(req["request_id"])
    env.chain.reorg(40)
    assert env.engine.verify(req["request_id"]) == E.SECURITY_ERROR
    assert env.engine.halted and env.eth.paused
    with pytest.raises(E.EngineHalted):
        env.engine.create_request(RECIPIENT, 1_000 * 10**8)


def test_vault_output_spent_before_mint_is_security_error():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    txid = env.deposit(req)
    env.engine.scan_vault()
    env.chain.mine(30)
    env.chain.spent.add((txid, 0))
    assert env.engine.verify(req["request_id"]) == E.SECURITY_ERROR


def test_expiry_and_reauthorization():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.t[0] += 25 * 3600
    env.engine.expire()
    assert env.engine.get(req["request_id"])["status"] == E.EXPIRED
    env2 = Env()
    r = env2.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env2.deposit(r)
    env2.to_confirmed(r["request_id"])
    b1 = env2.engine.authorize(r["request_id"])
    env2.t[0] += 31 * 60
    with pytest.raises(RuntimeError, match="Expired"):
        env2.eth.mint(b1)
    env2.engine.expire()
    assert env2.engine.get(r["request_id"])["status"] == E.DEPOSIT_CONFIRMED
    b2 = env2.engine.authorize(r["request_id"])
    assert b2["authorization"]["nonce"] != b1["authorization"]["nonce"]
    env2.eth.mint(b2)
    assert env2.engine.observe_mint(r["request_id"]) == E.COMPLETED


def test_burn_release_flow_and_reconciliation():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    dtx = env.deposit(req)
    env.to_confirmed(req["request_id"])
    env.eth.mint(env.engine.authorize(req["request_id"]))
    env.engine.observe_mint(req["request_id"])
    rid = env.eth.burn(RECIPIENT, 400 * 10**8, USER_SOST)
    assert env.engine.ingest_burn(rid, RECIPIENT, 400 * 10**8, USER_SOST, 10_000) == "RELEASE_PENDING"
    assert env.engine.ingest_burn(rid, RECIPIENT, 400 * 10**8, USER_SOST, 10_000) == "DUPLICATE_IGNORED"
    ins = env.engine.release_instruction(rid)
    assert ins["amount_stocks"] == 400 * 10**8 - 10_000 and ins["debit_from_vault_stocks"] == 400 * 10**8
    # cold signer pays: spend the deposit UTXO, 600 change back to the vault, fee 0.0001 to miners
    env.chain.spent.add((dtx, 0))
    rel = keccak(text="release-tx").hex()
    env.chain.add_tx(rel, [{"address": USER_SOST, "stocks": ins["amount_stocks"], "payload_hex": ins["capsule_hex"]},
                           {"address": VAULT, "stocks": 600 * 10**8}],
                     vin=[{"prev_txid": dtx, "index": 0, "address": VAULT, "stocks": 1_000 * 10**8}])
    env.chain.mine(1, include=[rel])
    assert env.engine.confirm_release(rid, rel) == "RELEASE_CONFIRMING"
    env.chain.mine(30)
    assert env.engine.confirm_release(rid, rel) == "RELEASED"
    assert env.engine.reconcile()["status"] == "BALANCED"                  # paid on SOST, not yet recorded on Ethereum
    env.eth.record_release(rid, rel)
    rep = env.engine.reconcile()
    assert rep["status"] == "BALANCED" and rep["vault_stocks"] == 600 * 10**8 and rep["wsost_supply"] == 600 * 10**8


def test_release_with_wrong_amount_is_mismatch():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.deposit(req)
    env.to_confirmed(req["request_id"])
    env.eth.mint(env.engine.authorize(req["request_id"]))
    rid = env.eth.burn(RECIPIENT, 400 * 10**8, USER_SOST)
    env.engine.ingest_burn(rid, RECIPIENT, 400 * 10**8, USER_SOST, 10_000)
    bad = keccak(text="bad-release").hex()
    env.chain.add_tx(bad, [{"address": USER_SOST, "stocks": 300 * 10**8, "payload_hex": release_capsule(bytes.fromhex(rid[2:]))}],
                     vin=[{"prev_txid": "bb" * 32, "index": 0, "address": VAULT, "stocks": 300 * 10**8}])
    env.chain.mine(31, include=[bad])
    assert env.engine.confirm_release(rid, bad) == "RELEASE_MISMATCH"


def test_unbacked_supply_is_critical_and_pauses():
    env = Env()
    req = env.engine.create_request(RECIPIENT, 1_000 * 10**8)
    env.deposit(req)
    env.to_confirmed(req["request_id"])
    env.eth.mint(env.engine.authorize(req["request_id"]))
    env.eth.supply += 50 * 10**8                                            # simulated key-compromise mint
    rep = env.engine.reconcile()
    assert rep["status"] == "CRITICAL" and env.engine.halted and env.eth.paused


# ---------------------------------------------------------------- RPC formats / capsules
def test_rpc_fixtures_parse_exactly_with_decimal():
    for name in ("gettransaction_confirmed.json", "gettxout.json", "getaddressutxos.json"):
        raw = open(os.path.join(FIX, name)).read()
        body = json.loads(raw, parse_float=Decimal)
        assert "result" in body
    tx = json.loads(open(os.path.join(FIX, "gettransaction_confirmed.json")).read(), parse_float=Decimal)["result"]
    assert to_stocks(tx["vout"][0]["amount"]) == 100_000_000_001        # 1000.00000001 exactly
    assert request_id_from_capsule(tx["vout"][0]["payload_hex"]) is not None
    with pytest.raises(TypeError):
        to_stocks(1000.00000001)


def test_capsule_codec_strict():
    rid = keccak(text="r")
    cap = capsule_for_request(rid)
    assert request_id_from_capsule(cap) == rid
    assert len(bytes.fromhex(cap)) <= 255
    assert request_id_from_capsule(build_open_note("C701:0x" + rid.hex().upper())) is None
    enc = bytearray(bytes.fromhex(cap)); enc[4] = 0x01                       # ENCRYPTED flag
    assert request_id_from_capsule(enc.hex()) is None
    assert parse_open_note(cap[:-2]) is None                                 # truncated
    assert request_id_from_capsule(None) is None


def test_engine_rpc_is_read_only():
    with pytest.raises(PermissionError):
        SostRpc("http://127.0.0.1:1").call("sendrawtransaction", "00")
