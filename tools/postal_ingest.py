"""Ingest street names from the Poșta Română postal-code registry into `postal_streets`.

Source: data/reference/coduri-postale+/infocod-cu-siruta-mai-2016.xlsx
Sheets used: 'Bucuresti', 'Localitati peste 50.000 loc'. The third sheet,
'Localitati sub 50.000 loc', has no street-level columns at all (just
locality-wide postal codes) — skipped, a structural gap this source can't
close. See CODE_SPEC §12 for why the 2009 coduri_postale.sql dump was
evaluated and excluded (it adds no locality coverage beyond this xlsx).

UAT resolution (see CODE_SPEC §12 for the empirical corrections this encodes):
  - 'Bucuresti' sheet:                    SIRUTA SECTOR column, direct.
  - 'Localitati peste 50.000 loc' sheet:  SIRSUP column, direct — NOT the
    column literally named SIRUTA (verified 0/47 match vs SIRSUP's 47/47;
    SIRUTA here is a finer-grained internal postal sub-code).
  - Fallback (either sheet, or if the direct code isn't a real electoral-
    source SIRUTA): name-match judet+localitate against the SIRUTA-coords CSV.

Person names in this source are frequently "Surname Firstname" (reversed vs.
the electoral source's "Firstname Surname") — core_name_norm_swapped captures the
2-token reorder so tools/postal_match.py can catch these.

Idempotent: --rebuild truncates postal_streets (and street_postal_matches,
which references it) before inserting.

Usage:
  python3 tools/postal_ingest.py
  python3 tools/postal_ingest.py --rebuild
  python3 tools/postal_ingest.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streets_lib import (  # noqa: E402
    fix_diacritics, normalize_match, extract_features, JUDET_NAME_TO_COD,
)

TIP_ARTERA_MAP = {
    "Stradă": "Strada", "Bulevard": "Bulevardul", "Cale": "Calea",
    "Drum": "Drumul", "Intrare": "Intrarea", "Piaţă": "Piața",
    "Piaţetă": "Piața", "Prelungire": "Prelungirea",
    "Şosea": "Șoseaua", "Sosea": "Șoseaua", "Splai": "Splaiul",
    "Stradelă": "Stradela", "Uliţă": "Ulița", "Cartier": "Cartierul",
    "Fundătură": "Fundătura", "Fundac": "Fundătura", "Pasaj": "Pasajul",
    "Rampa": "Rampa", "Trecătoare": "Trecerea", "Potecă": "Cărarea",
}
# "Alee", "Alee I".."Alee VIII" all collapse to "Aleea" — handled separately
# below since it's a prefix match, not an exact key.

_PAREN_RE = re.compile(r"\s*\([^)]+\)")


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--xlsx",
                     default="data/reference/coduri-postale+/infocod-cu-siruta-mai-2016.xlsx")
    ap.add_argument("--siruta-coords",
                     default="data/gis/populatie-romania-siruta-coords.csv")
    ap.add_argument("--rebuild", action="store_true",
                     help="Truncate postal_streets before inserting.")
    ap.add_argument("--dry-run", action="store_true",
                     help="Parse and group, print stats, do not write.")
    return ap.parse_args()


def load_siruta_in_db(con: sqlite3.Connection) -> set:
    return {
        row[0] for row in
        con.execute("SELECT DISTINCT siruta FROM streets WHERE siruta IS NOT NULL")
    }


def load_locality_index(coords_csv: Path, siruta_in_db: set) -> list:
    """[(cod_judet, name_normalized, siruta)] filtered to SIRUTAs in the electoral source DB."""
    out = []
    with coords_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                siruta = int(row["siruta"])
            except (KeyError, ValueError):
                continue
            if siruta not in siruta_in_db:
                continue
            out.append((row["cod_judet"], normalize_match(row["localitate"]), siruta))
    return out


def resolve_name_match(judet_raw: str, localitate_raw: str, locality_index: list):
    """Return (siruta, method) via județ+localitate name matching, or (None, 'unresolved')."""
    cod_judet = JUDET_NAME_TO_COD.get(normalize_match(judet_raw))
    if not cod_judet:
        return None, "unresolved"
    loc_norm = normalize_match(localitate_raw)
    if not loc_norm:
        return None, "unresolved"
    candidates = [(cj, ln, s) for cj, ln, s in locality_index if cj == cod_judet]
    for cj, ln, s in candidates:
        if ln == loc_norm:
            return s, "name_match_exact"
    # Truncation-tolerant fallback (e.g. "Drobeta-Turnu S" vs "Drobeta-Turnu Severin").
    for cj, ln, s in candidates:
        if ln.startswith(loc_norm) or loc_norm.startswith(ln):
            return s, "name_match_fuzzy"
    return None, "unresolved"


def map_street_type(tip_raw: str) -> str | None:
    if not tip_raw:
        return None
    t = fix_diacritics(tip_raw).strip()
    if t.startswith("Alee"):
        return "Aleea"
    return TIP_ARTERA_MAP.get(t, t)


def clean_name(denumire_raw: str) -> str | None:
    if not denumire_raw:
        return None
    s = fix_diacritics(denumire_raw).strip()
    s = _PAREN_RE.sub("", s).strip()
    return s or None


# Trailing title/rank abbreviations seen in the Bucuresti sheet's comma-suffix
# convention ("Surname Firstname, <abbr>.", e.g. "Mincu Ion, arh.") -- distinct
# from the electoral source's leading-prefix TITLES/RANKS in streets_lib.py, which use
# full/differently-abbreviated forms these don't match (logged in BACKLOG.md
# "Postal source: trailing comma-suffixed titles not stripped"). Full-word
# suffixes already spelled out (doctor, general, pictor, ...) don't need an
# entry here -- expand_trailing_title() capitalizes anything not in this map.
TRAILING_ABBR = {
    "sold.": "Soldat", "serg.": "Sergent", "slt.": "Sublocotenent",
    "lt.": "Locotenent", "cap.": "Caporal", "cpt.": "Căpitan",
    "g-ral.": "General", "g-ral": "General", "mr.": "Maior",
    "col.": "Colonel", "maj.": "Major", "av.": "Aviator",
    "plt.": "Plutonier", "prof.": "Prof.", "dr.": "Dr.", "comp.": "Compozitor",
}


def expand_trailing_title(name: str) -> str:
    """'Mincu Ion, arh.' -> 'Arh. Mincu Ion', for feature extraction only --
    never for display (see build_row(), which calls this on a copy, not on
    the stored `name` field). No-op if there's no comma.

    Deliberately does NOT reorder the name part, unlike swap_two_tokens()
    above. A first pass here did ("Mincu Ion" -> "Ion Mincu") on the
    assumption postal names are always reversed "Surname Firstname" -- but
    spot-checking against real rows falsified that: "Gala Galaction" (a pen
    name, not Surname-Firstname) and "Petöfi Șándor" (Hungarian
    family-name-first order, already correct) both got silently corrupted by
    a blind swap. Reordering needs actual evidence, not a heuristic guess --
    see tools/resolve_reversed_person_duplicates.py, which only reorders a
    name when its reversed form already exists as a curated person. This
    function's job is just the unambiguous part: strip the trailing title/
    rank so it doesn't stay glued onto core_name.
    """
    if "," not in name:
        return name
    name_part, _, suffix = name.rpartition(",")
    name_part = name_part.strip()
    suffix_tokens = suffix.strip().split()
    if not suffix_tokens:
        return name
    expanded = " ".join(TRAILING_ABBR.get(t.lower(), t.capitalize()) for t in suffix_tokens)
    return f"{expanded} {name_part}".strip()


def swap_two_tokens(core_name_norm: str | None) -> str | None:
    if not core_name_norm:
        return None
    parts = core_name_norm.split(" ")
    if len(parts) != 2:
        return None
    return f"{parts[1]} {parts[0]}"


def build_row(source_sheet, row_id, judet_raw, localitate_raw, uat_siruta,
              resolution_method, resolution_confidence, tip_artera_raw, denumire_raw):
    street_type = map_street_type(tip_artera_raw)
    name = clean_name(denumire_raw)
    if not name:
        return None
    name_norm = normalize_match(name)
    if not name_norm:
        return None
    feats = extract_features(expand_trailing_title(name))
    core_norm = normalize_match(feats["core_name"]) if feats["core_name"] else None
    return {
        "source_sheet": source_sheet,
        "row_id": row_id,
        "judet_raw": judet_raw,
        "localitate_raw": localitate_raw,
        "uat_siruta": uat_siruta,
        "resolution_method": resolution_method,
        "resolution_confidence": resolution_confidence,
        "tip_artera_raw": tip_artera_raw,
        "street_type": street_type,
        "name": name,
        "name_normalized": name_norm,
        "title": feats["title"],
        "rank": feats["rank"],
        "is_saint": feats["is_saint"],
        "is_date": feats["is_date"],
        "is_numeric": feats["is_numeric"],
        "core_name": feats["core_name"],
        "core_name_norm": core_norm,
        "core_name_norm_swapped": swap_two_tokens(core_norm),
    }


def main():
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"DB not found at {db_path}. Run build_db.py first.")
    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        sys.exit(f"Postal xlsx not found at {xlsx_path}.")
    coords_csv = Path(args.siruta_coords)
    if not coords_csv.exists():
        sys.exit(f"SIRUTA coords CSV not found at {coords_csv}.")

    try:
        import openpyxl
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}\n  pip install openpyxl")

    con = sqlite3.connect(db_path)
    siruta_in_db = load_siruta_in_db(con)
    locality_index = load_locality_index(coords_csv, siruta_in_db)
    print(f"Loaded {len(siruta_in_db):,} electoral-source SIRUTAs, "
          f"{len(locality_index):,} localities for name-match fallback.")

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)

    resolution_counts: dict = {}
    rows_read = 0
    rows_skipped = 0
    grouped: dict = {}

    def note_resolution(method):
        resolution_counts[method] = resolution_counts.get(method, 0) + 1

    def add_to_group(rec):
        key = (rec["uat_siruta"], rec["name_normalized"])
        slot = grouped.setdefault(key, {**rec, "source_row_ids": []})
        slot["source_row_ids"].append(rec["row_id"])

    # ---------- Bucuresti sheet ----------
    ws = wb["Bucuresti"]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    idx = {name: i for i, name in enumerate(header)}
    for i, row in enumerate(rows):
        rows_read += 1
        tip_raw = row[idx["Tip artera"]]
        den_raw = row[idx["Denumire artera"]]
        sector_siruta = row[idx["SIRUTA SECTOR"]]
        if not tip_raw or not den_raw:
            rows_skipped += 1
            continue
        uat_siruta, method = None, "unresolved"
        try:
            cand = int(sector_siruta)
            if cand in siruta_in_db:
                uat_siruta, method = cand, "direct_sector"
        except (TypeError, ValueError):
            pass
        note_resolution(method)
        rec = build_row("Bucuresti", i, "București", None, uat_siruta, method, 1.0,
                         tip_raw, den_raw)
        if rec is None:
            rows_skipped += 1
            continue
        if uat_siruta is not None:
            add_to_group(rec)

    # ---------- Localitati peste 50.000 loc sheet ----------
    ws = wb["Localitati peste 50.000 loc"]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    idx = {name: i for i, name in enumerate(header)}
    for i, row in enumerate(rows):
        rows_read += 1
        judet_raw = row[idx["Judet"]]
        localitate_raw = row[idx["Localitate"]]
        tip_raw = row[idx["Tip artera"]]
        den_raw = row[idx["Denumire artera"]]
        sirsup = row[idx["SIRSUP"]]
        if not tip_raw or not den_raw:
            rows_skipped += 1
            continue
        uat_siruta, method, conf = None, "unresolved", 0.0
        try:
            cand = int(sirsup)
            if cand in siruta_in_db:
                uat_siruta, method, conf = cand, "direct_sirsup", 1.0
        except (TypeError, ValueError):
            pass
        if uat_siruta is None:
            m_siruta, m_method = resolve_name_match(judet_raw, localitate_raw, locality_index)
            if m_siruta is not None:
                uat_siruta = m_siruta
                method = m_method
                conf = 0.8 if m_method == "name_match_exact" else 0.5
        note_resolution(method)
        rec = build_row("Localitati peste 50.000 loc", i, judet_raw, localitate_raw,
                         uat_siruta, method, conf, tip_raw, den_raw)
        if rec is None:
            rows_skipped += 1
            continue
        if uat_siruta is not None:
            add_to_group(rec)

    print(f"\nRows read:    {rows_read:,}")
    print(f"Rows skipped: {rows_skipped:,} (empty type/name)")
    print("\nResolution method breakdown:")
    for method, count in sorted(resolution_counts.items(), key=lambda kv: -kv[1]):
        pct = 100 * count / rows_read if rows_read else 0
        print(f"  {method:<20} {count:>7,}  ({pct:5.1f}%)")
    print(f"\nGrouped into {len(grouped):,} distinct (uat_siruta, name_normalized) rows.")

    if args.dry_run:
        print("[DRY RUN] Not writing.")
        con.close()
        return

    if args.rebuild:
        con.execute("DELETE FROM street_postal_matches")
        con.execute("DELETE FROM postal_streets")

    insert_rows = [
        {
            "source_sheet": g["source_sheet"],
            "source_row_ids": json.dumps(g["source_row_ids"]),
            "judet_raw": g["judet_raw"],
            "localitate_raw": g["localitate_raw"],
            "uat_siruta": g["uat_siruta"],
            "resolution_method": g["resolution_method"],
            "resolution_confidence": g["resolution_confidence"],
            "tip_artera_raw": g["tip_artera_raw"],
            "street_type": g["street_type"],
            "name": g["name"],
            "name_normalized": g["name_normalized"],
            "title": g["title"],
            "rank": g["rank"],
            "is_saint": g["is_saint"],
            "is_date": g["is_date"],
            "is_numeric": g["is_numeric"],
            "core_name": g["core_name"],
            "core_name_norm": g["core_name_norm"],
            "core_name_norm_swapped": g["core_name_norm_swapped"],
        }
        for g in grouped.values()
    ]
    con.executemany(
        """INSERT INTO postal_streets
           (source_sheet, source_row_ids, judet_raw, localitate_raw, uat_siruta,
            resolution_method, resolution_confidence, tip_artera_raw, street_type,
            name, name_normalized, title, rank, is_saint, is_date, is_numeric,
            core_name, core_name_norm, core_name_norm_swapped)
           VALUES (:source_sheet, :source_row_ids, :judet_raw, :localitate_raw, :uat_siruta,
                   :resolution_method, :resolution_confidence, :tip_artera_raw, :street_type,
                   :name, :name_normalized, :title, :rank, :is_saint, :is_date, :is_numeric,
                   :core_name, :core_name_norm, :core_name_norm_swapped)
           ON CONFLICT(uat_siruta, name_normalized) DO UPDATE SET
             source_sheet           = excluded.source_sheet,
             source_row_ids         = excluded.source_row_ids,
             judet_raw               = excluded.judet_raw,
             localitate_raw          = excluded.localitate_raw,
             resolution_method       = excluded.resolution_method,
             resolution_confidence   = excluded.resolution_confidence,
             tip_artera_raw          = excluded.tip_artera_raw,
             street_type             = excluded.street_type,
             name                    = excluded.name,
             title                   = excluded.title,
             rank                    = excluded.rank,
             is_saint                = excluded.is_saint,
             is_date                 = excluded.is_date,
             is_numeric              = excluded.is_numeric,
             core_name               = excluded.core_name,
             core_name_norm          = excluded.core_name_norm,
             core_name_norm_swapped  = excluded.core_name_norm_swapped""",
        insert_rows,
    )
    con.commit()
    con.close()
    print(f"\nInserted/updated {len(insert_rows):,} rows in postal_streets.")


if __name__ == "__main__":
    main()
