#!/usr/bin/env bash
#
# install-sost.sh — bootstrap a SOST node + miner build from source.
#
# What it does:
#   1. Verifies it is running on a Debian/Ubuntu-family system.
#   2. Installs build dependencies (build-essential, cmake, git, libssl,
#      libsecp256k1) using apt — and only if they are missing.
#   3. Clones https://github.com/Neob1844/sost-core (or runs git pull
#      if the repository already exists) into ~/sost-core.
#   4. Builds the binaries in ~/sost-core/build using cmake + make.
#   5. Prints next steps. Does NOT create a wallet, does NOT start the
#      node, does NOT start the miner. The user must do that with their
#      own SOST address.
#
# Safety:
#   - This script never asks for, reads, or writes private keys, seed
#     phrases or wallet files.
#   - This script never uploads anything.
#   - This script is idempotent: re-running it after success just
#     pulls latest and rebuilds.
#   - This script never runs `rm -rf` on system paths. The only delete
#     it can do is `rm -f install-sost.sh` at the very end if invoked
#     through curl|bash, and only the script that downloaded itself.
#
# Advanced users should inspect this file before running it. To do so:
#
#   curl -fsSL https://sostcore.com/install-sost.sh -o install-sost.sh
#   less install-sost.sh
#   bash install-sost.sh

set -euo pipefail

REPO_URL="${SOST_REPO_URL:-https://github.com/Neob1844/sost-core.git}"
INSTALL_DIR="${SOST_INSTALL_DIR:-$HOME/sost-core}"
BUILD_TYPE="${SOST_BUILD_TYPE:-Release}"

C_RED=$'\033[0;31m'
C_GRN=$'\033[0;32m'
C_YEL=$'\033[0;33m'
C_DIM=$'\033[0;90m'
C_BOLD=$'\033[1m'
C_OFF=$'\033[0m'

step() { printf '\n%s==> %s%s\n' "$C_BOLD" "$1" "$C_OFF"; }
info() { printf '   %s%s%s\n' "$C_DIM" "$1" "$C_OFF"; }
warn() { printf '%s   ! %s%s\n' "$C_YEL" "$1" "$C_OFF"; }
ok()   { printf '%s   ok %s%s\n' "$C_GRN" "$1" "$C_OFF"; }
die()  { printf '%s   x %s%s\n' "$C_RED" "$1" "$C_OFF" >&2; exit 1; }

# ---------------------------------------------------------------- preflight

step "preflight"
if [ "$(id -u)" -eq 0 ]; then
  warn "you are running as root. Recommended: run as a normal user with sudo when prompted."
fi

if [ ! -r /etc/os-release ]; then
  die "/etc/os-release not found — this script targets Debian/Ubuntu-family systems."
fi
. /etc/os-release
case "${ID_LIKE:-$ID}" in
  *debian*|*ubuntu*) ok "detected ${PRETTY_NAME:-$ID}";;
  *) warn "this script is tuned for Ubuntu/Debian. Detected: ${PRETTY_NAME:-$ID}. Continuing, but apt commands may fail.";;
esac

if ! command -v sudo >/dev/null 2>&1; then
  die "sudo not available. Install sudo first or run apt steps manually."
fi

# ------------------------------------------------------------ dependencies

DEPS=(build-essential cmake git pkg-config libssl-dev libsecp256k1-dev ca-certificates curl)

step "checking build dependencies"
MISSING=()
for pkg in "${DEPS[@]}"; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    MISSING+=("$pkg")
  fi
done

if [ "${#MISSING[@]}" -eq 0 ]; then
  ok "all build dependencies already installed"
else
  info "missing: ${MISSING[*]}"
  info "running: sudo apt update && sudo apt install -y ${MISSING[*]}"
  sudo apt update
  sudo apt install -y "${MISSING[@]}"
  ok "dependencies installed"
fi

# ---------------------------------------------------------------- clone / pull

step "fetching sost-core source"
if [ -d "$INSTALL_DIR/.git" ]; then
  info "repository already at $INSTALL_DIR — pulling latest"
  git -C "$INSTALL_DIR" pull --ff-only
  ok "pulled"
elif [ -e "$INSTALL_DIR" ]; then
  die "$INSTALL_DIR exists but is not a git checkout. Move it aside and re-run."
else
  info "cloning $REPO_URL into $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
  ok "cloned"
fi

# ---------------------------------------------------------------- build

step "building (cmake + make)"
mkdir -p "$INSTALL_DIR/build"
cd "$INSTALL_DIR/build"
if [ ! -f CMakeCache.txt ]; then
  cmake .. -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
fi
cmake --build . -j"$(nproc)"
ok "build complete"

# ---------------------------------------------------------------- summary

cat <<EOF

${C_BOLD}SOST source built successfully.${C_OFF}

Binaries are in:
  $INSTALL_DIR/build/

Next steps (each is a separate command you run yourself):

  ${C_GRN}1. Create a wallet${C_OFF}
     cd $INSTALL_DIR/build
     ./sost-cli newwallet
     ./sost-cli getnewaddress "mining"
     # copy the sost1... address — you'll need it for the miner.

  ${C_GRN}2. Start the node${C_OFF} (in its own terminal or systemd unit)
     cd $INSTALL_DIR/build
     ./sost-node --rpc-user YOUR_USER --rpc-pass YOUR_PASS

  ${C_GRN}3. Start the miner${C_OFF} (in another terminal)
     cd $INSTALL_DIR/build
     ./sost-miner \\
       --address sost1YOURADDRESS \\
       --rpc 127.0.0.1:18232 \\
       --rpc-user YOUR_USER --rpc-pass YOUR_PASS \\
       --blocks 999999 --profile mainnet --threads 16

Notes:
  - Try 16 or 32 threads first. ConvergenceX is memory-bandwidth bound;
    more threads is not always better and can slow you down.
  - Solo mining is high variance. You may go hours without finding a
    block. That is expected behaviour, not a bug.
  - Network status: https://sostcore.com/sost-network-status.html
  - Mining guide:   https://sostcore.com/sost-mine.html
  - Why no pools:   https://sostcore.com/sost-why-no-pools.html

This script never asked for, read, or wrote any private key, seed phrase
or wallet file. You remain in control of your keys.
EOF
