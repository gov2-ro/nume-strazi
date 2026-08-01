#!/usr/bin/env python3
"""LLM-assisted classification of unclassified street name keys.

Provider access goes through tools/llm_layer.py (simonw/llm), which loads .env,
bridges key names to what the llm plugins expect, and falls back to a direct
OpenAI-compatible call for model ids the installed plugins predate:

  deepseek-*    →  DeepSeek    (DEEPSEEK_API_KEY)
  gemini-*      →  Google      (GOOGLE_API_KEY)
  claude-*      →  Anthropic   (ANTHROPIC_API_KEY)
  <org>/<model> →  OpenRouter  (OPENROUTER_API_KEY)

With no --model, the model comes from LLM_MODEL / LLM_model in .env.

Idempotent: re-running with the same --out file skips already-written keys, so
a long run can be interrupted and resumed, losing at most one in-flight batch.

Usage:
    python3 tools/llm_classify.py [--model MODEL] [--limit N]
    python3 tools/llm_classify.py --limit 0                    # whole backlog
    python3 tools/llm_classify.py --model gemini-2.5-flash-lite --limit 500
    python3 tools/llm_classify.py --dry-run
    python3 tools/llm_classify.py --limit 500 --import

Default --out is data/curation/llm_<model-slug>.csv so parallel runs with
different models land in separate files without extra flags.
"""
import argparse, csv, json, os, re, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

# Provider access goes through llm_layer (simonw/llm + key bridging + .env
# loading), so adding a provider is a registry entry there rather than another
# hand-rolled HTTP client here.
from llm_layer import complete_with_usage, resolve_model

# Append-only provenance log, one JSON object per batch. The CSV records what
# was decided; this records what it cost and which model decided it, so a run
# stays auditable after the terminal scrollback is gone.
RUN_LOG = Path("data/curation/llm_runs.jsonl")

DEFAULT_MODEL = None          # None → llm_layer picks from LLM_MODEL/.env
BATCH_SIZE    = 20
SLEEP_S       = 1.0
# Headroom for reasoning models: they bill thinking against max_tokens and can
# spend the entire budget before emitting any content. deepseek-v4-flash used
# ~14k reasoning tokens on a 20-key batch, so 4096 returned an empty string that
# looked exactly like a malformed reply. Harmless for non-reasoning models —
# it is a ceiling, not an allocation.
MAX_TOKENS    = 16384

HEADER = [
    "core_name_norm", "freq", "judete_n", "uats_n", "sample_name", "judete_list",
    "table",
    "full_name", "gender", "birth_year", "death_year", "era", "profession",
    "nationality", "wikidata_qid",
    "term", "nature_type",
    "category", "subcategory",
    "place_name", "place_type", "country",
    "notes",
]

SYSTEM = """You classify Romanian street name roots for a national street-name database.

Each input entry:
  "key"    – core_name_norm (ASCII-normalised Romanian, street-type/rank prefix stripped)
  "sample" – full display name of one real street using this key (context only)
  "freq"   – count of deduped streets nationwide with this name
  "judete" – counties where it appears (2-letter RO codes)

Respond with a JSON array, one object per input entry, same order. Each object:
  { "key": "<exactly as given>", "table": "<target>", ...fields... }

table values and required fields:

  persons        → full_name (str), gender ("M"/"F"/"collective"),
                   birth_year (int|null), death_year (int|null),
                   era ("ancient"|"medieval"|"premodern"|"1848"|"interwar"|"communist"),
                   profession (str), nationality (ISO-2 str|null)
                   Era guide: ancient=pre-500AD, medieval=500-1700, premodern=1700-1900,
                   1848=1848-revolution figures, interwar=1900-1947, communist=1947-1989

  nature_terms   → term (Romanian display form), nature_type (str)
                   nature_type: tree, flower, plant, fruit, bird, animal, water,
                                geography, forest, meadow, season, sky, weather

  name_categories → category (str), subcategory (str)
                   category: religious, ideological, abstract, institutional, trade,
                             occupational, commemorative, mythology, infrastructure

  place_refs     → place_name (Romanian display form), place_type (str), country (ISO-2|null)
                   place_type: river, mountain, mountain_peak, region, ro_city, ro_village,
                               ro_monastery, resort, ancient_city, ancient_region,
                               city, battle_site

  skip           → use when genuinely ambiguous or too obscure to classify with confidence

Return ONLY the JSON array, no prose."""

# Sources from all_street_names_cache (all 4 sources: registry, OSM, postal,
# RENNS), not electoral_dedup (electoral-only) -- see tools/materialize_all_street_names.py
# and docs/BACKLOG.md's "Make all_street_names the dashboard's main corpus"
# entry. Registry-only classification is a strict subset of this.
UNCLASSIFIED_SQL = """
WITH curated AS (
  SELECT core_name_norm FROM persons         UNION
  SELECT core_name_norm FROM nature_terms    UNION
  SELECT core_name_norm FROM name_categories UNION
  SELECT core_name_norm FROM place_refs
)
SELECT
  s.core_name_norm,
  COUNT(*)                        AS freq,
  COUNT(DISTINCT s.judet)         AS judete_n,
  COUNT(DISTINCT s.uat)           AS uats_n,
  MIN(s.name)                     AS sample_name,
  GROUP_CONCAT(DISTINCT s.judet)  AS judete_list
FROM all_street_names_cache s
WHERE s.core_name_norm IS NOT NULL
  AND s.is_numeric = 0
  AND s.is_date    = 0
  AND s.is_saint   = 0
  AND s.core_name_norm NOT IN (SELECT core_name_norm FROM curated)
GROUP BY s.core_name_norm
ORDER BY freq DESC
LIMIT ?
"""


# ── model naming ──────────────────────────────────────────────────────────────

def model_slug(model: str) -> str:
    slug = model.split("/")[-1]
    slug = re.sub(r"-\d{8}$", "", slug)          # strip YYYYMMDD date suffix
    return re.sub(r"[^a-z0-9.-]", "-", slug.lower())[:40]


# ── API call ──────────────────────────────────────────────────────────────────

def _parse_text(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def call_llm(model: str, entries: list,
             max_tokens: int = MAX_TOKENS) -> tuple[list, dict]:
    """One batch → (parsed JSON array, token usage).

    Provider routing, key bridging and the direct-HTTP fallback for model ids
    the installed llm plugins don't know all live in llm_layer.
    """
    text, usage = complete_with_usage(
        system=SYSTEM,
        user=json.dumps(entries, ensure_ascii=False),
        model=model,
        max_tokens=max_tokens,
        temperature=0,
    )
    return _parse_text(text), usage


# ── row helpers ───────────────────────────────────────────────────────────────

def empty_row(cnorm, freq, jn, un, sample, jlist):
    r = {h: "" for h in HEADER}
    r.update(core_name_norm=cnorm, freq=freq, judete_n=jn,
             uats_n=un, sample_name=sample, judete_list=jlist)
    return r


def apply(row, cls):
    t = cls.get("table", "skip")
    if t == "skip":
        return row
    row["table"] = t
    if t == "persons":
        for f in ("full_name", "gender", "birth_year", "death_year",
                  "era", "profession", "nationality"):
            row[f] = cls.get(f) or ""
    elif t == "nature_terms":
        row["term"]        = cls.get("term") or ""
        row["nature_type"] = cls.get("nature_type") or ""
    elif t == "name_categories":
        row["category"]    = cls.get("category") or ""
        row["subcategory"] = cls.get("subcategory") or ""
    elif t == "place_refs":
        row["place_name"]  = cls.get("place_name") or ""
        row["place_type"]  = cls.get("place_type") or ""
        row["country"]     = cls.get("country") or ""
    return row


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model",      default=DEFAULT_MODEL,
                    help="Model to use; provider auto-detected (default: %(default)s)")
    ap.add_argument("--db",         default="data/streets.db")
    ap.add_argument("--limit",      type=int, default=200,
                    help="Max keys to classify this run (0 = all, default: %(default)s)")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--max-consecutive-errors", type=int, default=5,
                    help="Abort after this many failing batches in a row (default: %(default)s)")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS,
                    help="Output ceiling; reasoning models need slack (default: %(default)s)")
    ap.add_argument("--sleep",      type=float, default=SLEEP_S,
                    help="Seconds to sleep between batches (default: %(default)s)")
    ap.add_argument("--out",        default=None,
                    help="Output CSV (default: data/curation/llm_<model-slug>.csv)")
    ap.add_argument("--import",     dest="do_import", action="store_true",
                    help="Run import_csv.py on the output file when done")
    ap.add_argument("--dry-run",    action="store_true",
                    help="Print first batch; make no API calls")
    args = ap.parse_args()

    # Resolve here rather than inside the batch loop: the CSV name is derived
    # from the model id, so it has to be the concrete one, not None.
    provider, model, api_key = resolve_model(args.model)
    slug     = model_slug(model)
    out_path = Path(args.out) if args.out else Path(f"data/curation/llm_{slug}.csv")

    print(f"Model: {model}  provider: {provider}  "
          f"key: {'set' if api_key else 'MISSING'}  out: {out_path}")

    # Keys already written (resume support)
    processed: set[str] = set()
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                processed.add(row["core_name_norm"])
        print(f"Resuming: {len(processed)} keys already in {out_path.name}")

    no_limit = args.limit == 0
    fetch_n  = 999_999 if no_limit else args.limit + len(processed)
    con      = sqlite3.connect(args.db)
    all_rows = con.execute(UNCLASSIFIED_SQL, (fetch_n,)).fetchall()
    con.close()

    candidates = [r for r in all_rows if r[0] not in processed]
    if not no_limit:
        candidates = candidates[: args.limit]

    if not candidates:
        print("Nothing to classify.")
        return
    print(f"Keys to classify: {len(candidates)}")

    if args.dry_run:
        batch = candidates[: args.batch_size]
        print(f"[dry-run] First batch ({len(batch)} keys):")
        for r in batch:
            print(f"  {r[0]:<35}  freq={r[1]:>4}  sample={r[4]}")
        return

    is_new = not out_path.exists()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_classified = n_skipped = n_errors = 0
    run_id  = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    totals  = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
               "cached_tokens": 0}
    cost_usd, cost_known, t_start = 0.0, True, time.time()
    consecutive_errors = 0
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(RUN_LOG, "a", encoding="utf-8")

    def log(event: str, **fields) -> None:
        log_f.write(json.dumps(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "run_id": run_id, "event": event, "model": model,
             "provider": provider, "out": str(out_path), **fields},
            ensure_ascii=False) + "\n")
        log_f.flush()

    log("run_start", batch_size=args.batch_size, max_tokens=args.max_tokens,
        candidates=len(candidates), db=args.db, resumed_from=len(processed))

    with open(out_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        if is_new:
            writer.writeheader()

        for i in range(0, len(candidates), args.batch_size):
            batch_rows = candidates[i : i + args.batch_size]
            batch_no   = i // args.batch_size + 1
            entries    = [{"key": r[0], "sample": r[4], "freq": r[1], "judete": r[5]}
                          for r in batch_rows]
            lookup     = {r[0]: r for r in batch_rows}

            print(f"Batch {batch_no:>3}  [{i+1:>4}–{i+len(batch_rows):>4}]  … ", end="", flush=True)
            t0 = time.time()
            try:
                results, usage = call_llm(model, entries, args.max_tokens)
            except Exception as e:
                print(f"ERROR: {e}")
                n_errors += len(batch_rows)
                log("batch_error", batch=batch_no, keys=len(batch_rows),
                    seconds=round(time.time() - t0, 2), error=str(e)[:300],
                    first_key=batch_rows[0][0])
                # A misspelled model name returns 400 on every batch, forever. On
                # 2026-08-01 one such run churned through 1,271 consecutive
                # failures over 11 minutes before the backlog ran out. Nothing
                # recoverable looks like this: stop and let the operator fix it.
                consecutive_errors += 1
                if consecutive_errors >= args.max_consecutive_errors:
                    print(f"\nABORTING: {consecutive_errors} batches failed in a "
                          f"row without a single success. The cause is almost "
                          f"certainly configuration (model name, key, quota), not "
                          f"the data — fix it and re-run; work already in "
                          f"{out_path.name} is kept and will be skipped.")
                    log("run_abort", reason="consecutive_errors",
                        consecutive_errors=consecutive_errors, batch=batch_no)
                    break
                continue
            consecutive_errors = 0

            for k in totals:
                totals[k] += usage.get(k) or 0
            batch_cost = usage.get("estimated_cost_usd")
            if batch_cost is None:
                cost_known = False          # unpriced model: don't fake a total
            else:
                cost_usd += batch_cost

            b_cls = b_skip = 0
            for cls in results:
                key = cls.get("key", "")
                if key not in lookup:
                    continue
                row = apply(empty_row(*lookup[key]), cls)
                writer.writerow(row)
                if cls.get("table", "skip") != "skip":
                    b_cls        += 1
                    n_classified += 1
                else:
                    b_skip   += 1
                    n_skipped += 1

            f.flush()
            cost_note = f"  ${batch_cost:.4f}" if batch_cost is not None else ""
            print(f"{b_cls} classified, {b_skip} skipped{cost_note}")
            log("batch", batch=batch_no, keys=len(batch_rows),
                classified=b_cls, skipped=b_skip,
                seconds=round(time.time() - t0, 2),
                first_key=batch_rows[0][0], **usage)

            if i + args.batch_size < len(candidates):
                time.sleep(args.sleep)

    elapsed = time.time() - t_start
    done = n_classified + n_skipped
    print(f"\nDone — classified: {n_classified}, skipped: {n_skipped}, errors: {n_errors}")
    print(f"Tokens: {totals['input_tokens']:,} in "
          f"({totals['cached_tokens']:,} cached) / {totals['output_tokens']:,} out"
          + (f" / {totals['reasoning_tokens']:,} reasoning"
             if totals["reasoning_tokens"] else ""))
    if cost_known:
        per_1k = f"  (${cost_usd / done * 1000:.2f} per 1k keys)" if done else ""
        print(f"Estimated cost: ${cost_usd:.4f}{per_1k}   — estimate from "
              f"llm_layer.PRICING, not a provider invoice")
    else:
        print("Estimated cost: unavailable (model not in llm_layer.PRICING); "
              "token counts above are exact")
    print(f"Elapsed: {elapsed/60:.1f} min"
          + (f"  ({elapsed/done:.2f} s/key)" if done else ""))
    print(f"Output: {out_path}")
    print(f"Run log: {RUN_LOG}  (run_id {run_id})")

    log("run_end", classified=n_classified, skipped=n_skipped, errors=n_errors,
        seconds=round(elapsed, 1),
        estimated_cost_usd=round(cost_usd, 6) if cost_known else None, **totals)
    log_f.close()

    if n_classified and args.do_import:
        print("Importing …")
        result = subprocess.run(
            ["python3", "tools/import_csv.py", str(out_path), "--db", args.db],
            capture_output=True, text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print("Import errors:", result.stderr)
            sys.exit(1)
    elif n_classified:
        print(f"Import with:  python3 tools/import_csv.py {out_path}")


if __name__ == "__main__":
    main()
