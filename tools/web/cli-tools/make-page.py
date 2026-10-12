#!/usr/bin/env python3
"""Assemble the single-file CLI wallet tools page (hosted copy == offline copy, byte for byte).
CSP pins both inline scripts by SHA-256 and forbids every network connection."""
import base64, hashlib, os, sys
here = os.path.dirname(os.path.abspath(__file__))
version = sys.argv[1]
out_dir = sys.argv[2]                                    # website/
bundle = open(os.path.join(here, 'dist/sost-cli-wallet.bundle.js')).read()
app = open(os.path.join(here, 'app.js')).read()
for s in (bundle, app):
    assert '</script' not in s.lower()
h = lambda s: "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
csp = ("default-src 'none'; script-src " + h(bundle) + " " + h(app) + "; style-src 'unsafe-inline'; img-src data:; "
       "connect-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; "
       "manifest-src 'none'; form-action 'none'; base-uri 'none'")
page = open(os.path.join(here, 'page.template.html')).read()
page = (page.replace('{{CSP}}', csp).replace('{{VERSION}}', version)
            .replace('{{SELFHASH_NOTE}}', 'published next to the file as sost-cli-tools-offline-' + version + '.html.sha256')
            .replace('{{BUNDLE}}', bundle).replace('{{APP}}', app))
os.makedirs(os.path.join(out_dir, 'downloads'), exist_ok=True)
open(os.path.join(out_dir, 'cli-tools.html'), 'w').write(page)
off = os.path.join(out_dir, 'downloads', 'sost-cli-tools-offline-' + version + '.html')
open(off, 'w').write(page)
d = hashlib.sha256(page.encode()).hexdigest()
open(off + '.sha256', 'w').write(d + '  sost-cli-tools-offline-' + version + '.html\n')
print(d)
