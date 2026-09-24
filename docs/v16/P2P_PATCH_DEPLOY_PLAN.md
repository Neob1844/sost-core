# Parche P2P — plan de despliegue y reversión

Rama `fix/p2p-block-serving`. **No es un cambio de consenso.** No toca la
validación de bloques, la emisión, cASERT ni las 66 excepciones históricas ya
validadas. Cambia sólo el transporte P2P: cómo se sirven los bloques y el
contador anti-spam del receptor.

## Qué entra (3 ficheros, frente a `main`)

| Fichero | Qué cambia |
|---|---|
| `src/sost-node.cpp` | (1) al servir un lote GETB: no enviar nunca un bloque incompleto, cifrar el lote en conexiones cifradas, cortar al primer fallo; (2) `version` explícito en bloques pre-SbPoW; (3) las 47 excepciones de parámetros + las 19 de cASERT; (4) el límite de tasa por crédito de sincronización |
| `tools/casert_replay_scanner.cpp` | prueba permanente de las 19 divergencias cASERT |
| `tools/param_divergence_scan.py` | prueba permanente de las 47 divergencias de parámetros |

## Por qué es seguro desplegarlo sin coordinación de red

- **No es un fork.** Un nodo con el parche y un nodo sin él aceptan y rechazan
  exactamente los mismos bloques. Las excepciones históricas están por debajo
  del ancla `assumevalid` que ya usan todos, y sólo afectan a una sincronización
  desde génesis, no a la punta.
- **Interoperable en ambos sentidos.** Probado: cliente parcheado ↔ servidor
  parcheado, y también contra el binario de STRATO actual, cifrado y sin cifrar.
- **El cambio de `version` es de representación**, no de identidad: no altera
  ningún `block_id` (demostrado con la huella SHA-256 de los 26.974 ids).

## Despliegue (cuando lo autorices)

STRATO corre **un** nodo. El parche es compatible con el binario actual, así
que el orden no es crítico, pero lo prudente es:

```bash
# 1. Construir desde la rama, con las banderas obligatorias
git -C /opt/sost fetch origin fix/p2p-block-serving
git -C /opt/sost checkout fix/p2p-block-serving
cmake -S /opt/sost -B /opt/sost/build-p2p -DCMAKE_BUILD_TYPE=Release \
      -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=OFF
cmake --build /opt/sost/build-p2p -j4

# 2. Verificar el binario y las pruebas ANTES de sustituir nada
/opt/sost/build-p2p/sost-node --version
( cd /opt/sost/build-p2p && ctest -j2 )   # debe dar 119/119

# 3. Copia de seguridad del binario en producción (el oficial b253e4a9…)
cp /opt/sost/build/sost-node /opt/sost/rollback-p2p-$(date +%Y%m%d_%H%M%S)/sost-node

# 4. Parar el nodo POR SU PID (nunca por nombre), sustituir, arrancar
#    — con la ventana de mantenimiento anunciada; NO tocar el minero del usuario.
```

El nodo actual arranca con `--p2p-enc on --connect 127.0.0.1:1`; el parche
respeta ambos.

## Reversión

El parche no cambia el formato en disco de `chain.json` salvo por añadir el
campo `version` a bloques que no lo tenían. Ese campo lo entienden **los dos**
binarios (el actual ya lo infiere cuando falta), así que **la reversión es
simétrica y sin migración**:

```bash
# volver al binario oficial guardado en el paso 3
systemctl stop sost-node        # o kill <PID> del nodo, nunca pkill
cp /opt/sost/rollback-p2p-YYYYmmdd_HHMMSS/sost-node /opt/sost/build/sost-node
systemctl start sost-node
```

No hay estado que deshacer: la cadena que escribió el binario parcheado la lee
el oficial sin cambios (probado: los `chain.json` de ambos son byte a byte
idénticos salvo el `version` explícito, que el oficial acepta).

## Lo que NO arregla este parche, y queda anotado

Al inundar con bloques nuevos que no encadenan, un par consigue que el nodo los
**almacene como forks** (`Fork stored but has LESS cumulative work`) antes de
que el límite de tasa lo banee — hasta ~150 por conexión (100 de crédito + 50
de relevo), y podría reconectar. Es un vector de agotamiento de memoria por
forks, **preexistente e independiente del límite de tasa**, que este parche no
toca para no ampliar el alcance. Recomendación separada: acotar el número de
forks huérfanos retenidos por par o por debajo de un umbral de trabajo. No es
bloqueante para este despliegue.
