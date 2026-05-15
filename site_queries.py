# site_queries.py
import sqlite3


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
    top_names = _rows(conn, """
        SELECT
          sd.name_normalized,
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
    return {"top_names": top_names}


def section3(conn: sqlite3.Connection) -> dict:
    top_persons = _rows(conn, """
        SELECT p.full_name, p.gender, p.profession, p.era,
               COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY p.core_name_norm
        ORDER BY street_count DESC
        LIMIT 20
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

    era_dist = _rows(conn, """
        SELECT COALESCE(p.era, 'necunoscută') AS era,
               COUNT(DISTINCT p.core_name_norm) AS n
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY era
        ORDER BY n DESC
        LIMIT 6
    """)

    return {
        "top_persons": top_persons,
        "total_m": counts.get("m", 0) or 0,
        "total_f": counts.get("f", 0) or 0,
        "profession_dist": profession_dist,
        "era_dist": era_dist,
    }


def section4(conn: sqlite3.Connection) -> dict:
    top_pageviews = _rows(conn, """
        SELECT p.full_name, p.wiki_scope, p.wiki_sitelinks,
               p.wiki_ro_views, p.wiki_ro_url,
               COUNT(*) AS street_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        WHERE p.wiki_ro_views IS NOT NULL AND p.wiki_ro_views > 0
        GROUP BY p.core_name_norm
        ORDER BY p.wiki_ro_views DESC
        LIMIT 10
    """)

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
            top_map[j].append({"n": r["display_name"], "c": r["cnt"]})

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
        rare_map[j].append({"n": r["display_name"], "j": r["judet_count"]})

    persons_rows = _rows(conn, """
        WITH ranked AS (
          SELECT sd.judet,
                 p.full_name,
                 MAX(p.gender) AS gender,
                 MAX(p.wiki_scope) AS wiki_scope,
                 COUNT(*) AS cnt,
                 ROW_NUMBER() OVER (
                   PARTITION BY sd.judet ORDER BY COUNT(*) DESC
                 ) AS rn
          FROM streets_dedup sd
          JOIN persons p ON p.core_name_norm = sd.core_name_norm
          WHERE sd.is_numeric = 0
          GROUP BY sd.judet, p.full_name
        )
        SELECT judet, full_name, gender, wiki_scope, cnt FROM ranked WHERE rn <= 5
        ORDER BY judet, cnt DESC
    """)
    persons_map: dict[str, list] = {}
    for r in persons_rows:
        j = r["judet"]
        if j not in persons_map:
            persons_map[j] = []
        persons_map[j].append({
            "n": r["full_name"],
            "g": r["gender"],
            "s": r["wiki_scope"],
            "c": r["cnt"],
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

    animal_names = _rows(conn, """
        SELECT nt.term AS animal_ro, sd.name_normalized, COUNT(*) AS n
        FROM streets_dedup sd
        JOIN nature_terms nt ON nt.core_name_norm = sd.core_name_norm
        WHERE nt.nature_type = 'animal'
        GROUP BY nt.term
        ORDER BY n DESC
        LIMIT 10
    """)

    local_honorees = _rows(conn, """
        SELECT p.full_name, p.profession, sd.judet, sd.uat,
               COUNT(DISTINCT sd.siruta) AS uat_count
        FROM streets_dedup sd
        JOIN persons p ON p.core_name_norm = sd.core_name_norm
        GROUP BY p.core_name_norm
        HAVING COUNT(DISTINCT sd.siruta) = 1
        ORDER BY sd.judet, sd.uat
        LIMIT 10
    """)

    return {
        "ciorani": {
            "total": ciorani_row.get("total", 0) or 0,
            "numeric": ciorani_row.get("numeric_streets", 0) or 0,
        },
        "longest_names": longest_names,
        "animal_names": animal_names,
        "local_honorees": local_honorees,
    }
