#!/usr/bin/env python3
"""
sim_80_15_5.py - RESEARCH ONLY. Not consensus code. Changes nothing on chain.

Replays a real SOST mainnet chain dump (JSON with "blocks"[].transactions[] as
raw serialized tx hex) and compares the CURRENT post-V15 coinbase split against a
hypothetical 80 / 15 / 5 split:

  current (verified from code, src/sost-node.cpp coinbase shape decision +
  include/sost/lottery.h phase2_coinbase_split):
      from V15_HEIGHT (25000) every block is a DTD draw (is_lottery_block == true).
      total_reward = subsidy + fees
      DTD share    = total_reward // 2         -> OUT_COINBASE_LOTTERY (0x04) to the
                                                  DTD winner, or chain-state pending
                                                  if the eligibility set is empty
      miner share  = total_reward - DTD share  -> OUT_COINBASE_MINER (0x01)
      Gold Vault / PoPC coinbase outputs: 0 (emission transition (T)).
      Historical Jackpot: TX_TYPE_JACKPOT (0x02) every 288 blocks from 25290,
      base 100 SOST / cap 500, spent from the FROZEN historical reserve UTXOs
      (Gold Vault + PoPC constitutional addresses). No new emission feeds it.

  candidate (research):
      same total_reward, no new emission, no fee burn, no native burn
      jackpot inflow = total_reward * 5 // 100        -> EXISTING jackpot pool
                                                         (modelled as a separate
                                                         accumulator J; the frozen
                                                         historical reserve is NOT
                                                         mixed with it)
      DTD share      = total_reward * 15 // 100       -> same DTD winner as on chain
      miner share    = total_reward - DTD - jackpot    (miner absorbs rounding)
      The 5% is NOT a direct node payment; it is paid out only through the
      existing jackpot draw.

Standard library only. Usage:
    python3 tools/research/sim_80_15_5.py <mainnet-chain.json> [--json out.json]
"""
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict

STOCKS = 100_000_000
V11_PHASE2_HEIGHT = 7100
V15_HEIGHT = 25000
V16_HEIGHT = 30000
JACKPOT_FIRST = 25290
JACKPOT_CADENCE = 288
JACKPOT_BASE = 100 * STOCKS
DTD_DOMINANCE_WINDOW = 288
DTD_DOMINANCE_MAX_BPS = 1000
DTD_DOMINANCE_MIN_MINERS = 11
DTD_RECENCY_V15 = 5000
DTD_RECENCY_V15_JACKPOT = 20000
DTD_RECENCY_V16 = 288
COOLDOWN = 6
BLOCKS_PER_EPOCH = 131_553
R0 = 785_100_863
Q = math.exp(-0.25)
BLOCKS_PER_DAY = 144  # 600 s target

ADDR_GOLD_VAULT = bytes.fromhex("1a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d")
ADDR_POPC_POOL = bytes.fromhex("d876c5b8580ca8d2818ab0fed393df9cb1c3a30f")
RESERVE = {ADDR_GOLD_VAULT, ADDR_POPC_POOL}


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
    txid = hashlib.sha256(hashlib.sha256(b).digest()).digest()
    return ttype, ins, outs, txid


def gini(vals):
    v = sorted(x for x in vals if x > 0)
    n = len(v)
    if n == 0:
        return 0.0
    s = sum(v)
    cum = sum((i + 1) * x for i, x in enumerate(v))
    return (2 * cum) / (n * s) - (n + 1) / n


def hhi(vals):
    s = sum(vals)
    return sum((x / s) ** 2 for x in vals) if s else 0.0


def addr(pkh):
    return "sost1" + pkh.hex()


def dtd_eligible(h, last_mined, window_counts, recent):
    """Replicates compute_lottery_eligibility_set for mainnet (PoPC gate inert)."""
    if h >= V16_HEIGHT:
        rec = DTD_RECENCY_V16
    elif h >= V15_HEIGHT:
        is_jp = h >= JACKPOT_FIRST and (h - JACKPOT_FIRST) % JACKPOT_CADENCE == 0
        rec = DTD_RECENCY_V15_JACKPOT if is_jp else DTD_RECENCY_V15
    else:
        rec = 0
    observed = sum(window_counts.values())
    armed = (h < V16_HEIGHT) or len(window_counts) >= DTD_DOMINANCE_MIN_MINERS

    def build(apply_cd):
        out = []
        for pkh in sorted(last_mined):
            lm = last_mined[pkh]
            if rec and lm < h - rec:
                continue
            if apply_cd and pkh in recent:
                continue
            if lm < V11_PHASE2_HEIGHT:
                continue
            if armed and window_counts.get(pkh, 0) * 10000 >= DTD_DOMINANCE_MAX_BPS * observed:
                continue
            out.append(pkh)
        return out

    s = build(True)
    if h >= V16_HEIGHT and not s:
        s = build(False)
    return s


def dtd_pick(eligible, hashes, h):
    buf = b"SOST_LOTTERY_V11"
    for hh in range(h - 16, h):
        if hh >= 0:
            buf += hashes[hh]
    buf += h.to_bytes(8, "little")
    roll = int.from_bytes(hashlib.sha256(buf).digest()[:8], "little")
    return eligible[roll % len(eligible)]


def binom_stats(n, p, amt):
    """mean and sd of amt * Binomial(n, p)."""
    return amt * n * p, amt * math.sqrt(n * p * (1 - p))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    out_json = None
    if "--json" in sys.argv:
        out_json = sys.argv[sys.argv.index("--json") + 1]
    chain = json.load(open(sys.argv[1]))
    blocks = chain["blocks"]
    tip = blocks[-1]["height"]

    utxo = {}
    hashes = {}
    last_mined = {}
    miner_at = {}
    rows = []
    jackpots = []
    reserve_bal = 0
    reserve_series = []
    dtd_model_checked = dtd_model_match = 0
    eligible_sizes = []

    for blk in blocks:
        h = blk["height"]
        hashes[h] = bytes.fromhex(blk["block_id"])
        if not blk.get("transactions"):
            # genesis dump carries no tx list; its outputs are not in the UTXO set here
            miner_at[h] = bytes(20)
            # genesis coinbase reserve outputs (gold vault + popc) are not in the dump;
            # count them so the reserve balance is exact (spent by the first jackpot).
            reserve_bal += blk.get("gold_vault", 0) + blk.get("popc_pool", 0)
            reserve_series.append((h, reserve_bal))
            continue
        txs = [parse_tx(x) for x in blk["transactions"]]
        cb_type, _, cb_outs, _ = txs[0]
        assert cb_type == 0x01
        miner_pkh = next(p for t, p, a in cb_outs if t == 0x01)
        cb_total = sum(a for t, p, a in cb_outs)
        miner_amt = sum(a for t, p, a in cb_outs if t == 0x01)
        dtd = [(p, a) for t, p, a in cb_outs if t == 0x04]
        gold = sum(a for t, p, a in cb_outs if t == 0x02)
        popc = sum(a for t, p, a in cb_outs if t == 0x03)

        # DTD eligibility model (validated against on-chain winners from V15).
        if h >= V15_HEIGHT:
            wlo = h - DTD_DOMINANCE_WINDOW
            wc = Counter(miner_at[x] for x in range(max(0, wlo), h))
            recent = {miner_at[x] for x in range(max(0, h - COOLDOWN), h)}
            el = dtd_eligible(h, last_mined, wc, recent)
            eligible_sizes.append((h, len(el)))
            if dtd and el:
                dtd_model_checked += 1
                if dtd_pick(el, hashes, h) == dtd[0][0]:
                    dtd_model_match += 1

        jp_paid = []
        for ttype, ins, outs, txid in txs:
            in_found = 0
            missing = 0
            for pt, pi in ins:
                if ttype == 0x01:
                    continue
                o = utxo.pop((pt, pi), None)
                if o is None:
                    missing += 1
                    continue
                in_found += o[1]
                if o[0] in RESERVE:
                    reserve_bal -= o[1]
            if ttype == 0x02 and missing:
                # inputs not in the dump = genesis reserve outputs; jackpot txs carry
                # zero fee (verified: inputs == outputs on every fully-resolved jackpot)
                reserve_bal -= sum(a for _, _, a in outs) - in_found
            for i, (oty, pkh, amt) in enumerate(outs):
                utxo[(txid, i)] = (pkh, amt, oty)
                if pkh in RESERVE:
                    reserve_bal += amt
            if ttype == 0x02:
                for oty, pkh, amt in outs:
                    if pkh not in RESERVE:
                        jp_paid.append((pkh, amt))
        for pkh, amt in jp_paid:
            jackpots.append((h, pkh, amt))

        rows.append(dict(h=h, ts=blk["timestamp"], subsidy=blk["subsidy"], total=cb_total,
                         miner=miner_pkh, miner_amt=miner_amt, dtd=dtd, gold=gold, popc=popc,
                         jp=jp_paid))
        reserve_series.append((h, reserve_bal))
        miner_at[h] = miner_pkh
        last_mined[miner_pkh] = h

    res = {"tip": tip, "blocks": len(rows)}
    res["dtd_model_validation"] = {
        "checked_blocks": dtd_model_checked, "exact_winner_matches": dtd_model_match}

    # ---------------- regime windows ----------------
    windows = {"V15 [25000,29999]": (V15_HEIGHT, V16_HEIGHT - 1),
               f"V16 [30000,{tip}]": (V16_HEIGHT, tip),
               f"post-V15 [25000,{tip}]": (V15_HEIGHT, tip)}
    res["windows"] = {}
    for name, (lo, hi) in windows.items():
        W = [r for r in rows if lo <= r["h"] <= hi]
        n = len(W)
        tot = sum(r["total"] for r in W)
        fees = sum(r["total"] - r["subsidy"] for r in W)
        days = (W[-1]["ts"] - W[0]["ts"]) / 86400 if n > 1 else 0
        blocks_by = Counter(r["miner"] for r in W)

        cur = defaultdict(int)       # per-pkh total received, current rules
        cur_miner = defaultdict(int)
        cur_dtd = defaultdict(int)
        cand = defaultdict(int)
        cand_miner = defaultdict(int)
        cand_dtd = defaultdict(int)
        cand_dtd_pending = 0
        cand_jinflow = 0
        empty_dtd_blocks = 0
        for r in W:
            T = r["total"]
            cur[r["miner"]] += r["miner_amt"]
            cur_miner[r["miner"]] += r["miner_amt"]
            for p, a in r["dtd"]:
                cur[p] += a
                cur_dtd[p] += a
            jp5 = T * 5 // 100
            d15 = T * 15 // 100
            m80 = T - d15 - jp5
            cand[r["miner"]] += m80
            cand_miner[r["miner"]] += m80
            cand_jinflow += jp5
            cand_dtd_pending += d15
            if r["dtd"]:
                p = r["dtd"][0][0]
                cand[p] += cand_dtd_pending
                cand_dtd[p] += cand_dtd_pending
                cand_dtd_pending = 0
            else:
                empty_dtd_blocks += 1
            for p, a in r["jp"]:      # actual jackpot payouts are identical in both
                cur[p] += a
                cand[p] += a

        def top(d, k):
            s = sum(d.values())
            return sum(sorted(d.values(), reverse=True)[:k]) / s if s else 0

        big = {p for p, c in blocks_by.items() if c / n >= 0.10}
        small = set(cur) | set(cand)
        small -= big

        def share(d, ks):
            s = sum(d.values())
            return sum(v for p, v in d.items() if p in ks) / s if s else 0

        topm = blocks_by.most_common(5)
        w = {
            "blocks": n, "days": round(days, 2),
            "total_reward_SOST": tot / STOCKS, "fees_SOST": fees / STOCKS,
            "distinct_producers": len(blocks_by),
            "producer_block_share_top5": [(addr(p)[:16], round(c / n, 4)) for p, c in topm],
            "top1_block_share": round(topm[0][1] / n, 4),
            "top3_block_share": round(sum(c for _, c in topm[:3]) / n, 4),
            "dtd_empty_blocks": empty_dtd_blocks,
            "current": {
                "miner_SOST_per_block": sum(cur_miner.values()) / n / STOCKS,
                "dtd_SOST_per_block": sum(cur_dtd.values()) / n / STOCKS,
                "jackpot_inflow_SOST_per_block": 0.0,
                "dtd_distinct_recipients": len(cur_dtd),
                "dtd_gini": round(gini(cur_dtd.values()), 4),
                "dtd_hhi": round(hhi(list(cur_dtd.values())), 4),
                "dtd_to_top1_producer": round(share(cur_dtd, {topm[0][0]}), 4),
                "all_flows_top1": round(top(cur, 1), 4),
                "all_flows_top3": round(top(cur, 3), 4),
                "all_flows_gini": round(gini(cur.values()), 4),
                "all_flows_hhi": round(hhi(list(cur.values())), 4),
                "small_participants_share_all_flows": round(share(cur, small), 4),
                "hash_proportional_share": round(sum(cur_miner.values()) / tot, 4),
            },
            "candidate_80_15_5": {
                "miner_SOST_per_block": sum(cand_miner.values()) / n / STOCKS,
                "dtd_SOST_per_block": (sum(cand_dtd.values()) + cand_dtd_pending) / n / STOCKS,
                "jackpot_inflow_SOST_per_block": cand_jinflow / n / STOCKS,
                "jackpot_inflow_total_SOST": cand_jinflow / STOCKS,
                "dtd_distinct_recipients": len(cand_dtd),
                "dtd_gini": round(gini(cand_dtd.values()), 4),
                "dtd_hhi": round(hhi(list(cand_dtd.values())), 4),
                "all_flows_top1": round(top(cand, 1), 4),
                "all_flows_top3": round(top(cand, 3), 4),
                "all_flows_gini": round(gini(cand.values()), 4),
                "all_flows_hhi": round(hhi(list(cand.values())), 4),
                "small_participants_share_all_flows": round(share(cand, small), 4),
                "hash_proportional_share": round(sum(cand_miner.values()) / tot, 4),
            },
            "per_producer_SOST": sorted(
                [(addr(p)[:16], blocks_by.get(p, 0), round(cur[p] / STOCKS, 2),
                  round(cand[p] / STOCKS, 2)) for p in set(cur) | set(cand)],
                key=lambda x: -x[2])[:12],
        }
        el = [s for hh, s in eligible_sizes if lo <= hh <= hi]
        w["dtd_eligible_set_size_mean"] = round(sum(el) / len(el), 2) if el else 0
        w["dtd_eligible_set_size_min_max"] = (min(el), max(el)) if el else (0, 0)
        res["windows"][name] = w

    # ---------------- jackpot pool ----------------
    rb = dict(reserve_series)
    jp_total = sum(a for _, _, a in jackpots)
    reserve_now = rb[tip]
    jp_heights = sorted({h for h, _, _ in jackpots})
    res["jackpot"] = {
        "historical_reserve_at_24999_SOST": rb[V15_HEIGHT - 1] / STOCKS,
        "historical_reserve_at_tip_SOST": reserve_now / STOCKS,
        "jackpot_payouts": len(jackpots),
        "jackpot_paid_total_SOST": jp_total / STOCKS,
        "first_last_paid_height": (jp_heights[0], jp_heights[-1]) if jp_heights else None,
        "payout_sizes_SOST": sorted({a / STOCKS for _, _, a in jackpots}),
        "v2_jackpot_heights_to_tip": [h for h in range(30186, tip + 1, JACKPOT_CADENCE)],
        "v2_jackpots_paid": len([h for h in jp_heights if h >= V16_HEIGHT]),
    }
    # Forward projection (subsidy decays by exp(-1/4) per epoch of 131,553 blocks).
    drain_per_block = JACKPOT_BASE / JACKPOT_CADENCE

    def project(inflow_frac, years=40):
        hist = reserve_now
        J = 0
        h = tip
        hist_empty_h = None
        pool_empty_h = None
        step = JACKPOT_CADENCE
        traj = []
        while h < tip + years * 365 * BLOCKS_PER_DAY:
            sub = int(R0 * Q ** (h // BLOCKS_PER_EPOCH))
            J += int(sub * inflow_frac) * step
            pay = JACKPOT_BASE
            take = min(hist, pay)
            hist -= take
            pay -= take
            if hist == 0 and hist_empty_h is None:
                hist_empty_h = h
            take = min(J, pay)
            J -= take
            pay -= take
            if pay > 0 and pool_empty_h is None:
                pool_empty_h = h
            h += step
            if (h - tip) % (BLOCKS_PER_DAY * 365) < step:
                traj.append((round((h - tip) / BLOCKS_PER_DAY / 365, 1),
                             round(hist / STOCKS, 1), round(J / STOCKS, 1)))
        yrs = lambda x: None if x is None else round((x - tip) / BLOCKS_PER_DAY / 365, 2)
        return {"historical_reserve_empty_height": hist_empty_h,
                "historical_reserve_empty_years": yrs(hist_empty_h),
                "base_payout_unfundable_height": pool_empty_h,
                "base_payout_unfundable_years": yrs(pool_empty_h),
                "yearly_hist_and_inflow_pool_SOST": traj[:12]}

    res["jackpot"]["drain_SOST_per_block_at_base"] = drain_per_block / STOCKS
    res["jackpot"]["projection_current_no_inflow"] = project(0.0)
    res["jackpot"]["projection_candidate_5pct_inflow"] = project(0.05)
    ep = [(e, int(R0 * Q ** e) * 5 // 100 * JACKPOT_CADENCE / STOCKS) for e in range(0, 6)]
    res["jackpot"]["inflow_per_288_blocks_by_epoch_SOST"] = ep

    # ---------------- small-miner variance (analytic) ----------------
    T = 785_100_863
    E16 = res["windows"][f"V16 [30000,{tip}]"]["dtd_eligible_set_size_mean"] or 1
    E15 = res["windows"][f"post-V15 [25000,{tip}]"]["dtd_eligible_set_size_mean"] or 1
    var = []
    for E, p in [(e, q) for e in (E16 + 1, 20, E15) for q in (0.005, 0.01, 0.05, 0.10)]:
        # a new small miner joins the eligible set, hence E16 + 1 in the V16 case
        row = {"hash_share": p, "assumed_dtd_eligible_set": round(E, 2)}
        for name, mf, df in (("current_50_50", 0.5, 0.5), ("candidate_80_15", 0.80, 0.15)):
            mm, ms = binom_stats(BLOCKS_PER_DAY, p, T * mf / STOCKS)
            # DTD is uniform over the eligible set and only reachable if the miner mined
            # in the last 288 blocks (2 days): P(eligible) = 1-(1-p)^288.
            pe = 1 - (1 - p) ** DTD_RECENCY_V16
            dm, ds = binom_stats(BLOCKS_PER_DAY, pe / E, T * df / STOCKS)
            mean = mm + dm
            sd = math.sqrt(ms ** 2 + ds ** 2)
            row[name] = {"daily_mean_SOST": round(mean, 3), "daily_sd_SOST": round(sd, 3),
                         "cv": round(sd / mean, 3) if mean else None,
                         "hash_proportional_fraction": round(mm / mean, 3) if mean else None}
        var.append(row)
    res["small_miner_daily_variance"] = var

    s = json.dumps(res, indent=1, default=str)
    print(s)
    if out_json:
        open(out_json, "w").write(s)


if __name__ == "__main__":
    main()
