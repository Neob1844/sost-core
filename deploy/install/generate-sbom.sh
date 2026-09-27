#!/usr/bin/env bash
# Generate SHA256SUMS + a minimal SBOM for a SOST release bundle.
# Usage: ./generate-sbom.sh <dir-with-binaries> [version]
# Produces <dir>/SHA256SUMS and <dir>/sbom.json (CycloneDX-ish, no network needed).
set -euo pipefail
DIR="${1:?release dir required}"; VER="${2:-unknown}"
cd "$DIR"

# 1. hashes for every shipped file
: > SHA256SUMS
find . -maxdepth 1 -type f ! -name SHA256SUMS ! -name sbom.json -print0 \
  | sort -z | xargs -0 sha256sum >> SHA256SUMS
echo "wrote SHA256SUMS ($(wc -l < SHA256SUMS) files)"

# 2. minimal SBOM: each binary + its linked shared libs (ldd), best-effort
comp=""
for f in $(find . -maxdepth 1 -type f -perm -u+x ! -name '*.sh' ! -name SHA256SUMS); do
  h=$(sha256sum "$f" | awk '{print $1}')
  libs=$(ldd "$f" 2>/dev/null | awk '{print $1}' | grep -E '\.so' | sort -u | sed 's/.*/"&"/' | paste -sd, - || true)
  comp="$comp{\"name\":\"$(basename "$f")\",\"version\":\"$VER\",\"type\":\"application\",\"hashes\":[{\"alg\":\"SHA-256\",\"content\":\"$h\"}],\"dependencies\":[${libs:-}]},"
done
comp="${comp%,}"
cat > sbom.json <<EOF
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "metadata": { "component": { "name": "sost", "version": "$VER", "type": "application" } },
  "components": [ $comp ]
}
EOF
echo "wrote sbom.json"
echo "verify later with:  sha256sum -c SHA256SUMS"
