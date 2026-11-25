"""Load a generated dataset and pass invoice files through the quality gate."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .quality import check_file

DATE_COLS = {
    "circuits": ["install_date", "disconnect_date"],
    "orders": ["order_date", "effective_date"],
    "contracts": ["effective_from", "effective_to"],
    "neca_sim": ["effective_from", "effective_to"],
    "dispute_history": ["filed_date"],
}
REFERENCE = ["vendors", "services", "circuits", "orders", "contracts", "contract_clauses", "lerg_sim", "neca_sim", "dispute_history"]


def load_reference(data_dir: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for name in REFERENCE:
        df = pd.read_csv(Path(data_dir) / f"{name}.csv")
        for col in DATE_COLS.get(name, []):
            df[col] = pd.to_datetime(df[col])
        out[name] = df
    return out


def ingest_invoices(data_dir: Path, vendors: pd.DataFrame, year: int):
    """Return (invoice_lines, dq_report, quarantined_rows)."""
    known = set(vendors["vendor_id"])
    results, frames, quarantined = [], [], []
    seen_ids: set[str] = set()
    for path in sorted((Path(data_dir) / "invoices").glob("invoice_*.csv")):
        res = check_file(path, known, year)
        if res.clean is not None:
            # A line id that already arrived in an earlier file is a conflict.
            dup = res.clean["line_id"].isin(seen_ids)
            if dup.any():
                extra = res.clean[dup].copy()
                extra["reason"] = "line_id already loaded from another file"
                extra["file"] = path.name
                quarantined.append(extra)
                res.clean = res.clean[~dup]
                res.rows_ok = len(res.clean)
                res.issues.append(f"{int(dup.sum())} rows repeat a line_id from another file")
            seen_ids.update(res.clean["line_id"])
            frames.append(res.clean)
        if res.quarantined is not None and len(res.quarantined):
            quarantined.append(res.quarantined)
        results.append({
            "file": res.file, "rows_in": res.rows_in, "rows_loaded": res.rows_ok,
            "status": res.status, "issues": " | ".join(res.issues),
        })
    lines = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    q = pd.concat(quarantined, ignore_index=True) if quarantined else pd.DataFrame()
    return lines, pd.DataFrame(results), q
