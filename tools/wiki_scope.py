#!/usr/bin/env python3
"""
Classify persons' recognition scope based on Wikidata sitelink counts.
Also fetches Romanian Wikipedia pageviews and article URLs (ro + en).

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
    --db PATH           SQLite DB path (default: data/streets.db)
"""

import sqlite3
import sys
import argparse
import json
import urllib.request
import urllib.parse
import time
from datetime import date, timedelta

WIKIDATA_API  = "https://www.wikidata.org/w/api.php"
PAGEVIEW_API  = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
BATCH_SIZE    = 50
UA            = "RomanianStreetsAnalysis/1.0"


def fetch_sitelinks(qids: list) -> dict:
    """
    Batch fetch sitelink data for multiple QIDs.
    Returns dict of qid -> (sitelink_count, ro_title_or_None, en_title_or_None).
    """
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "format": "json",
        "props": "sitelinks",
    }

    try:
        url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"  ⚠ API error fetching {len(qids)} QIDs: {e}", file=sys.stderr)
        return {}

    results = {}
    for qid, entity in data.get("entities", {}).items():
        sitelinks = entity.get("sitelinks", {})
        ro_title  = sitelinks.get("rowiki", {}).get("title")
        en_title  = sitelinks.get("enwiki", {}).get("title")
        results[qid] = (len(sitelinks), ro_title, en_title)

    return results


def fetch_ro_pageviews(title: str) -> int:
    """
    Fetch average monthly Romanian Wikipedia pageviews over the last 12 months.
    Returns 0 on any error or if no data.
    """
    today  = date.today()
    end    = date(today.year, today.month, 1) - timedelta(days=1)   # last complete month
    start  = date(end.year - 1, end.month, 1)                        # 12 months back
    s_str  = start.strftime("%Y%m01")
    e_str  = end.strftime("%Y%m01")

    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="_")
    url = f"{PAGEVIEW_API}/ro.wikipedia/all-access/user/{encoded}/monthly/{s_str}/{e_str}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        items = data.get("items", [])
        if not items:
            return 0
        return round(sum(i["views"] for i in items) / len(items))
    except Exception:
        return 0


def classify_scope(sitelink_count: int, universal_thresh: int, national_min: int, national_max: int) -> str:
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
    parser.add_argument("--limit",        type=int,   default=None,              help="Only process first N persons with QID")
    parser.add_argument("--dry-run",       action="store_true",                   help="Print updates without writing to DB")
    parser.add_argument("--universal",     type=int,   default=50,                help="Sitelink threshold for universal tier")
    parser.add_argument("--national-min",  type=int,   default=5,                 help="Min sitelinks for national tier")
    parser.add_argument("--national-max",  type=int,   default=49,                help="Max sitelinks for national tier")
    parser.add_argument("--db",            default="data/streets.db",             help="SQLite DB path")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure schema has all wiki columns (safe to run on old DBs)
    for col, typedef in [
        ("wiki_sitelinks", "INTEGER"),
        ("wiki_scope",     "TEXT"),
        ("wiki_ro_url",    "TEXT"),
        ("wiki_en_url",    "TEXT"),
        ("wiki_ro_views",  "INTEGER"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE persons ADD COLUMN {col} {typedef};")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    query = """
        SELECT core_name_norm, full_name, wikidata_qid
        FROM persons
        WHERE wikidata_qid IS NOT NULL AND wiki_scope IS NULL
        ORDER BY full_name
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    persons = cursor.execute(query).fetchall()
    print(f"Processing {len(persons)} persons with QID…")

    updates = []

    for batch_start in range(0, len(persons), BATCH_SIZE):
        batch = persons[batch_start : batch_start + BATCH_SIZE]
        qids  = [p["wikidata_qid"] for p in batch]
        sl    = fetch_sitelinks(qids)

        for person in batch:
            qid                      = person["wikidata_qid"]
            count, ro_title, en_title = sl.get(qid, (0, None, None))
            scope                    = classify_scope(count, args.universal, args.national_min, args.national_max)
            ro_url = (f"https://ro.wikipedia.org/wiki/{urllib.parse.quote(ro_title.replace(' ', '_'), safe='_:/')}"
                      if ro_title else None)
            en_url = (f"https://en.wikipedia.org/wiki/{urllib.parse.quote(en_title.replace(' ', '_'), safe='_:/')}"
                      if en_title else None)

            # Fetch Romanian pageviews (one request per person with a ro article)
            ro_views = 0
            if ro_title:
                ro_views = fetch_ro_pageviews(ro_title)
                time.sleep(1)

            updates.append({
                "core_name_norm": person["core_name_norm"],
                "full_name":      person["full_name"],
                "sitelinks":      count,
                "scope":          scope,
                "ro_url":         ro_url,
                "en_url":         en_url,
                "ro_views":       ro_views,
            })

            print(f"  {person['full_name']}: {count} langs → {scope}"
                  f"  ro_views={ro_views}"
                  + (f"  [{ro_title}]" if ro_title else ""))

        time.sleep(1)

    if not args.dry_run:
        for u in updates:
            cursor.execute(
                """
                UPDATE persons
                SET wiki_sitelinks=?, wiki_scope=?, wiki_ro_url=?, wiki_en_url=?, wiki_ro_views=?
                WHERE core_name_norm=?
                """,
                (u["sitelinks"], u["scope"], u["ro_url"], u["en_url"], u["ro_views"],
                 u["core_name_norm"])
            )
        conn.commit()
        print(f"\n✓ Updated {len(updates)} persons")
    else:
        print(f"\n[dry-run] Would update {len(updates)} persons")

    rows = cursor.execute(
        "SELECT wiki_scope, COUNT(*) FROM persons WHERE wiki_scope IS NOT NULL GROUP BY wiki_scope"
    ).fetchall()
    print("\nScope distribution:")
    for scope, count in rows:
        print(f"  {scope}: {count}")

    conn.close()


if __name__ == "__main__":
    main()
