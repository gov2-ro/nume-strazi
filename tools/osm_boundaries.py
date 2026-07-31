"""Build UAT boundary polygons from OSM and resolve each to a SIRUTA code.

Populates `uat_boundaries`, the spatial index that `tools/osm_ingest.py` uses to
assign each OSM way to the UAT that actually contains it.

Why this exists
---------------
The previous ingest assigned ways by nearest UAT *centroid*, drawn from a
centroid list filtered to SIRUTAs present in the electoral source. That had two
consequences, both wrong:

  1. OSM could only ever land in the ~1,207 UATs the electoral export happens to
     cover, out of Romania's 3,181. The electoral source is a starter list, not
     an authority (CLAUDE.md "4 sources with equal standing"), so nothing else
     should inherit its coverage.
  2. Ways outside those UATs were not dropped — `nearest_siruta` snapped them to
     the nearest *in-scope* centroid up to ~55 km away, silently attributing
     one UAT's streets to a neighbour.

Resolution strategy
-------------------
OSM Romania does not tag SIRUTA on boundaries (`siruta:code` appears on 6 of
3,379 admin_level=8 relations), so the mapping is geometric: every SIRUTA in the
coordinates reference has a known centroid, and a boundary owns the SIRUTA whose
centroid falls inside it. The Geofabrik extract overlaps HU/RS/BG/UA territory;
those foreign communes contain no Romanian centroid and drop out for free.

Bucharest is special-cased: OSM models the six sectors as admin_level=9 relations
named "Sector N", and the coordinates reference only carries the municipality
centroid (179132). Sectors are mapped by name, and 179132 is excluded from the
centroid pool so it cannot claim whichever sector polygon happens to contain it.

Idempotent: --rebuild drops and repopulates the table.

Usage:
  python3 tools/osm_boundaries.py
  python3 tools/osm_boundaries.py --pbf data/reference/romania-staging.osm.pbf
  python3 tools/osm_boundaries.py --rebuild
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streets_lib import normalize_match  # noqa: E402

try:
    import osmium
    import shapely
    from shapely import STRtree
except ImportError as exc:  # pragma: no cover
    sys.exit(f"Missing dependency: {exc}. Needs pyosmium + shapely.")

# OSM models Bucharest's sectors as admin_level=9 "Sector N" relations. The
# SIRUTA coords reference has only the municipality (179132), so map by name.
_BUCHAREST_SECTORS = {
    "sector 1": 179141,
    "sector 2": 179150,
    "sector 3": 179169,
    "sector 4": 179178,
    "sector 5": 179187,
    "sector 6": 179196,
}
# Excluded from the centroid pool: covered by the six sector polygons above.
_BUCHAREST_MUNICIPALITY_SIRUTA = 179132

DDL = """
CREATE TABLE IF NOT EXISTS uat_boundaries (
    siruta        INTEGER PRIMARY KEY,
    osm_rel_id    INTEGER,
    osm_name      TEXT,
    admin_level   INTEGER,
    match_method  TEXT NOT NULL,   -- centroid_in_polygon | bucharest_sector | name_unique
    area_km2      REAL,
    geometry_wkt  TEXT NOT NULL
);
"""


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--pbf", default="data/reference/romania-latest.osm.pbf")
    ap.add_argument("--siruta-coords",
                    default="data/gis/populatie-romania-siruta-coords.csv")
    ap.add_argument("--rebuild", action="store_true",
                    help="Drop uat_boundaries before inserting.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve and report, do not write.")
    return ap.parse_args()


def load_siruta_centroids(coords_csv: Path) -> dict[int, tuple[float, float]]:
    """Every SIRUTA in the reference file — deliberately NOT filtered to the
    electoral source. Bucharest municipality is excluded (see module docstring)."""
    out: dict[int, tuple[float, float]] = {}
    with coords_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                siruta = int(row["siruta"])
                lat, lon = float(row["lat"]), float(row["long"])
            except (KeyError, ValueError):
                continue
            if siruta == _BUCHAREST_MUNICIPALITY_SIRUTA:
                continue
            out[siruta] = (lat, lon)
    return out


def collect_boundaries(pbf: Path) -> list[dict]:
    """Stream admin_level=8 boundaries (plus Bucharest's level-9 sectors)."""
    wkt_fab = osmium.geom.WKTFactory()
    keep: list[dict] = []
    seen = 0

    fp = (osmium.FileProcessor(pbf)
          .with_areas()
          .with_filter(osmium.filter.TagFilter(("boundary", "administrative"))))

    for obj in fp:
        if not obj.is_area():
            continue
        tags = obj.tags
        lvl = tags.get("admin_level")
        name = tags.get("name") or ""
        # Hungarian-majority UATs carry the Hungarian name in `name` (Ojdula →
        # "Ozsdola", Sândominic → "Csíkszentdomokos"), so the name fallback needs
        # the Romanian forms too.
        alt_names = [tags.get(k) for k in ("name:ro", "official_name", "int_name")]
        if lvl == "9":
            # Only Bucharest sectors; every other level-9 is a foreign village.
            if normalize_match(name) not in _BUCHAREST_SECTORS:
                continue
        elif lvl != "8":
            continue

        seen += 1
        try:
            geom = shapely.from_wkt(wkt_fab.create_multipolygon(obj))
        except Exception:
            continue
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
            if geom.is_empty or not geom.is_valid:
                continue

        keep.append({
            "osm_rel_id": obj.orig_id(),
            "name": name,
            "alt_names": [n for n in alt_names if n],
            "admin_level": int(lvl),
            "geom": geom,
        })
        if seen % 500 == 0:
            print(f"  … {seen:,} boundary areas scanned, {len(keep):,} kept",
                  flush=True)

    return keep


def _area_km2(geom) -> float:
    """Rough planar area at Romania's latitude. Good enough for a sanity column."""
    lat = geom.centroid.y
    import math
    km_per_deg_lat = 110.574
    km_per_deg_lon = 111.320 * math.cos(math.radians(lat))
    return geom.area * km_per_deg_lat * km_per_deg_lon


def resolve(boundaries: list[dict],
            centroids: dict[int, tuple[float, float]]) -> tuple[dict[int, dict], dict]:
    """Assign a SIRUTA to each boundary. Returns (siruta -> boundary, stats)."""
    sirutas = list(centroids.keys())
    points = [shapely.Point(centroids[s][1], centroids[s][0]) for s in sirutas]
    tree = STRtree(points)

    assigned: dict[int, dict] = {}
    stats = {
        "boundaries": len(boundaries),
        "bucharest_sector": 0,
        "centroid_in_polygon": 0,
        "name_unique": 0,
        "no_centroid": 0,
        "multi_centroid": 0,
        "conflict": 0,
    }

    # Name index for the fallback pass — only usable when nationally unique.
    by_norm_name: dict[str, list[int]] = {}

    def _claim(siruta: int, b: dict, method: str):
        prev = assigned.get(siruta)
        if prev is not None:
            # Keep the larger polygon; a UAT should have exactly one boundary.
            stats["conflict"] += 1
            if prev["geom"].area >= b["geom"].area:
                return
        assigned[siruta] = {**b, "match_method": method}

    deferred: list[dict] = []

    for b in boundaries:
        norm = normalize_match(b["name"] or "")
        if b["admin_level"] == 9:
            siruta = _BUCHAREST_SECTORS.get(norm)
            if siruta:
                _claim(siruta, b, "bucharest_sector")
                stats["bucharest_sector"] += 1
            continue

        by_norm_name.setdefault(norm, []).append(id(b))

        hits = tree.query(b["geom"], predicate="contains")
        if len(hits) == 1:
            _claim(sirutas[int(hits[0])], b, "centroid_in_polygon")
            stats["centroid_in_polygon"] += 1
        elif len(hits) == 0:
            stats["no_centroid"] += 1
            deferred.append(b)
        else:
            # Several reference centroids inside one boundary (villages folded
            # into a commune). Take the one nearest the polygon's interior point.
            rp = b["geom"].representative_point()
            best = min((int(i) for i in hits), key=lambda i: points[i].distance(rp))
            _claim(sirutas[best], b, "centroid_in_polygon")
            stats["multi_centroid"] += 1
            stats["centroid_in_polygon"] += 1

    # Fallback: a boundary with no centroid inside it may still be a real
    # Romanian UAT whose reference centroid is slightly off (bad geocode).
    # Accept only when the name maps to exactly one still-unassigned SIRUTA.
    unassigned_by_name: dict[str, list[int]] = {}
    for siruta in sirutas:
        if siruta in assigned:
            continue
        unassigned_by_name.setdefault(_NAME_BY_SIRUTA.get(siruta, ""), []).append(siruta)

    for b in deferred:
        for candidate_name in [b["name"]] + b.get("alt_names", []):
            norm = normalize_match(candidate_name or "")
            cands = [s for s in unassigned_by_name.get(norm, []) if s not in assigned]
            if len(cands) == 1:
                _claim(cands[0], b, "name_unique")
                stats["name_unique"] += 1
                stats["no_centroid"] -= 1
                break

    return assigned, stats


# Populated by main() before resolve() runs — SIRUTA -> normalized UAT name.
_NAME_BY_SIRUTA: dict[int, str] = {}


def load_names(coords_csv: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    with coords_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                siruta = int(row["siruta"])
            except (KeyError, ValueError):
                continue
            label = (row.get("localitate") or row.get("namecheck") or "").strip()
            # Strip the "Municipiul "/"Orașul "/"Comuna " prefix OSM omits.
            label = re.sub(r"^(municipiul|orasul|orașul|comuna)\s+", "", label,
                           flags=re.IGNORECASE)
            out[siruta] = normalize_match(label)
    return out


def main():
    args = parse_args()
    pbf = Path(args.pbf)
    coords_csv = Path(args.siruta_coords)
    if not pbf.exists():
        sys.exit(f"PBF not found: {pbf}")
    if not coords_csv.exists():
        sys.exit(f"SIRUTA coords not found: {coords_csv}")

    con = sqlite3.connect(args.db)
    con.executescript(DDL)

    centroids = load_siruta_centroids(coords_csv)
    global _NAME_BY_SIRUTA
    _NAME_BY_SIRUTA = load_names(coords_csv)
    print(f"Loaded {len(centroids):,} SIRUTA centroids "
          f"(unfiltered — all of Romania, not just the electoral source)")

    print(f"Parsing boundaries from {pbf} (two-pass area build, a few minutes)…")
    boundaries = collect_boundaries(pbf)
    print(f"  → {len(boundaries):,} admin boundary polygons built")

    assigned, stats = resolve(boundaries, centroids)

    print("\n=== resolution ===")
    print(f"  boundaries scanned      {stats['boundaries']:,}")
    print(f"  centroid_in_polygon     {stats['centroid_in_polygon']:,}"
          f"   (of which multi-centroid: {stats['multi_centroid']:,})")
    print(f"  bucharest_sector        {stats['bucharest_sector']:,}")
    print(f"  name_unique fallback    {stats['name_unique']:,}")
    print(f"  no centroid (foreign)   {stats['no_centroid']:,}")
    print(f"  polygon conflicts       {stats['conflict']:,}")
    resolvable = len(centroids) + len(_BUCHAREST_SECTORS)
    missing = sorted(set(centroids) - set(assigned))
    print(f"  → {len(assigned):,} SIRUTAs resolved of {resolvable:,} resolvable "
          f"({len(centroids):,} reference centroids + {len(_BUCHAREST_SECTORS)} "
          f"Bucharest sectors)")
    if missing:
        print(f"  unresolved SIRUTAs: {missing[:20]}"
              f"{' …' if len(missing) > 20 else ''}")

    if args.dry_run:
        print("\n[DRY RUN] Not writing.")
        con.close()
        return

    if args.rebuild:
        con.execute("DELETE FROM uat_boundaries")

    rows = [{
        "siruta": siruta,
        "osm_rel_id": b["osm_rel_id"],
        "osm_name": b["name"],
        "admin_level": b["admin_level"],
        "match_method": b["match_method"],
        "area_km2": round(_area_km2(b["geom"]), 3),
        "geometry_wkt": b["geom"].wkt,
    } for siruta, b in assigned.items()]

    con.executemany("""
        INSERT INTO uat_boundaries
            (siruta, osm_rel_id, osm_name, admin_level, match_method,
             area_km2, geometry_wkt)
        VALUES (:siruta, :osm_rel_id, :osm_name, :admin_level, :match_method,
                :area_km2, :geometry_wkt)
        ON CONFLICT(siruta) DO UPDATE SET
            osm_rel_id   = excluded.osm_rel_id,
            osm_name     = excluded.osm_name,
            admin_level  = excluded.admin_level,
            match_method = excluded.match_method,
            area_km2     = excluded.area_km2,
            geometry_wkt = excluded.geometry_wkt
    """, rows)
    con.commit()
    print(f"\nWrote {len(rows):,} rows to uat_boundaries.")
    con.close()


if __name__ == "__main__":
    main()
