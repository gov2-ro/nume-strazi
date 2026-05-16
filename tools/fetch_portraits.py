#!/usr/bin/env python3
"""
Fetch Wikimedia portrait thumbnails for persons with Wikidata QIDs.

For each QID in the persons table, fetches the P18 (image) claim from
Wikidata, then downloads a 64px thumbnail from Wikimedia Commons.
Saves to dist/portraits/<qid>.jpg. Idempotent — skips cached files.

Usage:
    python3 tools/fetch_portraits.py [--force] [--dry-run] [--limit N] [--db PATH]

Options:
    --force      Re-download even if file already cached
    --dry-run    Print what would be fetched without writing files
    --limit N    Process only first N QIDs
    --db PATH    SQLite DB path (default: data/streets.db)
"""

import sqlite3
import sys
import argparse
import json
import urllib.request
import urllib.parse
import urllib.error
import time
from pathlib import Path

WIKIDATA_API  = "https://www.wikidata.org/w/api.php"
COMMONS_API   = "https://commons.wikimedia.org/w/api.php"
BATCH_SIZE    = 50
THUMB_WIDTH   = 64
UA            = "RomanianStreetsAnalysis/1.0"
PORTRAITS_DIR = Path("dist/portraits")
# Conservative delays — Wikimedia CDN rate-limits at ~1 req/sec sustained
BATCH_SLEEP   = 2.0   # after each Wikidata batch fetch
ITEM_SLEEP    = 2.0   # after each successful download
# Max wait on Retry-After (cap so we don't hang indefinitely)
MAX_RETRY_WAIT = 120


def _get_with_retry(url: str, label: str, binary: bool = False):
    """GET a URL with retry, honouring Retry-After on 429.

    Returns parsed JSON (binary=False) or raw bytes (binary=True), or None on failure.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(1, 5):  # up to 4 attempts
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                return raw if binary else json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 0)) or (attempt * 15)
                wait = min(wait, MAX_RETRY_WAIT)
                print(f"  ⚠ 429 {label} — waiting {wait}s (attempt {attempt}/4)", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  ⚠ HTTP {e.code} on {label}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"  ⚠ Error on {label}: {e}", file=sys.stderr)
            return None
    print(f"  ⚠ Gave up on {label} after 4 attempts", file=sys.stderr)
    return None


def fetch_p18_batch(qids: list[str]) -> dict[str, str | None]:
    """Batch-fetch P18 (image filename) for up to 50 QIDs at once.
    Returns dict of qid -> Commons filename, or None if no P18 claim."""
    params = {
        "action": "wbgetentities",
        "ids":    "|".join(qids),
        "format": "json",
        "props":  "claims",
    }
    url  = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    data = _get_with_retry(url, f"Wikidata batch ({qids[0]}…)")
    if data is None:
        return {qid: None for qid in qids}

    results: dict[str, str | None] = {}
    for qid in qids:
        entity = data.get("entities", {}).get(qid, {})
        p18 = entity.get("claims", {}).get("P18", [])
        filename = None
        if p18:
            try:
                filename = p18[0]["mainsnak"]["datavalue"]["value"]
            except (KeyError, IndexError):
                pass
        results[qid] = filename
    return results


def fetch_thumb_url(filename: str) -> str | None:
    """Get 64px thumbnail URL from Wikimedia Commons for a given filename."""
    params = {
        "action":    "query",
        "titles":    f"File:{filename}",
        "prop":      "imageinfo",
        "iiprop":    "url",
        "iiurlwidth": str(THUMB_WIDTH),
        "format":    "json",
    }
    url  = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    data = _get_with_retry(url, f"Commons:{filename[:40]}")
    if data is None:
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        info = page.get("imageinfo", [])
        if info:
            return info[0].get("thumburl")
    return None


def download_file(url: str, dest: Path) -> bool:
    """Download URL to dest with retry on 429. Returns True on success."""
    raw = _get_with_retry(url, dest.name, binary=True)
    if raw is None:
        return False
    dest.write_bytes(raw)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--force",   action="store_true", help="Re-download even if cached")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing files")
    parser.add_argument("--limit",   type=int, default=None, help="Process only first N QIDs")
    parser.add_argument("--db",      default="data/streets.db", help="SQLite DB path")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT wikidata_qid FROM persons WHERE wikidata_qid IS NOT NULL ORDER BY wikidata_qid"
    ).fetchall()
    conn.close()

    qids = [r[0] for r in rows]
    if args.limit:
        qids = qids[: args.limit]

    print(f"Processing {len(qids)} QIDs …")

    if not args.dry_run:
        PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)

    processed = found = skipped = no_image = 0

    for i in range(0, len(qids), BATCH_SIZE):
        batch = qids[i : i + BATCH_SIZE]
        p18_map = fetch_p18_batch(batch)
        time.sleep(BATCH_SLEEP)

        for qid, filename in p18_map.items():
            processed += 1
            dest = PORTRAITS_DIR / f"{qid}.jpg"

            if not args.force and dest.exists():
                skipped += 1
                continue

            if filename is None:
                no_image += 1
                continue

            thumb_url = fetch_thumb_url(filename)
            time.sleep(1.0)  # between Commons API and download
            if thumb_url is None:
                no_image += 1
                continue

            if args.dry_run:
                print(f"  {qid}: {filename}")
                found += 1
                continue

            if download_file(thumb_url, dest):
                found += 1
                print(f"  ✓ {qid}")
            else:
                no_image += 1

            time.sleep(ITEM_SLEEP)

    print(f"\n{processed} processed · {found} downloaded · {skipped} skipped (cached) · {no_image} no image")


if __name__ == "__main__":
    main()
