"""End-to-end audit run: ingest, rules, claims, ranking, filing cycle, outputs."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Config
from .db import build_warehouse, load_tables
from .evidence import build_evidence
from .harness import score
from .ingest import ingest_invoices, load_reference
from .lifecycle import run_cycle
from .notes import draft_note
from .ranking import rank_claims, recovery_rates
from .report_html import build_dashboard
from .report_xlsx import build_workbook
from .rollup import build_claims
from .rules import run_rules


def _calibration(claims: pd.DataFrame) -> pd.DataFrame:
    done = claims[(claims.decision == "file") & claims.response_outcome.notna()]
    rows = []
    for rule, g in done.groupby("rule"):
        rows.append({"rule": rule, "resolved": len(g), "predicted_rate": round(float(g.recovery_rate.mean()), 4),
                     "actual_rate": round(float(g.credit_pct.fillna(0).mean()), 4)})
    return pd.DataFrame(rows, columns=["rule", "resolved", "predicted_rate", "actual_rate"])


def _dbsafe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == "object":
            df[c] = df[c].astype("string")
    return df


def run_audit(cfg: Config, data_dir: Path, out_dir: Path, rules_dir: Path | None = None,
              use_llm: bool = False, evidence_limit: int | None = None) -> dict:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    notes_dir = out_dir / "dispute_notes"
    notes_dir.mkdir(exist_ok=True)
    for old in notes_dir.glob("*.txt"):
        old.unlink()
    db_path = out_dir / "billaudit.duckdb"
    if db_path.exists():
        db_path.unlink()

    ref = load_reference(data_dir)
    lines, dq, quarantined = ingest_invoices(data_dir, ref["vendors"], cfg.year)
    con = build_warehouse(cfg, ref, lines, db_path)

    findings, raw = run_rules(con, cfg, rules_dir)
    claims, claim_lines = build_claims(findings, ref["vendors"], cfg)
    rates = recovery_rates(con)
    ranked = rank_claims(claims, rates, cfg)
    claims, events, report_date = run_cycle(ranked, cfg)
    events["event_date"] = pd.to_datetime(events["event_date"])

    # Evidence packs and draft notes for every filed claim.
    filed = claims[claims.decision == "file"].sort_values("rank")
    if evidence_limit:
        filed = filed.head(evidence_limit)
    evidence, note_sources = {}, {}
    for _, row in filed.iterrows():
        ev = build_evidence(con, row, claim_lines, ref["contract_clauses"])
        evidence[row["claim_id"]] = ev
        text, src = draft_note(ev, use_llm=use_llm)
        note_sources[row["claim_id"]] = src
        (notes_dir / f"{row['claim_id']}.txt").write_text(text + "\n", encoding="utf-8")

    truth_path = data_dir / "ground_truth.csv"
    rule_perf = score(findings, pd.read_csv(truth_path)) if truth_path.exists() else pd.DataFrame()
    calibration = _calibration(claims)

    # Persist results next to the raw tables so they can be queried with SQL.
    load_tables(con, {
        "claims": _dbsafe(claims), "claim_lines": _dbsafe(claim_lines), "claim_events": _dbsafe(events),
        "dq_report": _dbsafe(dq), "rule_recovery_rates": rates,
    })
    con.close()

    # Flat exports (the R cross-check reads these).
    export = claim_lines.copy()
    export["period"] = pd.to_datetime(export["period"]).dt.strftime("%Y-%m-%d")
    export.drop(columns=["cutoff"]).to_csv(out_dir / "findings.csv", index=False)
    claims.to_csv(out_dir / "claims.csv", index=False)
    totals = findings.groupby("rule").agg(n_lines=("line_id", "count"), total_est_overcharge=("est_overcharge", "sum")).round(2).reset_index()
    totals.to_csv(out_dir / "rule_totals.csv", index=False)
    dq.to_csv(out_dir / "dq_report.csv", index=False)

    meta = {
        "year": cfg.year, "as_of": cfg.as_of.isoformat(), "report_date": report_date.isoformat(),
        "lines_loaded": int(len(lines)),
    }
    payload = {
        "claims": claims, "claim_lines": claim_lines, "events": events, "rule_perf": rule_perf,
        "calibration": calibration, "dq": dq, "quarantined": quarantined, "evidence": evidence,
        "vendors": ref["vendors"], "meta": meta,
    }
    build_workbook(out_dir / "dispute_workbook.xlsx", payload)
    build_dashboard(out_dir / "dashboard.html", payload)

    return {
        "meta": meta, "claims": claims, "findings": findings, "raw_hits": len(raw), "rule_perf": rule_perf,
        "calibration": calibration, "dq": dq, "note_sources": note_sources, "out_dir": out_dir,
    }
