#!/usr/bin/env python3
"""Independent V17 economics audit of a SOST chain.json (standard library only).

Replays every transaction of the chain (UTXO set from genesis), and checks for
every block from V17_HEIGHT, without using any node code:
  * miner output  == subsidy - subsidy*15//100 - subsidy*5//100 + fees
  * DTD output    == subsidy*15//100 + pending_before   (when present)
  * J_BALANCE     == J_before - J output + subsidy*5//100, J >= 0, == persisted value
  * jackpot H part (TX_TYPE_JACKPOT output 0) and J part (coinbase 0x05) recorded
  * no OUT_COINBASE_JACKPOT below V17_HEIGHT, at most one per coinbase
and, for EVERY block, the supply identity
  sum(unspent outputs) + pending + J == sum_{h<=tip} subsidy(h).

Usage: v17_chain_audit.py <chain.json> <genesis_block.json> <v17_height>
                          [--expect-j N] [--expect-pending N] [--json out.json]
Exit 0 = all checks pass.
"""
import hashlib
import json
import sys

OUT_COINBASE_MINER, OUT_COINBASE_LOTTERY, OUT_COINBASE_JACKPOT = 0x01, 0x04, 0x05
OUT_NODE_PROTOCOL, OUT_ASSET_BURN = 0x30, 0x42
TX_COINBASE, TX_JACKPOT = 0x01, 0x02


def cs(b, o):
    v = b[o]
    if v < 0xFD:
        return v, o + 1
    if v == 0xFD:
        return int.from_bytes(b[o + 1:o + 3], "little"), o + 3
    if v == 0xFE:
        return int.from_bytes(b[o + 1:o + 5], "little"), o + 5
    return int.from_bytes(b[o + 1:o + 9], "little"), o + 9


def parse_tx(hx):
    b = bytes.fromhex(hx)
    ttype = b[4]
    n, o = cs(b, 5)
    ins = []
    for _ in range(n):
        ins.append((b[o:o + 32], int.from_bytes(b[o + 32:o + 36], "little")))
        o += 133
    m, o = cs(b, o)
    outs = []
    for _ in range(m):
        amt = int.from_bytes(b[o:o + 8], "little", signed=True)
        oty = b[o + 8]
        pkh = b[o + 9:o + 29]
        pl = int.from_bytes(b[o + 29:o + 31], "little")
        o += 31 + pl
        outs.append((oty, pkh, amt))
    if o != len(b):
        raise ValueError("trailing bytes")
    return ttype, ins, outs, hashlib.sha256(hashlib.sha256(b).digest()).digest()


def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print(__doc__)
        return 2
    chain_path, genesis_path, v17 = args[0], args[1], int(args[2])
    opts = {}
    i = 3
    while i < len(args):
        opts[args[i]] = args[i + 1]
        i += 2
    chain = json.load(open(chain_path))
    gen = json.load(open(genesis_path))
    blocks = sorted((b for b in chain["blocks"] if b.get("height", 0) >= 1), key=lambda b: b["height"])
    fails = []

    def fail(msg):
        fails.append(msg)
        if len(fails) <= 30:
            print("  FAIL:", msg)

    # genesis UTXOs: 50/25/25 of the genesis subsidy (as the node creates them)
    gsub = int(gen["subsidy_stocks"])
    gid = bytes.fromhex(gen["block_id"])
    q = gsub // 4
    utxo = {(gid, 0): gsub - 2 * q, (gid, 1): q, (gid, 2): q}
    utxo_sum = gsub
    emitted = gsub
    pending, J = 0, 0
    events = []
    stats = {"v17_blocks": 0, "fee_blocks": 0, "zero_fee_blocks": 0, "dtd_paid": 0, "dtd_rollover": 0,
             "supply_checks": 0}
    prev_h = 0
    for b in blocks:
        h = b["height"]
        if h != prev_h + 1:
            fail("height gap at %d" % h)
        prev_h = h
        sub = int(b["subsidy"])
        txs = [parse_tx(x) for x in b.get("transactions", [])]
        if not txs or txs[0][0] != TX_COINBASE:
            fail("h=%d: missing coinbase" % h)
            continue
        fees = 0
        h_paid = 0
        h_winner = None
        for (ttype, ins, outs, txid) in txs[1:]:
            sin = 0
            for op in ins:
                if op not in utxo:
                    fail("h=%d: input %s:%d missing" % (h, op[0].hex()[:16], op[1]))
                    continue
                sin += utxo.pop(op)
            sout = sum(a for (_, _, a) in outs)
            if ttype == TX_JACKPOT:
                if sin != sout:
                    fail("h=%d: jackpot tx not value-conserving (%d != %d)" % (h, sin, sout))
                h_paid = outs[0][2]
                h_winner = outs[0][1]
            elif ins:
                fees += sin - sout
            if any(t == OUT_COINBASE_JACKPOT for (t, _, _) in outs):
                fail("h=%d: OUT_COINBASE_JACKPOT outside the coinbase" % h)
            utxo_sum -= sin
            for k, (t, pkh, a) in enumerate(outs):
                if t in (OUT_NODE_PROTOCOL, OUT_ASSET_BURN):
                    continue
                utxo[(txid, k)] = a
                utxo_sum += a
        cb_type, _, cb_outs, cb_txid = txs[0]
        j_outs = [(pkh, a) for (t, pkh, a) in cb_outs if t == OUT_COINBASE_JACKPOT]
        lot = [(pkh, a) for (t, pkh, a) in cb_outs if t == OUT_COINBASE_LOTTERY]
        if h < v17:
            if j_outs:
                fail("h=%d: OUT_COINBASE_JACKPOT below V17" % h)
            pending = int(b.get("pending_lottery_after", 0))      # pre-V17: node value
            if "v17_j_balance_after" in b:
                fail("h=%d: v17 field persisted below V17" % h)
        else:
            stats["v17_blocks"] += 1
            stats["fee_blocks" if fees > 0 else "zero_fee_blocks"] += 1
            dtd = sub * 15 // 100
            jal = sub * 5 // 100
            miner_sub = sub - dtd - jal
            if cb_outs[0][0] != OUT_COINBASE_MINER or cb_outs[0][2] != miner_sub + fees:
                fail("h=%d: miner output %d != %d" % (h, cb_outs[0][2], miner_sub + fees))
            if len(lot) > 1 or len(j_outs) > 1:
                fail("h=%d: duplicate DTD/J outputs" % h)
            if lot:
                if lot[0][1] != dtd + pending:
                    fail("h=%d: DTD output %d != dtd %d + pending %d" % (h, lot[0][1], dtd, pending))
                pending = 0
                stats["dtd_paid"] += 1
            else:
                pending += dtd
                stats["dtd_rollover"] += 1
            if int(b.get("pending_lottery_after", 0)) != pending:
                fail("h=%d: persisted pending %s != recomputed %d" % (h, b.get("pending_lottery_after", 0), pending))
            j_paid = j_outs[0][1] if j_outs else 0
            if j_paid > J:
                fail("h=%d: J output %d exceeds J_before %d" % (h, j_paid, J))
            J_before = J
            J = J - j_paid + jal
            if "v17_j_balance_after" in b and int(b["v17_j_balance_after"]) != J:
                fail("h=%d: persisted J %s != recomputed %d" % (h, b["v17_j_balance_after"], J))
            if h_paid or j_paid:
                if j_outs and h_winner is not None and j_outs[0][0] != h_winner:
                    fail("h=%d: H and J parts paid to different winners" % h)
                events.append({"height": h, "h_part": h_paid, "j_part": j_paid, "j_before": J_before,
                               "j_after": J, "winner": (h_winner or j_outs[0][0]).hex()})
            elif (h - v17) >= 0:
                pass
        # coinbase outputs into the UTXO set
        for k, (t, pkh, a) in enumerate(cb_outs):
            utxo[(cb_txid, k)] = a
            utxo_sum += a
        emitted += sub
        stats["supply_checks"] += 1
        if utxo_sum + pending + J != emitted:
            fail("h=%d: supply identity broken: utxo %d + pending %d + J %d != emitted %d"
                 % (h, utxo_sum, pending, J, emitted))
    if sum(utxo.values()) != utxo_sum:
        fail("internal: utxo sum drift")
    if "--expect-j" in opts and int(opts["--expect-j"]) != J:
        fail("tip J %d != node J %s" % (J, opts["--expect-j"]))
    if "--expect-pending" in opts and int(opts["--expect-pending"]) != pending:
        fail("tip pending %d != node pending %s" % (pending, opts["--expect-pending"]))
    res = {"tip": prev_h, "utxo_sum": utxo_sum, "pending": pending, "j_balance": J, "emitted": emitted,
           "jackpot_events_v17": events, "stats": stats, "failures": len(fails)}
    if "--json" in opts:
        json.dump(res, open(opts["--json"], "w"), indent=1)
    print("audit tip=%d utxo=%d pending=%d J=%d emitted=%d identity=%s v17_blocks=%d fee_blocks=%d "
          "zero_fee=%d dtd_paid=%d dtd_rollover=%d jackpot_events=%d failures=%d"
          % (prev_h, utxo_sum, pending, J, emitted, utxo_sum + pending + J == emitted, stats["v17_blocks"],
             stats["fee_blocks"], stats["zero_fee_blocks"], stats["dtd_paid"], stats["dtd_rollover"],
             len(events), len(fails)))
    for e in events:
        print("  jackpot #%d: H %d + J %d (J %d -> %d) winner %s" % (e["height"], e["h_part"], e["j_part"],
                                                                     e["j_before"], e["j_after"], e["winner"][:16]))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
