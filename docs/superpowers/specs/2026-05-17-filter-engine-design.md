# Filter Engine — Design Spec

**Date:** 2026-05-17
**Status:** Approved

## Overview

An exhaustive multi-attribute filtering UI for the streets dataset. Lets the user intersect any combination of geographic, typological, and semantic dimensions — e.g. "all streets named after female poets of Romanian nationality in Harghita county." Results are individual (street, UAT) occurrences, not aggregated canonical names.

Initially local-only (stdlib Python server). API is designed to be deployed unchanged behind gunicorn when the time comes.

---

## Architecture

Two new files:

| File | Role |
|---|---|
| `filter_server.py` | stdlib HTTP server — serves the API and the static UI page |
| `dist/filter/index.html` | Self-contained HTML+JS filter UI — no Jinja, no build step |

**Server routes:**

| Route | Description |
|---|---|
| `GET /api/meta` | All valid enum values for every filter dimension (called once on page load) |
| `GET /api/filter` | Parameterized filter query — returns paginated JSON rows + total count |
| `GET /` | Serves `dist/filter/index.html` |

Run with:
```bash
python3 filter_server.py          # defaults to localhost:8765
python3 filter_server.py --port 9000 --db data/streets.db
```

Nothing else in the repo is modified. The `dist/filter/` page can be linked from the main site nav later.

---

## API

### `GET /api/meta`

Called once on page load to populate all dropdowns. Returns current valid values from the live DB.

```json
{
  "judete": ["AB", "AG", "AR", "B", ...],
  "street_types": ["Aleea", "Bulevardul", "Calea", ...],
  "classifications": ["person", "nature", "place", "category", "saint", "date", "numeric"],
  "professions": ["poet", "writer", "voievod", ...],
  "nationalities": ["RO", "HU", ...],
  "genders": ["M", "F", "collective"],
  "eras": ["ancient", "medieval", "premodern", "1848", "interwar", "communist"],
  "wiki_scopes": ["local", "national", "universal", "unknown"],
  "categories": ["abstract", "commemorative", "ideological", "infrastructure", ...],
  "subcategories": ["church", "freedom", "school", ...],
  "nature_types": ["animal", "bird", "field", "flower", "forest", ...],
  "place_types": ["ancient_city", "battle_site", "foreign_city", "mountain", ...],
  "place_countries": ["AT", "BG", "DE", "FR", "GB", "GR", "IT", "RO", ...]
}
```

### `GET /api/filter`

Multi-value params: repeat a key for OR within a dimension, AND across dimensions.

| Param | Type | Notes |
|---|---|---|
| `judet` | multi | County code(s): `judet=HR&judet=CV` |
| `uat` | text | Free-text partial match against UAT name (case-insensitive, uses `LIKE '%?%'`) |
| `street_type` | multi | `Strada`, `Bulevardul`, etc. |
| `classification` | multi | `person`, `nature`, `place`, `category`, `saint`, `date`, `numeric` |
| `profession` | multi | Person sub-filter (implicitly constrains to person) |
| `nationality` | multi | Person sub-filter |
| `gender` | multi | Person sub-filter |
| `era` | multi | Person sub-filter |
| `wiki_scope` | multi | Person sub-filter |
| `category` | multi | Category sub-filter |
| `subcategory` | multi | Category sub-filter |
| `nature_type` | multi | Nature sub-filter |
| `place_type` | multi | Place sub-filter |
| `place_country` | multi | Place sub-filter |
| `limit` | int | Default 200, max 1000 |
| `offset` | int | For pagination, default 0 |

**Response:**

```json
{
  "total": 847,
  "limit": 200,
  "offset": 0,
  "rows": [
    {
      "name": "Strada Mihai Eminescu",
      "street_type": "Strada",
      "uat": "MUNICIPIUL MIERCUREA CIUC",
      "judet": "HR",
      "siruta": 92216,
      "classification": "person",
      "person_full_name": "Mihai Eminescu",
      "profession": "poet",
      "nationality": "RO",
      "gender": "M",
      "era": "premodern",
      "wiki_scope": "universal",
      "category": null,
      "subcategory": null,
      "nature_type": null,
      "place_type": null,
      "place_country": null,
      "street_slug": "mihai-eminescu"
    }
  ]
}
```

Non-person fields are `null` for person rows and vice versa. `street_slug` is `slugify(core_name or name_normalized)` — matches the slug used in the static site's `/strada/<slug>/` pages.

---

## SQL Query Strategy

Base: `streets_dedup` LEFT JOINed to all four lookup tables (`persons`, `name_categories`, `nature_terms`, `place_refs`). Classification derived inline via the same CASE expression used in `streets_classified_pct`.

WHERE clause built programmatically:
- Each active filter appends a condition + values to a `params` list
- Multi-value params expand to `col IN (?, ?, ...)`
- All values go through `?` placeholders — no string interpolation
- Sub-filters (e.g. `profession=poet`) implicitly constrain classification to `person` via a JOIN condition; no need to also pass `classification=person`
- Contradictory filters (e.g. `classification=nature&profession=poet`) return zero rows — correct, no special-casing needed

Two queries per request:
1. `SELECT COUNT(*)` with the same WHERE — gives `total`
2. Paginated `SELECT ... LIMIT ? OFFSET ?` — gives `rows`

Both run fast on 105k rows with existing indexes (`ix_streets_judet`, `ix_streets_corenorm`, etc.).

`street_slug` is computed server-side as `streets_lib.slugify(core_name or name_normalized)` — the same expression `build_site.py` uses to generate `/strada/<slug>/` directory names.

---

## Frontend UI

Self-contained `dist/filter/index.html`. Uses the existing site's CSS variables and IBM Plex font stack.

### Layout

```
┌─────────────────────────────────────────────────────┐
│ nav / breadcrumb                                    │
├──────────────┬──────────────────────────────────────┤
│ FILTER PANEL │ RESULTS                              │
│ ~280px       │                                      │
│              │  847 results · showing 1–200         │
│ County       │                                      │
│ [checkboxes] │  Name          Type  UAT      Județ  │
│              │  ─────────────────────────────────   │
│ UAT          │  Str. Eminescu  Str  M. Ciuc   HR    │
│ [text]       │  ...                                 │
│              │                                      │
│ Street type  │  [← Prev]              [Next →]      │
│ [checkboxes] │                                      │
│              │                                      │
│ Classification│                                     │
│ (●) All      │                                      │
│ ( ) Person   │                                      │
│ ( ) Nature   │                                      │
│ ...          │                                      │
│              │                                      │
│ ── Sub-filters│                                     │
│ (contextual) │                                      │
└──────────────┴──────────────────────────────────────┘
```

### Filter panel details

- **County** — multi-select checkboxes, with a search-within input above (client-side filter of the checkbox list, not a new API call)
- **UAT** — free text, debounced 300ms before firing API call
- **Street type** — multi-select checkboxes
- **Classification** — radio group: All / Person / Nature / Place / Category / Saint / Date / Numeric
- **Contextual sub-panel** — shown below classification radio, only when a specific classification is selected:
  - Person: profession, nationality, gender, era, wiki_scope (all multi-select checkboxes)
  - Nature: nature_type (multi-select)
  - Place: place_type, place_country (multi-select)
  - Category: category → subcategory (multi-select; subcategory list is not filtered by selected category, kept simple)
  - Saint / Date / Numeric / All: no sub-panel

### Results table

Columns: **Name** (links to `/strada/<slug>/`) · **Type** · **UAT** (links to `/oras/<judet>/<siruta>/`) · **Județ** · **Detail** (profession for persons, nature_type for nature, place_name for places, category for categories — whichever applies)

Zero results state: "Nicio potrivire găsită pentru filtrele selectate."

### URL state

- Every filter change calls `history.replaceState` to update `?` params
- On page load, params are parsed and the filter panel is restored before the first API call
- Pagination offset is also a URL param (`&offset=200`)
- The URL is fully shareable and reproducible

---

## File Checklist

- [ ] `filter_server.py` — HTTP server (stdlib only: `http.server`, `sqlite3`, `urllib.parse`, `json`, `argparse`)
- [ ] `dist/filter/index.html` — self-contained filter UI

No changes to: `build_site.py`, `build_db.py`, `streets_lib.py`, templates, or any existing dist files.

---

## Deployment path (future)

When deploying:
1. Install `gunicorn`
2. Wrap `filter_server.py`'s handler in a WSGI adapter (one function, ~10 lines) or migrate to Flask (API contract unchanged)
3. Serve `dist/filter/index.html` via nginx or as a route on the same server
4. Point the main site's nav link at the hosted URL
