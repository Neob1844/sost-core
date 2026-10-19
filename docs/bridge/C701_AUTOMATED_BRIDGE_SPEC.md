# C701 — SOST Automated Bridge, Gold Access Key y Gold Reserve V2

**Estado:** especificación de DESARROLLO. Nada desplegado (ni mainnet, ni testnet pública, ni web).
**Veredicto de producción:** NOT_READY (ver §12). Este documento describe exactamente lo que el
código de la rama `feat/c701-automated-bridge` hace y lo que todavía no hace.

Código:

| Pieza | Ruta |
|---|---|
| Contrato del puente | `contracts/bridge/src/SOSTBridge.sol` |
| Token wSOST | `contracts/bridge/src/WSOST.sol` |
| Matemática Gold Access Key | `contracts/bridge/src/GoldAccessKey.sol` y `ops/c701bridge/fee.py` (idénticas) |
| Gold Reserve V2 / Quarantine Vault | `contracts/bridge/src/GoldReserveV2.sol`, `QuarantineVault.sol`, `ReserveBase.sol` |
| Motor de verificación (prototipo) | `ops/c701bridge/` |
| Tests | `contracts/bridge/test/`, `tests/c701bridge/` |

---

## 1. Alcance: solo dos servicios

1. **SOST Bridge** — SOST nativo ↔ wSOST (Ethereum), 1:1. Es lo que especifica este documento.
2. **SOST Atomic Swap** — servicio P2P independiente (HTLC). No incluye el par SOST↔wSOST, no cobra
   Gold Access Key y no toca Gold Reserve V2. El contrato `AtomicSwapHTLCv2` NO se reutiliza para el
   puente (problema conocido K-1: `claimNative` sin comprobación `token == 0`).

Explícitamente fuera de alcance (y retirado como arquitectura objetivo): pool de liquidez, mercado
interno wSOST/XAUT, venta de wSOST desde tesorería («Gold → wSOST desk»), conversión de comisiones
wSOST a oro, escrow personal de XAUT con caducidad, red de observadores federados (el diseño 2-de-3
observadores de las ramas `feat/wsost-*` queda como **histórico**), gestión manual de solicitudes.

## 2. Invariantes

```
1 SOST nativo bloqueado en el Bridge Vault  =  1 wSOST emitido
La aportación XAUT NUNCA reduce la cantidad emitida (se paga aparte, en XAUT)
Quemar N wSOST  ->  derecho a liberar N SOST (menos la comisión de red SOST de la tx de liberación, publicada)
Nunca se emite wSOST sin depósito nativo confirmado
Nunca se crea SOST nativo; nunca se quema SOST nativo
DTD Jackpot, Gold Vault histórico y PoPC: jamás se tocan
```

## 3. Arquitectura

```
 USUARIO (wallet SOST)                MOTOR C701 (operador)                 ETHEREUM
 1 crea solicitud  ───────────────▶  requestId = keccak(chainId, contrato,
                                      destinatario, cantidad, vault, salt)
 2 envía N SOST al Bridge Vault  ───▶ 3 detecta (getaddressutxos del vault)
   con cápsula "C701:0x<requestId>"   4 verifica (§5)
   en LA MISMA salida                 5 firma EIP-712 MintAuthorization
                                        + PriceQuote (clave de precio separada)
 6 MetaMask: approve XAUT + mint() ◀──────────────────────────────────────▶ SOSTBridge.mint():
                                                                              verifica firmas, precio,
                                                                              recalcula la comisión,
                                                                              XAUT usuario -> Gold Reserve V2,
                                                                              emite N wSOST   (UNA tx)
 7 la interfaz muestra: txid SOST, tx Ethereum, comisión, justificante (eventos BridgeMinted + GoldAccessKeyPaid)
```

Retorno:

```
 titular wSOST (cualquiera, también comprado en exchange)
   burnForRelease(N, "sost1…")  ──▶ evento BurnedForRelease(releaseId)   (sin pago XAUT)
 motor: ingiere el evento (idempotente) -> instrucción de liberación para el FIRMANTE FRÍO del vault
   tx SOST vault -> sost1… por N - comisión de red, con cápsula "C701R:0x<releaseId>"
 motor: verifica la tx en SOST (≥ minConfirmations, importe exacto, cápsula, entradas del vault)
   -> recordRelease(releaseId, txid) en Ethereum (registro público, idempotente)
```

### 3.1 Vinculación del depósito: cápsula (elegida) vs solicitud prefirmada

Se elige **cápsula SCPv1 open-note en la propia salida del depósito** (`C701:0x` + 64 hex = 71 de 80
bytes; cápsulas activas en mainnet desde #7.350, sin cambio de consenso). Motivos:

- La firma SOST del depositante sobre la transacción autentica el compromiso con `requestId`, y éste
  es un hash público y recomputable de (chainId, contrato, destinatario Ethereum, cantidad, vault,
  salt). El operador no puede redirigir el depósito a otro destinatario sin que el hash deje de cuadrar.
- Una solicitud prefirmada fuera de cadena dependería de la base de datos del operador; la cápsula
  queda en la cadena SOST para siempre y cualquiera puede re-verificarla.
- Un hash tecleado por el usuario NO es prueba: `lookup_hint` solo busca; la verificación siempre se
  rehace contra el nodo.

Límite reconocido: el wallet SOST debe poder poner la cápsula (sost-cli `--capsule-mode open-note`
existe). Si el usuario envía sin cápsula o con otra cápsula, el depósito queda *unbound* → recuperación (§8).

## 4. Gold Access Key

```
feeEUR  = min(50, max(0.50, bridgeValueEUR × 0.001))
feeXAUT = feeEUR / verifiedXAUTPriceEUR        redondeo HACIA ARRIBA a 6 decimales (1e-6 XAUT)
operación mínima 100 EUR (inferiores: rechazadas, no se ejecutan)
100 % a Gold Reserve V2 · gas Ethereum a cargo del usuario · retorno sin segundo peaje XAUT
```

- **XAUT = 6 decimales**, verificado (Etherscan, contrato oficial 0x68749665FF8D2d112Fa859AA293F07A622782F38,
  «Token Contract (WITH 6 Decimals)», proxy EIP-1967 actualizable por el emisor).
- Implementación: enteros escalados 1e8 (EUR8); el valor del puente se lleva como racional exacto
  `vNum/vDen` (`amount × sostEur8 / 1e8`), un único redondeo final (techo). El contrato **recalcula**
  la comisión y exige `feeXaut` firmado == recalculado.
- La comisión se transfiere `transferFrom(usuario → GoldReserveV2)` y se exige que el saldo de la
  reserva suba exactamente `fee` (rechaza tokens con comisión de transferencia).

Tabla (1 XAUT = 3.713,13 EUR, valor fijo ilustrativo del 2026-10-19, NO es cotización):

| Valor (EUR) | Comisión EUR | XAUT (6 dec, techo) | Estado |
|---:|---:|---:|---|
| 0 | — | — | RECHAZADA (< 100 EUR) |
| 10 | — | — | RECHAZADA |
| 50 | — | — | RECHAZADA |
| 100 | 0,50 | 0,000135 | OK |
| 250 | 0,50 | 0,000135 | OK |
| 500 | 0,50 | 0,000135 | OK |
| 750 | 0,75 | 0,000202 | OK |
| 1.000 | 1,00 | 0,000270 | OK |
| 1.500 | 1,50 | 0,000404 | OK |
| 2.000 | 2,00 | 0,000539 | OK |
| 3.000 | 3,00 | 0,000808 | OK |
| 5.000 | 5,00 | 0,001347 | OK |
| 7.500 | 7,50 | 0,002020 | OK |
| 10.000 | 10,00 | 0,002694 | OK |
| 15.000 | 15,00 | 0,004040 | OK |
| 25.000 | 25,00 | 0,006733 | OK |
| 50.000 | 50,00 | 0,013466 | OK |
| 100.000 | 50,00 | 0,013466 | OK |
| 500.000 | 50,00 | 0,013466 | OK |
| 1.000.000 | 50,00 | 0,013466 | OK |

(Calculada de forma independiente con racionales exactos en Python y verificada en Solidity y Python.)

### 4.1 Dos fuentes de valoración y la compuerta (gate)

- **XAUT/EUR**: ≥ 2 fuentes independientes, frescas (≤ 10 min en el motor), diferencia entre fuentes
  ≤ 1 %, mediana, límites de cordura; firmada por la **clave de precio** (rol distinto del autorizador).
  En cadena: frescura (`maxPriceAge`), límites (`min/maxXautEur8`), desviación máxima frente al último
  precio aceptado (`maxDeviationBps`), precio ligado por hash a la autorización.
- **SOST/EUR**: **no existe metodología aprobada.** El contrato tiene `params.approvedMethodology`;
  con valor 0 (despliegue por defecto) **todo `mint` revierte** (`NoApprovedValuation`) y el motor
  rechaza toda solicitud (`ValuationNotApproved`). La referencia de 0,8886707657 mg de oro por SOST es
  informativa y **no se usa como precio**. Activarla exige una metodología aprobada (identificador
  `bytes32` = hash del documento publicado), configurada con timelock de 2 días.
- Todos los costes (Gold Access Key, gas estimado, comisión de red SOST de la liberación) se muestran
  antes de confirmar. No se presenta como gratuito.

## 5. Motor de verificación (14 pasos)

| # | Paso | Implementación |
|---|---|---|
| 1 | Solicitud única | `create_request`: valida destinatario (checksum EIP-55), cantidad ≥ 100 EUR, gate de valoración; `requestId` con salt aleatorio |
| 2 | Cotización con caducidad | estimación al crear; la comisión vinculante se fija con la PriceQuote firmada al autorizar; `expiry` ≤ `maxAuthTtl` (1 h; motor 30 min) |
| 3 | Bridge Vault | dirección `sost1…` fija por despliegue (`bridgeVault = keccak(dirección)` inmutable en el contrato) |
| 4 | Detección automática | `scan_vault`: `getaddressutxos(vault)` + parseo de cápsula |
| 5 | Hash / red / confirmaciones / importe / UTXO | `verify`: tx confirmada, salida al vault, tipo estándar, cápsula == request, importe EXACTO, ≥ 30 conf., hash de bloque re-leído, `gettxout` no gastado |
| 6 | Vinculación criptográfica con Ethereum | cápsula ⇒ requestId ⇒ destinatario/chainId/contrato/cantidad |
| 7 | No reutilización | `deposit_id = keccak("SOST-C701-DEPOSIT-V1"‖txid‖vout)` UNIQUE en BD y `depositUsed` en el contrato |
| 8 | Autorización única | EIP-712 `MintAuthorization` (§6) con nonce de contador; idempotente mientras viva |
| 9 | Usuario autoriza XAUT en MetaMask | `approve(SOSTBridge, fee)` |
| 10 | El contrato valida | firmas, precio, comisión, topes, pausa |
| 11 | Transfiere XAUT a Gold Reserve V2 | `transferFrom` con delta exacto |
| 12 | Emite wSOST en la misma tx | `token.mint(recipient, amount)` |
| 13 | Muestra ambos hashes | txid SOST + tx Ethereum + eventos |
| 14 | Justificante | eventos `GoldAccessKeyPaid` + `BridgeMinted` + registro `log` del motor |

Estados visibles (UI ↔ motor): Solicitud creada `REQUEST_CREATED` · Esperando SOST `AWAITING_SOST` ·
Verificando blockchain `VERIFYING` · Depósito confirmado `DEPOSIT_CONFIRMED` · Autorización lista
`AUTH_READY` · Esperando firma MetaMask `AWAITING_METAMASK` · Emisión en curso `MINTING` · Completada
`COMPLETED` · Pendiente de recuperación `PENDING_RECOVERY` · Error de seguridad `SECURITY_ERROR`.

## 6. Mensajes EIP-712 (dominio `SOST Automated Bridge`, versión `1`, chainId, verifyingContract)

```
MintAuthorization(bytes32 requestId,address recipient,uint256 amount,bytes32 depositTxid,uint32 depositVout,
                  bytes32 bridgeVault,bytes32 sostBlockHash,uint64 sostBlockHeight,uint32 confirmations,
                  uint256 feeXaut,bytes32 priceHash,uint64 expiry,uint256 nonce)
PriceQuote(uint256 xautEur8,uint256 sostEur8,bytes32 methodology,uint64 observedAt,bytes32 quoteId)
```

Ligado a chainId, contrato, destinatario, cantidad, depósito (txid:vout), vault, bloque SOST,
confirmaciones, comisión, precio, vencimiento y nonce. Firmas ECDSA low-s, v∈{27,28}; umbral M-de-N de
autorizadores ordenados y distintos. Probado: un cambio en cualquier campo invalida la firma; firma para
otra cadena u otro contrato rechazada; la Python del motor produce firmas aceptadas por el bytecode real
(E2E Anvil).

## 7. Controles de seguridad del contrato

| Control | Detalle |
|---|---|
| Anti-replay / doble emisión | `depositUsed`, `requestUsed`, `nonceUsed` |
| Vencimiento | `expiry`; además `expiry - now ≤ maxAuthTtl` |
| Topes | `perMintCap`, `dailyMintCap` (día UTC), `exposureCap` (suministro máximo) |
| Pausa | `pauseMint` (pausers, autorizadores o admin); `unpauseMint` solo admin; **las quemas nunca se pausan** |
| Separación de roles | autorizador ≠ firmante de precio ≠ admin (comprobado en cadena); la custodia nativa (clave del vault SOST) **no existe en Ethereum**; guardianes de la reserva ≠ roles del puente |
| Configuración | propuesta → 2 días → aplicación (hash exacto); re-ancla el precio de referencia |
| Reentrada | `nonReentrant`; checks-effects-interactions |
| Reserva pausada | si Gold Reserve V2 está pausada, `mint` revierte |
| Token | wSOST sin owner, sin blacklist, sin upgrade; solo el puente que lo desplegó acuña/quema |
| Registro público | eventos `BridgeMinted`, `GoldAccessKeyPaid`, `DepositRevoked`, `BurnedForRelease`, `ReleaseRecorded`, `MintPaused`, `Config*` |

### 7.1 Finalidad y reorgs

- SOST: 30 confirmaciones (política provisional, ~5 h; reorg de 1 bloque observado en #30.297). El
  motor re-lee el hash del bloque tras la comprobación de profundidad. Reorg antes de autorizar →
  vuelve a `VERIFYING` (inocuo). Reorg que afecta a un depósito ya autorizado o emitido →
  `SECURITY_ERROR`, el motor se detiene y pausa la emisión en cadena.
- Ethereum: el reembolso SOST solo tras finalidad de `revokeDeposit` (en producción: checkpoint
  *finalized*); las liberaciones se procesan tras la confirmación del burn.

### 7.2 Conciliación

```
obligaciones = suministro wSOST + quemado-no-liberado - liberado-en-SOST-aún-no-registrado
en vuelo     = depósitos verificados aún no emitidos / revocados aún no reembolsados
no vinculados = UTXO del vault sin cápsula válida (pendientes de reembolso)
BALANCED  saldo vault == obligaciones + en vuelo + no vinculados
PENDING   superávit no explicado (investigar)
CRITICAL  saldo vault < obligaciones  -> parada del motor + pauseMint en cadena
```

Probado en E2E: tras compromiso simulado del vault → CRITICAL → `mintPaused == true` en el contrato real, y
las quemas siguen funcionando.

## 8. Matriz de fallos y recuperación (sección G)

| Fallo | Comportamiento | Recuperación |
|---|---|---|
| Depósito confirmado, emisión pendiente | estado `DEPOSIT_CONFIRMED`/`AUTH_READY`; autorización re-emitible tras caducar (nuevo nonce); el depósito no puede emitirse dos veces | el usuario completa en MetaMask cuando quiera; o reembolso (fila «Reembolso») |
| Caída del verificador | no se emiten autorizaciones; nada se pierde (todo está en las cadenas); BD idempotente | al volver re-escanea el vault y continúa |
| Ethereum congestionado | la autorización caduca (≤ 1 h) | se re-autoriza con cotización fresca; la tx antigua revierte por `Expired` |
| XAUT insuficiente / sin approve | `mint` revierte entero (nada emitido, nada cobrado, depósito no marcado) | el mismo usuario reintenta con XAUT |
| Gas insuficiente | la tx revierte entera | reintento |
| Cotización caducada | `Expired` / `StalePrice` | re-autorización |
| Dirección incorrecta (Ethereum) | checksum EIP-55 validado al crear; destinatario comprometido en la cápsula | si el usuario puso una dirección válida pero ajena, NO es recuperable (se avisa en la UI) |
| Dirección incorrecta (SOST) | depósito a otra dirección: no llega al vault, el puente no puede hacer nada | — |
| Hash inválido introducido por el usuario | solo pista; formato y existencia se comprueban; nunca cambia estado | — |
| Solicitud duplicada | cada solicitud tiene salt propio; una cápsula solo vincula su solicitud | el segundo depósito con la misma cápsula queda *unbound* → reembolso |
| Reutilización de depósito | `deposit_id` único en BD y en contrato | — |
| Reorg | §7.1 | — |
| Compromiso de clave del autorizador | emisión sin respaldo posible **hasta los topes** hasta que la conciliación pause | pausa, rotación de claves con timelock; ver §10. **Por esto el puente NO está aprobado para producción.** |
| Compromiso de clave del vault SOST | robo del SOST bloqueado; wSOST quedaría sin respaldo | ninguna recuperación técnica hoy (multisig nativo inexistente hasta V17 #40.000) |
| Quema confirmada, liberación pendiente | `RELEASE_PENDING`; la obligación sigue contada | el firmante frío paga; el motor verifica y registra; idempotente |
| Reembolso | solo tras (1) `revokeDeposit` en Ethereum, (2) finalidad, (3) caducidad de toda autorización emitida; destino = dirección de la primera entrada del depósito | **imposible conservar ambos**: tras revocar, `mint` revierte (`DepositAlreadyUsed`); tras emitir, `revoke` revierte |

## 9. Custodia nativa (Bridge Vault) — estado real

- SOST mainnet **no tiene multisig nativo operativo** (código de librería; su activación está en el
  alcance V17 #40.000, no activo). Hoy el Bridge Vault solo puede ser una dirección `sost1` de **clave
  única**, custodiada en frío y firmada offline.
- Consecuencias: (a) la liberación y el reembolso **no están automatizados** — el motor genera la
  instrucción y un firmante frío la ejecuta; automatizarlo exigiría una clave caliente del vault,
  inaceptable; (b) la pérdida o robo de esa clave no tiene recuperación técnica; (c) la separación
  autorizador-de-mint / custodia es organizativa (claves distintas, máquinas distintas), no criptográfica.
- **Bloqueo de despliegue**: mientras la custodia no garantice recuperación segura (multisig nativo M-de-N
  con claves en HSM distintos y procedimiento de recuperación probado), el puente no se despliega.

## 10. Confianza centralizada (reconocimiento explícito) y opciones futuras

El puente **no es trustless**. Ethereum no puede leer SOST; el respaldo lo afirma el conjunto de
autorizadores del operador. Un único firmante es un punto centralizado. Si su clave se compromete,
puede emitirse wSOST sin respaldo (acotado por topes y por la pausa automática de la conciliación).
**Según la orden (F), eso impide aprobarlo para producción.**

Mitigaciones implementadas: umbral M-de-N de autorizadores (p. ej. 2-de-3 en HSM distintos del mismo
operador — separación de funciones interna, no una red federada), firmante de precio separado, topes,
TTL corto, pausa, conciliación con parada automática, timelock de configuración.

Opciones más fuertes para una fase posterior (sin red federada):

1. **Relé de cabeceras SOST tipo SPV en Ethereum**: el contrato guarda cabeceras SOST y verifica la
   prueba Merkle de la tx de depósito. Obstáculo: verificar ConvergenceX (memoria 4 GB SbPoW) en la EVM
   es inviable; alternativa: verificación optimista (cabeceras publicadas con fianza y ventana de
   impugnación) o checkpoints firmados + pruebas de inclusión.
2. **Prueba ZK de validez de la cadena SOST** (cliente ligero sucinto) — investigación a largo plazo.
3. **Retraso + ventana de veto para emisiones grandes**: emisiones por encima de un umbral quedan en
   cola N horas, cancelables por un monitor independiente (reduce el daño de una clave comprometida).
4. **Firma umbral (MPC/TSS)** dentro del propio operador para la clave del autorizador y, tras V17,
   **multisig nativo SOST** para el vault.

## 11. Gold Reserve V2

- Contrato separado; recibe XAUT de operaciones completadas (directo desde el usuario en la tx de mint) y
  aportaciones voluntarias (`contribute`); **no emite nada; no tiene `withdraw`**; balances verificables
  (`balanceOf`) y eventos; no da liquidez.
- PAUSE 2/5 (no mueve nada) · UNPAUSE 4/5 · CRITICAL RESCUE 4/5 + retardo → **solo** a la Quarantine
  Vault fijada en el despliegue · FINAL MIGRATION 4/5 + resultado de gobernanza (YES ≥ ⌈2/3 × censo
  elegible completo⌉, censo/votos atestiguados) + timelock + sucesor exacto con code hash registrado.
- Recuperación de guardianes (C701): rotación 4/5 + timelock (≥ el de migración), cancelable por 2
  cualesquiera; no mueve activos ni cambia umbrales. Las aprobaciones se recuentan sobre el conjunto
  actual de guardianes (una aprobación de un guardián rotado nunca cuenta — corrección de auditoría).
- Guardianes ≠ autorizadores del puente. Gold Vault histórico y DTD Jackpot: intactos.
- Riesgo de emisor: XAUT es un proxy actualizable; el emisor puede congelar/bloquear (por eso existe el
  rescate a cuarentena). Si XAUT se congela, `mint` revierte entero.

## 12. Estado y condiciones de producción

| Componente | Estado |
|---|---|
| SOSTBridge / WSOST / GoldReserveV2 | código + tests locales (87 Foundry, E2E Anvil 20/20); NO desplegado; sin auditoría externa |
| Motor | prototipo; 25 tests; sin HSM, sin servicio, sin monitorización real |
| Valoración SOST/EUR | INEXISTENTE → todo bloqueado por diseño |
| Custodia nativa | clave única fría; multisig nativo no activo → NOT READY |
| Liberación/reembolso | manual-frío; no automatizado |

Condiciones previas: metodología SOST/EUR aprobada; multisig nativo activo y probado (V17) o solución de
custodia equivalente con recuperación demostrada; autorizadores en HSM con umbral y procedimiento de
rotación; auditoría externa de contratos y motor; oráculo XAUT/EUR con fuentes contractuales; revisión
regulatoria (transmisión de valor, MiCA/AML, comisión en un token de oro, KYC del retorno, fiscalidad);
despliegue en testnet pública con pruebas de recuperación; plan de respuesta a incidentes.
