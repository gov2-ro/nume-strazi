"""Materialize the all_street_names view into a fast, indexed cache table.

all_street_names is a live view — a 4-way UNION ALL + GROUP BY +
json_group_array aggregation over electoral_dedup/osm_streets/postal_streets/
renns_streets, recomputed on every query. Measured ~5-8x slower per call than
electoral_dedup, and missing a diacritic-folded name_normalized column (the
identity key used throughout site_queries.py for routing/slugging). Neither
is a problem for the view's current one-shot-per-build callers
(sources_overview(), get_source_coverage_by_judet(), the client-side /surse/
page), but both block ever calling it per-entity in a loop the way
electoral_dedup is used today.

This creates a SIBLING table, all_street_names_cache — it does not replace
or touch the all_street_names view itself, which stays the single source of
truth for "how the union is computed" and keeps working exactly as before.

Can't live inside build_db.py: the view reads from osm_streets/
postal_streets/renns_streets, which are populated by separate tools
(osm_ingest.py, postal_ingest.py, renns_ingest.py) run *after* build_db.py.
Materializing too early would snapshot an electoral-only "union". Run this
after the full 4-source ingest pipeline, and re-run any time one of those
sources is re-ingested — it's idempotent (drops and rebuilds the cache table
each time).

Usage:
  python3 tools/materialize_all_street_names.py
  python3 tools/materialize_all_street_names.py --db data/streets.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streets_lib import normalize_match  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="data/streets.db")
args = ap.parse_args()

con = sqlite3.connect(args.db)
t0 = time.time()

con.execute("DROP TABLE IF EXISTS all_street_names_cache")
con.execute("""
    CREATE TABLE all_street_names_cache AS
    SELECT * FROM all_street_names
""")
con.execute("ALTER TABLE all_street_names_cache ADD COLUMN name_normalized TEXT")

rows = con.execute("SELECT rowid, name FROM all_street_names_cache").fetchall()
con.executemany(
    "UPDATE all_street_names_cache SET name_normalized = ? WHERE rowid = ?",
    [(normalize_match(name), rowid) for rowid, name in rows],
)

con.execute("CREATE INDEX ix_asnc_siruta          ON all_street_names_cache(siruta)")
con.execute("CREATE INDEX ix_asnc_corenorm        ON all_street_names_cache(core_name_norm)")
con.execute("CREATE INDEX ix_asnc_namenorm        ON all_street_names_cache(name_normalized)")
con.execute("CREATE INDEX ix_asnc_siruta_namenorm ON all_street_names_cache(siruta, name_normalized)")
con.commit()

n = con.execute("SELECT COUNT(*) FROM all_street_names_cache").fetchone()[0]
n_null = con.execute(
    "SELECT COUNT(*) FROM all_street_names_cache WHERE name_normalized IS NULL"
).fetchone()[0]
con.close()

elapsed = time.time() - t0
print(f"all_street_names_cache: {n} rows ({n_null} with NULL name_normalized), {elapsed:.1f}s")
