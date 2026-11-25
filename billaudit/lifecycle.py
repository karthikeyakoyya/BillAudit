"""Dispute lifecycle: detected, reviewed, filed, vendor response, credit.

The tracker enforces legal transitions and keeps an event log, so aging and win
rates are computed from what happened rather than from a status column alone.
Vendor answers are simulated (see sim_params.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import Config
from .sim_params import (CREDIT_LAG_DAYS, REJECTION_REASONS, VENDOR_RESPONSE_DAYS,
                         accept_probability, RULE_PARTIAL_P)

TRANSITIONS = {
    "detected": {"reviewed", "deferred", "time_barred"},
    "reviewed": {"filed", "deferred"},
    "filed": {"accepted", "partial", "rejected"},
    "accepted": {"credited"},
    "partial": {"credited"},
    "deferred": {"reviewed"},
    "rejected": set(),
    "credited": set(),
    "time_barred": set(),
}


class IllegalTransition(ValueError):
    pass


class ClaimTracker:
    def __init__(self, claim_ids: list[str], opened: date):
        self.status = {c: "detected" for c in claim_ids}
        self.events: list[dict] = [
            {"claim_id": c, "event_date": opened, "from_status": None, "to_status": "detected", "note": "Flagged by audit"}
            for c in claim_ids
        ]

    def move(self, claim_id: str, to: str, on: date, note: str = "") -> None:
        cur = self.status[claim_id]
        if to not in TRANSITIONS[cur]:
            raise IllegalTransition(f"{claim_id}: {cur} -> {to}")
        self.status[claim_id] = to
        self.events.append({"claim_id": claim_id, "event_date": on, "from_status": cur, "to_status": to, "note": note})

    def events_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.events)


def _aging_bucket(days: int) -> str:
    return "0-30 days" if days <= 30 else ("31-60 days" if days <= 60 else "61+ days")


def run_cycle(ranked: pd.DataFrame, cfg: Config):
    """File the claims marked 'file', play out vendor responses, and cut the
    tracker at the report date. Returns (claims, events)."""
    rng = np.random.default_rng(cfg.seed + 1)
    opened = cfg.as_of
    report_date = opened + timedelta(days=cfg.report_days_after)
    tracker = ClaimTracker(ranked["claim_id"].tolist(), opened)

    cols = ["filed_date", "response_date", "response_outcome", "reject_reason", "credit_pct", "aging_days"]
    extra = {c: [None] * len(ranked) for c in cols}
    ranked = ranked.copy()
    filed_seq = 0
    for i, r in enumerate(ranked.itertuples()):
        cid = r.claim_id
        if r.decision == "time_barred":
            tracker.move(cid, "time_barred", opened, "All billed periods are outside the vendor's dispute window")
            continue
        if r.decision in ("below_threshold", "defer_capacity"):
            why = "Claimable value below filing threshold" if r.decision == "below_threshold" else "Over this cycle's filing capacity"
            tracker.move(cid, "deferred", opened, why)
            continue

        filed_seq += 1
        reviewed_on = opened + timedelta(days=1 + (filed_seq - 1) // 8)
        filed_on = reviewed_on + timedelta(days=1)
        tracker.move(cid, "reviewed", reviewed_on, "Evidence pack checked")
        tracker.move(cid, "filed", filed_on, f"Dispute filed with {r.vendor_name}")
        extra["filed_date"][i] = filed_on

        mean = VENDOR_RESPONSE_DAYS[r.vendor_id]
        lag = max(5, int(rng.gamma(4.0, mean / 4.0)))
        answered_on = filed_on + timedelta(days=lag)
        if answered_on > report_date:
            extra["aging_days"][i] = (report_date - filed_on).days
            continue

        u = float(rng.random())
        p_acc = accept_probability(r.rule, r.vendor_id)
        if u < p_acc:
            outcome, pct, note = "accepted", 1.0, "Vendor accepted in full"
        elif u < p_acc + RULE_PARTIAL_P[r.rule]:
            outcome, pct = "partial", round(float(rng.uniform(0.4, 0.7)), 2)
            note = f"Vendor accepted {int(pct * 100)} percent"
        else:
            outcome, pct = "rejected", 0.0
            reason = str(rng.choice(REJECTION_REASONS[r.rule]))
            extra["reject_reason"][i] = reason
            note = f"Vendor rejected: {reason}"
        tracker.move(cid, outcome, answered_on, note)
        extra["response_date"][i], extra["response_outcome"][i], extra["credit_pct"][i] = answered_on, outcome, pct
        if outcome != "rejected":
            credited_on = answered_on + timedelta(days=CREDIT_LAG_DAYS)
            if credited_on <= report_date:
                tracker.move(cid, "credited", credited_on, "Credit applied on a later invoice")

    for c in cols:
        ranked[c] = extra[c]
    for c in ("filed_date", "response_date"):
        ranked[c] = pd.to_datetime(ranked[c])
    for c in ("credit_pct", "aging_days"):
        ranked[c] = pd.to_numeric(ranked[c])
    ranked["reject_reason"] = ranked["reject_reason"].astype("object")
    ranked["response_outcome"] = ranked["response_outcome"].astype("object")
    ranked["status"] = ranked["claim_id"].map(tracker.status)
    pct = ranked["credit_pct"].fillna(0.0).astype(float)
    ranked["credit_amount"] = np.where(ranked["status"] == "credited", (ranked["claimable_amount"] * pct).round(2), 0.0)
    ranked["credit_pending"] = np.where(ranked["status"].isin(["accepted", "partial"]), (ranked["claimable_amount"] * pct).round(2), 0.0)
    ranked["aging_bucket"] = [
        _aging_bucket(int(a)) if (s == "filed" and a is not None and not pd.isna(a)) else None
        for s, a in zip(ranked["status"], ranked["aging_days"])
    ]
    return ranked, tracker.events_df(), report_date
