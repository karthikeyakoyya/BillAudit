"""Excel workbook for the audit team. Totals on the Summary sheet are live
formulas over the Claims sheet, so they follow any edit an analyst makes."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .config import RULE_LABELS, RULE_PRIORITY

FONT = "Arial"
INK = "1F2937"
HEAD_FILL = PatternFill("solid", fgColor="1F2937")
BAND_FILL = PatternFill("solid", fgColor="F3F4F6")
LABEL_FILL = PatternFill("solid", fgColor="E5E7EB")
THIN = Side(style="thin", color="D1D5DB")
MONEY = '$#,##0.00;($#,##0.00);"-"'
PCT = "0.0%"


def _style_cell(c, bold=False, color=INK, size=10, fmt=None, wrap=False, align=None):
    c.font = Font(name=FONT, size=size, bold=bold, color=color)
    if fmt:
        c.number_format = fmt
    if wrap or align:
        c.alignment = Alignment(wrap_text=wrap, vertical="top", horizontal=align)


def _title(ws, text, sub=None):
    ws["A1"] = text
    _style_cell(ws["A1"], bold=True, size=14)
    if sub:
        ws["A2"] = sub
        _style_cell(ws["A2"], color="6B7280")


def write_table(ws, df: pd.DataFrame, row: int, col: int = 1, formats: dict | None = None,
                widths: dict | None = None, filter_: bool = False):
    formats = formats or {}
    for j, name in enumerate(df.columns):
        c = ws.cell(row=row, column=col + j, value=name)
        c.fill = HEAD_FILL
        _style_cell(c, bold=True, color="FFFFFF", wrap=True)
        c.border = Border(bottom=THIN)
    for i, rec in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(rec):
            if pd.isna(v) if not isinstance(v, (list, dict)) else False:
                v = None
            if isinstance(v, pd.Timestamp):
                v = v.to_pydatetime().date()
            c = ws.cell(row=row + i, column=col + j, value=v)
            _style_cell(c, fmt=formats.get(df.columns[j]))
            if i % 2 == 0:
                c.fill = BAND_FILL
    for j, name in enumerate(df.columns):
        letter = get_column_letter(col + j)
        w = (widths or {}).get(name)
        if w is None:
            body = df[name].astype(str).str.len().max() if len(df) else 0
            w = min(max(len(str(name)) + 2, (body if body == body else 0) + 2), 46)
        ws.column_dimensions[letter].width = w
    if filter_ and len(df):
        ws.auto_filter.ref = f"{get_column_letter(col)}{row}:{get_column_letter(col + len(df.columns) - 1)}{row + len(df)}"
    return row + len(df)


CLAIM_COLS = [
    "rank", "claim_id", "vendor_id", "vendor_name", "circuit_id", "service", "rule", "rule_label", "n_lines",
    "first_period", "last_period", "total_overcharge", "claimable_amount", "barred_amount", "recovery_rate",
    "expected_value", "decision", "status", "filed_date", "credit_amount", "credit_pending",
]


def build_workbook(path: Path, d: dict) -> None:
    """d keys: claims, claim_lines, events, rule_perf, calibration, dq, quarantined, evidence (dict claim_id->ev),
    vendors, meta."""
    wb = Workbook()
    claims = d["claims"].copy()
    claims["rule_label"] = claims["rule"].map(RULE_LABELS)
    claims["first_period"] = pd.to_datetime(claims["first_period"]).dt.strftime("%Y-%m")
    claims["last_period"] = pd.to_datetime(claims["last_period"]).dt.strftime("%Y-%m")
    claims["filed_date"] = pd.to_datetime(claims["filed_date"])
    claims = claims[CLAIM_COLS]
    n = len(claims)
    letter = {c: get_column_letter(i + 1) for i, c in enumerate(CLAIM_COLS)}

    def rng(col):  # absolute range on the Claims sheet
        return f"Claims!${letter[col]}$2:${letter[col]}${n + 1}"

    # ---------------- Summary ----------------
    ws = wb.active
    ws.title = "Summary"
    m = d["meta"]
    _title(ws, "Telecom invoice audit: dispute summary",
           f"Invoices {m['year']} | audit run {m['as_of']} | tracker cut {m['report_date']} | simulated data")
    ws["A4"] = "Position"
    _style_cell(ws["A4"], bold=True, size=11)
    kpis = [
        ("Invoice lines audited", int(m["lines_loaded"]), "0"),
        ("Lines flagged", f"=SUM({rng('n_lines')})", "0"),
        ("Claims raised", f"=COUNTA({rng('claim_id')})", "0"),
        ("Flagged value ($)", f"=SUM({rng('total_overcharge')})", MONEY),
        ("Claimable inside dispute windows ($)", f"=SUM({rng('claimable_amount')})", MONEY),
        ("Time-barred value ($)", f"=SUM({rng('barred_amount')})", MONEY),
        ("Claims filed this cycle", f'=COUNTIF({rng("decision")},"file")', "0"),
        ("Claimable value filed ($)", f'=SUMIFS({rng("claimable_amount")},{rng("decision")},"file")', MONEY),
        ("Expected recovery on filed claims ($)", f'=SUMIFS({rng("expected_value")},{rng("decision")},"file")', MONEY),
        ("Credits received ($)", f"=SUM({rng('credit_amount')})", MONEY),
        ("Accepted, credit not yet applied ($)", f"=SUM({rng('credit_pending')})", MONEY),
        ("Filed, no vendor answer yet", f'=COUNTIF({rng("status")},"filed")', "0"),
    ]
    for i, (label, formula, fmt) in enumerate(kpis, start=5):
        ws.cell(row=i, column=1, value=label).fill = LABEL_FILL
        _style_cell(ws.cell(row=i, column=1))
        c = ws.cell(row=i, column=2, value=formula)
        _style_cell(c, bold=True, fmt=fmt, align="right")

    r0 = 5 + len(kpis) + 2
    ws.cell(row=r0, column=1, value="By rule")
    _style_cell(ws.cell(row=r0, column=1), bold=True, size=11)
    hdr = ["Rule", "Claims", "Flagged ($)", "Claimable ($)", "Filed claims", "Expected recovery ($)", "Credits received ($)"]
    for j, h in enumerate(hdr, start=1):
        c = ws.cell(row=r0 + 1, column=j, value=h)
        c.fill = HEAD_FILL
        _style_cell(c, bold=True, color="FFFFFF", wrap=True)
    for i, rule in enumerate(RULE_PRIORITY, start=r0 + 2):
        ws.cell(row=i, column=1, value=RULE_LABELS[rule])
        ws.cell(row=i, column=2, value=f'=COUNTIF({rng("rule")},"{rule}")')
        ws.cell(row=i, column=3, value=f'=SUMIFS({rng("total_overcharge")},{rng("rule")},"{rule}")')
        ws.cell(row=i, column=4, value=f'=SUMIFS({rng("claimable_amount")},{rng("rule")},"{rule}")')
        ws.cell(row=i, column=5, value=f'=COUNTIFS({rng("rule")},"{rule}",{rng("decision")},"file")')
        ws.cell(row=i, column=6, value=f'=SUMIFS({rng("expected_value")},{rng("rule")},"{rule}",{rng("decision")},"file")')
        ws.cell(row=i, column=7, value=f'=SUMIFS({rng("credit_amount")},{rng("rule")},"{rule}")')
        for j, f in enumerate(["@", "0", MONEY, MONEY, "0", MONEY, MONEY], start=1):
            _style_cell(ws.cell(row=i, column=j), fmt=f if j > 1 else None)
    r1 = r0 + 2 + len(RULE_PRIORITY) + 1

    ws.cell(row=r1, column=1, value="By vendor")
    _style_cell(ws.cell(row=r1, column=1), bold=True, size=11)
    hdr = ["Vendor", "Dispute window (months)", "Claims", "Claimable ($)", "Filed claims", "Credits received ($)", "Time-barred ($)"]
    for j, h in enumerate(hdr, start=1):
        c = ws.cell(row=r1 + 1, column=j, value=h)
        c.fill = HEAD_FILL
        _style_cell(c, bold=True, color="FFFFFF", wrap=True)
    for i, v in enumerate(d["vendors"].itertuples(), start=r1 + 2):
        ws.cell(row=i, column=1, value=f"{v.vendor_name} ({v.vendor_id})")
        ws.cell(row=i, column=2, value=int(v.dispute_window_months))
        ws.cell(row=i, column=3, value=f'=COUNTIF({rng("vendor_id")},"{v.vendor_id}")')
        ws.cell(row=i, column=4, value=f'=SUMIFS({rng("claimable_amount")},{rng("vendor_id")},"{v.vendor_id}")')
        ws.cell(row=i, column=5, value=f'=COUNTIFS({rng("vendor_id")},"{v.vendor_id}",{rng("decision")},"file")')
        ws.cell(row=i, column=6, value=f'=SUMIFS({rng("credit_amount")},{rng("vendor_id")},"{v.vendor_id}")')
        ws.cell(row=i, column=7, value=f'=SUMIFS({rng("barred_amount")},{rng("vendor_id")},"{v.vendor_id}")')
        for j, f in enumerate([None, "0", "0", MONEY, "0", MONEY, MONEY], start=1):
            _style_cell(ws.cell(row=i, column=j), fmt=f)
    r2 = r1 + 2 + len(d["vendors"]) + 1
    notes = [
        "Basis of the numbers",
        "All data is simulated from a seed. Vendor names, rates, circuits and contracts are invented.",
        "Flagged value is the estimated overcharge on each flagged line, one finding per line (overlaps resolved by rule priority).",
        "Claimable value counts only invoice periods inside the vendor's dispute window as of the audit date.",
        "Expected recovery = claimable value x the rule's recovery rate from the prior-year dispute history.",
        "Vendor responses and credits after filing are simulated; credits are applied 12 days after acceptance.",
        "Invoice lines audited is a count taken from the ingest step, not a formula.",
    ]
    for i, t in enumerate(notes, start=r2):
        c = ws.cell(row=i, column=1, value=t)
        _style_cell(c, bold=(i == r2), size=10 if i > r2 else 11, color=INK if i == r2 else "4B5563")
    ws.column_dimensions["A"].width = 44
    for col in "BCDEFG":
        ws.column_dimensions[col].width = 20
    ws.sheet_view.showGridLines = False

    # ---------------- Claims ----------------
    ws = wb.create_sheet("Claims")
    fm = {"total_overcharge": MONEY, "claimable_amount": MONEY, "barred_amount": MONEY, "expected_value": MONEY,
          "credit_amount": MONEY, "credit_pending": MONEY, "recovery_rate": PCT, "filed_date": "yyyy-mm-dd"}
    write_table(ws, claims, 1, formats=fm, filter_=True)
    ws.freeze_panes = "C2"

    # ---------------- Lifecycle ----------------
    ws = wb.create_sheet("Lifecycle")
    filed = d["claims"][d["claims"]["decision"] == "file"].copy()
    life = filed[["claim_id", "vendor_name", "circuit_id", "rule", "claimable_amount", "expected_value", "filed_date",
                  "status", "response_date", "response_outcome", "reject_reason", "credit_pct", "credit_amount",
                  "credit_pending", "aging_days", "aging_bucket"]].copy()
    for col in ("filed_date", "response_date"):
        life[col] = pd.to_datetime(life[col])
    write_table(ws, life, 1, formats={"claimable_amount": MONEY, "expected_value": MONEY, "credit_amount": MONEY,
                                      "credit_pending": MONEY, "credit_pct": PCT, "filed_date": "yyyy-mm-dd",
                                      "response_date": "yyyy-mm-dd"}, filter_=True)
    ws.freeze_panes = "B2"

    ws = wb.create_sheet("Events")
    ev = d["events"].copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    ev = ev[ev.claim_id.isin(filed.claim_id)].sort_values(["claim_id", "event_date"])
    write_table(ws, ev, 1, formats={"event_date": "yyyy-mm-dd"}, widths={"note": 60}, filter_=True)
    ws.freeze_panes = "A2"

    # ---------------- Rule performance ----------------
    ws = wb.create_sheet("Rule Performance")
    _title(ws, "Rules scored against the injected answer key",
           "Precision = share of flagged lines that were real injected errors. Recall = share of injected errors that were flagged.")
    perf = d["rule_perf"].copy()
    perf.insert(1, "label", perf["rule"].map(RULE_LABELS))
    end = write_table(ws, perf, 4, formats={"precision": PCT, "recall": PCT, "dollars_injected": MONEY,
                                           "dollars_estimated_on_hits": MONEY, "dollars_flagged_total": MONEY})
    ws.cell(row=end + 2, column=1, value="Predicted vs actual recovery on resolved claims")
    _style_cell(ws.cell(row=end + 2, column=1), bold=True, size=11)
    write_table(ws, d["calibration"], end + 3, formats={"predicted_rate": PCT, "actual_rate": PCT})

    # ---------------- Findings ----------------
    ws = wb.create_sheet("Findings")
    f = d["claim_lines"][["claim_id", "line_id", "rule", "vendor_id", "circuit_id", "period", "charge_type", "rate_billed",
                          "contract_rate", "amount", "est_overcharge", "claimable", "detail"]].copy()
    f["period"] = pd.to_datetime(f["period"]).dt.strftime("%Y-%m")
    f["claimable"] = f["claimable"].map({True: "Yes", False: "No"})
    write_table(ws, f, 1, formats={"rate_billed": MONEY, "contract_rate": MONEY, "amount": MONEY, "est_overcharge": MONEY},
                widths={"detail": 70}, filter_=True)
    ws.freeze_panes = "C2"

    # ---------------- Data quality ----------------
    ws = wb.create_sheet("Data Quality")
    _title(ws, "Invoice file gate", "Files failing structure or row checks are held back from the audit.")
    dq = d["dq"].copy()
    dq = pd.concat([dq[dq.status == "rejected"], dq[dq.status != "rejected"]])
    end = write_table(ws, dq, 4, widths={"file": 38, "issues": 90})
    if len(d["quarantined"]):
        q = d["quarantined"]
        ws.cell(row=end + 2, column=1, value="Quarantined rows (reason counts)")
        _style_cell(ws.cell(row=end + 2, column=1), bold=True, size=11)
        qs = q.groupby(["file", "reason"]).size().reset_index(name="rows")
        write_table(ws, qs, end + 3)

    # ---------------- Evidence sheets ----------------
    for cid, ev_ in d["evidence"].items():
        _evidence_sheet(wb, cid, ev_, d["meta"])

    wb.save(path)


def _evidence_sheet(wb: Workbook, cid: str, ev: dict, meta: dict) -> None:
    c = ev["claim"]
    ws = wb.create_sheet(f"EV {cid}")
    _title(ws, f"Claim {cid}: {c['vendor_name']}, circuit {c['circuit_id']}", ev["rule_label"])
    facts = [
        ("Service", ev["circuit"]["service"] or "not in inventory"),
        ("True jurisdiction", ev["circuit"]["true_jurisdiction"] or "n/a"),
        ("Circuit ends (states)", f"{ev['circuit']['a_state'] or 'n/a'} / {ev['circuit']['z_state'] or 'n/a'}"),
        ("Dispute window (months)", int(c["window_months"])),
        ("Earliest period still disputable", pd.Timestamp(c["cutoff"]).strftime("%Y-%m")),
        ("Status", c["status"]),
    ]
    r = 4
    for label, val in facts:
        ws.cell(row=r, column=1, value=label).fill = LABEL_FILL
        _style_cell(ws.cell(row=r, column=1))
        _style_cell(ws.cell(row=r, column=2, value=val))
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Invoice lines")
    _style_cell(ws.cell(row=r, column=1), bold=True, size=11)
    lines = ev["lines"].copy()
    lines["claimable"] = lines["claimable"].map({True: "Yes", False: "No"})
    hdr_row = r + 1
    end = write_table(ws, lines, hdr_row, formats={"rate_billed": MONEY, "contract_rate": MONEY, "amount": MONEY,
                                                   "expected_amount": MONEY, "est_overcharge": MONEY,
                                                   "billed_pct": "0.00", "tariff_pct": "0.00"})
    first, last = hdr_row + 1, end
    cols = list(lines.columns)
    est = get_column_letter(cols.index("est_overcharge") + 1)
    clm = get_column_letter(cols.index("claimable") + 1)

    r = end + 2
    ws.cell(row=r, column=1, value="Claimable total")
    ws.cell(row=r, column=2, value=f'=SUMIFS({est}{first}:{est}{last},{clm}{first}:{clm}{last},"Yes")')
    _style_cell(ws.cell(row=r, column=1), bold=True)
    _style_cell(ws.cell(row=r, column=2), bold=True, fmt=MONEY)
    ws.cell(row=r + 1, column=1, value="Outside dispute window")
    ws.cell(row=r + 1, column=2, value=f'=SUMIFS({est}{first}:{est}{last},{clm}{first}:{clm}{last},"No")')
    _style_cell(ws.cell(row=r + 1, column=1))
    _style_cell(ws.cell(row=r + 1, column=2), fmt=MONEY)
    ws.cell(row=r + 2, column=1, value="Method")
    _style_cell(ws.cell(row=r + 2, column=1))
    ws.cell(row=r + 2, column=2, value="Overcharge per line = billed amount less the amount at the contract rate in force for that period.")
    _style_cell(ws.cell(row=r + 2, column=2), color="4B5563")

    r += 4
    if len(ev["orders"]):
        ws.cell(row=r, column=1, value="Order records")
        _style_cell(ws.cell(row=r, column=1), bold=True, size=11)
        r = write_table(ws, ev["orders"], r + 1) + 2
    if len(ev["contract"]):
        ws.cell(row=r, column=1, value="Contract rates for this service and jurisdiction")
        _style_cell(ws.cell(row=r, column=1), bold=True, size=11)
        r = write_table(ws, ev["contract"], r + 1, formats={"rate": MONEY}) + 2
    if len(ev.get("tariff", [])):
        ws.cell(row=r, column=1, value="Tariff surcharge percentage (NECA-style reference)")
        _style_cell(ws.cell(row=r, column=1), bold=True, size=11)
        r = write_table(ws, ev["tariff"], r + 1, formats={"surcharge_pct": "0.00"}) + 2
    ws.cell(row=r, column=1, value="Contract clauses")
    _style_cell(ws.cell(row=r, column=1), bold=True, size=11)
    for k, cl in enumerate(ev["clauses"], start=1):
        a = ws.cell(row=r + k, column=1, value=f"{cl['clause_ref']} ({cl['category'].replace('_', ' ')})")
        _style_cell(a)
        b = ws.cell(row=r + k, column=2, value=cl["text"])
        _style_cell(b, wrap=True)
        ws.merge_cells(start_row=r + k, start_column=2, end_row=r + k, end_column=8)
        ws.row_dimensions[r + k].height = 42
    ws.column_dimensions["A"].width = 34
    for col, w in zip("BCDEFGH", [24, 14, 14, 14, 16, 16, 12]):
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False
