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


def test_section2_search_box():
    html = Path("dist/index.html").read_text(encoding="utf-8")
    assert "cele-mai-intalnite" in html
    assert "Căutați un nume de stradă" in html


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
