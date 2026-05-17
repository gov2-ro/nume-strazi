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
