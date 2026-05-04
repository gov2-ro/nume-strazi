"""LLM-assisted classification of unclassified street name keys using Claude Haiku.

Queries the DB for the top-N unclassified core_name_norm keys, sends them in
batches to Claude Haiku for classification, and appends results to a CSV that
tools/import_csv.py can consume.

Idempotent: re-running with the same --out file skips already-written keys.

Usage:
    python3 tools/llm_classify.py --limit 500
    python3 tools/llm_classify.py --limit 500 --dry-run
    python3 tools/llm_classify.py --limit 500 --out data/curation/llm_batch1.csv --import
"""
import argparse, csv, json, sqlite3, subprocess, sys, time
from pathlib import Path
import anthropic

MODEL      = "claude-haiku-4-5-20251001"
BATCH_SIZE = 20
SLEEP_S    = 1.0  # between batches

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
FROM streets_dedup s
WHERE s.core_name_norm IS NOT NULL
  AND s.is_numeric = 0
  AND s.is_date    = 0
  AND s.is_saint   = 0
  AND s.core_name_norm NOT IN (SELECT core_name_norm FROM curated)
GROUP BY s.core_name_norm
ORDER BY freq DESC
LIMIT ?
"""


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


def call_api(client, entries):
    msg = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(entries, ensure_ascii=False)}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",         default="data/streets.db")
    ap.add_argument("--limit",      type=int, default=200,
                    help="max keys to classify this run (0 = all)")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--out",        default="data/curation/llm_batch.csv")
    ap.add_argument("--import",     dest="do_import", action="store_true",
                    help="run import_csv.py on the output file when done")
    ap.add_argument("--dry-run",    action="store_true",
                    help="print first batch; make no API calls")
    args = ap.parse_args()

    out_path = Path(args.out)

    # Keys already written to the output file (resume support)
    processed: set[str] = set()
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                processed.add(row["core_name_norm"])
        print(f"Resuming: {len(processed)} keys already in {out_path.name}")

    # Fetch unclassified candidates from DB (fetch extra to cover processed overlap)
    # limit=0 means "all" — use a sentinel large enough to fetch everything
    no_limit = args.limit == 0
    fetch_n = 999_999 if no_limit else args.limit + len(processed)
    con = sqlite3.connect(args.db)
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

    client  = anthropic.Anthropic()
    is_new  = not out_path.exists()
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
                results = call_api(client, entries)
            except Exception as e:
                print(f"ERROR: {e}")
                n_errors += len(batch_rows)
                continue

            b_cls = b_skip = 0
            for cls in results:
                key = cls.get("key", "")
                if key not in lookup:
                    continue
                r   = lookup[key]
                row = apply(empty_row(*r), cls)
                writer.writerow(row)
                if cls.get("table", "skip") != "skip":
                    b_cls      += 1
                    n_classified += 1
                else:
                    b_skip  += 1
                    n_skipped += 1

            print(f"{b_cls} classified, {b_skip} skipped")
            if i + args.batch_size < len(candidates):
                time.sleep(SLEEP_S)

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
