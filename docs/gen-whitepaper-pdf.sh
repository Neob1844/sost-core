#!/bin/bash
# Regenerate website/whitepaper.pdf from the current website/sost-whitepaper.html.
# Uses the page's @media print rules. Requires: WeasyPrint (pip install --user weasyprint).
# The former pandoc build of docs/convergencex_whitepaper.txt into
# docs/convergencex_whitepaper.pdf is retired: that PDF is no longer published.
set -e
cd "$(dirname "$0")/.."
weasyprint website/sost-whitepaper.html website/whitepaper.pdf
echo "Generated: website/whitepaper.pdf"
