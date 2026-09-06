#!/usr/bin/env python3
"""Harvest the UAE SDGs Data Hub (ArcGIS Hub) catalogue and its data.

The hub at https://sdgsuae-fcsa.opendata.arcgis.com is an ArcGIS Hub site, so
everything it publishes is reachable through three public REST APIs:

  1. Hub search   -> the catalogue of items (datasets, maps, documents, apps)
  2. Feature      -> /FeatureServer/<layer>/query paged with resultOffset
     services       (GeoJSON + attribute CSV)
  3. Item data    -> www.arcgis.com/sharing/rest/content/items/<id>/data
                     for documents (PDF/XLSX) and other file items

Only the Python standard library is used, and HTTPS_PROXY / REQUESTS_CA_BUNDLE
style environment settings are honoured through urllib.

Usage
-----
  python3 tools/fetch_sdg_hub.py --catalog-only
  python3 tools/fetch_sdg_hub.py --out data/sdg_uae
  python3 tools/fetch_sdg_hub.py --out data/sdg_uae --formats geojson,csv --limit 20

The script is resumable: files that already exist are skipped unless
--overwrite is passed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HUB = "https://sdgsuae-fcsa.opendata.arcgis.com"
AGO = "https://www.arcgis.com"
USER_AGENT = "sdg-hub-harvester/1.0 (+python-urllib)"
PAGE_SIZE = 100
FEATURE_PAGE = 1000
MAX_RETRIES = 5


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------

def _context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        ctx.load_verify_locations(bundle)
    return ctx


def request(url: str, *, params: dict | None = None, binary: bool = False,
            timeout: int = 120):
    """GET a URL with exponential-backoff retries. Returns text, or bytes."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=_context()) as resp:
                raw = resp.read()
            return raw if binary else raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last = exc
            # 4xx other than throttling will not improve on retry.
            if exc.code not in (408, 429, 500, 502, 503, 504):
                raise
        except Exception as exc:                      # noqa: BLE001 - network
            last = exc
        wait = 2 ** attempt
        print(f"    retry {attempt + 1}/{MAX_RETRIES} in {wait}s ({last})",
              file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last}")


def get_json(url: str, *, params: dict | None = None) -> dict:
    return json.loads(request(url, params=params))


def slugify(text: str, fallback: str = "item") -> str:
    text = re.sub(r"[^\w؀-ۿ]+", "-", (text or "").strip(), flags=re.U)
    text = text.strip("-").lower()
    return (text or fallback)[:120]


# --------------------------------------------------------------------------
# 1. Catalogue
# --------------------------------------------------------------------------

def _next_href(payload: dict) -> str | None:
    """Extract the rel=next link, tolerating both list and dict link shapes."""
    links = payload.get("links")
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict) and link.get("rel") == "next":
                return link.get("href")
    elif isinstance(links, dict):
        nxt = links.get("next")
        if isinstance(nxt, dict):
            return nxt.get("href")
        if isinstance(nxt, str):
            return nxt
    return None


def _extract_item(feature: dict) -> dict:
    props = feature.get("properties") or {}
    links = props.get("links")
    return {
        "id": feature.get("id") or props.get("id"),
        "title": props.get("title"),
        "type": props.get("type"),
        "owner": props.get("owner"),
        "snippet": props.get("snippet"),
        "description": props.get("description"),
        "tags": props.get("tags"),
        "created": props.get("created"),
        "modified": props.get("modified"),
        "url": props.get("url"),
        "licenseInfo": props.get("licenseInfo"),
        "hub_page": links.get("self") if isinstance(links, dict) else None,
    }


def fetch_catalog(limit: int | None = None,
                  collection: str | None = None) -> list[dict]:
    """Page through the Hub search API and return every catalogue item.

    Hub sites differ in which search collections they expose, so unless the
    caller pins one with --collection we try them in order and keep the first
    that answers. Paging follows the rel=next link when the site provides one
    and falls back to explicit startindex paging when it does not.
    """
    candidates = [collection] if collection else ["all", "dataset", "content"]
    last_error: Exception | None = None
    for name in candidates:
        items: list[dict] = []
        url = f"{HUB}/api/search/v1/collections/{name}/items"
        params: dict | None = {"limit": PAGE_SIZE}
        try:
            while True:
                payload = get_json(url, params=params)
                features = payload.get("features") or []
                items.extend(_extract_item(f) for f in features)
                print(f"  catalogue [{name}]: {len(items)} items")
                if limit and len(items) >= limit:
                    return items[:limit]
                if len(features) < PAGE_SIZE:
                    break
                href = _next_href(payload)
                if href:
                    url, params = href, None
                else:                       # site omits rel=next - page by hand
                    url = f"{HUB}/api/search/v1/collections/{name}/items"
                    params = {"limit": PAGE_SIZE, "startindex": len(items) + 1}
        except Exception as exc:            # noqa: BLE001 - try next collection
            last_error = exc
            print(f"  collection '{name}' unavailable ({exc})", file=sys.stderr)
            continue
        if items:
            return items
    if last_error:
        raise RuntimeError(
            f"could not read the Hub catalogue from {HUB}: {last_error}")
    return []


def write_catalog(items: list[dict], out: str) -> None:
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
    columns = ["id", "title", "type", "owner", "tags", "created", "modified",
               "url", "snippet"]
    with open(os.path.join(out, "catalog.csv"), "w", encoding="utf-8-sig",
              newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            row = dict(item)
            if isinstance(row.get("tags"), list):
                row["tags"] = "; ".join(row["tags"])
            writer.writerow(row)
    print(f"  wrote catalog.json / catalog.csv ({len(items)} items)")


# --------------------------------------------------------------------------
# 2. Feature services
# --------------------------------------------------------------------------

def service_layers(service_url: str) -> list[tuple[str, str]]:
    """Return [(layer_url, layer_name)] for a Feature/Map service URL."""
    service_url = service_url.rstrip("/")
    # A URL that already points at a single layer, e.g. .../FeatureServer/0
    if re.search(r"/(Feature|Map)Server/\d+$", service_url):
        meta = get_json(service_url, params={"f": "json"})
        return [(service_url, meta.get("name") or "layer")]
    meta = get_json(service_url, params={"f": "json"})
    layers = (meta.get("layers") or []) + (meta.get("tables") or [])
    return [(f"{service_url}/{lyr['id']}", lyr.get("name") or f"layer_{lyr['id']}")
            for lyr in layers]


def download_layer(layer_url: str, base_path: str, formats: set[str],
                   overwrite: bool) -> dict:
    """Page a layer's features out to GeoJSON and/or CSV. Returns a summary."""
    meta = get_json(layer_url, params={"f": "json"})
    page = min(int(meta.get("maxRecordCount") or FEATURE_PAGE), FEATURE_PAGE)
    geometry_type = meta.get("geometryType")

    geojson_path = f"{base_path}.geojson"
    csv_path = f"{base_path}.csv"
    want_geojson = "geojson" in formats and geometry_type
    want_csv = "csv" in formats
    if (not overwrite
            and (not want_geojson or os.path.exists(geojson_path))
            and (not want_csv or os.path.exists(csv_path))):
        print(f"    skip (already downloaded): {os.path.basename(base_path)}")
        return {"status": "skipped"}

    features: list[dict] = []
    offset = 0
    while True:
        payload = get_json(layer_url + "/query", params={
            "where": "1=1",
            "outFields": "*",
            "outSR": 4326,
            "returnGeometry": "true" if geometry_type else "false",
            "resultOffset": offset,
            "resultRecordCount": page,
            "f": "geojson" if geometry_type else "json",
        })
        batch = payload.get("features") or []
        features.extend(batch)
        print(f"    {os.path.basename(base_path)}: {len(features)} features",
              end="\r", flush=True)
        if len(batch) < page:
            break
        offset += len(batch)
    print()

    os.makedirs(os.path.dirname(base_path), exist_ok=True)
    if want_geojson:
        with open(geojson_path, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": features},
                      fh, ensure_ascii=False)
    if want_csv:
        rows = [(f.get("properties") or f.get("attributes") or {})
                for f in features]
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return {"status": "ok", "features": len(features),
            "geometry_type": geometry_type}


# --------------------------------------------------------------------------
# 3. Document / file items
# --------------------------------------------------------------------------

EXTENSIONS = {
    "PDF": ".pdf", "Microsoft Excel": ".xlsx", "Microsoft Word": ".docx",
    "Microsoft Powerpoint": ".pptx", "CSV": ".csv", "Image": ".png",
    "Shapefile": ".zip", "File Geodatabase": ".gdb.zip", "GeoJson": ".geojson",
}


def download_item_data(item: dict, base_path: str, overwrite: bool) -> dict:
    ext = EXTENSIONS.get(item.get("type") or "", ".bin")
    path = base_path + ext
    if os.path.exists(path) and not overwrite:
        print(f"    skip (already downloaded): {os.path.basename(path)}")
        return {"status": "skipped"}
    blob = request(f"{AGO}/sharing/rest/content/items/{item['id']}/data",
                   binary=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(blob)
    return {"status": "ok", "bytes": len(blob), "path": path}


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

SERVICE_TYPES = {"Feature Service", "Map Service", "Feature Layer",
                 "Table", "Feature Collection"}
FILE_TYPES = set(EXTENSIONS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/sdg_uae",
                        help="output directory (default: data/sdg_uae)")
    parser.add_argument("--formats", default="geojson,csv",
                        help="comma separated: geojson,csv")
    parser.add_argument("--catalog-only", action="store_true",
                        help="only harvest the item catalogue, no data")
    parser.add_argument("--limit", type=int,
                        help="stop after N catalogue items (for testing)")
    parser.add_argument("--overwrite", action="store_true",
                        help="re-download files that already exist")
    parser.add_argument("--collection",
                        help="pin the Hub search collection "
                             "(default: try all, dataset, content)")
    parser.add_argument("--sleep", type=float, default=0.3,
                        help="pause between items, in seconds")
    args = parser.parse_args()

    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    print(f"Harvesting {HUB}")
    items = fetch_catalog(limit=args.limit, collection=args.collection)
    write_catalog(items, out)
    if args.catalog_only:
        return 0

    manifest = []
    for index, item in enumerate(items, start=1):
        title = item.get("title") or item.get("id")
        kind = item.get("type") or ""
        print(f"[{index}/{len(items)}] {title}  ({kind})")
        stem = os.path.join(out, "datasets",
                            f"{slugify(title)}__{item.get('id')}")
        record = {"id": item.get("id"), "title": title, "type": kind}
        try:
            if kind in SERVICE_TYPES and item.get("url"):
                layers = service_layers(item["url"])
                record["layers"] = []
                for layer_url, layer_name in layers:
                    suffix = f"__{slugify(layer_name, 'layer')}" if len(layers) > 1 else ""
                    result = download_layer(layer_url, stem + suffix, formats,
                                            args.overwrite)
                    result["layer"] = layer_name
                    result["source"] = layer_url
                    record["layers"].append(result)
            elif kind in FILE_TYPES:
                record.update(download_item_data(item, stem, args.overwrite))
            else:
                record["status"] = "no downloadable payload"
                record["url"] = item.get("url")
                print("    no downloadable payload (link / app / map item)")
        except Exception as exc:                      # noqa: BLE001
            record["status"] = "error"
            record["error"] = str(exc)
            print(f"    ERROR: {exc}", file=sys.stderr)
        manifest.append(record)
        time.sleep(args.sleep)

    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    ok = sum(1 for r in manifest if r.get("status") == "ok"
             or any(l.get("status") == "ok" for l in r.get("layers", [])))
    errors = [r for r in manifest if r.get("status") == "error"]
    print(f"\nDone. {ok} downloaded, {len(errors)} errors, "
          f"{len(manifest)} catalogue items. Output: {out}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
