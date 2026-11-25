"""Data-quality gate for incoming invoice files.

A file is rejected outright when its structure is wrong (missing columns) or
when too many rows fail row-level checks. Otherwise the clean rows go on to
the audit and the bad rows are quarantined with a reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REQUIRED = [
    "line_id", "invoice_id", "vendor_id", "circuit_id", "period",
    "charge_type", "rate_billed", "amount", "billed_jurisdiction",
]
CHARGE_TYPES = {"MRC", "NRC", "SUR"}
JURISDICTIONS = {"intrastate", "interstate"}
MAX_BAD_ROW_SHARE = 0.02
_NAME = re.compile(r"invoice_(V\d+)_(\d{4})-(\d{2})(?:_\w+)?\.csv$")


@dataclass
class FileResult:
    file: str
    rows_in: int
    rows_ok: int
    status: str                      # accepted | accepted_with_quarantine | rejected
    issues: list[str] = field(default_factory=list)
    clean: pd.DataFrame | None = None
    quarantined: pd.DataFrame | None = None


def check_file(path: Path, known_vendors: set[str], year: int) -> FileResult:
    path = Path(path)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    n = len(df)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        return FileResult(path.name, n, 0, "rejected", [f"missing columns: {', '.join(missing)}"])

    m = _NAME.search(path.name)
    exp_vendor = m.group(1) if m else None
    exp_period = pd.Timestamp(int(m.group(2)), int(m.group(3)), 1) if m else None

    work = df.copy()
    work["period"] = pd.to_datetime(work["period"], errors="coerce")
    for col in ("rate_billed", "amount"):
        work[col] = pd.to_numeric(work[col], errors="coerce")

    reasons = pd.Series("", index=work.index)

    def flag(mask: pd.Series, text: str) -> None:
        nonlocal reasons
        mask = mask.fillna(True)
        reasons = reasons.where(~mask, reasons + (reasons.ne("").map({True: "; ", False: ""}) + text))

    flag(work[["line_id", "circuit_id", "vendor_id", "invoice_id"]].isna().any(axis=1), "null key field")
    flag(work["period"].isna() | (work["period"].dt.day != 1), "period is not a first-of-month date")
    flag(~work["period"].dt.year.between(year, year), f"period outside audit year {year}")
    flag(work["amount"].isna() | work["rate_billed"].isna(), "amount or rate not numeric")
    flag(work["amount"] <= 0, "amount is zero or negative")
    flag(work["line_id"].duplicated(keep="first") & work["line_id"].notna(), "duplicate line_id in file")
    flag(~work["vendor_id"].isin(known_vendors), "unknown vendor")
    flag(~work["charge_type"].isin(CHARGE_TYPES), "unexpected charge type")
    flag(~work["billed_jurisdiction"].isin(JURISDICTIONS), "unexpected jurisdiction label")
    if exp_vendor:
        flag(work["vendor_id"] != exp_vendor, "vendor does not match file name")
        flag(work["period"] != exp_period, "period does not match file name")

    bad = reasons.ne("")
    n_bad = int(bad.sum())
    issues: list[str] = []
    if n_bad:
        counts = pd.Series([r for rs in reasons[bad] for r in rs.split("; ")]).value_counts()
        issues = [f"{k}: {v} rows" for k, v in counts.items()]

    if n and n_bad / n > MAX_BAD_ROW_SHARE:
        return FileResult(path.name, n, 0, "rejected", [f"{n_bad} of {n} rows failed checks"] + issues)

    clean = work.loc[~bad].copy()
    quarantined = work.loc[bad].copy()
    quarantined["reason"] = reasons[bad]
    quarantined["file"] = path.name
    status = "accepted_with_quarantine" if n_bad else "accepted"
    return FileResult(path.name, n, len(clean), status, issues, clean, quarantined)
