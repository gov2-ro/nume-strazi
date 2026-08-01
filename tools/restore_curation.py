#!/usr/bin/env python3
"""
Run the full curation-restore sequence after a build_db.py rebuild wipes
persons/nature_terms/name_categories/place_refs, Wikidata QIDs, wiki_scope,
birthplaces, and biostats (see CLAUDE.md rule #12). Fails loudly instead of
silently shipping degraded data — asserts classification_coverage_summary's
pct_streets_classified lands within tolerance of a known-good floor.

Also pre-flight-checks the OSM/postal/RENNS source tables against SOURCE_FLOORS.
It does not restore them (that's a per-source re-ingest), but a rebuild wipes
them too, and until 2026-08-01 nothing here noticed: renns_streets sat empty for
two weeks while every assertion still passed.

Always operates on data/streets.db. tools/seed_top500.py and
tools/seed_batch2.py shell out to import_csv.py without a --db flag, so they
can only ever write to that fixed path — there's no way to honor a
--db override across all nine steps without silently splitting writes across
two different databases, so this script doesn't offer one.

Usage:
    python3 tools/restore_curation.py
    python3 tools/restore_curation.py --min-pct 60
    python3 tools/restore_curation.py --wiki-scope   # also fetch pending wiki_scope rows live (slow)
    python3 tools/restore_curation.py --allow-empty renns_streets  # while renns.ancpi.ro is down

Steps (in order, stop on first failure):
    0. SOURCE_FLOORS pre-flight over the source tables (see --allow-empty)
    1. seed_lookups.py
    2. tools/seed_top500.py
    3. tools/seed_batch2.py
    4-6. tools/import_csv.py on the 3 one-off LLM batch CSVs (not regenerated
         by any seed script — see CLAUDE.md Common Commands)
    7. tools/wikidata_persons.py --replay-csv --force
    8. tools/wiki_birthplace.py --replay-csv --force
    9. tools/wiki_biostats.py --replay-csv --force
Then: run_queries.py --name classification_coverage_summary, asserting
pct_streets_classified >= known-good floor minus tolerance.

wiki_scope.py has no --replay-csv mode (always a live, rate-limited Wikidata
call) so it's reported on but not run by default; pass --wiki-scope to fetch
pending rows live, with the 429→'unknown' remediation from CLAUDE.md applied
automatically (reset + one bounded retry pass).

NOTE on step 7: the replay CSV is the durable record of curated QIDs — whatever
it contains wins after a rebuild, --force and all. The 2026-07-31 audit found
84 of 297 QIDs pointing at communes/taxa/disambiguation pages rather than people
(CLAUDE.md rule #16), and 31 of those were sitting in this CSV. If you correct
QIDs in the DB, run `tools/audit_person_qids.py --sync-replay-csv` or the next
restore silently replays the bad ones.
"""
import argparse, json, subprocess, sys, sqlite3, time
from pathlib import Path

DB = "data/streets.db"

# Last verified live baseline (2026-07-14): pct_streets_classified = 64.0.
# Bump this as curation coverage genuinely grows; a real regression should
# trip TOLERANCE_PCT well before this needs manual widening.
KNOWN_GOOD_PCT_STREETS_CLASSIFIED = 64.0
TOLERANCE_PCT = 5.0

# Source tables this script does NOT restore, but whose absence silently degrades
# everything downstream. `renns_streets` was emptied by a build_db.py rebuild on
# 2026-07-15 and went unnoticed for over two weeks: the union quietly dropped from
# ~224k to 166k rows and still passed every check here, because the assertions only
# ever looked at curation coverage. Floors are ~10% under the verified 2026-08-01
# counts (osm 108,489 / postal 23,724 / renns 116,016 pre-loss / union 163,404
# with RENNS missing), loose enough to absorb a genuine re-ingest, tight enough
# that a wiped or half-crawled source trips them.
SOURCE_FLOORS = {
    "osm_streets":            95_000,
    "postal_streets":         22_000,
    "renns_streets":         100_000,
    "all_street_names_cache": 150_000,
}

REQUIRED_CSVS = [
    "data/curation/llm_batch.csv",
    "data/curation/llm_batch2.csv",
    "data/curation/llm_gemini-3.1-flash-lite.csv",
    "data/curation/wikidata_qids.csv",
    "data/curation/wikidata_birthplaces.csv",
    "data/curation/wikidata_biostats.csv",
]


def run_step(n, total, label, cmd):
    print(f"[{n}/{total}] {label}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"    {line}")
    if result.returncode != 0:
        print(f"[{n}/{total}] FAILED ({label})", file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)


def table_count(table):
    con = sqlite3.connect(DB)
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    con.close()
    return n


def fetch_wiki_scope(py, batch_size=40, max_iterations=30, sleep_between=3):
    con = sqlite3.connect(DB)

    def pending():
        return con.execute(
            "SELECT COUNT(*) FROM persons WHERE wikidata_qid IS NOT NULL AND wiki_scope IS NULL"
        ).fetchone()[0]

    def unknown():
        return con.execute("SELECT COUNT(*) FROM persons WHERE wiki_scope = 'unknown'").fetchone()[0]

    print(f"\n--wiki-scope: fetching live sitelink data for {pending()} pending persons...")
    for i in range(max_iterations):
        if pending() == 0:
            break
        print(f"  batch {i + 1}: {pending()} pending...")
        subprocess.run([py, "tools/wiki_scope.py", "--limit", str(batch_size), "--db", DB], check=False)
        time.sleep(sleep_between)
    else:
        print(f"  hit max_iterations ({max_iterations}) with {pending()} still pending — stopping.")

    # Documented remediation (CLAUDE.md): batches that silently hit a Wikidata
    # 429 get recorded as wiki_scope='unknown' with 0 sitelinks instead of
    # retried. A real zero-sitelink Wikidata item is rare (3/297 confirmed
    # 2026-07-14) — reset once and retry rather than trusting every 'unknown'.
    before_unknown = unknown()
    if before_unknown:
        print(f"  resetting {before_unknown} 'unknown' rows for one retry pass (429 remediation)...")
        con.execute("UPDATE persons SET wiki_scope=NULL, wiki_sitelinks=NULL WHERE wiki_scope='unknown'")
        con.commit()
        for i in range(max_iterations):
            if pending() == 0:
                break
            subprocess.run([py, "tools/wiki_scope.py", "--limit", str(batch_size), "--db", DB], check=False)
            time.sleep(sleep_between)

    print(f"  done: {pending()} still pending, {unknown()} recorded as 'unknown' (genuine no-article items).")
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-pct", type=float, default=KNOWN_GOOD_PCT_STREETS_CLASSIFIED - TOLERANCE_PCT,
                     help="Fail if pct_streets_classified drops below this (default: known-good minus tolerance)")
    ap.add_argument("--wiki-scope", action="store_true",
                     help="Also run wiki_scope.py live batches for any pending persons (slow, network-bound)")
    ap.add_argument("--allow-empty", action="append", default=[], metavar="TABLE",
                     help="Skip the row-count floor for this source table (repeatable). "
                          "Use when a source genuinely cannot be re-ingested, e.g. "
                          "--allow-empty renns_streets while renns.ancpi.ro is offline.")
    args = ap.parse_args()

    py = sys.executable

    missing = [p for p in REQUIRED_CSVS if not Path(p).exists()]
    if missing:
        print("Missing required curation CSV(s) — cannot restore:", file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        sys.exit(1)

    # Pre-flight, not post-flight: none of the restore steps below touch the
    # source tables, so there is no reason to spend several minutes replaying
    # curation before reporting that a source was wiped.
    unknown_exempt = [t for t in args.allow_empty if t not in SOURCE_FLOORS]
    if unknown_exempt:
        print(f"--allow-empty names no such source table: {', '.join(unknown_exempt)}",
              file=sys.stderr)
        print(f"  known: {', '.join(SOURCE_FLOORS)}", file=sys.stderr)
        sys.exit(1)

    print("Source tables:")
    starved = []
    for table, floor in SOURCE_FLOORS.items():
        n = table_count(table)
        if table in args.allow_empty:
            print(f"  {table:<24} {n:>9,}  (floor {floor:,} waived via --allow-empty)")
        elif n < floor:
            print(f"  {table:<24} {n:>9,}  BELOW FLOOR {floor:,}")
            starved.append((table, n, floor))
        else:
            print(f"  {table:<24} {n:>9,}  (floor {floor:,})")
    if starved:
        sys.stdout.flush()   # keep the table listing above the failure in piped logs
        print("\nFAILED: source table(s) below their known-good floor — a rebuild or a "
              "failed re-ingest has dropped data this script does not restore:", file=sys.stderr)
        for table, n, floor in starved:
            print(f"  {table}: {n:,} < {floor:,}", file=sys.stderr)
        print("\nRe-ingest the affected source(s) before restoring curation — see CLAUDE.md's\n"
              "Common Commands for the per-source ingest/match/sanity sequence. If a source is\n"
              "legitimately unavailable, rerun with --allow-empty <table> to record the exemption.",
              file=sys.stderr)
        sys.exit(1)

    steps = [
        ("seed_lookups.py", [py, "seed_lookups.py", "--db", DB]),
        ("tools/seed_top500.py", [py, "tools/seed_top500.py"]),
        ("tools/seed_batch2.py", [py, "tools/seed_batch2.py"]),
        ("import_csv.py llm_batch.csv",
         [py, "tools/import_csv.py", "data/curation/llm_batch.csv", "--db", DB]),
        ("import_csv.py llm_batch2.csv",
         [py, "tools/import_csv.py", "data/curation/llm_batch2.csv", "--db", DB]),
        ("import_csv.py llm_gemini-3.1-flash-lite.csv",
         [py, "tools/import_csv.py", "data/curation/llm_gemini-3.1-flash-lite.csv", "--db", DB]),
        ("wikidata_persons.py --replay-csv --force",
         [py, "tools/wikidata_persons.py", "--replay-csv", "--force", "--db", DB]),
        ("wiki_birthplace.py --replay-csv --force",
         [py, "tools/wiki_birthplace.py", "--replay-csv", "--force", "--db", DB]),
        ("wiki_biostats.py --replay-csv --force",
         [py, "tools/wiki_biostats.py", "--replay-csv", "--force", "--db", DB]),
    ]

    total = len(steps)
    for i, (label, cmd) in enumerate(steps, start=1):
        run_step(i, total, label, cmd)

    con = sqlite3.connect(DB)
    pending = con.execute(
        "SELECT COUNT(*) FROM persons WHERE wikidata_qid IS NOT NULL AND wiki_scope IS NULL"
    ).fetchone()[0]
    unknown = con.execute("SELECT COUNT(*) FROM persons WHERE wiki_scope = 'unknown'").fetchone()[0]
    con.close()

    print(f"\nwiki_scope: {pending} persons pending, {unknown} recorded as 'unknown'.")
    if pending and not args.wiki_scope:
        print("  (not fetched — rerun with --wiki-scope to fill these in live; rate-limited, slow)")
    if args.wiki_scope and pending:
        fetch_wiki_scope(py)

    result = subprocess.run(
        [py, "run_queries.py", "--db", DB, "--format", "json", "--name", "classification_coverage_summary"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("FAILED to run classification_coverage_summary:", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    row = json.loads(result.stdout)[0]
    pct = row["pct_streets_classified"]

    print(f"\nclassification_coverage_summary: {row['classified_streets']:,} / {row['total_streets']:,} "
          f"streets classified ({pct}%)")
    print(f"  persons={table_count('persons')} nature_terms={table_count('nature_terms')} "
          f"name_categories={table_count('name_categories')} place_refs={table_count('place_refs')}")

    if pct < args.min_pct:
        print(f"\nFAILED: pct_streets_classified {pct}% is below the floor of {args.min_pct}% "
              f"(known-good {KNOWN_GOOD_PCT_STREETS_CLASSIFIED}% - tolerance {TOLERANCE_PCT}pp). "
              f"Curation restore looks incomplete.", file=sys.stderr)
        sys.exit(1)

    print(f"\nOK: restore complete, coverage {pct}% >= floor {args.min_pct}%.")


if __name__ == "__main__":
    main()
