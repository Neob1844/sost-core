#!/usr/bin/env python3
"""Regression test: the published whitepaper must not present retired off-chain
research modules as part of SOST.

Checks
  1. website/whitepaper.pdf (the published PDF): text extracted with PyMuPDF or
     pdftotext must contain none of the retired-module terms (case-insensitive).
  2. docs/convergencex_whitepaper.txt (the specification text): the same terms may
     only appear inside a clearly historical section, i.e. when the line itself or
     the nearest preceding section heading is marked Historical / Removed.

Usage:  python3 tests/whitepaper_pdf_content_test.py [repo_root]
Exit:   0 = pass, 1 = fail, 77 = skipped (no PDF text extractor available).
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..'))
PDF = os.path.join(ROOT, 'website', 'whitepaper.pdf')
TXT = os.path.join(ROOT, 'docs', 'convergencex_whitepaper.txt')

TERMS = [
    ('GeaSpirit', re.compile(r'gea\s*spirit', re.I)),
    ('Materials Engine', re.compile(r'materials\s+engine', re.I)),
    ('Materials Discovery Engine', re.compile(r'materials\s+discovery\s+engine', re.I)),
    ('Mineral Intelligence Platform', re.compile(r'mineral\s+intelligence\s+platform', re.I)),
    ('SOST AI', re.compile(r'\bSOST\s+AI\b(\s+Engine)?', re.I)),
]
HISTORICAL = re.compile(r'historical|removed|retired|non-normative', re.I)
HEADING = re.compile(r'^(#{1,6}\s|\d+(\.\d+)*\.?\s+[A-Z]|Appendix\s|[A-Z][A-Z \-—]{8,}$)')


def pdf_text(path):
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            return '\n'.join(page.get_text() for page in doc), 'PyMuPDF'
    except ImportError:
        pass
    if shutil.which('pdftotext'):
        out = subprocess.run(['pdftotext', '-layout', path, '-'], check=True, capture_output=True, text=True)
        return out.stdout, 'pdftotext'
    return None, None


def hits(text):
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in TERMS:
            if rx.search(line):
                found.append((lineno, name, line.strip()))
    return found


def main():
    failures = 0

    if not os.path.isfile(PDF):
        print(f'[FAIL] missing {PDF}')
        return 1
    text, tool = pdf_text(PDF)
    if text is None:
        print('[SKIP] neither PyMuPDF (python3 -m pip install pymupdf) nor pdftotext (poppler-utils) is installed')
        return 77
    # Joined text as well, to catch terms split across a line break in the PDF layout.
    joined = re.sub(r'\s+', ' ', text)
    pdf_hits = hits(text) + [(0, n, '(across line break)') for n, rx in TERMS if rx.search(joined) and not rx.search(text)]
    if pdf_hits:
        failures += len(pdf_hits)
        for lineno, name, line in pdf_hits:
            print(f'[FAIL] whitepaper.pdf: "{name}" — {line[:120]}')
    else:
        print(f'[PASS] website/whitepaper.pdf ({tool}, {len(text)} chars): no retired-module terms')

    with open(TXT, encoding='utf-8') as fh:
        lines = fh.read().splitlines()
    heading = ''
    txt_bad = 0
    txt_hist = 0
    for lineno, line in enumerate(lines, 1):
        if HEADING.match(line):
            heading = line
        for name, rx in TERMS:
            if rx.search(line):
                if HISTORICAL.search(line) or HISTORICAL.search(heading):
                    txt_hist += 1
                else:
                    txt_bad += 1
                    print(f'[FAIL] convergencex_whitepaper.txt:{lineno}: "{name}" outside a historical section — {line.strip()[:120]}')
    failures += txt_bad
    if not txt_bad:
        print(f'[PASS] docs/convergencex_whitepaper.txt: no retired-module terms outside historical notes ({txt_hist} inside)')

    print('RESULT:', 'PASS' if failures == 0 else f'FAIL ({failures})')
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
