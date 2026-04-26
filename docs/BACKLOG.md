# Backlog

Items detected during sessions. Each entry has enough context to act on cold.

---

## P0 — Fix stale CLAUDE.md layout section

The `## Repository layout` and `## Common commands` sections in `CLAUDE.md` describe a different layout than what exists:
- Docs are in `docs/` (not root)
- DB lives at `data/streets.db` (not `streets.db` in root)
- Source xlsx is in `data/reference/` (not `data/source/`)
- `--limit N` flag already implemented (remove the "(P0 task in CODE_SPEC)" note)

---

## P1 — `communist_aliases` query missing DISTINCT

`docs/queries.sql` `:name communist_aliases` produces duplicate rows: same `(current_name, communist_alias, uat)` triplet repeated once per polling section. The query joins `streets` (not `streets_dedup`) and doesn't use `SELECT DISTINCT`. Fix: add `DISTINCT` or rewrite to join via `streets_dedup`.

---

## P1 — `unique_names` query polluted by numbered-street names

`:name unique_names` currently surfaces names like "1 1 Mai", "1 22 Decembrie 1989" from DJ — strings that parse as `is_numeric=0` (not purely numeric) but are really section-prefixed street numbers. Consider adding `WHERE is_numeric = 0 AND name NOT REGEXP '^\d'` or filtering in post-processing.

---

## P1 — Investigate DUMBRĂVIȚA (BV) near-zero entropy

`uat_diversity` shows DUMBRĂVIȚA BV with entropy 0.14 on 428 streets. That's essentially one name dominating a large UAT. Investigate what that name is and whether it's a data anomaly (e.g. a bulk registration of streets under a single name prefix).

```sql
SELECT name, COUNT(*) AS n FROM streets_dedup
WHERE uat = 'DUMBRĂVIȚA' AND judet = 'BV'
GROUP BY name_normalized ORDER BY n DESC LIMIT 10;
```

---

## P1 — Curation tooling (from CODE_SPEC P1)

- `tools/export_unclassified.py` — top-N unclassified `core_name_norm` ordered by frequency, with sample streets/UATs for context
- `tools/import_csv.py` — generic upserter for the 4 lookup tables
- `tools/wikidata_persons.py` — SPARQL query for top-N unmatched person candidates
- `tools/llm_classify.py` — Claude Haiku batch classifier (rate-limited, idempotent)
- Coverage view: `streets_classified_pct`

---

## P2 — Gender story needs curation before it can be told

Current seed has 1 woman (Elena Văcărescu) → 6 female streets vs 2,972 male. The real ratio is hidden behind the 83% unclassified mass. The gender gap is a headline finding for the publication but requires meaningful person-table coverage first. Priority curation target: female honorees in the top-500 unclassified names.

---

## P2 — `ORAŞ CERNAVODĂ` numeric streets named 1848 and 1933

`anonymous_uats` shows CERNAVODĂ CT with 5 "numeric" streets, lowest=1848, highest=1933. These are likely historical date references (year numbers) rather than true street numbers. The `is_numeric` flag catches them correctly (purely numeric), but the `anonymous_uats` query displays them alongside CIORANI's 1-218 run, which are different phenomena. Consider a sub-query that separates true sequence numbering (contiguous run starting at 1) from isolated year-numbers.

---

## P3 — `run_queries.py` output not machine-readable

The runner pretty-prints to stdout. When curation tooling or a dashboard pipeline needs query output, it'll need JSON/CSV mode. Add `--format json|csv|table` flag.
