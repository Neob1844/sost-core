#!/usr/bin/env python3
"""Atomic-swap completion audit — cross-chain cases D1-D8, D10 + secret-flow vector (E).

Real SOST DEVNET_FAST node + real sost-miner, real Anvil + REAL WSOST + AtomicSwapHTLCv2.
SOST txs: built by the unchanged `sost-cli createhtlclock/claimhtlc/refundhtlc`, signed by the
lab signer (tests/bridge/lab/sost_lab_sign.cpp; NOT a shipped tool), broadcast via sendrawtransaction.

usage: e2e_cases.py <base_dir_with_bootstrapped_chain> <work_dir>
"""
import os
import shutil
import sys
sys.path.insert(0, os.path.dirname(__file__))
from swaplab import *   # noqa

base, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
if os.path.exists(work):
    shutil.rmtree(work)
shutil.copytree(base, work, ignore=shutil.ignore_patterns("*.log"))

A = Sost(work, "nodeA", 19801, 19811).start()
E = Evm(work, 18547)
wa, alice = new_wallet(work, "alice.json")
wb, bob = new_wallet(work, "bob.json")
wv, vault = new_wallet(work, "vault.json")
E.setup_wsost(vault, 500 * STOCK)
BASE = E.bridge_state()
VAULT0 = A.balance(vault)
log(f"SOST tip {A.height()} · Alice {A.balance(alice)/STOCK} SOST · Bob {E.bal(E.bob)/STOCK} wSOST · WSOST {E.wsost.address} HTLCv2 {E.htlc.address}")


def mine1(n=1):
    got = A.mine(n, wa, alice)
    assert got == n, f"mined {got}/{n}"


def mine_until(h):
    assert A.mine_to(h, wa, alice), f"could not reach {h}"


def bridge_unchanged(label):
    now = E.bridge_state()
    diff = {k: (BASE[k], now[k]) for k in BASE if BASE[k] != now[k]}
    step(f"{label}: wSOST supply/minted/burned/burnNonce/mintPaused + Bridge Vault SOST UNCHANGED",
         not diff and A.balance(vault) == VAULT0, str(diff))


def verify_sost_lock(txid, H, claim_addr, refund_addr, amount, rh, min_conf=1):
    st = A.htlc(txid)
    ok = (st["status"] == "locked" and st["hashlock"] == H and st["claim_pkh"] == pkh(claim_addr)
          and st["refund_pkh"] == pkh(refund_addr) and round(float(st["amount"]) * STOCK) == amount
          and int(st["refund_height"]) == rh and A.confs(txid) >= min_conf)
    return ok, st


def verify_evm_lock(sid, H, claimer, refunder, amount, rt):
    s = E.swap(sid)
    return (s["state"] == 1 and s["token"] == E.wsost.address and s["locked"] == amount and s["hashlock"] == H
            and s["claimer"] == claimer and s["refunder"] == refunder and s["refundTime"] == rt), s


try:
    # =========================================================== E + D1: SOST -> wSOST
    log("\n=== D1  SOST -> wSOST (Alice initiates, holds the secret) + E fixed vector ===")
    P = bytes(range(32)).hex()
    H = hashlib.sha256(bytes.fromhex(P)).hexdigest()
    step("E0 vector: sha256(000102..1f) = 630dcd29…10dd (python hashlib)",
         H == "630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd")
    amt, wamt = 2 * STOCK, 199 * STOCK // 100
    u = pick_utxo(A, alice, amt + FEE)
    rh = A.height() + 40
    raw, signed = sost_lock(A, wa, alice, u, H, rh, bob, alice, amt)
    dec = json.loads(cli("decodehtlc", signed)[1])
    step("E1 decodehtlc(lock) shows the hashlock bytes exactly as given (no byte reversal)", dec.get("hashlock") == H, dec.get("hashlock", ""))
    lock1 = A.send(signed)
    mine1()
    ok, st = verify_sost_lock(lock1, H, bob, alice, amt, rh)
    step("D1.1 Alice SOST lock confirmed; Bob verifies hashlock/claim/refund pkh/amount/refund_height/confs via gethtlcstatus", ok, json.dumps(st, default=str)[:200])
    sid1 = hashlib.sha256(b"D1" + bytes.fromhex(H)).digest()
    rt1 = E.w3.eth.block_number + 20
    E.lock(E.bob, sid1, wamt, bytes.fromhex(H), rt1, E.alice, E.bob)
    ok, s = verify_evm_lock(sid1, H, E.alice, E.bob, wamt, rt1)
    step("D1.2 Bob wSOST lock; Alice verifies token/amount/hashlock/claimer/refunder/refundTime via getSwap", ok)
    step("E2 same 32-byte hashlock on both chains (SOST payload hex == EVM bytes32 hex)", s["hashlock"] == st["hashlock"] == H)
    a0 = E.bal(E.alice)
    E.tx(E.htlc.functions.claimERC20(sid1, bytes.fromhex(P), wamt), E.alice)
    step("D1.3 Alice claims wSOST with the preimage", E.bal(E.alice) - a0 == wamt)
    Px = E.extract_preimage(sid1)
    step("E3 Bob's watcher extracts the preimage from the Claimed log (eth_getLogs by swapId)", Px == P, str(Px))
    b0 = A.balance(bob)
    c1 = A.send(sost_claim(wb, bob, lock1, amt, Px, bob))
    mine1()
    st = A.htlc(lock1)
    step("D1.4 Bob claims the SOST HTLC with the extracted preimage", A.confs(c1) >= 1 and A.balance(bob) - b0 == amt - FEE,
         f"+{(A.balance(bob)-b0)/STOCK} SOST")
    step("E4 SOST node reports CLAIMED + revealed_preimage byte-identical to the EVM preimage",
         st["status"] == "claimed" and st.get("revealed_preimage") == P, st.get("revealed_preimage", ""))
    raw_claim = A.call("getrawtransaction", [c1])
    raw_claim = raw_claim if isinstance(raw_claim, str) else raw_claim.get("hex", "")
    dc = json.loads(cli("decodehtlc", raw_claim)[1])
    step("E5 independent extraction: decodehtlc(getrawtransaction(claim)) preimage == P", dc.get("preimage") == P)
    bridge_unchanged("D1.5")

    # =========================================================== D2: wSOST -> SOST
    log("\n=== D2  wSOST -> SOST (Bob initiates, holds the secret) ===")
    S2 = secrets.token_bytes(32).hex()
    H2 = hashlib.sha256(bytes.fromhex(S2)).hexdigest()
    sid2 = hashlib.sha256(b"D2" + bytes.fromhex(H2)).digest()
    rt2 = E.w3.eth.block_number + 60                 # initiator's lock: LONGER timeout
    E.lock(E.bob, sid2, wamt, bytes.fromhex(H2), rt2, E.alice, E.bob)
    ok, _ = verify_evm_lock(sid2, H2, E.alice, E.bob, wamt, rt2)
    step("D2.1 Bob (initiator) locks wSOST first; Alice verifies", ok)
    u = pick_utxo(A, alice, amt + FEE)
    rh2 = A.height() + 20                            # responder's lock: SHORTER timeout
    _, signed = sost_lock(A, wa, alice, u, H2, rh2, bob, alice, amt)
    lock2 = A.send(signed)
    mine1()
    ok, _ = verify_sost_lock(lock2, H2, bob, alice, amt, rh2)
    step("D2.2 Alice locks SOST (claim=Bob, refund=Alice) with Bob's hashlock", ok)
    b0 = A.balance(bob)
    c2 = A.send(sost_claim(wb, bob, lock2, amt, S2, bob))
    mine1()
    step("D2.3 Bob claims SOST, revealing the secret on the SOST chain", A.balance(bob) - b0 == amt - FEE)
    rev = A.htlc(lock2).get("revealed_preimage")
    step("D2.4 Alice extracts the secret from the SOST chain (gethtlcstatus revealed_preimage)", rev == S2)
    a0 = E.bal(E.alice)
    E.tx(E.htlc.functions.claimERC20(sid2, bytes.fromhex(rev), wamt), E.alice)
    step("D2.5 Alice claims wSOST with the extracted secret", E.bal(E.alice) - a0 == wamt)
    bridge_unchanged("D2.6")

    # =========================================================== D3: Alice disappears
    log("\n=== D3  Alice (initiator) disappears after both locks -> both refund ===")
    S3 = secrets.token_bytes(32).hex(); H3 = hashlib.sha256(bytes.fromhex(S3)).hexdigest()
    u = pick_utxo(A, alice, amt + FEE)
    rh3 = A.height() + 10
    lock3 = A.send(sost_lock(A, wa, alice, u, H3, rh3, bob, alice, amt)[1]); mine1()
    sid3 = hashlib.sha256(b"D3" + bytes.fromhex(H3)).digest(); rt3 = E.w3.eth.block_number + 6
    E.lock(E.bob, sid3, wamt, bytes.fromhex(H3), rt3, E.alice, E.bob)
    ok, why = E.try_tx(E.htlc.functions.refundERC20(sid3), E.bob)
    step("D3.1 Bob's early wSOST refund rejected", not ok and "NOT_YET" in str(why), str(why)[:80])
    E.mine(rt3 - E.w3.eth.block_number)
    b0 = E.bal(E.bob)
    ok, _ = E.try_tx(E.htlc.functions.refundERC20(sid3), E.bob)
    step("D3.2 Bob refunds wSOST after refundTime", ok and E.bal(E.bob) - b0 == wamt)
    rf = sost_refund(wa, alice, lock3, amt, alice)
    ok, why = A.try_send(rf)
    step("D3.3 Alice's early SOST refund rejected (R24)", not ok and "R24" in why, why[:100])
    mine_until(rh3 - 1)
    a0 = A.balance(alice)
    ok, r3 = A.try_send(rf)
    mine1()
    step("D3.4 Alice refunds SOST at refund_height", ok and A.confs(r3) >= 1, str(r3)[:80])
    step("D3.5 gethtlcstatus reports refunded", A.htlc(lock3)["status"] in ("refunded",), A.htlc(lock3)["status"])

    # =========================================================== D4: Bob disappears
    log("\n=== D4  Bob never locks -> Alice refunds ===")
    S4 = secrets.token_bytes(32).hex(); H4 = hashlib.sha256(bytes.fromhex(S4)).hexdigest()
    u = pick_utxo(A, alice, amt + FEE)
    rh4 = A.height() + 6
    lock4 = A.send(sost_lock(A, wa, alice, u, H4, rh4, bob, alice, amt)[1]); mine1()
    mine_until(rh4 - 1)
    ok, r4 = A.try_send(sost_refund(wa, alice, lock4, amt, alice)); mine1()
    step("D4.1 Alice refunds her SOST after timeout (Bob never funded)", ok and A.confs(r4) >= 1)

    # =========================================================== D5: wrong secret / key / replay
    log("\n=== D5  wrong secret / wrong key / replay ===")
    S5 = secrets.token_bytes(32).hex(); H5 = hashlib.sha256(bytes.fromhex(S5)).hexdigest()
    u = pick_utxo(A, alice, amt + FEE)
    rh5 = A.height() + 30
    lock5 = A.send(sost_lock(A, wa, alice, u, H5, rh5, bob, alice, amt)[1]); mine1()
    sid5 = hashlib.sha256(b"D5" + bytes.fromhex(H5)).digest()
    E.lock(E.bob, sid5, wamt, bytes.fromhex(H5), E.w3.eth.block_number + 20, E.alice, E.bob)
    ok, why = A.try_send(sost_claim(wb, bob, lock5, amt, secrets.token_hex(32), bob))
    step("D5.1 SOST claim with wrong preimage rejected (R21)", not ok and "R21" in why, why[:90])
    ok, why = A.try_send(sost_claim(wa, alice, lock5, amt, S5, alice))
    step("D5.2 SOST claim signed by the refund key (not claim key) rejected", not ok, why[:90])
    ok, why = A.try_send(sost_refund(wb, bob, lock5, amt, bob))
    step("D5.3 SOST refund by the claim key before timeout rejected", not ok, why[:90])
    ok, why = E.try_tx(E.htlc.functions.claimERC20(sid5, bytes.fromhex(secrets.token_hex(32)), 0), E.alice)
    step("D5.4 EVM claim with wrong preimage reverts BAD_PREIMAGE", not ok and "BAD_PREIMAGE" in str(why))
    ok, why = E.try_tx(E.htlc.functions.claimERC20(sid5, bytes.fromhex(S5), 0), E.mallory)
    step("D5.5 EVM claim by a third party with the right preimage reverts NOT_CLAIMER", not ok and "NOT_CLAIMER" in str(why))
    rc, o, e = cli("claimhtlc", lock5, 0, amt, S5[:62], pkh(bob), MARKER, FEE)
    step("D5.6 CLI refuses a non-32-byte preimage", rc != 0, (e or o).strip()[:80])
    good = sost_claim(wb, bob, lock5, amt, S5, bob)
    A.send(good); mine1()
    ok, why = A.try_send(good)
    step("D5.7 replay of a confirmed SOST claim rejected", not ok, why[:90])
    E.tx(E.htlc.functions.claimERC20(sid5, bytes.fromhex(S5), 0), E.alice)
    ok, why = E.try_tx(E.htlc.functions.claimERC20(sid5, bytes.fromhex(S5), 0), E.alice)
    step("D5.8 EVM double claim reverts NOT_LOCKED", not ok and "NOT_LOCKED" in str(why))

    # =========================================================== D6 / D7: boundaries
    log("\n=== D6/D7  claim just before / refund just after timeout (SOST + EVM) ===")
    S6 = secrets.token_bytes(32).hex(); H6 = hashlib.sha256(bytes.fromhex(S6)).hexdigest()
    locks = []
    for _ in range(3):
        u = pick_utxo(A, alice, amt + FEE)
        locks.append(u)
    rh6 = A.height() + 8
    L = [A.send(sost_lock(A, wa, alice, u, H6, rh6, bob, alice, amt)[1]) for u in locks]
    mine1()
    mine_until(rh6 - 2)
    ok, c6 = A.try_send(sost_claim(wb, bob, L[0], amt, S6, bob))
    ok_r, why_r = A.try_send(sost_refund(wa, alice, L[1], amt, alice))
    mine1()
    blk = A.call("gettransaction", [c6]) if ok else {}
    step("D6.1 SOST claim broadcast at tip=rh-2 is accepted and mined in block rh-1", ok and A.confs(c6) >= 1
         and int(blk.get("block_height", -1)) == rh6 - 1, f"block {blk.get('block_height')} rh {rh6}")
    step("D7.1 SOST refund at tip=rh-2 (spend height rh-1) rejected", not ok_r and "R24" in why_r, why_r[:80])
    ok, why = A.try_send(sost_claim(wb, bob, L[1], amt, S6, bob))
    step("D6.2 SOST claim at tip=rh-1 (spend height rh) rejected (R22)", not ok and "R22" in why, why[:80])
    ok, r7 = A.try_send(sost_refund(wa, alice, L[1], amt, alice)); mine1()
    blk = A.call("gettransaction", [r7]) if ok else {}
    step("D7.2 SOST refund at tip=rh-1 accepted and mined in block rh", ok and int(blk.get("block_height", -1)) == rh6,
         f"block {blk.get('block_height')}")
    # EVM boundaries (automine: a tx sent at block.number=N is mined in N+1)
    sids = [hashlib.sha256(bytes([i]) + bytes.fromhex(H6)).digest() for i in range(4)]
    rt6 = E.w3.eth.block_number + 12
    for s_ in sids:
        E.lock(E.bob, s_, STOCK // 10, bytes.fromhex(H6), rt6, E.alice, E.bob)
    E.mine(rt6 - 2 - E.w3.eth.block_number)                      # head = rt-2
    E.automine(False)
    def pend(fn, who):
        return fn.transact({"from": who, "gas": 400_000})
    h1 = pend(E.htlc.functions.claimERC20(sids[0], bytes.fromhex(S6), 0), E.alice)
    h2 = pend(E.htlc.functions.refundERC20(sids[1]), E.bob)
    E.mine(1)                                                      # block rt-1
    h3 = pend(E.htlc.functions.claimERC20(sids[2], bytes.fromhex(S6), 0), E.alice)
    h4 = pend(E.htlc.functions.refundERC20(sids[3]), E.bob)
    E.mine(1)                                                      # block rt
    E.automine(True)
    R = [E.w3.eth.get_transaction_receipt(h) for h in (h1, h2, h3, h4)]
    log("   EVM refundTime %d: " % rt6 + ", ".join(f"{n}@{r.blockNumber}:{r.status}" for n, r in zip(("claim", "refund", "claim", "refund"), R)))
    step("D6.3 EVM claim in block refundTime-1 succeeds", R[0].blockNumber == rt6 - 1 and R[0].status == 1)
    step("D7.3 EVM refund in block refundTime-1 reverts (NOT_YET)", R[1].blockNumber == rt6 - 1 and R[1].status == 0)
    step("D6.4 EVM claim in block refundTime reverts (EXPIRED)", R[2].blockNumber == rt6 and R[2].status == 0)
    step("D7.4 EVM refund in block refundTime succeeds", R[3].blockNumber == rt6 and R[3].status == 1)

    # =========================================================== D8: node restart midway
    log("\n=== D8  SOST node restart in the middle of a swap ===")
    S8 = secrets.token_bytes(32).hex(); H8 = hashlib.sha256(bytes.fromhex(S8)).hexdigest()
    u = pick_utxo(A, alice, amt + FEE)
    rh8 = A.height() + 30
    lock8 = A.send(sost_lock(A, wa, alice, u, H8, rh8, bob, alice, amt)[1]); mine1()
    sid8 = hashlib.sha256(b"D8" + bytes.fromhex(H8)).digest()
    E.lock(E.bob, sid8, wamt, bytes.fromhex(H8), E.w3.eth.block_number + 20, E.alice, E.bob)
    before = (A.height(), A.htlc(lock8))
    A.stop(); A.start()
    after = (A.height(), A.htlc(lock8))
    step("D8.1 after SIGTERM + restart the node keeps height and the open lock (gethtlcstatus identical)",
         before == after, f"h {before[0]}→{after[0]}")
    E.tx(E.htlc.functions.claimERC20(sid8, bytes.fromhex(S8), wamt), E.alice)
    # Bob's tooling "restarts": nothing persisted except lock txid + swapId -> recovers from chain state alone
    Px = E.extract_preimage(sid8)
    c8 = A.send(sost_claim(wb, bob, lock8, amt, Px, bob)); mine1()
    step("D8.2 swap completes after restart; Bob recovers the secret from chain logs only (lock txid + swapId)",
         A.htlc(lock8)["status"] == "claimed")

    # =========================================================== D10: EVM reorg equivalent
    log("\n=== D10 EVM reorg equivalent (evm_snapshot/evm_revert) ===")
    S10 = secrets.token_bytes(32).hex(); H10 = hashlib.sha256(bytes.fromhex(S10)).hexdigest()
    sid10 = hashlib.sha256(b"D10" + bytes.fromhex(H10)).digest()
    snap = E.w3.provider.make_request("evm_snapshot", [])["result"]
    E.lock(E.bob, sid10, wamt, bytes.fromhex(H10), E.w3.eth.block_number + 60, E.alice, E.bob)
    seen = verify_evm_lock(sid10, H10, E.alice, E.bob, wamt, E.swap(sid10)["refundTime"])[0]
    u = pick_utxo(A, alice, amt + FEE)
    rh10 = A.height() + 20
    lock10 = A.send(sost_lock(A, wa, alice, u, H10, rh10, bob, alice, amt)[1]); mine1()
    E.w3.provider.make_request("evm_revert", [snap])      # the EVM block holding Bob's lock is reorged out
    gone = E.swap(sid10)["state"] == 0
    b0 = A.balance(bob)
    A.send(sost_claim(wb, bob, lock10, amt, S10, bob)); mine1()
    ok, why = E.try_tx(E.htlc.functions.claimERC20(sid10, bytes.fromhex(S10), 0), E.alice)
    step("D10.1 Alice acted on a 1-block EVM lock; the EVM reorg removes it; Bob still claims SOST; Alice's wSOST claim fails "
         "(=> responders MUST wait for EVM finality; no tool enforces it)",
         seen and gone and A.balance(bob) - b0 == amt - FEE and not ok, str(why)[:60])
    bridge_unchanged("final")
finally:
    summary(os.path.join(work, "results.json"))
    stop_all()
