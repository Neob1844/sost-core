# SOST Core — ConvergenceX PoW Engine

**Status:** Pre-genesis (target: 2026-02-28 00:00:00 UTC)
**Version:** 0.1.0
**Tests:** 92/92 passing
**Cross-verified:** C++ and Python bit-for-bit determinism confirmed

## Build

Requirements: g++ (C++17), OpenSSL (libcrypto).
```
chmod +x build.sh
./build.sh
```

## Binaries
```
./build/sost-miner --blocks 5 --profile dev
./build/sost-node --blocks 10 --profile dev --port 8332
./build/sost-wallet generate
```

## License

Proprietary. All rights reserved.
