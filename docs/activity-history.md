# Activity History

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
