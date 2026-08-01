#!/usr/bin/env python3
"""
Summarise data/curation/llm_runs.jsonl — what each classification run cost.

The JSONL is append-only and written per batch by tools/llm_classify.py, so it
survives the terminal scrollback and answers "which model classified these keys,
when, and for how much" after the fact.

Usage:
    python3 tools/llm_runs_report.py                  # one line per run
    python3 tools/llm_runs_report.py --batches RUN_ID # per-batch detail
    python3 tools/llm_runs_report.py --errors         # only failed batches
    python3 tools/llm_runs_report.py --reprice        # recost from PRICING now

--reprice exists because cost is an estimate from llm_layer.PRICING, not a
provider invoice: correct a price there and every past run recosts from the
token counts, which are exact.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

LOG = Path("data/curation/llm_runs.jsonl")


def load(path: Path) -> list[dict]:
    if not path.exists():
        print(f"No run log at {path} — nothing has been classified yet, "
              f"or the run predates run logging.", file=sys.stderr)
        return []
    out = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # A killed process can leave a half-written final line; that's the
            # normal cost of append-only logging, not corruption worth failing on.
            print(f"  (skipping malformed line {lineno})", file=sys.stderr)
    return out


def _fmt_cost(v) -> str:
    return "     ?" if v is None else f"${v:8.4f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=str(LOG))
    ap.add_argument("--batches", metavar="RUN_ID", help="Per-batch detail for one run")
    ap.add_argument("--errors", action="store_true", help="Only failed batches")
    ap.add_argument("--reprice", action="store_true",
                    help="Recompute cost from the current llm_layer.PRICING")
    args = ap.parse_args()

    events = load(Path(args.log))
    if not events:
        return 1

    if args.errors:
        errs = [e for e in events if e.get("event") == "batch_error"]
        if not errs:
            print("No batch errors logged.")
            return 0
        print(f"{len(errs)} failed batch(es):\n")
        for e in errs:
            print(f"  {e['ts']}  {e['run_id']}  batch {e.get('batch')}  "
                  f"{e.get('keys')} keys  from {e.get('first_key')!r}")
            print(f"      {e.get('error', '')[:160]}")
        return 0

    if args.batches:
        rows = [e for e in events
                if e.get("run_id") == args.batches and e.get("event") in ("batch", "batch_error")]
        if not rows:
            print(f"No batches logged for run_id {args.batches}", file=sys.stderr)
            return 1
        print(f"Run {args.batches}\n")
        print(f"{'batch':>5} {'keys':>5} {'clas':>5} {'skip':>5} {'secs':>6} "
              f"{'in':>8} {'out':>8} {'cost':>9}  first key")
        for e in rows:
            if e["event"] == "batch_error":
                print(f"{e.get('batch', '?'):>5} {e.get('keys', 0):>5} "
                      f"{'ERROR':>5} {'':>5} {e.get('seconds', 0):>6.1f} "
                      f"{'':>8} {'':>8} {'':>9}  {e.get('first_key', '')}")
                continue
            print(f"{e['batch']:>5} {e['keys']:>5} {e['classified']:>5} {e['skipped']:>5} "
                  f"{e.get('seconds', 0):>6.1f} {e.get('input_tokens') or 0:>8,} "
                  f"{e.get('output_tokens') or 0:>8,} "
                  f"{_fmt_cost(e.get('estimated_cost_usd'))}  {e.get('first_key', '')}")
        return 0

    # Default: one line per run, aggregated from its batches (a run killed
    # before run_end still has batches, and those are what actually cost money).
    runs: dict[str, dict] = defaultdict(lambda: {
        "batches": 0, "errors": 0, "classified": 0, "skipped": 0,
        "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
        "cached_tokens": 0, "cost": 0.0, "cost_known": True, "seconds": 0.0,
        "model": "", "ts": "", "ended": False,
    })
    for e in events:
        r = runs[e.get("run_id", "?")]
        r["model"] = e.get("model") or r["model"]
        r["ts"] = r["ts"] or e.get("ts", "")
        ev = e.get("event")
        if ev == "batch_error":
            r["errors"] += 1
            r["seconds"] += e.get("seconds") or 0
        elif ev == "batch":
            r["batches"] += 1
            r["classified"] += e.get("classified") or 0
            r["skipped"] += e.get("skipped") or 0
            r["seconds"] += e.get("seconds") or 0
            for k in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens"):
                r[k] += e.get(k) or 0
            if args.reprice:
                continue  # priced below, from totals
            c = e.get("estimated_cost_usd")
            if c is None:
                r["cost_known"] = False
            else:
                r["cost"] += c
        elif ev == "run_end":
            r["ended"] = True

    if args.reprice:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from llm_layer import estimate_cost
        for r in runs.values():
            c = estimate_cost(r["model"], r)
            r["cost"], r["cost_known"] = (c or 0.0), c is not None

    print(f"{'run_id':<18} {'model':<20} {'keys':>6} {'err':>4} {'min':>6} "
          f"{'in tok':>10} {'out tok':>9} {'cost':>9}")
    tot_cost, tot_keys, all_known = 0.0, 0, True
    for run_id, r in sorted(runs.items()):
        keys = r["classified"] + r["skipped"]
        tot_keys += keys
        if r["cost_known"]:
            tot_cost += r["cost"]
        else:
            all_known = False
        flag = "" if r["ended"] else " *"
        print(f"{run_id:<18} {r['model']:<20} {keys:>6,} {r['errors']:>4} "
              f"{r['seconds']/60:>6.1f} {r['input_tokens']:>10,} "
              f"{r['output_tokens']:>9,} {_fmt_cost(r['cost'] if r['cost_known'] else None)}{flag}")
    print(f"\n{len(runs)} run(s), {tot_keys:,} keys, "
          f"{'$%.4f' % tot_cost if all_known else '$%.4f + unpriced runs' % tot_cost} total")
    if any(not r["ended"] for r in runs.values()):
        print("* run has no run_end record — interrupted, or still going.")
    print("Cost is an estimate from llm_layer.PRICING, not a provider invoice; "
          "token counts are exact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
