# tests/test_build.py
import subprocess
import sys
from pathlib import Path


def test_build_runs_and_produces_output():
    result = subprocess.run(
        [sys.executable, "build_site.py", "--db", "data/streets.db"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert Path("dist/index.html").exists()
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "adrese" in html
    assert Path("dist/ro-counties.geojson").exists()


def test_section2_top_list():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "cele-mai-intalnite" in html
    assert "s2-judet-select" in html  # județ filter present
    assert "Cele mai frecvente" in html


def test_section3_gender_grid():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "pe-cine-onoram" in html
    assert "s3-gap-grid" in html
    assert "Femeie" in html


def test_section4_tiers():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "recunoastere" in html
    assert "Universal" in html
    assert "Național" in html


def test_section5_theme_donut():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "tematica" in html
    assert "conic-gradient" in html


def test_section6_map():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "harta" in html
    assert "s6-map" in html
    assert "% sfinți" in html


def test_section7_renumiri():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "renumiri" in html
    assert "în construcție" in html


def test_footer_present():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "<footer" in html
    assert "Despre date" in html
    assert "Metodologie" in html
    assert "Cod sursă" in html


def test_methodology_page_builds():
    result = subprocess.run(
        [sys.executable, "build_site.py", "--variant", "methodology",
         "--db", "data/streets.db"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    out = Path("dist/metodologie.html")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    # Hero + structural anchors
    assert "Metodologie · cum funcționează" in html
    for anchor in ("de-ce", "sursa", "schema", "clasificare",
                   "recunoastere", "osm", "limite", "ce-urmeaza",
                   "cronologie", "cod"):
        assert f'id="{anchor}"' in html, f"missing anchor #{anchor}"
    # Editorial-review notice required by CLAUDE.md
    assert "Revizuire editorială RO" in html
    # Cross-link to dashboard nav present
    assert 'href="index.html' in html


def test_methodology_link_in_dashboard():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert 'href="metodologie.html"' in html


def test_default_is_cluster_cloud():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    # Both top panels present and ordered before #tematica
    assert 'id="cele-mai-intalnite"' in html
    assert 'id="top-persoane"' in html
    assert html.index('id="cele-mai-intalnite"') < html.index('id="tematica"')
    assert html.index('id="top-persoane"') < html.index('id="tematica"')
    # Flat-cloud markup present, old leaderboard markup gone
    assert "flat-tokens" in html
    assert 'rank-list rank-2col s2-list' not in html


def test_v2_dashboard_builds():
    result = subprocess.run(
        [sys.executable, "build_site.py", "--variant", "v2",
         "--db", "data/streets.db"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    out = Path("dist/index-v2.html")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    # v2 keeps the original dense leaderboards
    assert 'rank-list rank-2col s2-list' in html
    assert 'id="cele-mai-intalnite"' in html
