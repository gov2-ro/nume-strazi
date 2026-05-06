# Cum ne numim străzile — Design Spec
**Date:** 2026-05-05  
**Status:** Draft — awaiting user review of mockups before implementation plan

---

## 1. Product summary

A Romanian-language interactive publication exploring how Romania names its streets. Source: the Permanent Electoral Authority's polling-section registry (~140k rows, 41 județe + Bucharest sectors). Output: a single static `index.html` built by a Python script, with embedded JSON data and CDN-loaded chart/map libraries.

**Aesthetic target:** The Pudding / Bloomberg Graphics — editorial scrolling, embedded interactives, minimal chrome. Not a dashboard.

---

## 2. Design system

### Palette — "Os & cerneală"

| Token | Hex | Usage |
|---|---|---|
| `--bg` | `#FAF8F3` | Page background, card backgrounds |
| `--ink` | `#15171A` | Body text, headings, active chip bg |
| `--muted` | `#6E6E70` | Captions, labels, secondary text |
| `--rule` | `#DDDCD7` | Dividers, card borders, input borders |
| `--wash` | `#EEEAE0` | Bar chart track, tag backgrounds, subtle fills |
| `--accent` | `#C04F35` | Single accent: hero numbers, chart highlights, callout borders |

One accent color only. Never use accent on two elements in the same visual region.

### Typography

| Role | Font | Size | Weight | Notes |
|---|---|---|---|---|
| Display headline | Source Serif 4 | 42–56px | 500 | `letter-spacing: -0.012em` |
| Section heading | Source Serif 4 | 32–42px | 500 | |
| Card heading | Source Serif 4 | 20–26px | 500 | |
| Body / lede | Source Serif 4 | 17–19px | 400 | `font-style: italic; color: var(--muted)` |
| Chart names | Source Serif 4 | 14–17px | 400 | Upright |
| Kicker / label | Inter | 10–11px | 500 | `letter-spacing: 0.14–0.18em; text-transform: uppercase` |
| UI (chips, tags) | Inter | 11–13px | 400/500 | |
| Caption / source | Inter | 11px | 400 | `color: var(--muted)` |

Google Fonts import:
```
https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400;1,8..60,500&family=Inter:wght@400;500;600&display=swap
```

Diacritics tested: `ă â î ș ț Ă Â Î Ș Ț — Învățător Constanța`. Source Serif 4 passes.

### Spacing rhythm

- Section padding: `64px 80px 48px` (desktop); `48px 24px 36px` (mobile)
- Max content width: `1200px`, centered
- Section dividers: `1px solid var(--rule)`
- Kicker–headline gap: `22px`
- Headline–lede gap: `20px`
- Lede–content gap: `40–48px`

### Chart rules

- Direct labeling over legends wherever practical
- Bar track: `var(--wash)`, 6px height, 1px radius
- Highlighted bar: `var(--accent)` at 60–75% opacity; others `var(--ink)` at 30–45% opacity
- Women's bars in people charts: `var(--accent)` at 50% opacity (distinguishes from male top bar)
- Numbers: Romanian thousands separator (`.` not `,`): `12.847`
- Source row: `border-top: 1px solid var(--rule)`, `padding: 14px 80px`, space-between

---

## 3. Information architecture

8 sections, single-page, deep-linkable via `#anchor`. Top nav always visible.

| # | Anchor | Title | Hero element |
|---|---|---|---|
| 1 | `#acasa` | Acasă | Headline stat (99/100) + top 5 men vs women comparison |
| 2 | `#cele-mai-intalnite` | Cele mai întâlnite | Searchable ranked list with bars |
| 3 | `#pe-cine-onoram` | Pe cine onorăm | 100-square gender gap + top-20 tower chart |
| 4 | `#recunoastere` | Recunoaștere | 3-tier recognition cards + pageviews chart |
| 5 | `#tematica` | Tematică | CSS donut + category legend + drill-downs |
| 6 | `#harta` | Harta României | Choropleth + județ fingerprint panel |
| 7 | `#renumiri` | Renumiri | Before/after gallery + reciclare semantică |
| 8 | `#curiozitati` | Curiozități | CIORANI hero + 3 curiosity cards |
| — | — | Footer | Despre date · surse · download |

---

## 4. Component inventory

### Navigation
- Fixed top bar, `background: var(--bg)`, `border-bottom: 1px solid var(--rule)`
- Brand: `"Cum ne numim străzile"`, Inter 600, uppercase, `letter-spacing: 0.12em`
- Nav links: Inter 11.5px, `color: var(--muted)`, active: `color: var(--ink)`, `font-weight: 500`

### Chip toggles (metric switcher / filter)
```css
.chip { padding: 5–6px 12–14px; border: 1px solid var(--rule); border-radius: 999px; }
.chip.active { color: var(--bg); background: var(--ink); border-color: var(--ink); }
```

### Ranked list row
`grid-template-columns: 36px 1fr 220px 56px` — num | name+tag | bar | count

### Bar chart row (tower/people)
`grid-template-columns: 180–200px 1fr 50–54px` — name | bar | count

### Recognition tier card
Three equal columns in a 1px-gap grid. Dark card (`background: var(--ink)`) = highlight tier (Universal). Others on `var(--bg)`.

### Before/after rename card
Stack: old-name header → arrow+badge divider → new-name body. Special "reciclare semantică" card spans full width, `border-color: var(--accent)`.

### CIORANI hero
Full-width, `display: grid; grid-template-columns: 1fr auto`. Big number (`112px`, accent color) on the right. Narrative text on the left.

### Tooltip (map)
`background: var(--ink); color: var(--bg)`. Arrow via rotated 12px square at bottom-left. Min-width 180px.

### Source row
Every section ends with: `font-family: Inter 11px; color: var(--muted); border-top: 1px solid var(--rule); padding: 14px 80px; display: flex; justify-content: space-between`.

---

## 5. Section-by-section notes

### Section 1 — Acasă
- `<h1>` with `<span class="accent">99 din 100</span>` prefix
- Two-column compare: top 5 men (dark stat) vs top 5 women (accent stat)
- List rows: rank number + name + count, `border-bottom: 1px solid var(--wash)`
- Scroll cue: centered Inter uppercase with `↓` in accent

### Section 2 — Cele mai întâlnite
- Prominent search input (full-width, Source Serif 4 body size)
- Filter chips for all 41 județe + Bucharest — show 6, collapse rest
- "Principală excluded" callout with left `3px solid var(--accent)` border
- Tags on each row: `persoană` (warm bg), `natură`, `concept`, `dată` (all on `var(--wash)`)
- Bars normalized to rank-2 (Eminescu = 100%); Principală excluded from scale

### Section 3 — Pe cine onorăm
- 10×10 grid: 99 `var(--ink)` squares + 1 `var(--accent)` square — use CSS grid, 18px squares, 3px gap
- Gender gap stat: `72px / 40px` two-size number display
- Tower chart: women's entries get `var(--accent)` bar + `•` dot after name
- Bottom mini-charts: two columns, bars at 160px wide, 5px height

### Section 4 — Recunoaștere
- Tier cards: 3-col grid with 1px background gap (so dividers render as lines)
- Highlighted tier (Universal): `background: var(--ink)`, white text, accent badge
- Pageviews: first column (`var(--accent)` bars) = Universal tier; rest = `var(--ink)` at low opacity
- Tier badge pill at end of each row in pageviews list

### Section 5 — Tematică
- Donut: CSS `conic-gradient`, 260px, 140px hole. Center: `"142k / adrese total"`
- Legend: each row = colored swatch + category name (large) + % (right-aligned large Inter) + sub-description
- Nature drill: bars in `#A0826A` at varying opacity
- Ideo tokens: pill cloud; hot tokens (>100 occurrences) get accent border + warm fill

### Section 6 — Harta
- Two-column grid: `1.6fr 1fr`, gap `56px`
- Map: real D3 + TopoJSON from `data/gis/romania-counties.geojson` (county level) or `ro-uats.topojson`
- Color scale: `#F4EFE6 → #E8B299 → #D27A5C → #A53A22` (4-stop warm ramp)
- Bucharest inset: `position: absolute; right: 14px; bottom: 24px`, 130px wide
- Fingerprint panel: most-distinctive TF-IDF tokens (5 items, color-ranked) + most-frequent + deviations

### Section 7 — Renumiri
- Count stats row before filter chips (3 numbers with rules)
- Card grid: 2-column, gap 24px; special card spans both
- Substitution type badges: `Ideologic` = dark pill; `Persoană` = warm pill; `Reciclare` = accent pill
- Reciclare semantică card: 3-col body showing old → new pairs with `color: var(--accent)` arrows

### Section 8 — Curiozități
- CIORANI `218` at `font-size: 112px`, `color: var(--accent)` — the largest number in the publication
- Three supporting cards in a 3-column grid
- Longest names: stack at decreasing sizes (22px → 18px → 16px) to imply rank by length
- Animal contest: same pattern as tower chart, bars 70px wide
- Locally-honored: colored dot `•` before each name, Inter 11px context text below

---

## 6. Data requirements per section

| Section | DB queries needed | Notes |
|---|---|---|
| 1 Acasă | top 5 persons by gender, total classified persons by gender | Static — rarely changes |
| 2 Cele mai întâlnite | top 50 `name_normalized` by count nationwide; same per județ | Exclude numeric streets |
| 3 Pe cine onorăm | persons with gender + street count; profession/era distributions | Needs gender curation (P2) |
| 4 Recunoaștere | persons with wiki_sitelinks, wiki_scope, wiki_ro_views, wiki_ro_url | Already in DB |
| 5 Tematică | name_categories distribution; nature subtypes; ideological tokens | Needs category coverage |
| 6 Harta | per-județ stats: total streets, % female, % saint, % numeric, modal name, TF-IDF top 5 | TF-IDF needs computing |
| 7 Renumiri | renamed streets with old/new names, substitution type | Data source TBD |
| 8 Curiozități | CIORANI (Prahova numeric streets), longest names, animal street names, 1-UAT persons | Several sub-queries |

---

## 7. Static build architecture

### Stack
- **Build:** `build_site.py` (Python 3.11, stdlib + Jinja2 + sqlite3)
- **Charts:** Observable Plot 0.6 (CDN `cdn.jsdelivr.net/npm/@observablehq/plot`)
- **Maps:** D3 7 + TopoJSON 3 (CDN)
- **Fonts:** Google Fonts CDN (preconnect in `<head>`)
- **Output:** `dist/index.html` — single file, data embedded as JSON in `<script>` tags

### Build flow
```
build_site.py
  ├── Query streets.db for each section's data
  ├── Serialize to JSON (compact)
  ├── Render Jinja2 template → dist/index.html
  └── Copy static assets (GIS TopoJSON) → dist/
```

### File layout
```
dist/
  index.html          ← single output file
  ro-counties.topojson← county outlines for choropleth
templates/
  index.html.j2       ← Jinja2 master template
  sections/           ← one partial per section (optional)
build_site.py         ← entry point
```

### Performance targets
- Initial paint: <2s broadband
- Data for sections 1–3 embedded inline (always needed)
- Sections 4–8 data lazy-loaded on scroll via `IntersectionObserver`
- TopoJSON loaded async; map renders after first scroll to section 6

---

## 8. Open questions (resolve before implementing)

1. **GIS file for choropleth:** `data/gis/romania-counties.geojson` exists. Is it at the right level (județ) for the map? Confirm coordinate system.
2. **Renaming data source:** Renamings not yet in DB. Is there an external source or should section 7 be deferred?
3. **TF-IDF for regional fingerprints:** Not pre-computed. Needs a `build_db.py` step or done at build time in `build_site.py`.
4. **Gender curation coverage:** Current coverage of women in curated `persons` may undercount — affects section 3 accuracy.
5. **Pagination/search in section 2:** For full 50-item list, implement as pure CSS/JS (no server). Confirm OK.
