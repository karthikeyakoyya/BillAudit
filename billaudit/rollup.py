"""Turn line-level findings into claims and apply each vendor's dispute window."""
from __future__ import annotations

from datetime import date

import pandas as pd

from .config import Config


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def window_start(as_of: date, months: int) -> pd.Timestamp:
    """First invoice period a dispute can still reach. Periods before it are time-barred."""
    return pd.Timestamp(add_months(date(as_of.year, as_of.month, 1), -months))


def build_claims(findings: pd.DataFrame, vendors: pd.DataFrame, cfg: Config):
    """One claim per vendor, circuit and rule. A vendor error that repeats for
    eight months is one claim with a lookback, not eight rows.

    Returns (claims, claim_lines).
    """
    if findings.empty:
        return pd.DataFrame(), findings.assign(claim_id=[], claimable=[])
    win = dict(zip(vendors.vendor_id, vendors.dispute_window_months))
    names = dict(zip(vendors.vendor_id, vendors.vendor_name))
    lines = findings.copy()
    lines["window_months"] = lines["vendor_id"].map(win)
    lines["cutoff"] = [window_start(cfg.as_of, int(w)) for w in lines["window_months"]]
    lines["claimable"] = lines["period"] >= lines["cutoff"]

    keys = ["vendor_id", "circuit_id", "rule"]
    order = lines[keys].drop_duplicates().sort_values(keys).reset_index(drop=True)
    order["claim_id"] = [f"C-{i + 1:04d}" for i in range(len(order))]
    lines = lines.merge(order, on=keys, how="left")

    g = lines.groupby("claim_id")
    claims = g.agg(
        vendor_id=("vendor_id", "first"), circuit_id=("circuit_id", "first"), rule=("rule", "first"),
        service=("service", "first"), n_lines=("line_id", "count"),
        first_period=("period", "min"), last_period=("period", "max"),
        total_overcharge=("est_overcharge", "sum"), window_months=("window_months", "first"),
        cutoff=("cutoff", "first"),
    ).reset_index()
    claimable = lines[lines.claimable].groupby("claim_id")["est_overcharge"].sum()
    n_claimable = lines[lines.claimable].groupby("claim_id")["line_id"].count()
    claims["claimable_amount"] = claims["claim_id"].map(claimable).fillna(0.0).round(2)
    claims["claimable_lines"] = claims["claim_id"].map(n_claimable).fillna(0).astype(int)
    claims["total_overcharge"] = claims["total_overcharge"].round(2)
    claims["barred_amount"] = (claims["total_overcharge"] - claims["claimable_amount"]).round(2)
    claims["vendor_name"] = claims["vendor_id"].map(names)
    return claims, lines
