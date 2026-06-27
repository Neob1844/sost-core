# Atomic Swap (HTLC) — Guía de prueba para el FOUNDER

> Estado a 2026-06-28 · cadena en altura ~15.015 · **HTLC consensus ACTIVO en mainnet**
> (activación V14_HEIGHT = 15.000) · **EVM-only** (SOST↔ETH/BNB/ERC-20) · **SOST↔BTC = V15
> (todavía OFF)** · feature **founder-only, sin auditar**: en pruebas reales puedes **perder
> fondos**. No anuncies "safe to use" hasta auditoría.

---

## 0. Qué es y qué estás probando (en 30 segundos)

Un **HTLC** (Hash-Time-Locked Contract) bloquea SOST en un output especial que solo se
puede gastar de dos formas:

- **CLAIM** (reclamar): quien conozca el *secreto* (`preimage`) cuyo SHA256 = `hashlock`,
  **antes** de `refund_height`. Revelar el secreto on-chain es lo que hace el swap atómico:
  la otra cadena usa el mismo secreto.
- **REFUND** (devolución): el que bloqueó recupera sus fondos **a partir de** `refund_height`
  (si el swap se aborta). Nunca antes (la consensus lo rechaza, regla R24).

Mecánica on-chain (lo que valida el nodo):

| Campo (payload LOCK, 80 bytes) | Significado |
|---|---|
| `hashlock` (32B) | `SHA256(preimage)` |
| `refund_height` (8B) | altura absoluta tras la cual se puede REFUND; debe ser `> altura_actual` |
| `claim_pkh` (20B) | pkh de quien puede reclamar (la contraparte) |
| `refund_pkh` (20B) | pkh de quien recupera (tú) |

Reglas de consenso clave (`src/tx_validation.cpp`):
`R17` LOCK bien formado (80B, importe ≥ dust, refund_height futura) · `R21` CLAIM exige
`SHA256(preimage)==hashlock` · `R22` CLAIM solo **antes** de `refund_height` · `R24` REFUND
solo **en/después** de `refund_height`.

---

## 1. Camino A — Validación OFFLINE (riesgo CERO, hazlo PRIMERO)

No mueve fondos, no toca mainnet. Demuestra que el consenso y la orquestación funcionan.
Ya verificado: **12/12 tests + coordinador happy/refund/negativos OK.**

```bash
cd ~/SOST/sostcore/sost-core
# (usa cualquier build mainnet ya compilado; aquí build-g3b)
# A.1 — suite de consenso + módulos atomic-swap
( cd build-g3b && ctest -R atomic-swap --output-on-failure )

# A.2 — ensayo del coordinador end-to-end (offer→lock→claim→Completed, refund, negativos)
BUILD=build-g3b bash scripts/otc_rehearsal_sost_local.sh
```
Debes ver `100% tests passed` y las fases `Completed` / `Refunded` / `TIMEOUT_ORDER_INVALID`.
Esto es lo que firma que la lógica es correcta antes de arriesgar un satoshi de SOST.

---

## 2. Camino B — Prueba EN VIVO en REGTEST (live, seguro, repetible)

La forma correcta de probar LOCK/CLAIM/REFUND reales sin tocar mainnet: un nodo regtest
con la activación HTLC en altura baja. **El binario mainnet NO cambia** (su constante sigue
en 15.000); esto es solo un build de operador.

1. **Build regtest** con activación temprana (perfil aparte, no lo subas a mainnet):
   ```bash
   cmake -S . -B build-regtest -DSOST_TESTNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON \
         -DCMAKE_BUILD_TYPE=Release
   cmake --build build-regtest --target sost-node sost-cli sost-miner -j$(nproc)
   ```
   (En testnet, V14_HEIGHT=200 → con minar >200 bloques el HTLC queda activo.)

2. **Arranca el nodo regtest local**, mina más allá de la altura de activación, y comprueba
   el estado HTLC con los comandos de la sección 4.

3. Secuencia completa (ver sección 4 para sintaxis exacta):
   `createhtlclock` → firmar → `sendrawtransaction` → `gethtlcstatus` (Locked) →
   `claimhtlc` → `sendrawtransaction` → `gethtlcstatus` (Claimed + `revealed_preimage`).
   Repite cambiando el final por `refundhtlc` tras `refund_height` para probar la recuperación.

---

## 3. Camino C — Prueba EN VIVO en MAINNET (la de verdad) vía la consola Atomic Swap DEX

El HTLC ya está activo en mainnet, así que puedes hacer un **self-swap** real: bloqueas un
importe **diminuto** de SOST en un HTLC donde **`claim_pkh` y `refund_pkh` son direcciones
TUYAS**. Así no hay contraparte ni riesgo de robo: o lo reclamas con tu propio secreto, o lo
recuperas tras el timeout.

**Usa la consola web** (`website/sost-dex.html`, enlazada desde la wallet como "ATOMIC SWAP
DEX"). Es la vía founder soportada porque **construye, firma y difunde** el HTLC por ti, y
convierte dirección→pkh automáticamente. La CLI (sección 4) produce tx **sin firmar** y no
trae un `signrawtransaction` de un solo paso, por eso para mainnet conviene la consola.

Pasos del self-swap mínimo:
1. Genera el secreto y el hashlock (sección 5).
2. En la consola: **Lock SOST** con importe diminuto (p. ej. 1 SOST), `refund_height` =
   altura_actual + ~30 bloques (margen corto para no esperar días), `claim_pkh`/`refund_pkh`
   = direcciones tuyas. Difunde. Anota el `lock_txid`.
3. `gethtlcstatus <lock_txid> 0` → debe decir **Locked**.
4. **Claim** con el `preimage`: difunde. `gethtlcstatus` → **Claimed**, y `revealed_preimage`
   debe coincidir con tu secreto. ✅ eso es un swap atómico funcionando.
5. (Otra prueba) repite pero **no reclames**; espera a pasar `refund_height` y haz **Refund**:
   recuperas el SOST. Antes del timeout debe **fallar** (R24) — confírmalo.

> Importe diminuto + ambas patas tuyas = la prueba mainnet más segura posible. Aun así es
> dinero real; empieza por A y B.

---

## 4. Referencia de comandos CLI (sintaxis exacta)

Todos los `create*/claim*/refund*` devuelven tx **sin firmar** (hex). `gethtlcstatus` y
`listhtlclocks` son solo-lectura contra el nodo.

```bash
# Generar el bloque LOCK (gastas un UTXO tuyo hacia un HTLC)
sost-cli createhtlclock <prev_txid> <prev_vout> <prev_amount> <prev_pkh> \
                        <hashlock> <refund_height> <claim_pkh> <refund_pkh> \
                        <lock_amount> <fee>

# Reclamar revelando el secreto (antes de refund_height)
sost-cli claimhtlc <lock_txid> <lock_vout> <lock_amount> <preimage> \
                   <claim_dest_pkh> <marker_dust_amount> <fee>

# Recuperar tras el timeout (>= refund_height)
sost-cli refundhtlc <lock_txid> <lock_vout> <lock_amount> <refund_dest_pkh> <fee>

# Inspeccionar una tx HTLC sin firmar antes de difundir (verifica campos)
sost-cli decodehtlc <raw_tx_hex>

# Estado on-chain
sost-cli gethtlcstatus <lock_txid> <lock_vout>   # Unknown|Locked|Expired|Claimed|Refunded
sost-cli listhtlclocks                           # todos los LOCK abiertos

# Difundir una tx ya firmada
sost-cli sendrawtransaction <signed_hex>
```
Unidades: importes en **stocks** (1 SOST = 100.000.000 stocks). `*_pkh` = 40 hex
(RIPEMD160(SHA256(pubkey))). `hashlock`/`preimage` = 64 hex (32 bytes).

---

## 5. Generar secreto + hashlock (tú, el iniciador)

```bash
SECRET=$(openssl rand -hex 32)                                              # 32 bytes
HASHLOCK=$(python3 -c "import hashlib,sys;print(hashlib.sha256(bytes.fromhex(sys.argv[1])).hexdigest())" "$SECRET")
echo "SECRET   (guárdalo en secreto): $SECRET"
echo "HASHLOCK (público, va en el LOCK): $HASHLOCK"
```
**Nunca** reveles `SECRET` hasta el CLAIM. Quien lo vea on-chain puede completar su pata.

---

## 6. Checklist de seguridad (antes de cada prueba en vivo)

- [ ] Hecho el **Camino A** (offline) y todo en verde.
- [ ] Importe **diminuto** y, en mainnet, **ambas patas con direcciones tuyas** (self-swap).
- [ ] `refund_height` razonable (corto para probar refund sin esperar días; estás a ~12 min/bloque).
- [ ] `decodehtlc` sobre tu tx sin firmar **antes** de difundir, para verificar `hashlock`,
      `refund_height`, `claim_pkh`, `refund_pkh`.
- [ ] Confirmar que **REFUND antes del timeout FALLA** (R24) y que **CLAIM con preimage
      incorrecto FALLA** (R21) — son las garantías de seguridad.
- [ ] SOST↔BTC: **no probar**, no está activo (V15).
- [ ] **No** publicar "safe to use" hasta auditoría externa.

---

## 7. Recuperación / troubleshooting

- **"Atomic Swap HTLC is disabled until protocol activation"** → estás bajo la altura de
  activación (en regtest, mina más; en mainnet ya está activo >15.000).
- **CLAIM rechazado** → preimage no casa (R21) o ya pasó `refund_height` (R22).
- **REFUND rechazado** → todavía no llegó `refund_height` (R24); espera.
- **Fondos atascados** → si nadie reclama, tú **siempre** recuperas con REFUND pasado el
  timeout. Por eso el self-swap es seguro: el peor caso es esperar al refund.
- Estado en cualquier momento: `gethtlcstatus` / `listhtlclocks`.

---

## 8. Roadmap de pruebas recomendado (orden)

1. **A (offline)** — hoy, riesgo cero. ✅ ya pasa 12/12 + coordinador.
2. **B (regtest)** — LOCK/CLAIM/REFUND reales en un nodo local desechable.
3. **C (mainnet self-swap)** — 1 SOST, ambas patas tuyas, vía consola DEX. Prueba CLAIM y
   prueba REFUND-tras-timeout.
4. **D (cross-chain SOST↔EVM)** — solo cuando A–C estén sólidos: contraparte en una testnet
   EVM (anvil/sepolia), usando `scripts/otc_rehearsal_evm_anvil.sh` como referencia.
5. Solo tras auditoría → considerar uso público y el anuncio "safe to use".
