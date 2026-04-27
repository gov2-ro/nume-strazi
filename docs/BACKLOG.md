# Backlog

Items detected during sessions. Each entry has enough context to act on cold.

---

## P0

- [x] **Fix stale CLAUDE.md layout section** — The `## Repository layout` and `## Common commands` sections describe a different layout than what exists: docs are in `docs/` (not root), DB lives at `data/streets.db` (not `streets.db` in root), source xlsx is in `data/reference/` (not `data/source/`), and `--limit N` flag is already implemented (remove the "(P0 task in CODE_SPEC)" note).

---

## P1

- [ ] **`communist_aliases` query missing DISTINCT** — `docs/queries.sql` `:name communist_aliases` produces duplicate rows: same `(current_name, communist_alias, uat)` triplet repeated once per polling section. The query joins `streets` (not `streets_dedup`) and doesn't use `SELECT DISTINCT`. Fix: add `DISTINCT` or rewrite to join via `streets_dedup`.

- [ ] **`unique_names` query polluted by numbered-street names** — `:name unique_names` surfaces names like "1 1 Mai", "1 22 Decembrie 1989" from DJ — strings that parse as `is_numeric=0` but are really section-prefixed street numbers. Consider adding `WHERE is_numeric = 0 AND name NOT REGEXP '^\d'` or filtering in post-processing.

- [ ] **Investigate DUMBRĂVIȚA (BV) near-zero entropy** — `uat_diversity` shows DUMBRĂVIȚA BV with entropy 0.14 on 428 streets. Investigate what name dominates and whether it's a data anomaly.
  ```sql
  SELECT name, COUNT(*) AS n FROM streets_dedup
  WHERE uat = 'DUMBRĂVIȚA' AND judet = 'BV'
  GROUP BY name_normalized ORDER BY n DESC LIMIT 10;
  ```

- [ ] **Curation tooling (from CODE_SPEC P1)**
  - [x] `tools/export_unclassified.py` — top-N unclassified `core_name_norm` ordered by frequency, with sample streets/UATs
  - [x] `tools/import_csv.py` — generic upserter for the 4 lookup tables
  - [ ] `tools/wikidata_persons.py` — SPARQL query for top-N unmatched person candidates
  - [x] `tools/llm_classify.py` — Claude Haiku batch classifier (rate-limited, idempotent)
  - [ ] Coverage view: `streets_classified_pct`

- **Classification pipeline decision (settled):** run `llm_classify.py` directly on all unclassified keys. No `rule_classify.py` pre-filter, no spaCy/RoWordNet middle tier. Rationale: full 28k-key run costs ~$2 at Haiku pricing, making rule/NLP pre-filters a complexity cost that saves nothing. LLM handles Romanian morphology and cultural context better than a lemmatizer+wordnet chain would anyway. RoWordNet remains a P3 option only if API-free reproducibility becomes a hard requirement.

---

## P2

- [ ] **Gender story needs curation before it can be told** — Current data has very few women classified. The gender gap is a headline finding for the publication but requires meaningful person-table coverage first. Priority curation target: female honorees in the top-500 unclassified names.

- [ ] **`ORAŞ CERNAVODĂ` numeric streets named 1848 and 1933** — `anonymous_uats` shows CERNAVODĂ CT with 5 "numeric" streets, lowest=1848, highest=1933. These are likely historical date references rather than true street numbers. Consider a sub-query that separates true sequence numbering (contiguous run starting at 1) from isolated year-numbers.

- [x] **OSM enrichment: scaffolding** — Tables (`osm_streets`, `street_osm_matches`) added to `build_db.py`. Tools written: `tools/osm_ingest.py`, `tools/osm_match.py`, `tools/osm_score.py`, `tools/osm_sanity.py`. v1 score = `highway_weight × log(1 + length_m) + ref_bonus`, z-scored within UAT. POI counts deliberately skipped (would measure mapper density, not street importance).

- [ ] **OSM enrichment: download Romania PBF and run end-to-end** — Deferred from the scaffolding session because user was on mobile data. Steps:
  1. `wget https://download.geofabrik.de/europe/romania-latest.osm.pbf -O data/reference/romania-latest.osm.pbf` (~700 MB).
  2. From `~/devbox/envs/240826/`: `pip install pyrosm shapely`.
  3. `python3 tools/osm_ingest.py` (expect ~10–30 min on full PBF).
  4. `python3 tools/osm_match.py` then `python3 tools/osm_score.py`.
  5. `python3 tools/osm_sanity.py` — eyeball the top-10 lists for the 5 reference UATs.
  Document the PBF snapshot date in `docs/CODE_SPEC.md` §11 once ingested.

- [ ] **OSM enrichment: importance v2 (per-UAT betweenness centrality)** — After v1 is validated, add `betweenness_uat` column. For each UAT subgraph (small enough that `networkx.betweenness_centrality` is cheap), build node=intersection / edge=way-segment graph weighted by length. Combine: `score_v2 = 0.6·z(v1) + 0.4·z(betweenness)`. Worth doing only if v1 misranks visibly in `osm_sanity.py` output — inside settlements the highway hierarchy collapses to flat tertiary/residential, which is exactly where centrality discriminates.

- [ ] **OSM enrichment: SIRUTA-on-admin-boundary fallback** — `tools/osm_ingest.py` resolves UAT identity by reading `ref:RO:SIRUTA`/`ref:siruta`/`siruta` tags from admin_level=8 polygons, then falls back to name-match against `populatie-romania-siruta-coords.csv`. If too many UATs drop in step 1 (watch the `unresolved` count), build a centroid-distance fallback against the same CSV.

---

## P3

- [ ] **`run_queries.py` output not machine-readable** — The runner pretty-prints to stdout. When curation tooling or a dashboard pipeline needs query output, it'll need JSON/CSV mode. Add `--format json|csv|table` flag.

- [ ] **RoWordNet for nature/abstract classification** — After `llm_classify.py` runs, evaluate RoWordNet as a deterministic fallback for residual unclassified nature and abstract terms. Approach: lemmatize `core_name_norm` to dictionary form (genitives like `florilor` → `floare`, `trandafirului` → `trandafir`) using a Romanian morphological lemmatizer, then walk the WordNet hypernym chain to map to a `nature_type` or `category`. Useful if: (a) LLM leaves a long tail of plant/terrain/abstract names unclassified, or (b) reproducibility without API calls is a requirement. Prerequisite: find a Romanian lemmatizer that handles genitive/plural forms reliably (`ro_lemmatizer` in spaCy's `ro_core_news_lg` is a candidate). Skip RoNER — it gives entity type only, not the structured metadata (gender, era, profession) we need for persons.


## Misc ideas

Go wild.
The people, how old, what are the occupations? Reason of death?