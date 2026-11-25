"""Score audit rules against the injected answer key and guard against regressions.

A line counts as correct for a rule only when the rule it was finally assigned
matches the injected error type. Precision is measured over everything the
audit flagged; recall over everything that was injected.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from .config import GOLDEN, RULE_PRIORITY, Config
from .generate import generate
from .ingest import ingest_invoices, load_reference

TOLERANCE = 0.02


def score(findings: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    flagged = findings[["line_id", "rule", "est_overcharge"]]
    rows = []
    for rule in RULE_PRIORITY:
        f = flagged[flagged.rule == rule]
        t = truth[truth.error_type == rule]
        hit = f.merge(t, on="line_id", how="inner")
        tp, fp, fn = len(hit), len(f) - len(hit), len(t) - len(hit)
        rows.append({
            "rule": rule,
            "injected": len(t),
            "flagged": len(f),
            "true_pos": tp,
            "false_pos": fp,
            "missed": fn,
            "precision": round(tp / len(f), 4) if len(f) else None,
            "recall": round(tp / len(t), 4) if len(t) else None,
            "dollars_injected": round(float(t.true_overcharge.sum()), 2),
            "dollars_estimated_on_hits": round(float(hit.est_overcharge.sum()), 2),
            "dollars_flagged_total": round(float(f.est_overcharge.sum()), 2),
        })
    return pd.DataFrame(rows)


def run_on_dataset(cfg: Config, data_dir: Path, rules_dir: Path | None = None):
    from .db import build_warehouse
    from .rules import run_rules

    ref = load_reference(data_dir)
    lines, dq, _ = ingest_invoices(data_dir, ref["vendors"], cfg.year)
    con = build_warehouse(cfg, ref, lines)
    findings, raw = run_rules(con, cfg, rules_dir)
    truth = pd.read_csv(Path(data_dir) / "ground_truth.csv")
    return findings, truth, dq, raw


def golden_scores(rules_dir: Path | None = None, cfg: Config = GOLDEN) -> pd.DataFrame:
    with tempfile.TemporaryDirectory() as tmp:
        generate(cfg, Path(tmp))
        findings, truth, _, _ = run_on_dataset(cfg, Path(tmp), rules_dir)
    return score(findings, truth)


def _to_baseline(df: pd.DataFrame) -> dict:
    return {r.rule: {"precision": r.precision, "recall": r.recall} for r in df.itertuples()}


def compare(current: pd.DataFrame, baseline: dict, tol: float = TOLERANCE) -> tuple[pd.DataFrame, bool]:
    rows, ok = [], True
    for r in current.itertuples():
        base = baseline.get(r.rule, {})
        entry = {"rule": r.rule}
        for metric in ("precision", "recall"):
            now, before = getattr(r, metric), base.get(metric)
            delta = None if now is None or before is None else round(now - before, 4)
            entry[f"{metric}_before"], entry[f"{metric}_now"], entry[f"{metric}_delta"] = before, now, delta
            if delta is not None and delta < -tol:
                ok = False
        rows.append(entry)
    out = pd.DataFrame(rows)
    out["verdict"] = [
        "REGRESSION" if any((d is not None and d < -tol) for d in (r.precision_delta, r.recall_delta))
        else ("improved" if any((d is not None and d > tol) for d in (r.precision_delta, r.recall_delta)) else "same")
        for r in out.itertuples()
    ]
    return out, ok


def load_baseline(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def save_baseline(df: pd.DataFrame, path: Path) -> None:
    Path(path).write_text(json.dumps(_to_baseline(df), indent=2) + "\n")
