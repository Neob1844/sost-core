#!/usr/bin/env bash
# Build helper for the vendored libwally-core submodule.
#
# Builds libwally as a static library INSIDE the submodule directory,
# at the exact paths SOST's CMake probe looks for:
#
#   vendor/libwally-core/include/wally_*.h
#   vendor/libwally-core/src/.libs/libwallycore.a
#
# After a successful run, the SOST CMake configure step with
#   -DSOST_BTC_HTLC_SIGNING=ON
# discovers libwally via its built-in manual probe (no extra
# -DWALLY_INCLUDE_DIR / -DWALLY_LIBRARY arguments needed).
#
# What this script does NOT do:
#   - install libwally system-wide
#   - enable any SOST build flag automatically
#   - touch the SOST consensus gate (ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT)
#   - enable real BTC signing (src/atomic_swap_btc_signing.cpp stays
#     a stub returning disabled_result() until Phase C wires it)
#
# Required tooling (the script aborts loudly if any is missing):
#   - autoreconf  (autoconf >= 2.69)
#   - libtoolize  (libtool — Debian/Ubuntu package: libtool)
#   - make
#   - gcc / clang
#   - python3     (libwally's test generator)
#
# Usage:
#   tools/build_libwally.sh          # build static library
#   tools/build_libwally.sh --clean  # wipe build artefacts first

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/vendor/libwally-core"

if [[ ! -e "${VENDOR_DIR}/.git" ]]; then
    echo "FATAL: vendor/libwally-core submodule not initialised." >&2
    echo "Run: git submodule update --init --recursive" >&2
    exit 2
fi

# Hard tool check — fail fast and loud if anything is missing.
need_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "FATAL: required tool '$1' not found on PATH. Install it and retry." >&2
        echo "  Debian/Ubuntu: sudo apt-get install -y $2" >&2
        exit 3
    fi
}
need_tool autoreconf  autoconf
need_tool libtoolize  libtool
need_tool make        build-essential
need_tool gcc         build-essential
need_tool python3     python3

if [[ "${1:-}" == "--clean" ]]; then
    echo "wiping libwally build artefacts ..."
    ( cd "${VENDOR_DIR}" && make clean >/dev/null 2>&1 || true )
    rm -f  "${VENDOR_DIR}/configure"
    rm -rf "${VENDOR_DIR}/autom4te.cache"
fi

cd "${VENDOR_DIR}"

# Bootstrap via libwally's documented autogen script.
if [[ ! -f configure ]]; then
    echo "running autogen.sh ..."
    ./tools/autogen.sh
fi

# Configure with the minimum surface required by SOST:
#   - static library only (no shared / no install ceremony needed)
#   - no language bindings (no python wheel, no nodejs)
#   - no elements-specific extras (we only need core BTC primitives)
if [[ ! -f Makefile ]]; then
    echo "configuring ..."
    ./configure \
        --enable-static \
        --disable-shared \
        --disable-elements \
        --disable-swig-python \
        --disable-swig-java >/dev/null
fi

echo "compiling (this takes ~30 s on a modest machine) ..."
make -j"$(nproc)" >/dev/null

# Layout check: the artefacts SOST's CMake probe will look for.
if [[ ! -f "src/.libs/libwallycore.a" ]]; then
    echo "FATAL: src/.libs/libwallycore.a was not produced. Check the make output." >&2
    exit 4
fi
if [[ ! -f "include/wally_bip32.h" ]]; then
    echo "FATAL: include/wally_bip32.h header is missing. The build is incomplete." >&2
    exit 5
fi

echo
echo "libwally-core release_1.5.3 built successfully."
echo "  include dir : ${VENDOR_DIR}/include"
echo "  static lib  : ${VENDOR_DIR}/src/.libs/libwallycore.a"
echo
echo "Next: re-configure SOST with the signing flag enabled."
echo "      The CMake manual probe finds the artefacts automatically."
echo
echo "  cmake -S . -B build-atomic-audit \\"
echo "      -DCMAKE_BUILD_TYPE=Release \\"
echo "      -DSOST_ENABLE_PHASE2_SBPOW=ON \\"
echo "      -DSOST_BTC_HTLC_SIGNING=ON"
echo
echo "Reminder: SOST_BTC_HTLC_SIGNING=ON only enables the CMake link."
echo "          No actual BTC signing happens until Phase C wires the"
echo "          wally_* calls into src/atomic_swap_btc_signing.cpp."
echo "          The consensus gate ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT"
echo "          stays at INT64_MAX regardless of this flag."
