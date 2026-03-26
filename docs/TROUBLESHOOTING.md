# SOST Protocol — Guía de Troubleshooting

Formato: SÍNTOMA → CAUSA PROBABLE → SOLUCIÓN

---

## Red / Conectividad

**1.** "Connection refused" al intentar RPC
→ El nodo no está corriendo
→ `sudo systemctl restart sost-node`

**2.** "Connection refused" pero el nodo está corriendo
→ El puerto RPC no está escuchando o el firewall lo bloquea
→ `ss -tlnp | grep 18232` para verificar. Comprobar `ufw status`.

**3.** El miner dice "RPC Connection lost" repetidamente
→ El túnel SSH se cayó
→ `pkill -f "ssh -N.*18232"` y recrear con autossh (ver Runbook #18)

**4.** "Permission denied" al conectar SSH al VPS
→ Clave SSH no autorizada o cambiada
→ Verificar `~/.ssh/authorized_keys` en el VPS

**5.** La web carga lento pero funciona
→ Nginx sin caché o DDoS
→ `sudo nginx -t` para verificar config. Revisar `access.log`.

## Nodo / Blockchain

**6.** El nodo arranca pero se queda en "Loading chain..."
→ chain.json corrupto o muy grande
→ Restaurar backup: `cp /opt/sost/backups/chain_ULTIMO.json build/chain.json`

**7.** "Invalid block" en los logs del nodo
→ Bloque recibido que no pasa validación de consenso
→ Normal si peers envían basura. Si persiste, verificar versión del código.

**8.** La cadena no avanza (mismo bloque durante >1 hora)
→ No hay mineros activos o la dificultad es muy alta
→ Verificar: `curl -s -d '{"method":"getinfo"}' http://127.0.0.1:18232/` — ver campo "blocks"

**9.** "Reorg detected" en logs
→ Normal si <10 bloques. Si >10, puede indicar un ataque.
→ MAX_REORG_DEPTH=500, protege contra reorgs profundos.

**10.** "Peer banned" en los logs
→ Un peer envió datos inválidos. Normal.
→ Ban dura 24h. No requiere acción.

## Miner

**11.** El miner consume >8GB de RAM y se muere (OOM Killer)
→ ConvergenceX necesita 8GB (4GB dataset + 4GB scratchpad)
→ Añadir swap (ver Runbook #20). Verificar `.wslconfig`.

**12.** "ConvergenceX: stability check FAILED"
→ El bloque generado no pasó la verificación de estabilidad
→ Normal — el miner descarta ese intento y prueba otro nonce.

**13.** El miner produce bloques pero no aparecen en el explorer
→ El RPC funciona pero la cadena del VPS no los acepta
→ Verificar que miner y nodo están en la misma versión. Recompilar ambos.

**14.** "Duplicate coinbase" error
→ Dos bloques con el mismo height intentados
→ Reiniciar miner para que pida el height actual.

## Web / Explorer

**15.** El explorer muestra "OFFLINE" en rojo
→ El fetch al RPC falla desde el navegador
→ Verificar que nginx proxy_pass al RPC está configurado, o que node-status.json se genera.

**16.** Los gráficos del explorer no cargan
→ Sin datos de bloques o JavaScript error
→ Abrir DevTools (F12) → Console para ver errores.

**17.** "Mixed content" warning en el navegador
→ HTTP recursos cargados desde HTTPS página
→ Asegurar que todos los assets usan URLs relativas o HTTPS.

**18.** La app dice "SESSION ENDED" inmediatamente
→ El splash no terminó o hay error JS
→ Limpiar caché: Ctrl+Shift+Delete → Recargar

## Auth / Seguridad

**19.** "401 Unauthorized" al acceder a páginas protegidas
→ Token expirado o credenciales incorrectas
→ Re-login o regenerar credenciales (ver Runbook #6)

**20.** "CORS error" en la consola del navegador
→ Nginx no envía headers CORS
→ Añadir en nginx config: `add_header Access-Control-Allow-Origin *;`

## SSL

**21.** "NET::ERR_CERT_DATE_INVALID" en el navegador
→ Certificado SSL expirado
→ `sudo certbot renew && sudo systemctl reload nginx`

**22.** "Certificate for wrong domain"
→ Nginx está sirviendo el certificado equivocado
→ Verificar `server_name` en config nginx coincide con el dominio.

## Disco / Sistema

**23.** "No space left on device"
→ Disco lleno
→ `df -h /` → Limpiar logs y backups viejos (ver Runbook #5)

**24.** El VPS está muy lento
→ RAM insuficiente o CPU saturada
→ `htop` para ver procesos. Matar zombies: `pkill -f python.*train`

**25.** Los logs crecen sin parar
→ No hay rotación de logs configurada
→ Instalar cron con log_rotate.sh (ver `deploy/setup_cron.sh`)

## GeaSpirit

**26.** Un script de GeaSpirit falla con "ModuleNotFoundError"
→ Falta un paquete Python
→ `pip install rasterio scikit-learn xgboost pandas numpy scipy`

**27.** "EMIT stack not found"
→ Los datos EMIT no están descargados
→ Ver manual dropzone: `~/SOST/geaspirit/data/manual_drop/peru_emit/README.md`

**28.** "rasterio: file not recognized"
→ El archivo descargado está truncado o es HTML
→ Verificar tamaño (`ls -la`). Si <1MB probablemente no es un GeoTIFF real.

## Build

**29.** "cmake: command not found"
→ cmake no instalado
→ `sudo apt install cmake build-essential libssl-dev libsecp256k1-dev`

**30.** "error: secp256k1.h not found"
→ libsecp256k1 no instalado
→ `sudo apt install libsecp256k1-dev`
