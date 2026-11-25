import duckdb
from openpyxl import load_workbook

from billaudit.pipeline import run_audit


def test_full_run_writes_every_output(cfg, data_dir, tmp_path):
    res = run_audit(cfg, data_dir, tmp_path, evidence_limit=4)
    for name in ("dispute_workbook.xlsx", "dashboard.html", "findings.csv", "claims.csv", "rule_totals.csv", "billaudit.duckdb"):
        assert (tmp_path / name).exists(), name
    assert len(list((tmp_path / "dispute_notes").glob("*.txt"))) == 4
    wb = load_workbook(tmp_path / "dispute_workbook.xlsx")
    assert wb.sheetnames[:2] == ["Summary", "Claims"]
    formulas = [c.value for row in wb["Summary"].iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
    assert len(formulas) > 20
    html = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
    assert "<svg" in html and "<script src" not in html and "http" not in html
    assert 'href="#main"' in html and 'id="claims"' in html and "<details" in html and "@media print" in html
    assert res["claims"].claim_id.is_unique


def test_results_are_queryable_with_sql(cfg, data_dir, tmp_path):
    run_audit(cfg, data_dir, tmp_path, evidence_limit=2)
    con = duckdb.connect(str(tmp_path / "billaudit.duckdb"), read_only=True)
    n = con.execute("SELECT count(*) FROM claims WHERE decision = 'file'").fetchone()[0]
    assert n == cfg.capacity or n > 0
    q = (cfg.sql_dir / "analyst_queries.sql").read_text().split(";")
    for stmt in [s for s in q if s.strip() and "SELECT" in s.upper()]:
        con.execute(stmt).df()
