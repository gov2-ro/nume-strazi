# Portraits Feature Design

**Date:** 2026-05-16  
**Status:** Approved

## Overview

Wire Wikimedia portrait thumbnails into the Top Persoane dashboard panels. Persons with a Wikidata QID and a P18 image get a 26px circular photo next to their name chip. Persons without an image render name-only (no circle).

## Scope

Portraits appear in:
- Top global Bărbați / Femei lists (`top_men` / `top_women`)
- Per-județ Bărbați / Femei breakdowns (`men_by_judet` / `women_by_judet`)

Not in: cluster cloud, county fingerprint panels, or any non-person token.

## Components

### 1. `tools/fetch_portraits.py` (new)

Standalone enrichment script; run once after DB is populated.

**Behaviour:**
- Queries `persons` for all rows where `wikidata_qid IS NOT NULL` (currently 206).
- For each QID, calls Wikidata `wbgetentities` with `props=claims` to retrieve the P18 claim (Commons filename).
- Calls Wikimedia Commons `imageinfo` API with `iiurlwidth=64` to get the thumbnail URL.
- Downloads and saves to `dist/portraits/<qid>.jpg`.
- Idempotent: skips QIDs whose file already exists unless `--force` is passed.
- Rate-limited: 0.5 s between Wikidata API calls (same pattern as `wiki_scope.py`).
- Prints summary line: `206 processed, 142 found, 64 no image`.
- `--dry-run` flag prints what would be fetched without writing files.
- Creates `dist/portraits/` if it does not exist.
- No new dependencies: stdlib `urllib`, `json`, `sqlite3`.

**CLI:**
```
python3 tools/fetch_portraits.py [--force] [--dry-run] [--db PATH] [--limit N]
```

### 2. `site_queries.py` — section3 queries

Add `p.wikidata_qid` to the SELECT clause in:
- `top_men` query
- `top_women` query
- `_persons_by_judet()` inner function — add `MAX(p.wikidata_qid) AS wikidata_qid` to SELECT and `"wikidata_qid": r["wikidata_qid"]` to the output dict

### 3. `build_site.py` — portrait set injection

After loading section3 data, scan `dist/portraits/` for `*.jpg` filenames, strip the `.jpg` extension to collect QIDs, and pass as `portraits` to the template context:

```python
portraits_dir = Path("dist/portraits")
portraits = [p.stem for p in portraits_dir.glob("*.jpg")] if portraits_dir.exists() else []
```

Template receives the list; JS turns it into a `Set`.

### 4. Template (`templates/index.html.j2`) — PORTRAITS constant

Add near the other DATA constants:
```js
const PORTRAITS = new Set({{ portraits | tojson }});
```

### 5. JS — `renderFlat()` update

When `isPersons && r.wikidata_qid && PORTRAITS.has(r.wikidata_qid)`, prepend a portrait element:

```html
<span class="portrait"><img src="portraits/<qid>.jpg" alt=""></span>
```

Full token structure with portrait:
```html
<span class="ctok person [leader]">
  <span class="portrait"><img src="portraits/Q184935.jpg" alt=""></span>
  <span class="chip" style="font-size:Npx;">Name</span>
  <sup class="cnt-badge">N</sup>
</span>
```

No portrait → no `.portrait` span. No CSS changes needed; `.portrait img` rule already handles `object-fit: cover` and `overflow: hidden`.

## Data flow

```
build_db.py → seed_lookups.py → ... → wikidata_persons.py   # QIDs in persons table
tools/fetch_portraits.py                                      # dist/portraits/*.jpg
build_site.py                                                 # scans dist/portraits/, bakes PORTRAITS set
```

`fetch_portraits.py` is a one-time enrichment step, not part of the standard rebuild sequence. Re-run when new QIDs are added.

## Rebuild sequence (updated)

```bash
python3 build_db.py
python3 seed_lookups.py
python3 tools/seed_top500.py
python3 tools/seed_batch2.py
python3 tools/wikidata_persons.py --replay-csv --force
python3 tools/wiki_scope.py --limit 40   # repeat until no output
python3 tools/fetch_portraits.py         # new — run once; idempotent
python3 build_site.py
```

## Out of scope

- Portrait display in cluster cloud, county fingerprints, or any other panel
- Portrait detail views or lightboxes
- Updating `index-v2.html.j2` (dense layout variant) — can be done in a follow-up
