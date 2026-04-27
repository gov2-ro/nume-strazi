"""Ingest OSM ways from a Romania PBF extract into `osm_streets`.

Scope: named highway ways inside populated areas only. Motorways and trunk
roads are excluded by design — see CODE_SPEC §11 (OSM enrichment) for the
rationale. Service roads kept only when named (otherwise: driveway noise).

OSM splits a single street into many `way` rows at every junction. We group
by (uat_siruta, name_normalized) so the resulting table mirrors the grain of
streets_dedup, making the downstream join 1:1.

Idempotent: --rebuild drops `osm_streets` rows before inserting.

Usage:
  python3 tools/osm_ingest.py                                  # default PBF path
  python3 tools/osm_ingest.py --pbf data/reference/romania-latest.osm.pbf
  python3 tools/osm_ingest.py --rebuild
  python3 tools/osm_ingest.py --uat-siruta 179132              # single UAT (Bucharest) for fast iteration
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

# Allow `from streets_lib import …` regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streets_lib import normalize_match, strip_street_type  # noqa: E402

# --- Highway classes we keep. Motorways/trunks excluded: they're inter-city
# infrastructure, not "streets in populated areas". `link` variants of the
# kept classes are also dropped — slip-roads, not addressable streets.
KEPT_HIGHWAY = {
    "primary", "secondary", "tertiary",
    "residential", "unclassified", "living_street",
    "pedestrian", "service",
}


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--pbf", default="data/reference/romania-latest.osm.pbf")
    ap.add_argument(
        "--siruta-coords",
        default="data/gis/populatie-romania-siruta-coords.csv",
        help="UAT centroid lookup; used as a fallback when admin polygons don't carry SIRUTA tags.",
    )
    ap.add_argument("--rebuild", action="store_true",
                    help="Truncate osm_streets before inserting.")
    ap.add_argument("--uat-siruta", type=int, default=None,
                    help="Restrict ingest to a single UAT (by SIRUTA). Useful for iteration.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and group, print stats, do not write.")
    return ap.parse_args()


def load_uat_index(coords_csv: Path) -> dict[int, tuple[str, float, float]]:
    """SIRUTA → (UAT name, lat, lon) for the spatial-join fallback."""
    index = {}
    with coords_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                siruta = int(row["siruta"])
                lat = float(row["lat"])
                lon = float(row["long"])
            except (KeyError, ValueError):
                continue
            index[siruta] = (row["localitate"], lat, lon)
    return index


def build_populated_area_mask(osm):
    """Union of admin_level=8 polygons ∩ (place=* polygons ∪ landuse=residential).

    Where `place` polygons are missing for a hamlet, fall back to a buffered
    union of `place=village|hamlet` nodes (≈300m). Returns a dict keyed by
    SIRUTA where possible, else by admin polygon name.
    """
    # Lazy imports keep this file importable without geo deps installed.
    from shapely.ops import unary_union
    from shapely.geometry import Point

    admin = osm.get_boundaries(boundary_type="administrative")
    if admin is None or admin.empty:
        raise SystemExit("No admin boundaries in PBF — wrong extract?")
    admin = admin[admin["admin_level"].astype(str) == "8"]

    landuse = osm.get_landuse(custom_filter={"landuse": ["residential"]})
    places  = osm.get_data_by_custom_criteria(
        custom_filter={"place": ["city", "town", "village", "hamlet", "suburb", "neighbourhood"]},
        filter_type="keep", keep_nodes=True, keep_ways=True, keep_relations=True,
    )

    place_polys = places[places.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    place_nodes = places[places.geometry.geom_type == "Point"]

    masks: dict[object, object] = {}
    for _, uat_row in admin.iterrows():
        uat_geom = uat_row.geometry
        # Try several known SIRUTA-bearing tags. Coverage in OSM is partial.
        siruta = None
        for key in ("ref:RO:SIRUTA", "ref:siruta", "siruta"):
            v = uat_row.get(key)
            if v:
                try:
                    siruta = int(v); break
                except (TypeError, ValueError):
                    pass
        key = siruta if siruta is not None else uat_row.get("name")

        polys_in = place_polys[place_polys.geometry.intersects(uat_geom)]
        landuse_in = landuse[landuse.geometry.intersects(uat_geom)] if landuse is not None else None
        nodes_in = place_nodes[place_nodes.geometry.within(uat_geom)]

        parts = []
        if not polys_in.empty:
            parts.append(unary_union(polys_in.geometry.tolist()))
        if landuse_in is not None and not landuse_in.empty:
            parts.append(unary_union(landuse_in.geometry.tolist()))
        if not nodes_in.empty:
            # ~300m buffer in degrees ≈ 0.003 at RO latitudes. Coarse but cheap.
            parts.append(unary_union([Point(p.x, p.y).buffer(0.003) for p in nodes_in.geometry]))

        if not parts:
            continue
        masks[key] = unary_union(parts).intersection(uat_geom)
    return masks


def shape_length_m(geom):
    """Approximate geodesic length in metres for a (Multi)LineString in EPSG:4326.

    We stay in lat/lon throughout (no GeoPandas reprojection) and use the
    equirectangular approximation per-segment. Accurate enough for ranking
    streets within a single UAT — we never compare absolute lengths across
    Romania without per-UAT z-scoring.
    """
    import math
    R = 6_371_000  # mean Earth radius, m

    def _coords_iter(g):
        if g.geom_type == "LineString":
            yield list(g.coords)
        elif g.geom_type == "MultiLineString":
            for part in g.geoms:
                yield list(part.coords)

    total = 0.0
    for coords in _coords_iter(geom):
        for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
            phi = math.radians((lat1 + lat2) / 2)
            dx = math.radians(lon2 - lon1) * math.cos(phi)
            dy = math.radians(lat2 - lat1)
            total += R * math.hypot(dx, dy)
    return total


def main():
    args = parse_args()

    pbf = Path(args.pbf)
    if not pbf.exists():
        sys.exit(
            f"PBF not found at {pbf}. Download Romania extract from Geofabrik:\n"
            "  https://download.geofabrik.de/europe/romania-latest.osm.pbf\n"
            "Or pass --pbf <path>."
        )

    try:
        from pyrosm import OSM
    except ImportError:
        sys.exit(
            "pyrosm not installed. From the project venv:\n"
            "  pip install pyrosm shapely\n"
            "(See CODE_SPEC §11 — pyrosm is the documented exception to the stdlib-only ETL rule.)"
        )

    from shapely.ops import linemerge, unary_union  # noqa: F401  (linemerge used below)

    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found at {db}. Run build_db.py first.")

    print(f"Parsing PBF: {pbf}")
    osm = OSM(str(pbf))

    print("Building populated-area mask…")
    masks = build_populated_area_mask(osm)
    print(f"  → {len(masks)} UAT masks")

    print("Extracting named highways…")
    ways = osm.get_network(network_type="all", extra_attributes=["ref"])
    if ways is None or ways.empty:
        sys.exit("No ways extracted from PBF — wrong extract?")

    ways = ways[ways["highway"].isin(KEPT_HIGHWAY) & ways["name"].notna()]
    print(f"  → {len(ways)} candidate ways")

    # Group by (UAT, normalized name) by spatial containment in each mask.
    grouped: dict[tuple[object, str], dict] = {}
    for uat_key, mask in masks.items():
        if args.uat_siruta is not None and uat_key != args.uat_siruta:
            continue
        in_uat = ways[ways.geometry.intersects(mask)]
        for _, w in in_uat.iterrows():
            name = w["name"]
            name_norm = normalize_match(name)
            if not name_norm:
                continue
            _, core_display = strip_street_type(name)
            core_norm = normalize_match(core_display) if core_display else None

            geom = w.geometry.intersection(mask)
            if geom.is_empty:
                continue

            key = (uat_key, name_norm)
            slot = grouped.setdefault(key, {
                "uat_key": uat_key,
                "name": name,
                "name_normalized": name_norm,
                "core_name_norm": core_norm,
                "highway_class": w["highway"],
                "ref": w.get("ref"),
                "way_ids": [],
                "geoms": [],
            })
            slot["way_ids"].append(int(w["id"]))
            slot["geoms"].append(geom)
            # Keep the highest class seen across way segments of one street.
            if class_rank(w["highway"]) > class_rank(slot["highway_class"]):
                slot["highway_class"] = w["highway"]
            # Take the first non-null ref (DN1, DJ105 etc.).
            if not slot["ref"] and w.get("ref"):
                slot["ref"] = w.get("ref")

    print(f"  → {len(grouped)} (uat, street) groups")

    # Resolve uat_key → SIRUTA. If not numeric, try the centroid index by name.
    uat_index = load_uat_index(Path(args.siruta_coords))
    name_to_siruta = {
        normalize_match(name).upper(): siruta
        for siruta, (name, _, _) in uat_index.items()
    }

    rows = []
    unresolved = 0
    for (uat_key, name_norm), slot in grouped.items():
        siruta = uat_key if isinstance(uat_key, int) else name_to_siruta.get(
            normalize_match(str(uat_key)).upper()
        )
        if siruta is None:
            unresolved += 1
            continue
        merged = unary_union(slot["geoms"])
        rows.append({
            "uat_siruta": siruta,
            "name": slot["name"],
            "name_normalized": slot["name_normalized"],
            "core_name_norm": slot["core_name_norm"],
            "highway_class": slot["highway_class"],
            "ref": slot["ref"],
            "length_m": shape_length_m(merged),
            "way_ids": json.dumps(slot["way_ids"]),
            "geometry_wkt": merged.wkt,
        })

    print(f"  → {len(rows)} resolvable rows ({unresolved} dropped: no SIRUTA match)")

    if args.dry_run:
        print("[DRY RUN] Not writing.")
        return

    con = sqlite3.connect(db)
    if args.rebuild:
        con.execute("DELETE FROM street_osm_matches")
        con.execute("DELETE FROM osm_streets")
    con.executemany(
        """INSERT INTO osm_streets
           (uat_siruta, name, name_normalized, core_name_norm,
            highway_class, ref, length_m, way_ids, geometry_wkt)
           VALUES (:uat_siruta, :name, :name_normalized, :core_name_norm,
                   :highway_class, :ref, :length_m, :way_ids, :geometry_wkt)
           ON CONFLICT(uat_siruta, name_normalized) DO UPDATE SET
             name          = excluded.name,
             core_name_norm= excluded.core_name_norm,
             highway_class = excluded.highway_class,
             ref           = excluded.ref,
             length_m      = excluded.length_m,
             way_ids       = excluded.way_ids,
             geometry_wkt  = excluded.geometry_wkt""",
        rows,
    )
    con.commit()
    print(f"Inserted/updated {len(rows)} rows in osm_streets.")
    con.close()


# Highway-class ordering used to pick the dominant class across way segments
# of one logical street. Mirrors the weights in tools/osm_score.py.
_CLASS_ORDER = [
    "service", "pedestrian", "living_street", "residential",
    "unclassified", "tertiary", "secondary", "primary",
]


def class_rank(c: str) -> int:
    try:
        return _CLASS_ORDER.index(c)
    except ValueError:
        return -1


if __name__ == "__main__":
    main()
