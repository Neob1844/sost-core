# SOST Node — Windows Quickstart

Runs the same `sost-node.exe` binary. No admin rights required for a user-level install.

## 1. Verify the download
Open PowerShell in the folder with the release files:
```powershell
Get-FileHash .\sost-node.exe -Algorithm SHA256
# Compare the hash against the line for sost-node.exe in SHA256SUMS
Get-Content .\SHA256SUMS | Select-String 'sost-node.exe'
```
Do not run a binary whose hash does not match.

## 2. Lay out data + secrets
```powershell
$Data = "$env:LOCALAPPDATA\SOST"
New-Item -ItemType Directory -Force -Path $Data | Out-Null
# RPC password (kept in the data dir, readable only by your user)
$pw = [Convert]::ToBase64String((1..24 | % {Get-Random -Max 256})) -replace '[/+=]',''
Set-Content -Path "$Data\rpc.pass" -Value $pw -NoNewline
# Node key
$key = -join ((1..64) | % { '{0:x}' -f (Get-Random -Max 16) })
Set-Content -Path "$Data\node.key" -Value $key -NoNewline
icacls "$Data\rpc.pass" /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null
icacls "$Data\node.key"  /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null
```

## 3. Run the node
```powershell
$Data = "$env:LOCALAPPDATA\SOST"
.\sost-node.exe `
  --chain    "$Data\chain.json" `
  --wallet   "$Data\wallet.json" `
  --genesis  ".\genesis.json" `
  --port 18333 --rpc-port 18332 `
  --rpc-user sostrpc --rpc-pass-file "$Data\rpc.pass" `
  --node-key-file "$Data\node.key"
```
Secrets are passed as **files**, never on the command line (the command line is visible to other
processes).

## 4. Check it
```powershell
$pw = Get-Content "$env:LOCALAPPDATA\SOST\rpc.pass"
$b  = "sostrpc:$pw"; $h = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($b))
Invoke-RestMethod -Uri http://127.0.0.1:18332/ -Method Post `
  -Headers @{Authorization="Basic $h"} -ContentType 'application/json' `
  -Body '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}'
```

## 5. Run in the background (Task Scheduler)
```powershell
$action  = New-ScheduledTaskAction -Execute "$PWD\sost-node.exe" -Argument "--chain `"$env:LOCALAPPDATA\SOST\chain.json`" --rpc-pass-file `"$env:LOCALAPPDATA\SOST\rpc.pass`" --node-key-file `"$env:LOCALAPPDATA\SOST\node.key`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "SOST Node" -Action $action -Trigger $trigger -Description "SOST full node"
```

## 6. Upgrade / rollback
- **Upgrade:** stop the task/process, rename `sost-node.exe` to `sost-node.exe.bak`, drop in the
  new hash-verified binary, restart. Your data dir (`%LOCALAPPDATA%\SOST`) is untouched.
- **Rollback:** stop, restore `sost-node.exe.bak`, restart.

## Note (miners only)
Node and miner binaries **must** be built with
`-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF` or the node rejects all blocks. The
released binaries already are; this matters only if you build your own.
