# SOST Security Masterplan — el "Security Gauntlet"

Programa integral de endurecimiento previo a #30.000. Todo el trabajo va en ramas
de desarrollo, sin tocar main, producción, el minero ni las reglas de consenso.
Regla de oro: **nada se marca COMPLETADO si sólo está PREPARADO.**

Estados: `HECHO+VERIFICADO` · `PREPARADO` (escrito, no ejecutado) · `PENDIENTE`.
Última actualización: 2026-09-25. Referencia estable: **v16.3.0** (nodo 304d056d).
Rama de esta fase: `feat/fork-store-hardening` (publicada en GitHub, sin merge).

## Fase 1 — V1–V5 (fork-store hardening + herramientas)

| # | Mejora | Estado | Consenso | Commit | Pruebas | Riesgo residual |
|---|---|---|---|---|---|---|
| V1 | Índice de forks: cuota por origen + admisión validada | **HECHO+VERIFICADO** | No | 0e907618 | Regresión antes/después: envenenado→honesto NO entra; endurecido→SÍ entra | Ninguno conocido en este vector |
| V2 | Límite de bytes global (96 MB) + por origen (8 MB) | **HECHO+VERIFICADO** | No | 0e907618 | RAM estable ~10–12 MB bajo flood, sin OOM | Falta el peor caso con bloques de 1 MB (medición pendiente) |
| V3 | Cuota por /24 con **eviction de subred** (no bloquea honestos NAT/VPN) | **HECHO+VERIFICADO** | No | 533f4aef | Honesto misma /24 que atacantes → ENTRA; memoria acotada | Un atacante puede rotar su propia cuota (sin crecer memoria) |
| V4 | CI: ASan/UBSan/TSan + fuzz-smoke + ctest como gate | **HECHO+VERIFICADO** | No | 941a952d | Workflow ejecutado en GitHub Actions: unit-and-consensus ✓, asan-ubsan ✓, fuzz-smoke ✓ | btc-*/checkpoints excluidos (infra externa / config de entorno) |
| V5 | Fuzzer de tx/bloque (deserializadores) | **HECHO+VERIFICADO** | No | 86dfee03 | >23 M ejecuciones, 0 crashes, 0 hallazgos ASan/UBSan; corpus conservado | Cobertura saturada en cov:47; faltan fuzzers de más superficie (fase A) |
| **V6** | **SIGPIPE ignorado** — DoS de disponibilidad (crash del nodo por churn) | **HECHO+VERIFICADO** | No | 20e009f9 | ANTES: muere en 6 s (Broken pipe). DESPUÉS: vive 45 s bajo churn+flood, RSS estable. Regresión v6_sigpipe_dos.sh | **v16.3.0 y STRATO tienen este bug** — debe ir en la release de endurecimiento |

**Bug latente arreglado (no-consenso):** el cap de forks mezclaba entradas ACTIVE
(sin poda) con forks; ahora cuenta sólo transitorios.
**Reorg E2E:** verificada con el binario endurecido (arnés devnet): un fork con más
trabajo reorganiza, desconecta el jackpot viejo, conecta el nuevo y el estado
resultante == estado limpio.
**Sync desde génesis:** **HECHO+VERIFICADO** hasta la punta 26.973 con el binario
endurecido (cifrado y claro): 8/8 hashes de bloque MATCH + estado UTXO idéntico
(utxo_count 66239, supply 211773.10678562), 0 rechazos. Sellado además con el
binario definitivo (V6+subred, sha 12e1f0b3) que reproduce la referencia. Detalle
en docs/security/ACCEPTANCE_V16_HARDENING.md §4.
**Interoperabilidad v16.3.0 ↔ endurecido:** 0 rechazos en ambas direcciones,
cifrado y sin cifrar.

## Fases pendientes (registradas para no perderlas)

| Fase | Trabajo | Estado | Prioridad | Consenso |
|---|---|---|---|---|
| **A** | Fuzzing integral: **P2P framing/handshake**, mempool, RPC, SbPoW, NODE_BIND, heartbeats, Jackpot | PENDIENTE | Alta | No (tooling) |
| **B** | Auditoría de aritmética segura e **invariantes monetarias** (inflación, inputs duplicados, RBF, DTD, Jackpot, reservas) con tests adversariales | PENDIENTE (base ya existe: subsidy check, guards de overflow) | Alta | No (tests) |
| **C** | **Property-based testing** + **implementación de referencia independiente** (Python) para differential testing del consenso C++ | PENDIENTE | Media | No (tests) |
| **D** | **Laboratorio de ataques masivos**: flood P2P, forks, huérfanos, churn, mempool, double-spend, eclipse, Sybil, particiones, reorgs, ataques de Jackpot | **INICIADO** (adversarial_lab.sh; churn+fork-storm ejecutado y encontró V6). Falta: escalar a cientos de peers, mempool/double-spend/eclipse/particiones, instrumentación fiable de recursos | Alta | No |
| **E** | **Chaos testing**: kill -9 en escrituras/reorgs, disco lleno, ficheros truncados, reinicios, recuperación | PENDIENTE | Media | No |
| **F** | CPU-DoS: orden barato-antes-de-caro, límites de parsers, **diversidad de peers**, mitigación de eclipse | PENDIENTE (S2 sospecha sin cuantificar) | Media | No |
| **G** | **Builds reproducibles** independientes de la ruta, releases firmadas, manifiestos/SBOM, dependencias verificadas, **endurecimiento systemd de STRATO** (mínimo privilegio) | PENDIENTE | Media | No |
| **H** | **SOST Security Gauntlet**: `tests/security-gauntlet.sh` que ejecute todo lo anterior de forma reproducible con puertas obligatorias | PENDIENTE | Alta | No |

### Sospechas abiertas (a cuantificar)
- **S1** double-spend en RBF / cadenas de dependencia del mempool — fuzzing + property tests (fase B/C).
- **S2** CPU-DoS por orden de validación — auditar cada ruta (fase F).
- **Test frágil** `test-checkpoints`: depende de config de assumevalid dinámica del
  entorno; hacerlo determinista (fase C).

### Regla para #30.000
Sólo entra en el fork de #30.000 una corrección de **consenso** con vulnerabilidad
reproducible, corrección probada y análisis de compatibilidad, y con autorización
explícita. Todo lo NO-consenso (V1–V5 y fases A–H) se distribuye antes, compatible
con v16.3.0, sin fork.


## Revisión de seguridad "sec1" de v16.3.0 (NODE-ONLY, NON-CONSENSUS) — VERIFICADA, sin publicar

Commit congelado **1a675744** (rama feat/fork-store-hardening), base v16.3.0 (ec2bea2c).
NO es v16.3.1: se incorpora a la Release v16.3.0 existente como revisión "sec1" (tag v16.3.0 sin mover, originales conservados). Empaqueta V1–V6 + P4. Solo cambia `sost-node`
(d3212aea); `sost-miner` (2ef9d0a7) y `sost-cli` (489f4374) byte-idénticos a v16.3.0.

- Diff vs v16.3.0: solo src/sost-node.cpp; 0 ficheros de consenso; no cambia
  emisión/SbPoW/DTD/NODE_BIND/Jackpot/#30.000.
- SIGPIPE/EPIPE/escrituras: auditado (write_exact devuelve false en EPIPE).
- Campaña prolongada 300 s: vivo, CPU 24%, RSS 482 MB, RPC 52 ms, fork store 150,
  recupera; v16.3.0 muere en ~6 s.
- ASan/UBSan + 119 tests: 0 hallazgos de memoria. GitHub Actions 1a675744: verde.
- Fuzzer sobre el parser de producción real (p2p_frame.h): 0 crashes.
- Sync génesis→26.973 con el binario definitivo: 9/9 hashes + UTXO idénticos.
  Interop v16.3.1↔v16.3.0 cifrado/claro: 0 rechazos.
- Residual (NO bloqueante, fuera del hotfix): test unit `checkpoints` contradice el
  ancla assumevalid 3554 ya presente en v16.3.0 (arreglar el test aparte); huecos de
  CI (TSan, fuzzer P2P gated, checkpoints/btc-watch) al masterplan.
- Test de checkpoints corregido (CHECK activa en Debug+Release, ancla 3554); suite 119/119 en Release y Debug/ASan.
- Entregables: docs/security/V16_3_0_SEC1_{RELEASE,ACCEPTANCE,INCORPORATION}.md, docs/v16/SHA256SUMS.v16.3.0-sec1. Estado: **APTA, pendiente de autorización para incorporar a la Release v16.3.0.**

## Fase C — estado real (ejecutado)
- subsidy/emisión: modelo bit-exacto independiente, 0 divergencias vs C++ (30.307 alturas) y == cadena real. **HECHO**.
- invariantes monetarias I1-I6: **HECHO** (30.245 alturas + identidad vs C++).
- cASERT: el sim Python existente es de comportamiento (parity validator: LOW confidence, 2 divergencias HIGH). Modelo bit-exacto independiente de cASERT = **PENDIENTE** (grande; no marcado como superado).
- DTD/Jackpot/NODE_BIND/heartbeat/UTXO transition: **PENDIENTE**.

## sec1 sync CERRADO EN VERDE (binario FINAL d3212aea)
9/9 hashes MATCH + UTXO 66239 + emision 21177310678562 idénticos vs referencia; cifrado+claro; 0 rechazos. sec1 = APTA (pendiente solo tu autorización de publicación). Tiempo end-to-end 5h03m CONTAMINADO (medición limpia pendiente).
