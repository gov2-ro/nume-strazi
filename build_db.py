"""Rebuild SQLite with full feature extraction + curated table scaffolds.

Layers in `streets`:
  artera_raw       - original
  street_type      - 'Strada', 'Aleea', ...
  name             - display form (post-1993 diacritics, original â/î preserved)
  name_normalized  - lowercase ASCII, î≡â collapsed (matching key)
  title            - 'Prof.', 'Învățător', ...
  rank             - 'General', 'Voievod', ...
  is_saint, is_date, is_numeric  (0/1 flags)
  core_name        - name with title/rank/saint prefixes stripped
  core_name_norm   - normalized version of core_name (the join key for `persons`)
"""
import csv, openpyxl, sqlite3, re
from pathlib import Path

from streets_lib import (
    DIACRITIC_FIX, fix_diacritics, normalize_match, STREET_TYPES,
    parse_artery, extract_features,
)

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--limit", type=int, default=None)
_ap.add_argument("--src", default="data/reference/registrul sectiilor de vot 14.05.2025.xlsx")
_ap.add_argument("--db",  default="data/streets.db")
_args = _ap.parse_args()

SRC = Path(_args.src)
DB  = Path(_args.db)
LIMIT = _args.limit
if DB.exists(): DB.unlink()

# normalization helpers (DIACRITIC_FIX, fix_diacritics, normalize_match),
# STREET_TYPES, and feature extraction (parse_artery, extract_features) live
# in streets_lib so the OSM/postal enrichment tools can reuse them.

# ---------- schema ----------
con = sqlite3.connect(DB)
con.executescript("""
CREATE TABLE streets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judet TEXT NOT NULL,
    uat TEXT NOT NULL,
    siruta INTEGER,
    artera_raw TEXT NOT NULL,
    street_type TEXT,
    name TEXT,
    name_normalized TEXT,
    title TEXT,
    rank TEXT,
    is_saint INTEGER NOT NULL DEFAULT 0,
    is_date INTEGER NOT NULL DEFAULT 0,
    is_numeric INTEGER NOT NULL DEFAULT 0,
    core_name TEXT,
    core_name_norm TEXT
);
CREATE TABLE street_aliases (
    street_id INTEGER NOT NULL REFERENCES streets(id),
    alias TEXT NOT NULL,
    alias_normalized TEXT NOT NULL
);

-- ===== Curated lookup tables (scaffolds) =====
CREATE TABLE name_categories (
    core_name_norm TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    subcategory TEXT,
    notes TEXT
);
CREATE TABLE persons (
    core_name_norm TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    gender TEXT,
    birth_year INTEGER,
    death_year INTEGER,
    era TEXT,
    profession TEXT,
    nationality TEXT DEFAULT 'RO',
    wikidata_qid TEXT,
    wiki_sitelinks INTEGER,
    wiki_scope TEXT,
    wiki_ro_url TEXT,
    wiki_en_url TEXT,
    wiki_ro_views INTEGER,
    birth_place_qid TEXT,
    birth_place_label TEXT,
    birth_judet TEXT,
    cause_of_death_qid TEXT,
    cause_of_death_label TEXT,
    notes TEXT
);
CREATE TABLE place_refs (
    core_name_norm TEXT PRIMARY KEY,
    place_name TEXT NOT NULL,
    place_type TEXT,
    country TEXT DEFAULT 'RO',
    notes TEXT
);
CREATE TABLE nature_terms (
    core_name_norm TEXT PRIMARY KEY,
    term TEXT NOT NULL,
    nature_type TEXT,
    notes TEXT
);

-- ===== OSM enrichment scaffolds (populated by tools/osm_*.py) =====
-- One logical street per (uat_siruta, name_normalized). OSM splits a single
-- street into many `way` rows at every junction; tools/osm_ingest.py groups
-- those before insert, so this table mirrors electoral_dedup's grain.
CREATE TABLE osm_streets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uat_siruta INTEGER NOT NULL,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    street_type TEXT,               -- best-effort, via streets_lib.strip_street_type
    title TEXT,
    rank TEXT,
    is_saint INTEGER NOT NULL DEFAULT 0,
    is_date INTEGER NOT NULL DEFAULT 0,
    is_numeric INTEGER NOT NULL DEFAULT 0,
    core_name TEXT,
    core_name_norm TEXT,
    highway_class TEXT NOT NULL,
    ref TEXT,
    length_m REAL NOT NULL,
    segment_count INTEGER,         -- contributing OSM ways, materialized from way_ids
    way_ids TEXT NOT NULL,         -- JSON array of contributing OSM way ids
    geometry_wkt TEXT,
    importance_v1 REAL,            -- raw score from tools/osm_score.py
    importance_v1_uat_z REAL,      -- z-score within UAT
    UNIQUE (uat_siruta, name_normalized)
);
CREATE INDEX ix_osm_uat       ON osm_streets(uat_siruta);
CREATE INDEX ix_osm_namenorm  ON osm_streets(name_normalized);
CREATE INDEX ix_osm_corenorm  ON osm_streets(core_name_norm);

-- OSM admin_level=8 boundary polygons resolved to SIRUTA, built by
-- tools/osm_boundaries.py. This is what tools/osm_ingest.py assigns ways to;
-- it deliberately covers every UAT OSM knows about, not only those the
-- electoral source lists. Build-time only — dropped from the shipped dist DB.
CREATE TABLE uat_boundaries (
    siruta        INTEGER PRIMARY KEY,
    osm_rel_id    INTEGER,
    osm_name      TEXT,
    admin_level   INTEGER,
    match_method  TEXT NOT NULL,   -- centroid_in_polygon | bucharest_sector | name_unique
    area_km2      REAL,
    geometry_wkt  TEXT NOT NULL
);

CREATE TABLE street_osm_matches (
    street_id INTEGER NOT NULL REFERENCES streets(id),
    osm_street_id INTEGER NOT NULL REFERENCES osm_streets(id),
    match_type TEXT NOT NULL,      -- 'exact_type_core' | 'fuzzy_core_name'
    confidence REAL NOT NULL,
    PRIMARY KEY (street_id, osm_street_id)
);
CREATE INDEX ix_match_osm     ON street_osm_matches(osm_street_id);

-- ===== Postal registry scaffolds (populated by tools/postal_*.py) =====
-- Source: data/reference/coduri-postale+/infocod-cu-siruta-mai-2016.xlsx
-- (Bucuresti + Localitati peste 50.000 loc sheets only — the sub-50.000 sheet
-- has no street-level columns, a structural gap this source can't close; see
-- CODE_SPEC §12). One row per (uat_siruta, name_normalized), same grain as
-- osm_streets/electoral_dedup. `name` excludes the street-type prefix (the
-- source already separates Tip artera/Denumire artera), unlike osm_streets.
CREATE TABLE postal_streets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_sheet TEXT NOT NULL,           -- 'Bucuresti' | 'Localitati peste 50.000 loc'
    source_row_ids TEXT NOT NULL,         -- JSON array of contributing raw row indices
    judet_raw TEXT,
    localitate_raw TEXT,
    uat_siruta INTEGER,                   -- resolved & validated against streets.siruta; NULL = unresolved
    resolution_method TEXT NOT NULL,      -- 'direct_sector' | 'direct_sirsup' | 'name_match_exact'
                                           -- | 'name_match_fuzzy' | 'unresolved'
    resolution_confidence REAL NOT NULL,
    tip_artera_raw TEXT,
    street_type TEXT,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    title TEXT,
    rank TEXT,
    is_saint INTEGER NOT NULL DEFAULT 0,
    is_date INTEGER NOT NULL DEFAULT 0,
    is_numeric INTEGER NOT NULL DEFAULT 0,
    core_name TEXT,
    core_name_norm TEXT,
    core_name_norm_swapped TEXT,          -- 2-token reorder of core_name_norm, else NULL
    UNIQUE (uat_siruta, name_normalized)
);
CREATE INDEX ix_postal_uat      ON postal_streets(uat_siruta);
CREATE INDEX ix_postal_namenorm ON postal_streets(name_normalized);
CREATE INDEX ix_postal_corenorm ON postal_streets(core_name_norm);
CREATE INDEX ix_postal_swapped  ON postal_streets(core_name_norm_swapped);

CREATE TABLE street_postal_matches (
    street_id INTEGER NOT NULL REFERENCES streets(id),
    postal_street_id INTEGER NOT NULL REFERENCES postal_streets(id),
    match_type TEXT NOT NULL,      -- 'exact_type_core' | 'fuzzy_core_name' | 'reordered_core_name'
    confidence REAL NOT NULL,
    PRIMARY KEY (street_id, postal_street_id)
);
CREATE INDEX ix_pmatch_postal ON street_postal_matches(postal_street_id);

-- ===== RENNS (ANCPI cadastral street registry) scaffolds (populated by tools/renns_*.py) =====
-- Source: https://renns.ancpi.ro (Registrul Electronic Național al Nomenclaturii
-- Stradale) "Drumuri" endpoint. One row per (uat_siruta, name_normalized), same
-- grain as osm_streets/postal_streets. `name` excludes the street-type prefix
-- (RENNS separates roadType/name already), like postal_streets. uat_siruta is
-- the RENNS uat.id verbatim — validated 3180/3181 against the electoral
-- source's own SIRUTA codes, so (unlike postal) no name-matching fallback is needed; the
-- rare miss is left NULL. See CODE_SPEC §13.
CREATE TABLE renns_streets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_road_ids TEXT NOT NULL,        -- JSON array of contributing RENNS road ids
    uat_siruta INTEGER,                   -- = RENNS uat.id; NULL only for the rare unresolved case
    judet TEXT,                           -- RENNS county.shortName (fix_diacritics'd)
    locality_raw TEXT,                    -- first-seen locality.name; debug aid only, not resolved further
    road_type_raw TEXT,                   -- original roadType.name (messy; 90 distinct raw values)
    street_type TEXT,                     -- cleaned via ROAD_TYPE_MAP; NULL for rural/unclassified codes
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    title TEXT,
    rank TEXT,
    is_saint INTEGER NOT NULL DEFAULT 0,
    is_date INTEGER NOT NULL DEFAULT 0,
    is_numeric INTEGER NOT NULL DEFAULT 0,
    core_name TEXT,
    core_name_norm TEXT,
    road_status TEXT,                     -- roadStatus.name; always 'Publicat' in the full dataset today
    UNIQUE (uat_siruta, name_normalized)
);
CREATE INDEX ix_renns_uat      ON renns_streets(uat_siruta);
CREATE INDEX ix_renns_namenorm ON renns_streets(name_normalized);
CREATE INDEX ix_renns_corenorm ON renns_streets(core_name_norm);

CREATE TABLE street_renns_matches (
    street_id INTEGER NOT NULL REFERENCES streets(id),
    renns_street_id INTEGER NOT NULL REFERENCES renns_streets(id),
    match_type TEXT NOT NULL,      -- 'exact_type_core' | 'fuzzy_core_name'
    confidence REAL NOT NULL,
    PRIMARY KEY (street_id, renns_street_id)
);
CREATE INDEX ix_rmatch_renns ON street_renns_matches(renns_street_id);

CREATE INDEX ix_streets_judet     ON streets(judet);
CREATE INDEX ix_streets_uat       ON streets(uat);
CREATE INDEX ix_streets_namenorm  ON streets(name_normalized);
CREATE INDEX ix_streets_corenorm  ON streets(core_name_norm);
CREATE INDEX ix_streets_type      ON streets(street_type);
CREATE INDEX ix_streets_flags     ON streets(is_saint, is_date, is_numeric);
-- Composite index allows the optimizer to push WHERE siruta=? into electoral_dedup.
CREATE INDEX ix_streets_siruta_name ON streets(siruta, name_normalized);
-- Supports the cross-source anti-join in the external_corroboration_gap query
-- (docs/queries.sql) — without it, that query falls back to a slow scan.
CREATE INDEX ix_streets_siruta_corenorm ON streets(siruta, core_name_norm);
CREATE INDEX ix_aliases_norm      ON street_aliases(alias_normalized);

-- National SIRUTA -> (judet, uat-name) reference, used only to label
-- all_street_names rows for UATs the electoral source has zero data for (its
-- own judet/uat columns are preferred wherever available).
-- Loaded from data/gis/populatie-romania-siruta-coords.csv (3,180 UATs) plus
-- the 6 Bucharest sectors hardcoded below (missing from that CSV; centroids
-- for the same 6 are hardcoded the same way in tools/osm_ingest.py).
-- Validated: resolves 2,258/2,264 (99.7%) of every SIRUTA our 4 sources
-- actually reference; the 6 misses are exactly those Bucharest sectors.
-- uat names here are not COMUNA/ORAȘ/MUNICIPIUL-prefixed like the electoral
-- source's own (that prefix isn't derivable from the CSV) — a cosmetic gap,
-- only affects UATs the electoral source itself has zero rows for.
CREATE TABLE uat_reference (
    siruta INTEGER PRIMARY KEY,
    judet TEXT,
    uat TEXT
);

-- GROUP BY siruta (not uat) is intentional: 48 UAT names are shared across
-- multiple județe and would be incorrectly merged if grouped by name alone.
-- street_type is part of the dedup key: a UAT can legitimately have both
-- "Bulevardul X" and "Strada X" as two distinct real streets sharing a core
-- name — grouping by name_normalized alone (which never included the type
-- for electoral-source rows, stripped upstream in parse_artery()) silently
-- merged these. Fixed 2026-07-08 after finding 2,479 (siruta, name_normalized)
-- groups with 2+ distinct street_types — see CODE_SPEC and activity-history.
-- Deduplicates only the electoral (AEP polling-section) source — one of 4
-- sources this project tracks, no more authoritative than the others (see
-- all_street_names below). Kept as its own view because it's the one source
-- with a stable per-row `id` that the OSM/postal/RENNS match tables join
-- against.
CREATE VIEW electoral_dedup AS
SELECT MIN(id) AS id, judet, uat, siruta, street_type, name, name_normalized,
       title, rank, is_saint, is_date, is_numeric, core_name, core_name_norm
FROM streets
WHERE name_normalized != ''
GROUP BY siruta, name_normalized, street_type;

CREATE VIEW streets_classified_pct AS
-- One row per distinct core_name_norm (non-null).
-- classification: first matching bucket; NULL means unclassified.
-- street_count: number of (uat, name) pairs sharing this core_name_norm.
-- Query this view grouped by classification for curation coverage reports.
WITH base AS (
  SELECT core_name_norm,
    MAX(is_numeric) AS is_numeric,
    MAX(is_date)    AS is_date,
    MAX(is_saint)   AS is_saint,
    COUNT(*)        AS street_count
  FROM electoral_dedup
  WHERE core_name_norm IS NOT NULL
  GROUP BY core_name_norm
)
SELECT
  b.core_name_norm,
  b.street_count,
  CASE
    WHEN b.is_numeric  = 1             THEN 'numeric'
    WHEN b.is_date     = 1             THEN 'date'
    WHEN b.is_saint    = 1             THEN 'saint'
    WHEN p.core_name_norm  IS NOT NULL THEN 'person'
    WHEN n.core_name_norm  IS NOT NULL THEN 'nature'
    WHEN c.core_name_norm  IS NOT NULL THEN 'category'
    WHEN pr.core_name_norm IS NOT NULL THEN 'place'
    ELSE NULL
  END AS classification
FROM base b
LEFT JOIN persons         p  ON p.core_name_norm  = b.core_name_norm
LEFT JOIN nature_terms    n  ON n.core_name_norm  = b.core_name_norm
LEFT JOIN name_categories c  ON c.core_name_norm  = b.core_name_norm
LEFT JOIN place_refs      pr ON pr.core_name_norm = b.core_name_norm;

-- Additive consolidation of all 4 street-name sources: electoral (full
-- attributes, from the AEP polling-section source) + streets OSM/postal/RENNS
-- found that have no electoral match. Anchored on the electoral source only
-- because it's the one source with stable per-row ids feeding the match
-- tables (street_osm_matches/street_postal_matches/street_renns_matches) — a
-- pre-existing implementation detail, not a claim that it outranks the
-- others (see all_street_names below, and CODE_SPEC §13.8). Does not touch
-- electoral_dedup. Cross-source comparison must join on core_name_norm,
-- never name_normalized — osm_streets.name_normalized includes the
-- street-type prefix, postal's/RENNS's and the electoral source's don't.
-- See CODE_SPEC §12, §13.
CREATE VIEW streets_all_sources AS
SELECT 'electoral' AS source, sd.id, sd.judet, sd.uat, sd.siruta, sd.street_type, sd.name,
       sd.name_normalized, sd.title, sd.rank, sd.is_saint, sd.is_date, sd.is_numeric,
       sd.core_name, sd.core_name_norm, NULL AS source_note
FROM electoral_dedup sd

UNION ALL

SELECT 'osm', NULL, su.judet, su.uat, o.uat_siruta, o.street_type, o.name, o.name_normalized,
       o.title, o.rank, o.is_saint, o.is_date, o.is_numeric, o.core_name, o.core_name_norm,
       'highway=' || o.highway_class
FROM osm_streets o
LEFT JOIN (SELECT DISTINCT siruta, judet, uat FROM streets) su ON su.siruta = o.uat_siruta
WHERE NOT EXISTS (SELECT 1 FROM street_osm_matches m WHERE m.osm_street_id = o.id)

UNION ALL

SELECT 'postal', NULL, su.judet, su.uat, p.uat_siruta, p.street_type, p.name, p.name_normalized,
       p.title, p.rank, p.is_saint, p.is_date, p.is_numeric, p.core_name, p.core_name_norm,
       'sheet=' || p.source_sheet
FROM postal_streets p
LEFT JOIN (SELECT DISTINCT siruta, judet, uat FROM streets) su ON su.siruta = p.uat_siruta
WHERE p.uat_siruta IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM street_postal_matches m WHERE m.postal_street_id = p.id)

UNION ALL

SELECT 'renns', NULL, su.judet, su.uat, r.uat_siruta, r.street_type, r.name, r.name_normalized,
       r.title, r.rank, r.is_saint, r.is_date, r.is_numeric, r.core_name, r.core_name_norm,
       'roadType=' || COALESCE(r.road_type_raw, '?')
FROM renns_streets r
LEFT JOIN (SELECT DISTINCT siruta, judet, uat FROM streets) su ON su.siruta = r.uat_siruta
WHERE r.uat_siruta IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM street_renns_matches m WHERE m.renns_street_id = r.id);

-- The true deduplicated master list of "every distinct street name in
-- Romania, from any of the 4 sources" — unlike streets_all_sources (which
-- keeps one row PER SOURCE for external-only streets, so 2-3 sources
-- agreeing on the same electoral-missing street produce 2-3 rows), this view
-- collapses cross-source duplicates and keeps every contributing source's
-- exact name in `variants` (JSON) rather than silently discarding the losers.
-- `corroboration_count` is how many of the 4 sources have this exact street;
-- higher is a stronger signal the street genuinely exists. streets_all_sources
-- is kept as-is for its existing narrower per-source gap-analysis queries
-- (postal_only_streets, renns_only_streets, ...) — this view is the one to
-- use for "give me every Romanian street name, deduplicated."
--
-- Fully symmetric across all 4 sources (revised 2026-07-08, replacing an
-- earlier registry/external "layer" split): the electoral source is pooled
-- into the same UNION ALL as OSM/postal/RENNS and grouped by exactly the
-- same key, (siruta, street_type, core_name_norm) — same invariant as
-- electoral_dedup, a UAT can have both "Bulevardul X" and "Strada X" as
-- genuinely distinct streets, but not two "Strada X"s. This is NOT the same
-- thing as routing through street_osm_matches/street_postal_matches/
-- street_renns_matches (those keep their own independent match tiers,
-- including a type-blind fuzzy_core_name fallback, for their own
-- coverage-report purposes) — here, deliberately, there's no fuzzy/type-blind
-- fallback at all: two entries that share a core name but disagree on
-- street_type are NEVER auto-merged, since that's exactly the ambiguity
-- "type is identity" was meant to resolve (is it one street two sources
-- mislabeled, or two real streets that happen to share a name? not
-- decidable from the data alone). See the `type_variant_candidates` query
-- in docs/queries.sql for surfacing those cases for manual review instead
-- of guessing. `in_electoral` (0/1) replaces the old layer column's
-- practical use (filtering "not in the electoral source") — the electoral
-- source is just one of the 4 contributing sources here, not a special
-- anchor; no source is treated as higher-priority than another (2026-07-08 decision,
-- reversing an earlier RENNS > OSM > postal ranking) — when sources
-- disagree on exact spelling within an otherwise-identical group, the
-- representative name/core_name is simply the alphabetically-first one
-- (MIN()); `variants` retains every source's exact spelling regardless.
--
-- Numeric streets (core_name_norm IS NULL, e.g. rural cadastral "184") have
-- no meaningful cross-source join key — grouping by (siruta, street_type,
-- core_name_norm) would collapse every numeric street in a UAT into one
-- fake merged row, since SQL GROUP BY treats all NULLs as equal. Falls back
-- to grouping by exact `name` instead in that case (COALESCE below) — two
-- sources both listing "184" of the same type in the same UAT still
-- corroborate each other, but "184" and "185" correctly stay separate.
CREATE VIEW all_street_names AS
WITH all_entries AS (
  SELECT 'electoral' AS source, sd.siruta, sd.street_type, sd.name,
         sd.core_name, sd.core_name_norm, sd.is_saint, sd.is_date, sd.is_numeric
    FROM electoral_dedup sd
  UNION ALL
  SELECT 'osm', o.uat_siruta, o.street_type, o.name,
         o.core_name, o.core_name_norm, o.is_saint, o.is_date, o.is_numeric
    FROM osm_streets o
  UNION ALL
  SELECT 'postal', p.uat_siruta, p.street_type, p.name,
         p.core_name, p.core_name_norm, p.is_saint, p.is_date, p.is_numeric
    FROM postal_streets p
   WHERE p.uat_siruta IS NOT NULL
  UNION ALL
  SELECT 'renns', r.uat_siruta, r.street_type, r.name,
         r.core_name, r.core_name_norm, r.is_saint, r.is_date, r.is_numeric
    FROM renns_streets r
),
grouped AS (
  SELECT siruta, street_type, COALESCE(core_name_norm, name) AS group_key,
         MIN(name) AS name, MIN(core_name) AS core_name, MIN(core_name_norm) AS core_name_norm,
         json_group_array(json_object('source', source, 'name', name, 'street_type', street_type)) AS variants,
         COUNT(DISTINCT source) AS corroboration_count,
         MAX(CASE WHEN source = 'electoral' THEN 1 ELSE 0 END) AS in_electoral,
         MAX(is_saint) AS is_saint, MAX(is_date) AS is_date, MAX(is_numeric) AS is_numeric
    FROM all_entries
   GROUP BY siruta, street_type, COALESCE(core_name_norm, name)
)
SELECT COALESCE(su.judet, ur.judet) AS judet,
       COALESCE(su.uat, ur.uat) AS uat,
       g.siruta, g.street_type, g.name, g.core_name, g.core_name_norm,
       g.is_saint, g.is_date, g.is_numeric, g.in_electoral,
       g.corroboration_count, g.variants
  FROM grouped g
  LEFT JOIN (SELECT DISTINCT siruta, judet, uat FROM streets) su ON su.siruta = g.siruta
  LEFT JOIN uat_reference ur ON ur.siruta = g.siruta;
""")

# ---------- ingest ----------
wb = openpyxl.load_workbook(SRC, read_only=True)
ws = wb[wb.sheetnames[0]]
inserted = 0
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0: continue
    if row[0] is None: break
    if LIMIT and inserted >= LIMIT: break
    judet, uat, siruta = row[0], row[1], row[2]
    artera = row[10]
    if not artera: continue
    st, name, aliases = parse_artery(artera)
    feats = extract_features(name)
    cur = con.execute("""
        INSERT INTO streets (judet, uat, siruta, artera_raw, street_type, name,
            name_normalized, title, rank, is_saint, is_date, is_numeric,
            core_name, core_name_norm)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (judet, uat, siruta, artera, st, name,
          normalize_match(name), feats["title"], feats["rank"],
          feats["is_saint"], feats["is_date"], feats["is_numeric"],
          feats["core_name"], normalize_match(feats["core_name"]) if feats["core_name"] else None))
    sid = cur.lastrowid
    for a in aliases:
        con.execute("INSERT INTO street_aliases(street_id,alias,alias_normalized) VALUES (?,?,?)",
                    (sid, a, normalize_match(a)))
    inserted += 1

# ---------- uat_reference (SIRUTA -> judet/uat label, for all_street_names) ----------
GIS_SIRUTA_CSV = Path("data/gis/populatie-romania-siruta-coords.csv")
if GIS_SIRUTA_CSV.exists():
    with GIS_SIRUTA_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = row["siruta"].strip()
            if not s:
                continue
            con.execute(
                "INSERT OR IGNORE INTO uat_reference (siruta, judet, uat) VALUES (?,?,?)",
                (int(s), row["cod_judet"].strip(), fix_diacritics(row["localitate"].strip().upper())),
            )
# Missing from the CSV above; same 6 sectors are hardcoded in tools/osm_ingest.py.
for _siruta, _n in [(179141,1),(179150,2),(179169,3),(179178,4),(179187,5),(179196,6)]:
    con.execute(
        "INSERT OR IGNORE INTO uat_reference (siruta, judet, uat) VALUES (?,?,?)",
        (_siruta, "B", f"BUCUREȘTI SECTORUL {_n}"),
    )

con.commit()
def n(sql): return con.execute(sql).fetchone()[0]
print(f"Inserted     {inserted}")
print(f"Aliases      {n('SELECT COUNT(*) FROM street_aliases')}")
print(f"Deduped      {n('SELECT COUNT(*) FROM electoral_dedup')}")
print(f"Saints       {n('SELECT COUNT(*) FROM electoral_dedup WHERE is_saint=1')}")
print(f"Dates        {n('SELECT COUNT(*) FROM electoral_dedup WHERE is_date=1')}")
print(f"Numeric      {n('SELECT COUNT(*) FROM electoral_dedup WHERE is_numeric=1')}")
print(f"With title   {n('SELECT COUNT(*) FROM electoral_dedup WHERE title IS NOT NULL')}")
print(f"With rank    {n('SELECT COUNT(*) FROM electoral_dedup WHERE rank IS NOT NULL')}")
print(f"UAT reference {n('SELECT COUNT(*) FROM uat_reference')}")
con.close()
