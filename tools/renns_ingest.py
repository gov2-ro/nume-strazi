"""Ingest street names from ANCPI's RENNS (Registrul Electronic Național al
Nomenclaturii Stradale) into `renns_streets`.

Source: https://renns.ancpi.ro public API, "Drumuri" (roads) tab —
https://renns.ancpi.ro/api/public/roads?idCounty=<id>&idUAT=<id>&page=1&items=2000

Crawl strategy — per-(county, UAT), NOT the flat/unfiltered endpoint:
  The unfiltered endpoint (idCounty alone is silently ignored server-side;
  omitting both params returns the *entire* national dataset, paginated
  67x2000) looks tempting — only 67 requests for all of Romania. But a full
  sequential crawl of it produced 3,680 duplicate ids out of 133,194 rows
  (2.8%) — the live dataset shifts under a multi-page unfiltered crawl, so
  rows get skipped or duplicated non-deterministically. Rejected.

  The per-(county, UAT) filtered endpoint is safe: every single UAT's road
  count fits in one page (max observed: Cluj-Napoca at 1,212, vs. the
  2,000-item cap), so each UAT fetch is an atomic single-page snapshot with
  no pagination-drift risk. This is the only path implemented here — do not
  re-add the flat crawl without re-checking that finding.

UAT resolution: RENNS's `uat.id` IS the electoral source's SIRUTA code, verified
directly (3,180/3,181 exact matches against every UAT in
data/gis/populatie-romania-siruta-coords.csv). No name-matching fallback,
unlike tools/postal_ingest.py. Rows are kept even when uat_siruta has no
counterpart in our own `streets` table (e.g. RENNS's "Racșa", SM, id
180091) — that's a genuine electoral-source gap worth surfacing via
streets_all_sources, not something to silently drop.

Coverage caveats (see CODE_SPEC §13 for the full picture):
  - București has ZERO roads in RENNS (checked directly, not just absent
    from a sample) — a structural gap, not a bug.
  - Only ~1,902 of Romania's 3,181 UATs (60%) have ANY roads in RENNS —
    this is a rolling/partial national digitization, not a finished registry.

Idempotent: --rebuild truncates renns_streets (and street_renns_matches,
which references it) before inserting.

Usage:
  python3 tools/renns_ingest.py
  python3 tools/renns_ingest.py --rebuild
  python3 tools/renns_ingest.py --uat-siruta 1017      # Alba Iulia, fast iteration
  python3 tools/renns_ingest.py --workers 16
  python3 tools/renns_ingest.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streets_lib import fix_diacritics, normalize_match, extract_features  # noqa: E402

API_BASE = "https://renns.ancpi.ro/api"

# Raw roadType.name -> canonical street_type. Keys are lowercased and
# fix_diacritics-folded before lookup, so cedilla variants (Piaţa/Piața,
# Uliţa/Ulița, Şoseaua/Șoseaua) collapse automatically and don't need
# separate entries. Some entries fold distinct-but-equivalent regional
# spellings onto one canonical form, mirroring the precedent already set by
# tools/postal_ingest.py's TIP_ARTERA_MAP (e.g. "Fundac" -> "Fundătura",
# "Trecătoare" -> "Trecerea").
ROAD_TYPE_MAP = {
    "strada": "Strada",
    "aleea": "Aleea",
    "fundatura": "Fundătura", "fundătura": "Fundătura",
    "fundacul": "Fundătura", "infundatura": "Fundătura", "înfundătura": "Fundătura",
    "intrarea": "Intrarea",
    "ulita": "Ulița", "ulița": "Ulița",
    "ulicioara": "Ulicioara",
    "drumul": "Drumul",
    "calea": "Calea",
    "bulevardul": "Bulevardul",
    "piata": "Piața", "piața": "Piața",
    "soseaua": "Șoseaua", "șoseaua": "Șoseaua",
    "soseaua nationala": "Șoseaua", "șoseaua națională": "Șoseaua",
    "stradela": "Stradela",
    "prelungirea": "Prelungirea",
    "curtea": "Curtea",
    "pasajul": "Pasajul",
    "splaiul": "Splaiul",
    "cartierul": "Cartierul",
    "parcul": "Parcul", "parc": "Parcul",
    "vadul": "Vadul",
    "trecatoarea": "Trecerea", "trecătoarea": "Trecerea",
    "cantonul": "Cantonul",
    "catun": "Cătun", "cătun": "Cătun",
    "scuarul": "Scuarul",
    "colonia": "Colonia",
    "centura": "Centura",
    "cvartal": "Cvartal",
    "pietonal": "Pietonal",
    "podul": "Podul",
}

# Rural/cadastral road-classification codes and unspecified markers — not
# named streets in the honorific-street-name sense. street_type = NULL,
# road_type_raw kept for transparency (same posture as core_name=NULL on
# numeric streets: don't force-fit ambiguous data).
RURAL_ADMIN_TYPES = {
    "", "nespecificat", "ds", "d.s.", "dc", "de", "dj",
    "drumul ds", "drumul dc", "drum comunal", "drum comunal dc",
    "drum comunal de", "drum judetean", "drum judeţean", "drum judetean dj",
    "drum județean dj", "drum national", "drum naţional", "drum național",
}


def clean_road_type(raw):
    """Map a raw roadType.name to a canonical street_type, or None for
    rural/admin/unspecified codes. Also handles the "Strada X" double-prefix
    data-entry glitch (e.g. "Strada aleea", "Strada FUNDATURA") by stripping
    the leading "Strada " and re-resolving the remainder."""
    if not raw:
        return None
    s = fix_diacritics(raw).strip()
    key = s.lower()
    if key in RURAL_ADMIN_TYPES:
        return None
    if key in ROAD_TYPE_MAP:
        return ROAD_TYPE_MAP[key]
    if key.startswith("strada "):
        rest = key[len("strada "):].strip()
        if not rest or rest == "strada":
            return "Strada"
        if rest in ROAD_TYPE_MAP:
            return ROAD_TYPE_MAP[rest]
    return None


def fetch_json(url, retries=3):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def fetch_counties():
    return fetch_json(f"{API_BASE}/counties?page=1&items=2000")["items"]


def fetch_uats(county_id):
    return fetch_json(f"{API_BASE}/uats?countyId={county_id}&page=1&items=2000")["items"]


def fetch_roads(county_id, uat_siruta):
    data = fetch_json(
        f"{API_BASE}/public/roads?idCounty={county_id}&idUAT={uat_siruta}&page=1&items=2000"
    )
    if data.get("hasNextPage"):
        raise RuntimeError(
            f"UAT {uat_siruta} (county {county_id}) has >2000 roads — "
            "single-page assumption broken, needs a multi-page loop."
        )
    return data["items"]


def build_row(item):
    uat = item.get("uat") or {}
    uat_siruta = uat.get("id")
    if uat_siruta is None:
        return None
    name = fix_diacritics(item.get("name") or "").strip()
    if not name:
        return None
    name_norm = normalize_match(name)
    if not name_norm:
        return None
    road_type_raw = (item.get("roadType") or {}).get("name")
    street_type = clean_road_type(road_type_raw)
    feats = extract_features(name)
    core_norm = normalize_match(feats["core_name"]) if feats["core_name"] else None
    county = item.get("county") or {}
    locality = item.get("locality") or {}
    road_status = (item.get("roadStatus") or {}).get("name")
    return {
        "road_id": item.get("id"),
        "uat_siruta": uat_siruta,
        "judet": county.get("shortName"),
        "locality_raw": locality.get("name"),
        "road_type_raw": road_type_raw,
        "street_type": street_type,
        "name": name,
        "name_normalized": name_norm,
        "title": feats["title"],
        "rank": feats["rank"],
        "is_saint": feats["is_saint"],
        "is_date": feats["is_date"],
        "is_numeric": feats["is_numeric"],
        "core_name": feats["core_name"],
        "core_name_norm": core_norm,
        "road_status": road_status,
    }


def parse_args():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--rebuild", action="store_true",
                     help="Truncate renns_streets before inserting.")
    ap.add_argument("--dry-run", action="store_true",
                     help="Fetch and group, print stats, do not write.")
    ap.add_argument("--workers", type=int, default=8,
                     help="Concurrent requests for the per-UAT crawl.")
    ap.add_argument("--uat-siruta", type=int, default=None,
                     help="Restrict ingest to one UAT (SIRUTA = RENNS uat.id). For iteration.")
    return ap.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"DB not found at {db_path}. Run build_db.py first.")

    con = sqlite3.connect(db_path)

    print("Fetching county list…")
    counties = fetch_counties()
    county_id_by_short = {c["shortName"]: c["id"] for c in counties}
    print(f"  → {len(counties)} counties")

    if args.uat_siruta is not None:
        row = con.execute(
            "SELECT DISTINCT judet FROM streets WHERE siruta = ?", (args.uat_siruta,)
        ).fetchone()
        if not row:
            sys.exit(f"SIRUTA {args.uat_siruta} not found in the electoral source — "
                      "can't derive its RENNS county id. Pass a known SIRUTA.")
        county_id = county_id_by_short.get(row[0])
        if county_id is None:
            sys.exit(f"Judet {row[0]!r} not found in RENNS county list.")
        pairs = [(county_id, args.uat_siruta)]
    else:
        print("Fetching UAT list per county…")
        pairs = []
        for c in counties:
            uats = fetch_uats(c["id"])
            pairs.extend((c["id"], u["id"]) for u in uats)
        print(f"  → {len(pairs):,} (county, UAT) pairs")

    print(f"Fetching roads for {len(pairs):,} UATs ({args.workers} workers)…")
    grouped = {}
    done = 0
    empty_uats = 0
    errors = 0

    def process(pair):
        county_id, uat_siruta = pair
        return fetch_roads(county_id, uat_siruta)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process, p): p for p in pairs}
        for fut in as_completed(futures):
            done += 1
            if done % 200 == 0:
                print(f"  … {done:,}/{len(pairs):,} UATs processed", flush=True)
            try:
                items = fut.result()
            except Exception as e:
                errors += 1
                print(f"  ! failed for {futures[fut]}: {e}", file=sys.stderr)
                continue
            if not items:
                empty_uats += 1
                continue
            for item in items:
                rec = build_row(item)
                if rec is None:
                    continue
                key = (rec["uat_siruta"], rec["name_normalized"])
                slot = grouped.setdefault(key, {**rec, "source_road_ids": []})
                slot["source_road_ids"].append(rec["road_id"])

    print(f"\nUATs processed:      {done:,}")
    print(f"  with ≥1 road:      {done - empty_uats - errors:,}")
    print(f"  with zero roads:   {empty_uats:,}")
    print(f"  failed:            {errors:,}")
    print(f"Grouped into {len(grouped):,} distinct (uat_siruta, name_normalized) rows.")

    if args.dry_run:
        print("[DRY RUN] Not writing.")
        con.close()
        return

    if args.rebuild:
        con.execute("DELETE FROM street_renns_matches")
        con.execute("DELETE FROM renns_streets")

    insert_rows = [
        {
            "source_road_ids": json.dumps(g["source_road_ids"]),
            "uat_siruta": g["uat_siruta"],
            "judet": g["judet"],
            "locality_raw": g["locality_raw"],
            "road_type_raw": g["road_type_raw"],
            "street_type": g["street_type"],
            "name": g["name"],
            "name_normalized": g["name_normalized"],
            "title": g["title"],
            "rank": g["rank"],
            "is_saint": g["is_saint"],
            "is_date": g["is_date"],
            "is_numeric": g["is_numeric"],
            "core_name": g["core_name"],
            "core_name_norm": g["core_name_norm"],
            "road_status": g["road_status"],
        }
        for g in grouped.values()
    ]
    con.executemany(
        """INSERT INTO renns_streets
           (source_road_ids, uat_siruta, judet, locality_raw, road_type_raw,
            street_type, name, name_normalized, title, rank, is_saint, is_date,
            is_numeric, core_name, core_name_norm, road_status)
           VALUES (:source_road_ids, :uat_siruta, :judet, :locality_raw, :road_type_raw,
                   :street_type, :name, :name_normalized, :title, :rank, :is_saint, :is_date,
                   :is_numeric, :core_name, :core_name_norm, :road_status)
           ON CONFLICT(uat_siruta, name_normalized) DO UPDATE SET
             source_road_ids = excluded.source_road_ids,
             judet           = excluded.judet,
             locality_raw    = excluded.locality_raw,
             road_type_raw   = excluded.road_type_raw,
             street_type     = excluded.street_type,
             name            = excluded.name,
             title           = excluded.title,
             rank            = excluded.rank,
             is_saint        = excluded.is_saint,
             is_date         = excluded.is_date,
             is_numeric      = excluded.is_numeric,
             core_name       = excluded.core_name,
             core_name_norm  = excluded.core_name_norm,
             road_status     = excluded.road_status""",
        insert_rows,
    )
    con.commit()
    con.close()
    print(f"\nInserted/updated {len(insert_rows):,} rows in renns_streets.")


if __name__ == "__main__":
    main()
