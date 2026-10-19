"""C701 verification engine: request -> deposit detection -> verification -> EIP-712 authorization,
plus refund guard, burn -> release, reorg handling and reconciliation. Idempotent SQLite ledger.

Single-operator, centralized by design and by admission: whoever holds the authorizer key(s) can
authorize mints. Every decision is logged in the public `log` table and every authorization carries
the full deposit statement so anyone can re-verify it against the SOST chain.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Callable, Optional

from eth_utils import keccak, is_address, is_checksum_address, to_checksum_address

from . import fee as feemod
from .eip712 import deposit_id, request_id, sign_mint
from .pricing import PriceUnavailable, ValuationNotApproved
from .sost import RpcError, capsule_for_request, is_sost_address, is_txid, release_capsule, \
    request_id_from_capsule, to_stocks

# ---- the 10 public states (UI) + internal terminal states
REQUEST_CREATED = "REQUEST_CREATED"          # Solicitud creada
AWAITING_SOST = "AWAITING_SOST"              # Esperando SOST
VERIFYING = "VERIFYING"                      # Verificando blockchain
DEPOSIT_CONFIRMED = "DEPOSIT_CONFIRMED"      # Depósito confirmado
AUTH_READY = "AUTH_READY"                    # Autorización lista
AWAITING_METAMASK = "AWAITING_METAMASK"      # Esperando firma MetaMask
MINTING = "MINTING"                          # Emisión en curso
COMPLETED = "COMPLETED"                      # Completada
PENDING_RECOVERY = "PENDING_RECOVERY"        # Pendiente de recuperación
SECURITY_ERROR = "SECURITY_ERROR"            # Error de seguridad
EXPIRED = "EXPIRED"                          # request expired with no deposit (nothing to recover)
REFUND_PREPARED = "REFUND_PREPARED"          # refund instruction handed to the cold signer
REFUNDED = "REFUNDED"

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
  request_id TEXT PRIMARY KEY, recipient TEXT NOT NULL, amount INTEGER NOT NULL, salt TEXT NOT NULL,
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, status TEXT NOT NULL,
  deposit_txid TEXT, deposit_vout INTEGER, deposit_id TEXT UNIQUE, block_height INTEGER, block_hash TEXT,
  confirmations INTEGER, deposit_amount INTEGER, refund_address TEXT, auth_json TEXT, auth_nonce INTEGER, auth_expiry INTEGER,
  mint_tx TEXT, reason TEXT, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS releases (
  release_id TEXT PRIMARY KEY, holder TEXT NOT NULL, amount INTEGER NOT NULL, sost_address TEXT NOT NULL,
  network_fee INTEGER NOT NULL, status TEXT NOT NULL, sost_txid TEXT, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS log (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, kind TEXT, ref TEXT, detail TEXT);
"""


class EngineHalted(Exception):
    pass


class Engine:
    def __init__(self, db_path: str, rpc, eth, *, chain_id: int, bridge: str, vault_address: str,
                 authorizer_key, price_signer, oracle, valuation, observations: Callable[[], list],
                 min_confirmations=30, request_ttl=24 * 3600, auth_ttl=30 * 60, release_fee=10_000,
                 now: Callable[[], int] = lambda: int(time.time())):
        if not is_sost_address(vault_address):
            raise ValueError("bad vault address")
        self.db = sqlite3.connect(db_path, isolation_level=None)
        self.db.executescript(SCHEMA)
        self.rpc, self.eth = rpc, eth
        self.chain_id, self.bridge = chain_id, to_checksum_address(bridge)
        self.vault, self.vault_hash = vault_address, keccak(text=vault_address)
        self.key, self.price_signer, self.oracle, self.valuation = authorizer_key, price_signer, oracle, valuation
        self.observations = observations
        self.min_conf, self.request_ttl, self.auth_ttl, self.release_fee = min_confirmations, request_ttl, auth_ttl, release_fee
        self.now = now
        self.halted = False

    # ------------------------------------------------------------------ helpers
    def _log(self, kind, ref, **detail):
        self.db.execute("INSERT INTO log(ts,kind,ref,detail) VALUES(?,?,?,?)",
                        (self.now(), kind, ref, json.dumps(detail, sort_keys=True, default=str)))

    def _set(self, rid, status, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        sql = f"UPDATE requests SET status=?, updated_at=?{', ' + cols if cols else ''} WHERE request_id=?"
        self.db.execute(sql, (status, self.now(), *fields.values(), rid))
        self._log("state", rid, status=status, **{k: v for k, v in fields.items() if k != "auth_json"})

    def get(self, rid):
        cur = self.db.execute("SELECT * FROM requests WHERE request_id=?", (rid,))
        row = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], row)) if row else None

    def _next_nonce(self):
        self.db.execute("INSERT OR IGNORE INTO counters VALUES('nonce', 0)")
        self.db.execute("UPDATE counters SET value = value + 1 WHERE name='nonce'")
        return self.db.execute("SELECT value FROM counters WHERE name='nonce'").fetchone()[0]

    def halt(self, why):
        """Fail closed: stop issuing authorizations and ask the pauser to pause minting on-chain."""
        self.halted = True
        self._log("HALT", "engine", reason=why)
        if hasattr(self.eth, "pause_mint"):
            self.eth.pause_mint(why)

    def _quote(self):
        """Fresh XAUT/EUR + approved SOST/EUR, or raise. Blocks everything without a valuation."""
        xo = self.oracle.aggregate(self.observations(), self.now())
        return self.price_signer.quote(xo, self.valuation)

    # ------------------------------------------------------------------ 1. request
    def create_request(self, recipient: str, amount_stocks: int):
        if self.halted:
            raise EngineHalted("engine halted")
        if not isinstance(amount_stocks, int) or amount_stocks <= 0:
            raise ValueError("amount must be positive integer stocks")
        if not is_address(recipient) or int(recipient, 16) == 0:
            raise ValueError("bad Ethereum recipient")
        body = recipient[2:]
        if body != body.lower() and body != body.upper() and not is_checksum_address(recipient):
            raise ValueError("Ethereum address checksum mismatch")
        q, _, _ = self._quote()            # raises ValuationNotApproved / PriceUnavailable
        fee_units = feemod.fee_xaut_for_amount(amount_stocks, q["sostEur8"], q["xautEur8"])  # raises below 100 EUR
        salt = os.urandom(32)
        rid = request_id(self.chain_id, self.bridge, to_checksum_address(recipient), amount_stocks, self.vault_hash, salt)
        now = self.now()
        self.db.execute("INSERT INTO requests(request_id,recipient,amount,salt,created_at,expires_at,status,updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?)", ("0x" + rid.hex(), to_checksum_address(recipient), amount_stocks,
                                                    salt.hex(), now, now + self.request_ttl, REQUEST_CREATED, now))
        self._log("request", "0x" + rid.hex(), recipient=recipient, amount=amount_stocks, salt=salt.hex())
        self._set("0x" + rid.hex(), AWAITING_SOST)
        return {"request_id": "0x" + rid.hex(), "vault": self.vault, "amount_stocks": amount_stocks,
                "capsule_hex": capsule_for_request(rid), "expires_at": now + self.request_ttl,
                "estimated_fee_xaut_units": fee_units, "xaut_eur8": q["xautEur8"],
                "note": "estimate only; the binding fee is fixed by the signed quote at authorization time"}

    # ------------------------------------------------------------------ 2. detection (automatic)
    def scan_vault(self):
        """Automatic detection: list the vault's UTXOs, match capsules to open requests.
        A user-typed hash is never needed; `lookup_hint` exists only for recovery/search."""
        for u in self.rpc.call("getaddressutxos", self.vault):
            rid_b = request_id_from_capsule(u.get("payload"))
            if rid_b is None:
                self._unbound_deposit(u["txid"], int(u["vout"]))
                continue
            r = self.get("0x" + rid_b.hex())
            if r is None:
                self._unbound_deposit(u["txid"], int(u["vout"]), why="capsule names an unknown request")
                continue
            if r["deposit_txid"] is None and r["status"] in (AWAITING_SOST, EXPIRED):
                did = "0x" + deposit_id(u["txid"], int(u["vout"])).hex()
                try:
                    self.db.execute("UPDATE requests SET deposit_txid=?, deposit_vout=?, deposit_id=? WHERE request_id=?",
                                    (u["txid"], int(u["vout"]), did, r["request_id"]))
                except sqlite3.IntegrityError:
                    self._set(r["request_id"], SECURITY_ERROR, reason="deposit already bound to another request")
                    continue
                self._set(r["request_id"], VERIFYING)

    def _unbound_deposit(self, txid, vout, why="no C701 capsule"):
        did = "0x" + deposit_id(txid, vout).hex()
        known = self.db.execute("SELECT 1 FROM requests WHERE deposit_id=?", (did,)).fetchone()
        if known:
            return
        if self.db.execute("SELECT 1 FROM log WHERE kind='unbound' AND ref=?", (did,)).fetchone():
            return
        self._log("unbound", did, txid=txid, vout=vout, reason=why, action="PENDING_RECOVERY: revoke on Ethereum, then refund")

    def lookup_hint(self, request_id_hex: str, txid: str):
        """Recovery/search only: a hash typed by a user is a HINT. Everything is re-verified from the node."""
        if not is_txid(txid):
            return {"ok": False, "error": "invalid transaction hash format"}
        try:
            tx = self.rpc.call("gettransaction", txid)
        except RpcError:
            return {"ok": False, "error": "transaction not found on the SOST node"}
        for n, o in enumerate(tx["vout"]):
            if o["address"] == self.vault and request_id_from_capsule(o.get("payload_hex")) == bytes.fromhex(request_id_hex[2:]):
                return {"ok": True, "vout": n, "note": "found; the automatic verifier will process it"}
        return {"ok": False, "error": "transaction does not pay the bridge vault for this request"}

    # ------------------------------------------------------------------ 3. verification
    def verify(self, rid):
        r = self.get(rid)
        if r["status"] not in (VERIFYING, DEPOSIT_CONFIRMED, AUTH_READY, AWAITING_METAMASK, MINTING):
            return r["status"]
        txid, n = r["deposit_txid"], r["deposit_vout"]
        try:
            tx = self.rpc.call("gettransaction", txid)
        except RpcError:
            return self._lost_deposit(r, "deposit transaction disappeared (reorg)")
        if tx.get("in_mempool") or tx["block_height"] < 0:
            return self._lost_deposit(r, "deposit back in mempool (reorg)") if r["block_hash"] else VERIFYING
        if not r["refund_address"] and tx.get("vin"):
            # refund destination = the depositor's first input address (authenticated by its signature)
            self.db.execute("UPDATE requests SET refund_address=? WHERE request_id=?", (tx["vin"][0]["address"], rid))
        if n >= len(tx["vout"]):
            return self._recover(r, "vout out of range")
        o = tx["vout"][n]
        self.db.execute("UPDATE requests SET deposit_amount=? WHERE request_id=?", (to_stocks(o["amount"]), rid))
        if o["address"] != self.vault:
            return self._recover(r, "output does not pay the bridge vault")
        if int(o.get("type", 0)) != 0:
            return self._recover(r, "vault output is not a standard output")
        if request_id_from_capsule(o.get("payload_hex")) != bytes.fromhex(rid[2:]):
            return self._recover(r, "capsule does not commit to this request")
        if to_stocks(o["amount"]) != r["amount"]:
            return self._recover(r, f"amount mismatch: got {to_stocks(o['amount'])} expected {r['amount']}")
        bh = self.rpc.call("getblockhash", tx["block_height"])
        if r["block_hash"] and (r["block_hash"] != bh or r["block_height"] != tx["block_height"]):
            # included in a different block than the one we recorded: a reorg moved it
            if r["status"] in (AUTH_READY, AWAITING_METAMASK, MINTING):
                return self._lost_deposit(r, "deposit block changed after authorization")
        if tx["confirmations"] < self.min_conf:
            self.db.execute("UPDATE requests SET block_height=?, block_hash=?, confirmations=? WHERE request_id=?",
                            (tx["block_height"], bh, tx["confirmations"], rid))
            return VERIFYING
        if self.rpc.call("gettxout", txid, n) is None:
            return self._recover(r, "vault output already spent before mint", security=True)
        # re-read the block hash after the depth check: closes the read-race with a reorg
        if self.rpc.call("getblockhash", tx["block_height"]) != bh:
            return VERIFYING
        if r["status"] == VERIFYING:
            self._set(rid, DEPOSIT_CONFIRMED, block_height=tx["block_height"], block_hash=bh, confirmations=tx["confirmations"])
        return self.get(rid)["status"]

    def _recover(self, r, why, security=False):
        self._set(r["request_id"], SECURITY_ERROR if security else PENDING_RECOVERY, reason=why)
        if security:
            self.halt(why)
        return self.get(r["request_id"])["status"]

    def _lost_deposit(self, r, why):
        if r["status"] in (AUTH_READY, AWAITING_METAMASK, MINTING) or self.eth.deposit_used(bytes.fromhex(r["deposit_id"][2:])):
            # an authorization exists or a mint happened against a deposit that is no longer final
            self._set(r["request_id"], SECURITY_ERROR, reason=why)
            self.halt(why)
        else:
            self._set(r["request_id"], VERIFYING, block_hash=None, block_height=None, confirmations=0, reason=why)
        return self.get(r["request_id"])["status"]

    # ------------------------------------------------------------------ 4. authorization
    def authorize(self, rid):
        if self.halted:
            raise EngineHalted("engine halted")
        r = self.get(rid)
        if r["status"] == AUTH_READY and r["auth_expiry"] > self.now():
            return json.loads(r["auth_json"])                  # idempotent: same live authorization
        if r["status"] not in (DEPOSIT_CONFIRMED, AUTH_READY, AWAITING_METAMASK):
            raise ValueError(f"cannot authorize in state {r['status']}")
        if self.verify(rid) not in (DEPOSIT_CONFIRMED, AUTH_READY, AWAITING_METAMASK):
            raise ValueError("deposit no longer verifies")
        did = bytes.fromhex(r["deposit_id"][2:])
        if self.eth.deposit_used(did):
            if self.eth.deposit_revoked(did):
                raise ValueError("deposit revoked on Ethereum (refund path)")
            self._set(rid, COMPLETED, reason="already minted on-chain")
            return None
        q, psig, phash = self._quote()
        fee_units = feemod.fee_xaut_for_amount(r["amount"], q["sostEur8"], q["xautEur8"])
        a = {"requestId": bytes.fromhex(rid[2:]), "recipient": r["recipient"], "amount": r["amount"],
             "depositTxid": bytes.fromhex(r["deposit_txid"]), "depositVout": r["deposit_vout"],
             "bridgeVault": self.vault_hash, "sostBlockHash": bytes.fromhex(r["block_hash"]),
             "sostBlockHeight": r["block_height"], "confirmations": r["confirmations"], "feeXaut": fee_units,
             "priceHash": phash, "expiry": self.now() + self.auth_ttl, "nonce": self._next_nonce()}
        sig = sign_mint(a, self.chain_id, self.bridge, self.key)
        bundle = {"authorization": {k: ("0x" + v.hex() if isinstance(v, bytes) else v) for k, v in a.items()},
                  "quote": {k: ("0x" + v.hex() if isinstance(v, bytes) else v) for k, v in q.items()},
                  "authSigs": ["0x" + sig.hex()], "priceSig": "0x" + psig.hex(),
                  "fee_xaut": feemod.fmt_xaut(fee_units), "chainId": self.chain_id, "bridge": self.bridge}
        self._set(rid, AUTH_READY, auth_json=json.dumps(bundle), auth_nonce=a["nonce"], auth_expiry=a["expiry"])
        return bundle

    # UI transitions reported by the dApp (informational; the chain is the source of truth)
    def wallet_signing(self, rid):
        if self.get(rid)["status"] == AUTH_READY:
            self._set(rid, AWAITING_METAMASK)

    def mint_submitted(self, rid, eth_tx):
        if self.get(rid)["status"] in (AUTH_READY, AWAITING_METAMASK):
            self._set(rid, MINTING, mint_tx=eth_tx)

    def observe_mint(self, rid, eth_tx=None):
        r = self.get(rid)
        if r["deposit_id"] and self.eth.deposit_used(bytes.fromhex(r["deposit_id"][2:])) \
                and not self.eth.deposit_revoked(bytes.fromhex(r["deposit_id"][2:])):
            self._set(rid, COMPLETED, mint_tx=eth_tx or r["mint_tx"])
        return self.get(rid)["status"]

    def expire(self):
        """Requests with no deposit expire; expired authorizations fall back to DEPOSIT_CONFIRMED
        (re-authorizable after re-verification — the contract's deposit-id guard prevents double mint)."""
        now = self.now()
        for (rid,) in self.db.execute("SELECT request_id FROM requests WHERE status=? AND expires_at<?", (AWAITING_SOST, now)).fetchall():
            self._set(rid, EXPIRED, reason="no deposit before request expiry")
        for (rid,) in self.db.execute("SELECT request_id FROM requests WHERE status IN (?,?,?) AND auth_expiry<?",
                                      (AUTH_READY, AWAITING_METAMASK, MINTING, now)).fetchall():
            if self.observe_mint(rid) != COMPLETED:
                self._set(rid, DEPOSIT_CONFIRMED, reason="authorization expired unused")

    # ------------------------------------------------------------------ 5. refund (cannot keep both)
    def prepare_refund(self, rid):
        """Refund only after (1) the deposit is REVOKED on Ethereum and that revoke is FINAL, and
        (2) every authorization ever issued for it has expired. Then the deposit can never mint."""
        r = self.get(rid)
        if r["status"] not in (PENDING_RECOVERY, DEPOSIT_CONFIRMED, AUTH_READY, AWAITING_METAMASK, MINTING, EXPIRED):
            raise ValueError(f"no refund in state {r['status']}")
        if not r["deposit_id"]:
            raise ValueError("no deposit bound to this request")
        did = bytes.fromhex(r["deposit_id"][2:])
        if not self.eth.deposit_revoked(did):
            return {"ok": False, "next": "call SOSTBridge.revokeDeposit(txid, vout, reason) and wait for finality"}
        if not self.eth.revoke_final(did):
            return {"ok": False, "next": "wait for Ethereum finality of the revoke"}
        if r["auth_expiry"] and r["auth_expiry"] >= self.now():
            return {"ok": False, "next": "wait until the issued authorization has expired"}
        if not r.get("refund_address"):
            return {"ok": False, "next": "refund address unknown — manual review"}
        tx = self.rpc.call("gettransaction", r["deposit_txid"])
        amt = to_stocks(tx["vout"][r["deposit_vout"]]["amount"])
        instr = {"kind": "REFUND", "spend": f"{r['deposit_txid']}:{r['deposit_vout']}", "to": r["refund_address"],
                 "amount_stocks": amt - self.release_fee, "network_fee_stocks": self.release_fee,
                 "signer": "COLD vault key (offline); no hot release key exists"}
        self._set(rid, REFUND_PREPARED, reason=json.dumps(instr))
        return {"ok": True, "instruction": instr}

    # ------------------------------------------------------------------ 6. burn -> release
    def ingest_burn(self, release_id: str, holder: str, amount: int, sost_address: str, network_fee: int):
        if self.db.execute("SELECT 1 FROM releases WHERE release_id=?", (release_id,)).fetchone():
            return "DUPLICATE_IGNORED"
        status = "RELEASE_PENDING" if is_sost_address(sost_address) else "RELEASE_BAD_ADDRESS"
        self.db.execute("INSERT INTO releases VALUES(?,?,?,?,?,?,?,?)",
                        (release_id, holder, amount, sost_address, network_fee, status, None, self.now()))
        self._log("burn", release_id, holder=holder, amount=amount, to=sost_address)
        return status

    def release_instruction(self, release_id):
        r = self.db.execute("SELECT amount, sost_address, network_fee, status FROM releases WHERE release_id=?", (release_id,)).fetchone()
        if not r or r[3] != "RELEASE_PENDING":
            raise ValueError("no pending release")
        return {"kind": "RELEASE", "release_id": release_id, "to": r[1], "amount_stocks": r[0] - r[2],
                "network_fee_stocks": r[2], "capsule_hex": release_capsule(bytes.fromhex(release_id[2:])),
                "debit_from_vault_stocks": r[0], "signer": "COLD vault key (offline)"}

    def confirm_release(self, release_id, sost_txid):
        """Verify the release on SOST (vault -> destination, exact net amount, capsule bound to releaseId,
        min confirmations). Only then mark RELEASED (and call SOSTBridge.recordRelease)."""
        row = self.db.execute("SELECT amount, sost_address, network_fee, status FROM releases WHERE release_id=?", (release_id,)).fetchone()
        if not row:
            raise ValueError("unknown release")
        if row[3] == "RELEASED":
            return "RELEASED"
        tx = self.rpc.call("gettransaction", sost_txid)
        if tx.get("in_mempool") or tx["confirmations"] < self.min_conf:
            return "RELEASE_CONFIRMING"
        ok = any(o["address"] == row[1] and to_stocks(o["amount"]) == row[0] - row[2]
                 and o.get("payload_hex") == release_capsule(bytes.fromhex(release_id[2:])) for o in tx["vout"])
        if not ok or not all(i["address"] == self.vault for i in tx["vin"]):
            self._log("release_mismatch", release_id, txid=sost_txid)
            return "RELEASE_MISMATCH"
        self.db.execute("UPDATE releases SET status='RELEASED', sost_txid=?, updated_at=? WHERE release_id=?",
                        (sost_txid, self.now(), release_id))
        self._log("released", release_id, sost_txid=sost_txid)
        return "RELEASED"

    # ------------------------------------------------------------------ 7. reconciliation
    def reconcile(self):
        """Locked SOST vs wSOST obligations.
        obligations = wSOST supply + burned-but-unreleased (+ release network fees are paid from the burned amount)
        in-flight   = confirmed deposits not yet minted, revoked-not-yet-refunded deposits
        BALANCED  : vault == obligations + in-flight (+ unbound deposits awaiting refund)
        PENDING   : vault >  that (unexplained surplus or deposits still confirming) — investigate, no action
        CRITICAL  : vault <  obligations -> unbacked wSOST may exist -> HALT + pause minting"""
        vault = int(self.rpc.call("getaddressbalance", self.vault)["balance_stocks"])
        supply = self.eth.total_supply()
        unreleased = self.eth.burned_unreleased()
        # releases already paid on SOST but whose recordRelease is not yet on Ethereum
        paid_not_recorded = sum(a for rid, a in self.db.execute(
            "SELECT release_id, amount FROM releases WHERE status='RELEASED'").fetchall()
            if not self.eth.release_recorded(rid))
        obligations = supply + unreleased - paid_not_recorded
        inflight = 0
        for status, amt in self.db.execute(
                "SELECT status, COALESCE(deposit_amount, amount) FROM requests WHERE deposit_id IS NOT NULL").fetchall():
            if status in (VERIFYING, DEPOSIT_CONFIRMED, AUTH_READY, AWAITING_METAMASK, MINTING, PENDING_RECOVERY, REFUND_PREPARED, EXPIRED):
                inflight += amt
        unbound = 0
        own = {t for (t,) in self.db.execute("SELECT sost_txid FROM releases WHERE sost_txid IS NOT NULL")}
        for u in self.rpc.call("getaddressutxos", self.vault):
            if u["txid"] in own:
                continue                                   # change of the vault's own release transactions
            did = "0x" + deposit_id(u["txid"], int(u["vout"])).hex()
            if not self.db.execute("SELECT 1 FROM requests WHERE deposit_id=?", (did,)).fetchone():
                unbound += int(u["amount_stocks"])
        expected = obligations + inflight + unbound
        if vault < obligations:
            status = "CRITICAL"
            self.halt(f"vault {vault} < obligations {obligations}")
        elif vault == expected:
            status = "BALANCED"
        else:
            status = "PENDING"
        report = {"status": status, "vault_stocks": vault, "wsost_supply": supply, "burned_unreleased": unreleased,
                  "obligations": obligations, "paid_not_recorded": paid_not_recorded, "in_flight_deposits": inflight, "unbound_deposits": unbound,
                  "difference": vault - expected, "ts": self.now()}
        self._log("reconcile", status, **report)
        return report
