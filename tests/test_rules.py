import pandas as pd
import pytest

from billaudit.config import RULE_PRIORITY
from billaudit.harness import score


@pytest.mark.parametrize("rule", [r for r in RULE_PRIORITY if r != "spike"])
def test_exact_rules_find_everything_and_flag_nothing_else(scored, rule):
    row = score(scored["findings"], scored["truth"]).set_index("rule").loc[rule]
    assert row.injected > 0
    assert row.recall == 1.0
    assert row.precision == 1.0


def test_spike_rule_has_full_recall_but_is_fooled_by_voice_usage(scored):
    row = score(scored["findings"], scored["truth"]).set_index("rule").loc["spike"]
    assert row.recall == 1.0
    assert 0.5 < row.precision < 1.0   # the usage-overage lines are real false positives


def test_one_finding_per_line_and_overlaps_resolved(scored):
    f, raw = scored["findings"], scored["raw"]
    assert f.line_id.is_unique
    assert len(raw) > len(f)           # injected duplicates of over-rate lines hit two rules
    dups = set(scored["truth"][scored["truth"].error_type == "duplicate"].line_id)
    assert set(f[f.line_id.isin(dups)].rule) == {"duplicate"}


def test_install_fees_are_never_flagged(scored, data_dir):
    inv = pd.concat([pd.read_csv(p) for p in (data_dir / "invoices").glob("invoice_V0?_2025-??.csv")])
    nrc = set(inv[inv.charge_type == "NRC"].line_id)
    assert nrc and not nrc & set(scored["findings"].line_id)


def test_disconnect_month_is_not_billed_in_error(scored, data_dir):
    circuits = pd.read_csv(data_dir / "circuits.csv", parse_dates=["disconnect_date"]).dropna(subset=["disconnect_date"])
    f = scored["findings"][scored["findings"].rule == "post_disconnect"].merge(circuits, on="circuit_id")
    assert (pd.to_datetime(f.period) > f.disconnect_date.dt.to_period("M").dt.to_timestamp()).all()


def test_amended_rates_do_not_look_like_overcharges(scored):
    f = scored["findings"]
    flagged_v2_after_amendment = f[(f.rule == "rate_mismatch") & (f.vendor_id == "V02") & (pd.to_datetime(f.period) >= "2025-07-01")]
    truth_ids = set(scored["truth"].line_id)
    assert set(flagged_v2_after_amendment.line_id) <= truth_ids


def test_estimates_match_injected_dollars(scored):
    perf = score(scored["findings"], scored["truth"]).set_index("rule")
    for rule in ("unknown_circuit", "post_disconnect", "duplicate", "jurisdiction_misrate", "rate_mismatch"):
        assert perf.loc[rule, "dollars_estimated_on_hits"] == pytest.approx(perf.loc[rule, "dollars_injected"], abs=1.0)
