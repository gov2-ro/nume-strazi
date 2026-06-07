"""Run named queries from queries.sql and print results.

Default output is a human-readable table (capped at 15 rows). For pipelines
that need to consume the output, --format json|csv emits machine-readable rows
(uncapped unless --limit is given). --name runs a single query by slug.

  python3 run_queries.py                                  # all, table, 15-row cap
  python3 run_queries.py --name anonymous_uats            # one query
  python3 run_queries.py --name anonymous_uats --format csv > out.csv
  python3 run_queries.py --format json --limit 50 > all.json
"""
import sqlite3, re, math, sys, csv, json, argparse

_ap = argparse.ArgumentParser()
_ap.add_argument("--db",  default="data/streets.db")
_ap.add_argument("--sql", default="docs/queries.sql")
_ap.add_argument("--format", choices=["table", "json", "csv"], default="table",
                 help="output format (default: table)")
_ap.add_argument("--name", default=None,
                 help="run only the query with this -- :name slug")
_ap.add_argument("--limit", type=int, default=None,
                 help="max rows per query (default: 15 for table, all for json/csv)")
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

if _args.name:
    named = [(n, b) for n, b in named if n == _args.name]
    if not named:
        sys.exit(f"No query named '{_args.name}' in {_args.sql}")


def run(body):
    """Return (cols, rows) or raise."""
    cur = con.execute(body)
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, cur.fetchall()


def cap(rows):
    return rows if _args.limit is None else rows[:_args.limit]


if _args.format == "table":
    row_cap = 15 if _args.limit is None else _args.limit
    for name, body in named:
        print(f"\n========== {name} ==========")
        try:
            cols, rows = run(body)
            if cols:
                print("  " + " | ".join(cols))
            for r in rows[:row_cap]:
                print("  " + " | ".join(str(v) if v is not None else "·" for v in r))
            if len(rows) > row_cap:
                print(f"  ...({len(rows) - row_cap} more)")
            if not rows:
                print("  (no rows)")
        except Exception as e:
            print(f"  ERROR: {e}")

elif _args.format == "json":
    out = {}
    for name, body in named:
        try:
            cols, rows = run(body)
            out[name] = [dict(zip(cols, r)) for r in cap(rows)]
        except Exception as e:
            out[name] = {"error": str(e)}
    # A single --name yields just its payload; otherwise keyed by query name.
    payload = out[named[0][0]] if _args.name else out
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

elif _args.format == "csv":
    w = csv.writer(sys.stdout)
    for idx, (name, body) in enumerate(named):
        if not _args.name:
            if idx:
                sys.stdout.write("\n")
            sys.stdout.write(f"# {name}\n")
        try:
            cols, rows = run(body)
            if cols:
                w.writerow(cols)
            for r in cap(rows):
                w.writerow(["" if v is None else v for v in r])
        except Exception as e:
            sys.stdout.write(f"# ERROR: {e}\n")
