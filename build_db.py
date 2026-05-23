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
import openpyxl, sqlite3, re
from pathlib import Path

from streets_lib import (
    DIACRITIC_FIX, fix_diacritics, normalize_match, STREET_TYPES,
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

# normalization helpers (DIACRITIC_FIX, fix_diacritics, normalize_match) and
# STREET_TYPES live in streets_lib so the OSM tools can reuse them.

# ---------- titles / ranks / saints ----------
TITLES = sorted([
    "Profesor Universitar Doctor","Profesor Universitar",
    "Profesor Doctor","Profesor","Prof. Univ. Dr.","Prof. Dr.","Prof.",
    "Academician","Acad.","Doctor","Dr.","Ing.","Arh.",
    "Învățătorul","Învățător","Înv.",
    "Pictorul","Pictor","Sculptorul","Sculptor",
    "Compozitorul","Compozitor","Poetul","Poet",
    "Scriitorul","Scriitor","Dramaturgul","Dramaturg","Filozoful","Filozof",
    "Părintele","Preotul","Preot","Episcopul","Episcop",
    "Mitropolitul","Mitropolit","Patriarhul","Patriarh",
], key=len, reverse=True)

RANKS = sorted([
    "Locotenent-colonel","General-locotenent","Sublocotenent",
    "General","Colonel","Maior","Căpitan","Locotenent","Sergent","Caporal","Soldat",
    "Mareșal","Amiral","Comandor",
    "Voievodul","Voievod","Domnitorul","Domnitor",
    "Regele","Regina","Împăratul","Împărăteasa","Prințul","Prinț","Prințesa",
    "Eroii","Eroul","Erou","Martirii","Martirul","Martir",
    "Haiducul",
], key=len, reverse=True)

SAINTS = sorted([
    "Sfinții Apostoli","Sfinții","Sfântul","Sfânta","Sfântu","Sfânt",
    "Sf-a","Sfta.","Sf.",
], key=len, reverse=True)

MONTHS_RO = ["ianuarie","februarie","martie","aprilie","mai","iunie",
             "iulie","august","septembrie","octombrie","noiembrie","decembrie"]
DATE_RE = re.compile(r"^(\d{1,2})\s+(" + "|".join(MONTHS_RO) + r")$", re.IGNORECASE)
NUMERIC_RE = re.compile(r"^\d+[A-Za-z]?$")

def parse_artery(raw):
    if not raw: return None, None, []
    s = fix_diacritics(raw).strip()
    aliases_raw = re.findall(r"\(([^)]+)\)", s)
    main = re.sub(r"\s*\([^)]+\)", "", s).strip()
    aliases = [a.strip() for a in aliases_raw if len(a.strip()) > 2]
    for st in STREET_TYPES:
        if main.startswith(st + " "):
            return st, main[len(st):].strip(), aliases
    return None, main, aliases

def extract_features(name):
    f = {"title":None,"rank":None,"is_saint":0,"is_date":0,"is_numeric":0,"core_name":name}
    if not name: return f
    if NUMERIC_RE.match(name):
        f["is_numeric"]=1; f["core_name"]=None; return f
    if DATE_RE.match(name):
        f["is_date"]=1; f["core_name"]=name; return f

    remaining = name
    progress = True
    while progress:
        progress = False
        for s in SAINTS:
            if remaining == s or remaining.startswith(s + " "):
                f["is_saint"]=1; remaining = remaining[len(s):].strip(); progress=True; break
        if progress: continue
        for t in TITLES:
            if remaining == t or remaining.startswith(t + " "):
                f["title"] = (f["title"] + " " + t) if f["title"] else t
                remaining = remaining[len(t):].strip(); progress=True; break
        if progress: continue
        for r in RANKS:
            if remaining == r or remaining.startswith(r + " "):
                f["rank"] = (f["rank"] + " " + r) if f["rank"] else r
                remaining = remaining[len(r):].strip(); progress=True; break
    f["core_name"] = remaining if remaining else None
    return f

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
-- those before insert, so this table mirrors streets_dedup's grain.
CREATE TABLE osm_streets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uat_siruta INTEGER NOT NULL,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    core_name_norm TEXT,
    highway_class TEXT NOT NULL,
    ref TEXT,
    length_m REAL NOT NULL,
    way_ids TEXT NOT NULL,         -- JSON array of contributing OSM way ids
    geometry_wkt TEXT,
    importance_v1 REAL,            -- raw score from tools/osm_score.py
    importance_v1_uat_z REAL,      -- z-score within UAT
    UNIQUE (uat_siruta, name_normalized)
);
CREATE INDEX ix_osm_uat       ON osm_streets(uat_siruta);
CREATE INDEX ix_osm_namenorm  ON osm_streets(name_normalized);
CREATE INDEX ix_osm_corenorm  ON osm_streets(core_name_norm);

CREATE TABLE street_osm_matches (
    street_id INTEGER NOT NULL REFERENCES streets(id),
    osm_street_id INTEGER NOT NULL REFERENCES osm_streets(id),
    match_type TEXT NOT NULL,      -- 'exact_normalized' | 'fuzzy_core_name'
    confidence REAL NOT NULL,
    PRIMARY KEY (street_id, osm_street_id)
);
CREATE INDEX ix_match_osm     ON street_osm_matches(osm_street_id);

CREATE INDEX ix_streets_judet     ON streets(judet);
CREATE INDEX ix_streets_uat       ON streets(uat);
CREATE INDEX ix_streets_namenorm  ON streets(name_normalized);
CREATE INDEX ix_streets_corenorm  ON streets(core_name_norm);
CREATE INDEX ix_streets_type      ON streets(street_type);
CREATE INDEX ix_streets_flags     ON streets(is_saint, is_date, is_numeric);
-- Composite index allows the optimizer to push WHERE siruta=? into streets_dedup.
CREATE INDEX ix_streets_siruta_name ON streets(siruta, name_normalized);
CREATE INDEX ix_aliases_norm      ON street_aliases(alias_normalized);

-- GROUP BY siruta (not uat) is intentional: 48 UAT names are shared across
-- multiple județe and would be incorrectly merged if grouped by name alone.
CREATE VIEW streets_dedup AS
SELECT MIN(id) AS id, judet, uat, siruta, street_type, name, name_normalized,
       title, rank, is_saint, is_date, is_numeric, core_name, core_name_norm
FROM streets
WHERE name_normalized != ''
GROUP BY siruta, name_normalized;

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
  FROM streets_dedup
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

con.commit()
def n(sql): return con.execute(sql).fetchone()[0]
print(f"Inserted     {inserted}")
print(f"Aliases      {n('SELECT COUNT(*) FROM street_aliases')}")
print(f"Deduped      {n('SELECT COUNT(*) FROM streets_dedup')}")
print(f"Saints       {n('SELECT COUNT(*) FROM streets_dedup WHERE is_saint=1')}")
print(f"Dates        {n('SELECT COUNT(*) FROM streets_dedup WHERE is_date=1')}")
print(f"Numeric      {n('SELECT COUNT(*) FROM streets_dedup WHERE is_numeric=1')}")
print(f"With title   {n('SELECT COUNT(*) FROM streets_dedup WHERE title IS NOT NULL')}")
print(f"With rank    {n('SELECT COUNT(*) FROM streets_dedup WHERE rank IS NOT NULL')}")
con.close()
