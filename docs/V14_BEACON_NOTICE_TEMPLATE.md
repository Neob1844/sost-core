# V14 Beacon Notice (Phase II-A) — operator template

Phase A / A6 of `docs/V14_EXECUTION_PLAN.md`. Use the **already-live Beacon II-A**
channel to advise miners/nodes to upgrade before block 15,000. II-A is advisory
only: `commands` MUST be `[]` — a notice never executes anything.

Signed with the operator II-A key (private key on the encrypted USB; public key
hardcoded in `src/beacon.cpp`, fingerprint
`bbb560e3ec86114a59762d467d645c88cfe0497a8f7ca542c973e2e0def8186b`). Served by the
`getbeaconnotices` RPC and rendered by the explorer banner.

## 1. Unsigned notice (`v14-notice-unsigned.json`)
```json
{
  "notice_id": "v14-upgrade-001",
  "network": "mainnet",
  "severity": "warning",
  "title": "V14 hard fork at block 15,000 — upgrade required",
  "message": "V14 activates H3/H4 block-validation hardening and raises the relay fee floor (1 -> 10 stocks/byte). Node and miner operators MUST run the V14 binary before block 15,000 to stay on consensus. Details: https://sostcore.com/news.html",
  "url": "https://sostcore.com/news.html",
  "activation_height": 15000,
  "expires_height": 16000,
  "created_at": "2026-06-15T12:00:00Z",
  "commands": [],
  "signature": ""
}
```

## 2. Sign (operator, offline)
```bash
# canonical payload = notice with the signature field removed
scripts/beacon-sign.sh v14-notice-unsigned.json > notices.json   # uses the II-A private key
scripts/beacon-verify.sh notices.json                            # MUST verify against the hardcoded pubkey
```

## 3. Publish
```bash
# node datadir (served by getbeaconnotices) + explorer
cp notices.json /opt/sost/notices.json
cp notices.json website/api/notices.json   # then deploy website (VPS git pull)
# verify live:
curl -s -u USER:PASS -d '{"method":"getbeaconnotices","params":[],"id":1}' http://127.0.0.1:18232
```

## 4. Checklist
- [ ] `activation_height` = 15000, `network` = "mainnet", `commands` = `[]`
- [ ] Signed with II-A key; `beacon-verify.sh` passes against the hardcoded pubkey
- [ ] Published ≥ 1 week before block 15,000 (and to BitcoinTalk + Telegram official channel)
- [ ] Explorer banner shows the notice; `getbeaconnotices` returns it
- [ ] `expires_height` set so the banner self-clears after the fork settles
