# Informe de aceptación — Endurecimiento de seguridad (no-consenso) sobre v16.3.0

Rama: `feat/fork-store-hardening` · candidato de release de endurecimiento, **no desplegado**.
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
| Sync completa génesis→punta (hashes + estado UTXO) | ⏳ EN CURSO — se cierra abajo |

## 4. Sincronización completa (pendiente de cierre)

Dos nodos endurecidos (uno con P2P cifrado, otro en claro) sincronizan desde génesis contra un
nodo de referencia en la punta actual (26.973). Al alcanzar la punta se comparan hash de bloque
por altura y estado UTXO. Estado al momento de escribir: en progreso, **0 rechazos, 0 baneos**.

> _Fila a completar cuando el monitor confirme `enc==plain==26973`:_
> - Hash de punta endurecido (cifrado): `____` · (claro): `____` · referencia: `____` → MATCH?
> - Recuento UTXO / hash de conjunto UTXO endurecido vs referencia → MATCH?

## 5. Recomendación

- **Los seis hallazgos están corregidos y verificados**; ninguno toca consenso; 119/119 en verde.
- V6 es motivo suficiente por sí solo para publicar la release de endurecimiento (producción es
  vulnerable a un DoS trivial de disponibilidad).
- **Bloqueante restante para el veredicto de producción**: cierre de la sync completa (§4) con el
  binario definitivo. El binario que corre la sync actual precede a V6 y al fix de subred, que **no
  tocan la ruta de sincronización**; aun así, para el sello final se re-verifica que el binario
  definitivo produce el mismo hash de punta.
- **Fuera de alcance de esta release** (registrado en el masterplan, fases A–H): fuzzers restantes
  (mempool/NODE_BIND/latidos/Jackpot), laboratorio masivo a escala de cientos de peers,
  invariantes monetarios, modelo de referencia property-based, eclipse/particiones, builds
  reproducibles/firma. Nada de esto bloquea la release de endurecimiento no-consenso.

_Sin merge a main. Sin desplegar. STRATO, minero de usuario y reglas de consenso intactos._
