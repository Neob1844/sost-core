# SOST — Guía Rápida: Descargar, Instalar y Transferir

## ¿Qué necesitas?

- Ubuntu 24.04 (o WSL2 en Windows)
- 4 GB de RAM libres (para el minero)
- Conexión a internet (solo para descargar)

---

## Paso 1: Descargar

```bash
# Instalar dependencias
sudo apt update
sudo apt install build-essential cmake libssl-dev libsecp256k1-dev git

# Clonar el repositorio
git clone https://github.com/Neob1844/sost-core.git
cd sost-core

# Compilar
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
cd ..
```

Deberías tener 3 binarios en `build/`:
- `sost-node` — el nodo
- `sost-miner` — el minero
- `sost-cli` — la wallet

---

## Paso 2: Crear tu wallet

```bash
./build/sost-cli newwallet
```

Esto crea `wallet.json` con tu primera dirección. Para verla:

```bash
./build/sost-cli listaddresses
```

Tu dirección empieza por `sost1` seguida de 40 caracteres hex. Ejemplo:

```
sost1ee1363a3232416184c166e2160bc6bbbdd91f0da
```

**Guarda esta dirección** — es como tu número de cuenta.

---

## Paso 3: Recibir SOST

### Opción A — Alguien te envía directamente

Dale tu dirección `sost1...` a quien te vaya a enviar. Esa persona ejecuta:

```bash
./build/sost-cli --wallet wallet.json send sost1<TU_DIRECCIÓN> 50.0 0.001
```

### Opción B — Conectarte a un nodo existente y minar

```bash
# Terminal 1: arrancar nodo conectado a otro
./build/sost-node --genesis genesis_block.json --chain chain.json \
    --wallet wallet.json --connect <IP_DEL_NODO>:19333

# Terminal 2: minar (los rewards van a tu wallet)
./build/sost-miner --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 --blocks 100
```

Cada bloque minado te da **~3.93 SOST** (50% de la recompensa de bloque).

---

## Paso 4: Ver tu saldo

```bash
./build/sost-cli getbalance
```

O en el Explorer — abre `explorer.html` en tu navegador y busca tu dirección.

---

## Paso 5: Enviar SOST

**Importante:** Si tu saldo viene de minar, necesitas esperar **100 bloques** de confirmaciones antes de poder gastar.

```bash
./build/sost-cli --wallet wallet.json send sost1<DESTINO> 10.0 0.001
```

Donde:
- `sost1<DESTINO>` = dirección del destinatario
- `10.0` = cantidad en SOST
- `0.001` = comisión (fee) para el minero

El CLI mostrará:

```
TX created: af3605507a5a3a7e...
TX accepted by node!
Waiting for next mined block to confirm...
```

Ahora hay que minar 1 bloque para confirmar:

```bash
./build/sost-miner --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 --blocks 1
```

Cuando el nodo muestre `TX confirmed` — la transferencia está hecha.

---

## Paso 6: Verificar la transferencia

En el Explorer (`explorer.html`), busca la dirección del destinatario. Verás:

- **BALANCE:** la cantidad recibida
- **UTXOs:** el listado de salidas no gastadas
- **HEIGHT:** en qué bloque se confirmó

---

## Resumen de comandos

| Qué quieres hacer | Comando |
|--------------------|---------|
| Crear wallet | `sost-cli newwallet` |
| Ver tu dirección | `sost-cli listaddresses` |
| Ver tu saldo | `sost-cli getbalance` |
| Arrancar nodo | `sost-node --genesis genesis_block.json --chain chain.json --wallet wallet.json` |
| Minar bloques | `sost-miner --genesis genesis_block.json --chain chain.json --rpc 127.0.0.1:18232 --blocks 10` |
| Enviar SOST | `sost-cli --wallet wallet.json send sost1<destino> <cantidad> 0.001` |
| Confirmar TX | `sost-miner ... --rpc 127.0.0.1:18232 --blocks 1` |

---

## ¿Problemas?

| Error | Solución |
|-------|----------|
| `insufficient funds` | Necesitas más SOST o esperar 100 bloques (maturity) |
| `coinbase immature` | Mina más bloques — los UTXO de minería necesitan 100 confirmaciones |
| `node rejected block` | Asegúrate de que el nodo (T1) está corriendo |
| `Address already in use` | Ya hay un nodo corriendo — `pkill -f sost-node` y reinicia |

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

---

*SOST Protocol — sostcore.com*
