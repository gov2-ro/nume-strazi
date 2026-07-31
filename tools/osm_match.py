"""Populate `street_osm_matches` by joining electoral_dedup ↔ osm_streets.

Pass 1: exact match on (siruta, street_type, core_name_norm) — confidence 1.0.
Pass 2: fallback on (siruta, core_name_norm) only            — confidence 0.5,
        only for electoral-source rows still unmatched after pass 1.

Pass 1 replaced a raw (siruta, name_normalized) string comparison (2026-07-08)
— that never worked well for OSM specifically, since osm_streets.name_normalized
includes the street-type prefix while the electoral source's doesn't (see
CODE_SPEC): it produced only 490 matches (0.85% of the total), with 99%+ of
real matches coming from pass 2 instead. But pass 2 alone is type-blind, and
6.3% of the matches it produced connected DIFFERENT street types (e.g. the
electoral source's "Bulevardul X" linked to OSM's "Strada X") — a UAT can legitimately have both
as distinct real streets, so a type-blind match risks cross-wiring them.
Comparing (street_type, core_name_norm) directly sidesteps the
name_normalized incompatibility AND fixes the type-blindness in one move.
Pass 2's confidence is lowered from 0.6 to 0.5 to reflect that residual risk
for the cases it still has to guess on (type differs or is missing on
either side).

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

    # Pass 1: same street_type (NULL-safe via IS) + core_name_norm, within the
    # same UAT. We resolve street_id to MIN(id) per (uat, name_normalized,
    # street_type) — the same grain electoral_dedup now uses.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, osm_street_id, match_type, confidence)
        SELECT sd.id, o.id, 'exact_type_core', 1.0
          FROM electoral_dedup sd
          JOIN osm_streets   o
            ON o.uat_siruta = sd.siruta
           AND o.core_name_norm = sd.core_name_norm
           AND o.core_name_norm IS NOT NULL
           AND o.street_type IS sd.street_type
    """)
    exact = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='exact_type_core'").fetchone()[0]

    # Pass 2: core_name_norm fallback (type differs or missing on either
    # side), only for streets not already linked.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, osm_street_id, match_type, confidence)
        SELECT sd.id, o.id, 'fuzzy_core_name', 0.5
          FROM electoral_dedup sd
          JOIN osm_streets   o
            ON o.uat_siruta = sd.siruta
           AND o.core_name_norm = sd.core_name_norm
           AND o.core_name_norm IS NOT NULL
         WHERE sd.id NOT IN (SELECT street_id FROM {target})
    """)
    fuzzy = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='fuzzy_core_name'").fetchone()[0]

    total_streets = con.execute("SELECT COUNT(*) FROM electoral_dedup").fetchone()[0]
    matched_streets = con.execute(f"SELECT COUNT(DISTINCT street_id) FROM {target}").fetchone()[0]
    matched_osm = con.execute(f"SELECT COUNT(DISTINCT osm_street_id) FROM {target}").fetchone()[0]

    print(f"Pass 1 (exact_type_core): {exact}")
    print(f"Pass 2 (fuzzy_core_name): {fuzzy}")
    print(f"Electoral coverage:        {matched_streets}/{total_streets} "
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
