from types import SimpleNamespace

import pandas as pd

from billaudit.harness import compare, golden_scores, load_baseline
from billaudit.notes import draft_note, template_note, validate_llm_text
from billaudit.config import ROOT


def _evidence():
    lines = pd.DataFrame({"line_id": ["L1", "L2"], "period": ["2025-08", "2025-09"], "rate_billed": [320.0, 320.0],
                          "contract_rate": [320.0, 320.0], "amount": [320.0, 320.0], "est_overcharge": [320.0, 320.0],
                          "claimable": [True, True]})
    orders = pd.DataFrame({"order_id": ["ORD-1"], "order_type": ["disconnect"], "order_date": ["2025-02-01"], "effective_date": ["2025-02-22"]})
    claim = {"claim_id": "C-0001", "vendor_name": "Northgate Telecom", "circuit_id": "CKT-10001", "rule": "post_disconnect",
             "claimable_amount": 640.0, "barred_amount": 0.0, "window_months": 6}
    clauses = [{"category": "disconnect", "clause_ref": "Sec. 6.2", "text": "Billing stops on the effective date."}]
    return {"claim": claim, "rule_label": "Billed after disconnect", "lines": lines, "orders": orders, "clauses": clauses,
            "circuit": {"service": "DS1", "true_jurisdiction": "intrastate", "a_state": "NY", "z_state": "NY"}}


class _Client:
    def __init__(self, text):
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(type="text", text=text)]))


def test_template_note_carries_the_facts():
    t = template_note(_evidence())
    assert "CKT-10001" in t and "$640.00" in t and "2025-02-22" in t and "Sec. 6.2" in t


def test_note_names_the_lines_and_uses_singular_period_wording():
    ev = _evidence()
    t = template_note(ev)
    assert "Invoice lines: L1, L2." in t and "the periods 2025-08 to 2025-09" in t
    ev["lines"] = ev["lines"].head(1)
    ev["claim"]["claimable_amount"] = 320.0
    one = template_note(ev)
    assert "the period 2025-08," in one and "to 2025-08" not in one


def test_llm_text_with_invented_numbers_is_refused():
    ev = _evidence()
    text, src = draft_note(ev, use_llm=True, client=_Client("Please credit $999.00 for the circuit."))
    assert src == "template" and text == template_note(ev)


def test_llm_text_with_same_numbers_is_accepted():
    ev = _evidence()
    base = template_note(ev)
    text, src = draft_note(ev, use_llm=True, client=_Client(base.replace("We are disputing", "We dispute")))
    assert src == "llm" and "We dispute" in text
    assert validate_llm_text(text, base)


def test_llm_off_by_default():
    assert draft_note(_evidence())[1] == "template"


def test_golden_run_matches_committed_baseline():
    table, ok = compare(golden_scores(), load_baseline(ROOT / "golden" / "baseline.json"))
    assert ok, table.to_string()


def test_compare_flags_a_drop_in_recall():
    base = {"spike": {"precision": 0.9, "recall": 0.95}}
    now = pd.DataFrame([{"rule": "spike", "precision": 0.95, "recall": 0.7}])
    table, ok = compare(now, base)
    assert not ok and table.verdict.iloc[0] == "REGRESSION"


def test_compare_allows_small_noise_and_reports_gains():
    base = {"spike": {"precision": 0.80, "recall": 0.95}}
    table, ok = compare(pd.DataFrame([{"rule": "spike", "precision": 0.90, "recall": 0.94}]), base)
    assert ok and table.verdict.iloc[0] == "improved"
