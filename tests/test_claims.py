from dataclasses import replace

import pandas as pd
import pytest

from billaudit.db import build_warehouse
from billaudit.ingest import ingest_invoices, load_reference
from billaudit.lifecycle import ClaimTracker, IllegalTransition, run_cycle
from billaudit.ranking import rank_claims, recovery_rates
from billaudit.rollup import add_months, build_claims, window_start


@pytest.fixture(scope="module")
def built(cfg, data_dir, scored):
    ref = load_reference(data_dir)
    claims, lines = build_claims(scored["findings"], ref["vendors"], cfg)
    lines_in, _, _ = ingest_invoices(data_dir, ref["vendors"], cfg.year)
    con = build_warehouse(cfg, ref, lines_in)
    ranked = rank_claims(claims, recovery_rates(con), cfg)
    return {"claims": claims, "lines": lines, "ranked": ranked, "ref": ref}


def test_window_start_counts_back_in_months(cfg):
    assert window_start(cfg.as_of, 6) == pd.Timestamp("2025-07-01")
    assert window_start(cfg.as_of, 12) == pd.Timestamp("2025-01-01")
    assert add_months(pd.Timestamp("2026-01-31").date().replace(day=1), -2).isoformat() == "2025-11-01"


def test_claims_cover_every_flagged_dollar_once(built, scored):
    c = built["claims"]
    assert c.total_overcharge.sum() == pytest.approx(scored["findings"].est_overcharge.sum(), abs=0.5)
    assert c.n_lines.sum() == len(scored["findings"])
    assert c.groupby(["vendor_id", "circuit_id", "rule"]).size().max() == 1


def test_repeating_errors_collapse_into_one_claim(built):
    c = built["claims"]
    assert (c.n_lines > 1).any()
    assert len(c) < c.n_lines.sum()


def test_dispute_window_splits_claimable_from_barred(built):
    c, lines = built["claims"], built["lines"]
    assert (c.claimable_amount + c.barred_amount).round(2).eq(c.total_overcharge.round(2)).all()
    short = lines[lines.window_months == 6]
    assert (short[~short.claimable].period < pd.Timestamp("2025-07-01")).all()
    assert (short[short.claimable].period >= pd.Timestamp("2025-07-01")).all()


def test_expected_value_is_claimable_times_rule_rate(built):
    r = built["ranked"]
    assert (r.expected_value - (r.claimable_amount * r.recovery_rate)).abs().max() < 0.01


def test_filing_respects_capacity_and_picks_highest_value(built, cfg):
    r = built["ranked"]
    filed = r[r.decision == "file"]
    assert len(filed) == min(cfg.capacity, (r.decision.isin(["file", "defer_capacity"])).sum())
    waiting = r[r.decision == "defer_capacity"]
    if len(waiting):
        assert filed.expected_value.min() >= waiting.expected_value.max()
    assert not r[r.decision == "time_barred"].claimable_lines.gt(0).any()
    assert (r[r.decision == "file"].claimable_amount >= cfg.min_claim_value).all()


def test_tracker_rejects_illegal_moves():
    t = ClaimTracker(["C-1"], pd.Timestamp("2026-01-31").date())
    with pytest.raises(IllegalTransition):
        t.move("C-1", "credited", pd.Timestamp("2026-02-01").date())
    t.move("C-1", "reviewed", pd.Timestamp("2026-02-01").date())
    t.move("C-1", "filed", pd.Timestamp("2026-02-02").date())
    with pytest.raises(IllegalTransition):
        t.move("C-1", "detected", pd.Timestamp("2026-02-03").date())


def test_cycle_outcomes_are_consistent(built, cfg):
    claims, events, report_date = run_cycle(built["ranked"], cfg)
    assert set(claims.status) <= {"deferred", "time_barred", "filed", "accepted", "partial", "rejected", "credited"}
    assert (claims[claims.decision != "file"].status.isin(["deferred", "time_barred"])).all()
    cred = claims[claims.status == "credited"]
    assert (cred.credit_amount <= cred.claimable_amount + 0.01).all() and (cred.credit_amount > 0).all()
    assert (claims[claims.status == "rejected"].credit_amount == 0).all()
    assert claims[claims.status == "rejected"].reject_reason.notna().all()
    waiting = claims[claims.status == "filed"]
    assert waiting.aging_bucket.notna().all() and waiting.response_date.isna().all()
    ev = events.sort_values(["claim_id", "event_date"])
    assert (ev.groupby("claim_id").event_date.apply(lambda s: s.is_monotonic_increasing)).all()
    assert pd.Timestamp(report_date) == pd.Timestamp(cfg.as_of) + pd.Timedelta(days=cfg.report_days_after)


def test_cycle_is_repeatable(built, cfg):
    a, _, _ = run_cycle(built["ranked"], cfg)
    b, _, _ = run_cycle(built["ranked"], cfg)
    assert a.status.tolist() == b.status.tolist()


def test_lower_capacity_files_fewer(built, cfg):
    small = rank_claims(built["claims"], built["ranked"][["rule", "n_past_claims", "recovery_rate"]].drop_duplicates("rule"),
                        replace(cfg, capacity=5))
    assert (small.decision == "file").sum() == 5
