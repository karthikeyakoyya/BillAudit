"""Run the audit rules (SQL files) and reduce overlaps to one finding per line."""
from __future__ import annotations

from pathlib import Path
from string import Template

import duckdb
import pandas as pd

from .config import RULE_PRIORITY, Config

FINDING_COLS = ["line_id", "rule", "est_overcharge", "detail"]


def run_rules(con: duckdb.DuckDBPyConnection, cfg: Config, rules_dir: Path | None = None):
    """Return (findings, raw_hits). findings has one row per flagged line."""
    rules_dir = Path(rules_dir or cfg.rules_dir)
    frames = []
    for f in sorted(rules_dir.glob("*.sql")):
        sql = Template(f.read_text()).safe_substitute(cfg.rule_params())
        frames.append(con.execute(sql).df()[FINDING_COLS])
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FINDING_COLS)

    rank = {r: i for i, r in enumerate(RULE_PRIORITY)}
    raw["_prio"] = raw["rule"].map(rank).fillna(len(rank)).astype(int)
    final = raw.sort_values(["line_id", "_prio"]).drop_duplicates("line_id").drop(columns="_prio")
    raw = raw.drop(columns="_prio")

    ctx = con.execute(
        "SELECT line_id, vendor_id, circuit_id, period, charge_type, rate_billed, amount, "
        "contract_rate, service, true_jurisdiction, billed_jurisdiction, a_state, neca_pct FROM line_ref"
    ).df()
    findings = final.merge(ctx, on="line_id", how="left")
    findings["est_overcharge"] = findings["est_overcharge"].astype(float).round(2)
    return findings.sort_values(["vendor_id", "circuit_id", "period"]).reset_index(drop=True), raw
