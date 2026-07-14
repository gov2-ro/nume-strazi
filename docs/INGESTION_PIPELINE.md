# Ingestion Pipeline

Reference for adding a new street-name source. Written 2026-07-14 after
the 4th source (RENNS) was added, capturing the pattern all 3 external
sources (OSM, postal, RENNS) converged on — plus the specific mistakes
each one made first, so a 5th source doesn't repeat them.

## The shape of the pipeline

Every external source goes through the same 3 stages, each its own
script in `tools/`:

```
tools/<source>_ingest.py   raw source → <source>_streets table
tools/<source>_match.py    <source>_streets ↔ registry streets_dedup
tools/<source>_sanity.py   eyeball coverage on 5 reference UATs
(all_street_names view picks it up automatically — see below)
```

The registry itself (`build_db.py`) is the one source that doesn't
follow this pattern — it's the foundation everything else joins
against, ingested once, not a "new source" in this sense.

## Stage 1: `<source>_ingest.py`

**Grain**: one row per `(uat_siruta, name_normalized)` — same as every
other source table and `streets_dedup`. If the raw source has
finer-grained records (OSM splits one street into many ways at every
junction; RENNS returns raw road segments), group and merge *inside the
ingest script*, before insert — see `osm_ingest.py`'s way-merging and
`renns_ingest.py`'s per-UAT grouping. Never leave grouping for query
time; `all_street_names` and every downstream query assume the table is
already at this grain.

**Required columns** (every `<source>_streets` table has all of these —
copy `postal_streets`'s or `renns_streets`'s `CREATE TABLE` in
`build_db.py` verbatim as a starting point):

```
id                 INTEGER PRIMARY KEY AUTOINCREMENT
uat_siruta         INTEGER              -- resolved SIRUTA; NULL if unresolved
name               TEXT NOT NULL        -- display name, type-prefix stripped
name_normalized    TEXT NOT NULL        -- normalize_match(name) — diacritic-folded
street_type        TEXT                 -- registry-convention type word, or NULL
title, rank        TEXT                 -- from extract_features()
is_saint, is_date, is_numeric   INTEGER DEFAULT 0
core_name          TEXT
core_name_norm     TEXT                 -- normalize_match(core_name) — THE join key
UNIQUE (uat_siruta, name_normalized)
```

Plus whatever source-specific provenance columns are useful for
debugging (`postal_streets.source_sheet`, `renns_streets.road_type_raw`
+ `road_status`, `osm_streets.way_ids`/`highway_class`/`length_m`) —
keep the raw/messy original value around even after cleaning it,
you'll need it the first time coverage looks wrong.

**Feature extraction — reuse, don't reinvent.** `street_type` /
`title` / `rank` / `is_saint` / `is_date` / `is_numeric` / `core_name`
all come from `streets_lib.extract_features(name)` — the same function
the registry's own ETL uses. `core_name_norm = normalize_match(core_name)`.
If the source's naming convention needs pre-processing before
`extract_features()` can handle it (see postal's trailing-title and
person-name-order issues below), do that transform *before* calling it,
keep it in the source's own `_ingest.py`, and feed the *transformed*
string only into feature extraction — never mutate the displayed `name`
field to match a convention that isn't what the source actually said.

**SIRUTA resolution — validate the mapping empirically, every source
has had a surprise here:**
- RENNS: `uat.id` *is* the registry's SIRUTA directly (verified 3180/3181
  exact match) — no fallback needed.
- Postal: two different mislabeled-column traps, found only by checking
  against the live DB, not by reading the source's documentation — a
  column literally named `SIRUTA` on one sheet matched 0/47 real SIRUTAs
  (it's an internal postal sub-code; the real code was in a
  *differently-named* column, `SIRSUP`); the `Bucuresti` sheet was the
  reverse. Assert the resolution column actually matches known SIRUTAs
  in the live DB before trusting it — don't assume the obviously-named
  column is the right one.
- OSM: resolved via `ref:RO:SIRUTA`/`ref:siruta`/`siruta` tags on
  `admin_level=8` boundary polygons, name-match fallback against
  `data/gis/populatie-romania-siruta-coords.csv` for the rest.
- Always keep a fallback name-match path (județ + locality name against
  the same coords CSV) for whatever fraction doesn't resolve directly,
  and track *how* each row resolved (`resolution_method` column) so a
  sanity pass can distinguish "confidently resolved" from "best guess."

**CLI conventions** (match every existing `_ingest.py`):
```
--db PATH            default data/streets.db
--rebuild             truncate the table before inserting (idempotent —
                      re-running without --rebuild UPSERTs, doesn't duplicate)
--dry-run             parse + report stats, write nothing
--uat-siruta N        single-UAT run, for fast iteration on a live/slow API
```

**Validate against the live API/file before committing to a crawl
design, not after.** RENNS's ingest design changed because of this: the
unfiltered "all roads" endpoint looked like the efficient path (67
requests for all of Romania vs. thousands of per-UAT calls) until a real
double-crawl showed 2.8% of rows had different ids between runs — the
dataset shifts under a paginated unfiltered crawl. The
per-`(county, UAT)` filtered endpoint, checked the same way (crawled
twice, byte-identical), was the one actually used. **Run the
boring/verbose crawl design and diff two real runs before trusting a
clever one.**

## Stage 2: `<source>_match.py`

Links source rows to registry rows (`streets_dedup`), *separate from*
the ingest step and *separate from* how `all_street_names` groups
things (see below — that view doesn't use this table at all). Purpose:
per-source coverage reporting (`docs/queries.sql`'s
`registry_<source>_gap`, `<source>_only_streets` queries) and,
historically, picking a "best" spelling — no longer used for that since
the 2026-07-08 decision that no source outranks another.

**3-tier match, same shape every time:**
```sql
-- Pass 1: exact_type_core, confidence 1.0
--   (siruta, street_type, core_name_norm) match, NULL-safe (`IS`, not `=`)
-- Pass 2: fuzzy_core_name, confidence 0.5
--   (siruta, core_name_norm) only — type differs or is missing either side
-- Pass 3 (postal only): reordered_core_name, confidence 0.4
--   core_name_norm_swapped (2-token reorder) — see the person-name-order
--   note below for why this is postal-specific
```
`INSERT OR IGNORE` into `street_<source>_matches (street_id, <source>_street_id,
match_type, confidence)`, one query per pass, in confidence order —
`OR IGNORE` means a pair already matched at higher confidence in an
earlier pass never gets overwritten by a lower-confidence later pass.

**Compare `(street_type, core_name_norm)` as two separate columns, never
compare raw `name_normalized` strings across sources.** OSM's
`name_normalized` includes the street-type prefix; the registry's,
postal's, and RENNS's don't. This was a real bug (Pass 1 was a 0.85%
no-op for OSM for months before being caught) — the type-aware rewrite
fixed it to 95.7%.

**Person names may be in "Surname Firstname" order.** Postal's `Denumire
artera` frequently is (`"Alecsandri Vasile"` vs. the registry's
`"Vasile Alecsandri"`) — hence Pass 3. RENNS and OSM haven't needed this
(their conventions already follow the registry's Firstname-Surname
order). **Don't assume a new source needs this pass — check a sample
first**, and don't build the reordering into Pass 3 blindly either:
`core_name_norm_swapped` only swaps *exactly* 2-token names, and even
then it's used only as a *match candidate* (low confidence, 0.4, never
auto-merged into the canonical spelling) — see the cross-source
consolidation section below for why blind reordering is actively unsafe
at the *identity* level, not just the matching level.

## Stage 3: `<source>_sanity.py`

Read-only, no dependencies beyond `sqlite3`. Two checks against the same
5 `REFERENCE_UATS` every sanity script uses (chosen to span scale — a
Bucharest sector, a big city, a mid town, a small town, a rural
commune):
```python
REFERENCE_UATS = [
    ("București (Sector 1)", 179141),
    ("Cluj-Napoca",           54975),
    ("Sibiu",                143450),
    ("Câmpulung Moldovenesc",146502),
    ("Cornu (rural, PH)",    132805),
]
```
1. Top-N by whatever the source's own quality signal is (OSM:
   `importance_v1`; postal/RENNS: just list them) — eyeball check that
   obvious main streets surface sensibly, not e.g. all-numeric noise at
   the top.
2. Per-UAT registry coverage (% of `streets_dedup` rows in that UAT with
   ≥1 match) — flag anything surprisingly low, then go find out *why*
   before assuming it's a source gap (see the Gorj/Tulcea note below: a
   low number is sometimes real sparse source coverage, not a bug).

A structural zero for some reference UATs is sometimes correct, not a
bug — RENNS has zero rows for all of București (confirmed, not a
crawl gap), postal only covers București + localities >50,000 population
by design (the source's own scope, not this pipeline's limitation).
Know your source's actual coverage boundary before treating a zero as
broken.

**Regional stratification is real, not always a bug.** OSM coverage
ranges from 17.7% (Gorj) to 87.3% (Tulcea) — investigated once and found
to be genuine sparse/incomplete mapping in Gorj's small villages, not a
naming-mismatch bug (mapper density varies by region, especially for
crowdsourced sources like OSM). Expect a new source to have its own
regional unevenness; investigate outliers before assuming the ingest is
broken.

## Stage 4: pick up in `all_street_names` (no new code needed)

`build_db.py`'s `all_street_names` view (search for `CREATE VIEW
all_street_names`) is a `UNION ALL` across `streets_dedup` +
`osm_streets` + `postal_streets` + `renns_streets`, grouped by
`(siruta, street_type, COALESCE(core_name_norm, name))`. **Adding a 5th
source means adding one more arm to that `UNION ALL`** — same 9 columns
(`source, siruta, street_type, name, core_name, core_name_norm,
is_saint, is_date, is_numeric`) as the other 3 arms, nothing else
changes. The grouping, `corroboration_count`, `variants` JSON,
`in_registry` flag, and `judet`/`uat` labeling (via `uat_reference`) all
apply automatically.

**This grouping is deliberately *not* fuzzy.** It groups on exact
`core_name_norm` equality — no type tolerance, no reordering, no
routing through the match tables' looser passes. Two entries sharing a
core name but disagreeing on `street_type` are *never* auto-merged (see
`type_variant_candidates` in `docs/queries.sql` for surfacing those for
manual review instead). **This is intentional and has already caught
one real bug**: a first design gave the registry arm a type-blind
fallback the other 3 arms didn't get (via the match tables), silently
granting it easier corroboration than any external-to-external pair —
fixed by making all 4 arms go through the exact same grouping, no
exceptions. Keep it that way for a 5th source: whatever grouping rule
applies to source #1 must apply identically to source #5.

**Never blindly reorder two-token names to "fix" apparent duplicates.**
A postal comma-suffix cleanup pass tried reordering every 2-token
"Surname Firstname" postal name to "Firstname Surname" — and corrupted
real data doing it: "Gala Galaction" is a pen name, not a reversed
surname/firstname pair, and "Petöfi Șándor" is Hungarian
family-name-first order, *already correct*. Both got silently flipped
to garbage. The fix: never reorder on a heuristic. Only reorder when the
reversed form is a *confirmed, already-curated* identity (see
`tools/resolve_reversed_person_duplicates.py`) — evidence, not a guess,
and scoped to `persons` only (reordering has no meaning for a nature
term or place name).

## After ingest: materialize + classify

- `python3 tools/materialize_all_street_names.py` — the live
  `all_street_names` view is an unindexed 4-way `UNION ALL`
  (~5-8x slower per query than `streets_dedup`), and has no
  diacritic-folded `name_normalized` column. This rebuilds it into an
  indexed `all_street_names_cache` table. Re-run any time a source is
  re-ingested; idempotent (drops and rebuilds every time). Not touched
  by `build_db.py` itself — it depends on tables `build_db.py` doesn't
  populate (they're separate tools, run after).
- A new source introduces brand-new `core_name_norm` keys the
  classification pipeline (`persons`/`nature_terms`/`name_categories`/
  `place_refs`) has never seen. **Before running `tools/llm_classify.py`
  on them, sample first** — a meaningful fraction may be resolvable for
  free rather than needing fresh LLM classification: known parsing
  artifacts (check for the source's own version of postal's
  comma-suffix titles), and reversed-name duplicates of already-curated
  persons (`tools/resolve_reversed_person_duplicates.py` is generic,
  re-run it as-is against any new source's new keys, not just postal's).
  `tools/export_unclassified.py` / `tools/llm_classify.py` both already
  query `all_street_names_cache`, not `streets_dedup` — a new source's
  keys are automatically in scope, no code change needed there either.

## Shipping: `tools/build_dist_db.py`

Materializes `all_street_names` (and `streets_all_sources`,
`streets_dedup`) into real tables in the *copy* at `dist/streets.db`,
drops every source table (`osm_streets`, `street_osm_matches`, ...,
`all_street_names_cache`) that the client-side filter UI doesn't need
directly. **A 5th source's raw table and match table go in the same
drop-list** (the `for tbl in (...)` loop) — the union's already been
materialized by the time that loop runs, so dropping the source table
is safe and keeps the shipped DB from carrying data twice.

## Checklist for source #5

1. Confirm the source's actual scope (nationwide? which UATs? which
   street types?) — don't assume, check.
2. Probe the raw API/file directly. If it's a live API, crawl-and-diff
   twice before committing to a crawl design.
3. `CREATE TABLE <source>_streets` — copy `postal_streets`'s /
   `renns_streets`'s shape, grain `(uat_siruta, name_normalized)`.
4. `tools/<source>_ingest.py` — SIRUTA resolution with an empirically-
   verified column, `--rebuild`/`--dry-run`/`--uat-siruta` flags,
   `extract_features()` reused (with a pre-processing step first if the
   source's naming convention needs it — check a sample before
   assuming reversed names or trailing titles, don't copy postal's
   fixes blind).
5. `tools/<source>_match.py` — 3-tier (or 2-tier, if no reorder need)
   pass, `(street_type, core_name_norm)` never raw `name_normalized`.
6. `tools/<source>_sanity.py` — same 5 `REFERENCE_UATS`, coverage +
   top-N eyeball.
7. Add one `UNION ALL` arm to `all_street_names` in `build_db.py` — same
   9 columns, same grouping key, no exceptions.
8. Add `<source>_streets` + `street_<source>_matches` to
   `build_dist_db.py`'s drop-list.
9. Re-run `tools/materialize_all_street_names.py`.
10. Sample the new `core_name_norm` keys before classifying — resolve
    what's free first (parsing artifacts, reversed-name duplicates),
    *then* `tools/llm_classify.py`.
11. New `docs/queries.sql` block: `registry_<source>_gap`,
    `<source>_only_streets`, `<source>_judet_coverage` (mirrors the
    existing postal/RENNS blocks).
12. Update `CLAUDE.md`'s critical rules if the new source breaks a new
    kind of assumption (as OSM/postal/RENNS each did), plus the repo
    layout + Common Commands sections either way.
13. `docs/activity-history.md` entry — what the source's own surprises
    were, empirically, not assumed.
