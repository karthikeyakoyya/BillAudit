"""Synthetic telecom billing data with a known answer key.

Nothing here is real vendor data. Rates, circuits, contracts and the
LERG/NECA-style lookup are generated from a seed. A set of billing errors is
injected on purpose and recorded in ground_truth.csv so the audit rules can be
scored later. Legitimate-but-unusual charges (install fees, prorated first
months, contract amendments, usage on voice lines) are included so the rules
can also be scored on what they should leave alone.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .sim_params import RULE_ACCEPT_P, RULE_PARTIAL_P, accept_probability

VENDORS = [
    ("V01", "Northgate Telecom", 6),
    ("V02", "Pinecrest Networks", 9),
    ("V03", "Harborline Carrier", 12),
    ("V04", "Sable Communications", 12),
]
SERVICES = {"DS1": 310.0, "ETH100": 520.0, "PRI": 410.0, "VOICE": 38.0, "MPLS": 780.0}
SERVICE_WEIGHTS = [0.27, 0.22, 0.12, 0.27, 0.12]
STATES = {
    "CA": "415", "TX": "214", "NY": "212", "FL": "305", "IL": "312", "WA": "206",
    "GA": "404", "MA": "617", "CO": "303", "AZ": "602", "OH": "216", "PA": "215",
}
VENDOR_RATE_MULT = {"V01": 1.00, "V02": 0.94, "V03": 1.07, "V04": 0.98}
FAR_FUTURE = date(2099, 12, 31)

# Injected error counts at n_circuits = 600. They scale with circuit count.
BASE_COUNTS = {
    "post_disconnect": 30,
    "rate_mismatch": 35,
    "jurisdiction_misrate": 25,
    "unknown_circuit": 15,
    "duplicate": 40,
    "spike": 30,
    "usage_trap": 12,
    "overlap_duplicate": 8,
    "surcharge_rate": 10,
    "surcharge_stale": 8,
    "surcharge_exempt": 8,
}

# NECA-style tariff reference: regulatory surcharge as a percent of the monthly
# charge, by originating state and service. Data/ethernet-class services are
# exempt (0 percent). Four states change their percentage on 1 July.
NECA_EXEMPT = ["ETH100", "MPLS"]
NECA_SUBJECT = [s for s in SERVICES if s not in NECA_EXEMPT]
NECA_CHANGES = {"TX": -1.1, "NY": -0.8, "FL": -1.5, "CA": 0.9}


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _month_range(start: date, end: date) -> list[date]:
    out, cur = [], _first_of_month(start)
    while cur <= _first_of_month(end):
        out.append(cur)
        cur = _next_month(cur)
    return out


def build_lerg(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for state, npa in STATES.items():
        nxxs = rng.choice(np.arange(200, 1000), size=12, replace=False)
        for i, nxx in enumerate(sorted(nxxs)):
            rows.append((f"{npa}{nxx}", state, f"{state} RC{i + 1:02d}"))
    return pd.DataFrame(rows, columns=["npanxx", "state", "rate_center"])


def build_contracts(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    y = cfg.year
    rows = []
    for vid, _, _ in VENDORS:
        for svc, base in SERVICES.items():
            intra = round(base * VENDOR_RATE_MULT[vid] * float(rng.uniform(0.97, 1.03)), 2)
            inter = round(intra * 1.18, 2)
            for jur, rate in (("intrastate", intra), ("interstate", inter)):
                start = date(y - 1, 1, 1)
                if vid == "V02":  # 3 percent increase by amendment from July
                    rows.append((vid, svc, jur, rate, start, date(y, 6, 30)))
                    rows.append((vid, svc, jur, round(rate * 1.03, 2), date(y, 7, 1), FAR_FUTURE))
                elif vid == "V04":  # 5 percent reduction by amendment from April
                    rows.append((vid, svc, jur, rate, start, date(y, 3, 31)))
                    rows.append((vid, svc, jur, round(rate * 0.95, 2), date(y, 4, 1), FAR_FUTURE))
                else:
                    rows.append((vid, svc, jur, rate, start, FAR_FUTURE))
    return pd.DataFrame(rows, columns=["vendor_id", "service", "jurisdiction", "rate", "effective_from", "effective_to"])


def build_neca(cfg: Config) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed + 100)
    y, rows = cfg.year, []
    for state in STATES:
        for svc in SERVICES:
            start = date(y - 1, 1, 1)
            if svc in NECA_EXEMPT:
                rows.append((state, svc, 0.0, start, FAR_FUTURE))
                continue
            pct = round(float(rng.uniform(2.5, 9.5)), 2)
            if state in NECA_CHANGES:
                rows.append((state, svc, pct, start, date(y, 6, 30)))
                rows.append((state, svc, round(pct + NECA_CHANGES[state], 2), date(y, 7, 1), FAR_FUTURE))
            else:
                rows.append((state, svc, pct, start, FAR_FUTURE))
    return pd.DataFrame(rows, columns=["state", "service", "surcharge_pct", "effective_from", "effective_to"])


def build_clauses() -> pd.DataFrame:
    rows = []
    for vid, name, window in VENDORS:
        rows += [
            (vid, "rates", "Sec. 4.1", f"{name} will bill each service at the rate in the rate schedule effective for the invoice period. Amended rates apply from their stated effective date."),
            (vid, "jurisdiction", "Sec. 4.3", "Services whose two ends terminate in the same state are billed at the intrastate rate. Services that terminate in different states are billed at the interstate rate."),
            (vid, "disconnect", "Sec. 6.2", "Billing stops on the effective date of a disconnect order. The final invoice covers service through the month of that date."),
            (vid, "duplicate_billing", "Sec. 7.1", "A charge may appear on one invoice only. Duplicate charges are credited on request."),
            (vid, "inventory", "Sec. 2.4", "Only circuits listed in the service inventory attached to the agreement may be billed to the customer account."),
            (vid, "regulatory_surcharge", "Sec. 5.2", "Regulatory surcharges are billed as a percentage of the monthly recurring charge at the rate in the filed tariff for the circuit's originating state and service, effective for the invoice period. Services the tariff lists as exempt carry no surcharge."),
            (vid, "surcharge", "Sec. 5.5", "Charges not listed in the rate schedule require written notice to the customer before they are billed."),
            (vid, "dispute_procedure", "Sec. 9.1", f"The customer may dispute an invoiced charge within {window} months of the invoice period. A dispute must identify the circuit, invoice period and amount in question."),
        ]
    return pd.DataFrame(rows, columns=["vendor_id", "category", "clause_ref", "text"])


class _TariffBook:
    def __init__(self, neca: pd.DataFrame):
        self._rows: dict[tuple, list] = {}
        for r in neca.itertuples(index=False):
            self._rows.setdefault((r.state, r.service), []).append(r)

    def pct(self, state: str, service: str, period: date) -> float:
        for r in self._rows[(state, service)]:
            if r.effective_from <= period <= r.effective_to:
                return float(r.surcharge_pct)
        raise KeyError((state, service, period))


class _RateBook:
    def __init__(self, contracts: pd.DataFrame):
        self._rows: dict[tuple, list] = {}
        for r in contracts.itertuples(index=False):
            self._rows.setdefault((r.vendor_id, r.service, r.jurisdiction), []).append(r)

    def rate(self, vendor: str, service: str, jurisdiction: str, period: date) -> float:
        for r in self._rows[(vendor, service, jurisdiction)]:
            if r.effective_from <= period <= r.effective_to:
                return float(r.rate)
        raise KeyError((vendor, service, jurisdiction, period))


def generate(cfg: Config, out_dir: Path) -> dict[str, pd.DataFrame]:
    """Build every table, write them as CSV under out_dir, and return them."""
    rng = np.random.default_rng(cfg.seed)
    y = cfg.year
    out_dir = Path(out_dir)
    (out_dir / "invoices").mkdir(parents=True, exist_ok=True)
    for old in (out_dir / "invoices").glob("*.csv"):
        old.unlink()

    lerg = build_lerg(rng)
    contracts = build_contracts(cfg, rng)
    clauses = build_clauses()
    book = _RateBook(contracts)
    neca = build_neca(cfg)
    tariff = _TariffBook(neca)
    state_of = dict(zip(lerg.npanxx, lerg.state))
    by_state = {s: g.npanxx.tolist() for s, g in lerg.groupby("state")}
    state_list = sorted(by_state)

    # ---- circuits and orders -------------------------------------------------
    vendor_ids = [v[0] for v in VENDORS]
    svc_names = list(SERVICES)
    circuits, orders = [], []
    order_seq = 0
    for i in range(cfg.n_circuits):
        cid = f"CKT-{10001 + i}"
        vendor = str(rng.choice(vendor_ids, p=[0.30, 0.25, 0.25, 0.20]))
        service = str(rng.choice(svc_names, p=SERVICE_WEIGHTS))
        a_state = str(rng.choice(state_list))
        a_nx = str(rng.choice(by_state[a_state]))
        if service == "VOICE":
            z_nx = a_nx
        elif rng.random() < 0.72:
            z_nx = str(rng.choice([n for n in by_state[a_state] if n != a_nx]))
        else:
            z_state = str(rng.choice([s for s in state_list if s != a_state]))
            z_nx = str(rng.choice(by_state[z_state]))
        if rng.random() < 0.15:
            install = date(y, 1, 5) + timedelta(days=int(rng.integers(0, 290)))
        else:
            install = date(y - 4, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 4)))
        disconnect = None
        if install.year < y and rng.random() < 0.12:
            disconnect = date(y, 2, 3) + timedelta(days=int(rng.integers(0, 235)))
        circuits.append((cid, vendor, service, a_nx, z_nx, install, disconnect))
        order_seq += 1
        orders.append((f"ORD-{order_seq:06d}", cid, "install", install - timedelta(days=30), install))
        if disconnect:
            order_seq += 1
            orders.append((f"ORD-{order_seq:06d}", cid, "disconnect", disconnect - timedelta(days=21), disconnect))
    circuits_df = pd.DataFrame(circuits, columns=["circuit_id", "vendor_id", "service", "a_npanxx", "z_npanxx", "install_date", "disconnect_date"])
    orders_df = pd.DataFrame(orders, columns=["order_id", "circuit_id", "order_type", "order_date", "effective_date"])
    install_order = {r.circuit_id: r.order_id for r in orders_df.itertuples() if r.order_type == "install"}
    true_jur = {}
    for r in circuits_df.itertuples():
        true_jur[r.circuit_id] = "intrastate" if state_of[r.a_npanxx] == state_of[r.z_npanxx] else "interstate"

    # ---- clean invoice lines -------------------------------------------------
    lines: list[dict] = []
    by_circuit: dict[str, list[int]] = {}
    seq = 0

    def add_line(circuit, vendor, period, ctype, rate_billed, amount, jur_billed, order_ref=None) -> int:
        nonlocal seq
        seq += 1
        lines.append({
            "line_id": f"L{seq:06d}", "invoice_id": f"INV-{vendor}-{period:%Y%m}", "vendor_id": vendor,
            "circuit_id": circuit, "period": period, "charge_type": ctype,
            "rate_billed": round(rate_billed, 2), "amount": round(amount, 2),
            "billed_jurisdiction": jur_billed, "order_ref": order_ref,
        })
        by_circuit.setdefault(circuit, []).append(len(lines) - 1)
        return len(lines) - 1

    year_start, year_end = date(y, 1, 1), date(y, 12, 1)
    for c in circuits_df.itertuples():
        first = max(_first_of_month(c.install_date), year_start)
        last = _first_of_month(c.disconnect_date) if c.disconnect_date else year_end
        for p in _month_range(first, last):
            rate = book.rate(c.vendor_id, c.service, true_jur[c.circuit_id], p)
            frac = 1.0
            if c.install_date.year == y and _first_of_month(c.install_date) == p:
                dim = calendar.monthrange(p.year, p.month)[1]
                frac = (dim - c.install_date.day + 1) / dim
                nrc = float(rng.uniform(250, 900))
                add_line(c.circuit_id, c.vendor_id, p, "NRC", nrc, nrc, true_jur[c.circuit_id], install_order[c.circuit_id])
            add_line(c.circuit_id, c.vendor_id, p, "MRC", rate, rate * frac, true_jur[c.circuit_id])
            pct = tariff.pct(state_of[c.a_npanxx], c.service, p)
            if pct > 0:
                sur = round(rate * pct / 100, 2)
                add_line(c.circuit_id, c.vendor_id, p, "SUR", sur, sur, true_jur[c.circuit_id])

    # ---- inject known errors --------------------------------------------------
    scale = cfg.n_circuits / 600
    counts = {k: max(3, round(v * scale)) for k, v in BASE_COUNTS.items()}
    truth: list[tuple[str, str, float]] = []
    used: set[str] = set()

    def pick(pool: list[str], n: int) -> list[str]:
        chosen = [c for c in pool if c not in used][:n]
        used.update(chosen)
        return chosen

    cdf = circuits_df.set_index("circuit_id")
    mature = [c for c in circuits_df.circuit_id if cdf.at[c, "install_date"].year < y and pd.isna(cdf.at[c, "disconnect_date"])]
    rng.shuffle(mature)
    disconnected = [c for c in circuits_df.circuit_id if pd.notna(cdf.at[c, "disconnect_date"]) and cdf.at[c, "disconnect_date"].month <= 9]
    rng.shuffle(disconnected)

    # 1. billed after disconnect
    for cid in pick(disconnected, counts["post_disconnect"]):
        vendor, service = cdf.at[cid, "vendor_id"], cdf.at[cid, "service"]
        for p in _month_range(_next_month(cdf.at[cid, "disconnect_date"]), year_end):
            rate = book.rate(vendor, service, true_jur[cid], p)
            idx = add_line(cid, vendor, p, "MRC", rate, rate, true_jur[cid])
            truth.append((lines[idx]["line_id"], "post_disconnect", rate))

    # 2. rate above contract (a run of months from a start month)
    rate_start: dict[str, date] = {}
    for cid in pick(mature, counts["rate_mismatch"]):
        start = date(y, int(rng.integers(3, 9)), 1)
        rate_start[cid] = start
        pct = float(rng.uniform(0.04, 0.14))
        for i in by_circuit[cid]:
            ln = lines[i]
            if ln["charge_type"] == "MRC" and ln["period"] >= start:
                expected = ln["amount"]
                ln["rate_billed"] = round(ln["rate_billed"] * (1 + pct), 2)
                ln["amount"] = ln["rate_billed"]
                truth.append((ln["line_id"], "rate_mismatch", round(ln["amount"] - expected, 2)))

    # 3. interstate rate billed on an intrastate circuit
    intra_pool = [c for c in mature if true_jur[c] == "intrastate"]
    for cid in pick(intra_pool, counts["jurisdiction_misrate"]):
        start = date(y, int(rng.integers(2, 9)), 1)
        for i in by_circuit[cid]:
            ln = lines[i]
            if ln["charge_type"] == "MRC" and ln["period"] >= start:
                expected = ln["amount"]
                inter = book.rate(ln["vendor_id"], cdf.at[cid, "service"], "interstate", ln["period"])
                ln["billed_jurisdiction"], ln["rate_billed"], ln["amount"] = "interstate", inter, inter
                truth.append((ln["line_id"], "jurisdiction_misrate", round(inter - expected, 2)))

    # 4. circuits that are billed but not in the inventory
    for k in range(counts["unknown_circuit"]):
        cid = f"CKT-{90001 + k}"
        vendor = str(rng.choice(vendor_ids))
        service = str(rng.choice(svc_names))
        start = date(y, int(rng.integers(2, 9)), 1)
        for p in _month_range(start, year_end):
            rate = book.rate(vendor, service, "intrastate", p)
            idx = add_line(cid, vendor, p, "MRC", rate, rate, "intrastate")
            truth.append((lines[idx]["line_id"], "unknown_circuit", rate))

    # 5. one-off charge spikes (rate unchanged, amount inflated)
    for cid in pick(mature, counts["spike"]):
        month = date(y, int(rng.integers(4, 13)), 1)
        for i in by_circuit[cid]:
            ln = lines[i]
            if ln["charge_type"] == "MRC" and ln["period"] == month:
                expected = ln["amount"]
                ln["amount"] = round(expected * float(rng.uniform(1.8, 3.2)), 2)
                truth.append((ln["line_id"], "spike", round(ln["amount"] - expected, 2)))

    # 6. legitimate usage overage on voice lines (must NOT be a confirmed error)
    voice_pool = [c for c in mature if cdf.at[c, "service"] == "VOICE"]
    for cid in pick(voice_pool, counts["usage_trap"]):
        month = date(y, int(rng.integers(4, 13)), 1)
        for i in by_circuit[cid]:
            ln = lines[i]
            if ln["charge_type"] == "MRC" and ln["period"] == month:
                ln["amount"] = round(ln["amount"] * float(rng.uniform(1.7, 2.6)), 2)

    # 7. duplicates of otherwise clean lines (the copy carries the later line id)
    clean_pool = [c for c in mature if c not in used]
    dup_circuits = pick(clean_pool, counts["duplicate"])
    for cid in dup_circuits:
        cand = [i for i in by_circuit[cid] if lines[i]["charge_type"] == "MRC"]
        src = dict(lines[int(rng.choice(cand))])
        idx = add_line(src["circuit_id"], src["vendor_id"], src["period"], src["charge_type"], src["rate_billed"], src["amount"], src["billed_jurisdiction"])
        truth.append((lines[idx]["line_id"], "duplicate", src["amount"]))

    # 8. duplicates of over-rate lines: two rules hit the copy, and the duplicate rule must win
    for cid in list(rate_start)[: counts["overlap_duplicate"]]:
        cand = [i for i in by_circuit[cid] if lines[i]["charge_type"] == "MRC" and lines[i]["period"] >= rate_start[cid]]
        src = dict(lines[int(rng.choice(cand))])
        idx = add_line(src["circuit_id"], src["vendor_id"], src["period"], src["charge_type"], src["rate_billed"], src["amount"], src["billed_jurisdiction"])
        truth.append((lines[idx]["line_id"], "duplicate", src["amount"]))

    # 9. regulatory surcharge above the tariff, three ways
    a_state_of = {r.circuit_id: state_of[r.a_npanxx] for r in circuits_df.itertuples()}
    decreasing = {s for s, delta in NECA_CHANGES.items() if delta < 0}
    subject_pool = [c for c in mature if cdf.at[c, "service"] in NECA_SUBJECT]

    def sur_lines(cid: str) -> list[dict]:
        return [lines[i] for i in by_circuit[cid] if lines[i]["charge_type"] == "SUR"]

    # (a) the percentage billed is too high
    for cid in pick(subject_pool, counts["surcharge_rate"]):
        start = date(y, int(rng.integers(2, 9)), 1)
        bump = float(rng.uniform(1.2, 3.5))
        svc = cdf.at[cid, "service"]
        for ln in sur_lines(cid):
            if ln["period"] >= start:
                rate = book.rate(ln["vendor_id"], svc, true_jur[cid], ln["period"])
                expected = ln["amount"]
                billed = round(rate * (tariff.pct(a_state_of[cid], svc, ln["period"]) + bump) / 100, 2)
                ln["amount"] = ln["rate_billed"] = billed
                truth.append((ln["line_id"], "surcharge_misrate", round(billed - expected, 2)))

    # (b) the vendor keeps billing the old percentage after a tariff decrease
    stale_pool = [c for c in subject_pool if a_state_of[c] in decreasing]
    for cid in pick(stale_pool, counts["surcharge_stale"]):
        svc = cdf.at[cid, "service"]
        for ln in sur_lines(cid):
            if ln["period"] >= date(y, 7, 1):
                rate = book.rate(ln["vendor_id"], svc, true_jur[cid], ln["period"])
                expected = ln["amount"]
                billed = round(rate * tariff.pct(a_state_of[cid], svc, date(y, 6, 1)) / 100, 2)
                ln["amount"] = ln["rate_billed"] = billed
                truth.append((ln["line_id"], "surcharge_misrate", round(billed - expected, 2)))

    # (c) a surcharge billed on a service the tariff exempts
    exempt_pool = [c for c in mature if cdf.at[c, "service"] in NECA_EXEMPT]
    for cid in pick(exempt_pool, counts["surcharge_exempt"]):
        start = date(y, int(rng.integers(2, 9)), 1)
        vendor, svc = cdf.at[cid, "vendor_id"], cdf.at[cid, "service"]
        share = float(rng.uniform(3.0, 6.0))
        for p in _month_range(start, year_end):
            amt = round(book.rate(vendor, svc, true_jur[cid], p) * share / 100, 2)
            idx = add_line(cid, vendor, p, "SUR", amt, amt, true_jur[cid])
            truth.append((lines[idx]["line_id"], "surcharge_misrate", amt))

    invoices = pd.DataFrame(lines).sort_values(["period", "vendor_id", "line_id"]).reset_index(drop=True)
    truth_df = pd.DataFrame(truth, columns=["line_id", "error_type", "true_overcharge"])

    # ---- prior-year dispute history ------------------------------------------
    rules = list(RULE_ACCEPT_P)
    hist = []
    for k in range(360):
        rule = str(rng.choice(rules))
        vendor = str(rng.choice(vendor_ids))
        amt = round(float(np.exp(rng.normal(6.3, 0.9))), 2)
        u = float(rng.random())
        p_acc = accept_probability(rule, vendor)
        if u < p_acc:
            outcome, pct = "accepted", 1.0
        elif u < p_acc + RULE_PARTIAL_P[rule]:
            outcome, pct = "partial", round(float(rng.uniform(0.4, 0.7)), 2)
        else:
            outcome, pct = "rejected", 0.0
        d = date(y - 1, 1, 10) + timedelta(days=int(rng.integers(0, 340)))
        hist.append((f"H-{k + 1:04d}", rule, vendor, amt, d, outcome, pct))
    history_df = pd.DataFrame(hist, columns=["history_id", "rule", "vendor_id", "amount", "filed_date", "outcome", "recovered_pct"])

    vendors_df = pd.DataFrame(VENDORS, columns=["vendor_id", "vendor_name", "dispute_window_months"])
    services_df = pd.DataFrame([(k, v) for k, v in SERVICES.items()], columns=["service", "list_rate"])

    # ---- write ---------------------------------------------------------------
    tables = {
        "vendors": vendors_df, "services": services_df, "circuits": circuits_df, "orders": orders_df,
        "contracts": contracts, "contract_clauses": clauses, "lerg_sim": lerg, "neca_sim": neca,
        "dispute_history": history_df, "ground_truth": truth_df,
    }
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    for (vendor, period), g in invoices.groupby(["vendor_id", "period"]):
        g.to_csv(out_dir / "invoices" / f"invoice_{vendor}_{period:%Y-%m}.csv", index=False)

    # Two deliberately broken files so the quality gate has something to reject.
    bad1 = invoices[(invoices.vendor_id == "V03") & (invoices.period == date(y, 9, 1))].head(25).drop(columns=["amount"])
    bad1.to_csv(out_dir / "invoices" / f"invoice_V03_{y}-09_reissue.csv", index=False)
    bad2 = invoices[(invoices.vendor_id == "V01") & (invoices.period == date(y, 10, 1))].head(40).copy()
    bad2["line_id"] = bad2["line_id"].iloc[0]
    bad2.loc[bad2.index[::2], "circuit_id"] = None
    bad2.loc[bad2.index[1::5], "amount"] = -abs(bad2["amount"].iloc[0])
    bad2["period"] = f"{y + 6}-01-01"
    bad2.to_csv(out_dir / "invoices" / f"invoice_V01_{y}-10_reissue.csv", index=False)

    tables["invoices"] = invoices
    return tables
