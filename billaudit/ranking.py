"""Rank claims by expected recovery, not by size alone."""
from __future__ import annotations

import duckdb
import pandas as pd

from .config import Config

RATE_SQL = """
SELECT rule,
       count(*) AS n_past_claims,
       sum(recovered_pct) AS credit_units,
       (sum(recovered_pct) + 2 * 0.5) / (count(*) + 2) AS recovery_rate
FROM dispute_history
GROUP BY rule
ORDER BY rule
"""


def recovery_rates(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Share of a claim's value recovered in past disputes, by rule.

    Smoothed toward 50 percent with the weight of two past claims so that a rule
    with very little history is not ranked on noise.
    """
    return con.execute(RATE_SQL).df()


def rank_claims(claims: pd.DataFrame, rates: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    out = claims.merge(rates[["rule", "n_past_claims", "recovery_rate"]], on="rule", how="left")
    out["recovery_rate"] = out["recovery_rate"].fillna(0.5)
    out["expected_value"] = (out["claimable_amount"] * out["recovery_rate"]).round(2)

    worth = (out["claimable_amount"] >= cfg.min_claim_value) & (out["claimable_lines"] > 0)
    out["decision"] = "below_threshold"
    out.loc[out["claimable_lines"] == 0, "decision"] = "time_barred"
    eligible = out[worth].sort_values(["expected_value", "claim_id"], ascending=[False, True])
    out.loc[eligible.index, "decision"] = "defer_capacity"
    out.loc[eligible.index[: cfg.capacity], "decision"] = "file"
    out["rank"] = out["expected_value"].rank(ascending=False, method="first").astype(int)
    return out.sort_values("rank").reset_index(drop=True)
