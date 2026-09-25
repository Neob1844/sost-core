# Informe de aceptación — Endurecimiento de seguridad (no-consenso) sobre v16.3.0

Rama: `feat/fork-store-hardening` · candidato de release de endurecimiento, **no desplegado**.
Veredicto: **APTO para producción** (sync cerrada en verde; sin bloqueantes técnicos).
Objetivo: decidir si la versión endurecida está lista para producción **sin cambiar el consenso**
(activación, emisión, SbPoW, DTD, NODE_BIND, Jackpot intactos).

## 1. Alcance y garantía de no-consenso

- Ficheros de consenso tocados: **0** (`params.h`, `block_validation.h`, `consensus_constants.h`,
  `checkpoints.h` sin cambios). Verificado por diff.
- Todos los cambios son de **disponibilidad / robustez de red / límites de memoria**.
- Interoperabilidad con v16.3.0 confirmada en ambos sentidos, cifrado y claro.

## 2. Hallazgos y correcciones (ANTES / DESPUÉS)

| ID | Vulnerabilidad | ANTES | DESPUÉS | Consenso | Commit |
|----|----------------|-------|---------|----------|--------|
| V1 | Envenenamiento del índice de forks (DoS de memoria; forks/huérfanos guardados antes de validar CX) | Atacante multi-IP llena 1000 entradas → un fork honesto **NO entra** | Cuota por IP + por /24 con **eviction**; el fork honesto **SÍ entra**, memoria acotada | No | 0e907618 |
| V2 | Mezcla de entradas ACTIVE con forks bajo el mismo tope; nodo longevo deja de guardar forks | Tope compartido ACTIVE+fork, sin poda en runtime | Contabilidad de sólo-transitorios como fuente de verdad; ACTIVE excluido del tope | No | 0e907618 |
| V3 | Falso positivo de subred: peer honesto tras el mismo NAT/VPN que atacantes era bloqueado | Peer honesto en la **misma /24** que atacantes → **bloqueado** | Eviction del más antiguo de la propia subred en vez de rechazo duro → honesto **entra** | No | 533f4aef |
| V4 | Sin CI de seguridad (consenso/ASan/UBSan/fuzz) | No existía workflow | GitHub Actions **verde**: unit+consenso, ASan/UBSan, fuzz-smoke (libsecp256k1 con schnorrsig) | No | 86dfee03 / a6148f2b / 941a952d |
| V5 | Superficie de deserialización sin fuzzing | Sin fuzzers | tx/bloque **>23 M ejec., 0 crashes**; corpus conservado | No | 86dfee03 |
| **V6** | **SIGPIPE no ignorado → DoS de disponibilidad** | Bajo churn+flood el nodo **muere en ~6 s** (Broken pipe, 0 crash en log = muerte por señal) | `signal(SIGPIPE, SIG_IGN)`; **sobrevive 45 s**, RSS estable, sigue aceptando forks | No | 20e009f9 |

⚠️ **v16.3.0 y STRATO en producción contienen V6.** La corrección debe viajar en esta release de endurecimiento.

## 3. Verificaciones ejecutadas

| Verificación | Resultado |
|---|---|
| V1 antes/después (poisoning) | ✅ envenenado→NO entra; endurecido→SÍ |
| V3 honesto misma /24 que atacantes | ✅ entra (eviction de subred) |
| V6 DoS SIGPIPE (laboratorio Fase D) | ✅ antes 6 s→muerte; después 45 s→vivo |
| Reorg de mayor trabajo E2E (binario endurecido, devnet) | ✅ reorganiza; estado == limpio |
| Suite completa de tests (×3, tras cada cambio; última tras V6) | ✅ **119/119**, 0 fallos, ~78 s |
| Workflow en GitHub Actions | ✅ verde (unit+consenso, ASan/UBSan, fuzz) |
| Fuzzing tx/bloque | ✅ >23 M ejec., 0 hallazgos |
| Fuzzing framing P2P (mirror de `try_parse_message`) | ✅ 186k ejec./76 s, cov saturada, 0 crashes; corpus conservado |
| Interoperabilidad v16.3.0 ↔ endurecido (cifrado y claro) | ✅ 4 direcciones, 0 rechazos |
| Sync completa génesis→punta (hashes + estado UTXO) | ✅ **8/8 hashes MATCH** (0,1,5038,10k,15k,20k,25k,punta) + UTXO idéntico |

## 4. Sincronización completa (CERRADA — VERDE)

Dos nodos endurecidos (P2P cifrado y en claro) sincronizaron desde génesis contra un nodo de
referencia hasta la punta actual **26.973**, con **0 rechazos y 0 baneos** en todo el trayecto.

**Comparación de hash de bloque por altura** (referencia vs cifrado vs claro):

| Altura | Hash (16 hex) | Veredicto |
|---|---|---|
| 0 (génesis) | `6517916b98ab9f80` | MATCH |
| 1 | `02cd911caffad16b` | MATCH |
| 5038 (borde tabla de excepciones) | `4556ac446a5d7be6` | MATCH |
| 10000 | `a6f59f1f2f0e6b03` | MATCH |
| 15000 | `4a8ddb8df0ddd9a4` | MATCH |
| 20000 | `5907d3b39eee2ce8` | MATCH |
| 25000 | `a8fb4673dee26c93` | MATCH |
| 26973 (punta) | `f4e28b935fdcbd28` | MATCH |

**Estado UTXO** (los tres nodos, idéntico): `utxo_count = 66239`, `total_supply = 211773.10678562`
(gold_vault, popc_pool, dtd_lottery y circulating también coinciden byte a byte via `getsupplyinfo`).

**Sello con el binario DEFINITIVO** (el que corrió la sync precedía a V6+subred): el binario final
`sost-node` sha256 `12e1f0b3cadaec5e…` (con V6 y eviction por subred) cargó y validó la misma cadena
persistida y reprodujo **exactamente** la referencia — punta `f4e28b935fdcbd28…`, `utxo_count = 66239`,
`total_supply = 211773.10678562`. Confirmado que V6 (`signal` en `main`) y la eviction por subred (sólo
el *store* de forks transitorios) **no alteran la ruta de validación/conexión** de bloques.

_Conclusión §4: la versión endurecida produce una cadena y un estado UTXO idénticos bit a bit a la
referencia._


## 5. Recomendación

- **Los seis hallazgos están corregidos y verificados**; ninguno toca consenso; 119/119 en verde.
- V6 es motivo suficiente por sí solo para publicar la release de endurecimiento (producción es
  vulnerable a un DoS trivial de disponibilidad).
- **Sync completa CERRADA en verde** (§4): 8/8 hashes MATCH + UTXO idéntico, sellado además con el
  binario definitivo (V6+subred, sha `12e1f0b3`). **No quedan bloqueantes técnicos** para el veredicto.
- **Fuera de alcance de esta release** (registrado en el masterplan, fases A–H): fuzzers restantes
  (mempool/NODE_BIND/latidos/Jackpot), laboratorio masivo a escala de cientos de peers,
  invariantes monetarios, modelo de referencia property-based, eclipse/particiones, builds
  reproducibles/firma. Nada de esto bloquea la release de endurecimiento no-consenso.

_Sin merge a main. Sin desplegar. STRATO, minero de usuario y reglas de consenso intactos._
