#!/usr/bin/env python3
"""
nginx-patch.py — idempotent rewrite of the SOST nginx site to add an
upstream block with keepalive AND switch every proxy_pass that targets
http://127.0.0.1:18232 to use that upstream over HTTP/1.1 with
Connection-header pooling.

Why we do not just `cp` a static file:
  the operator may have customised the site (TLS, hostnames, address-
  book proxies, geo-blocks). We surgically add what is missing instead
  of overwriting their config.

Usage:
    python3 nginx-patch.py <path-to-nginx-site>

Exit codes:
    0 — file already had the required directives, OR file was patched
        cleanly and the result passes `nginx -t`.
    1 — the file did not look like a SOST nginx site we know how to
        patch; left untouched.
    2 — patch produced a file that fails `nginx -t`; original is
        restored from the .pre-keepalive backup.
"""
import os
import re
import shutil
import subprocess
import sys
import time

UPSTREAM_BLOCK = """\
# === SOST: connection pool to local sost-node RPC ===========================
# Added by scripts/vps-resilience/nginx-patch.py. Reusing the keepalive pool
# avoids the TIME-WAIT loopback saturation that bricks sost-node every ~24 h
# under explorer + miner polling. Safe to keep across redeploys.
upstream sost_node {
    server 127.0.0.1:18232;
    keepalive 32;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}
# ============================================================================

"""

PROXY_HEADERS = """\
        proxy_http_version 1.1;
        proxy_set_header Connection "";
"""

def main(path: str) -> int:
    if not os.path.isfile(path):
        sys.stderr.write(f"file not found: {path}\n")
        return 1

    with open(path) as f:
        src = f.read()

    if "127.0.0.1:18232" not in src:
        sys.stderr.write(
            "this nginx site does not reference 127.0.0.1:18232 anywhere; "
            "nothing to patch.\n")
        return 1

    needs_upstream = "upstream sost_node" not in src
    needs_pool = ("proxy_pass http://127.0.0.1:18232" in src or
                  "proxy_pass http://127.0.0.1:18232/" in src)

    if not needs_upstream and not needs_pool:
        sys.stderr.write("already patched; nothing to do.\n")
        return 0

    backup = f"{path}.pre-keepalive.{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    sys.stderr.write(f"backup: {backup}\n")

    out = src

    if needs_upstream:
        # Drop the upstream block immediately before the first `server {`
        # — that's the canonical placement.
        m = re.search(r"^\s*server\s*\{", out, flags=re.M)
        if not m:
            sys.stderr.write("could not find a server { block to anchor on.\n")
            return 1
        out = out[:m.start()] + UPSTREAM_BLOCK + out[m.start():]

    # Rewrite proxy_pass lines and inject HTTP/1.1 + Connection "" headers
    # for every location block that proxies to 127.0.0.1:18232.
    def patch_location(loc: str) -> str:
        if "proxy_pass http://127.0.0.1:18232" not in loc:
            return loc
        loc = re.sub(
            r"proxy_pass\s+http://127\.0\.0\.1:18232/?\s*;",
            "proxy_pass http://sost_node;",
            loc,
        )
        if "proxy_http_version 1.1" not in loc:
            # Insert headers right after the proxy_pass line.
            loc = re.sub(
                r"(proxy_pass\s+http://sost_node;\s*\n)",
                r"\1" + PROXY_HEADERS,
                loc, count=1,
            )
        return loc

    # Walk top-level location { ... } blocks. Simple brace counter is enough
    # for the SOST site (no nested location { }).
    pieces = []
    i = 0
    while i < len(out):
        m = re.search(r"location\s+[^{]+\{", out[i:])
        if not m:
            pieces.append(out[i:])
            break
        loc_start = i + m.start()
        pieces.append(out[i:loc_start])
        # Find matching close brace.
        depth = 0
        j = i + m.end() - 1   # at the opening {
        while j < len(out):
            c = out[j]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        loc_block = out[loc_start:j]
        pieces.append(patch_location(loc_block))
        i = j

    out = "".join(pieces)

    if out == src:
        sys.stderr.write("nothing changed after rewrite; aborting.\n")
        os.remove(backup)
        return 0

    with open(path, "w") as f:
        f.write(out)

    # Validate the resulting config.
    try:
        r = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write("nginx -t FAILED:\n" + r.stderr + "\n")
            sys.stderr.write(f"restoring backup {backup}\n")
            shutil.copy2(backup, path)
            return 2
        sys.stderr.write("nginx -t passed.\n")
    except FileNotFoundError:
        sys.stderr.write("nginx binary not found in PATH; skipped validation.\n")

    sys.stderr.write("nginx site patched.\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stderr.write("usage: nginx-patch.py <path-to-nginx-site>\n")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
