#!/usr/bin/env python3
"""
Resolve birth place (Wikidata P19) for honorees with QIDs, then walk the
P131 (located in admin entity) chain to land them in a Romanian județ when
possible. Persists to persons.birth_place_qid / birth_place_label / birth_judet.

CSV audit trail at data/curation/wikidata_birthplaces.csv. Run with --replay-csv
to restore after build_db.py wipes the persons table.

Honorees born outside present-day Romania (Chișinău, Cernăuți, Paris, Vienna…)
keep birth_place_qid and label, but birth_judet is left NULL — they drop out of
the self-honor numerator automatically.

Usage:
    python3 tools/wiki_birthplace.py [--limit N] [--dry-run]
    python3 tools/wiki_birthplace.py --replay-csv [--force]
"""

import sqlite3, sys, argparse, json, csv, urllib.request, urllib.parse, time
from pathlib import Path

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
BATCH_SIZE   = 50
UA           = "RomanianStreetsAnalysis/1.0 (https://github.com/; alex.popescu@gmail.com)"
CSV_PATH     = Path("data/curation/wikidata_birthplaces.csv")
CSV_FIELDS   = ["core_name_norm", "full_name", "wikidata_qid",
                "birth_place_qid", "birth_place_label", "birth_judet"]

# Wikidata QIDs that identify a Romanian county entity. Accept either:
#   Q1776764 — "county of Romania" (modern usage)
#   Q15947   — older / alternate typing still attached to a few entries
JUDET_TYPE_QIDS = {"Q1776764", "Q15947"}
# București is administratively its own entity, registry code 'B'.
BUCHAREST_QID  = "Q19660"

# Maps the Romanian/English label returned by Wikidata to the 2-char registry code.
LABEL_TO_CODE = {
    "Alba": "AB", "Arad": "AR", "Argeș": "AG", "Bacău": "BC",
    "Bihor": "BH", "Bistrița-Năsăud": "BN", "Botoșani": "BT",
    "Brașov": "BV", "Brăila": "BR", "Buzău": "BZ",
    "Caraș-Severin": "CS", "Cluj": "CJ", "Constanța": "CT",
    "Covasna": "CV", "Călărași": "CL", "Dâmbovița": "DB", "Dolj": "DJ",
    "Galați": "GL", "Giurgiu": "GR", "Gorj": "GJ", "Harghita": "HR",
    "Hunedoara": "HD", "Ialomița": "IL", "Iași": "IS", "Ilfov": "IF",
    "Maramureș": "MM", "Mehedinți": "MH", "Mureș": "MS", "Neamț": "NT",
    "Olt": "OT", "Prahova": "PH", "Sălaj": "SJ", "Satu Mare": "SM",
    "Sibiu": "SB", "Suceava": "SV", "Teleorman": "TR", "Timiș": "TM",
    "Tulcea": "TL", "Vâlcea": "VL", "Vaslui": "VS", "Vrancea": "VN",
}


def http_json(url, accept=None, max_retries=4):
    """GET + parse JSON, with exponential backoff on 429."""
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    delay = 2
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                retry_after = int(e.headers.get("Retry-After") or delay)
                wait = max(retry_after, delay)
                print(f"  ⏳ 429 — sleeping {wait}s (attempt {attempt+1}/{max_retries})",
                      file=sys.stderr)
                time.sleep(wait)
                delay *= 2
                continue
            raise


def judet_code_for(entity) -> str | None:
    """
    Determine if a Wikidata entity is a Romanian județ (or Bucharest itself).
    Returns the 2-char registry code, or None.

    Detection: P31 must include Q15947 (județ of Romania) AND the ro/en label
    must match a known county name (with or without "Județul" prefix). Bucharest
    is detected by QID directly since it is a "municipality" entity, not a județ.
    """
    # Bucharest special case: matches by entity identity.
    if entity.get("id") == BUCHAREST_QID:
        return "B"

    p31s = claim_targets(entity, "P31")
    if not (set(p31s) & JUDET_TYPE_QIDS):
        return None

    labels = entity.get("labels", {})
    for lang in ("ro", "en"):
        label = labels.get(lang, {}).get("value", "")
        if not label:
            continue
        for prefix in ("Județul ", ""):
            if label.startswith(prefix):
                bare = label[len(prefix):]
                bare = bare.removesuffix(" County")  # English label form
                if bare in LABEL_TO_CODE:
                    return LABEL_TO_CODE[bare]
    return None


def fetch_entities(qids, props):
    """Batch wbgetentities. Returns {qid: entity_dict}. Empty dict on error."""
    params = {
        "action": "wbgetentities",
        "ids":    "|".join(qids),
        "format": "json",
        "props":  props,
    }
    try:
        data = http_json(f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}")
    except Exception as e:
        print(f"  ⚠ API error: {e}", file=sys.stderr)
        return {}
    return data.get("entities", {})


def claim_targets(entity, prop):
    """Extract list of target QIDs from claims[prop]."""
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        ms = c.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        dv = ms.get("datavalue", {}).get("value", {})
        if isinstance(dv, dict) and dv.get("entity-type") == "item":
            out.append(dv.get("id"))
    return out


def entity_label(entity):
    labels = entity.get("labels", {})
    for lang in ("ro", "en"):
        if lang in labels:
            return labels[lang].get("value")
    return None


def resolve_judet(start_qid, place_cache, max_depth=6):
    """
    BFS up the P131 chain from start_qid. Returns judet_code or None.
    Hydrates place_cache[qid] = {'p131', 'label', 'judet_code'} for visited entities.
    Detects județe inline via judet_code_for(); no pre-discovery of județ QIDs.
    """
    visited = set()
    frontier = [start_qid]
    for _ in range(max_depth):
        if not frontier:
            break
        uncached = [q for q in frontier if q not in place_cache and q not in visited]
        if uncached:
            ents = fetch_entities(uncached, props="claims|labels")
            for q in uncached:
                e = ents.get(q, {"id": q})
                e.setdefault("id", q)
                place_cache[q] = {
                    "p131":       claim_targets(e, "P131"),
                    "label":      entity_label(e),
                    "judet_code": judet_code_for(e),
                }
            time.sleep(1.0)

        next_frontier = []
        for q in frontier:
            if q in visited:
                continue
            visited.add(q)
            code = place_cache.get(q, {}).get("judet_code")
            if code:
                return code
            next_frontier.extend(place_cache.get(q, {}).get("p131", []))
        frontier = next_frontier
    return None


def load_csv():
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    deduped = []
    for r in reversed(rows):  # later wins
        if r["core_name_norm"] in seen:
            continue
        seen.add(r["core_name_norm"])
        deduped.append(r)
    deduped.reverse()
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(deduped)


def replay_csv(cursor, conn, force):
    rows = load_csv()
    if not rows:
        print(f"No CSV at {CSV_PATH}; nothing to replay.")
        return
    n = 0
    for r in rows:
        if not force:
            existing = cursor.execute(
                "SELECT birth_place_qid FROM persons WHERE core_name_norm=?",
                (r["core_name_norm"],)
            ).fetchone()
            if existing and existing[0]:
                continue
        cursor.execute("""
            UPDATE persons
            SET birth_place_qid=?, birth_place_label=?, birth_judet=?
            WHERE core_name_norm=?
        """, (
            r["birth_place_qid"] or None,
            r["birth_place_label"] or None,
            r["birth_judet"] or None,
            r["core_name_norm"],
        ))
        if cursor.rowcount:
            n += 1
    conn.commit()
    print(f"✓ Replayed {n}/{len(rows)} rows from {CSV_PATH}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit",      type=int)
    p.add_argument("--dry-run",    action="store_true")
    p.add_argument("--replay-csv", action="store_true")
    p.add_argument("--force",      action="store_true",
                   help="With --replay-csv, overwrite existing birth_place values")
    p.add_argument("--db",         default="data/streets.db")
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure schema (safe on older DBs).
    for col in ("birth_place_qid", "birth_place_label", "birth_judet"):
        try:
            cursor.execute(f"ALTER TABLE persons ADD COLUMN {col} TEXT;")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    if args.replay_csv:
        replay_csv(cursor, conn, args.force)
        conn.close()
        return

    query = """
        SELECT core_name_norm, full_name, wikidata_qid
        FROM persons
        WHERE wikidata_qid IS NOT NULL AND birth_place_qid IS NULL
        ORDER BY full_name
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    persons = cursor.execute(query).fetchall()
    print(f"Processing {len(persons)} persons (QID set, no birth_place yet)…")

    if not persons:
        conn.close()
        return

    place_cache = {}

    new_rows = []
    for batch_start in range(0, len(persons), BATCH_SIZE):
        batch = persons[batch_start : batch_start + BATCH_SIZE]
        qids  = [p["wikidata_qid"] for p in batch]
        ents  = fetch_entities(qids, props="claims")
        time.sleep(1)

        # Pre-fetch labels + P131 for all P19 targets in this batch in one call
        p19_by_person = {}
        all_p19 = set()
        for person in batch:
            p19s = claim_targets(ents.get(person["wikidata_qid"], {}), "P19")
            p19  = p19s[0] if p19s else None
            p19_by_person[person["core_name_norm"]] = p19
            if p19 and p19 not in place_cache:
                all_p19.add(p19)
        if all_p19:
            chunk = list(all_p19)
            for i in range(0, len(chunk), BATCH_SIZE):
                slc = chunk[i:i+BATCH_SIZE]
                sub = fetch_entities(slc, props="claims|labels")
                for q in slc:
                    e = sub.get(q, {"id": q})
                    e.setdefault("id", q)
                    place_cache[q] = {
                        "p131":       claim_targets(e, "P131"),
                        "label":      entity_label(e),
                        "judet_code": judet_code_for(e),
                    }
                time.sleep(1.0)

        for person in batch:
            cn   = person["core_name_norm"]
            qid  = person["wikidata_qid"]
            p19  = p19_by_person[cn]
            if not p19:
                print(f"  {person['full_name']}: no P19")
                new_rows.append({
                    "core_name_norm":    cn,
                    "full_name":         person["full_name"],
                    "wikidata_qid":      qid,
                    "birth_place_qid":   "",
                    "birth_place_label": "",
                    "birth_judet":       "",
                })
                continue
            label       = place_cache.get(p19, {}).get("label") or ""
            judet_code  = resolve_judet(p19, place_cache)
            print(f"  {person['full_name']:35s} → {label or '?':25s} ({p19})  judet={judet_code or '-'}")
            new_rows.append({
                "core_name_norm":    cn,
                "full_name":         person["full_name"],
                "wikidata_qid":      qid,
                "birth_place_qid":   p19,
                "birth_place_label": label,
                "birth_judet":       judet_code or "",
            })

    if args.dry_run:
        print(f"\n[dry-run] Would update {len(new_rows)} persons")
        return

    for u in new_rows:
        cursor.execute("""
            UPDATE persons
            SET birth_place_qid=?, birth_place_label=?, birth_judet=?
            WHERE core_name_norm=?
        """, (
            u["birth_place_qid"] or None,
            u["birth_place_label"] or None,
            u["birth_judet"] or None,
            u["core_name_norm"],
        ))
    conn.commit()

    existing = load_csv()
    write_csv(existing + new_rows)
    print(f"\n✓ Updated {len(new_rows)} persons; CSV → {CSV_PATH}")

    summary = cursor.execute("""
        SELECT
            COUNT(*)                                                       AS qid_persons,
            SUM(birth_place_qid IS NOT NULL)                              AS resolved,
            SUM(birth_judet     IS NOT NULL)                              AS in_romania
        FROM persons WHERE wikidata_qid IS NOT NULL
    """).fetchone()
    print(f"\nCoverage: {summary['resolved']}/{summary['qid_persons']} have a birth_place; "
          f"{summary['in_romania']} land inside a Romanian județ.")

    conn.close()


if __name__ == "__main__":
    main()
