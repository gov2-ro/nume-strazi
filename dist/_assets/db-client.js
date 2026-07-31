/*  db-client.js — Client-side replacement for filter_server.py.
 *
 *  Same SQL, same row shapes. Loads streets.db via sql.js-httpvfs over HTTP
 *  range requests so only the touched pages are fetched.
 *
 *  Exposes window.DbClient = { meta, filter, getDb, normalize, slugify }.
 *
 *  Parameters accepted by filter():
 *    - URLSearchParams instance, or
 *    - plain object whose values may be string | string[] (multi-select).
 *
 *  Stay in lockstep with filter_server.py — it is the source of truth.
 */
(function () {
  'use strict';

  // Derive the site base from this script's own URL. Works at any mount point
  // (root, /strazi/, etc.) without rebuild. Falls back to "/" if currentScript
  // isn't available (older browsers loading via <script> in async contexts).
  const SCRIPT_URL = (document.currentScript && document.currentScript.src) || '';
  const SITE_BASE  = SCRIPT_URL
    ? SCRIPT_URL.replace(/_assets\/db-client\.js.*$/, '')
    : '/';
  const ASSET_BASE = SITE_BASE + '_assets/sqljs-httpvfs/';
  const DB_URL     = SITE_BASE + 'streets.db';

  // ── Init (lazy, one-shot) ────────────────────────────────────────────
  let _dbPromise = null;
  function getDb() {
    if (_dbPromise) return _dbPromise;
    _dbPromise = (async () => {
      await loadScript(ASSET_BASE + 'index.js');
      const worker = await window.createDbWorker(
        [{
          from: 'inline',
          config: {
            serverMode: 'full',
            url: DB_URL,
            requestChunkSize: 4096,
          },
        }],
        ASSET_BASE + 'sqlite.worker.js',
        ASSET_BASE + 'sql-wasm.wasm'
      );
      return worker.db;
    })();
    return _dbPromise;
  }

  function loadScript(src) {
    return new Promise((res, rej) => {
      const existing = document.querySelector(`script[data-src="${src}"]`);
      if (existing) { res(); return; }
      const s = document.createElement('script');
      s.src = src;
      s.dataset.src = src;
      s.onload = () => res();
      s.onerror = () => rej(new Error('failed to load ' + src));
      document.head.appendChild(s);
    });
  }

  // ── normalize_match() mirror (streets_lib.py) ────────────────────────
  function normalize(s) {
    if (!s) return '';
    return s
      .replace(/[îÎ]/g, 'a')           // î ≡ â, then NFD strips circumflex
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '') // strip combining diacritics
      .toLowerCase()
      .trim();
  }

  // ── slugify() mirror (streets_lib.py) ────────────────────────────────
  function slugify(s) {
    const base = normalize(s);
    if (!base) return '';
    return base.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  // ── Param access helpers ─────────────────────────────────────────────
  function getAll(params, key) {
    if (params instanceof URLSearchParams) return params.getAll(key);
    const v = params[key];
    if (v == null) return [];
    return Array.isArray(v) ? v.filter(x => x != null && x !== '')
                            : (v === '' ? [] : [v]);
  }
  function getOne(params, key, dflt) {
    if (params instanceof URLSearchParams) {
      const v = params.get(key);
      return v == null ? dflt : v;
    }
    const v = params[key];
    return v == null ? dflt : (Array.isArray(v) ? v[0] : v);
  }

  // ── SQL fragments — mirror of filter_server.py constants ─────────────
  const BASE_FROM = `
    FROM electoral_dedup sd
    LEFT JOIN persons         p  ON p.core_name_norm  = sd.core_name_norm
    LEFT JOIN name_categories c  ON c.core_name_norm  = sd.core_name_norm
    LEFT JOIN nature_terms    n  ON n.core_name_norm  = sd.core_name_norm
    LEFT JOIN place_refs      pr ON pr.core_name_norm = sd.core_name_norm
  `;

  const SELECT_COLS = `
    sd.name,
    sd.street_type,
    sd.uat,
    sd.judet,
    sd.siruta,
    sd.core_name,
    sd.name_normalized,
    (SELECT COUNT(*) FROM electoral_dedup x
     WHERE x.name_normalized = sd.name_normalized) AS name_count,
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
    p.wikidata_qid,
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
  `;

  const SELECT_AGG = `
    MAX(sd.name)            AS name,
    sd.name_normalized,
    MAX(sd.core_name)       AS core_name,
    COUNT(*)                AS name_count,
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
    MAX(p.wikidata_qid)     AS wikidata_qid,
    MAX(p.full_name)        AS person_full_name,
    MAX(p.profession)       AS profession,
    MAX(p.nationality)      AS nationality,
    MAX(p.gender)           AS gender,
    MAX(p.era)              AS era,
    MAX(p.wiki_scope)       AS wiki_scope,
    MAX(c.category)         AS category,
    MAX(c.subcategory)      AS subcategory,
    MAX(n.nature_type)      AS nature_type,
    MAX(pr.place_type)      AS place_type,
    MAX(pr.country)         AS place_country
  `;

  const CLS_MAP = {
    person:   'p.core_name_norm IS NOT NULL',
    nature:   'n.core_name_norm IS NOT NULL',
    place:    'pr.core_name_norm IS NOT NULL',
    category: 'c.core_name_norm IS NOT NULL',
    saint:    'sd.is_saint = 1',
    date:     'sd.is_date = 1',
    numeric:  'sd.is_numeric = 1',
  };

  const PERSON_COLS = ['profession', 'nationality', 'gender', 'era', 'wiki_scope'];

  // ── build_filter_query() mirror ──────────────────────────────────────
  function buildWhere(params) {
    const conditions = [];
    const values = [];

    const nameQ = getOne(params, 'name', '');
    if (nameQ && String(nameQ).trim()) {
      conditions.push("sd.name_normalized LIKE ?");
      values.push('%' + normalize(String(nameQ).trim()) + '%');
    }

    const judete = getAll(params, 'judet');
    if (judete.length) {
      conditions.push(`sd.judet IN (${judete.map(() => '?').join(', ')})`);
      values.push(...judete);
    }

    const uat = getOne(params, 'uat', '');
    if (uat && String(uat).trim()) {
      const raw = String(uat).toUpperCase()
        .replace(/\\/g, '\\\\').replace(/%/g, '\\%').replace(/_/g, '\\_');
      conditions.push("sd.uat LIKE ? ESCAPE '\\'");
      values.push('%' + raw + '%');
    }

    const stypes = getAll(params, 'street_type');
    if (stypes.length) {
      conditions.push(`sd.street_type IN (${stypes.map(() => '?').join(', ')})`);
      values.push(...stypes);
    }

    const cls = getAll(params, 'classification');
    if (cls.length) {
      const parts = cls.filter(c => CLS_MAP[c]).map(c => CLS_MAP[c]);
      if (parts.length) conditions.push(`(${parts.join(' OR ')})`);
    }

    const personActive = PERSON_COLS.some(c => getAll(params, c).length);
    if (personActive) {
      conditions.push('p.core_name_norm IS NOT NULL');
      for (const col of PERSON_COLS) {
        const vals = getAll(params, col);
        if (vals.length) {
          conditions.push(`p.${col} IN (${vals.map(() => '?').join(', ')})`);
          values.push(...vals);
        }
      }
    }

    const cats = getAll(params, 'category');
    if (cats.length) {
      conditions.push('c.core_name_norm IS NOT NULL');
      conditions.push(`c.category IN (${cats.map(() => '?').join(', ')})`);
      values.push(...cats);
    }
    const subcats = getAll(params, 'subcategory');
    if (subcats.length) {
      conditions.push('c.core_name_norm IS NOT NULL');
      conditions.push(`c.subcategory IN (${subcats.map(() => '?').join(', ')})`);
      values.push(...subcats);
    }
    const ntypes = getAll(params, 'nature_type');
    if (ntypes.length) {
      conditions.push('n.core_name_norm IS NOT NULL');
      conditions.push(`n.nature_type IN (${ntypes.map(() => '?').join(', ')})`);
      values.push(...ntypes);
    }
    const ptypes = getAll(params, 'place_type');
    if (ptypes.length) {
      conditions.push('pr.core_name_norm IS NOT NULL');
      conditions.push(`pr.place_type IN (${ptypes.map(() => '?').join(', ')})`);
      values.push(...ptypes);
    }
    const pcountries = getAll(params, 'place_country');
    if (pcountries.length) {
      conditions.push('pr.core_name_norm IS NOT NULL');
      conditions.push(`pr.country IN (${pcountries.map(() => '?').join(', ')})`);
      values.push(...pcountries);
    }

    const where = conditions.length ? 'WHERE ' + conditions.join(' AND ') : '';
    return { where, values };
  }

  function orderClause(sort, aggregate) {
    if (sort === 'name')                       return 'ORDER BY name ASC';
    if (sort === 'location' && !aggregate)     return 'ORDER BY sd.judet, sd.uat, sd.name';
    return 'ORDER BY name_count DESC, name ASC';
  }

  // ── meta() mirror ────────────────────────────────────────────────────
  async function meta() {
    const db = await getDb();
    const col = async (sql) => {
      const rows = await db.query(sql);
      return rows.map(r => Object.values(r)[0]);
    };

    return {
      judete:          await col("SELECT DISTINCT judet FROM electoral_dedup WHERE judet IS NOT NULL ORDER BY judet"),
      street_types:    await col("SELECT DISTINCT street_type FROM electoral_dedup WHERE street_type IS NOT NULL ORDER BY street_type"),
      classifications: ['person', 'nature', 'place', 'category', 'saint', 'date', 'numeric'],
      professions:     await col("SELECT DISTINCT profession FROM persons WHERE profession IS NOT NULL ORDER BY profession"),
      nationalities:   await col("SELECT DISTINCT nationality FROM persons WHERE nationality IS NOT NULL ORDER BY nationality"),
      genders:         await col("SELECT DISTINCT gender FROM persons WHERE gender IS NOT NULL ORDER BY gender"),
      eras:            await col("SELECT DISTINCT era FROM persons WHERE era IS NOT NULL ORDER BY era"),
      wiki_scopes:     await col("SELECT DISTINCT wiki_scope FROM persons WHERE wiki_scope IS NOT NULL ORDER BY wiki_scope"),
      categories:      await col("SELECT DISTINCT category FROM name_categories WHERE category IS NOT NULL ORDER BY category"),
      subcategories:   await col("SELECT DISTINCT subcategory FROM name_categories WHERE subcategory IS NOT NULL ORDER BY subcategory"),
      nature_types:    await col("SELECT DISTINCT nature_type FROM nature_terms WHERE nature_type IS NOT NULL ORDER BY nature_type"),
      place_types:     await col("SELECT DISTINCT place_type FROM place_refs WHERE place_type IS NOT NULL ORDER BY place_type"),
      place_countries: await col("SELECT DISTINCT country FROM place_refs WHERE country IS NOT NULL ORDER BY country"),
    };
  }

  // ── filter() mirror ──────────────────────────────────────────────────
  async function filter(params) {
    const db = await getDb();

    const limit     = Math.max(1, Math.min(parseInt(getOne(params, 'limit',  '200'), 10) || 200, 1000));
    const offset    = Math.max(0,         parseInt(getOne(params, 'offset', '0'),   10) || 0);
    const aggRaw    = getOne(params, 'aggregate', '0');
    const aggregate = aggRaw === '1' || aggRaw === 1 || aggRaw === true;
    const sort      = getOne(params, 'sort', 'count');

    const { where, values } = buildWhere(params);

    let countSql, selectSql;
    if (aggregate) {
      countSql  = `SELECT COUNT(*) AS c FROM (SELECT 1 ${BASE_FROM} ${where} GROUP BY sd.name_normalized)`;
      selectSql = `SELECT ${SELECT_AGG} ${BASE_FROM} ${where} GROUP BY sd.name_normalized ${orderClause(sort, true)} LIMIT ? OFFSET ?`;
    } else {
      countSql  = `SELECT COUNT(*) AS c ${BASE_FROM} ${where}`;
      selectSql = `SELECT ${SELECT_COLS} ${BASE_FROM} ${where} ${orderClause(sort, false)} LIMIT ? OFFSET ?`;
    }

    const countRows = await db.query(countSql, values);
    const total     = countRows[0] ? Number(Object.values(countRows[0])[0] || 0) : 0;
    const rawRows   = await db.query(selectSql, [...values, limit, offset]);

    const rows = rawRows.map(r => {
      const d  = { ...r };
      const core = d.core_name;
      const nn   = d.name_normalized || '';
      d.street_slug = slugify(core || nn);
      if (!aggregate) {
        d.uat_slug = slugify(d.uat || '');
        delete d.siruta;
      }
      delete d.core_name;
      delete d.name_normalized;
      return d;
    });

    return { total, limit, offset, aggregate, rows };
  }

  window.DbClient = { meta, filter, getDb, normalize, slugify };
})();
