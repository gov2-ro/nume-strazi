# CLAUDE.md

Operational instructions for Claude Code working on this project. Loaded into every session. Keep it lean — full specs live elsewhere.

## What this is

An analytical project on Romanian street names. Source: the Permanent Electoral Authority's polling-section registry (~140k rows, 41 județe + Bucharest sectors). Output: a SQLite database with a query catalog, eventually feeding a Romanian-language interactive publication.

Currently in **prototype phase**. The data layer is being hardened; dashboard runtime is deferred. Solo project.

## Read first

When starting a new session, in this order:

1. **This file** — operational rules and project pulse.
2. **`docs/CODE_SPEC.md`** — full PRD for the data layer. Schema rationale, cleaning rules, curation strategy, prioritized task list, pitfalls.
3. **`docs/queries.sql`** — what's already built, organized by dashboard view.
4. **`DESIGN_BRIEF.md`** — only when work touches editorial decisions or hero findings. Otherwise, skip.

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
│   ├── queries.sql       # Named query catalog (-- :name slug)
│   ├── BACKLOG.md        # tracked issues and future work
│   └── activity-history.md
├── tools/
│   ├── export_unclassified.py  # export top-N unclassified keys to CSV
│   ├── import_csv.py           # upsert classified CSV into lookup tables
│   ├── seed_top500.py          # batch 1 curation (top-500 keys)
│   ├── seed_batch2.py          # batch 2 curation
│   ├── llm_classify.py         # LLM batch classifier (Anthropic/Google/OpenRouter)
│   ├── llm_compare.py          # compare two llm_classify CSVs for convergence
│   ├── fetch_portraits.py      # Wikidata P18 → Wikimedia thumbnails → dist/portraits/
│   ├── osm_ingest.py           # PBF → osm_streets (needs osmium + shapely)
│   ├── osm_match.py            # streets_dedup ↔ osm_streets join
│   ├── osm_score.py            # importance_v1 = highway × log(length) + ref bonus
│   └── osm_sanity.py           # top-10 / coverage report for reference UATs
└── data/
    ├── reference/        # Raw xlsx inputs (registry exports)
    ├── curation/         # CSV inputs for incremental curation
    ├── gis/              # GIS / geometry assets (future)
    └── streets.db        # Generated artifact. Not the source of truth.
```

## Critical rules — read every time

These are the booby traps. Internalize before writing any query or transform.

1. **Never count on `streets` directly.** Use the `streets_dedup` view. Section-rows duplicate streets that span polling sections. Counting raw `streets` overcounts by section repetition.
2. **Two normalization keys, two purposes.** `name_normalized` for grouping streets by canonical name. `core_name_norm` for joining to curated lookup tables (`persons`, `nature_terms`, `name_categories`, `place_refs`). Never mix them.
3. **`î ≡ â` only in match keys.** The display column `name` preserves the original orthography. The `_normalized` columns collapse them. Don't normalize for display.
4. **Aliases require DISTINCT.** Section-rows duplicate the same alias multiple times. Any query joining `street_aliases` should use `SELECT DISTINCT` or aggregate.
5. **`core_name = NULL` on numeric streets is intentional.** Don't "fix" it.
6. **Curation upserts must be idempotent.** Use `ON CONFLICT(core_name_norm) DO UPDATE`. Re-running an import with the same CSV must be a no-op.
7. **`osm_streets` is already grouped per `(uat_siruta, name_normalized)`.** OSM splits one street into many ways at every junction; `tools/osm_ingest.py` merges them before insert. Don't `GROUP BY` again or you'll over-aggregate. To compare a registry street to its OSM counterpart, join `streets_dedup` ↔ `osm_streets` via `street_osm_matches` (don't re-derive the join in queries).
8. **OSM scope is populated areas only.** Motorways and trunks are filtered out at ingest by design. If a query expects them, it's wrong — they belong to a future inter-city analysis, not this one.

## Common commands

```bash
# Rebuild from scratch (drops data/streets.db)
python3 build_db.py

# Rebuild with row limit for fast iteration
python3 build_db.py --limit 5000

# Apply starter curation (always after build_db; idempotent)
python3 seed_lookups.py

# Apply batch curation
python3 tools/seed_top500.py
python3 tools/seed_batch2.py

# Restore manually curated QIDs after rebuild (authoritative: data/curation/wikidata_qids.csv)
python3 tools/wikidata_persons.py --replay-csv --force

# Restore wiki scope/sitelinks (run in batches of ~40 to avoid rate limiting; see wiki_scope.py)
python3 tools/wiki_scope.py --limit 40   # repeat until no output

# Fetch/refresh portrait thumbnails (run once; idempotent; skips already-cached)
python3 tools/fetch_portraits.py

# Run all named queries from docs/queries.sql
python3 run_queries.py

# LLM classification (provider auto-detected from model name)
# ANTHROPIC_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY must be set
python3 tools/llm_classify.py --limit 500                              # Haiku (default)
python3 tools/llm_classify.py --model gemini-2.0-flash-lite --limit 500  # Google
python3 tools/llm_classify.py --model google/gemini-flash-1.5-8b --limit 500  # OpenRouter
python3 tools/llm_compare.py data/curation/llm_claude-haiku-4-5.csv \
                              data/curation/llm_gemini-2.0-flash-lite.csv

# Export top-N unclassified keys for manual curation
python3 tools/export_unclassified.py --limit 500

# Import a classified CSV back into the DB
python3 tools/import_csv.py data/curation/my_batch.csv

# Quick interactive exploration
sqlite3 data/streets.db

# OSM enrichment (requires osmium + shapely; PBF at data/reference/romania-latest.osm.pbf)
python3 tools/osm_ingest.py                  # PBF → osm_streets (~15 min on full Romania)
python3 tools/osm_match.py                   # populate street_osm_matches
python3 tools/osm_score.py                   # compute importance_v1
python3 tools/osm_sanity.py                  # eyeball top-10 + coverage
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

The full registry has properties that surprise people. If a query returns weird results, check these first:

- **Did you dedup?** Always `streets_dedup`, not `streets`.
- **Are you joining on the right key?** `core_name_norm` for curated tables, `name_normalized` for street-level grouping.
- **Is the sample biased?** During prototype phase, the 4-județ sample is 75% Prahova-rural. Frequencies skew nature-heavy. Don't generalize to "Romanian streets" from sample data.
- **Are Bucharest sectors throwing you off?** Six sectors register as separate UATs (`BUCUREȘTI SECTORUL N`). Treat as separate UATs for dedup; aggregate as `B` for county comparisons.

## Decision boundaries

- **Locked:** SQLite, schema layout, normalization rules, dedup approach. Don't change without a clear reason and an update to CODE_SPEC.
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