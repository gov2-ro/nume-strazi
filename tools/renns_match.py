"""Populate `street_renns_matches` by joining streets_dedup ↔ renns_streets.

Two-pass shape, same as tools/osm_match.py (not postal_match.py's 3-pass) —
RENNS person names follow the registry's "Firstname Surname" convention
(verified by sampling, e.g. "Mihai Eminescu"), unlike postal's frequently
reversed "Surname Firstname", so no reordered-name pass is needed here.

Pass 1: exact match on (siruta, street_type, core_name_norm) — confidence 1.0.
Pass 2: fallback on (siruta, core_name_norm) only            — confidence 0.5.

Each pass only considers registry rows still unmatched after the previous one.

Pass 1 compares (street_type, core_name_norm) rather than the raw
name_normalized string (2026-07-08) — same fix as osm_match.py: a type-blind
match risks cross-wiring two genuinely distinct streets that share a core
name but differ by type ("Bulevardul X" vs "Strada X"), which can both
legitimately exist in one UAT. Pass 2's confidence is lowered from 0.6 to
0.5 to reflect that residual risk for the cases it still has to guess on.

Pure SQL. No deps. Idempotent: clears existing rows before re-inserting.

We stop at fuzzy_core_name for the same reason osm_match.py/postal_match.py
do: broader fuzzy matching produces enough false positives to poison
downstream analysis — better to surface gaps in tools/renns_sanity.py than
auto-link.
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
    renns_count = con.execute("SELECT COUNT(*) FROM renns_streets").fetchone()[0]
    if renns_count == 0:
        sys.exit("renns_streets is empty. Run tools/renns_ingest.py first.")

    if args.dry_run:
        con.execute("CREATE TEMP TABLE tmp_rmatches AS SELECT * FROM street_renns_matches WHERE 0")
        target = "tmp_rmatches"
    else:
        con.execute("DELETE FROM street_renns_matches")
        target = "street_renns_matches"

    # Pass 1: same street_type (NULL-safe via IS) + core_name_norm, within
    # the same UAT.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, renns_street_id, match_type, confidence)
        SELECT sd.id, r.id, 'exact_type_core', 1.0
          FROM streets_dedup sd
          JOIN renns_streets r
            ON r.uat_siruta = sd.siruta
           AND r.core_name_norm = sd.core_name_norm
           AND r.core_name_norm IS NOT NULL
           AND r.street_type IS sd.street_type
    """)
    exact = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='exact_type_core'").fetchone()[0]

    # Pass 2: core_name_norm fallback (type differs or missing on either
    # side), only for streets not already linked.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, renns_street_id, match_type, confidence)
        SELECT sd.id, r.id, 'fuzzy_core_name', 0.5
          FROM streets_dedup sd
          JOIN renns_streets r
            ON r.uat_siruta = sd.siruta
           AND r.core_name_norm = sd.core_name_norm
           AND r.core_name_norm IS NOT NULL
         WHERE sd.id NOT IN (SELECT street_id FROM {target})
    """)
    fuzzy = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='fuzzy_core_name'").fetchone()[0]

    total_streets = con.execute("SELECT COUNT(*) FROM streets_dedup").fetchone()[0]
    matched_streets = con.execute(f"SELECT COUNT(DISTINCT street_id) FROM {target}").fetchone()[0]
    matched_renns = con.execute(f"SELECT COUNT(DISTINCT renns_street_id) FROM {target}").fetchone()[0]

    print(f"Pass 1 (exact_type_core): {exact}")
    print(f"Pass 2 (fuzzy_core_name): {fuzzy}")
    print(f"Registry coverage:        {matched_streets}/{total_streets} "
          f"({100*matched_streets/total_streets:.1f}%)")
    print(f"RENNS coverage:            {matched_renns}/{renns_count} "
          f"({100*matched_renns/renns_count:.1f}%)")

    if args.dry_run:
        print("[DRY RUN] Not committed.")
    else:
        con.commit()
    con.close()


if __name__ == "__main__":
    main()
