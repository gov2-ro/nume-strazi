# Portraits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch Wikimedia portrait thumbnails for all persons with Wikidata QIDs and display them as 26px circles next to person name chips in the Top Persoane dashboard panels.

**Architecture:** A standalone fetch script (`tools/fetch_portraits.py`) downloads thumbnails to `dist/portraits/<qid>.jpg` once. `build_site.py` scans that directory and bakes a `PORTRAITS` set into the template. `renderFlat()` in the JS checks the set and prepends an `<img>` when available; persons without a portrait render name-only.

**Tech Stack:** Python 3.11 stdlib (urllib, sqlite3, json, pathlib), Jinja2 template, vanilla JS. Wikidata `wbgetentities` API + Wikimedia Commons imageinfo API.

---

### Task 1: `tools/fetch_portraits.py`

**Files:**
- Create: `tools/fetch_portraits.py`

- [ ] **Step 1: Write the script**

```python
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
import time
from pathlib import Path

WIKIDATA_API  = "https://www.wikidata.org/w/api.php"
COMMONS_API   = "https://commons.wikimedia.org/w/api.php"
BATCH_SIZE    = 50
THUMB_WIDTH   = 64
UA            = "RomanianStreetsAnalysis/1.0"
PORTRAITS_DIR = Path("dist/portraits")


def fetch_p18_batch(qids: list[str]) -> dict[str, str | None]:
    """Batch-fetch P18 (image filename) for up to 50 QIDs at once.
    Returns dict of qid -> Commons filename, or None if no P18 claim."""
    params = {
        "action": "wbgetentities",
        "ids":    "|".join(qids),
        "format": "json",
        "props":  "claims",
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ⚠ Wikidata API error: {e}", file=sys.stderr)
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
    url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ⚠ Commons API error for {filename!r}: {e}", file=sys.stderr)
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        info = page.get("imageinfo", [])
        if info:
            return info[0].get("thumburl")
    return None


def download_file(url: str, dest: Path) -> bool:
    """Download URL to dest. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"  ⚠ Download error {url}: {e}", file=sys.stderr)
        return False


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
        time.sleep(0.5)

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

            time.sleep(0.5)

    print(f"\n{processed} processed · {found} downloaded · {skipped} skipped (cached) · {no_image} no image")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify dry-run works**

```bash
source ~/devbox/envs/240826/bin/activate
python3 tools/fetch_portraits.py --dry-run --limit 5
```

Expected: prints 5 lines of `  <QID>: <Commons filename>` (or "no image" for those without P18), then a summary line. No files created.

- [ ] **Step 3: Run for real (first 10 to sanity-check)**

```bash
python3 tools/fetch_portraits.py --limit 10
ls dist/portraits/
```

Expected: some `.jpg` files appear in `dist/portraits/`. Not all 10 will have images — that's fine.

- [ ] **Step 4: Run for all QIDs**

```bash
python3 tools/fetch_portraits.py
```

Expected: `206 processed · N downloaded · 0 skipped · M no image` (N + M = 206). Takes ~2–3 minutes due to rate limiting.

- [ ] **Step 5: Commit**

```bash
git add tools/fetch_portraits.py dist/portraits/
git commit -m "feat(portraits): add fetch_portraits.py; cache thumbnails for all QID persons"
```

---

### Task 2: Add `wikidata_qid` to section3 queries in `site_queries.py`

**Files:**
- Modify: `site_queries.py`

Three changes in `section3()`:

- [ ] **Step 1: Update `top_men` query (around line 184)**

Change:
```python
    top_men = _rows(conn, """
        SELECT p.full_name, p.gender, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'M'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 15
    """)
```
To:
```python
    top_men = _rows(conn, """
        SELECT p.full_name, p.gender, p.wikidata_qid, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'M'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 15
    """)
```

- [ ] **Step 2: Update `top_women` query (around line 193)**

Change:
```python
    top_women = _rows(conn, """
        SELECT p.full_name, p.gender, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'F'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 15
    """)
```
To:
```python
    top_women = _rows(conn, """
        SELECT p.full_name, p.gender, p.wikidata_qid, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'F'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 15
    """)
```

- [ ] **Step 3: Update `_persons_by_judet()` (around line 203)**

In the `per_judet` CTE, change the SELECT from:
```sql
              SELECT
                CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                     ELSE sd.judet END AS judet,
                p.core_name_norm,
                MAX(p.full_name) AS full_name,
                MAX(p.gender)    AS gender,
                COUNT(*)         AS street_count
```
To:
```sql
              SELECT
                CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                     ELSE sd.judet END AS judet,
                p.core_name_norm,
                MAX(p.full_name)       AS full_name,
                MAX(p.gender)          AS gender,
                MAX(p.wikidata_qid)    AS wikidata_qid,
                COUNT(*)               AS street_count
```

And in the `ranked` CTE, change:
```sql
              SELECT judet, full_name, gender, street_count,
                     ROW_NUMBER() OVER (PARTITION BY judet ORDER BY street_count DESC) AS rn
```
To:
```sql
              SELECT judet, full_name, gender, wikidata_qid, street_count,
                     ROW_NUMBER() OVER (PARTITION BY judet ORDER BY street_count DESC) AS rn
```

And the final SELECT:
```sql
            SELECT judet, full_name, gender, street_count
            FROM ranked WHERE rn <= 10
```
To:
```sql
            SELECT judet, full_name, gender, wikidata_qid, street_count
            FROM ranked WHERE rn <= 10
```

And in the Python dict-building loop at the end of `_persons_by_judet()`, change:
```python
            out.setdefault(r["judet"], []).append({
                "full_name": r["full_name"],
                "gender": r["gender"],
                "street_count": r["street_count"],
            })
```
To:
```python
            out.setdefault(r["judet"], []).append({
                "full_name":    r["full_name"],
                "gender":       r["gender"],
                "wikidata_qid": r["wikidata_qid"],
                "street_count": r["street_count"],
            })
```

- [ ] **Step 4: Verify queries return QIDs**

```bash
source ~/devbox/envs/240826/bin/activate
python3 -c "
import site_queries, json
conn = site_queries.get_connection('data/streets.db')
s3 = site_queries.section3(conn)
print(json.dumps(s3['top_men'][:3], ensure_ascii=False, indent=2))
"
```

Expected: each object in `top_men` now has a `wikidata_qid` field (may be a Q-string or null).

- [ ] **Step 5: Commit**

```bash
git add site_queries.py
git commit -m "feat(portraits): add wikidata_qid to section3 person queries"
```

---

### Task 3: Inject `portraits` set into `build_site.py`

**Files:**
- Modify: `build_site.py`

- [ ] **Step 1: Add portrait scanning to `build()`**

In `build_site.py`, after the `data = {...}` block (around line 43), add portrait scanning before the Jinja env setup:

```python
    if variant not in STATIC_VARIANTS:
        portraits_dir = DIST / "portraits"
        data["portraits"] = [p.stem for p in sorted(portraits_dir.glob("*.jpg"))] \
            if portraits_dir.exists() else []
```

The full `build()` function body should look like:

```python
def build(db_path: str = DB_PATH, variant: str = "default") -> None:
    DIST.mkdir(exist_ok=True)

    if variant in STATIC_VARIANTS:
        data = {}
    else:
        conn = site_queries.get_connection(db_path)
        data = {
            "section1": site_queries.section1(conn),
            "section2": site_queries.section2(conn),
            "section3": site_queries.section3(conn),
            "section4": site_queries.section4(conn),
            "section5": site_queries.section5(conn),
            "section6": site_queries.section6(conn),
            "section8": site_queries.section8(conn),
        }
        conn.close()

        portraits_dir = DIST / "portraits"
        data["portraits"] = [p.stem for p in sorted(portraits_dir.glob("*.jpg"))] \
            if portraits_dir.exists() else []

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    ...
```

- [ ] **Step 2: Verify portraits list is populated**

```bash
source ~/devbox/envs/240826/bin/activate
python3 -c "
from pathlib import Path
portraits_dir = Path('dist/portraits')
result = [p.stem for p in sorted(portraits_dir.glob('*.jpg'))] if portraits_dir.exists() else []
print(f'{len(result)} portraits found')
print(result[:5])
"
```

Expected: prints the count of downloaded portraits and the first 5 QID strings.

- [ ] **Step 3: Commit**

```bash
git add build_site.py
git commit -m "feat(portraits): inject portraits QID list into build context"
```

---

### Task 4: Wire portraits into the template and `renderFlat()`

**Files:**
- Modify: `templates/index.html.j2`

Two changes: add the `PORTRAITS` JS constant, and update `renderFlat()`.

- [ ] **Step 1: Add `PORTRAITS` constant after the other DATA_ constants**

In `templates/index.html.j2`, find the `<script>` block at the top (lines 13–20):

```html
  <script>
const DATA_S2 = {{ section2 | tojson }};
const DATA_S3 = {{ section3 | tojson }};
const DATA_S4 = {{ section4 | tojson }};
const DATA_S5 = {{ section5 | tojson }};
const DATA_S6 = {{ section6 | tojson }};
const DATA_S8 = {{ section8 | tojson }};
  </script>
```

Change to:

```html
  <script>
const DATA_S2 = {{ section2 | tojson }};
const DATA_S3 = {{ section3 | tojson }};
const DATA_S4 = {{ section4 | tojson }};
const DATA_S5 = {{ section5 | tojson }};
const DATA_S6 = {{ section6 | tojson }};
const DATA_S8 = {{ section8 | tojson }};
const PORTRAITS = new Set({{ portraits | tojson }});
  </script>
```

- [ ] **Step 2: Update `renderFlat()` to show portrait images**

Find the person token rendering block inside `renderFlat()` (around line 1431):

```js
      if (isPersons) {
        return `<span class="ctok person${isLeader ? ' leader' : ''}">`
             + `<span class="chip" style="font-size:${fs}px;">${escapeHtml(labelFn(r))}</span>`
             + cnt + `</span>`;
      }
```

Replace with:

```js
      if (isPersons) {
        const qid = r.wikidata_qid;
        const portrait = (qid && PORTRAITS.has(qid))
          ? `<span class="portrait"><img src="portraits/${qid}.jpg" alt="" loading="lazy"></span>`
          : '';
        return `<span class="ctok person${isLeader ? ' leader' : ''}">`
             + portrait
             + `<span class="chip" style="font-size:${fs}px;">${escapeHtml(labelFn(r))}</span>`
             + cnt + `</span>`;
      }
```

- [ ] **Step 3: Build the site and verify**

```bash
source ~/devbox/envs/240826/bin/activate
python3 build_site.py
```

Expected output: `→ dist/index.html  (N KB)` with no errors.

- [ ] **Step 4: Spot-check the HTML**

```bash
grep -c 'class="portrait"' dist/index.html
grep 'portraits/Q' dist/index.html | head -3
```

Expected: non-zero count of `.portrait` spans; lines showing `src="portraits/Q<number>.jpg"`.

- [ ] **Step 5: Check the browser**

Open `dist/index.html` in a browser (or `python3 build_site.py --serve`). In the Top Persoane panel:
- Persons with a Wikimedia image show a 26px circular portrait left of their name chip.
- Persons without an image show only the name chip with no circle.
- Switching the județ filter updates both men and women lists with portraits.

- [ ] **Step 6: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(portraits): wire Wikimedia thumbnails into Top Persoane panel"
```

---

### Task 5: Update CLAUDE.md rebuild sequence and activity log

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/activity-history.md`

- [ ] **Step 1: Add `fetch_portraits.py` to rebuild sequence in CLAUDE.md**

Find the rebuild sequence comment block in `CLAUDE.md` under `## Common commands`. Add after `wiki_scope.py`:

```bash
# Fetch/refresh portrait thumbnails (run once; idempotent)
python3 tools/fetch_portraits.py
```

The full sequence in the comment should read:

```bash
python3 build_db.py
python3 seed_lookups.py
python3 tools/seed_top500.py
python3 tools/seed_batch2.py
python3 tools/wikidata_persons.py --replay-csv --force
python3 tools/wiki_scope.py --limit 40   # repeat until no output
python3 tools/fetch_portraits.py         # run once; idempotent
python3 build_site.py
```

- [ ] **Step 2: Add activity log entry**

In `docs/activity-history.md`, prepend a new entry under the latest heading:

```markdown
## 2026-05-16 — Wire Wikimedia portrait thumbnails into Top Persoane panel

Added `tools/fetch_portraits.py`: fetches P18 claim from Wikidata, downloads 64px thumbnails
from Wikimedia Commons, caches to `dist/portraits/<qid>.jpg`. Idempotent — skips cached files.

Updated `site_queries.py` section3 queries to include `wikidata_qid` in top_men, top_women,
and per-județ person lists.

Updated `build_site.py` to scan `dist/portraits/` and bake a `PORTRAITS` JS Set into the
template. Updated `renderFlat()` in `templates/index.html.j2` to prepend a 26px portrait
`<img>` for persons that have a cached thumbnail; persons without an image render name-only.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/activity-history.md
git commit -m "docs: update rebuild sequence and activity log for portraits feature"
```
