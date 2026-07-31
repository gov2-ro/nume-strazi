"""Populate `street_postal_matches` by joining electoral_dedup ↔ postal_streets.

Pass 1: exact match on (siruta, street_type, core_name_norm) — confidence 1.0.
Pass 2: fallback on (siruta, core_name_norm) only            — confidence 0.5.
Pass 3: fallback on (siruta, core_name_norm_swapped)         — confidence 0.4.
        Postal person-names are frequently "Surname Firstname" (reversed vs.
        the electoral source's "Firstname Surname", e.g. "Alecsandri Vasile"
        vs. the electoral source's "Vasile Alecsandri") — this pass catches
        the 2-token swap. Not needed for OSM, which doesn't have this
        convention. Left type-blind: it's already the lowest-confidence
        fallback, and splitting it further wasn't worth the complexity for
        its (small) match volume.

Each pass only considers electoral-source rows still unmatched after the previous one.

Pass 1 compares (street_type, core_name_norm) rather than the raw
name_normalized string (2026-07-08) — same fix as osm_match.py/renns_match.py:
a type-blind match risks cross-wiring two genuinely distinct streets that
share a core name but differ by type ("Bulevardul X" vs "Strada X"), which
can both legitimately exist in one UAT. Pass 2's confidence is lowered from
0.6 to 0.5 to reflect that residual risk for the cases it still has to guess on.

Pure SQL. No geo deps. Idempotent: clears existing rows before re-inserting.

Below the reordered_core_name threshold we deliberately stop, for the same
reason tools/osm_match.py stops at fuzzy_core_name: broader fuzzy matching
produces enough false positives to poison downstream analysis — better to
surface gaps in tools/postal_sanity.py than auto-link.
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
    postal_count = con.execute("SELECT COUNT(*) FROM postal_streets").fetchone()[0]
    if postal_count == 0:
        sys.exit("postal_streets is empty. Run tools/postal_ingest.py first.")

    if args.dry_run:
        con.execute("CREATE TEMP TABLE tmp_pmatches AS SELECT * FROM street_postal_matches WHERE 0")
        target = "tmp_pmatches"
    else:
        con.execute("DELETE FROM street_postal_matches")
        target = "street_postal_matches"

    # Pass 1: same street_type (NULL-safe via IS) + core_name_norm, within
    # the same UAT.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, postal_street_id, match_type, confidence)
        SELECT sd.id, p.id, 'exact_type_core', 1.0
          FROM electoral_dedup sd
          JOIN postal_streets p
            ON p.uat_siruta = sd.siruta
           AND p.core_name_norm = sd.core_name_norm
           AND p.core_name_norm IS NOT NULL
           AND p.street_type IS sd.street_type
    """)
    exact = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='exact_type_core'").fetchone()[0]

    # Pass 2: core_name_norm fallback (type differs or missing on either
    # side), only for streets not already linked.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, postal_street_id, match_type, confidence)
        SELECT sd.id, p.id, 'fuzzy_core_name', 0.5
          FROM electoral_dedup sd
          JOIN postal_streets p
            ON p.uat_siruta = sd.siruta
           AND p.core_name_norm = sd.core_name_norm
           AND p.core_name_norm IS NOT NULL
         WHERE sd.id NOT IN (SELECT street_id FROM {target})
    """)
    fuzzy = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='fuzzy_core_name'").fetchone()[0]

    # Pass 3: reordered (Surname Firstname → Firstname Surname) core-name match.
    con.execute(f"""
        INSERT OR IGNORE INTO {target} (street_id, postal_street_id, match_type, confidence)
        SELECT sd.id, p.id, 'reordered_core_name', 0.4
          FROM electoral_dedup sd
          JOIN postal_streets p
            ON p.uat_siruta = sd.siruta
           AND p.core_name_norm_swapped = sd.core_name_norm
           AND p.core_name_norm_swapped IS NOT NULL
         WHERE sd.id NOT IN (SELECT street_id FROM {target})
    """)
    reordered = con.execute(f"SELECT COUNT(*) FROM {target} WHERE match_type='reordered_core_name'").fetchone()[0]

    total_streets = con.execute("SELECT COUNT(*) FROM electoral_dedup").fetchone()[0]
    matched_streets = con.execute(f"SELECT COUNT(DISTINCT street_id) FROM {target}").fetchone()[0]
    matched_postal = con.execute(f"SELECT COUNT(DISTINCT postal_street_id) FROM {target}").fetchone()[0]

    print(f"Pass 1 (exact_type_core):     {exact}")
    print(f"Pass 2 (fuzzy_core_name):     {fuzzy}")
    print(f"Pass 3 (reordered_core_name): {reordered}")
    print(f"Electoral coverage:           {matched_streets}/{total_streets} "
          f"({100*matched_streets/total_streets:.1f}%)")
    print(f"Postal coverage:               {matched_postal}/{postal_count} "
          f"({100*matched_postal/postal_count:.1f}%)")

    if args.dry_run:
        print("[DRY RUN] Not committed.")
    else:
        con.commit()
    con.close()


if __name__ == "__main__":
    main()
