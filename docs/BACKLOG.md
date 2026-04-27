# Backlog

Items detected during sessions. Each entry has enough context to act on cold.

---

## P0

- [ ] **Fix stale CLAUDE.md layout section** — The `## Repository layout` and `## Common commands` sections describe a different layout than what exists: docs are in `docs/` (not root), DB lives at `data/streets.db` (not `streets.db` in root), source xlsx is in `data/reference/` (not `data/source/`), and `--limit N` flag is already implemented (remove the "(P0 task in CODE_SPEC)" note).

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
  - [ ] `tools/llm_classify.py` — Claude Haiku batch classifier (rate-limited, idempotent)
  - [ ] Coverage view: `streets_classified_pct`

---

## P2

- [ ] **Gender story needs curation before it can be told** — Current data has very few women classified. The gender gap is a headline finding for the publication but requires meaningful person-table coverage first. Priority curation target: female honorees in the top-500 unclassified names.

- [ ] **`ORAŞ CERNAVODĂ` numeric streets named 1848 and 1933** — `anonymous_uats` shows CERNAVODĂ CT with 5 "numeric" streets, lowest=1848, highest=1933. These are likely historical date references rather than true street numbers. Consider a sub-query that separates true sequence numbering (contiguous run starting at 1) from isolated year-numbers.

- [ ] **OSM enrichment: street geometry + importance** — After the data layer stabilises, pull street geometries from OpenStreetMap (Overpass API or a Romania PBF extract) and join on UAT + normalized name. Goals: (1) rank streets by physical size/length and width (highway class → proxy for importance), (2) flag whether a street is a main artery vs a cul-de-sac, (3) weight frequency counts by relative position in town (central vs peripheral). This enrichment would power a "most important street in Romania named after a woman" type of finding. Prerequisite: stable UAT–OSM admin boundary mapping.

---

## P3

- [ ] **`run_queries.py` output not machine-readable** — The runner pretty-prints to stdout. When curation tooling or a dashboard pipeline needs query output, it'll need JSON/CSV mode. Add `--format json|csv|table` flag.

- [ ] **RoWordNet for nature/abstract classification** — After `llm_classify.py` runs, evaluate RoWordNet as a deterministic fallback for residual unclassified nature and abstract terms. Approach: lemmatize `core_name_norm` to dictionary form (genitives like `florilor` → `floare`, `trandafirului` → `trandafir`) using a Romanian morphological lemmatizer, then walk the WordNet hypernym chain to map to a `nature_type` or `category`. Useful if: (a) LLM leaves a long tail of plant/terrain/abstract names unclassified, or (b) reproducibility without API calls is a requirement. Prerequisite: find a Romanian lemmatizer that handles genitive/plural forms reliably (`ro_lemmatizer` in spaCy's `ro_core_news_lg` is a candidate). Skip RoNER — it gives entity type only, not the structured metadata (gender, era, profession) we need for persons.
