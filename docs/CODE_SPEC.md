# Romanian Street Names Analysis — Code Spec

A technical PRD for continuing the build. Audience: Claude Code (or any senior engineer picking up where this prototype left off). Language: English. Romanian terms preserved verbatim.

---

## 1. Project context

Analytical platform for Romanian street names. Two-phase deliverable:

- **Phase 1 — exploration.** A SQLite database with cleaned, feature-extracted street records, plus a query catalog. Outputs feed manual analysis and editorial decisions.
- **Phase 2 — publication.** A Romanian-language interactive dashboard surfacing both insightful and funny findings. Runtime to be decided (Observable Framework / Datasette / static + DuckDB-WASM are all candidates). The data layer (this spec) is runtime-agnostic.

Source dataset: Romanian Permanent Electoral Authority's polling-section registry ("Registrul Secțiilor de Vot"), ~140,000 rows. Each row maps a street to a polling section. The current prototype was built from a 4,007-row, 4-județ sample.

Geolocation of individual streets is explicitly out of scope for the data layer in this phase. Județ-level choropleth maps are in scope at the dashboard layer (TopoJSON owned by the user).

## 2. Data source — known caveats

These are not bugs. They are properties of the source dataset that must be respected throughout.

1. **Polling-section bias.** This is the *electoral* view of streets. Streets without registered voters are excluded. For most analyses this is fine; flag where it matters (e.g. comparing total street counts to OSM).
2. **Row repetition.** A single street that spans multiple polling sections appears once per section. Frequency analysis must dedup on `(uat, name_normalized)` first. The `streets_dedup` view handles this.
3. **Diacritic mixing.** The dataset uses the pre-1993 cedilla forms (`ş`, `ţ`) and the post-1993 comma-below forms (`ș`, `ț`) interchangeably. We normalize to post-1993 on ingest.
4. **Orthography reform of 1993.** The reform changed many `î`→`â` mid-word. Both forms exist for the same street name. We collapse `î ≡ â` *only* in the matching key (`name_normalized`, `core_name_norm`); the display column (`name`) preserves the original form.
5. **Parenthetical aliases.** Some `Arteră` cells contain `(Strada X)` — historical names. These are extracted into `street_aliases`. Single-letter administrative tags like `(D)` are filtered out (`len > 2` rule).
6. **Mixed naming conventions.** Numeric-only street names exist (commune CIORANI in Prahova has 218 of them). Date names exist (`1 Decembrie`). These get dedicated flags rather than special-cased throughout.

## 3. Architecture decisions (locked)

| Decision | Rationale |
|---|---|
| SQLite as source of truth | Fits 140k rows comfortably. Portable, embeddable in any runtime. |
| Python stdlib + openpyxl for ETL | Solo dev, simple deployment. No ORM. |
| `streets` flat table + 4 curated lookup tables | Curated data evolves independently. Lookups join on `core_name_norm`. |
| Display vs. matching layers | `name` for humans (preserves orthographic variants); `name_normalized` for joins/groupby. |
| Greedy prefix peeling for title/rank/saint | Handles "Colonel Dr. Ion X" without combinatorial regex. |
| `streets_dedup` view, not materialization | Keeps the source rows intact for raw inspection. Re-evaluates cheaply at 140k. |

**Deferred decisions** (call out in PRs that touch them):
- Dashboard runtime
- Whether to add a person-resolution step (multiple `core_name_norm` keys → single Wikidata QID)
- Whether to publish the SQLite as Datasette alongside the dashboard

## 4. Repository conventions

```
.
├── build_db.py           # ETL: xlsx → SQLite. Idempotent (drops + rebuilds).
├── seed_lookups.py       # Hand-curated starter data for 4 lookup tables.
├── queries.sql           # Named query catalog (-- :name <id>) per dashboard view.
├── run_queries.py        # Runner with log() and regexp() shims for SQLite.
├── streets.db            # Generated. Not committed (or committed with caveat).
└── data/
    ├── source/           # Raw xlsx inputs
    └── curation/         # CSV inputs for incremental curation (see §8)
```

Conventions:
- Python 3.11+. Stdlib + `openpyxl` only for ETL. No pandas in the build path.
- SQL files use `-- :name slug_id` markers. The runner splits on these.
- All SQL is parameterized — never f-string-injected user values. (Currently no user input, but future curation tools should respect this.)
- Romanian text: post-1993 orthography (`ș`, `ț`, `â` mid-word, `î` at boundaries). Pre-1993 forms accepted as input only.
- snake_case for everything except SQL keywords.

## 5. Schema reference

```sql
streets
  id              INTEGER PRIMARY KEY
  judet           TEXT NOT NULL          -- 2-letter county code
  uat             TEXT NOT NULL          -- "Unitate Administrativ-Teritorială" (commune/city)
  siruta          INTEGER                -- statistical territorial unit code
  artera_raw      TEXT NOT NULL          -- original "Arteră" cell verbatim
  street_type     TEXT                   -- 'Strada' | 'Aleea' | ... | NULL
  name            TEXT                   -- display form, post-1993 diacritics, original â/î
  name_normalized TEXT                   -- lowercase ASCII, î≡â collapsed
  title           TEXT                   -- 'Prof.' | 'Dr.' | 'Învățător' | ...
  rank            TEXT                   -- 'General' | 'Voievod' | 'Erou' | ...
  is_saint        INTEGER NOT NULL       -- 0/1
  is_date         INTEGER NOT NULL       -- 0/1
  is_numeric      INTEGER NOT NULL       -- 0/1
  core_name       TEXT                   -- name with title/rank/saint stripped
  core_name_norm  TEXT                   -- normalized core_name (join key)

street_aliases
  street_id          INTEGER REFERENCES streets(id)
  alias              TEXT NOT NULL
  alias_normalized   TEXT NOT NULL

-- Curated lookup tables (hand + Wikidata + LLM-assisted)
persons          (core_name_norm PK, full_name, gender, birth_year, death_year,
                  era, profession, nationality, wikidata_qid, notes)
nature_terms     (core_name_norm PK, term, nature_type, notes)
name_categories  (core_name_norm PK, category, subcategory, notes)
place_refs       (core_name_norm PK, place_name, place_type, country, notes)

-- Views
streets_dedup    -- one row per (uat, name_normalized); use this for ALL frequency analysis
```

Indexes: `judet`, `uat`, `name_normalized`, `core_name_norm`, `street_type`, `(is_saint,is_date,is_numeric)`, `alias_normalized`.

### Why two name layers

`name_normalized` collapses orthographic variants for grouping (`Topîrceanu` ≡ `Topârceanu`). `name` preserves the original so the UI shows what's actually written. Never display `name_normalized`. Never join curated tables on `name`.

### Why `core_name_norm`

A street is `Strada Prof. Dr. Mihai Eminescu`. After parsing: `street_type=Strada`, `name="Prof. Dr. Mihai Eminescu"`, `title="Prof. Dr."`, `core_name="Mihai Eminescu"`, `core_name_norm="mihai eminescu"`. The `persons` table joins on the last one. This decouples honorific noise from identity.

## 6. Cleaning pipeline rules

Implemented in `build_db.py`. If reimplementing, preserve these behaviors:

1. **Diacritic fix** — `ş→ș`, `ţ→ț`, capitals likewise. Unicode codepoint translation, not regex.
2. **Parse arteră** — strip parenthetical aliases first into a list, then match street type prefix from a longest-first sorted list. Returns `(street_type, name, [aliases])`.
3. **Aliases** — keep only those with `len(stripped) > 2` (filters single-letter admin tags).
4. **`normalize_match(s)`** — `s.replace("î","â").replace("Î","Â")` → NFKD → strip combining → lowercase → strip. ASCII-only output.
5. **No silent drops.** Rows with NULL `Arteră` are skipped; everything else is recorded with NULL feature columns where extraction failed.

### Street type list (extend as needed)

```
Bulevardul, Fundătura, Cartierul, Prelungirea, Strada, Aleea, Intrarea,
Calea, Drumul, Piața, Șoseaua, Ulița, Splaiul, Pasajul, Cheiul, Trecerea,
Cărarea, Stradela, Rampa
```

Match longest first. The full 140k may surface additional types (`Esplanada`, `Curtea`, `Trecerea`, regional terms). Extend the list and re-run; idempotent.

## 7. Feature extraction rules

Order of operations on a parsed `name`:

1. **Numeric** — `^\d+[A-Za-z]?$` → `is_numeric=1`, `core_name=NULL`. Stop.
2. **Date** — `^\d{1,2}\s+(luna)$` against the 12 Romanian months → `is_date=1`, `core_name=name`. Stop.
3. **Greedy prefix peeling** — repeatedly try saint, then title, then rank prefixes (each list sorted by length desc). Multiple passes handle chains like `Colonel Dr. X`.
4. **Remainder** — whatever's left after peeling becomes `core_name`.

Lists (extend with care; prefer adding to a curated CSV over hardcoding):

- **TITLES**: academic, professional, clergy honorifics. See `build_db.py`.
- **RANKS**: military, royal, heroic, religious-leadership ranks.
- **SAINTS**: `Sfinții Apostoli`, `Sfinții`, `Sfântul`, `Sfânta`, `Sfântu`, `Sfânt`, `Sf-a`, `Sfta.`, `Sf.`

### Edge cases the current implementation handles

- `Profesor Universitar Ion Tudorache` → `title="Profesor Universitar"`, `core_name="Ion Tudorache"` ✓
- `Colonel Dr. Ion Ștefănescu` → `rank="Colonel"`, `title="Dr."`, `core_name="Ion Ștefănescu"` ✓
- `Sfânta Maria` → `is_saint=1`, `core_name="Maria"` ✓

### Edge cases the current implementation does NOT handle (open tickets)

- **Collective honorees** — `Frații Buzești`, `Sfinții Apostoli Petru și Pavel`. The `persons` table needs a `gender='collective'` value and the `core_name_norm` must remain the full collective phrase.
- **Acronym people** — `C.I. Parhon`, `N.D. Paulescu`. These work but `core_name_norm` becomes `c.i. parhon` (with periods). Wikidata join needs alias resolution.
- **Pen names + birth names** — `Bogdan Petriceicu Hașdeu` is one person; we currently treat the full string as the key. That's correct for our purposes but flag if a UAT honors both forms separately.
- **Mid-name titles** — `Ion C. Brătianu` and `Ion I. C. Brătianu` are different people sharing a surname. Don't auto-merge.
- **Ambiguous prefixes** — `Maior` could be a rank OR a place name (`Strada Maior` referring to a settlement). Currently treated as rank. Manual override via curated tables planned.

## 8. Curation strategy

Coverage with the starter seed (90 entries) was ~24% on the sample. To hit 80%+ on the full 140k, run this loop:

### The classification loop

```
1. Run coverage query → list of unclassified `core_name_norm` ordered by frequency
2. Export top-N (start with 500) to data/curation/unclassified.csv
3. Classify rows by adding category + subcategory columns
4. Import via upsert into the relevant curated table
5. Recompute coverage. Repeat until diminishing returns.
```

### Three population sources, in priority order

1. **CSV curation (closed vocabularies)** — for nature terms, place names, name categories. Fast, deterministic, you stay in control. Maintain `data/curation/{nature,places,categories}.csv` as source of truth; `seed_lookups.py` imports them.
2. **Wikidata SPARQL (persons)** — query for Romanian historical/cultural figures by name. Expected ~40-60% hit rate for top honorees. Returns QID, gender, birth/death, profession, nationality. Free, partial, slow. Pseudocode:
   ```
   SELECT ?person ?label ?gender ?birth ?death ?occupation
   WHERE {
     ?person rdfs:label ?label.
     FILTER(LANG(?label) = "ro" || LANG(?label) = "en")
     ?person wdt:P27 wd:Q218.   # citizenship: Romania
     OPTIONAL { ?person wdt:P21 ?gender. }
     ...
   }
   ```
   Match results back to `core_name_norm` via fuzzy comparison (Levenshtein ≤ 2 on lowered ASCII).
3. **LLM batch (Claude Haiku) — last resort for residue.** Cost estimate: ~$5–15 for full 140k unique names. Prompt template lives in `data/prompts/classify_name.md`. Always include 5-10 few-shot examples in Romanian. Output strict JSON. Validate against schema before import.

### Idempotence requirement

All curation imports must be upserts keyed on `core_name_norm`. Re-running the import with the same CSV must not change the DB. Re-running with a corrected CSV must apply only the corrections. SQLite syntax:

```sql
INSERT INTO persons (core_name_norm, full_name, gender, ...)
VALUES (?, ?, ?, ...)
ON CONFLICT(core_name_norm) DO UPDATE SET
  full_name = excluded.full_name,
  gender = excluded.gender,
  ...
```

## 9. Query catalog overview

`queries.sql` contains 20+ named queries grouped by dashboard view. Each query stands alone, queries `streets_dedup` (never `streets` directly for analytical purposes), and joins curated tables via `core_name_norm`.

View groupings (name prefix in the file):
- `overview_*` — KPI tiles, street-type distribution
- `top_*` — national rankings
- `universal_*` / `unique_*` — distribution tails
- `people_*` — gender, era, profession, foreign honorees
- `theme_*` / `nature_*` — composition
- `judet_*` / `modal_*` / `uat_diversity` — regional analysis
- `*_renamings` / `communist_aliases` — historical layer
- `anonymous_*` / `longest_*` / `locally_*` — curiosities

When adding queries: name them, comment the intent, prefer CTEs over nested subqueries, return columns in display order.

## 10. Open tasks (prioritized)

### P0 — Scaling

- [ ] Run `build_db.py` against the full 140k registry. Add a `--limit N` flag for fast iteration.
- [ ] Verify `streets_dedup` count drops to a reasonable distinct-street total (rough estimate: 80k-100k unique names across UATs). If it doesn't, the dedup grouping is wrong.
- [ ] Verify all 41 județe + Bucharest sectors are present.

### P1 — Curation tooling

- [ ] `tools/export_unclassified.py` — generates CSV of unclassified `core_name_norm` ordered by frequency, with sample streets/UATs for context.
- [ ] `tools/import_csv.py` — generic upserter for the 4 lookup tables; takes table name + CSV path.
- [ ] `tools/wikidata_persons.py` — SPARQL query for top-N unmatched person candidates; outputs CSV for review before import.
- [ ] `tools/llm_classify.py` — batch classifier using Claude Haiku; rate-limited; idempotent (re-runs only unclassified rows).
- [ ] Coverage query view: `streets_classified_pct` per category.

### P1 — Analysis modules not yet built

- [ ] `regional_fingerprint` — TF-IDF per județ over `core_name_norm` tokens. Outputs the top distinctive names per județ.
- [ ] `token_cooccurrence` — bigram analysis over multi-word names (e.g., "Mihai" most often followed by which surname?).
- [ ] `animal_ranking` — populate nature_terms with full animal vocabulary; build top-N animal query with regional split.
- [ ] `holiday_distribution` — choropleth-ready aggregate of date streets per județ, by date.
- [ ] `saint_ranking` — top saints with regional preference scores.
- [ ] `title_bearers_by_judet` — heatmap matrix of title × judet (which județe honor learned professions vs. military).
- [ ] `renaming_timeline` — group renamings by likely renaming date (heuristic: communist token presence) and visualize the wave.

### P2 — Resolution & quality

- [ ] Person identity resolution: merge `c.i. parhon` ↔ `constantin ion parhon` ↔ `parhon` into one entity with multiple `core_name_norm` keys.
- [ ] Cross-curate aliases: a street whose alias resolves to a known person via curated tables provides historical naming evidence even without explicit communist tokens.
- [ ] Add `street_history` table: derived from aliases, reconstructs (current_name, historical_name, change_type) where change_type ∈ {orthographic, semantic, ideological}.

### P2 — Dashboard data delivery

- [ ] Decide runtime. Options unchanged from earlier discussion.
- [ ] If static (DuckDB-WASM): export Parquet partitions by județ for lazy loading. Target <30 MB total payload.
- [ ] If Datasette: write per-view facet config; canned queries map 1:1 to the named queries.
- [ ] Per-judet API endpoint or partition (regardless of runtime).

### P3 — Geolocation (deferred, but data layer prep)

- [ ] `geocoded_streets` table: `(street_id, lat, lng, source, confidence)`. Don't populate yet.
- [ ] Plan: feature-flag a separate ingest that calls Nominatim/OSM for streets matching a UAT centroid filter. Rate limits: 1 req/sec → 140k requests = ~40 hours. Better: bulk-match against an OSM Romania extract.

## 11. OSM enrichment pipeline

Goal: attach geometry, road class, and an importance score to streets that exist in **populated areas**. Motorways and inter-city trunks are out of scope — this is about ranking streets *within* settlements, not roads between them.

### 11.1 Source

- Geofabrik Romania PBF: `https://download.geofabrik.de/europe/romania-latest.osm.pbf` (~300 MB compressed).
- Stored at `data/reference/romania-latest.osm.pbf`. **Snapshot date: 2026-04-28.**
- **Refresh cadence:** pin a snapshot per release; don't auto-update.

### 11.2 Dependency exception

The OSM path imports `osmium` and `shapely`. This is the **only** documented exception to the "stdlib + openpyxl" rule for ETL. Justification: PBF parsing without bindings is not feasible; `geopandas` is intentionally avoided (heavier dep tree, no benefit here). The registry ETL (`build_db.py`) remains stdlib-only.

Install in the project venv (`~/devbox/envs/240826/`): `pip install osmium shapely`.

Note: `pyrosm` was the originally planned dep but cannot build on Python 3.12 (`pyrobuf` dep fails). `osmium` (pyosmium 4.x) is the replacement — lighter, maintained, compatible.

### 11.3 Tables

| Table | Grain | Notes |
|---|---|---|
| `osm_streets` | one row per `(uat_siruta, name_normalized)` | OSM splits a single street into many ways at intersections; `tools/osm_ingest.py` merges them before insert. Mirrors `streets_dedup`'s grain. |
| `street_osm_matches` | one row per `(street_id, osm_street_id)` | Two pass types: `exact_normalized` (confidence 1.0), `fuzzy_core_name` (0.6). Below this threshold we don't auto-link — see §11.6. |

### 11.4 Pipeline

```
tools/osm_ingest.py  →  osm_streets         (PBF → SQLite, geo work)
tools/osm_match.py   →  street_osm_matches  (pure SQL, fast)
tools/osm_score.py   →  importance_v1       (pure Python math, fast)
tools/osm_sanity.py  →  read-only report    (eyeball reference UATs)
```

Each step is idempotent. `osm_ingest.py --rebuild` truncates `osm_streets` first; the others overwrite their outputs unconditionally.

### 11.5 UAT assignment

Each OSM way is assigned to a UAT by **nearest-centroid matching**: the way's midpoint is compared against a spatial grid of UAT centroids loaded from `data/gis/populatie-romana-siruta-coords.csv`, filtered to SIRUTAs present in the registry DB.

Grid is 0.5°×0.5° cells (≈ 50 km), so each lookup checks only the way's cell plus the 8 adjacent cells — typically 9–54 candidates instead of all 1207 UATs. Fast enough for 4M ways without numpy.

The 6 Bucharest sectors (SIRUTAs 179141–179196) are absent from the coords CSV (which only has the municipality code 179132). Their centroids are hardcoded in `tools/osm_ingest.py:_BUCHAREST_SECTOR_CENTROIDS` with approximate per-sector coordinates. Coverage for Bucharest sectors is lower than other cities (~30%) because sector boundaries are complex and the centroid assignment is less precise — acceptable for v1.

The original plan (geopandas polygon containment via admin_level=8 boundaries) was dropped because `pyrosm` cannot build on Python 3.12. Centroid assignment is simpler and sufficient for importance scoring, which is per-UAT z-scored anyway.

### 11.6 Score formula (v1)

```
raw  = highway_weight × log(1 + length_m) + ref_bonus
v1_z = z-score of raw within UAT
```

Weights (`tools/osm_score.py`): `primary=5, secondary=4, tertiary=3, residential=2, unclassified=2, living_street=1, pedestrian=1, service=1`. `ref_bonus=2.0` when `ref` matches `^(DN|DJ|DC|A)\d+`.

**Why per-UAT z-score:** without it, Bucharest streets dominate any national ranking by sheer length. The z-score is the comparable axis; `raw` is informational only.

**Why `ref_bonus`:** a numbered route (DN1, DJ105) running through a town is almost always the local main street, even when OSM tags the in-town segment as just `secondary`. Highest signal-per-line of any addition.

**Why no POI counts:** OSM POI density correlates with mapper activity, not street importance. Would measure Bucharest enthusiasm vs rural neglect, not street prominence.

**v2 plan (deferred):** add per-UAT betweenness centrality as `betweenness_uat`, combine `score_v2 = 0.6·z(v1) + 0.4·z(betweenness)`. Inside settlements the highway hierarchy collapses (lots of tied tertiary/residential), which is exactly where centrality discriminates. Worth doing only if `osm_sanity.py` shows v1 misranking visibly.

### 11.7 Match strategy

Pass 1: `streets_dedup.siruta + name_normalized` ↔ `osm_streets.uat_siruta + name_normalized`. Confidence 1.0.

Pass 2 (only for unmatched registry rows): same join on `core_name_norm`. Confidence 0.6. Catches `Strada` vs `Bulevardul` prefix differences and honorific variations.

We deliberately stop there. Levenshtein on ~100k×100k name pairs produces enough false positives to poison the importance index downstream — better to surface gaps in `tools/osm_sanity.py` than auto-link.

### 11.8 What `geocoded_streets` becomes

The `geocoded_streets` table stub mentioned in §10.P3 is superseded by this pipeline. Per-street lat/lng, when needed, can be derived from `osm_streets.geometry_wkt` (centroid of the merged geometry). No need for Nominatim.

### 11.9 Feature-column extension (2026-07-08)

`osm_streets` originally only carried `core_name_norm` (street-type-stripped, via `strip_street_type`), while the registry's `core_name_norm` is type-stripped *and* honorific-stripped (via `extract_features`). This meant an OSM `Strada Sfântul Andrei` (core "Sfântul Andrei") never matched a registry street honoring the same saint (core "Andrei", `is_saint=1`) — `fuzzy_core_name` compared apples to oranges.

Fixed by extending `osm_streets` with `street_type`, `title`, `rank`, `is_saint`, `is_date`, `is_numeric`, `core_name` (alongside the existing `core_name_norm`), computed by `tools/osm_ingest.py` via the now-shared `extract_features()` (promoted to `streets_lib.py`, see §12.2). Registry/OSM coverage moved from 52.1%/53.3% to 53.3%/54.6% after re-running `osm_ingest.py --rebuild` + `osm_match.py` — a real, if modest, improvement, not noise.

This also gives `streets_all_sources` (§12.6) genuine column parity across all three sources instead of NULL-padding the OSM arm.

## 12. Postal-code enrichment pipeline

Goal: a second independent street-name source (Poșta Română's postal-code registry) to cross-reference against the AEP registry and OSM, surfacing streets none of the three sources alone would catch. Unlike OSM (geometry/importance scoring), postal-code data has no independent value beyond names — its only role is completeness checking.

### 12.1 Source

- `data/reference/coduri-postale+/infocod-cu-siruta-mai-2016.xlsx` (May 2016 snapshot). Three sheets: `Bucuresti` (12,400 rows, street-level, direct SIRUTA per sector), `Localitati peste 50.000 loc` (29,204 rows, street-level, direct SIRUTA-equivalent), `Localitati sub 50.000 loc` (13,803 rows, **locality-level only — no street columns at all**). Only the first two sheets are ingested; the third contributes nothing to street names and is a structural coverage gap this source cannot close (small/rural towns rely on the registry and OSM instead).
- **Evaluated and excluded**: `data/reference/coduri-postale+/coduri_postale.sql`, a 2009 MySQL dump (51,898 rows, no SIRUTA). Its apparent appeal — covering small towns the 2016 xlsx omits — does not hold up empirically: of 51,898 rows, only 48 distinct localities have any street-level data at all (the rest are locality-only codes, the same structural gap as the excluded xlsx sheet). Of those 48, 47 are already fully covered by the 2016 xlsx (the one apparent miss, "Drobeta-Turnu S", is a truncated "Drobeta-Turnu Severin", itself in the xlsx). It adds zero new locality coverage — not worth the parsing complexity (raw SQL `INSERT` statements, no SIRUTA) for a stale second witness on towns already covered.
- **Also excluded**: `data/reference/infocod-mai-2016+.csv` — a flattened, SIRUTA-less duplicate of the xlsx's first two sheets. Strictly redundant.

### 12.2 Dependency exception

None. Stays stdlib + openpyxl, like the registry ETL — the xlsx needs only `openpyxl`, already a dependency.

### 12.3 Tables

| Table | Grain | Notes |
|---|---|---|
| `postal_streets` | one row per `(uat_siruta, name_normalized)` | Same grain as `osm_streets`/`streets_dedup`. `name` **excludes** the street-type prefix (unlike `osm_streets.name`) — the source already separates `Tip artera`/`Denumire artera`, so `name_normalized` is directly comparable to the registry's. |
| `street_postal_matches` | one row per `(street_id, postal_street_id)` | Three pass types: `exact_normalized` (1.0), `fuzzy_core_name` (0.6), `reordered_core_name` (0.4) — see §12.5. |

### 12.4 UAT resolution — empirical corrections

Two mislabeled/untrustworthy-column traps discovered by validating against the live registry, not assumed:

1. **`Localitati peste 50.000 loc` sheet: use `SIRSUP`, not the column literally named `SIRUTA`.** Verified: the `SIRUTA` column matches 0/47 registry SIRUTAs (it's a finer-grained internal postal sub-locality/zone code); `SIRSUP` ("SIRUTA superior") matches 47/47.
2. **`Bucuresti` sheet: the reverse — use `SIRUTA SECTOR`, not `SIRSUP`.** `SIRSUP` there is always 179132 (the whole-municipality code, absent from the registry, which only has sector-level SIRUTAs for București). `SIRUTA SECTOR` matches the registry's 179141–179196 directly, verified 6/6.
3. **Even a "direct" code isn't always trustworthy.** Example: Câmpulung Moldovenesc's postal SIRUTA (146511, on the excluded sub-50k sheet) differs from the registry's (146502) for the same town. `tools/postal_ingest.py` always validates the resolved code against the live `streets.siruta` set and falls back to județ+localitate name-matching (against `data/gis/populatie-romania-siruta-coords.csv`) when it isn't found.

In practice, both ingested sheets resolved 100% via their direct column (47/47 SIRSUP, 6/6 SIRUTA SECTOR) — the name-match fallback exists as a safety net, not because it's regularly needed.

### 12.5 Match strategy

`tools/postal_match.py`, same two-pass shape as `osm_match.py` plus a third pass:

1. `exact_normalized` (1.0) — `(siruta, name_normalized)`. Unlike OSM (where this pass is a near no-op — 490 vs 57,437 `fuzzy_core_name` matches), this is the **workhorse pass for postal** (15,986 vs 43 `fuzzy_core_name`), because postal `name` is already type-stripped like the registry's, not embedded like OSM's.
2. `fuzzy_core_name` (0.6) — `(siruta, core_name_norm)`, unmatched rows only.
3. `reordered_core_name` (0.4) — `(siruta, core_name_norm_swapped)`, unmatched rows only. Postal person-names are frequently **"Surname Firstname"** (reversed vs. the registry's "Firstname Surname" — e.g. "Alecsandri Vasile" vs. registry's "Vasile Alecsandri"; titles also appear as trailing comma-suffixes, `"Mincu Ion, arh."`, rather than the registry's leading-prefix convention). `core_name_norm_swapped` is a 2-token reorder computed at ingest; this pass caught 3,724 matches in the full run, spot-checked clean.

We stop there, for the same reason `osm_match.py` stops at `fuzzy_core_name`: broader fuzzy matching produces false positives that poison downstream analysis — better to surface gaps in `tools/postal_sanity.py` than auto-link.

**Known caveat, not yet handled**: the trailing comma-suffixed title convention (`"Mincu Ion, arh."`, `"Kiseleff Pavel Dimitrievici, g-ral."`) uses abbreviated forms not in `TITLES`/`RANKS` (which use full forms like "Arhitect"/"General"). These remain unmatched past all 3 passes. Logged in BACKLOG rather than fixed inline — would need a dedicated abbreviation-expansion map for the Bucuresti sheet's convention specifically.

### 12.6 `streets_all_sources` view

Additive consolidation, does **not** touch `streets_dedup`: `UNION ALL` of registry rows (full attributes) + `osm_streets` rows with no `street_osm_matches` row + `postal_streets` rows with no `street_postal_matches` row, each flagged by a `source` column (`'registry'`/`'osm'`/`'postal'`). A view in `data/streets.db`; materialized into a real table by `tools/build_dist_db.py` before its source tables (which don't ship) are dropped.

**Cross-source comparison must join on `core_name_norm`, never `name_normalized`** — OSM's `name_normalized` includes the type prefix, postal's and the registry's don't. This is why `docs/queries.sql`'s `external_corroboration_gap`/`registry_uncorroborated` queries use `core_name_norm` exclusively.

### 12.7 Verified results (full run, 2026-07-08)

- Postal ingest: 41,604 raw rows → 23,724 grouped `postal_streets` rows. 100% direct SIRUTA resolution (no name-match fallback needed in practice).
- Postal match: registry coverage 19,753/105,343 (18.8% — expected, since postal only covers Bucuresti + >50k towns); postal coverage 19,715/23,724 (83.1%).
- `streets_all_sources`: 105,343 registry + 48,063 OSM-only + 4,009 postal-only = 157,415 rows.

## 13. Pitfalls / gotchas

These are the booby traps. A senior engineer reading this should not have to discover any of them by stubbing toes.

1. **Never count without dedup.** `SELECT COUNT(*) FROM streets WHERE name='Eminescu'` overcounts by section repetition. Use `streets_dedup`.
2. **Renamings query needs DISTINCT.** Section-rows duplicate aliases. The current `real_renamings` query handles this; future ones must too.
3. **`name_normalized` ≠ `core_name_norm`.** Frequency by canonical street name → `name_normalized`. Joining to `persons` → `core_name_norm`. Mixing them gives subtly wrong answers.
4. **Sample bias.** The 4-județ prototype is 75% Prahova-rural. Top frequencies are nature-dominated. Do not generalize from sample-only output to "Romanian streets in general." The full 140k will show person names overtaking nature names.
5. **Bucharest's six sectors register as separate UATs** (`BUCUREȘTI SECTORUL N`). They share streets administratively but not in this dataset. Treat them as separate UATs for dedup, but optionally aggregate as `B` for comparative county analysis.
6. **The 1944–1989 communist era is a renaming wave, not a dataset.** We can detect it heuristically (ideological tokens in aliases) but not authoritatively. Don't claim certainty.
7. **`is_saint=1` is necessary but not sufficient for "religious."** A `Strada Bisericii` is religious without being saint-prefixed. Always use the full theme classification, not flags alone.
8. **Don't strip diacritics for display.** It happens naturally when bugs are introduced. Add a startup assertion that `name` columns contain non-ASCII Romanian characters.
9. **`core_name=NULL` on numeric streets is intentional.** Queries that join curated tables on `core_name_norm` will correctly skip these. Queries that filter for "anonymous" should use `is_numeric=1`.
10. **The `(D)` parenthetical is filtered as too short, but other admin codes might exist.** Audit the full 140k for unexpected short parentheticals (`(I)`, `(II)`, `(B)`?).
11. **`osm_streets.name_normalized` includes the street-type prefix; `postal_streets.name_normalized` and `streets_dedup.name_normalized` don't.** Comparing across sources by `name_normalized` silently under-corroborates. Always use `core_name_norm` for cross-source comparison (see §12.6).
12. **`postal_streets` covers Bucuresti + localities over 50,000 population only.** Zero postal rows for a small/rural UAT is expected, not a bug — don't read it as "this town has no streets."

## 14. Out of scope for the data layer

- Visual design, color palette, layout — see Design Brief.
- Editorial copy in Romanian — see Design Brief.
- Per-street geocoding — Phase 3.
- Voter-data joins — different project.
- Real-time updates — the registry updates infrequently; manual rebuild is fine.

## 15. Reference: current state files

| File | Purpose |
|---|---|
| `build_db.py` | ETL + schema + indexes |
| `seed_lookups.py` | 90-row starter curation |
| `queries.sql` | Named query catalog by view |
| `run_queries.py` | Runner with `log` and `regexp` shims |
| `streets.db` | Generated artifact (4-județ sample) |

To verify the prototype: run `build_db.py`, then `seed_lookups.py`, then `run_queries.py`. Expected output documented in conversation transcript.
