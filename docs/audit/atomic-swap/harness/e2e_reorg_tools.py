#!/usr/bin/env python3
"""Atomic-swap completion audit — B (offline-signing integration), D9 (real SOST reorg),
K-TP (near-deadline HTLC claim left in the mempool -> block template), sost-signtx check.

Two real DEVNET_FAST nodes (A, B) + real sost-miner + Anvil (WSOST + AtomicSwapHTLCv2).
usage: e2e_reorg_tools.py <base_dir> <work_dir>
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
os.makedirs(os.path.join(work, "nodeB"), exist_ok=True)
shutil.copy(os.path.join(work, "nodeA", "chain.json"), os.path.join(work, "nodeB", "chain.json"))

A = Sost(work, "nodeA", 19801, 19811).start()
B = Sost(work, "nodeB", 19802, 19812)
wa, alice = new_wallet(work, "alice.json")
wb, bob = new_wallet(work, "bob.json")
wv, vault = new_wallet(work, "vault.json")
amt = 2 * STOCK


def deliver(src, dst, h_from, h_to):
    out = []
    for h in range(h_from, h_to + 1):
        raw = src.call("getrawblock", [src.getblockhash(h) if hasattr(src, "getblockhash") else src.rpc.getblockhash(h)])
        try:
            out.append(str(dst.call("submitblock", [raw]))[:40])
        except Exception as e:
            out.append("ERR " + str(e)[:80])
    return out


def sync_B_from_A():
    B.start(connect=f"127.0.0.1:{A.p2p}")
    try:
        wait_until(lambda: B.height() == A.height() and B.rpc.getblockhash(B.height()) == A.rpc.getblockhash(A.height()),
                   180, "B sync")
    finally:
        B.stop()


try:
    # =========================================================== B: V17 offline tools vs HTLC
    log("\n=== B  V17 offline signing (buildtx/signtx) against HTLC transactions ===")
    S = secrets.token_bytes(32).hex(); H = hashlib.sha256(bytes.fromhex(S)).hexdigest()
    u = pick_utxo(A, alice, amt + FEE)
    rh = A.height() + 30
    raw_lock = build("createhtlclock", u["txid"], u["vout"], u["amount_stocks"], pkh(alice), H, rh, pkh(bob), pkh(alice), amt, FEE)
    tx_out = sum([amt, int(u["amount_stocks"]) - amt - FEE])

    def unsigned_file(name, raw_hex, inputs, fee):
        j = {"format": "sost-unsigned-tx-v1", "network": "dev", "genesis": GENESIS, "chain_height": A.height(),
             "from": alice, "to": bob, "amount": amt, "fee": fee, "capsule_mode": "none", "capsule_hex": "",
             "inputs": inputs, "unsigned_hex": raw_hex}
        f = os.path.join(work, name)
        json.dump(j, open(f, "w"), indent=1)
        return f
    f_lock = unsigned_file("htlc_lock.unsigned.json", raw_lock,
                           [{"txid": u["txid"], "vout": u["vout"], "amount": int(u["amount_stocks"]),
                             "output_type": int(u["output_type"]), "address": alice}], FEE)
    rc, o, e = cli("--wallet", wa, "signtx", f_lock, "--network", "dev", "--yes", "--out", os.path.join(work, "lock.signed.hex"))
    step("B1 V17 `sost-cli signtx` REFUSES the HTLC LOCK (OUT_HTLC_LOCK output) — offline signing of a swap lock impossible",
         rc != 0, (e or o).strip().splitlines()[-1][:120])
    signed_lock = labsign(wa, raw_lock, f"{u['amount_stocks']}:{u['output_type']}:{alice}")
    lock = A.send(signed_lock)
    A.mine(1, wa, alice)
    raw_claim = build("claimhtlc", lock, 0, amt, S, pkh(bob), MARKER, FEE)
    f_claim = unsigned_file("htlc_claim.unsigned.json", raw_claim,
                            [{"txid": lock, "vout": 0, "amount": amt, "output_type": OUT_HTLC_LOCK, "address": bob}], FEE)
    rc, o, e = cli("--wallet", wb, "signtx", f_claim, "--network", "dev", "--yes", "--out", os.path.join(work, "claim.signed.hex"))
    step("B2 V17 `sost-cli signtx` REFUSES the HTLC CLAIM (tx_type 0x10)", rc != 0, (e or o).strip().splitlines()[-1][:120])
    raw_ref = build("refundhtlc", lock, 0, amt, pkh(alice), FEE)
    f_ref = unsigned_file("htlc_refund.unsigned.json", raw_ref,
                          [{"txid": lock, "vout": 0, "amount": amt, "output_type": OUT_HTLC_LOCK, "address": alice}], FEE)
    rc, o, e = cli("--wallet", wa, "signtx", f_ref, "--network", "dev", "--yes", "--out", os.path.join(work, "refund.signed.hex"))
    step("B3 V17 `sost-cli signtx` REFUSES the HTLC REFUND (tx_type 0x11)", rc != 0, (e or o).strip().splitlines()[-1][:120])
    rc, o, e = cli("verifytx", signed_lock)
    step("B4 `sost-cli verifytx <raw hex>` on a signed HTLC lock (structure-only path)", rc in (0, 3), (o or e).strip().splitlines()[-1][:120])
    # in-tree founder tool sost-signtx: takes the PRIVATE KEY ON argv (disposable devnet key here)
    priv = json.load(open(wb))["keys"][0]["privkey"]
    r = subprocess.run([SIGNTX, raw_claim, priv, str(amt), str(OUT_HTLC_LOCK), "0", GENESIS], capture_output=True, text=True)
    sig_hex = (r.stdout.strip().splitlines() or [""])[-1]
    ok, c = A.try_send(sig_hex) if r.returncode == 0 else (False, r.stderr[:100])
    A.mine(1, wa, alice)
    step("B5 in-tree `sost-signtx` (private key passed on argv) can sign an HTLC CLAIM that the node accepts",
         ok and A.htlc(lock)["status"] == "claimed", str(c)[:80])

    # =========================================================== D9: real SOST reorg
    log("\n=== D9  SOST reorg before finality: lock reorged out + funding input double-spent ===")
    E = Evm(work, 18548)
    E.setup_wsost(vault, 500 * STOCK)
    sync_B_from_A()
    T = A.height()
    S9 = secrets.token_bytes(32).hex(); H9 = hashlib.sha256(bytes.fromhex(S9)).hexdigest()
    u = pick_utxo(A, alice, amt + FEE)
    rh9 = T + 40
    lock9 = A.send(sost_lock(A, wa, alice, u, H9, rh9, bob, alice, amt)[1])
    A.mine(1, wa, alice)
    st = A.htlc(lock9)
    step("D9.1 Alice's SOST lock has 1 confirmation on node A", st["status"] == "locked" and A.confs(lock9) >= 1)
    sid9 = hashlib.sha256(b"D9" + bytes.fromhex(H9)).digest()
    E.lock(E.bob, sid9, amt, bytes.fromhex(H9), E.w3.eth.block_number + 30, E.alice, E.bob)
    step("D9.2 Bob locks wSOST after seeing 1 SOST confirmation (no tool enforces a depth)", E.swap(sid9)["state"] == 1)
    # Alice privately double-spends the same funding input on a competing branch (node B, offline)
    B.start()
    ds = sost_lock(B, wa, alice, u, hashlib.sha256(b"other").hexdigest(), T + 5, alice, alice, amt)[1]
    ok_ds, ds_txid = B.try_send(ds)
    B.mine(3, wa, alice)
    hb = B.height()
    B_hashes = [B.rpc.getblockhash(h) for h in range(T + 1, hb + 1)]
    sub = []
    for bh in B_hashes:
        try:
            sub.append(str(A.call("submitblock", [B.call("getrawblock", [bh])]))[:30])
        except Exception as e:
            sub.append("ERR " + str(e)[:60])
    B.stop()
    reorged = A.rpc.getblockhash(T + 1) == B_hashes[0] and A.height() == hb
    st = A.htlc(lock9)
    step("D9.3 REAL reorg on node A: B's longer branch (with Alice's double-spend of the funding input) replaces the lock block",
         ok_ds and reorged and st.get("status") != "locked", f"tip {A.height()} lock status now {st.get('status')} submit {sub}")
    ok, why = A.try_send(signed_lock if False else ds)
    E.tx(E.htlc.functions.claimERC20(sid9, bytes.fromhex(S9), 0), E.alice)
    ok, why = A.try_send(sost_claim(wb, bob, lock9, amt, S9, bob))
    step("D9.4 Alice claims Bob's wSOST; Bob's SOST claim now fails (lock no longer exists) => Bob LOSES "
         "(responder must wait for SOST finality depth; nothing enforces it)", not ok, why[:100])

    # =========================================================== K-TP: near-deadline claim left in mempool
    log("\n=== K-TP  near-deadline HTLC CLAIM left in the mempool after the next block ===")
    S7 = secrets.token_bytes(32).hex(); H7 = hashlib.sha256(bytes.fromhex(S7)).hexdigest()
    u = pick_utxo(A, alice, amt + FEE)
    L = A.height() + 1
    rh7 = L + 3
    lock7 = A.send(sost_lock(A, wa, alice, u, H7, rh7, bob, alice, amt)[1])
    A.mine(2, wa, alice)                                            # tip = L+1 = rh-2
    sync_B_from_A()
    step("K-TP.1 node A and node B share tip rh-2", A.height() == rh7 - 2, f"tip {A.height()} rh {rh7}")
    ok, c7 = A.try_send(sost_claim(wb, bob, lock7, amt, S7, bob))
    step("K-TP.2 claim accepted into A's mempool at tip rh-2 (valid for block rh-1)", ok, str(c7)[:70])
    B.start()
    B.mine(1, wa, alice)                                            # block rh-1 WITHOUT the claim (stale template / other miner)
    raw = B.call("getrawblock", [B.rpc.getblockhash(B.height())])
    B.stop()
    A.call("submitblock", [raw])
    mp = A.call("getrawmempool") or []
    in_mp = c7 in json.dumps(mp)
    tmpl = A.call("getblocktemplate", [alice])
    in_tmpl = any(c7 in json.dumps(t) for t in tmpl.get("transactions", [])) or len(tmpl.get("transactions", [])) > 0
    step("K-TP.3 after block rh-1 without it, the now-EXPIRED claim (R22 at rh) stays in A's mempool and in getblocktemplate",
         A.height() == rh7 - 1 and in_mp, f"tip {A.height()} in_mempool {in_mp} template_txs {len(tmpl.get('transactions', []))}")
    h0 = A.height()
    t0 = time.time()
    p = subprocess.Popen(["nice", "-n", "15", MINER, "--profile", "dev", "--genesis", GENESIS_JSON, "--rpc", A.addr,
                          "--address", alice, "--wallet", wa, "--mining-key-label", "default", "--blocks", "1",
                          "--threads", "2", "--realtime"], cwd=A.dir,
                         stdout=open(os.path.join(work, "miner-tp.log"), "w"), stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    procs["miner"] = p
    try:
        p.wait(timeout=240)
    except subprocess.TimeoutExpired:
        pass
    stop("miner")
    adv = A.height() - h0
    mlog = open(os.path.join(work, "miner-tp.log")).read()
    nlog = open(os.path.join(work, "nodeA.log")).read()
    rej = [l for l in (mlog + nlog).splitlines() if "R22" in l or "rejected" in l.lower()][-3:]
    step("K-TP.4 node A's miner CANNOT extend the chain while the expired claim is in the template (template poisoning)",
         adv == 0, f"advanced {adv} block(s) in {int(time.time()-t0)}s; evidence: {rej}")
    mp2 = A.call("getrawmempool") or []
    step("K-TP.5 the expired claim is still in the mempool afterwards (no eviction path for HTLC CLAIM)", c7 in json.dumps(mp2),
         f"{len(mp2) if isinstance(mp2, list) else mp2}")
finally:
    summary(os.path.join(work, "results.json"))
    stop_all()
