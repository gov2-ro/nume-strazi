"""Export unclassified core_name_norm values for curation.

Outputs data/curation/unclassified.csv with frequency, context, and blank
columns ready for classification. Fill in category/subcategory (or whichever
lookup table columns apply), then import with tools/import_csv.py.

Sources from all_street_names_cache (all 4 sources: registry, OSM, postal,
RENNS), not streets_dedup (registry-only) -- see
tools/materialize_all_street_names.py and docs/BACKLOG.md's "Make
all_street_names the dashboard's main corpus" entry. Registry-only
classification is a strict subset of this.

Usage:
  python3 tools/export_unclassified.py             # top 500, default db
  python3 tools/export_unclassified.py --limit 200
  python3 tools/export_unclassified.py --limit 0   # all unclassified
"""
import sqlite3, csv, argparse, math
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--db",    default="data/streets.db")
ap.add_argument("--out",   default="data/curation/unclassified.csv")
ap.add_argument("--limit", type=int, default=500)
args = ap.parse_args()

con = sqlite3.connect(args.db)
con.create_function("log", 1, math.log)

rows = con.execute("""
WITH classified_keys AS (
  SELECT core_name_norm FROM persons
  UNION
  SELECT core_name_norm FROM nature_terms
  UNION
  SELECT core_name_norm FROM name_categories
  UNION
  SELECT core_name_norm FROM place_refs
),
candidates AS (
  SELECT
    s.core_name_norm,
    COUNT(*)                        AS freq,
    COUNT(DISTINCT s.judet)         AS judete_n,
    COUNT(DISTINCT s.uat)           AS uats_n,
    MIN(s.name)                     AS sample_name,
    GROUP_CONCAT(DISTINCT s.judet)  AS judete_list
  FROM all_street_names_cache s
  WHERE s.core_name_norm IS NOT NULL
    AND s.is_numeric = 0
    AND s.is_date    = 0
    AND s.is_saint   = 0
    AND s.core_name_norm NOT IN (SELECT core_name_norm FROM classified_keys)
  GROUP BY s.core_name_norm
)
SELECT core_name_norm, freq, judete_n, uats_n, sample_name, judete_list
FROM candidates
ORDER BY freq DESC
""" + ("" if args.limit == 0 else f" LIMIT {args.limit}")).fetchall()

out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)

with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "core_name_norm", "freq", "judete_n", "uats_n", "sample_name", "judete_list",
        # --- fill these in for import ---
        "table",           # target: persons | nature_terms | name_categories | place_refs
        # persons columns
        "full_name", "gender", "birth_year", "death_year", "era", "profession",
        "nationality", "wikidata_qid",
        # nature_terms columns
        "term", "nature_type",
        # name_categories columns
        "category", "subcategory",
        # place_refs columns
        "place_name", "place_type", "country",
        # shared
        "notes",
    ])
    w.writerows(rows)

total = con.execute("""
  SELECT COUNT(DISTINCT core_name_norm)
  FROM all_street_names_cache
  WHERE core_name_norm IS NOT NULL AND is_numeric=0 AND is_date=0 AND is_saint=0
""").fetchone()[0]
classified = con.execute("""
  SELECT COUNT(DISTINCT s.core_name_norm)
  FROM all_street_names_cache s
  WHERE s.core_name_norm IS NOT NULL AND s.is_numeric=0 AND s.is_date=0 AND s.is_saint=0
    AND s.core_name_norm IN (
      SELECT core_name_norm FROM persons UNION
      SELECT core_name_norm FROM nature_terms UNION
      SELECT core_name_norm FROM name_categories UNION
      SELECT core_name_norm FROM place_refs
    )
""").fetchone()[0]

print(f"Distinct classifiable core_name_norm: {total:,}")
print(f"Already classified:                   {classified:,}  ({100*classified/total:.1f}%)")
print(f"Unclassified:                         {total-classified:,}  ({100*(total-classified)/total:.1f}%)")
print(f"Exported {len(rows):,} rows → {out}")
