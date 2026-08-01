#!/usr/bin/env python3
"""Measure how many UATs each OSM highway class would add to our reach.

Answers "if we widened the ingest scope to include class X, how many more UATs
would have street names?" — without committing to a scope change.

One pass over the PBF. Every *named* highway way's midpoint is resolved to a UAT
with the same polygon containment `tools/osm_ingest.py` uses (`uat_boundaries`,
so run `tools/osm_boundaries.py` first), then tallied per `highway=*` value.

Written 2026-08-01 to test the standing assumption that our reach gap versus
OSM-only competitors was rural UATs whose only named road is tagged `track`.
It is not: `track` adds 77 UATs, and the union of *every* highway class tops out
at 2,802 of 3,183 — 381 UATs contain no named highway way at all, so no scope
widening reaches them. Keep this tool around; the next "why don't we cover X"
question is cheaper to measure than to argue about.

Usage:
    python3 tools/osm_reach_report.py                  # the table + greedy rollup
    python3 tools/osm_reach_report.py --list-empty     # the UATs no class reaches
    python3 tools/osm_reach_report.py --csv out.csv    # per-UAT, per-class detail
"""
import argparse, csv, sqlite3, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from osm_ingest import UatIndex, KEPT_HIGHWAY  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--pbf", default="data/reference/romania-latest.osm.pbf")
    ap.add_argument("--list-empty", action="store_true",
                    help="List UATs with no named highway way of ANY class")
    ap.add_argument("--csv", default=None, help="Write per-class detail to CSV")
    args = ap.parse_args()

    import osmium

    con = sqlite3.connect(args.db)
    idx = UatIndex(con)
    print(f"boundary index: {len(idx)} UATs", flush=True)

    ways_by_class: dict[str, int] = defaultdict(int)
    uats_by_class: dict[str, set] = defaultdict(set)

    class Scan(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.n = 0

        def way(self, w):
            hw = w.tags.get("highway")
            if not hw or not w.tags.get("name"):
                return
            self.n += 1
            if self.n % 200_000 == 0:
                print(f"  ...{self.n:,} named highway ways", flush=True)
            try:
                nodes = list(w.nodes)
                mid = nodes[len(nodes) // 2]
                siruta = idx.locate(mid.location.lon, mid.location.lat)
            except Exception:
                return
            ways_by_class[hw] += 1
            if siruta is not None:
                uats_by_class[hw].add(siruta)

    scan = Scan()
    scan.apply_file(args.pbf, locations=True)
    print(f"total named highway ways: {scan.n:,}\n")

    kept = set()
    for c in KEPT_HIGHWAY:
        kept |= uats_by_class.get(c, set())
    print(f"CURRENT filter ({', '.join(sorted(KEPT_HIGHWAY))})")
    print(f"  reaches {len(kept)} UATs\n")

    print(f"{'class':<18} {'named ways':>11} {'UATs':>7} {'NEW UATs':>9}  in filter")
    print("-" * 62)
    for cls, n in sorted(ways_by_class.items(),
                         key=lambda kv: -len(uats_by_class[kv[0]])):
        us = uats_by_class[cls]
        print(f"{cls:<18} {n:>11,} {len(us):>7} {len(us - kept):>9}  "
              f"{'yes' if cls in KEPT_HIGHWAY else ''}")

    # Greedy: which additions actually buy reach, best first. Order matters —
    # classes overlap heavily, so summing their individual "NEW UATs" columns
    # overstates the total badly.
    print("\ncumulative reach if added (greedy, best-first):")
    pool = set(kept)
    cands = {c: u for c, u in uats_by_class.items() if c not in KEPT_HIGHWAY}
    while cands:
        best = max(cands, key=lambda c: len(cands[c] - pool))
        gain = len(cands[best] - pool)
        if gain == 0:
            break
        pool |= cands.pop(best)
        print(f"  +{best:<18} +{gain:>5} UATs → {len(pool)}")

    everything = set().union(*uats_by_class.values()) if uats_by_class else set()
    empty = set(idx.sirutas) - everything if hasattr(idx, "sirutas") else None
    if empty is None:
        empty = {s for (s,) in con.execute("SELECT siruta FROM uat_boundaries")} - everything
    print(f"\nceiling: {len(everything)} UATs have >=1 named highway way of any class")
    print(f"{len(empty)} UATs have NONE — unreachable by any scope widening")

    if args.list_empty:
        # Label from uat_reference, not all_street_names_cache: by definition
        # these UATs have little or no street data, and 326 of the 381 have no
        # row in the cache at all. uat_reference covers every SIRUTA (CLAUDE.md
        # rule #14 — build-time only, which is exactly when this tool runs).
        labels = dict()
        for siruta, judet, uat in con.execute(
                "SELECT siruta, judet, uat FROM uat_reference"):
            labels[siruta] = (judet, uat)
        print(f"\n── {len(empty)} UATs with no named highway in OSM ──")
        for s in sorted(empty, key=lambda s: labels.get(s, ("ZZ", ""))):
            judet, uat = labels.get(s, ("??", "(unlabelled)"))
            print(f"  {s:>7}  {judet or '??':<3} {uat}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["highway_class", "named_ways", "uats", "new_uats", "in_filter"])
            for cls, n in sorted(ways_by_class.items(),
                                 key=lambda kv: -len(uats_by_class[kv[0]])):
                us = uats_by_class[cls]
                w.writerow([cls, n, len(us), len(us - kept), int(cls in KEPT_HIGHWAY)])
        print(f"\nWrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
