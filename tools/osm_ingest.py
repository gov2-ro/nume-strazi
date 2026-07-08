"""Ingest OSM ways from a Romania PBF extract into `osm_streets`.

Scope: named highway ways. Motorways and trunk roads are excluded by design
(see CODE_SPEC §11). Service roads kept only when named.

OSM splits a single street into many `way` rows at every junction. We group by
(uat_siruta, name_normalized) so the table mirrors the grain of streets_dedup.

UAT assignment: each way's midpoint is matched to the nearest UAT centroid from
the SIRUTA coordinates reference file, filtered to SIRUTAs present in the
registry DB. This replaces the original pyrosm/geopandas polygon-containment
approach, which cannot be built on Python 3.12.

Idempotent: --rebuild drops `osm_streets` rows before inserting.

Usage:
  python3 tools/osm_ingest.py
  python3 tools/osm_ingest.py --pbf data/reference/romania-latest.osm.pbf
  python3 tools/osm_ingest.py --rebuild
  python3 tools/osm_ingest.py --uat-siruta 179132   # single UAT for fast iteration
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streets_lib import normalize_match, strip_street_type, extract_features  # noqa: E402

KEPT_HIGHWAY = {
    "primary", "secondary", "tertiary",
    "residential", "unclassified", "living_street",
    "pedestrian", "service",
}

# Romania bounding box for the spatial grid
_GRID_LAT_MIN, _GRID_LON_MIN = 43.0, 19.0
_GRID_STEP = 0.5  # degrees per cell


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--pbf", default="data/reference/romania-latest.osm.pbf")
    ap.add_argument("--siruta-coords",
                    default="data/gis/populatie-romania-siruta-coords.csv")
    ap.add_argument("--rebuild", action="store_true",
                    help="Truncate osm_streets before inserting.")
    ap.add_argument("--uat-siruta", type=int, default=None,
                    help="Restrict ingest to one UAT (SIRUTA). For iteration.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and group, print stats, do not write.")
    return ap.parse_args()


# The SIRUTA coords CSV uses the Bucharest municipality code (179132) but the
# registry splits Bucharest into 6 sectors with separate SIRUTAs. Hardcode
# approximate sector centroids so nearest-centroid assignment works for Bucharest.
_BUCHAREST_SECTOR_CENTROIDS = {
    179141: (44.47, 26.01),   # Sector 1 — Aviatorilor / Victoriei
    179150: (44.46, 26.12),   # Sector 2 — Colentina / Iancului
    179169: (44.43, 26.16),   # Sector 3 — Titan / Dristor
    179178: (44.40, 26.07),   # Sector 4 — Berceni / Sudului
    179187: (44.40, 26.00),   # Sector 5 — Rahova / Ferentari
    179196: (44.44, 25.97),   # Sector 6 — Militari / Drumul Taberei
}


def load_centroid_index(con: sqlite3.Connection, coords_csv: Path) -> list:
    """Return [(siruta, lat, lon)] filtered to SIRUTAs in the registry DB."""
    siruta_in_db = {
        row[0]
        for row in con.execute(
            "SELECT DISTINCT siruta FROM streets WHERE siruta IS NOT NULL"
        )
    }
    out = []
    with coords_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                siruta = int(row["siruta"])
                if siruta not in siruta_in_db:
                    continue
                out.append((siruta, float(row["lat"]), float(row["long"])))
            except (KeyError, ValueError):
                continue
    # Add Bucharest sectors that are missing from the coords CSV
    for siruta, (lat, lon) in _BUCHAREST_SECTOR_CENTROIDS.items():
        if siruta in siruta_in_db:
            out.append((siruta, lat, lon))
    return out


def build_grid(centroids: list) -> dict:
    """Bucket centroids into 0.5°×0.5° grid cells for O(1) neighbour lookup."""
    grid: dict = {}
    for item in centroids:
        _, lat, lon = item
        cell = (
            int((lat - _GRID_LAT_MIN) / _GRID_STEP),
            int((lon - _GRID_LON_MIN) / _GRID_STEP),
        )
        grid.setdefault(cell, []).append(item)
    return grid


def nearest_siruta(lat: float, lon: float, grid: dict) -> int | None:
    """Return SIRUTA of the nearest UAT centroid using equirectangular distance."""
    ci = int((lat - _GRID_LAT_MIN) / _GRID_STEP)
    cj = int((lon - _GRID_LON_MIN) / _GRID_STEP)
    candidates = []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            candidates.extend(grid.get((ci + di, cj + dj), []))
    if not candidates:
        candidates = [item for cell in grid.values() for item in cell]
    if not candidates:
        return None
    cos_lat = math.cos(math.radians(lat))
    best_siruta, best_d = None, float("inf")
    for siruta, clat, clon in candidates:
        d = (lat - clat) ** 2 + ((lon - clon) * cos_lat) ** 2
        if d < best_d:
            best_d, best_siruta = d, siruta
    return best_siruta


def shape_length_m(geom) -> float:
    """Approximate geodesic length in metres for a (Multi)LineString (EPSG:4326)."""
    R = 6_371_000

    def _segs(g):
        if g.geom_type == "LineString":
            yield list(g.coords)
        elif g.geom_type == "MultiLineString":
            for part in g.geoms:
                yield list(part.coords)

    total = 0.0
    for coords in _segs(geom):
        for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
            phi = math.radians((lat1 + lat2) / 2)
            dx = math.radians(lon2 - lon1) * math.cos(phi)
            dy = math.radians(lat2 - lat1)
            total += R * math.hypot(dx, dy)
    return total


_CLASS_ORDER = [
    "service", "pedestrian", "living_street", "residential",
    "unclassified", "tertiary", "secondary", "primary",
]


def class_rank(c: str) -> int:
    try:
        return _CLASS_ORDER.index(c)
    except ValueError:
        return -1


def main():
    args = parse_args()

    pbf = Path(args.pbf)
    if not pbf.exists():
        sys.exit(
            f"PBF not found at {pbf}.\n"
            "Download: wget https://download.geofabrik.de/europe/romania-latest.osm.pbf"
            f" -O {pbf}"
        )

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"DB not found at {db_path}. Run build_db.py first.")

    coords_csv = Path(args.siruta_coords)
    if not coords_csv.exists():
        sys.exit(f"SIRUTA coords CSV not found at {coords_csv}.")

    try:
        import osmium
        import osmium.geom
        import shapely
        import shapely.ops
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}\n  pip install osmium shapely")

    con = sqlite3.connect(db_path)

    print("Loading UAT centroid index…")
    centroids = load_centroid_index(con, coords_csv)
    grid = build_grid(centroids)
    print(f"  → {len(centroids)} UATs indexed")

    wkt_fab = osmium.geom.WKTFactory()
    grouped: dict = {}
    skipped = 0
    way_count = 0

    class _Handler(osmium.SimpleHandler):
        def way(self, w):
            nonlocal skipped, way_count
            way_count += 1
            if way_count % 200_000 == 0:
                print(f"  … {way_count:,} ways scanned, {len(grouped):,} groups", flush=True)

            hw = w.tags.get("highway")
            name = w.tags.get("name")
            if hw not in KEPT_HIGHWAY or not name:
                return

            try:
                wkt_str = wkt_fab.create_linestring(w)
                geom = shapely.from_wkt(wkt_str)
                mid = geom.interpolate(0.5, normalized=True)
            except Exception:
                skipped += 1
                return

            siruta = nearest_siruta(mid.y, mid.x, grid)
            if siruta is None:
                skipped += 1
                return
            if args.uat_siruta is not None and siruta != args.uat_siruta:
                return

            name_norm = normalize_match(name)
            if not name_norm:
                return
            street_type, core_display = strip_street_type(name)
            feats = extract_features(core_display) if core_display else {
                "title": None, "rank": None, "is_saint": 0, "is_date": 0,
                "is_numeric": 0, "core_name": None,
            }
            core_norm = normalize_match(feats["core_name"]) if feats["core_name"] else None

            ref = w.tags.get("ref")
            key = (siruta, name_norm)
            slot = grouped.setdefault(key, {
                "uat_siruta": siruta,
                "name": name,
                "name_normalized": name_norm,
                "street_type": street_type,
                "title": feats["title"],
                "rank": feats["rank"],
                "is_saint": feats["is_saint"],
                "is_date": feats["is_date"],
                "is_numeric": feats["is_numeric"],
                "core_name": feats["core_name"],
                "core_name_norm": core_norm,
                "highway_class": hw,
                "ref": ref,
                "way_ids": [],
                "geoms": [],
            })
            slot["way_ids"].append(int(w.id))
            slot["geoms"].append(geom)
            if class_rank(hw) > class_rank(slot["highway_class"]):
                slot["highway_class"] = hw
            if not slot["ref"] and ref:
                slot["ref"] = ref

    print(f"Parsing PBF: {pbf}")
    print("  (location pass + way extraction — may take 10–30 min on full Romania PBF)")
    _Handler().apply_file(str(pbf), locations=True)
    print(f"  → {len(grouped):,} (UAT, street) groups  ({skipped:,} ways skipped)")

    if args.dry_run:
        print("[DRY RUN] Not writing.")
        con.close()
        return

    print("Merging geometries and writing to DB…")
    rows = []
    for slot in grouped.values():
        merged = shapely.ops.unary_union(slot["geoms"])
        rows.append({
            "uat_siruta": slot["uat_siruta"],
            "name": slot["name"],
            "name_normalized": slot["name_normalized"],
            "street_type": slot["street_type"],
            "title": slot["title"],
            "rank": slot["rank"],
            "is_saint": slot["is_saint"],
            "is_date": slot["is_date"],
            "is_numeric": slot["is_numeric"],
            "core_name": slot["core_name"],
            "core_name_norm": slot["core_name_norm"],
            "highway_class": slot["highway_class"],
            "ref": slot["ref"],
            "length_m": shape_length_m(merged),
            "way_ids": json.dumps(slot["way_ids"]),
            "geometry_wkt": merged.wkt,
        })

    if args.rebuild:
        con.execute("DELETE FROM street_osm_matches")
        con.execute("DELETE FROM osm_streets")

    con.executemany(
        """INSERT INTO osm_streets
           (uat_siruta, name, name_normalized, street_type, title, rank,
            is_saint, is_date, is_numeric, core_name, core_name_norm,
            highway_class, ref, length_m, way_ids, geometry_wkt)
           VALUES (:uat_siruta, :name, :name_normalized, :street_type, :title, :rank,
                   :is_saint, :is_date, :is_numeric, :core_name, :core_name_norm,
                   :highway_class, :ref, :length_m, :way_ids, :geometry_wkt)
           ON CONFLICT(uat_siruta, name_normalized) DO UPDATE SET
             name           = excluded.name,
             street_type    = excluded.street_type,
             title          = excluded.title,
             rank           = excluded.rank,
             is_saint       = excluded.is_saint,
             is_date        = excluded.is_date,
             is_numeric     = excluded.is_numeric,
             core_name      = excluded.core_name,
             core_name_norm = excluded.core_name_norm,
             highway_class  = excluded.highway_class,
             ref            = excluded.ref,
             length_m       = excluded.length_m,
             way_ids        = excluded.way_ids,
             geometry_wkt   = excluded.geometry_wkt""",
        rows,
    )
    con.commit()
    con.close()
    print(f"Inserted/updated {len(rows):,} rows in osm_streets.")


if __name__ == "__main__":
    main()
