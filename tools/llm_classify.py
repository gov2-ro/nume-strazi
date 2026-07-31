#!/usr/bin/env python3
"""LLM-assisted classification of unclassified street name keys.

Supports three providers; auto-detected from the model name:
  claude-*      →  Anthropic   (ANTHROPIC_API_KEY)
  gemini-*      →  Google      (GOOGLE_API_KEY)
  <org>/<model> →  OpenRouter  (OPENROUTER_API_KEY)

Idempotent: re-running with the same --out file skips already-written keys.

Usage:
    python3 tools/llm_classify.py [--model MODEL] [--limit N]
    python3 tools/llm_classify.py --model gemini-2.0-flash-lite --limit 500
    python3 tools/llm_classify.py --model google/gemini-flash-1.5-8b --limit 500
    python3 tools/llm_classify.py --dry-run
    python3 tools/llm_classify.py --limit 500 --import

Default --out is data/curation/llm_<model-slug>.csv so parallel runs with
different models land in separate files without extra flags.
"""
import argparse, csv, json, os, re, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE    = 20
SLEEP_S       = 1.0

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


# ── provider detection ────────────────────────────────────────────────────────

def detect_provider(model: str) -> str:
    if "/" in model:
        return "openrouter"
    if model.startswith("gemini"):
        return "google"
    if model.startswith("claude"):
        return "anthropic"
    raise ValueError(
        f"Cannot auto-detect provider for '{model}'. "
        "Use 'claude-*' (Anthropic), 'gemini-*' (Google), or 'org/model' (OpenRouter)."
    )


def model_slug(model: str) -> str:
    slug = model.split("/")[-1]
    slug = re.sub(r"-\d{8}$", "", slug)          # strip YYYYMMDD date suffix
    return re.sub(r"[^a-z0-9.-]", "-", slug.lower())[:40]


# ── API calls ─────────────────────────────────────────────────────────────────

def _parse_text(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def _call_anthropic(model: str, entries: list) -> list:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model, max_tokens=4096, system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(entries, ensure_ascii=False)}],
    )
    return _parse_text(msg.content[0].text)


def _call_google(model: str, entries: list) -> list:
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY environment variable not set")

    body = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(entries, ensure_ascii=False)}]}],
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0},
    }, ensure_ascii=False).encode()

    url = (f"https://generativelanguage.googleapis.com/v1beta"
           f"/models/{model}:generateContent?key={key}")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Google API error {e.code}: {e.read().decode()[:200]}")

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Google returned no candidates (safety filter?): {data}")

    return _parse_text(candidates[0]["content"]["parts"][0]["text"])


def _call_openrouter(model: str, entries: list) -> list:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable not set")

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(entries, ensure_ascii=False)},
        ],
        "max_tokens": 4096,
        "temperature": 0,
    }, ensure_ascii=False).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter error {e.code}: {e.read().decode()[:200]}")

    return _parse_text(data["choices"][0]["message"]["content"])


def call_llm(model: str, provider: str, entries: list) -> list:
    if provider == "anthropic":
        return _call_anthropic(model, entries)
    if provider == "google":
        return _call_google(model, entries)
    if provider == "openrouter":
        return _call_openrouter(model, entries)
    raise ValueError(f"Unknown provider: {provider}")


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
    ap.add_argument("--sleep",      type=float, default=SLEEP_S,
                    help="Seconds to sleep between batches (default: %(default)s)")
    ap.add_argument("--out",        default=None,
                    help="Output CSV (default: data/curation/llm_<model-slug>.csv)")
    ap.add_argument("--import",     dest="do_import", action="store_true",
                    help="Run import_csv.py on the output file when done")
    ap.add_argument("--dry-run",    action="store_true",
                    help="Print first batch; make no API calls")
    args = ap.parse_args()

    provider = detect_provider(args.model)
    slug     = model_slug(args.model)
    out_path = Path(args.out) if args.out else Path(f"data/curation/llm_{slug}.csv")

    print(f"Model: {args.model}  provider: {provider}  out: {out_path}")

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
            try:
                results = call_llm(args.model, provider, entries)
            except Exception as e:
                print(f"ERROR: {e}")
                n_errors += len(batch_rows)
                continue

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
            print(f"{b_cls} classified, {b_skip} skipped")

            if i + args.batch_size < len(candidates):
                time.sleep(args.sleep)

    print(f"\nDone — classified: {n_classified}, skipped: {n_skipped}, errors: {n_errors}")
    print(f"Output: {out_path}")

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
