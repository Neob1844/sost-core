#!/usr/bin/env bash
# Compare the live sostcore.com web root with website/ in this repository.
# Read-only on the server. Exit 0 = in sync, 1 = drift found, 2 = error.
# Usage: deploy/web-sync/web-drift-check.sh [ssh_target] [remote_web_root]
set -euo pipefail
TARGET=${1:-root@212.132.108.244}
ROOT=${2:-/var/www/sost-website/website}
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
ssh -o ConnectTimeout=15 "$TARGET" "cd '$ROOT' && find . -type f -print0 | xargs -0 sha256sum" \
  | sed 's#  \./#\t#' > "$TMP/prod" || exit 2
(cd "$REPO/website" && git ls-files -z | xargs -0 sha256sum) | sed 's#  #\t#' > "$TMP/repo"
python3 - "$TMP/prod" "$TMP/repo" "$HERE/EXCLUDE.txt" <<'PY'
import sys, re
X=[re.compile(l.strip()) for l in open(sys.argv[3]) if l.strip() and not l.lstrip().startswith('#')]
X.append(re.compile(r'^\.gitignore$'))
EXC={'prod':[], 'repo':[]}
def load(f, side):
    out={}
    for l in open(f):
        if '\t' not in l: continue
        v,k=l.rstrip('\n').split('\t',1)
        if any(x.search(k) for x in X):
            if k!='.gitignore': EXC[side].append(k)
        else: out[k]=v
    return out
P,R=load(sys.argv[1],'prod'),load(sys.argv[2],'repo')
changed=sorted(p for p in P if p in R and P[p]!=R[p]); po=sorted(set(P)-set(R)); ro=sorted(set(R)-set(P))
print(f"prod files {len(P)} | repo files {len(R)} | identical {len(set(P)&set(R))-len(changed)}")
for t,l in (("CHANGED (prod != repo)",changed),("ONLY IN PROD (missing from GitHub)",po),("ONLY IN REPO (not deployed)",ro)):
    if l: print(f"\n{t}: {len(l)}"); [print("  "+x) for x in l[:200]]
# Excluded paths are never hidden: they are counted and grouped so new ones are visible.
import collections
for side in ('prod','repo'):
    g=collections.Counter(re.sub(r'/[^/]+$','/*',k) if k.startswith('media/') else k for k in EXC[side])
    print(f"\nEXCLUDED by EXCLUDE.txt ({side}): {len(EXC[side])} files" + ("" if EXC[side] else " (none)"))
    for k,n in sorted(g.items()): print(f"  {k}" + (f"  [{n}]" if n>1 else ""))
if EXC['repo']: print("\nWARNING: excluded paths are tracked in git; remove them from website/.")
sys.exit(1 if (changed or po or ro or EXC['repo']) else 0)
PY
