#!/bin/bash
# Regenerate whitepaper PDF from source
# Requires: sudo apt install pandoc texlive-xetex fonts-dejavu
set -e
cd "$(dirname "$0")"
pandoc convergencex_whitepaper.txt -o convergencex_whitepaper.pdf \
  --pdf-engine=xelatex \
  -V geometry:margin=1in \
  -V fontsize=11pt \
  -V mainfont="DejaVu Sans" \
  -V monofont="DejaVu Sans Mono" \
  --wrap=auto
cp convergencex_whitepaper.pdf ../website/whitepaper.pdf
echo "Generated: docs/convergencex_whitepaper.pdf + website/whitepaper.pdf"
