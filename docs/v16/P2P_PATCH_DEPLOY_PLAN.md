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

## Binario preparado (para verificar tras construir)

Construido desde la rama con las banderas obligatorias
(`-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=OFF`,
Release). El hash completo del ejecutable varía con la metainformación de
compilación (ruta, timestamp), pero las secciones de código (`.text`) y de datos
de sólo lectura (`.rodata`) son idénticas a las del binario que superó la
sincronización completa desde génesis. Referencia de esta preparación:

```
29ada78fa687336181db4b5f54f05c5dcd649bfdd6d19a98f2ca6c5a6a48df86  sost-node
3e3b79f7b07df7f7bdd431e4e5fcf5a8faf822c773b53b1287224686430d37c2  sost-cli
```

Verificación de que NO cambia el minero ni las reglas de bloques nuevos:
- El diff toca `src/sost-node.cpp` (sólo lo enlaza el nodo) y dos herramientas
  standalone; NO toca `src/sost-miner.cpp` ni ninguna de las 25 fuentes de la
  biblioteca `sost-core`, así que el binario del minero es el mismo.
- Las dos tablas de excepción tienen corte duro por altura: cASERT ≤ 5.410,
  parámetros ≤ 5.038, ambos ~21.500 bloques por debajo de la punta (26.973) y
  bajo el ancla `assumevalid` (3.554). No pueden dispararse en un bloque nuevo.
- El cambio del límite de tasa no añade ninguna llamada a la validación de
  consenso (`process_block`, `verify_cx`, `casert_*`, `subsidy`, `merkle`,
  `coinbase`): es sólo el contador anti-spam del transporte.

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

## Despliegue ejecutado — 2026-09-24

Instalado en STRATO el commit `cfcfe9df` (`main`). Binario del nodo compilado en
el propio VPS con las banderas obligatorias:

```
caef71a3bfaac317b31d47cbafdec7454e26247cb3d11677b612ff84613f26f4   sost-node  (nativo VPS, cfcfe9df)
```

(El hash difiere del binario compilado en WSL — `29ada78f…` — sólo por el
toolchain; mismo commit. 10/10 pruebas de consenso pasaron en el binario nativo
del VPS antes de instalar.) Altura previa 27803 → nodo recuperado en 27803 con
el mismo tip, 67703 UTXOs, RPC y P2P activos, 0 baneos por tasa. Backup oficial
en la ruta exacta de la sección de Reversión.

## Reversión (ruta exacta, sin comodín)

El despliegue del 2026-09-24 guardó el binario oficial en una **ruta fija**, con
su hash y verificado byte a byte:

```
/opt/sost/rollback-p2p-20260924_201231/sost-node.official
  b253e4a9c352ea4b8557eec78d57e1c7619ab267af228c3e8f24bf8d7b69b897   (= v16.2.3 oficial)
```

Para volver al binario oficial (comprobando el hash ANTES de arrancar):

```bash
BK=/opt/sost/rollback-p2p-20260924_201231/sost-node.official   # ruta exacta
TARGET=/opt/sost/build/sost-node
# 1. comprobar que el backup sigue íntegro
sha256sum -c /opt/sost/rollback-p2p-20260924_201231/SHA256.orig
# 2. parar SÓLO el nodo (por servicio; nunca pkill)
systemctl stop sost-node
# 3. restaurar y verificar el hash del binario ya instalado
cp -a "$BK" "$TARGET"
test "$(sha256sum "$TARGET" | awk '{print $1}')" = \
     "b253e4a9c352ea4b8557eec78d57e1c7619ab267af228c3e8f24bf8d7b69b897" \
     && echo "restauración verificada" || { echo "HASH NO COINCIDE"; exit 1; }
# 4. arrancar
systemctl start sost-node
```

No hay estado que deshacer: la cadena que escribió el binario parcheado la lee
el oficial sin cambios (el campo `version` explícito ya lo infiere).

## Lo que NO arregla este parche, y queda anotado

Al inundar con bloques nuevos que no encadenan, un par consigue que el nodo los
**almacene como forks** (`Fork stored but has LESS cumulative work`) antes de
que el límite de tasa lo banee — hasta ~150 por conexión (100 de crédito + 50
de relevo), y podría reconectar. Es un vector de agotamiento de memoria por
forks, **preexistente e independiente del límite de tasa**, que este parche no
toca para no ampliar el alcance. Recomendación separada: acotar el número de
forks huérfanos retenidos por par o por debajo de un umbral de trabajo. No es
bloqueante para este despliegue.
