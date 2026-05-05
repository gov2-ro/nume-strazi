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
