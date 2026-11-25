"""Dispute note drafts.

The note is built from a template using only evidence fields. An LLM can be
asked to polish the wording (opt-in, needs ANTHROPIC_API_KEY and the
anthropic package), but its output is accepted only if every number in it
already appears in the template note. Otherwise the template note is used.
"""
from __future__ import annotations

import os
import re

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _money(x: float) -> str:
    return f"${x:,.2f}"


def template_note(ev: dict) -> str:
    c = ev["claim"]
    lines = ev["lines"]
    claim_lines = lines[lines.claimable]
    first, last = claim_lines["period"].min(), claim_lines["period"].max()
    span = f"the period {first}" if first == last else f"the periods {first} to {last}"
    ids = claim_lines["line_id"].tolist()
    shown = ", ".join(ids[:8]) + (f" and {len(ids) - 8} more" if len(ids) > 8 else "")
    out = [
        f"To: {c['vendor_name']} Billing Disputes",
        f"Subject: Dispute {c['claim_id']} - circuit {c['circuit_id']} - {ev['rule_label'].lower()}",
        "",
        f"We are disputing {len(claim_lines)} invoice line(s) on circuit {c['circuit_id']} for {span}, "
        f"totalling {_money(c['claimable_amount'])}.",
        f"Invoice lines: {shown}.",
        "",
        "What we found:",
        _finding_sentence(ev),
        "",
        "Basis:",
    ]
    for cl in ev["clauses"]:
        out.append(f"- {cl['clause_ref']} ({cl['category'].replace('_', ' ')}): {cl['text']}")
    out += [
        "",
        "Please issue a credit of " + _money(c["claimable_amount"]) + " or reply with the records that support the charges. "
        "The calculation for each line is in the attached evidence sheet.",
    ]
    if c["barred_amount"] > 0:
        out.append(f"Earlier periods ({_money(c['barred_amount'])}) fall outside the {int(c['window_months'])}-month dispute window and are not included.")
    return "\n".join(out)


def _finding_sentence(ev: dict) -> str:
    c, rule = ev["claim"], ev["claim"]["rule"]
    lines = ev["lines"]
    one = lines.iloc[0]
    if rule == "unknown_circuit":
        return f"Circuit {c['circuit_id']} appears on your invoices but is not in our service inventory."
    if rule == "post_disconnect":
        d = ev["orders"][ev["orders"].order_type == "disconnect"]
        eff = d["effective_date"].iloc[0] if len(d) else "the disconnect date on record"
        return f"A disconnect order for this circuit took effect on {eff}. Charges continued after that month."
    if rule == "duplicate":
        return "The same charge was billed more than once for the same circuit and period."
    if rule == "jurisdiction_misrate":
        return (f"The circuit is {ev['circuit']['true_jurisdiction']} (both ends in {ev['circuit']['a_state']}"
                f"{'' if ev['circuit']['a_state'] == ev['circuit']['z_state'] else ' and ' + str(ev['circuit']['z_state'])}) "
                f"but was billed at the other jurisdiction's rate. Contract rate {_money(one['contract_rate'])}, billed {_money(one['rate_billed'])}.")
    if rule == "surcharge_misrate":
        state, svc = ev["circuit"]["a_state"], ev["circuit"]["service"]
        if float(one["tariff_pct"]) == 0:
            return f"{svc} service originating in {state} is exempt from the regulatory surcharge under the tariff, but a surcharge was billed ({one['billed_pct']} percent of the monthly charge)."
        return (f"The regulatory surcharge was billed at {one['billed_pct']} percent of the monthly charge. "
                f"The tariff rate for {svc} service originating in {state} is {one['tariff_pct']} percent for the period.")
    if rule == "rate_mismatch":
        return f"The rate billed is above the contract rate in force for the period. Contract rate {_money(one['contract_rate'])}, billed {_money(one['rate_billed'])}."
    return "The charge is well above this circuit's usual monthly charge and no rate change or surcharge notice is on file."


def validate_llm_text(text: str, template: str) -> bool:
    allowed = set(NUMBER.findall(template))
    return all(n in allowed for n in NUMBER.findall(text))


def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:
        return None


def draft_note(ev: dict, use_llm: bool = False, client=None) -> tuple[str, str]:
    """Return (text, source) where source is 'template' or 'llm'."""
    base = template_note(ev)
    if not use_llm:
        return base, "template"
    client = client or get_client()
    if client is None:
        return base, "template"
    try:
        resp = client.messages.create(
            model=os.environ.get("BILLAUDIT_MODEL", "claude-sonnet-5-5"),
            max_tokens=700,
            system=("Rewrite the dispute note so it reads clearly to a vendor billing team. Keep every fact and number exactly as given. "
                    "Do not add numbers, dates, clauses or claims that are not in the draft. Return only the note."),
            messages=[{"role": "user", "content": base}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception:
        return base, "template"
    return (text, "llm") if text and validate_llm_text(text, base) else (base, "template")
