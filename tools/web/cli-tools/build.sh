#!/bin/bash
# Reproducible build of the CLI wallet tools crypto bundle (pinned by package-lock.json; npm ci verifies integrity).
set -euo pipefail
cd "$(dirname "$0")"
npm ci --no-audit --no-fund >/dev/null
./node_modules/.bin/esbuild entry-browser.mjs --bundle --format=iife --minify --target=es2020 \
  --legal-comments=inline --outfile=dist/sost-cli-wallet.bundle.js
./node_modules/.bin/esbuild sost-cli-wallet-core.mjs --bundle --format=esm --platform=node --outfile=dist/core.node.mjs
sha256sum dist/sost-cli-wallet.bundle.js
