#!/usr/bin/env python3
# build_site.py
import argparse
import json
import os
import shutil
import sqlite3
from pathlib import Path

import jinja2

import site_queries


DIST = Path("dist")
TEMPLATES = Path("templates")
DB_PATH = "data/streets.db"
COUNTIES_SRC = Path("data/gis/romania-counties.geojson")


def build(db_path: str = DB_PATH) -> None:
    DIST.mkdir(exist_ok=True)

    conn = site_queries.get_connection(db_path)

    data = {
        "section1": site_queries.section1(conn),
        "section2": site_queries.section2(conn),
        "section3": site_queries.section3(conn),
        "section4": site_queries.section4(conn),
        "section5": site_queries.section5(conn),
        "section6": site_queries.section6(conn),
        "section8": site_queries.section8(conn),
    }
    conn.close()

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    tmpl = env.get_template("index.html.j2")
    html = tmpl.render(**data)

    out = DIST / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"  → {out}  ({out.stat().st_size // 1024} KB)")

    if COUNTIES_SRC.exists():
        shutil.copy(COUNTIES_SRC, DIST / "ro-counties.geojson")
        print(f"  → {DIST}/ro-counties.geojson")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build street names static site")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    build(db_path=args.db)


if __name__ == "__main__":
    main()
