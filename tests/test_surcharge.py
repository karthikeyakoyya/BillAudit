import pandas as pd
import pytest
from openpyxl import Workbook

from billaudit.db import build_warehouse
from billaudit.evidence import build_evidence
from billaudit.ingest import ingest_invoices, load_reference
from billaudit.notes import template_note
from billaudit.ranking import rank_claims, recovery_rates
from billaudit.report_xlsx import _evidence_sheet
from billaudit.rollup import build_claims


@pytest.fixture(scope="module")
def sur(cfg, data_dir, scored):
    ref = load_reference(data_dir)
    lines, _, _ = ingest_invoices(data_dir, ref["vendors"], cfg.year)
    con = build_warehouse(cfg, ref, lines)
    claims, claim_lines = build_claims(scored["findings"], ref["vendors"], cfg)
    ranked = rank_claims(claims, recovery_rates(con), cfg)
    ranked["status"] = "detected"
    return {"con": con, "ref": ref, "lines": lines, "claims": ranked, "claim_lines": claim_lines}


def test_tariff_table_has_exempt_services_and_mid_year_changes(data_dir):
    neca = pd.read_csv(data_dir / "neca_sim.csv")
    assert (neca[neca.service.isin(["ETH100", "MPLS"])].surcharge_pct == 0).all()
    ca = neca[(neca.state == "CA") & (neca.service == "DS1")]
    assert len(ca) == 2 and ca.surcharge_pct.iloc[1] > ca.surcharge_pct.iloc[0]


def test_new_rate_after_a_tariff_change_is_not_flagged(scored, data_dir):
    inv = pd.concat([pd.read_csv(p, parse_dates=["period"]) for p in (data_dir / "invoices").glob("invoice_V0?_2025-??.csv")])
    cir = pd.read_csv(data_dir / "circuits.csv")
    lerg = pd.read_csv(data_dir / "lerg_sim.csv")
    cir = cir.merge(lerg, left_on="a_npanxx", right_on="npanxx")[["circuit_id", "state"]]
    sur = inv[(inv.charge_type == "SUR") & (inv.period >= "2025-07-01")].merge(cir, on="circuit_id")
    ca_clean = sur[(sur.state == "CA") & ~sur.line_id.isin(set(scored["truth"].line_id))]
    assert len(ca_clean) > 0
    assert not set(ca_clean.line_id) & set(scored["findings"].line_id)


def test_exempt_service_surcharge_is_flagged_in_full(scored):
    f = scored["findings"]
    exempt = f[(f.rule == "surcharge_misrate") & (f.service.isin(["ETH100", "MPLS"]))]
    assert len(exempt) > 0
    assert (exempt.est_overcharge - exempt.amount).abs().max() < 0.01
    assert exempt.detail.str.contains("is 0.0 percent").all()


def test_stale_tariff_after_a_decrease_is_found(scored):
    f = scored["findings"]
    stale = f[(f.rule == "surcharge_misrate") & (f.a_state.isin(["TX", "NY", "FL"])) & (pd.to_datetime(f.period) >= "2025-07-01")]
    assert len(stale) > 0


def test_surcharge_claim_evidence_note_and_sheet(sur):
    claim = sur["claims"][sur["claims"].rule == "surcharge_misrate"].iloc[0]
    ev = build_evidence(sur["con"], claim, sur["claim_lines"], sur["ref"]["contract_clauses"])
    assert {"billed_pct", "tariff_pct", "expected_amount"} <= set(ev["lines"].columns)
    assert len(ev["tariff"]) >= 1
    assert any(c["category"] == "regulatory_surcharge" for c in ev["clauses"])
    note = template_note(ev)
    assert "tariff" in note and "percent" in note and claim["circuit_id"] in note
    wb = Workbook()
    _evidence_sheet(wb, claim["claim_id"], ev, {})
    ws = wb[f"EV {claim['claim_id']}"]
    formulas = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=SUMIFS")]
    assert len(formulas) == 2 and all(f.startswith("=SUMIFS(G") for f in formulas)
