"""Sanity-check the OSM ingest + score by inspecting reference UATs.

Two reports:
1. Top-10 streets by importance_v1 in 5 reference UATs (Bucharest Sector 1,
   Cluj-Napoca, Sibiu, a small town, a rural commune). Eyeball check that
   obvious main streets surface at the top.
2. Per-UAT electoral coverage for those same UATs (% of electoral_dedup rows
   with at least one OSM match). Flag <50%.

Read-only. No deps beyond sqlite3.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# (label, siruta) — chosen to span scale: capital sector → big city → mid town
# → small town → rural commune. Adjust freely; SIRUTA codes from
# data/gis/populatie-romania-siruta-coords.csv.
REFERENCE_UATS = [
    ("București (Sector 1)", 179141),
    ("Cluj-Napoca",           54975),
    ("Sibiu",                143450),  # MUNICIPIUL SIBIU
    ("Câmpulung Moldovenesc",146502),  # MUNICIPIUL CÂMPULUNG MOLDOVENESC, SV
    ("Cornu (rural, PH)",    132805),  # CORNU, PH
]


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--limit", type=int, default=10)
    return ap.parse_args()


def main():
    args = parse_args()
    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found at {db}.")

    con = sqlite3.connect(db)
    if con.execute("SELECT COUNT(*) FROM osm_streets").fetchone()[0] == 0:
        sys.exit("osm_streets is empty — run tools/osm_ingest.py and tools/osm_score.py first.")

    print("=" * 72)
    print(f"TOP {args.limit} STREETS BY importance_v1")
    print("=" * 72)
    for label, siruta in REFERENCE_UATS:
        print(f"\n— {label} (SIRUTA {siruta}) —")
        rows = con.execute("""
            SELECT name, highway_class, ROUND(length_m) AS len_m,
                   ref, ROUND(importance_v1, 1) AS imp,
                   ROUND(importance_v1_uat_z, 2) AS z
              FROM osm_streets
             WHERE uat_siruta = ?
             ORDER BY importance_v1 DESC
             LIMIT ?
        """, (siruta, args.limit)).fetchall()
        if not rows:
            print("  (no OSM rows for this UAT — check ingest spatial join)")
            continue
        for name, hc, lm, ref, imp, z in rows:
            ref_str = f" [{ref}]" if ref else ""
            print(f"  {imp:>6.1f}  z={z:>+5.2f}  {hc:<13} {int(lm):>5}m  {name}{ref_str}")

    print("\n" + "=" * 72)
    print("ELECTORAL COVERAGE PER REFERENCE UAT")
    print("=" * 72)
    print(f"{'UAT':<30} {'reg streets':>12} {'matched':>10} {'coverage':>10}")
    for label, siruta in REFERENCE_UATS:
        total = con.execute(
            "SELECT COUNT(*) FROM electoral_dedup WHERE siruta = ?", (siruta,)
        ).fetchone()[0]
        matched = con.execute("""
            SELECT COUNT(DISTINCT sd.id)
              FROM electoral_dedup sd
              JOIN street_osm_matches m ON m.street_id = sd.id
             WHERE sd.siruta = ?
        """, (siruta,)).fetchone()[0]
        if total == 0:
            print(f"{label:<30} {total:>12} {matched:>10} {'—':>10}")
            continue
        pct = 100 * matched / total
        flag = "  ⚠ <50%" if pct < 50 else ""
        print(f"{label:<30} {total:>12} {matched:>10} {pct:>9.1f}%{flag}")

    print("\n" + "=" * 72)
    print("OSM STREETS WITH NO ELECTORAL MATCH (sample of 20)")
    print("=" * 72)
    print("(real coverage gaps OR OSM noise — eyeball before trusting)\n")
    rows = con.execute("""
        SELECT o.uat_siruta, o.name, o.highway_class, ROUND(o.length_m) AS len_m
          FROM osm_streets o
         WHERE NOT EXISTS (
                   SELECT 1 FROM street_osm_matches m WHERE m.osm_street_id = o.id
               )
         ORDER BY o.importance_v1 DESC
         LIMIT 20
    """).fetchall()
    for siruta, name, hc, lm in rows:
        print(f"  SIRUTA={siruta:>7}  {hc:<13} {int(lm):>5}m  {name}")

    con.close()


if __name__ == "__main__":
    main()
