# site_queries.py
import sqlite3
from collections import defaultdict

from streets_lib import slugify, fix_diacritics


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
              SELECT judet, full_name, nationality, wikidata_qid, street_count,
                     ROW_NUMBER() OVER (PARTITION BY judet ORDER BY street_count DESC) AS rn
              FROM per_judet
            )
            SELECT judet, full_name, nationality, wikidata_qid, street_count
            FROM ranked WHERE rn <= 10
            ORDER BY judet, street_count DESC
        """)
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r["judet"], []).append({
                "full_name":    r["full_name"],
                "nationality": r["nationality"],
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

    return {
        "top_persons": top_persons,
        "persons_by_judet": persons_by_judet,
        "top_men": top_men,
        "top_women": top_women,
        "men_by_judet": men_by_judet,
        "women_by_judet": women_by_judet,
        "foreigners_by_judet": foreigners_by_judet,
        "total_m": counts.get("m", 0) or 0,
        "total_f": counts.get("f", 0) or 0,
        "profession_dist": profession_dist,
        "era_dist": era_dist,
        "top_foreigners": top_foreigners,
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

    return {
        "top_pageviews": top_pageviews,
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

    return {
        "theme_dist": theme_dist,
        "nature_subtypes": nature_subtypes,
        "ideo_tokens": ideo_tokens,
    }


def section6(conn: sqlite3.Connection) -> dict:
    by_judet = _rows(conn, """
        SELECT judet,
               COUNT(*) AS total_streets,
               ROUND(100.0 * SUM(is_saint) / COUNT(*), 1) AS saint_pct,
               ROUND(100.0 * SUM(is_numeric) / COUNT(*), 1) AS numeric_pct,
               ROUND(100.0 * SUM(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS female_pct
        FROM streets_dedup sd
        LEFT JOIN persons p ON p.core_name_norm = sd.core_name_norm
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


def enumerate_uats(conn: sqlite3.Connection, min_streets: int = 50) -> list[dict]:
    """UATs with their own page: >= min_streets total streets."""
    rows = _rows(conn, """
        SELECT sd.judet, sd.uat, sd.siruta, COUNT(*) AS total
        FROM streets_dedup sd
        GROUP BY sd.siruta
        HAVING total >= ?
        ORDER BY total DESC
    """, (min_streets,))
    out = []
    for r in rows:
        uat_display = fix_diacritics(r["uat"])
        slug = slugify(uat_display)
        if not slug:
            continue
        out.append({
            "slug":    slug,
            "judet":   r["judet"],
            "siruta":  r["siruta"],
            "uat":     uat_display,
            "total":   r["total"],
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


def street_detail(conn: sqlite3.Connection, name_normalized: str) -> dict:
    """All UATs (grouped by județ) where a given street name exists."""
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

    # Group UATs by județ, count occurrences per UAT (a street can technically appear
    # multiple times in one UAT under name variants — collapse here).
    per_uat: dict[str, dict] = {}
    for r in rows:
        key = r["siruta"]
        if key not in per_uat:
            per_uat[key] = {
                "judet": r["judet"],
                "uat":   fix_diacritics(r["uat"]),
                "siruta": r["siruta"],
                "uat_slug": slugify(fix_diacritics(r["uat"])),
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
        "is_saint":      bool(first["is_saint"]),
        "is_date":       bool(first["is_date"]),
        "nature_type":   first["nature_type"],
        "place_type":    first["place_type"],
        "ideo_subcat":   first["ideo_subcat"],
    }


def person_detail(conn: sqlite3.Connection, core_name_norm: str) -> dict:
    """Person bio + complete street footprint."""
    person = _one(conn, "SELECT * FROM persons WHERE core_name_norm = ?", (core_name_norm,))
    if not person:
        return {}

    rows = _rows(conn, """
        SELECT sd.judet, sd.uat, sd.siruta, sd.name, sd.core_name, sd.name_normalized
        FROM streets_dedup sd
        WHERE sd.core_name_norm = ?
        ORDER BY sd.judet, sd.uat
    """, (core_name_norm,))

    per_uat: dict[str, dict] = {}
    for r in rows:
        if r["siruta"] not in per_uat:
            per_uat[r["siruta"]] = {
                "judet": r["judet"], "uat": fix_diacritics(r["uat"]),
                "siruta": r["siruta"],
                "uat_slug": slugify(fix_diacritics(r["uat"])),
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


def uat_detail(conn: sqlite3.Connection, siruta: str) -> dict:
    """All streets in one UAT, themed and ranked, with national-average deltas."""
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

    # Names rare nationally but present here
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

    # National averages (single row, joined in Python for clarity)
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
    """Compact JSON indexes for the /cauta/ autocomplete page."""
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
        slug = slugify(r["display"] or r["name_normalized"])
        if not slug:
            continue
        street_idx.append({
            "s": slug,
            "n": r["display"],
            "t": r["total"],
            "u": r["uat_count"],
        })

    uats = _rows(conn, """
        SELECT siruta, judet, uat, COUNT(*) AS total
        FROM streets_dedup
        GROUP BY siruta
        ORDER BY uat
    """)
    uat_idx = []
    for r in uats:
        uat_display = fix_diacritics(r["uat"])
        slug = slugify(uat_display)
        if not slug:
            continue
        uat_idx.append({
            "s": slug, "j": r["judet"], "n": uat_display, "t": r["total"],
        })

    return {"streets": street_idx, "uats": uat_idx}
