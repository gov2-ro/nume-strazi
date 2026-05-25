#!/usr/bin/env python3
"""
Fetch biographical stats from Wikidata for all persons with QIDs:
  - P509: cause of death  → cause_of_death_qid, cause_of_death_label
  - P569: date of birth   → fill missing birth_year only
  - P570: date of death   → fill missing death_year only

Deduplicates by QID so same-person aliases (e.g. all Cuza variants) receive the
same data without redundant API calls. Propagates to all aliases sharing a QID.

CSV audit trail at data/curation/wikidata_biostats.csv with --replay-csv for
rebuild persistence (same pattern as wiki_birthplace.py).

Usage:
    python3 tools/wiki_biostats.py [--limit N] [--dry-run]
    python3 tools/wiki_biostats.py --replay-csv [--force]
"""

import argparse
import csv
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
BATCH_SIZE   = 50
UA           = "RomanianStreetsAnalysis/1.0 (https://github.com/; alex.popescu@gmail.com)"
CSV_PATH     = Path("data/curation/wikidata_biostats.csv")
CSV_FIELDS   = [
    "core_name_norm", "full_name", "wikidata_qid",
    "cause_of_death_qid", "cause_of_death_label",
    "birth_year_wd", "death_year_wd",
]


def http_json(url, max_retries=4):
    headers = {"User-Agent": UA}
    delay = 2
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = max(int(e.headers.get("Retry-After") or delay), delay)
                print(f"  ⏳ 429 — sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                delay *= 2
                continue
            raise


def fetch_entities(qids, props):
    params = {
        "action": "wbgetentities",
        "ids":    "|".join(qids),
        "format": "json",
        "props":  props,
    }
    try:
        return http_json(f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}").get("entities", {})
    except Exception as e:
        print(f"  ⚠ API error: {e}", file=sys.stderr)
        return {}


def claim_targets(entity, prop):
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        ms = c.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        dv = ms.get("datavalue", {}).get("value", {})
        if isinstance(dv, dict) and dv.get("entity-type") == "item":
            out.append(dv["id"])
    return out


def claim_time(entity, prop):
    """Extract year from the first P569/P570 claim. Returns int or None."""
    for c in entity.get("claims", {}).get(prop, []):
        ms = c.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        t = ms.get("datavalue", {}).get("value", {}).get("time", "")
        # Wikidata time format: "+1849-00-00T00:00:00Z" or "-0044-03-15T00:00:00Z"
        if t:
            sign = -1 if t.startswith("-") else 1
            try:
                year = int(t.lstrip("+-").split("-")[0])
                return sign * year
            except (ValueError, IndexError):
                pass
    return None


def entity_label(entity):
    labels = entity.get("labels", {})
    for lang in ("en", "ro"):
        v = labels.get(lang, {}).get("value")
        if v:
            return v
    return None


def load_csv():
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    deduped = []
    for r in reversed(rows):
        if r["core_name_norm"] in seen:
            continue
        seen.add(r["core_name_norm"])
        deduped.append(r)
    deduped.reverse()
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(deduped)


def write_to_db(cursor, conn, rows, force=False):
    n = 0
    for r in rows:
        if not force:
            existing = cursor.execute(
                "SELECT cause_of_death_qid FROM persons WHERE core_name_norm=?",
                (r["core_name_norm"],)
            ).fetchone()
            if existing and existing[0]:
                continue
        cursor.execute("""
            UPDATE persons
            SET cause_of_death_qid=?, cause_of_death_label=?
            WHERE core_name_norm=?
        """, (
            r["cause_of_death_qid"] or None,
            r["cause_of_death_label"] or None,
            r["core_name_norm"],
        ))
        # Fill birth/death year only if missing in the DB
        if r.get("birth_year_wd"):
            cursor.execute("""
                UPDATE persons SET birth_year=?
                WHERE core_name_norm=? AND birth_year IS NULL
            """, (r["birth_year_wd"] or None, r["core_name_norm"]))
        if r.get("death_year_wd"):
            cursor.execute("""
                UPDATE persons SET death_year=?
                WHERE core_name_norm=? AND death_year IS NULL
            """, (r["death_year_wd"] or None, r["core_name_norm"]))
        if cursor.rowcount:
            n += 1
    conn.commit()

    # Propagate to same-QID aliases
    propagated = cursor.execute("""
        UPDATE persons
        SET cause_of_death_qid = (
              SELECT src.cause_of_death_qid FROM persons src
              WHERE src.wikidata_qid = persons.wikidata_qid
                AND src.cause_of_death_qid IS NOT NULL LIMIT 1),
            cause_of_death_label = (
              SELECT src.cause_of_death_label FROM persons src
              WHERE src.wikidata_qid = persons.wikidata_qid
                AND src.cause_of_death_qid IS NOT NULL LIMIT 1)
        WHERE cause_of_death_qid IS NULL
          AND wikidata_qid IN (
              SELECT wikidata_qid FROM persons WHERE cause_of_death_qid IS NOT NULL)
    """).rowcount
    if propagated:
        conn.commit()
        print(f"  ↳ Propagated cause_of_death to {propagated} same-QID alias(es)")

    return n


def replay_csv(cursor, conn, force):
    rows = load_csv()
    if not rows:
        print(f"No CSV at {CSV_PATH}; nothing to replay.")
        return
    n = write_to_db(cursor, conn, rows, force=force)
    print(f"✓ Replayed {n}/{len(rows)} rows from {CSV_PATH}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit",      type=int)
    p.add_argument("--dry-run",    action="store_true")
    p.add_argument("--replay-csv", action="store_true")
    p.add_argument("--force",      action="store_true",
                   help="With --replay-csv, overwrite existing cause_of_death values")
    p.add_argument("--db",         default="data/streets.db")
    args = p.parse_args()

    conn   = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for col in ("cause_of_death_qid", "cause_of_death_label"):
        try:
            cursor.execute(f"ALTER TABLE persons ADD COLUMN {col} TEXT;")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    if args.replay_csv:
        replay_csv(cursor, conn, args.force)
        conn.close()
        return

    # Fetch all distinct QIDs (dedup aliases → one API call per real person)
    all_persons = cursor.execute("""
        SELECT core_name_norm, full_name, wikidata_qid, birth_year, death_year
        FROM persons
        WHERE wikidata_qid IS NOT NULL
          AND cause_of_death_qid IS NULL
        ORDER BY full_name
    """).fetchall()

    if args.limit:
        all_persons = all_persons[:args.limit]

    # Group by QID so we fetch each QID once
    by_qid: dict[str, list] = {}
    for person in all_persons:
        by_qid.setdefault(person["wikidata_qid"], []).append(person)

    unique_qids = list(by_qid.keys())
    print(f"Processing {len(unique_qids)} unique QIDs ({len(all_persons)} persons)…")

    if not unique_qids:
        conn.close()
        return

    # Collect all P509 target QIDs to batch-fetch their labels
    p509_by_qid: dict[str, str | None] = {}
    p569_by_qid: dict[str, int | None] = {}
    p570_by_qid: dict[str, int | None] = {}
    all_cause_qids: set[str] = set()

    for batch_start in range(0, len(unique_qids), BATCH_SIZE):
        batch = unique_qids[batch_start:batch_start + BATCH_SIZE]
        ents  = fetch_entities(batch, props="claims")
        time.sleep(1)
        for qid in batch:
            e = ents.get(qid, {})
            p509s = claim_targets(e, "P509")
            p509_by_qid[qid] = p509s[0] if p509s else None
            p569_by_qid[qid] = claim_time(e, "P569")
            p570_by_qid[qid] = claim_time(e, "P570")
            if p509s:
                all_cause_qids.add(p509s[0])

    # Batch-fetch labels for all cause-of-death QIDs
    cause_labels: dict[str, str] = {}
    cause_list = list(all_cause_qids)
    for i in range(0, len(cause_list), BATCH_SIZE):
        slc  = cause_list[i:i + BATCH_SIZE]
        ents = fetch_entities(slc, props="labels")
        time.sleep(1)
        for qid in slc:
            label = entity_label(ents.get(qid, {}))
            if label:
                cause_labels[qid] = label

    # Build rows for all persons
    new_rows = []
    for qid, persons in by_qid.items():
        cause_qid   = p509_by_qid.get(qid)
        cause_label = cause_labels.get(cause_qid, "") if cause_qid else ""
        birth_wd    = p569_by_qid.get(qid)
        death_wd    = p570_by_qid.get(qid)
        display = f"{persons[0]['full_name']:35s} P509={cause_label or '-':30s} P569={birth_wd or '-'} P570={death_wd or '-'}"
        print(f"  {display}")
        for person in persons:
            new_rows.append({
                "core_name_norm":      person["core_name_norm"],
                "full_name":           person["full_name"],
                "wikidata_qid":        qid,
                "cause_of_death_qid":  cause_qid or "",
                "cause_of_death_label": cause_label,
                "birth_year_wd":       birth_wd or "",
                "death_year_wd":       death_wd or "",
            })

    if args.dry_run:
        print(f"\n[dry-run] Would update {len(new_rows)} persons")
        conn.close()
        return

    n_written = write_to_db(cursor, conn, new_rows)

    existing = load_csv()
    write_csv(existing + new_rows)
    print(f"\n✓ Updated {n_written} persons; CSV → {CSV_PATH}")

    summary = cursor.execute("""
        SELECT
            COUNT(*)                                          AS qid_persons,
            SUM(cause_of_death_qid IS NOT NULL)              AS with_cause,
            SUM(cause_of_death_label IS NOT NULL
                AND cause_of_death_label != '')               AS with_label
        FROM persons WHERE wikidata_qid IS NOT NULL
    """).fetchone()
    print(f"\nCoverage: {summary['with_label']}/{summary['qid_persons']} persons have a cause-of-death label.")

    conn.close()


if __name__ == "__main__":
    main()
