#!/bin/bash
# Regenerate website/whitepaper.pdf from the current website/sost-whitepaper.html.
# Uses the page's @media print rules. Requires: WeasyPrint (pip install --user weasyprint).
# The former pandoc build of docs/convergencex_whitepaper.txt into
# docs/convergencex_whitepaper.pdf is retired: that PDF is no longer published, and this
# script has no other input than the current HTML.
# After building, tests/whitepaper_pdf_content_test.py is run; if it fails, the previous
# website/whitepaper.pdf is restored and the script exits non-zero.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC=website/sost-whitepaper.html
OUT=website/whitepaper.pdf
[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
weasyprint "$SRC" "$tmp/whitepaper.pdf"
[ -f "$OUT" ] && cp -p "$OUT" "$tmp/previous.pdf"
mv "$tmp/whitepaper.pdf" "$OUT"
set +e
python3 tests/whitepaper_pdf_content_test.py
rc=$?
set -e
if [ "$rc" -ne 0 ] && [ "$rc" -ne 77 ]; then
  if [ -f "$tmp/previous.pdf" ]; then cp -p "$tmp/previous.pdf" "$OUT"; fi
  echo "content check FAILED: $OUT restored to its previous version" >&2
  exit 1
fi
echo "Generated: $OUT"
