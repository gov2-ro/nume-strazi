# CLAUDE.md

Operational instructions for Claude Code working on this project. Loaded into every session. Keep it lean — full specs live elsewhere.

## What this is

An analytical project on Romanian street names, combining 4 sources with equal standing — no single one is authoritative: the Permanent Electoral Authority's polling-section export (~140k rows, 41 județe + Bucharest sectors), OpenStreetMap, postal codes, and ANCPI's RENNS cadastral registry. Output: a SQLite database with a query catalog, eventually feeding a Romanian-language interactive publication.

Currently in **prototype phase**. The data layer is being hardened; dashboard runtime is deferred. Solo project.

## Read first

When starting a new session, in this order:

1. **This file** — operational rules and project pulse.
2. **`docs/CODE_SPEC.md`** — full PRD for the data layer. Schema rationale, cleaning rules, curation strategy, prioritized task list, pitfalls.
3. **`docs/queries.sql`** — what's already built, organized by dashboard view.
4. **`DESIGN_BRIEF.md`** — only when work touches editorial decisions or hero findings. Otherwise, skip.
5. **`docs/INGESTION_PIPELINE.md`** — only when adding a new street-name source. Otherwise, skip.

If asked to do something not covered by the above, ask before improvising.

## Repository layout

```
.
├── CLAUDE.md             # this file
├── build_db.py           # ETL: xlsx → SQLite. Idempotent.
├── streets_lib.py        # Shared helpers (normalize_match, strip_street_type, ...)
├── seed_lookups.py       # Hand-curated starter data (4 lookup tables)
├── run_queries.py        # Runner with log() and regexp() shims
├── docs/
│   ├── CODE_SPEC.md      # full data-layer PRD
│   ├── DESIGN_BRIEF.md   # editorial direction for the dashboard
│   ├── INGESTION_PIPELINE.md  # reference for adding a new street-name source
│   ├── queries.sql       # Named query catalog (-- :name slug)
│   ├── BACKLOG.md        # tracked issues and future work
│   └── activity-history.md
├── tools/
│   ├── export_unclassified.py  # export top-N unclassified keys to CSV
│   ├── import_csv.py           # upsert classified CSV into lookup tables
│   ├── seed_top500.py          # batch 1 curation (top-500 keys)
│   ├── seed_batch2.py          # batch 2 curation
│   ├── llm_layer.py            # provider-agnostic LLM access (simonw/llm + .env + pricing)
│   ├── llm_classify.py         # LLM batch classifier (DeepSeek/Google/Anthropic/OpenRouter)
│   ├── llm_runs_report.py      # summarise llm_runs.jsonl — tokens + cost per run
│   ├── llm_compare.py          # compare two llm_classify CSVs for convergence
│   ├── audit_person_qids.py    # verify persons.wikidata_qid against P31=Q5; clear/re-resolve
│   ├── fetch_portraits.py      # Wikidata P18 → Wikimedia thumbnails → dist/portraits/
│   ├── osm_boundaries.py       # PBF admin_level=8 → uat_boundaries (SIRUTA polygons)
│   ├── osm_ingest.py           # PBF → osm_streets (needs osmium + shapely)
│   ├── osm_match.py            # electoral_dedup ↔ osm_streets join
│   ├── osm_score.py            # importance_v1 = highway × log(length) + ref bonus
│   ├── osm_sanity.py           # top-10 / coverage report for reference UATs
│   ├── postal_ingest.py        # postal xlsx → postal_streets
│   ├── postal_match.py         # electoral_dedup ↔ postal_streets join
│   ├── postal_sanity.py        # coverage report for reference UATs
│   ├── renns_ingest.py         # ANCPI RENNS API → renns_streets (per-UAT crawl)
│   ├── renns_match.py          # electoral_dedup ↔ renns_streets join
│   ├── renns_sanity.py         # coverage report for reference UATs + national rollout %
│   ├── restore_curation.py     # run the full post-rebuild curation restore, asserting coverage
│   └── materialize_all_street_names.py  # all_street_names view → fast indexed cache table
└── data/
    ├── reference/        # Raw xlsx inputs (electoral-source exports)
    ├── curation/         # CSV inputs for incremental curation
    ├── gis/              # GIS / geometry assets (future)
    └── streets.db        # Generated artifact. Not the source of truth.
```

## Critical rules — read every time

These are the booby traps. Internalize before writing any query or transform.

1. **Never count on `streets` directly.** Use the `electoral_dedup` view (renamed from `streets_dedup` 2026-07-15 — it's the AEP electoral source's own deduplicated street list, one of 4 equal sources; see rule #11 for `all_street_names`, the cross-source union). Section-rows duplicate streets that span polling sections. Counting raw `streets` overcounts by section repetition. Its dedup key is `(siruta, name_normalized, street_type)` — street type is part of a street's identity (a UAT can have both `Bulevardul X` and `Strada X` as genuinely distinct streets, fixed 2026-07-08, see CODE_SPEC §14); the count is currently **107,957**, not the older 105,343.
2. **Two normalization keys, two purposes.** `name_normalized` for grouping streets by canonical name. `core_name_norm` for joining to curated lookup tables (`persons`, `nature_terms`, `name_categories`, `place_refs`). Never mix them.
3. **`î ≡ â` only in match keys.** The display column `name` preserves the original orthography. The `_normalized` columns collapse them. Don't normalize for display.
4. **Aliases require DISTINCT.** Section-rows duplicate the same alias multiple times. Any query joining `street_aliases` should use `SELECT DISTINCT` or aggregate.
5. **`core_name = NULL` on numeric streets is intentional.** Don't "fix" it.
6. **Curation upserts must be idempotent.** Use `ON CONFLICT(core_name_norm) DO UPDATE`. Re-running an import with the same CSV must be a no-op.
7. **`osm_streets` is already grouped per `(uat_siruta, name_normalized)`.** OSM splits one street into many ways at every junction; `tools/osm_ingest.py` merges them before insert. Don't `GROUP BY` again or you'll over-aggregate. To compare an electoral-source street to its OSM counterpart, join `electoral_dedup` ↔ `osm_streets` via `street_osm_matches` (don't re-derive the join in queries).
8. **OSM scope is populated areas only.** Motorways and trunks are filtered out at ingest by design. If a query expects them, it's wrong — they belong to a future inter-city analysis, not this one.
9. **Postal source is the 2016 xlsx only (`data/reference/coduri-postale+/infocod-cu-siruta-mai-2016.xlsx`).** The 2009 `coduri_postale.sql` dump in the same folder was evaluated and excluded — it adds zero new locality coverage over the xlsx (see CODE_SPEC §12.1), don't re-propose it without reading that section first. Postal only covers Bucuresti + localities over 50,000 population; zero `postal_streets` rows for a small/rural UAT is expected, not a bug. Cross-source comparison (`streets_all_sources`, `docs/queries.sql`'s `external_corroboration_gap`) must join on `core_name_norm`, never `name_normalized` — `osm_streets.name_normalized` includes the street-type prefix, postal's/RENNS's and the electoral source's don't.
10. **RENNS's `uat.id` is the electoral source's SIRUTA code directly** — no name-matching fallback needed (see CODE_SPEC §13.4). Only crawl it per-`(county, UAT)`; the unfiltered flat endpoint has confirmed pagination drift (see CODE_SPEC §13.5) — don't re-add it without re-verifying that first. București has zero RENNS roads (structural, not a bug) and only ~60% of Romania's UATs are digitized in RENNS yet.
11. **`streets_all_sources` is additive but not cross-source-deduplicated** — a street missing from the electoral source but corroborated by 2-3 external sources gets one row *per source* there. Use `all_street_names` (CODE_SPEC §13.8/§14.5) for a genuinely deduplicated "every street name in Romania" list — **this is the project's canonical corpus, materialized as `all_street_names_cache`**: one flat, fully symmetric view across all 4 sources (the electoral source is just another source, no `layer` column, no dependency on the match tables), grouped by `(siruta, street_type, core_name_norm)` — not `core_name_norm` alone — for the same type-matters reason as rule #1, with `in_electoral` (0/1) marking whether the electoral source is among the contributing sources. Type mismatches (e.g. OSM's `Calea X` vs postal's `Strada X`) are never auto-merged, even electoral-to-external — check `type_variant_candidates` (`docs/queries.sql`) instead of assuming they've been reconciled. `variants` (JSON) preserves every source's exact spelling; `corroboration_count` counts distinct sources; no source is ranked above another, so the representative name is just the alphabetically-first one.
12. **`build_db.py` wipes ALL curation state, not just the schema.** Rebuilding to add/change a table drops `persons`/`nature_terms`/`name_categories`/`place_refs`/QIDs/wiki_scope/birthplaces/biostats along with everything else (observed: 57%→16.4% classification coverage after a rebuild that only restored OSM/postal, not curation — twice). Always run `python3 tools/restore_curation.py` after `build_db.py` — it runs the full restore sequence in fixed order and asserts `classification_coverage_summary`'s `pct_streets_classified` against a known-good floor, failing loudly instead of silently shipping degraded curation. **It also wipes the OSM/postal/RENNS source tables, which nothing restores** — those need a per-source re-ingest (see Common Commands). `restore_curation.py` pre-flight-checks them against `SOURCE_FLOORS` and refuses to run if one is starved; a source that genuinely can't be re-ingested needs an explicit `--allow-empty <table>` so the exemption shows up in the run log rather than passing silently. That check exists because `renns_streets` sat empty for two weeks (2026-07-15 → 08-01) while every other assertion still passed. For a schema-only change, prefer a targeted live migration (`DROP VIEW`/`CREATE VIEW` against the running DB) over a full rebuild — see how the street_type dedup fix (#1) was applied.
13. **OSM/postal/RENNS match tiers are named `exact_type_core` (1.0) / `fuzzy_core_name` (0.5) / (postal only) `reordered_core_name` (0.4)**, not `exact_normalized`. Pass 1 compares `(street_type, core_name_norm)` directly — never compare raw `name_normalized` strings across sources, since OSM's includes the street-type prefix and the electoral source's/postal's/RENNS's don't (rule #9).
14. **`uat_reference` (siruta → judet/uat label) is a build-time-only table**, loaded from `data/gis/populatie-romania-siruta-coords.csv` + 6 hardcoded Bucharest sectors, used solely to label `all_street_names` rows for UATs the electoral source has zero data for. Dropped from the shipped `dist/streets.db` (already baked into `all_street_names`'s materialized columns) — don't expect to query it in the client-side filter UI.
15. **OSM ways are assigned to UATs by polygon containment, never by proximity.** `tools/osm_boundaries.py` builds `uat_boundaries` (3,183 of 3,185 SIRUTAs) from OSM `admin_level=8` relations plus Bucharest's six `admin_level=9` "Sector N" relations, and `tools/osm_ingest.py` point-in-polygons each way's midpoint against it. Run the boundaries tool **before** the ingest — the ingest exits if `uat_boundaries` is empty. OSM tags no SIRUTA on boundaries (`siruta:code` on 6 of 3,379), so the polygon→SIRUTA mapping is geometric: a boundary owns the SIRUTA whose reference centroid it contains. Do **not** reintroduce a nearest-centroid fallback: until 2026-07-31 the ingest snapped ways to the nearest centroid *drawn from a list filtered to electoral SIRUTAs*, which both capped OSM at ~1,207 UATs and silently attributed out-of-scope streets to a neighbour up to ~55 km away. Fixing it took OSM from 1,185 to 2,630 UATs covered. A way outside every boundary is dropped, by design.
16. **`persons.wikidata_qid` needs `P31 = Q5` verification.** Romania names communes after national figures, so a bare label search returns the *place*, not the person — the commune "Nicolae Bălcescu" (Q940856) outranked the man (Q513394). A 2026-07-31 audit found 84 of 297 curated QIDs wrong (17 communes, 6 taxa, 5 disambiguation pages, 4 villages; `mihail eminescu` pointed at Q169930, "Extended play"). `tools/wikidata_persons.py` now gates every candidate on P31; re-audit with `tools/audit_person_qids.py` after any bulk QID work. Multiple `core_name_norm` rows sharing one `full_name`/`wikidata_qid` is the project's alias mechanism, not a duplicate — don't dedupe them.

## Common commands

```bash
# Rebuild from scratch (drops data/streets.db)
python3 build_db.py

# Rebuild with row limit for fast iteration
python3 build_db.py --limit 5000

# Restore ALL curation state after a rebuild (seed_lookups, seed_top500,
# seed_batch2, the 3 one-off llm_*.csv imports, wikidata_persons/wiki_birthplace/
# wiki_biostats --replay-csv --force, in that fixed order) — asserts
# classification_coverage_summary's pct_streets_classified against a known-good
# floor and fails loudly instead of silently shipping degraded curation.
# Always operates on data/streets.db (seed_top500.py/seed_batch2.py can't be
# pointed at another path, so this script doesn't offer a --db override either).
python3 tools/restore_curation.py

# Pre-flight also asserts the OSM/postal/RENNS source tables are above their
# SOURCE_FLOORS. RENNS is empty while renns.ancpi.ro is offline, so today it
# needs an explicit waiver (repeat the flag per table):
python3 tools/restore_curation.py --allow-empty renns_streets

# wiki_scope/sitelinks aren't included above (no --replay-csv mode — always a
# live, rate-limited Wikidata call). Reported by restore_curation.py either way;
# pass --wiki-scope to also fetch pending rows live. It applies the 429→'unknown'
# remediation automatically (reset + one bounded retry pass) — see wiki_scope.py
# if you need to run it standalone instead.
python3 tools/restore_curation.py --wiki-scope

# Fetch/refresh portrait thumbnails (run once; idempotent; skips already-cached)
python3 tools/fetch_portraits.py

# Build the slim production DB shipped to clients (sql.js-httpvfs reads this).
# Materializes streets_all_sources + all_street_names (the cross-source-
# deduplicated master list), drops OSM/postal/RENNS source tables + street_aliases,
# VACUUMs, page_size=4096. ~90 MB (bigger than the pre-RENNS ~13.5 MB since both
# consolidation tables now carry 4 sources' worth of rows).
python3 tools/build_dist_db.py

# Build for a subdirectory deployment (e.g. https://example.com/nume-strazi/)
# --variant all rebuilds metodologie.html too; --base must match the actual deploy path
python3 build_site.py --variant all --detail --base /nume-strazi
# Test locally under the same prefix (--base must match --mount so the rebuild is correct):
python3 build_site.py --variant all --serve --port 9000 --base /nume-strazi --mount /nume-strazi

# Run all named queries from docs/queries.sql
python3 run_queries.py

# LLM classification. Keys come from .env via tools/llm_layer.py (simonw/llm) —
# no need to export anything. Provider is inferred from the model name.
# Use deepseek-chat, NOT the .env default deepseek-v4-flash: v4-flash is a
# REASONING model that bills thinking against max_tokens and regularly burns the
# whole budget before emitting content, losing ~50% of batches. Measured
# 2026-08-01 on identical 20-key batches: deepseek-chat 0.44 s/key & $0.11/1k
# keys with zero failures; deepseek-v4-flash 11.09 s/key, $0.40/1k, half the
# batches empty. Full 39k backlog: ~5 h and ~$4.30 vs ~58 h.
python3 tools/llm_classify.py --model deepseek-chat --limit 500
python3 tools/llm_classify.py --model deepseek-chat --limit 0    # whole backlog
python3 tools/llm_classify.py --model gemini-2.5-flash-lite --limit 500

# Resumable: re-running the same command skips keys already in the --out CSV, so
# an interrupted run loses at most one batch. Aborts after 5 consecutive failed
# batches (--max-consecutive-errors) — a bad model name 400s forever otherwise;
# one such typo run churned 1,271 dead batches before this guard existed.

# Per-batch model/token/cost provenance, appended to data/curation/llm_runs.jsonl
python3 tools/llm_runs_report.py                    # one line per run
python3 tools/llm_runs_report.py --batches RUN_ID   # per-batch detail
python3 tools/llm_runs_report.py --errors           # only failed batches
python3 tools/llm_runs_report.py --reprice          # recost from current PRICING
# Token counts are exact (straight from the API); cost is an estimate from
# llm_layer.PRICING, a hand-maintained table that will drift. Fix a price there
# and --reprice recosts every past run.

python3 tools/llm_compare.py data/curation/llm_claude-haiku-4-5.csv \
                              data/curation/llm_gemini-2.0-flash-lite.csv

# Export top-N unclassified keys for manual curation
python3 tools/export_unclassified.py --limit 500

# Import a classified CSV back into the DB
python3 tools/import_csv.py data/curation/my_batch.csv

# Verify curated Wikidata QIDs really point at humans (P31=Q5), not the commune
# named after them. --fix-not-human clears bad QIDs + their derived columns;
# --reresolve then re-searches those keys with the P31-gated resolver.
python3 tools/audit_person_qids.py --csv data/curation/qid_audit.csv
python3 tools/audit_person_qids.py --fix-not-human --reresolve

# Quick interactive exploration
sqlite3 data/streets.db

# OSM enrichment (requires osmium + shapely; PBF at data/reference/romania-latest.osm.pbf)
# Refresh the PBF first if it's stale — OSM mapping moves fast:
#   curl -L -o data/reference/romania-latest.osm.pbf \
#        https://download.geofabrik.de/europe/romania-latest.osm.pbf
# (keep the .osm.pbf suffix — pyosmium detects format by filename, not content)
python3 tools/osm_boundaries.py --rebuild    # admin_level=8 → uat_boundaries (~15 s). REQUIRED FIRST.
python3 tools/osm_ingest.py                  # PBF → osm_streets (~15 min on full Romania)
python3 tools/osm_match.py                   # populate street_osm_matches
python3 tools/osm_score.py                   # compute importance_v1
python3 tools/osm_sanity.py                  # eyeball top-10 + coverage

# Postal-code enrichment (stdlib + openpyxl only; source: data/reference/coduri-postale+/)
python3 tools/postal_ingest.py --rebuild     # xlsx → postal_streets
python3 tools/postal_match.py                # populate street_postal_matches
python3 tools/postal_sanity.py               # eyeball reference-UAT coverage

# RENNS enrichment (live API; stdlib urllib only, no PBF/xlsx needed)
python3 tools/renns_ingest.py --rebuild      # per-(county,UAT) crawl → renns_streets (~1 min)
python3 tools/renns_ingest.py --uat-siruta 1017  # single UAT, fast iteration
python3 tools/renns_match.py                 # populate street_renns_matches
python3 tools/renns_sanity.py                # eyeball reference-UAT + national coverage %

# Materialize all_street_names (the cross-source union view) into a fast,
# indexed all_street_names_cache table with a name_normalized column, for any
# future per-entity-loop querying against the union. Run after the full
# 4-source pipeline above (needs osm_streets/postal_streets/renns_streets
# populated); re-run any time one of those sources is re-ingested. Idempotent.
python3 tools/materialize_all_street_names.py
```

## Conventions

- **Python 3.11+.** Stdlib + `openpyxl` only in the ETL path. No pandas. No ORM.
- **SQL files use named blocks** with `-- :name slug_id` markers. The runner splits on these.
- **Romanian text:** post-1993 orthography. Pre-1993 forms accepted as input only. Cedilla diacritics (`ş`, `ţ`) get fixed on ingest, never written out.
- **Romanian numbers:** thousands separator is `.`, decimal is `,`. `12.847,5` is twelve thousand, not twelve.
- **All SQL parameterized.** No f-string injection. Future curation tools take user CSV — must respect this.
- **snake_case** everywhere except SQL keywords.
- **Idempotency over migrations.** This is a prototype; rebuilding from source is cheap. No Alembic, no schema versioning yet. If that changes, update this file.

## When the data confuses you

The full electoral dataset has properties that surprise people. If a query returns weird results, check these first:

- **Did you dedup?** Always `electoral_dedup`, not `streets`.
- **Are you joining on the right key?** `core_name_norm` for curated tables, `name_normalized` for street-level grouping.
- **Is the sample biased?** During prototype phase, the 4-județ sample is 75% Prahova-rural. Frequencies skew nature-heavy. Don't generalize to "Romanian streets" from sample data.
- **Are Bucharest sectors throwing you off?** Six sectors register as separate UATs (`BUCUREȘTI SECTORUL N`). Treat as separate UATs for dedup; aggregate as `B` for county comparisons.

## Decision boundaries

- **Locked:** SQLite, schema layout, normalization rules, dedup approach. Don't change without a clear reason and an update to CODE_SPEC. (The dedup key itself was revised once, 2026-07-08 — added `street_type` — after finding it silently merged distinct streets; see CODE_SPEC §14. That's the bar: a demonstrated correctness bug plus explicit user sign-off, not a stylistic preference.)
- **Open:** dashboard runtime, person-resolution layer (multiple `core_name_norm` keys → one identity), publishing as Datasette alongside the dashboard.
- **Out of scope this phase:** per-street geocoding, voter-data joins, real-time updates, multilingual UI.

## Don't

- Don't add pandas to the ETL path. The simplicity is intentional.
- Don't generate fictional Romanian copy that "sounds right." If editorial copy is needed and the user hasn't approved a Romanian-native pass, mark it `[needs RO editorial review]` and move on.
- Don't auto-merge person identities (e.g. `c.i. parhon` ↔ `constantin ion parhon`) without explicit instruction. Resolution is a separate, careful task.
- Don't claim certainty about communist-era renamings. We can detect ideological tokens; we cannot prove dating without external sources.
- Don't strip diacritics from display strings. If you find code doing this, flag it as a bug.
- Don't optimize prematurely. The data is small. Clarity > cleverness.

## When you're stuck

Ask the user. The user is a senior dev — concise questions, no preamble. Specifically helpful patterns:

- "I see X and Y are both reasonable. Picking X by default unless you push back."
- "Before I write 200 lines of curation tooling: is the Wikidata route still preferred over LLM batch?"
- "Found an edge case: <description>. Two options: <A>, <B>. Which?"

Avoid: long lists of clarifying questions, restating the request back, or "I'll be happy to help with that!"-style preamble.

## Other notes

- When detecting things that need to be addressed later, add to `docs/BACKLOG.md`. Use a checkbox `- [ ]` entry with a clear title and enough context to act on it later.
- After completing any meaningful work, add an entry to `docs/activity-history.md` under a `## YYYY-MM-DD — Short Title` heading. Include what was done, why, and any non-obvious decisions.
- When running Python commands, always first activate the following venv `~/devbox/envs/240826/` (/Users/pax/devbox/envs/240826/bin/activate)