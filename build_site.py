#!/usr/bin/env python3
# build_site.py
import argparse
import shutil
from pathlib import Path

import jinja2

import site_queries


DIST = Path("dist")
TEMPLATES = Path("templates")
DB_PATH = "data/streets.db"
COUNTIES_SRC = Path("data/gis/romania-counties.geojson")

VARIANTS = {
    "default": ("index.html.j2", "index.html"),
    "v1": ("index-v1.html.j2", "index-v1.html"),
    "v2": ("index-v2.html.j2", "index-v2.html"),
    "methodology": ("metodologie.html.j2", "metodologie.html"),
}

# Static-content variants don't need any of the section query data.
STATIC_VARIANTS = {"methodology"}


def build(db_path: str = DB_PATH, variant: str = "default") -> None:
    DIST.mkdir(exist_ok=True)

    if variant in STATIC_VARIANTS:
        data = {}
    else:
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
    template_name, output_name = VARIANTS[variant]
    tmpl = env.get_template(template_name)
    html = tmpl.render(**data)

    out = DIST / output_name
    out.write_text(html, encoding="utf-8")
    print(f"  → {out}  ({out.stat().st_size // 1024} KB)")

    if COUNTIES_SRC.exists():
        shutil.copy(COUNTIES_SRC, DIST / "ro-counties.geojson")
        print(f"  → {DIST}/ro-counties.geojson")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build street names static site")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument(
        "--variant",
        choices=["default", "v1", "v2", "methodology", "both", "all"],
        default="default",
        help="Which template to render (default = cluster cloud | v1 | v2 = dense | methodology | both = default+v2 | all)",
    )
    parser.add_argument("--serve", action="store_true", help="Build then serve on localhost:8000")
    args = parser.parse_args()
    if args.variant == "both":
        variants = ["default", "v2"]
    elif args.variant == "all":
        variants = ["default", "v1", "v2", "methodology"]
    else:
        variants = [args.variant]
    for v in variants:
        build(db_path=args.db, variant=v)
    if args.serve:
        import http.server
        import os
        os.chdir("dist")
        print("Serving at http://localhost:8000 …")
        http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=8000, bind="127.0.0.1")


if __name__ == "__main__":
    main()
