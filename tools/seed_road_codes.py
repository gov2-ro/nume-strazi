#!/usr/bin/env python3
"""Deterministically classify Romanian road codes into name_categories.

DN/DJ/DC/DE codes ("DN6D", "DJ243A", "DC27", "DC117-Bica") are pure pattern,
not judgement: the prefix names the road class outright. They were sitting in
tools/llm_classify.py's candidate pool and getting classified correctly by the
model — 300 keys' worth of API calls for what a regex settles for free.

Codes carry an optional locality or street suffix after a dash
("DC117-Bica", "DC57 - Str. Iuliu Maniu"); the prefix still determines the
class, so those are seeded too. The suffix is preserved in `notes` rather than
dropped, since it's the only place the referenced locality survives.

Idempotent per CLAUDE.md rule #6: ON CONFLICT DO UPDATE, so re-running with the
same DB is a no-op.

Usage:
    python3 tools/seed_road_codes.py
    python3 tools/seed_road_codes.py --dry-run
"""
import argparse, re, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Prefix → subcategory. Anchored, and the prefix must be followed by digits, so
# a real name that merely starts with these two letters ("Dnestru", "Dciului",
# and every ordinary Romanian "de ...") cannot match.
#
# "de" is drum de exploatare — an agricultural/cadastral access road — NOT a
# European route. Romania's European routes are E60/E85, prefix "E". The DE
# keys in this dataset ("DE 1845/4", "DE 657/1/31") carry cadastral parcel
# references, which is what gives them away.
ROAD_CLASSES = {
    "dn": "national_road",      # drum național
    "dj": "county_road",        # drum județean
    "dc": "communal_road",      # drum comunal
    "de": "exploitation_road",  # drum de exploatare (agricultural/cadastral)
}
# Optional trailing segment after a dash (locality: "DC117-Bica") or a slash
# (cadastral parcel: "DE 1845/4").
ROAD_CODE_RE = re.compile(
    r"^(dn|dj|dc|de)\s*(\d+[a-z]?)\s*(?:[-–/]\s*(.+))?$", re.IGNORECASE
)

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="data/streets.db")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

con = sqlite3.connect(args.db)

keys = [r[0] for r in con.execute(
    "SELECT DISTINCT core_name_norm FROM all_street_names_cache "
    "WHERE core_name_norm IS NOT NULL"
)]

rows = []
for key in keys:
    m = ROAD_CODE_RE.match(key)
    if not m:
        continue
    prefix, number, suffix = m.group(1).lower(), m.group(2), m.group(3)
    note = f"road code {prefix.upper()}{number.upper()}"
    if suffix:
        note += f"; segment: {suffix.strip()}"
    if prefix == "de":
        note += " (drum de exploatare)"
    rows.append((key, "infrastructure", ROAD_CLASSES[prefix], note))

print(f"Matched {len(rows)} road-code keys of {len(keys)} distinct keys.")
by_class = {}
for _, _, sub, _ in rows:
    by_class[sub] = by_class.get(sub, 0) + 1
for sub, n in sorted(by_class.items(), key=lambda kv: -kv[1]):
    print(f"  {sub:<16} {n}")

if args.dry_run:
    for r in rows[:20]:
        print(f"  [dry-run] {r[0]:<28} {r[2]:<16} {r[3]}")
    sys.exit(0)

con.executemany(
    """INSERT INTO name_categories (core_name_norm, category, subcategory, notes)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(core_name_norm) DO UPDATE SET
         category    = excluded.category,
         subcategory = excluded.subcategory,
         notes       = excluded.notes""",
    rows,
)
con.commit()
print(f"Upserted {len(rows)} rows into name_categories.")
