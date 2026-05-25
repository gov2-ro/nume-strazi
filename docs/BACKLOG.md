# Backlog

Items detected during sessions. Each entry has enough context to act on cold.

---

## P0

- [x] **Fix stale CLAUDE.md layout section** — The `## Repository layout` and `## Common commands` sections describe a different layout than what exists: docs are in `docs/` (not root), DB lives at `data/streets.db` (not `streets.db` in root), source xlsx is in `data/reference/` (not `data/source/`), and `--limit N` flag is already implemented (remove the "(P0 task in CODE_SPEC)" note).

---

## P0

- [x] **Fix relative links that break on detail pages** — Done 2026-05-18. Audit covered both Jinja-rendered HTML and JS template literals. `metodologie.html`, `index.html`, and `portraits/` references in `index.html.j2`, `index-v1.html.j2`, `index-v2.html.j2`, and `metodologie.html.j2` converted to root-relative. Detail templates were already root-relative. Confirmed zero relative `metodologie.html` / `portraits/` references in the rebuilt landing pages.

---

## P1

- [x] **`communist_aliases` query missing DISTINCT** — `docs/queries.sql` `:name communist_aliases` produces duplicate rows: same `(current_name, communist_alias, uat)` triplet repeated once per polling section. The query joins `streets` (not `streets_dedup`) and doesn't use `SELECT DISTINCT`. Fix: add `DISTINCT` or rewrite to join via `streets_dedup`.

- [x] **`unique_names` query polluted by numbered-street names** — `:name unique_names` surfaces names like "1 1 Mai", "1 22 Decembrie 1989" from DJ — strings that parse as `is_numeric=0` but are really section-prefixed street numbers. Consider adding `WHERE is_numeric = 0 AND name NOT REGEXP '^\d'` or filtering in post-processing.

- [x] **Investigate DUMBRĂVIȚA (BV) near-zero entropy** — Was a sample artifact: the 4-județ dev sample included only 1 DUMBRĂVIȚA street. Full dataset has 10 streets, all distinct names, maximum entropy. Closed.

- [ ] **Curation tooling (from CODE_SPEC P1)**
  - [x] `tools/export_unclassified.py` — top-N unclassified `core_name_norm` ordered by frequency, with sample streets/UATs
  - [x] `tools/import_csv.py` — generic upserter for the 4 lookup tables
  - [x] `tools/wikidata_persons.py` — search Wikidata for QIDs for persons missing them; idempotent CSV audit trail; writes auto-matches (conf ≥ 0.95) directly to DB
  - [x] `tools/llm_classify.py` — Claude Haiku batch classifier (rate-limited, idempotent)
  - [x] Coverage view: `streets_classified_pct` — per-key classification with street_count. Two named queries added: `classification_coverage` (by category) and `classification_coverage_summary` (single-row totals). Current: 59.8% of streets classified by frequency; 4.9% of unique keys.
  - [x] **Manual QID review** — All 43 `auto_match=False` rows resolved: 300 persons now have QIDs. 10 remain without (folklore characters, disambiguation cases, hyper-local figures). CSV updated with confirmed QIDs (`auto_match=True`, `confidence=1.00`).
  - [x] **QID uniqueness guard in `wikidata_persons.py`** — Two entries (`cuza voda`, `a. i. cuza`) were assigned Michel Vorm's QID (Q208518) instead of Q294832, because the wikidata search returned a wrong top match with confidence 0.95. Fix: before writing a QID, check if it's already assigned to a *different* `core_name_norm` in `persons` and warn/skip if so. Fixed manually: `UPDATE persons SET wikidata_qid='Q294832' WHERE core_name_norm IN ('cuza voda', 'a. i. cuza')` + re-run `wiki_scope.py`.
  - [x] **QID rebuild persistence** — Manual QID assignments in DB don't survive `build_db.py` + `seed_lookups.py` rebuild. The CSV (`data/curation/wikidata_qids.csv`) is now the authoritative record. Added `--replay-csv` and `--force` flags to `wikidata_persons.py`. Rebuild sequence: `build_db.py → seed_lookups.py → seed_top500.py → seed_batch2.py → wikidata_persons.py --replay-csv --force → wiki_scope.py (in batches of ~40)`.

- **Classification pipeline decision (settled):** run `llm_classify.py` directly on all unclassified keys. No `rule_classify.py` pre-filter, no spaCy/RoWordNet middle tier. Rationale: full 28k-key run costs ~$2 at Haiku pricing, making rule/NLP pre-filters a complexity cost that saves nothing. LLM handles Romanian morphology and cultural context better than a lemmatizer+wordnet chain would anyway. RoWordNet remains a P3 option only if API-free reproducibility becomes a hard requirement.

---

## P2

- [ ] **Reconsider pre-rendering ~3k detail pages now that the DB ships to clients** — Done 2026-05-19, the client-side sql.js-httpvfs layer means any detail (street/person/UAT) can be rendered live in the browser from a slug in the URL. Currently `build_site.py --detail` writes 3,042 HTML files (streets, persons, UATs, themes). A SPA approach: one `dist/strada/index.html` template that reads the slug from `location.pathname`, queries the shipped DB, renders. Same for `/persoana/`, `/oras/`, `/tema/`. Tradeoffs: removes ~50 MB of static output and a slow build step; degrades SEO for individual streets unless we keep a thin static stub per slug + client hydration. Measure before deciding — most visits land on the landing page, the long tail may not justify the build cost.

- [x] **Trim DB further by column / row pruning** — Done 2026-05-20. `tools/build_dist_db.py` now materializes `streets_dedup` as a real table (dropping the view + underlying `streets` table), retaining only the 11 columns referenced by `db-client.js`. Drops `id`, `artera_raw`, `title`, `rank`. Also drops `streets_classified_pct` view. Result: 30 MB → 13.5 MB (−59%).

- [x] **Optimize `/browser` page load and filter responsiveness** — Done 2026-05-20. `build_site.py` now generates `dist/browser/data.json` (~3 MB) via `site_queries.browser_export()`. Compact view uses pure JS filtering over 30k pre-loaded rows — no WASM, no SQL on initial load. Table view still loads WASM lazily on first switch. `dist/browser/index.html` updated accordingly.

- [x] **Live statistics bar for current Browser selection** — Done 2026-05-20. `.stats-bar` strip below the result count bar shows: top-3 classification types (%), gender split (F/M %), top profession, top era, top nationality. Computed from the in-memory filtered rows on every filter change — zero DB queries. Hides when result set is empty.

- [x] **Keyboard navigation for Browser filter bar** — Done 2026-05-20. `tabindex="0"` + `role="button"` on all 7 `.fdd-btn` divs; `tabindex="-1"` + `role="option"` on all `.fdd-item` elements. `/` shortcut focuses search; Enter/Space opens focused dropdown; ArrowDown/Up navigates items (ArrowUp from top returns focus to button); Escape closes + returns focus to button. Escape on search blurs it.

- [x] **Scope UAT detail page generation to județe capitals + county seats only** — Done 2026-05-18. `site_queries.enumerate_uats()` now filters to (a) 41 county seats via hardcoded `COUNTY_SEAT_SIRUTAS`, (b) 6 Bucharest sectors (detected by `judet='B'`), (c) `MUNICIPIUL ...` UATs with ≥50 streets. Returned dicts carry `is_capital`. UAT page count: 676 → 108. `build_detail_pages` also prunes stale `dist/oras/<judet>/<slug>/` dirs so the output stays consistent with the filter. Templates don't yet visually distinguish seats — the flag is available but unused.

- [x] **Search index includes UATs without detail pages** — Done 2026-05-18. `explorer_indexes` now sources its UAT list from `enumerate_uats`, so search is automatically in sync with whatever has a rendered page (108 UATs). Rural comune are no longer surfaced in `/cauta/`. When/if we add a DB-backed endpoint for long-tail UATs, route it through `enumerate_uats` (or a sibling) so the search index stays the single source of truth.

- [x] **Search index includes streets without detail pages** — Done 2026-05-18. The 29,735-row street index was clickable on all rows but only 2,464 streets have rendered pages — clicks on the rest were silent 404s. Added a `p` flag (0/1) to each index entry, and rendered `p=0` rows as disabled greyed-out rows with a "fără pagină" tag plus a note ("Rezultatele estompate sunt în baza de date dar nu au încă pagină proprie generată."). Renderable hits sort first within the 20-row cap. Fix is name_normalized-based (not bare-slug), so it survives slug collisions on both sides (`enumerate_streets` suffixes `-2` on collisions; explorer index would otherwise mark a non-rendered duplicate as `p=1`).

- [ ] **Reconsider static export strategy for all entities** — Phase 1 pre-renders ~3,400 detail pages (2,464 streets + 211 persons + 672 UATs + 72 themes) at build time. This is a significant storage and build-time overhead for long-tail entities that may receive very few visits. Consider: (a) reduce static thresholds (render only top-N per category), (b) render on-demand (Datasette or dynamic handler for missing slugs), or (c) hybrid (static for top-100 streets, dynamic for long tail). Measure traffic patterns first to justify the export cost.

- [x] **Fix `build_site.py --detail-only` hanging on re-runs** — Root cause: `uat_detail()` ran two global full-table scans (distinctive CTE + national averages) on every one of 672 UAT calls = ~740s wall time. Fixes: (1) changed `streets_dedup` GROUP BY from `(uat, name_normalized)` to `(siruta, name_normalized)` — this is also a correctness fix since 48 UAT names appear in multiple județe and were being merged; (2) added `ix_streets_siruta_name` composite index so per-UAT queries can use the index; (3) precompute `global_rarity` dict and `nat` once before the UAT loop in `build_detail_pages` and pass as kwargs to `uat_detail`. Full `--detail-only` now completes in ~100s (3427 pages). UAT count 672→676 due to correctness fix.

- [ ] **Renaming data source for Section 7 (Renumiri)** — Section 7 of the static site needs before/after rename pairs with substitution type labels. Source candidates: (a) street name version comparison across two registry exports; (b) manual curation CSV; (c) external renamed-streets dataset. Currently the section renders with static illustrative data. When data is available, add `renamings` table to `build_db.py` and implement `site_queries.section7()`.

- [x] **Gender story needs curation before it can be told** — Done 2026-05-18. The earlier-run Gemini batch CSV (`data/curation/llm_gemini-3.1-flash-lite.csv`, 700 rows) was imported via `tools/import_csv.py` — it had been sitting on disk but never applied. Net additions to `persons`: 3 women (Smaranda Brăescu, Domnița Bălașa, Iulia Hașdeu) on top of the existing 12, plus 122 men and 572 nature/place/category rows. Headline numbers: 15 female honorees covering 426 street-instances (3.42% of person-streets); top woman Ana Ipătescu at 91 streets vs. top man Mihai Eminescu at 300 (×3.3 ratio). Notebook re-executed and all four sections render cleanly. The persistent 3–5% female share is itself the story — adding more women didn't move the headline because the long tail is genuinely male-heavy. Future expansion would come from a fresh `llm_classify.py` pass on the remaining unclassified keys.

- [ ] **`ORAŞ CERNAVODĂ` numeric streets named 1848 and 1933** — `anonymous_uats` shows CERNAVODĂ CT with 5 "numeric" streets, lowest=1848, highest=1933. These are likely historical date references rather than true street numbers. Consider a sub-query that separates true sequence numbering (contiguous run starting at 1) from isolated year-numbers.

- [x] **OSM enrichment: scaffolding** — Tables (`osm_streets`, `street_osm_matches`) added to `build_db.py`. Tools written: `tools/osm_ingest.py`, `tools/osm_match.py`, `tools/osm_score.py`, `tools/osm_sanity.py`. v1 score = `highway_weight × log(1 + length_m) + ref_bonus`, z-scored within UAT. POI counts deliberately skipped (would measure mapper density, not street importance).

- [x] **OSM enrichment: download Romania PBF and run end-to-end** — Completed 2026-04-28. PBF snapshot 2026-04-28 at `data/reference/romania-latest.osm.pbf`. `osm_ingest.py` rewritten to use `osmium` + `shapely` (pyrosm cannot build on Python 3.12). 105,905 OSM street groups ingested. Match: 52.1% registry coverage, 53.3% OSM coverage. Sanity check passes for all 5 reference UATs.

- [ ] **OSM enrichment: importance v2 (per-UAT betweenness centrality)** — After v1 is validated, add `betweenness_uat` column. For each UAT subgraph (small enough that `networkx.betweenness_centrality` is cheap), build node=intersection / edge=way-segment graph weighted by length. Combine: `score_v2 = 0.6·z(v1) + 0.4·z(betweenness)`. Worth doing only if v1 misranks visibly in `osm_sanity.py` output — inside settlements the highway hierarchy collapses to flat tertiary/residential, which is exactly where centrality discriminates.

- [ ] **OSM enrichment: SIRUTA-on-admin-boundary fallback** — `tools/osm_ingest.py` resolves UAT identity by reading `ref:RO:SIRUTA`/`ref:siruta`/`siruta` tags from admin_level=8 polygons, then falls back to name-match against `populatie-romania-siruta-coords.csv`. If too many UATs drop in step 1 (watch the `unresolved` count), build a centroid-distance fallback against the same CSV.

- [ ] **OSM: Bucharest sector coverage is low (~31%)** — Centroid-based UAT assignment is imprecise for Bucharest's 6 sectors because their boundaries interleave. Two options: (a) parse admin_level=9 boundaries from the PBF using osmium's area assembler to get sector polygons, then re-assign ways by polygon containment; (b) accept as-is for v1 (sector-level scoring is degraded but the rest of Romania is fine). Note: `osm_sanity.py` reference UAT for Bucharest is Sector 1 (SIRUTA 179141); re-run sanity after any fix.

- [x] **Person recognition scope via Wikipedia sitelinks** — For each honoree in the `persons` table, classify their recognition as `universal` / `national` / `local` / `unknown` based on how many Wikipedia language editions have an article for them. Sitelink count is a static, auth-free Wikidata API signal that proxies international recognition well.

  Tiers (to calibrate after first run): `universal` ≥50 editions (Eminescu, Trajan, Curie), `national` 5–49 (most Romanian historical figures), `local` 1–4 (obscure outside RO), `unknown` no article found.

  Data path: `persons.full_name` → Wikidata SPARQL/search → QID → `wbgetentities` API → `sitelinks` count. Optionally add Romanian Wikipedia monthly page views (Wikimedia REST API) as secondary signal.

  Schema: add `wikidata_qid TEXT`, `wiki_sitelinks INTEGER`, `wiki_scope TEXT` to `persons` table in `build_db.py`. Tooling: extend planned `tools/wikidata_persons.py` to output QIDs, then a separate `tools/wiki_scope.py` that batches QID lookups (50/request) and writes back counts.

  Dependencies: LLM classifier first (person table coverage), then `wikidata_persons.py` for QID matching.

  Story: "streets named after people known only locally vs. globally" — core editorial finding. Also surfaces surprising gaps (famous Romanians in few streets) and surprising presences (obscure local figures everywhere).

---

## P3

- [ ] **OSM coverage is regionally stratified (17.7% Gorj → 87.3% Tulcea)** — Investigation revealed that Gorj's low OSM match rate (17.7%) is not a naming-mismatch issue but sparse/incomplete mapping: generic street names like "Principală", "Bisericii", "Viilor" don't exist in OSM for Gorj's small villages at all. Tulcea (87.3%) has much better coverage. This stratification likely reflects OSM mapper distribution (concentrated in cities, less active in rural regions). Similar patterns should be expected in Wikipedia/Wikidata signals (coverage better for urban areas). Story implication: "streets in well-mapped regions vs. poorly-mapped regions" could be a regional finding for the dashboard.

- [ ] **`run_queries.py` output not machine-readable** — The runner pretty-prints to stdout. When curation tooling or a dashboard pipeline needs query output, it'll need JSON/CSV mode. Add `--format json|csv|table` flag.

- [ ] **RoWordNet for nature/abstract classification** — After `llm_classify.py` runs, evaluate RoWordNet as a deterministic fallback for residual unclassified nature and abstract terms. Approach: lemmatize `core_name_norm` to dictionary form (genitives like `florilor` → `floare`, `trandafirului` → `trandafir`) using a Romanian morphological lemmatizer, then walk the WordNet hypernym chain to map to a `nature_type` or `category`. Useful if: (a) LLM leaves a long tail of plant/terrain/abstract names unclassified, or (b) reproducibility without API calls is a requirement. Prerequisite: find a Romanian lemmatizer that handles genitive/plural forms reliably (`ro_lemmatizer` in spaCy's `ro_core_news_lg` is a candidate). Skip RoNER — it gives entity type only, not the structured metadata (gender, era, profession) we need for persons.


## Misc ideas

- [x] UI - more of a compact dashboard,  raw numbers. Leave the story telling / editorialisation to another medium, move that to Jupyter notebooks. *(partly done 2026-05-16 — the dense layout has been restyled bolder/denser with IBM Plex, dark statbar, larger numbers, leader-row highlights. Editorial-mode page already lives separately at `dist/index-v1.html` via `--variant v1`. Remaining: Jupyter notebooks for the editorial/story side.)*

- [x] UI make emojis larger/icons, slightly larger than the text

- [x] UI: Landing, balance the 2 sections below stats. Personalități non-române (universale) is in 2 sections. Remove the first. Keep the second. Remove 'Notorietate Wikipedia' section. — Done 2026-05-18. The duplicate sub-section inside Persoane removed; the "Notorietate Wikipedia · vizualizări" panel removed. JS handlers for the now-missing IDs cleaned up.

- [x] UI: search from anywhere, with `/` or `Ctrl/Command + k` ? — Done 2026-05-18. `templates/_search_overlay.html.j2` partial included from `_detail-shell.html.j2` and all top-level templates. `/` (when not in a text input) or `Cmd/Ctrl+K` opens; Esc closes; arrows + Enter navigate. Reuses `/cauta/*.json` indexes and the `p` flag for "fără pagină" rows.

- [ ] UI: try compact version. Instead of showing multiple lists show one that's highly filterable. Start with stats, then a single filterable list of streets.

- [x] create a shared hosting version (no Python, static or php ai)

- [x] web ui. can be served from subfolder

- [ ] Ui, break into stats and list of streets/names, with the above filter

- [ ] UI: try a super dorpdown navigator, where it can reach all options via taxonomies, attributes, witih contextual keyboard shortcuts. or just search by visible terms. but how can we select more or exclude, to make it crazy good? With streer count in brackets?

- [ ] street names profiles, convert it to map. shows towns that match the name.

- [ ] for people, also show link to ro.wikipedia page. maybe even fetch some info besides the image?

- [x] map mode. a choropleth map colored by different variables (genders, flowers, independence, universal, etc) — Done 2026-05-18. The existing `/judete/` map gained 8 new metrics: `person_pct`, `male_pct`, `foreign_pct`, `universal_pct`, `date_pct`, `flora_pct` (flori/copaci), `ideology_pct` next to the prior saint/numeric/female/nature. Scale auto-switches to min..max when the spread is tight so person/nature metrics show actual variation; 0..max stays for rare-event metrics. 11 chips total; default is now `person_pct`. Chip CSS was missing from the detail-shell — added local style block in `judete-index.html.j2`.

- [ ] choropleth: option to render per-uat (not just per-județ). Currently the map is județ-level only; same chip metrics applied to UAT polygons would surface much finer signal (the urban/rural split, neighbourhood patterns). Blocked on UAT polygon source — admin_level=8 in OSM, parsed via osmium area assembler. Roughly: extract 3,200 UAT polygons → simplify (Mapshaper or `topojson-simplify`) → publish as `uats.topojson`. Plug into the same updateMetric() flow, swap geometry only.

- [ ] create spider chart for judete, based on choice of street names

- [ ] follow schema.org for appropriate entities - add to claude.md maybe?

- [x] Harta din front page · statistici pe județ – select random județ on load

- [ ] add orașe / towns - top by population. SIRUTA?

- [x] og image, og description, metadata — Done 2026-05-18. `_meta.html.j2` partial emits og + twitter cards + meta description. Detail renders pass per-page `og_title`/`og_description`/`og_url_path` from `build_site.py`. Single static OG image at `dist/og.png` (1200×630, brand + live counts) regenerated with `python3 tools/gen_og_image.py`.

- [x] top of foreigners foreign street names

- [x] lading page, permanent urls for selected judet / municipiu

- [x] percent of nationalities of personalities. Universal. Local. — Done 2026-05-18. New "Naționalitatea personalităților onorate" panel on the landing page: side-by-side bars `după persoane` vs `după străzi (ponderate)`. Surfaced the asymmetry: non-Romanian personalities are 7.4% of persons but only 4.49% of streets — onorate proporțional pe mai puține străzi decât cota lor numerică. Source data via `section3.nationality_breakdown` in `site_queries.py`. Note: `wiki_scope` is too sparse (3 universal only) for a "Universal vs Local" sub-split to be informative; deferred until scope coverage improves.

- [~] Go wild, nerdy, quirky. The people, how old, what are the occupations? Reason of death? *(partial 2026-05-23: brainstorm catalog saved to `/Users/pax/.claude/plans/let-s-touch-the-go-structured-taco.md` — 35+ candidate stats across 7 themes. Picks B + C shipped: km-per-honoree leaderboard, prestige-hierarchy stacked bar, self-honor index per județ. Cause-of-death/biographical-lifecycle picks deferred — natural next batch since `wiki_birthplace.py` already proved out the wbgetentities pattern for an extra Wikidata property.)*

- [ ] Norm to population, street length, lanes, centrality. Order by number (absolute), relative to population, relative to population x street relevance

- [ ] **Replace placeholder emojis with proper monoline SVG icons.** Current dashboard uses emojis (🔝 🧭 🌿 🚩 🎓 ⏳ 👥 🌍 📈 🗺️ 🧬 📜 🔎 🏟️ 📝, + per-row category emojis in nature subtypes / professions / eras / contests) as category cues. They render inconsistently across OSes (Apple Color Emoji vs Noto vs Segoe) and clash with the otherwise refined typography. Plan: inline SVG sprite of ~30 Lucide/Phosphor icons, swap each `<span class="emo">…</span>` to `<svg class="icon">…</svg>`. The `.icon` CSS class already exists in the stylesheet for this. Wait until icon set is curated — don't dribble in one-off SVGs.

- [x] **Wire real portraits into the Top Persoane list.** The dense dashboard now has a `.portrait` CSS class on each row of the s12 "Top persoane onorate" list, currently filled with parsed initials. When portrait images are available (Wikimedia thumbnails via `wikidata_persons.qid` is the obvious path), replace the initials with `<img>`. Layout already accommodates 26px circles without reflow. Wikimedia API: `https://commons.wikimedia.org/w/api.php?action=query&titles=File:<P18-value>&prop=imageinfo&iiprop=url&iiurlwidth=64`. Cache hashed thumbnails to `dist/portraits/<qid>.jpg` so the static site stays portable.

- [ ] **Validate dark-statbar direction with stakeholders.** The bold-restyle pass moved the stats band from a light cream to dark ink (Bloomberg-feel). User brief said "white background" — interpreted as the main panels, with the statbar as a structural masthead. If user pushes back, flip `.statbar` to `background: var(--bg)` + `color: var(--ink)` and the rest of the design holds (panels, leader highlights, type scale all read fine on white-on-white as well).

- [ ] if wikipedia/data missing – don't show anything instead of template links

- [x] **Cuza-family QID regression after rebuild** — Fixed 2026-05-26. Added all four aliases (`a. i. cuza`, `cuza voda`, `al. i. cuza`, `alexandru Ioan cuza`) to `data/curation/wikidata_qids.csv` with `Q294832`. Modified uniqueness guard in `wikidata_persons.py` to allow same-`full_name` aliases to share a QID (previously blocked cross-person only, now blocks cross-full_name). Added propagation step to `wiki_birthplace.py` to copy birth_place to all same-QID aliases after the main loop (SQLite correlated-subquery UPDATE). Stale IJsselstein data cleared and Bârlad (VS) propagated to all four aliases.

## Later

- [ ] side by side comparison. Judete or UATs - can be mixed. Pick max 6? toponyms to compare. Attempt (later) an automated commentary based on stats.

- [ ] brainstorm on naming

- [ ] generate custom stylized portraits for people

- [ ] translate, localisation - translate UI and street names, where possible

- [ ] Create analysis for each județ. also bigger cities, capitale de județ.. Compare regions. Have a look at the data and write the text.

- [ ] draw city map filtering out or with colored street names. militari vs femei. see [osm-poster](https://baditaflorin.github.io/osm-poster)

- [ ] create clusters of street similar ctg names in cities, detect neighbourhoods

- [ ] cel mai scurt mihai eminescu

- [ ] look at where else we might find srteet names, as coduri poștale. see what's missing from which dataset (sectii vot, cod postal, osm)

- [ ] create presentation video. With PLaywright and a scenario, subtitles and generated voiceover. Create youtube account / channel.

## Post launch

- [ ] traffic analytics
- [ ] SEO webmasters registrations
- [ ] write scientific paper(s). 1. method, 2. conclusions – co-publish with academic?
- [ ] write articles, scena9 or such 