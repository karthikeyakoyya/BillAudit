"""Command line: generate data, run an audit, run the regression harness."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .config import GOLDEN, ROOT, Config
from .generate import generate
from .harness import compare, golden_scores, load_baseline, save_baseline
from .pipeline import run_audit

BASELINE = ROOT / "golden" / "baseline.json"


def _money(x) -> str:
    return f"${x:,.0f}"


def cmd_generate(a) -> int:
    cfg = replace(Config(), seed=a.seed, n_circuits=a.circuits)
    t = generate(cfg, Path(a.data_dir))
    print(f"Wrote {len(t['invoices']):,} invoice lines, {len(t['circuits'])} circuits to {a.data_dir}")
    return 0


def cmd_audit(a) -> int:
    cfg = Config()
    overrides = {k: v for k, v in {
        "capacity": a.capacity, "spike_multiplier": a.spike_multiplier, "min_claim_value": a.min_claim_value,
    }.items() if v is not None}
    cfg = replace(cfg, **overrides)
    res = run_audit(cfg, Path(a.data_dir), Path(a.out_dir), Path(a.rules_dir) if a.rules_dir else None, use_llm=a.llm)
    c, m = res["claims"], res["meta"]
    filed = c[c.decision == "file"]
    print(f"Lines audited      {m['lines_loaded']:,}")
    rej = res["dq"][res["dq"].status == "rejected"]
    print(f"Files rejected     {len(rej)}  ({', '.join(rej.file)})" if len(rej) else "Files rejected     0")
    print(f"Findings           {len(res['findings']):,} lines, {len(c)} claims ({res['raw_hits'] - len(res['findings'])} overlapping hits removed)")
    print(f"Flagged value      {_money(c.total_overcharge.sum())}   inside windows {_money(c.claimable_amount.sum())}   time-barred {_money(c.barred_amount.sum())}")
    print(f"Filed              {len(filed)} claims, {_money(filed.claimable_amount.sum())}, expected {_money(filed.expected_value.sum())}")
    print(f"Credits received   {_money(c.credit_amount.sum())}   pending credit {_money(c.credit_pending.sum())}   unanswered {int((c.status == 'filed').sum())}")
    if len(res["rule_perf"]):
        print("\nRule scores against the answer key")
        print(res["rule_perf"][["rule", "injected", "flagged", "precision", "recall"]].to_string(index=False))
    print(f"\nOutputs in {res['out_dir']}")
    return 0


def cmd_regress(a) -> int:
    cfg = replace(GOLDEN, **({"spike_multiplier": a.spike_multiplier} if a.spike_multiplier is not None else {}))
    now = golden_scores(Path(a.rules_dir) if a.rules_dir else None, cfg)
    if a.update_baseline:
        save_baseline(now, BASELINE)
        print(f"Baseline written to {BASELINE}")
        print(now[["rule", "injected", "flagged", "precision", "recall"]].to_string(index=False))
        return 0
    table, ok = compare(now, load_baseline(BASELINE), a.tolerance)
    pd.set_option("display.width", 200)
    print(table.to_string(index=False))
    print("\nPASS: no rule lost precision or recall beyond tolerance" if ok else "\nFAIL: a rule regressed beyond tolerance")
    return 0 if ok else 1


def cmd_demo(a) -> int:
    cmd_generate(argparse.Namespace(data_dir=a.data_dir, seed=42, circuits=600))
    return cmd_audit(argparse.Namespace(data_dir=a.data_dir, out_dir=a.out_dir, capacity=None, spike_multiplier=None,
                                        min_claim_value=None, rules_dir=None, llm=False))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="billaudit", description="Telecom invoice audit and dispute tracker (simulated data)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="create a synthetic dataset")
    g.add_argument("--data-dir", default=str(ROOT / "data"))
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--circuits", type=int, default=600)
    g.set_defaults(fn=cmd_generate)

    r = sub.add_parser("audit", help="run the audit and write reports")
    r.add_argument("--data-dir", default=str(ROOT / "data"))
    r.add_argument("--out-dir", default=str(ROOT / "outputs"))
    r.add_argument("--rules-dir", default=None, help="folder of rule .sql files to use instead of sql/rules")
    r.add_argument("--capacity", type=int, default=None, help="claims the team can file this cycle")
    r.add_argument("--spike-multiplier", type=float, default=None)
    r.add_argument("--min-claim-value", type=float, default=None)
    r.add_argument("--llm", action="store_true", help="polish dispute notes with Claude (needs ANTHROPIC_API_KEY)")
    r.set_defaults(fn=cmd_audit)

    x = sub.add_parser("regress", help="re-score the rules on the golden dataset and compare with the baseline")
    x.add_argument("--rules-dir", default=None)
    x.add_argument("--spike-multiplier", type=float, default=None)
    x.add_argument("--tolerance", type=float, default=0.02)
    x.add_argument("--update-baseline", action="store_true")
    x.set_defaults(fn=cmd_regress)

    d = sub.add_parser("demo", help="generate data and run the audit with defaults")
    d.add_argument("--data-dir", default=str(ROOT / "data"))
    d.add_argument("--out-dir", default=str(ROOT / "outputs"))
    d.set_defaults(fn=cmd_demo)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
