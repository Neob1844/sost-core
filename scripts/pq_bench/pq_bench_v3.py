#!/usr/bin/env python3
# SOST Post-Quantum Migration V3 — benchmark harness (RESEARCH ONLY)
#
# NOT part of the SOST node/miner build. Touches no consensus code, no keys, no
# chain state. It (1) always emits the transaction SIZE math, which is known
# exactly from FIPS 204 parameter sets, and (2) measures ML-DSA keygen/sign/
# verify timings ONLY if a real PQ library (liboqs via python 'oqs') is present
# on THIS machine. If the library is absent it marks every timing cell
# RESULTS_PENDING_COMPUTE_ENV and NEVER fabricates a number.
#
# Usage:
#   python3 scripts/pq_bench/pq_bench_v3.py                 # auto-detect oqs
#   python3 scripts/pq_bench/pq_bench_v3.py --iters 200
#   python3 scripts/pq_bench/pq_bench_v3.py --json results/run.json
#
# To obtain measured timings, install liboqs + python bindings, e.g.:
#   git clone --depth 1 https://github.com/open-quantum-safe/liboqs
#   cmake -S liboqs -B liboqs/build -DBUILD_SHARED_LIBS=ON
#   cmake --build liboqs/build --parallel
#   pip install liboqs-python
#
# Author: NeoB.
import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone

PENDING = "RESULTS_PENDING_COMPUTE_ENV"

# --- Exact FIPS 204 component sizes (bytes). Do NOT alter without a citation. --
SIZES = {
    "ECDSA_SECP256K1": {"sig": 64,   "pk": 33,   "level": "classical"},
    "ML_DSA_44":       {"sig": 2420, "pk": 1312, "level": "NIST L2 (FIPS 204)"},
    "ML_DSA_65":       {"sig": 3309, "pk": 1952, "level": "NIST L3 (FIPS 204)"},
    "ML_DSA_87":       {"sig": 4627, "pk": 2592, "level": "NIST L5 (FIPS 204)"},
}

# Current SOST consensus limits (see include/sost/consensus_constants.h:15-16).
MAX_TX_BYTES_CONSENSUS = 100_000
MAX_BLOCK_BYTES_CONSENSUS = 1_000_000
# Hard cap on inputs per tx, independent of byte budget
# (include/sost/consensus_constants.h:17).
MAX_INPUTS_CONSENSUS = 256
# Fixed per-input overhead (prev_txid 32 + prev_index 4) before the witness.
INPUT_OUTPOINT_OVERHEAD = 36
# 2-byte length prefix per witness component (prototype format).
LEN_PREFIX = 2
ALGID_BYTE = 1


def per_input_bytes(name, hybrid_with=None):
    """Serialized per-input witness size under the prototype wire format."""
    s = SIZES[name]
    size = INPUT_OUTPOINT_OVERHEAD + ALGID_BYTE
    size += LEN_PREFIX + s["sig"] + LEN_PREFIX + s["pk"]
    if hybrid_with:
        h = SIZES[hybrid_with]
        size += LEN_PREFIX + h["sig"] + LEN_PREFIX + h["pk"]
    return size


def size_table():
    rows = []
    configs = [
        ("LEGACY_ECDSA", "ECDSA_SECP256K1", None),
        ("PQ_ML_DSA_44", "ML_DSA_44", None),
        ("PQ_ML_DSA_65", "ML_DSA_65", None),
        ("HYBRID_ECDSA_ML_DSA_44", "ECDSA_SECP256K1", "ML_DSA_44"),
    ]
    for label, base, hyb in configs:
        pib = per_input_bytes(base, hyb)
        by_bytes = MAX_TX_BYTES_CONSENSUS // pib
        rows.append({
            "config": label,
            "per_input_bytes": pib,
            "max_inputs_per_tx_by_bytes": by_bytes,
            # The 256-input consensus cap can bind before the byte budget.
            "max_inputs_per_tx_effective": min(by_bytes, MAX_INPUTS_CONSENSUS),
            "max_single_input_txs_per_block": MAX_BLOCK_BYTES_CONSENSUS // pib,
        })
    return rows


def try_measure(iters):
    """Return a dict of measured timings, or None if no PQ library present."""
    try:
        import oqs  # type: ignore
    except Exception:
        return None
    results = {}
    for mech, name in [("Dilithium2", "ML_DSA_44"),
                       ("Dilithium3", "ML_DSA_65"),
                       ("Dilithium5", "ML_DSA_87")]:
        try:
            import oqs, time  # noqa
            if mech not in oqs.get_enabled_sig_mechanisms():
                results[name] = {"status": "MECH_NOT_ENABLED"}
                continue
            keygen, sign, verify = [], [], []
            msg = b"SOST-pq-bench-v3"
            for _ in range(iters):
                with oqs.Signature(mech) as signer:
                    t = time.perf_counter(); pk = signer.generate_keypair()
                    keygen.append(time.perf_counter() - t)
                    t = time.perf_counter(); sig = signer.sign(msg)
                    sign.append(time.perf_counter() - t)
                    with oqs.Signature(mech) as ver:
                        t = time.perf_counter(); ok = ver.verify(msg, sig, pk)
                        verify.append(time.perf_counter() - t)
                        assert ok

            def stats(xs):
                xs_us = sorted(x * 1e6 for x in xs)
                return {
                    "iters": len(xs_us),
                    "mean_us": statistics.mean(xs_us),
                    "median_us": statistics.median(xs_us),
                    "p95_us": xs_us[int(0.95 * (len(xs_us) - 1))],
                    "stddev_us": statistics.pstdev(xs_us),
                }
            results[name] = {"status": "MEASURED", "keygen": stats(keygen),
                             "sign": stats(sign), "verify": stats(verify)}
        except Exception as e:  # pragma: no cover
            results[name] = {"status": f"ERROR:{type(e).__name__}"}
    return results


def env_block():
    def _git(*a):
        try:
            return subprocess.check_output(["git", *a],
                                           cwd=os.path.dirname(__file__) or ".",
                                           stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            return "unknown"
    return {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
    }


def main():
    ap = argparse.ArgumentParser(description="SOST PQ V3 benchmark harness (research only)")
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--json", type=str, default=None, help="write JSON results to this path")
    args = ap.parse_args()

    env = env_block()
    sizes = size_table()
    measured = try_measure(args.iters)

    print("== SOST PQ V3 benchmark harness (research only, off-consensus) ==")
    print(f"date={env['date_utc']} commit={env['git_commit'][:12]} branch={env['git_branch']}")
    print(f"platform={env['platform']} python={env['python']}")
    print()
    print("-- Transaction size impact (exact, from FIPS 204) --")
    print(f"  (effective max in/tx = min(byte-budget, MAX_INPUTS_CONSENSUS=256))")
    print(f"{'config':26} {'per_input_B':>12} {'in/tx(bytes)':>13} {'in/tx(eff)':>11} {'1in-tx/block':>13}")
    for r in sizes:
        print(f"{r['config']:26} {r['per_input_bytes']:>12} "
              f"{r['max_inputs_per_tx_by_bytes']:>13} {r['max_inputs_per_tx_effective']:>11} "
              f"{r['max_single_input_txs_per_block']:>13}")
    print()
    print("-- Timings (keygen / sign / verify) --")
    if measured is None:
        print(f"  liboqs / python 'oqs' NOT available on this machine.")
        print(f"  All timing cells = {PENDING}. No numbers fabricated.")
        print(f"  Install liboqs + liboqs-python and re-run to populate.")
    else:
        for name, res in measured.items():
            print(f"  {name}: {res.get('status')}")
            if res.get("status") == "MEASURED":
                for op in ("keygen", "sign", "verify"):
                    s = res[op]
                    print(f"    {op:7} mean={s['mean_us']:.1f}us median={s['median_us']:.1f}us "
                          f"p95={s['p95_us']:.1f}us stddev={s['stddev_us']:.1f}us n={s['iters']}")

    out = {
        "schema": "sost-pq-bench-v3",
        "environment": env,
        "sizes_bytes": SIZES,
        "consensus_limits": {
            "MAX_TX_BYTES_CONSENSUS": MAX_TX_BYTES_CONSENSUS,
            "MAX_BLOCK_BYTES_CONSENSUS": MAX_BLOCK_BYTES_CONSENSUS,
        },
        "size_impact": sizes,
        "timings": measured if measured is not None else PENDING,
        "timings_status": "MEASURED" if measured is not None else PENDING,
    }
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
