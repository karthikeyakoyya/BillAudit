"""Assemble the evidence pack for one claim."""
from __future__ import annotations

import duckdb
import pandas as pd

from .config import RULE_LABELS
from .research import clauses_for


def build_evidence(con: duckdb.DuckDBPyConnection, claim: pd.Series, claim_lines: pd.DataFrame,
                   clauses: pd.DataFrame) -> dict:
    cid, vendor, rule = claim["circuit_id"], claim["vendor_id"], claim["rule"]
    lines = claim_lines[claim_lines.claim_id == claim["claim_id"]].sort_values("period")
    lines = lines[["line_id", "period", "rate_billed", "contract_rate", "amount", "est_overcharge", "claimable", "neca_pct"]].copy()
    lines["period"] = pd.to_datetime(lines["period"]).dt.strftime("%Y-%m")
    lines["expected_amount"] = (lines["amount"] - lines["est_overcharge"]).round(2)
    if rule == "surcharge_misrate":
        lines["billed_pct"] = (100 * lines["amount"] / lines["contract_rate"]).round(2)
        lines["tariff_pct"] = lines["neca_pct"].fillna(0.0)
        lines = lines[["line_id", "period", "billed_pct", "tariff_pct", "amount", "expected_amount", "est_overcharge", "claimable"]]
    else:
        lines = lines[["line_id", "period", "rate_billed", "contract_rate", "amount", "expected_amount", "est_overcharge", "claimable"]]

    orders = con.execute(
        "SELECT order_id, order_type, order_date, effective_date FROM orders WHERE circuit_id = ? ORDER BY effective_date",
        [cid],
    ).df()
    ref = con.execute(
        "SELECT service, true_jurisdiction, a_state, z_state FROM circuit_ref WHERE circuit_id = ?", [cid]
    ).df()
    info = ref.iloc[0].to_dict() if len(ref) else {"service": None, "true_jurisdiction": None, "a_state": None, "z_state": None}
    contract = pd.DataFrame()
    if info["service"]:
        contract = con.execute(
            "SELECT jurisdiction, rate, effective_from, effective_to FROM contracts "
            "WHERE vendor_id = ? AND service = ? AND jurisdiction = ? ORDER BY effective_from",
            [vendor, info["service"], info["true_jurisdiction"]],
        ).df()
        for col in ("effective_from", "effective_to"):
            contract[col] = pd.to_datetime(contract[col]).dt.strftime("%Y-%m-%d")
    tariff = pd.DataFrame()
    if rule == "surcharge_misrate" and info["service"]:
        tariff = con.execute(
            "SELECT state, service, surcharge_pct, effective_from, effective_to FROM neca_sim "
            "WHERE state = ? AND service = ? ORDER BY effective_from",
            [info["a_state"], info["service"]],
        ).df()
        for col in ("effective_from", "effective_to"):
            tariff[col] = pd.to_datetime(tariff[col]).dt.strftime("%Y-%m-%d")
    for col in ("order_date", "effective_date"):
        if len(orders):
            orders[col] = pd.to_datetime(orders[col]).dt.strftime("%Y-%m-%d")

    return {
        "claim": claim.to_dict(),
        "rule_label": RULE_LABELS[rule],
        "circuit": info,
        "lines": lines,
        "orders": orders,
        "contract": contract,
        "tariff": tariff,
        "clauses": clauses_for(rule, vendor, clauses),
    }
