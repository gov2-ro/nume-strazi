#!/usr/bin/env python3
"""
Classify persons' recognition scope based on Wikidata sitelink counts.

Fetches Wikipedia language edition counts for each person with a wikidata_qid,
classifies as universal/national/local/unknown, and updates the persons table.

Scope tiers (tunable):
  universal: ≥50 editions (Eminescu, Trajan, Curie)
  national:  5–49 editions (most Romanian historical figures)
  local:     1–4 editions (obscure outside RO)
  unknown:   no article found

Usage:
    python3 tools/wiki_scope.py [--limit N] [--dry-run] [--universal N] [--national-min N] [--national-max N]

Options:
    --limit N           Only process first N persons with a QID (default: all)
    --dry-run           Print updates without writing to DB
    --universal N       Sitelink threshold for universal tier (default: 50)
    --national-min N    Min sitelinks for national tier (default: 5)
    --national-max N    Max sitelinks for national tier (default: 49)
"""

import sqlite3
import sys
import argparse
import json
import urllib.request
import urllib.parse
import time

DB_PATH = "data/streets.db"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
BATCH_SIZE = 50  # Wikidata API can handle up to 50 IDs per request

def fetch_sitelinks(qids: list) -> dict:
    """
    Batch fetch sitelink counts for multiple QIDs.
    Returns dict of qid -> sitelink_count.
    """
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "format": "json",
        "props": "sitelinks",
    }

    try:
        url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "RomanianStreetsAnalysis/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"  ⚠ API error fetching {len(qids)} QIDs: {e}", file=sys.stderr)
        return {}

    results = {}
    for qid, entity in data.get("entities", {}).items():
        sitelinks = entity.get("sitelinks", {})
        results[qid] = len(sitelinks)

    return results

def classify_scope(sitelink_count: int, universal_thresh: int, national_min: int, national_max: int) -> str:
    """Classify scope tier based on sitelink count."""
    if sitelink_count == 0:
        return "unknown"
    elif sitelink_count >= universal_thresh:
        return "universal"
    elif national_min <= sitelink_count <= national_max:
        return "national"
    else:
        return "local"

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Only process first N persons with QID")
    parser.add_argument("--dry-run", action="store_true", help="Print updates without writing to DB")
    parser.add_argument("--universal", type=int, default=50, help="Sitelink threshold for universal tier")
    parser.add_argument("--national-min", type=int, default=5, help="Min sitelinks for national tier")
    parser.add_argument("--national-max", type=int, default=49, help="Max sitelinks for national tier")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure schema has wiki columns
    try:
        cursor.execute("ALTER TABLE persons ADD COLUMN wiki_sitelinks INTEGER;")
        cursor.execute("ALTER TABLE persons ADD COLUMN wiki_scope TEXT;")
        conn.commit()
    except sqlite3.OperationalError:
        # Columns already exist
        pass

    # Fetch persons with a QID but no scope yet
    query = """
        SELECT core_name_norm, full_name, wikidata_qid
        FROM persons
        WHERE wikidata_qid IS NOT NULL AND wiki_scope IS NULL
        ORDER BY full_name
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    cursor.execute(query)
    persons = cursor.fetchall()

    print(f"Processing {len(persons)} persons with QID...")

    updates = []

    # Batch fetch sitelinks
    for batch_start in range(0, len(persons), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(persons))
        batch = persons[batch_start:batch_end]

        qids = [p["wikidata_qid"] for p in batch]
        sitelinks = fetch_sitelinks(qids)

        for person in batch:
            qid = person["wikidata_qid"]
            sitelink_count = sitelinks.get(qid, 0)
            scope = classify_scope(sitelink_count, args.universal, args.national_min, args.national_max)

            updates.append({
                "core_name_norm": person["core_name_norm"],
                "full_name": person["full_name"],
                "qid": qid,
                "sitelinks": sitelink_count,
                "scope": scope,
            })

            print(f"  {person['full_name']}: {sitelink_count} editions → {scope}")

        # Rate limit
        time.sleep(1)

    # Apply updates
    if not args.dry_run:
        for update in updates:
            cursor.execute(
                """
                UPDATE persons
                SET wiki_sitelinks = ?, wiki_scope = ?
                WHERE core_name_norm = ?
                """,
                (update["sitelinks"], update["scope"], update["core_name_norm"])
            )
        conn.commit()
        print(f"\n✓ Updated {len(updates)} persons in database")
    else:
        print(f"\n[dry-run] Would update {len(updates)} persons")

    # Summary stats
    cursor.execute("SELECT wiki_scope, COUNT(*) FROM persons WHERE wiki_scope IS NOT NULL GROUP BY wiki_scope")
    stats = cursor.fetchall()

    print(f"\nScope distribution:")
    for scope, count in stats:
        print(f"  {scope}: {count}")

    conn.close()

if __name__ == "__main__":
    main()
