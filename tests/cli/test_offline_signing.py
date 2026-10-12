#!/usr/bin/env python3
"""Offline signing E2E against a REAL devnet node: buildtx (watch-only) -> signtx (offline) -> sendrawtransaction.

  python3 tests/cli/test_offline_signing.py --cli build/sost-cli --work DIR [--rpc 127.0.0.1:18655] [--capsule]

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rpc", default="127.0.0.1:18655")
    ap.add_argument("--capsule", action="store_true")
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

    def broadcast(hexs):
        r = rpc("sendrawtransaction", [hexs])
        return r.get("result"), (r.get("error") or {}).get("message", "")

    def wait_conf(txid, t=300):
        t0 = time.time()
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

    n = sum(results)
    print(f"\nRESULT: {n}/{len(results)} PASS")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()
