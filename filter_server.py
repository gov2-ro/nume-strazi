#!/usr/bin/env python3
"""
filter_server.py — Exploratory filter API for streets.db

Routes:
  GET /          → dist/filter/index.html
  GET /api/meta  → enum values for every filter dimension
  GET /api/filter → parameterized filter query, paginated JSON

Usage:
  python3 filter_server.py [--port 8765] [--db data/streets.db]
"""
import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from streets_lib import fix_diacritics, slugify

DB_PATH = "data/streets.db"
UI_PATH = Path("dist/filter/index.html")

_BASE_FROM = """
FROM streets_dedup sd
LEFT JOIN persons         p  ON p.core_name_norm  = sd.core_name_norm
LEFT JOIN name_categories c  ON c.core_name_norm  = sd.core_name_norm
LEFT JOIN nature_terms    n  ON n.core_name_norm  = sd.core_name_norm
LEFT JOIN place_refs      pr ON pr.core_name_norm = sd.core_name_norm
"""

_SELECT_COLS = """
    sd.name,
    sd.street_type,
    sd.uat,
    sd.judet,
    sd.siruta,
    sd.core_name,
    sd.name_normalized,
    CASE
        WHEN sd.is_numeric = 1             THEN 'numeric'
        WHEN sd.is_date    = 1             THEN 'date'
        WHEN sd.is_saint   = 1             THEN 'saint'
        WHEN p.core_name_norm  IS NOT NULL THEN 'person'
        WHEN n.core_name_norm  IS NOT NULL THEN 'nature'
        WHEN c.core_name_norm  IS NOT NULL THEN 'category'
        WHEN pr.core_name_norm IS NOT NULL THEN 'place'
        ELSE NULL
    END AS classification,
    p.full_name   AS person_full_name,
    p.profession,
    p.nationality,
    p.gender,
    p.era,
    p.wiki_scope,
    c.category,
    c.subcategory,
    n.nature_type,
    pr.place_type,
    pr.country    AS place_country
"""

_CLS_MAP = {
    'person':   'p.core_name_norm IS NOT NULL',
    'nature':   'n.core_name_norm IS NOT NULL',
    'place':    'pr.core_name_norm IS NOT NULL',
    'category': 'c.core_name_norm IS NOT NULL',
    'saint':    'sd.is_saint = 1',
    'date':     'sd.is_date = 1',
    'numeric':  'sd.is_numeric = 1',
}

_PERSON_COLS = ('profession', 'nationality', 'gender', 'era', 'wiki_scope')


def build_filter_query(params: dict) -> tuple[str, list]:
    """
    Build (where_clause, bind_values) from parsed query params.
    params: dict of str -> list[str] (multi-value already parsed).
    Returns '' for where_clause when no filters are active.
    All values go through ? placeholders — no string interpolation.
    """
    conditions: list[str] = []
    values: list = []

    if judete := params.get('judet'):
        conditions.append(f"sd.judet IN ({', '.join('?' * len(judete))})")
        values.extend(judete)

    if uat := params.get('uat'):
        conditions.append("sd.uat LIKE ?")
        values.append(f"%{uat[0].upper()}%")

    if stypes := params.get('street_type'):
        conditions.append(f"sd.street_type IN ({', '.join('?' * len(stypes))})")
        values.extend(stypes)

    if cls := params.get('classification'):
        parts = [_CLS_MAP[c] for c in cls if c in _CLS_MAP]
        if parts:
            conditions.append(f"({' OR '.join(parts)})")

    if any(params.get(f) for f in _PERSON_COLS):
        conditions.append('p.core_name_norm IS NOT NULL')
        for col in _PERSON_COLS:
            if vals := params.get(col):
                conditions.append(f"p.{col} IN ({', '.join('?' * len(vals))})")
                values.extend(vals)

    if cats := params.get('category'):
        conditions.append('c.core_name_norm IS NOT NULL')
        conditions.append(f"c.category IN ({', '.join('?' * len(cats))})")
        values.extend(cats)

    if subcats := params.get('subcategory'):
        conditions.append('c.core_name_norm IS NOT NULL')
        conditions.append(f"c.subcategory IN ({', '.join('?' * len(subcats))})")
        values.extend(subcats)

    if ntypes := params.get('nature_type'):
        conditions.append('n.core_name_norm IS NOT NULL')
        conditions.append(f"n.nature_type IN ({', '.join('?' * len(ntypes))})")
        values.extend(ntypes)

    if ptypes := params.get('place_type'):
        conditions.append('pr.core_name_norm IS NOT NULL')
        conditions.append(f"pr.place_type IN ({', '.join('?' * len(ptypes))})")
        values.extend(ptypes)

    if pcountries := params.get('place_country'):
        conditions.append('pr.core_name_norm IS NOT NULL')
        conditions.append(f"pr.country IN ({', '.join('?' * len(pcountries))})")
        values.extend(pcountries)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, values


def get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query_meta(conn: sqlite3.Connection) -> dict:
    def distinct(sql):
        return [r[0] for r in conn.execute(sql)]

    return {
        'judete': distinct(
            "SELECT DISTINCT judet FROM streets_dedup WHERE judet IS NOT NULL ORDER BY judet"),
        'street_types': distinct(
            "SELECT DISTINCT street_type FROM streets_dedup WHERE street_type IS NOT NULL ORDER BY street_type"),
        'classifications': [
            'person', 'nature', 'place', 'category', 'saint', 'date', 'numeric'
        ],
        'professions': distinct(
            "SELECT DISTINCT profession FROM persons WHERE profession IS NOT NULL ORDER BY profession"),
        'nationalities': distinct(
            "SELECT DISTINCT nationality FROM persons WHERE nationality IS NOT NULL ORDER BY nationality"),
        'genders': distinct(
            "SELECT DISTINCT gender FROM persons WHERE gender IS NOT NULL ORDER BY gender"),
        'eras': distinct(
            "SELECT DISTINCT era FROM persons WHERE era IS NOT NULL ORDER BY era"),
        'wiki_scopes': distinct(
            "SELECT DISTINCT wiki_scope FROM persons WHERE wiki_scope IS NOT NULL ORDER BY wiki_scope"),
        'categories': distinct(
            "SELECT DISTINCT category FROM name_categories WHERE category IS NOT NULL ORDER BY category"),
        'subcategories': distinct(
            "SELECT DISTINCT subcategory FROM name_categories WHERE subcategory IS NOT NULL ORDER BY subcategory"),
        'nature_types': distinct(
            "SELECT DISTINCT nature_type FROM nature_terms WHERE nature_type IS NOT NULL ORDER BY nature_type"),
        'place_types': distinct(
            "SELECT DISTINCT place_type FROM place_refs WHERE place_type IS NOT NULL ORDER BY place_type"),
        'place_countries': distinct(
            "SELECT DISTINCT country FROM place_refs WHERE country IS NOT NULL ORDER BY country"),
    }


def query_filter(conn: sqlite3.Connection, params: dict) -> dict:
    limit = min(int((params.get('limit') or ['200'])[0]), 1000)
    offset = int((params.get('offset') or ['0'])[0])

    where, values = build_filter_query(params)

    count_sql = f"SELECT COUNT(*) {_BASE_FROM} {where}"
    total = conn.execute(count_sql, values).fetchone()[0]

    select_sql = (
        f"SELECT {_SELECT_COLS} {_BASE_FROM} {where} "
        f"ORDER BY sd.judet, sd.uat, sd.name LIMIT ? OFFSET ?"
    )
    rows = conn.execute(select_sql, [*values, limit, offset]).fetchall()

    def serialize(r: sqlite3.Row) -> dict:
        d = dict(r)
        core = d.pop('core_name', None)
        name_norm = d.get('name_normalized', '')
        d['street_slug'] = slugify(core or name_norm)
        d['uat_slug'] = slugify(fix_diacritics(d.get('uat') or ''))
        return d

    return {
        'total': total,
        'limit': limit,
        'offset': offset,
        'rows': [serialize(r) for r in rows],
    }


def make_handler(conn: sqlite3.Connection):
    class FilterHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # silence per-request access log

        def send_json(self, data, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip('/')

            if path in ('', '/filter'):
                if not UI_PATH.exists():
                    self.send_json({'error': f'{UI_PATH} not found — run build_site.py first'}, 503)
                    return
                html = UI_PATH.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)

            elif path == '/api/meta':
                try:
                    self.send_json(query_meta(conn))
                except Exception as exc:
                    self.send_json({'error': str(exc)}, 500)

            elif path == '/api/filter':
                try:
                    params = parse_qs(parsed.query, keep_blank_values=False)
                    self.send_json(query_filter(conn, params))
                except Exception as exc:
                    self.send_json({'error': str(exc)}, 500)

            else:
                self.send_json({'error': 'not found'}, 404)

    return FilterHandler


def main() -> None:
    parser = argparse.ArgumentParser(description='Filter API server for streets.db')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default=DB_PATH)
    args = parser.parse_args()

    conn = get_db(args.db)
    handler = make_handler(conn)
    server = HTTPServer(('localhost', args.port), handler)
    print(f'Filter server → http://localhost:{args.port}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
