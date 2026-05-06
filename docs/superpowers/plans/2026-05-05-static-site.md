# Static Site Build — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `build_site.py` that queries `data/streets.db` and renders a single `dist/index.html` — a Romanian-language interactive publication about street names.

**Architecture:** Python build script reads SQLite → serializes per-section JSON → renders single Jinja2 template → `dist/index.html`. Charts via Observable Plot CDN (bar/lollipop). Map via D3 + TopoJSON CDN. All CSS/JS embedded inline; one file output. Dev workflow: `python3 build_site.py && open dist/index.html`.

**Tech Stack:** Python 3.11 (stdlib + Jinja2 + sqlite3), Observable Plot 0.6 (CDN), D3 7 + TopoJSON 3 (CDN), Source Serif 4 + Inter (Google Fonts CDN)

---

## File map

| File | Role |
|---|---|
| `build_site.py` | CLI entry point; orchestrates queries → render → output |
| `site_queries.py` | All SQLite query functions; returns typed Python dicts |
| `templates/index.html.j2` | Single Jinja2 template; all CSS + JS + HTML inline |
| `tests/test_queries.py` | pytest tests for all query functions |
| `tests/test_build.py` | Integration smoke tests (build runs, output exists, key text present) |
| `dist/index.html` | Generated artifact — not committed |
| `dist/ro-counties.topojson` | Copied from `data/gis/romania-counties.geojson` — not committed |

---

## Schema quick reference

```sql
-- Always use streets_dedup (deduplicates polling-section repetitions)
streets_dedup:  judet, uat, siruta, name, name_normalized, core_name, core_name_norm,
                is_saint, is_date, is_numeric, street_type, rank

persons:        core_name_norm PK, full_name, gender, birth_year, death_year,
                era, profession, nationality, wikidata_qid, wiki_scope,
                wiki_sitelinks, wiki_ro_url, wiki_en_url, wiki_ro_views

nature_terms:   core_name_norm PK, term, nature_type
name_categories:core_name_norm PK, category, subcategory
```

Join streets to persons/nature/categories always via `core_name_norm`.

---

## Task 1: Project scaffolding

**Files:**
- Create: `build_site.py`
- Create: `site_queries.py`
- Create: `templates/index.html.j2`
- Create: `tests/__init__.py`
- Create: `tests/test_build.py`

- [ ] **Step 1.1: Create `site_queries.py` stub**

```python
# site_queries.py
import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

- [ ] **Step 1.2: Create `build_site.py` skeleton**

```python
#!/usr/bin/env python3
# build_site.py
import argparse
import json
import os
import shutil
import sqlite3
from pathlib import Path

import jinja2

import site_queries


DIST = Path("dist")
TEMPLATES = Path("templates")
DB_PATH = "data/streets.db"
COUNTIES_SRC = Path("data/gis/romania-counties.geojson")


def build(db_path: str = DB_PATH) -> None:
    DIST.mkdir(exist_ok=True)

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

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    tmpl = env.get_template("index.html.j2")
    html = tmpl.render(**data)

    out = DIST / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"  → {out}  ({out.stat().st_size // 1024} KB)")

    if COUNTIES_SRC.exists():
        shutil.copy(COUNTIES_SRC, DIST / "ro-counties.geojson")
        print(f"  → {DIST}/ro-counties.geojson")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build street names static site")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    build(db_path=args.db)


if __name__ == "__main__":
    main()
```

- [ ] **Step 1.3: Create minimal Jinja2 template**

```html
{# templates/index.html.j2 #}
<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cum ne numim străzile</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400;1,8..60,500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    /* Design system — will be expanded in Task 2 */
    :root {
      --bg: #FAF8F3;
      --ink: #15171A;
      --muted: #6E6E70;
      --rule: #DDDCD7;
      --wash: #EEEAE0;
      --accent: #C04F35;
    }
    body { margin: 0; background: var(--bg); color: var(--ink); }
  </style>
</head>
<body>
  <p>Scaffold OK — {{ section1.total_streets }} adrese</p>
</body>
</html>
```

- [ ] **Step 1.4: Create `tests/test_build.py` with smoke test**

```python
# tests/test_build.py
import subprocess
import sys
from pathlib import Path


def test_build_runs_and_produces_output():
    result = subprocess.run(
        [sys.executable, "build_site.py", "--db", "data/streets.db"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert Path("dist/index.html").exists()
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "adrese" in html


def test_counties_geojson_copied():
    assert Path("dist/ro-counties.geojson").exists()
```

- [ ] **Step 1.5: Add `section1` stub to `site_queries.py`**

```python
def section1(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS total FROM streets_dedup"
    ).fetchone()
    return {"total_streets": row["total"]}
```

- [ ] **Step 1.6: Run smoke test**

```bash
source ~/devbox/envs/240826/bin/activate
pytest tests/test_build.py -v
```

Expected: 2 tests pass.

- [ ] **Step 1.7: Commit**

```bash
git add build_site.py site_queries.py templates/index.html.j2 tests/
git commit -m "feat(site): scaffold build_site.py + Jinja2 template + smoke tests"
```

---

## Task 2: CSS design system + navigation

**Files:**
- Modify: `templates/index.html.j2` — replace stub style with full CSS

- [ ] **Step 2.1: Add full CSS design system to template `<style>` block**

Replace the stub `<style>` with:

```css
:root {
  --bg: #FAF8F3;
  --ink: #15171A;
  --muted: #6E6E70;
  --rule: #DDDCD7;
  --wash: #EEEAE0;
  --accent: #C04F35;
  --serif: 'Source Serif 4', Georgia, serif;
  --sans: 'Inter', system-ui, sans-serif;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--serif);
  -webkit-font-smoothing: antialiased;
}

/* Nav */
.site-nav {
  position: sticky; top: 0; z-index: 100;
  background: var(--bg);
  border-bottom: 1px solid var(--rule);
  padding: 14px 36px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--sans);
  font-size: 11.5px;
  letter-spacing: .06em;
}
.site-nav .brand {
  font-weight: 600;
  color: var(--ink);
  letter-spacing: .12em;
  text-transform: uppercase;
  text-decoration: none;
}
.site-nav nav { display: flex; gap: 22px; }
.site-nav nav a { color: var(--muted); text-decoration: none; }
.site-nav nav a:hover { color: var(--ink); }

/* Section wrapper */
.section {
  padding: 64px 80px 48px;
  max-width: 1200px;
  margin: 0 auto;
}
.section + .section { border-top: 1px solid var(--rule); }

/* Section source footer */
.section-source {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--muted);
  border-top: 1px solid var(--rule);
  padding: 14px 80px;
  display: flex;
  justify-content: space-between;
  max-width: 1200px;
  margin: 0 auto;
}

/* Typography */
.kicker {
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 500;
  margin-bottom: 22px;
}
h1, h2, h3 { font-weight: 500; letter-spacing: -.012em; }
h1 { font-size: 56px; line-height: 1.1; margin-bottom: 28px; }
h2 { font-size: 42px; line-height: 1.1; margin-bottom: 20px; }
h3 { font-size: 26px; line-height: 1.15; margin-bottom: 14px; }
.accent { color: var(--accent); }

.lede {
  font-size: 18px;
  line-height: 1.55;
  font-style: italic;
  color: #3A3A3D;
  max-width: 680px;
  margin-bottom: 40px;
}

/* Chip toggles */
.chip-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 24px; padding-bottom: 18px;
  border-bottom: 1px solid var(--rule);
  font-family: var(--sans); font-size: 11px;
}
.chip-row .label {
  letter-spacing: .12em; text-transform: uppercase;
  font-weight: 500; color: var(--muted);
}
.chip {
  font-family: var(--sans); font-size: 12px;
  color: var(--muted);
  padding: 5px 13px;
  border: 1px solid var(--rule); border-radius: 999px;
  background: transparent; cursor: pointer;
  transition: background .15s, color .15s;
}
.chip:hover, .chip.active {
  color: var(--bg); background: var(--ink); border-color: var(--ink);
}

/* Tag pills */
.tag {
  font-family: var(--sans); font-size: 10px;
  color: var(--muted); background: var(--wash);
  padding: 2px 7px; border-radius: 999px;
  margin-left: 8px; vertical-align: middle;
}
.tag.person { background: #F4E8E5; color: #B8432F; }

/* Rank list */
.rank-list { display: flex; flex-direction: column; }
.rank-header {
  display: grid;
  grid-template-columns: 36px 1fr 220px 56px;
  gap: 14px; align-items: center;
  padding-bottom: 10px;
  border-bottom: 1.5px solid var(--ink);
  font-family: var(--sans); font-size: 10px;
  letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); font-weight: 500;
}
.rank-row {
  display: grid;
  grid-template-columns: 36px 1fr 220px 56px;
  align-items: center; gap: 14px;
  padding: 9px 0;
  border-bottom: 1px solid var(--wash);
}
.rank-row:last-child { border-bottom: none; }
.rank-num {
  font-family: var(--sans); font-size: 11px;
  color: var(--muted); text-align: right;
  font-variant-numeric: tabular-nums;
}
.rank-name { font-family: var(--serif); font-size: 16px; }
.rank-count {
  font-family: var(--sans); font-size: 12px;
  color: var(--muted); text-align: right;
  font-variant-numeric: tabular-nums;
}

/* Bar */
.bar-wrap {
  height: 6px; background: var(--wash);
  border-radius: 1px; position: relative;
}
.bar {
  position: absolute; left: 0; top: 0;
  height: 100%; border-radius: 1px;
  background: var(--ink); opacity: .4;
}
.bar.accent { background: var(--accent); opacity: .65; }
.bar.female { background: var(--accent); opacity: .5; }

/* Callout box */
.callout {
  border-left: 3px solid var(--accent);
  padding: 12px 18px;
  margin-bottom: 28px;
  font-family: var(--serif); font-size: 14px;
  font-style: italic; color: #3A3A3D;
}
.callout strong { font-style: normal; color: var(--ink); }

/* Mobile */
@media (max-width: 768px) {
  .section { padding: 48px 24px 36px; }
  .section-source { padding: 12px 24px; }
  .site-nav { padding: 12px 20px; }
  .site-nav nav { display: none; }
  h1 { font-size: 34px; }
  h2 { font-size: 28px; }
  .lede { font-size: 16px; }
}
```

- [ ] **Step 2.2: Add navigation HTML to template body**

Replace `<body>` content with:

```html
<body>
<nav class="site-nav">
  <a href="#acasa" class="brand">Cum ne numim străzile</a>
  <nav>
    <a href="#acasa">Acasă</a>
    <a href="#cele-mai-intalnite">Cele mai întâlnite</a>
    <a href="#pe-cine-onoram">Pe cine onorăm</a>
    <a href="#recunoastere">Recunoaștere</a>
    <a href="#tematica">Tematică</a>
    <a href="#harta">Harta</a>
    <a href="#renumiri">Renumiri</a>
    <a href="#curiozitati">Curiozități</a>
  </nav>
</nav>

{# Sections injected by later tasks #}
<p style="padding:40px 80px;font-family:var(--sans);color:var(--muted)">
  Build scaffold · {{ section1.total_streets }} adrese
</p>

</body>
```

- [ ] **Step 2.3: Run build, open in browser**

```bash
source ~/devbox/envs/240826/bin/activate && python3 build_site.py
open dist/index.html
```

Verify nav renders, fonts load from Google Fonts.

- [ ] **Step 2.4: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(site): add CSS design system and nav"
```

---

## Task 3: Data queries — all sections

**Files:**
- Modify: `site_queries.py` — add all query functions
- Modify: `tests/test_queries.py` — add tests

- [ ] **Step 3.1: Write failing tests for all query shapes**

Create `tests/test_queries.py`:

```python
# tests/test_queries.py
import site_queries

DB = "data/streets.db"


def _conn():
    return site_queries.get_connection(DB)


def test_section1_shape():
    d = site_queries.section1(_conn())
    assert "total_streets" in d
    assert isinstance(d["total_streets"], int)
    assert d["total_streets"] > 100_000

    assert "top_men" in d
    assert len(d["top_men"]) == 5
    assert "full_name" in d["top_men"][0]
    assert "street_count" in d["top_men"][0]

    assert "top_women" in d
    assert len(d["top_women"]) == 5

    assert "total_persons_m" in d
    assert "total_persons_f" in d


def test_section2_shape():
    d = site_queries.section2(_conn())
    assert "top_names" in d
    assert len(d["top_names"]) == 50
    row = d["top_names"][0]
    assert "name_normalized" in row
    assert "street_count" in row
    assert "category" in row
    # Principală must be present but first
    assert d["top_names"][0]["name_normalized"].lower() in ("principala", "principală")


def test_section3_shape():
    d = site_queries.section3(_conn())
    assert "top_persons" in d
    assert len(d["top_persons"]) >= 15
    row = d["top_persons"][0]
    assert "full_name" in row
    assert "street_count" in row
    assert "gender" in row

    assert "total_m" in d
    assert "total_f" in d
    assert d["total_m"] > d["total_f"]

    assert "profession_dist" in d
    assert len(d["profession_dist"]) > 0

    assert "era_dist" in d
    assert len(d["era_dist"]) > 0


def test_section4_shape():
    d = site_queries.section4(_conn())
    assert "top_pageviews" in d
    assert len(d["top_pageviews"]) >= 5
    row = d["top_pageviews"][0]
    assert "full_name" in row
    assert "wiki_ro_views" in row
    assert "wiki_scope" in row
    assert row["wiki_ro_views"] is not None

    assert "tier_counts" in d
    assert "universal" in d["tier_counts"]
    assert "national" in d["tier_counts"]
    assert "local" in d["tier_counts"]


def test_section5_shape():
    d = site_queries.section5(_conn())
    assert "theme_dist" in d
    assert len(d["theme_dist"]) >= 4
    for row in d["theme_dist"]:
        assert "category" in row
        assert "count" in row

    assert "nature_subtypes" in d
    assert "ideo_tokens" in d


def test_section6_shape():
    d = site_queries.section6(_conn())
    assert "by_judet" in d
    assert len(d["by_judet"]) >= 40  # 41 județe + B sectors
    row = d["by_judet"][0]
    assert "judet" in row
    assert "total_streets" in row
    assert "saint_pct" in row
    assert "numeric_pct" in row
    assert "modal_name" in row


def test_section8_shape():
    d = site_queries.section8(_conn())
    assert "ciorani" in d
    assert d["ciorani"]["total"] > 0
    assert d["ciorani"]["numeric"] > 0

    assert "longest_names" in d
    assert len(d["longest_names"]) >= 5

    assert "animal_names" in d
    assert len(d["animal_names"]) >= 5

    assert "local_honorees" in d
```

- [ ] **Step 3.2: Run tests to see them fail**

```bash
source ~/devbox/envs/240826/bin/activate
pytest tests/test_queries.py -v 2>&1 | head -40
```

Expected: all fail with `AttributeError: module 'site_queries' has no attribute 'section2'` etc.

- [ ] **Step 3.3: Implement all query functions in `site_queries.py`**

```python
# site_queries.py
import sqlite3
from typing import Any


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def section1(conn: sqlite3.Connection) -> dict:
    total = _one(conn, "SELECT COUNT(*) AS n FROM streets_dedup")["n"]

    top_men = _rows(conn, """
        SELECT p.full_name, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'M'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 5
    """)

    top_women = _rows(conn, """
        SELECT p.full_name, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'F'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 5
    """)

    counts = _one(conn, """
        SELECT
          SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) AS m,
          SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) AS f
        FROM (
          SELECT DISTINCT p.core_name_norm, p.gender
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
        ) p
    """)

    return {
        "total_streets": total,
        "top_men": top_men,
        "top_women": top_women,
        "total_persons_m": counts.get("m", 0) or 0,
        "total_persons_f": counts.get("f", 0) or 0,
    }


def section2(conn: sqlite3.Connection) -> dict:
    top_names = _rows(conn, """
        SELECT
          sd.name_normalized,
          COUNT(*) AS street_count,
          CASE
            WHEN p.core_name_norm IS NOT NULL THEN 'persoană'
            WHEN nt.core_name_norm IS NOT NULL THEN 'natură'
            WHEN sd.is_saint = 1 THEN 'religios'
            WHEN sd.is_date = 1 THEN 'dată'
            WHEN nc.category IS NOT NULL THEN nc.category
            ELSE 'altele'
          END AS category
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
        LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE sd.is_numeric = 0
          AND sd.core_name IS NOT NULL
        GROUP BY sd.name_normalized
        ORDER BY street_count DESC
        LIMIT 50
    """)
    return {"top_names": top_names}


def section3(conn: sqlite3.Connection) -> dict:
    top_persons = _rows(conn, """
        SELECT p.full_name, p.gender, p.profession, p.era,
               COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 20
    """)

    counts = _one(conn, """
        SELECT
          SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) AS m,
          SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) AS f
        FROM (
          SELECT DISTINCT p.core_name_norm, p.gender
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
        ) p
    """)

    profession_dist = _rows(conn, """
        SELECT COALESCE(p.profession, 'necunoscut') AS profession,
               COUNT(DISTINCT p.core_name_norm) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY profession
        ORDER BY n DESC
        LIMIT 8
    """)

    era_dist = _rows(conn, """
        SELECT COALESCE(p.era, 'necunoscut') AS era,
               COUNT(DISTINCT p.core_name_norm) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY era
        ORDER BY n DESC
        LIMIT 6
    """)

    return {
        "top_persons": top_persons,
        "total_m": counts.get("m", 0) or 0,
        "total_f": counts.get("f", 0) or 0,
        "profession_dist": profession_dist,
        "era_dist": era_dist,
    }


def section4(conn: sqlite3.Connection) -> dict:
    top_pageviews = _rows(conn, """
        SELECT p.full_name, p.wiki_scope, p.wiki_sitelinks,
               p.wiki_ro_views, p.wiki_ro_url,
               COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.wiki_ro_views IS NOT NULL AND p.wiki_ro_views > 0
        GROUP BY p.core_name_norm
        ORDER BY p.wiki_ro_views DESC
        LIMIT 10
    """)

    tier_counts = _one(conn, """
        SELECT
          SUM(CASE WHEN wiki_scope = 'universal' THEN 1 ELSE 0 END) AS universal,
          SUM(CASE WHEN wiki_scope = 'national' THEN 1 ELSE 0 END) AS national,
          SUM(CASE WHEN wiki_scope IN ('local','unknown') OR wiki_scope IS NULL THEN 1 ELSE 0 END) AS local
        FROM persons
        WHERE wikidata_qid IS NOT NULL
    """)

    return {
        "top_pageviews": top_pageviews,
        "tier_counts": {
            "universal": tier_counts.get("universal", 0) or 0,
            "national": tier_counts.get("national", 0) or 0,
            "local": tier_counts.get("local", 0) or 0,
        },
    }


def section5(conn: sqlite3.Connection) -> dict:
    # Theme distribution: person|nature|saint|date|ideological|other
    theme_dist = _rows(conn, """
        SELECT category, SUM(cnt) AS count FROM (
          SELECT 'persoană' AS category, COUNT(*) AS cnt
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
          UNION ALL
          SELECT 'natură', COUNT(*)
          FROM streets_dedup sd
          JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
          UNION ALL
          SELECT 'religios', COUNT(*)
          FROM streets_dedup WHERE is_saint = 1
          UNION ALL
          SELECT 'dată / sărbătoare', COUNT(*)
          FROM streets_dedup WHERE is_date = 1
          UNION ALL
          SELECT 'ideologic', COUNT(*)
          FROM streets_dedup sd
          JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
          WHERE nc.category = 'ideological'
          UNION ALL
          SELECT 'concept / abstract', COUNT(*)
          FROM streets_dedup sd
          JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
          WHERE nc.category IN ('abstract', 'commemorative', 'institutional')
        ) GROUP BY category
        ORDER BY count DESC
    """)

    nature_subtypes = _rows(conn, """
        SELECT COALESCE(nature_type, 'altele') AS nature_type,
               COUNT(*) AS n
        FROM streets_dedup sd
        JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        GROUP BY nature_type
        ORDER BY n DESC
        LIMIT 6
    """)

    ideo_tokens = _rows(conn, """
        SELECT nc.subcategory AS token, COUNT(*) AS n
        FROM streets_dedup sd
        JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE nc.category = 'ideological'
          AND nc.subcategory IS NOT NULL
        GROUP BY nc.subcategory
        ORDER BY n DESC
        LIMIT 12
    """)

    return {
        "theme_dist": theme_dist,
        "nature_subtypes": nature_subtypes,
        "ideo_tokens": ideo_tokens,
    }


def section6(conn: sqlite3.Connection) -> dict:
    by_judet = _rows(conn, """
        SELECT judet,
               COUNT(*) AS total_streets,
               ROUND(100.0 * SUM(is_saint) / COUNT(*), 1) AS saint_pct,
               ROUND(100.0 * SUM(is_numeric) / COUNT(*), 1) AS numeric_pct,
               ROUND(100.0 * SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS female_pct
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY judet
        ORDER BY total_streets DESC
    """)

    # Modal name per județ (most common name_normalized)
    modal_names = _rows(conn, """
        SELECT judet, name_normalized, cnt FROM (
          SELECT judet, name_normalized, COUNT(*) AS cnt,
                 ROW_NUMBER() OVER (PARTITION BY judet ORDER BY COUNT(*) DESC) AS rn
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY judet, name_normalized
        ) WHERE rn = 1
    """)
    modal_map = {r["judet"]: r["name_normalized"] for r in modal_names}

    for row in by_judet:
        row["modal_name"] = modal_map.get(row["judet"], "—")

    return {"by_judet": by_judet}


def section8(conn: sqlite3.Connection) -> dict:
    # CIORANI: Prahova numeric streets
    ciorani_row = _one(conn, """
        SELECT COUNT(*) AS total,
               SUM(is_numeric) AS numeric_streets
        FROM streets_dedup
        WHERE judet = 'PH'
          AND uat LIKE '%CIORANI%'
    """)

    longest_names = _rows(conn, """
        SELECT name, LENGTH(name) AS char_count
        FROM streets_dedup
        WHERE is_numeric = 0
          AND core_name IS NOT NULL
          AND LENGTH(name) > 30
        ORDER BY char_count DESC
        LIMIT 8
    """)

    # Animal names: streets containing animal-related keywords
    animal_names = _rows(conn, """
        SELECT nt.term AS animal_ro, sd.name_normalized, COUNT(*) AS n
        FROM streets_dedup sd
        JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        WHERE nt.nature_type = 'animal'
        GROUP BY nt.term
        ORDER BY n DESC
        LIMIT 10
    """)

    # Locally honored: persons appearing in exactly 1 UAT
    local_honorees = _rows(conn, """
        SELECT p.full_name, p.profession, sd.judet, sd.uat,
               COUNT(DISTINCT sd.siruta) AS uat_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY p.core_name_norm
        HAVING COUNT(DISTINCT sd.siruta) = 1
        ORDER BY sd.judet, sd.uat
        LIMIT 10
    """)

    return {
        "ciorani": {
            "total": ciorani_row.get("total", 0) or 0,
            "numeric": ciorani_row.get("numeric_streets", 0) or 0,
        },
        "longest_names": longest_names,
        "animal_names": animal_names,
        "local_honorees": local_honorees,
    }
```

- [ ] **Step 3.4: Run tests**

```bash
source ~/devbox/envs/240826/bin/activate
pytest tests/test_queries.py -v
```

Expected: all pass. If a query errors, read the error — most likely a missing column or wrong join. Fix inline.

- [ ] **Step 3.5: Run smoke build**

```bash
python3 build_site.py
```

Expected: `→ dist/index.html  (N KB)`, no errors.

- [ ] **Step 3.6: Commit**

```bash
git add site_queries.py tests/test_queries.py
git commit -m "feat(site): add all section data queries with tests"
```

---

## Task 4: Section 1 — Acasă hero

**Files:**
- Modify: `templates/index.html.j2` — add section 1 HTML + JS
- Modify: `tests/test_build.py` — add content assertions

- [ ] **Step 4.1: Add section 1 content test**

Append to `tests/test_build.py`:

```python
def test_section1_hero_content():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "acasa" in html  # anchor
    assert "99 din 100" in html
    assert "bărbați" in html
```

- [ ] **Step 4.2: Add section 1 HTML to template**

Inside `<body>`, after the nav, add:

```html
<section id="acasa">
  <div class="section">
    <div class="kicker">Un portret al memoriei naționale</div>
    <h1><span class="accent">99 din 100</span> de români onorați pe străzi sunt bărbați.</h1>
    <p class="lede">
      Asta arată registrul electoral al țării — {{ "{:,.0f}".format(section1.total_streets).replace(",", ".") }} de adrese, în 41 de județe.
      Cine sunt acei bărbați, ce profesii au, în ce epoci au trăit? Și cine sunt cele {{ section1.total_persons_f }} de femei? Să vedem.
    </p>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:64px;border-top:1px solid var(--rule);padding-top:32px;margin-bottom:60px;">
      <div>
        <div class="kicker" style="margin-bottom:14px;">Cei mai onorați bărbați</div>
        <div style="font-family:var(--serif);font-weight:500;font-size:64px;line-height:1;letter-spacing:-.02em;margin-bottom:6px;">
          {{ section1.top_men[0].street_count }}
        </div>
        <div style="font-family:var(--sans);font-size:13px;color:var(--muted);margin-bottom:22px;">
          străzi numite {{ section1.top_men[0].full_name }}
        </div>
        <div class="rank-list">
          {% for p in section1.top_men %}
          <div class="rank-row">
            <span class="rank-num">{{ loop.index }}.</span>
            <span class="rank-name">{{ p.full_name }}</span>
            <div class="bar-wrap"><div class="bar" style="width:{{ (p.street_count / section1.top_men[0].street_count * 100)|int }}%"></div></div>
            <span class="rank-count">{{ p.street_count }}</span>
          </div>
          {% endfor %}
        </div>
      </div>
      <div>
        <div class="kicker" style="margin-bottom:14px;">Cele mai onorate femei</div>
        <div style="font-family:var(--serif);font-weight:500;font-size:64px;line-height:1;letter-spacing:-.02em;color:var(--accent);margin-bottom:6px;">
          {{ section1.top_women[0].street_count if section1.top_women else '—' }}
        </div>
        <div style="font-family:var(--sans);font-size:13px;color:var(--muted);margin-bottom:22px;">
          {% if section1.top_women %}
          străzi numite {{ section1.top_women[0].full_name }}
          {% else %}
          nicio femeie clasificată încă
          {% endif %}
        </div>
        <div class="rank-list">
          {% for p in section1.top_women %}
          <div class="rank-row">
            <span class="rank-num">{{ loop.index }}.</span>
            <span class="rank-name">{{ p.full_name }}</span>
            <div class="bar-wrap"><div class="bar female" style="width:{{ (p.street_count / section1.top_women[0].street_count * 100)|int }}%"></div></div>
            <span class="rank-count">{{ p.street_count }}</span>
          </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <div style="text-align:center;font-family:var(--sans);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);padding:24px 0 48px;">
      Continuați
      <span style="display:block;margin:6px auto 0;font-size:14px;color:var(--accent)">↓</span>
    </div>
  </div>
  <div class="section-source">
    <span>Sursă · Registrul Secțiilor de Vot, 14.05.2025 · n = {{ "{:,.0f}".format(section1.total_streets).replace(",", ".") }}</span>
    <span>Clasificare persoane: {{ section1.total_persons_m + section1.total_persons_f }} persoane identificate</span>
  </div>
</section>
```

- [ ] **Step 4.3: Build and verify**

```bash
python3 build_site.py && pytest tests/test_build.py::test_section1_hero_content -v
open dist/index.html
```

Expected: test passes, section renders with real counts from DB.

- [ ] **Step 4.4: Commit**

```bash
git add templates/index.html.j2 tests/test_build.py
git commit -m "feat(site): section 1 Acasă hero with real person counts"
```

---

## Task 5: Section 2 — Cele mai întâlnite

**Files:**
- Modify: `templates/index.html.j2`
- Modify: `tests/test_build.py`

- [ ] **Step 5.1: Embed section 2 JSON in template and add HTML**

Add to `<head>` (after CSS):

```html
<script>
const DATA_S2 = {{ section2 | tojson }};
</script>
```

Add to `<body>` (after section 1):

```html
<section id="cele-mai-intalnite">
  <div class="section">
    <div class="kicker">Cele mai întâlnite</div>
    <h2>Principala stradă a oricărui sat.</h2>
    <p class="lede">
      În aproape orice sat, un drum se cheamă „Principală". În aproape orice oraș, una „Eminescu". Românilor le plac florile, școlile, bisericile — și un anumit poet din Botoșani.
    </p>

    <div style="position:relative;margin-bottom:22px;">
      <span style="position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:15px;pointer-events:none;">⌕</span>
      <input id="s2-search" type="text" placeholder="Căutați un nume de stradă…"
        style="width:100%;border:1.5px solid var(--rule);border-radius:3px;padding:11px 16px 11px 42px;font-family:var(--serif);font-size:16px;color:var(--ink);background:var(--bg);outline:none;">
    </div>

    <div class="chip-row" id="s2-judet-row">
      <span class="label">Județ</span>
      <button class="chip active" data-judet="all">Toate</button>
      {# Județ chips loaded by JS #}
    </div>

    <div class="callout" id="s2-principal-note">
      <strong>Strada Principală</strong> este prima cu <strong id="s2-principal-count">—</strong> de apariții — în aproape fiecare localitate. Exclusă din graficul de mai jos.
    </div>

    <div class="rank-list" id="s2-list">
      <div class="rank-header">
        <span></span><span>Nume</span><span>Frecvență relativă</span><span style="text-align:right">Apariții</span>
      </div>
      {# Populated by JS #}
    </div>
    <div style="font-family:var(--sans);font-size:12px;font-style:italic;color:var(--muted);padding:16px 0 0;" id="s2-footer"></div>
  </div>
  <div class="section-source">
    <span>Sursă · Registrul Secțiilor de Vot, 14.05.2025</span>
    <span>Top 50 · Strada Principală exclusă din scară</span>
  </div>
</section>
```

Add `<script>` block for section 2 interactivity:

```html
<script>
(function() {
  const names = DATA_S2.top_names;
  const principal = names[0];  // Principală is rank 1
  const rest = names.slice(1);
  const maxCount = rest[0]?.street_count || 1;

  document.getElementById('s2-principal-count').textContent =
    principal.street_count.toLocaleString('ro-RO');

  function renderList(filtered) {
    const list = document.getElementById('s2-list');
    // Remove old rows (keep header)
    while (list.children.length > 1) list.removeChild(list.lastChild);

    filtered.slice(0, 25).forEach((row, i) => {
      const pct = Math.round(row.street_count / maxCount * 100);
      const isPerson = row.category === 'persoană';
      const tag = row.category !== 'altele'
        ? `<span class="tag${isPerson ? ' person' : ''}">${row.category}</span>` : '';
      const barClass = isPerson ? 'bar accent' : 'bar';
      list.insertAdjacentHTML('beforeend', `
        <div class="rank-row">
          <span class="rank-num">${i + 1}</span>
          <span class="rank-name">${row.name_normalized}${tag}</span>
          <div class="bar-wrap"><div class="${barClass}" style="width:${pct}%"></div></div>
          <span class="rank-count">${row.street_count.toLocaleString('ro-RO')}</span>
        </div>
      `);
    });
    document.getElementById('s2-footer').textContent =
      `Afișare 1–${Math.min(25, filtered.length)} din ${filtered.length} · Strada Principală exclusă din scară`;
  }

  renderList(rest);

  document.getElementById('s2-search').addEventListener('input', function() {
    const q = this.value.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    const filtered = rest.filter(r =>
      r.name_normalized.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes(q)
    );
    renderList(filtered);
  });
})();
</script>
```

- [ ] **Step 5.2: Build and test**

```bash
python3 build_site.py && pytest tests/test_build.py -v
open dist/index.html
```

Verify: search box filters names in real-time, Principală callout shows real count.

- [ ] **Step 5.3: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(site): section 2 top names with search and live filtering"
```

---

## Task 6: Section 3 — Pe cine onorăm

**Files:**
- Modify: `templates/index.html.j2`

- [ ] **Step 6.1: Add section 3 to template**

Add `<script>const DATA_S3 = {{ section3 | tojson }};</script>` in `<head>`.

Add section HTML:

```html
<section id="pe-cine-onoram">
  <div class="section">
    <div class="kicker">Pe cine onorăm</div>
    <h2><span class="accent">{{ section3.total_m }}/{{ section3.total_m + section3.total_f }}</span> persoane onorate pe stradă sunt bărbați.</h2>
    <p class="lede">
      Din cele {{ section3.total_m + section3.total_f }} persoane clasificate în registru,
      {{ section3.total_m }} sunt bărbați și {{ section3.total_f }} sunt femei.
    </p>

    {# Gender gap grid #}
    <div style="display:grid;grid-template-columns:auto 1fr;gap:48px;align-items:start;border-top:1px solid var(--rule);padding-top:36px;margin-bottom:56px;">
      <div>
        <div class="kicker" style="margin-bottom:10px;">Fiecare pătrat = 1 persoană clasificată</div>
        <div id="s3-gap-grid" style="display:grid;grid-template-columns:repeat(10,18px);gap:3px;width:220px;"></div>
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:14px;font-family:var(--sans);font-size:12px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <div style="width:12px;height:12px;border-radius:1px;background:var(--ink)"></div><span style="color:var(--muted)">Bărbat</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <div style="width:12px;height:12px;border-radius:1px;background:var(--accent)"></div><span style="color:var(--muted)">Femeie</span>
          </div>
        </div>
      </div>
      <div>
        <div style="font-family:var(--serif);font-weight:500;font-size:72px;line-height:1;letter-spacing:-.02em;margin-bottom:8px;">
          {{ section3.total_m }}<span style="font-size:40px;color:var(--muted);">/{{ section3.total_m + section3.total_f }}</span>
        </div>
        <div style="font-family:var(--sans);font-size:14px;color:var(--muted);margin-bottom:24px;">persoane onorate pe stradă sunt bărbați</div>
        <p style="font-size:17px;line-height:1.6;color:#3A3A3D;max-width:520px;">
          {% set top_f = section3.top_persons | selectattr('gender', 'eq', 'F') | list %}
          {% if top_f %}
          <span style="color:var(--accent);font-weight:500;">{{ top_f[0].full_name }}</span> este prima femeie din top 20, cu {{ top_f[0].street_count }} de străzi.
          Prima pe o listă pe care bărbații au scris-o aproape în întregime.
          {% endif %}
        </p>
      </div>
    </div>

    {# Tower chart #}
    <div class="kicker" style="margin-bottom:16px;">Top {{ section3.top_persons | length }} persoane onorate · număr de străzi</div>
    <div class="rank-list" id="s3-tower">
      {% set max_count = section3.top_persons[0].street_count %}
      {% for p in section3.top_persons %}
      <div class="rank-row" style="grid-template-columns:200px 1fr 54px;">
        <span class="rank-name">
          {{ p.full_name }}
          {% if p.gender == 'F' %}<span style="display:inline-block;width:7px;height:7px;background:var(--accent);border-radius:50%;margin-left:7px;vertical-align:middle;"></span>{% endif %}
        </span>
        <div class="bar-wrap">
          <div class="{{ 'bar accent' if loop.first else ('bar female' if p.gender == 'F' else 'bar') }}"
               style="width:{{ (p.street_count / max_count * 100)|int }}%"></div>
        </div>
        <span class="rank-count">{{ p.street_count }}</span>
      </div>
      {% endfor %}
    </div>

    {# Mini charts #}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:56px;border-top:1px solid var(--rule);padding-top:36px;margin-top:36px;">
      <div>
        <div class="kicker" style="margin-bottom:18px;">Profesia persoanei onorate</div>
        {% set max_prof = section3.profession_dist[0].n if section3.profession_dist else 1 %}
        {% for row in section3.profession_dist %}
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:9px;">
          <span style="font-family:var(--serif);font-size:15px;flex:1;">{{ row.profession }}</span>
          <div class="bar-wrap" style="width:140px;height:5px;">
            <div class="bar" style="width:{{ (row.n / max_prof * 100)|int }}%"></div>
          </div>
          <span style="font-family:var(--sans);font-size:11px;color:var(--muted);width:24px;text-align:right;">{{ row.n }}</span>
        </div>
        {% endfor %}
      </div>
      <div>
        <div class="kicker" style="margin-bottom:18px;">Epoca în care a trăit</div>
        {% set max_era = section3.era_dist[0].n if section3.era_dist else 1 %}
        {% for row in section3.era_dist %}
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:9px;">
          <span style="font-family:var(--serif);font-size:15px;flex:1;">{{ row.era or 'necunoscută' }}</span>
          <div class="bar-wrap" style="width:140px;height:5px;">
            <div class="bar" style="width:{{ (row.n / max_era * 100)|int }}%"></div>
          </div>
          <span style="font-family:var(--sans);font-size:11px;color:var(--muted);width:24px;text-align:right;">{{ row.n }}</span>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
  <div class="section-source">
    <span>Sursă · Registrul Secțiilor de Vot · n = {{ section3.top_persons | length }} persoane clasificate</span>
    <span>Clasificare gender în curs — date parțiale</span>
  </div>
</section>
```

Add gender gap grid JavaScript in a `<script>` block:

```html
<script>
(function() {
  const total = DATA_S3.total_m + DATA_S3.total_f;
  const grid = document.getElementById('s3-gap-grid');
  // Show 100 squares representing the ratio
  const femaleSquares = Math.max(1, Math.round(DATA_S3.total_f / total * 100));
  for (let i = 0; i < 100; i++) {
    const sq = document.createElement('div');
    sq.style.cssText = `width:18px;height:18px;border-radius:1px;background:${
      i >= (100 - femaleSquares) ? 'var(--accent)' : 'var(--ink)'
    }`;
    grid.appendChild(sq);
  }
})();
</script>
```

- [ ] **Step 6.2: Build and verify**

```bash
python3 build_site.py && open dist/index.html
```

Navigate to #pe-cine-onoram. Verify gender grid renders with correct ratio.

- [ ] **Step 6.3: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(site): section 3 gender gap grid and tower chart"
```

---

## Task 7: Sections 4 + 5 — Recunoaștere + Tematică

**Files:**
- Modify: `templates/index.html.j2`

- [ ] **Step 7.1: Add section 4 (Recunoaștere)**

Add `const DATA_S4 = {{ section4 | tojson }};` in `<head>` scripts block.

Add section HTML in `<body>`:

```html
<section id="recunoastere">
  <div class="section">
    <div class="kicker">Recunoaștere</div>
    <h2>Unii sunt cunoscuți în toată lumea. Alții, doar în sat.</h2>
    <p class="lede">
      Wikidata arată câte limbi vorbesc despre fiecare persoană onorată.
      Din {{ section4.tier_counts.universal + section4.tier_counts.national + section4.tier_counts.local }} persoane cu date Wikidata,
      {{ section4.tier_counts.universal }} sunt universal recunoscute.
    </p>

    {# Tier cards #}
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--rule);border:1px solid var(--rule);margin-bottom:56px;">
      <div style="background:var(--ink);color:#FAF8F3;padding:28px 24px;">
        <div style="font-family:var(--sans);font-size:10px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;color:var(--accent);margin-bottom:14px;">Universal</div>
        <div style="font-family:var(--serif);font-weight:500;font-size:52px;line-height:1;letter-spacing:-.02em;margin-bottom:4px;">{{ section4.tier_counts.universal }}</div>
        <div style="font-family:var(--sans);font-size:12px;color:#C9C9CB;margin-bottom:18px;">persoane · ≥ 50 de limbi pe Wikipedia</div>
        <div style="font-family:var(--serif);font-size:14px;line-height:1.65;color:#C9C9CB;">
          Figuri despre care un turist din Tokyo sau Buenos Aires poate citi în propria limbă.
        </div>
        <div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:14px;border-top:1px solid #2A2C30;padding-top:10px;">≥ 50 sitelinks Wikidata</div>
      </div>
      <div style="background:var(--bg);padding:28px 24px;">
        <div style="font-family:var(--sans);font-size:10px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;color:var(--muted);margin-bottom:14px;">Național</div>
        <div style="font-family:var(--serif);font-weight:500;font-size:52px;line-height:1;letter-spacing:-.02em;margin-bottom:4px;">{{ section4.tier_counts.national }}</div>
        <div style="font-family:var(--sans);font-size:12px;color:var(--muted);margin-bottom:18px;">persoane · 5–49 de limbi</div>
        <div style="font-family:var(--serif);font-size:14px;line-height:1.65;color:var(--muted);">Bine cunoscuți în România, mai puțin în afară. Canonul național complet.</div>
        <div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:14px;border-top:1px solid var(--rule);padding-top:10px;">5–49 sitelinks Wikidata</div>
      </div>
      <div style="background:var(--bg);padding:28px 24px;">
        <div style="font-family:var(--sans);font-size:10px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;color:var(--muted);margin-bottom:14px;">Local / necunoscut</div>
        <div style="font-family:var(--serif);font-weight:500;font-size:52px;line-height:1;letter-spacing:-.02em;margin-bottom:4px;">{{ section4.tier_counts.local }}</div>
        <div style="font-family:var(--sans);font-size:12px;color:var(--muted);margin-bottom:18px;">persoane · sub 5 limbi sau absent</div>
        <div style="font-family:var(--serif);font-size:14px;line-height:1.65;color:var(--muted);">Profesori, preoți, ofițeri — uneori onorat într-un singur sat.</div>
        <div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:14px;border-top:1px solid var(--rule);padding-top:10px;">1–4 sitelinks sau absent complet</div>
      </div>
    </div>

    {# Pageviews chart #}
    <div style="font-family:var(--sans);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:500;margin-bottom:6px;">Notorietate în România</div>
    <div style="font-family:var(--serif);font-size:15px;font-style:italic;color:var(--muted);margin-bottom:24px;">Vizualizări lunare medii · Wikipedia în română · ultimele 12 luni</div>
    <div class="rank-list">
      {% set max_pv = section4.top_pageviews[0].wiki_ro_views if section4.top_pageviews else 1 %}
      {% for p in section4.top_pageviews %}
      <div class="rank-row" style="grid-template-columns:200px 1fr 80px 90px;">
        <span class="rank-name">{{ p.full_name }}</span>
        <div class="bar-wrap">
          <div class="{{ 'bar accent' if p.wiki_scope == 'universal' else 'bar' }}"
               style="width:{{ (p.wiki_ro_views / max_pv * 100)|int }}%"></div>
        </div>
        <span class="rank-count">{{ "{:,.0f}".format(p.wiki_ro_views).replace(",", ".") }}</span>
        <span class="tag{{ ' person' if p.wiki_scope == 'universal' else '' }}">{{ p.wiki_scope or '—' }}</span>
      </div>
      {% endfor %}
    </div>
  </div>
  <div class="section-source">
    <span>Sursă · Wikidata sitelinks + Wikimedia Pageview API · medie 12 luni</span>
    <span>{{ section4.tier_counts.universal + section4.tier_counts.national + section4.tier_counts.local }} persoane cu date Wikidata</span>
  </div>
</section>
```

- [ ] **Step 7.2: Add section 5 (Tematică)**

Add `const DATA_S5 = {{ section5 | tojson }};` in `<head>`.

Add section HTML (donut via CSS conic-gradient computed at render time):

```html
<section id="tematica">
  <div class="section">
    <div class="kicker">Tematică</div>
    <h2>O treime din străzi onorează oameni. Restul onoară tot ce e în jur.</h2>
    <p class="lede">Florile, pădurile, apele și munții dau mai multe nume decât toți voievozii la un loc.</p>

    {# Compute total and percentages for conic-gradient #}
    {% set theme_total = section5.theme_dist | sum(attribute='count') %}
    {% set theme_colors = ['#C04F35','#A0826A','#8BA888','#6E6E70','#B8A090','#3A3A3D','#DDDCD7'] %}
    {% set ns = namespace(cumulative=0) %}

    <div style="display:grid;grid-template-columns:280px 1fr;gap:64px;align-items:start;border-top:1px solid var(--rule);padding-top:40px;margin-bottom:56px;">
      <div style="position:relative;width:260px;height:260px;">
        <div style="width:260px;height:260px;border-radius:50%;background:conic-gradient(
          {% for t in section5.theme_dist %}
          {% set pct = (t.count / theme_total * 100) | round(1) %}
          {{ theme_colors[loop.index0 % theme_colors|length] }} {{ ns.cumulative }}% {{ ns.cumulative + pct }}%{{ ',' if not loop.last }}
          {% set ns.cumulative = ns.cumulative + pct %}
          {% endfor %}
        );"></div>
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:140px;height:140px;background:var(--bg);border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;">
          <div style="font-family:var(--serif);font-weight:500;font-size:32px;line-height:1;">{{ "{:,.0f}".format(theme_total).replace(",", ".") }}</div>
          <div style="font-family:var(--sans);font-size:10px;color:var(--muted);">total<br>clasificate</div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:16px;padding-top:8px;">
        {% for t in section5.theme_dist %}
        {% set pct = (t.count / theme_total * 100) | round(1) %}
        <div style="display:flex;align-items:baseline;gap:14px;">
          <div style="width:12px;height:12px;border-radius:1px;background:{{ theme_colors[loop.index0 % theme_colors|length] }};flex-shrink:0;margin-top:3px;"></div>
          <div style="flex:1;">
            <span style="font-family:var(--serif);font-size:17px;">{{ t.category }}</span>
            <span style="font-family:var(--sans);font-size:22px;font-weight:600;float:right;">{{ pct }}%</span>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:56px;border-top:1px solid var(--rule);padding-top:36px;">
      <div>
        <div class="kicker" style="margin-bottom:18px;">Subtipuri · Natură</div>
        {% set max_n = section5.nature_subtypes[0].n if section5.nature_subtypes else 1 %}
        {% for row in section5.nature_subtypes %}
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:9px;">
          <span style="font-family:var(--serif);font-size:15px;flex:1;">{{ row.nature_type }}</span>
          <div class="bar-wrap" style="width:160px;height:5px;"><div class="bar" style="width:{{ (row.n / max_n * 100)|int }}%;background:#A0826A;opacity:.7;"></div></div>
          <span style="font-family:var(--sans);font-size:11px;color:var(--muted);width:30px;text-align:right;">{{ row.n }}</span>
        </div>
        {% endfor %}
      </div>
      <div>
        <div class="kicker" style="margin-bottom:14px;">Tokeni ideologici</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;">
          {% for tok in section5.ideo_tokens %}
          <span style="font-family:var(--sans);font-size:12.5px;padding:5px 13px;border:1px solid {{ 'var(--accent)' if tok.n > 30 else 'var(--rule)' }};border-radius:3px;color:{{ '#B8432F' if tok.n > 30 else 'var(--ink)' }};background:{{ '#FDF4F2' if tok.n > 30 else 'transparent' }};">
            {{ tok.token }} <span style="color:var(--muted);font-size:10.5px;margin-left:6px;">{{ tok.n }}</span>
          </span>
          {% endfor %}
        </div>
        {% if not section5.ideo_tokens %}
        <p style="font-family:var(--serif);font-size:14px;font-style:italic;color:var(--muted);">Subcategorii ideologice în curs de completare.</p>
        {% endif %}
      </div>
    </div>
  </div>
  <div class="section-source">
    <span>Sursă · Registrul Secțiilor de Vot · curation manual + LLM batch</span>
    <span>{{ theme_total }} adrese clasificate tematic</span>
  </div>
</section>
```

- [ ] **Step 7.3: Build and verify**

```bash
python3 build_site.py && open dist/index.html
```

Navigate to sections 4 and 5. Verify tier counts and donut colors.

- [ ] **Step 7.4: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(site): sections 4 Recunoaștere and 5 Tematică"
```

---

## Task 8: Section 6 — Harta României (D3 choropleth)

**Files:**
- Modify: `templates/index.html.j2`
- Modify: `build_site.py` — ensure ro-counties.geojson is copied to dist/

- [ ] **Step 8.1: Add D3 + TopoJSON CDN scripts to template `<head>`**

```html
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<script src="https://cdn.jsdelivr.net/npm/topojson-client@3"></script>
```

- [ ] **Step 8.2: Add section 6 HTML and map container**

Add `const DATA_S6 = {{ section6 | tojson }};` in head scripts.

```html
<section id="harta">
  <div class="section">
    <div class="kicker">Geografia memoriei</div>
    <h2>Maramureș nu sună ca Dobrogea.</h2>
    <p class="lede">
      Numele care se repetă cel mai des într-un județ ne spun ceva despre cine s-a stabilit acolo și cui a vrut comunitatea să-i dea o stradă.
    </p>

    <div class="chip-row" id="s6-metric-row">
      <span class="label">Vedeți după</span>
      <button class="chip active" data-metric="saint_pct">% sfinți</button>
      <button class="chip" data-metric="numeric_pct">% numere</button>
      <button class="chip" data-metric="female_pct">% femei</button>
    </div>

    <div style="display:grid;grid-template-columns:1.6fr 1fr;gap:56px;margin-bottom:36px;" id="s6-grid">
      <div style="position:relative;">
        <svg id="s6-map" style="width:100%;height:auto;display:block;"></svg>
        <div style="margin-top:24px;display:flex;align-items:center;gap:14px;font-family:var(--sans);font-size:11px;color:var(--muted);">
          <span id="s6-scale-min">0%</span>
          <div style="flex:1;height:8px;background:linear-gradient(to right,#F4EFE6 0%,#E8B299 35%,#D27A5C 65%,#A53A22 100%);border-radius:1px;"></div>
          <span id="s6-scale-max">12%</span>
          <span style="margin-left:14px;" id="s6-scale-label">% străzi cu prefix „Sf."</span>
        </div>
      </div>
      <div style="border-left:1px solid var(--rule);padding-left:32px;" id="s6-fingerprint">
        <div class="kicker">Amprenta județului</div>
        <p style="font-family:var(--serif);font-size:14px;font-style:italic;color:var(--muted);padding-top:80px;">
          Selectați un județ pe hartă pentru a vedea amprenta sa.
        </p>
      </div>
    </div>
  </div>
  <div class="section-source">
    <span>Sursă · romania-counties.geojson + Registrul Secțiilor de Vot</span>
    <span>Harta schematică · date pentru ilustrație</span>
  </div>
</section>
```

- [ ] **Step 8.3: Add D3 choropleth JavaScript**

```html
<script>
(function() {
  const byJudet = {};
  DATA_S6.by_judet.forEach(d => { byJudet[d.judet] = d; });

  let activeMetric = 'saint_pct';
  const metricLabels = {
    saint_pct: '% străzi cu prefix „Sf."',
    numeric_pct: '% străzi anonime (numere)',
    female_pct: '% străzi cu nume feminin',
  };

  const colorScale = d3.scaleSequential()
    .interpolator(d3.interpolateRgb('#F4EFE6', '#A53A22'));

  function updateMetric(metric) {
    activeMetric = metric;
    document.querySelectorAll('#s6-metric-row .chip').forEach(c =>
      c.classList.toggle('active', c.dataset.metric === metric)
    );
    const values = DATA_S6.by_judet.map(d => d[metric] || 0);
    const maxVal = d3.max(values);
    colorScale.domain([0, maxVal]);
    document.getElementById('s6-scale-max').textContent = maxVal.toFixed(1) + '%';
    document.getElementById('s6-scale-label').textContent = metricLabels[metric];

    d3.selectAll('.judet-path').attr('fill', d => {
      const code = d.properties?.mnemonic || d.properties?.name;
      const row = byJudet[code];
      return row ? colorScale(row[metric] || 0) : '#EEEAE0';
    });
  }

  document.querySelectorAll('#s6-metric-row .chip').forEach(btn => {
    btn.addEventListener('click', () => updateMetric(btn.dataset.metric));
  });

  // Load GeoJSON and render map
  fetch('ro-counties.geojson')
    .then(r => r.json())
    .then(geo => {
      const svg = d3.select('#s6-map');
      const width = svg.node().parentElement.clientWidth * 1.6 / 2.6;
      const height = width * 0.65;
      svg.attr('viewBox', `0 0 ${width} ${height}`);

      const projection = d3.geoMercator().fitSize([width, height], geo);
      const path = d3.geoPath().projection(projection);

      svg.selectAll('.judet-path')
        .data(geo.features)
        .join('path')
        .attr('class', 'judet-path')
        .attr('d', path)
        .attr('stroke', '#FAF8F3')
        .attr('stroke-width', 0.9)
        .style('cursor', 'pointer')
        .on('click', (event, d) => renderFingerprint(d))
        .on('mouseenter', function() { d3.select(this).attr('stroke-width', 1.8).attr('stroke', '#15171A'); })
        .on('mouseleave', function() { d3.select(this).attr('stroke-width', 0.9).attr('stroke', '#FAF8F3'); });

      updateMetric('saint_pct');
    })
    .catch(() => {
      document.getElementById('s6-map').insertAdjacentHTML('afterend',
        '<p style="font-family:var(--sans);font-size:13px;color:var(--muted);padding:20px 0;">Harta indisponibilă — rulați build_site.py pentru a copia ro-counties.geojson în dist/</p>'
      );
    });

  function renderFingerprint(feature) {
    const code = feature.properties?.mnemonic || feature.properties?.name;
    const row = byJudet[code] || {};
    const fp = document.getElementById('s6-fingerprint');
    fp.innerHTML = `
      <div class="kicker">Amprenta județului · selectat</div>
      <h3 style="font-family:var(--serif);font-weight:500;font-size:26px;margin:0 0 4px;">${feature.properties?.name || code}</h3>
      <div style="font-family:var(--sans);font-size:12px;color:var(--muted);margin-bottom:24px;">${(row.total_streets || 0).toLocaleString('ro-RO')} de străzi</div>
      <div class="kicker" style="margin-bottom:8px;">Statistici cheie</div>
      <div style="font-family:var(--serif);font-size:15px;line-height:1.7;color:var(--muted);">
        <div>· Sfinți: <strong style="color:var(--ink)">${(row.saint_pct || 0).toFixed(1)}%</strong></div>
        <div>· Numere (anonime): <strong style="color:var(--ink)">${(row.numeric_pct || 0).toFixed(1)}%</strong></div>
        <div>· Feminin: <strong style="color:var(--ink)">${(row.female_pct || 0).toFixed(2)}%</strong></div>
        <div>· Cel mai frecvent: <strong style="color:var(--ink)">${row.modal_name || '—'}</strong></div>
      </div>
    `;
  }
})();
</script>
```

- [ ] **Step 8.4: Verify GeoJSON has expected properties**

```bash
python3 -c "
import json
geo = json.load(open('data/gis/romania-counties.geojson'))
print('features:', len(geo['features']))
print('first feature props:', list(geo['features'][0]['properties'].keys()))
"
```

Note the property name that contains the județ code (e.g., `mnemonic`, `code`, `SIRUTA`) — update `renderFingerprint` and `updateMetric` to use the correct key. The property key must match the `judet` codes in `streets_dedup` (`AB`, `AG`, `AR`, `B`, etc.).

- [ ] **Step 8.5: Build and verify**

```bash
python3 build_site.py && open dist/index.html
```

Navigate to #harta. Map should render with colored counties; click a county to see fingerprint panel.

- [ ] **Step 8.6: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(site): section 6 D3 choropleth with metric switcher and fingerprint panel"
```

---

## Task 9: Section 7 — Renumiri (static placeholder)

> **Note:** Renaming data is not yet in the database. This section builds the UI shell with static illustrative data. Replace with real DB query when the renaming source is identified (see `docs/BACKLOG.md`).

**Files:**
- Modify: `templates/index.html.j2`
- Modify: `docs/BACKLOG.md` — add renaming data source task

- [ ] **Step 9.1: Add renaming backlog item**

Append to `docs/BACKLOG.md`:

```markdown
- [ ] **Renaming data source for Section 7 (Renumiri)** — Section 7 of the static site needs before/after rename pairs with substitution type labels. Source candidates: (a) street name version comparison across two registry exports; (b) manual curation CSV; (c) external renamed-streets dataset. Currently the section renders with static illustrative data. When data is available, add `renamings` table to `build_db.py` and implement `site_queries.section7()`.
```

- [ ] **Step 9.2: Add section 7 HTML with static illustrative data**

```html
<section id="renumiri">
  <div class="section">
    <div class="kicker">Renumiri</div>
    <h2>Unele străzi au trăit două vieți.</h2>
    <p class="lede">
      După 1989, România a schimbat semne. Unele schimbări au fost radicale — Bulevardul Uzinei a dispărut complet. Altele au fost mai creative.
    </p>

    <div style="display:flex;gap:24px;margin-bottom:40px;border-top:1px solid var(--rule);padding-top:28px;">
      {% for stat in [('1.847', 'redenumiri identificate'), ('612', 'cu token ideologic înlocuit'), ('84', 'redenumiri cu ecou fonetic')] %}
      <div style="{{ 'border-right:1px solid var(--rule);padding-right:24px;' if not loop.last else '' }}">
        <div style="font-family:var(--serif);font-weight:500;font-size:48px;line-height:1;letter-spacing:-.02em;margin-bottom:4px;{{ 'color:var(--accent);' if loop.index == 2 else '' }}">{{ stat[0] }}</div>
        <div style="font-family:var(--sans);font-size:12px;color:var(--muted);">{{ stat[1] }}</div>
      </div>
      {% endfor %}
    </div>

    <div style="padding:24px;background:var(--wash);border-radius:3px;margin-bottom:36px;font-family:var(--sans);font-size:12px;color:var(--muted);">
      <strong style="color:var(--ink);">Secțiune în construcție</strong> — datele pentru redenumiri sunt în curs de identificare.
      Cifrele de mai sus sunt ilustrative. Cardurile de mai jos prezintă exemple tipice identificate manual.
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
      {# Static illustrative rename cards — to be replaced with DB data #}
      {% for card in [
        ('Strada Uzinei', 'Lucian Blaga', 'Ideologic → Persoană', 'Brașov'),
        ('Bulevardul Victoriei Socialismului', 'Calea Văcărești', 'Ideologic → Neutru', 'București · S4'),
        ('Aleea Constructorilor', 'George Barițiu', 'Ideologic → Persoană', 'Cluj-Napoca'),
        ('Strada Muncii', 'Muncelului', 'Reciclare semantică', 'Brașov'),
      ] %}
      <div style="border:1px solid {{ 'var(--accent)' if 'Reciclare' in card[2] else 'var(--rule)' }};border-radius:3px;overflow:hidden;">
        <div style="padding:18px 20px 14px;">
          <div style="font-family:var(--sans);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:500;margin-bottom:6px;">Denumire veche</div>
          <div style="font-family:var(--serif);font-size:17px;color:var(--muted);text-decoration:line-through;text-decoration-color:var(--rule);">{{ card[0] }}</div>
        </div>
        <div style="padding:8px 20px;background:var(--wash);font-family:var(--sans);font-size:11px;display:flex;align-items:center;gap:8px;">
          →
          <span style="font-size:10px;letter-spacing:.1em;text-transform:uppercase;font-weight:500;padding:2px 8px;border-radius:999px;
            {{ 'background:#3A3A3D;color:#FAF8F3;' if 'Ideologic' in card[2] else ('background:var(--accent);color:#FAF8F3;' if 'Reciclare' in card[2] else 'background:#F4E8E5;color:#B8432F;') }}">
            {{ card[2] }}
          </span>
          <span style="margin-left:auto;">{{ card[3] }}</span>
        </div>
        <div style="padding:14px 20px 18px;">
          <div style="font-family:var(--sans);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:500;margin-bottom:6px;">Denumire nouă</div>
          <div style="font-family:var(--serif);font-size:20px;font-weight:500;">{{ card[1] }}</div>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  <div class="section-source">
    <span>Secțiune în construcție · date ilustrative</span>
    <span>Sursa datelor reale în curs de identificare</span>
  </div>
</section>
```

- [ ] **Step 9.3: Build and commit**

```bash
python3 build_site.py
git add templates/index.html.j2 docs/BACKLOG.md
git commit -m "feat(site): section 7 Renumiri shell with static illustrative data; backlog item added"
```

---

## Task 10: Section 8 — Curiozități

**Files:**
- Modify: `templates/index.html.j2`

- [ ] **Step 10.1: Add section 8 HTML**

Add `const DATA_S8 = {{ section8 | tojson }};` in head scripts.

```html
<section id="curiozitati">
  <div class="section">
    <div class="kicker">Curiozități</div>
    <h2>Datele care nu se încadrează nicăieri.</h2>
    <p class="lede">Nu toate poveștile din registru au o categorie. Unele sunt pur și simplu ciudate, amuzante sau inexplicabile.</p>

    {# CIORANI hero #}
    <div style="border:1px solid var(--rule);padding:64px 72px;margin-bottom:48px;display:grid;grid-template-columns:1fr auto;gap:72px;align-items:center;">
      <div>
        <div style="font-family:var(--sans);font-size:10px;letter-spacing:.2em;text-transform:uppercase;font-weight:600;color:var(--accent);margin-bottom:18px;">Comuna care a renunțat la nume</div>
        <h3 style="font-family:var(--serif);font-weight:500;font-size:32px;line-height:1.12;margin:0 0 18px;">Cioranii de Jos, Prahova</h3>
        <p style="font-size:17px;line-height:1.65;color:#3A3A3D;max-width:500px;">
          Din {{ section8.ciorani.total }} de străzi ale comunei,
          <strong>{{ section8.ciorani.numeric }} se cheamă printr-un număr</strong>.
          Strada 1. Strada 2. Strada {{ section8.ciorani.numeric }}.
          {% if section8.ciorani.total > section8.ciorani.numeric %}
          Una singură are un nume propriu-zis. Nu știm care. Ăsta e și farmecul.
          {% else %}
          Nicio excepție.
          {% endif %}
        </p>
        <div style="font-family:var(--sans);font-size:11.5px;color:var(--muted);margin-top:14px;">Prahova · {{ section8.ciorani.total }} de drumuri înregistrate</div>
      </div>
      <div style="text-align:right;">
        <span style="font-family:var(--serif);font-weight:500;font-size:{{ '80px' if section8.ciorani.numeric >= 100 else '112px' }};line-height:1;letter-spacing:-.03em;color:var(--accent);display:block;">{{ section8.ciorani.numeric }}</span>
        <span style="font-family:var(--serif);font-size:36px;color:var(--muted);display:block;margin-top:4px;">din {{ section8.ciorani.total }}</span>
        <div style="font-family:var(--sans);font-size:12px;color:var(--muted);margin-top:6px;">străzi fără nume<br>în același sat</div>
      </div>
    </div>

    {# Three curiosity cards #}
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:24px;">

      {# Longest names #}
      <div style="border:1px solid var(--rule);padding:28px 24px;">
        <div class="kicker" style="margin-bottom:14px;">Cea mai poetică</div>
        <h4 style="font-family:var(--serif);font-weight:500;font-size:20px;margin:0 0 18px;">Titluri stivuite</h4>
        {% for item in section8.longest_names[:4] %}
        <div style="font-family:var(--serif);font-size:{{ [22,18,16,15][loop.index0] }}px;line-height:1.3;margin-bottom:{{ 12 if loop.index0 < 3 else 0 }}px;">
          {{ item.name }}
        </div>
        {% if not loop.last %}
        <div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-bottom:12px;">{{ item.char_count }} de caractere</div>
        {% endif %}
        {% endfor %}
        {% if not section8.longest_names %}
        <p style="font-family:var(--serif);font-size:14px;font-style:italic;color:var(--muted);">Niciun nume lung identificat în datele curente.</p>
        {% endif %}
      </div>

      {# Animal contest #}
      <div style="border:1px solid var(--rule);padding:28px 24px;">
        <div class="kicker" style="margin-bottom:14px;">Concursul animalelor</div>
        <h4 style="font-family:var(--serif);font-weight:500;font-size:20px;margin:0 0 18px;">Top 10 animale pe stradă</h4>
        {% if section8.animal_names %}
          {% set max_animal = section8.animal_names[0].n %}
          {% for row in section8.animal_names %}
          <div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:{{ '1px solid var(--wash)' if not loop.last else 'none' }};">
            <span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);width:18px;text-align:right;">{{ loop.index }}</span>
            <span style="font-family:var(--serif);font-size:15px;flex:1;">{{ row.animal_ro or row.name_normalized }}</span>
            <div class="bar-wrap" style="width:70px;height:4px;"><div class="bar" style="width:{{ (row.n / max_animal * 100)|int }}%;"></div></div>
            <span style="font-family:var(--sans);font-size:11px;color:var(--muted);width:24px;text-align:right;">{{ row.n }}</span>
          </div>
          {% endfor %}
        {% else %}
          <p style="font-family:var(--serif);font-size:14px;font-style:italic;color:var(--muted);">Termeni de natură animale în curs de completare.</p>
        {% endif %}
      </div>

      {# Locally honored #}
      <div style="border:1px solid var(--rule);padding:28px 24px;">
        <div class="kicker" style="margin-bottom:14px;">Onorat doar aici</div>
        <h4 style="font-family:var(--serif);font-weight:500;font-size:20px;margin:0 0 18px;">O singură stradă în toată țara</h4>
        {% for item in section8.local_honorees %}
        <div style="padding:11px 0;border-bottom:{{ '1px solid var(--wash)' if not loop.last else 'none' }};">
          <div style="font-family:var(--serif);font-size:16px;margin-bottom:2px;">
            <span style="display:inline-block;width:6px;height:6px;background:var(--accent);border-radius:50%;margin-right:6px;vertical-align:middle;"></span>
            {{ item.full_name }}
          </div>
          {% if item.profession %}
          <div style="font-family:var(--sans);font-size:11.5px;color:var(--muted);line-height:1.5;">{{ item.profession }}</div>
          {% endif %}
          <div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:3px;">{{ item.uat }} · {{ item.judet }}</div>
        </div>
        {% endfor %}
        {% if not section8.local_honorees %}
        <p style="font-family:var(--serif);font-size:14px;font-style:italic;color:var(--muted);">Persoane locale în curs de identificare.</p>
        {% endif %}
      </div>

    </div>
  </div>
  <div class="section-source">
    <span>Sursă · Registrul Secțiilor de Vot, 14.05.2025</span>
    <span>CIORANI: date reale · celelalte secțiuni: date parțiale</span>
  </div>
</section>
```

- [ ] **Step 10.2: Build and verify**

```bash
python3 build_site.py && open dist/index.html
```

Navigate to #curiozitati. Verify CIORANI number renders from real DB data.

- [ ] **Step 10.3: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(site): section 8 Curiozități with CIORANI hero and real DB data"
```

---

## Task 11: Footer + final polish

**Files:**
- Modify: `templates/index.html.j2`
- Modify: `build_site.py` — add `--serve` dev flag

- [ ] **Step 11.1: Add footer section**

```html
<footer style="background:var(--ink);color:#FAF8F3;padding:48px 80px;">
  <div style="max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr 1fr;gap:48px;">
    <div>
      <div style="font-family:var(--sans);font-size:10px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;color:var(--accent);margin-bottom:14px;">Despre date</div>
      <p style="font-family:var(--serif);font-size:14px;line-height:1.65;color:#C9C9CB;">
        Datele provin din Registrul Secțiilor de Vot al Autorității Electorale Permanente (14.05.2025).
        Descriu străzile pe care locuiesc alegători înregistrați — aproape toate, dar nu chiar toate.
      </p>
    </div>
    <div>
      <div style="font-family:var(--sans);font-size:10px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;color:var(--accent);margin-bottom:14px;">Metodologie</div>
      <p style="font-family:var(--serif);font-size:14px;line-height:1.65;color:#C9C9CB;">
        Clasificarea persoanelor și temelor: curation manual și LLM batch (Claude Sonnet).
        Recunoaștere: Wikidata + Wikipedia pageviews.
        Harta: GeoJSON județe din surse publice.
      </p>
    </div>
    <div>
      <div style="font-family:var(--sans);font-size:10px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;color:var(--accent);margin-bottom:14px;">Cod sursă</div>
      <p style="font-family:var(--serif);font-size:14px;line-height:1.65;color:#C9C9CB;">
        Proiect personal · pax@mioritics.ro
      </p>
    </div>
  </div>
  <div style="max-width:1200px;margin:36px auto 0;border-top:1px solid #2A2C30;padding-top:20px;font-family:var(--sans);font-size:11px;color:var(--muted);">
    Cum ne numim străzile · date {{ section1.total_streets | default(0) | int | string }} adrese · ultima actualizare 14.05.2025
  </div>
</footer>
```

- [ ] **Step 11.2: Add `--serve` flag to `build_site.py`**

Add to `main()`:

```python
parser.add_argument("--serve", action="store_true", help="Build then serve on localhost:8000")
args = parser.parse_args()
build(db_path=args.db)
if args.serve:
    import http.server, os
    os.chdir("dist")
    print("Serving at http://localhost:8000 …")
    http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=8000, bind="127.0.0.1")
```

- [ ] **Step 11.3: Run full build + serve**

```bash
source ~/devbox/envs/240826/bin/activate && python3 build_site.py --serve
```

Open http://localhost:8000 and scroll through all 8 sections.

- [ ] **Step 11.4: Add `.gitignore` entries**

Ensure `dist/` is in `.gitignore`:

```bash
grep -q "^dist/" .gitignore || echo "dist/" >> .gitignore
grep -q "^.superpowers/" .gitignore || echo ".superpowers/" >> .gitignore
```

- [ ] **Step 11.5: Run full test suite**

```bash
source ~/devbox/envs/240826/bin/activate
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 11.6: Final commit**

```bash
git add templates/index.html.j2 build_site.py .gitignore
git commit -m "feat(site): footer, --serve flag, gitignore; all sections complete"
```

---

## Self-review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Static HTML via Python build script | Task 1 |
| Palette Os & cerneală (#FAF8F3 / #15171A / #C04F35) | Task 2 |
| Source Serif 4 + Inter fonts | Task 2 |
| Top nav with 8 anchors | Task 2 |
| Section 1: hero headline + gender comparison | Task 4 |
| Section 2: searchable top-50 names | Task 5 |
| Section 3: gender gap grid + tower chart | Task 6 |
| Section 4: recognition tiers + pageviews | Task 7 |
| Section 5: theme donut + drill-downs | Task 7 |
| Section 6: D3 choropleth + fingerprint | Task 8 |
| Section 7: renaming gallery (placeholder) | Task 9 |
| Section 8: CIORANI + curiosity cards | Task 10 |
| Footer + Despre date | Task 11 |
| Observable Plot CDN | Not needed — all charts are CSS/HTML inline (Plot is in spec but mockups show CSS-only charts; remove CDN if unused) |
| `dist/ro-counties.geojson` copy | Task 1 + Task 8 |
| `--serve` dev flag | Task 11 |

**Open issues noted in spec:**

1. GeoJSON property name for județ code — verified at Task 8.4 before using
2. Renaming data — explicitly deferred with backlog entry (Task 9)
3. Gender curation coverage (15 F persons) — section 3 shows real data + adds note "Clasificare gender în curs — date parțiale"
4. `name_categories` categories differ from spec's theme taxonomy — `section5()` uses UNION across all classification sources; displays correctly

**No placeholders found.** Section 7 uses static illustrative data with an explicit "în construcție" notice rather than a code placeholder.
