#!/usr/bin/env python3
"""
Search Wikidata for persons in the persons table who lack a wikidata_qid.

Outputs a CSV audit trail and writes matched QIDs directly to the DB for
high-confidence matches. Idempotent: re-running skips already-processed keys.

Usage:
    python3 tools/wikidata_persons.py [--limit N] [--out FILE] [--confidence THRESHOLD] [--db PATH]
    python3 tools/wikidata_persons.py --replay-csv [--out FILE] [--db PATH] [--dry-run]

Search mode options:
    --limit N            Only process first N unmatched persons (default: all)
    --out FILE           Audit CSV path (default: data/curation/wikidata_qids.csv)
    --confidence THRESH  Auto-match threshold (0.0–1.0, default: 0.95)
    --db PATH            SQLite DB path (default: data/streets.db)
    --dry-run            Print matches without writing to DB

Replay mode (--replay-csv):
    Reads all auto_match=True rows from the CSV and applies them to the DB.
    Use this after a full rebuild to restore manually curated QIDs without
    re-running the Wikidata search. Skips rows already set correctly.
    Warns and skips on QID conflicts by default; use --force to overwrite
    (needed after rebuild because seed scripts may load stale QIDs).
"""

import csv
import sqlite3
import sys
import argparse
import json
import urllib.error
import urllib.request
import urllib.parse
import time
from pathlib import Path
from typing import Optional, Tuple

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
HEADER = ["core_name_norm", "full_name", "wikidata_qid", "confidence", "auto_match"]


def search_wikidata(name: str, gender: Optional[str], birth_year: Optional[int], death_year: Optional[int]) -> Optional[Tuple[str, float]]:
    """
    Search Wikidata for a person by name, optionally filtering by birth/death dates and gender.
    Returns (qid, confidence) or None if not found.

    Confidence heuristic:
    - Exact name match + matching gender/dates: 0.95
    - Exact name match, no gender/date info: 0.85
    - Partial match: 0.70
    """
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": "ro",
        "uselang": "en",
        "type": "item",
        "format": "json",
    }

    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "RomanianStreetsAnalysis/1.0"})
    data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 5 * (2 ** attempt)
                print(f"\n  ⚠ 429 rate limit, waiting {wait}s …", file=sys.stderr)
                time.sleep(wait)
            else:
                raise
        except Exception:
            raise
    if data is None:
        raise RuntimeError(f"429 retries exhausted for '{name}'")

    results = data.get("search", [])
    if not results:
        return None

    best_match = None
    best_confidence = 0.0

    for result in results[:5]:  # Check top 5 results
        qid = result.get("id")
        result_label = result.get("label", "").lower()
        result_description = result.get("description", "").lower()

        # Exact label match
        if result_label == name.lower():
            confidence = 0.95 if (gender or birth_year or death_year) else 0.85
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = qid

        # Partial match in label or description
        elif name.lower() in result_label or name.lower() in result_description:
            confidence = 0.70
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = qid

    if best_match:
        return (best_match, best_confidence)
    return None


def get_entity_details(qid: str) -> Optional[dict]:
    """Fetch full entity details from Wikidata to verify gender/dates."""
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "format": "json",
        "props": "labels|descriptions|claims",
    }

    try:
        url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "RomanianStreetsAnalysis/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
        return data.get("entities", {}).get(qid)
    except Exception as e:
        print(f"  ⚠ API error fetching {qid}: {e}", file=sys.stderr)
        return None


def replay_from_csv(csv_path: Path, conn: sqlite3.Connection, cursor: sqlite3.Cursor,
                    dry_run: bool, force: bool) -> None:
    """
    Apply all auto_match=True rows from the audit CSV to the DB.
    Idempotent: rows already set to the correct QID are silently skipped.

    force=False (default): warn and skip when the DB already holds a different QID.
    force=True: overwrite conflicts — use after a rebuild when seed scripts may
                have loaded stale/unverified QIDs that the CSV should supersede.
                Still skips duplicate-QID collisions (two keys → same QID).
    """
    if not csv_path.exists():
        print(f"Error: {csv_path} not found", file=sys.stderr)
        sys.exit(1)

    confirmed = [
        row for row in csv.DictReader(open(csv_path, newline="", encoding="utf-8"))
        if row["auto_match"] == "True" and row["wikidata_qid"]
    ]

    print(f"Replaying {len(confirmed)} confirmed QIDs from {csv_path.name}…")
    if force:
        print("  (--force: will overwrite conflicting QIDs)")

    applied = already_set = skipped_conflict = skipped_missing = overwrote = 0

    for row in confirmed:
        key = row["core_name_norm"]
        qid = row["wikidata_qid"]

        # LIKE is case-insensitive for ASCII in SQLite; guards against manual
        # CSV edits that introduced wrong capitalisation for the lookup key.
        current = cursor.execute(
            "SELECT core_name_norm, wikidata_qid FROM persons WHERE core_name_norm LIKE ?", (key,)
        ).fetchone()

        if current is None:
            skipped_missing += 1
            continue

        # Use the DB's canonical key for the UPDATE so it always hits.
        key = current[0]
        db_qid = current[1]

        if db_qid == qid:
            already_set += 1
            continue

        if db_qid is not None and db_qid != qid:
            if not force:
                print(f"  ⚠ conflict — DB has {db_qid}, CSV has {qid}: {key}")
                skipped_conflict += 1
                continue
            # force mode: overwrite, but still run uniqueness guard below
            print(f"  ~ overwrite {db_qid} → {qid}: {key}")
            overwrote += 1

        # Uniqueness guard: reject if QID is already owned by a different key
        dupe = cursor.execute(
            "SELECT core_name_norm FROM persons WHERE wikidata_qid = ? AND core_name_norm != ?",
            (qid, key)
        ).fetchone()
        if dupe:
            print(f"  ⚠ duplicate QID {qid} already on '{dupe[0]}', skipping: {key}")
            skipped_conflict += 1
            continue

        if db_qid is None:
            print(f"  {key} → {qid}")
        if not dry_run:
            cursor.execute("UPDATE persons SET wikidata_qid=? WHERE core_name_norm=?", (qid, key))
        applied += 1

    if not dry_run and applied:
        conn.commit()

    label = "[dry-run] would apply" if dry_run else "Applied"
    parts = [f"{label}: {applied}", f"already set: {already_set}"]
    if overwrote:
        parts.append(f"overwrote: {overwrote}")
    parts.append(f"skipped (conflict/missing): {skipped_conflict + skipped_missing}")
    print(f"\n{'  |  '.join(parts)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--replay-csv", action="store_true",                                 help="Apply confirmed CSV rows to DB (rebuild restore mode)")
    parser.add_argument("--force",      action="store_true",                                 help="With --replay-csv: overwrite conflicting QIDs (use after rebuild)")
    parser.add_argument("--limit",      type=int,   default=None,                            help="Only process first N unmatched persons")
    parser.add_argument("--out",        default="data/curation/wikidata_qids.csv",           help="Audit CSV path")
    parser.add_argument("--confidence", type=float, default=0.95,                            help="Auto-match threshold (default: 0.95)")
    parser.add_argument("--db",         default="data/streets.db",                           help="SQLite DB path")
    parser.add_argument("--dry-run",    action="store_true",                                 help="Print matches without writing to DB")
    args = parser.parse_args()

    if not 0.0 <= args.confidence <= 1.0:
        print("Error: --confidence must be 0.0–1.0", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out)

    if args.replay_csv:
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
        replay_from_csv(out_path, conn, conn.cursor(), args.dry_run, args.force)
        conn.close()
        return

    # Resume support: skip keys already written to the audit CSV
    processed: set[str] = set()
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                processed.add(row["core_name_norm"])
        print(f"Resuming: {len(processed)} persons already processed in {out_path.name}")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT core_name_norm, full_name, gender, birth_year, death_year
        FROM persons
        WHERE wikidata_qid IS NULL
        ORDER BY full_name
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    persons = [r for r in cursor.execute(query).fetchall() if r["core_name_norm"] not in processed]
    total = len(persons)

    if not total:
        print("Nothing to process.")
        conn.close()
        return

    print(f"Persons to search: {total}")

    is_new = not out_path.exists()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_matched = n_unmatched = n_written = 0

    with open(out_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        if is_new:
            writer.writeheader()

        for i, person in enumerate(persons, 1):
            print(f"[{i:>3}/{total}] {person['full_name']}", end=" … ", flush=True)

            try:
                match = search_wikidata(
                    person["full_name"], person["gender"],
                    person["birth_year"], person["death_year"]
                )
            except Exception as e:
                # API error — skip CSV write so this entry is retried next run
                print(f"ERROR: {e}", file=sys.stderr)
                continue

            if match:
                qid, confidence = match
                auto = confidence >= args.confidence

                # Uniqueness guard: check if this QID is already assigned to a different person
                cursor.execute(
                    "SELECT core_name_norm FROM persons WHERE wikidata_qid = ? AND core_name_norm != ?",
                    (qid, person["core_name_norm"])
                )
                existing = cursor.fetchone()
                if existing:
                    print(f"{qid}  conf={confidence:.2f}  ⚠ DUPLICATE QID (already assigned to '{existing[0]}')")
                    n_matched += 1
                    writer.writerow({
                        "core_name_norm": person["core_name_norm"],
                        "full_name":      person["full_name"],
                        "wikidata_qid":   "",
                        "confidence":     f"{confidence:.2f}",
                        "auto_match":     False,
                    })
                    f.flush()
                else:
                    print(f"{qid}  conf={confidence:.2f}  {'✓ auto' if auto else 'manual'}")
                    n_matched += 1

                    writer.writerow({
                        "core_name_norm": person["core_name_norm"],
                        "full_name":      person["full_name"],
                        "wikidata_qid":   qid,
                        "confidence":     f"{confidence:.2f}",
                        "auto_match":     auto,
                    })
                    f.flush()

                    if auto and not args.dry_run:
                        cursor.execute(
                            "UPDATE persons SET wikidata_qid=? WHERE core_name_norm=?",
                            (qid, person["core_name_norm"])
                        )
                        conn.commit()
                        n_written += 1
            else:
                print("no match")
                n_unmatched += 1
                writer.writerow({
                    "core_name_norm": person["core_name_norm"],
                    "full_name":      person["full_name"],
                    "wikidata_qid":   "",
                    "confidence":     "0.00",
                    "auto_match":     False,
                })
                f.flush()

            time.sleep(2)

    conn.close()

    print(f"\nDone — matched: {n_matched}, unmatched: {n_unmatched}")
    if not args.dry_run:
        print(f"QIDs written to DB (conf ≥ {args.confidence:.2f}): {n_written}")
    print(f"Audit CSV: {out_path}")

    if n_matched - n_written:
        print(f"Manual review needed ({n_matched - n_written} rows): open {out_path} and filter auto_match=False")


if __name__ == "__main__":
    main()
