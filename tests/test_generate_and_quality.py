import pandas as pd

from billaudit.generate import generate
from billaudit.quality import check_file


def test_generation_is_deterministic(cfg, tmp_path):
    a = generate(cfg, tmp_path / "a")["invoices"]
    b = generate(cfg, tmp_path / "b")["invoices"]
    pd.testing.assert_frame_equal(a, b)


def test_answer_key_points_at_real_lines(data_dir):
    inv = pd.concat([pd.read_csv(p) for p in (data_dir / "invoices").glob("invoice_V0?_2025-??.csv")])
    truth = pd.read_csv(data_dir / "ground_truth.csv")
    assert truth.line_id.is_unique
    assert set(truth.line_id) <= set(inv.line_id)
    assert inv.line_id.is_unique


def test_gate_rejects_the_two_broken_files(scored):
    dq = scored["dq"].set_index("file")
    assert dq.loc["invoice_V03_2025-09_reissue.csv", "status"] == "rejected"
    assert "missing columns" in dq.loc["invoice_V03_2025-09_reissue.csv", "issues"]
    assert dq.loc["invoice_V01_2025-10_reissue.csv", "status"] == "rejected"
    assert (dq.status == "rejected").sum() == 2


def test_gate_accepts_clean_files_in_full(scored):
    ok = scored["dq"][scored["dq"].status == "accepted"]
    assert (ok.rows_in == ok.rows_loaded).all()


def test_few_bad_rows_are_quarantined_not_fatal(data_dir, tmp_path):
    src = next((data_dir / "invoices").glob("invoice_V02_2025-05.csv"))
    df = pd.read_csv(src)
    df = pd.concat([df] * 6, ignore_index=True)
    df["line_id"] = [f"X{i:05d}" for i in range(len(df))]
    df.loc[3, "amount"] = -10.0
    p = tmp_path / "invoice_V02_2025-05.csv"
    df.to_csv(p, index=False)
    res = check_file(p, {"V01", "V02", "V03", "V04"}, 2025)
    assert res.status == "accepted_with_quarantine"
    assert len(df) > 100
    assert len(res.clean) == len(df) - 1 and len(res.quarantined) == 1


def test_wrong_vendor_in_file_is_caught(data_dir, tmp_path):
    src = next((data_dir / "invoices").glob("invoice_V02_2025-05.csv"))
    df = pd.read_csv(src)
    p = tmp_path / "invoice_V03_2025-05.csv"
    df.to_csv(p, index=False)
    assert check_file(p, {"V01", "V02", "V03", "V04"}, 2025).status == "rejected"
