import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import json
import threading
import urllib.error
import urllib.request
import pytest
from http.server import HTTPServer

import filter_server


class TestBuildFilterQuery:
    def test_empty_params_returns_empty_where(self):
        where, vals = filter_server.build_filter_query({})
        assert where == ""
        assert vals == []

    def test_single_judet(self):
        where, vals = filter_server.build_filter_query({'judet': ['HR']})
        assert "sd.judet IN (?)" in where
        assert vals == ['HR']

    def test_multiple_judete_joined_as_or(self):
        where, vals = filter_server.build_filter_query({'judet': ['HR', 'CV']})
        assert "sd.judet IN (?, ?)" in where
        assert vals == ['HR', 'CV']

    def test_uat_uppercased_partial_match(self):
        where, vals = filter_server.build_filter_query({'uat': ['ciuc']})
        assert "sd.uat LIKE ?" in where
        assert "%CIUC%" in vals

    def test_street_type(self):
        where, vals = filter_server.build_filter_query({'street_type': ['Strada']})
        assert "sd.street_type IN (?)" in where
        assert vals == ['Strada']

    def test_classification_person(self):
        where, vals = filter_server.build_filter_query({'classification': ['person']})
        assert "p.core_name_norm IS NOT NULL" in where

    def test_classification_saint(self):
        where, vals = filter_server.build_filter_query({'classification': ['saint']})
        assert "sd.is_saint = 1" in where

    def test_classification_multi_or(self):
        where, vals = filter_server.build_filter_query(
            {'classification': ['saint', 'date']}
        )
        assert "sd.is_saint = 1" in where
        assert "sd.is_date = 1" in where

    def test_profession_implies_person_join(self):
        where, vals = filter_server.build_filter_query({'profession': ['poet']})
        assert "p.core_name_norm IS NOT NULL" in where
        assert "p.profession IN (?)" in where
        assert vals == ['poet']

    def test_multi_person_subfilters(self):
        where, vals = filter_server.build_filter_query({
            'profession': ['poet'],
            'nationality': ['RO'],
            'gender': ['F'],
        })
        assert "p.profession IN (?)" in where
        assert "p.nationality IN (?)" in where
        assert "p.gender IN (?)" in where
        assert set(vals) == {'poet', 'RO', 'F'}

    def test_nature_type(self):
        where, vals = filter_server.build_filter_query({'nature_type': ['flower']})
        assert "n.core_name_norm IS NOT NULL" in where
        assert "n.nature_type IN (?)" in where
        assert vals == ['flower']

    def test_place_country(self):
        where, vals = filter_server.build_filter_query({'place_country': ['FR']})
        assert "pr.core_name_norm IS NOT NULL" in where
        assert "pr.country IN (?)" in where
        assert vals == ['FR']

    def test_category_subfilter(self):
        where, vals = filter_server.build_filter_query({'category': ['religious']})
        assert "c.core_name_norm IS NOT NULL" in where
        assert "c.category IN (?)" in where

    def test_combined_geo_and_person(self):
        where, vals = filter_server.build_filter_query({
            'judet': ['HR'],
            'profession': ['writer'],
            'nationality': ['RO'],
        })
        assert "sd.judet IN (?)" in where
        assert "p.profession IN (?)" in where
        assert "p.nationality IN (?)" in where
        assert 'HR' in vals and 'writer' in vals and 'RO' in vals

    def test_where_clause_starts_with_WHERE(self):
        where, _ = filter_server.build_filter_query({'judet': ['AB']})
        assert where.startswith("WHERE ")

    def test_all_conditions_joined_with_AND(self):
        where, _ = filter_server.build_filter_query({
            'judet': ['AB'],
            'street_type': ['Strada'],
        })
        assert " AND " in where


DB_PATH = "data/streets.db"
DB_EXISTS = os.path.exists(DB_PATH)


def _start_test_server(db_path: str) -> tuple:
    """Start server on a random port, return (base_url, server, conn)."""
    conn = filter_server.get_db(db_path)
    handler = filter_server.make_handler(conn)
    server = HTTPServer(('localhost', 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://localhost:{port}", server, conn


@pytest.mark.skipif(not DB_EXISTS, reason="streets.db not present")
class TestServerIntegration:
    @pytest.fixture(scope="class")
    def base_url(self):
        url, server, conn = _start_test_server(DB_PATH)
        yield url
        server.shutdown()
        conn.close()

    def test_meta_returns_200(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/meta") as r:
            assert r.status == 200

    def test_meta_has_required_keys(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/meta") as r:
            data = json.loads(r.read())
        required = {
            'judete', 'street_types', 'classifications',
            'professions', 'nationalities', 'genders', 'eras', 'wiki_scopes',
            'categories', 'subcategories', 'nature_types',
            'place_types', 'place_countries',
        }
        assert required <= set(data.keys())

    def test_meta_judete_non_empty(self, base_url):
        with urllib.request.urlopen(f"{base_url}/api/meta") as r:
            data = json.loads(r.read())
        assert len(data['judete']) > 0

    def test_unknown_path_returns_404(self, base_url):
        try:
            urllib.request.urlopen(f"{base_url}/nonexistent")
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 404
