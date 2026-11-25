"""Runs the jsdom behaviour checks when Node and jsdom are installed."""
import shutil
import subprocess
from pathlib import Path

import pytest

from billaudit.pipeline import run_audit

JS_DIR = Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(shutil.which("node") is None or not (JS_DIR / "node_modules" / "jsdom").exists(),
                    reason="needs Node and `npm install` in tests/js")
def test_dashboard_behaviour(cfg, data_dir, tmp_path):
    run_audit(cfg, data_dir, tmp_path, evidence_limit=2)
    out = subprocess.run(["node", "dashboard_behaviour.js", str(tmp_path / "dashboard.html")],
                         cwd=JS_DIR, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
