-- Queries to run against outputs/billaudit.duckdb after an audit.
-- With the DuckDB CLI: duckdb -readonly outputs/billaudit.duckdb < sql/analyst_queries.sql

-- 1. Filed value and credits by vendor and rule
SELECT vendor_id, rule,
       count(*) AS filed_claims,
       round(sum(claimable_amount), 2) AS claimable,
       round(sum(credit_amount), 2) AS credited,
       round(sum(credit_pending), 2) AS accepted_not_yet_credited
FROM claims
WHERE decision = 'file'
GROUP BY vendor_id, rule
ORDER BY vendor_id, claimable DESC;

-- 2. Filed claims still waiting on the vendor, oldest first
SELECT claim_id, vendor_id, circuit_id, rule, claimable_amount, filed_date, aging_days, aging_bucket
FROM claims
WHERE status = 'filed'
ORDER BY aging_days DESC;

-- 3. This cycle's answer rate by rule against what the history predicted
SELECT rule,
       count(*) AS answered,
       round(avg(recovery_rate), 3) AS predicted_rate,
       round(avg(coalesce(credit_pct, 0)), 3) AS actual_rate
FROM claims
WHERE decision = 'file' AND response_outcome IS NOT NULL
GROUP BY rule
ORDER BY rule;

-- 4. Highest-value claims left unfiled this cycle
SELECT claim_id, vendor_id, circuit_id, rule, claimable_amount, expected_value, decision
FROM claims
WHERE decision IN ('defer_capacity', 'below_threshold')
ORDER BY expected_value DESC
LIMIT 15;

-- 5. Value already lost to dispute windows, by vendor
SELECT vendor_id, window_months, count(*) AS claims_affected, round(sum(barred_amount), 2) AS time_barred
FROM claims
WHERE barred_amount > 0
GROUP BY vendor_id, window_months
ORDER BY time_barred DESC;

-- 6. Average days from filing to vendor answer
SELECT vendor_id,
       count(*) AS answered,
       round(avg(date_diff('day', filed_date, response_date)), 1) AS avg_days_to_answer
FROM claims
WHERE response_date IS NOT NULL
GROUP BY vendor_id
ORDER BY avg_days_to_answer;

-- 7. Rejection reasons
SELECT rule, reject_reason, count(*) AS n, round(sum(claimable_amount), 2) AS value
FROM claims
WHERE status = 'rejected'
GROUP BY rule, reject_reason
ORDER BY value DESC;
