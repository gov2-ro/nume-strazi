"""Compute the v1 importance score for every row in `osm_streets`.

  importance_v1     = highway_weight × log(1 + length_m) + ref_bonus
  importance_v1_uat_z = z-score of importance_v1 within the UAT

The per-UAT z-score is what makes Bucharest streets comparable to a rural
commune's. Without it, length alone would let Bucharest dominate any
national ranking.

ref_bonus exists because a numbered route (DN1, DJ105, A2…) running through
a town is almost always the local main street, even when OSM tags the
in-town segment as just `secondary` — the prior conversation flagged this
as the highest-signal-per-line addition.

Pure SQL + Python math. No geo deps. Idempotent: overwrites importance_v1
columns each run.

Tunable knobs (HIGHWAY_WEIGHT, REF_BONUS) are top-level constants — change,
re-run, no DB rebuild needed. If you change the formula structurally, bump
to importance_v2 in a separate column rather than overwriting v1.
"""
from __future__ import annotations

import argparse
import math
import re
import sqlite3
import statistics
import sys
from pathlib import Path

HIGHWAY_WEIGHT = {
    "primary":       5.0,
    "secondary":     4.0,
    "tertiary":      3.0,
    "unclassified":  2.0,
    "residential":   2.0,
    "living_street": 1.0,
    "pedestrian":    1.0,
    "service":       1.0,
}
DEFAULT_WEIGHT = 1.0

# DN = drum național, DJ = drum județean, DC = drum comunal, A = autostradă.
# The pattern is intentionally Romania-specific.
REF_RE = re.compile(r"\b(DN|DJ|DC|A)\d+", re.IGNORECASE)
REF_BONUS = 2.0


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and print summary stats; do not write.")
    return ap.parse_args()


def raw_score(highway_class: str, length_m: float, ref: str | None) -> float:
    w = HIGHWAY_WEIGHT.get(highway_class, DEFAULT_WEIGHT)
    base = w * math.log1p(max(0.0, length_m))
    if ref and REF_RE.search(ref):
        base += REF_BONUS
    return base


def main():
    args = parse_args()
    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found at {db}.")

    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT id, uat_siruta, highway_class, length_m, ref FROM osm_streets"
    ).fetchall()
    if not rows:
        sys.exit("osm_streets is empty. Run tools/osm_ingest.py first.")

    raw = {rid: raw_score(hc, lm, rf) for rid, _, hc, lm, rf in rows}

    by_uat: dict[int, list[int]] = {}
    for rid, uat, *_ in rows:
        by_uat.setdefault(uat, []).append(rid)

    z_scores: dict[int, float] = {}
    for uat, ids in by_uat.items():
        vals = [raw[i] for i in ids]
        if len(vals) < 2:
            for i in ids:
                z_scores[i] = 0.0
            continue
        mu = statistics.fmean(vals)
        sd = statistics.pstdev(vals)
        if sd == 0:
            for i in ids:
                z_scores[i] = 0.0
            continue
        for i in ids:
            z_scores[i] = (raw[i] - mu) / sd

    print(f"Scored {len(rows)} rows across {len(by_uat)} UATs.")
    sample = sorted(raw.values())
    if sample:
        print(f"  raw    min/median/max: {sample[0]:.2f} / "
              f"{sample[len(sample)//2]:.2f} / {sample[-1]:.2f}")
        zsample = sorted(z_scores.values())
        print(f"  uat_z  min/median/max: {zsample[0]:.2f} / "
              f"{zsample[len(zsample)//2]:.2f} / {zsample[-1]:.2f}")

    if args.dry_run:
        print("[DRY RUN] Not written.")
        return

    con.executemany(
        "UPDATE osm_streets SET importance_v1=?, importance_v1_uat_z=? WHERE id=?",
        [(raw[rid], z_scores[rid], rid) for rid in raw],
    )
    con.commit()
    con.close()
    print("Wrote importance_v1, importance_v1_uat_z.")


if __name__ == "__main__":
    main()
