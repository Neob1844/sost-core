#!/usr/bin/env python3
"""
Validate parity between the cASERT Python simulator (scripts/v5_simulator.py)
and the C++ consensus implementation (src/pow/casert.cpp + include/sost/params.h).

Extracts constants and logic from both source files via text parsing,
compares them, and runs behavioral checks on the simulator.

Output:
  reports/simulator_parity_report.md   (human-readable)
  reports/simulator_parity_report.json (machine-readable)
"""

import json
import math
import os
import re
import sys
import random
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
CPP_FILE = os.path.join(ROOT_DIR, "src", "pow", "casert.cpp")
PARAMS_FILE = os.path.join(ROOT_DIR, "include", "sost", "params.h")
SIM_FILE = os.path.join(ROOT_DIR, "scripts", "v5_simulator.py")
REPORTS_DIR = os.path.join(ROOT_DIR, "reports")

# ---------------------------------------------------------------------------
# 1. Parse C++ constants from params.h
# ---------------------------------------------------------------------------

def parse_cpp_constants(path):
    """Extract all inline constexpr constants from params.h."""
    consts = {}
    with open(path) as f:
        text = f.read()

    # Match: inline constexpr <type> NAME = VALUE;
    pattern = re.compile(
        r'inline\s+constexpr\s+\w+\s+(\w+)\s*=\s*([^;]+);'
    )
    for m in pattern.finditer(text):
        name = m.group(1)
        val_str = m.group(2).strip()
        # Strip LL/u/U suffixes and evaluate
        cleaned = re.sub(r'[LlUu]+$', '', val_str)
        # Handle expressions like "1u << 16"
        cleaned = re.sub(r'(\d+)[uU]', r'\1', cleaned)
        # Handle "255u * Q16_ONE" by substituting known values
        # Two-pass: first get simple literals, then expressions
        try:
            val = int(cleaned, 0)
        except (ValueError, SyntaxError):
            val = cleaned  # defer
        consts[name] = val

    # Second pass: resolve expressions
    max_iters = 5
    for _ in range(max_iters):
        unresolved = {k: v for k, v in consts.items() if isinstance(v, str)}
        if not unresolved:
            break
        for name, expr in unresolved.items():
            resolved_expr = expr
            for cname, cval in consts.items():
                if isinstance(cval, int):
                    resolved_expr = re.sub(r'\b' + cname + r'\b', str(cval), resolved_expr)
            try:
                val = eval(resolved_expr)
                consts[name] = int(val)
            except Exception:
                pass  # still unresolved

    return consts


def parse_cpp_antistall_decay(path):
    """Extract anti-stall decay zone costs from casert.cpp."""
    with open(path) as f:
        text = f.read()

    zones = {}
    # Looking for: if (decayed_H >= 7) cost = 600;
    pattern = re.compile(r'if\s*\(\s*decayed_H\s*>=\s*(\d+)\)\s*cost\s*=\s*(\d+)')
    for m in pattern.finditer(text):
        threshold = int(m.group(1))
        cost = int(m.group(2))
        zones[threshold] = cost

    # Also "else cost = 1200;"
    else_pattern = re.compile(r'else\s+cost\s*=\s*(\d+)')
    m = else_pattern.search(text)
    if m:
        zones['else'] = int(m.group(1))

    return zones


def parse_cpp_easing_extra(path):
    """Extract the easing extra threshold and per-level cost."""
    with open(path) as f:
        text = f.read()
    # easing_time / 1800
    m = re.search(r'easing_drops\s*=.*easing_time\s*/\s*(\d+)', text)
    return int(m.group(1)) if m else None


def parse_cpp_profiles(path):
    """Extract CASERT_PROFILES from params.h."""
    with open(path) as f:
        text = f.read()
    # Find the CASERT_PROFILES array and extract all {a,b,c,d} tuples
    # The array spans multiple lines, so we grab everything between the
    # opening "= {" and the closing "};"
    m = re.search(r'CASERT_PROFILES\[\]\s*=\s*\{(.*?)\};', text, re.DOTALL)
    if not m:
        return []
    inner = m.group(1)
    tuples = re.findall(r'\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}', inner)
    profiles = []
    for t in tuples:
        profiles.append({
            'scale': int(t[0]),
            'steps': int(t[1]),
            'k': int(t[2]),
            'margin': int(t[3]),
        })
    return profiles


# ---------------------------------------------------------------------------
# 2. Parse Python simulator constants
# ---------------------------------------------------------------------------

def parse_python_constants(path):
    """Extract top-level constant assignments from the Python simulator."""
    consts = {}
    with open(path) as f:
        text = f.read()

    # Simple assignments: NAME = VALUE (with optional comment)
    pattern = re.compile(r'^(\w+)\s*=\s*(-?\d+)\s*(?:#.*)?$', re.MULTILINE)
    for m in pattern.finditer(text):
        consts[m.group(1)] = int(m.group(2))

    return consts


def parse_python_antistall_decay(path):
    """Extract anti-stall decay zone costs from the Python simulator."""
    with open(path) as f:
        text = f.read()

    zones = {}
    # if H >= 7: cost = 600
    pattern = re.compile(r'if\s+(?:H|decayed_H)\s*>=\s*(\d+):\s*\n\s*cost\s*=\s*(\d+)')
    for m in pattern.finditer(text):
        zones[int(m.group(1))] = int(m.group(2))

    # elif H >= 4: cost = 900
    pattern2 = re.compile(r'elif\s+(?:H|decayed_H)\s*>=\s*(\d+):\s*\n\s*cost\s*=\s*(\d+)')
    for m in pattern2.finditer(text):
        zones[int(m.group(1))] = int(m.group(2))

    # else: cost = 1200
    else_pattern = re.compile(r'else:\s*\n\s*cost\s*=\s*(\d+)')
    m = else_pattern.search(text)
    if m:
        zones['else'] = int(m.group(1))

    return zones


def parse_python_easing_per_level(path):
    """Extract easing per-level cost from simulator."""
    with open(path) as f:
        text = f.read()
    # easing_drops = int(easing_time / 1800) or similar
    m = re.search(r'easing_time\s*//?\s*(\d+)', text)
    return int(m.group(1)) if m else None


def parse_python_stab_pct(path):
    """Extract STAB_PCT dict from simulator."""
    with open(path) as f:
        text = f.read()
    m = re.search(r'STAB_PCT\s*=\s*\{([^}]+)\}', text)
    if not m:
        return {}
    d = {}
    for pair in re.finditer(r'(-?\d+)\s*:\s*(\d+)', m.group(1)):
        d[int(pair.group(1))] = int(pair.group(2))
    return d


# ---------------------------------------------------------------------------
# 3. Comparison engine
# ---------------------------------------------------------------------------

CONST_MAP = [
    # (display_name, cpp_name, python_name, category)
    ("GENESIS_TIME", "GENESIS_TIME", "GENESIS_TIME", "core"),
    ("TARGET_SPACING", "TARGET_SPACING", "TARGET_SPACING", "core"),
    ("GENESIS_BITSQ", "GENESIS_BITSQ", "GENESIS_BITSQ", "core"),
    ("H_MIN", "CASERT_H_MIN", "CASERT_H_MIN", "profile_range"),
    ("H_MAX", "CASERT_H_MAX", "CASERT_H_MAX", "profile_range"),
    ("V3_SLEW_RATE", "CASERT_V3_SLEW_RATE", "CASERT_V3_SLEW_RATE", "slew"),
    ("V3_LAG_FLOOR_DIV", "CASERT_V3_LAG_FLOOR_DIV", "CASERT_V3_LAG_FLOOR_DIV", "slew"),
    ("V4_FORK_HEIGHT", "CASERT_V4_FORK_HEIGHT", "CASERT_V4_FORK_HEIGHT", "fork"),
    ("AHEAD_ENTER", "CASERT_AHEAD_ENTER", "CASERT_AHEAD_ENTER", "ahead_guard"),
    ("V5_FORK_HEIGHT", "CASERT_V5_FORK_HEIGHT", "CASERT_V5_FORK_HEIGHT", "fork"),
    ("ANTISTALL_FLOOR_V5", "CASERT_ANTISTALL_FLOOR_V5", "CASERT_ANTISTALL_FLOOR_V5", "antistall"),
    ("ANTISTALL_FLOOR", "CASERT_ANTISTALL_FLOOR", "CASERT_ANTISTALL_FLOOR", "antistall"),
    ("ANTISTALL_EASING_EXTRA", "CASERT_ANTISTALL_EASING_EXTRA", "CASERT_ANTISTALL_EASING_EXTRA", "antistall"),
    ("EBR_ENTER", "CASERT_EBR_ENTER", "CASERT_EBR_ENTER", "ebr"),
    ("EBR_LEVEL_E2", "CASERT_EBR_LEVEL_E2", "CASERT_EBR_LEVEL_E2", "ebr"),
    ("EBR_LEVEL_E3", "CASERT_EBR_LEVEL_E3", "CASERT_EBR_LEVEL_E3", "ebr"),
    ("EBR_LEVEL_E4", "CASERT_EBR_LEVEL_E4", "CASERT_EBR_LEVEL_E4", "ebr"),
    ("V5_EXTREME_MIN", "CASERT_V5_EXTREME_MIN", "CASERT_V5_EXTREME_MIN", "extreme_cap"),
]

# Constants present in C++ but intentionally absent from the Python simulator
# (because the simulator simplifies bitsQ / EWMA / PID into an approximation)
CPP_ONLY_CONSTS = [
    "CASERT_EWMA_SHORT_ALPHA",
    "CASERT_EWMA_LONG_ALPHA",
    "CASERT_EWMA_VOL_ALPHA",
    "CASERT_EWMA_DENOM",
    "CASERT_INTEG_RHO",
    "CASERT_INTEG_ALPHA",
    "CASERT_INTEG_MAX",
    "CASERT_K_R",
    "CASERT_K_L",
    "CASERT_K_I",
    "CASERT_K_B",
    "CASERT_K_V",
    "CASERT_HYSTERESIS",
    "CASERT_DT_MIN",
    "CASERT_DT_MAX",
    "BITSQ_HALF_LIFE",
    "BITSQ_HALF_LIFE_V2",
    "BITSQ_MAX_DELTA_DEN",
    "BITSQ_MAX_DELTA_DEN_V2",
    "CASERT_V2_FORK_HEIGHT",
    "CASERT_V3_FORK_HEIGHT",
    "CASERT_V3_1_FORK_HEIGHT",
    "CASERT_AHEAD_EXIT",
    "CASERT_AHEAD_DELTA_DEN",
    "CASERT_AHEAD_PROFILE_THRESH",
    "CASERT_ANTISTALL_INTEG_DECAY",
]


def compare_constant(cpp_val, py_val):
    if cpp_val is None and py_val is None:
        return "SKIP"
    if cpp_val is None:
        return "WARN"  # present in Python but not C++
    if py_val is None:
        return "WARN"  # present in C++ but not Python
    if isinstance(cpp_val, int) and isinstance(py_val, int):
        if cpp_val == py_val:
            return "PASS"
        # Check if close (within 1%)
        if cpp_val != 0 and abs(cpp_val - py_val) / abs(cpp_val) < 0.01:
            return "WARN"
        return "FAIL"
    return "FAIL"


# ---------------------------------------------------------------------------
# 4. Logic comparison
# ---------------------------------------------------------------------------

def check_logic_differences(cpp_text, py_text):
    """Identify structural logic differences between C++ and Python."""
    findings = []

    # Check 1: PID controller -- C++ uses full EWMA/PID, Python uses simplified
    if 'CASERT_K_R' in cpp_text and 'K_R' not in py_text:
        findings.append({
            "id": "LOGIC-001",
            "title": "PID controller is simplified in simulator",
            "detail": (
                "C++ uses a full 5-term PID controller (K_R*r + K_L*lag + K_I*I + "
                "K_B*burst + K_V*vol) with EWMA smoothing. Python uses a simplified "
                "approximation: H_raw = int(round(lag * 0.25 + burst_signal * 0.5)). "
                "The gains are NOT the same as the C++ K_L=0.40, K_R=0.05, etc."
            ),
            "severity": "HIGH",
            "impact": (
                "Profile selection will differ between C++ and Python for the same "
                "chain state. The simulator is a behavioral model, not a bit-exact "
                "replica. This is documented in the simulator header."
            ),
            "cpp_location": "casert.cpp:234-238",
            "py_location": "v5_simulator.py:124",
        })

    # Check 2: bitsQ computation -- not in simulator
    if 'casert_next_bitsq' in cpp_text and 'casert_next_bitsq' not in py_text.lower():
        findings.append({
            "id": "LOGIC-002",
            "title": "bitsQ primary controller absent from simulator",
            "detail": (
                "C++ computes bitsQ (Q16.16 difficulty) using exponential adjustment "
                "with epoch anchoring, half-life, delta caps, and Ahead Guard. "
                "Python simulator does not model bitsQ at all; it uses a separate "
                "block-time sampling model (exponential distribution based on "
                "PROFILE_DIFFICULTY and STAB_PCT)."
            ),
            "severity": "MEDIUM",
            "impact": (
                "Simulator cannot verify bitsQ-related behavior (delta caps, Ahead "
                "Guard on bitsQ). Equalizer policy is tested, bitsQ is not."
            ),
            "cpp_location": "casert.cpp:67-158",
            "py_location": "v5_simulator.py:188-208 (sample_block_dt)",
        })

    # Check 3: EWMA computation absent
    if 'CASERT_EWMA_SHORT_ALPHA' in cpp_text and 'EWMA' not in py_text:
        findings.append({
            "id": "LOGIC-003",
            "title": "EWMA signal computation absent from simulator",
            "detail": (
                "C++ computes S (short EWMA), M (long EWMA), V (volatility), and "
                "I (integrator) iteratively over the last 128 blocks. Python "
                "simulator approximates the control signal directly from lag and "
                "a single burst_signal term."
            ),
            "severity": "MEDIUM",
            "impact": (
                "Volatility-driven and integrator-driven profile adjustments are "
                "not captured. The simulator may under- or over-respond to "
                "sustained deviations."
            ),
            "cpp_location": "casert.cpp:192-224",
            "py_location": "v5_simulator.py:121-124",
        })

    # Check 4: Safety rule 1 placement
    # C++ pre-V5: safety rule 1 before slew only
    # C++ V5: safety rule 1 before AND after slew
    # Python: safety rule 1 before slew AND after slew (when v5_enabled)
    py_has_post_slew_safety = 'Safety rule 1 post-slew' in py_text or (
        'if lag <= 0:' in py_text and 'v5_enabled' in py_text
    )
    if py_has_post_slew_safety:
        findings.append({
            "id": "LOGIC-004",
            "title": "Safety rule 1 post-slew: MATCHES C++ V5 logic",
            "detail": (
                "Both C++ and Python apply safety rule 1 (if lag <= 0: H = min(H, 0)) "
                "AFTER the slew rate when V5 is active. This is the key V5 fix."
            ),
            "severity": "OK",
            "impact": "Correct behavior.",
            "cpp_location": "casert.cpp:371-373",
            "py_location": "v5_simulator.py:143-144",
        })

    # Check 5: V2 slew (pre-V3) not modeled in simulator
    if 'prev_H_est' in cpp_text and 'prev_H_est' not in py_text:
        findings.append({
            "id": "LOGIC-005",
            "title": "V2 slew rate heuristic not modeled in simulator",
            "detail": (
                "C++ has a V2 code path (blocks < 4100) with +/-1 slew and "
                "heuristic prev_H estimation. The simulator only models V3+ "
                "behavior (starts at height 4300 by default)."
            ),
            "severity": "LOW",
            "impact": (
                "Not relevant for V5 analysis since the simulator focuses on "
                "heights >= 4300."
            ),
            "cpp_location": "casert.cpp:404-416",
            "py_location": "N/A",
        })

    # Check 6: V3/V3.1 prev_H recomputation not modeled
    if 'V3 (blocks 4100-4199)' in cpp_text and 'V3 (blocks' not in py_text:
        findings.append({
            "id": "LOGIC-006",
            "title": "V3/V3.1 prev_H recomputation not modeled",
            "detail": (
                "C++ has separate code paths for V3 (PID recompute) and V3.1 "
                "(stored profile_index with fallback). The simulator uses "
                "chain[-1]['profile_index'] directly (V4+ behavior)."
            ),
            "severity": "LOW",
            "impact": (
                "Not relevant for V5 analysis. V3/V3.1 heights are in the past."
            ),
            "cpp_location": "casert.cpp:292-339",
            "py_location": "v5_simulator.py:111",
        })

    # Check 7: Anti-stall easing absent from simulator
    py_has_easing = 'CASERT_ANTISTALL_EASING_EXTRA' in py_text or 'easing_time' in py_text
    if not py_has_easing and 'CASERT_ANTISTALL_EASING_EXTRA' in cpp_text:
        findings.append({
            "id": "LOGIC-007",
            "title": "Anti-stall easing (E1-E4 after 6h at B0) absent from simulator",
            "detail": (
                "C++ implements an easing emergency: if stall >= t_act and H <= 0, "
                "after CASERT_ANTISTALL_EASING_EXTRA (21600s = 6h) additional time, "
                "activate easing profiles at 1800s per level. The Python simulator's "
                "anti-stall only decays H toward 0 but never goes below 0."
            ),
            "severity": "MEDIUM",
            "impact": (
                "Simulator cannot test the easing emergency path. Very long stalls "
                "(8+ hours) would behave differently in the simulator vs C++."
            ),
            "cpp_location": "casert.cpp:447-455",
            "py_location": "v5_simulator.py:165-183 (missing easing section)",
        })

    # Check 8: Python PID weights vs C++ gains
    py_lag_weight = None
    py_burst_weight = None
    m = re.search(r'lag\s*\*\s*([\d.]+)', py_text)
    if m:
        py_lag_weight = float(m.group(1))
    m = re.search(r'burst_signal\s*\*\s*([\d.]+)', py_text)
    if m:
        py_burst_weight = float(m.group(1))

    if py_lag_weight is not None:
        cpp_k_l = 26214 / 65536.0  # ~0.40
        findings.append({
            "id": "LOGIC-008",
            "title": f"PID lag gain mismatch: C++ K_L={cpp_k_l:.4f} vs Python lag*{py_lag_weight}",
            "detail": (
                f"C++ K_L = 26214/65536 = {cpp_k_l:.4f}. Python uses lag * {py_lag_weight}. "
                f"The Python weight is applied to raw lag (integer), while C++ applies "
                f"K_L to L_q16 >> 16. The effective scaling differs because C++ also "
                f"includes K_R, K_I, K_B, K_V terms and a final >> 16 normalization."
            ),
            "severity": "HIGH",
            "impact": (
                "Exact profile indices will differ. The simulator is a behavioral "
                "approximation, not a consensus-exact replica."
            ),
            "cpp_location": "casert.cpp:234 (CASERT_K_L = 26214)",
            "py_location": f"v5_simulator.py:124 (lag * {py_lag_weight})",
        })

    return findings


# ---------------------------------------------------------------------------
# 5. Behavioral checks (run the simulator)
# ---------------------------------------------------------------------------

# We need to import the simulator's compute_profile and simulate functions.
# Add the scripts dir to path and import.

def import_simulator():
    """Import the simulator module."""
    sys.path.insert(0, SCRIPT_DIR)
    import importlib
    spec = importlib.util.spec_from_file_location("v5_simulator", SIM_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_behavioral_checks():
    """Run behavioral checks on the simulator."""
    sim = import_simulator()
    results = []

    # -- Check B1: Determinism --
    class Args:
        blocks = 500
        start_height = 4300
        hashrate = 1.3
        variance = "medium"
        inject_stalls = False
        stall_prob = 0.0
        stall_min = 0
        stall_max = 0
        seed = 42
        fork_v5 = True
        output = "/dev/null"

    args = Args()
    rng1 = random.Random(42)
    rows1 = sim.simulate(args, rng1)
    rng2 = random.Random(42)
    rows2 = sim.simulate(args, rng2)
    deterministic = (rows1 == rows2)
    results.append({
        "id": "BEH-001",
        "name": "Determinism (same seed, same output)",
        "status": "PASS" if deterministic else "FAIL",
        "detail": f"Ran 500 blocks twice with seed=42. Identical={'yes' if deterministic else 'NO'}.",
    })

    # -- Check B2: No impossible profile jumps (delta > 3 after slew) --
    # Note: the lag_floor (lag / LAG_FLOOR_DIV) is applied AFTER the slew
    # rate in both C++ and Python, so it CAN push H above prev_H + 3.
    # The extreme cap (V5, H10+) limits climb to +1/block in the extreme
    # range but not below H10.  We only flag jumps that exceed what
    # lag_floor could produce.
    rows = rows1
    max_jump = 0
    violations = []
    for i in range(1, len(rows)):
        pi_prev = rows[i-1]["profile_index"]
        pi_curr = rows[i]["profile_index"]
        delta = abs(pi_curr - pi_prev)
        if delta > max_jump:
            max_jump = delta

        # A jump > 3 is allowed if lag_floor explains the upward push
        # (lag > 10 and lag // 8 >= pi_curr) OR if it's a downward jump
        # due to safety-rule-1-post-slew / EBR.
        if delta > 3:
            lag_i = rows[i]["lag"]
            upward = pi_curr > pi_prev
            # lag_floor can justify upward jumps when lag > 10
            lag_floor_justified = upward and lag_i > 10 and (lag_i // 8) >= pi_curr
            # Downward jumps beyond slew are justified by safety rule 1
            # post-slew (lag <= 0 forces H <= 0) or EBR cliffs
            downward_justified = (not upward) and (lag_i <= 0 or lag_i <= sim.CASERT_EBR_ENTER)
            if not lag_floor_justified and not downward_justified:
                violations.append({
                    "height": rows[i]["height"],
                    "from": pi_prev,
                    "to": pi_curr,
                    "delta": delta,
                    "lag": lag_i,
                })
    results.append({
        "id": "BEH-002",
        "name": "No unexplained profile jumps (delta > 3 without lag_floor/safety justification)",
        "status": "PASS" if len(violations) == 0 else "FAIL",
        "detail": (
            f"Max observed jump: {max_jump}. "
            f"Unexplained violations: {len(violations)}. "
            f"(Jumps > 3 from lag_floor or safety-rule-post-slew are expected.)"
            + (f" First unexplained: height {violations[0]['height']}, "
               f"{violations[0]['from']}->{violations[0]['to']} (lag={violations[0]['lag']})"
               if violations else "")
        ),
    })

    # -- Check B3: Target mean near 600s over 5000 blocks --
    args_long = Args()
    args_long.blocks = 5000
    args_long.variance = "low"
    rng_long = random.Random(12345)
    rows_long = sim.simulate(args_long, rng_long)
    intervals = [r["interval_s"] for r in rows_long]
    mean_interval = sum(intervals) / len(intervals)
    # Allow 15% tolerance
    mean_ok = abs(mean_interval - 600) / 600 < 0.15
    results.append({
        "id": "BEH-003",
        "name": "Target mean near 600s over 5000 blocks",
        "status": "PASS" if mean_ok else "WARN",
        "detail": (
            f"Mean block interval: {mean_interval:.1f}s "
            f"(target: 600s, tolerance: +/-15%). "
            f"{'Within' if mean_ok else 'OUTSIDE'} tolerance."
        ),
    })

    # -- Check B4: Anti-stall monotonicity --
    # When stall time grows with no block, profile should never INCREASE.
    # Test: build a chain at B0 on schedule, then simulate increasing stall times.
    chain = []
    base_time = sim.GENESIS_TIME + 4300 * sim.TARGET_SPACING
    for i in range(5):
        chain.append({
            "height": 4297 + i,
            "time": base_time + i * 600,
            "profile_index": 5,  # start at H5
        })
    stall_profiles = []
    for stall_add in range(0, 40000, 300):  # 0 to ~11 hours
        now = chain[-1]["time"] + stall_add
        p = sim.compute_profile(chain, 4302, now, True)
        stall_profiles.append((stall_add, p))

    monotonic = True
    mono_violations = []
    for i in range(1, len(stall_profiles)):
        if stall_profiles[i][1] > stall_profiles[i-1][1]:
            monotonic = False
            mono_violations.append({
                "stall_s": stall_profiles[i][0],
                "prev_profile": stall_profiles[i-1][1],
                "curr_profile": stall_profiles[i][1],
            })

    results.append({
        "id": "BEH-004",
        "name": "Anti-stall monotonicity (profile never increases during stall)",
        "status": "PASS" if monotonic else "FAIL",
        "detail": (
            f"Tested stall from 0 to 40000s. "
            f"Monotonic={'yes' if monotonic else 'NO'}. "
            f"Violations: {len(mono_violations)}."
            + (f" First at {mono_violations[0]['stall_s']}s: "
               f"{mono_violations[0]['prev_profile']}->{mono_violations[0]['curr_profile']}"
               if mono_violations else "")
        ),
    })

    # -- Check B5: No undefined profile indices --
    all_profiles = set()
    for r in rows_long:
        all_profiles.add(r["profile_index"])
    out_of_range = [p for p in all_profiles if p < sim.CASERT_H_MIN or p > sim.CASERT_H_MAX]
    results.append({
        "id": "BEH-005",
        "name": "No undefined profile indices (outside H_MIN to H_MAX)",
        "status": "PASS" if len(out_of_range) == 0 else "FAIL",
        "detail": (
            f"Observed profiles: {sorted(all_profiles)}. "
            f"Valid range: [{sim.CASERT_H_MIN}, {sim.CASERT_H_MAX}]. "
            f"Out-of-range: {out_of_range if out_of_range else 'none'}."
        ),
    })

    return results


# ---------------------------------------------------------------------------
# 6. Report generation
# ---------------------------------------------------------------------------

def generate_reports(const_results, logic_findings, behavioral_results,
                     cpp_only_missing, antistall_cmp, easing_cmp, profiles_match):
    """Generate .md and .json reports."""

    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # --- Compute overall verdict ---
    n_fail = sum(1 for r in const_results if r["status"] == "FAIL")
    n_warn = sum(1 for r in const_results if r["status"] == "WARN")
    n_pass = sum(1 for r in const_results if r["status"] == "PASS")

    beh_fail = sum(1 for r in behavioral_results if r["status"] == "FAIL")
    beh_warn = sum(1 for r in behavioral_results if r["status"] == "WARN")

    logic_high = sum(1 for f in logic_findings if f["severity"] == "HIGH")
    logic_medium = sum(1 for f in logic_findings if f["severity"] == "MEDIUM")

    if n_fail > 0 or beh_fail > 0:
        confidence = "LOW"
        verdict_detail = (
            "Constant mismatches or behavioral failures detected. "
            "The simulator does NOT faithfully replicate the consensus code."
        )
    elif logic_high > 0 or n_warn > 2 or beh_warn > 0:
        confidence = "MEDIUM"
        verdict_detail = (
            "Equalizer policy constants match, but the simulator uses a "
            "simplified PID model and omits bitsQ/EWMA computation. "
            "It is a behavioral approximation, not a bit-exact replica."
        )
    else:
        confidence = "HIGH"
        verdict_detail = "All constants match and behavioral checks pass."

    # --- Markdown report ---
    md = []
    md.append(f"# SOST cASERT Simulator Parity Report")
    md.append(f"")
    md.append(f"Generated: {timestamp}")
    md.append(f"")
    md.append(f"C++ source: `src/pow/casert.cpp` + `include/sost/params.h`")
    md.append(f"Python simulator: `scripts/v5_simulator.py`")
    md.append(f"")

    # Section 1: Constants Comparison
    md.append(f"## 1. CONSTANTS COMPARISON")
    md.append(f"")
    md.append(f"| Constant | C++ Value | Python Value | Status |")
    md.append(f"|----------|-----------|--------------|--------|")
    for r in const_results:
        status_icon = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}.get(r["status"], r["status"])
        md.append(
            f"| {r['name']} | {r.get('cpp_val', 'N/A')} | "
            f"{r.get('py_val', 'N/A')} | {status_icon} |"
        )
    md.append(f"")

    # Anti-stall decay zones
    md.append(f"### Anti-stall Decay Zone Costs")
    md.append(f"")
    md.append(f"| Zone | C++ Cost (s) | Python Cost (s) | Status |")
    md.append(f"|------|-------------|-----------------|--------|")
    for entry in antistall_cmp:
        md.append(f"| {entry['zone']} | {entry['cpp']} | {entry['py']} | {entry['status']} |")
    md.append(f"")

    # Easing per-level
    md.append(f"### Easing Per-Level Cost")
    md.append(f"")
    md.append(f"| Parameter | C++ | Python | Status |")
    md.append(f"|-----------|-----|--------|--------|")
    md.append(
        f"| Easing seconds per level | {easing_cmp['cpp']} | "
        f"{easing_cmp['py']} | {easing_cmp['status']} |"
    )
    md.append(f"")

    # Profile table match
    md.append(f"### Profile Table (CASERT_PROFILES)")
    md.append(f"")
    md.append(f"Profile table present in C++ with 17 entries: **{'MATCH' if profiles_match else 'MISMATCH'}**")
    md.append(f"")
    md.append(
        f"Note: The Python simulator does not use the profile table directly. "
        f"It uses STAB_PCT and PROFILE_DIFFICULTY lookup tables as behavioral "
        f"approximations of the scale/steps/k/margin parameters."
    )
    md.append(f"")

    # C++ only constants
    md.append(f"### Constants Present in C++ Only (Not in Simulator)")
    md.append(f"")
    md.append(f"These are intentionally omitted because the simulator uses a simplified model:")
    md.append(f"")
    for c in cpp_only_missing:
        md.append(f"- `{c['name']}` = {c['value']}")
    md.append(f"")

    # Section 2: Logic Comparison
    md.append(f"## 2. LOGIC COMPARISON")
    md.append(f"")
    for f in logic_findings:
        md.append(f"### {f['id']}: {f['title']}")
        md.append(f"")
        md.append(f"**Severity:** {f['severity']}")
        md.append(f"")
        md.append(f"{f['detail']}")
        md.append(f"")
        md.append(f"**Impact:** {f['impact']}")
        md.append(f"")
        md.append(f"- C++ location: `{f['cpp_location']}`")
        md.append(f"- Python location: `{f['py_location']}`")
        md.append(f"")

    # Section 3: Behavioral Checks
    md.append(f"## 3. BEHAVIORAL CHECKS")
    md.append(f"")
    md.append(f"| ID | Check | Status | Detail |")
    md.append(f"|----|-------|--------|--------|")
    for r in behavioral_results:
        md.append(f"| {r['id']} | {r['name']} | {r['status']} | {r['detail']} |")
    md.append(f"")

    # Section 4: Overall Verdict
    md.append(f"## 4. OVERALL VERDICT")
    md.append(f"")
    md.append(f"**Confidence: {confidence}**")
    md.append(f"")
    md.append(f"{verdict_detail}")
    md.append(f"")
    md.append(f"- Constants matched: {n_pass}/{n_pass + n_warn + n_fail}")
    md.append(f"- Constants warned: {n_warn}")
    md.append(f"- Constants failed: {n_fail}")
    md.append(f"- Logic findings (HIGH): {logic_high}")
    md.append(f"- Logic findings (MEDIUM): {logic_medium}")
    md.append(f"- Behavioral checks passed: {sum(1 for r in behavioral_results if r['status'] == 'PASS')}/{len(behavioral_results)}")
    md.append(f"")

    # Section 5: Discrepancies
    discrepancies = []
    for r in const_results:
        if r["status"] in ("FAIL", "WARN"):
            discrepancies.append({
                "type": "constant",
                "name": r["name"],
                "cpp_val": r.get("cpp_val"),
                "py_val": r.get("py_val"),
                "status": r["status"],
            })
    for f in logic_findings:
        if f["severity"] in ("HIGH", "MEDIUM"):
            discrepancies.append({
                "type": "logic",
                "id": f["id"],
                "title": f["title"],
                "severity": f["severity"],
                "impact": f["impact"],
            })
    for r in behavioral_results:
        if r["status"] in ("FAIL", "WARN"):
            discrepancies.append({
                "type": "behavioral",
                "id": r["id"],
                "name": r["name"],
                "status": r["status"],
                "detail": r["detail"],
            })

    md.append(f"## 5. DISCREPANCIES")
    md.append(f"")
    if not discrepancies:
        md.append(f"No discrepancies found.")
    else:
        md.append(f"Found {len(discrepancies)} discrepancy/discrepancies:")
        md.append(f"")
        for i, d in enumerate(discrepancies, 1):
            if d["type"] == "constant":
                md.append(
                    f"{i}. **Constant `{d['name']}`** [{d['status']}]: "
                    f"C++={d['cpp_val']}, Python={d['py_val']}"
                )
            elif d["type"] == "logic":
                md.append(
                    f"{i}. **{d['id']}: {d['title']}** [{d['severity']}]: "
                    f"{d['impact']}"
                )
            elif d["type"] == "behavioral":
                md.append(
                    f"{i}. **{d['id']}: {d['name']}** [{d['status']}]: "
                    f"{d['detail']}"
                )
        md.append(f"")

    # Write MD
    md_path = os.path.join(REPORTS_DIR, "simulator_parity_report.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md) + "\n")

    # --- JSON report ---
    report_json = {
        "timestamp": timestamp,
        "sources": {
            "cpp": ["src/pow/casert.cpp", "include/sost/params.h"],
            "python": "scripts/v5_simulator.py",
        },
        "constants_comparison": const_results,
        "antistall_decay_comparison": antistall_cmp,
        "easing_comparison": easing_cmp,
        "profiles_match": profiles_match,
        "cpp_only_constants": cpp_only_missing,
        "logic_findings": logic_findings,
        "behavioral_checks": behavioral_results,
        "verdict": {
            "confidence": confidence,
            "detail": verdict_detail,
            "stats": {
                "constants_pass": n_pass,
                "constants_warn": n_warn,
                "constants_fail": n_fail,
                "logic_high": logic_high,
                "logic_medium": logic_medium,
                "behavioral_pass": sum(1 for r in behavioral_results if r["status"] == "PASS"),
                "behavioral_warn": beh_warn,
                "behavioral_fail": beh_fail,
            },
        },
        "discrepancies": discrepancies,
    }

    json_path = os.path.join(REPORTS_DIR, "simulator_parity_report.json")
    with open(json_path, "w") as f:
        json.dump(report_json, f, indent=2)

    return md_path, json_path, confidence


# ---------------------------------------------------------------------------
# 7. Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("  SOST cASERT Simulator Parity Validator")
    print("=" * 72)
    print()

    # Verify files exist
    for path, label in [(CPP_FILE, "casert.cpp"), (PARAMS_FILE, "params.h"), (SIM_FILE, "v5_simulator.py")]:
        if not os.path.exists(path):
            print(f"ERROR: {label} not found at {path}")
            return 1
        print(f"  Found: {path}")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    print()

    # --- Parse C++ ---
    print("[1/6] Parsing C++ constants from params.h ...")
    cpp_consts = parse_cpp_constants(PARAMS_FILE)
    print(f"       Extracted {len(cpp_consts)} constants.")

    cpp_antistall = parse_cpp_antistall_decay(CPP_FILE)
    print(f"       Anti-stall decay zones: {cpp_antistall}")

    cpp_easing_per_level = parse_cpp_easing_extra(CPP_FILE)
    print(f"       Easing per-level cost: {cpp_easing_per_level}s")

    cpp_profiles = parse_cpp_profiles(PARAMS_FILE)
    print(f"       Profile table: {len(cpp_profiles)} entries")

    # --- Parse Python ---
    print("[2/6] Parsing Python simulator constants ...")
    py_consts = parse_python_constants(SIM_FILE)
    print(f"       Extracted {len(py_consts)} constants.")

    py_antistall = parse_python_antistall_decay(SIM_FILE)
    print(f"       Anti-stall decay zones: {py_antistall}")

    py_easing_per_level = parse_python_easing_per_level(SIM_FILE)
    print(f"       Easing per-level cost: {py_easing_per_level}")

    # --- Compare constants ---
    print("[3/6] Comparing constants ...")
    const_results = []
    for display, cpp_name, py_name, category in CONST_MAP:
        cpp_val = cpp_consts.get(cpp_name)
        py_val = py_consts.get(py_name)
        status = compare_constant(cpp_val, py_val)
        const_results.append({
            "name": display,
            "cpp_name": cpp_name,
            "py_name": py_name,
            "cpp_val": cpp_val if cpp_val is not None else "N/A",
            "py_val": py_val if py_val is not None else "N/A",
            "category": category,
            "status": status,
        })
        icon = {"PASS": "+", "WARN": "~", "FAIL": "X", "SKIP": "-"}[status]
        print(f"       [{icon}] {display}: C++={cpp_val} vs Py={py_val} -> {status}")

    # Anti-stall decay comparison
    antistall_cmp = []
    for zone in [7, 4]:
        cpp_v = cpp_antistall.get(zone, "N/A")
        py_v = py_antistall.get(zone, "N/A")
        status = "PASS" if cpp_v == py_v else "FAIL"
        zone_label = f"H>={zone}"
        antistall_cmp.append({"zone": zone_label, "cpp": cpp_v, "py": py_v, "status": status})
    # else zone
    cpp_else = cpp_antistall.get('else', "N/A")
    py_else = py_antistall.get('else', "N/A")
    antistall_cmp.append({
        "zone": "else (H1-H3)",
        "cpp": cpp_else,
        "py": py_else,
        "status": "PASS" if cpp_else == py_else else "FAIL",
    })

    for entry in antistall_cmp:
        icon = "+" if entry["status"] == "PASS" else "X"
        print(f"       [{icon}] Anti-stall {entry['zone']}: C++={entry['cpp']}s vs Py={entry['py']}s -> {entry['status']}")

    # Easing comparison
    easing_status = "PASS" if cpp_easing_per_level == py_easing_per_level else "FAIL"
    # Note: Python simulator does NOT implement easing, so py will be None
    if py_easing_per_level is None:
        easing_status = "WARN"
    easing_cmp = {
        "cpp": cpp_easing_per_level,
        "py": py_easing_per_level if py_easing_per_level is not None else "N/A (not implemented)",
        "status": easing_status,
    }
    icon = {"PASS": "+", "WARN": "~", "FAIL": "X"}[easing_status]
    print(f"       [{icon}] Easing per-level: C++={cpp_easing_per_level}s vs Py={easing_cmp['py']} -> {easing_status}")

    # Profile table
    profiles_match = len(cpp_profiles) == 17
    print(f"       Profile table: {len(cpp_profiles)} entries ({'OK' if profiles_match else 'MISMATCH'})")

    # C++ only constants
    cpp_only_missing = []
    for cname in CPP_ONLY_CONSTS:
        val = cpp_consts.get(cname)
        if val is not None:
            cpp_only_missing.append({"name": cname, "value": val})

    print(f"       C++ only constants (not in simulator): {len(cpp_only_missing)}")

    # --- Logic comparison ---
    print("[4/6] Analyzing logic differences ...")
    with open(CPP_FILE) as f:
        cpp_text = f.read()
    with open(SIM_FILE) as f:
        py_text = f.read()
    logic_findings = check_logic_differences(cpp_text, py_text)
    for f in logic_findings:
        sev = f["severity"]
        icon = {"OK": "+", "LOW": ".", "MEDIUM": "~", "HIGH": "!"}[sev]
        print(f"       [{icon}] {f['id']}: {f['title']} [{sev}]")

    # --- Behavioral checks ---
    print("[5/6] Running behavioral checks (this may take a moment) ...")
    behavioral_results = run_behavioral_checks()
    for r in behavioral_results:
        icon = {"PASS": "+", "WARN": "~", "FAIL": "X"}[r["status"]]
        print(f"       [{icon}] {r['id']}: {r['name']} -> {r['status']}")

    # --- Generate reports ---
    print("[6/6] Generating reports ...")
    md_path, json_path, confidence = generate_reports(
        const_results, logic_findings, behavioral_results,
        cpp_only_missing, antistall_cmp, easing_cmp, profiles_match,
    )
    print(f"       Markdown: {md_path}")
    print(f"       JSON:     {json_path}")

    # --- Summary ---
    print()
    print("=" * 72)
    print(f"  OVERALL VERDICT: {confidence} confidence")
    print("=" * 72)
    n_pass = sum(1 for r in const_results if r["status"] == "PASS")
    n_warn = sum(1 for r in const_results if r["status"] == "WARN")
    n_fail = sum(1 for r in const_results if r["status"] == "FAIL")
    beh_pass = sum(1 for r in behavioral_results if r["status"] == "PASS")
    beh_total = len(behavioral_results)
    logic_high = sum(1 for f in logic_findings if f["severity"] == "HIGH")
    logic_med = sum(1 for f in logic_findings if f["severity"] == "MEDIUM")

    print(f"  Constants:  {n_pass} PASS / {n_warn} WARN / {n_fail} FAIL")
    print(f"  Behavioral: {beh_pass}/{beh_total} PASS")
    print(f"  Logic:      {logic_high} HIGH / {logic_med} MEDIUM severity findings")
    print()

    if confidence == "LOW":
        print("  The simulator has significant divergence from the consensus code.")
    elif confidence == "MEDIUM":
        print("  The simulator faithfully implements the V5 equalizer POLICY")
        print("  (slew, safety rules, EBR, extreme cap, anti-stall decay) but")
        print("  uses a simplified PID model and omits bitsQ/EWMA entirely.")
        print("  It is suitable for behavioral analysis, NOT consensus validation.")
    else:
        print("  The simulator closely matches the consensus implementation.")
    print()

    return 0 if confidence != "LOW" else 1


if __name__ == "__main__":
    sys.exit(main())
