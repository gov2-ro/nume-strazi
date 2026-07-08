"""Sanity-check the RENNS ingest + match by inspecting reference UATs.

Uses the same reference UATs as tools/osm_sanity.py/postal_sanity.py for
continuity, but the caveat is different from postal's population threshold:
RENNS is a rolling, partial national digitization — only ~60% of Romania's
3,181 UATs have ANY road registered yet (verified at ingest time, see
CODE_SPEC §13). A zero result for a small/rural reference UAT is therefore
plausible and NOT flagged here — only the two cases we have hard evidence
for are asserted:
  - București (all 6 sectors): RENNS has literally zero roads for
    București, confirmed directly (not a per-sector sampling artifact) —
    any non-zero result here is a real bug to investigate.
  - Cluj-Napoca / Sibiu: known to have strong RENNS coverage (1,212 / 719
    roads respectively, verified during research) — a zero result here
    would indicate an ingest bug, not a coverage gap.

Read-only. No deps beyond sqlite3.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Same reference set as tools/osm_sanity.py/postal_sanity.py, for continuity.
REFERENCE_UATS = [
    ("București (Sector 1)", 179141, "zero"),
    ("Cluj-Napoca",           54975, "strong"),
    ("Sibiu",                143450, "strong"),
    ("Câmpulung Moldovenesc",146502, "unknown"),
    ("Cornu (rural, PH)",    132805, "unknown"),
]

# All 6 București sectors — RENNS has zero roads for the whole municipality.
BUCURESTI_SECTOR_SIRUTAS = [179141, 179150, 179169, 179178, 179187, 179196]

# Romania's total UAT count, per RENNS's own /api/uats enumeration across all
# 42 counties (verified 2026-07-08: 3,181 UATs). This is a stable national
# administrative fact, not derived from our own `streets` table — the
# registry only has entries for ~1,207 distinct SIRUTAs (a known gap in the
# AEP polling-section source, unrelated to RENNS), so using COUNT(DISTINCT
# siruta) FROM streets as the denominator would understate RENNS's real
# national coverage.
TOTAL_ROMANIA_UATS = 3181


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--limit", type=int, default=20)
    return ap.parse_args()


def main():
    args = parse_args()
    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found at {db}.")

    con = sqlite3.connect(db)
    if con.execute("SELECT COUNT(*) FROM renns_streets").fetchone()[0] == 0:
        sys.exit("renns_streets is empty — run tools/renns_ingest.py first.")

    print("=" * 72)
    print("NATIONAL RENNS COVERAGE")
    print("=" * 72)
    registry_uats = con.execute(
        "SELECT COUNT(DISTINCT siruta) FROM streets WHERE siruta IS NOT NULL"
    ).fetchone()[0]
    uats_with_renns = con.execute(
        "SELECT COUNT(DISTINCT uat_siruta) FROM renns_streets WHERE uat_siruta IS NOT NULL"
    ).fetchone()[0]
    print(f"UATs with ≥1 RENNS road: {uats_with_renns:,}/{TOTAL_ROMANIA_UATS:,} "
          f"({100*uats_with_renns/TOTAL_ROMANIA_UATS:.1f}%) — partial national rollout, expected.")
    print(f"(Our own registry only has street data for {registry_uats:,} distinct UATs — "
          f"RENNS actually covers more UATs than the AEP registry does.)")

    print("\n" + "=" * 72)
    print("BUCUREȘTI (all 6 sectors) — expect ZERO")
    print("=" * 72)
    for siruta in BUCURESTI_SECTOR_SIRUTAS:
        total = con.execute(
            "SELECT COUNT(*) FROM renns_streets WHERE uat_siruta = ?", (siruta,)
        ).fetchone()[0]
        flag = "  ⚠ expected ZERO — investigate" if total > 0 else ""
        print(f"  SIRUTA {siruta}: {total} rows{flag}")

    print("\n" + "=" * 72)
    print("RENNS ROW COUNTS PER REFERENCE UAT")
    print("=" * 72)
    for label, siruta, expectation in REFERENCE_UATS:
        total = con.execute(
            "SELECT COUNT(*) FROM renns_streets WHERE uat_siruta = ?", (siruta,)
        ).fetchone()[0]
        flag = ""
        if expectation == "zero" and total > 0:
            flag = "  ⚠ expected ZERO — investigate"
        elif expectation == "strong" and total == 0:
            flag = "  ⚠ expected strong coverage — investigate"
        elif expectation == "unknown":
            flag = "  (no prior expectation — partial rollout, either is plausible)"
        print(f"— {label} (SIRUTA {siruta}): {total} rows{flag}")

    print("\n" + "=" * 72)
    print("REGISTRY COVERAGE PER REFERENCE UAT (RENNS)")
    print("=" * 72)
    print(f"{'UAT':<30} {'reg streets':>12} {'matched':>10} {'coverage':>10}")
    for label, siruta, _ in REFERENCE_UATS:
        total = con.execute(
            "SELECT COUNT(*) FROM streets_dedup WHERE siruta = ?", (siruta,)
        ).fetchone()[0]
        matched = con.execute("""
            SELECT COUNT(DISTINCT sd.id)
              FROM streets_dedup sd
              JOIN street_renns_matches m ON m.street_id = sd.id
             WHERE sd.siruta = ?
        """, (siruta,)).fetchone()[0]
        if total == 0:
            print(f"{label:<30} {total:>12} {matched:>10} {'—':>10}")
            continue
        pct = 100 * matched / total
        print(f"{label:<30} {total:>12} {matched:>10} {pct:>9.1f}%")

    print("\n" + "=" * 72)
    print(f"RENNS STREETS WITH NO REGISTRY MATCH (sample of {args.limit})")
    print("=" * 72)
    print("(real coverage gaps OR RENNS noise — eyeball before trusting)\n")
    rows = con.execute("""
        SELECT r.uat_siruta, r.name, r.road_type_raw
          FROM renns_streets r
         WHERE NOT EXISTS (
                   SELECT 1 FROM street_renns_matches m WHERE m.renns_street_id = r.id
               )
         ORDER BY r.id
         LIMIT ?
    """, (args.limit,)).fetchall()
    for siruta, name, road_type_raw in rows:
        print(f"  SIRUTA={siruta!s:>7}  [{road_type_raw or '?':<16}] {name}")

    con.close()


if __name__ == "__main__":
    main()
