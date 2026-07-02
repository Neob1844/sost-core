#!/usr/bin/env python3
# SOST Post-Quantum Migration V2 — benchmark harness (RESEARCH ONLY)
#
# This script is NOT part of the SOST node/miner build. It touches no consensus
# code, no keys, no chain state. It measures ML-DSA (FIPS 204) sign/verify cost
# and derives transaction-size impact for the PQ_TX_FORMAT proposal.
#
# Timing numbers require a real PQ library. If liboqs / python-oqs is present the
# harness measures on THIS machine and prints measured microseconds. If it is
# absent the harness still emits the size math (from published FIPS 204/203
# parameter sets) and marks every timing cell RESULTS_PENDING_COMPUTE_ENV.
# It NEVER fabricates timings.
#
# Run:
#   python3 scripts/pq_bench/pq_bench.py                 # auto-detect oqs
#   python3 scripts/pq_bench/pq_bench.py --iters 200
#
# To get measured timings install liboqs + python bindings, e.g.:
#   git clone --depth 1 https://github.com/open-quantum-safe/liboqs
#   cmake -S liboqs -B liboqs/build -DBUILD_SHARED_LIBS=ON && cmake --build liboqs/build --parallel
#   sudo cmake --install liboqs/build && sudo ldconfig
#   pip install liboqs-python           # provides `import oqs`
# then re-run this script; PENDING cells become measured numbers.

import argparse
import json
import statistics
import sys
import time

# --- Published parameter-set sizes (bytes) ---------------------------------
# FIPS 204 (ML-DSA) final, Aug 2024. FIPS 203 (ML-KEM) final, Aug 2024.
# Sizes are fixed by the standard and are safe to use for size math without a
# library. They are NOT timings.
FIPS_SIZES = {
    "ML-DSA-44": {"pk": 1312, "sk": 2560, "sig": 2420, "std": "FIPS 204", "nist_level": 2},
    "ML-DSA-65": {"pk": 1952, "sk": 4032, "sig": 3309, "std": "FIPS 204", "nist_level": 3},
    "ML-DSA-87": {"pk": 2592, "sk": 4896, "sig": 4627, "std": "FIPS 204", "nist_level": 5},
    # KEM (P2P handshake research only, not a spend scheme)
    "ML-KEM-768": {"pk": 1184, "sk": 2400, "ct": 1088, "ss": 32, "std": "FIPS 203", "nist_level": 3},
}

# liboqs mechanism names (final FIPS names; some builds still expose Dilithium*)
OQS_ALIASES = {
    "ML-DSA-44": ["ML-DSA-44", "Dilithium2"],
    "ML-DSA-65": ["ML-DSA-65", "Dilithium3"],
    "ML-DSA-87": ["ML-DSA-87", "Dilithium5"],
}

# --- Current SOST consensus constants (from source of truth) ----------------
# include/sost/transaction.h:72-73  signature[64] + pubkey[33]
# include/sost/consensus_constants.h:15-16
ECDSA_SIG = 64
ECDSA_PUB = 33
LEGACY_WITNESS = ECDSA_SIG + ECDSA_PUB            # 97 bytes per input today
MAX_TX_BYTES = 100_000
MAX_BLOCK_BYTES = 1_000_000
# Non-witness per-input bytes: prev_txid(32)+prev_index(4) = 36 (transaction.cpp:207)
INPUT_FIXED_NONWITNESS = 36
# Per-output: amount(8)+type(1)+pkh(20)+payload_len(2) = 31 (transaction.cpp:233)
OUTPUT_BYTES = 31
TX_HEADER = 4 + 1 + 1 + 1  # version+tx_type+~compactsize in/out (approx small tx)


def try_import_oqs():
    try:
        import oqs  # noqa
        return oqs
    except Exception:
        return None


def resolve_mech(oqs, logical):
    enabled = set(oqs.get_enabled_sig_mechanisms())
    for name in OQS_ALIASES[logical]:
        if name in enabled:
            return name
    return None


def bench_sig(oqs, mech, iters):
    """Return dict of measured sizes + timing stats (microseconds) or None."""
    import oqs as _oqs
    msg = b"SOST-PQ-bench sighash 32-byte digest placeholder............"[:32]
    sign_us, verify_us = [], []
    with _oqs.Signature(mech) as signer:
        pk = signer.generate_keypair()
        for _ in range(iters):
            t0 = time.perf_counter()
            sig = signer.sign(msg)
            t1 = time.perf_counter()
            ok = signer.verify(msg, sig, pk)
            t2 = time.perf_counter()
            if not ok:
                raise RuntimeError(f"{mech}: self-verify failed")
            sign_us.append((t1 - t0) * 1e6)
            verify_us.append((t2 - t1) * 1e6)
    return {
        "measured": True,
        "pk": len(pk),
        "sig": len(sig),
        "sign_us_median": round(statistics.median(sign_us), 1),
        "verify_us_median": round(statistics.median(verify_us), 1),
        "sign_us_p95": round(sorted(sign_us)[int(len(sign_us) * 0.95)], 1),
        "verify_us_p95": round(sorted(verify_us)[int(len(verify_us) * 0.95)], 1),
    }


def witness_bytes(scheme, alg):
    """Serialized witness bytes for one input under the proposed format.
    Adds algorithm framing: alg_id(1) + sig_len(2 varint approx) + pk_len(2)."""
    frame = 1 + 2 + 2
    if scheme == "legacy":
        return LEGACY_WITNESS  # unchanged fixed layout, no framing (byte-identical)
    if scheme == "pq":
        s = FIPS_SIZES[alg]
        return frame + s["sig"] + s["pk"]
    if scheme == "hybrid":
        s = FIPS_SIZES[alg]
        # BOTH signatures must validate: ECDSA(64)+pub(33) AND ML-DSA(sig+pk)
        return frame + ECDSA_SIG + ECDSA_PUB + s["sig"] + s["pk"]
    raise ValueError(scheme)


def tx_size(scheme, alg, n_in, n_out=2):
    w = witness_bytes(scheme, alg)
    return TX_HEADER + n_in * (INPUT_FIXED_NONWITNESS + w) + n_out * OUTPUT_BYTES


def size_report():
    rows = []
    for scheme, alg in [("legacy", None),
                        ("pq", "ML-DSA-44"), ("pq", "ML-DSA-65"),
                        ("hybrid", "ML-DSA-44"), ("hybrid", "ML-DSA-65")]:
        label = scheme if scheme == "legacy" else f"{scheme}/{alg}"
        row = {"scheme": label, "witness_bytes_per_input": witness_bytes(scheme, alg)}
        for n in (1, 2, 10):
            sz = tx_size(scheme, alg, n)
            row[f"tx_{n}in_bytes"] = sz
            row[f"tx_{n}in_fits_MAX_TX"] = sz <= MAX_TX_BYTES
        # tx-per-1MB-block using the 2-input tx as a representative unit
        rep = tx_size(scheme, alg, 2)
        row["tx_per_1MB_block_2in"] = MAX_BLOCK_BYTES // rep
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    oqs = try_import_oqs()
    result = {"env": {"python": sys.version.split()[0], "oqs_available": bool(oqs)},
              "fips_sizes": FIPS_SIZES,
              "size_math": size_report(),
              "timings": {}}

    for logical in ("ML-DSA-44", "ML-DSA-65"):
        if oqs:
            mech = resolve_mech(oqs, logical)
            if mech:
                try:
                    result["timings"][logical] = bench_sig(oqs, mech, args.iters)
                    result["timings"][logical]["mechanism"] = mech
                    continue
                except Exception as e:  # pragma: no cover
                    result["timings"][logical] = {"error": str(e)}
                    continue
        result["timings"][logical] = {
            "measured": False,
            "status": "RESULTS_PENDING_COMPUTE_ENV",
            "note": "No liboqs/python-oqs in this environment; timings not fabricated.",
            "sizes_from": FIPS_SIZES[logical]["std"],
        }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    e = result["env"]
    print(f"# SOST PQ benchmark  python={e['python']}  oqs_available={e['oqs_available']}")
    print("\n## FIPS parameter sizes (bytes, from standard — not measured)")
    for k, v in FIPS_SIZES.items():
        print(f"  {k:12s} {v}")
    print("\n## Transaction-size impact (proposed witness framing)")
    for r in result["size_math"]:
        print(f"  {r['scheme']:16s} witness/input={r['witness_bytes_per_input']:5d}B  "
              f"1in={r['tx_1in_bytes']}B 2in={r['tx_2in_bytes']}B 10in={r['tx_10in_bytes']}B  "
              f"tx/1MB(2in)={r['tx_per_1MB_block_2in']}  10in<=MAX_TX:{r['tx_10in_fits_MAX_TX']}")
    print("\n## Timings (sign/verify, microseconds)")
    for k, v in result["timings"].items():
        if v.get("measured"):
            print(f"  {k:12s} MEASURED via {v['mechanism']:12s} "
                  f"sign~{v['sign_us_median']}us verify~{v['verify_us_median']}us "
                  f"(p95 sign {v['sign_us_p95']} / verify {v['verify_us_p95']})")
        else:
            print(f"  {k:12s} {v['status']} — {v.get('note','')}")
    print("\nRun with --json for machine-readable output.")


if __name__ == "__main__":
    main()
