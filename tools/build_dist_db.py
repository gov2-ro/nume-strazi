#!/usr/bin/env python3
"""
build_dist_db.py — Build a slim, production-ready streets.db for shipping.

Reads  data/streets.db
Writes dist/streets.db

What it does:
  - Materializes streets_all_sources (the registry+OSM+postal+RENNS
    consolidation view) and all_street_names (the cross-source-deduplicated
    master list, see CODE_SPEC §13.8) into real tables before their source
    tables are dropped.
  - Drops tables not used by the client-side filter UI: osm_streets,
    street_osm_matches, postal_streets, street_postal_matches, renns_streets,
    street_renns_matches, street_aliases.
  - Sets page_size=4096 (predictable HTTP range alignment for sql.js-httpvfs).
  - Sets journal_mode=DELETE so the shipped file is self-contained.
  - VACUUMs to repack and apply the new page size.
  - Prints before/after sizes.

Idempotent — rerun freely after rebuilding data/streets.db.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

SRC = Path("data/streets.db")
DST = Path("dist/streets.db")

def main() -> None:
    if not SRC.exists():
        print(f"error: {SRC} missing. Run build_db.py first.", file=sys.stderr)
        sys.exit(1)

    DST.parent.mkdir(parents=True, exist_ok=True)
    if DST.exists():
        DST.unlink()
    shutil.copy2(SRC, DST)
    src_size = SRC.stat().st_size

    conn = sqlite3.connect(DST)
    try:
        # streets_all_sources and all_street_names are views over
        # streets/streets_dedup/osm_streets/postal_streets/renns_streets
        # (+ their match tables) — materialize both FIRST, before any of
        # those get dropped below, or the view resolution breaks.
        conn.execute("""
            CREATE TABLE streets_all_sources_slim AS
            SELECT * FROM streets_all_sources
        """)
        conn.execute("DROP VIEW streets_all_sources")

        conn.execute("""
            CREATE TABLE all_street_names_slim AS
            SELECT * FROM all_street_names
        """)
        conn.execute("DROP VIEW all_street_names")

        # Materialize streets_dedup view → table with only client-needed columns.
        # Drops id/artera_raw/title/rank (ETL artefacts never read by db-client.js).
        conn.execute("""
            CREATE TABLE streets_dedup_slim AS
            SELECT judet, uat, siruta, street_type, name,
                   name_normalized, core_name, core_name_norm,
                   is_numeric, is_date, is_saint
            FROM streets_dedup
        """)
        conn.execute("DROP VIEW streets_dedup")
        conn.execute("DROP TABLE streets")
        conn.execute("DROP VIEW IF EXISTS streets_classified_pct")
        conn.execute("ALTER TABLE streets_dedup_slim RENAME TO streets_dedup")

        # Indexes lost when the view was dropped; re-add on the real table.
        conn.execute("CREATE INDEX ix_sd_nn  ON streets_dedup(name_normalized)")
        conn.execute("CREATE INDEX ix_sd_cnn ON streets_dedup(core_name_norm)")
        conn.execute("CREATE INDEX ix_sd_j   ON streets_dedup(judet)")

        # Drop tables not used by the client-side filter UI. uat_reference is
        # only a build-time input to all_street_names' judet/uat labeling
        # (already baked into the materialized table above) — not needed
        # standalone in the shipped DB.
        for tbl in ("osm_streets", "street_osm_matches",
                    "postal_streets", "street_postal_matches",
                    "renns_streets", "street_renns_matches", "street_aliases",
                    "uat_reference"):
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")

        conn.execute("ALTER TABLE streets_all_sources_slim RENAME TO streets_all_sources")
        conn.execute("CREATE INDEX ix_sas_siruta   ON streets_all_sources(siruta)")
        conn.execute("CREATE INDEX ix_sas_corenorm ON streets_all_sources(core_name_norm)")

        conn.execute("ALTER TABLE all_street_names_slim RENAME TO all_street_names")
        conn.execute("CREATE INDEX ix_asn_siruta   ON all_street_names(siruta)")
        conn.execute("CREATE INDEX ix_asn_corenorm ON all_street_names(core_name_norm)")

        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA page_size = 4096")
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()

    dst_size = DST.stat().st_size
    pct = (1 - dst_size / src_size) * 100
    print(f"wrote {DST}  ({dst_size/1024/1024:.1f} MB, "
          f"−{pct:.1f}% vs source {src_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
