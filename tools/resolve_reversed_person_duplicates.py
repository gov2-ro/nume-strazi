"""Alias reversed-spelling duplicates of already-curated persons.

For two-token core_name_norm keys that are new to the registry (present in
all_street_names_cache but not streets_dedup) and not yet classified in ANY
curation table, check whether the REVERSED token order already exists as a
classified person in `persons`. If so, alias the new key to that person's
row instead of letting it surface as a spurious "unclassified new key" for
LLM classification to (re-)discover under a different spelling -- same
pattern already used for Alexandru Ioan Cuza's 4 name-form aliases
(core_name_norm values a. i. cuza / cuza voda / al. i. cuza /
alexandru ioan cuza all sharing one identity).

Deliberately conservative: only acts when the reversed form is an EXISTING,
already-curated persons.core_name_norm -- never guesses at reordering. A
first draft of tools/postal_ingest.py's comma-suffix fix tried blindly
reversing every 2-token postal name and was falsified immediately by real
data ("Gala Galaction" is a pen name, not Surname-Firstname; "Petöfi
Șándor" is Hungarian family-name-first order, already correct) -- this tool
exists precisely so that reordering only happens on positive evidence
(a confirmed existing identity), not a heuristic. Scoped to `persons` only,
not nature_terms/name_categories/place_refs -- token-order swapping only
has "Firstname Surname" semantics for personal names.

Usage:
  python3 tools/resolve_reversed_person_duplicates.py --dry-run
  python3 tools/resolve_reversed_person_duplicates.py
"""
from __future__ import annotations

import argparse
import sqlite3

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--db", default="data/streets.db")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

con = sqlite3.connect(args.db)
con.row_factory = sqlite3.Row

reg_keys = {r[0] for r in con.execute(
    "SELECT DISTINCT core_name_norm FROM streets_dedup WHERE core_name_norm IS NOT NULL"
)}
curated_keys: set[str] = set()
for t in ("persons", "nature_terms", "name_categories", "place_refs"):
    curated_keys |= {r[0] for r in con.execute(f"SELECT core_name_norm FROM {t}")}

new_keys = {r[0] for r in con.execute(
    "SELECT DISTINCT core_name_norm FROM all_street_names_cache WHERE core_name_norm IS NOT NULL"
)} - reg_keys

cols = [d[0] for d in con.execute("SELECT * FROM persons LIMIT 0").description]
value_cols = [c for c in cols if c != "core_name_norm"]
person_rows = {r["core_name_norm"]: r for r in con.execute("SELECT * FROM persons")}

candidates = []
for k in sorted(new_keys):
    if k in curated_keys:
        continue
    tokens = k.split()
    if len(tokens) != 2:
        continue
    reversed_k = f"{tokens[1]} {tokens[0]}"
    if reversed_k in person_rows:
        candidates.append((k, reversed_k, person_rows[reversed_k]))

print(f"Found {len(candidates)} new keys resolvable as reversed-spelling aliases of an existing curated person.")
for k, reversed_k, row in candidates:
    print(f"  {k!r:35s} -> alias of {reversed_k!r:35s} ({row['full_name']})")

if args.dry_run:
    print("\n[dry-run] no changes written.")
else:
    placeholders = ", ".join("?" * len(cols))
    for k, reversed_k, row in candidates:
        values = [k] + [row[c] for c in value_cols]
        con.execute(
            f"INSERT INTO persons ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(core_name_norm) DO NOTHING",
            values,
        )
    con.commit()
    print(f"\nInserted {len(candidates)} aliased persons rows.")
