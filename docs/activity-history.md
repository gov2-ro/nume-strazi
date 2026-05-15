# Activity History

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
