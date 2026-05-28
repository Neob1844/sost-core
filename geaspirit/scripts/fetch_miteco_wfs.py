#!/usr/bin/env python3
"""
Best-effort fetcher for MITECO Catastro Minero (Spanish mining
rights) via the official WFS service catalogued at:

    https://datos.gob.es/eu/catalogo/e0dat0002-servicio-de-descarga-wfs-de-derechos-mineros-de-espana.xml

Important caveats
-----------------
* The exact WFS endpoint URL on the MITECO infrastructure has rotated
  in the past (we have seen 404 / 302 redirects to bulk shapefiles
  during sprint 1.1). When the endpoint is up, this script writes a
  GeoJSON FeatureCollection into
  geaspirit/data/opportunity/miteco_manual/ so the runtime
  miteco_catastro connector can read it offline.
* When the endpoint is down, the script EXITS cleanly with a
  non-zero status and prints the manual-fallback instructions. The
  runtime connector still works via mode 2 (visor GeoJSON export)
  or mode 3 (operator-pasted JSON).
* This is a SPRINT 2.1 best-effort wrapper. It does not parse GML
  rigorously; it requests an `outputFormat=application/json` response
  and trusts the server. If your endpoint only returns GML, convert
  with `ogr2ogr -f GeoJSON out.geojson in.gml` and drop the result
  in the manual dropbox.

USE
---
    python3 scripts/fetch_miteco_wfs.py \\
        --endpoint https://wms.mapama.gob.es/sig/Energia/Mineria/wms \\
        --bbox 41.8,-9.4,43.9,-6.7 \\
        --label galicia_n_portugal

Default endpoint and type-name are placeholders. Override with the
URL printed by the datos.gob.es catalogue entry the day you run this.

LICENCE
-------
MITECO Catastro Minero — standard MITECO terms. Treat as reference
data; do not redistribute the raw payload as your own.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


USER_AGENT = "SOST-GeaSpirit-opportunity/0.3 (MITECO Catastro Minero fetcher)"
_HERE      = Path(__file__).resolve().parent
_OUT_DIR   = _HERE.parent / "data" / "opportunity" / "miteco_manual"

# Placeholders — override with --endpoint and --typename when the
# operator has confirmed the day's live URL from datos.gob.es.
_DEFAULT_ENDPOINT  = "https://wfs.miteco.gob.es/sig/Energia/Mineria/wfs"
_DEFAULT_TYPENAME  = "Mineria:DerechosMineros"


def _build_url(endpoint: str, typename: str, bbox: str) -> str:
    params = {
        "service":      "WFS",
        "version":      "2.0.0",
        "request":      "GetFeature",
        "typeNames":    typename,
        "outputFormat": "application/json",
        "srsName":      "EPSG:4326",
        # WFS 2.0 BBOX expects: minx,miny,maxx,maxy[,srs] in the
        # declared SRS. We pass lon,lat order with EPSG:4326.
        "bbox":         bbox + ",EPSG:4326",
    }
    return endpoint + "?" + urllib.parse.urlencode(params)


def _fetch(url: str, timeout_s: int) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(
            "WFS server did not return JSON. The endpoint may only "
            "support GML — fetch GML separately and convert with ogr2ogr."
        )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Best-effort MITECO Catastro Minero WFS fetcher.")
    p.add_argument("--endpoint", default=_DEFAULT_ENDPOINT,
                   help="WFS endpoint URL (override with the live one "
                        "from datos.gob.es).")
    p.add_argument("--typename", default=_DEFAULT_TYPENAME,
                   help="WFS typeName for derechos mineros.")
    p.add_argument("--bbox", default="41.8,-9.4,43.9,-6.7",
                   help="bbox south,west,north,east (default: "
                        "Galicia + N Portugal).")
    p.add_argument("--label", default="galicia_n_portugal",
                   help="short label used in the output filename.")
    p.add_argument("--timeout", type=int, default=120,
                   help="HTTP timeout seconds.")
    args = p.parse_args(argv)

    try:
        s, w, n, e = (float(x) for x in args.bbox.split(","))
    except ValueError:
        print(f"ERROR: bad --bbox {args.bbox!r}", file=sys.stderr)
        return 2

    # WFS BBOX in EPSG:4326 with axis order Lat,Lon (yes, WFS 2.0).
    bbox_param = f"{s},{w},{n},{e}"
    url = _build_url(args.endpoint, args.typename, bbox_param)
    print(f"[fetch_miteco_wfs] GET {url}")

    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        payload = _fetch(url, args.timeout)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as err:
        print(
            f"ERROR: WFS fetch failed: {type(err).__name__}: {err}\n"
            "The official MITECO WFS endpoint has rotated before — try "
            "looking up the current URL at "
            "https://datos.gob.es/eu/catalogo/"
            "e0dat0002-servicio-de-descarga-wfs-de-derechos-mineros-de-espana.xml "
            "and re-run with --endpoint <new-url>.\n"
            "Fallbacks: open the visor at "
            "https://geoportal.minetur.gob.es/CatastroMinero/ and export "
            "GeoJSON manually, OR transcribe records into the "
            "miteco_record.v0 schema. Drop either into "
            f"{_OUT_DIR}.",
            file=sys.stderr,
        )
        return 1

    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        print("ERROR: WFS response is not a GeoJSON FeatureCollection.",
              file=sys.stderr)
        return 1

    n_features = len(payload.get("features") or [])
    print(f"[fetch_miteco_wfs] features: {n_features}")

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = _OUT_DIR / f"miteco_wfs__{args.label}__{stamp}.geojson"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"[fetch_miteco_wfs] wrote {out}")
    print("[fetch_miteco_wfs] LICENCE: MITECO Catastro Minero — "
          "treat as reference data; do not redistribute as own.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
