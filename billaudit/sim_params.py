"""Behaviour of the simulated vendors. Used to build the prior-year dispute
history and to play out vendor responses during a run.

The audit ranks claims from the history only (per-rule recovery rate). The
vendor modifiers below are *not* visible to the ranking step, so the report can
show where predicted and actual recovery drift apart.
"""

# Chance a vendor accepts a claim in full, by rule.
RULE_ACCEPT_P = {
    "duplicate": 0.86,
    "post_disconnect": 0.70,
    "rate_mismatch": 0.62,
    "surcharge_misrate": 0.58,
    "unknown_circuit": 0.45,
    "jurisdiction_misrate": 0.38,
    "spike": 0.20,
}
# Chance of a partial credit (40 to 70 percent of the claim).
RULE_PARTIAL_P = {
    "duplicate": 0.06,
    "post_disconnect": 0.10,
    "rate_mismatch": 0.12,
    "surcharge_misrate": 0.12,
    "unknown_circuit": 0.12,
    "jurisdiction_misrate": 0.12,
    "spike": 0.12,
}
VENDOR_ACCEPT_MOD = {"V01": 0.90, "V02": 1.00, "V03": 1.08, "V04": 0.80}
# Mean days a vendor takes to answer a filed claim.
VENDOR_RESPONSE_DAYS = {"V01": 22, "V02": 34, "V03": 52, "V04": 28}
# Days between a vendor accepting and the credit appearing on an invoice.
CREDIT_LAG_DAYS = 12

REJECTION_REASONS = {
    "duplicate": ["Credit already issued on a later invoice", "Line is a valid reissue of a corrected invoice"],
    "post_disconnect": ["Disconnect order not received before vendor cutoff", "Early termination liability applies"],
    "rate_mismatch": ["Contract amendment applies to this circuit", "Rate protection period has expired"],
    "unknown_circuit": ["Circuit belongs to a different account", "Vendor could not locate circuit in customer records"],
    "jurisdiction_misrate": ["Vendor jurisdiction records differ from customer records"],
    "surcharge_misrate": ["Tariff change not yet effective for this account", "Surcharge reflects a state-specific rider"],
    "spike": ["Usage charges apply under tariff", "One-time surcharge per service terms"],
}


def accept_probability(rule: str, vendor_id: str) -> float:
    return min(0.95, RULE_ACCEPT_P[rule] * VENDOR_ACCEPT_MOD[vendor_id])
