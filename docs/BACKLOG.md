# Backlog

Items detected during sessions. Each entry has enough context to act on cold.

---

## P0

- [x] **Fix stale CLAUDE.md layout section** — The `## Repository layout` and `## Common commands` sections describe a different layout than what exists: docs are in `docs/` (not root), DB lives at `data/streets.db` (not `streets.db` in root), source xlsx is in `data/reference/` (not `data/source/`), and `--limit N` flag is already implemented (remove the "(P0 task in CODE_SPEC)" note).

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

- [ ] **Renaming data source for Section 7 (Renumiri)** — Section 7 of the static site needs before/after rename pairs with substitution type labels. Source candidates: (a) street name version comparison across two registry exports; (b) manual curation CSV; (c) external renamed-streets dataset. Currently the section renders with static illustrative data. When data is available, add `renamings` table to `build_db.py` and implement `site_queries.section7()`.

- [ ] **Gender story needs curation before it can be told** — Current data has very few women classified. The gender gap is a headline finding for the publication but requires meaningful person-table coverage first. Priority curation target: female honorees in the top-500 unclassified names.

- [ ] **`ORAŞ CERNAVODĂ` numeric streets named 1848 and 1933** — `anonymous_uats` shows CERNAVODĂ CT with 5 "numeric" streets, lowest=1848, highest=1933. These are likely historical date references rather than true street numbers. Consider a sub-query that separates true sequence numbering (contiguous run starting at 1) from isolated year-numbers.

- [x] **OSM enrichment: scaffolding** — Tables (`osm_streets`, `street_osm_matches`) added to `build_db.py`. Tools written: `tools/osm_ingest.py`, `tools/osm_match.py`, `tools/osm_score.py`, `tools/osm_sanity.py`. v1 score = `highway_weight × log(1 + length_m) + ref_bonus`, z-scored within UAT. POI counts deliberately skipped (would measure mapper density, not street importance).

- [x] **OSM enrichment: download Romania PBF and run end-to-end** — Completed 2026-04-28. PBF snapshot 2026-04-28 at `data/reference/romania-latest.osm.pbf`. `osm_ingest.py` rewritten to use `osmium` + `shapely` (pyrosm cannot build on Python 3.12). 105,905 OSM street groups ingested. Match: 52.1% registry coverage, 53.3% OSM coverage. Sanity check passes for all 5 reference UATs.

- [ ] **OSM enrichment: importance v2 (per-UAT betweenness centrality)** — After v1 is validated, add `betweenness_uat` column. For each UAT subgraph (small enough that `networkx.betweenness_centrality` is cheap), build node=intersection / edge=way-segment graph weighted by length. Combine: `score_v2 = 0.6·z(v1) + 0.4·z(betweenness)`. Worth doing only if v1 misranks visibly in `osm_sanity.py` output — inside settlements the highway hierarchy collapses to flat tertiary/residential, which is exactly where centrality discriminates.

- [ ] **OSM enrichment: SIRUTA-on-admin-boundary fallback** — `tools/osm_ingest.py` resolves UAT identity by reading `ref:RO:SIRUTA`/`ref:siruta`/`siruta` tags from admin_level=8 polygons, then falls back to name-match against `populatie-romania-siruta-coords.csv`. If too many UATs drop in step 1 (watch the `unresolved` count), build a centroid-distance fallback against the same CSV.

- [ ] **OSM: Bucharest sector coverage is low (~31%)** — Centroid-based UAT assignment is imprecise for Bucharest's 6 sectors because their boundaries interleave. Two options: (a) parse admin_level=9 boundaries from the PBF using osmium's area assembler to get sector polygons, then re-assign ways by polygon containment; (b) accept as-is for v1 (sector-level scoring is degraded but the rest of Romania is fine). Note: `osm_sanity.py` reference UAT for Bucharest is Sector 1 (SIRUTA 179141); re-run sanity after any fix.

- [ ] **Person recognition scope via Wikipedia sitelinks** — For each honoree in the `persons` table, classify their recognition as `universal` / `national` / `local` / `unknown` based on how many Wikipedia language editions have an article for them. Sitelink count is a static, auth-free Wikidata API signal that proxies international recognition well.

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

- [ ] UI - more of a compact dashboard,  raw numbers. Leave the story telling / editorialisation to another medium, move that to Jupyter notebooks. *(partly done 2026-05-16 — the dense layout has been restyled bolder/denser with IBM Plex, dark statbar, larger numbers, leader-row highlights. Editorial-mode page already lives separately at `dist/index-v1.html` via `--variant v1`. Remaining: Jupyter notebooks for the editorial/story side.)*
- [ ] Go wild, nerdy, quirky. The people, how old, what are the occupations? Reason of death?

- [ ] **Replace placeholder emojis with proper monoline SVG icons.** Current dashboard uses emojis (🔝 🧭 🌿 🚩 🎓 ⏳ 👥 🌍 📈 🗺️ 🧬 📜 🔎 🏟️ 📝, + per-row category emojis in nature subtypes / professions / eras / contests) as category cues. They render inconsistently across OSes (Apple Color Emoji vs Noto vs Segoe) and clash with the otherwise refined typography. Plan: inline SVG sprite of ~30 Lucide/Phosphor icons, swap each `<span class="emo">…</span>` to `<svg class="icon">…</svg>`. The `.icon` CSS class already exists in the stylesheet for this. Wait until icon set is curated — don't dribble in one-off SVGs.

- [ ] **Wire real portraits into the Top Persoane list.** The dense dashboard now has a `.portrait` CSS class on each row of the s12 "Top persoane onorate" list, currently filled with parsed initials. When portrait images are available (Wikimedia thumbnails via `wikidata_persons.qid` is the obvious path), replace the initials with `<img>`. Layout already accommodates 26px circles without reflow. Wikimedia API: `https://commons.wikimedia.org/w/api.php?action=query&titles=File:<P18-value>&prop=imageinfo&iiprop=url&iiurlwidth=64`. Cache hashed thumbnails to `dist/portraits/<qid>.jpg` so the static site stays portable.

- [ ] **Validate dark-statbar direction with stakeholders.** The bold-restyle pass moved the stats band from a light cream to dark ink (Bloomberg-feel). User brief said "white background" — interpreted as the main panels, with the statbar as a structural masthead. If user pushes back, flip `.statbar` to `background: var(--bg)` + `color: var(--ink)` and the rest of the design holds (panels, leader highlights, type scale all read fine on white-on-white as well).

## Later

- [ ] Create analysis for each județ. also bigger cities, capitale de județ.. Compare regions. Have a look at the data and write the text.

- [ ] draw city map filtering out or with colored street names. militari vs femei. see [osm-poster](https://baditaflorin.github.io/osm-poster)

- [ ] create clusters of street similar ctg names in cities, detect neighbourhoods

- [ ] cel mai scurt mihai eminescu

- [ ] look at where else we might find srteet names, as coduri poștale. see what's missing from which dataset (sectii vot, cod postal, osm)
