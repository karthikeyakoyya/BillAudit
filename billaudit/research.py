"""Find the contract clauses that back a claim."""
from __future__ import annotations

import pandas as pd

RULE_CLAUSES = {
    "unknown_circuit": ["inventory"],
    "post_disconnect": ["disconnect"],
    "duplicate": ["duplicate_billing"],
    "jurisdiction_misrate": ["jurisdiction", "rates"],
    "rate_mismatch": ["rates"],
    "surcharge_misrate": ["regulatory_surcharge"],
    "spike": ["surcharge", "rates"],
}


def clauses_for(rule: str, vendor_id: str, clauses: pd.DataFrame) -> list[dict]:
    """Clauses that support the rule, plus the vendor's dispute procedure."""
    wanted = RULE_CLAUSES.get(rule, []) + ["dispute_procedure"]
    sub = clauses[(clauses.vendor_id == vendor_id) & (clauses.category.isin(wanted))]
    sub = sub.assign(_o=sub.category.map({c: i for i, c in enumerate(wanted)})).sort_values("_o")
    return sub[["category", "clause_ref", "text"]].to_dict("records")
