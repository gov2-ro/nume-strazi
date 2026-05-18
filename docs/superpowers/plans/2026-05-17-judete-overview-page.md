# Județe Overview Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the județ selector to the sticky navbar, strip all per-județ comparison panels from the landing page, and introduce a rich `/judete/` overview page with map, sortable comparison table, amprente, semnături, curiozități, and top-20 cities.

**Architecture:** The judete overview page is a static HTML page built by `build_detail_pages()` alongside all other entity detail pages. It extends `_detail-shell.html.j2` and injects `DATA_S6` / `DATA_S8` as JSON blobs for the map and table JS. The landing page (`index.html`) keeps `DATA_S6` only for the navbar select; the full map/comparison JS moves to the judete template.

**Tech Stack:** Python 3.11+, Jinja2, D3 v7 (CDN), vanilla JS, SQLite, pytest

---

## File Map

| Action | File |
|---|---|
| Modify | `site_queries.py` — add `nature_pct` to `section6()` |
| Modify | `build_site.py` — load section6/section8 in `build_detail_pages`, render two judete pages |
| Rename→Create | `templates/judete-lista.html.j2` — simple UAT list (current judete-index content) |
| Rewrite | `templates/judete-index.html.j2` — new full overview page |
| Modify | `templates/index.html.j2` — move select to nav, remove 4 judete panels + D3 JS block |
| Modify | `tests/test_build.py` — update/add 4 tests |

---

## Task 1: Write Failing Tests First

**Files:**
- Modify: `tests/test_build.py`

- [ ] **Step 1.1: Update `test_section6_map` to check judete page instead of index**

Replace the existing `test_section6_map` function with one that checks the judete overview page, and add two new tests. Run all existing tests first to capture the current baseline.

```bash
cd /Users/pax/devbox/gov2/misc/nume-strazi
source ~/devbox/envs/240826/bin/activate
python3 -m pytest tests/test_build.py -q 2>&1 | tail -5
```

Expected: 12 pass, 0 fail.

- [ ] **Step 1.2: Edit `tests/test_build.py` — replace `test_section6_map` and add new tests**

Find and replace the existing `test_section6_map` function, and add `test_judete_overview_builds` and `test_judete_lista_builds` right after it. Also add assertion to `test_default_is_cluster_cloud`.

Replace the entire `test_section6_map` function:

```python
def test_section6_in_index_for_select():
    """DATA_S6 must still be baked into index.html for the nav select."""
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "DATA_S6" in html
    assert "s2-judet-select" in html
    # Harta panel must NOT be in the landing page any more
    assert 'id="harta"' not in html
    assert "s6-map" not in html
```

Append these two new test functions after `test_section6_in_index_for_select`:

```python
def test_judete_overview_builds():
    """dist/judete/index.html — overview page with map, table, amprente, top cities."""
    result = subprocess.run(
        [sys.executable, "build_site.py", "--db", "data/streets.db", "--detail-only"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    out = Path("dist/judete/index.html")
    assert out.exists(), "dist/judete/index.html not found"
    html = out.read_text(encoding="utf-8")
    assert 'id="s6-map"' in html,        "map SVG container missing"
    assert 'id="judet-table"' in html,   "sortable table missing"
    assert "judet_distinctive" in html,  "amprente data missing (DATA_S8)"
    assert "top-cities" in html,         "top cities section missing"


def test_judete_lista_builds():
    """dist/judete/lista/index.html — full UAT alphabetical list."""
    out = Path("dist/judete/lista/index.html")
    assert out.exists(), "dist/judete/lista/index.html not found"
    html = out.read_text(encoding="utf-8")
    assert "localități" in html
    assert "/oras/" in html
```

Update `test_default_is_cluster_cloud` — add one assertion at the end of the function body:

```python
    # Harta panel removed from landing
    assert 'id="harta"' not in html
```

- [ ] **Step 1.3: Run tests — confirm failures**

```bash
python3 -m pytest tests/test_build.py -q 2>&1 | tail -10
```

Expected: `test_section6_in_index_for_select` FAIL (s6-map still in index.html), `test_judete_overview_builds` FAIL (file not built with section data yet), `test_default_is_cluster_cloud` FAIL (`id="harta"` still present).

---

## Task 2: Extend `section6()` with `nature_pct`

**Files:**
- Modify: `site_queries.py:479-489`

- [ ] **Step 2.1: Update the `by_judet` query in `section6()`**

Nature streets live in the `nature_terms` table joined on `core_name_norm`. Add a `LEFT JOIN` and a new `CASE` column.

In `site_queries.py`, replace the `by_judet` query (the SQL string inside `section6()`):

```python
    by_judet = _rows(conn, """
        SELECT judet,
               COUNT(*) AS total_streets,
               ROUND(100.0 * SUM(is_saint) / COUNT(*), 1) AS saint_pct,
               ROUND(100.0 * SUM(is_numeric) / COUNT(*), 1) AS numeric_pct,
               ROUND(100.0 * SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS female_pct,
               ROUND(100.0 * SUM(CASE WHEN nt.core_name_norm IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS nature_pct
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
        LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        GROUP BY judet
        ORDER BY total_streets DESC
    """)
```

- [ ] **Step 2.2: Verify the query returns `nature_pct`**

```bash
source ~/devbox/envs/240826/bin/activate
python3 -c "
import site_queries, sqlite3
conn = sqlite3.connect('data/streets.db')
conn.row_factory = sqlite3.Row
rows = site_queries.section6(conn)['by_judet']
print(dict(rows[0]))
conn.close()
"
```

Expected: output includes `'nature_pct': <float>`.

- [ ] **Step 2.3: Commit**

```bash
git add site_queries.py
git commit -m "feat(queries): add nature_pct to section6 by_judet"
```

---

## Task 3: Create `judete-lista.html.j2` (Simple UAT List)

**Files:**
- Create: `templates/judete-lista.html.j2`

The current `judete-index.html.j2` content (simple alphabetical UAT list) moves here. The original file will be rewritten in Task 5.

- [ ] **Step 3.1: Create `templates/judete-lista.html.j2`**

```jinja2
{# templates/judete-lista.html.j2 — alphabetical UAT list #}
{% extends "_detail-shell.html.j2" %}

{% block title %}Toate localitățile — Cum ne numim străzile{% endblock %}

{% block body %}
<div class="detail-page">

  <div class="breadcrumb">
    <a href="/">Acasă</a>
    <span class="sep">›</span>
    <a href="/judete/">Județe</a>
    <span class="sep">›</span>
    <span>Toate localitățile</span>
  </div>

  <div class="detail-hero">
    <div class="kicker"><span class="emo">🗺️</span> Localități</div>
    <h1 style="font-size:28px; font-weight:700; font-family:var(--street);">{{ uats | length }} localități cu pagini proprii</h1>
    <div class="meta-row">Localități cu minim 50 de străzi înregistrate · <a href="/judete/">← Înapoi la overview județe</a></div>
  </div>

  {% for j in judete %}
  {% set j_uats = uats | selectattr('judet', 'equalto', j) | sort(attribute='total', reverse=true) | list %}
  {% if j_uats %}
  <div class="detail-section">
    <div class="detail-section-header">{{ j }} — {{ j_uats | length }} localități</div>
    <div class="uat-cluster">
      {% for u in j_uats %}
        <a class="uat-pill" href="/oras/{{ j | lower }}/{{ u.slug }}/">
          {{ u.uat | title }}
          <span style="font-size:10px; color:var(--muted); font-weight:500; margin-left:4px;">{{ u.total }}</span>
        </a>
      {% endfor %}
    </div>
  </div>
  {% endif %}
  {% endfor %}

</div>
{% endblock %}
```

---

## Task 4: Update `build_site.py` — Render Both Județe Pages

**Files:**
- Modify: `build_site.py:183-187` (the judete render block inside `build_detail_pages`)

- [ ] **Step 4.1: Load section6 and section8 inside `build_detail_pages`, render both pages**

In `build_site.py`, find the judete render block in `build_detail_pages()` (currently lines 183-187):

```python
    judete_list = sorted({u["judet"] for u in uats})
    _render(env, "judete-index.html.j2",
            DIST / "judete" / "index.html",
            judete=judete_list, uats=uats)
    print("    → dist/judete/index.html")
```

Replace it with:

```python
    judete_list = sorted({u["judet"] for u in uats})
    section6_data = site_queries.section6(conn)
    section8_data = site_queries.section8(conn)
    _render(env, "judete-index.html.j2",
            DIST / "judete" / "index.html",
            section6=section6_data, section8=section8_data,
            judete=judete_list, uats=uats, portraits=portraits)
    print("    → dist/judete/index.html")
    _render(env, "judete-lista.html.j2",
            DIST / "judete" / "lista" / "index.html",
            judete=judete_list, uats=uats)
    print("    → dist/judete/lista/index.html")
```

- [ ] **Step 4.2: Verify the build runs (template doesn't exist yet — expect Jinja TemplateNotFound, not Python error)**

```bash
source ~/devbox/envs/240826/bin/activate
python3 build_site.py --detail-only --db data/streets.db 2>&1 | tail -5
```

Expected: `TemplateNotFound: judete-index.html.j2` — proves the Python wiring works, template is next.

- [ ] **Step 4.3: Commit**

```bash
git add build_site.py templates/judete-lista.html.j2
git commit -m "feat(build): load section6/section8 for judete overview; add lista page"
```

---

## Task 5: Create `templates/judete-index.html.j2` (Overview Page)

**Files:**
- Rewrite: `templates/judete-index.html.j2`

This is the core template. It extends `_detail-shell.html.j2`. The D3 map JS block is moved here from `index.html.j2`; the GeoJSON path becomes `../ro-counties.geojson`; `escapeHtml` is defined in the shared script scope (not inside an IIFE). The sortable table uses `DATA_S6.by_judet` client-side.

- [ ] **Step 5.1: Write `templates/judete-index.html.j2`**

```jinja2
{# templates/judete-index.html.j2 — Județe overview page #}
{% extends "_detail-shell.html.j2" %}

{% block title %}Județe — Cum ne numim străzile{% endblock %}

{% block head_scripts %}
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
{% endblock %}

{% block body %}
<script>
const DATA_S6 = {{ section6 | tojson }};
const DATA_S8 = {{ section8 | tojson }};
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
</script>

<div class="detail-page" style="max-width:1640px;">

  <div class="breadcrumb">
    <a href="/">Acasă</a>
    <span class="sep">›</span>
    <span>Județe</span>
  </div>

  <div class="detail-hero">
    <div class="kicker"><span class="emo">🗺️</span> Județe</div>
    <h1 style="font-size:32px; font-weight:700; font-family:var(--street);">Statistici pe județ</h1>
    <div class="meta-row">{{ section6.by_judet | length }} județe · date din registrul secțiilor de vot</div>
  </div>

  {# ── 1. HARTA ─────────────────────────────────────────────────────────── #}
  <div class="panel s12" id="harta" style="background:var(--surface-1);border:1px solid var(--rule);border-radius:6px;padding:16px 20px;margin-bottom:16px;">
    <div class="panel-header">
      <span class="panel-label"><span class="emo xl">🗺️</span> Harta · statistici pe județ</span>
      <div class="chip-row" id="s6-metric-row" style="margin:0;padding:0;border:none;">
        <span class="label">Vedeți după</span>
        <button class="chip active" data-metric="saint_pct">% sfinți</button>
        <button class="chip" data-metric="numeric_pct">% numere</button>
        <button class="chip" data-metric="female_pct">% femei</button>
      </div>
    </div>
    <div class="map-grid" id="s6-grid">
      <div style="position:relative;">
        <svg id="s6-map" style="width:100%;height:auto;display:block;"></svg>
        <div style="margin-top:10px;display:flex;align-items:center;gap:12px;font-family:var(--sans);font-size:10.5px;color:var(--muted);">
          <span id="s6-scale-min">0%</span>
          <div style="flex:1;height:5px;background:linear-gradient(to right,#F4EFE6 0%,#E8B299 35%,#D27A5C 65%,#A53A22 100%);border-radius:1px;"></div>
          <span id="s6-scale-max" style="font-variant-numeric:tabular-nums;">12%</span>
          <span style="margin-left:10px;" id="s6-scale-label">% străzi cu prefix „Sf."</span>
        </div>
      </div>
      <div class="fingerprint" id="s6-fingerprint">
        <div class="kicker"><span class="emo lg">🧬</span> Amprenta județului</div>
        <p style="font-family:var(--sans);font-size:12.5px;color:var(--muted);padding-top:20px;line-height:1.55;">
          Selectați un județ pe hartă.
        </p>
      </div>
    </div>
  </div>

  {# ── 2. TABEL COMPARATIV ──────────────────────────────────────────────── #}
  <div class="panel s12" style="background:var(--surface-1);border:1px solid var(--rule);border-radius:6px;padding:16px 20px;margin-bottom:16px;">
    <div class="panel-header">
      <span class="panel-label"><span class="emo xl">📊</span> Comparație județe</span>
      <span class="panel-meta">click pe coloană pentru sortare</span>
    </div>
    <div style="overflow-x:auto;">
      <table id="judet-table" style="width:100%;border-collapse:collapse;font-family:var(--sans);font-size:11.5px;">
        <thead>
          <tr>
            <th data-col="judet"         data-label="Județ"    style="text-align:left;padding:6px 10px;background:var(--surface-1);border-bottom:2px solid var(--rule-strong);cursor:pointer;white-space:nowrap;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);">Județ ▾</th>
            <th data-col="total_streets" data-label="Străzi"   style="text-align:right;padding:6px 10px;background:var(--surface-1);border-bottom:2px solid var(--rule-strong);cursor:pointer;white-space:nowrap;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);">Străzi</th>
            <th data-col="saint_pct"     data-label="% sfinți" style="text-align:right;padding:6px 10px;background:var(--surface-1);border-bottom:2px solid var(--rule-strong);cursor:pointer;white-space:nowrap;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);">% sfinți</th>
            <th data-col="nature_pct"    data-label="% natură" style="text-align:right;padding:6px 10px;background:var(--surface-1);border-bottom:2px solid var(--rule-strong);cursor:pointer;white-space:nowrap;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);">% natură</th>
            <th data-col="female_pct"    data-label="% femei"  style="text-align:right;padding:6px 10px;background:var(--surface-1);border-bottom:2px solid var(--rule-strong);cursor:pointer;white-space:nowrap;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);">% femei</th>
            <th data-col="numeric_pct"   data-label="% numere" style="text-align:right;padding:6px 10px;background:var(--surface-1);border-bottom:2px solid var(--rule-strong);cursor:pointer;white-space:nowrap;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);">% numere</th>
          </tr>
        </thead>
        <tbody id="judet-table-body"></tbody>
      </table>
    </div>
  </div>

  {# ── 3. AMPRENTE JUDEȚENE ─────────────────────────────────────────────── #}
  <div class="panel s12" style="background:var(--surface-1);border:1px solid var(--rule);border-radius:6px;padding:16px 20px;margin-bottom:16px;">
    <div class="panel-header">
      <span class="panel-label"><span class="emo xl">🧬</span> Amprente județene · trei caractere</span>
    </div>
    <div class="subgrid-3">

      <div style="background:var(--bg);padding:14px 16px;">
        <div class="panel-label" style="margin-bottom:6px;"><span class="emo xl">💎</span> Cele mai exclusiviste</div>
        <div class="panel-caption" style="margin:0 0 8px;">Județe cu cele mai multe nume găsite doar acolo · ≥3 străzi local</div>
        {% set max_d = section8.judet_distinctive[0].n if section8.judet_distinctive else 1 %}
        {% for row in section8.judet_distinctive %}
        <div style="display:flex;align-items:center;gap:8px;padding:3px 0;border-bottom:{{ '1px solid var(--wash)' if not loop.last else 'none' }};">
          <span style="font-family:var(--sans);font-size:9.5px;color:var(--muted);width:14px;text-align:right;font-variant-numeric:tabular-nums;">{{ loop.index }}</span>
          <span style="font-family:var(--sans);font-size:12px;font-weight:600;letter-spacing:.04em;width:30px;">{{ row.judet }}</span>
          <div class="bar-wrap" style="flex:1;"><div class="bar accent" style="width:{{ (row.n / max_d * 100)|int }}%;"></div></div>
          <span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);width:30px;text-align:right;font-variant-numeric:tabular-nums;">{{ row.n }}</span>
        </div>
        {% endfor %}
      </div>

      <div style="background:var(--bg);padding:14px 16px;">
        <div class="panel-label" style="margin-bottom:6px;"><span class="emo xl">🌾</span> Cele mai «rurale-poetice»</div>
        <div class="panel-caption" style="margin:0 0 8px;">Cota de străzi cu nume din natură (flori, copaci, ape, animale…)</div>
        {% set max_r = section8.judet_rural[0].pct if section8.judet_rural else 1 %}
        {% for row in section8.judet_rural %}
        <div style="display:flex;align-items:center;gap:8px;padding:3px 0;border-bottom:{{ '1px solid var(--wash)' if not loop.last else 'none' }};">
          <span style="font-family:var(--sans);font-size:9.5px;color:var(--muted);width:14px;text-align:right;font-variant-numeric:tabular-nums;">{{ loop.index }}</span>
          <span style="font-family:var(--sans);font-size:12px;font-weight:600;letter-spacing:.04em;width:30px;">{{ row.judet }}</span>
          <div class="bar-wrap" style="flex:1;"><div class="bar" style="width:{{ (row.pct / max_r * 100)|int }}%;background:#8BA888;opacity:.75;"></div></div>
          <span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);width:46px;text-align:right;font-variant-numeric:tabular-nums;">{{ row.pct }}%</span>
        </div>
        {% endfor %}
      </div>

      <div style="background:var(--bg);padding:14px 16px;">
        <div class="panel-label" style="margin-bottom:6px;"><span class="emo xl">🚩</span> Cele mai «ideologice»</div>
        <div class="panel-caption" style="margin:0 0 8px;">Cota de străzi cu nume ideologic (libertate, victorie, unire…)</div>
        {% set max_i = section8.judet_ideo[0].pct if section8.judet_ideo else 1 %}
        {% for row in section8.judet_ideo %}
        <div style="display:flex;align-items:center;gap:8px;padding:3px 0;border-bottom:{{ '1px solid var(--wash)' if not loop.last else 'none' }};">
          <span style="font-family:var(--sans);font-size:9.5px;color:var(--muted);width:14px;text-align:right;font-variant-numeric:tabular-nums;">{{ loop.index }}</span>
          <span style="font-family:var(--sans);font-size:12px;font-weight:600;letter-spacing:.04em;width:30px;">{{ row.judet }}</span>
          <div class="bar-wrap" style="flex:1;"><div class="bar accent" style="width:{{ (row.pct / max_i * 100)|int }}%;"></div></div>
          <span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);width:46px;text-align:right;font-variant-numeric:tabular-nums;">{{ row.pct }}%</span>
        </div>
        {% endfor %}
      </div>

    </div>
  </div>

  {# ── 4. SEMNĂTURI + CURIOZITĂȚI ───────────────────────────────────────── #}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">

    <div class="panel s6" style="background:var(--surface-1);border:1px solid var(--rule);border-radius:6px;padding:16px 20px;">
      <div class="panel-header">
        <span class="panel-label"><span class="emo xl">📜</span> Semnături regionale · ≥80% concentrare într-un județ</span>
        <span class="panel-meta">{{ section8.regional_signatures | length }} nume</span>
      </div>
      <div class="rank-list">
        {% for r in section8.regional_signatures %}
        <div class="rank-row" style="grid-template-columns: minmax(0, 1fr) 30px 70px; gap: 10px;">
          <span class="rank-name">{{ r.display_name }}</span>
          <span style="font-family:var(--sans);font-size:11px;font-weight:600;letter-spacing:.04em;color:var(--ink);text-align:right;">{{ r.judet }}</span>
          <span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums;">{{ r.local_total }}/{{ r.national_total }} · {{ r.pct }}%</span>
        </div>
        {% endfor %}
      </div>
    </div>

    <div class="panel s6" id="curiozitati" style="background:var(--surface-1);border:1px solid var(--rule);border-radius:6px;padding:16px 20px;">
      <div class="panel-header">
        <span class="panel-label"><span class="emo xl">🔎</span> Curiozități unice naționale · doar într-un singur UAT</span>
        <span class="panel-meta">selecție · geografice</span>
      </div>
      <div class="rank-list">
        {% for r in section8.local_uniques %}
        <div class="rank-row" style="grid-template-columns: minmax(0, 1fr) auto; gap: 10px;">
          <span class="rank-name">{{ r.display_name }}</span>
          <span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;">{{ r.uat | title }} · <strong style="color:var(--ink);font-weight:600;letter-spacing:.04em;">{{ r.judet }}</strong></span>
        </div>
        {% endfor %}
      </div>
    </div>

  </div>

  {# ── 5. TOP 20 LOCALITĂȚI ─────────────────────────────────────────────── #}
  {% set top_uats = uats | sort(attribute='total', reverse=true) | list %}
  <div class="panel s12" id="top-cities" style="background:var(--surface-1);border:1px solid var(--rule);border-radius:6px;padding:16px 20px;margin-bottom:24px;">
    <div class="panel-header">
      <span class="panel-label"><span class="emo xl">🏙️</span> Cele mai mari localități · top 20</span>
      <span class="panel-meta">după număr de străzi</span>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;padding-top:4px;">
      {% for u in top_uats[:20] %}
      <a href="/oras/{{ u.judet | lower }}/{{ u.slug }}/"
         style="display:inline-flex;align-items:center;gap:8px;background:var(--bg);border:1px solid var(--rule);border-radius:4px;padding:6px 12px;text-decoration:none;color:var(--ink);">
        <span style="font-family:var(--sans);font-weight:600;font-size:12px;">{{ u.uat | title }}</span>
        <span style="font-family:var(--sans);font-size:10px;color:var(--muted);letter-spacing:.04em;text-transform:uppercase;">{{ u.judet }}</span>
        <span style="font-family:var(--mono);font-size:11px;color:var(--gold);font-weight:700;">{{ u.total }}</span>
      </a>
      {% endfor %}
    </div>
    <div style="margin-top:14px;font-family:var(--sans);font-size:11px;color:var(--muted);">
      <a href="/judete/lista/" style="color:var(--plaque);">Vezi toate {{ uats | length }} localitățile →</a>
    </div>
  </div>

</div>{# end detail-page #}

{# ── D3 MAP JS (moved from index.html.j2) ────────────────────────────────── #}
<script>
(function() {
  const byJudet = {};
  DATA_S6.by_judet.forEach(d => { byJudet[d.judet] = d; });
  const topPerJudet    = DATA_S6.top_per_judet    || {};
  const rarePerJudet   = DATA_S6.rare_per_judet   || {};
  const personsPerJudet = DATA_S6.persons_per_judet || {};

  let activeMetric = 'saint_pct';
  const metricLabels = {
    saint_pct:   '% străzi cu prefix „Sf."',
    numeric_pct: '% străzi anonime (numere)',
    female_pct:  '% străzi cu nume feminin',
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
      const code = d.properties?.cod;
      const row = byJudet[code];
      return row ? colorScale(row[metric] || 0) : '#EEEAE0';
    });
  }

  document.querySelectorAll('#s6-metric-row .chip').forEach(btn => {
    btn.addEventListener('click', () => updateMetric(btn.dataset.metric));
  });

  fetch('../ro-counties.geojson')
    .then(r => r.json())
    .then(geo => {
      const svg = d3.select('#s6-map');
      const cellWidth = svg.node().parentElement.clientWidth;
      const width = cellWidth;
      const height = width * 0.62;
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

      const randomFeature = geo.features[Math.floor(Math.random() * geo.features.length)];
      renderFingerprint(randomFeature);
    })
    .catch(() => {
      document.getElementById('s6-map').insertAdjacentHTML('afterend',
        '<p style="font-family:var(--sans);font-size:12px;color:var(--muted);padding:14px 0;">Harta indisponibilă.</p>'
      );
    });

  function renderFingerprint(feature) {
    const code = feature.properties?.cod;
    const row  = byJudet[code] || {};
    const top  = topPerJudet[code]     || [];
    const rare = rarePerJudet[code]    || [];
    const persons = personsPerJudet[code] || [];

    const scopeDot = s => ({ universal: '🌍', national: '🇷🇴', local: '·' }[s] || '·');
    const genderDot = g => g === 'F'
      ? '<span style="color:#C05E8A;">●</span>'
      : '<span style="color:#4A7FA5;">●</span>';

    const topRows = top.map(s => {
      const tag = s.sl
        ? `<a href="/strada/${s.sl}/" style="text-decoration:none;"><span class="street-tag small">${escapeHtml(s.n)}</span></a>`
        : `<span class="street-tag small">${escapeHtml(s.n)}</span>`;
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid var(--rule);">
        ${tag}
        <span style="color:var(--muted);font-size:10.5px;font-variant-numeric:tabular-nums;">${s.c}</span>
      </div>`;
    }).join('');

    const personsRows = persons.map((p, i) => {
      const nameEl = p.sl
        ? `<a href="/persoana/${p.sl}/" style="color:var(--ink);text-decoration:none;font-weight:${i===0?'600':'500'};font-size:11.5px;">${escapeHtml(p.n)}</a>`
        : `<span style="font-family:var(--sans);color:var(--ink);font-weight:${i===0?'600':'500'};font-size:11.5px;">${escapeHtml(p.n)}</span>`;
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;border-bottom:1px solid var(--rule);">
        <span style="display:flex;align-items:center;gap:5px;">${genderDot(p.g)}${nameEl}</span>
        <span style="color:var(--muted);font-size:10.5px;font-variant-numeric:tabular-nums;">${p.c} ${p.s ? scopeDot(p.s) : ''}</span>
      </div>`;
    }).join('');

    const rareRows = rare.map(s => {
      const tag = s.sl
        ? `<a href="/strada/${s.sl}/" style="text-decoration:none;"><span class="street-tag small">${escapeHtml(s.n)}</span></a>`
        : `<span class="street-tag small">${escapeHtml(s.n)}</span>`;
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid var(--rule);">
        ${tag}
        <span style="color:var(--muted);font-size:10.5px;">${s.j === 1 ? 'unic' : s.j + ' județe'}</span>
      </div>`;
    }).join('');

    const fp = document.getElementById('s6-fingerprint');
    fp.innerHTML = `
      <div class="kicker"><span class="emo lg">🧬</span> Amprenta județului</div>
      <div style="font-family:var(--sans);font-weight:700;font-size:20px;margin:2px 0 4px;letter-spacing:-.015em;color:var(--ink);">${feature.properties?.name || code}</div>
      <div style="font-family:var(--sans);font-size:11px;color:var(--muted);margin-bottom:14px;font-variant-numeric:tabular-nums;font-weight:500;">${(row.total_streets||0).toLocaleString('ro-RO')} de străzi · Sfinți ${(row.saint_pct||0).toFixed(1)}% · Feminin ${(row.female_pct||0).toFixed(1)}%</div>
      <div class="kicker" style="margin-bottom:6px;"><span class="emo lg">🔝</span> Cele mai frecvente</div>
      <div style="margin-bottom:14px;">${topRows || '<span style="color:var(--muted)">—</span>'}</div>
      <div class="kicker" style="margin-bottom:6px;"><span class="emo lg">👤</span> Persoane omagiate</div>
      <div style="margin-bottom:14px;">${personsRows || '<span style="color:var(--muted)">—</span>'}</div>
      <div class="kicker" style="margin-bottom:6px;"><span class="emo lg">💎</span> Cele mai rare (unice național)</div>
      <div>${rareRows || '<span style="color:var(--muted)">—</span>'}</div>
    `;
  }
})();
</script>

{# ── SORTABLE TABLE JS ────────────────────────────────────────────────────── #}
<script>
(function() {
  const data = DATA_S6.by_judet.slice();
  let sortCol = 'total_streets';
  let sortAsc  = false;

  function render() {
    const sorted = data.slice().sort((a, b) => {
      const va = a[sortCol] ?? 0;
      const vb = b[sortCol] ?? 0;
      if (typeof va === 'string') return sortAsc ? va.localeCompare(vb, 'ro') : vb.localeCompare(va, 'ro');
      return sortAsc ? va - vb : vb - va;
    });
    const tbody = document.getElementById('judet-table-body');
    tbody.innerHTML = sorted.map(row => `
      <tr style="border-bottom:1px solid var(--rule);">
        <td style="padding:5px 10px;font-weight:600;">${escapeHtml(row.judet)}</td>
        <td style="padding:5px 10px;text-align:right;font-variant-numeric:tabular-nums;">${(row.total_streets||0).toLocaleString('ro-RO')}</td>
        <td style="padding:5px 10px;text-align:right;font-variant-numeric:tabular-nums;">${(row.saint_pct||0).toFixed(1)}%</td>
        <td style="padding:5px 10px;text-align:right;font-variant-numeric:tabular-nums;">${(row.nature_pct||0).toFixed(1)}%</td>
        <td style="padding:5px 10px;text-align:right;font-variant-numeric:tabular-nums;">${(row.female_pct||0).toFixed(1)}%</td>
        <td style="padding:5px 10px;text-align:right;font-variant-numeric:tabular-nums;">${(row.numeric_pct||0).toFixed(1)}%</td>
      </tr>
    `).join('');
  }

  document.querySelectorAll('#judet-table th[data-col]').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      if (sortCol === th.dataset.col) {
        sortAsc = !sortAsc;
      } else {
        sortCol = th.dataset.col;
        sortAsc  = (sortCol === 'judet');
      }
      document.querySelectorAll('#judet-table th[data-col]').forEach(h => {
        const indicator = h.dataset.col === sortCol ? (sortAsc ? ' ▴' : ' ▾') : '';
        h.textContent = h.dataset.label + indicator;
      });
      render();
    });
  });

  render();
})();
</script>

{% endblock %}
```

- [ ] **Step 5.2: Build the judete overview and verify no errors**

```bash
source ~/devbox/envs/240826/bin/activate
python3 build_site.py --detail-only --db data/streets.db 2>&1 | grep -E "judete|error|Error|Traceback"
```

Expected: `→ dist/judete/index.html` and `→ dist/judete/lista/index.html`, no tracebacks.

- [ ] **Step 5.3: Run tests — judete tests should now pass**

```bash
python3 -m pytest tests/test_build.py::test_judete_overview_builds tests/test_build.py::test_judete_lista_builds -v
```

Expected: both PASS.

- [ ] **Step 5.4: Commit**

```bash
git add templates/judete-index.html.j2 templates/judete-lista.html.j2
git commit -m "feat(judete): add overview page with map, table, amprente, top cities"
```

---

## Task 6: Update Landing Page — Move Select to Navbar, Strip Judete Panels

**Files:**
- Modify: `templates/index.html.j2`

This task has four distinct sub-changes. Do them in order, rebuilding and checking after each.

### 6a — CSS: Remove `.s2-judet-pick` rules, add `.nav-sep` + `.site-nav select`

- [ ] **Step 6a.1: Remove the three `.s2-judet-pick` CSS rules**

Find these lines in the `<style>` block of `templates/index.html.j2` (around line 415):

```css
.s2-judet-pick {
  display: flex; align-items: center; gap: 10px;
  font-family: var(--sans); font-size: 11.5px;
}
.s2-judet-pick label {
  letter-spacing: .14em; text-transform: uppercase;
  font-weight: 700; color: var(--muted);
  font-size: 10.5px;
}
.s2-judet-pick select {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
  background: var(--bg);
  border: 1.5px solid var(--ink);
  border-radius: 2px;
  padding: 5px 28px 5px 11px;
  -webkit-appearance: none; -moz-appearance: none; appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, var(--ink) 50%),
    linear-gradient(135deg, var(--ink) 50%, transparent 50%);
  background-position: calc(100% - 12px) 55%, calc(100% - 8px) 55%;
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
  cursor: pointer; outline: none;
  min-width: 220px;
}
.s2-judet-pick select:focus { box-shadow: 0 0 0 3px var(--warn-2); }
```

Delete all of the above. Then add these new rules immediately after the `.site-nav nav a:hover` rule (around line 169):

```css
.site-nav .nav-sep {
  display: inline-block; width: 1px; height: 16px;
  background: rgba(255,255,255,.18); margin: 0 4px; vertical-align: middle;
}
.site-nav select {
  background: transparent;
  border: 1px solid rgba(255,255,255,.22);
  color: #f0ede6;
  font-family: var(--sans); font-size: 11px; font-weight: 600;
  padding: 2px 22px 2px 8px;
  border-radius: 3px; height: 26px; cursor: pointer;
  -webkit-appearance: none; -moz-appearance: none; appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, #f0ede6 50%),
    linear-gradient(135deg, #f0ede6 50%, transparent 50%);
  background-position: calc(100% - 9px) 54%, calc(100% - 5px) 54%;
  background-size: 4px 4px, 4px 4px; background-repeat: no-repeat;
  max-width: 160px;
}
.site-nav select:focus { outline: none; border-color: var(--gold); }
```

### 6b — HTML nav: move select, update links

- [ ] **Step 6b.1: Update the `<nav class="site-nav">` block (around line 812)**

Replace:

```html
<nav class="site-nav">
  <a href="#cele-mai-intalnite" class="brand">Cum ne numim străzile</a>
  <nav>
    <a href="#cele-mai-intalnite">Cele mai întâlnite</a>
    <a href="#tematica">Tematică</a>
    <a href="#pe-cine-onoram">Pe cine onorăm</a>
    <a href="#harta">Harta</a>
    <a href="#curiozitati">Curiozități</a>
    <a href="metodologie.html">Metodologie</a>
  </nav>
</nav>
```

With:

```html
<nav class="site-nav">
  <a href="#cele-mai-intalnite" class="brand">Cum ne numim străzile</a>
  <nav>
    <a href="#cele-mai-intalnite">Cele mai întâlnite</a>
    <a href="#tematica">Tematică</a>
    <a href="#pe-cine-onoram">Pe cine onorăm</a>
    <a href="/judete/">Județe</a>
    <a href="metodologie.html">Metodologie</a>
    <span class="nav-sep"></span>
    <select id="s2-judet-select">
      <option value="all">Toate județele</option>
    </select>
  </nav>
</nav>
```

### 6c — HTML panel: remove `.s2-judet-pick` and the "filtrat de județ" meta span

- [ ] **Step 6c.1: Remove `.s2-judet-pick` div from the `#cele-mai-intalnite` panel header**

Find (around line 922):

```html
      <div class="s2-judet-pick">
        <label for="s2-judet-select">Județ</label>
        <select id="s2-judet-select">
          <option value="all">Toate județele</option>

        </select>
      </div>
```

Delete the entire `.s2-judet-pick` div (the `<select>` is now in the nav).

- [ ] **Step 6c.2: Remove "filtrat de județ ↑" meta span from the persons panel header**

Find (around line 941 after the above deletion):

```html
    <span class="panel-meta">filtrat de județ ↑</span>
```

Delete this line.

### 6d — Remove the four judete panels and the D3 JS block

- [ ] **Step 6d.1: Remove the Harta panel**

Delete the entire block from:
```
{# PANEL: HARTA (s12, internal 8/4) #}
<div class="panel s12" id="harta">
```
through the matching closing `</div>` and blank line (currently lines 1272-1300).

- [ ] **Step 6d.2: Remove the Amprente județene panel**

Delete the entire block from:
```
{# PANEL: AMPRENTE JUDEȚENE (s12, internal 3-col) #}
<div class="panel s12">
```
through the matching closing `</div>` and blank line (currently lines 1302-1355).

- [ ] **Step 6d.3: Remove the Semnături + Curiozități panels**

Delete the entire block from:
```
{# PANEL: SEMNĂTURI REGIONALE (s6) + CURIOZITĂȚI UNICE NAȚIONALE (s6) #}
<div class="panel s6">
```
through the closing `</div>` of the curiozitati panel (currently lines 1357-1387).

- [ ] **Step 6d.4: Remove the Section 6 D3 JS block**

Delete the entire block from:
```
{# JavaScript for Section 6 (D3 choropleth) #}
<script>
```
through the matching closing `</script>` tag (currently lines 1607-1741).

Keep the `{# JavaScript: flat cloud render — both panels share the județ filter #}` script block — it still populates the nav `<select>` with options.

- [ ] **Step 6d.5: Rebuild and check for errors**

```bash
source ~/devbox/envs/240826/bin/activate
python3 build_site.py --variant default --db data/streets.db 2>&1
```

Expected: `→ dist/index.html  (NNN KB)` with no errors. File should be noticeably smaller than before (D3 JS block removed).

---

## Task 7: Run All Tests and Verify

- [ ] **Step 7.1: Run full test suite**

```bash
source ~/devbox/envs/240826/bin/activate
python3 -m pytest tests/test_build.py -v 2>&1
```

Expected: all tests pass. Specific tests to confirm:
- `test_section6_in_index_for_select` — PASS (DATA_S6 present, s2-judet-select present, id="harta" absent, s6-map absent)
- `test_judete_overview_builds` — PASS (judete page has map, table, amprente data, top-cities section)
- `test_judete_lista_builds` — PASS
- `test_default_is_cluster_cloud` — PASS (id="harta" absent)
- All other previously-passing tests — PASS

- [ ] **Step 7.2: Serve locally and verify visually**

```bash
python3 build_site.py --variant default --db data/streets.db --serve --port 8001
```

Check:
- Landing: nav has județ select at right; cloud panels filter on change; no harta panel below
- `http://localhost:8001/judete/`: map renders, table is sortable, amprente bars show, curiozități present, top cities link to UAT pages
- `http://localhost:8001/judete/lista/`: alphabetical UAT list with "← Înapoi la overview județe" link

- [ ] **Step 7.3: Final commit**

```bash
git add templates/index.html.j2 tests/test_build.py
git commit -m "feat: move județ selector to navbar; add /judete/ overview page

- Selector always visible in sticky dark navbar
- Landing page now national-only: harta, amprente, semnături, curiozități panels removed
- /judete/ has map + sortable table + amprente + semnături + top cities
- /judete/lista/ preserves full 676-UAT alphabetical list"
```
