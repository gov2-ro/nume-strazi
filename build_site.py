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
DEFAULT_SITE_URL = "https://strazi.gov2.ro"


def _normalize_base(raw: str) -> str:
    """Normalize a subdirectory base path: '' (root), '/strazi' (no trailing slash)."""
    raw = (raw or "").strip()
    if not raw or raw == "/":
        return ""
    raw = raw.rstrip("/")
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw

VARIANTS = {
    "default": ("index.html.j2", "index.html"),
    "v1": ("index-v1.html.j2", "index-v1.html"),
    "v2": ("index-v2.html.j2", "index-v2.html"),
    "methodology": ("metodologie.html.j2", "metodologie.html"),
}

# Static-content variants don't need any of the section query data.
STATIC_VARIANTS = {"methodology"}


def build(db_path: str = DB_PATH, variant: str = "default",
          base: str = "", site_url: str = DEFAULT_SITE_URL) -> None:
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
            "section_quirky": site_queries.section_quirky(conn),
            "municipii": site_queries.municipii_index(conn),
        }
        conn.close()

        portraits_dir = DIST / "portraits"
        data["portraits"] = [p.stem for p in sorted(portraits_dir.glob("*.jpg"))] \
            if portraits_dir.exists() else []

    env = _make_env(base=base, site_url=site_url)
    template_name, output_name = VARIANTS[variant]
    tmpl = env.get_template(template_name)
    html = tmpl.render(**data)

    out = DIST / output_name
    out.write_text(html, encoding="utf-8")
    print(f"  → {out}  ({out.stat().st_size // 1024} KB)")

    if COUNTIES_SRC.exists():
        shutil.copy(COUNTIES_SRC, DIST / "ro-counties.geojson")
        print(f"  → {DIST}/ro-counties.geojson")


def _make_env(base: str = "", site_url: str = DEFAULT_SITE_URL) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    env.filters["enumerate"] = enumerate
    env.globals["base"]     = base
    env.globals["site_url"] = site_url
    return env


def _render(env: jinja2.Environment, template_name: str, out_path: Path, **ctx) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env.get_template(template_name).render(**ctx), encoding="utf-8")


def build_browser_data(db_path: str = DB_PATH) -> None:
    """Generate dist/browser/data.json — pre-computed compact rows + meta."""
    conn = site_queries.get_connection(db_path)
    data = site_queries.browser_export(conn)
    conn.close()
    out = DIST / "browser" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding="utf-8")
    print(f"  → {out}  ({out.stat().st_size // 1024} KB)")


def build_detail_pages(db_path: str = DB_PATH,
                       base: str = "", site_url: str = DEFAULT_SITE_URL) -> None:
    """Render all per-entity detail pages and index pages into dist/."""
    conn = site_queries.get_connection(db_path)
    env = _make_env(base=base, site_url=site_url)
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
    parser.add_argument("--base", default="",
                        help="Subdirectory prefix for all internal URLs (e.g. '/strazi'). Default: empty (root).")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL,
                        help=f"Canonical site origin for OG/canonical URLs. Default: {DEFAULT_SITE_URL}")
    parser.add_argument("--mount", default="",
                        help="When using --serve, mount the dist tree under this path (e.g. '/strazi'). Default: '/'.")
    args = parser.parse_args()

    base     = _normalize_base(args.base)
    site_url = args.site_url.rstrip("/")
    mount    = _normalize_base(args.mount)

    if not args.detail_only:
        if args.variant == "both":
            variants = ["default", "v2"]
        elif args.variant == "all":
            variants = ["default", "v1", "v2", "methodology"]
        else:
            variants = [args.variant]
        for v in variants:
            build(db_path=args.db, variant=v, base=base, site_url=site_url)
        build_browser_data(args.db)
    if args.detail or args.detail_only:
        build_detail_pages(db_path=args.db, base=base, site_url=site_url)
    if args.serve:
        import http.server
        import os
        import urllib.request
        import urllib.error

        FILTER_PORT = 8765  # filter_server.py default
        MOUNT = mount  # captured from CLI; "" means root

        class SiteHandler(http.server.SimpleHTTPRequestHandler):
            """Static file server that proxies /api/* and /portraits/* to filter_server.
            If MOUNT is set, the dist tree is served under that prefix and any other
            path returns 404 — simulating a shared-host subdirectory deployment."""

            def log_message(self, fmt, *args):
                pass

            def _strip_mount(self) -> bool:
                """Strip MOUNT prefix from self.path. Return False if path doesn't match."""
                if not MOUNT:
                    return True
                qmark = self.path.find("?")
                pure = self.path if qmark < 0 else self.path[:qmark]
                qs   = self.path[qmark:] if qmark >= 0 else ""
                if pure == MOUNT or pure == MOUNT + "/":
                    self.path = "/" + qs
                    return True
                if pure.startswith(MOUNT + "/"):
                    self.path = pure[len(MOUNT):] + qs
                    return True
                return False

            def _send_404(self) -> None:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not found (outside mount)\n")

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

            def _serve_range(self) -> bool:
                """Honor a Range request for the current static file. Returns True if handled.
                Production hosts (Apache/Nginx) handle this natively; we need it locally
                so sql.js-httpvfs can fetch SQLite pages without pulling the whole DB."""
                range_hdr = self.headers.get("Range")
                if not range_hdr or not range_hdr.startswith("bytes="):
                    return False
                fpath = self.translate_path(self.path)
                if not os.path.isfile(fpath):
                    return False
                try:
                    size = os.path.getsize(fpath)
                    spec = range_hdr[len("bytes="):].strip()
                    start_s, _, end_s = spec.partition("-")
                    if start_s == "":
                        # suffix: last N bytes
                        n = int(end_s)
                        start, end = max(0, size - n), size - 1
                    else:
                        start = int(start_s)
                        end   = int(end_s) if end_s else size - 1
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return True
                    end = min(end, size - 1)
                    length = end - start + 1
                    ctype = self.guess_type(fpath)
                    with open(fpath, "rb") as f:
                        f.seek(start)
                        body = f.read(length)
                    self.send_response(206)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(length))
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(body)
                    return True
                except (ValueError, OSError):
                    return False

            def end_headers(self):
                # advertise range support on every static response
                if "Accept-Ranges" not in self._headers_buffer_str():
                    self.send_header("Accept-Ranges", "bytes")
                super().end_headers()

            def _headers_buffer_str(self) -> str:
                return b"".join(self._headers_buffer).decode("latin-1", "replace")

            def do_GET(self):
                if not self._strip_mount():
                    self._send_404(); return
                path = self.path.split("?")[0]
                if path.startswith("/api/"):
                    upstream = f"http://localhost:{FILTER_PORT}{self.path}"
                    self._proxy(upstream)
                    return
                if self._serve_range():
                    return
                super().do_GET()

            def do_HEAD(self):
                if not self._strip_mount():
                    self._send_404(); return
                path = self.path.split("?")[0]
                if path.startswith("/api/"):
                    self.send_response(200); self.end_headers()
                    return
                super().do_HEAD()

        os.chdir("dist")
        mount_msg = f"  mount={MOUNT}" if MOUNT else ""
        print(f"Serving at http://localhost:{args.port}{MOUNT}/  (API proxied → :{FILTER_PORT}){mount_msg} …")
        http.server.test(HandlerClass=SiteHandler, port=args.port, bind="127.0.0.1")


if __name__ == "__main__":
    main()
