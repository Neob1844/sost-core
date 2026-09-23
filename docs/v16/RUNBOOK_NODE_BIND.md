# NODE_BIND — runbook probado (STRATO + minero WSL)

Estado a 2026-09-23, altura 27.661.

## Lo que ya está hecho

| | |
|---|---|
| Clave de identidad del nodo | creada, `/etc/sost/node.key` (600 root:root) |
| Copia recuperable | `/root/sost-backups/node.key.20260923` (600, dir 700) |
| Copia para firmar el bind | `~/.sost/node.key` en WSL (600 sost:sost), idéntica |
| `sost-cli` | v16.2.3 verificado, `489f4374…5e07d07` |
| Etiqueta minera | `SOST CEX LIQUIDITY RESERVE` — presente en la cartera real |
| Bloques SbPoW en ventana | **1.643** (mínimo exigido: 3) |
| Latidos exigidos para #30.186 | **0** (ninguna época completa aún) |
| `node_bound` | **false** ← lo único que falta |

La clave NO se ha registrado en la cadena: el registro no debe emitirse antes
de #30.000.

## Qué falta, y cuándo

**Esperar a que la cadena pase de #30.000.** Comprobación:

```bash
curl -s -X POST https://sostcore.com/rpc/public \
  -d '{"jsonrpc":"1.0","id":"a","method":"getblockcount","params":[]}'
```

### Paso 1 — construir la transacción de vinculación (en WSL)

```bash
cd ~/SOST/sostcore/sost-core
./build/sost-cli \
    --wallet /home/sost/sost-keys/cex-wallet.json \
    --mining-key-label "SOST CEX LIQUIDITY RESERVE" \
    createnodebind 1 --node-key-file ~/.sost/node.key
```

Imprime en stderr la clave minera que vincula y en stdout **352 caracteres hex**.
La etiqueta debe ser exactamente esa: si no existe, el comando se niega y lista
las etiquetas de la cartera en vez de vincular la clave equivocada.

`1` es `bind_seq`, el primero. Sólo sube si en el futuro se cambia de clave de nodo.

### Paso 2 — difundirla

```bash
curl -s -X POST https://sostcore.com/rpc/public \
  -d '{"jsonrpc":"1.0","id":"a","method":"sendrawtransaction","params":["<HEX>"]}'
```

Devuelve el txid. Si NO devuelve un txid, **no volver a enviarla a ciegas**:
mirar antes `getrawmempool`.

### Paso 3 — esperar a que entre en un bloque

```bash
curl -s -X POST https://sostcore.com/rpc/public \
  -d '{"jsonrpc":"1.0","id":"a","method":"getrawtransaction","params":["<TXID>"]}'
```

### Paso 4 — que el nodo emita latidos por sí mismo

Añadir `--node-key-file /etc/sost/node.key` al ExecStart y reiniciar **sólo el
nodo** (~4 s; el minero no se toca):

```bash
ssh root@<vps> 'systemctl edit sost-node --full'   # o editar el drop-in
ssh root@<vps> 'systemctl daemon-reload && systemctl restart sost-node'
ssh root@<vps> 'grep -a "auto-heartbeat" /var/log/sost-node.log | tail -2'
```

Debe aparecer `[NODE-HEARTBEAT] auto-heartbeat enabled for node pubkey …`.

### Paso 5 — verificación (la prueba real)

```bash
curl -s -X POST https://sostcore.com/rpc/public -d '{"jsonrpc":"1.0","id":"a",
 "method":"checkhistoricaljackpoteligibility",
 "params":["sost1ad01a1ce3ae7d0dbcc1baae7a11e9ecde28683a2"]}'
```

Hoy responde:

```json
{"node_bound":false,"pow_blocks":1643,"pow_minimum":3,
 "heartbeats_valid":0,"heartbeats_required":0,
 "eligible":false,"reasons":["not_node_bound"]}
```

Tras el registro debe responder `"node_bound":true`, `"reasons":[]` y
`"eligible":true`. **Esa es la comprobación que hay que hacer antes de #30.186**,
no suponerlo por haber enviado la transacción.

## Lo que ya se probó (con cartera desechable, la real no se tocó)

| Prueba | Resultado |
|---|---|
| Etiqueta correcta | produce 352 hex y nombra la clave vinculada |
| Etiqueta inexistente | se niega y lista las etiquetas de la cartera |
| Fichero de clave en modo 644 | se niega a leer el secreto |
| Dos ejecuciones seguidas | hex idéntico (determinista) |

## Avisos

- **No** usar la forma posicional `createnodebind 1 <hex>`: deja la clave privada
  del nodo visible en `ps` para cualquier usuario local. El propio comando avisa.
- La clave de nodo **no** es la clave de minado y **no** mueve fondos; identifica
  al nodo. Aun así, quien la tenga puede suplantar los latidos: mantener 600.
- Si se pierde la clave de nodo, se genera otra y se registra con `bind_seq 2`.
