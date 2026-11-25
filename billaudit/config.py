"""Run settings. Everything that changes an audit outcome lives here."""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Order matters: when one invoice line trips several rules, the first rule wins,
# so a single charge is never counted twice in a claim.
RULE_PRIORITY = [
    "unknown_circuit",
    "post_disconnect",
    "duplicate",
    "jurisdiction_misrate",
    "rate_mismatch",
    "surcharge_misrate",
    "spike",
]

RULE_LABELS = {
    "unknown_circuit": "Billed, not in inventory",
    "post_disconnect": "Billed after disconnect",
    "duplicate": "Duplicate charge",
    "jurisdiction_misrate": "Wrong jurisdiction rate",
    "rate_mismatch": "Rate above contract",
    "surcharge_misrate": "Surcharge above tariff",
    "spike": "Unexplained charge spike",
}


@dataclass(frozen=True)
class Config:
    seed: int = 42
    n_circuits: int = 600
    year: int = 2025
    # Date the audit runs. Dispute windows are measured back from here.
    as_of: date = date(2026, 1, 31)
    # The tracker report is cut this many days after filing starts.
    report_days_after: int = 45
    # Spike rule: charge must exceed this multiple of the circuit's own median
    # MRC, have at least this many prior months, and exceed it by this many dollars.
    spike_multiplier: float = 1.5
    spike_min_history: int = 3
    spike_min_abs: float = 25.0
    # Claims below this claimable value are not worth an analyst's time.
    min_claim_value: float = 150.0
    # Claims the team can file in one cycle.
    capacity: int = 45
    rules_dir: Path = field(default_factory=lambda: ROOT / "sql" / "rules")
    sql_dir: Path = field(default_factory=lambda: ROOT / "sql")

    def rule_params(self) -> dict:
        return {
            "spike_multiplier": self.spike_multiplier,
            "spike_min_history": self.spike_min_history,
            "spike_min_abs": self.spike_min_abs,
        }


# Fixed, smaller dataset used by the regression harness. Never change the seed
# without regenerating golden/baseline.json.
GOLDEN = Config(seed=2024, n_circuits=300)
