"""Populate `street_osm_matches` by joining streets_dedup ↔ osm_streets.

Pass 1: exact match on (siruta, name_normalized) — confidence 1.0.
Pass 2: fallback on (siruta, core_name_norm)     — confidence 0.6, only for
        registry rows still unmatched after pass 1.

Pure SQL. No geo deps. Idempotent: clears existing rows before re-inserting.

Below the fuzzy_core_name threshold we deliberately stop. Levenshtein on
~100k×100k name pairs produces enough false positives to poison the
importance index downstream — we'd rather surface gaps in the coverage
report (tools/osm_sanity.py) than auto-link.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args()


def main():
    args = parse_args()
    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found at {db}. Run build_db.py first.")

    con = sqlite3.connect(db)
    osm_count = con.execute("SELECT COUNT(*) FROM osm_streets").fetchone()[0]
    if osm_count == 0:
        sys.exit("osm_streets is empty. Run tools/osm_ingest.py first.")

    if args.dry_run:
        con.execute("CREATE TEMP TABLE tmp_matches AS SELECT * FROM street_osm_matches WHERE 0")
        target = "tmp_matches"
    else:
        con.execute("DELETE FROM street_osm_matches")
        target = "street_osm_matches"

    # Pass 1: exact normalized name within the same UAT.
    # We resolve street_id to MIN(id) per (uat, name_normalized) — the same
    # grain that streets_dedup uses, so we don't multi-link section-rows.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, osm_street_id, match_type, confidence)
        SELECT sd.id, o.id, 'exact_normalized', 1.0
          FROM streets_dedup sd
          JOIN osm_streets   o
            ON o.uat_siruta = sd.siruta
           AND o.name_normalized = sd.name_normalized
    """)
    exact = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='exact_normalized'").fetchone()[0]

    # Pass 2: core_name_norm fallback, but only for streets not already linked.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, osm_street_id, match_type, confidence)
        SELECT sd.id, o.id, 'fuzzy_core_name', 0.6
          FROM streets_dedup sd
          JOIN osm_streets   o
            ON o.uat_siruta = sd.siruta
           AND o.core_name_norm = sd.core_name_norm
           AND o.core_name_norm IS NOT NULL
         WHERE sd.id NOT IN (SELECT street_id FROM {target})
    """)
    fuzzy = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='fuzzy_core_name'").fetchone()[0]

    total_streets = con.execute("SELECT COUNT(*) FROM streets_dedup").fetchone()[0]
    matched_streets = con.execute(f"SELECT COUNT(DISTINCT street_id) FROM {target}").fetchone()[0]
    matched_osm = con.execute(f"SELECT COUNT(DISTINCT osm_street_id) FROM {target}").fetchone()[0]

    print(f"Pass 1 (exact_normalized): {exact}")
    print(f"Pass 2 (fuzzy_core_name):  {fuzzy}")
    print(f"Registry coverage:         {matched_streets}/{total_streets} "
          f"({100*matched_streets/total_streets:.1f}%)")
    print(f"OSM coverage:              {matched_osm}/{osm_count} "
          f"({100*matched_osm/osm_count:.1f}%)")

    if args.dry_run:
        print("[DRY RUN] Not committed.")
    else:
        con.commit()
    con.close()


if __name__ == "__main__":
    main()
