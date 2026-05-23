-- ================================================================
-- DASHBOARD QUERY CATALOG
-- Organized by view. Each block targets one panel/chart.
-- All queries operate on `streets_dedup` (one row per UAT-street).
-- ================================================================


-- ============= CURATION COVERAGE =============

-- Street-level classification coverage (run after curation updates)
-- :name coverage_summary
WITH classified AS (
  SELECT s.id,
    CASE
      WHEN s.is_numeric = 1                       THEN 'numeric'
      WHEN s.is_date    = 1                       THEN 'date'
      WHEN s.is_saint   = 1                       THEN 'religious'
      WHEN p.core_name_norm  IS NOT NULL          THEN 'person'
      WHEN n.core_name_norm  IS NOT NULL          THEN 'nature'
      WHEN pl.core_name_norm IS NOT NULL          THEN 'place'
      WHEN c.core_name_norm  IS NOT NULL          THEN 'category'
      ELSE 'unclassified'
    END AS status
  FROM streets_dedup s
  LEFT JOIN persons         p  ON p.core_name_norm  = s.core_name_norm
  LEFT JOIN nature_terms    n  ON n.core_name_norm  = s.core_name_norm
  LEFT JOIN place_refs      pl ON pl.core_name_norm = s.core_name_norm
  LEFT JOIN name_categories c  ON c.core_name_norm  = s.core_name_norm
)
SELECT status,
       COUNT(*) AS streets,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM streets_dedup), 1) AS pct
FROM classified
GROUP BY status ORDER BY streets DESC;

-- Distinct-name coverage (what fraction of unique core_name_norm keys are curated)
-- :name coverage_names
WITH all_keys AS (
  SELECT DISTINCT core_name_norm FROM streets_dedup
  WHERE core_name_norm IS NOT NULL AND is_numeric=0 AND is_date=0 AND is_saint=0
),
curated_keys AS (
  SELECT core_name_norm FROM persons      UNION
  SELECT core_name_norm FROM nature_terms UNION
  SELECT core_name_norm FROM name_categories UNION
  SELECT core_name_norm FROM place_refs
)
SELECT
  COUNT(*)                                                  AS total_keys,
  SUM(CASE WHEN c.core_name_norm IS NOT NULL THEN 1 ELSE 0 END)
                                                            AS curated_keys,
  ROUND(100.0 * SUM(CASE WHEN c.core_name_norm IS NOT NULL THEN 1 ELSE 0 END)
        / COUNT(*), 1)                                      AS pct_keys_curated
FROM all_keys a LEFT JOIN curated_keys c USING (core_name_norm);


-- ============= VIEW 1: OVERVIEW =============

-- KPI tiles
-- :name overview_kpis
SELECT
  (SELECT COUNT(*) FROM streets_dedup)                      AS total_streets,
  (SELECT COUNT(DISTINCT uat) FROM streets_dedup)           AS total_uats,
  (SELECT COUNT(DISTINCT judet) FROM streets_dedup)         AS total_judete,
  (SELECT COUNT(DISTINCT name_normalized)
     FROM streets_dedup)                                    AS distinct_names,
  (SELECT COUNT(*) FROM streets_dedup WHERE is_numeric=1)   AS anonymous_streets,
  (SELECT COUNT(*) FROM streets_dedup WHERE is_date=1)      AS date_streets,
  (SELECT COUNT(*) FROM streets_dedup WHERE is_saint=1)     AS saint_streets,
  (SELECT COUNT(*) FROM street_aliases)                     AS aliases;

-- Street type breakdown (donut)
-- :name overview_street_types
SELECT COALESCE(street_type,'(altele)') AS type, COUNT(*) AS n
FROM streets_dedup GROUP BY type ORDER BY n DESC;


-- ============= VIEW 2: NATIONAL TOP-N =============

-- Most common street names nationwide (deduped by UAT)
-- :name top_names_national
SELECT name AS display, name_normalized AS key, COUNT(*) AS occurrences,
       COUNT(DISTINCT judet) AS judete_present,
       COUNT(DISTINCT uat) AS uats_present
FROM streets_dedup
WHERE name_normalized != ''
GROUP BY name_normalized
ORDER BY occurrences DESC
LIMIT 100;

-- Names that appear in EVERY judet (universal canon)
-- (At full scale will be the small set of Eminescu/Eroilor/Unirii etc.)
-- :name universal_names
WITH total_judete AS (SELECT COUNT(DISTINCT judet) AS k FROM streets_dedup)
SELECT name, name_normalized, COUNT(DISTINCT judet) AS in_judete, COUNT(*) AS total
FROM streets_dedup
GROUP BY name_normalized
HAVING COUNT(DISTINCT judet) = (SELECT k FROM total_judete)
ORDER BY total DESC;

-- Hapaxes — names that exist in only one UAT (long tail / curiosities)
-- :name unique_names
SELECT judet, uat, name
FROM streets_dedup
WHERE is_numeric = 0 AND is_date = 0 AND name NOT REGEXP '^\d'
GROUP BY name_normalized
HAVING COUNT(*) = 1
LIMIT 50;


-- ============= VIEW 3: PEOPLE — GENDER, ERA, PROFESSION =============

-- Gender breakdown of person-named streets
-- :name people_gender
SELECT p.gender, COUNT(*) AS streets, COUNT(DISTINCT p.core_name_norm) AS distinct_persons
FROM streets_dedup s JOIN persons p ON p.core_name_norm = s.core_name_norm
GROUP BY p.gender;

-- Most-honored person (top N)
-- :name top_persons
SELECT p.full_name, p.gender, p.era, p.profession,
       COUNT(*) AS streets, COUNT(DISTINCT s.judet) AS judete
FROM streets_dedup s JOIN persons p ON p.core_name_norm = s.core_name_norm
GROUP BY p.core_name_norm
ORDER BY streets DESC LIMIT 30;

-- Most-honored woman (so we can headline the gap)
-- :name top_women
SELECT p.full_name, COUNT(*) AS streets
FROM streets_dedup s JOIN persons p ON p.core_name_norm = s.core_name_norm
WHERE p.gender = 'F'
GROUP BY p.core_name_norm
ORDER BY streets DESC LIMIT 20;

-- Profession distribution among honorees
-- :name people_profession
SELECT p.profession, COUNT(*) AS streets
FROM streets_dedup s JOIN persons p ON p.core_name_norm = s.core_name_norm
GROUP BY p.profession ORDER BY streets DESC;

-- Era distribution
-- :name people_era
SELECT p.era, COUNT(*) AS streets
FROM streets_dedup s JOIN persons p ON p.core_name_norm = s.core_name_norm
GROUP BY p.era ORDER BY streets DESC;

-- Foreign-named streets (where the honoree isn't Romanian)
-- :name foreign_honorees
SELECT p.full_name, p.nationality, COUNT(*) AS streets,
       GROUP_CONCAT(DISTINCT s.judet) AS judete
FROM streets_dedup s JOIN persons p ON p.core_name_norm = s.core_name_norm
WHERE p.nationality != 'RO'
GROUP BY p.core_name_norm ORDER BY streets DESC;


-- ============= VIEW 4: THEME COMPOSITION =============

-- Macro-theme split: person / nature / place / religious / etc.
-- :name theme_composition
WITH classified AS (
  SELECT s.id, s.judet,
    CASE
      WHEN s.is_numeric=1                        THEN 'numeric'
      WHEN s.is_date=1                           THEN 'date'
      WHEN s.is_saint=1                          THEN 'religious'
      WHEN p.core_name_norm IS NOT NULL          THEN 'person'
      WHEN n.core_name_norm IS NOT NULL          THEN 'nature_' || n.nature_type
      WHEN pl.core_name_norm IS NOT NULL         THEN 'place_' || pl.place_type
      WHEN c.core_name_norm IS NOT NULL          THEN c.category
      ELSE 'unclassified'
    END AS theme
  FROM streets_dedup s
  LEFT JOIN persons         p  ON p.core_name_norm  = s.core_name_norm
  LEFT JOIN nature_terms    n  ON n.core_name_norm  = s.core_name_norm
  LEFT JOIN place_refs      pl ON pl.core_name_norm = s.core_name_norm
  LEFT JOIN name_categories c  ON c.core_name_norm  = s.core_name_norm
)
SELECT theme, COUNT(*) AS n FROM classified GROUP BY theme ORDER BY n DESC;

-- Nature subtype breakdown (which flora/fauna dominates?)
-- :name nature_subtypes
SELECT n.nature_type, COUNT(*) AS streets,
       GROUP_CONCAT(DISTINCT n.term) AS terms
FROM streets_dedup s JOIN nature_terms n ON n.core_name_norm = s.core_name_norm
GROUP BY n.nature_type ORDER BY streets DESC;


-- ============= VIEW 5: REGIONAL MAP =============

-- Per-judet aggregates for choropleth coloring
-- :name judet_aggregates
SELECT
  s.judet,
  COUNT(*)                                                       AS total_streets,
  COUNT(DISTINCT s.uat)                                          AS uats,
  ROUND(100.0 * SUM(CASE WHEN p.gender='F' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN p.gender IS NOT NULL THEN 1 ELSE 0 END),0), 1)
                                                                 AS pct_female_among_persons,
  ROUND(100.0 * SUM(CASE WHEN s.is_saint=1 THEN 1 ELSE 0 END)
              / COUNT(*), 1)                                     AS pct_saint,
  ROUND(100.0 * SUM(CASE WHEN s.is_numeric=1 THEN 1 ELSE 0 END)
              / COUNT(*), 1)                                     AS pct_anonymous
FROM streets_dedup s
LEFT JOIN persons p ON p.core_name_norm = s.core_name_norm
GROUP BY s.judet;

-- Modal street name per judet (most common name in each judet)
-- :name modal_per_judet
WITH ranked AS (
  SELECT judet, name, COUNT(*) AS n,
         ROW_NUMBER() OVER (PARTITION BY judet ORDER BY COUNT(*) DESC) AS rn
  FROM streets_dedup GROUP BY judet, name_normalized
)
SELECT judet, name, n FROM ranked WHERE rn=1;

-- Per-UAT diversity score (entropy of names) — find monocultural villages
-- :name uat_diversity
WITH name_counts AS (
  SELECT uat, judet, name_normalized, COUNT(*)*1.0 AS c,
         SUM(COUNT(*)) OVER (PARTITION BY uat) AS total
  FROM streets_dedup GROUP BY uat, judet, name_normalized
)
SELECT uat, judet,
       MAX(total) AS streets,
       -SUM((c/total) * log(c/total)) AS entropy
FROM name_counts
GROUP BY uat, judet
HAVING streets >= 10
ORDER BY entropy ASC LIMIT 20;


-- ============= VIEW 6: RENAMING HISTORY =============

-- Real renamings (where current name and historical alias are semantically different)
-- :name real_renamings
SELECT DISTINCT s.judet, s.uat, s.core_name AS current_name, a.alias AS historical_name
FROM streets s
JOIN street_aliases a ON a.street_id = s.id
WHERE s.core_name_norm IS NOT NULL
  AND s.core_name_norm != a.alias_normalized
  AND a.alias_normalized NOT LIKE '%' || s.core_name_norm || '%'
  AND s.core_name_norm NOT LIKE '%' || a.alias_normalized || '%'
ORDER BY s.uat, s.core_name;

-- "Communist-era" historical aliases (heuristic: contains ideological tokens)
-- :name communist_aliases
SELECT DISTINCT s.core_name AS current_name, a.alias AS communist_alias, s.uat
FROM streets s JOIN street_aliases a ON a.street_id = s.id
WHERE a.alias_normalized REGEXP '(colectivist|uzin|lenin|stalin|partidul|tovaras|mai 1|7 noiembrie|23 august|cap-?ului|ceapeu)'
ORDER BY s.uat;


-- ============= VIEW 7: CURIOSITIES =============

-- Numeric/anonymous streets by UAT (the CIORANI phenomenon)
-- :name anonymous_uats
SELECT uat, judet, COUNT(*) AS anonymous_streets,
       MIN(name) AS lowest, MAX(CAST(name AS INTEGER)) AS highest
FROM streets_dedup
WHERE is_numeric=1
GROUP BY uat ORDER BY anonymous_streets DESC;

-- Longest street names (poetic outliers)
-- :name longest_names
SELECT judet, uat, name, LENGTH(name) AS chars
FROM streets_dedup
ORDER BY LENGTH(name) DESC LIMIT 20;

-- Locally-honored (street name appears in only 1 UAT and it's a person/title)
-- :name locally_honored
SELECT s.judet, s.uat, s.name
FROM streets_dedup s
WHERE s.title IS NOT NULL OR s.rank IS NOT NULL
GROUP BY s.core_name_norm
HAVING COUNT(*) = 1
LIMIT 30;


-- ============= VIEW 8: OSM ↔ REGISTRY COVERAGE =============
-- Requires osm_ingest + osm_match + osm_score to have run first.

-- Per-județ: what % of registry streets have an OSM match?
-- Low pct = poor OSM mapping or systematic name-format mismatch.
-- :name osm_judet_coverage
SELECT sd.judet,
       COUNT(*)                                                          AS registry_streets,
       SUM(CASE WHEN m.street_id IS NOT NULL THEN 1 ELSE 0 END)         AS osm_matched,
       ROUND(100.0 * SUM(CASE WHEN m.street_id IS NOT NULL THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                             AS pct_osm
FROM streets_dedup sd
LEFT JOIN street_osm_matches m ON m.street_id = sd.id
GROUP BY sd.judet
ORDER BY pct_osm DESC;

-- Registry street names that are frequent (≥10 UATs) but have zero OSM matches
-- in any UAT. Systematic gaps: likely naming convention differences or
-- streets that exist only in the electoral database (e.g. unnumbered rural paths).
-- :name registry_osm_gap
SELECT sd.name,
       COUNT(DISTINCT sd.uat)                                            AS uats_in_registry,
       SUM(CASE WHEN m.street_id IS NOT NULL THEN 1 ELSE 0 END)         AS uats_with_osm_match
FROM streets_dedup sd
LEFT JOIN street_osm_matches m ON m.street_id = sd.id
GROUP BY sd.name_normalized
HAVING COUNT(DISTINCT sd.uat) >= 10
   AND SUM(CASE WHEN m.street_id IS NOT NULL THEN 1 ELSE 0 END) = 0
ORDER BY uats_in_registry DESC
LIMIT 30;

-- OSM streets not in the registry, ranked by importance score.
-- These are real streets that have no registered voters: scenic/transit roads,
-- new developments, industrial access roads, private roads.
-- :name osm_only_prominent
SELECT o.uat_siruta, o.name, o.highway_class,
       ROUND(o.length_m)          AS length_m,
       ROUND(o.importance_v1, 1)  AS importance
FROM osm_streets o
WHERE NOT EXISTS (
    SELECT 1 FROM street_osm_matches m WHERE m.osm_street_id = o.id
)
ORDER BY o.importance_v1 DESC
LIMIT 50;

-- Self-honor index per județ: of person-streets in județ X whose honoree's
-- birth_judet is known, what % were also born in județ X? "Knowing your own".
-- Foreign-born or unknown-birth honorees fall out of the denominator so the
-- numbers aren't deflated by Wikidata sparsity.
-- :name self_honor_per_judet
SELECT s.judet,
       SUM(CASE WHEN p.birth_judet = s.judet THEN 1 ELSE 0 END) AS self_honor_streets,
       SUM(CASE WHEN p.birth_judet IS NOT NULL THEN 1 ELSE 0 END) AS known_birth_streets,
       COUNT(*) AS total_person_streets,
       ROUND(100.0 * SUM(CASE WHEN p.birth_judet = s.judet THEN 1 ELSE 0 END)
                   / NULLIF(SUM(CASE WHEN p.birth_judet IS NOT NULL THEN 1 ELSE 0 END), 0), 1)
                                                                AS pct_self_honor_known
FROM streets_dedup s
JOIN persons p ON p.core_name_norm = s.core_name_norm
GROUP BY s.judet
ORDER BY pct_self_honor_known DESC;

-- Most parochial honorees: persons whose streets cluster heavily in one județ.
-- Useful for picking out local heroes.
-- :name most_parochial_honorees
WITH streets_per_person_judet AS (
  SELECT p.core_name_norm, p.full_name, p.birth_judet, s.judet,
         COUNT(*) AS streets_in_judet
  FROM streets_dedup s JOIN persons p ON p.core_name_norm = s.core_name_norm
  GROUP BY p.core_name_norm, s.judet
),
totals AS (
  SELECT core_name_norm, SUM(streets_in_judet) AS total_streets
  FROM streets_per_person_judet
  GROUP BY core_name_norm
)
SELECT spj.full_name, spj.birth_judet, spj.judet AS dominant_judet,
       spj.streets_in_judet, t.total_streets,
       ROUND(100.0 * spj.streets_in_judet / t.total_streets, 1) AS pct_in_dominant
FROM streets_per_person_judet spj
JOIN totals t ON t.core_name_norm = spj.core_name_norm
WHERE t.total_streets >= 5
  AND 100.0 * spj.streets_in_judet / t.total_streets >= 50
ORDER BY t.total_streets DESC, pct_in_dominant DESC
LIMIT 40;


-- Kilometers of OSM-mapped road per honored person, ranked.
-- Reframes the "who has the most streets" question as "who owns the most asphalt".
-- Coverage caveat: street_osm_matches covers ~52% of the registry, so absolute
-- totals under-count, but the ranking is stable across the matched subset.
-- :name total_km_per_honoree
SELECT
    p.full_name,
    p.gender,
    p.era,
    p.profession,
    p.nationality,
    COUNT(DISTINCT sd.id)              AS matched_streets,
    ROUND(SUM(o.length_m) / 1000.0, 2) AS total_km
FROM streets_dedup        sd
JOIN persons              p  ON p.core_name_norm = sd.core_name_norm
JOIN street_osm_matches   m  ON m.street_id      = sd.id
JOIN osm_streets          o  ON o.id             = m.osm_street_id
GROUP BY p.core_name_norm
ORDER BY total_km DESC
LIMIT 50;

-- Highway-class composition by macro-classification.
-- Tests the prestige-hierarchy hypothesis: do person/military streets skew toward
-- primary/secondary while nature/saint streets concentrate in residential/tertiary?
-- :name highway_class_by_category
WITH classified AS (
  SELECT sd.id,
    CASE
      WHEN sd.is_numeric=1                       THEN 'numeric'
      WHEN sd.is_date=1                          THEN 'date'
      WHEN sd.is_saint=1                         THEN 'religious'
      WHEN p.core_name_norm  IS NOT NULL         THEN 'person'
      WHEN n.core_name_norm  IS NOT NULL         THEN 'nature'
      WHEN pl.core_name_norm IS NOT NULL         THEN 'place'
      WHEN c.core_name_norm  IS NOT NULL         THEN 'category'
      ELSE 'unclassified'
    END AS category
  FROM streets_dedup sd
  LEFT JOIN persons         p  ON p.core_name_norm  = sd.core_name_norm
  LEFT JOIN nature_terms    n  ON n.core_name_norm  = sd.core_name_norm
  LEFT JOIN place_refs      pl ON pl.core_name_norm = sd.core_name_norm
  LEFT JOIN name_categories c  ON c.core_name_norm  = sd.core_name_norm
)
SELECT
    cl.category,
    o.highway_class,
    COUNT(*)                            AS streets,
    ROUND(SUM(o.length_m) / 1000.0, 1)  AS total_km
FROM classified cl
JOIN street_osm_matches m ON m.street_id    = cl.id
JOIN osm_streets        o ON o.id           = m.osm_street_id
GROUP BY cl.category, o.highway_class
ORDER BY cl.category, total_km DESC;


-- Curation coverage: how many distinct core_name_norm keys are classified,
-- and what percentage of streets (weighted by frequency) they represent.
-- :name classification_coverage
SELECT
  COALESCE(classification, 'unclassified')      AS category,
  COUNT(*)                                       AS key_count,
  SUM(street_count)                              AS street_count,
  ROUND(100.0 * SUM(street_count) /
    SUM(SUM(street_count)) OVER (), 1)           AS pct_of_streets
FROM streets_classified_pct
GROUP BY classification
ORDER BY street_count DESC;

-- Single-row summary: classified keys and street-weighted coverage %.
-- :name classification_coverage_summary
SELECT
  COUNT(*)                                                               AS total_keys,
  SUM(CASE WHEN classification IS NOT NULL THEN 1 ELSE 0 END)           AS classified_keys,
  ROUND(100.0 * SUM(CASE WHEN classification IS NOT NULL THEN 1 ELSE 0 END)
    / COUNT(*), 1)                                                       AS pct_keys_classified,
  SUM(street_count)                                                      AS total_streets,
  SUM(CASE WHEN classification IS NOT NULL THEN street_count ELSE 0 END) AS classified_streets,
  ROUND(100.0 * SUM(CASE WHEN classification IS NOT NULL THEN street_count ELSE 0 END)
    / SUM(street_count), 1)                                              AS pct_streets_classified
FROM streets_classified_pct;
