# Redundancia de nodos antes de #30.000 — laboratorio de peers estáticos

Fecha: 2026-09-29 · mainnet en ~#28.495 · STRATO = único nodo público.

Pregunta: ¿pueden varios nodos SOST reales mantener la misma cadena **sin tocar
consenso ni el protocolo P2P**, y cuál es la forma menos arriesgada de añadir
redundancia a mainnet antes de #30.000?

Respuesta corta: **sí, con el binario oficial v16.3.0 y peers estáticos, pero
sólo con un watchdog de reinicio en cada nodo relay**. El código P2P actual tiene
un defecto que hace que un nodo que sólo retransmite (no mina) deje de recibir
bloques ~50 bloques después de conectarse. Los arreglos existen y pasan el lab,
pero requieren cambiar el nodo **emisor** (STRATO), así que quedan para después
de #30.000.

Distinciones que se mantienen en todo el documento: MINER ≠ NODE ·
BLOCK PRODUCER ≠ ACTIVE NODE · KNOWN ADDRESS ≠ ACTIVE NODE ·
CONNECTED PEER = ACTIVE EXTERNAL NODE.

---

## 1. Capacidades P2P actuales (código real, `src/sost-node.cpp`, idéntico en v16.3.0, `main` y producción)

| Aspecto | Qué hace el código |
|---|---|
| Peer saliente | `--connect host:port` (repetible). Si la lista está vacía, marca 4 semillas por defecto (sólo `seed.sostcore.com` resuelve, y es STRATO). |
| Peer entrante | Escucha en `--port` (19333) en todas las interfaces. Límites: 32 entrantes, 2 por IP, 30 s de cooldown por IP. |
| addnode / RPC de peers | **No existe.** Sólo `getpeerinfo` (lectura). No hay `addnode`/`disconnectnode`. |
| Descubrimiento | **No existe.** Mensajes: EKEY/VERS/VACK/GETB/BLCK/TXXX/PING/PONG/DONE/BCNN. No hay intercambio de direcciones. |
| Persistencia de peers | **No existe.** Tras reiniciar sólo conoce su `--connect`. |
| Reconexión | Cada 30 s, **sólo si el nodo tiene 0 peers**, re-marca toda la lista `--connect`. |
| Handshake | EKEY opcional (X25519 + ChaCha20), VERS con altura + hash génesis (génesis distinto → desconexión), VACK. |
| Identidad de nodo | No hay node-id. Un peer es su `ip:puerto`. Sin detección de auto-conexión (de ahí `20-no-self-connect.conf`). |
| Deduplicación | Ninguna entre conexiones: A→B y B→A son dos conexiones. |
| Timeouts | Sin timeout por inactividad. `connect()` sin timeout. Escritura: 5 s para vaciar el buffer. |
| Bans | Puntuación ≥ 100 → ban de 24 h por IP (sólo en memoria). |
| Relay de bloques | A todos los peers con handshake **excepto** los que cree "sincronizando" (`their_height < tip − 50`). |
| Relay de tx | A todos los peers con handshake salvo el origen. |

## 2. Método de peer estático (sin cambios de código)

Topología en **estrella** alrededor de STRATO: cada nodo nuevo lleva un único
`--connect seed.sostcore.com:19333` y **ningún** enlace entre nodos relay. Con un
solo destino, la regla "reconectar sólo con 0 peers" funciona: si STRATO se
reinicia, el relay se queda a 0 peers y re-marca en ≤ 30 s. STRATO no necesita
ningún cambio: acepta entrantes en 19333 desde hace meses.

## 3. Laboratorio

Código P2P **sin modificar** de v16.3.0 (commit `a69e7182`), compilado como
DEVNET_FAST (`Profile::DEV`) para poder minar bloques en segundos. Puertos
aislados 1896x/1996x. Cada proceso se lanza y se mata por PID. Scripts en
`tests/p2p-lab/` (rama `lab/p2p-static-peers`).

Además, sincronización real de mainnet con el **binario oficial** v16.3.0
(`304d056d…`, verificado contra la release): M1 carga una copia de la cadena de
STRATO y M2 sincroniza desde génesis sólo por P2P desde M1. Aislamiento: ambos
nodos llevan `--connect` explícito, así que nunca marcan las semillas.

### 3.1 Resultado con v16.3.0 sin modificar (A ← B ← C)

| Prueba | Resultado |
|---|---|
| Handshake cifrado A↔B, B↔C | ✅ |
| Propagación de bloques: el minero entrega sólo a A; B y C por P2P (2 saltos) | ✅ mismos hashes en **todas** las alturas |
| Transacción A → B → C: en el mempool de los tres antes de minarse, después minada y retirada de los tres | ✅ |
| Reinicio de B desde su `chain.json` + reconexión + puesta al día | ✅ |
| Peer inalcanzable al arrancar (`--connect` a un puerto muerto) | ✅ se ignora, arranca normal |
| Peer congelado (SIGSTOP 90 s) con el resto propagando | ✅ A y C siguen; B se pone al día al descongelarse |
| **+70 bloques con B y C conectados** | ❌ **B y C se congelan en h49** (2 de 2 ejecuciones) |
| Pérdida parcial (C con A y B; A cae y vuelve) | ❌ ni B ni C re-marcan a A; A queda aislado y extiende **su** cadena sola |
| Bloque retransmitido mientras C se pone al día | ❌ C queda **atascado para siempre** en h41 (A llegó a h161) |
| Nodo lanzado desde shell (no systemd) y un peer le cierra el socket | ❌ el proceso muere por SIGPIPE |

### 3.2 Los cuatro defectos (causa raíz verificada)

1. **Inanición del relay** (el que importa). `their_height` de un peer sólo se
   actualiza con su VERS (una vez) y con bloques que **nosotros aceptamos de él**.
   Un relay nunca origina bloques, así que el emisor lo recuerda con su altura de
   handshake y, 50 bloques después, `broadcast_block_to_peers()` lo salta como
   "sincronizando". Se queda conectado, sin avanzar y sin recuperarse.
   En mainnet: **~8 h después de conectar**. La prueba de versiones mixtas
   demuestra que el arreglo tiene que estar en el **emisor**:
   emisor oficial + receptor arreglado → h49; emisor arreglado + receptor oficial → h75.
2. **Callejón del huérfano.** Guardar un huérfano lo marca como "conocido". Al
   reprocesarlo cuando llega su padre, el filtro de duplicados de `process_block`
   devuelve `false` antes de validar. El huérfano ya se ha borrado del índice, así
   que se pierde, y cada bloque posterior se clasifica como fork de menos trabajo.
   Reproducción determinista con un peer sintético (`orphan_repro.sh`):
   orden 1,2,3,4,5 → h5; orden 1,3,2,4,5 → **h2 para siempre**; al reiniciar → h5.
3. **Re-marcado sólo a 0 peers**, y además con `g_peers_mu` tomado mientras
   `connect()` puede bloquear minutos contra un destino con DROP.
4. **SIGPIPE.** El nodo no lo ignora. En STRATO no afecta: systemd lo ignora por
   defecto (`IgnoreSIGPIPE=yes`, máscara `SigIgn 0x1000` comprobada en el proceso).
   Afecta a quien lance el nodo con `nohup`/`screen` (reproducido: exit 141).

Ninguno toca reglas de consenso: son el transporte, el relay y el reprocesado de
huérfanos. El camino de validación queda intacto.

### 3.3 Rama `lab/p2p-static-peers` (sobre v16.3.0, sólo `src/sost-node.cpp`, +63/−10)

| Arreglo | Cambio |
|---|---|
| Inanición | Un eco `BLCK` de un bloque que ya tenemos actualiza `their_height` del peer (el peer que lo envía lo tiene). Sin mensajes nuevos. |
| Huérfano | Olvidar el hash en `g_known_blocks` antes de reprocesarlo. |
| Re-marcado | Por destino configurado no conectado, fuera de `g_peers_mu`. |
| SIGPIPE | `signal(SIGPIPE, SIG_IGN)` al arrancar. |

Mismo lab, nodos **sin** máscara de SIGPIPE: **23/23**. Sin inanición tras +70
bloques, C y B re-marcan a A sin reinicios, no hay partición, el huérfano llega
a h5 y el nodo sobrevive al cierre de socket. La rama `integration/sec2-p2p-ibd`
ya corrige huérfano y SIGPIPE, pero **no la inanición** (mismo lab: h49).

### 3.4 Mitigación sin tocar STRATO: watchdog en cada relay

`sost-relay-watchdog.sh` (timer de 5 min): si la altura local va ≥ 2 bloques por
detrás de `https://sostcore.com/rpc/public` en dos comprobaciones seguidas,
reinicia **su propio** nodo, como mucho una vez cada 15 min. El reinicio vuelve a
enviar VERS, lo que resetea `their_height` en STRATO y lo pone al día por GETB.
También limpia los defectos 2 y 3. Nunca actúa sin referencia y deja las caídas
del proceso a systemd.

Lab con código **oficial** en los dos nodos: sin watchdog, B se congela en h49.
Con watchdog, B sigue a A hasta h200 con 3 reinicios y un retraso máximo de 14
bloques a ritmo de lab (≈ 1 bloque/5 s). A 600 s/bloque, el retraso esperado es
de uno o dos bloques unos 10–15 min, cada ~8 h.

### 3.5 Sincronización mainnet real (binario oficial)

M1 cargó la cadena de STRATO (h28.486, 458 MB) en **19 s**. M2 desde génesis
por P2P: **0 → 17.807 en 97 min**, frenando de ~3.700 a ~55 bloques/min; se paró
ahí para no quitar CPU al minero en vivo de la máquina. **11/11 alturas
muestreadas (incluidas 4.160, 5.038, 5.410, 7.100 y 12.000) idénticas en M2, M1 y la
RPC pública de mainnet, 0 rechazos.** Encaja con la medición limpia previa de
202 min génesis→punta con el binario oficial (commit 8e1bee2b). La ralentización se debe a que v16.3.0 reescribe
`chain.json` entero en cada bloque (O(N²), documentado en la rama sec2, que lo
reduce a ~25 min).
Conclusión práctica: un relay nuevo arranca antes con una **copia verificada de
la cadena** (tip comprobado contra la RPC pública) que por IBD.

## 4. Cambios necesarios para mainnet

**Antes de #30.000: ninguno en STRATO, ninguno en el protocolo, ninguno en el binario.**
Sólo infraestructura nueva en máquinas nuevas:

| | |
|---|---|
| Binario | `sost-node` oficial v16.3.0, sha256 `304d056d504960b4179543672f14bee28146788b985363a5e95d476cc6b1492e` (el instalador rechaza otro hash) |
| Génesis | `genesis_block.json` sha256 `4e66143cbb49574e2681cf44f4c94ab8f5246ed1b5880640dd9c3c8d3020cdd0` (igual que STRATO) |
| Cadena | copia de `/opt/sost/build/chain.json` de STRATO, con el tip comprobado contra la RPC pública, o IBD por P2P |
| Peer | `--connect seed.sostcore.com:19333` (único) |
| Puertos | P2P 19333 (abrir entrante en un VPS: convierte el relay en segunda semilla). RPC 18232 sólo en 127.0.0.1 |
| Firewall | entrante 19333/tcp. Nada más público. STRATO sin cambios (ya permite 19333, máx. 2 conexiones por IP) |
| Servicio | `sost-relay-node.service` (usuario `sost`, `ProtectSystem=strict`, `IgnoreSIGPIPE=yes`) + `sost-relay-watchdog.timer` |
| Minado | ninguno. **No apuntar mineros a un relay** mientras exista el defecto 1: un minero sobre un relay atrasado crearía forks |

Comportamiento esperado: el relay sincroniza y aparece en STRATO como peer
entrante con handshake. El Explorer pasa a UNIQUE NODES = 2 (`1 local · 1 external`)
sin cambios manuales: `getnetworksummary` agrupa peers por máquina y cuenta los
que tienen handshake. Matiz: el nodo enmascara los dos últimos octetos de cada
dirección, así que dos relays en el mismo /16 se contarían como uno. Usar
proveedores distintos lo evita, y además es lo que da redundancia real. Cada ~8 h el watchdog hace un reinicio de ~20 s.

Rollback: `install-relay-node.sh --uninstall` (para y borra las unidades) o
`systemctl disable --now sost-relay-watchdog.timer sost-relay-node`. En STRATO y
en la red no hay nada que deshacer: el relay sólo recibe y retransmite.

## 5. Recomendación

**Antes de #30.000**
1. Uno o dos nodos relay con el paquete `deploy/relay-node/` y el binario oficial,
   en máquinas **distintas de STRATO**. Uno en un VPS de otro proveedor o región
   aporta redundancia real y una segunda semilla alcanzable.
2. Sin mineros apuntando a los relays.
3. STRATO, V16, #30.000, NODE_BIND, firewall y `20-no-self-connect.conf` intactos.

**Después de #30.000**
1. Release sólo de nodo (v16.3.1) con los cuatro arreglos de `lab/p2p-static-peers`,
   desplegada **primero en STRATO** (el arreglo de inanición es del emisor).
   Después se retira el watchdog.
2. Persistencia de peers (`feat/peer-persistence`), para que un nodo que ya
   conectó una vez arranque sin STRATO.
3. Intercambio de direcciones con límites anti-envenenamiento
   (`feat/peer-discovery`, diseño + addrman de referencia). Queda en LAB hasta
   después del fork porque sí añade un mensaje al protocolo.

| | |
|---|---|
| CONSENSUS IMPACT | **NO** (ni el paquete ni los arreglos tocan validación, PoW, serialización ni emisión) |
| P2P PROTOCOL CHANGE | **NO** para el paquete ni para los 4 arreglos (sin mensajes nuevos). **SÍ** para el discovery futuro (ADDR), que queda en lab |
