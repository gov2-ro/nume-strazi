#!/usr/bin/env python3
"""Compare two llm_classify.py output CSVs and report agreement rate.

Useful for running two models in parallel and checking convergence before importing.
Agreement is measured on the 'table' field (classification bucket). Disagreements
are printed sorted by frequency so the highest-impact mismatches surface first.

Usage:
    python3 tools/llm_compare.py data/curation/llm_claude-haiku.csv data/curation/llm_gemini-flash.csv
    python3 tools/llm_compare.py FILE_A FILE_B --show-agrees
"""
import argparse, csv
from pathlib import Path


def load(path: Path) -> dict:
    with open(path, newline="", encoding="utf-8") as f:
        return {
            row["core_name_norm"]: row
            for row in csv.DictReader(f)
            if row["core_name_norm"]
        }


def table_of(row: dict) -> str:
    return row.get("table", "") or "skip"


def detail(row: dict) -> str:
    t = table_of(row)
    if t == "persons":
        return row.get("full_name") or row.get("profession") or ""
    if t == "nature_terms":
        return row.get("nature_type") or ""
    if t == "name_categories":
        sub = row.get("subcategory") or ""
        return f"{row.get('category','')}/{sub}" if sub else row.get("category", "")
    if t == "place_refs":
        return f"{row.get('place_type','')} {row.get('place_name','')}".strip()
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file_a")
    ap.add_argument("file_b")
    ap.add_argument("--show-agrees", action="store_true",
                    help="Also print keys where both models agree (verbose)")
    args = ap.parse_args()

    a = load(Path(args.file_a))
    b = load(Path(args.file_b))

    a_name = Path(args.file_a).stem.removeprefix("llm_")
    b_name = Path(args.file_b).stem.removeprefix("llm_")

    common  = sorted(set(a) & set(b))
    only_a  = set(a) - set(b)
    only_b  = set(b) - set(a)

    agree = disagree = skipped_both = 0
    disagree_rows = []
    agree_rows    = []

    for key in common:
        ra, rb   = a[key], b[key]
        ta, tb   = table_of(ra), table_of(rb)
        freq     = int(ra.get("freq") or 0)
        sample   = ra.get("sample_name") or ""

        if ta == "skip" and tb == "skip":
            skipped_both += 1
        elif ta == tb:
            agree += 1
            agree_rows.append((freq, key, ta, detail(ra), detail(rb), sample))
        else:
            disagree += 1
            disagree_rows.append((freq, key, ta, detail(ra), tb, detail(rb), sample))

    classified_both = agree + disagree
    pct = f"{100*agree/classified_both:.1f}%" if classified_both else "n/a"

    print(f"{'─'*70}")
    print(f"  A: {Path(args.file_a).name}  ({len(a)} keys)")
    print(f"  B: {Path(args.file_b).name}  ({len(b)} keys)")
    print(f"{'─'*70}")
    print(f"  Common keys     : {len(common)}")
    print(f"  Only in A       : {len(only_a)}")
    print(f"  Only in B       : {len(only_b)}")
    print(f"  Both skipped    : {skipped_both}")
    print(f"  Both classified : {classified_both}")
    print(f"  Agreement       : {agree} / {classified_both}  ({pct})")
    print(f"  Disagreements   : {disagree}")
    print(f"{'─'*70}")

    if disagree_rows:
        disagree_rows.sort(key=lambda x: -x[0])
        w = max(len(a_name), len(b_name), 8)
        print(f"\nDisagreements (sorted by frequency):")
        print(f"  {'key':<32}  freq  {a_name:<{w}}  detail-A         {b_name:<{w}}  detail-B")
        print(f"  {'─'*32}  ────  {'─'*w}  {'─'*15}  {'─'*w}  {'─'*15}")
        for freq, key, ta, da, tb, db, _ in disagree_rows:
            print(f"  {key:<32}  {freq:>4}  {ta:<{w}}  {da[:15]:<15}  {tb:<{w}}  {db[:15]}")

    if args.show_agrees and agree_rows:
        agree_rows.sort(key=lambda x: -x[0])
        print(f"\nAgreements:")
        print(f"  {'key':<32}  freq  table            detail-A         detail-B")
        print(f"  {'─'*32}  ────  {'─'*15}  {'─'*15}  {'─'*15}")
        for freq, key, t, da, db, _ in agree_rows:
            print(f"  {key:<32}  {freq:>4}  {t:<15}  {da[:15]:<15}  {db[:15]}")

    if only_a:
        print(f"\nOnly in A ({len(only_a)} keys) — not yet run through B:")
        for key in sorted(only_a)[:10]:
            print(f"  {key}")
        if len(only_a) > 10:
            print(f"  … and {len(only_a)-10} more")

    if only_b:
        print(f"\nOnly in B ({len(only_b)} keys) — not yet run through A:")
        for key in sorted(only_b)[:10]:
            print(f"  {key}")
        if len(only_b) > 10:
            print(f"  … and {len(only_b)-10} more")


if __name__ == "__main__":
    main()
