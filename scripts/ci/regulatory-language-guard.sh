#!/usr/bin/env bash
# SOST · Regulatory-language guard (anti-inercia). Fails if PUBLIC surfaces gain
# gambling/prize/investment MARKETING framing. Rule (from block G, 2026-09-29):
#   Public framing MUST be consensus / reward-distribution among eligible miners/nodes.
#   ANY "prize / win the / jackpot-you-win / lottery-you-play / buy-ticket-win /
#   premio monetario / gana el bote / participa y gana / investment offer" framing
#   requires LEGAL SIGN-OFF first (DGOJ Ley 13/2011 — a periodic monetary-prize draw
#   is state-monopoly LOTTERY territory; MiCA/ECSPR — token-as-investment = security).
# The DTD "lottery" mechanic is a MINER-REWARD distribution, not a public game; the
# technical term alone is allowed, but the PLAY/PRIZE/WIN framing below is not.
# Scope: user-visible public HTML/JS. EXCLUDES the BIP39 wordlist (contains "prize")
# and the DEX Draw legal DISCLAIMER (which correctly flags itself as a regulated rifa).
set -uo pipefail
ROOT="${1:-website}"
# Marketing/prize/gambling framing aimed at the PUBLIC (not the technical term):
PATTERNS='gana el bote|participa y gana|juega y gana|compra .*(ticket|boleto).* gana|win the (jackpot|bote|prize|pot)|your chance to win|buy a ticket|premio monetario|apuesta( tu| aqu[íi])|play to win|enter to win'
# files to scan (public surfaces), excluding known-safe CLASS C:
mapfile -t FILES < <(find "$ROOT" -type f \( -name '*.html' -o -name '*.js' \) 2>/dev/null \
  | grep -vE 'wallet\.html|sost-wallet\.html' )   # BIP39 wordlist lives here
HITS=0
for f in "${FILES[@]}"; do
  # skip the DEX Draw legal disclaimer lines (accurate self-labeling, CLASS C)
  m=$(grep -inE "$PATTERNS" "$f" 2>/dev/null | grep -viE 'requires authorization|DGOJ|Ley 13/2011|rifa \(ES' )
  if [ -n "$m" ]; then echo "REGULATORY-GUARD FAIL: $f"; echo "$m" | sed 's/^/   /'; HITS=$((HITS+1)); fi
done
if [ "$HITS" -gt 0 ]; then
  echo ""
  echo "❌ Public gambling/prize/investment framing detected ($HITS file(s))."
  echo "   Per block G: public framing = consensus/reward-distribution ONLY."
  echo "   Prize/lottery/investment marketing needs LEGAL SIGN-OFF (DGOJ / MiCA) before publish."
  exit 1
fi
echo "✅ regulatory-language guard: clean (no public prize/gambling/investment framing)."
