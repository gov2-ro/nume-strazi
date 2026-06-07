# Activity History

## 2026-06-07 — Geographic-ego + lifecycle panels (quirky batch, existing data)

New `site_queries.section_geo(conn)` + three landing panels, all from `persons.birth_judet`/`birth_year` already in the DB (no new Wikidata pulls). Deduplicated by `full_name` so a person's alias-forms (Cuza ×4) count once.

**`section_geo()`** — one per-honoree aggregate (103 honorees with a resolved birth-județ: total national streets, județ reach, streets in birth-județ), then:
- **forgotten_at_home** — ≥10 national streets but ≤5% in the birth județ. Reframed editorially: this is the *dilution* effect, not literal neglect. Eminescu: 300 streets nationwide, only 7 (2.3%) in Botoșani — roughly the 1/42 baseline. The genuinely under-honored: Cantemir (0.7% in AG), Mihai Viteazul (0.8% in IL), Ana Ipătescu (0 in B).
- **most_exported** — național-street total of all honorees born in each județ. BT exports ~490 streets via just 4 honorees (Eminescu + Iorga); IS 493 via 9; B 531 via 13.
- **most_parochial** — honorees with streets ≥concentrated in one județ (≥8 total). Local heroes: Ioan Suciu 75% in AR, Hungarian figures (Orbán Balázs, Gábor Áron) in Harghita, voievozi in Suceava. `is_native` flag marks those honored in their own birth-județ (e.g. Ion Nistor SV). Tie-on-max-județ rows deduped to one per person in Python.

**Birth-century** panel surfaces the already-computed `section_quirky.century_rows` (no new query) — sec. XIX dominates massively (208 persons / 7,697 streets, the 1848 generation); sec. I = Decebal & Traian (173 streets, 1 "person"-pair).

**Blocked picks (noted, not built):** literal "honored-while-alive" needs street-naming dates (not in registry); "died-in-exile" needs place-of-death (Wikidata P20, not pulled — only P19 birthplace is). A "born outside present borders" substitute is possible (25 honorees with `birth_place_label` set but `birth_judet` NULL — Babeș/Viena, Asachi/Herța, Russo/Chișinău) but P19 has visible mismatches (Vasile Lupu→Chester, Magheru→Birmingham) so it was skipped to avoid surfacing bad data. See BACKLOG.

**Template** (`templates/index.html.j2`): `#secole-nastere`, `#geografia-gloriei` (two sub-sections), `#eroi-locali`. Wired `section_geo` into `build_site.py`. Build verified; all ids present with real data.

## 2026-06-07 — Lexical quirks + frequency anomalies (quirky batch, existing data only)

New `site_queries.section_lexical(conn)` + four landing-page panels. Zero new data — pure SQL over `streets_dedup` (non-numeric names) plus Python post-processing. `get_connection` doesn't register a `regexp` shim, so all matching is `substr`/`LIKE` in SQL or Python `re` after the fetch.

**`section_lexical()`** pulls one distinct-name aggregate (29,737 non-numeric names with street/UAT counts) plus a `(name_normalized, judet)` presence list, then derives:
- **first_letters** — A–Z distribution of distinct names (C dominates at 3,282; diacritics fold to base letter since `name_normalized` is ASCII).
- **palindromes** — `core(name)` (alphanumerics only) ≥5 chars and equal reversed. Filtered out enumerator artifacts (`A III-a`, `A XIX-a`) via `^a [ivxlcdm]+-?a?$`. 8 real ones: Sebeș (7 str.), Anina (6), Salaș, Ciric, Laval, Potop, Seles, Somoș.
- **longest / shortest** — char-length extremes. Longest excludes raw road-segment descriptions (`\bkm \d|^d[njc]\s?\d`) so highway rows like "DN65A de la km 100+900…" drop out; top is "Florin Popescu - Campion Olimpic Sydnei 2000" (44 ch.). Shortest restricted to single-token alphabetic words ≥3 ch (Tei, Olt, Iza, Dej…) so single-letter block-streets don't dominate.
- **prepositional** — first token in a locative-preposition set (la/sub/peste/după/între…); 517 names / 662 streets. "Reads-as-a-sentence" rural toponymy: Peste Vale (13), Sub Coastă (13), Pe Vale, După Grădini.
- **near_universal / universal_count** — per-name județ set vs all 42. 19 names in every județ; 22 in exactly 41/42, each tagged with its single holdout județ. București is the most common holdout (absent from rural flower/tree lists — Trandafirilor −B, Morii −B, Stadionului −B), which is itself the editorial point.
- **singletons** — 22,687 names (76.3%) exist in exactly one UAT nationwide (shown as a caption stat).

**Template** (`templates/index.html.j2`): four new `s6` panels before the contests panel — `#abecedar` (flex bar strip, new inline CSS), `#curiozitati-lexicale` (palindrome/shortest chips + longest list), `#nume-propozitii` (rank-row bars), `#nume-universale` (name + holdout-județ + street count). Reused existing `.panel`/`.sub-section`/`.rank-row`/`.bar-wrap` patterns. Wired `section_lexical` into `build_site.py` context. Icons reused: list-ordered, search, map-pin, globe. Build verified; all four ids present with real data in `dist/index.html`.

## 2026-05-26 — Gender km gap + association rules / national canon

**Gender km gap panel (`#gender-km-gap`, s6).** New `gender_km` and `female_km_list` keys in `section_quirky()`. Proportional bar (F 2.5% / M 97.5%) + comparison table (km total, km per honoree, avg street length, honoree count) + female leaderboard with portraits. Headline: female honorees command 2.5% of total person-street km despite making up 4.9% of honorees; female streets are on average 19% shorter than male streets (575m vs 708m). Two new named queries added: `gender_km_gap`, `female_km_leaderboard`.

**Association rules / national canon panel (`#canon-associations`, s6).** Computed entirely in Python inside `section_quirky()` — no extra SQL beyond a `GROUP BY (full_name, siruta)` presence matrix. Deduplicates aliases by `full_name` before computing so Cuza's four name-forms count as one. Canon set (≥30% of 668 UATs with person streets): 11 names from Eminescu (62.9%) down to Decebal (30.5%). Surprising pairs ranked by lift (co_uats / (support_a × support_b × n_uats)): top pairs at lift ×9.0 (Theodor Aman + Ștefan Luchian — painters), ×8.18 (Ady Endre + Petőfi Sándor — Hungarian duo), ×7.67 (Ion Neculce + Miron Costin — 17th-c Moldavian chroniclers), ×7.46 (Gheorghe Șincai + Petru Maior — Transylvanian School). Top-3 canon names excluded from pair list to surface non-obvious associations. Min support: 5% of UATs (≥33 UATs).

## 2026-05-26 — Cuza QID fix + biographical lifecycle stats (Pick A)

**Cuza QID regression (data integrity fix).** Four `core_name_norm` aliases for Alexandru Ioan Cuza (`a. i. cuza`, `cuza voda`, `al. i. cuza`, `alexandru Ioan cuza`) were either missing from `data/curation/wikidata_qids.csv` or carrying Michel Vorm's QID `Q208518` from a prior bad auto-match. Fixed: all four entries added to CSV with `Q294832`; uniqueness guard in `tools/wikidata_persons.py` updated to allow same-`full_name` aliases to share a QID (previously the guard blocked any QID already held by *any* other key, which made it impossible to have multiple name-forms for one person — now it only blocks *cross-person* collisions by checking `full_name !=`). Also added a propagation UPDATE to `tools/wiki_birthplace.py` that runs after every live-fetch pass: copies `birth_place_qid/label/birth_judet` from any resolved alias to all other aliases sharing the same QID (correlated subquery, idempotent). Bârlad/VS correctly propagated to all four Cuza aliases.

**`tools/wiki_biostats.py` (new).** Fetches Wikidata P509 (cause of death), P569 (birth date), P570 (death date) for all 232 unique QIDs. Deduplicates by QID before fetching — same-person aliases don't generate redundant API calls. Propagates results to all aliases sharing a QID after writes. CSV audit trail at `data/curation/wikidata_biostats.csv`; `--replay-csv --force` for rebuild persistence. Result: 43 of 243 QID persons now have a cause-of-death label; 236/243 have birth year; 241/243 have death year.

**New schema columns.** Added `cause_of_death_qid TEXT`, `cause_of_death_label TEXT` to `persons` in `build_db.py` and applied via `ALTER TABLE` to the live DB.

**Three new named queries in `docs/queries.sql`:** `age_at_death`, `cause_of_death_breakdown`, `birth_century_distribution`.

**`section_quirky()` extended.** Two new sub-sections: (1) age-at-death analysis — deduplicates by `full_name`, computes weighted average (58.0 years per street), produces "forever young" list (died < 40) sorted by street count; (2) cause-of-death macro breakdown — raw Wikidata labels bucketed into `boală` / `violență` / `accident` / `altele` / `necunoscută` in Python using keyword matching; (3) birth-century distribution as `century_rows` (available to templates, not yet displayed as a panel).

**Two new landing-page panels.** `#young-dead` (s6): top-10 honorees who died before 40, with portrait thumbnails and dates, sorted by street count — Eminescu leads at 431 streets, died 39. `#cause-of-death` (s6): macro-category bars for boală/violență/accident/necunoscută; footnote shows ~18% P509 coverage of QID holders. `heart-crack` icon added to Lucide sprite; `tools/fetch_lucide_icons.py` updated.

**Notable editorial findings:** 30 illness deaths vs 9 violent deaths (street-weighted: 1587 vs 546 streets for illness). "Violență" covers executions (Vlad Țepeș, Horia/Cloșca/Crișan), assassination (Iorga, Grozăvescu), and historically famous poisonings (Lăpușneanu). Tuberculosis alone accounts for 6 persons including Porumbescu (30 y.o.) and Panait Istrati.

## 2026-05-23 — "Quirky stats" round 1: km per honoree, prestige hierarchy, self-honor index

Brainstormed (`docs/BACKLOG.md` line 146, *"go wild, nerdy, quirky"*) and locked in two starter picks: OSM-based real-estate framing of honor (Pick B) and a Wikidata-driven self-honor index (Pick C). Pick A (cause-of-death breakdown) deferred.

**Data layer.** Added two named queries to `docs/queries.sql`: `total_km_per_honoree` (joins `streets_dedup ↔ street_osm_matches ↔ osm_streets`, sums `length_m` per `core_name_norm`) and `highway_class_by_category` (same join, grouped by macro-classification × OSM `highway_class`). Added `self_honor_per_judet` and `most_parochial_honorees`. OSM pipeline (`osm_ingest` → `osm_match` → `osm_score`) was empty after a prior rebuild — replayed end-to-end; 52.2% registry coverage restored.

**Birthplace pipeline (Pick C).** New `tools/wiki_birthplace.py` fetches Wikidata P19 for the 206 persons with QIDs, walks the P131 chain to land them in a Romanian județ when possible. Result: 133 birth places resolved, 106 inside a Romanian județ. CSV audit trail at `data/curation/wikidata_birthplaces.csv` with `--replay-csv` for build_db rebuild persistence. Two gotchas worth a note: (1) Wikidata's `P31` for counties is `Q1776764` (not the more obvious `Q15947`, which is the older/secondary typing — both accepted now). (2) Action-API endpoint was 429-rate-limited; the SPARQL endpoint is in worse shape (HTTP 429 with explicit "WDQS outage" message), so the tool avoids SPARQL entirely and discovers județe inline during the P131 walk by matching `Q1776764/Q15947` + label.

**Site wiring.** New `site_queries.section_quirky()` returns `top_km` (top-20 leaderboard), `class_by_category` (bucketed into 4 prestige tiers: principale / intermediare / rezidențiale / altele — to make the stacked bar legible), and `self_honor_top` / `self_honor_bottom` (top-5 + bottom-5 with `known_birth_streets >= 20` floor so rural județe with single-digit denominators don't sit at the extremes). Extended `section6` with `self_honor_pct` so the existing `/judete/` choropleth can display it.

Three new panels added to `templates/index.html.j2` (km leaderboard, prestige hierarchy bars, self-honor top/bottom). New chip `onorează localii` on `templates/judete-index.html.j2`. Verified visually via Chrome DevTools MCP — Harghita 31.4% leads the self-honor map; Ștefan cel Mare leads the km board at 320 km, ahead of Tudor Vladimirescu (291) and Eminescu (262). Prestige-hierarchy hypothesis confirmed: nature streets are ~95% residential km, while person streets get ~26% primary+secondary share.

**Schema.** Added `birth_place_qid`, `birth_place_label`, `birth_judet` to `persons` in `build_db.py`. Brainstorm catalog (35+ candidate stats across 7 themes) saved at `/Users/pax/.claude/plans/let-s-touch-the-go-structured-taco.md` for future picks.

**Coverage caveats logged in panel captions:** km totals under-count because OSM matches cover only 52% of registry streets (ranking is stable); self-honor denominator is "person-streets with known birth-județ" (only ~50% of QID-holding persons resolve to a Romanian județ, so foreign-born and unknown-birth honorees drop out cleanly).

**Found-not-fixed.** `core_name_norm` rows `a. i. cuza` and `cuza voda` are mapped to Michel Vorm's QID (IJsselstein NL) — same regression flagged in BACKLOG's QID uniqueness guard item that didn't survive the last rebuild. Added a BACKLOG note with the replay-CSV remediation path.


## 2026-05-21 — SVG icons + Wikipedia links

Replaced all structural emoji (panel headers, kicker chips) with Lucide inline SVG icons; added Wikipedia fallback links to person detail pages.

**SVG sprite** (`templates/_icons.html.j2` new, `tools/fetch_lucide_icons.py` new): fetched 29 Lucide 0.468.0 icons from GitHub CDN, stripped redundant inline attributes, rendered as an inline `<svg style="display:none">` sprite with `<symbol>` definitions. The fetch script discovered three icon renames in 0.468.0 vs the spec: `pie-chart → chart-pie`, `bar-chart-2 → chart-bar-big`, `home → house`.

**Template wiring** (`_detail-shell.html.j2`, `index.html.j2`): added `.icon` CSS size variants (default 14px, `.sm`, `.md`, `.lg`, `.xl`) to both parent templates; included sprite partial after `<body>` in each.

**Icon replacements** (20 swaps in `index.html.j2`; kicker swaps in `person-detail`, `street-detail`, `uat-detail`, `persons-index`, `themes-index`; 9 panel-label + 6 kicker swaps in `judete-index`): row-level per-category emojis (nature subtypes, professions, eras) left unchanged as `.emo`.

**Wikipedia links** (`person-detail.html.j2`): replaced `wiki_ro_url`-only conditional with a two-tier fallback — if `wiki_ro_url` is NULL but `wikidata_qid` is set, derives a link via `Special:GoToLinkedPage/rowiki/{QID}` (stable Wikidata redirect, no HTTP at build time). All 206 persons with QIDs now show a "↗ Wikipedia română" link.

Post-review cleanup: restored `fill="currentColor"` on `icon-tag` circle (the strip regex incorrectly removed it); removed dead `contest_emoji` Jinja2 dict from `index.html.j2`.

## 2026-05-20 — Shipped product quality (P2): DB trim, browser perf, stats bar, keyboard nav

Four related improvements to the live product:

**DB trim** (`tools/build_dist_db.py`): replaced the shallow "drop 3 tables + VACUUM" approach with full materialization. The `streets_dedup` view is now written as a real table containing only the 11 columns actually referenced by `db-client.js`; the original `streets` table (127k rows, includes `artera_raw`, `id`, etc.) and the view are dropped. Also drops `streets_classified_pct`. Result: dist/streets.db shrinks from 30 MB → 13.5 MB (−59%).

**Browser perf** (`site_queries.py`, `build_site.py`, `dist/browser/index.html`): added `browser_export()` to `site_queries.py` — one aggregate SQL query that produces all 30k grouped rows with every filterable field, plus 12 meta queries for dropdown options. `build_site.py` writes this to `dist/browser/data.json` (~3 MB) on every standard build. The browser compact view now fetches this JSON on load and filters client-side in JS — no WASM, no SQL on initial load. Table view still loads WASM lazily on first switch to it.

**Live stats bar** (`dist/browser/index.html`): new `.stats-bar` strip below the result count showing top-3 classification types (%), gender split (F/M %), top profession, top era, top nationality for the current filter. Computed from the in-memory filtered rows synchronously on every filter change.

**Keyboard navigation** (`dist/browser/index.html`): `tabindex="0"` + `role="button"` on all 7 filter dropdown buttons; `tabindex="-1"` + `role="option"` on all `.fdd-item` elements (including the "Toate" clear option). `/` shortcut focuses search; Enter/Space opens dropdown; ArrowDown/Up navigates items; Escape closes and returns focus to the button; Escape in search blurs it.

## 2026-05-19 — Subfolder hosting: JS link and portrait fixes

Previous `--base` work only covered Jinja2-rendered HTML. JS-generated links
(`/persoana/`, `/strada/`, `/tema/`) and portrait `img src` values inside JS
template literals were still hardcoded without the base prefix — broken when
served from a subfolder.

**Template fixes (`templates/index.html.j2`, `templates/_search_overlay.html.j2`):**
Added `const BASE = "{{ base }}";` (baked at build time) as a JS variable, then
replaced all bare absolute paths in JS with `${BASE}/persoana/`, `${BASE}/strada/`,
`${BASE}/tema/`, `${BASE}/portraits/`, `${BASE}/oras/`. The Jinja2 inline
`{{ base }}/…` pattern inside JS template literals was also replaced with
`${BASE}/…` for consistency. 6 paths fixed in `index.html.j2`, 2 in
`_search_overlay.html.j2`.

**Dev server fix (`build_site.py`):** Removed `/portraits/` from the
proxy-to-filter_server list. Portraits live in `dist/portraits/` as static
files; routing them to the (usually not running) `filter_server.py` caused 502
errors. They now fall through to `SimpleHTTPRequestHandler` like any other
static asset.

**Workflow clarification:** `--serve` rebuilds the site before starting the
server. The `--base` flag must be passed to both the build step and the serve
step — `--mount` alone is not enough. `--variant all` is also required to
rebuild `metodologie.html`; the default variant only rebuilds `index.html`.
Correct invocation:
```
python3 build_site.py --variant all --detail --base /nume-strazi
python3 build_site.py --variant all --serve --port 9000 --base /nume-strazi --mount /nume-strazi
```

Verified end-to-end with Playwright: all nav links, portrait images, JS-rendered
person/street/theme tokens, and search overlay results correctly prefixed with
`/nume-strazi/` on all page types (index, metodologie, UAT detail pages).

---

## 2026-05-19 — Subdirectory hosting (`--base /strazi`)

Made every page in the site servable from an arbitrary subpath. Two layers:

**Build-time prefix** for Jinja-rendered pages. `build_site.py` learned `--base` (default empty) and `--site-url` (default `https://strazi.gov2.ro`). Both are normalized and exposed as Jinja globals via `env.globals["base"]` / `env.globals["site_url"]`, so every template render picks them up without per-call wiring. Mechanical sed pass across `templates/*.j2` rewrote ~70 absolute paths (`href="/cauta/"`, `src="/portraits/…"`, `fetch('/cauta/streets.json')`, JS template literals like `\`/strada/${slug}/\``) to `{{ base }}/…`. Anchor links (`href="#…"`) left alone — they're page-local. `_meta.html.j2` recomposes `og:url` as `{{ site_url }}{{ base }}{{ og_url_path }}` and `og:image` likewise, so canonical URLs reflect the deployed subpath.

**Runtime base detection** for the three non-Jinja files (`dist/_assets/db-client.js`, `dist/browser/index.html`, `dist/filter/index.html`). `db-client.js` derives `SITE_BASE` from `document.currentScript.src` by stripping `_assets/db-client.js`; works at any mount with no rebuild. The two HTML pages use relative paths (`../_assets/db-client.js`, `../cauta/`, `../strada/${slug}/`) — same effect, no build flag needed.

**Local subdirectory testing.** `build_site.py --serve --port 9000 --mount /strazi` strips the mount prefix from incoming requests before serving from `dist/`, and returns 404 for any path outside the mount. Simulates a real Apache/Nginx subdirectory locally so we can verify the wiring without rsyncing to a host.

**Verified end-to-end in Chrome.**
- Default root build (no flag): regression check, 1121 KB landing renders with `/cauta/`, `/browser/`, etc. paths.
- Subdirectory build (`--base /strazi`): landing renders with 61 `/strazi/`-prefixed links, the `/strazi/browser/` page loads 30,089 unique names through sql.js-httpvfs reading `/strazi/streets.db` via Range requests, and a sample detail page (`/strazi/strada/mihai-eminescu/`) has 311 prefixed links + correct `og:url = https://strazi.gov2.ro/strazi/strada/mihai-eminescu/`.
- 404 sanity: `/cauta/` (outside `/strazi` mount) returns 404 as expected.

**Docs.** `README.md` gained a "Subdirectory deployment" subsection under "Web frontend"; `CLAUDE.md` lists the new build invocation.

---

## 2026-05-19 — Shared-host port: client-side SQLite via sql.js-httpvfs

The whole app now works on a vanilla static host (Apache/Nginx, no PHP, no Python). The two pages that needed live filter queries — `/browser/` and `/filter/` — were rewired to run the same SQL client-side against a shipped 30 MB SQLite file, fetched on demand over HTTP Range requests. `filter_server.py` stays for local Python testing but is no longer required to view the site.

**Slim DB.** `tools/build_dist_db.py` (new) copies `data/streets.db` → `dist/streets.db`, drops `osm_streets` + `street_osm_matches` (both 0 rows) and `street_aliases` (17k rows, not touched by the JS pages or `site_queries.py`), sets `PRAGMA page_size=4096` and `journal_mode=DELETE`, then VACUUMs. Result: 30 MB, −9% vs source. Idempotent.

**Vendored sql.js-httpvfs.** `dist/_assets/sqljs-httpvfs/{sql-wasm.wasm, sqlite.worker.js, index.js}` pulled from `unpkg.com/sql.js-httpvfs@0.8.12/dist/`. Checked in so deployment is just `rsync dist/ host:public_html/` — no build step, no CDN dependency. The UMD bundle attaches `createDbWorker` to `window` when loaded via `<script>`.

**Shared SQL client.** `dist/_assets/db-client.js` mirrors `filter_server.py` exactly: same `BASE_FROM`, `_SELECT_COLS`, `_SELECT_AGG`, `_CLS_MAP`, `_PERSON_COLS`, same `build_filter_query` conditional WHERE builder, same `_order_clause`. Exposes `window.DbClient.{meta, filter, getDb, normalize, slugify}`. `meta()` returns the same 13-key dict as `query_meta`; `filter(params)` accepts either `URLSearchParams` or a plain object (values may be `string | string[]` for multi-select) — that single shape covers `/browser/`'s single-select + `/filter/`'s multi-checkbox pattern. All SQL still goes through `?` placeholders. Adds `uat_slug` to non-aggregate rows (the `/filter/` table linked UATs via that field). The `normalize()` JS function mirrors `streets_lib.normalize_match()`: `î→a` first, then NFD + strip combining chars + lowercase — verified produces the same hashes for Romanian inputs.

**Page ports.** `dist/browser/index.html` — replaced the 3 `fetch('/api/...')` calls with `DbClient.meta()` and `DbClient.filter(URLSearchParams)`; removed the `const API = ''` indirection; `buildParams()` now returns the `URLSearchParams` directly instead of a string. `dist/filter/index.html` — same swap (`fetchResults` and the init block). Updated error copy from "Rulați: python3 filter_server.py" to a generic DB-load error. Both pages add `<script src="/_assets/db-client.js"></script>` to `<head>`.

**Dev-server Range support.** Python's `SimpleHTTPRequestHandler` doesn't honor `Range:` — it always returns the full file. `build_site.py --serve`'s `SiteHandler` (added earlier this session for API proxying) now implements partial-content responses: parses `bytes=start-end` (with suffix-byte support), seeks the file, returns 206 with `Content-Range` and `Accept-Ranges: bytes`, also handles 416 unsatisfiable ranges. Without this, sql.js-httpvfs pulls the whole 30 MB DB on every query during local dev. Apache/Nginx on the shared host handle this natively. Verified with `curl -H "Range: bytes=0-99"` — 206 + 100 bytes.

**Smoke-tested in Chrome.** Loaded `/browser/` — ~88 range requests against `streets.db` (only the SQLite pages touched by the meta queries + the aggregate compact query), 30,089 unique names rendered, top counts match Python server (Florilor 532, Trandafirilor 496, Mihai Eminescu 300). No JS errors. `/filter/` — `105.343 rezultate` matches the original Python total. Portrait 404s in the network log are pre-existing (QIDs without portrait files; handled by `<img onerror=…>`).

**Build/deploy command.** Added to `CLAUDE.md` common commands: `python3 tools/build_dist_db.py`. Run after each `build_db.py` rebuild before deploying.

**Backlog.** Logged: (a) consider dropping the 3,042 pre-rendered detail pages and using a SPA-style template that queries the shipped DB by slug; (b) trim DB further by column / row pruning (target <20 MB).

---

## 2026-05-19 — Browser page (`/browser/`)

New explorer view at `/browser/` — filter bar on top + two layouts (Tabel / Compact), powered by `filter_server.py`.

**filter_server.py changes.** Added `p.wikidata_qid` and a `name_count` correlated subquery to `_SELECT_COLS` (per-row national frequency). Added a name search param (`?name=…`) that uses `streets_lib.normalize_match` on the input and `LIKE %…%` on `sd.name_normalized`. Added `?sort=count|name|location` (default: `count` desc). Added `?aggregate=1` mode — one row per distinct name, grouped by `sd.name_normalized`, returned with portrait + person metadata via `MAX()` (the joins are per-`core_name_norm`, so all non-null values within a group are identical). New routes: `GET /browser` → `dist/browser/index.html`, and `GET /portraits/<file>` → static serving from `dist/portraits/`.

**`dist/browser/index.html`** (new). Single-page UI, no Jinja — fetched live from the API. Filter bar on top: 130px search input + seven single-select dropdowns (Clasificare / Gen / Profesie / Eră / Naționalitate / Județ / Tip) + Tabel|Compact view toggle on the right. Each dropdown has a "Toate" item at top (italic when active = no filter selected) that resets just that criterion; clicking a value sets the filter and recolors the button accent. Result count bar with spinner. Two panes: a dense table (load-more pagination, 200 rows/page, sort=count default) and a Compact view that reuses the landing-page `.ctok.street .plaque` markup verbatim (46px circular portraits overflowing the sign, gold ring on top-3 leaders, Mono count badges). Info footer (sticky, 66px) updates on hover/click of any tag with portrait + person/gender/era/profession/nationality fields + national count. Default view is Compact, fetches `?aggregate=1&limit=500&sort=count`.

**Fixed compact-view vertical alignment.** `.flat-tokens` used `align-items: baseline` (copy of the landing-page rule) — but in flex-wrap rows, tokens with portraits push the row taller, and baseline alignment then misaligns plaque text against plain plaques. Changed to `align-items: center`. The landing page doesn't show this because its `.cluster-tokens` lives in 2-column multicol where rows are independent.

**`build_site.py --serve` proxy.** The dev static server (default 8000, the user runs on 9000) is `SimpleHTTPRequestHandler` — has no `/api/*` routes. Replaced with a `SiteHandler` that proxies `/api/*` and `/portraits/*` to `localhost:8765` (filter_server). Single entry point for browsing the site; `filter_server.py` must be running separately.

**Top nav.** Added `/browser/` link to both `templates/index.html.j2` and `templates/_detail-shell.html.j2` (between Caută and Persoane). Rebuilt: landing variants + all 3,042 detail pages now carry the link.

**Backlog.** Logged P2 items for keyboard navigation of the filter bar and a live-statistics bar for the current selection (gender split / top era / top profession / classification breakdown / total UATs, updates on each filter change).

---

## 2026-05-18 — Backlog Sweep: Trim, Search, OG, Choropleth, Nationalities

One sitting, five backlog items.

**Landing trim** (`templates/index.html.j2`). Removed the duplicate "Non-române" sub-section inside the Persoane panel (kept the richer standalone s8 foreigners panel). Also removed the "Notorietate Wikipedia · vizualizări lunare" panel — it was a duplicate signal next to the Wikidata scope panel and never drove story. JS `renderFlat` for `s3p-foreigners` removed; pageviews updater is harmless when the panel is missing (`if (!container) return`).

**Global search shortcut** (`templates/_search_overlay.html.j2`). New partial: `/` or `Cmd/Ctrl+K` opens a modal with input + lazy-loaded indexes (`/cauta/streets.json` + `/cauta/uats.json`). Arrow keys to navigate, Enter to open, Esc to close. Reuses the same `p` flag so streets without rendered pages show as dimmed `fără pagină` rows. Included from `_detail-shell.html.j2` (covers all 3,042 detail pages) and from `index.html.j2`, `index-v1.html.j2`, `index-v2.html.j2`, `metodologie.html.j2`. Module guards against double-init via `window.__gsoInit`.

**OG metadata + image** (`templates/_meta.html.j2`, `tools/gen_og_image.py`). New `_meta.html.j2` partial emits og:title / og:description / og:url / og:image plus the twitter:card pair and a meta description. Each detail render in `build_site.py` now passes per-page `og_title` / `og_description` / `og_url_path` overrides; landings and methodology set them inline. Static OG image at `dist/og.png` (1200×630): gold rule, brand mark, two-line serif headline, dark stats band with live counts (104,483 streets · 1,207 localități · 42 județe), Georgia + Menlo only — no extra font dependencies. Regenerate with `python3 tools/gen_og_image.py`.

**Choropleth · 11 metrics on the judete map** (`site_queries.section6`, `templates/judete-index.html.j2`). Extended the per-județ stats with `male_pct`, `person_pct`, `foreign_pct`, `universal_pct`, `date_pct`, `flora_pct`, `ideology_pct` next to the existing saint/numeric/female/nature columns. Chip row at the top of the existing `/judete/` map now exposes all 11. Scale logic now uses `min..max` when the metric is tightly clustered (spread < 50% of max) so e.g. `person_pct` (range 8–13%) shows visible county-to-county differentiation instead of a flat wash; rare-event metrics (`female_pct`, `ideology_pct`) still use 0..max so the absolute zero is grounded. Default chip changed from `saint_pct` to `person_pct`. The `.chip` / `.chip-row` styles weren't present in `_detail-shell.html.j2`, so the chips rendered as plain text — re-added the same rules locally via `{% block head_scripts %}`.

**Nationalities breakdown panel** (`site_queries.section3.nationality_breakdown`, `templates/index.html.j2`). New compact `s8` panel "Naționalitatea personalităților onorate". Side-by-side bars: "după persoane" vs "după străzi (ponderate)". Reveals the asymmetry — non-Romanian honorees are 7.4% of persons but only 4.49% of streets, i.e. foreign personalities get fewer streets per person than their numeric share. Flag chips + Romanian-language full country labels. RO bars use plaque blue; non-RO use olive to visually separate. Placed between the rich foreigners panel and the (hidden) global-recognition panel.

## 2026-05-18 — Search: Disable Rows for Streets Without Pages

The `/cauta/` autocomplete was finding 29,735 streets but only 2,464 have rendered detail pages — clicks on the long-tail 27k were silent 404s. Added a `p` flag to the street index (`1` if a rendered page exists, `0` otherwise). The page renders `p=0` rows as dimmed, non-clickable rows with a "fără pagină" tag and an explanatory note line ("Rezultatele estompate sunt în baza de date dar nu au încă pagină proprie generată."). Search results are sorted so renderable hits come first within the 20-row cap.

Subtle correctness fix in `site_queries.explorer_indexes`: matching on bare slug was wrong on both ends — (a) two `name_normalized` values that happen to slugify to the same string would both be marked `p=1` even though only one renders, and (b) `enumerate_streets` suffixes colliding slugs (`-2`, `-3`), so the rendered page's slug differs from the bare slugify output. Switched to a `{name_normalized → rendered_slug}` map: `p=1` only when name_normalized is in the rendered set, and the row's slug is taken from the map so the link goes to the actual rendered URL.

## 2026-05-18 — UI Polish: Seats, Foreigners Panel, Nav Consistency

Three polish passes on the static site.

**Mark county seats in /judete/.** Used the `is_capital` flag from yesterday's UAT-scoping work. Added `.uat-pill.is-capital` style in `_detail-shell.html.j2` — gold border + inset accent + ◆ glyph. `judete-lista.html.j2` now sorts capitals first within each județ and applies the class; `judete-index.html.j2` does the same inline for the top-20 cities block. The 41 seats now read at a glance.

**Foreigners panel.** With 125 more persons in the table (after this morning's Gemini batch import), the s8 panel grew richer entries. Added missing profession translations (architect, linguist, biologist/chemist, biologist, chemist, physicist) so labels render in Romanian. Precomputed a `foreign_nat_summary` list of `(nationality, count)` sorted by count in `site_queries.section3()` — Jinja's `groupby` can't sort by group length cleanly. The panel caption now shows a flag-chip strip (`🇭🇺 16 · 🇫🇷 2 · 🇲🇩 1 · 🇷🇺 1 …`) before the Hungarian-community footnote.

**Nav consistency.** The landing page nav had section-anchor links plus only `/judete/` and `/metodologie.html` for site navigation; the detail-shell nav had the full set (Caută, Persoane, Teme, Județe) but no anchors. Unified the landing nav by adding `/cauta/`, `/persoane/`, `/teme/` between separator chips, alongside the existing anchors. Brand link changed from `#cele-mai-intalnite` to `/` so it behaves like the detail-shell brand. Footers stay distinct on purpose — landing has the wide 3-column data/methodology/source band; detail-shell has the compact one-line strip.

## 2026-05-18 — Gender Curation: Import LLM Batch, Refresh Notebook

Closed the "Gender story needs curation" P2 item. Discovered that `data/curation/llm_gemini-3.1-flash-lite.csv` (700 rows from a Gemini classification run, dated 2026-05-15) had never been imported. Ran it through `tools/import_csv.py`: 125 persons + 208 nature_terms + 191 name_categories + 173 place_refs upserted.

Net additions to `persons`: 3 women on top of the existing 12 — Smaranda Brăescu (aviator, interwar), Domnița Bălașa (noble, medieval), Iulia Hașdeu (poet, premodern). Plus 122 men and one collective. Manual scan of the fresh top-500 unclassified turned up no additional confident female candidates the LLM had missed — the long tail is male-heavy and noisy with abstract / geographic / nature terms.

Headline numbers after import:
- 15 female honorees covering 426 street-instances
- 318 male honorees covering 12,020 street-instances
- 3.42% of person-named streets honor women
- Top woman: Ana Ipătescu (91 streets); top man: Mihai Eminescu (300). Ratio ×3.3.

Re-executed `notebooks/01_gender_gap.ipynb` end-to-end; all four sections (national ratio, top-M vs top-F, per-județ, era trend) render with the refreshed data.

The persistent 3–5% female share is itself the editorial finding — adding more women didn't move the headline because that's genuinely what the data shows.

## 2026-05-18 — Root-Relative Links + Scoped UAT Detail Pages

Two backlog items.

**P0: root-relative links.** Audited every `href` and `src` in the templates that weren't already `/`-prefixed. Changed `href="metodologie.html"` → `href="/metodologie.html"` across `index.html.j2`, `index-v1.html.j2`, `index-v2.html.j2`. In `metodologie.html.j2`, the nav's `href="index.html"` and `href="index.html#…"` became `href="/"` and `href="/#…"`, and the self-link to `metodologie.html` became absolute. Four JS template-literal portrait `src="portraits/${qid}.jpg"` occurrences (foreigners panel renderer, two branches of `renderFlat`, plus one server-rendered Jinja path) became `/portraits/${qid}.jpg`. Detail templates (`_detail-shell`, `street-detail`, `person-detail`, `uat-detail`, `persons-index`) were already root-relative. Rebuilt all variants — `dist/index.html`, `dist/index-v1.html`, `dist/index-v2.html`, `dist/metodologie.html` now contain zero relative `metodologie.html` or `portraits/` references.

**P2: scope UAT detail pages.** `site_queries.enumerate_uats()` rewrote to return pages only for (a) the 41 county-seat municipalities, (b) the 6 Bucharest sectors, (c) any other UAT named `MUNICIPIUL ...` with ≥50 streets. Added `COUNTY_SEAT_SIRUTAS` dict — hardcoded because the DB carries no rank/seat metadata, the seat is not always the largest municipiu (HR: Miercurea-Ciuc < Odorheiu Secuiesc by street count), and Ilfov's seat Buftea is `ORAŞ`, not `MUNICIPIUL`, so a pure-rank filter would drop it. Returned dicts now include `is_capital`. UAT page count: 676 → 108 (41 seats + 6 sectors + 61 other municipii). Bucharest sectors are detected by `judet == "B"`. Added prune step in `build_detail_pages` that removes any `dist/oras/<judet>/<slug>/` not in the rendered set — first prune deleted 568 stale comune directories.

Closed the search-index follow-up in the same session: `explorer_indexes` now sources its UAT list from `enumerate_uats` instead of a separate query, so `dist/cauta/uats.json` shrank 1207 → 108 and stays in sync with whatever has a rendered page. A future DB-backed endpoint for long-tail UATs can be wired in later without re-introducing the 404s.

## 2026-05-18 — Permanent URLs for Landing-Page Filter

Added query-string state persistence to the two-level județ/municipiu filter on the landing page. Selecting a județ updates the URL to `/?judet=CJ`; selecting a municipiu appends `&siruta=54984`. On page load, `URLSearchParams` is read and the filter is restored before the first `render()` call — with `updateUrl()` called after each branch to clean any stale params. `history.replaceState` (not `pushState`) is used — Back button is intentionally not wired to filter navigation. All changes in `templates/index.html.j2`.

## 2026-05-17 — All landing-page panels now filter by județ/municipiu

Extended the nav filter to cover every content panel. Previously only the cluster cloud, persons, theme donut, gender grid, and pageviews list responded to the selector. Now all panels update:

- **Subtipuri Natură** — per-județ `nature_by_judet` dict from new SQL query
- **Tokeni Ideologici** — per-județ `ideo_by_judet` dict
- **Profesia persoanei** — per-județ `profession_by_judet` dict
- **Epoca în care a trăit** — per-județ `era_by_judet` dict
- **Personalități non-române** (full s8 panel) — re-renders from `foreigners_by_judet`; profession field was missing from that query and was added
- **Conteste tematice** — hidden when any filter is active (data is national-only, too costly to precompute per-județ)

At municipiu (SIRUTA) level, the four breakdown panels show "(date insuficiente)" — per-siruta breakdown at that granularity isn't precomputed.

### JS architecture
Added generic `_renderBarRows()` helper shared by nature subtypes, professions, and eras (all are emoji + label + bar + count). Separate `updateIdeoTokens()` for chip-cloud layout, `updateForeigners()` for the rank-list panel. Slug lookups for per-județ rows are built once from national `DATA_S5`/`DATA_S3` at init time (no slug field in the per-județ dicts).

### Non-obvious decisions
- Ideo token accent threshold lowered from `n > 30` to `n > 10` in the per-județ view — county-level counts are an order of magnitude smaller than national, so the original threshold would never trigger.
- Contests panel hides rather than shows stale national data — showing national numbers when a județ is selected would be actively misleading.

## 2026-05-17 — Three-level landing-page filter (națonal → județ → municipiu)

### What was built

**Three-level filter in the navbar** — the sticky nav now has two `<select>` elements:
- **Județ selector** (always visible) — selecting a județ rewrites all landing-page panels for that județ's data.
- **Municipiu selector** (hidden until a județ is chosen) — once a județ is selected, a second `<select>` appears with all municipii for that județ; choosing one filters everything to that single city (identified by SIRUTA code).
- Resetting the județ selector back to "toate județele" clears both selects and restores national data.

**All panels now respond to the filter** — previously only the cluster cloud and top-persons list responded. Now wired:
- Theme donut (`conic-gradient` rebuilt from per-județ/per-siruta counts)
- Gender grid (100 squares recoloured by M/F ratio)
- Wikipedia notoriety rank list (top-5 persons by `wiki_ro_views`, per-județ)
- Cluster cloud + persons panel (already worked; now also responds at municipiu level)

**`site_queries.py` additions:**
- `section3()` extended with `gender_by_judet` — per-județ M/F street counts via JOIN with `persons`.
- `section4()` extended with `top_pageviews_by_judet` — top-5 persons per județ by `wiki_ro_views` using `ROW_NUMBER() OVER (PARTITION BY judet)`.
- `section5()` extended with `theme_by_judet` — per-județ CASE WHEN counts for all 6 macro categories.
- New `municipii_index()` — returns compact per-SIRUTA data for 102 municipii: top-25 streets (ranked by national frequency, not per-UAT count), top-10 M/F persons, gender ratio, theme breakdown. Compact dict keys (`s`, `n`, `sl`, `c`, `cat`, `qid`, `nn`) to keep the JSON payload to ~380 KB extra (955 KB total page).

**Streets within a municipiu ranked by national frequency** — `streets_dedup` has one row per `(siruta, name_normalized)`, so `COUNT(*)` is always 1 and can't be used as a sort key. Instead, a national CTE (`COUNT(DISTINCT siruta) AS nat_count`) provides the ranking, so universally common street names (Florilor 532, Trandafirilor 496, Morii 494) appear first rather than alphabetically.

**Removed per-județ comparison panels from landing page** — HARTA, AMPRENTE JUDEȚENE, SEMNĂTURI REGIONALE, CURIOZITĂȚI UNICE panels removed from `index.html.j2`; their data lives on `/judete/` (built in the previous session). D3 script tag and DATA_S6/DATA_S8 globals also removed.

**Nav CSS fix** — the județ `<select>` was white-on-white (border and text rendered in white against the white navbar). Fixed: `border: 1px solid var(--rule)`, `color: var(--ink)`, muted chevron via `var(--muted)`.

### Non-obvious decisions
- `uatSelect.style.display = 'inline-block'` (not `''`) — setting to empty string reverts to `display: none` from the CSS rule `#s2-uat-select { display: none }`, which would immediately re-hide it.
- Gender-grid squares created once on first `updateGenderGrid` call, then recoloured on subsequent calls — avoids DOM thrash on every filter change.
- Stats ticker (105.343 adrese, 203 persoane onorate) intentionally stays national — it is a scope descriptor, not a filtered count.

### Backlog item added
P2: Scope UAT detail page generation to județe capitals + county seats only (currently renders all 676 UATs with ≥50 streets; scoping would cut build time and storage substantially).

### Files touched
- `templates/index.html.j2` — filter UI, syncUatSelect, updateTheme, updateGenderGrid, updatePageviews, render(code, siruta)
- `site_queries.py` — gender_by_judet, top_pageviews_by_judet, theme_by_judet, municipii_index()
- `build_site.py` — passes `municipii` to template context
- `docs/BACKLOG.md` — new P2 item
- `tests/test_build.py` — DATA_S6 assertion inverted (nav select uses DATA_S2, not DATA_S6)

### Verification
All 14 tests pass. Manually verified Cluj-Napoca municipiu filter: streets show Florilor 532 / Trandafirilor 496 / Morii 494 / Primăverii 487; persons show Zaharia Stancu / Vlad Țepeș / Victor Babeș; theme donut and gender grid update correctly.

## 2026-05-17 — Județe overview page + navbar county selector

### What was built

Added a `/judete/` overview page to replace the removed per-județ comparison panels from the landing page. The page has:
- Choropleth map of Romania (D3 + TopoJSON) shaded by nature_pct (share of nature-named streets)
- Summary stats table with columns: județ, streets, persons, nature %, numeric %, top street, rare street
- "Amprente" section (most distinctive per-județ names)
- Top 5 cities per județ by street count
- `/judete/lista/` — plain alphabetical table of all 42 județe

**Nav selector** — a `<select>` in the sticky navbar of the landing page (`index.html.j2`) that lets the user jump to a county-specific view. Implemented as a client-side filter (no page reload) that rewrites the cluster cloud and top-persons panels using `DATA_S2.by_judet`.

### Files touched
- `templates/judete-index.html.j2` (new) — overview page with D3 map + table
- `templates/judete-lista.html.j2` (new) — plain listing
- `templates/index.html.j2` — added nav `<select>` + client-side render(code) function
- `site_queries.py` — extended `section6()` with `nature_pct`, `numeric_pct`, `top_street`, `rare_street`; added `section8()` top-cities-per-județ
- `build_site.py` — wires section6/section8 for detail build; renders both judete pages

---

## 2026-05-17 — Fix --detail-only hang + streets_dedup correctness

### Root cause
`uat_detail()` ran two global full-table scans on every one of the 672 UAT calls:
a full-scan CTE for "distinctive" names (counting all streets globally) and a separate full-scan for national saint/numeric averages. Total wall time: ~740s — effectively a hang.

### Fixes applied

**`build_db.py`**
- Changed `streets_dedup` GROUP BY from `(uat, name_normalized)` to `(siruta, name_normalized)`. This is a correctness fix: 48 Romanian UAT names appear in multiple județe (e.g. ALBEȘTI in Argeș and Mureș); the old grouping merged them. UAT count 672→676.
- Added `ix_streets_siruta_name` composite index on `streets(siruta, name_normalized)` — enables the optimizer to push `WHERE siruta = ?` into the view, cutting per-UAT query time from ~250ms to ~2ms.

**`site_queries.py` — `uat_detail`**
- Added optional keyword args `global_rarity: dict | None` and `nat: dict | None`.
- When provided, the distinctive-names section fetches only the current UAT's names (fast, indexed) and filters against the precomputed dict in Python. Falls back to the full-scan CTE if called standalone.

**`build_site.py` — `build_detail_pages`**
- Precomputes `global_rarity` and `nat` once before the 676-UAT loop, passes them in.

### Result
`--detail-only` runs complete in ~100s (3427 pages). The bug is closed.

## 2026-05-17 — Detail-page browsing (Phase 1)

Implemented navigable detail pages for all four entity types: streets, persons, UATs (towns), and themes. Pages have real URLs and are statically generated at build time.

### What was built

**site_queries.py**
- Added `slugify` import from `streets_lib`
- Added `enumerate_streets/persons/uats/themes()` — enumerator functions for the build loop (2464, 211, 672, 72 entities respectively)
- Added `street_detail()`, `person_detail()`, `uat_detail()`, `theme_detail()` — per-entity drilldown queries
- Added `explorer_indexes()` — compact JSON for `/cauta/` autocomplete
- Added `slug` fields to section2 (top_names, by_judet), section3 (top_persons, top_men, top_women, top_foreigners, by-judet dicts), section4 (top_pageviews), section5 (theme_dist, nature_subtypes, ideo_tokens), section6 (top_per_judet, rare_per_judet, persons_per_judet)
- Fixed `_theme_where()` helper that replaced duplicate `_macro_where`/`_macro_where_impl` definitions; fixed `theme_detail()` `params` bug; fixed double-join conflict for person-themed queries

**templates/ (new)**
- `_detail-shell.html.j2` — shared base: CSS variables, sticky nav (Acasă · Caută · Persoane · Teme · Județe), footer, portrait/rank-list/uat-pill CSS
- `street-detail.html.j2` — street page: hero plaque, honoree bio, UAT pills grouped by județ
- `person-detail.html.j2` — person page: portrait, bio, geographic footprint, peers sidebar
- `uat-detail.html.j2` — UAT page: theme breakdown, top streets, top persons, distinctive names
- `theme-detail.html.j2` — theme page: top streets ranked, județ heatmap bars
- `explorer.html.j2` — `/cauta/` autocomplete: loads JSON on first keystroke, fuzzy match with diacritics normalization
- `persons-index.html.j2`, `themes-index.html.j2`, `judete-index.html.j2` — alphabetical/grouped index pages

**build_site.py**
- Added `_make_env()` with `enumerate` custom filter; `build()` now uses it
- Added `_render()` helper
- Added `build_detail_pages()` — renders all entity pages + JSON indexes; deduplicates person slugs (some share QID)
- Added `--detail` and `--detail-only` flags

**templates/index.html.j2** (wiring existing UI)
- `renderFlat()`: chips now wrap in `<a href>` to `/strada/<slug>/` and `/persoana/<slug>/`
- Fingerprint panel (map sidebar): top streets, persons, rare names are all linked
- Profession dist rows → `/tema/profesie-<slug>/`
- Nature subtype rows → `/tema/natura-<slug>/`
- Ideological tokens → `/tema/ideologic-<slug>/`
- Theme dist pie labels → `/tema/<macro-slug>/`
- Wikipedia notoriety panel persons → `/persoana/<slug>/`
- Foreigners panel persons → `/persoana/<slug>/`

### URL scheme
- `/strada/<slug>/` — 2464 pages
- `/persoana/<slug>/` — 204 unique pages (QID-based slugs; 7 entries deduplicated)
- `/oras/<judet>/<slug>/` — 672 pages
- `/tema/<slug>/` — 72 pages (prefixed: `profesie-*`, `natura-*`, `ideologic-*`, macro keys)
- `/cauta/` — autocomplete explorer with `streets.json` (~1.8MB) and `uats.json` (~74KB)
- `/persoane/`, `/teme/`, `/judete/` — index listing pages

### Build
- `python3 build_site.py --detail-only` — ~3,424 HTML files in ~60s
- `python3 build_site.py --variant default` — main index (666KB) clean

## 2026-05-16 — Wire Wikimedia portrait thumbnails into Top Persoane panel

Added `tools/fetch_portraits.py`: for each person with a Wikidata QID, fetches the P18 (image) claim from Wikidata, downloads a 64px thumbnail from Wikimedia Commons, and caches it to `dist/portraits/<qid>.jpg`. Idempotent, rate-limited, honours 429 Retry-After headers.

Updated `site_queries.py` section3 queries (`top_men`, `top_women`, `_persons_by_judet`) to include `wikidata_qid` in results.

Updated `build_site.py` to scan `dist/portraits/` at build time and bake a `PORTRAITS` JS Set into the template. Updated `renderFlat()` in `templates/index.html.j2` to prepend a 26px portrait `<img>` for persons with a cached thumbnail; persons without an image render name-only (no placeholder circle).

The `.portrait` CSS class (26px circle, `overflow:hidden`, `object-fit:cover`) was already in place — no CSS changes needed.

## 2026-05-16 — Emoji size bumps + Top 50 expansion

### What was done
- **Bumped emoji sizes** across the dashboard to match the larger row text introduced in the prior commit (12px → 22px on panel rows). Cascade:
  - **Row emojis** (nature subtypes, professions, eras, theme dist): `.emo.md` (12px) → `.emo.xxl` (22px); container width `14px → 24px`.
  - **Panel header labels** (16 panels): `.emo.md` → `.emo.xl` (12px → 18px).
  - **Sub-panel labels** (s8 fingerprint sub-headers, contest family headers): `.emo.md` → `.emo.xl`.
  - **Kicker labels** (map sidebar, fingerprint sub-blocks): `.emo.md` → `.emo.lg` (12px → 14px).
  - **Statbar group labels** (Scară / Tematică / Gen / Onorați): `.emo.md` → `.emo.lg`.
  - **Footer column labels** kept at `.emo.md` — text is 10px there; bumping unbalances the small uppercase headers.
- **Top 50 instead of Top 30** in the left cluster-cloud panel to fill the vertical space alongside the gender-split persons panel on the right. JS `LIMIT_STREETS = 30 → 50`; per-județ SQL `rn <= 30 → 50` in `site_queries.section2()`; panel label updated to "Cele mai frecvente · Top 50".

### Why
- The previous commit (`8fdfb62`, msg "-") bumped row text from 12px → 22px without touching emoji sizes; emojis ended up visually puny next to the new text. User asked to "bump also the emoji/icon size accordingly. make them stand out a bit."
- Left widget was top-30 plaques (~7 rows), right widget showed gender-split persons spanning ~10 rows — vertical mismatch. Bumping to 50 fills the parity.

### Files touched
- `templates/index.html.j2` — emoji class bumps + `LIMIT_STREETS=50` + label text
- `site_queries.py` — `section2` per-județ `rn <= 50`
- `dist/index.html` rebuilt (~490 KB, up from ~400 KB; growth is the extra 20 plaque entries × 42 județe)

### Verification
- `python3 build_site.py --variant default` → clean
- `python3 -m pytest tests/test_build.py -q` → 12/12 pass

## 2026-05-16 — Cluster cloud promoted to primary (`dist/index.html`)

### What was done
- Iterated the cluster-cloud variant through three rounds of refinement, then **swapped the variant names**: the former `index-clusters.html` is now `dist/index.html` (the primary dashboard) and the former `dist/index.html` (dense leaderboard layout) is now `dist/index-v2.html`. `--variant default` builds the cluster cloud; `--variant v2` builds the dense legacy.
- **Round 1 — flatten:** removed the category/wiki_scope cluster banding entirely. Both panels render as a single flat word-cloud (no eyebrows, no colored rules, no ALTELE tail). One shared `<select>` filters both panels by județ; added `persons_by_judet` to `site_queries.section3()` so the persons panel also responds to the filter.
- **Round 2 — bigger type, real superscripts:** doubled the token font range from `11.5–14.5px` → `17–28px` for a stronger tagcloud rhythm; switched `.ctok` from `inline-flex` (which silently disabled `<sup>` positioning) to `inline-block` so the count badge can be truly superscript.
- **Round 3 — floating count badges:** the count is now absolutely positioned at the top-right corner of each plaque/chip as a tiny dark pill (9px mono, gold-soft text on streets, white text on persons). Removes all inline horizontal space taken by counts — the tokens pack tighter, the count reads as a notification-style annotation.
- **Light statbar:** flipped the top stats header from dark Bloomberg-ticker (`var(--ink-band)`) to a soft light surface (`var(--surface-1)`) with ink text, muted gray labels, and `var(--rule)` dividers. The 3px gold border-bottom is preserved as the divider between statbar and dash-grid. The dark footer is untouched.
- **Test updates:** removed `test_clusters_page_builds` (obsolete now that clusters IS default), added `test_default_is_cluster_cloud` (asserts flat-tokens markup + cluster panels before `#tematica` in `dist/index.html`) and `test_v2_dashboard_builds` (smoke test for the renamed dense layout). **12/12 tests pass.**

### Why
- The first cluster prototype had three issues the user flagged: (1) category bands felt like over-grouping for what was already a small data set, (2) județ filter only affected streets, breaking the side-by-side parity, and (3) the original cluster idea looked better as a true cloud than as banded groups. Each round of changes addressed user feedback directly.
- The rename reflects a decision: the cluster cloud is now the better default for the casual visitor — denser, more scannable, instantly comparable street-vs-person honoring. The dense leaderboard remains accessible at `/index-v2.html` for users who want the long-ranked-list view.

### Non-obvious decisions
- **Count badge as absolute, not inline `<sup>`:** the user said "superscript-like, more compact" three times. The breakthrough was realizing `<sup>` inside `display:inline-flex` silently loses its `vertical-align: super` behavior — flex baseline alignment overrides it. Switching `.ctok` to `inline-block` restored real superscript, but absolute positioning (top-right corner pill) made it truly *take no horizontal space*, which is the actual win for compactness.
- **Persons panel uses chips, streets uses plaques** — kept from round 1. Multi-word person names ("Mihai Eminescu", "Ștefan cel Mare") don't read as street plaques; flat ink-on-surface chips with a 1px rule border carry the information without forcing every name into RO-plaque aesthetic.
- **Both panels' top-3 get the gold halo, not just cluster leaders** — there's no clustering anymore, but the "top-3 by count" rule still applies so the most-frequent items pop.
- **Statbar light, footer dark:** the user asked to flip only the stats header. The dark footer stays — it acts as a closer on the page and the brand gold accents (Despre date / Metodologie / Cod sursă section labels) need a dark background to sing. Light statbar + dark footer reads as "data inputs above, attribution below."
- **`persons_by_judet` shape mirrors `streets by_judet`** so the JS render function can swap data sources without restructuring. Bucharest sectors collapse to `'B'` at the SQL level for consistency with the rest of the site.

### Files touched
- `templates/index.html.j2` (was `index-clusters.html.j2`) — rounds 1-3 + light statbar
- `templates/index-v2.html.j2` (was `index.html.j2`) — unchanged content, renamed file
- `site_queries.py` (`persons_by_judet` query added to `section3()`)
- `build_site.py` (`VARIANTS` swapped; `v2` added; `clusters` removed; `--variant all` builds default + v1 + v2 + methodology)
- `tests/test_build.py` (test renames + v2 smoke test)

## 2026-05-16 — Cluster-cloud variant (`dist/index-clusters.html`)

### What was done
- Added a fourth build variant (`--variant clusters`) that ships `dist/index-clusters.html` alongside the unchanged dense layout. New template `templates/index-clusters.html.j2` (~267 KB rendered), copied from `index.html.j2` with two structural changes at the top of `.dash-grid`.
- **Two s6 panels side-by-side** replace the previous pair of stacked s12 leaderboards: streets cluster on the left, persons cluster on the right. The old s12 Top persoane panel is removed from its original position further down the page.
- **Cluster-cloud layout**: tokens flow inline (flex-wrap), grouped under category eyebrows with a colored left-rule. Top 3 clusters highlighted; remaining categories merge into an ALTELE tail. Font varies mildly within each cluster (11.5–14.5px normalized to cluster min/max). Overall top-3 entries by count get a gold halo regardless of which cluster they belong to.
- **Streets panel**: blue RO plaques, grouped by `category` (natură / persoană / instituțional / …). County `<select>` preserved — changing județ re-clusters. Count badges in gold mono after each token.
- **Persons panel**: flat ink-on-surface chips (not plaques), grouped by `wiki_scope` (universal / național / local / unknown). Red accent border on female persons. Same size-variance and gold-halo logic.
- **Data change**: `site_queries.section3()` `top_persons` query now returns `COALESCE(p.wiki_scope, 'unknown') AS wiki_scope` so the JS grouper can bucket persons by recognition tier.
- **`build_site.py`**: `"clusters"` added to `VARIANTS` and `--variant` choices; `--variant all` now renders default + v1 + methodology + clusters.
- **Smoke test**: `test_clusters_page_builds` in `tests/test_build.py` asserts file exists, both panels precede `#tematica` in DOM order, `.cluster-band`/`.cluster-eyebrow` present, old `.rank-list.rank-2col.s2-list` markup absent. 11/11 tests pass.

### Why
- The user wanted to try an alternative visual rhythm at the top of the dashboard — "word next to word, somewhat like a wordcloud" — without throwing away the dense ranked-list view. Shipping as a parallel variant lets both sit open in browser tabs.

### Non-obvious decisions
- **Size-variance capped deliberately at 3px spread (11.5–14.5px).** The user asked for "not big difference, first to last." Normalizing within each cluster independently (not globally) keeps the spread local so even a small cluster with just 3–4 tokens still shows visible rhythm.
- **Persons use chips, not plaques**, because multi-word names ("Mihai Eminescu") sit awkwardly in narrow blue street-plaque form at inline-flow sizes. The contrast flip (light chip, dark text) also visually separates the two panels when they sit side-by-side.
- **No LOCAL wiki_scope cluster visible** in current data — the top-20 persons don't include any `wiki_scope='local'` rows. The JS renders clusters from data only; `local` is wired and will appear as the DB coverage improves.
- **Tail group merges all non-top-3 categories** (streets) and renders `unknown` scope as tail (persons). Eyebrow uses a muted color and a dimmer dot to visually retire these entries from the primary scan path.
- **Panel is data-backed (not STATIC)** because it renders `section2`, `section3`, `section4`, `section5`, `section6`, `section8` — same as the default variant. Only the template and the top-of-grid layout differ.

### Files touched
- `templates/index-clusters.html.j2` (new, ~1600 lines)
- `site_queries.py` (`section3` `top_persons` SELECT: added `COALESCE(p.wiki_scope,'unknown')`)
- `build_site.py` (clusters variant wired)
- `tests/test_build.py` (`test_clusters_page_builds` added)

## 2026-05-16 — Methodology page (`dist/metodologie.html`)

### What was done
- Added a standalone Romanian-language methodology page rendered through the existing `build_site.py` pipeline. New template `templates/metodologie.html.j2`, new variant `methodology` in `VARIANTS`, output `dist/metodologie.html` (~34 KB).
- `build_site.py` now distinguishes data-backed variants from `STATIC_VARIANTS` (currently just `methodology`), so the methodology build skips the `site_queries.section1..section8` calls entirely — no DB needed at template render time. The `--variant` flag gained `methodology` and `all` (the latter renders default + v1 + methodology).
- Page structure: hero with 4-number statbar strip and an editorial-review flag, 2-column TOC, 10 sections (`#de-ce`, `#sursa`, `#schema`, `#clasificare`, `#recunoastere`, `#osm`, `#limite`, `#ce-urmeaza`, `#cronologie`, `#cod`), and a vertical timeline of ~16 milestones distilled from the activity log and git history (2026-04-26 ETL → 2026-05-16 bold restyle → this page).
- Visual treatment shares the dashboard's design language without forking it: `var(--ink-band)` hero/footer, gold accents, IBM Plex Sans body, 2px ink-rule section headings, small monospace dark `demo` block for the `Bd. Regele Carol I → carol i` normalization example.
- Wired cross-links in both dashboard variants: `templates/index.html.j2` and `templates/index-v1.html.j2` got a `Metodologie` link in the sticky nav and a "Citește metodologia completă →" link in the footer's existing Metodologie column.
- Added two smoke tests to `tests/test_build.py`: `test_methodology_page_builds` (builds the variant, asserts all 10 section anchors + editorial-review notice + dashboard cross-link) and `test_methodology_link_in_dashboard`. All 10 tests pass.

### Why
- The footer's Metodologie column was two sentences. Anyone wondering "where does the ~57% classified come from?", "why does Gorj have 18% OSM coverage?" or "what does `core_name_norm` mean?" had nowhere to look. The page is the structured answer.
- The user explicitly asked for a methodology page with a timeline drawn from the activity log, backlog, and git history. Tone: lightly informal, mostly explanatory — closer to good docs than to a blog post.

### Non-obvious decisions
- **Standalone HTML, not a section appended to the dashboard.** Long-form prose dilutes the dense-analytics feel of `index.html`; the methodology page also wants a different layout (single-column 760px prose) than the 12-column dashboard grid. Separate page keeps both reads clean.
- **Romanian copy carries a `[Revizuire editorială RO în curs]` flag** in the hero and as a header comment in the `.j2`, per the CLAUDE.md rule against generating fictional Romanian copy that "sounds right." The copy is structurally and factually correct, but tone/word-choice benefit from a native pass before this is treated as final.
- **Hero stat numbers hardcoded** (`105.107`, `1.155`, `~57%`, `310`) rather than passed through from queries. They're snapshot-anchored (14.05.2025 build) and the methodology page explicitly explains they're prototype-phase figures; coupling this page to the DB just to render its hero would add a build-time dependency for cosmetic value.
- **Coverage table doesn't auto-update either.** Same reasoning: the methodology page describes a *moment* in the project; if numbers shift materially, this page is the right place to revise narrative and number together, not have one slip silently when the other isn't ready.
- **Timeline cut at ~16 entries.** The activity log has ~25 distinct sessions; keeping only the load-bearing ones (first ETL, each curation batch, LLM classifier, OSM milestones, Wikidata milestones, dense-variant rebuild, design passes, this page) shows the arc without becoming a commit-log dump. Each entry has a one-sentence "what" and an optional italic "why" pulled from the activity log's non-obvious-decisions sections.
- **No emoji in the timeline entries** even though the dashboard uses them as category cues. At ~16 entries on a single vertical rule the page reads cleanly with just the gold date chip; adding per-entry emojis would compete visually with the chips themselves.
- **Footer's Metodologie column is now a real link, not a static blurb.** On `metodologie.html` itself it reads "Sunteți pe pagina de metodologie. Înapoi la dashboard →" so the column adapts to context.

### Files touched
- `templates/metodologie.html.j2` (new, 34 KB rendered)
- `build_site.py` (VARIANTS + STATIC_VARIANTS gate + --variant choices)
- `templates/index.html.j2` (nav link + footer cross-link)
- `templates/index-v1.html.j2` (nav link + footer cross-link)
- `tests/test_build.py` (2 new tests; 8 existing still pass)

### Verification
- `python3 build_site.py --variant all` → all 3 variants build cleanly.
- `python3 -m pytest tests/test_build.py` → 10/10 pass.
- Visual: hero, TOC, all 10 sections, timeline, and footer render at 1440×900; Metodologie link present and highlighted in the dashboard nav.

## 2026-05-16 — Bold analytics restyle: dark statbar, IBM Plex, emoji category cues

### What was done
- Reskinned the dense dashboard (`templates/index.html.j2`) for a "bolder, denser, analytics" feel while keeping the structure and all D3/JS hooks intact. All changes are in the template's `<style>` block plus targeted label/header edits — no schema, query, or build-pipeline changes.
- **Palette pivot from cream to white.** Dropped `--bg #FAF8F3` / `--wash #EEEAE0`. Body is now `#FFFFFF`. Cool washes (`--surface-1 #F7F9FC`, `--surface-2 #ECF1F8`) replace the warm cream as bar tracks and tag fills. Pale yellow (`--warn-1 #FFF7CC`, `--warn-2 #FBE486`) introduced as a leader-highlight; gold (`--gold #E8AE00`) introduced as the dashboard's secondary accent (used in nav brand mark, statbar group labels, footer section labels, and the leader-row inset stripe on every rank list).
- **Dark statbar.** Statbar is now an ink-black band (`var(--ink-band) #0B1118`) with reverse-out white type, gold group labels, and a 3px gold underline anchoring it to the canvas below. Headline numbers grew from 22px → 34px (scale items 22px → 28px), tabular-nums and tight letterspacing. Group columns separated by 1px white-alpha rules instead of gap-only.
- **Typography swap.** `Inter` → `IBM Plex Sans` (400/500/600/700). `Barlow Semi Condensed` retained for the RO white-on-blue street plaques. Plaque size bumped 12.5px → 13.5px (small variant 11.5px → 12px) to match the denser overall feel.
- **Panel headers** now use a 2px solid-ink rule (was 1px hairline `--rule`), 700-weight uppercase 11.5px labels (was 600/9.5px), and each panel-label gained an emoji prefix for at-a-glance category cue (🔝, 🧭, 🌿, 🚩, 🎓, ⏳, 👥, 🌍, 📈, 🗺️, 🧬, 📜, 🔎, 🏟️, 📝).
- **Leader-row highlight.** Every `.rank-list > .rank-row:first-child` gets `box-shadow: inset 3px 0 0 var(--gold)` + a pale yellow horizontal gradient. Rank-num for the leader row goes from muted to ink-700. Works across all leaderboards including the s2 top-30 (DOM order = visual order on the multicol).
- **Bars.** Height 3px → 5px, opacity .4 → .82 — visibly more present. New variants: `.bar.olive` (used in nature subtypes panel) and `.bar.gold` (reserved for future highlight bars).
- **Recognition tier cards** (Universal / Național / Local) got bigger 38px numbers, emoji corner markers (🌍 / 🇷🇴 / 📍), and a deep-ink Universal card with gold uppercase label instead of the old accent-red label.
- **Footer** moved from cream-accent to gold-accent labels; added emoji prefixes (📄 / ⚗️ / ⌨️). Footer dark band now aligns visually with the new dark statbar — symmetric framing.
- **Portrait scaffolding.** Added `.portrait` CSS class (26px gradient circle, gold-rule fallback) wired into the s12 "Top persoane onorate" list with first+last initials as placeholders. When real portraits arrive, drop in `<img>` and the layout already accommodates them.
- **Inline rows** (nature subtypes, professions, eras) restructured to: leading emoji column (14px), label, bar, count. Each row gets a hairline top border for visual rhythm; counts are now ink-700 12px instead of muted 10.5px.
- **Ideological-token chips** got bolder weights, sharper outlines (1.5px), and a more saturated red highlight for high-frequency tokens.
- **Stat picker / chip styles** — judet `<select>` now has a 1.5px ink border and a gold focus ring; `.chip` lost its pill radius and became a 2px-rounded square with a flat-black active state.

### Why
- Brief: "bolder, denser dashboard, larger type, like a data heavy dashboard, analytics. White background. Light blueish / yellow shades, if/where necessary." Plus "add icons where possible" — covered with emojis as placeholders (proper SVG icons can swap in later via the unused `.icon` CSS class already in the stylesheet).

### Non-obvious decisions
- **Dark statbar over light statbar** despite the "white background" brief. Reading "white background" as the *main canvas* (panels), with the statbar serving as a Bloomberg-style ticker masthead. The dark band creates the strongest analytics-dashboard cue available in one move; it also mirrors the existing footer (symmetric framing). Easy to flip to a white statbar if the user pushes back — just swap the `.statbar` background and color values.
- **Gold (`#E8AE00`) chosen over a pure-yellow (`#FFD84D`) for the secondary accent.** Pure yellow on white reads as warning/alert in this kind of layout; gold reads as "honor/leader" and pairs better with the blue plaques. The pale-yellow leader-row wash (`--warn-1 #FFF7CC`) is the only place a near-pure yellow appears.
- **IBM Plex Sans over Inter Tight or Manrope.** Plex has the analytical-publication register (used by IBM, Mozilla, Stripe in similar contexts) and the open counters/short ascenders give better information density at the smaller body sizes the dashboard uses. Retained Barlow Semi Condensed for the plaque type — that's the RO street-sign convention and shouldn't move.
- **Emojis instead of an SVG icon sprite** because the user explicitly chose that route ("or emojis and we'll later look for icons"). Trade-off accepted: emoji rendering varies by OS (a Liberation/Symbola fallback on Linux looks worse than Apple Color Emoji on macOS). The `.emo` class isolates the emoji styling so swapping to inline SVG is a single search-and-replace later.
- **`:first-child` for leader highlight, not nth-child(-n+3).** Top-3 highlight would have been noisy across the ~10 rank lists on the page. Single-leader highlight reads as "the standout in this list" without competing with the bars themselves. Also works correctly under `column-count: 2` multicol because DOM order = visual order, so only rank 1 (DOM) gets the gold inset (not rank 16, despite both being column-tops).
- **Portrait placeholders use 2-letter initials parsed in Jinja** (`p.full_name.split()[0][0] + p.full_name.split()[-1][0]`) rather than a server-side helper. Trade-off: not robust to one-word names or names with mid-word particles, but acceptable for the placeholder state — it's meant to be replaced with `<img>` before this matters.

### Files touched
- `templates/index.html.j2` (CSS rewrite + emoji insertion + portrait scaffolding)
- `dist/index.html` (rebuilt, 263 KB — up from 252 KB; growth is the emoji codepoints and the slightly longer CSS)
- Verification screenshots: `ss-bold-1440-top.png`, `ss-bold-1440-full.png`

## 2026-05-16 — Header rebuild: județ filter, stats widget, drop search

### What was done
- Removed the section-2 search input. It was redundant with the județ filter and competed for header space.
- Wired up the județ filter that previously only showed "Toate". Added `by_judet` to `section2()` in `site_queries.py` — a per-județ top-30 with the same category logic as the national list, Bucharest sectors aggregated as 'B'. Replaced the chip row with a native `<select>` (all 42 județe, sorted alphabetically by Romanian name, displayed as "Cluj · CJ"). JS swaps the rendered list on change and rescales the bars to that județ's local max.
- Dropped the "Strada Principală · N apariții · exclusă" header callout and its principal/rest split in the section-2 JS. The split's logic took `top_names[0]` blindly as Principală, but that comment was stale — in the current sample, rank 1 is `florilor` (519). Principală sits at rank 12 (381) and now appears in the list at its actual position.
- Replaced the dark inline `.stats-bar` ticker with a light-background widget (`.statbar`). 4 modules: Scară (Adrese / Persoane onorate), Tematică (lead category % + 5-segment minibar pulling from `section5.theme_dist` using the same palette as the conic-gradient in the panel below + named breakdown), Repartiție pe gen (M% / F% + minibar), Cei mai des onorați (#1 B / #1 F with counts). Removed Județe and Wikidata counts — neither was a strong story to lead with.
- Statbar is responsive: 4 cols ≥ 1025px → 2×2 ≤ 1024px → single column ≤ 640px.

### Non-obvious decisions
- Stats-widget tematică palette deliberately reuses the conic-gradient colors from the Repartiție tematică panel (`#C04F35,#A0826A,#8BA888,#6E6E70,#B8A090,#3A3A3D`). Visually links the minibar at the top of the page with the donut chart below. The semantic oddity (`#C04F35` = accent red applied to *natură* which dominates) is inherited from the existing panel and worth revisiting site-wide later, not in this pass.
- The județ picker is a native `<select>` rather than a custom searchable combobox. Native gives free type-ahead, a11y, and mobile UX with zero JS. 42 entries is well within native-select usability.
- Top-3 categories in tematică subline only — bottom 2 ("date", "religios") are barely visible at 1-2% and would clutter the row.

## 2026-05-16 — RO blue street-plaques + promote dense layout to primary

### What was done
- Redesigned street-name plaques to follow the Romanian street-sign convention: white on signal blue (`#0E4D92`), with a dual text-shadow (faint top darkening + soft cast below) for a slightly engraved feel, and a tighter `2px 9px` padding (`1px 7px` for `.small`). Added `--plaque` token to `:root`. Updated `.rank-name.person` to clear the inherited text-shadow so plain person-name text doesn't pick up the engraved look.
- Promoted the dense layout to the project's primary deliverable. `templates/index.dense.html.j2` → `templates/index.html.j2` (the editorial layout it replaces was archived as `templates/index-v1.html.j2`). `build_site.py` `VARIANTS` and `--variant` choices updated accordingly; `--variant both` now renders `default + v1`.
- Slimmed `tests/test_build.py` to assertions that hold for the new primary layout. Dropped `test_section1_hero_content` and `test_section8_ciorani` — both were editorial-layout-specific (hero copy "99 din 100" and the Cioranii curiosity). 8 tests pass against the new `dist/index.html`.

### Non-obvious decisions
- Plaque variants explored under `dist/plaque-preview.html` (4 directions: classic enamel, signal blue, embossed gradient, flat-with-outline) and `dist/plaque-preview-b.html` (4 refinements of signal-blue varying padding and text-shadow). Chose **B4 · Engraved**: `text-shadow: 0 -0.5px 0 rgba(0,0,0,.30), 0 1px 1.5px rgba(0,0,0,.50)`. The negative-y component is what makes the type read as pressed into the plate rather than floating above it.
- Editorial layout was archived (not deleted) so its hero copy and Cioranii framing remain available if we want to revive any of it later. Available via `python3 build_site.py --variant v1` → `dist/index-v1.html`.
- Slimmed tests rather than rewriting copy-specific assertions against the new layout. The dense layout's copy is still being iterated; pinning copy-string tests now would just mean rewriting them on the next pass. Structural-anchor assertions (which already pass) are the durable shape of coverage for this phase.

## 2026-05-16 — Dense UI variant + atlas-style data panels

### What was done
- Added a parallel "dense" build of the dashboard. New template `templates/index.dense.html.j2` rendered via `python3 build_site.py --variant dense` (also `--variant both`); writes to `dist/index.dense.html`, leaving the existing `dist/index.html` untouched for side-by-side comparison.
- Switched the dense variant to a 12-column outer grid (`.panel.s4/s6/s8/s12`) with three responsive tiers: aggressive 3-up at desktop, 2-up at ≤1024px, single column at ≤640px. Stats bar now horizontally scrollable on mobile; nav collapses to brand only. Wide rank lists (top 30 frequent, top persons, top pageviews) use `column-count: 2` with `display: block` override (flex `.rank-list` blocked multicol — needed explicit override).
- Replaced Source Serif 4 with **Barlow Semi Condensed** (street names) + **Inter** (everything else). All `var(--serif)` usages removed; person names stay in Inter. Both fonts have full Romanian Latin Extended (`ă â î ș ț`).
- Removed Cioranii hero + "Cea mai poetică" longest-names columns from the curiozități area. Removed the standalone "Onorat doar aici" panel — the curated `persons` table has only 2 truly-unique-to-one-UAT entries, too thin to fill the panel.
- Added 4 new data-driven sections to the dense variant:
  - **Amprente județene** (s12, 3-col internal): top-8 județe by (a) most names found nowhere else with ≥3 streets local, (b) % nume natură ("rurale-poetice"), (c) % nume ideologic.
  - **Semnături regionale** (s6): up to 18 names where one județ holds ≥80% of all national occurrences (≥5 national). Tolocii 8/8 SV, Meduzei 7/8 CT, Suru 5/5 SB, Tánorok 5/5 HR, etc.
  - **Curiozități unice naționale** (s6): 14 atmospheric/geographic names existing in exactly 1 UAT in the country. Surfaced via positive prefix filter on landscape nouns (Valea/Dealul/Plaiul/Pârâul/Lunca/Poiana/Pădurea/Moara/Cetatea/Cheile/Coasta/Pietrele/…) with `ROW_NUMBER() OVER (PARTITION BY prefix)` so each prefix shows once for diversity.
  - **Conteste tematice** (s12, 3×2 cell grid): top-7 per family across Flori (8,493 streets / 107 distinct), Copaci (8,298 / 87), Păsări (1,527 / 43), Animale (697 / 25), Cer · lumină (1,237 / 25), Meserii (occupational + trade combined).
- Section 8 (`section8()` in `site_queries.py`) gained: `contests` (dict of 6 lemma lists via `_contest_by_nature` + `_contest_trades` helpers), `regional_signatures`, `local_uniques`, `judet_distinctive`, `judet_rural`, `judet_ideo`.
- Styled all street-name strings as **enamel plaques**: `.rank-name` and `.street-tag` get a thin `var(--ink)` border, `var(--bg)` background, weight 600 Barlow Semi Condensed, slight tracking. `.rank-name.person` overrides back to clean Inter 600 (no plaque) so person names in the top-persoane and pageviews lists stay typographic. Restructured the section-2 JS to emit `<span class="name-cell"><span class="rank-name">name</span><span class="tag">cat</span></span>` so the category pill sits beside the plaque, not inside it. Fingerprint top/rare lists use `.street-tag.small`.

### Numbers
- Default `dist/index.html`: 101 KB. Dense `dist/index.dense.html`: ~160 KB.
- Page height at 1440px: original ~4,500px → dense ~3,620px (with the 4 new substantive panels added). Without the new panels, dense bottomed out at ~2,757px.
- Mobile (≤640px): bodyWidth equals viewport, no horizontal overflow.

### Non-obvious decisions
- 1-UAT curiosities had to use a positive geographic-prefix filter, not an anti-join with `persons`. The curated persons table is partial, so the anti-join still leaked person names (Abraham Lincoln, A.C. Popovici, Acad. X). The prefix list (Valea, Dealul, …) is the load-bearing filter. `ROW_NUMBER() OVER (PARTITION BY prefix)` is what made the output diverse — naive alphabetical ordering surfaced 14 "Cetatea …" entries.
- Plaque outline uses `var(--ink)` border on `var(--bg)` (panel bg) rather than a filled coloured rectangle. Keeps the editorial earth-tone palette intact (no Bucharest navy/green) while still reading as a signage placard. Person names get the explicit `.person` override because boxing 20 person-rank rows in the top-persoane tower looked oppressive in early tests.
- `.rank-2col` needs `display: block` explicitly. Flex containers ignore `column-count`; the bug was masked by `getComputedStyle().columnCount === "2"` returning truthful values while the visual layout silently stayed single-column.
- Map fingerprint sizing dropped the original `* 1.6 / 2.6` multiplier — the dense map cell already gets 8/12 of the panel via `.map-grid`, so the SVG just uses `parentElement.clientWidth` directly.

## 2026-05-15 — Multi-provider LLM classifier + convergence tool

### What was done
- Refactored `tools/llm_classify.py` to support three providers via `--model MODEL` flag. Provider auto-detected from model name: `claude-*` → Anthropic SDK, `gemini-*` → Google REST API (raw urllib, no extra SDK), `<org>/<model>` → OpenRouter (urllib). Default unchanged (`claude-haiku-4-5-20251001`).
- `--out` now defaults to `data/curation/llm_<model-slug>.csv` (slug strips org prefix and YYYYMMDD date suffix), so parallel runs with different models write to separate files automatically.
- Added `--sleep` flag for rate-limit control (Google free tier needs ~4s between batches).
- Added `tools/llm_compare.py`: loads two output CSVs, reports agreement rate on the `table` field, lists disagreements sorted by frequency, and shows keys only in one file.
- Updated CLAUDE.md layout and common commands sections.

### Non-obvious decisions
- Used raw urllib for Google (Gemini REST API) instead of `google-generativeai` SDK — the SDK isn't installed and the REST API is simple enough. Avoids a new dependency.
- Kept Anthropic on the native SDK (not OpenRouter) so existing `ANTHROPIC_API_KEY` workflows require no changes.

## 2026-05-15 — Fix wrong QIDs; add --replay-csv to wikidata_persons.py

### What was done
- Added `--replay-csv` and `--force` flags to `tools/wikidata_persons.py`. Reads all `auto_match=True` rows from `data/curation/wikidata_qids.csv` and re-applies QIDs to the DB — canonical post-rebuild restoration step. `--force` overwrites conflicts (needed because seed scripts load unverified QIDs that the curated CSV should supersede).
- Fixed 6 wrong QIDs in seed scripts (seed_top500.py, seed_batch2.py) that had been seeded with stale or commune-matching QIDs. Affected persons: Gheorghe Lazăr (×2), Traian Vuia, Tudor Vianu, Gábor Áron.
- Fixed 2 wrong QIDs in `data/curation/wikidata_qids.csv`: Simion Bărnuțiu (Q136671938→Q701594), Traian/Emperor (Q105974734→Q1425). Added 5 missing CSV entries for the seed-only persons (no row existed in CSV for gabor aron, gheorghe lazar, lazar gheorghe, traian vuia, tudor vianu).
- Re-ran `tools/wiki_scope.py` for the 7 corrected persons. All now resolved (were returning 0 sitelinks due to stale QIDs). Final scope: 19 local / 168 national / 19 universal / 0 unknown.
- Updated CLAUDE.md with canonical post-rebuild sequence including `--replay-csv --force` and `wiki_scope.py` batch guidance.

### Non-obvious decisions
- Wrong QIDs for these 6 persons traced to training-data hallucinations in the original seed scripts — numbers that looked plausible (Q647xxx range) but pointed to deleted/redirected entities with 0 sitelinks. The `--replay-csv --force` pattern was specifically designed to survive this: the curated CSV overwrites seed-script values after every rebuild.
- `simion barnutiu` CSV entry had a high-numbered QID (Q136671938) that existed on Wikidata but had 0 sitelinks — a different item with the same name. Correct QID is Q701594 (the well-known Romanian academic with 13 language editions).

## 2026-05-15 — streets_classified_pct view + coverage queries

### What was done
- Added `CREATE VIEW streets_classified_pct` to `build_db.py` (right after `streets_dedup`). One row per distinct `core_name_norm`; columns: `core_name_norm`, `street_count`, `classification` (first matching bucket: numeric/date/saint/person/nature/category/place, or NULL for unclassified).
- Applied the view to the current DB without a full rebuild (`DROP VIEW IF EXISTS` + `CREATE VIEW`).
- Added two named queries to `docs/queries.sql`: `classification_coverage` (breakdown by category with street-weighted %) and `classification_coverage_summary` (single-row totals).
- Marked P1 backlog item as done.

### Coverage numbers at this point
- 29,302 distinct classified-eligible keys; 1,450 classified (4.9% of keys)
- 104,236 total streets; 62,382 classified (59.8% by frequency)
- Largest unclassified mass: 27,852 unique name-keys representing 41,854 streets (the long tail of rare or local street names)

### Non-obvious decisions
- View uses `MAX(is_numeric/is_date/is_saint)` over the `streets_dedup` group so the flags aggregate correctly across UATs sharing a `core_name_norm`.
- Priority order in CASE: numeric/date/saint flags first, then lookup table joins. A street flagged `is_saint=1` that also appears in `persons` is counted as `saint`.

## 2026-05-15 — wiki_scope.py run: recognition scope and pageviews populated for all 300 persons

### What was done
- Ran `tools/wiki_scope.py` to populate `wiki_sitelinks`, `wiki_scope`, `wiki_ro_views`, and Wikipedia URLs for the 55 newly-QID-matched persons (previous sessions had covered the other 245).
- Final scope distribution across all 300 QID-matched persons: **32 universal, 210 national, 48 local, 10 unknown**.
- Notable highs: Vlad Tepes (90 langs, 14k ro_views/month), Stefan cel Mare (53 langs, 15.7k ro_views/month), Matei Corvin (70 langs).
- Handled a 429 rate-limit error that falsely marked 5 persons as `unknown` (Vlad Tepes, Stefan cel Mare, etc.): reset them to NULL and re-ran.
- Site builds cleanly with real Section 4 data (tier counts: 32 universal / 210 national / 58 local+unknown).

### Non-obvious decisions
- Re-run strategy for rate-limited rows: reset `wiki_scope=NULL` so the tool's `WHERE wiki_scope IS NULL` filter re-picks them up. No `--force` flag needed.
- Known data artifact: persons with multiple `core_name_norm` variants (e.g., 'mihai eminescu' and 'eminescu') appear as duplicate rows in the section4 query. This is the identity-deduplication gap acknowledged in CLAUDE.md as out-of-scope for this phase.

## 2026-05-15 — Manual QID review: 300 persons now matched to Wikidata

### What was done
- **Committed QID uniqueness guard** in `tools/wikidata_persons.py` — before writing a QID auto-match, the tool now checks if that QID is already assigned to a different `core_name_norm`. Duplicate is logged, written to CSV with `auto_match=False` and blank QID, and skipped.
- **Resolved all 43 `auto_match=False` rows** from `data/curation/wikidata_qids.csv`. Prior count was 248 matched; now 300 out of 310 persons have verified Wikidata QIDs. 10 remain without (folklore/legendary figures with no Wikidata entity, disambiguation cases, and hyper-local persons).
- **Corrected two wrong QIDs from the tool's 0.70-confidence suggestions:** `c.i. parhon` (was Q52452470 = a scientific article, corrected to Q612177 = Constantin Ion Parhon) and `Ioan ratiu` (was Q12723573 = a memorial house, corrected to Q14543073 = Ioan Rațiu the politician).
- **Updated `data/curation/wikidata_qids.csv`** with all confirmed QIDs set to `auto_match=True, confidence=1.00`, so they can be replayed after a DB rebuild (pending `--replay-csv` flag in `wikidata_persons.py`).
- **Backlog:** marked manual QID review as done, marked uniqueness guard as done, added `--replay-csv` flag as next tooling task for rebuild persistence.

### Non-obvious decisions
- `horia,closca si crisan` (collective street entry): assigned Horea's QID (Q1656593) as the primary figure. Cloșca and Crișan have no dedicated Wikidata entity separate from disambiguation pages.
- `george baritiu` and `gheorghe baritiu` are stored as separate `core_name_norm` keys but refer to the same person (George Barițiu, Q445042). Both assigned the same QID. Deduplication of person identities is a separate future task.
- 10 final no-QID persons: `closca`, `banu maracine`, `voinicului`, `brates`, `nicovalei`, `iosif sarbu`, `ion arion`, `eugen hulea`, `aleea sf. eugeniu`, `mos ion roata`. These are genuinely not findable on Wikidata or are multi-meaning disambiguation targets.
- Used Wikipedia API (`wbpageprops` endpoint) to get QIDs for persons the Wikidata search couldn't find due to name collisions with Romanian communes (Avram Iancu, Cloșca).

## 2026-05-06 — Static site build complete: all 8 sections + D3 choropleth + footer

### What was done
- **Completed Tasks 4–11** of the static site implementation plan (subagent-driven execution).
- **Templates/index.html.j2** — added 8 interactive sections + footer (1,779 lines total):
  - Section 1 (Acasă): hero headline "99 din 100 de români onorați pe străzi sunt bărbați" with gender comparison charts (top men/women by street count)
  - Section 2 (Cele mai întâlnite): searchable top-50 street names with diacritics-aware live filtering, Principală callout, category tags
  - Section 3 (Pe cine onorăm): gender gap grid (100 CSS squares), top-20 persons tower chart, profession/era distribution bars
  - Section 4 (Recunoaștere): Wikidata tier cards (Universal/National/Local), pageviews rank list with recognition scope coloring
  - Section 5 (Tematică): CSS conic-gradient donut chart showing theme distribution, nature subtypes, ideological tokens with dynamic color logic
  - Section 6 (Harta): D3 v7 choropleth map of Romania's 41 counties, 3-metric switcher (% saints / % numeric / % female names), county fingerprint panel on click
  - Section 7 (Renumiri): static illustrative rename cards (marked "în construcție") with 4 before/after examples
  - Section 8 (Curiozități): CIORANI hero (227 numeric streets in Comuna Cioranii de Jos), 3 curiosity cards (longest names, animal names top-10, locally honored persons)
  - Footer: dark background with 3-column layout (Despre date / Metodologie / Cod sursă), dynamic address count from section1 data
- **build_site.py** — added `--serve` flag: builds site then starts http.server.test() on localhost:8000 for local development
- **tests/test_build.py** — added 9 new content assertions (one per major section/feature)
- **docs/BACKLOG.md** — added item for Section 7 renaming data source integration
- **.gitignore** — added `.superpowers/` for Claude Code artifacts
- All 17 tests passing (100%). Single commit: `feat(site): all 8 sections complete with D3 choropleth, footer, and --serve flag`

### Key implementation details
- **Data embedding:** 6 DATA_* JSON variables injected into template head (`DATA_S1` through `DATA_S8`), computed from SQLite queries
- **Interactive search (S2):** diacritics-aware via `normalize('NFD').replace(/[̀-ͯ]/g, '')`, live re-render to 25 results
- **D3 choropleth (S6):** loads `ro-counties.geojson` from dist/, uses `geoMercator` projection, metric switcher with dynamic color scale, click handler for county fingerprint
- **CSS conic-gradient donut (S5):** theme percentages computed at render time via Jinja2 loop with cumulative tracking
- **Single-file output:** 97 KB HTML with embedded CSS, JS, and CDN scripts (D3, TopoJSON) — ready for static deployment

### Non-obvious decisions
- **Single subagent for 8 tasks:** User chose subagent-driven development with "1 sub-agent drive". Implementer worked through all tasks 4–11 sequentially in one session, completing entire feature set without intermediate reviews.
- **Section 7 deferred:** Renaming data source not yet available; section uses static illustrative data with explicit "în construcție" notice + backlog entry, avoiding placeholder code.
- **GeoJSON property resolution:** D3 code handles both `mnemonic` and `name` properties at runtime to accommodate different GeoJSON sources; the exact property key for județ codes is flexible.
- **D3 over Observable Plot:** Despite Plot appearing in original spec, all charts ended up CSS + inline HTML (bars, grid, donut, rank lists) — more performant than Plot CDN for static data. Plot script left out.

### Verification
- Tested locally: `python3 build_site.py --serve` → http://localhost:8000 renders all 8 sections with real data from SQLite
- All query functions tested and passing (section1–section8 shape tests + smoke test)
- GeoJSON copied correctly to dist/ on each build
- D3 choropleth renders 41 counties, metric switching works, fingerprint panel updates on county click

---

## 2026-05-04 — Wikidata QID matching + Wikipedia scope/pageview enrichment

### What was done
- **`tools/wikidata_persons.py`** — major rewrite of the previously non-functional tool:
  - Fixed CSV quoting (was bare f-string concatenation; names with commas broke the output)
  - Added resume support: reads existing output CSV at startup, skips already-processed keys
  - Added direct DB write-back for auto-matched results (conf ≥ 0.95); no longer orphaned in CSV
  - Added 429 retry with exponential backoff (5 / 10 / 20s); API errors no longer written as "no match" (entry stays out of CSV to be retried next run)
  - Increased base sleep to 2s
  - Added `--db`, `--out`, `--dry-run` args
  - Run produced 183 QIDs written to DB from 248 missing persons; 12 rows need manual review (conf < 0.95)
- **`tools/wiki_scope.py`** — extended with three new signals:
  - `wiki_ro_url` / `wiki_en_url` — Wikipedia article URLs for Romanian and English editions, extracted from sitelinks (no extra API calls)
  - `wiki_ro_views` — average monthly Romanian Wikipedia pageviews (last 12 months) via Wikimedia REST API
  - Fixed URL encoding (`safe="_:/"` not `safe=""`)
- **`build_db.py`** — added `wiki_ro_url TEXT`, `wiki_en_url TEXT`, `wiki_ro_views INTEGER` to `persons` schema
- **`tools/llm_classify.py`** — fixed `--limit 0` bug (was interpreted as SQL `LIMIT 0`, fetched nothing; now treated as "all")
- Ran full LLM classification of remaining 306 unclassified keys: 292 classified, 14 skipped; coverage moved from 56.9% → 60.1%

### Non-obvious decisions
- Romanian pageviews added over other signals (edit count, article age, article length) because they directly measure *living cultural memory* — how much Romanians actively read about a person today. Sitelinks = breadth; ro_views = depth of local recognition.
- API errors in `wikidata_persons.py` are intentionally *not* written to the CSV so that re-running automatically retries them. Only definitive results (found or genuinely not found) are recorded.
- Known data issue: `cuza voda` and `a. i. cuza` were assigned Michel Vorm's QID (Q208518) — a false positive from the wikidata search. Fixed manually; QID uniqueness guard added to BACKLOG.

## 2026-04-28 — Fix G-ral abbreviation mismatch in OSM matching

### What was done
- Identified that `normalize_match()` in `streets_lib.py` preserved hyphens, causing registry "G-ral" to normalize to `g-ral` while OSM stores "General". This blocked 85+ matches for "G-ral Eremia Grigorescu" (28 UATs) and related military-rank streets.
- Added `_ABBR_EXPANSIONS` list to `streets_lib.py` with a case-insensitive word-boundary regex for `G[-.]ral` → `General`. Expansion runs before the NFKD/lowercase step so downstream normalization is unaffected.
- Patched 328 affected `streets` rows in-place (UPDATE on `name_normalized` + `core_name_norm`) — no full rebuild needed since the pattern replacement is unambiguous.
- Re-ran `osm_match.py`: fuzzy matches 56,002 → 56,087 (+85). Registry coverage 52.1% → 52.2%.
- Re-ran `osm_score.py`: all 105,905 rows rescored.
- Closed DUMBRĂVIȚA (BV) entropy backlog item — was a sample artifact (1 street in dev sample vs 10 in full dataset, maximum entropy).

### Non-obvious decisions
- Regex `\bG[-.]ral\b` with `re.IGNORECASE` covers both "G-ral" and "G.ral" variants. Word-boundary ensures it doesn't match inside longer tokens.
- Expansion runs before NFKD normalization because the NFKD step lowercases; doing it after would require the regex to match only lowercase.
- Only `g-ral` was fixed. `prof.dr.` affects only 4 UATs (trivial). `sfantul`/`sfanta` mismatches are UAT centroid precision issues, not abbreviation issues.
- The +85 new matches were specifically for "General Eremia Grigorescu" and related streets; verified by spot-checking `streets_dedup` for `name_normalized LIKE '%general eremia%'`.

## 2026-04-28 — OSM pipeline end-to-end (ingest → match → score → sanity)

### What was done
- Downloaded Romania PBF from Geofabrik (303 MB, snapshot 2026-04-28) to `data/reference/romania-latest.osm.pbf`.
- Installed `osmium` 4.3.1 + `shapely` 2.1.2 in the project venv (`~/devbox/envs/240826/`). `pyrosm` could not be installed on Python 3.12 — `pyrobuf` dependency fails with `AttributeError: 'PyrobufDistribution' object has no attribute 'dry_run'` (setuptools compatibility breakage).
- Rewrote `tools/osm_ingest.py`: replaced pyrosm/geopandas with osmium's `SimpleHandler.apply_file(locations=True)` + shapely. UAT assignment changed from polygon containment to **nearest-centroid with a 0.5°×0.5° spatial grid** (fast enough for 4M ways × 1207 UATs without numpy). Added `_BUCHAREST_SECTOR_CENTROIDS` hardcode for the 6 sector SIRUTAs (179141–179196) absent from the coords CSV.
- Fixed `osm_sanity.py` reference SIRUTA codes: 143426→143450 (MUNICIPIUL SIBIU), 146734→146502 (MUNICIPIUL CÂMPULUNG MOLDOVENESC, SV), 132581→132805 (CORNU, PH). The original codes were from the SIRUTA coords CSV and didn't match registry codes.
- Ran full pipeline:
  - `osm_ingest.py --rebuild`: 4M ways scanned, 105,905 (UAT, street) groups, 0 skipped.
  - `osm_match.py`: 490 exact_normalized + 56,002 fuzzy_core_name = 56,492 matches. Registry coverage 52.1%, OSM coverage 53.3%.
  - `osm_score.py`: 105,905 rows scored across 1,185 UATs.
  - `osm_sanity.py`: top-10 lists for all 5 reference UATs look correct. Coverage: Cluj 75.3%, Sibiu 77.3%, Câmpulung 64.1%, Cornu 64.5%, București Sector 1 31.5% (known issue — see BACKLOG).
- Updated `docs/CODE_SPEC.md` §11.1 (snapshot date), §11.2 (osmium replaces pyrosm), §11.5 (centroid approach replaces polygon containment). Updated `CLAUDE.md` common commands.

### Non-obvious decisions
- **Nearest-centroid instead of polygon containment**: The polygon approach required pyrosm/geopandas (unavailable on Py3.12). Centroid assignment is sufficient for importance scoring, which is per-UAT z-scored anyway — a way misassigned to an adjacent UAT doesn't corrupt the scoring of its true UAT.
- **Bucharest sector centroids hardcoded**: The SIRUTA coords CSV has only the municipality code (179132), not the 6 sector codes. Hardcoded approximate centroids are reasonable for v1 — sectors are well-known geographic areas. Accuracy is limited (31% coverage) but the rest of Romania is unaffected.
- **Low pass 1 count (490)**: OSM often omits the street type prefix from `name` tags (just "Mihai Eminescu" not "Strada Mihai Eminescu"), so `name_normalized` rarely matches between registry and OSM. `core_name_norm` (pass 2) does the work.
- **Spatial grid step 0.5°**: At Romanian latitudes, 0.5° ≈ 50 km. Average UAT density in the grid: ~6 UATs/cell. Each way checks 9 cells × 6 = 54 candidates — fast enough in pure Python (~15 min total for 4M ways).

### Verification
- `osm_sanity.py`: top-10 rankings for Cluj, Sibiu, Câmpulung, Cornu match expected main roads. Unmatched OSM top list shows Transfăgărășan, Transalpina, generic "Strada Principală" — all explainable (scenic cross-commune roads, no registered voters).

---

## 2026-04-28 — Fix P1 query bugs

### What was done
- `docs/queries.sql` `:name communist_aliases`: added `DISTINCT` to `SELECT` to eliminate duplicate rows caused by the same street spanning multiple polling sections in the raw `streets` table.
- `docs/queries.sql` `:name unique_names`: added `WHERE is_numeric = 0 AND is_date = 0 AND name NOT REGEXP '^\d'` to filter out section-prefixed numeric artifact names (e.g. "1 1 Mai", "1 22 Decembrie 1989") that were polluting the hapax list.
- Marked both P1 backlog items as complete.

### Non-obvious decisions
- `communist_aliases` cannot be rewritten to use `streets_dedup` because `street_aliases` is keyed to `streets.id`. DISTINCT on output is the correct fix, consistent with `real_renamings` which uses the same pattern.
- `name NOT REGEXP '^\d'` catches names that evade both `is_numeric` and `is_date` flags — these are a data artifact from section-numbering in the source registry, not real street names.

---


## 2026-04-28 — OSM enrichment scaffolding

### What was done
- Designed an OSM enrichment pipeline scoped to **populated areas only** (motorways/trunks excluded by design). Plan saved at `~/.claude/plans/we-d-only-be-interested-magical-sutton.md`.
- Extracted `normalize_match`, `fix_diacritics`, `STREET_TYPES`, plus a new `strip_street_type` helper into `streets_lib.py`. `build_db.py` now imports them; behavior unchanged (verified with `--limit 500` and a full rebuild — same row counts as before).
- Added two empty tables to `build_db.py`: `osm_streets` (one row per `(uat_siruta, name_normalized)`, mirrors `streets_dedup`'s grain) and `street_osm_matches` (link table with `match_type` + `confidence`).
- Wrote four scripts under `tools/`:
  - `osm_ingest.py` — PBF → `osm_streets`. Builds populated-area mask from `admin_level=8 ∩ (place=* ∪ landuse=residential ∪ buffered place nodes)`. Groups OSM ways by `(uat, normalized name)` so one logical street = one row. Lazy-imports `pyrosm`/`shapely` so the file is importable without those deps.
  - `osm_match.py` — Pure-SQL, two-pass join: exact `name_normalized` (confidence 1.0), then `core_name_norm` fallback for unmatched (0.6). Tested with synthetic rows.
  - `osm_score.py` — `importance_v1 = highway_weight × log(1+length_m) + ref_bonus`, then per-UAT z-score. Tested end-to-end on three Bucharest stub rows: Calea Victoriei (40.0) > Bd. Magheru (36.6) > Strada Ada Kaleh (11.1).
  - `osm_sanity.py` — Read-only report: top-10 by score for 5 reference UATs (Bucharest Sector 1, Cluj-Napoca, Sibiu, Câmpulung Moldovenesc, Cornu) + per-UAT registry coverage + sample of OSM-only streets.
- Updated `docs/CODE_SPEC.md` (new §11 OSM enrichment pipeline; old §11/12 renumbered to §12/13/14), `CLAUDE.md` (commands + two new critical rules about OSM grouping and scope), `docs/BACKLOG.md` (marked scaffolding done; added concrete download steps and v2 betweenness item).

### Deferred
- PBF download (~700 MB) and `pip install pyrosm shapely` postponed because user was on mobile data. All steps documented in `docs/BACKLOG.md` for the next session on wired connection.

### Non-obvious decisions
- **`pyrosm` is the only documented exception to the stdlib-only ETL rule.** PBF parsing without bindings isn't feasible; `geopandas` is intentionally avoided (heavier dep tree, no benefit). Justified in CODE_SPEC §11.2.
- **No POI counts in the score.** OSM POI density correlates with mapper activity, not street importance — including it would measure Bucharest enthusiasm vs rural neglect rather than the thing we want to rank.
- **No Levenshtein fallback in matching.** With ~100k×100k name pairs, fuzzy matching produces enough false positives to poison the importance index downstream. We surface gaps in `osm_sanity.py` instead and accept some unmatched rows on both sides.
- **Per-UAT z-score is the comparable axis, not raw `importance_v1`.** Without it, Bucharest dominates everything by length alone. `raw` is informational; `importance_v1_uat_z` is what dashboards should rank by.
- **Highway-class promotion across way segments.** When an OSM street has segments tagged with different `highway` values (common — a `primary` street can have `service` slip-roads), the merged row keeps the highest class. Mirrors how a human would describe the street.

### Verification
- `build_db.py --limit 500` → identical row counts after refactor.
- Full rebuild (`build_db.py` + `seed_lookups.py` + both `seed_*` tools): 127,364 rows / 105,107 deduped, all curated tables seeded as before.
- `osm_ingest.py` errors cleanly with helpful download instructions when PBF is missing.
- `osm_match.py` and `osm_sanity.py` error cleanly when `osm_streets` is empty.
- `osm_match.py` end-to-end test with 5 synthetic registry-derived rows: 5/5 exact matches.
- `osm_score.py` end-to-end test with 3 synthetic Bucharest rows: ranking matches intuition.

---

## 2026-04-27 — LLM classifier + CLAUDE.md housekeeping

### What was done
- Fixed stale CLAUDE.md: corrected all paths (`docs/`, `data/reference/`, `data/streets.db`), updated layout tree to include `tools/` and `docs/`, rewrote common commands to cover full curation pipeline. Closes P0 backlog item.
- Wrote `tools/llm_classify.py`: Claude Haiku (`claude-haiku-4-5-20251001`) batch classifier. Queries top-N unclassified `core_name_norm` keys from DB, sends in configurable batches (default 20), appends results to a CSV consumable by `import_csv.py`. Resumable (skips keys already in output file). `--import` flag runs the import step automatically. Requires `ANTHROPIC_API_KEY` in environment.
- Updated BACKLOG: refactored to checkbox format, marked completed items, added OSM enrichment and RoWordNet items.

### Non-obvious decisions
- LLM output CSV is append-only (not overwrite) to enable resume after partial runs. The `processed` set is built from the existing CSV at startup, not from the DB, so keys written but not yet imported are still skipped on re-run.
- `--batch-size` defaults to 20 — balances API latency against prompt length. At 20 keys × ~100 chars context each, the input is well under Haiku's context limit and the JSON output parses reliably.

---

## 2026-04-27 — Batch 2 curation (47.6% → 56.9% street coverage)

### What was done
- Ran `tools/seed_batch2.py` (written in previous session): generated and imported `data/curation/classified_batch2.csv` with 497 entries — 122 nature terms, 116 persons, 173 name categories, 86 place references.
- Duplicates in the PERSONS/CATEGORIES lists are silently deduplicated by the `seen` set in the script; idempotent on re-run.

### Coverage after (105,107 deduped streets)
| status | streets | pct |
|--------|---------|-----|
| unclassified | 45,286 | 43.1% |
| nature | 27,356 | 26.0% |
| category | 14,849 | 14.1% |
| person | 11,297 | 10.7% |
| place | 4,343 | 4.1% |
| numeric+date+religious | 1,976 | 1.9% |

### Non-obvious decisions
- `bistrita` maps to both `ro_city` (Bistrița city) and `river` (Bistrița river) — only the city entry survived dedup (river entry was listed second). Street context is ambiguous; accepted for now.
- `sucevei` similarly maps to both river and city — city entry kept (first seen wins in the script).
- `timisoarei` appeared in PERSONS list as a sentinel skip (full_name=None); correct, it's a place not a person. Classified correctly as `ro_city` via the PLACES list.
- Several Hungarian-minority honorees added (Bartók, Arany, Jókai, József Attila, Kossuth, Bethlen, Gábor Áron) — nationality set to `HU`, important for the foreign_honorees query.

---

## 2026-04-26 — Top-500 pre-classification (16.6% → 47.6% street coverage)

### What was done
- Fixed 6 wrong join keys in `seed_lookups.py`: royalty entries (`regele carol i` → `carol i`, `regele ferdinand` → `ferdinand`, `regina maria` → `maria`, `regina elisabeta` → `elisabeta`), `pintea haiducul` → `pintea`, and `george topârceanu` → `george toparceanu` (diacritic in key broke ASCII normalization join).
- Wrote `tools/seed_top500.py`: generates + imports `data/curation/classified_top500.csv` with 447 entries — 193 nature terms, 94 persons, 105 name categories, 55 place references.
- Rebuilt DB, re-applied seed, applied top-500 classification.

### Coverage after (105,107 deduped streets)
| status        | streets | pct |
|---------------|---------|-----|
| unclassified  | 55,077  | 52.4% |
| nature        | 23,925  | 22.8% |
| category      | 11,504  | 10.9% |
| person        | 9,665   | 9.2% |
| place         | 2,960   | 2.8% |
| numeric+date+religious | 1,976 | 1.9% |

### Non-obvious decisions
- Royalty entries with rank prefixes: `Regele`/`Regina` are in the RANKS list, so `Strada Regele Carol I` → core_name_norm = `carol i` (rank stripped). Seed keys must match the normalized core_name, not the full display form.
- Roman deities/planets (Venus, Saturn, etc.) → `name_categories/mythology` rather than `place_refs` since streets across inland Romania are named after the deities, not the Black Sea resorts.
- `traian` → persons entry as Emperor Trajan (nationality NULL — Roman, not Romanian). Common Romanian first name complicates this but the street context is almost always the emperor.

---

## 2026-04-26 — P1 curation tooling: export + import + coverage queries

### What was done
- `tools/export_unclassified.py` — queries unclassified `core_name_norm` (excluding numeric/date/saint, excluding already-curated keys), exports to `data/curation/unclassified.csv` with frequency, județe count, sample name, and blank columns for all four lookup tables. `--limit 0` exports all.
- `tools/import_csv.py` — reads a classified CSV (same shape as the export), upserts into the correct lookup table based on the `table` column. Skips blank-table rows. Validates required fields per table. `--dry-run` flag for safe previewing. Rolls back on any error.
- Added `coverage_summary` and `coverage_names` named queries to `docs/queries.sql`.
- Created `data/curation/` directory and generated initial `unclassified.csv` (top-500 by frequency).

### Key numbers after first export
- 29,199 distinct classifiable `core_name_norm` keys
- 87 curated (0.3%) — the seed is nearly negligible at full scale
- 83.4% of streets unclassified at street level

### Non-obvious decisions
- Import CSV has columns for all four tables in one row — only the columns relevant to `table` are used; the rest are ignored. Simpler than separate per-table CSVs for a human doing mixed curation.
- Export excludes `is_saint=1` rows from the unclassified pool — saints are already classified via flag.
- `--limit 0` sentinel exports everything (no SQL LIMIT clause appended).

---

## 2026-04-26 — P0 complete: full 141k build running

### What was done
- Fixed hardcoded `/home/claude/` paths in `build_db.py`, `seed_lookups.py`, and `run_queries.py`. All three scripts now accept `--db` / `--src` / `--sql` CLI args with correct defaults pointing at `data/reference/` and `data/streets.db`.
- Added `--limit N` flag to `build_db.py` for fast iteration.
- Ran the full build against `data/reference/registrul sectiilor de vot 14.05.2025.xlsx` (141,643 source rows).
- Applied seed lookups and ran the full query catalog baseline.

### Key numbers (full build)
- 127,364 rows ingested (remainder had null `Arteră`)
- 105,107 deduped streets across 1,155 UATs, 42 județe (41 + B as 6 sectors)
- 17,015 aliases
- 30,106 distinct normalized names
- 87,664 unclassified (83%) — curation headroom is enormous

### Non-obvious decisions
- `--limit` checks `inserted >= LIMIT` (after insert), not the row counter `i`, so the limit is exact regardless of null-artery skips.
- Kept `--src` and `--db` as overridable args rather than hardcoded constants; makes it easy to test against the sample xlsx without changing source.
