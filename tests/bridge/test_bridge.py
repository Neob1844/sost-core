"""Stage 1 bridge tests on an in-memory SOST chain (reorgs included) and a Python mirror of WSOST.
Run: python3 -m pytest -q tests/bridge
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ops"))

from eth_account import Account
from sostbridge.common import (to_stocks, fmt_sost, build_open_note, parse_open_note, parse_wsost_recipient,
                               deposit_id, vault_hash, release_note, parse_release)
from sostbridge.sostchain import FakeSostChain
from sostbridge.ethside import FakeWSOST
from sostbridge.observer import Observer, ObserverConfig, collect, still_canonical
from sostbridge.ledger import scan_vault, reconcile, enforce_safety, BALANCED, PENDING, CRITICAL
from sostbridge.signer import (ReleaseProcessor, ReleaseJournal, FakeChainSigner,
                               NativeMultisigSigner, ReleaseRequest, ReleaseSigner)

VAULT = "sost1" + "a" * 40
JUAN = "sost1" + "b" * 40
JUAN_ETH = Account.from_key(b"\x11" * 32).address
ALLOW = to_stocks("0.001")
KEYS = [bytes([0x21 + i]) * 32 for i in range(3)]


def deposit_tx(tag, amount, recipient=JUAN_ETH, sender=JUAN, note=None):
    return {"txid": FakeSostChain.txid_for(tag),
            "vin": [{"address": sender, "amount": fmt_sost(to_stocks(amount) + 5000)}],
            "vout": [{"address": VAULT, "amount": str(amount),
                      "payload_hex": build_open_note(note if note is not None else "WSOST:" + recipient)},
                     {"address": sender, "amount": "0"}]}


class Rig:
    def __init__(self, min_conf=30):
        self.chain = FakeSostChain()
        self.chain.mine(5)
        self.start = 1
        obs = [Account.from_key(k).address for k in KEYS]
        self.eth = FakeWSOST(obs, 2, vault_hash(VAULT), min_conf=min_conf)
        self.min_conf = min_conf
        self.status = None
        cfg = ObserverConfig(vault=VAULT, start_height=self.start, min_confirmations=min_conf,
                             chain_id=self.eth.chain_id, wsost=self.eth.address)
        self.observers = [Observer(f"obs{i}", k, self.chain, cfg, self.eth, status_fn=lambda: self.status) for i, k in enumerate(KEYS)]

    def rec(self):
        r = reconcile(scan_vault(self.chain, VAULT, self.start), self.eth, self.min_conf, ALLOW)
        self.status = r.status
        return r

    def attest_all(self, idx=(0, 1, 2)):
        out = []
        for i in idx:
            for d in self.observers[i].candidates():
                out.append(self.observers[i].attest(d))
        return out

    def relay(self, atts):
        got = collect(atts, 2)
        if got is None:
            return False
        msg, sigs = got
        if not still_canonical(self.chain, msg):
            return False
        self.eth.mint(msg, sigs)
        return True


# ---------------------------------------------------------------- primitives
def test_capsule_roundtrip_and_rejections():
    h = build_open_note("WSOST:" + JUAN_ETH)
    assert parse_open_note(h) == "WSOST:" + JUAN_ETH
    b = bytearray(bytes.fromhex(h))
    enc = bytearray(b); enc[4] = 0x01
    assert parse_open_note(enc.hex()) is None                 # encrypted flag
    bad = bytearray(b); bad[0] = 0x00
    assert parse_open_note(bad.hex()) is None                 # magic
    assert parse_open_note(h[:-2]) is None                     # truncated
    assert parse_open_note("zz") is None
    with pytest.raises(ValueError):
        build_open_note("x" * 81)


def test_recipient_parsing():
    assert parse_wsost_recipient("WSOST:" + JUAN_ETH) == JUAN_ETH
    assert parse_wsost_recipient("WSOST:" + JUAN_ETH.lower()) == JUAN_ETH
    wrong = JUAN_ETH[:2] + JUAN_ETH[2:].swapcase()
    if wrong != JUAN_ETH and wrong[2:] != wrong[2:].lower() and wrong[2:] != wrong[2:].upper():
        assert parse_wsost_recipient("WSOST:" + wrong) is None   # bad EIP-55 checksum
    assert parse_wsost_recipient("WSOST:0x" + "0" * 40) is None
    assert parse_wsost_recipient("WSOST: " + JUAN_ETH) is None
    assert parse_wsost_recipient("WSOST:" + JUAN_ETH + "00") is None


def test_amounts_exact():
    assert to_stocks("500") == 500 * 10**8
    assert to_stocks("0.00000001") == 1
    with pytest.raises(TypeError):
        to_stocks(0.1)
    with pytest.raises(ValueError):
        to_stocks("0.000000001")
    assert fmt_sost(30_000_000_001) == "300.00000001"


def test_deposit_id_deterministic():
    t = FakeSostChain.txid_for("x")
    assert deposit_id(t, 0) == deposit_id(t, 0)
    assert deposit_id(t, 0) != deposit_id(t, 1)
    assert len(release_note(b"\xaa" * 32)) == 80
    assert parse_release(release_note(b"\xaa" * 32)) == b"\xaa" * 32


# ---------------------------------------------------------------- end-to-end on the fake chain
def test_wrap500_unwrap200_balanced(tmp_path):
    r = Rig()
    r.chain.add_block([deposit_tx("juan-500", "500")])
    r.chain.mine(10)
    assert r.rec().status == PENDING                          # waiting confirmations
    assert all(a is None for a in r.attest_all())             # nobody signs before 30
    r.chain.mine(25)
    atts = r.attest_all()
    assert sum(a is not None for a in atts) == 3
    assert len({a.msg.key() for a in atts}) == 1              # identical statement from every observer
    assert r.relay(atts)
    rec = r.rec()
    assert rec.status == BALANCED, rec.reasons
    assert r.eth.balances[JUAN_ETH] == to_stocks("500")

    r.eth.burn(JUAN_ETH, to_stocks("200"), JUAN)
    assert r.rec().status == PENDING                          # burn awaiting release
    proc = ReleaseProcessor(FakeChainSigner(r.chain, VAULT), ReleaseJournal(str(tmp_path / "j.json")),
                            r.chain, VAULT, r.start, ALLOW)
    assert len(proc.process(r.eth)) == 1
    assert proc.process(r.eth) == []                          # never twice
    rec = r.rec()
    assert rec.status == BALANCED, rec.reasons
    assert rec.ledger["H_total_supply"] == to_stocks("300")
    assert rec.ledger["confirmed_backing"] >= to_stocks("300")
    assert rec.ledger["F_completed_releases"] == to_stocks("200") - ALLOW


def test_duplicate_mint_rejected():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35)
    atts = r.attest_all()
    assert r.relay(atts)
    msg, sigs = collect(atts, 2)
    with pytest.raises(RuntimeError, match="DepositAlreadyUsed"):
        r.eth.mint(msg, sigs)
    assert all(a is None for a in r.attest_all())             # observers also refuse used deposits


def test_one_observer_cannot_mint_two_can():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35)
    assert collect(r.attest_all(idx=(0,)), 2) is None
    assert collect(r.attest_all(idx=(1, 2)), 2) is not None   # one observer unavailable: still works


def test_unattributed_payment_not_mintable():
    r = Rig()
    r.chain.add_block([deposit_tx("bad", "7", note="hello")]); r.chain.mine(35)
    assert r.attest_all() == []
    rec = r.rec()
    assert rec.status == BALANCED and rec.warnings


def test_mint_without_deposit_is_critical_and_pauses():
    r = Rig()
    r.eth.force_mint_unbacked(JUAN_ETH, to_stocks("150000"), b"\x99" * 32)   # two compromised observers
    rec = r.rec()
    assert rec.status == CRITICAL
    assert any("mint without a canonical deposit" in x for x in rec.reasons)
    assert any("exceeds confirmed native backing" in x for x in rec.reasons)
    assert enforce_safety(rec, r.eth) is True and r.eth.mint_paused
    r.chain.add_block([deposit_tx("later", "1")]); r.chain.mine(35)
    assert all(a is None for a in r.attest_all())             # no new attestations while CRITICAL


def _release_tx(tag, dest, amount, note):
    return {"txid": FakeSostChain.txid_for(tag), "vin": [{"address": VAULT, "amount": fmt_sost(amount + 3000)}],
            "vout": [{"address": dest, "amount": fmt_sost(amount), "payload_hex": build_open_note(note)},
                     {"address": VAULT, "amount": "0"}]}


def test_release_without_burn_is_critical():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35); r.relay(r.attest_all())
    r.chain.add_block([_release_tx("rogue", JUAN, to_stocks("1"), release_note(b"\x42" * 32))])
    rec = r.rec()
    assert rec.status == CRITICAL and any("without a wSOST burn" in x for x in rec.reasons)


def test_release_amount_and_destination_checked():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35); r.relay(r.attest_all())
    bid = r.eth.burn(JUAN_ETH, to_stocks("4"), JUAN)
    r.chain.add_block([_release_tx("wrong", "sost1" + "c" * 40, to_stocks("5"), release_note(bid))])
    rec = r.rec()
    assert any("amount mismatch" in x for x in rec.reasons)
    assert any("destination substituted" in x for x in rec.reasons)


def test_duplicate_release_is_critical():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35); r.relay(r.attest_all())
    bid = r.eth.burn(JUAN_ETH, to_stocks("4"), JUAN)
    amt = to_stocks("4") - ALLOW
    r.chain.add_block([_release_tx("r1", JUAN, amt, release_note(bid))])
    r.chain.add_block([_release_tx("r2", JUAN, amt, release_note(bid))])
    rec = r.rec()
    assert any("released 2 times" in x for x in rec.reasons)


def test_unexplained_vault_spend_is_critical():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35)
    r.chain.add_block([{"txid": FakeSostChain.txid_for("theft"), "vin": [{"address": VAULT, "amount": "10"}],
                        "vout": [{"address": "sost1" + "e" * 40, "amount": "9.99"}]}])
    assert r.rec().status == CRITICAL


# ---------------------------------------------------------------- reorgs
def test_one_block_reorg_removes_immature_deposit():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")])
    h = r.chain.getblockcount()
    r.chain.reorg(h, [[]])                                     # replaced by an empty block
    r.chain.mine(40)
    assert r.attest_all() == []
    assert r.rec().status == BALANCED


def test_reorg_2_to_5_blocks_deposit_reappears_once():
    for depth in (2, 3, 4, 5):
        r = Rig()
        r.chain.add_block([deposit_tx("d", "10")])
        h = r.chain.getblockcount()
        r.chain.mine(depth - 1)
        r.chain.reorg(h, [[] for _ in range(depth - 1)] + [[deposit_tx("d", "10")]])   # same tx, later block
        r.chain.mine(35)
        atts = r.attest_all()
        assert r.relay(atts)
        assert r.rec().status == BALANCED
        assert len(r.eth.mints) == 1


def test_reorg_after_threshold_stale_attestation_refused():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")])
    h = r.chain.getblockcount()
    r.chain.mine(34)
    atts = r.attest_all()
    assert collect(atts, 2) is not None
    r.chain.reorg(h, [[deposit_tx("d", "10")]] + [[] for _ in range(34)])  # same deposit, different block hash
    assert r.relay(atts) is False                             # relayer refuses the stale statement
    atts2 = r.attest_all()
    assert r.relay(atts2)
    assert r.rec().status == BALANCED


def test_stale_block_hash_forced_mint_is_flagged():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); h = r.chain.getblockcount(); r.chain.mine(34)
    msg, sigs = collect(r.attest_all(), 2)
    r.chain.reorg(h, [[deposit_tx("d", "10")]] + [[] for _ in range(34)])
    r.eth.mint(msg, sigs)                                      # a relayer ignoring the pre-flight
    rec = r.rec()
    assert rec.status == CRITICAL and any("not canonical" in x for x in rec.reasons)


def test_deep_reorg_after_mint_removes_deposit_critical():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); h = r.chain.getblockcount(); r.chain.mine(35)
    assert r.relay(r.attest_all())
    r.chain.reorg(h, [[] for _ in range(40)])                  # deep reorg drops the deposit entirely
    rec = r.rec()
    assert rec.status == CRITICAL and any("without a canonical deposit" in x for x in rec.reasons)
    assert enforce_safety(rec, r.eth)


def test_deposit_disappears_before_maturity_then_reappears_on_branch():
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); h = r.chain.getblockcount(); r.chain.mine(5)
    r.chain.reorg(h, [[] for _ in range(8)])                  # gone
    r.chain.mine(30)
    assert r.attest_all() == []
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35)   # reappears later
    assert r.relay(r.attest_all())
    assert r.rec().status == BALANCED


# ---------------------------------------------------------------- signer abstraction
def test_signer_interface_is_swappable():
    with pytest.raises(NotImplementedError):
        NativeMultisigSigner().execute_release(ReleaseRequest(b"\x00" * 32, JUAN, 1))
    assert issubclass(FakeChainSigner, ReleaseSigner)


def test_mint_amount_or_recipient_differs_from_deposit_is_critical():
    from sostbridge.ethside import MintEvent
    r = Rig()
    r.chain.add_block([deposit_tx("d", "10")]); r.chain.mine(35)
    d = scan_vault(r.chain, VAULT, r.start).deposits[0]
    # a compromised threshold signs the right deposit id but a larger amount
    r.eth.used[d.deposit_id] = True
    r.eth.supply += to_stocks("11")
    r.eth.mints.append(MintEvent(d.deposit_id, d.recipient, to_stocks("11"), bytes.fromhex(d.block_hash), d.height))
    rec = r.rec()
    assert rec.status == CRITICAL and any("mint amount mismatch" in x for x in rec.reasons)
    r2 = Rig()
    r2.chain.add_block([deposit_tx("d", "10")]); r2.chain.mine(35)
    d2 = scan_vault(r2.chain, VAULT, r2.start).deposits[0]
    r2.eth.used[d2.deposit_id] = True
    r2.eth.supply += d2.amount
    r2.eth.mints.append(MintEvent(d2.deposit_id, Account.from_key(b"\x77" * 32).address, d2.amount,
                                  bytes.fromhex(d2.block_hash), d2.height))
    rec2 = r2.rec()
    assert rec2.status == CRITICAL and any("recipient mismatch" in x for x in rec2.reasons)
