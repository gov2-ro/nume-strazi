"""Run all queries from queries.sql, print results.
Skips queries using REGEXP (SQLite needs an extension for that)."""
import sqlite3, re, math, sys, argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--db",  default="data/streets.db")
_ap.add_argument("--sql", default="docs/queries.sql")
_args = _ap.parse_args()
con = sqlite3.connect(_args.db)

# Enable log() for entropy query
con.create_function("log", 1, math.log)
# Stub REGEXP so the communist_aliases query runs
con.create_function("regexp", 2, lambda pat, s: 1 if s and re.search(pat, s) else 0)

with open(_args.sql) as f:
    sql = f.read()

# Split on `-- :name xxx`
blocks = re.split(r"-- :name (\w+)\s*\n", sql)
# blocks[0] = preamble; then alternating name, sql
named = []
for i in range(1, len(blocks), 2):
    name = blocks[i]
    body = blocks[i+1].split("\n\n\n")[0].strip().rstrip(";") + ";"
    # Trim trailing comment-only sections
    body = re.split(r"^-- =+", body, flags=re.MULTILINE)[0].strip().rstrip(";")
    named.append((name, body))

for name, body in named:
    print(f"\n========== {name} ==========")
    try:
        cur = con.execute(body)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        if cols: print("  " + " | ".join(cols))
        for r in rows[:15]:
            print("  " + " | ".join(str(v) if v is not None else "·" for v in r))
        if len(rows) > 15: print(f"  ...({len(rows)-15} more)")
        if not rows: print("  (no rows)")
    except Exception as e:
        print(f"  ERROR: {e}")
