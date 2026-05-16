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

    # Top-30 within each județ — drives the județ filter dropdown.
    # Bucharest sectors aggregate as 'B' to match the rest of the site.
    by_judet_rows = _rows(conn, """
        WITH judet_named AS (
          SELECT
            CASE WHEN sd.judet LIKE 'BUCURESTI%' OR sd.judet = 'B' THEN 'B'
                 ELSE sd.judet END AS judet,
            sd.name_normalized,
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
          SELECT judet, name_normalized, category,
                 COUNT(*) AS street_count,
                 ROW_NUMBER() OVER (PARTITION BY judet ORDER BY COUNT(*) DESC) AS rn
          FROM judet_named
          GROUP BY judet, name_normalized
        )
        SELECT judet, name_normalized, category, street_count
        FROM ranked
        WHERE rn <= 30
        ORDER BY judet, street_count DESC
    """)
    by_judet: dict[str, list[dict]] = {}
    for r in by_judet_rows:
        by_judet.setdefault(r["judet"], []).append({
            "name_normalized": r["name_normalized"],
            "street_count": r["street_count"],
            "category": r["category"],
        })

    return {"top_names": top_names, "by_judet": by_judet}


def section3(conn: sqlite3.Connection) -> dict:
    top_persons = _rows(conn, """
        SELECT p.full_name, p.gender, p.profession, p.era,
               COALESCE(p.wiki_scope, 'unknown') AS wiki_scope,
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
