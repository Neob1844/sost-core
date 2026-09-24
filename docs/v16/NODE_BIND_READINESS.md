# NODE_BIND — estado de preparación y procedimiento

Comprobación en modo lectura del 2026-09-24 sobre el nodo de producción.
No se envió ninguna transacción ni se reinició nada.

## Por qué importa

El primer sorteo del Jackpot V2 es el bloque **#30.186**. Para entrar en él un
minero necesita las tres cosas a la vez:

1. identidad SbPoW válida,
2. al menos 3 bloques propios en los últimos 2.016,
3. un **NODE_BIND activo**, es decir, una clave de nodo registrada en cadena.

El primer sorteo exige **cero latidos**: la rampa de latidos empieza después
(1/1 → 2/2 → 3/3) y se asienta en 3-de-4 desde el **#31.338**. No hay una
segunda bifurcación; es una sola regla contando épocas.

## Lo que ya está hecho

| Elemento | Estado | Evidencia |
|---|---|---|
| Clave de nodo generada | **HECHO** | `/etc/sost/node.key`, 65 bytes, modo `600 root:root` |
| Copia en el propio VPS | **HECHO** | `/root/sost-backups/node.key.20260923`, modo `600` |
| Copia cifrada fuera del VPS | **HECHO** | `sost-node-key-20260923.enc` en Windows, AES-256-CBC + PBKDF2-SHA512 con 1.000.000 de iteraciones; la frase de paso NO viaja con el fichero |
| Nodo en ejecución | **HECHO** | `sost-node` activo, binario `b253e4a9c352ea4b…` = v16.2.3 oficial |
| El binario admite la clave | **HECHO** | `--node-key-file <ruta>` y `--node-key <hex64>` presentes en la ayuda |
| Altura actual | 27.692 | faltan ~2.300 bloques para el #30.000 |

## Lo que falta, y por qué no lo he hecho

### 1. El nodo todavía no arranca con la clave

La línea de órdenes actual no incluye `--node-key-file`:

```
/opt/sost/build/sost-node --genesis genesis_block.json --chain chain.json \
  --rpc-user AdminNeoB --rpc-pass-file /etc/sost/rpc.pass \
  --profile mainnet --p2p-enc on --connect 127.0.0.1:1
```

Añadirla exige **reiniciar el nodo**, y eso no entra en una comprobación de
lectura. Queda pendiente de tu aprobación.

### 2. El registro en cadena es una transacción

`createnodebind` firma y difunde una transacción. Dijiste explícitamente que
esta tarea no envía ninguna, así que no se ha enviado.

### 3. El `sost-cli` del PATH está desactualizado

Hay dos:

```
/usr/local/bin/sost-cli     0e1781d9eeafbcea…   24 may 2026   ← el que encuentra el PATH
/opt/sost/build/sost-cli    489f43741437a08b…   v16.2.3 oficial
```

El de mayo **no tiene** `--mining-key-label` ni `createnodebind`, que son
justo las dos cosas que hacen falta aquí. La guía publicada dice v16.2.3, así
que el PATH del propio VPS contradice a la guía. Mientras no se corrija, todas
las órdenes de abajo llevan la ruta completa.

## Procedimiento, cuando lo autorices

Ventana recomendada: **después del bloque #29.900 y antes del #30.000**, la
misma que publica la guía de operador.

```bash
# 1. Arrancar el nodo con la clave (una sola vez; sobrevive a los reinicios)
sudo install -d -m 700 /etc/systemd/system/sost-node.service.d
sudo tee /etc/systemd/system/sost-node.service.d/30-node-key.conf >/dev/null <<'CONF'
[Service]
Environment=SOST_NODE_KEY_FILE=/etc/sost/node.key
CONF
# …y añadir --node-key-file $SOST_NODE_KEY_FILE a ExecStart.
sudo systemctl daemon-reload && sudo systemctl restart sost-node

# 2. Comprobar que el nodo la ha tomado (lectura)
/opt/sost/build/sost-cli --rpc-user AdminNeoB --rpc-pass-file /etc/sost/rpc.pass getinfo

# 3. Registrar el vínculo (ESTO SÍ ES UNA TRANSACCIÓN)
/opt/sost/build/sost-cli --rpc-user AdminNeoB --rpc-pass-file /etc/sost/rpc.pass \
  --mining-key-label "SOST CEX LIQUIDITY RESERVE" createnodebind

# 4. Confirmar que está en cadena antes del #30.186 (NO existe "getnodebinds")
#    La comprobación real es checkhistoricaljackpoteligibility sobre la dirección minera:
curl -s -X POST http://127.0.0.1/rpc --data \
  '{"jsonrpc":"2.0","id":1,"method":"checkhistoricaljackpoteligibility","params":["<DIRECCION_MINERA>"]}'
#    Debe pasar de "node_bound":false a "node_bound":true, y "reasons" quedar vacío.
```

Nota: **no existe un método `getnodebinds`**. El estado del vínculo se lee con
`checkhistoricaljackpoteligibility <address>` (campo `node_bound`), o con
`getjackpotv2audit` / `gethistoricaljackpotstatus` para la vista del sorteo.
Estos métodos de consulta son públicos por el proxy; `sendrawtransaction` es lo
único que el proxy deja pasar para escribir.

## Recuperación de la clave

Si se pierde `/etc/sost/node.key`:

1. `/root/sost-backups/node.key.20260923` en el propio VPS.
2. Si el VPS entero se pierde: el fichero `.enc` de Windows, con la frase de
   paso de 27 caracteres, que **no está en el pendrive** ni en este repositorio.

Perder la clave no cuesta fondos: cuesta el NODE_BIND, que habría que volver a
registrar con otra clave y otra transacción. Si eso ocurriera después del
#30.186, ese sorteo se pierde.
