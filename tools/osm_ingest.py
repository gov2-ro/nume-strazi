"""Ingest OSM ways from a Romania PBF extract into `osm_streets`.

Scope: named highway ways. Motorways and trunk roads are excluded by design
(see CODE_SPEC §11). Service roads kept only when named.

OSM splits a single street into many `way` rows at every junction. We group by
(uat_siruta, name_normalized) so the table mirrors the grain of electoral_dedup.

UAT assignment: each way's midpoint is tested for containment in the OSM
admin_level=8 boundary polygons held in `uat_boundaries` — run
`tools/osm_boundaries.py` first. Ways landing outside every boundary are dropped,
not snapped.

This replaces an earlier nearest-centroid scheme whose centroid list was filtered
to SIRUTAs present in the electoral source. That capped OSM at the ~1,207 UATs
the electoral export covers (of 3,181) and, worse, snapped out-of-scope ways up
to ~55 km to the nearest in-scope centroid, silently attributing one UAT's
streets to a neighbour. The electoral source is a starter list with no special
standing (CLAUDE.md: "4 sources with equal standing"), so nothing else should
inherit its coverage. The original pyrosm/geopandas containment approach was
abandoned because geopandas will not build on Python 3.12; pyosmium's own
AreaManager plus shapely's STRtree needs neither.

Idempotent: --rebuild drops `osm_streets` rows before inserting.

Usage:
  python3 tools/osm_boundaries.py --rebuild        # prerequisite, ~15 s
  python3 tools/osm_ingest.py
  python3 tools/osm_ingest.py --pbf data/reference/romania-latest.osm.pbf
  python3 tools/osm_ingest.py --rebuild
  python3 tools/osm_ingest.py --uat-siruta 179132   # single UAT for fast iteration
"""
from __future__ import annotations

import argparse
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

def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--pbf", default="data/reference/romania-latest.osm.pbf")
    ap.add_argument("--rebuild", action="store_true",
                    help="Truncate osm_streets before inserting.")
    ap.add_argument("--uat-siruta", type=int, default=None,
                    help="Restrict ingest to one UAT (SIRUTA). For iteration.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and group, print stats, do not write.")
    return ap.parse_args()


class UatIndex:
    """Point-in-polygon lookup over the OSM admin boundaries in `uat_boundaries`.

    Covers every UAT OSM knows about — not just the ones the electoral source
    happens to list. A point outside every boundary resolves to None and its way
    is dropped; there is deliberately no nearest-neighbour fallback, since that
    is exactly the behaviour that used to misattribute streets across borders.
    """

    def __init__(self, con: sqlite3.Connection):
        import shapely
        from shapely import STRtree

        rows = con.execute(
            "SELECT siruta, geometry_wkt FROM uat_boundaries"
        ).fetchall()
        if not rows:
            sys.exit(
                "uat_boundaries is empty — run `python3 tools/osm_boundaries.py "
                "--rebuild` first (it builds the admin_level=8 polygons this "
                "ingest assigns ways to)."
            )
        self.sirutas = [r[0] for r in rows]
        self.geoms = [shapely.from_wkt(r[1]) for r in rows]
        self.tree = STRtree(self.geoms)

    def __len__(self) -> int:
        return len(self.sirutas)

    def locate(self, lon: float, lat: float) -> int | None:
        import shapely

        pt = shapely.Point(lon, lat)
        hits = self.tree.query(pt, predicate="intersects")
        if len(hits) == 0:
            return None
        if len(hits) == 1:
            return self.sirutas[int(hits[0])]
        # Overlapping boundaries (shared borders, or a sector inside the city
        # polygon): prefer the smallest containing area — the most specific UAT.
        best = min((int(i) for i in hits), key=lambda i: self.geoms[i].area)
        return self.sirutas[best]


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

    try:
        import osmium
        import osmium.geom
        import shapely
        import shapely.ops
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}\n  pip install osmium shapely")

    con = sqlite3.connect(db_path)

    print("Loading UAT boundary index…")
    uats = UatIndex(con)
    print(f"  → {len(uats):,} UAT polygons indexed")

    wkt_fab = osmium.geom.WKTFactory()
    grouped: dict = {}
    skipped = 0
    outside = 0
    way_count = 0

    class _Handler(osmium.SimpleHandler):
        def way(self, w):
            nonlocal skipped, outside, way_count
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

            siruta = uats.locate(mid.x, mid.y)
            if siruta is None:
                outside += 1
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
    print(f"  → {len(grouped):,} (UAT, street) groups")
    print(f"     {skipped:,} ways with unusable geometry")
    print(f"     {outside:,} ways outside every Romanian UAT boundary "
          f"(foreign territory in the extract — dropped, not snapped)")

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
            "segment_count": len(slot["way_ids"]),
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
            highway_class, ref, length_m, segment_count, way_ids, geometry_wkt)
           VALUES (:uat_siruta, :name, :name_normalized, :street_type, :title, :rank,
                   :is_saint, :is_date, :is_numeric, :core_name, :core_name_norm,
                   :highway_class, :ref, :length_m, :segment_count, :way_ids,
                   :geometry_wkt)
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
             segment_count  = excluded.segment_count,
             way_ids        = excluded.way_ids,
             geometry_wkt   = excluded.geometry_wkt""",
        rows,
    )
    con.commit()
    con.close()
    print(f"Inserted/updated {len(rows):,} rows in osm_streets.")


if __name__ == "__main__":
    main()
