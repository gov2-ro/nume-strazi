#!/usr/bin/env python3
"""
build_dist_db.py — Build a slim, production-ready streets.db for shipping.

Reads  data/streets.db
Writes dist/streets.db

What it does:
  - Drops tables not used by the client-side filter UI: osm_streets,
    street_osm_matches, street_aliases.
  - Sets page_size=4096 (predictable HTTP range alignment for sql.js-httpvfs).
  - Sets journal_mode=DELETE so the shipped file is self-contained.
  - VACUUMs to repack and apply the new page size.
  - Prints before/after sizes.

Idempotent — rerun freely after rebuilding data/streets.db.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

SRC = Path("data/streets.db")
DST = Path("dist/streets.db")

DROP_TABLES = ("osm_streets", "street_osm_matches", "street_aliases")


def main() -> None:
    if not SRC.exists():
        print(f"error: {SRC} missing. Run build_db.py first.", file=sys.stderr)
        sys.exit(1)

    DST.parent.mkdir(parents=True, exist_ok=True)
    if DST.exists():
        DST.unlink()
    shutil.copy2(SRC, DST)
    src_size = SRC.stat().st_size

    conn = sqlite3.connect(DST)
    try:
        for tbl in DROP_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA page_size = 4096")
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()

    dst_size = DST.stat().st_size
    pct = (1 - dst_size / src_size) * 100
    print(f"wrote {DST}  ({dst_size/1024/1024:.1f} MB, "
          f"−{pct:.1f}% vs source {src_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
