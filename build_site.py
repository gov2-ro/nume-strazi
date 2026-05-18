#!/usr/bin/env python3
# build_site.py
import argparse
import json
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
            "municipii": site_queries.municipii_index(conn),
        }
        conn.close()

        portraits_dir = DIST / "portraits"
        data["portraits"] = [p.stem for p in sorted(portraits_dir.glob("*.jpg"))] \
            if portraits_dir.exists() else []

    env = _make_env()
    template_name, output_name = VARIANTS[variant]
    tmpl = env.get_template(template_name)
    html = tmpl.render(**data)

    out = DIST / output_name
    out.write_text(html, encoding="utf-8")
    print(f"  → {out}  ({out.stat().st_size // 1024} KB)")

    if COUNTIES_SRC.exists():
        shutil.copy(COUNTIES_SRC, DIST / "ro-counties.geojson")
        print(f"  → {DIST}/ro-counties.geojson")


def _make_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    env.filters["enumerate"] = enumerate
    return env


def _render(env: jinja2.Environment, template_name: str, out_path: Path, **ctx) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env.get_template(template_name).render(**ctx), encoding="utf-8")


def build_detail_pages(db_path: str = DB_PATH) -> None:
    """Render all per-entity detail pages and index pages into dist/."""
    conn = site_queries.get_connection(db_path)
    env = _make_env()
    portraits_dir = DIST / "portraits"
    portraits = [p.stem for p in sorted(portraits_dir.glob("*.jpg"))] \
        if portraits_dir.exists() else []

    # ── Streets ─────────────────────────────────────────────────────────────
    streets = site_queries.enumerate_streets(conn)
    print(f"  Rendering {len(streets)} street detail pages…")
    seen: dict[str, str] = {}
    for s in streets:
        slug = s["slug"]
        if slug in seen and seen[slug] != s["name_normalized"]:
            print(f"  WARN: street slug collision '{slug}'")
            continue
        seen[slug] = s["name_normalized"]
        detail = site_queries.street_detail(conn, s["name_normalized"])
        if not detail:
            continue
        og = {
            "og_title": f"{detail['display_name']} — Cum ne numim străzile",
            "og_description": (
                f"„{detail['display_name']}” — {detail['total_count']} străzi "
                f"în {detail['uat_count']} localități din România."
            ),
            "og_url_path": f"/strada/{slug}/",
        }
        _render(env, "street-detail.html.j2",
                DIST / "strada" / slug / "index.html",
                portraits=portraits, **og, **detail)
    print(f"    → dist/strada/ ({len(streets)} pages)")

    # ── Persons ──────────────────────────────────────────────────────────────
    persons = site_queries.enumerate_persons(conn)
    print(f"  Rendering {len(persons)} person detail pages…")
    seen_p: dict[str, str] = {}  # slug → core_name_norm (first = highest street count)
    rendered_p = 0
    for p in persons:
        slug = p["slug"]
        if slug in seen_p:
            continue  # duplicate QID — keep the first (higher street_count) rendering
        seen_p[slug] = p["core_name_norm"]
        detail = site_queries.person_detail(conn, p["core_name_norm"])
        if not detail:
            continue
        full_name = detail.get("full_name") or p["full_name"]
        sc = detail.get("street_count") or p.get("street_count") or 0
        og = {
            "og_title": f"{full_name} — Cum ne numim străzile",
            "og_description": (
                f"{full_name} — onorat(ă) pe {sc} străzi din România. "
                f"Profil, biografie scurtă, distribuție pe județe."
            ),
            "og_url_path": f"/persoana/{slug}/",
        }
        _render(env, "person-detail.html.j2",
                DIST / "persoana" / slug / "index.html",
                portraits=portraits, slug=slug, **og, **detail)
        rendered_p += 1
    print(f"    → dist/persoana/ ({rendered_p} pages)")

    # ── UATs ─────────────────────────────────────────────────────────────────
    uats = site_queries.enumerate_uats(conn)
    print(f"  Rendering {len(uats)} UAT detail pages…")
    # Precompute globals once — avoids a full streets_dedup scan per UAT page.
    global_rarity = {
        r["name_normalized"]: r["uat_n"]
        for r in site_queries._rows(conn, """
            SELECT name_normalized, COUNT(DISTINCT siruta) AS uat_n
            FROM streets_dedup
            WHERE is_numeric = 0 AND core_name IS NOT NULL
            GROUP BY name_normalized
        """)
    }
    nat = site_queries._one(conn, """
        SELECT ROUND(100.0 * SUM(is_saint)   / COUNT(*), 2) AS saint_pct,
               ROUND(100.0 * SUM(is_numeric) / COUNT(*), 2) AS numeric_pct
        FROM streets_dedup
    """)
    for u in uats:
        detail = site_queries.uat_detail(
            conn, str(u["siruta"]), global_rarity=global_rarity, nat=nat
        )
        if not detail:
            continue
        uat_label = detail.get("uat_name") or u.get("uat") or u["slug"]
        total_streets = detail.get("total_streets") or u.get("total") or 0
        og = {
            "og_title": f"{uat_label} — Cum ne numim străzile",
            "og_description": (
                f"{uat_label} ({u['judet']}) — {total_streets} străzi inventariate. "
                f"Top nume, raritate, comparație națională."
            ),
            "og_url_path": f"/oras/{u['judet'].lower()}/{u['slug']}/",
        }
        _render(env, "uat-detail.html.j2",
                DIST / "oras" / u["judet"].lower() / u["slug"] / "index.html",
                portraits=portraits, **og, **detail)
    # Prune stale UAT directories left over from earlier, less-scoped builds.
    # The set of rendered UATs shrank when comune were excluded; without this
    # sweep, /oras/<judet>/<old-slug>/ would keep serving outdated pages.
    valid = {(u["judet"].lower(), u["slug"]) for u in uats}
    oras_dir = DIST / "oras"
    pruned = 0
    if oras_dir.exists():
        for jud_dir in oras_dir.iterdir():
            if not jud_dir.is_dir():
                continue
            for uat_dir in jud_dir.iterdir():
                if uat_dir.is_dir() and (jud_dir.name, uat_dir.name) not in valid:
                    shutil.rmtree(uat_dir)
                    pruned += 1
            if not any(jud_dir.iterdir()):
                jud_dir.rmdir()
    print(f"    → dist/oras/ ({len(uats)} pages, pruned {pruned} stale)")

    # ── Themes ───────────────────────────────────────────────────────────────
    themes = site_queries.enumerate_themes(conn)
    print(f"  Rendering {len(themes)} theme detail pages…")
    seen_t: dict[str, str] = {}
    for t in themes:
        slug = t["slug"]
        key = f"{t['type']}/{t['key']}"
        if slug in seen_t:
            print(f"  WARN: theme slug collision '{slug}'")
            continue
        seen_t[slug] = key
        detail = site_queries.theme_detail(conn, t["type"], t["key"])
        if not detail:
            continue
        theme_label = t.get("label") or t["key"]
        og = {
            "og_title": f"{theme_label} — Cum ne numim străzile",
            "og_description": (
                f"Străzi din România care poartă tema „{theme_label}”."
            ),
            "og_url_path": f"/tema/{slug}/",
        }
        _render(env, "theme-detail.html.j2",
                DIST / "tema" / slug / "index.html",
                portraits=portraits, theme_meta=t, **og, **detail)
    print(f"    → dist/tema/ ({len(themes)} pages)")

    # ── Index pages ──────────────────────────────────────────────────────────
    _render(env, "persons-index.html.j2",
            DIST / "persoane" / "index.html",
            persons=persons, portraits=portraits)
    print("    → dist/persoane/index.html")

    _render(env, "themes-index.html.j2",
            DIST / "teme" / "index.html",
            themes=themes)
    print("    → dist/teme/index.html")

    judete_list = sorted({u["judet"] for u in uats})
    section6_data = site_queries.section6(conn)
    section8_data = site_queries.section8(conn)
    _render(env, "judete-index.html.j2",
            DIST / "judete" / "index.html",
            section6=section6_data, section8=section8_data,
            judete=judete_list, uats=uats, portraits=portraits)
    print("    → dist/judete/index.html")
    _render(env, "judete-lista.html.j2",
            DIST / "judete" / "lista" / "index.html",
            judete=judete_list, uats=uats)
    print("    → dist/judete/lista/index.html")

    # ── Explorer JSON + page ─────────────────────────────────────────────────
    indexes = site_queries.explorer_indexes(conn)
    cauta_dir = DIST / "cauta"
    cauta_dir.mkdir(parents=True, exist_ok=True)
    (cauta_dir / "streets.json").write_text(
        json.dumps(indexes["streets"], ensure_ascii=False), encoding="utf-8")
    (cauta_dir / "uats.json").write_text(
        json.dumps(indexes["uats"], ensure_ascii=False), encoding="utf-8")
    _render(env, "explorer.html.j2",
            cauta_dir / "index.html")
    print(f"    → dist/cauta/ ({len(indexes['streets'])} streets, {len(indexes['uats'])} uats)")

    conn.close()
    total = len(streets) + len(persons) + len(uats) + len(themes) + 4
    print(f"  Detail build complete — {total} files written.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build street names static site")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument(
        "--variant",
        choices=["default", "v1", "v2", "methodology", "both", "all"],
        default="default",
        help="Which template to render (default = cluster cloud | v1 | v2 = dense | methodology | both = default+v2 | all)",
    )
    parser.add_argument("--serve", action="store_true", help="Build then serve on localhost")
    parser.add_argument("--port", type=int, default=8000, help="Port for --serve (default: 8000)")
    parser.add_argument("--detail", action="store_true", help="Also build per-entity detail pages")
    parser.add_argument("--detail-only", action="store_true", help="Build only detail pages, skip main index")
    args = parser.parse_args()
    if not args.detail_only:
        if args.variant == "both":
            variants = ["default", "v2"]
        elif args.variant == "all":
            variants = ["default", "v1", "v2", "methodology"]
        else:
            variants = [args.variant]
        for v in variants:
            build(db_path=args.db, variant=v)
    if args.detail or args.detail_only:
        build_detail_pages(db_path=args.db)
    if args.serve:
        import http.server
        import os
        import urllib.request
        import urllib.error

        FILTER_PORT = 8765  # filter_server.py default

        class SiteHandler(http.server.SimpleHTTPRequestHandler):
            """Static file server that proxies /api/* and /portraits/* to filter_server."""

            def log_message(self, fmt, *args):
                pass

            def _proxy(self, upstream: str) -> None:
                try:
                    with urllib.request.urlopen(upstream, timeout=10) as resp:
                        body = resp.read()
                        self.send_response(resp.status)
                        ct = resp.headers.get("Content-Type", "application/octet-stream")
                        self.send_header("Content-Type", ct)
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(body)
                except urllib.error.HTTPError as e:
                    self.send_response(e.code)
                    self.end_headers()
                except Exception:
                    self.send_response(502)
                    self.end_headers()

            def do_GET(self):
                path = self.path.split("?")[0]
                if path.startswith("/api/") or path.startswith("/portraits/"):
                    upstream = f"http://localhost:{FILTER_PORT}{self.path}"
                    self._proxy(upstream)
                else:
                    super().do_GET()

        os.chdir("dist")
        print(f"Serving at http://localhost:{args.port}  (API proxied → :{FILTER_PORT}) …")
        http.server.test(HandlerClass=SiteHandler, port=args.port, bind="127.0.0.1")


if __name__ == "__main__":
    main()
