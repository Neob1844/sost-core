# SOST Protocol — Runbook de Operaciones

Guía paso a paso para mantener el sistema. Pensado para operar SIN asistencia de IA.
Todos los comandos son copy-paste. Ejecutar en el VPS salvo que se indique lo contrario.

---

## 1. El nodo se ha caído

**Verificar:** `curl -s -d '{"method":"getinfo","params":[],"id":1}' http://127.0.0.1:18232/`
Si no devuelve JSON → el nodo está caído.

**Reparar:**
```bash
sudo systemctl restart sost-node
sleep 5
sudo systemctl status sost-node
```

**Verificar:** Repetir el curl. Debe devolver JSON con `"blocks"`.

**Si falla:** `journalctl -u sost-node -n 50` para ver los logs de error.

---

## 2. El miner se ha desconectado

**Verificar:** `pgrep -af sost-miner` (en WSL)

**Reparar (en WSL):**
```bash
# Matar túneles viejos
pkill -f "ssh -N.*18232"
sleep 2

# Recrear túnel con autossh
autossh -M 0 -f -N -L 18232:127.0.0.1:18232 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  root@212.132.108.244

# Verificar túnel
ss -tlnp | grep 18232

# Reiniciar miner
cd ~/SOST/sostcore/sost-core/build
./sost-miner --address sost1a8eae8f80fedd8d86187db628a0d81e0367f76de \
  --rpc 127.0.0.1:18232 --rpc-user USER --rpc-pass PASS \
  --blocks 999999 --max-nonce 500000 --realtime --profile mainnet &
```

---

## 3. La web no carga

**Verificar:** `curl -sI https://sostcore.com | head -5`

**Reparar:**
```bash
sudo systemctl restart nginx
sudo nginx -t  # Verificar config válida
```

**Si falla:** `sudo nginx -t` muestra el error de configuración.

---

## 4. El SSL ha expirado

**Verificar:** `sudo openssl x509 -enddate -noout -in /etc/letsencrypt/live/sostcore.com/cert.pem`

**Reparar:**
```bash
sudo certbot renew
sudo systemctl reload nginx
```

---

## 5. El disco está lleno

**Verificar:** `df -h /`

**Limpiar:**
```bash
sudo journalctl --vacuum-time=7d
sudo find /var/log -name "*.gz" -mtime +30 -delete
sudo find /opt/sost/backups -mtime +30 -delete
```

---

## 6. He olvidado la contraseña admin

**Reparar:** Regenerar credenciales del auth gateway.
```bash
cd /opt/sost
# Editar auth.env con nuevas credenciales
sudo nano /etc/sost/auth.env
sudo systemctl restart sost-auth
```

---

## 7. El auth gateway no responde

**Verificar:** `curl -s http://127.0.0.1:8200/health`

**Reparar:** `sudo systemctl restart sost-auth`

**Si falla:** `journalctl -u sost-auth -n 30`

---

## 8. Quiero hacer un backup manual

```bash
sudo /opt/sost/deploy/auto_backup.sh
ls -la /opt/sost/backups/
```

---

## 9. Quiero restaurar un backup

```bash
# Parar el nodo
sudo systemctl stop sost-node

# Restaurar chain
sudo cp /opt/sost/backups/chain_FECHA.json /opt/sost/build/chain.json

# Arrancar
sudo systemctl start sost-node
```

---

## 10. Quiero actualizar el código

```bash
# En WSL:
cd ~/SOST/sostcore/sost-core
git push origin main

# En VPS:
cd /opt/sost
git pull origin main

# Si hay cambios de consenso, recompilar:
cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j2
sudo systemctl restart sost-node
```

---

## 11. El explorer muestra datos incorrectos

**Si RPC funciona pero el explorer muestra datos viejos:** Limpiar caché del navegador (Ctrl+Shift+F5).

**Si RPC no funciona:** Reiniciar el nodo (ver procedimiento 1).

---

## 12. Quiero crear una dirección multisig

```bash
cd ~/SOST/sostcore/sost-core/build
./sost-cli multisig create --m 2 --n 3 --pubkeys "KEY1,KEY2,KEY3"
```
La dirección resultante empezará con `sost3`.

---

## 13. Quiero hacer una transacción PSBT (offline signing)

```bash
# 1. Crear PSBT (en computador online)
./sost-cli psbt create --to ADDR --amount 1.5 --fee 0.001

# 2. Firmar (en computador offline/air-gapped)
./sost-cli psbt sign --file tx.psbt --key PRIVKEY

# 3. Broadcast (en computador online)
./sost-cli psbt broadcast --file tx_signed.psbt
```

---

## 14. El VPS necesita reinicio

Los servicios deben arrancar solos (systemd enabled). Después verificar:
```bash
sudo systemctl status sost-node nginx sost-auth
```

Si alguno no arrancó: `sudo systemctl start SERVICIO`

---

## 15. Quiero migrar a otro VPS

```bash
# En el VPS nuevo:
sudo apt install build-essential cmake libssl-dev libsecp256k1-dev nginx certbot python3-certbot-nginx
git clone https://github.com/Neob1844/sost-core.git /opt/sost
cd /opt/sost/build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j2

# Copiar datos del VPS viejo:
scp root@OLD_VPS:/opt/sost/build/chain.json /opt/sost/build/
scp root@OLD_VPS:/etc/sost/auth.env /etc/sost/
scp root@OLD_VPS:/etc/nginx/sites-enabled/sost* /etc/nginx/sites-enabled/

# Configurar SSL:
sudo certbot --nginx -d sostcore.com -d sostprotocol.com

# Arrancar:
sudo systemctl enable --now sost-node nginx sost-auth
```

---

## 16. Quiero añadir un dominio nuevo

```bash
# 1. DNS: apuntar el dominio al IP del VPS
# 2. Nginx: copiar config existente y cambiar server_name
sudo cp /etc/nginx/sites-enabled/sost /etc/nginx/sites-enabled/nuevo-dominio
sudo nano /etc/nginx/sites-enabled/nuevo-dominio  # cambiar server_name
sudo nginx -t && sudo systemctl reload nginx
# 3. SSL:
sudo certbot --nginx -d nuevo-dominio.com
```

---

## 17. Ha habido un hard fork

```bash
# En VPS:
cd /opt/sost && git pull origin main
cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j2
sudo systemctl restart sost-node

# En WSL:
cd ~/SOST/sostcore/sost-core
git pull origin main
cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)
# Reiniciar miner (ver procedimiento 2)
```

---

## 18. El túnel SSH se cae constantemente

```bash
# En WSL:
sudo apt install autossh
autossh -M 0 -f -N -L 18232:127.0.0.1:18232 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  root@212.132.108.244
```
autossh reconecta automáticamente si el túnel se cae.

---

## 19. Quiero ver el estado del sistema

```bash
# En VPS:
sudo systemctl status sost-node sost-auth nginx
df -h / && free -h
crontab -l
ls -lt /opt/sost/backups/ | head -5
cat /var/log/sost-health.log | tail -10
```

---

## 20. El miner usa demasiada RAM y se muere

**Verificar:** `free -h` (en WSL)

**Si no hay swap:**
```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**WSL config:** Editar `C:\Users\TU_USUARIO\.wslconfig`:
```
[wsl2]
memory=12GB
swap=8GB
```
Reiniciar WSL: `wsl --shutdown` desde PowerShell.
