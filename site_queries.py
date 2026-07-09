# site_queries.py
import csv
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from streets_lib import slugify, fix_diacritics

_COORDS_CSV = Path(__file__).resolve().parent / "data" / "gis" / "populatie-romania-siruta-coords.csv"
_SIRUTA_COORDS: dict | None = None


def _siruta_coords() -> dict:
    """Lazy-load {siruta:int -> (lat, lon)} from the GIS coords CSV (cached).

    Covers ~99% of registry UAT sirutas. Returns {} if the file is missing so
    map features degrade gracefully rather than breaking the build.
    """
    global _SIRUTA_COORDS
    if _SIRUTA_COORDS is None:
        _SIRUTA_COORDS = {}
        if _COORDS_CSV.exists():
            with open(_COORDS_CSV, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        _SIRUTA_COORDS[int(row["siruta"])] = (
                            round(float(row["lat"]), 5), round(float(row["long"]), 5))
                    except (TypeError, ValueError, KeyError):
                        continue
    return _SIRUTA_COORDS


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def section1(conn: sqlite3.Connection) -> dict:
    total = _one(conn, "SELECT COUNT(*) AS n FROM streets_dedup")["n"]

    top_men = _rows(conn, """
        SELECT p.full_name, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'M'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 5
    """)

    top_women = _rows(conn, """
        SELECT p.full_name, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'F'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 5
    """)

    counts = _one(conn, """
        SELECT
          SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) AS m,
          SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) AS f
        FROM (
          SELECT DISTINCT p.core_name_norm, p.gender
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
        ) p
    """)

    return {
        "total_streets": total,
        "top_men": top_men,
        "top_women": top_women,
        "total_persons_m": counts.get("m", 0) or 0,
        "total_persons_f": counts.get("f", 0) or 0,
    }


def section2(conn: sqlite3.Connection) -> dict:
    # core_name preserves diacritics + capitalization for display ("Florilor",
    # "Ștefan cel Mare"). name_normalized is the diacritic-folded lowercase key
    # used for grouping and matching. Don't display the latter.
    top_names = _rows(conn, """
        SELECT
          sd.name_normalized,
          MIN(sd.core_name)      AS core_name,
          MAX(p.wikidata_qid)    AS wikidata_qid,
          COUNT(*) AS street_count,
          CASE
            WHEN p.core_name_norm IS NOT NULL THEN 'persoană'
            WHEN nt.core_name_norm IS NOT NULL THEN 'natură'
            WHEN sd.is_saint = 1 THEN 'religios'
            WHEN sd.is_date = 1 THEN 'dată'
            WHEN nc.category IS NOT NULL THEN nc.category
            ELSE 'altele'
          END AS category
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
        LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE sd.is_numeric = 0
          AND sd.core_name IS NOT NULL
        GROUP BY sd.name_normalized
        ORDER BY street_count DESC
        LIMIT 50
    """)

    # Top-30 within each județ — drives the județ filter dropdown.
    # Bucharest sectors aggregate as 'B' to match the rest of the site.
    by_judet_rows = _rows(conn, """
        WITH judet_named AS (
          SELECT
            CASE WHEN sd.judet LIKE 'BUCURESTI%' OR sd.judet = 'B' THEN 'B'
                 ELSE sd.judet END AS judet,
            sd.name_normalized,
            sd.core_name,
            p.wikidata_qid,
            CASE
              WHEN p.core_name_norm IS NOT NULL THEN 'persoană'
              WHEN nt.core_name_norm IS NOT NULL THEN 'natură'
              WHEN sd.is_saint = 1 THEN 'religios'
              WHEN sd.is_date = 1 THEN 'dată'
              WHEN nc.category IS NOT NULL THEN nc.category
              ELSE 'altele'
            END AS category
          FROM streets_dedup sd
          LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
          LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
          LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
          WHERE sd.is_numeric = 0 AND sd.core_name IS NOT NULL
        ),
        ranked AS (
          SELECT judet, name_normalized,
                 MIN(core_name)     AS core_name,
                 MAX(category)      AS category,
                 MAX(wikidata_qid)  AS wikidata_qid,
                 COUNT(*) AS street_count,
                 ROW_NUMBER() OVER (PARTITION BY judet ORDER BY COUNT(*) DESC) AS rn
          FROM judet_named
          GROUP BY judet, name_normalized
        )
        SELECT judet, name_normalized, core_name, category, wikidata_qid, street_count
        FROM ranked
        WHERE rn <= 50
        ORDER BY judet, street_count DESC
    """)
    by_judet: dict[str, list[dict]] = {}
    for r in by_judet_rows:
        by_judet.setdefault(r["judet"], []).append({
            "name_normalized": r["name_normalized"],
            "core_name":       r["core_name"],
            "wikidata_qid":    r["wikidata_qid"],
            "street_count":    r["street_count"],
            "category":        r["category"],
        })

    for r in top_names:
        r["slug"] = slugify(r["core_name"] or r["name_normalized"])
    for rows in by_judet.values():
        for r in rows:
            r["slug"] = slugify(r["core_name"] or r["name_normalized"])

    return {"top_names": top_names, "by_judet": by_judet}


def section3(conn: sqlite3.Connection) -> dict:
    top_persons = _rows(conn, """
        SELECT p.full_name, p.gender, p.profession, p.era, p.wikidata_qid,
               COALESCE(p.wiki_scope, 'unknown') AS wiki_scope,
               COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 50
    """)

    counts = _one(conn, """
        SELECT
          SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) AS m,
          SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) AS f
        FROM (
          SELECT DISTINCT p.core_name_norm, p.gender
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
        ) p
    """)

    profession_dist = _rows(conn, """
        SELECT COALESCE(p.profession, 'necunoscut') AS profession,
               COUNT(DISTINCT p.core_name_norm) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY profession
        ORDER BY n DESC
        LIMIT 8
    """)
    for r in profession_dist:
        r["slug"] = f"profesie-{slugify(r['profession'])}" if r.get("profession") and r["profession"] != "necunoscut" else ""

    era_dist = _rows(conn, """
        SELECT COALESCE(p.era, 'necunoscută') AS era,
               COUNT(DISTINCT p.core_name_norm) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY era
        ORDER BY n DESC
        LIMIT 6
    """)

    # Gender-specific top lists for the split Bărbați / Femei sub-panels.
    top_men = _rows(conn, """
        SELECT p.full_name, p.gender, p.wikidata_qid, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'M'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 15
    """)
    top_women = _rows(conn, """
        SELECT p.full_name, p.gender, p.wikidata_qid, COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.gender = 'F'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 15
    """)

    def _persons_by_judet(gender_filter: str) -> dict[str, list[dict]]:
        rows = _rows(conn, f"""
            WITH per_judet AS (
              SELECT
                CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                     ELSE sd.judet END AS judet,
                p.core_name_norm,
                MAX(p.full_name)       AS full_name,
                MAX(p.gender)          AS gender,
                MAX(p.wikidata_qid)    AS wikidata_qid,
                COUNT(*)               AS street_count
              FROM streets_dedup sd
              JOIN persons p ON p.core_name_norm = sd.core_name_norm
              WHERE sd.is_numeric = 0
                {gender_filter}
              GROUP BY 1, 2
            ),
            ranked AS (
              SELECT judet, full_name, gender, wikidata_qid, street_count,
                     ROW_NUMBER() OVER (PARTITION BY judet ORDER BY street_count DESC) AS rn
              FROM per_judet
            )
            SELECT judet, full_name, gender, wikidata_qid, street_count
            FROM ranked WHERE rn <= 10
            ORDER BY judet, street_count DESC
        """)
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r["judet"], []).append({
                "full_name":    r["full_name"],
                "gender":       r["gender"],
                "wikidata_qid": r["wikidata_qid"],
                "street_count": r["street_count"],
            })
        return out

    def _add_person_slugs(rows):
        for r in rows:
            r["slug"] = (r.get("wikidata_qid") or "").lower() or slugify(r.get("full_name") or "")

    _add_person_slugs(top_persons)
    _add_person_slugs(top_men)
    _add_person_slugs(top_women)

    men_by_judet   = _persons_by_judet("AND p.gender = 'M'")
    women_by_judet = _persons_by_judet("AND p.gender = 'F'")

    top_foreigners = _rows(conn, """
        SELECT p.full_name, p.nationality, p.profession, p.wikidata_qid,
               COUNT(*) AS street_count,
               GROUP_CONCAT(DISTINCT sd.judet) AS judete
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.nationality IS NOT NULL AND p.nationality != 'RO'
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 20
    """)

    def _foreigners_by_judet() -> dict[str, list[dict]]:
        rows = _rows(conn, """
            WITH per_judet AS (
              SELECT
                CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                     ELSE sd.judet END AS judet,
                p.core_name_norm,
                MAX(p.full_name)       AS full_name,
                MAX(p.nationality)     AS nationality,
                MAX(p.profession)      AS profession,
                MAX(p.wikidata_qid)    AS wikidata_qid,
                COUNT(*)               AS street_count
              FROM streets_dedup sd
              JOIN persons p ON p.core_name_norm = sd.core_name_norm
              WHERE sd.is_numeric = 0
                AND p.nationality IS NOT NULL
                AND p.nationality != 'RO'
              GROUP BY 1, 2
            ),
            ranked AS (
              SELECT judet, full_name, nationality, profession, wikidata_qid, street_count,
                     ROW_NUMBER() OVER (PARTITION BY judet ORDER BY street_count DESC) AS rn
              FROM per_judet
            )
            SELECT judet, full_name, nationality, profession, wikidata_qid, street_count
            FROM ranked WHERE rn <= 10
            ORDER BY judet, street_count DESC
        """)
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r["judet"], []).append({
                "full_name":    r["full_name"],
                "nationality":  r["nationality"],
                "profession":   r["profession"],
                "wikidata_qid": r["wikidata_qid"],
                "street_count": r["street_count"],
            })
        return out

    foreigners_by_judet = _foreigners_by_judet()
    _add_person_slugs(top_foreigners)
    for rows in men_by_judet.values():
        _add_person_slugs(rows)
    for rows in women_by_judet.values():
        _add_person_slugs(rows)
    for rows in foreigners_by_judet.values():
        _add_person_slugs(rows)

    # Profession distribution per județ
    prof_judet_rows = _rows(conn, """
        SELECT CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                    ELSE sd.judet END AS judet,
               COALESCE(p.profession, 'necunoscut') AS profession,
               COUNT(DISTINCT p.core_name_norm) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.profession IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 3 DESC
    """)
    profession_by_judet: dict[str, list[dict]] = {}
    for r in prof_judet_rows:
        profession_by_judet.setdefault(r["judet"], []).append(
            {"profession": r["profession"], "n": r["n"]}
        )

    # Era distribution per județ
    era_judet_rows = _rows(conn, """
        SELECT CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                    ELSE sd.judet END AS judet,
               COALESCE(p.era, 'necunoscută') AS era,
               COUNT(DISTINCT p.core_name_norm) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.era IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 3 DESC
    """)
    era_by_judet: dict[str, list[dict]] = {}
    for r in era_judet_rows:
        era_by_judet.setdefault(r["judet"], []).append(
            {"era": r["era"], "n": r["n"]}
        )

    gender_count_rows = _rows(conn, """
        SELECT CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                    ELSE sd.judet END AS judet,
               SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) AS m,
               SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) AS f
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY 1
    """)
    gender_by_judet = {r["judet"]: {"m": r["m"], "f": r["f"]} for r in gender_count_rows}

    # Top-20 persons per județ — drives the shared județ filter in the clusters variant.
    persons_by_judet_rows = _rows(conn, """
        WITH per_judet AS (
          SELECT
            CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                 ELSE sd.judet END AS judet,
            p.core_name_norm,
            MAX(p.full_name) AS full_name,
            MAX(p.gender)    AS gender,
            COUNT(*)         AS street_count
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
          WHERE sd.is_numeric = 0
          GROUP BY 1, 2
        ),
        ranked AS (
          SELECT judet, full_name, gender, street_count,
                 ROW_NUMBER() OVER (PARTITION BY judet ORDER BY street_count DESC) AS rn
          FROM per_judet
        )
        SELECT judet, full_name, gender, street_count
        FROM ranked WHERE rn <= 20
        ORDER BY judet, street_count DESC
    """)
    persons_by_judet: dict[str, list[dict]] = {}
    for r in persons_by_judet_rows:
        persons_by_judet.setdefault(r["judet"], []).append({
            "full_name": r["full_name"],
            "gender": r["gender"],
            "street_count": r["street_count"],
        })

    # Nationality summary for the s8 foreigners panel: list of
    # (nationality, count) tuples sorted by count desc. Template uses this
    # to render flag chips without re-grouping in Jinja.
    foreign_nat_counts: dict[str, int] = {}
    for p in top_foreigners:
        nat = p["nationality"]
        if nat:
            foreign_nat_counts[nat] = foreign_nat_counts.get(nat, 0) + 1
    foreign_nat_summary = sorted(
        foreign_nat_counts.items(), key=lambda kv: -kv[1]
    )

    # Full nationality breakdown (persons + street-weighted) for a side-by-side
    # "by person" / "by street" panel. Includes RO so the chart can show shares.
    nat_rows = _rows(conn, """
        SELECT COALESCE(p.nationality, 'XX') AS nationality,
               COUNT(DISTINCT p.core_name_norm) AS persons,
               COUNT(sd.id) AS streets
        FROM persons p
        LEFT JOIN streets_dedup sd ON sd.core_name_norm = p.core_name_norm
        GROUP BY nationality
        ORDER BY streets DESC
    """)
    nationality_breakdown = [
        {"nat": r["nationality"], "persons": r["persons"], "streets": r["streets"]}
        for r in nat_rows
    ]

    # Per-județ nationality breakdown — persons = distinct honorees in the
    # județ, streets = street-instances. Powers the landing's judet filter.
    nat_judet_rows = _rows(conn, """
        SELECT sd.judet,
               COALESCE(p.nationality, 'XX') AS nationality,
               COUNT(DISTINCT p.core_name_norm) AS persons,
               COUNT(sd.id) AS streets
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY sd.judet, nationality
        ORDER BY sd.judet, streets DESC
    """)
    nationality_breakdown_by_judet: dict[str, list[dict]] = {}
    for r in nat_judet_rows:
        nationality_breakdown_by_judet.setdefault(r["judet"], []).append({
            "nat": r["nationality"],
            "persons": r["persons"],
            "streets": r["streets"],
        })

    # Per-municipiu (siruta) nationality breakdown — only MUNICIPIUL UATs to
    # match the landing's UAT filter scope. Smaller payload than per-uat all.
    nat_siruta_rows = _rows(conn, """
        SELECT sd.siruta,
               COALESCE(p.nationality, 'XX') AS nationality,
               COUNT(DISTINCT p.core_name_norm) AS persons,
               COUNT(sd.id) AS streets
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE sd.uat LIKE 'MUNICIPIUL%'
        GROUP BY sd.siruta, nationality
        ORDER BY sd.siruta, streets DESC
    """)
    nationality_breakdown_by_siruta: dict[str, list[dict]] = {}
    for r in nat_siruta_rows:
        key = str(r["siruta"])
        nationality_breakdown_by_siruta.setdefault(key, []).append({
            "nat": r["nationality"],
            "persons": r["persons"],
            "streets": r["streets"],
        })

    return {
        "top_persons": top_persons,
        "persons_by_judet": persons_by_judet,
        "top_men": top_men,
        "top_women": top_women,
        "men_by_judet": men_by_judet,
        "women_by_judet": women_by_judet,
        "foreigners_by_judet": foreigners_by_judet,
        "gender_by_judet": gender_by_judet,
        "profession_by_judet": profession_by_judet,
        "era_by_judet": era_by_judet,
        "total_m": counts.get("m", 0) or 0,
        "total_f": counts.get("f", 0) or 0,
        "profession_dist": profession_dist,
        "era_dist": era_dist,
        "top_foreigners": top_foreigners,
        "foreign_nat_summary": foreign_nat_summary,
        "nationality_breakdown": nationality_breakdown,
        "nationality_breakdown_by_judet": nationality_breakdown_by_judet,
        "nationality_breakdown_by_siruta": nationality_breakdown_by_siruta,
    }


def section4(conn: sqlite3.Connection) -> dict:
    top_pageviews = _rows(conn, """
        SELECT p.full_name, p.wikidata_qid, p.wiki_scope, p.wiki_sitelinks,
               p.wiki_ro_views, p.wiki_ro_url,
               COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.wiki_ro_views IS NOT NULL AND p.wiki_ro_views > 0
        GROUP BY p.core_name_norm
        ORDER BY p.wiki_ro_views DESC
        LIMIT 10
    """)
    for r in top_pageviews:
        r["slug"] = (r.get("wikidata_qid") or "").lower() or slugify(r.get("full_name") or "")

    tier_counts = _one(conn, """
        SELECT
          SUM(CASE WHEN wiki_scope = 'universal' THEN 1 ELSE 0 END) AS universal,
          SUM(CASE WHEN wiki_scope = 'national' THEN 1 ELSE 0 END) AS national,
          SUM(CASE WHEN wiki_scope IN ('local','unknown') OR wiki_scope IS NULL THEN 1 ELSE 0 END) AS local
        FROM persons
        WHERE wikidata_qid IS NOT NULL
    """)

    pv_judet_rows = _rows(conn, """
        WITH per_judet AS (
          SELECT CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                      ELSE sd.judet END AS judet,
                 p.core_name_norm,
                 MAX(p.full_name)      AS full_name,
                 MAX(p.wikidata_qid)   AS wikidata_qid,
                 MAX(p.wiki_ro_views)  AS wiki_ro_views,
                 MAX(p.wiki_scope)     AS wiki_scope,
                 COUNT(*)              AS street_count
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
          WHERE p.wiki_ro_views IS NOT NULL AND p.wiki_ro_views > 0
          GROUP BY 1, 2
        ),
        ranked AS (
          SELECT judet, full_name, wikidata_qid, wiki_ro_views, wiki_scope, street_count,
                 ROW_NUMBER() OVER (PARTITION BY judet ORDER BY wiki_ro_views DESC) AS rn
          FROM per_judet
        )
        SELECT judet, full_name, wikidata_qid, wiki_ro_views, wiki_scope, street_count
        FROM ranked WHERE rn <= 5
        ORDER BY judet, wiki_ro_views DESC
    """)
    top_pageviews_by_judet: dict[str, list[dict]] = {}
    for r in pv_judet_rows:
        entry = {k: r[k] for k in ("full_name", "wikidata_qid", "wiki_ro_views", "wiki_scope", "street_count")}
        entry["slug"] = (r.get("wikidata_qid") or "").lower() or slugify(r.get("full_name") or "")
        top_pageviews_by_judet.setdefault(r["judet"], []).append(entry)

    return {
        "top_pageviews": top_pageviews,
        "top_pageviews_by_judet": top_pageviews_by_judet,
        "tier_counts": {
            "universal": tier_counts.get("universal", 0) or 0,
            "national": tier_counts.get("national", 0) or 0,
            "local": tier_counts.get("local", 0) or 0,
        },
    }


def section5(conn: sqlite3.Connection) -> dict:
    theme_dist = _rows(conn, """
        SELECT category, SUM(cnt) AS count FROM (
          SELECT 'persoană' AS category, COUNT(*) AS cnt
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
          UNION ALL
          SELECT 'natură', COUNT(*)
          FROM streets_dedup sd
          JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
          UNION ALL
          SELECT 'religios', COUNT(*)
          FROM streets_dedup WHERE is_saint = 1
          UNION ALL
          SELECT 'dată / sărbătoare', COUNT(*)
          FROM streets_dedup WHERE is_date = 1
          UNION ALL
          SELECT 'ideologic', COUNT(*)
          FROM streets_dedup sd
          JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
          WHERE nc.category = 'ideological'
          UNION ALL
          SELECT 'concept / abstract', COUNT(*)
          FROM streets_dedup sd
          JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
          WHERE nc.category IN ('abstract', 'commemorative', 'institutional')
        ) GROUP BY category
        ORDER BY count DESC
    """)

    nature_subtypes = _rows(conn, """
        SELECT COALESCE(nature_type, 'altele') AS nature_type,
               COUNT(*) AS n
        FROM streets_dedup sd
        JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        GROUP BY nature_type
        ORDER BY n DESC
        LIMIT 6
    """)

    ideo_tokens = _rows(conn, """
        SELECT nc.subcategory AS token, COUNT(*) AS n
        FROM streets_dedup sd
        JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE nc.category = 'ideological'
          AND nc.subcategory IS NOT NULL
        GROUP BY nc.subcategory
        ORDER BY n DESC
        LIMIT 12
    """)

    # Map section5 category labels → macro slugs for detail-page linking.
    _cat_to_slug = {
        'persoană': 'persoana', 'natură': 'natura',
        'religios': 'religios', 'dată / sărbătoare': 'data',
        'ideologic': 'ideologic',
    }
    for r in theme_dist:
        r["slug"] = _cat_to_slug.get(r["category"], "")

    for r in nature_subtypes:
        r["slug"] = f"natura-{slugify(r['nature_type'])}" if r.get("nature_type") else ""

    for r in ideo_tokens:
        r["slug"] = f"ideologic-{slugify(r['token'])}" if r.get("token") else ""

    # Nature subtypes per județ
    nature_judet_rows = _rows(conn, """
        SELECT CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                    ELSE sd.judet END AS judet,
               COALESCE(nt.nature_type, 'altele') AS nature_type,
               COUNT(DISTINCT sd.name_normalized) AS n
        FROM streets_dedup sd
        JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        WHERE sd.is_numeric = 0 AND sd.core_name IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 3 DESC
    """)
    nature_by_judet: dict[str, list[dict]] = {}
    for r in nature_judet_rows:
        nature_by_judet.setdefault(r["judet"], []).append(
            {"nature_type": r["nature_type"], "n": r["n"]}
        )

    # Ideo tokens per județ
    ideo_judet_rows = _rows(conn, """
        SELECT CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                    ELSE sd.judet END AS judet,
               nc.subcategory AS token,
               COUNT(DISTINCT sd.name_normalized) AS n
        FROM streets_dedup sd
        JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE nc.category = 'ideological' AND nc.subcategory IS NOT NULL
          AND sd.is_numeric = 0
        GROUP BY 1, 2
        ORDER BY 1, 3 DESC
    """)
    ideo_by_judet: dict[str, list[dict]] = {}
    for r in ideo_judet_rows:
        ideo_by_judet.setdefault(r["judet"], []).append(
            {"token": r["token"], "n": r["n"]}
        )

    theme_judet_rows = _rows(conn, """
        SELECT CASE WHEN sd.judet LIKE 'BUCURESTI%%' OR sd.judet = 'B' THEN 'B'
                    ELSE sd.judet END AS judet,
               SUM(CASE WHEN p.core_name_norm  IS NOT NULL THEN 1 ELSE 0 END) AS persoana,
               SUM(CASE WHEN nt.core_name_norm IS NOT NULL THEN 1 ELSE 0 END) AS natura,
               SUM(CASE WHEN sd.is_saint = 1   THEN 1 ELSE 0 END) AS religios,
               SUM(CASE WHEN sd.is_date  = 1   THEN 1 ELSE 0 END) AS data_sab,
               SUM(CASE WHEN nc.category = 'ideological' THEN 1 ELSE 0 END) AS ideologic,
               SUM(CASE WHEN nc.category IN ('abstract','commemorative','institutional') THEN 1 ELSE 0 END) AS abstract,
               COUNT(*) AS total
        FROM streets_dedup sd
        LEFT JOIN persons p      ON p.core_name_norm  = sd.core_name_norm
        LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE sd.is_numeric = 0
        GROUP BY 1
    """)
    theme_by_judet = {
        r["judet"]: {
            "persoană": r["persoana"], "natură": r["natura"],
            "religios": r["religios"], "dată / sărbătoare": r["data_sab"],
            "ideologic": r["ideologic"], "concept / abstract": r["abstract"],
            "total": r["total"],
        }
        for r in theme_judet_rows
    }

    return {
        "theme_dist": theme_dist,
        "theme_by_judet": theme_by_judet,
        "nature_subtypes": nature_subtypes,
        "nature_by_judet": nature_by_judet,
        "ideo_tokens": ideo_tokens,
        "ideo_by_judet": ideo_by_judet,
    }


def section6_uat(conn: sqlite3.Connection, min_streets: int = 10) -> dict:
    """Per-UAT version of the section6 choropleth metrics, keyed by siruta
    (as a string, to join the ro-uats.topojson `siruta` property).

    Same metric formulas as `section6.by_judet` but GROUP BY siruta. UATs below
    `min_streets` are excluded so tiny denominators don't blow out the colour
    scale — those polygons render grey on the map. self_honor_pct uses the UAT's
    own județ as the "born locally" test.

    Lazy-loaded by the județe map when the user switches to the localități level,
    so it's written to its own JSON rather than embedded in the page.
    """
    rows = _rows(conn, """
        SELECT sd.siruta, sd.judet, sd.uat,
               COUNT(*) AS total_streets,
               ROUND(100.0 * SUM(sd.is_saint) / COUNT(*), 1)                              AS saint_pct,
               ROUND(100.0 * SUM(sd.is_numeric) / COUNT(*), 1)                            AS numeric_pct,
               ROUND(100.0 * SUM(sd.is_date) / COUNT(*), 2)                               AS date_pct,
               ROUND(100.0 * SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS female_pct,
               ROUND(100.0 * SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) / COUNT(*), 1) AS male_pct,
               ROUND(100.0 * SUM(CASE WHEN p.core_name_norm IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS person_pct,
               ROUND(100.0 * SUM(CASE WHEN p.nationality IS NOT NULL AND p.nationality != 'RO' THEN 1 ELSE 0 END) / COUNT(*), 2) AS foreign_pct,
               ROUND(100.0 * SUM(CASE WHEN p.wiki_scope = 'universal' THEN 1 ELSE 0 END) / COUNT(*), 2) AS universal_pct,
               ROUND(100.0 * SUM(CASE WHEN nt.core_name_norm IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS nature_pct,
               ROUND(100.0 * SUM(CASE WHEN nt.nature_type IN ('flower','tree','plant','fruit','forest','orchard') THEN 1 ELSE 0 END) / COUNT(*), 2) AS flora_pct,
               ROUND(100.0 * SUM(CASE WHEN nc.category = 'ideological' THEN 1 ELSE 0 END) / COUNT(*), 2) AS ideology_pct,
               ROUND(100.0 * SUM(CASE WHEN p.birth_judet = sd.judet THEN 1 ELSE 0 END)
                           / NULLIF(SUM(CASE WHEN p.birth_judet IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS self_honor_pct
        FROM streets_dedup sd
        LEFT JOIN persons p          ON p.core_name_norm  = sd.core_name_norm
        LEFT JOIN nature_terms nt    ON nt.core_name_norm = sd.core_name_norm
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        GROUP BY sd.siruta
        HAVING COUNT(*) >= ?
    """, (min_streets,))

    # Modal (most-frequent) cultural name per UAT, for the click card.
    modal = {r["siruta"]: r["display_name"] for r in _rows(conn, """
        SELECT siruta, display_name FROM (
          SELECT siruta, MIN(name) AS display_name, COUNT(*) AS cnt,
                 ROW_NUMBER() OVER (PARTITION BY siruta ORDER BY COUNT(*) DESC, MIN(name)) AS rn
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY siruta, name_normalized
        ) WHERE rn = 1
    """)}

    # Which UATs have a rendered detail page (for the "vezi pagina" link).
    page_slug = {u["siruta"]: u["slug"] for u in enumerate_uats(conn)}

    by_siruta: dict[str, dict] = {}
    for r in rows:
        sir = r["siruta"]
        d = {k: r[k] for k in r if k != "siruta"}
        d["uat"]      = fix_diacritics(r["uat"])
        d["modal"]    = modal.get(sir, "—")
        d["slug"]     = page_slug.get(sir)        # None if no page
        by_siruta[str(sir)] = d

    return {"by_siruta": by_siruta, "min_streets": min_streets,
            "uat_count": len(by_siruta)}


def section6(conn: sqlite3.Connection) -> dict:
    by_judet = _rows(conn, """
        SELECT judet,
               COUNT(*) AS total_streets,
               ROUND(100.0 * SUM(is_saint) / COUNT(*), 1) AS saint_pct,
               ROUND(100.0 * SUM(is_numeric) / COUNT(*), 1) AS numeric_pct,
               ROUND(100.0 * SUM(is_date) / COUNT(*), 2) AS date_pct,
               ROUND(100.0 * SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS female_pct,
               ROUND(100.0 * SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) / COUNT(*), 1) AS male_pct,
               ROUND(100.0 * SUM(CASE WHEN p.core_name_norm IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS person_pct,
               ROUND(100.0 * SUM(CASE WHEN p.nationality IS NOT NULL AND p.nationality != 'RO' THEN 1 ELSE 0 END) / COUNT(*), 2) AS foreign_pct,
               ROUND(100.0 * SUM(CASE WHEN p.wiki_scope = 'universal' THEN 1 ELSE 0 END) / COUNT(*), 2) AS universal_pct,
               ROUND(100.0 * SUM(CASE WHEN nt.core_name_norm IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS nature_pct,
               ROUND(100.0 * SUM(CASE WHEN nt.nature_type IN ('flower','tree','plant','fruit','forest','orchard') THEN 1 ELSE 0 END) / COUNT(*), 2) AS flora_pct,
               ROUND(100.0 * SUM(CASE WHEN nc.category = 'ideological' THEN 1 ELSE 0 END) / COUNT(*), 2) AS ideology_pct,
               -- self_honor_pct: of person-streets in this județ with a KNOWN
               -- birth-județ on the honoree, what fraction were born locally.
               -- Denominator excludes foreign-born and unknown-birth honorees so
               -- the rate isn't deflated by Wikidata sparsity (~50% of QIDs).
               ROUND(100.0 * SUM(CASE WHEN p.birth_judet = sd.judet THEN 1 ELSE 0 END)
                           / NULLIF(SUM(CASE WHEN p.birth_judet IS NOT NULL THEN 1 ELSE 0 END), 0), 1)
                                                                                  AS self_honor_pct
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
        LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        GROUP BY judet
        ORDER BY total_streets DESC
    """)

    modal_names = _rows(conn, """
        SELECT judet, name_normalized, cnt FROM (
          SELECT judet, name_normalized, COUNT(*) AS cnt,
                 ROW_NUMBER() OVER (PARTITION BY judet ORDER BY COUNT(*) DESC) AS rn
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY judet, name_normalized
        ) WHERE rn = 1
    """)
    modal_map = {r["judet"]: r["name_normalized"] for r in modal_names}

    top_rows = _rows(conn, """
        SELECT judet, MIN(name) AS display_name, COUNT(*) AS cnt
        FROM streets_dedup
        WHERE is_numeric = 0 AND core_name IS NOT NULL
        GROUP BY judet, name_normalized
        ORDER BY judet, cnt DESC
    """)
    top_map: dict[str, list] = {}
    for r in top_rows:
        j = r["judet"]
        if j not in top_map:
            top_map[j] = []
        if len(top_map[j]) < 5:
            top_map[j].append({"n": r["display_name"], "c": r["cnt"],
                                "sl": slugify(r["display_name"])})

    rare_rows = _rows(conn, """
        WITH global_rarity AS (
          SELECT name_normalized, COUNT(DISTINCT judet) AS judet_count
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY name_normalized
        ),
        ranked AS (
          SELECT sd.judet, MIN(sd.name) AS display_name, gr.judet_count,
                 ROW_NUMBER() OVER (
                   PARTITION BY sd.judet
                   ORDER BY gr.judet_count ASC, MIN(sd.name)
                 ) AS rn
          FROM streets_dedup sd
          JOIN global_rarity gr ON gr.name_normalized = sd.name_normalized
          WHERE sd.is_numeric = 0 AND sd.core_name IS NOT NULL
          GROUP BY sd.judet, sd.name_normalized, gr.judet_count
        )
        SELECT judet, display_name, judet_count FROM ranked WHERE rn <= 5
        ORDER BY judet, judet_count
    """)
    rare_map: dict[str, list] = {}
    for r in rare_rows:
        j = r["judet"]
        if j not in rare_map:
            rare_map[j] = []
        rare_map[j].append({"n": r["display_name"], "j": r["judet_count"],
                            "sl": slugify(r["display_name"])})

    persons_rows = _rows(conn, """
        WITH ranked AS (
          SELECT sd.judet,
                 p.full_name,
                 MAX(p.gender) AS gender,
                 MAX(p.wiki_scope) AS wiki_scope,
                 MAX(p.wikidata_qid) AS wikidata_qid,
                 COUNT(*) AS cnt,
                 ROW_NUMBER() OVER (
                   PARTITION BY sd.judet ORDER BY COUNT(*) DESC
                 ) AS rn
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
          WHERE sd.is_numeric = 0
          GROUP BY sd.judet, p.full_name
        )
        SELECT judet, full_name, gender, wiki_scope, wikidata_qid, cnt FROM ranked WHERE rn <= 5
        ORDER BY judet, cnt DESC
    """)
    persons_map: dict[str, list] = {}
    for r in persons_rows:
        j = r["judet"]
        if j not in persons_map:
            persons_map[j] = []
        person_slug = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"] or "")
        persons_map[j].append({
            "n": r["full_name"],
            "g": r["gender"],
            "s": r["wiki_scope"],
            "c": r["cnt"],
            "sl": person_slug,
        })

    for row in by_judet:
        row["modal_name"] = modal_map.get(row["judet"], "—")

    return {
        "by_judet": by_judet,
        "top_per_judet": top_map,
        "rare_per_judet": rare_map,
        "persons_per_judet": persons_map,
    }


def section_quirky(conn: sqlite3.Connection) -> dict:
    """
    "Quirky" stats panels for the landing page:
      - top_km            : honorees ranked by total OSM kilometers (Pick B-1)
      - class_by_category : highway-class composition by classification (Pick B-2)
      - self_honor_top    : județe where local-born honorees dominate (Pick C)
      - self_honor_bottom : județe that honor outsiders more than their own
    Coverage caveats:
      - OSM joins: ~52% of registry streets are matched, so absolute km under-count
        but rankings are stable.
      - self_honor: only 106/206 honorees with QIDs land in a Romanian județ,
        so the denominator is "person-streets with known birth-județ".
    """
    top_km = _rows(conn, """
        SELECT
            p.full_name,
            p.gender,
            p.profession,
            p.wikidata_qid,
            COUNT(DISTINCT sd.id)              AS matched_streets,
            ROUND(SUM(o.length_m) / 1000.0, 1) AS total_km
        FROM streets_dedup sd
        JOIN persons p              ON p.core_name_norm = sd.core_name_norm
        JOIN street_osm_matches m   ON m.street_id      = sd.id
        JOIN osm_streets o          ON o.id             = m.osm_street_id
        GROUP BY p.core_name_norm
        ORDER BY total_km DESC
        LIMIT 20
    """)
    for r in top_km:
        r["slug"] = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"] or "")

    # Highway-class composition. Pivot client-side; here just return the long form
    # plus per-category totals for share computations.
    class_rows = _rows(conn, """
        WITH classified AS (
          SELECT sd.id,
            CASE
              WHEN sd.is_numeric=1                       THEN 'numerice'
              WHEN sd.is_date=1                          THEN 'date'
              WHEN sd.is_saint=1                         THEN 'religios'
              WHEN p.core_name_norm  IS NOT NULL         THEN 'persoane'
              WHEN n.core_name_norm  IS NOT NULL         THEN 'natură'
              WHEN pl.core_name_norm IS NOT NULL         THEN 'locuri'
              WHEN c.core_name_norm  IS NOT NULL         THEN 'categorii'
              ELSE 'neclasificate'
            END AS category
          FROM streets_dedup sd
          LEFT JOIN persons         p  ON p.core_name_norm  = sd.core_name_norm
          LEFT JOIN nature_terms    n  ON n.core_name_norm  = sd.core_name_norm
          LEFT JOIN place_refs      pl ON pl.core_name_norm = sd.core_name_norm
          LEFT JOIN name_categories c  ON c.core_name_norm  = sd.core_name_norm
        )
        SELECT cl.category,
               o.highway_class,
               COUNT(*)                            AS streets,
               ROUND(SUM(o.length_m) / 1000.0, 1)  AS total_km
        FROM classified cl
        JOIN street_osm_matches m ON m.street_id = cl.id
        JOIN osm_streets o        ON o.id        = m.osm_street_id
        GROUP BY cl.category, o.highway_class
    """)
    # Bucket OSM highway classes into 4 prestige tiers for a readable stacked bar.
    tier_map = {
        "primary":       "principale",
        "secondary":     "principale",
        "tertiary":      "intermediare",
        "unclassified":  "intermediare",
        "residential":   "rezidențiale",
        "living_street": "rezidențiale",
        "service":       "altele",
        "pedestrian":    "altele",
    }
    tier_order = ["principale", "intermediare", "rezidențiale", "altele"]
    # category_order chosen so the most visually-different categories come first.
    category_order = ["persoane", "locuri", "categorii", "natură",
                      "neclasificate", "date", "religios", "numerice"]

    by_category: dict[str, dict[str, float]] = {}
    for r in class_rows:
        cat  = r["category"]
        tier = tier_map.get(r["highway_class"], "altele")
        by_category.setdefault(cat, {t: 0.0 for t in tier_order})
        by_category[cat][tier] += r["total_km"] or 0

    class_by_category = []
    for cat in category_order:
        if cat not in by_category:
            continue
        tiers     = by_category[cat]
        total     = sum(tiers.values()) or 1.0
        row       = {"category": cat, "total_km": round(total, 1)}
        for t in tier_order:
            row[t]            = round(tiers[t], 1)
            row[t + "_pct"]   = round(100.0 * tiers[t] / total, 1)
        class_by_category.append(row)

    self_honor_rows = _rows(conn, """
        SELECT s.judet,
               COUNT(*)                                                       AS total_person_streets,
               SUM(CASE WHEN p.birth_judet IS NOT NULL THEN 1 ELSE 0 END)    AS known_birth_streets,
               SUM(CASE WHEN p.birth_judet = s.judet THEN 1 ELSE 0 END)      AS self_honor_streets,
               ROUND(100.0 * SUM(CASE WHEN p.birth_judet = s.judet THEN 1 ELSE 0 END)
                           / NULLIF(SUM(CASE WHEN p.birth_judet IS NOT NULL THEN 1 ELSE 0 END), 0), 1)
                                                                              AS pct
        FROM streets_dedup s
        JOIN persons p ON p.core_name_norm = s.core_name_norm
        GROUP BY s.judet
        HAVING known_birth_streets >= 20
        ORDER BY pct DESC
    """)
    self_honor_top    = self_honor_rows[:5]
    self_honor_bottom = sorted(self_honor_rows, key=lambda r: r["pct"] or 0)[:5]

    # National baseline so the panel can put județ values in context.
    nat = _one(conn, """
        SELECT
          SUM(CASE WHEN p.birth_judet IS NOT NULL THEN 1 ELSE 0 END) AS known,
          SUM(CASE WHEN p.birth_judet = s.judet THEN 1 ELSE 0 END)   AS self_count
        FROM streets_dedup s
        JOIN persons p ON p.core_name_norm = s.core_name_norm
    """)
    nat_pct = round(100.0 * nat["self_count"] / nat["known"], 1) if nat["known"] else 0.0

    # --- Biographical lifecycle (Pick A) -----------------------------------

    age_rows = _rows(conn, """
        SELECT p.full_name,
               MIN(p.birth_year)                    AS birth_year,
               MIN(p.death_year)                    AS death_year,
               MIN(p.death_year) - MIN(p.birth_year) AS age_at_death,
               p.gender, p.profession,
               MIN(p.wikidata_qid)                  AS wikidata_qid,
               COUNT(DISTINCT sd.id)                AS street_count
        FROM persons p
        JOIN streets_dedup sd ON sd.core_name_norm = p.core_name_norm
        WHERE p.birth_year IS NOT NULL AND p.death_year IS NOT NULL
          AND p.death_year > p.birth_year AND p.birth_year > 0
        GROUP BY p.full_name
        ORDER BY age_at_death
    """)
    for r in age_rows:
        r["slug"] = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"] or "")

    # Weighted average age (street-count weighted)
    total_streets = sum(r["street_count"] for r in age_rows) or 1
    weighted_avg_age = round(
        sum(r["age_at_death"] * r["street_count"] for r in age_rows) / total_streets, 1
    )

    # "Forever young" = died before 40, sorted by streets desc
    young_dead = sorted(
        [r for r in age_rows if r["age_at_death"] < 40],
        key=lambda r: r["street_count"], reverse=True
    )[:10]

    # Cause-of-death macro-bucketing
    def cause_macro(label: str | None) -> str:
        if not label:
            return "necunoscută"
        l = label.lower()
        if any(k in l for k in ("tuberculosis", "pneumonia", "typhus", "plague", "cancer",
                                "hepatitis", "nephritis", "infarction", "stroke", "gout",
                                "seizure", "foodborne", "lung", "infectious", "alzheimer",
                                "asphyxia", "disease", "illness")):
            return "boală"
        if any(k in l for k in ("gunshot", "shooting", "execution", "decapitation",
                                "breaking wheel", "poison", "ambush", "murder", "killed")):
            return "violență"
        if any(k in l for k in ("collision", "vehicle", "accident", "earthquake",
                                "invention")):
            return "accident"
        return "altele"

    cause_raw = _rows(conn, """
        WITH sc AS (
            SELECT core_name_norm, COUNT(DISTINCT id) AS street_count
            FROM streets_dedup GROUP BY core_name_norm
        )
        SELECT
            COALESCE(NULLIF(p.cause_of_death_label,''), '') AS cause_label,
            COUNT(DISTINCT p.core_name_norm)  AS persons,
            SUM(sc.street_count)              AS streets
        FROM persons p
        JOIN sc ON sc.core_name_norm = p.core_name_norm
        WHERE p.wikidata_qid IS NOT NULL
        GROUP BY cause_label
        ORDER BY streets DESC
    """)

    macro_acc: dict[str, dict] = {}
    for r in cause_raw:
        macro = cause_macro(r["cause_label"] or "")
        if macro not in macro_acc:
            macro_acc[macro] = {"macro": macro, "persons": 0, "streets": 0}
        macro_acc[macro]["persons"] += r["persons"]
        macro_acc[macro]["streets"] += r["streets"]

    macro_order = ["boală", "violență", "accident", "altele", "necunoscută"]
    total_cause_streets = sum(v["streets"] for v in macro_acc.values()) or 1
    cause_breakdown = []
    for m in macro_order:
        if m not in macro_acc:
            continue
        row = macro_acc[m]
        row["pct"] = round(100.0 * row["streets"] / total_cause_streets, 1)
        cause_breakdown.append(row)

    # Birth-century distribution (street-weighted)
    century_rows = _rows(conn, """
        WITH sc AS (
            SELECT core_name_norm, COUNT(DISTINCT id) AS street_count
            FROM streets_dedup GROUP BY core_name_norm
        )
        SELECT (p.birth_year / 100) * 100   AS century_start,
               COUNT(DISTINCT p.core_name_norm) AS persons,
               SUM(sc.street_count)             AS streets
        FROM persons p
        JOIN sc ON sc.core_name_norm = p.core_name_norm
        WHERE p.birth_year IS NOT NULL AND p.birth_year > 0
        GROUP BY century_start
        ORDER BY century_start
    """)
    # Format century label for display
    for r in century_rows:
        cs = r["century_start"]
        if cs is not None:
            r["century_label"] = f"sec. {abs(cs // 100) + 1}" + (" î.Hr." if cs < 0 else "")
        else:
            r["century_label"] = "?"

    # --- Gender km gap -------------------------------------------------------

    gender_rows = _rows(conn, """
        SELECT p.gender,
               COUNT(DISTINCT p.full_name)                          AS honorees,
               COUNT(DISTINCT sd.id)                                AS matched_streets,
               ROUND(SUM(o.length_m) / 1000.0, 1)                  AS total_km,
               ROUND(AVG(o.length_m), 0)                           AS avg_length_m,
               ROUND(SUM(o.length_m) / 1000.0
                     / COUNT(DISTINCT p.full_name), 1)             AS km_per_honoree
        FROM streets_dedup sd
        JOIN persons p            ON p.core_name_norm = sd.core_name_norm
        JOIN street_osm_matches m ON m.street_id      = sd.id
        JOIN osm_streets o        ON o.id             = m.osm_street_id
        WHERE p.gender IN ('F', 'M')
        GROUP BY p.gender
    """)
    gender_km = {r["gender"]: r for r in gender_rows}

    female_km_list = _rows(conn, """
        SELECT p.full_name, p.wikidata_qid,
               COUNT(DISTINCT sd.id)               AS streets,
               ROUND(SUM(o.length_m) / 1000.0, 1) AS km,
               ROUND(AVG(o.length_m), 0)           AS avg_m
        FROM streets_dedup sd
        JOIN persons p            ON p.core_name_norm = sd.core_name_norm
        JOIN street_osm_matches m ON m.street_id      = sd.id
        JOIN osm_streets o        ON o.id             = m.osm_street_id
        WHERE p.gender = 'F'
        GROUP BY p.full_name
        ORDER BY km DESC
    """)
    for r in female_km_list:
        r["slug"] = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"] or "")

    f_km  = gender_km.get("F", {}).get("total_km") or 0
    m_km  = gender_km.get("M", {}).get("total_km") or 0
    total_gkm = (f_km + m_km) or 1
    gender_km_pct = {
        "F": round(100.0 * f_km / total_gkm, 1),
        "M": round(100.0 * m_km / total_gkm, 1),
    }

    # --- Association rules / national canon ----------------------------------
    # Fetch person × UAT presence matrix (dedup by full_name so aliases don't
    # inflate counts — a UAT "has Cuza" if any of his 4 name-forms are present).
    presence_rows = _rows(conn, """
        SELECT p.full_name, sd.siruta
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY p.full_name, sd.siruta
    """)
    person_uats: dict[str, set[int]] = {}
    for r in presence_rows:
        person_uats.setdefault(r["full_name"], set()).add(r["siruta"])

    all_person_uats: set[int] = set()
    for uats in person_uats.values():
        all_person_uats |= uats
    n_uats = len(all_person_uats)

    # Canon set: names in ≥30% of UATs with any person street
    canon_threshold = 0.30
    canon_set = sorted(
        [
            {"name": name, "uats": len(uats),
             "pct": round(100.0 * len(uats) / n_uats, 1)}
            for name, uats in person_uats.items()
            if len(uats) / n_uats >= canon_threshold
        ],
        key=lambda r: -r["uats"],
    )

    # Lift-ranked pairs: restrict to persons with ≥5% UAT support for tractability
    min_support = max(5, int(0.05 * n_uats))
    candidates = [(name, uats) for name, uats in person_uats.items()
                  if len(uats) >= min_support]

    pair_list = []
    for (name_a, uats_a), (name_b, uats_b) in combinations(candidates, 2):
        co = len(uats_a & uats_b)
        if co < 5:
            continue
        sup_a  = len(uats_a) / n_uats
        sup_b  = len(uats_b) / n_uats
        sup_ab = co / n_uats
        lift   = round(sup_ab / (sup_a * sup_b), 2)
        pair_list.append({
            "name_a":     name_a,
            "name_b":     name_b,
            "co_uats":    co,
            "lift":       lift,
            "conf_ab":    round(100.0 * co / len(uats_a), 1),  # P(B|A)
            "sup_a":      len(uats_a),
            "sup_b":      len(uats_b),
        })

    # Top pairs by lift; filter out trivially obvious (both in top-3 ubiquitous canon)
    top3 = {r["name"] for r in canon_set[:3]}
    surprising_pairs = sorted(
        [p for p in pair_list if not (p["name_a"] in top3 and p["name_b"] in top3)],
        key=lambda r: -r["lift"],
    )[:12]

    return {
        "top_km":            top_km,
        "class_by_category": class_by_category,
        "tier_order":        tier_order,
        "self_honor_top":    self_honor_top,
        "self_honor_bottom": self_honor_bottom,
        "self_honor_national_pct": nat_pct,
        "age_rows":          age_rows,
        "weighted_avg_age":  weighted_avg_age,
        "young_dead":        young_dead,
        "cause_breakdown":   cause_breakdown,
        "century_rows":      century_rows,
        "gender_km":         gender_km,
        "gender_km_pct":     gender_km_pct,
        "female_km_list":    female_km_list,
        "canon_set":         canon_set,
        "surprising_pairs":  surprising_pairs,
        "n_uats_with_persons": n_uats,
    }


def section_lexical(conn: sqlite3.Connection) -> dict:
    """
    Linguistic / textual quirks + frequency anomalies — existing data only,
    no Wikidata or OSM dependency. All over distinct non-numeric street names.

      - first_letters     : A–Z distribution (distinct names + streets per letter)
      - palindromes        : names that read the same backwards (core ≥ 5 chars)
      - longest / shortest : char-length extremes among display names
      - prepositional      : "reads as a sentence" names (La Fântână, Sub Coastă…)
      - near_universal      : present in all-but-one județ, with the single holdout
      - universal_count     : names present in every județ
      - singleton_pct       : share of names that exist in exactly one UAT
    """
    import re

    rows = _rows(conn, """
        SELECT name_normalized AS n, MIN(name) AS disp,
               COUNT(*) AS streets, COUNT(DISTINCT siruta) AS uats
        FROM streets_dedup
        WHERE is_numeric = 0 AND name_normalized != ''
        GROUP BY name_normalized
    """)
    total_names = len(rows)

    # Per-name județ sets — drives the near-universal / universal anomaly.
    jud_rows = _rows(conn, """
        SELECT DISTINCT name_normalized AS n, judet
        FROM streets_dedup
        WHERE is_numeric = 0 AND name_normalized != ''
    """)
    name_jud: dict[str, set] = defaultdict(set)
    all_jud: set = set()
    for r in jud_rows:
        name_jud[r["n"]].add(r["judet"])
        all_jud.add(r["judet"])
    total_jud = len(all_jud)
    JUDET_NAMES = {
        "AB": "Alba", "AG": "Argeș", "AR": "Arad", "B": "București", "BC": "Bacău",
        "BH": "Bihor", "BN": "Bistrița-Năsăud", "BR": "Brăila", "BT": "Botoșani",
        "BV": "Brașov", "BZ": "Buzău", "CJ": "Cluj", "CL": "Călărași",
        "CS": "Caraș-Severin", "CT": "Constanța", "CV": "Covasna", "DB": "Dâmbovița",
        "DJ": "Dolj", "GJ": "Gorj", "GL": "Galați", "GR": "Giurgiu", "HD": "Hunedoara",
        "HR": "Harghita", "IF": "Ilfov", "IL": "Ialomița", "IS": "Iași",
        "MH": "Mehedinți", "MM": "Maramureș", "MS": "Mureș", "NT": "Neamț",
        "OT": "Olt", "PH": "Prahova", "SB": "Sibiu", "SJ": "Sălaj", "SM": "Satu Mare",
        "SV": "Suceava", "TL": "Tulcea", "TM": "Timiș", "TR": "Teleorman",
        "VL": "Vâlcea", "VN": "Vrancea", "VS": "Vaslui",
    }

    # First-letter distribution (a–z only; numerics already excluded).
    letter_acc: dict[str, dict] = {}
    for r in rows:
        ch = r["n"][:1]
        if "a" <= ch <= "z":
            d = letter_acc.setdefault(ch, {"letter": ch.upper(), "names": 0, "streets": 0})
            d["names"]   += 1
            d["streets"] += r["streets"]
    first_letters = [letter_acc[c] for c in sorted(letter_acc)]
    max_letter_names = max((d["names"] for d in first_letters), default=1)

    # Artifacts to keep out of the lexical curios: enumerated block-streets
    # ("A III-a") and raw road-segment descriptions ("DN65A de la km 100+900…").
    _ENUM_RE = re.compile(r"^a [ivxlcdm]+-?a?$")
    _ROAD_RE = re.compile(r"\bkm \d|^d[njc]\s?\d")

    # Palindromes — same backwards after dropping non-alphanumerics.
    def core(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s)
    palindromes = sorted(
        [{"disp": r["disp"], "streets": r["streets"], "uats": r["uats"]}
         for r in rows
         if len(core(r["n"])) >= 5 and core(r["n"]) == core(r["n"])[::-1]
         and not _ENUM_RE.match(r["n"])],
        key=lambda r: -r["streets"],
    )

    # Length extremes among display names (collapse internal whitespace first).
    # Shortest restricted to single-token real words (≥3 chars) — single-letter
    # block streets and enumerators aren't interesting here.
    def dlen(s: str) -> int:
        return len(re.sub(r"\s+", " ", s.strip()))
    short_cand = [r for r in rows
                  if " " not in r["disp"].strip() and r["disp"].strip().isalpha()
                  and dlen(r["disp"]) >= 3]
    shortest = [{"disp": r["disp"], "len": dlen(r["disp"]), "streets": r["streets"]}
                for r in sorted(short_cand, key=lambda r: (dlen(r["disp"]), -r["streets"]))[:8]]
    long_cand = [r for r in rows if not _ROAD_RE.search(r["n"])]
    longest  = [{"disp": r["disp"], "len": dlen(r["disp"]), "streets": r["streets"]}
                for r in sorted(long_cand, key=lambda r: -dlen(r["disp"]))[:8]]

    # "Reads as a sentence" — first token is a preposition/locative.
    PREPS = {"la", "sub", "catre", "peste", "intre", "spre", "dupa",
             "langa", "din", "in", "pe", "dinspre", "dintre", "deasupra"}
    prep_rows = [r for r in rows
                 if " " in r["n"] and r["n"].split(" ")[0] in PREPS]
    prep_total_names   = len(prep_rows)
    prep_total_streets = sum(r["streets"] for r in prep_rows)
    prepositional = sorted(
        [{"disp": r["disp"], "streets": r["streets"]} for r in prep_rows],
        key=lambda r: -r["streets"],
    )[:18]

    # Frequency anomaly: names in exactly total_jud-1 of total_jud județe.
    near_universal = []
    universal_count = 0
    for r in rows:
        seen = name_jud[r["n"]]
        if len(seen) == total_jud:
            universal_count += 1
        elif len(seen) == total_jud - 1:
            missing = (all_jud - seen).pop()
            near_universal.append({
                "disp": r["disp"], "streets": r["streets"],
                "missing": missing,
                "missing_name": JUDET_NAMES.get(missing, missing),
            })
    near_universal.sort(key=lambda r: -r["streets"])

    # Singletons ("dictionary hapax"): names that exist in exactly one UAT.
    singletons = sum(1 for r in rows if r["uats"] == 1)
    singleton_pct = round(100.0 * singletons / total_names, 1) if total_names else 0.0

    return {
        "total_names":        total_names,
        "total_jud":          total_jud,
        "first_letters":      first_letters,
        "max_letter_names":   max_letter_names,
        "palindromes":        palindromes,
        "shortest":           shortest,
        "longest":            longest,
        "prepositional":      prepositional,
        "prep_total_names":   prep_total_names,
        "prep_total_streets": prep_total_streets,
        "near_universal":     near_universal,
        "universal_count":    universal_count,
        "singletons":         singletons,
        "singleton_pct":      singleton_pct,
    }


def section_geo(conn: sqlite3.Connection) -> dict:
    """
    Geographic-ego stats — who gets honored where vs. where they were born.
    Built on `persons.birth_judet` (resolved for ~111 honorees via Wikidata P19),
    deduplicated by full_name so a person's name-forms (Cuza ×4) count once.

      - forgotten_at_home : many national streets, (almost) none in birth județ
      - most_exported     : județe that birth honorees with the widest reach
      - most_parochial    : honorees whose streets cluster in a single județ
    """
    per = _rows(conn, """
        SELECT p.full_name,
               MIN(p.birth_judet)                                          AS birth_judet,
               MIN(p.wikidata_qid)                                         AS wikidata_qid,
               MIN(p.profession)                                           AS profession,
               COUNT(DISTINCT s.id)                                        AS total_streets,
               COUNT(DISTINCT s.judet)                                     AS judete_reach,
               SUM(CASE WHEN s.judet = p.birth_judet THEN 1 ELSE 0 END)   AS home_streets
        FROM persons p
        JOIN streets_dedup s ON s.core_name_norm = p.core_name_norm
        WHERE p.birth_judet IS NOT NULL
        GROUP BY p.full_name
    """)
    for r in per:
        r["slug"]     = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"] or "")
        r["home_pct"] = round(100.0 * r["home_streets"] / r["total_streets"], 1) \
                        if r["total_streets"] else 0.0

    # "Prophet in their own land": ≥10 national streets but ≤5% (incl. 0) at home.
    forgotten_at_home = sorted(
        [r for r in per if r["total_streets"] >= 10 and r["home_pct"] <= 5.0],
        key=lambda r: -r["total_streets"],
    )[:12]

    # Most-exported județ: sum of national streets of all honorees born there.
    exp: dict[str, dict] = {}
    for r in per:
        j = r["birth_judet"]
        d = exp.setdefault(j, {"judet": j, "honorees": 0, "streets": 0})
        d["honorees"] += 1
        d["streets"]  += r["total_streets"]
    most_exported = sorted(exp.values(), key=lambda d: -d["streets"])[:10]

    # Most parochial: streets ≥80% concentrated in one județ (local heroes).
    parochial_rows = _rows(conn, """
        WITH spj AS (
            SELECT p.full_name, p.birth_judet, s.judet,
                   MIN(p.wikidata_qid) AS wikidata_qid,
                   COUNT(*) AS streets_in_judet
            FROM streets_dedup s
            JOIN persons p ON p.core_name_norm = s.core_name_norm
            GROUP BY p.full_name, s.judet
        ),
        tot AS (
            SELECT full_name, SUM(streets_in_judet) AS total_streets
            FROM spj GROUP BY full_name
        )
        SELECT spj.full_name, spj.birth_judet, spj.wikidata_qid,
               spj.judet AS dominant_judet, spj.streets_in_judet, t.total_streets,
               ROUND(100.0 * spj.streets_in_judet / t.total_streets, 1) AS pct_in_dominant
        FROM spj JOIN tot t ON t.full_name = spj.full_name
        WHERE t.total_streets >= 8
          AND spj.streets_in_judet = (
              SELECT MAX(streets_in_judet) FROM spj s2 WHERE s2.full_name = spj.full_name
          )
        ORDER BY pct_in_dominant DESC, t.total_streets DESC
        LIMIT 12
    """)
    # On ties the max-județ subquery emits one row per tied județ; keep the first
    # per person so the same honoree doesn't appear twice.
    seen_parochial: set = set()
    most_parochial = []
    for r in parochial_rows:
        if r["full_name"] in seen_parochial:
            continue
        seen_parochial.add(r["full_name"])
        r["slug"]      = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"] or "")
        r["is_native"] = (r["birth_judet"] == r["dominant_judet"])
        most_parochial.append(r)

    return {
        "forgotten_at_home": forgotten_at_home,
        "most_exported":     most_exported,
        "most_parochial":    most_parochial,
        "n_known_birth":     len(per),
    }


def section8(conn: sqlite3.Connection) -> dict:
    ciorani_row = _one(conn, """
        SELECT COUNT(*) AS total,
               SUM(is_numeric) AS numeric_streets
        FROM streets_dedup
        WHERE judet = 'PH'
          AND uat LIKE '%CIORANI%'
    """)

    longest_names = _rows(conn, """
        SELECT name, LENGTH(name) AS char_count
        FROM streets_dedup
        WHERE is_numeric = 0
          AND core_name IS NOT NULL
          AND LENGTH(name) > 30
        ORDER BY char_count DESC
        LIMIT 8
    """)

    animal_names = _contest_by_nature(conn, "animal")

    local_honorees = _rows(conn, """
        SELECT p.full_name, p.profession, sd.judet, sd.uat,
               COUNT(DISTINCT sd.siruta) AS uat_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY p.core_name_norm
        HAVING COUNT(DISTINCT sd.siruta) = 1
        ORDER BY sd.judet, sd.uat
        LIMIT 12
    """)

    # Themed contests: top-7 lemma per taxonomy
    contests = {
        "animals":  animal_names,
        "flowers":  _contest_by_nature(conn, "flower"),
        "trees":    _contest_by_nature(conn, "tree"),
        "birds":    _contest_by_nature(conn, "bird"),
        "sky":      _contest_by_nature(conn, "sky"),
        "trades":   _contest_trades(conn),
    }

    # Names where one județ holds ≥80% of national occurrences (≥5 total)
    regional_signatures = _rows(conn, """
        WITH per_name AS (
          SELECT name_normalized, COUNT(*) AS national_total
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY name_normalized
        ),
        per_jn AS (
          SELECT name_normalized, judet, MIN(name) AS display_name,
                 COUNT(*) AS local_total
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY name_normalized, judet
        )
        SELECT pj.display_name, pj.judet,
               pj.local_total, pn.national_total,
               ROUND(100.0 * pj.local_total / pn.national_total, 1) AS pct
        FROM per_jn pj
        JOIN per_name pn USING(name_normalized)
        WHERE pn.national_total >= 5
          AND 100.0 * pj.local_total / pn.national_total >= 80
        ORDER BY pn.national_total DESC, pct DESC
        LIMIT 18
    """)

    # Names existing in exactly 1 UAT nationally — atmospheric / geographic.
    # Positive filter on landscape / settlement noun prefixes that produce
    # evocative micro-toponyms ("Valea Lupului", "Dealul cu Vânt", etc.).
    # Person-honored streets and route prefixes (Strada/Aleea/...) are
    # excluded by construction.
    local_uniques = _rows(conn, """
        WITH x AS (
          SELECT sd.name_normalized,
                 MIN(sd.name) AS display_name,
                 MIN(sd.judet) AS judet, MIN(sd.uat) AS uat,
                 COUNT(DISTINCT sd.siruta) AS uat_n
          FROM streets_dedup sd
          WHERE sd.is_numeric = 0 AND sd.core_name IS NOT NULL
          GROUP BY sd.name_normalized
        )
        , prefixed AS (
          SELECT display_name, judet, uat,
                 -- First word of name = the prefix bucket
                 substr(display_name, 1, instr(display_name, ' ') - 1) AS prefix
          FROM x
          WHERE uat_n = 1
            AND LENGTH(display_name) BETWEEN 10 AND 30
            AND display_name LIKE '% %'
            AND (
              display_name LIKE 'Valea %'    OR display_name LIKE 'Dealul %'  OR
              display_name LIKE 'Plaiul %'   OR display_name LIKE 'Pârâul %'  OR
              display_name LIKE 'Lunca %'    OR display_name LIKE 'Poiana %'  OR
              display_name LIKE 'Pădurea %'  OR display_name LIKE 'Moara %'   OR
              display_name LIKE 'Cetatea %'  OR display_name LIKE 'Stejarii %' OR
              display_name LIKE 'Vatra %'    OR display_name LIKE 'Cireșii %' OR
              display_name LIKE 'Râul %'     OR display_name LIKE 'Lacul %'   OR
              display_name LIKE 'Izvorul %'  OR display_name LIKE 'Vârful %'  OR
              display_name LIKE 'Gura %'     OR display_name LIKE 'Dosul %'   OR
              display_name LIKE 'Mănăstirea %' OR display_name LIKE 'Cheile %' OR
              display_name LIKE 'Coasta %'   OR display_name LIKE 'Pietrele %' OR
              display_name LIKE 'Fântâna %'  OR display_name LIKE 'Câmpul %' OR
              display_name LIKE 'Crucea %'   OR display_name LIKE 'Movila %' OR
              display_name LIKE 'Vâlcele %'  OR display_name LIKE 'Bradului %'
            )
        ),
        ranked AS (
          SELECT display_name, judet, uat, prefix,
                 ROW_NUMBER() OVER (PARTITION BY prefix ORDER BY display_name) AS rn
          FROM prefixed
        )
        SELECT display_name, judet, uat
        FROM ranked
        WHERE rn = 1
        ORDER BY prefix
        LIMIT 14
    """)

    # Per-județ rankings — three different "characters" of a county

    # 1. Most territory-exclusive names (judet owns 100% of these names, ≥3 streets there)
    judet_distinctive = _rows(conn, """
        WITH per_name AS (
          SELECT name_normalized,
                 COUNT(DISTINCT judet) AS judet_n
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY name_normalized
        ),
        per_jn AS (
          SELECT name_normalized, judet, COUNT(*) AS local_total
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY name_normalized, judet
        )
        SELECT pj.judet, COUNT(*) AS n
        FROM per_jn pj
        JOIN per_name pn USING(name_normalized)
        WHERE pn.judet_n = 1 AND pj.local_total >= 3
        GROUP BY pj.judet
        ORDER BY n DESC LIMIT 8
    """)

    # 2. Most "rural-poetic" — highest % nature names among non-numeric streets
    judet_rural = _rows(conn, """
        SELECT sd.judet,
               ROUND(100.0 * SUM(CASE WHEN nt.nature_type IS NOT NULL THEN 1 ELSE 0 END)
                     / COUNT(*), 1) AS pct,
               COUNT(*) AS total
        FROM streets_dedup sd
        LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        WHERE sd.is_numeric = 0
        GROUP BY sd.judet
        ORDER BY pct DESC LIMIT 8
    """)

    # 3. Most ideological — highest % ideological-tagged names
    judet_ideo = _rows(conn, """
        SELECT sd.judet,
               ROUND(100.0 * SUM(CASE WHEN nc.category = 'ideological' THEN 1 ELSE 0 END)
                     / COUNT(*), 1) AS pct,
               COUNT(*) AS total
        FROM streets_dedup sd
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE sd.is_numeric = 0
        GROUP BY sd.judet
        ORDER BY pct DESC LIMIT 8
    """)

    return {
        "ciorani": {
            "total": ciorani_row.get("total", 0) or 0,
            "numeric": ciorani_row.get("numeric_streets", 0) or 0,
        },
        "longest_names": longest_names,
        "animal_names": animal_names,
        "local_honorees": local_honorees,
        "contests": contests,
        "regional_signatures": regional_signatures,
        "local_uniques": local_uniques,
        "judet_distinctive": judet_distinctive,
        "judet_rural": judet_rural,
        "judet_ideo": judet_ideo,
    }


def _contest_by_nature(conn: sqlite3.Connection, nature_type: str) -> list[dict]:
    return _rows(conn, """
        SELECT nt.term AS label, sd.name_normalized, COUNT(*) AS n
        FROM streets_dedup sd
        JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        WHERE nt.nature_type = ?
        GROUP BY nt.term
        ORDER BY n DESC
        LIMIT 7
    """, (nature_type,))


def _contest_trades(conn: sqlite3.Connection) -> list[dict]:
    # Mix of trade + occupational. Use core_name_norm display via name_normalized
    # of the most-frequent street for that lemma. The label shown is the lemma itself.
    return _rows(conn, """
        SELECT sd.name_normalized AS label,
               sd.name_normalized,
               COUNT(*) AS n
        FROM streets_dedup sd
        JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE nc.category IN ('trade', 'occupational')
        GROUP BY sd.name_normalized
        ORDER BY n DESC
        LIMIT 7
    """)


# ============================================================================
# Detail-page queries (per-entity drilldowns). All take canonical keys, not
# slugs — the build script holds the slug→key mapping.
# ============================================================================

# Macro themes resolved at runtime: a street's macro theme is the first match in
# this priority order. Mirrors `theme_composition` in queries.sql.
MACRO_THEMES = [
    ("persoana",  "Persoană",          "👤"),
    ("religios",  "Religios",          "⛪"),
    ("data",      "Dată / sărbătoare", "📅"),
    ("natura",    "Natură",            "🌿"),
    ("ideologic", "Ideologic",         "🚩"),
    ("loc",       "Loc / topografic",  "📍"),
]


def _street_theme(row: dict) -> str:
    """Pick the dominant theme label for a single streets_dedup row+joins."""
    if row.get("is_saint"):
        return "religios"
    if row.get("is_date"):
        return "data"
    if row.get("person_core"):
        return "persoana"
    if row.get("nature_core"):
        return "natura"
    if row.get("place_core"):
        return "loc"
    if row.get("ideo_subcat"):
        return "ideologic"
    return "alte"


def enumerate_streets(conn: sqlite3.Connection, min_uats: int = 5) -> list[dict]:
    """Streets with their own static page: name appears in >= min_uats UATs."""
    rows = _rows(conn, """
        SELECT sd.name_normalized,
               MIN(sd.core_name)   AS display,
               COUNT(*)            AS total,
               COUNT(DISTINCT sd.siruta) AS uat_count,
               MAX(p.wikidata_qid) AS qid,
               MAX(p.core_name_norm) AS person_core
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE sd.is_numeric = 0 AND sd.core_name IS NOT NULL
        GROUP BY sd.name_normalized
        HAVING uat_count >= ?
        ORDER BY total DESC
    """, (min_uats,))
    out = []
    seen_slugs: dict[str, str] = {}
    for r in rows:
        slug = slugify(r["display"] or r["name_normalized"])
        if not slug:
            continue
        # Resolve collisions by suffixing with a numeric counter — rare in practice.
        original = slug
        n = 2
        while slug in seen_slugs and seen_slugs[slug] != r["name_normalized"]:
            slug = f"{original}-{n}"
            n += 1
        seen_slugs[slug] = r["name_normalized"]
        out.append({
            "slug":            slug,
            "name_normalized": r["name_normalized"],
            "display":         r["display"],
            "total":           r["total"],
            "uat_count":       r["uat_count"],
            "qid":             r["qid"],
            "person_core":     r["person_core"],
        })
    return out


def enumerate_persons(conn: sqlite3.Connection) -> list[dict]:
    """Every person in the persons table — they all get a detail page."""
    rows = _rows(conn, """
        SELECT p.core_name_norm, p.full_name, p.wikidata_qid,
               COUNT(sd.id) AS street_count
        FROM persons p
        LEFT JOIN streets_dedup sd ON sd.core_name_norm = p.core_name_norm
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC, p.full_name
    """)
    out = []
    for r in rows:
        # Prefer QID — stable, unambiguous. Fall back to name slug.
        slug = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"])
        if not slug:
            continue
        out.append({
            "slug":           slug,
            "core_name_norm": r["core_name_norm"],
            "full_name":      r["full_name"],
            "qid":            r["wikidata_qid"],
            "street_count":   r["street_count"] or 0,
        })
    return out


# SIRUTA codes for the 41 county-seat municipalities (municipiu reședință de
# județ). Hardcoded because the DB carries no rank/seat metadata and the seat
# is not always the largest municipiu in the județ (e.g. HR: Miercurea-Ciuc
# has fewer streets than Odorheiu Secuiesc). Ilfov's seat Buftea is an ORAŞ,
# not MUNICIPIUL, so it would otherwise fail the rank filter.
COUNTY_SEAT_SIRUTAS: dict[str, int] = {
    "AB":  1017,  "AG":  13169, "AR":   9262, "BC": 20297,
    "BH": 26564,  "BN":  32394, "BR":  42682, "BT": 35731,
    "BV": 40198,  "BZ":  44818, "CJ":  54975, "CL": 92569,
    "CS": 50790,  "CT":  60419, "CV":  63394, "DB": 65342,
    "DJ": 69900,  "GJ":  77812, "GL":  75098, "GR": 100521,
    "HD": 86687,  "HR":  83320, "IF": 100576, "IL": 92658,
    "IS": 95060,  "MH": 109773, "MM": 106318, "MS": 114319,
    "NT": 120726, "OT": 125347, "PH": 130534, "SB": 143450,
    "SJ": 139704, "SM": 136483, "SV": 146263, "TL": 159614,
    "TM": 155243, "TR": 151790, "VL": 167473, "VN": 174744,
    "VS": 161945,
}


def enumerate_uats(conn: sqlite3.Connection, min_streets: int = 50) -> list[dict]:
    """UATs with their own detail page.

    Renders pages for:
      (a) the 41 county-seat municipalities, regardless of size or rank
      (b) the 6 Bucharest sectors
      (c) any other UAT named 'MUNICIPIUL ...' with >= min_streets streets

    Rural comune are deliberately excluded — long-tail pages saw near-zero
    traffic and the full set added meaningful build time and storage.
    Each returned dict carries an `is_capital` flag (True only for case a).
    """
    seat_set = set(COUNTY_SEAT_SIRUTAS.values())
    rows = _rows(conn, """
        SELECT sd.judet, sd.uat, sd.siruta, COUNT(*) AS total
        FROM streets_dedup sd
        GROUP BY sd.siruta
        ORDER BY total DESC
    """)
    out = []
    for r in rows:
        siruta       = r["siruta"]
        uat_raw      = r["uat"]
        is_seat      = siruta in seat_set
        is_sector    = r["judet"] == "B"
        is_municipiu = uat_raw.startswith("MUNICIPIUL ")
        if not (is_seat or is_sector or (is_municipiu and r["total"] >= min_streets)):
            continue
        uat_display = fix_diacritics(uat_raw)
        slug = slugify(uat_display)
        if not slug:
            continue
        out.append({
            "slug":       slug,
            "judet":      r["judet"],
            "siruta":     siruta,
            "uat":        uat_display,
            "total":      r["total"],
            "is_capital": is_seat,
        })
    return out


def enumerate_themes(conn: sqlite3.Connection) -> list[dict]:
    """All theme pages: profession × nature_type × ideological subcategory × macro."""
    out: list[dict] = []

    # Macro themes — fixed list, counts computed via SQL
    macro_counts = {r["theme"]: r["n"] for r in _rows(conn, """
        WITH classified AS (
          SELECT sd.id,
            CASE
              WHEN sd.is_saint = 1                       THEN 'religios'
              WHEN sd.is_date = 1                        THEN 'data'
              WHEN p.core_name_norm IS NOT NULL          THEN 'persoana'
              WHEN nt.core_name_norm IS NOT NULL         THEN 'natura'
              WHEN pl.core_name_norm IS NOT NULL         THEN 'loc'
              WHEN nc.category = 'ideological'           THEN 'ideologic'
              ELSE 'alte'
            END AS theme
          FROM streets_dedup sd
          LEFT JOIN persons p          ON p.core_name_norm  = sd.core_name_norm
          LEFT JOIN nature_terms nt    ON nt.core_name_norm = sd.core_name_norm
          LEFT JOIN place_refs pl      ON pl.core_name_norm = sd.core_name_norm
          LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        )
        SELECT theme, COUNT(*) AS n FROM classified GROUP BY theme
    """)}
    for key, label, emoji in MACRO_THEMES:
        n = macro_counts.get(key, 0)
        if n == 0:
            continue
        out.append({
            "slug": key, "type": "macro", "key": key,
            "label": label, "emoji": emoji, "count": n,
        })

    # Professions — labels from persons.profession (English keys)
    prof_ro = {
        "writer": "Scriitor", "poet": "Poet", "voievod": "Voievod",
        "politician": "Politician", "military": "Militar",
        "revolutionary": "Revoluționar", "king": "Rege",
        "scientist": "Om de știință", "painter": "Pictor",
        "composer": "Compozitor", "musician": "Muzician",
        "artist": "Artist", "clergy": "Cleric", "diplomat": "Diplomat",
        "educator": "Educator", "emperor": "Împărat",
        "engineer": "Inginer", "historian": "Istoric",
        "legendary": "Personaj legendar", "outlaw": "Haiduc",
        "philosopher": "Filozof", "royalty": "Membru al casei regale",
    }
    for r in _rows(conn, """
        SELECT p.profession AS key, COUNT(*) AS n
        FROM streets_dedup sd JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.profession IS NOT NULL
        GROUP BY p.profession ORDER BY n DESC
    """):
        slug = slugify(r["key"])
        if not slug:
            continue
        out.append({
            "slug": f"profesie-{slug}", "type": "profesie", "key": r["key"],
            "label": prof_ro.get(r["key"], r["key"].title()),
            "emoji": "🎓", "count": r["n"],
        })

    # Nature subtypes
    nature_ro = {
        "flower": "Flori", "tree": "Copaci", "bird": "Păsări",
        "animal": "Animale", "sky": "Cer / vreme", "water": "Apă",
        "mountain": "Munți", "forest": "Pădure", "fruit": "Fructe",
        "field": "Câmp", "valley": "Văi", "hill": "Dealuri",
        "peak": "Vârfuri", "meadow": "Pajiști", "orchard": "Livezi",
        "plant": "Plante", "season": "Anotimpuri",
        "geography": "Geografie", "weather": "Vreme",
    }
    for r in _rows(conn, """
        SELECT nt.nature_type AS key, COUNT(*) AS n
        FROM streets_dedup sd JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        WHERE nt.nature_type IS NOT NULL
        GROUP BY nt.nature_type ORDER BY n DESC
    """):
        slug = slugify(r["key"])
        if not slug:
            continue
        out.append({
            "slug": f"natura-{slug}", "type": "natura", "key": r["key"],
            "label": nature_ro.get(r["key"], r["key"].title()),
            "emoji": "🌿", "count": r["n"],
        })

    # Ideological subcategories
    ideo_ro = {
        "unification": "Unire", "freedom": "Libertate",
        "victory": "Victorie", "peace": "Pace",
        "independence": "Independență", "revolution": "Revoluție",
        "brotherhood": "Frăție", "homeland": "Patrie",
        "youth": "Tineret", "workers": "Muncitori",
        "labor": "Muncă", "national_day": "Ziua națională",
        "republic": "Republică", "democracy": "Democrație",
        "equality": "Egalitate", "fraternity": "Fraternitate",
        "solidarity": "Solidaritate", "emancipation": "Emancipare",
        "glory": "Glorie", "progress": "Progres", "rebirth": "Renaștere",
        "triumph": "Triumf", "liberation": "Eliberare",
        "communist_press": "Presa comunistă",
        "cooperative": "Cooperație",
    }
    for r in _rows(conn, """
        SELECT nc.subcategory AS key, COUNT(*) AS n
        FROM streets_dedup sd JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE nc.category = 'ideological' AND nc.subcategory IS NOT NULL
        GROUP BY nc.subcategory ORDER BY n DESC
    """):
        slug = slugify(r["key"])
        if not slug:
            continue
        out.append({
            "slug": f"ideologic-{slug}", "type": "ideologic", "key": r["key"],
            "label": ideo_ro.get(r["key"], r["key"].replace("_", " ").title()),
            "emoji": "🚩", "count": r["n"],
        })

    return out


def street_detail(conn: sqlite3.Connection, name_normalized: str,
                   built_uat_keys: set[tuple[str, str]] | None = None) -> dict:
    """All UATs (grouped by județ) where a given street name exists.

    Pass precomputed built_uat_keys (from enumerate_uats) to avoid rendering links
    to UAT pages that don't exist. If None, computes it internally.
    """
    rows = _rows(conn, """
        SELECT sd.judet, sd.uat, sd.siruta, sd.name, sd.core_name,
               sd.is_saint, sd.is_date,
               p.core_name_norm  AS person_core, p.full_name AS person_name,
               p.wikidata_qid    AS qid,        p.profession,
               p.era,            p.nationality,
               p.wiki_ro_url,    p.wiki_scope,
               nt.core_name_norm AS nature_core, nt.nature_type,
               pl.core_name_norm AS place_core,  pl.place_type,
               nc.category       AS ideo_cat,    nc.subcategory AS ideo_subcat
        FROM streets_dedup sd
        LEFT JOIN persons p          ON p.core_name_norm  = sd.core_name_norm
        LEFT JOIN nature_terms nt    ON nt.core_name_norm = sd.core_name_norm
        LEFT JOIN place_refs pl      ON pl.core_name_norm = sd.core_name_norm
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE sd.name_normalized = ?
        ORDER BY sd.judet, sd.uat
    """, (name_normalized,))
    if not rows:
        return {}

    first = rows[0]
    display_name = first["core_name"] or first["name"]

    # Compute built_uat_keys if not provided.
    if built_uat_keys is None:
        built_uat_keys = {(u["judet"].lower(), u["slug"]) for u in enumerate_uats(conn)}

    # Group UATs by județ, count occurrences per UAT (a street can technically appear
    # multiple times in one UAT under name variants — collapse here).
    per_uat: dict[str, dict] = {}
    for r in rows:
        key = r["siruta"]
        if key not in per_uat:
            judet_lower = r["judet"].lower()
            slug = slugify(fix_diacritics(r["uat"]))
            per_uat[key] = {
                "judet": r["judet"],
                "uat":   fix_diacritics(r["uat"]),
                "siruta": r["siruta"],
                "uat_slug": slug if (judet_lower, slug) in built_uat_keys else None,
                "count": 0,
            }
        per_uat[key]["count"] += 1

    per_judet: dict[str, dict] = defaultdict(lambda: {"judet": "", "total": 0, "uats": []})
    for u in per_uat.values():
        bucket = per_judet[u["judet"]]
        bucket["judet"] = u["judet"]
        bucket["total"] += u["count"]
        bucket["uats"].append(u)
    judet_list = sorted(per_judet.values(), key=lambda b: -b["total"])
    for b in judet_list:
        b["uats"].sort(key=lambda u: (-u["count"], u["uat"]))

    # Geographic footprint: one point per UAT that has the name, for the map.
    coords = _siruta_coords()
    map_points = []
    for u in per_uat.values():
        c = coords.get(u["siruta"])
        if c:
            map_points.append({
                "lat": c[0], "lon": c[1],
                "uat": u["uat"], "judet": u["judet"],
                "count": u["count"], "slug": u["uat_slug"],
            })
    map_points.sort(key=lambda p: -p["count"])

    honoree = None
    if first["person_core"]:
        honoree = {
            "core_name_norm": first["person_core"],
            "full_name":   first["person_name"],
            "qid":         first["qid"],
            "profession":  first["profession"],
            "era":         first["era"],
            "nationality": first["nationality"],
            "wiki_ro_url": first["wiki_ro_url"],
            "wiki_scope":  first["wiki_scope"],
            "slug":        (first["qid"] or "").lower() or slugify(first["person_name"] or ""),
        }

    return {
        "display_name":  display_name,
        "name_normalized": name_normalized,
        "total_count":   len(rows),
        "uat_count":     len(per_uat),
        "judet_count":   len(judet_list),
        "theme":         _street_theme(dict(first)),
        "honoree":       honoree,
        "per_judet":     judet_list,
        "map_points":    map_points,
        "is_saint":      bool(first["is_saint"]),
        "is_date":       bool(first["is_date"]),
        "nature_type":   first["nature_type"],
        "place_type":    first["place_type"],
        "ideo_subcat":   first["ideo_subcat"],
    }


def person_detail(conn: sqlite3.Connection, core_name_norm: str,
                   built_uat_keys: set[tuple[str, str]] | None = None) -> dict:
    """Person bio + complete street footprint.

    Pass precomputed built_uat_keys (from enumerate_uats) to avoid rendering links
    to UAT pages that don't exist. If None, computes it internally.
    """
    person = _one(conn, "SELECT * FROM persons WHERE core_name_norm = ?", (core_name_norm,))
    if not person:
        return {}

    rows = _rows(conn, """
        SELECT sd.judet, sd.uat, sd.siruta, sd.name, sd.core_name, sd.name_normalized
        FROM streets_dedup sd
        WHERE sd.core_name_norm = ?
        ORDER BY sd.judet, sd.uat
    """, (core_name_norm,))

    # Compute built_uat_keys if not provided.
    if built_uat_keys is None:
        built_uat_keys = {(u["judet"].lower(), u["slug"]) for u in enumerate_uats(conn)}

    per_uat: dict[str, dict] = {}
    for r in rows:
        if r["siruta"] not in per_uat:
            judet_lower = r["judet"].lower()
            slug = slugify(fix_diacritics(r["uat"]))
            per_uat[r["siruta"]] = {
                "judet": r["judet"], "uat": fix_diacritics(r["uat"]),
                "siruta": r["siruta"],
                "uat_slug": slug if (judet_lower, slug) in built_uat_keys else None,
                "count": 0,
            }
        per_uat[r["siruta"]]["count"] += 1

    per_judet: dict[str, dict] = defaultdict(lambda: {"judet": "", "total": 0, "uats": []})
    for u in per_uat.values():
        bucket = per_judet[u["judet"]]
        bucket["judet"] = u["judet"]
        bucket["total"] += u["count"]
        bucket["uats"].append(u)
    for b in per_judet.values():
        b["uats"].sort(key=lambda u: (-u["count"], u["uat"]))
    judet_list = sorted(per_judet.values(), key=lambda b: -b["total"])

    # Peers: other persons sharing profession or era
    peers = _rows(conn, """
        SELECT p.core_name_norm, p.full_name, p.wikidata_qid,
               COUNT(sd.id) AS street_count
        FROM persons p
        LEFT JOIN streets_dedup sd ON sd.core_name_norm = p.core_name_norm
        WHERE p.core_name_norm != ?
          AND (p.profession = ? OR p.era = ?)
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 8
    """, (core_name_norm, person.get("profession") or "", person.get("era") or ""))
    for pr in peers:
        pr["slug"] = (pr["wikidata_qid"] or "").lower() or slugify(pr["full_name"])

    return {
        "person":      person,
        "total":       len(rows),
        "uat_count":   len(per_uat),
        "judet_count": len(per_judet),
        "per_judet":   judet_list,
        "peers":       peers,
    }


def uat_detail(
    conn: sqlite3.Connection,
    siruta: str,
    *,
    global_rarity: dict | None = None,
    nat: dict | None = None,
) -> dict:
    """All streets in one UAT, themed and ranked, with national-average deltas.

    Pass precomputed `global_rarity` (name_normalized → uat_count) and `nat`
    (saint_pct, numeric_pct) to avoid per-call full-table scans when building
    all 672 UAT pages in a loop.
    """
    head = _one(conn, """
        SELECT judet, uat, siruta, COUNT(*) AS total,
               SUM(is_saint)   AS saints,
               SUM(is_numeric) AS numerics
        FROM streets_dedup
        WHERE siruta = ?
        GROUP BY siruta
    """, (siruta,))
    if not head:
        return {}

    # Theme breakdown for this UAT
    theme_rows = _rows(conn, """
        WITH classified AS (
          SELECT
            CASE
              WHEN sd.is_saint = 1                       THEN 'religios'
              WHEN sd.is_date = 1                        THEN 'data'
              WHEN sd.is_numeric = 1                     THEN 'numeric'
              WHEN p.core_name_norm IS NOT NULL          THEN 'persoana'
              WHEN nt.core_name_norm IS NOT NULL         THEN 'natura'
              WHEN pl.core_name_norm IS NOT NULL         THEN 'loc'
              WHEN nc.category = 'ideological'           THEN 'ideologic'
              ELSE 'alte'
            END AS theme
          FROM streets_dedup sd
          LEFT JOIN persons p          ON p.core_name_norm  = sd.core_name_norm
          LEFT JOIN nature_terms nt    ON nt.core_name_norm = sd.core_name_norm
          LEFT JOIN place_refs pl      ON pl.core_name_norm = sd.core_name_norm
          LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
          WHERE sd.siruta = ?
        )
        SELECT theme, COUNT(*) AS n FROM classified GROUP BY theme ORDER BY n DESC
    """, (siruta,))

    # Top street names within this UAT — group by name_normalized.
    top_streets = _rows(conn, """
        SELECT sd.name_normalized, MIN(sd.core_name) AS display,
               COUNT(*) AS n, MAX(p.wikidata_qid) AS qid,
               MAX(p.core_name_norm) AS person_core
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE sd.siruta = ? AND sd.is_numeric = 0 AND sd.core_name IS NOT NULL
        GROUP BY sd.name_normalized
        ORDER BY n DESC, display
        LIMIT 20
    """, (siruta,))
    for r in top_streets:
        r["slug"] = slugify(r["display"] or r["name_normalized"])

    top_persons = _rows(conn, """
        SELECT p.full_name, p.wikidata_qid, p.core_name_norm, p.profession,
               COUNT(*) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE sd.siruta = ?
        GROUP BY p.core_name_norm
        ORDER BY n DESC, p.full_name
        LIMIT 12
    """, (siruta,))
    for r in top_persons:
        r["slug"] = (r["wikidata_qid"] or "").lower() or slugify(r["full_name"])

    # Names rare nationally but present here.
    # When global_rarity is precomputed (batch build), fetch only this UAT's
    # names and filter in Python — avoids a full-scan CTE on every call.
    if global_rarity is not None:
        uat_names = _rows(conn, """
            SELECT sd.name_normalized, MIN(sd.core_name) AS display
            FROM streets_dedup sd
            WHERE sd.siruta = ? AND sd.is_numeric = 0 AND sd.core_name IS NOT NULL
            GROUP BY sd.name_normalized
        """, (siruta,))
        distinctive = sorted(
            [{"name_normalized": r["name_normalized"],
              "display": r["display"],
              "uat_n": global_rarity[r["name_normalized"]],
              "slug": slugify(r["display"] or r["name_normalized"])}
             for r in uat_names
             if global_rarity.get(r["name_normalized"], 99) <= 3],
            key=lambda x: (x["uat_n"], x["display"] or ""),
        )[:12]
    else:
        distinctive = _rows(conn, """
            WITH global_rarity AS (
              SELECT name_normalized, COUNT(DISTINCT siruta) AS uat_n
              FROM streets_dedup
              WHERE is_numeric = 0 AND core_name IS NOT NULL
              GROUP BY name_normalized
            )
            SELECT sd.name_normalized, MIN(sd.core_name) AS display, gr.uat_n
            FROM streets_dedup sd
            JOIN global_rarity gr ON gr.name_normalized = sd.name_normalized
            WHERE sd.siruta = ? AND sd.is_numeric = 0 AND sd.core_name IS NOT NULL
              AND gr.uat_n <= 3
            GROUP BY sd.name_normalized, gr.uat_n
            ORDER BY gr.uat_n, display
            LIMIT 12
        """, (siruta,))
        for r in distinctive:
            r["slug"] = slugify(r["display"] or r["name_normalized"])

    # National averages — precomputed by caller in batch mode.
    if nat is None:
        nat = _one(conn, """
            SELECT
              ROUND(100.0 * SUM(is_saint)   / COUNT(*), 2) AS saint_pct,
              ROUND(100.0 * SUM(is_numeric) / COUNT(*), 2) AS numeric_pct
            FROM streets_dedup
        """)
    saint_pct   = round(100.0 * (head["saints"]   or 0) / head["total"], 2) if head["total"] else 0
    numeric_pct = round(100.0 * (head["numerics"] or 0) / head["total"], 2) if head["total"] else 0

    return {
        "uat":         fix_diacritics(head["uat"]),
        "judet":       head["judet"],
        "siruta":      head["siruta"],
        "total":       head["total"],
        "saint_pct":   saint_pct,
        "numeric_pct": numeric_pct,
        "delta_saint":   round(saint_pct   - (nat["saint_pct"]   or 0), 2),
        "delta_numeric": round(numeric_pct - (nat["numeric_pct"] or 0), 2),
        "themes":      theme_rows,
        "top_streets": top_streets,
        "top_persons": top_persons,
        "distinctive": distinctive,
    }


def _theme_where(theme_type: str, theme_key: str):
    """Return (join_clause, where_clause, params) for theme filtering.

    macro themes pass a sentinel through theme_key (persoana, natura, religios, etc.);
    other types pass the raw DB key (profession/nature_type/subcategory value).
    """
    if theme_type == "macro":
        if theme_key == "religios":
            return "", "sd.is_saint = 1", ()
        if theme_key == "data":
            return "", "sd.is_date = 1", ()
        if theme_key == "persoana":
            return "JOIN persons p ON p.core_name_norm = sd.core_name_norm", "1 = 1", ()
        if theme_key == "natura":
            return "JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm", "1 = 1", ()
        if theme_key == "loc":
            return "JOIN place_refs pl ON pl.core_name_norm = sd.core_name_norm", "1 = 1", ()
        if theme_key == "ideologic":
            return ("JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm",
                    "nc.category = 'ideological'", ())
        return "", "1 = 0", ()
    if theme_type == "profesie":
        return ("JOIN persons p ON p.core_name_norm = sd.core_name_norm",
                "p.profession = ?", (theme_key,))
    if theme_type == "natura":
        return ("JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm",
                "nt.nature_type = ?", (theme_key,))
    if theme_type == "ideologic":
        return ("JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm",
                "nc.category = 'ideological' AND nc.subcategory = ?", (theme_key,))
    return "", "1 = 0", ()


def theme_detail(conn: sqlite3.Connection, theme_type: str, theme_key: str) -> dict:
    """Streets belonging to a theme, ranked by popularity, with județ heatmap."""
    join_clause, where_clause, params = _theme_where(theme_type, theme_key)

    # Only add a persons join for qid/person_core display if the filter join
    # doesn't already include one (avoids duplicate alias conflicts).
    person_join = (
        "" if "persons p" in join_clause
        else "LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm"
    )

    top_streets = _rows(conn, f"""
        SELECT sd.name_normalized, MIN(sd.core_name) AS display,
               MAX(p.wikidata_qid) AS qid,
               MAX(p.core_name_norm) AS person_core,
               COUNT(*) AS total,
               COUNT(DISTINCT sd.siruta) AS uat_count
        FROM streets_dedup sd
        {join_clause}
        {person_join}
        WHERE {where_clause}
          AND sd.is_numeric = 0 AND sd.core_name IS NOT NULL
        GROUP BY sd.name_normalized
        ORDER BY total DESC
        LIMIT 60
    """, params)
    for r in top_streets:
        r["slug"] = slugify(r["display"] or r["name_normalized"])

    # Județ heatmap data
    per_judet = _rows(conn, f"""
        SELECT sd.judet, COUNT(*) AS n
        FROM streets_dedup sd
        {join_clause}
        WHERE {where_clause}
          AND sd.is_numeric = 0
        GROUP BY sd.judet
        ORDER BY n DESC
    """, params)

    total = sum(r["n"] for r in per_judet)

    return {
        "type":        theme_type,
        "key":         theme_key,
        "total":       total,
        "top_streets": top_streets,
        "per_judet":   per_judet,
    }


def explorer_indexes(conn: sqlite3.Connection) -> dict:
    """Compact JSON indexes for the /cauta/ autocomplete page.

    Each street row carries a `p` flag — 1 if a detail page exists for the
    slug, 0 if the entity is only in the DB. The autocomplete renders the
    latter as disabled rows with a "fără pagină proprie" label rather than
    a 404-bound link.
    """
    # Map name_normalized → (slug, has_page) using the exact slugs assigned
    # during page rendering. Matching on name_normalized (not bare slug)
    # avoids two failure modes: (a) streets with uat_count < 5 that don't
    # render but coincidentally share a slug with a rendered one, (b)
    # rendered streets whose slug was suffixed (-2, -3) due to collision.
    rendered_by_namenorm = {
        s["name_normalized"]: s["slug"] for s in enumerate_streets(conn)
    }

    streets = _rows(conn, """
        SELECT sd.name_normalized, MIN(sd.core_name) AS display,
               COUNT(*) AS total, COUNT(DISTINCT sd.siruta) AS uat_count
        FROM streets_dedup sd
        WHERE sd.is_numeric = 0 AND sd.core_name IS NOT NULL
        GROUP BY sd.name_normalized
        ORDER BY total DESC
    """)
    street_idx = []
    for r in streets:
        rendered_slug = rendered_by_namenorm.get(r["name_normalized"])
        # Use the rendered slug when available (preserves -2 suffix);
        # otherwise fall back to the bare slug for the no-page label.
        slug = rendered_slug or slugify(r["display"] or r["name_normalized"])
        if not slug:
            continue
        street_idx.append({
            "s": slug,
            "n": r["display"],
            "t": r["total"],
            "u": r["uat_count"],
            "p": 1 if rendered_slug else 0,
        })

    # Only index UATs that have a rendered detail page — otherwise search
    # results 404 on the long-tail comune we no longer build. Rural UATs
    # could come back via a future DB-backed endpoint; for now they're
    # simply hidden from the autocomplete.
    uat_idx = [
        {"s": u["slug"], "j": u["judet"], "n": u["uat"], "t": u["total"]}
        for u in enumerate_uats(conn)
    ]
    uat_idx.sort(key=lambda x: x["n"])

    return {"streets": street_idx, "uats": uat_idx}


def browser_export(conn: sqlite3.Connection) -> dict:
    """Pre-compute compact view data written to dist/browser/data.json.

    Returns {"meta": {dropdown options}, "rows": [{compact row}, ...]}.
    All grouped rows sorted by national count DESC; null fields omitted.
    """
    def col(sql):
        return [r[0] for r in conn.execute(sql)]

    meta = {
        "judete":          col("SELECT DISTINCT judet FROM streets_dedup WHERE judet IS NOT NULL ORDER BY judet"),
        "street_types":    col("SELECT DISTINCT street_type FROM streets_dedup WHERE street_type IS NOT NULL ORDER BY street_type"),
        "professions":     col("SELECT DISTINCT profession FROM persons WHERE profession IS NOT NULL ORDER BY profession"),
        "nationalities":   col("SELECT DISTINCT nationality FROM persons WHERE nationality IS NOT NULL ORDER BY nationality"),
        "genders":         col("SELECT DISTINCT gender FROM persons WHERE gender IS NOT NULL ORDER BY gender"),
        "eras":            col("SELECT DISTINCT era FROM persons WHERE era IS NOT NULL ORDER BY era"),
        "wiki_scopes":     col("SELECT DISTINCT wiki_scope FROM persons WHERE wiki_scope IS NOT NULL ORDER BY wiki_scope"),
        "categories":      col("SELECT DISTINCT category FROM name_categories WHERE category IS NOT NULL ORDER BY category"),
        "subcategories":   col("SELECT DISTINCT subcategory FROM name_categories WHERE subcategory IS NOT NULL ORDER BY subcategory"),
        "nature_types":    col("SELECT DISTINCT nature_type FROM nature_terms WHERE nature_type IS NOT NULL ORDER BY nature_type"),
        "place_types":     col("SELECT DISTINCT place_type FROM place_refs WHERE place_type IS NOT NULL ORDER BY place_type"),
        "place_countries": col("SELECT DISTINCT country FROM place_refs WHERE country IS NOT NULL ORDER BY country"),
    }

    raw = _rows(conn, """
        SELECT
            MAX(sd.name)            AS name,
            sd.name_normalized,
            MAX(sd.core_name)       AS core_name,
            COUNT(*)                AS name_count,
            GROUP_CONCAT(DISTINCT sd.judet)       AS judete,
            GROUP_CONCAT(DISTINCT sd.street_type) AS street_types,
            CASE
                WHEN MAX(sd.is_numeric) = 1             THEN 'numeric'
                WHEN MAX(sd.is_date)    = 1             THEN 'date'
                WHEN MAX(sd.is_saint)   = 1             THEN 'saint'
                WHEN MAX(p.core_name_norm)  IS NOT NULL THEN 'person'
                WHEN MAX(n.core_name_norm)  IS NOT NULL THEN 'nature'
                WHEN MAX(c.core_name_norm)  IS NOT NULL THEN 'category'
                WHEN MAX(pr.core_name_norm) IS NOT NULL THEN 'place'
                ELSE NULL
            END AS classification,
            MAX(p.wikidata_qid)   AS wikidata_qid,
            MAX(p.full_name)      AS person_full_name,
            MAX(p.profession)     AS profession,
            MAX(p.nationality)    AS nationality,
            MAX(p.gender)         AS gender,
            MAX(p.era)            AS era,
            MAX(p.wiki_scope)     AS wiki_scope,
            MAX(c.category)       AS category,
            MAX(c.subcategory)    AS subcategory,
            MAX(n.nature_type)    AS nature_type,
            MAX(pr.place_type)    AS place_type,
            MAX(pr.country)       AS place_country
        FROM streets_dedup sd
        LEFT JOIN persons         p  ON p.core_name_norm  = sd.core_name_norm
        LEFT JOIN name_categories c  ON c.core_name_norm  = sd.core_name_norm
        LEFT JOIN nature_terms    n  ON n.core_name_norm  = sd.core_name_norm
        LEFT JOIN place_refs      pr ON pr.core_name_norm = sd.core_name_norm
        WHERE sd.name_normalized != ''
        GROUP BY sd.name_normalized
        ORDER BY name_count DESC
    """)

    rows = []
    for r in raw:
        core = r["core_name"] or r["name_normalized"]
        row = {
            "n":  r["name"],
            "nn": r["name_normalized"],
            "c":  r["name_count"],
            "j":  r["judete"].split(",") if r["judete"] else [],
            "st": [x for x in (r["street_types"] or "").split(",") if x],
            "sl": slugify(core),
        }
        for src, dst in [
            ("classification",  "cls"), ("wikidata_qid",    "q"),
            ("person_full_name","pn"),  ("profession",      "pr"),
            ("nationality",     "na"),  ("gender",          "g"),
            ("era",             "er"),  ("wiki_scope",      "sc"),
            ("category",        "cat"), ("subcategory",     "sub"),
            ("nature_type",     "nt"),  ("place_type",      "pt"),
            ("place_country",   "pc"),
        ]:
            if r.get(src) is not None:
                row[dst] = r[src]
        rows.append(row)

    return {"meta": meta, "rows": rows}


def municipii_index(conn: sqlite3.Connection) -> dict:
    """Per-municipiu data for the landing-page UAT filter dropdown.

    Only covers UATs whose name starts with 'MUNICIPIUL' (~102 UATs).
    Returns compact dicts to keep JSON payload manageable.
    """
    # List of municipii per județ
    list_rows = _rows(conn, """
        SELECT CASE WHEN judet LIKE 'BUCURESTI%%' OR judet = 'B' THEN 'B'
                    ELSE judet END AS judet,
               siruta, uat, COUNT(*) AS total
        FROM streets_dedup
        WHERE uat LIKE 'MUNICIPIUL%%' AND is_numeric = 0
        GROUP BY siruta, uat, judet
        ORDER BY judet, total DESC
    """)
    by_judet: dict[str, list[dict]] = {}
    for r in list_rows:
        slug = slugify(r["uat"])
        by_judet.setdefault(r["judet"], []).append({
            "s": str(r["siruta"]), "n": r["uat"].title(), "sl": slug, "t": r["total"],
        })

    # Top-25 streets per municipiu, ordered by national occurrence count so the
    # most recognisable names appear first (each name appears exactly once per UAT
    # in streets_dedup, so national frequency is the meaningful ranking signal).
    streets_rows = _rows(conn, """
        WITH nat AS (
          SELECT name_normalized, COUNT(DISTINCT siruta) AS nat_count
          FROM streets_dedup
          WHERE is_numeric = 0 AND core_name IS NOT NULL
          GROUP BY name_normalized
        ),
        uat_streets AS (
          SELECT sd.siruta, sd.name_normalized, MIN(sd.core_name) AS core_name,
                 MAX(p.wikidata_qid) AS wikidata_qid,
                 CASE WHEN MAX(p.core_name_norm) IS NOT NULL THEN 'persoana'
                      WHEN MAX(nt.core_name_norm) IS NOT NULL THEN 'natura'
                      WHEN MAX(sd.is_saint) = 1 THEN 'religios'
                      ELSE 'altele' END AS category
          FROM streets_dedup sd
          LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
          LEFT JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
          WHERE sd.is_numeric = 0 AND sd.core_name IS NOT NULL
            AND sd.uat LIKE 'MUNICIPIUL%%'
          GROUP BY sd.siruta, sd.name_normalized
        ),
        ranked AS (
          SELECT u.siruta, u.name_normalized, u.core_name, u.wikidata_qid, u.category,
                 COALESCE(n.nat_count, 1) AS street_count,
                 ROW_NUMBER() OVER (
                   PARTITION BY u.siruta ORDER BY COALESCE(n.nat_count, 1) DESC
                 ) AS rn
          FROM uat_streets u
          LEFT JOIN nat n ON n.name_normalized = u.name_normalized
        )
        SELECT siruta, name_normalized, core_name, wikidata_qid, category, street_count
        FROM ranked WHERE rn <= 25
        ORDER BY siruta, street_count DESC
    """)
    streets_by_siruta: dict[str, list[dict]] = {}
    for r in streets_rows:
        slug = slugify(r["core_name"] or r["name_normalized"])
        streets_by_siruta.setdefault(str(r["siruta"]), []).append({
            "n": r["core_name"], "nn": r["name_normalized"],
            "c": r["street_count"], "cat": r["category"], "sl": slug,
        })

    # Top-10 persons (M) per municipiu
    def _persons_by_siruta(gender: str) -> dict[str, list[dict]]:
        rows = _rows(conn, f"""
            WITH ranked AS (
              SELECT sd.siruta, p.core_name_norm,
                     MAX(p.full_name) AS full_name, MAX(p.gender) AS gender,
                     MAX(p.wikidata_qid) AS wikidata_qid, COUNT(*) AS street_count,
                     ROW_NUMBER() OVER (PARTITION BY sd.siruta ORDER BY COUNT(*) DESC) AS rn
              FROM streets_dedup sd
              JOIN persons p ON p.core_name_norm = sd.core_name_norm
              WHERE sd.uat LIKE 'MUNICIPIUL%%' AND p.gender = '{gender}'
              GROUP BY sd.siruta, p.core_name_norm
            )
            SELECT siruta, full_name, gender, wikidata_qid, street_count
            FROM ranked WHERE rn <= 10
            ORDER BY siruta, street_count DESC
        """)
        out: dict[str, list[dict]] = {}
        for r in rows:
            slug = (r.get("wikidata_qid") or "").lower() or slugify(r.get("full_name") or "")
            out.setdefault(str(r["siruta"]), []).append({
                "n": r["full_name"], "qid": r["wikidata_qid"],
                "c": r["street_count"], "sl": slug,
            })
        return out

    # Gender counts per municipiu for the grid
    gender_rows = _rows(conn, """
        SELECT sd.siruta,
               SUM(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) AS m,
               SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) AS f
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE sd.uat LIKE 'MUNICIPIUL%%'
        GROUP BY sd.siruta
    """)
    gender_by_siruta = {str(r["siruta"]): {"m": r["m"], "f": r["f"]} for r in gender_rows}

    # Theme counts per municipiu
    theme_rows = _rows(conn, """
        SELECT sd.siruta,
               SUM(CASE WHEN p.core_name_norm  IS NOT NULL THEN 1 ELSE 0 END) AS persoana,
               SUM(CASE WHEN nt.core_name_norm IS NOT NULL THEN 1 ELSE 0 END) AS natura,
               SUM(CASE WHEN sd.is_saint = 1   THEN 1 ELSE 0 END) AS religios,
               SUM(CASE WHEN sd.is_date  = 1   THEN 1 ELSE 0 END) AS data_sab,
               SUM(CASE WHEN nc.category = 'ideological' THEN 1 ELSE 0 END) AS ideologic,
               SUM(CASE WHEN nc.category IN ('abstract','commemorative','institutional') THEN 1 ELSE 0 END) AS abstract,
               COUNT(*) AS total
        FROM streets_dedup sd
        LEFT JOIN persons p       ON p.core_name_norm  = sd.core_name_norm
        LEFT JOIN nature_terms nt  ON nt.core_name_norm = sd.core_name_norm
        LEFT JOIN name_categories nc ON nc.core_name_norm = sd.core_name_norm
        WHERE sd.uat LIKE 'MUNICIPIUL%%' AND sd.is_numeric = 0
        GROUP BY sd.siruta
    """)
    theme_by_siruta = {
        str(r["siruta"]): {
            "persoană": r["persoana"], "natură": r["natura"],
            "religios": r["religios"], "dată / sărbătoare": r["data_sab"],
            "ideologic": r["ideologic"], "concept / abstract": r["abstract"],
            "total": r["total"],
        }
        for r in theme_rows
    }

    return {
        "by_judet": by_judet,
        "streets": streets_by_siruta,
        "men": _persons_by_siruta("M"),
        "women": _persons_by_siruta("F"),
        "gender": gender_by_siruta,
        "themes": theme_by_siruta,
    }


def get_source_coverage_by_judet(conn: sqlite3.Connection) -> list[dict]:
    """Per-source street coverage by județul, sorted by total descending."""
    rows = _rows(conn, """
        SELECT judet,
          SUM(EXISTS(SELECT 1 FROM json_each(a.variants) je WHERE json_extract(je.value,'$.source')='registry')) AS registry,
          SUM(EXISTS(SELECT 1 FROM json_each(a.variants) je WHERE json_extract(je.value,'$.source')='osm')) AS osm,
          SUM(EXISTS(SELECT 1 FROM json_each(a.variants) je WHERE json_extract(je.value,'$.source')='postal')) AS postal,
          SUM(EXISTS(SELECT 1 FROM json_each(a.variants) je WHERE json_extract(je.value,'$.source')='renns')) AS renns,
          COUNT(*) AS total,
          COUNT(DISTINCT siruta) AS uats
        FROM all_street_names a
        GROUP BY judet
        ORDER BY total DESC
    """)
    return rows
