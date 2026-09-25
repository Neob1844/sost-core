#!/usr/bin/env python3
"""Independent reference model of SOST block subsidy / cumulative emission.
Reimplemented from the spec (NOT copied from the C++) for differential testing
against src/subsidy.cpp. Python big-ints reproduce the C++ __int128 arithmetic
exactly. Phase C of the SOST Security Gauntlet.  Usage: --batch reads heights
from stdin (one per line) and prints '<h> <subsidy> <cumulative>'."""
import sys
BLOCKS_PER_EPOCH = 131553
Q_DEN = 10_000_000_000_000_000
Q_NUM = 7_788_007_830_714_049
R0_STOCKS = 785_100_863
SUPPLY_CAP = 466_920_160_910_299
U64_MAX = (1 << 64) - 1
I64_MAX = (1 << 63) - 1

def mul_q(a, b):
    prod = (a * b) // Q_DEN
    return 0 if prod < 0 else (U64_MAX if prod > U64_MAX else prod)

def pow_q(exp):
    result = Q_DEN; base = Q_NUM
    while exp > 0:
        if exp & 1: result = mul_q(result, base)
        exp >>= 1
        if exp: base = mul_q(base, base)
        else: break
    return result

def cumulative_emission(height):
    if height < 0: return 0
    total = 0; h = 0
    while h <= height:
        epoch = h // BLOCKS_PER_EPOCH
        sub = (R0_STOCKS * pow_q(epoch)) // Q_DEN
        if sub < 0: sub = 0
        epoch_end = (epoch + 1) * BLOCKS_PER_EPOCH - 1
        blocks = min(epoch_end, height) - h + 1
        total += sub * blocks
        if total >= SUPPLY_CAP: return SUPPLY_CAP
        h += blocks
    return total

def subsidy(height):
    if height < 0: return 0
    r = (R0_STOCKS * pow_q(height // BLOCKS_PER_EPOCH)) // Q_DEN
    if r < 0: return 0
    if r > I64_MAX: r = I64_MAX
    emitted_before = cumulative_emission(height - 1)
    if emitted_before >= SUPPLY_CAP: return 0
    remaining = SUPPLY_CAP - emitted_before
    return remaining if r > remaining else r

if __name__ == "__main__":
    if "--batch" in sys.argv:
        out = []
        for line in sys.stdin:
            line = line.strip()
            if line:
                h = int(line); out.append(f"{h} {subsidy(h)} {cumulative_emission(h)}")
        sys.stdout.write("\n".join(out) + "\n")
    else:
        for h in map(int, sys.argv[1:]):
            print(f"{h} {subsidy(h)} {cumulative_emission(h)}")
