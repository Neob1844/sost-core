# MITECO Catastro Minero — manual import dropbox

The `miteco_catastro` connector reads every `*.json` and `*.geojson`
file in this directory at scan time and merges them into the legal
sub-score for any AOI inside the records' radius.

It NEVER calls the network. Network fetches (when the official WFS is
up) live in `geaspirit/scripts/fetch_miteco_wfs.py` and write their
output here.

Three import modes are supported, listed from most robust to most
manual:

## 1. official_wfs

Run the fetcher script and drop the resulting GeoJSON here:

```bash
python3 geaspirit/scripts/fetch_miteco_wfs.py \
    --bbox 41.8,-9.4,43.9,-6.7 \
    --label galicia_n_portugal
```

If the official WFS endpoint is up, it writes
`miteco_wfs__galicia_n_portugal__<utc>.geojson` here. If it fails,
fall back to mode 2 or 3.

Official catalogue entry (URL may rotate):
<https://datos.gob.es/eu/catalogo/e0dat0002-servicio-de-descarga-wfs-de-derechos-mineros-de-espana.xml>

## 2. visor_geojson  — manual export from the official visor

Open the MITECO Catastro Minero visor:
<https://geoportal.minetur.gob.es/CatastroMinero/>

Help reference:
<https://geoportal.minetur.gob.es/CatastroMinero/assets/ayuda/catastroUser/visor.htm>

Steps:

1. Pan / zoom to your AOI.
2. Select the layer "Derechos mineros".
3. Use the export tool → choose GeoJSON. (Shapefile and KMZ exports
   work too, but Sprint 2.1 reads GeoJSON natively — convert SHP/KMZ
   to GeoJSON before dropping. Convert with `ogr2ogr` for example.)
4. Save the file here as something like
   `visor_export__<region>__<YYYYMMDD>.geojson`.
5. Re-run `python3 geaspirit/scripts/opportunity_scan.py …` —
   the connector picks it up automatically.

The connector recognises the visor's Spanish property names
(`EXPEDIENTE`, `ESTADO`, `TIPO`, `TITULAR`, `SECCION`,
`FECHA_INICIO`, `FECHA_FIN`) and English fallbacks.

## 3. operator_pasted_json — manual transcription

When the visor export is blocked or the operator wants to redact
holder identities before any internal sharing, transcribe records
directly into a JSON file matching the `miteco_record.v0` schema.
See `data/opportunity/samples/galicia_miteco_sample.json` for an
example. Minimum required fields per record:

```json
{
  "right_id": "PCS-Lugo-3265",
  "name": "Concesion de explotacion W-Sn La Madrona",
  "kind": "concesion_explotacion",
  "section": "C",
  "status": "expired",
  "holder": "redacted",
  "centroid": {"lat": 42.64, "lon": -8.35},
  "valid_from": "1985-04-12",
  "expires_at": "2015-04-12",
  "source_url": "https://geoportal.minetur.gob.es/CatastroMinero/",
  "imported_at": "2026-05-28T00:00:00Z",
  "confidence": 0.74,
  "operator_note": "Verified visually in visor on import date."
}
```

Accepted `status` values (internal vocabulary — the connector also
maps Spanish visor labels like `vigente`, `caducado`, `extinguido`,
`en tramite`, `cancelado`, `conflictivo`):

| status               | meaning                                          |
| -------------------- | ------------------------------------------------ |
| `active_clear`       | single clear owner, contactable                  |
| `active`             | active right, holder identifiable                |
| `active_third_party` | active right held by a third party              |
| `expired`            | term ended, no successor                         |
| `cancelled`          | extinguished / annulled                          |
| `pending_request`    | in-flight application by a third party           |
| `conflicting`        | litigation, overlap, disputed                    |
| `unknown`            | catastro consulted but record is unclear         |

## Rules

* **Holder field**: NEVER paste a personal email here. The connector
  belt-and-braces redacts strings containing `@`, but the operator is
  responsible for upstream redaction.
* **No automated outreach**: the connector emits Evidence only. Any
  contact with holders is operator-led and out-of-band.
* **No commit of holder PII**: this dropbox is gitignored at the
  project level (verify before sharing).
* **No data here → legal subscore 50 (neutral)**: the scorecard does
  not pretend a missing import means "free and clear".

## License

MITECO Catastro Minero is published under standard MITECO terms.
Re-distribution of bulk catastro data may carry attribution
requirements. Treat exports as reference data only; do NOT publish
the raw payload as your own.
