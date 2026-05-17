# Filter Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-attribute exploratory filter UI backed by a stdlib Python HTTP server that queries `streets.db` dynamically.

**Architecture:** A single `filter_server.py` (stdlib only: `http.server`, `sqlite3`, `urllib.parse`, `json`, `argparse`) serves two JSON endpoints (`/api/meta`, `/api/filter`) and one static HTML page (`dist/filter/index.html`). The HTML page is self-contained — all filtering is driven by JS calls to those endpoints. URL params mirror the active filter state so results are bookmarkable.

**Tech Stack:** Python 3.11 stdlib, SQLite, vanilla JS (no framework), IBM Plex fonts (Google Fonts CDN).

---

## File Map

| Path | Status | Responsibility |
|---|---|---|
| `filter_server.py` | Create | HTTP server, SQL builder, JSON endpoints |
| `tests/test_filter_server.py` | Create | Unit tests for `build_filter_query`, integration tests for endpoints |
| `dist/filter/index.html` | Create | Self-contained filter UI |

Nothing else is modified.

---

## Task 1: SQL query builder + test skeleton

The core of the server is `build_filter_query` — a pure function mapping filter params to a `(where_clause, bind_values)` pair. Write and test this in isolation before building any HTTP machinery.

**Files:**
- Create: `filter_server.py`
- Create: `tests/test_filter_server.py`

- [ ] **Step 1.1 — Write the failing tests**

Create `tests/test_filter_server.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest

import filter_server


class TestBuildFilterQuery:
    def test_empty_params_returns_empty_where(self):
        where, vals = filter_server.build_filter_query({})
        assert where == ""
        assert vals == []

    def test_single_judet(self):
        where, vals = filter_server.build_filter_query({'judet': ['HR']})
        assert "sd.judet IN (?)" in where
        assert vals == ['HR']

    def test_multiple_judete_joined_as_or(self):
        where, vals = filter_server.build_filter_query({'judet': ['HR', 'CV']})
        assert "sd.judet IN (?, ?)" in where
        assert vals == ['HR', 'CV']

    def test_uat_uppercased_partial_match(self):
        where, vals = filter_server.build_filter_query({'uat': ['ciuc']})
        assert "sd.uat LIKE ?" in where
        assert "%CIUC%" in vals

    def test_street_type(self):
        where, vals = filter_server.build_filter_query({'street_type': ['Strada']})
        assert "sd.street_type IN (?)" in where
        assert vals == ['Strada']

    def test_classification_person(self):
        where, vals = filter_server.build_filter_query({'classification': ['person']})
        assert "p.core_name_norm IS NOT NULL" in where

    def test_classification_saint(self):
        where, vals = filter_server.build_filter_query({'classification': ['saint']})
        assert "sd.is_saint = 1" in where

    def test_classification_multi_or(self):
        where, vals = filter_server.build_filter_query(
            {'classification': ['saint', 'date']}
        )
        assert "sd.is_saint = 1" in where
        assert "sd.is_date = 1" in where

    def test_profession_implies_person_join(self):
        where, vals = filter_server.build_filter_query({'profession': ['poet']})
        assert "p.core_name_norm IS NOT NULL" in where
        assert "p.profession IN (?)" in where
        assert vals == ['poet']

    def test_multi_person_subfilters(self):
        where, vals = filter_server.build_filter_query({
            'profession': ['poet'],
            'nationality': ['RO'],
            'gender': ['F'],
        })
        assert "p.profession IN (?)" in where
        assert "p.nationality IN (?)" in where
        assert "p.gender IN (?)" in where
        assert set(vals) == {'poet', 'RO', 'F'}

    def test_nature_type(self):
        where, vals = filter_server.build_filter_query({'nature_type': ['flower']})
        assert "n.core_name_norm IS NOT NULL" in where
        assert "n.nature_type IN (?)" in where
        assert vals == ['flower']

    def test_place_country(self):
        where, vals = filter_server.build_filter_query({'place_country': ['FR']})
        assert "pr.core_name_norm IS NOT NULL" in where
        assert "pr.country IN (?)" in where
        assert vals == ['FR']

    def test_category_subfilter(self):
        where, vals = filter_server.build_filter_query({'category': ['religious']})
        assert "c.core_name_norm IS NOT NULL" in where
        assert "c.category IN (?)" in where

    def test_combined_geo_and_person(self):
        where, vals = filter_server.build_filter_query({
            'judet': ['HR'],
            'profession': ['writer'],
            'nationality': ['RO'],
        })
        assert "sd.judet IN (?)" in where
        assert "p.profession IN (?)" in where
        assert "p.nationality IN (?)" in where
        assert 'HR' in vals and 'writer' in vals and 'RO' in vals

    def test_where_clause_starts_with_WHERE(self):
        where, _ = filter_server.build_filter_query({'judet': ['AB']})
        assert where.startswith("WHERE ")

    def test_all_conditions_joined_with_AND(self):
        where, _ = filter_server.build_filter_query({
            'judet': ['AB'],
            'street_type': ['Strada'],
        })
        assert " AND " in where
```

- [ ] **Step 1.2 — Run tests to confirm ImportError**

```bash
cd /Users/pax/devbox/gov2/misc/nume-strazi
source ~/devbox/envs/240826/bin/activate
pytest tests/test_filter_server.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'filter_server'`

- [ ] **Step 1.3 — Create `filter_server.py` with `build_filter_query` only**

Create `filter_server.py`:

```python
#!/usr/bin/env python3
"""
filter_server.py — Exploratory filter API for streets.db

Routes:
  GET /          → dist/filter/index.html
  GET /api/meta  → enum values for every filter dimension
  GET /api/filter → parameterized filter query, paginated JSON

Usage:
  python3 filter_server.py [--port 8765] [--db data/streets.db]
"""
import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from streets_lib import fix_diacritics, slugify

DB_PATH = "data/streets.db"
UI_PATH = Path("dist/filter/index.html")

_BASE_FROM = """
FROM streets_dedup sd
LEFT JOIN persons         p  ON p.core_name_norm  = sd.core_name_norm
LEFT JOIN name_categories c  ON c.core_name_norm  = sd.core_name_norm
LEFT JOIN nature_terms    n  ON n.core_name_norm  = sd.core_name_norm
LEFT JOIN place_refs      pr ON pr.core_name_norm = sd.core_name_norm
"""

_SELECT_COLS = """
    sd.name,
    sd.street_type,
    sd.uat,
    sd.judet,
    sd.siruta,
    sd.core_name,
    sd.name_normalized,
    CASE
        WHEN sd.is_numeric = 1             THEN 'numeric'
        WHEN sd.is_date    = 1             THEN 'date'
        WHEN sd.is_saint   = 1             THEN 'saint'
        WHEN p.core_name_norm  IS NOT NULL THEN 'person'
        WHEN n.core_name_norm  IS NOT NULL THEN 'nature'
        WHEN c.core_name_norm  IS NOT NULL THEN 'category'
        WHEN pr.core_name_norm IS NOT NULL THEN 'place'
        ELSE NULL
    END AS classification,
    p.full_name   AS person_full_name,
    p.profession,
    p.nationality,
    p.gender,
    p.era,
    p.wiki_scope,
    c.category,
    c.subcategory,
    n.nature_type,
    pr.place_type,
    pr.country    AS place_country
"""

_CLS_MAP = {
    'person':   'p.core_name_norm IS NOT NULL',
    'nature':   'n.core_name_norm IS NOT NULL',
    'place':    'pr.core_name_norm IS NOT NULL',
    'category': 'c.core_name_norm IS NOT NULL',
    'saint':    'sd.is_saint = 1',
    'date':     'sd.is_date = 1',
    'numeric':  'sd.is_numeric = 1',
}

_PERSON_COLS = ('profession', 'nationality', 'gender', 'era', 'wiki_scope')


def build_filter_query(params: dict) -> tuple[str, list]:
    """
    Build (where_clause, bind_values) from parsed query params.
    params: dict of str -> list[str] (multi-value already parsed).
    Returns '' for where_clause when no filters are active.
    All values go through ? placeholders — no string interpolation.
    """
    conditions: list[str] = []
    values: list = []

    if judete := params.get('judet'):
        conditions.append(f"sd.judet IN ({','.join('?' * len(judete))})")
        values.extend(judete)

    if uat := params.get('uat'):
        conditions.append("sd.uat LIKE ?")
        values.append(f"%{uat[0].upper()}%")

    if stypes := params.get('street_type'):
        conditions.append(f"sd.street_type IN ({','.join('?' * len(stypes))})")
        values.extend(stypes)

    if cls := params.get('classification'):
        parts = [_CLS_MAP[c] for c in cls if c in _CLS_MAP]
        if parts:
            conditions.append(f"({' OR '.join(parts)})")

    if any(params.get(f) for f in _PERSON_COLS):
        conditions.append('p.core_name_norm IS NOT NULL')
        for col in _PERSON_COLS:
            if vals := params.get(col):
                conditions.append(f"p.{col} IN ({','.join('?' * len(vals))})")
                values.extend(vals)

    if cats := params.get('category'):
        conditions.append('c.core_name_norm IS NOT NULL')
        conditions.append(f"c.category IN ({','.join('?' * len(cats))})")
        values.extend(cats)

    if subcats := params.get('subcategory'):
        conditions.append('c.core_name_norm IS NOT NULL')
        conditions.append(f"c.subcategory IN ({','.join('?' * len(subcats))})")
        values.extend(subcats)

    if ntypes := params.get('nature_type'):
        conditions.append('n.core_name_norm IS NOT NULL')
        conditions.append(f"n.nature_type IN ({','.join('?' * len(ntypes))})")
        values.extend(ntypes)

    if ptypes := params.get('place_type'):
        conditions.append('pr.core_name_norm IS NOT NULL')
        conditions.append(f"pr.place_type IN ({','.join('?' * len(ptypes))})")
        values.extend(ptypes)

    if pcountries := params.get('place_country'):
        conditions.append('pr.core_name_norm IS NOT NULL')
        conditions.append(f"pr.country IN ({','.join('?' * len(pcountries))})")
        values.extend(pcountries)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, values
```

- [ ] **Step 1.4 — Run tests to confirm they pass**

```bash
pytest tests/test_filter_server.py::TestBuildFilterQuery -v
```

Expected: all 16 tests PASS.

- [ ] **Step 1.5 — Commit**

```bash
git add filter_server.py tests/test_filter_server.py
git commit -m "feat(filter): add SQL query builder with unit tests"
```

---

## Task 2: DB connection + /api/meta endpoint + server skeleton

**Files:**
- Modify: `filter_server.py` (append after `build_filter_query`)
- Modify: `tests/test_filter_server.py` (append `TestServerIntegration` class)

- [ ] **Step 2.1 — Write integration test skeleton**

Append to `tests/test_filter_server.py`:

```python
import threading
import urllib.request

DB_PATH = "data/streets.db"
DB_EXISTS = os.path.exists(DB_PATH)


def _start_test_server(db_path: str) -> tuple:
    """Start server on a random port, return (base_url, server)."""
    conn = filter_server.get_db(db_path)
    handler = filter_server.make_handler(conn)
    server = HTTPServer(('localhost', 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://localhost:{port}", server


@pytest.mark.skipif(not DB_EXISTS, reason="streets.db not present")
class TestServerIntegration:
    @pytest.fixture(scope="class")
    def base_url(self):
        url, server = _start_test_server(DB_PATH)
        yield url
        server.shutdown()

    def test_meta_returns_200(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/meta") as r:
            assert r.status == 200

    def test_meta_has_required_keys(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/meta") as r:
            data = json.loads(r.read())
        required = {
            'judete', 'street_types', 'classifications',
            'professions', 'nationalities', 'genders', 'eras', 'wiki_scopes',
            'categories', 'subcategories', 'nature_types',
            'place_types', 'place_countries',
        }
        assert required <= set(data.keys())

    def test_meta_judete_non_empty(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/meta") as r:
            data = json.loads(r.read())
        assert len(data['judete']) > 0

    def test_unknown_path_returns_404(self, base_url):
        try:
            urllib.request.urlopen(f"{base_url}/nonexistent")
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 404
```

- [ ] **Step 2.2 — Run to confirm failure**

```bash
pytest tests/test_filter_server.py::TestServerIntegration -v 2>&1 | head -30
```

Expected: `AttributeError: module 'filter_server' has no attribute 'get_db'`

- [ ] **Step 2.3 — Append `get_db`, `query_meta`, `make_handler`, `main` to `filter_server.py`**

Add after the `build_filter_query` function:

```python
def get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query_meta(conn: sqlite3.Connection) -> dict:
    def distinct(sql):
        return [r[0] for r in conn.execute(sql)]

    return {
        'judete': distinct(
            "SELECT DISTINCT judet FROM streets WHERE judet IS NOT NULL ORDER BY judet"),
        'street_types': distinct(
            "SELECT DISTINCT street_type FROM streets WHERE street_type IS NOT NULL ORDER BY street_type"),
        'classifications': [
            'person', 'nature', 'place', 'category', 'saint', 'date', 'numeric'
        ],
        'professions': distinct(
            "SELECT DISTINCT profession FROM persons WHERE profession IS NOT NULL ORDER BY profession"),
        'nationalities': distinct(
            "SELECT DISTINCT nationality FROM persons WHERE nationality IS NOT NULL ORDER BY nationality"),
        'genders': distinct(
            "SELECT DISTINCT gender FROM persons WHERE gender IS NOT NULL ORDER BY gender"),
        'eras': distinct(
            "SELECT DISTINCT era FROM persons WHERE era IS NOT NULL ORDER BY era"),
        'wiki_scopes': distinct(
            "SELECT DISTINCT wiki_scope FROM persons WHERE wiki_scope IS NOT NULL ORDER BY wiki_scope"),
        'categories': distinct(
            "SELECT DISTINCT category FROM name_categories WHERE category IS NOT NULL ORDER BY category"),
        'subcategories': distinct(
            "SELECT DISTINCT subcategory FROM name_categories WHERE subcategory IS NOT NULL ORDER BY subcategory"),
        'nature_types': distinct(
            "SELECT DISTINCT nature_type FROM nature_terms WHERE nature_type IS NOT NULL ORDER BY nature_type"),
        'place_types': distinct(
            "SELECT DISTINCT place_type FROM place_refs WHERE place_type IS NOT NULL ORDER BY place_type"),
        'place_countries': distinct(
            "SELECT DISTINCT country FROM place_refs WHERE country IS NOT NULL ORDER BY country"),
    }


def make_handler(conn: sqlite3.Connection):
    class FilterHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # silence per-request access log

        def send_json(self, data, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip('/')

            if path in ('', '/filter'):
                if not UI_PATH.exists():
                    self.send_json({'error': f'{UI_PATH} not found — run build_site.py first'}, 503)
                    return
                html = UI_PATH.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)

            elif path == '/api/meta':
                try:
                    self.send_json(query_meta(conn))
                except Exception as exc:
                    self.send_json({'error': str(exc)}, 500)

            elif path == '/api/filter':
                try:
                    params = parse_qs(parsed.query, keep_blank_values=False)
                    self.send_json({'total': 0, 'limit': 200, 'offset': 0, 'rows': []})
                except Exception as exc:
                    self.send_json({'error': str(exc)}, 500)

            else:
                self.send_json({'error': 'not found'}, 404)

    return FilterHandler


def main() -> None:
    parser = argparse.ArgumentParser(description='Filter API server for streets.db')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default=DB_PATH)
    args = parser.parse_args()

    conn = get_db(args.db)
    handler = make_handler(conn)
    server = HTTPServer(('localhost', args.port), handler)
    print(f'Filter server → http://localhost:{args.port}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
```

Note: `/api/filter` returns a stub (empty rows) for now — Task 3 wires up the real query.

- [ ] **Step 2.4 — Add missing import to test file**

In `tests/test_filter_server.py`, the integration test uses `HTTPServer` and `json` — add at the top of the file after the existing imports:

```python
from http.server import HTTPServer
import json
```

- [ ] **Step 2.5 — Run integration tests**

```bash
pytest tests/test_filter_server.py::TestServerIntegration -v
```

Expected: all 4 meta tests PASS; filter tests (added in Task 3) not yet present.

- [ ] **Step 2.6 — Commit**

```bash
git add filter_server.py tests/test_filter_server.py
git commit -m "feat(filter): add server skeleton, /api/meta endpoint"
```

---

## Task 3: /api/filter endpoint

**Files:**
- Modify: `filter_server.py` (replace stub with `query_filter`, wire to handler)
- Modify: `tests/test_filter_server.py` (append filter + pagination tests)

- [ ] **Step 3.1 — Write failing filter integration tests**

Append to the `TestServerIntegration` class in `tests/test_filter_server.py`:

```python
    def test_filter_no_params_returns_rows(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/filter") as r:
            data = json.loads(r.read())
        assert data['total'] > 0
        assert len(data['rows']) > 0
        assert data['limit'] == 200
        assert data['offset'] == 0

    def test_filter_judet_constrains_results(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/filter?judet=HR") as r:
            data = json.loads(r.read())
        assert all(row['judet'] == 'HR' for row in data['rows'])
        assert data['total'] > 0

    def test_filter_classification_person_rows_only(self, base_url):
        url = f"{base_url}/api/filter?classification=person&limit=10"
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read())
        assert all(row['classification'] == 'person' for row in data['rows'])

    def test_filter_profession_poet_in_HR(self, base_url):
        url = f"{base_url}/api/filter?judet=HR&profession=poet&limit=50"
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read())
        assert all(row['judet'] == 'HR' for row in data['rows'])
        assert all(row['profession'] == 'poet' for row in data['rows'])

    def test_filter_pagination_no_overlap(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/filter?limit=10&offset=0") as r:
            p1 = json.loads(r.read())
        with urllib.request.urlopen(f"{base_url}/api/filter?limit=10&offset=10") as r:
            p2 = json.loads(r.read())
        keys1 = {(r['name'], r['uat']) for r in p1['rows']}
        keys2 = {(r['name'], r['uat']) for r in p2['rows']}
        assert len(keys1 & keys2) == 0

    def test_filter_rows_have_street_slug(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/filter?limit=5") as r:
            data = json.loads(r.read())
        assert all('street_slug' in row for row in data['rows'])

    def test_filter_rows_have_uat_slug(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/filter?limit=5") as r:
            data = json.loads(r.read())
        assert all('uat_slug' in row for row in data['rows'])

    def test_filter_limit_respected(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/filter?limit=7") as r:
            data = json.loads(r.read())
        assert len(data['rows']) <= 7
        assert data['limit'] == 7

    def test_filter_limit_capped_at_1000(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/filter?limit=9999") as r:
            data = json.loads(r.read())
        assert data['limit'] == 1000
```

- [ ] **Step 3.2 — Run to confirm failures**

```bash
pytest tests/test_filter_server.py::TestServerIntegration -v 2>&1 | tail -20
```

Expected: new tests FAIL (stub returns `total: 0, rows: []`).

- [ ] **Step 3.3 — Implement `query_filter` in `filter_server.py`**

Add `query_filter` after `query_meta`:

```python
def query_filter(conn: sqlite3.Connection, params: dict) -> dict:
    limit = min(int((params.get('limit') or ['200'])[0]), 1000)
    offset = int((params.get('offset') or ['0'])[0])

    where, values = build_filter_query(params)

    count_sql = f"SELECT COUNT(*) {_BASE_FROM} {where}"
    total = conn.execute(count_sql, values).fetchone()[0]

    select_sql = (
        f"SELECT {_SELECT_COLS} {_BASE_FROM} {where} "
        f"ORDER BY sd.judet, sd.uat, sd.name LIMIT ? OFFSET ?"
    )
    rows = conn.execute(select_sql, [*values, limit, offset]).fetchall()

    def serialize(r: sqlite3.Row) -> dict:
        d = dict(r)
        core = d.pop('core_name', None)
        name_norm = d.get('name_normalized', '')
        d['street_slug'] = slugify(core or name_norm)
        d['uat_slug'] = slugify(fix_diacritics(d.get('uat') or ''))
        return d

    return {
        'total': total,
        'limit': limit,
        'offset': offset,
        'rows': [serialize(r) for r in rows],
    }
```

Then update the `/api/filter` branch in `make_handler` — replace the stub line:

```python
                    self.send_json({'total': 0, 'limit': 200, 'offset': 0, 'rows': []})
```

with:

```python
                    self.send_json(query_filter(conn, params))
```

- [ ] **Step 3.4 — Run all tests**

```bash
pytest tests/test_filter_server.py -v
```

Expected: all tests PASS.

- [ ] **Step 3.5 — Manual smoke test**

```bash
source ~/devbox/envs/240826/bin/activate
python3 filter_server.py &
sleep 1
curl -s "http://localhost:8765/api/filter?judet=HR&profession=writer&nationality=RO" | python3 -m json.tool | head -40
kill %1
```

Expected: JSON with `total > 0`, rows all having `judet=HR`, `profession=writer`, `nationality=RO`.

- [ ] **Step 3.6 — Commit**

```bash
git add filter_server.py tests/test_filter_server.py
git commit -m "feat(filter): implement /api/filter endpoint with paginated SQL"
```

---

## Task 4: Filter UI

**Files:**
- Create: `dist/filter/index.html`

- [ ] **Step 4.1 — Create the directory**

```bash
mkdir -p dist/filter
```

- [ ] **Step 4.2 — Create `dist/filter/index.html`**

Create `dist/filter/index.html` with the full content below. This is self-contained — CSS variables match the main site theme; fonts load from Google Fonts CDN. No framework, no build step.

```html
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Filtru avansat — Cum ne numim străzile</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600;700&family=Barlow+Semi+Condensed:wght@600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #FFFFFF;
  --surface-1: #F7F9FC;
  --surface-2: #ECF1F8;
  --surface-blue: #DEE8F4;
  --warn-1: #FFF7CC;
  --warn-2: #FBE486;
  --ink: #0B1118;
  --ink-2: #2A313B;
  --muted: #5A6573;
  --muted-2: #8B95A2;
  --rule: #E2E6EC;
  --rule-strong: #BFC7D2;
  --hairline: #EEF1F5;
  --plaque: #0E4D92;
  --plaque-deep: #08366D;
  --accent: #C04F35;
  --sans: 'IBM Plex Sans', system-ui, sans-serif;
  --mono: 'IBM Plex Mono', monospace;
  --street: 'Barlow Semi Condensed', 'IBM Plex Sans', sans-serif;
  --panel-w: 270px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 13px;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--plaque); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Top bar ── */
.topbar {
  background: var(--plaque);
  color: #fff;
  padding: 10px 20px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.topbar a { color: rgba(255,255,255,.75); }
.topbar a:hover { color: #fff; text-decoration: none; }
.topbar .sep { color: rgba(255,255,255,.4); }
.topbar .title { font-family: var(--street); font-weight: 700; font-size: 14px; color: #fff; }

/* ── Layout ── */
.layout {
  display: flex;
  min-height: calc(100vh - 40px);
}

/* ── Filter panel ── */
.panel {
  width: var(--panel-w);
  flex-shrink: 0;
  border-right: 1px solid var(--rule);
  background: var(--surface-1);
  padding: 16px 14px;
  overflow-y: auto;
  position: sticky;
  top: 0;
  height: calc(100vh - 40px);
}
.panel-title {
  font-size: 10px;
  letter-spacing: .18em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--muted);
  margin-bottom: 14px;
}
.filter-section { margin-bottom: 18px; }
.filter-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--muted-2);
  margin-bottom: 6px;
}
.filter-search {
  width: 100%;
  font-family: var(--sans);
  font-size: 12px;
  border: 1px solid var(--rule-strong);
  border-radius: 3px;
  padding: 5px 8px;
  background: var(--bg);
  color: var(--ink);
  margin-bottom: 6px;
  outline: none;
}
.filter-search:focus { border-color: var(--plaque); }
.check-list {
  max-height: 160px;
  overflow-y: auto;
  border: 1px solid var(--rule);
  border-radius: 3px;
  background: var(--bg);
}
.check-list label {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  border-bottom: 1px solid var(--hairline);
}
.check-list label:last-child { border-bottom: none; }
.check-list label:hover { background: var(--surface-1); }
.check-list input[type=checkbox] { accent-color: var(--plaque); flex-shrink: 0; }
.check-list label.hidden { display: none; }

.text-filter {
  width: 100%;
  font-family: var(--sans);
  font-size: 12px;
  border: 1px solid var(--rule-strong);
  border-radius: 3px;
  padding: 6px 8px;
  background: var(--bg);
  color: var(--ink);
  outline: none;
}
.text-filter:focus { border-color: var(--plaque); }

.radio-list label {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 0;
  cursor: pointer;
  font-size: 12px;
}
.radio-list input[type=radio] { accent-color: var(--plaque); }

.subpanel {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--rule);
}
.subpanel.hidden { display: none; }

.btn-clear {
  width: 100%;
  margin-top: 14px;
  padding: 7px;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  background: transparent;
  border: 1px solid var(--rule-strong);
  border-radius: 3px;
  color: var(--muted);
  cursor: pointer;
}
.btn-clear:hover { background: var(--surface-2); color: var(--ink); }

/* ── Results area ── */
.results {
  flex: 1;
  padding: 20px 24px;
  overflow-x: auto;
}
.results-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.results-count {
  font-family: var(--street);
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
}
.results-sub {
  font-size: 12px;
  color: var(--muted);
}
.empty-state {
  color: var(--muted);
  font-size: 13px;
  padding: 32px 0;
}

.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.tbl th {
  text-align: left;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--muted);
  border-bottom: 2px solid var(--rule-strong);
  padding: 6px 10px 8px;
  white-space: nowrap;
}
.tbl td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--hairline);
  vertical-align: middle;
}
.tbl tr:hover td { background: var(--surface-1); }
.tbl .cell-name { font-weight: 600; font-family: var(--street); font-size: 13px; }
.tbl .cell-type { color: var(--muted-2); white-space: nowrap; }
.tbl .cell-uat  { max-width: 220px; }
.tbl .cell-jud  { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.tbl .cell-detail { color: var(--muted); max-width: 160px; }
.cls-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 2px;
  letter-spacing: .06em;
  text-transform: uppercase;
  background: var(--surface-2);
  color: var(--muted);
}
.cls-person   { background: #E8F0FB; color: #2A4A8C; }
.cls-nature   { background: #E8F5EC; color: #2E6040; }
.cls-place    { background: #FFF3E0; color: #7A4A00; }
.cls-category { background: #F3E8F8; color: #5A2080; }
.cls-saint    { background: #FFF8E1; color: #7A5800; }

.pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
  font-size: 12px;
  color: var(--muted);
}
.btn-page {
  padding: 5px 14px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--rule-strong);
  border-radius: 3px;
  background: var(--bg);
  color: var(--plaque);
  cursor: pointer;
}
.btn-page:hover { background: var(--surface-blue); }
.btn-page:disabled { color: var(--muted-2); cursor: default; background: var(--surface-1); }

.loading {
  font-size: 12px;
  color: var(--muted);
  padding: 24px 0;
}
</style>
</head>
<body>

<div class="topbar">
  <a href="/" class="title">Cum ne numim străzile</a>
  <span class="sep">›</span>
  <span>Filtru avansat</span>
</div>

<div class="layout">

  <!-- ── Filter panel ── -->
  <aside class="panel" id="panel">
    <div class="panel-title">Filtre</div>

    <!-- County -->
    <div class="filter-section">
      <div class="filter-label">Județ</div>
      <input class="filter-search" id="judet-search" placeholder="Caută județ…" autocomplete="off">
      <div class="check-list" id="judet-list"></div>
    </div>

    <!-- UAT -->
    <div class="filter-section">
      <div class="filter-label">Localitate</div>
      <input class="text-filter" id="uat-input" placeholder="ex. Miercurea Ciuc" autocomplete="off">
    </div>

    <!-- Street type -->
    <div class="filter-section">
      <div class="filter-label">Tip arteră</div>
      <div class="check-list" id="street-type-list"></div>
    </div>

    <!-- Classification -->
    <div class="filter-section">
      <div class="filter-label">Clasificare</div>
      <div class="radio-list" id="classification-list"></div>
    </div>

    <!-- Contextual sub-filters -->
    <div class="subpanel hidden" id="subpanel-person">
      <div class="filter-label">Persoană</div>
      <div class="filter-section">
        <div class="filter-label">Profesie</div>
        <div class="check-list" id="profession-list"></div>
      </div>
      <div class="filter-section">
        <div class="filter-label">Naționalitate</div>
        <div class="check-list" id="nationality-list"></div>
      </div>
      <div class="filter-section">
        <div class="filter-label">Gen</div>
        <div class="check-list" id="gender-list"></div>
      </div>
      <div class="filter-section">
        <div class="filter-label">Epocă</div>
        <div class="check-list" id="era-list"></div>
      </div>
      <div class="filter-section">
        <div class="filter-label">Notorietate Wikipedia</div>
        <div class="check-list" id="wiki-scope-list"></div>
      </div>
    </div>

    <div class="subpanel hidden" id="subpanel-nature">
      <div class="filter-label">Natură</div>
      <div class="filter-section">
        <div class="filter-label">Tip</div>
        <div class="check-list" id="nature-type-list"></div>
      </div>
    </div>

    <div class="subpanel hidden" id="subpanel-place">
      <div class="filter-label">Loc</div>
      <div class="filter-section">
        <div class="filter-label">Tip</div>
        <div class="check-list" id="place-type-list"></div>
      </div>
      <div class="filter-section">
        <div class="filter-label">Țară</div>
        <div class="check-list" id="place-country-list"></div>
      </div>
    </div>

    <div class="subpanel hidden" id="subpanel-category">
      <div class="filter-label">Categorie</div>
      <div class="filter-section">
        <div class="filter-label">Categorie</div>
        <div class="check-list" id="category-list"></div>
      </div>
      <div class="filter-section">
        <div class="filter-label">Subcategorie</div>
        <div class="check-list" id="subcategory-list"></div>
      </div>
    </div>

    <button class="btn-clear" id="btn-clear">Șterge toate filtrele</button>
  </aside>

  <!-- ── Results ── -->
  <main class="results">
    <div class="results-header">
      <div class="results-count" id="results-count">—</div>
      <div class="results-sub" id="results-sub"></div>
    </div>
    <div id="results-body"><div class="loading">Se încarcă…</div></div>
    <div class="pagination" id="pagination" style="display:none">
      <button class="btn-page" id="btn-prev">← Anterior</button>
      <span id="page-info"></span>
      <button class="btn-page" id="btn-next">Următor →</button>
    </div>
  </main>

</div>

<script>
'use strict';

// ── State ──────────────────────────────────────────────────────────────
const state = {
  meta: null,
  offset: 0,
  limit: 200,
  debounceTimer: null,
};

// ── Helpers ─────────────────────────────────────────────────────────────
function esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function getChecked(listId) {
  return Array.from(
    document.querySelectorAll(`#${listId} input[type=checkbox]:checked`)
  ).map(el => el.value);
}

function getRadio(listId) {
  const el = document.querySelector(`#${listId} input[type=radio]:checked`);
  return el ? el.value : '';
}

// ── URL sync ─────────────────────────────────────────────────────────────
function buildParams() {
  const p = new URLSearchParams();

  getChecked('judet-list').forEach(v => p.append('judet', v));

  const uat = document.getElementById('uat-input').value.trim();
  if (uat) p.set('uat', uat);

  getChecked('street-type-list').forEach(v => p.append('street_type', v));

  const cls = getRadio('classification-list');
  if (cls) p.set('classification', cls);

  if (cls === 'person' || !cls) {
    getChecked('profession-list').forEach(v => p.append('profession', v));
    getChecked('nationality-list').forEach(v => p.append('nationality', v));
    getChecked('gender-list').forEach(v => p.append('gender', v));
    getChecked('era-list').forEach(v => p.append('era', v));
    getChecked('wiki-scope-list').forEach(v => p.append('wiki_scope', v));
  }
  if (cls === 'nature' || !cls) {
    getChecked('nature-type-list').forEach(v => p.append('nature_type', v));
  }
  if (cls === 'place' || !cls) {
    getChecked('place-type-list').forEach(v => p.append('place_type', v));
    getChecked('place-country-list').forEach(v => p.append('place_country', v));
  }
  if (cls === 'category' || !cls) {
    getChecked('category-list').forEach(v => p.append('category', v));
    getChecked('subcategory-list').forEach(v => p.append('subcategory', v));
  }

  if (state.offset) p.set('offset', state.offset);
  return p;
}

function pushUrl(params) {
  const qs = params.toString();
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
}

function readUrl() {
  return new URLSearchParams(location.search);
}

// ── Render helpers ───────────────────────────────────────────────────────
function makeCheckList(listId, values, selectedSet) {
  const el = document.getElementById(listId);
  el.innerHTML = values.map(v => `
    <label>
      <input type="checkbox" value="${esc(v)}"${selectedSet.has(v) ? ' checked' : ''}>
      ${esc(v)}
    </label>`).join('');
  el.querySelectorAll('input').forEach(cb => cb.addEventListener('change', onFilterChange));
}

function makeRadioList(listId, values, selected) {
  const el = document.getElementById(listId);
  const opts = [['', 'Toate'], ...values.map(v => [v, v])];
  el.innerHTML = opts.map(([v, label]) => `
    <label>
      <input type="radio" name="classification" value="${esc(v)}"${v === selected ? ' checked' : ''}>
      ${esc(label)}
    </label>`).join('');
  el.querySelectorAll('input').forEach(r => r.addEventListener('change', () => {
    updateSubpanels();
    onFilterChange();
  }));
}

function updateSubpanels() {
  const cls = getRadio('classification-list');
  ['person', 'nature', 'place', 'category'].forEach(c => {
    document.getElementById(`subpanel-${c}`).classList.toggle('hidden', cls !== c);
  });
}

// ── Filter panel population ───────────────────────────────────────────────
function populatePanel(meta, urlParams) {
  const sel = (key) => new Set(urlParams.getAll(key));

  makeCheckList('judet-list', meta.judete, sel('judet'));
  makeCheckList('street-type-list', meta.street_types, sel('street_type'));
  makeRadioList('classification-list', meta.classifications, urlParams.get('classification') || '');

  makeCheckList('profession-list',    meta.professions,    sel('profession'));
  makeCheckList('nationality-list',   meta.nationalities,  sel('nationality'));
  makeCheckList('gender-list',        meta.genders,        sel('gender'));
  makeCheckList('era-list',           meta.eras,           sel('era'));
  makeCheckList('wiki-scope-list',    meta.wiki_scopes,    sel('wiki_scope'));
  makeCheckList('nature-type-list',   meta.nature_types,   sel('nature_type'));
  makeCheckList('place-type-list',    meta.place_types,    sel('place_type'));
  makeCheckList('place-country-list', meta.place_countries, sel('place_country'));
  makeCheckList('category-list',      meta.categories,     sel('category'));
  makeCheckList('subcategory-list',   meta.subcategories,  sel('subcategory'));

  document.getElementById('uat-input').value = urlParams.get('uat') || '';

  updateSubpanels();

  // County search-within
  document.getElementById('judet-search').addEventListener('input', e => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('#judet-list label').forEach(lbl => {
      lbl.classList.toggle('hidden', !lbl.textContent.toLowerCase().includes(q));
    });
  });
}

// ── Query & render results ─────────────────────────────────────────────────
async function fetchResults(params) {
  const apiParams = new URLSearchParams(params);
  apiParams.set('limit', state.limit);
  apiParams.set('offset', state.offset);
  // remove UI-only offset param if present
  apiParams.delete('offset');
  apiParams.set('offset', state.offset);

  const res = await fetch(`/api/filter?${apiParams}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

function clsBadge(row) {
  const cls = row.classification || '';
  const detail = row.person_full_name || row.nature_type || row.place_type || row.category || cls;
  return `<span class="cls-badge cls-${esc(cls)}">${esc(cls)}</span> ${esc(detail)}`;
}

function renderResults(data) {
  const { total, limit, offset, rows } = data;
  const from = offset + 1;
  const to = Math.min(offset + rows.length, total);

  document.getElementById('results-count').textContent =
    total === 0 ? 'Nicio potrivire' : `${total.toLocaleString('ro')} rezultate`;
  document.getElementById('results-sub').textContent =
    total > 0 ? `(${from}–${to} din ${total.toLocaleString('ro')})` : '';

  const body = document.getElementById('results-body');
  if (rows.length === 0) {
    body.innerHTML = '<div class="empty-state">Nicio potrivire găsită pentru filtrele selectate.</div>';
    document.getElementById('pagination').style.display = 'none';
    return;
  }

  body.innerHTML = `
    <table class="tbl">
      <thead>
        <tr>
          <th>Nume stradă</th>
          <th>Tip</th>
          <th>Localitate</th>
          <th>Județ</th>
          <th>Detaliu</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(r => `
        <tr>
          <td class="cell-name">
            ${r.street_slug
              ? `<a href="/strada/${esc(r.street_slug)}/">${esc(r.name)}</a>`
              : esc(r.name)}
          </td>
          <td class="cell-type">${esc(r.street_type || '')}</td>
          <td class="cell-uat">
            ${r.uat_slug
              ? `<a href="/oras/${esc((r.judet||'').toLowerCase())}/${esc(r.uat_slug)}/">${esc(r.uat)}</a>`
              : esc(r.uat)}
          </td>
          <td class="cell-jud">${esc(r.judet)}</td>
          <td class="cell-detail">${clsBadge(r)}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;

  const pag = document.getElementById('pagination');
  pag.style.display = total > limit ? 'flex' : 'none';
  document.getElementById('page-info').textContent = `${from}–${to} din ${total.toLocaleString('ro')}`;
  document.getElementById('btn-prev').disabled = offset === 0;
  document.getElementById('btn-next').disabled = to >= total;
}

// ── Event handlers ─────────────────────────────────────────────────────────
function onFilterChange() {
  state.offset = 0;
  clearTimeout(state.debounceTimer);
  state.debounceTimer = setTimeout(runQuery, 120);
}

async function runQuery() {
  const params = buildParams();
  pushUrl(params);
  document.getElementById('results-body').innerHTML = '<div class="loading">Se caută…</div>';
  try {
    const data = await fetchResults(params);
    renderResults(data);
  } catch (e) {
    document.getElementById('results-body').innerHTML =
      `<div class="empty-state">Eroare: ${esc(e.message)}</div>`;
  }
}

document.getElementById('uat-input').addEventListener('input', onFilterChange);

document.getElementById('btn-prev').addEventListener('click', () => {
  state.offset = Math.max(0, state.offset - state.limit);
  runQuery();
});
document.getElementById('btn-next').addEventListener('click', () => {
  state.offset += state.limit;
  runQuery();
});

document.getElementById('btn-clear').addEventListener('click', () => {
  // Reset all checkboxes
  document.querySelectorAll('.check-list input[type=checkbox]').forEach(cb => cb.checked = false);
  // Reset radio to "All"
  const allRadio = document.querySelector('#classification-list input[type=radio][value=""]');
  if (allRadio) allRadio.checked = true;
  // Reset text
  document.getElementById('uat-input').value = '';
  document.getElementById('judet-search').value = '';
  // Show all hidden county labels
  document.querySelectorAll('#judet-list label').forEach(l => l.classList.remove('hidden'));
  state.offset = 0;
  updateSubpanels();
  runQuery();
});

// ── Init ───────────────────────────────────────────────────────────────────
(async () => {
  try {
    const [metaRes] = await Promise.all([fetch('/api/meta')]);
    state.meta = await metaRes.json();

    const urlParams = readUrl();
    state.offset = parseInt(urlParams.get('offset') || '0', 10);
    if (isNaN(state.offset)) state.offset = 0;

    populatePanel(state.meta, urlParams);
    await runQuery();
  } catch (e) {
    document.getElementById('results-body').innerHTML =
      `<div class="empty-state">Nu s-a putut conecta la server (${esc(e.message)}). Rulați: <code>python3 filter_server.py</code></div>`;
  }
})();
</script>
</body>
</html>
```

- [ ] **Step 4.3 — Start server and verify in browser**

```bash
source ~/devbox/envs/240826/bin/activate
python3 filter_server.py
```

Open `http://localhost:8765/` in a browser. Verify:
- Filter panel populates (all dropdowns have values)
- Unfiltered load shows results
- Selecting `Județ = HR`, `Clasificare = Person`, `Profesie = writer` returns only matching rows
- URL updates on every filter change; pasting URL in new tab restores the same filter state
- "Șterge toate filtrele" resets everything and re-queries

- [ ] **Step 4.4 — Commit**

```bash
git add dist/filter/index.html
git commit -m "feat(filter): add self-contained filter UI at dist/filter/index.html"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Covered by |
|---|---|
| `/api/meta` returns all enum values | Task 2, `query_meta` |
| `/api/filter` with multi-value AND/OR params | Task 1+3, `build_filter_query` + `query_filter` |
| `total` + paginated rows in response | Task 3, `query_filter` |
| `street_slug` = `slugify(core_name or name_normalized)` | Task 3, `serialize()` |
| `uat_slug` = `slugify(fix_diacritics(uat))` | Task 3, `serialize()` |
| Classification CASE matches `streets_classified_pct` | Task 1, `_SELECT_COLS` |
| Person sub-filters implicitly constrain to person | Task 1, `build_filter_query` |
| `uat` filter is case-insensitive LIKE | Task 1, `build_filter_query` |
| URL params mirror filter state | Task 4, `buildParams` + `pushUrl` |
| Contextual sub-panels (person/nature/place/category) | Task 4, `updateSubpanels` |
| `--port` and `--db` CLI args | Task 2, `main` |
| 404 on unknown paths | Task 2, `make_handler` |
| Pagination: prev/next, page info | Task 4, render + event handlers |
| "Clear all" button | Task 4, `btn-clear` listener |
| County search-within | Task 4, `judet-search` listener |

**No placeholders found.**

**Type/name consistency:** `build_filter_query` defined in Task 1 and called by `query_filter` in Task 3 — same signature. `make_handler(conn)` defined in Task 2, called in Task 2's test and `main`. `query_meta` / `query_filter` both receive `sqlite3.Connection`. Consistent throughout.
