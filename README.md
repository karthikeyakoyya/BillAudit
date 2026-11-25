# BillAudit

Audits monthly telecom invoices against inventory, orders, contracts and a tariff table, turns the findings into dispute claims, ranks the claims by expected recovery, and tracks them from filing to credit.

The data is simulated. Vendors, rates, circuits, contracts, the LERG-style and NECA-style lookup tables are all generated from a seed. The data generator also injects a known set of billing errors and writes them to an answer key, so the audit rules can be scored on what they catch, what they miss and what they wrongly flag.

## Run it

```bash
pip install -r requirements.txt
python run.py demo              # generate data, audit, write reports to outputs/
python -m pytest                # 44 tests (the dashboard test needs Node: cd tests/js && npm install)
python run.py regress           # re-score the rules on the golden dataset
Rscript r/verify_totals.R       # optional: independent check of the totals in R
```

Tested on Python 3.12 with pandas 2.3 and 3.0, and DuckDB 1.1 and 2.0. `outputs/` in this zip is the result of one `python run.py demo` run, so the files can be opened without running anything.

## Data

| Table | Contents |
|---|---|
| Invoice lines | 11,427 lines over 12 months, one CSV per vendor and month: monthly recurring (MRC), one-time install (NRC) and regulatory surcharge (SUR) charges |
| Inventory and orders | 600 circuits with install and disconnect orders |
| Contracts and clauses | Rates by vendor, service and jurisdiction with effective dates (two mid-year amendments), plus clause text per vendor |
| LERG-style lookup | NPA-NXX to state, used to decide whether a circuit is intrastate or interstate |
| NECA-style tariff | Regulatory surcharge percentage by originating state and service. Two services are exempt. Four states change their percentage on 1 July |
| Dispute history | 360 simulated prior-year disputes, used to estimate recovery rates by rule |

## What it does

1. **Quality gate.** Each invoice file is checked for required columns, nulls, dates, negative amounts, duplicate line ids and a vendor/period that matches the file name. Files that fail structure or have more than 2% bad rows are rejected with a reason. Fewer bad rows are quarantined and the rest go on. The sample data includes two deliberately broken files.
2. **Seven SQL rules** (DuckDB, one file each in `sql/rules/`). A line that trips several rules is kept once, under the highest-priority rule, so a charge is never counted twice.

   | Rule | Flags | Overcharge estimate |
   |---|---|---|
   | Billed, not in inventory | Billed circuit that is not in the inventory | Whole amount |
   | Billed after disconnect | Monthly charge for a period after the disconnect month | Whole amount |
   | Duplicate charge | Same vendor, circuit, period, type and amount again | Whole amount of the copy |
   | Wrong jurisdiction rate | Rate for the other jurisdiction than the circuit's two ends call for | Billed less contract amount |
   | Rate above contract | Rate above the contract rate in force that month | Billed less contract amount |
   | Surcharge above tariff | Surcharge percentage above the tariff for the circuit's state and service, including any surcharge on an exempt service | Billed less amount at the tariff percentage |
   | Charge spike | Amount above 1.5x the circuit's own median, rate unchanged | Amount less median |

   Contract rates and tariff percentages are picked by effective date, so a mid-year amendment or tariff change is not an overcharge. Install fees, prorated first months and the disconnect month itself are billed legitimately and are left alone.
3. **Claims.** Findings roll up to one claim per vendor, circuit and rule, so an error that repeats for eight months is one claim with a lookback. Each vendor has its own dispute window (6, 9, 12 and 12 months). Periods older than the window are counted as time-barred and left out of the claimable amount.
4. **Ranking.** Expected value = claimable amount x the rule's recovery rate from the simulated prior-year history (smoothed toward 50% with the weight of two past claims). The team files the top claims up to a capacity (45 by default), skipping any under $150.
5. **Lifecycle.** Claims move through detected, reviewed, filed, accepted / partial / rejected, credited. Illegal moves raise an error, and every move is logged with a date. Vendor answers are simulated with different accept rates and response times per vendor. Rejected claims carry a reason. At the cut-off date, unanswered claims are aged in buckets.
6. **Evidence and notes.** Every filed claim gets an evidence sheet in the workbook (invoice lines, expected amounts, orders, contract rates or tariff rows, clauses, live total) and a draft dispute note in `outputs/dispute_notes/`. The clause lookup is a mapping from rule to clause type over a generated clause table.

## Outputs

| File | Contents |
|---|---|
| `outputs/dispute_workbook.xlsx` | Summary (formulas over the Claims sheet), ranked claims, lifecycle, event log, rule scores, line-level findings, data-quality gate, one evidence sheet per filed claim |
| `outputs/dashboard.html` | One-file dashboard with inline SVG charts. Sticky section nav (menu button on phones), skip link, system/light/dark theme switch, reading progress bar, back-to-top, filter box and status filter on the filed-claims table, copy buttons for claim ids, expandable notes, print stylesheet. No network requests |
| `outputs/billaudit.duckdb` | Raw tables plus claims, events and findings, ready for SQL (`sql/analyst_queries.sql`) |
| `outputs/dispute_notes/` | One draft note per filed claim |
| `outputs/*.csv` | Flat exports of findings, claims, rule totals and the quality report |

## Results from the included run

Seed 42, 600 circuits, 11,427 invoice lines audited, 2 files rejected by the gate.

- 1,049 flagged lines became 221 claims worth $188,856. $173,784 is inside dispute windows and $15,072 is time-barred.
- 45 claims were filed ($128,928 claimable, $90,312 expected). At the cut-off date, 18 had a credit applied ($33,732), 6 were accepted in full or part and waiting for the credit ($13,857), 11 were rejected and 10 had no answer.
- Six rules caught every injected error with no false flags, including the surcharge rule (204 of 204 lines). The spike rule also caught every injected spike but flagged 12 legitimate usage overages on voice lines, so its precision is 71% (30 of 42).
- The 26 surcharge claims total only $1,908 claimable. Most are under the $150 filing threshold, so none were filed in this run. The finding is real, but each circuit's surcharge error is small.
- Predicted recovery rates from the prior-year history were off by 12 points for duplicates (81% predicted, 69% actual), 13 for post-disconnect (75% vs 62%) and 29 for not-in-inventory (61% vs 32%). Counts are small (6 to 20 answered claims per rule), so these gaps are noisy.

## Changing a rule safely

`python run.py regress` generates a fixed golden dataset (seed 2024), runs the rules, and compares precision and recall per rule with `golden/baseline.json`. It exits non-zero if any rule drops by more than 2 points. Edit a rule file, or copy `sql/rules/` and point at it with `--rules-dir`, then run it.

Example: `python run.py regress --spike-multiplier 2.2` raises spike precision from 71% to 92% but drops recall from 100% to 73%, and the harness reports it as a regression. `--update-baseline` accepts a deliberate change.

## Optional pieces

- **Claude-polished notes.** `python run.py audit --llm` sends each template note to the Claude API (needs `ANTHROPIC_API_KEY` and `pip install anthropic`; model from `BILLAUDIT_MODEL`). The reply is used only if every number in it already appears in the template note, otherwise the template note is kept. The validation and fallback are covered by tests with a stub client. The live API call itself has not been exercised in this repository's tests.
- **R cross-check.** `r/verify_totals.R` recomputes the rule totals, the claim roll-up, the claimable/barred split and the expected values from the CSV exports using base R, and exits non-zero on any mismatch.

## Limits

- Simulated data throughout. The LERG-style and NECA-style tables have the same lookup shape as the real ones (NPA-NXX to state, state and service to surcharge percentage) but are invented, not the licensed or filed data.
- One invoice year, one currency, and three charge types. No usage or per-call billing.
- The answer key tests the rules against errors this generator creates. Real vendor errors are messier.
- Vendor behaviour after filing is a simulation. Win rates and response times are parameters in `billaudit/sim_params.py`, not observations.
- The spike rule cannot tell a real surcharge from a usage overage using amounts alone.
- Small recurring errors (surcharges, rate differences) are claimed per circuit. A real team might batch them per vendor. This project does not.
- No Alteryx or KNIME workflow is included.

## Layout

```
billaudit/        generate, quality, ingest, db, rules, rollup, ranking, lifecycle,
                  evidence, research, notes, harness, report_xlsx, report_html, pipeline, cli
sql/00_views.sql  reference views (true jurisdiction, contract rate and tariff percentage by period)
sql/rules/        the seven audit rules
sql/analyst_queries.sql
r/verify_totals.R
golden/baseline.json
tests/            44 tests; tests/js has the dashboard behaviour checks (jsdom)
data/             generated dataset and answer key
outputs/          results of one run
```
