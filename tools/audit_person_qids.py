"""Audit `persons.wikidata_qid` against Wikidata: is each QID actually a human?

Motivation: `mihail eminescu` was bound to Q169930 ("Extended play", a music
release format) while `mihai eminescu` correctly pointed at Q184935. Both rows
carried full_name "Mihai Eminescu", so nothing downstream noticed — but any
identity grouping keyed on QID silently splits the poet in two, and any
Wikidata-derived enrichment (sitelinks, birthplace, cause of death) pulled
nonsense for the bad key.

Checks each QID with `wbgetentities` (50 per request, the API maximum) and flags:
  - not_human      P31 has no Q5 → almost certainly a mis-resolution
  - missing        QID does not resolve at all
  - redirected     QID silently redirects to another entity
  - label_mismatch entity label shares no token with persons.full_name

Read-only by default. `--fix-not-human` clears the flagged QIDs (and the
Wikidata-derived columns that were populated from them), leaving full_name and
the hand-curated biographical fields untouched, so the key stays classified and
merely loses its bogus Wikidata link.

Durability: the corrected DB alone is not enough. `tools/restore_curation.py`
replays `data/curation/wikidata_qids.csv` after every rebuild, so a rejected QID
left in that file comes straight back. Pass --sync-replay-csv to realign it.

Usage:
  python3 tools/audit_person_qids.py                       # report only
  python3 tools/audit_person_qids.py --csv data/curation/qid_audit.csv
  python3 tools/audit_person_qids.py --fix-not-human --reresolve --sync-replay-csv
  python3 tools/audit_person_qids.py --sync-replay-csv     # realign CSV, no API calls
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://www.wikidata.org/w/api.php"
UA = "nume-strazi/1.0 (street-name research; contact via repo)"
BATCH = 50
HUMAN = "Q5"

# Wikidata-derived columns; cleared alongside a QID we reject.
DERIVED_COLUMNS = [
    "wiki_sitelinks", "wiki_scope", "wiki_ro_url", "wiki_en_url", "wiki_ro_views",
    "birth_place_qid", "birth_place_label", "birth_judet",
    "cause_of_death_qid", "cause_of_death_label",
]


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--csv", default=None, help="Write the full report to CSV.")
    ap.add_argument("--fix-not-human", action="store_true",
                    help="Clear QIDs (and derived columns) flagged not_human/missing.")
    ap.add_argument("--reresolve", action="store_true",
                    help="With --fix-not-human: re-search each cleared key using the "
                         "P31-verified resolver and write back any human match.")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="Seconds between API calls (Wikidata 429s below ~1s).")
    ap.add_argument("--sync-replay-csv",
                    nargs="?", const="data/curation/wikidata_qids.csv", default=None,
                    metavar="PATH",
                    help="Rewrite the wikidata_persons.py --replay-csv audit trail "
                         "from the DB's current (verified) QIDs. Without this, a "
                         "rebuild + restore_curation.py replays the OLD bogus QIDs "
                         "straight back in.")
    return ap.parse_args()


def sync_replay_csv(con: sqlite3.Connection, path: Path) -> None:
    """Rewrite the replay audit trail to match the DB.

    `tools/restore_curation.py` replays this file after every rebuild, so a
    corrected DB alone is not durable — the CSV is what survives `build_db.py`.
    Keys whose QID was cleared and not re-resolved are written with an empty
    QID and auto_match=False so replay leaves them unset rather than restoring
    a rejected value.
    """
    rows = con.execute("""
        SELECT core_name_norm, full_name, wikidata_qid
        FROM persons ORDER BY core_name_norm
    """).fetchall()

    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing[r["core_name_norm"]] = r

    out_rows, changed, cleared = [], 0, 0
    for r in rows:
        core, full_name, qid = r["core_name_norm"], r["full_name"], r["wikidata_qid"]
        prev = existing.get(core)
        if prev is None and not qid:
            continue  # never had one, still doesn't — nothing to record
        if prev and prev.get("wikidata_qid") != (qid or ""):
            changed += 1
            if not qid:
                cleared += 1
        out_rows.append({
            "core_name_norm": core,
            "full_name": full_name,
            "wikidata_qid": qid or "",
            "confidence": (prev or {}).get("confidence", "" if not qid else "0.95"),
            "auto_match": bool(qid),
        })

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["core_name_norm", "full_name",
                                          "wikidata_qid", "confidence", "auto_match"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nSynced {path}: {len(out_rows)} rows, {changed} changed "
          f"({cleared} now blank). restore_curation.py will replay these.")


def _norm(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {t for t in "".join(c if c.isalnum() else " " for c in s).split() if len(t) > 2}


def fetch(qids: list[str]) -> dict:
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "claims|labels|info",
        "languages": "ro|en",
        "format": "json",
    }
    req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    args = parse_args()
    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found: {db}")

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row

    # Standalone mode: no API traffic, just realign the replay trail with the DB.
    if args.sync_replay_csv and not (args.fix_not_human or args.reresolve):
        sync_replay_csv(con, Path(args.sync_replay_csv))
        con.close()
        return

    rows = con.execute("""
        SELECT core_name_norm, full_name, wikidata_qid
        FROM persons WHERE wikidata_qid IS NOT NULL AND wikidata_qid <> ''
        ORDER BY core_name_norm
    """).fetchall()
    print(f"Auditing {len(rows):,} QIDs across {len(rows)} persons keys…")

    by_qid: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_qid.setdefault(r["wikidata_qid"], []).append(r)

    qids = sorted(by_qid)
    entities: dict[str, dict] = {}
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        try:
            data = fetch(chunk)
        except Exception as exc:
            print(f"  ! batch {i // BATCH + 1} failed: {exc}", file=sys.stderr)
            continue
        entities.update(data.get("entities", {}))
        print(f"  … {min(i + BATCH, len(qids)):,}/{len(qids):,}", flush=True)
        time.sleep(args.sleep)

    report = []
    for qid in qids:
        ent = entities.get(qid) or {}
        keys = by_qid[qid]
        names = ", ".join(sorted({k["full_name"] for k in keys}))

        if "missing" in ent or not ent:
            report.append((qid, names, "missing", "", ""))
            continue

        label = ((ent.get("labels", {}).get("ro")
                  or ent.get("labels", {}).get("en") or {}).get("value", ""))
        p31 = [c["mainsnak"]["datavalue"]["value"]["id"]
               for c in ent.get("claims", {}).get("P31", [])
               if c.get("mainsnak", {}).get("datavalue")]

        if ent.get("id") and ent["id"] != qid:
            report.append((qid, names, "redirected", label, f"→ {ent['id']}"))
        elif HUMAN not in p31:
            report.append((qid, names, "not_human", label, ",".join(p31[:4])))
        elif not (_norm(label) & _norm(names)):
            report.append((qid, names, "label_mismatch", label, ""))

    verdicts = {}
    for _, _, v, _, _ in report:
        verdicts[v] = verdicts.get(v, 0) + 1

    print(f"\n=== {len(report)} flagged of {len(qids)} QIDs ===")
    for v, n in sorted(verdicts.items(), key=lambda x: -x[1]):
        print(f"  {v:16} {n}")

    if report:
        print("\nqid          verdict         entity label / detail        curated as")
        print("-" * 92)
        for qid, names, verdict, label, detail in sorted(report, key=lambda x: x[2]):
            print(f"  {qid:<11} {verdict:<15} {(label or '?')[:26]:<26} "
                  f"{detail[:14]:<14} {names[:30]}")

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["wikidata_qid", "curated_full_name", "verdict",
                        "entity_label", "detail", "core_name_norms"])
            for qid, names, verdict, label, detail in report:
                w.writerow([qid, names, verdict, label, detail,
                            " | ".join(k["core_name_norm"] for k in by_qid[qid])])
        print(f"\nWrote {out}")

    if args.fix_not_human:
        bad = [q for q, _, v, _, _ in report if v in ("not_human", "missing")]
        if not bad:
            print("\nNothing to fix.")
            con.close()
            return

        cleared_keys = [(k["core_name_norm"], k["full_name"])
                        for q in bad for k in by_qid[q]]
        sets = ", ".join(f"{c} = NULL" for c in DERIVED_COLUMNS)
        con.executemany(
            f"UPDATE persons SET wikidata_qid = NULL, {sets} WHERE wikidata_qid = ?",
            [(q,) for q in bad],
        )
        con.commit()
        print(f"\nCleared {len(bad)} bogus QIDs across {len(cleared_keys)} keys "
              f"(+ {len(DERIVED_COLUMNS)} derived columns each). "
              "full_name and hand-curated biography kept.")

        if args.reresolve:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from wikidata_persons import search_wikidata

            print(f"\nRe-resolving {len(cleared_keys)} keys with the "
                  f"P31-verified resolver…")
            fixed = still_missing = 0
            for core, full_name in cleared_keys:
                row = con.execute(
                    "SELECT gender, birth_year, death_year FROM persons "
                    "WHERE core_name_norm = ?", (core,)).fetchone()
                try:
                    match = search_wikidata(full_name, row["gender"],
                                            row["birth_year"], row["death_year"])
                except Exception as exc:
                    print(f"  {full_name:34} ERROR {exc}")
                    time.sleep(args.sleep * 3)
                    continue
                if match:
                    qid, conf = match
                    con.execute(
                        "UPDATE persons SET wikidata_qid = ? WHERE core_name_norm = ?",
                        (qid, core))
                    # Commit per row: this loop runs for tens of minutes against a
                    # rate-limited API, and a single transaction spanning it would
                    # hold SQLite's write lock the whole time, blocking every other
                    # tool in the pipeline.
                    con.commit()
                    fixed += 1
                    print(f"  {full_name:34} → {qid}  (conf {conf:.2f})", flush=True)
                else:
                    still_missing += 1
                    print(f"  {full_name:34} → no human match", flush=True)
                time.sleep(args.sleep)
            print(f"\nRe-resolved {fixed}; {still_missing} left without a QID.")

        if args.sync_replay_csv:
            sync_replay_csv(con, Path(args.sync_replay_csv))
    con.close()


if __name__ == "__main__":
    main()
