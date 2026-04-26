"""Upsert a classified CSV into the appropriate lookup table(s).

The CSV is the one produced by export_unclassified.py (or any CSV with
a `core_name_norm` column and a `table` column indicating the target).

Rows with a blank `table` column are skipped. Re-running with the same CSV
is a no-op. Re-running with corrections applies only the changed values.

Usage:
  python3 tools/import_csv.py data/curation/unclassified.csv
  python3 tools/import_csv.py --db data/streets.db data/curation/batch2.csv
"""
import sqlite3, csv, argparse, sys
from pathlib import Path

TABLES = {
    "persons": {
        "key": "core_name_norm",
        "cols": ["core_name_norm", "full_name", "gender", "birth_year", "death_year",
                 "era", "profession", "nationality", "wikidata_qid", "notes"],
        "required": ["full_name"],
    },
    "nature_terms": {
        "key": "core_name_norm",
        "cols": ["core_name_norm", "term", "nature_type", "notes"],
        "required": ["term"],
    },
    "name_categories": {
        "key": "core_name_norm",
        "cols": ["core_name_norm", "category", "subcategory", "notes"],
        "required": ["category"],
    },
    "place_refs": {
        "key": "core_name_norm",
        "cols": ["core_name_norm", "place_name", "place_type", "country", "notes"],
        "required": ["place_name"],
    },
}

ap = argparse.ArgumentParser()
ap.add_argument("csv_path")
ap.add_argument("--db", default="data/streets.db")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

con = sqlite3.connect(args.db)

counts = {t: 0 for t in TABLES}
skipped = 0
errors = []

with open(args.csv_path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for lineno, row in enumerate(reader, start=2):
        table = row.get("table", "").strip()
        if not table:
            skipped += 1
            continue
        if table not in TABLES:
            errors.append(f"line {lineno}: unknown table '{table}'")
            continue

        spec = TABLES[table]
        cnorm = row.get("core_name_norm", "").strip()
        if not cnorm:
            errors.append(f"line {lineno}: blank core_name_norm")
            continue

        for req in spec["required"]:
            if not row.get(req, "").strip():
                errors.append(f"line {lineno}: '{req}' required for table '{table}' but blank")
                continue

        vals = {}
        for col in spec["cols"]:
            v = row.get(col, "").strip() or None
            if v is not None and col in ("birth_year", "death_year"):
                try:
                    v = int(v)
                except ValueError:
                    v = None
            vals[col] = v
        vals["core_name_norm"] = cnorm

        col_list  = spec["cols"]
        placeholders = ", ".join("?" * len(col_list))
        update_set = ", ".join(
            f"{c} = excluded.{c}" for c in col_list if c != spec["key"]
        )
        sql = (
            f"INSERT INTO {table} ({', '.join(col_list)}) VALUES ({placeholders})\n"
            f"ON CONFLICT({spec['key']}) DO UPDATE SET {update_set}"
        )
        params = [vals[c] for c in col_list]

        if not args.dry_run:
            con.execute(sql, params)
        counts[table] += 1

if errors:
    print(f"ERRORS ({len(errors)}):")
    for e in errors[:20]:
        print(f"  {e}")
    if not args.dry_run:
        print("Rolling back.")
        sys.exit(1)

if not args.dry_run:
    con.commit()

label = "[DRY RUN] " if args.dry_run else ""
print(f"{label}Skipped (no table): {skipped}")
for t, n in counts.items():
    if n:
        print(f"{label}Upserted → {t}: {n}")
if not any(counts.values()):
    print("Nothing to import (all rows had blank 'table' column).")
