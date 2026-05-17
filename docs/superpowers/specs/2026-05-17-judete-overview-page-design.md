# Design: Județe Overview Page + Navbar Județ Selector

**Date:** 2026-05-17  
**Status:** Approved

---

## Goal

1. Move the județ `<select>` filter from inside the cluster-cloud panel header into the sticky navbar — always accessible, never scrolled away.
2. Strip all per-județ comparison content from the landing page (`index.html`), making it purely national.
3. Introduce a dedicated `/judete/` page that holds the map, comparison table, amprente, semnături, curiozități, and top cities.

---

## Changes at a Glance

| What | From | To |
|---|---|---|
| Județ `<select>` | Panel header in `#cele-mai-intalnite` | Sticky navbar, right side |
| Harta panel (`#harta`) | `index.html` | `/judete/` |
| Amprente județene panel | `index.html` | `/judete/` |
| Semnături regionale panel | `index.html` | `/judete/` |
| Curiozități unice panel (`#curiozitati`) | `index.html` | `/judete/` |
| Nav link "Harta" → `#harta` | `index.html` nav | Nav link "Județe" → `/judete/` |
| Nav link "Curiozități" → `#curiozitati` | `index.html` nav | Removed (Curiozități moves to `/judete/`) |
| Sortable comparison table | — | New, `/judete/` |
| Top 20 cities panel | — | New, `/judete/` |
| `/judete/index.html` UAT list | Simple list of 676 UATs | Replaced by rich overview; UAT list kept as "Vezi toate localitățile" link |

---

## 1. Navbar — Județ Selector

### HTML (`templates/index.html.j2`)

Move the `<select id="s2-judet-select">` element (and its options, populated by JS) out of `.s2-judet-pick` in the panel header and into `<nav class="site-nav">`:

```html
<nav class="site-nav">
  <a href="/" class="brand">Cum ne numim străzile</a>
  <nav>
    <a href="#cele-mai-intalnite">Cele mai întâlnite</a>
    <a href="#tematica">Tematică</a>
    <a href="#pe-cine-onoram">Pe cine onorăm</a>
    <a href="/judete/">Județe</a>
    <a href="metodologie.html">Metodologie</a>
    <span class="nav-sep"></span>
    <select id="s2-judet-select">
      <option value="all">Toate județele</option>
      <!-- populated by JS, same as before -->
    </select>
  </nav>
</nav>
```

Remove the entire `.s2-judet-pick` div from the panel header of `#cele-mai-intalnite`. Remove the `<span class="panel-meta">filtrat de județ ↑</span>` from the persons panel header.

### CSS

Keep the existing `#s2-judet-select` JS references unchanged — only the DOM location changes.

Add to `.site-nav` styles:

```css
.nav-sep {
  display: inline-block;
  width: 1px;
  height: 16px;
  background: #3a3a3a;   /* matches the dark nav background */
  margin: 0 6px;
  vertical-align: middle;
}
.site-nav select {
  background: transparent;
  border: 1px solid rgba(255,255,255,.18);
  color: var(--bg);          /* light text on dark nav */
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 22px 2px 8px;
  border-radius: 3px;
  height: 26px;
  cursor: pointer;
  appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, var(--bg) 50%),
    linear-gradient(135deg, var(--bg) 50%, transparent 50%);
  background-position: calc(100% - 9px) 54%, calc(100% - 5px) 54%;
  background-size: 4px 4px, 4px 4px;
  background-repeat: no-repeat;
  max-width: 150px;
}
.site-nav select:focus { outline: none; border-color: var(--gold); }
```

Remove `.s2-judet-pick`, `.s2-judet-pick label`, `.s2-judet-pick select` — no longer needed.

---

## 2. Landing Page — Remove Județ Comparison Sections

Remove from `templates/index.html.j2`:

- `{# PANEL: HARTA (s12) #}` — the entire `<div class="panel s12" id="harta">` block (~27 lines)
- `{# PANEL: AMPRENTE JUDEȚENE (s12) #}` — entire block (~47 lines)
- `{# PANEL: SEMNĂTURI REGIONALE (s6) + CURIOZITĂȚI UNICE (s6) #}` — both panels (~34 lines)
- The D3 / section6 JS blocks that populate the map, fingerprint, and `by_judet` rendering (~50 lines at the bottom of the `<script>` section)

Update the nav: remove `<a href="#curiozitati">Curiozități</a>` (that anchor no longer exists on the landing).

`DATA_S6` is still baked into the page (the JS for the cloud panels uses `DATA_S6.by_judet` to populate the select options). Keep the `{{ section6 | tojson }}` injection — only the map/fingerprint rendering code is removed.

---

## 3. `/judete/` Overview Page

### Template: `templates/judete-index.html.j2`

Replace the current simple UAT list with a full analysis page. Extends `_detail-shell.html.j2` (same as all detail pages).

Sections in order:

#### 3a. Harta interactivă + fingerprint
Moved verbatim from `index.html.j2` — same D3 choropleth SVG, same `#s6-metric-row` metric chips, same `#s6-fingerprint` sidebar. The JS for this section moves into the judete template's `{% block scripts %}`.

#### 3b. Tabel comparativ județe — sortabil
Client-side sortable table. Data source: `section6.by_judet`.

Columns: Județ | Străzi | % sfinți | % natură | % femei | % numeric. Add `nature_pct` to `section6()` query (see §4).

Clicking a column header toggles asc/desc sort. Active column header gets a `▾`/`▴` indicator. Each row links to `/judete/<judet-lower>/` (future — no-op for now, `#`).

#### 3c. Amprente județene — trei caractere
Moved verbatim: 3-column subgrid with exclusiviste / rural-poetice / ideologice bar charts. Data: `section8.judet_distinctive`, `section8.judet_rural`, `section8.judet_ideo`.

#### 3d. Semnături regionale + Curiozități unice
Moved verbatim side-by-side: `section8.regional_signatures` and `section8.local_uniques`.

#### 3e. Top 20 localități
Top 20 UATs by `total` descending, sorted in the Jinja2 template from the `uats` list (already passed, already has `slug`, `judet`, `uat`, `total`). Each entry is a pill linking to `/oras/<judet-lower>/<slug>/`. A "Vezi toate localitățile → /judete/lista/" link at the bottom preserves access to the full 676-UAT list.

### Data passed to the template

```python
_render(env, "judete-index.html.j2",
        DIST / "judete" / "index.html",
        section6=section6_data,
        section8=section8_data,
        judete=judete_list,
        uats=uats,          # for top-20 cities + UAT slugs
        portraits=portraits)
```

`section6` and `section8` are loaded inside `build_detail_pages()` — it already has a DB connection, so just call the queries there.

---

## 4. `section6()` Query Extension

Add `nature_pct` to the `by_judet` query in `site_queries.py`:

```sql
ROUND(100.0 * SUM(CASE WHEN nc.macro = 'natură' THEN 1 ELSE 0 END) / COUNT(*), 1) AS nature_pct
```

with a `LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm`.

This is one extra LEFT JOIN and one CASE expression — no new query needed.

---

## 5. UAT Full List Preservation

Move the UAT alphabetical list to `templates/judete-lista.html.j2`, rendered to `dist/judete/lista/index.html`. The current `judete-index.html.j2` content moves there. The overview page links to it at the bottom.

---

## 6. Build Changes

In `build_site.py → build_detail_pages()`:

```python
section6_data = site_queries.section6(conn)
section8_data = site_queries.section8(conn)

_render(env, "judete-index.html.j2",
        DIST / "judete" / "index.html",
        section6=section6_data, section8=section8_data,
        judete=judete_list, uats=uats, portraits=portraits)

_render(env, "judete-lista.html.j2",
        DIST / "judete" / "lista" / "index.html",
        judete=judete_list, uats=uats)
```

No new CLI flags needed — existing `--detail` / `--detail-only` already covers this.

---

## 7. Tests

Update `tests/test_build.py`:

- `test_default_is_cluster_cloud` — assert `#harta` panel is absent from `dist/index.html` after this change
- `test_judete_overview_builds` — assert `dist/judete/index.html` contains the map SVG container, the comparison table, and the top cities section
- `test_judete_lista_builds` — assert `dist/judete/lista/index.html` renders

---

## Out of Scope

- Per-județ sub-pages (`/judete/PH/`) — the map's click-to-link is a future step
- Mobile nav collapse for the select (existing mobile breakpoint hides the nav; the select can be added to that consideration later)
- Datasette integration
