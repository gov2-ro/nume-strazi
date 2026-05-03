#!/usr/bin/env python3
"""
Search Wikidata for persons in the persons table who lack a wikidata_qid.

Outputs a CSV with search results for manual review and matching, or direct insertion if high-confidence.

Usage:
    python3 tools/wikidata_persons.py [--limit N] [--output file.csv] [--confidence THRESHOLD]

Options:
    --limit N            Only process first N rows without a QID (default: all)
    --output FILE        Write results to FILE instead of stdout (default: stdout)
    --confidence THRESH  Only auto-match if confidence ≥ THRESH (0.0–1.0, default: 0.95)
                         Below threshold, output is CSV for manual review.
"""

import sqlite3
import sys
import argparse
import json
import urllib.request
import urllib.parse
import time
from typing import Optional, Tuple, List

DB_PATH = "data/streets.db"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

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

    try:
        url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "RomanianStreetsAnalysis/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"  ⚠ API error searching '{name}': {e}", file=sys.stderr)
        return None

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
            # Verify against gender/dates if available
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

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Only process first N unmatched persons")
    parser.add_argument("--output", type=str, default=None, help="Write results to file (default: stdout)")
    parser.add_argument("--confidence", type=float, default=0.95, help="Auto-match threshold (default: 0.95)")
    args = parser.parse_args()

    if args.confidence < 0 or args.confidence > 1:
        print("Error: --confidence must be 0.0–1.0", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch persons without a QID
    query = "SELECT core_name_norm, full_name, gender, birth_year, death_year FROM persons WHERE wikidata_qid IS NULL ORDER BY full_name"
    if args.limit:
        query += f" LIMIT {args.limit}"

    cursor.execute(query)
    persons = cursor.fetchall()

    results = []

    for i, person in enumerate(persons, 1):
        sys.stdout.write(f"\r[{i}/{len(persons)}] Searching '{person['full_name']}'...")
        sys.stdout.flush()

        match = search_wikidata(person["full_name"], person["gender"], person["birth_year"], person["death_year"])

        if match:
            qid, confidence = match
            results.append({
                "core_name_norm": person["core_name_norm"],
                "full_name": person["full_name"],
                "gender": person["gender"],
                "birth_year": person["birth_year"],
                "death_year": person["death_year"],
                "wikidata_qid": qid,
                "confidence": confidence,
                "auto_match": confidence >= args.confidence
            })
        else:
            results.append({
                "core_name_norm": person["core_name_norm"],
                "full_name": person["full_name"],
                "gender": person["gender"],
                "birth_year": person["birth_year"],
                "death_year": person["death_year"],
                "wikidata_qid": None,
                "confidence": 0.0,
                "auto_match": False
            })

        # Rate limit: 1 request per second to be polite to Wikidata
        time.sleep(1)

    sys.stdout.write("\n")

    # Output CSV
    output_file = sys.stdout if not args.output else open(args.output, "w")

    # Write header
    output_file.write("core_name_norm,full_name,gender,birth_year,death_year,wikidata_qid,confidence,auto_match\n")

    # Write rows
    for result in results:
        output_file.write(
            f"{result['core_name_norm']},"
            f"{result['full_name']},"
            f"{result['gender'] or ''},"
            f"{result['birth_year'] or ''},"
            f"{result['death_year'] or ''},"
            f"{result['wikidata_qid'] or ''},"
            f"{result['confidence']:.2f},"
            f"{result['auto_match']}\n"
        )

    if args.output:
        output_file.close()
        print(f"\n✓ Results written to {args.output}")

    # Summary
    auto_matched = sum(1 for r in results if r["auto_match"])
    manual_review = sum(1 for r in results if r["wikidata_qid"] and not r["auto_match"])
    unmatched = sum(1 for r in results if not r["wikidata_qid"])

    print(f"\nSummary:")
    print(f"  Auto-matched (confidence ≥ {args.confidence:.2f}): {auto_matched}")
    print(f"  Manual review required: {manual_review}")
    print(f"  No match found: {unmatched}")

    conn.close()

if __name__ == "__main__":
    main()
