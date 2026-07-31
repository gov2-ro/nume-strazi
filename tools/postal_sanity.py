"""Sanity-check the postal ingest + match by inspecting reference UATs.

Uses the same 5 reference UATs as tools/osm_sanity.py for continuity, but the
expectations differ — the postal source only covers Bucuresti + localities
over 50,000 population (see CODE_SPEC §12), so small towns and rural comune
are STRUCTURAL zeros here, not bugs:
  - Câmpulung Moldovenesc: expect ZERO postal rows (under the 50k threshold).
  - Cornu (rural, PH):     expect ZERO postal rows (same reason).
A non-zero result for either of those is a bug to investigate, not a win.

No geometry/length here, so no importance ranking like osm_sanity.py's —
reports row counts and resolution-method breakdown instead.

Read-only. No deps beyond sqlite3.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Same reference set as tools/osm_sanity.py, for continuity.
REFERENCE_UATS = [
    ("București (Sector 1)", 179141),
    ("Cluj-Napoca",           54975),
    ("Sibiu",                143450),
    ("Câmpulung Moldovenesc",146502),  # expect ZERO — under 50k threshold
    ("Cornu (rural, PH)",    132805),  # expect ZERO — under 50k threshold
]


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
    if con.execute("SELECT COUNT(*) FROM postal_streets").fetchone()[0] == 0:
        sys.exit("postal_streets is empty — run tools/postal_ingest.py first.")

    print("=" * 72)
    print("POSTAL ROW COUNTS + RESOLUTION METHOD PER REFERENCE UAT")
    print("=" * 72)
    for label, siruta in REFERENCE_UATS:
        rows = con.execute("""
            SELECT resolution_method, COUNT(*) FROM postal_streets
             WHERE uat_siruta = ? GROUP BY resolution_method
        """, (siruta,)).fetchall()
        total = sum(c for _, c in rows)
        expect_zero = siruta in (146502, 132805)
        flag = ""
        if expect_zero and total > 0:
            flag = "  ⚠ expected ZERO (under 50k threshold) — investigate"
        elif not expect_zero and total == 0:
            flag = "  ⚠ expected non-zero coverage — investigate"
        print(f"\n— {label} (SIRUTA {siruta}) — {total} rows{flag}")
        for method, count in rows:
            print(f"    {method:<20} {count}")

    print("\n" + "=" * 72)
    print("ELECTORAL COVERAGE PER REFERENCE UAT (postal)")
    print("=" * 72)
    print(f"{'UAT':<30} {'reg streets':>12} {'matched':>10} {'coverage':>10}")
    for label, siruta in REFERENCE_UATS:
        total = con.execute(
            "SELECT COUNT(*) FROM electoral_dedup WHERE siruta = ?", (siruta,)
        ).fetchone()[0]
        matched = con.execute("""
            SELECT COUNT(DISTINCT sd.id)
              FROM electoral_dedup sd
              JOIN street_postal_matches m ON m.street_id = sd.id
             WHERE sd.siruta = ?
        """, (siruta,)).fetchone()[0]
        if total == 0:
            print(f"{label:<30} {total:>12} {matched:>10} {'—':>10}")
            continue
        pct = 100 * matched / total
        print(f"{label:<30} {total:>12} {matched:>10} {pct:>9.1f}%")

    print("\n" + "=" * 72)
    print(f"POSTAL STREETS WITH NO ELECTORAL MATCH (sample of {args.limit})")
    print("=" * 72)
    print("(real coverage gaps OR postal noise — eyeball before trusting)\n")
    rows = con.execute("""
        SELECT p.uat_siruta, p.name, p.source_sheet, p.resolution_method
          FROM postal_streets p
         WHERE NOT EXISTS (
                   SELECT 1 FROM street_postal_matches m WHERE m.postal_street_id = p.id
               )
         ORDER BY p.id
         LIMIT ?
    """, (args.limit,)).fetchall()
    for siruta, name, sheet, method in rows:
        print(f"  SIRUTA={siruta:>7}  [{sheet:<26}] {method:<16} {name}")

    con.close()


if __name__ == "__main__":
    main()
