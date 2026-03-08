# SOST Protocol — Guía de Instalación, Minado y Transferencias

Esta guía cubre desde la instalación hasta tu primera transferencia. Cada comando incluye exactamente qué escribir y qué esperar como respuesta.

---

## 1. Requisitos

- Ubuntu 24.04 (nativo o WSL2 en Windows)
- 4 GB de RAM libres
- Conexión a internet para la descarga inicial

---

## 2. Instalación de dependencias

Abre una terminal de Ubuntu y ejecuta:

```bash
sudo apt update
sudo apt install build-essential cmake libssl-dev libsecp256k1-dev git -y
```

El sistema pedirá tu contraseña. Al escribirla no se muestran caracteres en pantalla — es el comportamiento normal de Linux. Pulsa Enter y espera a que termine.

---

## 3. Descarga y compilación

### 3.1 — Clonar el repositorio

```bash
git clone https://github.com/Neob1844/sost-core.git
cd sost-core
```

El comando `cd` te sitúa dentro de la carpeta descargada. Todos los comandos siguientes se ejecutan desde esta carpeta.

### 3.2 — Compilar

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
cd ..
```

La compilación tarda entre 1 y 5 minutos. Verás líneas numeradas del tipo `[ 25%] Building CXX...`. Si aparecen `warning:` se pueden ignorar — solo los mensajes `error:` son problemas reales.

### 3.3 — Verificar los binarios

```bash
ls build/sost-node build/sost-miner build/sost-cli
```

Debe mostrar las tres rutas. Si alguna falta, la compilación falló.

| Binario | Función |
|---------|---------|
| `sost-node` | Nodo completo: mantiene la cadena, valida bloques y transacciones, sirve RPC |
| `sost-miner` | Minero: resuelve PoW y envía bloques al nodo |
| `sost-cli` | Wallet: gestiona claves, saldos y envíos |

---

## 4. Crear wallet

```bash
./build/sost-cli newwallet
```

Respuesta esperada:

```
New wallet created: wallet.json
Address: sost1a7b3c4d5e6f7890123456789abcdef012345678
*** BACKUP THIS FILE — IT CONTAINS YOUR PRIVATE KEYS ***
```

El archivo `wallet.json` contiene tus claves privadas sin cifrar. Haz una copia de seguridad antes de continuar:

```bash
cp wallet.json wallet.json.backup
```

Para ver tu dirección en cualquier momento:

```bash
./build/sost-cli listaddresses
```

---

## 5. Arquitectura: tres terminales

SOST usa tres procesos independientes que se comunican entre sí por RPC (puerto 18232). Cada uno necesita su propia terminal:

```
Terminal 1 (T1) → sost-node    (corre permanentemente, mantiene la cadena)
Terminal 2 (T2) → sost-miner   (mina bloques, se puede parar y reiniciar)
Terminal 3 (T3) → sost-cli     (comandos puntuales: saldo, envíos, info)
```

Para abrir terminales adicionales en Ubuntu: `Ctrl+Alt+T`. En WSL2: abrir nuevas pestañas o ventanas de Windows Terminal.

**Importante:** Cada terminal nueva se abre en tu carpeta home. Necesitas situarte en la carpeta del proyecto antes de ejecutar cualquier comando:

```bash
cd ~/sost-core
```

O la ruta completa donde hayas clonado el repositorio (ejemplo: `cd ~/SOST/sostcore/sost-core`).

---

## 6. Arrancar el nodo (Terminal 1)

### 6.1 — Elegir credenciales RPC

El nodo requiere usuario y contraseña para autenticar las peticiones RPC. Elige las que quieras. En esta guía usamos `miusuario` y `mipassword` como ejemplo — cámbialos por los tuyos.

### 6.2 — Ejecutar

En la **Terminal 1**:

```bash
cd ~/sost-core

./build/sost-node --genesis genesis_block.json --chain chain.json \
    --wallet wallet.json --rpc-user=miusuario --rpc-pass=mipassword
```

Respuesta esperada:

```
=== SOST Node v0.3.1 ===
Profile: MAINNET | P2P: 19333 | RPC: 18232 | RPC auth: ON
Genesis: 0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793
Wallet: 1 keys
Node running. Ctrl+C to stop.
[P2P] Listening on port 19333
[RPC] Listening on port 18232 — 17 methods (auth=ON)
```

El nodo queda corriendo en primer plano. No cierres esta terminal. Toda la actividad (bloques aceptados, transacciones, conexiones de peers) aparece aquí.

### 6.3 — Parámetros del nodo

| Parámetro | Obligatorio | Descripción |
|-----------|:-----------:|-------------|
| `--genesis <ruta>` | Sí | Archivo JSON del bloque génesis |
| `--chain <ruta>` | No | Archivo de estado de la cadena (se crea si no existe) |
| `--wallet <ruta>` | No | Archivo wallet (default: wallet.json) |
| `--rpc-user <user>` | Recomendado | Usuario para autenticación RPC |
| `--rpc-pass <pass>` | Recomendado | Contraseña para autenticación RPC |
| `--port <n>` | No | Puerto P2P (default: 19333) |
| `--rpc-port <n>` | No | Puerto RPC (default: 18232) |
| `--connect <host:port>` | No | IP de otro nodo para sincronizar |

---

## 7. Minar bloques (Terminal 2)

Abre una **nueva terminal** y sitúate en la carpeta del proyecto:

```bash
cd ~/sost-core

./build/sost-miner --address sost1TU_DIRECCION_AQUI \
    --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 --rpc-user=miusuario --rpc-pass=mipassword --blocks 100
```

**`--address` es OBLIGATORIO.** Usa la dirección que obtuviste con `./build/sost-cli listaddresses`. Las credenciales `--rpc-user` y `--rpc-pass` deben ser las mismas que usaste en el nodo.

Respuesta esperada:

```
[MINER] Connecting to RPC 127.0.0.1:18232
[MINER] Block #1 mined! Hash: 00000a3f... Nonce: 234567 Time: 12.3s
[MINER] Block #2 mined! Hash: 000003b2... Nonce: 891023 Time: 8.7s
...
```

Cada bloque genera ~7.85 SOST de recompensa total. El 50% (~3.93 SOST) va a tu wallet. El 25% va al Gold Vault y el 25% al PoPC Pool.

### 7.1 — Parámetros del minero

| Parámetro | Obligatorio | Descripción |
|-----------|:-----------:|-------------|
| `--address <sost1..>` | **Sí** | Tu dirección wallet para recibir recompensas de minería |
| `--genesis <ruta>` | Sí | Archivo JSON del bloque génesis |
| `--chain <ruta>` | Sí | Archivo de estado de la cadena |
| `--rpc <host:port>` | Recomendado | Dirección del nodo (127.0.0.1:18232 para localhost) |
| `--rpc-user <user>` | Si el nodo lo requiere | Mismas credenciales que el nodo |
| `--rpc-pass <pass>` | Si el nodo lo requiere | Mismas credenciales que el nodo |
| `--blocks <n>` | No | Número de bloques a minar (default: 5) |
| `--max-nonce <n>` | No | Nonces por ronda (default: 500000) |

### 7.2 — Madurez de las recompensas (coinbase maturity)

Las recompensas de minería no son gastables inmediatamente. Cada UTXO de coinbase requiere **1,000 confirmaciones** (1,000 bloques posteriores, ~7 días) para madurar.

Ejemplo: Si minas el bloque #50, esa recompensa se desbloquea cuando la cadena llega al bloque #1050. Las transferencias normales entre usuarios, en cambio, son gastables desde el primer bloque de confirmación.

---

## 8. Consultar saldo (Terminal 3)

Abre una **tercera terminal**:

```bash
cd ~/sost-core

./build/sost-cli getbalance
```

Este comando muestra el saldo total de todos los UTXOs en tu wallet (incluyendo inmaduros). Para ver el desglose individual:

```bash
./build/sost-cli listunspent
```

Muestra cada UTXO con su txid, cantidad y altura de bloque. Para ver un resumen del wallet:

```bash
./build/sost-cli info
```

---

## 9. Enviar SOST (Terminal 3)

### 9.1 — Requisitos previos

- El nodo debe estar corriendo (Terminal 1)
- Tener saldo maduro (con 100+ confirmaciones si proviene de minería)
- Conocer la dirección `sost1...` del destinatario

### 9.2 — Ejecutar la transferencia

```bash
./build/sost-cli --wallet wallet.json --rpc-user=miusuario --rpc-pass=mipassword \
    send sost1ee1363a3232416184c166e2160bc6bbbdd91f0da 50
```

Sustituye la dirección `sost1ee13...` por la dirección real del destinatario, y `50` por la cantidad deseada.

Respuesta esperada:

```
Chain height: 614
TX created: af3605507a5a3a7e...
  To:     sost1ee1363a3232416184c166e2160bc6bbbdd91f0da
  Amount: 50.00000000 SOST
  Fee:    0.00001234 SOST (1234 stocks = 1234 bytes x 1 rate)
  Size:   1234 bytes
Sending to node 127.0.0.1:18232...

TX accepted by node!
  Waiting for next mined block to confirm...
```

La comisión (fee) se calcula automáticamente: tamaño en bytes × 1 stock/byte. Para prioridad más alta usa `--fee-rate 2` o superior:

```bash
./build/sost-cli --fee-rate 2 --wallet wallet.json \
    --rpc-user=miusuario --rpc-pass=mipassword \
    send sost1<destino> 50
```

### 9.3 — Confirmar la transacción

La transacción queda en el mempool hasta que un minero la incluya en un bloque. Si el minero sigue corriendo en T2, se confirma automáticamente en el siguiente bloque.

Si el minero no está corriendo, mina un bloque manualmente desde T2:

```bash
./build/sost-miner --address sost1TU_DIRECCION_AQUI \
    --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 --rpc-user=miusuario --rpc-pass=mipassword --blocks 1
```

La terminal del nodo (T1) mostrará la confirmación.

### 9.4 — Parámetros del CLI

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `--wallet <ruta>` | wallet.json | Archivo wallet |
| `--rpc-user <user>` | — | Credenciales RPC (mismas que el nodo) |
| `--rpc-pass <pass>` | — | Credenciales RPC (mismas que el nodo) |
| `--node <host:port>` | 127.0.0.1:18232 | Dirección del nodo |
| `--fee-rate <n>` | 1 | Stocks por byte (1 = mínimo consenso) |

---

## 10. Verificar la transferencia

### Por terminal

```bash
./build/sost-cli getbalance
```

### Por el Explorer

Abre `explorer.html` en cualquier navegador. El explorer se conecta al nodo en `http://localhost:18232`. Busca la dirección del destinatario en el campo de búsqueda para ver su saldo, UTXOs y el historial de transacciones.

---

## 11. Parar y reiniciar

### Parar el nodo

En la Terminal 1, pulsa `Ctrl+C`. La cadena se guarda en disco automáticamente.

### Reiniciar el nodo

```bash
./build/sost-node --genesis genesis_block.json --chain chain.json \
    --wallet wallet.json --rpc-user=miusuario --rpc-pass=mipassword
```

El nodo carga la cadena completa desde disco. No se pierde ningún bloque ni transacción.

### Minar en background (sesiones persistentes)

Para que el nodo y el minero sigan corriendo al cerrar la terminal:

```bash
# Instalar screen (solo la primera vez)
sudo apt install screen -y

# Sesión para el nodo
screen -S nodo
./build/sost-node --genesis genesis_block.json --chain chain.json \
    --wallet wallet.json --rpc-user=miusuario --rpc-pass=mipassword
# Pulsa Ctrl+A y luego D para dejar la sesión en background

# Sesión para el minero
screen -S minero
./build/sost-miner --address sost1TU_DIRECCION_AQUI \
    --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 --rpc-user=miusuario --rpc-pass=mipassword --blocks 10000
# Pulsa Ctrl+A y luego D para dejar la sesión en background

# Para volver a ver una sesión:
screen -r nodo
screen -r minero
```

---

## 12. Recompilar después de cambios en el código

Si modificas algún archivo del código fuente y necesitas recompilar, usa el script de backup automático **antes de compilar**:

```bash
chmod +x safe-rebuild.sh    # solo la primera vez
./safe-rebuild.sh
```

Este script crea una copia de seguridad del estado de la cadena y del wallet con timestamp, y después compila. Si la nueva compilación rompe algo, puedes restaurar con:

```bash
rm -rf ~/.sost/chainstate
cp -r ~/.sost/chainstate_backup_<timestamp> ~/.sost/chainstate
```

**Este paso solo es necesario al recompilar.** El uso normal (arrancar nodo, minar, enviar SOST) no requiere backup adicional.

---

## 13. Errores frecuentes

| Error | Causa | Solución |
|-------|-------|----------|
| `insufficient mature balance` | Las recompensas de minería aún no tienen 1,000 confirmaciones | Seguir minando hasta acumular 1,000 bloques sobre tus primeras recompensas |
| `insufficient mature funds` | Tienes algo gastable pero no suficiente para la cantidad + fee | Esperar más bloques o reducir la cantidad |
| `insufficient funds` | No hay saldo suficiente en total | Minar más bloques |
| `cannot connect to node` | El nodo no está corriendo o la dirección es incorrecta | Verificar que T1 muestra "Node running" |
| `401 Unauthorized` | Credenciales RPC incorrectas o ausentes | Usar los mismos `--rpc-user` y `--rpc-pass` que el nodo |
| `Address already in use` | Ya hay un nodo usando el puerto | `pkill -f sost-node` y reiniciar |
| `Permission denied` en scripts | El script no tiene permisos de ejecución | `chmod +x nombre_del_script.sh` |
| `TX rejected: S8: fee too low` | Fee inferior al mínimo por byte | Actualizar al CLI v1.3 (calcula fee automáticamente) |

---

## 14. Referencia rápida de comandos

| Acción | Comando |
|--------|---------|
| Crear wallet | `./build/sost-cli newwallet` |
| Ver direcciones | `./build/sost-cli listaddresses` |
| Ver saldo | `./build/sost-cli getbalance` |
| Ver UTXOs | `./build/sost-cli listunspent` |
| Info del wallet | `./build/sost-cli info` |
| Arrancar nodo | `./build/sost-node --genesis genesis_block.json --chain chain.json --wallet wallet.json --rpc-user=USER --rpc-pass=PASS` |
| Minar N bloques | `./build/sost-miner --address sost1TU_ADDR --genesis genesis_block.json --chain chain.json --rpc 127.0.0.1:18232 --rpc-user=USER --rpc-pass=PASS --blocks N` |
| Enviar SOST | `./build/sost-cli --wallet wallet.json --rpc-user=USER --rpc-pass=PASS send sost1<destino> <cantidad>` |
| Enviar con prioridad | `./build/sost-cli --fee-rate 2 --wallet wallet.json --rpc-user=USER --rpc-pass=PASS send sost1<destino> <cantidad>` |
| Minar 1 bloque (confirmar TX) | `./build/sost-miner --address sost1TU_ADDR --genesis genesis_block.json --chain chain.json --rpc 127.0.0.1:18232 --rpc-user=USER --rpc-pass=PASS --blocks 1` |
| Backup antes de recompilar | `./safe-rebuild.sh` |
| Exportar clave privada | `./build/sost-cli dumpprivkey <dirección>` |
| Importar clave privada | `./build/sost-cli importprivkey <64_hex>` |

---

## 15. Parámetros de red

| Parámetro | Valor |
|-----------|-------|
| Algoritmo | ConvergenceX (CPU, 4GB RAM) |
| Tiempo objetivo por bloque | 10 minutos |
| Recompensa inicial | 7.85100863 SOST |
| Distribución | 50% minero · 25% Gold Vault · 25% PoPC Pool |
| Madurez coinbase | 1,000 bloques (~7 días) |
| Supply máximo | ~4,669,201 SOST |
| Puerto P2P | 19333 |
| Puerto RPC | 18232 |
| Formato de dirección | `sost1` + 40 caracteres hex |

---
## Arquitectura mínima

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  sost-cli   │────▶│  sost-node  │◀────│ sost-miner  │
│  (wallet)   │ RPC │  (cadena)   │ RPC │  (bloques)  │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │ P2P
                    ┌──────┴──────┐
                    │ otro nodo   │
                    │ (amigo)     │
                    └─────────────┘
```

- El **CLI** crea y firma transacciones, las envía al nodo por RPC
- El **nodo** valida, mantiene la cadena y el mempool, sincroniza con peers por P2P
- El **minero** construye bloques incluyendo TXs del mempool, los envía al nodo por RPC
- Los **peers** se sincronizan automáticamente al conectarse

*SOST Protocol — [sostcore.com](https://sostcore.com)*
