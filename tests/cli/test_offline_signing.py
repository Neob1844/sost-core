#!/usr/bin/env python3
"""Offline signing E2E against a REAL devnet node: buildtx (watch-only) -> signtx (offline) -> sendrawtransaction.

  python3 tests/cli/test_offline_signing.py --cli build/sost-cli --work DIR [--rpc 127.0.0.1:18655] [--capsule] [--mine-cmd CMD]

DIR holds devnet test wallets alice.json (funded) and bob.json. Disposable devnet keys only.
--capsule additionally runs the capsule cases (needs devnet height >= 7,350).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

results = []


def step(name, ok, detail=""):
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def outpoints(path):
    return {(i["txid"], i["vout"]) for i in json.load(open(path))["inputs"]}


def mempool_section(a, run, rpc, broadcast, wait_conf, alice, bob, AW, p, tmp):
    """buildtx must never reuse an input that is already taken: spent by a tx in the node mempool,
    or reserved by an earlier unsigned build that has not reached the mempool yet."""
    def sign(u, s):
        r = run("--wallet", AW, "signtx", u, "--network", "dev", "--yes", "--out", s)
        return open(s).read().strip() if r.returncode == 0 else None

    # A: build -> sign -> broadcast (stays in the mempool), then IMMEDIATELY build B from the same address
    r = run("--from-address", alice, "buildtx", bob, "1", "--network", "dev", "--out", p("mpA.json"))
    sA = sign(p("mpA.json"), p("mpA.hex")) if r.returncode == 0 else None
    txA, e = broadcast(sA) if sA else (None, r.stderr)
    inA = outpoints(p("mpA.json")) if r.returncode == 0 else set()
    sp = rpc("getmempoolspends", [alice]).get("result") or {}
    got = {(x["txid"], x["vout"]) for x in sp.get("spent", [])}
    step("MEMPOOL: tx A built, signed, accepted into the mempool (unconfirmed)", bool(txA) and rpc("getrawtransaction", [txA, True]).get("result", {}).get("confirmed") is not True, e[:80])
    step("   getmempoolspends lists exactly A's inputs, spent_by = A", got == inA and all(x["spent_by"] == txA for x in sp.get("spent", [])), f"{len(got)} outpoint(s)")
    os.remove(os.path.join(tmp, "sost-buildtx-reservations.json"))          # mempool alone must protect B (no local ledger)
    r = run("--from-address", alice, "buildtx", bob, "1", "--network", "dev", "--out", p("mpB.json"))
    inB = outpoints(p("mpB.json")) if r.returncode == 0 else set()
    step("   build B (ledger removed): uses inputs disjoint from A", r.returncode == 0 and inB and not (inA & inB) and "spent by pending mempool txs" in r.stdout,
         r.stderr.strip()[-160:] if r.returncode else f"A={len(inA)} B={len(inB)} input(s)")
    sB = sign(p("mpB.json"), p("mpB.hex")) if r.returncode == 0 else None
    txB, e = broadcast(sB) if sB else (None, "not built")
    step("   B accepted by the node while A is still pending (no conflict / RBF rejection)", bool(txB), e[:100])

    # C: built (reserved) but NOT broadcast; D must not reuse C's inputs
    r = run("--from-address", alice, "buildtx", bob, "1", "--network", "dev", "--out", p("mpC.json"))
    inC = outpoints(p("mpC.json")) if r.returncode == 0 else set()
    step("RESERVATION: build C (not broadcast) records its inputs", r.returncode == 0 and "inputs reserved in" in r.stdout, r.stderr.strip()[-120:])
    r = run("--from-address", alice, "buildtx", bob, "1", "--network", "dev", "--out", p("mpD.json"))
    inD = outpoints(p("mpD.json")) if r.returncode == 0 else set()
    step("   build D avoids C's reserved inputs and the mempool inputs", r.returncode == 0 and inD and not (inD & (inC | inA | inB)),
         r.stderr.strip()[-160:] if r.returncode else "")
    r = run("buildtx", "--list-reservations", "--out", p("x.json"))
    step("   --list-reservations shows C and D", r.returncode == 0 and "mpC.json" in r.stdout and "mpD.json" in r.stdout)

    # Not enough AVAILABLE funds: clean failure naming what is held back, never a conflicting tx
    total = sum(u["amount_stocks"] for u in rpc("getaddressutxos", [alice])["result"] if u.get("spendable"))
    amt = f"{(total - 100_000_000) / 1e8:.8f}"
    r = run("--from-address", alice, "buildtx", bob, amt, "--network", "dev", "--out", p("mpBig.json"))
    step("INSUFFICIENT: total - 1 SOST requested -> 'insufficient available funds', nothing written",
         r.returncode != 0 and "insufficient available funds" in r.stderr and "mempool" in r.stderr and "reserved" in r.stderr
         and not os.path.exists(p("mpBig.json")), r.stderr.strip().splitlines()[0][:160] if r.stderr.strip() else "")
    # explicit override: --ignore-reservations may reuse C/D's inputs (but never mempool-spent ones)
    r = run("--from-address", alice, "buildtx", bob, "1", "--network", "dev", "--out", p("mpE.json"), "--ignore-reservations")
    inE = outpoints(p("mpE.json")) if r.returncode == 0 else set()
    step("   --ignore-reservations: warns, still excludes mempool-spent inputs", r.returncode == 0 and "WARNING" in r.stderr and not (inE & (inA | inB)))
    r = run("--from-address", alice, "buildtx", "--clear-reservations", "--out", p("y.json"))
    lst = run("buildtx", "--list-reservations", "--out", p("x.json"))
    step("   --clear-reservations releases the address's reservations", r.returncode == 0 and "Cleared " in r.stdout and "Reservations in" in lst.stdout and ": 0" in lst.stdout,
         r.stdout.strip()[-80:])

    # Older node without getmempoolspends: fallback via getrawmempool + getrawtransaction (proxy hides the method)
    import http.server, threading
    up = a.rpc
    class Hide(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            if json.loads(body).get("method") == "getmempoolspends":
                out = json.dumps({"result": None, "error": {"code": -32601, "message": "Method not found: getmempoolspends"}, "id": 1}).encode()
            else:
                out = urllib.request.urlopen(urllib.request.Request(f"http://{up}/", body, {"content-type": "application/json"}), timeout=20).read()
            self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(out)))
            self.end_headers(); self.wfile.write(out)
        def log_message(self, *x):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), Hide)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proxy = f"127.0.0.1:{srv.server_address[1]}"
    os.remove(os.path.join(tmp, "sost-buildtx-reservations.json"))
    r = subprocess.run([run.cli, "--node", proxy, "--from-address", alice, "buildtx", bob, "1", "--network", "dev", "--out", p("mpF.json")],
                       capture_output=True, text=True, timeout=180)
    inF = outpoints(p("mpF.json")) if r.returncode == 0 else set()
    pending = (inA | inB) if rpc("getrawtransaction", [txA, True]).get("result", {}).get("confirmed") is not True else set()
    step("FALLBACK (node without getmempoolspends): still excludes mempool-spent inputs", r.returncode == 0 and inF and not (inF & pending),
         r.stderr.strip()[-160:] if r.returncode else f"{len(pending)} pending outpoint(s) checked")
    srv.shutdown()

    # Negative control (the old behaviour): with both protections switched off, the same coin selection
    # picks an input that pending A/B already spend, and the node rejects the conflicting tx.
    r = run("--from-address", alice, "buildtx", bob, "1.5", "--network", "dev", "--out", p("mpG.json"), "--skip-mempool-check", "--ignore-reservations")
    inG = outpoints(p("mpG.json")) if r.returncode == 0 else set()
    sG = sign(p("mpG.json"), p("mpG.hex")) if r.returncode == 0 else None
    txG, e = broadcast(sG) if sG else (None, "not built")
    if inG & pending:
        step("NEGATIVE CONTROL: protections off -> reuses a pending input, node rejects it", not txG and bool(e), e[:90])
    else:
        print(f"[INFO] negative control inconclusive: selection did not hit a pending input (pending={len(pending)})")

    ok = all(wait_conf(t) for t in (txA, txB) if t)
    step("   A and B both confirm", ok and bool(txA) and bool(txB))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rpc", default="127.0.0.1:18655")
    ap.add_argument("--capsule", action="store_true")
    ap.add_argument("--mine-cmd", help="shell command that mines ONE block; when given, blocks are mined only while waiting "
                                       "for a confirmation, so pending transactions stay in the mempool deterministically")
    a = ap.parse_args()
    CLI = os.path.abspath(a.cli)
    tmp = tempfile.mkdtemp(prefix="sost-offline-")
    os.chmod(tmp, 0o700)

    def rpc(m, p):
        r = urllib.request.urlopen(urllib.request.Request(f"http://{a.rpc}/", json.dumps({"method": m, "params": p, "id": 1}).encode(),
                                                          {"content-type": "application/json"}), timeout=20)
        return json.load(r)

    def addr(name):
        return json.load(open(os.path.join(a.work, name)))["keys"][0]["address"]

    def bal(ad):
        return sum(u["amount_stocks"] for u in rpc("getaddressutxos", [ad])["result"])

    def run(*args, stdin=None):
        return subprocess.run([CLI, "--node", a.rpc, *args], capture_output=True, text=True, input=stdin, timeout=180)
    run.cli = CLI

    def broadcast(hexs):
        r = rpc("sendrawtransaction", [hexs])
        return r.get("result"), (r.get("error") or {}).get("message", "")

    def wait_conf(txid, t=300):
        t0 = time.time()
        if a.mine_cmd:
            while time.time() - t0 < t:
                r = rpc("gettransaction", [txid]).get("result") or {}
                if int(r.get("confirmations", 0) or 0) >= 1:
                    return True
                subprocess.run(a.mine_cmd, shell=True, capture_output=True, timeout=t)
            return False
        while time.time() - t0 < t:
            r = rpc("gettransaction", [txid]).get("result") or {}
            if int(r.get("confirmations", 0) or 0) >= 1:
                return True
            time.sleep(2)
        return False

    alice, bob = addr("alice.json"), addr("bob.json")
    AW, BW = os.path.join(a.work, "alice.json"), os.path.join(a.work, "bob.json")
    p = lambda n: os.path.join(tmp, n)

    # ------------------------------------------------------------------ happy path (plain v1 signer)
    r = run("--from-address", alice, "buildtx", bob, "5", "--network", "dev", "--out", p("t1.json"))
    step("OFFLINE_BUILDTX: watch-only build (no wallet, no key)", r.returncode == 0 and os.path.exists(p("t1.json")), r.stdout.strip().splitlines()[-2] if r.returncode == 0 else r.stderr[-200:])
    t1 = json.load(open(p("t1.json")))
    step("   unsigned file: all signatures zero", all(set(bytes.fromhex(t1["unsigned_hex"])[6 + 133 * i + 36: 6 + 133 * i + 100]) == {0} for i in range(len(t1["inputs"]))))
    r = run("--from-address", alice, "buildtx", bob, "5", "--network", "dev", "--out", p("t1.json"))
    step("   buildtx never overwrites an existing file", r.returncode != 0)
    r = run("--wallet", AW, "signtx", p("t1.json"), "--network", "dev", "--yes", "--out", p("s1.hex"))
    shown = r.stdout
    step("OFFLINE_SIGNTX: v1 wallet signs", r.returncode == 0, "")
    step("   review shows inputs, outputs, destination, fee, network", all(x in shown for x in ("Input  0", "Output 0", bob, "Fee:", "Network:  dev")))
    signed = open(p("s1.hex")).read().strip()
    b0 = bal(bob)
    txid, e = broadcast(signed)
    step("RAW_BROADCAST: node accepts the offline-signed tx", bool(txid), e)
    step("   confirmed and Bob +5 SOST", wait_conf(txid) and bal(bob) - b0 == 500_000_000)
    _, e = broadcast(signed)
    step("   replay of the same signed tx rejected", bool(e), e[:80])

    # ------------------------------------------------------------------ encrypted v2 signer (passphrase file)
    PASS = "offline signing test 7"
    pf = p("pass"); open(pf, "w").write(PASS + "\n"); os.chmod(pf, 0o600)
    v2 = p("alice.v2.json")
    subprocess.run(["bash", "-c", f'exec 3<"{pf}"; "{CLI}" --wallet "{AW}" wallet-export --encrypted --output "{v2}" --passphrase-fd 3'], capture_output=True)
    run("--from-address", alice, "buildtx", bob, "1.5", "--network", "dev", "--out", p("t2.json"))
    r = run("--wallet", v2, "signtx", p("t2.json"), "--network", "dev", "--yes", "--passphrase-file", pf, "--out", p("s2.hex"))
    txid2, e = broadcast(open(p("s2.hex")).read().strip()) if r.returncode == 0 else (None, r.stderr)
    step("OFFLINE_SIGNTX: encrypted v2 wallet (--passphrase-file) signs, node accepts", r.returncode == 0 and bool(txid2), e[:100])
    wait_conf(txid2) if txid2 else None
    r = run("--wallet", v2, "signtx", p("t2.json"), "--network", "dev", "--yes", "--passphrase-fd", "0", stdin="wrong passphrase 1\n")
    step("   wrong passphrase refused", r.returncode != 0 and "decryption failed" in r.stderr, r.stderr.strip()[:80])

    # ------------------------------------------------------------------ refusals before signing
    run("--from-address", alice, "buildtx", bob, "2", "--network", "dev", "--out", p("t3.json"))
    t3 = json.load(open(p("t3.json")))

    def variant(name, mut):
        j = json.loads(json.dumps(t3)); mut(j); f = p(name); json.dump(j, open(f, "w")); return f

    r = run("--wallet", AW, "signtx", p("t3.json"), "--yes")                    # signer defaults to mainnet
    step("wrong network (file dev, signer mainnet) refused", r.returncode != 0 and "network mismatch" in r.stderr)
    r = run("--wallet", BW, "signtx", p("t3.json"), "--network", "dev", "--yes")
    step("wrong wallet (no key for the inputs) refused", r.returncode != 0 and "no key" in r.stderr)
    r = run("--wallet", AW, "signtx", variant("fee.json", lambda j: j.update(fee=j["fee"] - 1)), "--network", "dev", "--yes")
    step("declared fee different from the tx refused", r.returncode != 0 and "fee" in r.stderr)
    r = run("--wallet", AW, "signtx", variant("trunc.json", lambda j: j.update(unsigned_hex=j["unsigned_hex"][:-20])), "--network", "dev", "--yes")
    step("truncated transaction refused", r.returncode != 0 and "cannot decode" in r.stderr)
    r = run("--wallet", AW, "signtx", variant("inp.json", lambda j: j["inputs"][0].update(vout=j["inputs"][0]["vout"] + 1)), "--network", "dev", "--yes")
    step("input list not matching the tx bytes refused", r.returncode != 0 and "does not match" in r.stderr)

    def dup(j):
        h = bytes.fromhex(j["unsigned_hex"])
        n = h[5]; inp = h[6:6 + 133]
        h2 = h[:5] + bytes([n + 1]) + inp + h[6:]
        j["unsigned_hex"] = h2.hex(); j["inputs"] = [j["inputs"][0]] + j["inputs"]
        j["fee"] = j["fee"] + j["inputs"][0]["amount"]
    r = run("--wallet", AW, "signtx", variant("dup.json", dup), "--network", "dev", "--yes")
    step("duplicate input refused", r.returncode != 0 and "duplicate" in r.stderr, r.stderr.strip()[:80])
    r = run("--wallet", AW, "signtx", p("s1.hex"), "--network", "dev", "--yes")
    step("a non-tx file refused", r.returncode != 0)
    r = run("--wallet", AW, "signtx", p("t3.json"), "--network", "dev", stdin="no\n")
    step("interactive review: answering anything but 'yes' does not sign", r.returncode != 0 and "Not signed" in r.stderr)

    # ------------------------------------------------------------------ tampering AFTER signing -> node rejects
    r = run("--wallet", AW, "signtx", p("t3.json"), "--network", "dev", "--yes", "--out", p("s3.hex"))
    s3 = bytes.fromhex(open(p("s3.hex")).read().strip())
    nin = s3[5]; out0 = 6 + 133 * nin + 1                                     # first output
    def patched(off, val):
        b = bytearray(s3); b[off:off + len(val)] = val; return bytes(b).hex()
    _, e = broadcast(patched(out0 + 9, bytes.fromhex(alice[5:])))               # destination -> alice
    step("modified destination after signing: node rejects", "S6" in e or "verify" in e.lower() or "signature" in e.lower(), e[:90])
    amt = int.from_bytes(s3[out0:out0 + 8], "little")
    _, e = broadcast(patched(out0, (amt + 1).to_bytes(8, "little")))
    step("modified amount after signing: node rejects", bool(e), e[:90])
    lie = variant("lie.json", lambda j: (j["inputs"][0].update(amount=j["inputs"][0]["amount"] - 1000), j.update(fee=j["fee"] - 1000)))
    r = run("--wallet", AW, "signtx", lie, "--network", "dev", "--yes", "--out", p("slie.hex"))
    _, e = broadcast(open(p("slie.hex")).read().strip()) if r.returncode == 0 else (None, "not signed")
    step("lying input amount in tx.json: signature is invalid on chain", bool(e), e[:90])
    tx3, e = broadcast(s3.hex())
    step("untampered signed tx still accepted", bool(tx3), e[:80])
    if tx3:
        wait_conf(tx3)

    # ------------------------------------------------------------------ capsule (needs >= 7,350)
    if a.capsule:
        h = rpc("getblockcount", [])["result"]
        r = run("--from-address", alice, "--capsule-mode", "open-note", "--capsule-text", "WSOST:0x1111111111111111111111111111111111111111",
                "buildtx", bob, "1", "--network", "dev", "--out", p("tc.json"))
        step("CLI_CAPSULE_SUPPORT: buildtx with an open-note capsule", r.returncode == 0 and json.load(open(p("tc.json")))["capsule_mode"] == "open-note",
             f"height {h}" if r.returncode == 0 else r.stderr.strip()[:120])
        if r.returncode == 0:
            r = run("--wallet", AW, "signtx", p("tc.json"), "--network", "dev", "--yes", "--out", p("sc.hex"))
            step("   review shows the capsule text and hash", "WSOST:0x1111" in r.stdout and "sha256" in r.stdout)
            sc = bytes.fromhex(open(p("sc.hex")).read().strip())
            n2 = sc[5]; o0 = 6 + 133 * n2 + 1
            plen = int.from_bytes(sc[o0 + 29:o0 + 31], "little")
            b = bytearray(sc); b[o0 + 31 + plen - 1] ^= 0x01                    # flip the last capsule byte
            _, e = broadcast(bytes(b).hex())
            step("   modified capsule after signing: node rejects", bool(e), e[:90])
            txc, e = broadcast(sc.hex())
            ok = bool(txc) and wait_conf(txc)
            got = rpc("getrawtransaction", [txc, True]).get("result") if txc else None
            step("   capsule tx accepted and confirmed on the real chain", ok, e[:80] if not ok else f"txid {txc[:16]}…")
        r = run("--from-address", alice, "--capsule-mode", "open-note", "--capsule-text", "x" * 81, "buildtx", bob, "1", "--network", "dev", "--out", p("big.json"))
        step("   oversized capsule refused", r.returncode != 0)
        r = run("--from-address", alice, "--capsule-mode", "bogus", "--capsule-text", "x", "buildtx", bob, "1", "--network", "dev", "--out", p("bad.json"))
        step("   invalid capsule mode refused", r.returncode != 0)

    # ------------------------------------------------------------------ pending transactions (mempool + local reservations)
    mempool_section(a, run, rpc, broadcast, wait_conf, alice, bob, AW, p, tmp)

    n = sum(results)
    print(f"\nRESULT: {n}/{len(results)} PASS")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()
