# SOST Core — ConvergenceX PoW Engine

**Status:** Pre-genesis (target: 2026-02-28 00:00:00 UTC)
**Version:** 0.1.0
**Tests:** 92/92 passing
**Cross-verified:** C++ and Python bit-for-bit determinism confirmed (mainnet params)

## What Is This

C++ implementation of the ConvergenceX Proof-of-Work consensus engine for the SOST protocol. This is the core library that powers block mining, validation, and chain management.

ConvergenceX replaces brute-force hash guessing with a mandatory sequential convergence process: 4 GB RAM, 100,000 rounds of integer-only gradient descent, memory-hard scratchpad reads, and a stability basin verification certificate.

## Build

Requirements: g++ (C++17), OpenSSL (libcrypto).
```
chmod +x build.sh
./build.sh
```

Compiles everything, links 3 binaries, runs all 92 tests.

## Binaries
```
./build/sost-miner --blocks 5 --profile dev
./build/sost-node --blocks 10 --profile dev --port 8332
./build/sost-wallet generate
```

## Cross-Verification
```
./build/cross_mainnet
```

Produces deterministic hex values matching the Python reference bit-for-bit on mainnet parameters (4GB scratchpad, 100k rounds).

## Emission Model — Feigenbaum Constants

The emission schedule is governed by the two Feigenbaum universal constants:

- **Epoch length:** alpha (2.502907875 years) = 131,553 blocks per epoch
- **Max supply:** delta-derived = 4,669,201.609 SOST (asymptotic hard cap)
- **Decay factor:** q = exp(-1/4) = 0.7788007831 per epoch (~9.03% annual)
- **Initial reward:** 7.85100863 SOST per block
- **95% mined** in ~12 epochs (~30 years), smooth decay with no halvings
- **Coinbase split:** 50% miner, 25% gold vault (automatic XAUT/PAXG), 25% PoPC pool
- **Arithmetic:** 100% integer fixed-point (zero floating-point in consensus)

## Consensus Parameters

| Parameter | Value |
|---|---|
| Genesis | 2026-02-28 00:00:00 UTC |
| Block target | 600s (10 min) |
| Epoch | 131,553 blocks (~2.5 years) |
| Max supply | 4,669,201.609 SOST (hard cap) |
| RAM | 4,096 MB scratchpad |
| Rounds | 100,000 sequential per attempt |
| Difficulty | ASERT Q16.16, 24h half-life |
| CASERT | 4 adaptive modes, 64-interval window |

## License

Proprietary. All rights reserved. Not for public distribution.
