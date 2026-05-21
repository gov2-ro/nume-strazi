# Design: SVG Icons + Wikipedia Links

**Date:** 2026-05-21  
**Scope:** Replace structural emoji with inline SVG icons; add Wikipedia ro links to all person detail pages that have a Wikidata QID.

---

## 1. SVG Icons

### Goal

Replace ~22 structural `<span class="emo SIZE">EMOJI</span>` usages (panel headers, section labels, kicker chips on detail pages) with `<svg class="icon SIZE"><use href="#icon-NAME"/></svg>` references backed by an inline SVG sprite. Row-level per-category emoji (nature subtypes, professions, eras, contest families, JS `ERA_EMO`/`PROF_EMO` maps) are out of scope — they stay as emoji.

### Icon library

**Lucide** — stroke-only, no fill, same visual language as the existing `.icon` CSS class (`stroke: currentColor; fill: none; stroke-linecap: round; stroke-linejoin: round`). Paths are copied verbatim from the Lucide 0.468 SVG source; no npm dependency needed.

### Sprite approach

New partial `templates/_icons.html.j2` — a single `<svg style="display:none" aria-hidden="true">` block containing `<symbol id="icon-NAME" viewBox="0 0 24 24">` entries for every icon in the mapping below. Included via `{% include '_icons.html.j2' %}` near the top of:

- `templates/index.html.j2` (after `<body>`)
- `templates/_detail-shell.html.j2` (after `<body>`)

No other templates need it directly (detail pages and theme/explorer pages all extend `_detail-shell.html.j2`).

### CSS

The existing `.icon` size variants already cover all structural usages (`sm`, `lg`, `xl`, default). No CSS changes needed.

### Icon mapping

| Symbol ID | Lucide icon | Replaces | Used in |
|-----------|-------------|----------|---------|
| `icon-list-ordered` | `list-ordered` | 🔝 | Cele mai frecvente (panel label) |
| `icon-users` | `users` | 👥 / ⚥ | Top persoane, Gen filter, Ecart de gen |
| `icon-user` | `user` | 👤 | Persoană kicker |
| `icon-pie-chart` | `pie-chart` | 🧭 | Repartiție tematică |
| `icon-leaf` | `leaf` | 🌿 | Subtipuri Natură (panel), Natură kicker |
| `icon-flag` | `flag` | 🚩 | Tokeni ideologici (panel), Ideologic kicker |
| `icon-graduation-cap` | `graduation-cap` | 🎓 | Profesia |
| `icon-hourglass` | `hourglass` | ⏳ | Epoca |
| `icon-globe` | `globe` | 🌍 / 🌐 | Personalități non-române, Naționalitate |
| `icon-star` | `star` | 🌍 (Wikidata) | Recunoaștere globală Wikidata panel |
| `icon-pencil-line` | `pencil-line` | 📝 | Renumiri |
| `icon-swords` | `swords` | 🏟️ | Conteste tematice |
| `icon-file-text` | `file-text` | 📄 | Despre date |
| `icon-flask-conical` | `flask-conical` | ⚗️ | Metodologie |
| `icon-terminal` | `terminal` | ⌨️ | Cod sursă |
| `icon-bar-chart-2` | `bar-chart-2` | 📊 | Scară (group-label), Comparație județe |
| `icon-tag` | `tag` | 🏷️ | Tematică (group-label), Teme kicker |
| `icon-trophy` | `trophy` | 🏆 | Cei mai des onorați |
| `icon-church` | `church` | ⛪ | Religios kicker |
| `icon-calendar` | `calendar` | 📅 | Dată kicker |
| `icon-map-pin` | `map-pin` | 📍 | Stradă kicker |
| `icon-home` | `home` | 🏘️ | Localitate kicker |
| `icon-map` | `map` | 🗺️ | Harta județe (kicker + panel label) |
| `icon-dna` | `dna` | 🧬 | Amprenta județului |
| `icon-gem` | `gem` | 💎 | Cele mai exclusiviste |
| `icon-wheat` | `wheat` | 🌾 | Cele mai «rurale-poetice» |
| `icon-scroll` | `scroll` | 📜 | Semnături regionale |
| `icon-search` | `search` | 🔎 | Curiozități unice |
| `icon-building-2` | `building-2` | 🏙️ | Cele mai mari localități |

### Usage pattern

```html
<!-- Before -->
<span class="emo xl">🌿</span>

<!-- After -->
<svg class="icon xl" aria-hidden="true"><use href="#icon-leaf"/></svg>
```

For kicker lines that were inline text + emoji (e.g. `<span class="emo">👤</span> Persoană`), keep the surrounding markup unchanged — only swap the inner `<span class="emo">` for `<svg class="icon">`.

### Files changed

| File | Change |
|------|--------|
| `templates/_icons.html.j2` | **New.** Inline SVG sprite with 22 symbols. |
| `templates/index.html.j2` | Include sprite; replace ~20 structural `<span class="emo">` in panel labels and group-labels; add `.icon.xxl` to CSS. |
| `templates/_detail-shell.html.j2` | Include sprite. |
| `templates/person-detail.html.j2` | Replace 👤 kicker. |
| `templates/street-detail.html.j2` | Replace 👤 🌿 ⛪ 📅 🚩 📍 kickers. |
| `templates/uat-detail.html.j2` | Replace 🏘️ kicker and 👤 🌿 ⛪ 📅 🚩 📍 theme chips in the street list. |
| `templates/theme-detail.html.j2` | `{{ theme_meta.emoji }}` kicker is a dynamic per-theme emoji from data — leave as `.emo`. No change. |
| `templates/persons-index.html.j2` | Replace 👤 kicker. |
| `templates/themes-index.html.j2` | Replace 🏷️ kicker; `type_emo` and `t.emoji` in section headers/rows are data-driven — leave as `.emo`. |
| `templates/judete-index.html.j2` | Replace ~9 structural panel-label and kicker emojis (🗺️ 🧬 📊 💎 🌾 🚩 📜 🔎 🏙️ 🔝 👤). |

---

## 2. Wikipedia Links

### Goal

Show a "↗ Wikipedia română" link on every person detail page where `wikidata_qid` is set, not just the 32/206 where `wiki_ro_url` is already populated in the DB.

### Approach

Template-only change in `person-detail.html.j2`. Derive a fallback URL from the QID when `wiki_ro_url` is NULL:

```jinja2
{% set wiki_ro = p.wiki_ro_url or
   ('https://www.wikidata.org/wiki/Special:GoToLinkedPage/rowiki/' ~ p.wikidata_qid
    if p.wikidata_qid else none) %}
<div style="margin-top:10px; font-size:12px; color:var(--muted);">
  {% if wiki_ro %}
    <a href="{{ wiki_ro }}" target="_blank" rel="noopener">↗ Wikipedia română</a>
  {% endif %}
  {% if p.wikidata_qid %}
    {% if wiki_ro %} · {% endif %}
    <a href="https://www.wikidata.org/wiki/{{ p.wikidata_qid }}" target="_blank" rel="noopener">Wikidata {{ p.wikidata_qid }}</a>
  {% endif %}
</div>
```

`Special:GoToLinkedPage/rowiki/{QID}` is a stable Wikidata feature that redirects to the Romanian Wikipedia article for the given entity, or returns a "not found" page if no ro sitelink exists. No HTTP request at build time; the redirect happens in the user's browser.

### Files changed

| File | Change |
|------|--------|
| `templates/person-detail.html.j2` | Replace the `wiki_ro_url` conditional block with the `wiki_ro` fallback pattern above. |

### Out of scope

- `persons-index.html.j2` — list page, external links would clutter it.
- Running `wiki_scope.py` to populate more `wiki_ro_url` DB rows — separate task.

---

## Acceptance criteria

1. Build completes without errors: `python3 build_site.py --variant all --detail`.
2. No `.emo` spans remain inside `<span class="panel-label">` or `<div class="kicker">` elements.
3. Every rendered panel header in `dist/index.html` contains an `<svg class="icon">` element.
4. Person detail pages for persons with QIDs show a "↗ Wikipedia română" link.
5. Person detail pages for persons without QIDs show no Wikipedia link.
6. Row-level category emojis (profession bar rows, era bar rows, nature sub-type rows) are unchanged.
